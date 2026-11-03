# Event facts (improvement plan S5)

Who does what in a panel, taken from the Qwen3-VL-32B captions and confirmed by an **independent model**
(decision D-C, 2026-11-02: a different model, default `OpenGVLab/InternVL3-14B`). Facts feed the later
event question families (S6). Plan: [benchmark_improvements.md](../../../docs/notes/benchmark_improvements.md) §3.1d.

## How a fact is made

1. **Statement** (CPU): a caption sentence with exactly one grounded phrase (a short noun phrase such as "a boy"),
   linked to one human-matched, named character, containing an action verb and not about text or speech bubbles.
   The phrase is replaced by "the outlined character":
   *"In the foreground, the outlined character with spiky black hair … sits at a wooden table, gripping a knife and fork."*
2. **Two images** of the panel: the subject's **human annotation box** outlined in red (positive), and another
   identified character of the same panel outlined (control). The subject's identity comes from human `is_char` facts.
   The caption's own name link is not trusted: it is sometimes wrong (e.g. "a boy" linked to a girl), and then the
   verifier sees a different character and says no.
3. **Verification** (GPU, user-run): the verifier answers yes/no for both images with the same statement.
4. **Acceptance** (CPU): positive = yes **and** control = no. Anything else is dropped (no/no, yes/yes, unparsed, missing).
   Accepted facts are `origin=M`, `tier=A_candidate`, `audit=pending`. Per the trust rules, they become usable for answers
   (tier A) only after the audit sample is reviewed and its error rate recorded.

Bounded trial (Blue Exorcist c002 + One Piece c001): 261 statements → 200 candidates (61 without a control character),
400 images, ~213 MB, ~1 min CPU.

## Commands (from `Code/`)

```bash
export BENCHMARK1000_PYTHON=/tmp/benchmark1000-dev-env/bin/python   # needs Pillow
B=/data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000

# 1. statements + images, all 50 chapters (CPU, ~25 min, ~5 GB of PNGs; resumable per chapter)
bash scripts/benchmark1000.sh prepare-events --out $B/events_v1_requests

# 2. verifier model, once (~30 GB to /data/151-3/comics/models/InternVL3-14B)
bash scripts/benchmark1000_event_verifier.sh --download

# 3. server, in its own screen, on a GPU with >= 45 GB free (Blackwell: --mem 0.45; an empty L40S: --mem 0.9)
bash scripts/benchmark1000_event_verifier.sh --gpu 2 --port 18101

# 4. answers (resumable; one file per request), after the server prints "Application startup complete"
bash scripts/benchmark1000.sh verify-events --requests $B/events_v1_requests \
  --endpoint http://localhost:18101/v1 --model internvl3-14b --workers 16 --out $B/events_v1_responses

# 5. accept facts + audit sample
bash scripts/benchmark1000.sh ingest-events --requests $B/events_v1_requests \
  --responses $B/events_v1_responses --out $B/events_v1
```

Try step 4 with `--limit 50` first; a rerun without `--limit` reuses those answers. A different verifier is set with
`VERIFIER_MODEL_ID=org/name` for the server script, plus `--model <served name>` for `verify-events`.

## Audit (needed before use)

`events_v1/audit.html` shows 60 seeded accepted facts with their outlined image. For each, record whether the
statement is true for the outlined character. Acceptance sampling (design brief §11.2): 0 errors in 60 → error
below ~5% at 95% confidence. With errors, drop the event share in the final selection or tighten the rules. The audit
intake and event question families (S6) come next.

## Full run (user-run, 2026-11-02)

2,761 candidates (from 4,036 statements; 1,256 had no control character, 230 panels not exact), 5,522 answers from
InternVL3-14B: **1,790 accepted** (yes/no), 788 yes/yes, 109 no/no, 74 no/yes. 50 chapters, 954 pages, 208 identities.
The 50-request test showed a yes-bias (67% yes), which the control requirement filters out.

## Audit intake (user step)

Fill `reports/benchmark1000/events_v1_audit_decisions.json` (60 entries; `verdict` = `correct`/`wrong`, `reviewer` = your
name) while looking at `events_v1/audit.html`, then:

```bash
bash scripts/benchmark1000.sh record-event-audit --facts $B/events_v1 \
  --decisions $B/events_v1_audit_decisions.json --out $B/events_v1_audit     # passes with <= 3 wrong (--max-errors)
```

Facts judged wrong are never used. A failed audit blocks `event-pilot`.

## Event questions (S6, `story_events.1`)

| Family | Example (trial, One Piece c001) | Answer |
|---|---|---|
| `event_actor_choice` | On the page where someone says "promise that you'll give it back to me someday...", on the left, which named character with short, light-colored hair and a goatee smiles broadly, eyes closed, …? Choose one: A) Shanks; B) Roger; C) Higuma; D) Makino. | `A` |
| `event_order` | Put these moments in the order they happen in the chapter, first to last: A) Someone with … B) In the foreground, someone with spiky black hair … pointing … Answer with the four letters. | `['B','C','A','D']` |

- **Actor:** the page is located by a distinct line on the same page (story-family certificate). The three distractors are readable names
  **not drawn on that page** (closed human character/name coverage), so the gold is unique if the fact is true. Gold letter rotates A–D;
  less frequent characters first; ≤3 per identity per chapter.
- **Order:** four confirmed events on four pages, ≥2 characters, decided by human page order; never shown already sorted.
- Both count as `event` in `story-profile`. The checker (`story_check._check_event`) re-reads the confirmed facts, requires yes/no
  confirmation and the human `is_char` identity, and rebuilds the wording; `check-story` re-reads the facts file (hash-pinned).

```bash
bash scripts/benchmark1000.sh event-pilot --facts $B/events_v1 --audit $B/events_v1_audit --out $B/story_events_v1   # ~10 min CPU
bash scripts/benchmark1000.sh check-story --store $B/story_events_v1 --out $B/story_events_v1.check.json
bash scripts/benchmark1000.sh story-profile --store $B/pool_v1 --store $B/branch_v1_admission --store $B/contrast_v1 \
  --store $B/story_v4 --store $B/story_events_v1 --out $B/story_profile_v6
```

Trial with a placeholder audit (scratch only, not a real audit; One Piece c001, Blue Exorcist c002, Naruto c001): 32 items
(8 actor, 24 order), 0 rejected, check 32/32. Estimated full yield ~130 actor + ~400 order. 4 new tests.

## Limits

- Statements are long caption sentences that mix appearance and action. S6 shortens them into question options.
- Only panels with ≥2 identified characters can have a control. Single-character panels are skipped (no control).
- Captions came from Qwen3-VL-32B. The verifier is a different model family, but both can share the same visual mistakes.
