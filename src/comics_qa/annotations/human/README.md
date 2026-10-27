# annotations/human

PopManga human ground truth, exported read-only to one JSON per page (`export_human.py`, launcher
`scripts/export_human.sh`, about 15 s on CPU). The source dataset (`PopManga_Test/dataset/*.arrow`) is
never modified. The export refuses to write inside the PopManga folder, and the source checksums were
verified unchanged after the run.

Output: `/data/151-3/comics/ComicsQA_Benchmark/annotations/human/<relative image path>.json`, with:
- `human.characters`: index, box, `name` (`"none"` = unnamed), `named`, `cluster` (page-local identity)
- `human.texts`: index, box, raw `text_classification` (0/1; meaning not verified)
- `human.tails`, `human.text_character` (`[text, character]`), `human.text_tail` (`[text, tail]`)
- `human.panels_proxy`: panel boxes included in the export, which are **model proxies, not human**
- `raw`: the original dataset row, unchanged
- `page`: split, row index, original `image_path`, image sha256 and size

Verified on the local copy (2026-10-23):
- **Coverage:** 1,925 pages (1,136 seen, 789 unseen).
- **Characters:** 18,778 boxes, 12,216 of them named.
- **Texts:** 20,843 boxes.
- **Relations:** every `text_char_matches` pair is in range as [text, character].
