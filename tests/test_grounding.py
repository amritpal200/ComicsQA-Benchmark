"""Character grounding: matching, output parsing and linking; human export conversion.
No model or GPU (stdlib + Pillow)."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src/comics_qa/annotations"
sys.path.insert(0, str(ROOT / "magi3_grounding"))
sys.path.insert(0, str(ROOT / "magi3"))


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


matching = load("matching", ROOT / "magi3_grounding/matching.py")
grounding = load("run_grounding", ROOT / "magi3_grounding/run_grounding.py")
export = load("export_human", ROOT / "human/export_human.py")


class MatchingTest(unittest.TestCase):
    def test_iou(self):
        self.assertAlmostEqual(matching.iou([0, 0, 10, 10], [5, 0, 15, 10]), 50 / 150)
        self.assertEqual(matching.iou([0, 0, 1, 1], [2, 2, 3, 3]), 0.0)

    def test_hungarian_beats_greedy(self):
        # greedy would give row0->col0 (0.9) and row1->nothing useful (0.1); optimum is 0.8+0.85
        w = [[0.9, 0.8], [0.85, 0.1]]
        self.assertEqual(matching.hungarian_max(w), {0: 1, 1: 0})
        self.assertEqual(matching.hungarian_max([[0.2], [0.7], [0.1]]), {1: 0})   # more rows than cols
        self.assertEqual(matching.hungarian_max([[0.1, 0.9, 0.3]]), {0: 1})

    def test_merge_near_duplicates(self):
        boxes = [[0, 0, 10, 10], [0, 0, 10, 11], [50, 50, 60, 60]]
        entities, owner = matching.merge_boxes(boxes, 0.8)
        self.assertEqual(len(entities), 2)
        self.assertEqual(owner, [0, 0, 1])

    def test_match_statuses(self):
        entities = [[0, 0, 10, 10], [100, 100, 110, 110], [50, 0, 60, 10]]
        refs = [("a", [0, 0, 10, 10]), ("b", [0.5, 0, 10.5, 10]), ("c", [50, 0, 58, 10])]   # IoU(e0,b)=0.905
        results = matching.match_entities(entities, refs, min_iou=0.5, margin=0.1)
        self.assertEqual(results[1]["status"], "unmatched")
        self.assertEqual(results[2], {"status": "matched", "ref": "c", "iou": 0.8, "second_iou": 0.0})
        self.assertEqual(results[0]["status"], "ambiguous")      # a and b overlap almost equally
        self.assertEqual(matching.match_entities(entities, [], 0.5, 0.1)[0]["status"], "unmatched")


class GroundingTest(unittest.TestCase):
    def test_phrases_spans_and_page_coordinates(self):
        out = {"grounded_caption": "A boy waves. He smiles.",
               "bboxes": [[[1, 2, 11, 12]], [[1, 2, 11, 12]], [[5, 5, 6, 6]]],
               "indices_of_bboxes_in_caption": [(0, 5), (13, 15), (23, 23)]}
        phrases = grounding.phrases_from_output(out, [100, 200, 300, 400])
        self.assertEqual([p["text"] for p in phrases], ["A boy", "He", ""])
        self.assertEqual(phrases[2]["kind"], "box_only")
        self.assertEqual(phrases[0]["boxes_page"], [[101.0, 202.0, 111.0, 212.0]])

    def test_spans_mapped_back_to_original_caption(self):
        caption = "A tall man, smiling, greets a girl."
        grounded = "A tall man smiling, greets a girl."          # MAGI v3 dropped a comma
        phrases = [{"span": [0, 10], "kind": "phrase"}, {"span": [27, 33], "kind": "phrase"}]
        grounding.map_spans_to_caption(phrases, grounded, caption)
        self.assertEqual([p["text_in_caption"] for p in phrases], ["A tall man", "a girl"])
        self.assertEqual(phrases[0]["span_in_caption"], [0, 10])
        self.assertEqual(phrases[1]["span_in_caption"], [28, 34])

    def test_box_only_phrases_reconstructed(self):
        caption = ("In the foreground, a boy with spiky hair waves, and a girl in a coat smiles. "
                   "To his right, she points.")
        ends = [caption.index(" waves"), caption.index(" smiles"), caption.index(" right"),
                caption.index(" points")]
        phrases = [{"span": [e, e], "kind": "box_only"} for e in ends]
        grounding.map_spans_to_caption(phrases, caption, caption)
        self.assertEqual([p["text_in_caption"] for p in phrases],
                         ["a boy with spiky hair", "a girl in a coat", "his", "she"])
        self.assertTrue(all(p["reconstructed"] for p in phrases))

    def test_box_after_locative_refers_to_following_phrase(self):
        caption = "On the far right, a girl with light hair smiles."
        anchor = caption.index(" a girl")
        phrases = [{"span": [anchor, anchor], "kind": "box_only"}]
        grounding.map_spans_to_caption(phrases, caption, caption)
        self.assertEqual(phrases[0]["text_in_caption"], "a girl")
        self.assertEqual(phrases[0]["phrase_direction"], "after")
        self.assertEqual(phrases[0]["anchor_in_caption"], anchor)

    def test_named_caption_inserts_names_at_anchors(self):
        caption = "A boy waves at a girl. He smiles."
        phrases = [{"anchor_in_caption": 5, "entity_ids": [0]}, {"anchor_in_caption": 21, "entity_ids": [1]},
                   {"anchor_in_caption": 25, "entity_ids": [0]}, {"anchor_in_caption": 0, "entity_ids": [2]}]
        entities = [{"human_character": {"status": "matched", "named": True, "name": "Naruto Uzumaki"}},
                    {"human_character": {"status": "matched", "named": False, "name": "none"}},
                    {"human_character": {"status": "ambiguous", "named": True, "name": "X"}}]
        self.assertEqual(grounding.named_caption(caption, phrases, entities),
                         "A boy [Naruto Uzumaki] waves at a girl [unnamed]. He [Naruto Uzumaki] smiles.")

    def test_link_panel_names_from_ground_truth_only(self):
        class A:
            merge_iou, match_iou, ambiguity_margin = 0.8, 0.5, 0.1
        panel = {"crop_bbox": [0, 0, 200, 200]}
        phrases = [{"phrase_index": 0, "boxes_page": [[10, 10, 50, 90]]},
                   {"phrase_index": 1, "boxes_page": [[11, 10, 50, 90]]},      # "he" -> same entity
                   {"phrase_index": 2, "boxes_page": [[120, 10, 160, 90]]}]
        human = {"human": {"characters": [
            {"index": 0, "box": [10, 10, 50, 92], "name": "Naruto Uzumaki", "named": True, "cluster": 0},
            {"index": 1, "box": [118, 12, 160, 90], "name": "none", "named": False, "cluster": 1},
            {"index": 2, "box": [500, 500, 600, 600], "name": "Outside", "named": True, "cluster": 2}]}}
        magi_chars = [[12, 10, 50, 90]]
        entities = grounding.link_panel(panel, phrases, magi_chars, human, A)
        self.assertEqual(len(entities), 2)
        self.assertEqual(phrases[0]["entity_ids"], phrases[1]["entity_ids"])
        self.assertEqual(phrases[0]["names"], ["Naruto Uzumaki"])
        self.assertEqual(phrases[1]["names"], ["Naruto Uzumaki"])
        self.assertEqual(phrases[2]["names"], [])                       # unnamed character
        self.assertEqual(entities[1]["human_character"]["cluster"], 1)
        self.assertEqual(entities[0]["magi3_character"]["status"], "matched")
        self.assertEqual(entities[1]["magi3_character"]["status"], "unmatched")
        no_gt = grounding.link_panel(panel, [{"phrase_index": 0, "boxes_page": [[10, 10, 50, 90]]}],
                                     magi_chars, None, A)
        self.assertEqual(no_gt[0]["human_character"], {"status": "no_ground_truth"})


class HumanExportTest(unittest.TestCase):
    def row(self):
        return {"image_path": "/old/PopManga_Test/images/S/ch1/p0.jpg",
                "magi_annotations": {"bboxes_as_x1y1x2y2": [[0, 0, 5, 5], [1, 1, 3, 3], [0, 0, 9, 9],
                                                            [6, 6, 8, 8], [2, 2, 4, 4]],
                                     "labels": [0, 1, 2, 0, 3]},
                "character_clusters": [0, 1], "character_names": ["Naruto Uzumaki", "none"],
                "text_char_matches": [[0, 1]], "text_tail_matches": [[0, 0]], "text_classification": [1]}

    def test_convert_row_splits_by_label_and_keeps_values(self):
        human = export.convert_row(self.row())
        self.assertEqual([c["box"] for c in human["characters"]], [[0, 0, 5, 5], [6, 6, 8, 8]])
        self.assertEqual([c["named"] for c in human["characters"]], [True, False])
        self.assertEqual(human["texts"][0]["box"], [1, 1, 3, 3])
        self.assertEqual(human["panels_proxy"][0]["box"], [0, 0, 9, 9])
        self.assertEqual(human["text_character"], [[0, 1]])
        self.assertEqual(export.relative_image_path(self.row()["image_path"]), "S/ch1/p0.jpg")

    def test_invalid_relations_rejected(self):
        row = self.row()
        row["text_char_matches"] = [[1, 0]]       # only one text box exists
        with self.assertRaises(ValueError):
            export.convert_row(row)

    def test_out_inside_source_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "PopManga_Test"
            (src / "dataset").mkdir(parents=True)
            (src / "images").mkdir()
            with self.assertRaises(SystemExit):
                export.main(["--dataset", str(src / "dataset"), "--images", str(src / "images"),
                             "--out", str(src / "annotations")])


if __name__ == "__main__":
    unittest.main()
