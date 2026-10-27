"""Core foundation: geometry port, file-name parsing, page joining, identities. Standard library only."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

CORE = Path(__file__).resolve().parents[1] / "src/comics_qa/core"
sys.path.insert(0, str(CORE))
import build_core  # noqa: E402
import geometry  # noqa: E402


class GeometryTest(unittest.TestCase):
    def test_box_to_panel_overlap_then_nearest(self):
        panels = [[0, 0, 100, 100], [100, 0, 200, 100]]
        self.assertEqual(geometry.box_to_panel([90, 10, 130, 20], panels), 1)   # larger overlap
        self.assertEqual(geometry.box_to_panel([0, 150, 10, 160], panels), 0)   # none overlaps: nearest
        self.assertEqual(geometry.box_to_panel([0, 0, 1, 1], []), -1)

    def test_right_to_left_order_within_and_across_panels(self):
        sorted_panels = [[100, 0, 200, 100], [0, 0, 100, 100]]       # right panel first (rtl)
        boxes = [[10, 10, 20, 20], [150, 50, 160, 60], [180, 5, 195, 15]]
        self.assertEqual(geometry.sort_boxes_in_reading_order(boxes, sorted_panels), [2, 1, 0])


def make_world(root):
    images = root / "images"
    magi3 = root / "magi3"
    human = root / "human"
    chapter = "Hero/Hero - 001 - Start"
    pages = ["Hero - 001 - p000 - Start.jpg", "Hero - 001 - p001-002 - Start.jpg", "Hero - 001 - p003 - Start.jpg"]
    for i, name in enumerate(pages):
        rel = f"{chapter}/{name}"
        (images / rel).parent.mkdir(parents=True, exist_ok=True)
        (images / rel).write_bytes(b"x")
        m = {"page": {"image_sha256": f"sha{i}"},
             "magi3": {"panels": [[0, 0, 50, 100], [50, 0, 100, 100]], "characters": [[1, 1, 5, 5]],
                       "character_cluster_labels": [0], "texts": [[2, 2, 4, 4]],
                       "reading_order": {"status": "complete", "panels": [1, 0]},
                       "_meta": {"image_size": [100, 100]}}}
        (magi3 / (rel + ".json")).parent.mkdir(parents=True, exist_ok=True)
        (magi3 / (rel + ".json")).write_text(json.dumps(m))
        if i == 1:
            continue                                                    # page without ground truth
        h = {"page": {"split": "seen", "image_sha256": f"sha{i}", "width": 100, "height": 100},
             "human": {"characters": [{"index": 0, "box": [60, 10, 90, 90], "name": "Hero Man", "named": True,
                                       "cluster": 0},
                                      {"index": 1, "box": [5, 10, 40, 90], "name": "none", "named": False,
                                       "cluster": 1}],
                       "texts": [{"index": 0, "box": [10, 5, 20, 15], "text_classification": 1},
                                 {"index": 1, "box": [70, 5, 80, 15], "text_classification": 1}],
                       "tails": [{"index": 0, "box": [70, 16, 72, 20]}],
                       "text_character": [[1, 0]], "text_tail": [[1, 0]]}}
        (human / (rel + ".json")).parent.mkdir(parents=True, exist_ok=True)
        (human / (rel + ".json")).write_text(json.dumps(h))
    return images, human, magi3


class BuildTest(unittest.TestCase):
    def test_parse_names_including_spreads(self):
        p = build_core.parse_page_path("Oshi No Ko/Oshi No Ko - 001 - Chapter 1 A/Oshi No Ko - 001 - p001-002 - Chapter 1 A.jpg")
        self.assertEqual((p["chapter_number"], p["page_start"], p["page_end"]), (1, 1, 2))
        self.assertIsNone(build_core.parse_page_path("A/B/c.jpg"))

    def test_build_joins_ground_truth_and_magi3(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            images, human, magi3 = make_world(root)
            before = {p: p.read_bytes() for p in root.rglob("*") if p.is_file()}
            out = root / "core"
            argv = ["--images", str(images), "--human", str(human), "--magi3", str(magi3), "--out", str(out)]
            self.assertEqual(build_core.main(argv), 0)
            self.assertEqual(build_core.main(argv), 1)                  # never overwrites a version
            self.assertEqual(before, {p: p.read_bytes() for p in before})   # inputs untouched
            pages = [json.loads(l) for l in (out / "v1/pages.jsonl").read_text().splitlines()]
            self.assertEqual([p["page_id"] for p in pages],
                             ["hero__c001__p000", "hero__c001__p001-002", "hero__c001__p003"])
            gt, spread = pages[0], pages[1]
            self.assertTrue(spread["is_spread"])
            self.assertFalse(spread["has_ground_truth"])
            self.assertEqual(spread["split"], "seen")
            self.assertEqual(spread["split_source"], "chapter")
            self.assertEqual(spread["model_only"]["characters"][0]["source"], "model:magi3")
            # panel 1 (right) is read first; texts follow panel order then rtl within panel
            self.assertEqual(gt["reading_order"]["panels"], ["hero__c001__p000__panel01", "hero__c001__p000__panel00"])
            self.assertEqual(gt["reading_order"]["texts"], ["hero__c001__p000__htext01", "hero__c001__p000__htext00"])
            text = gt["texts"][1]
            self.assertEqual(text["speaker_char_ids"], ["hero__c001__p000__hchar00"])
            self.assertEqual(text["tail_ids"], ["hero__c001__p000__htail00"])
            self.assertEqual(gt["characters"][0]["panel_id"], "hero__c001__p000__panel01")
            chars = {json.loads(l)["identity_id"]: json.loads(l)
                     for l in (out / "v1/characters.jsonl").read_text().splitlines()}
            hero = chars["hero__hero-man"]
            self.assertEqual(hero["counts"]["pages"], 2)
            self.assertEqual([a["text"] for a in hero["aliases"]], ["Hero Man", "Hero", "Man"])
            self.assertIn("hero__c001__p000__unnamed1", chars)
            chapters = [json.loads(l) for l in (out / "v1/chapters.jsonl").read_text().splitlines()]
            self.assertEqual(chapters[0]["pages_without_ground_truth"], ["hero__c001__p001-002"])
            self.assertEqual(chapters[0]["missing_page_numbers"], [])

    def test_aliases_flag_shared_name_parts(self):
        self.assertEqual(build_core.name_aliases("Konohamaru Sarutobi"), ["Konohamaru Sarutobi", "Konohamaru", "Sarutobi"])
        self.assertEqual(build_core.name_aliases("L"), ["L"])


if __name__ == "__main__":
    unittest.main()
