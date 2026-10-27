"""Qwen caption client: inputs, crops, resume, several servers. Mock HTTP; no GPU or model."""

import asyncio
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from PIL import Image

RUNNER = Path(__file__).resolve().parents[1] / "src/comics_qa/annotations/qwen/run_qwen.py"
spec = importlib.util.spec_from_file_location("run_qwen", RUNNER)
run_qwen = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_qwen)
MODEL = run_qwen.BASE_MODEL + "-FP8"


def magi3_doc(rel, image_path, panels, status="complete"):
    import hashlib
    with Image.open(image_path) as im:
        size = list(im.size)
    return {"schema": run_qwen.MAGI3_SCHEMA,
            "page": {"relative_path": rel, "image_sha256": hashlib.sha256(image_path.read_bytes()).hexdigest()},
            "magi3": {"panels": panels, "_meta": {"status": status, "image_size": size}}}


class MockServers:
    """Records which server got each request; fails the first `fail` panel requests."""

    def __init__(self, fail=0):
        self.hits = {}
        self.fail = fail

    def transport(self, base_url):
        def handler(request):
            self.hits[base_url] = self.hits.get(base_url, 0) + 1
            if request.url.path == "/v1/models":
                return httpx.Response(200, json={"data": [{"id": MODEL}]})
            body = json.loads(request.content)
            page = body["max_tokens"] == 1536
            if not page and self.fail > 0:
                self.fail -= 1
                return httpx.Response(400, json={"error": "bad request"})
            text = ("word " * (600 if page else 200)).strip() + "."
            return httpx.Response(200, json={"model": MODEL, "usage": {"total_tokens": 5},
                                             "choices": [{"finish_reason": "stop",
                                                          "message": {"content": text}}]})
        return httpx.MockTransport(handler)


class QwenRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.images, self.magi3, self.out = root / "images", root / "magi3", root / "out"
        self.pages = {"A/ch1/p0.jpg": [[0, 0, 50, 40], [10.5, 40.2, 60, 80]],
                      "A/ch1/p1.jpg": [],
                      "B/ch1/p0.jpg": [[-5, -5, 30, 30]]}
        for rel, panels in self.pages.items():
            image = self.images / rel
            image.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (60, 80), "white").save(image)
            target = run_qwen.annotation_path(self.magi3, Path(rel))
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(magi3_doc(rel, image, panels)))
        (self.magi3 / "logs").mkdir()
        (self.magi3 / "logs" / "x.json").write_text("{}")
        (self.magi3 / "runs.jsonl").write_text("")

    def tearDown(self):
        self.tmp.cleanup()

    def main(self, servers, *extra, ports=("18001",)):
        argv = ["--images", str(self.images), "--magi3", str(self.magi3), "--out", str(self.out),
                "--model", MODEL, "--retries", "0"]
        for p in ports:
            argv += ["--base-url", f"http://127.0.0.1:{p}"]
        real = httpx.AsyncClient

        def client(**kwargs):
            return real(transport=servers.transport(kwargs["base_url"]), **kwargs)
        with patch.object(run_qwen.httpx, "AsyncClient", side_effect=client):
            return run_qwen.main(argv + list(extra))

    def output(self, rel):
        return json.loads(run_qwen.annotation_path(self.out, Path(rel)).read_text())

    def test_lists_only_page_annotations_sorted(self):
        self.assertEqual([p.as_posix() for p in run_qwen.list_pages(self.magi3)], sorted(self.pages))

    def test_end_to_end_crops_limits_and_read_only_images(self):
        before = {p: p.read_bytes() for p in self.images.rglob("*.jpg")}
        self.assertEqual(self.main(MockServers()), 0)
        doc = self.output("A/ch1/p0.jpg")
        self.assertEqual(doc["schema"], run_qwen.SCHEMA)
        q = doc["qwen32B"]
        self.assertEqual(q["_meta"]["status"], "complete")
        self.assertEqual([p["crop_bbox"] for p in q["panels"]], [[0, 0, 50, 40], [10, 40, 60, 80]])
        self.assertTrue(all(p["word_count"] <= run_qwen.PANEL_WORD_LIMIT and p["shortened"]
                            and p["original_word_count"] == 200 for p in q["panels"]))
        self.assertLessEqual(q["page"]["word_count"], run_qwen.PAGE_WORD_LIMIT)
        self.assertEqual(q["_meta"]["prompt_version"], 4)
        self.assertEqual(self.output("A/ch1/p1.jpg")["qwen32B"]["panels"], [])   # page caption only
        self.assertEqual(self.output("B/ch1/p0.jpg")["qwen32B"]["panels"][0]["crop_bbox"], [0, 0, 30, 30])
        self.assertEqual(before, {p: p.read_bytes() for p in self.images.rglob("*.jpg")})
        run = json.loads((self.out / "runs.jsonl").read_text().splitlines()[-1])
        self.assertEqual(run["status"], "complete")

    def test_prompts_forbid_unseen_names_and_spell_out_order(self):
        self.assertIn("Never name characters", run_qwen.SYSTEM)
        self.assertIn("do not transcribe, quote or paraphrase", run_qwen.SYSTEM)
        page = run_qwen.PAGE_PROMPT.format(direction=run_qwen.DIRECTIONS["rtl"])
        self.assertIn("right-to-left, top-to-bottom", page)
        self.assertNotIn("aim for", (run_qwen.PANEL_PROMPT + page).lower())

    def test_partial_then_resume_only_missing(self):
        self.assertEqual(self.main(MockServers(fail=1)), 1)
        statuses = {rel: self.output(rel)["qwen32B"]["_meta"]["status"] for rel in self.pages}
        self.assertEqual(sorted(statuses.values()).count("partial"), 1)
        servers = MockServers()
        self.assertEqual(self.main(servers), 0)
        # resume: 1 models check + exactly the one missing panel caption
        self.assertEqual(sum(servers.hits.values()), 2)
        self.assertTrue(all(self.output(r)["qwen32B"]["_meta"]["status"] == "complete" for r in self.pages))

    def test_changed_settings_require_overwrite(self):
        self.assertEqual(self.main(MockServers()), 0)
        self.assertEqual(self.main(MockServers(), "--panel-max-pixels", "1000"), 1)
        self.assertEqual(self.main(MockServers(), "--panel-max-pixels", "1000", "--overwrite"), 0)

    def test_several_servers_share_requests(self):
        servers = MockServers()
        self.assertEqual(self.main(servers, ports=("18001", "18002")), 0)
        self.assertEqual(set(servers.hits), {"http://127.0.0.1:18001", "http://127.0.0.1:18002"})
        self.assertTrue(all(n >= 2 for n in servers.hits.values()))

    def test_image_changed_since_magi3_is_rejected(self):
        Image.new("RGB", (60, 80), "black").save(self.images / "A/ch1/p0.jpg")
        self.assertEqual(self.main(MockServers()), 1)
        self.assertFalse(run_qwen.annotation_path(self.out, Path("A/ch1/p0.jpg")).exists())

    def test_output_inside_images_rejected(self):
        with self.assertRaises(SystemExit):
            run_qwen.parse_args(["--images", str(self.images), "--magi3", str(self.magi3),
                                 "--out", str(self.images / "q")])

    def test_check_only_needs_no_server_and_writes_nothing(self):
        def boom(**kwargs):
            raise AssertionError("no HTTP client expected")
        with patch.object(run_qwen.CaptionClient, "check", side_effect=AssertionError("no check")):
            self.assertEqual(run_qwen.main(["--images", str(self.images), "--magi3", str(self.magi3),
                                            "--out", str(self.out), "--check-only"]), 0)
        self.assertFalse(self.out.exists())

    def test_shortening_policy(self):
        text = " ".join(["Short."] + ["w"] * 70 + ["end."] + ["x"] * 60)
        result = run_qwen.finalize_caption(text, 100)
        self.assertTrue(result["shortened"])
        self.assertEqual(result["shortening_method"], "sentence_boundary")
        self.assertEqual(result["word_count"], 72)


if __name__ == "__main__":
    unittest.main()
