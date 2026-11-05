# Free QA generation (expansion plan X3/X4; experimental track)

A local Qwen3-VL-32B reads a text **evidence pack** of a chapter and freely proposes questions. Each question lists its
reasoning as **typed claims** over pack IDs; a separate checker decides. Plan: [expansion_plan.md](../../../docs/notes/expansion_plan.md).

## Pack (`prepare-freegen`)

Four levels per chapter (`--per-level` packs each): `page` (one page with ≥2 identified characters), `window`
(6 consecutive pages), `selection` (all pages of a pair of characters), `chapter` (all pages; ~21k tokens max).
Every pack keeps the full CHARACTERS table (readable names only, with pages drawn). Per page: identified characters
drawn [H] with coverage status, then every text in reading order with ID `L<page>.<n>`, text (verified consensus [V]
or a single OCR reading [A]), speaker (`C…`, `unnamed`, `not dialogue`). `*` marks quotable lines (distinctiveness
certificate). With `--events`, audited event facts appear as `E…` [A, AI-audited]. The private ID map goes with each request.

## Proposals (`run-freegen`, local GPU)

The model returns a JSON list of `{question, answer_format, answer_ref, claims}`. Answer formats: character, page, line,
line_sequence. Claim types: `SAYS(L,C)`, `ON_PAGE(L,P)`, `DRAWN(C,P)`, `NOT_DRAWN(C,P)`, `SILENT(C,P)`,
`BEFORE(L1,L2)`, `NEXT_LINE(L1,L2)`, `EVENT(E,C)`, `FIRST_DRAWN(C,P)`.

## Checking (`ingest-freegen`; `freegen_check.py`, separate from the generator)

- Every claim is checked against the graph:
  - `SAYS`: human speaker link;
  - `NOT_DRAWN` / `FIRST_DRAWN`: closed character coverage;
  - `SILENT`: closed text boxes and speaker links;
  - same-page `BEFORE`, and `NEXT_LINE`: core v1 reading order (model fact);
  - `EVENT`: confirmed event fact.
- The answer must be a cited entity. A `line_sequence` must be in its true order.
- No pack IDs in the question. Every quoted line must match exactly one verified, distinct line. The answer must not appear in the question.
- Accepted items are `story_item.1`:
  - family `free_generation`, `generation_mode=free_generation`, `track=experimental`;
  - `uses_model_facts` (reading order / event facts);
  - `pack_level` and `pack_pages`;
  - flags `needs_human_verification` and `needs_uniqueness_check`. Claims can't prove that only one answer fits the question.
- `report.json` gives rejection reasons and accepted items per level. `check-story` re-checks the store.

## Commands (from `Code/`)

```bash
B=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000
# 1. packs, pilot on 4 chapters (CPU, ~1 min)
bash scripts/benchmark1000.sh prepare-freegen --events $B/events_v1 --chapter one-piece__c001 --chapter blue-exorcist__c002 \
  --chapter naruto__c001 --chapter spy-x-family__c001 --out $B/freegen_pilot_requests
# 2. model server, own screen, a GPU with >= 60 GB free (Instruct-FP8 default; add --thinking for Qwen3-VL-32B-Thinking)
bash scripts/benchmark1000_generator_server.sh --gpu 0 --port 18201 --mem 0.6
# 3. proposals (try --limit 2 first; rerun resumes)
bash scripts/benchmark1000.sh run-freegen --requests $B/freegen_pilot_requests --endpoint http://localhost:18201/v1 \
  --model qwen3-vl-32b-instruct-fp8 --out $B/freegen_pilot_responses
# 4. validation + store, then re-check
bash scripts/benchmark1000.sh ingest-freegen --requests $B/freegen_pilot_requests --responses $B/freegen_pilot_responses --out $B/freegen_pilot
bash scripts/benchmark1000.sh check-story --store $B/freegen_pilot --out $B/freegen_pilot.check.json
```

With `--thinking` (BF16, 63 GB weights: the script defaults to `--mem 0.92`, so it needs an empty 97 GB GPU), use `--model qwen3-vl-32b-thinking` and a larger `--max-tokens` (e.g. 12000).

## Verification (2026-11-05)

4 synthetic tests (pack, valid character and sequence items, false claims, pack IDs and answers in the question, unknown
IDs, wrong format, missing flags, `<think>` stripping). Real-data ingest with two hand-written proposals on One Piece c001:
the true one accepted, the false one rejected (`claim_false`), `check-story` 1/1. No model has run yet.

## Limits
- Uniqueness of the answer is not proven by claims: every item keeps `needs_uniqueness_check` (a judge step is next).
- Selection caps free generation at 300 of the final 1,000 until the pilot is measured (E5).
