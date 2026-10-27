# core

Benchmark foundation (spec 01): chapters, pages and character identities, joined from the human ground
truth (`annotations/human`) and MAGI v3 structure (`annotations/magi3`), following the source precedence
in `docs/specs/00_architecture.md`. Standard library only; CPU, a few seconds.

```bash
bash scripts/build_core.sh                 # -> /data/151-3/comics/ComicsQA_Benchmark/core/v1
bash scripts/build_core.sh --version v2    # new version after inputs change (never overwritten)
```

| File | Contents |
|---|---|
| `chapters.jsonl` | one row per chapter: series, number, title, split, `page_ids` in reading order, pages with/without ground truth, missing page numbers, counts |
| `pages.jsonl` | one row per page (below) |
| `characters.jsonl` | identities: named (series-level) and unnamed (page-level), with appearances per chapter, aliases, counts |
| `report.json` | summary and issues |
| `manifest.json` | input roots and the sha256 of every input annotation file |

Each page row has:
- `page_id`, `chapter_id`, `page_start`/`page_end` (spreads such as Oshi No Ko p001-002), `order_in_chapter`, `split` (`split_source`: human, or chapter for pages without ground truth), `has_ground_truth`;
- `panels` (MAGI v3, `reading_order` rank);
- `characters` (human: name, `named`, page cluster, `identity_id`, `panel_id`);
- `texts` (human: box, `panel_id`, `reading_order`, `speaker_char_ids`, `tail_ids`) and `tails` (human);
- `reading_order` (panel and text ids);
- `sources` (input file checksums);
- `model_only`: MAGI v3 characters and texts for context, on pages without ground truth only.

## Rules (decided from the data, 2026-10-23)
- **IDs** come from file names and ground-truth indices, so they are stable across rebuilds:
  `naruto__c001__p004__hchar05`, `…__htext07`, `…__htail02`, `…__panel03` (MAGI v3 panel index).
- **Reading order:**
  - Panels follow the MAGI v3 panel order.
  - Human text boxes are ordered with the MAGI v3 geometry rules, ported to plain Python in
    `geometry.py`. The port reproduces MAGI v3's own text order on all 2,022 pages.
  - Characters and texts are assigned to the panel they overlap most, or the nearest panel.
- **Identity:**
  - A named character is the same person across pages and chapters when the name is exactly the
    same within a series. Names are consistent per series in PopManga.
  - Subset names are different people (`L` vs `Lind L. Tailor`, `Sharon` vs `Sharon's son`), so
    nothing is merged.
  - `"none"` characters are only grouped within a page, by their human cluster.
- **Aliases** are the full name plus name parts of at least 3 letters, for the later name-visibility
  check. A part is flagged `ambiguous` when several people share it (e.g. "Sarutobi").

## v1 summary
- **Pages:** 50 chapters, 2,022 pages (1,925 with ground truth), 9,712 panels.
- **Human boxes:** 18,778 characters and 20,843 texts.
- **Identities:** 314 named identities (112 appear in both chapters of their series) and 6,033 unnamed
  page groups.
- **Name parts:** 32 ambiguous.
