# Full unified-pool review — 2026-10-31

The user completed `reports/benchmark1000/pool_v1` and `verify-store`. This review also ran `verify-store`: all 3,762 representatives pass saved-record, manifest, source-ledger, deduplication-index and regenerated-report validation. All 142 frozen legacy files still match. No new CRL replay of the full inventory, human review, solver selection or release occurred.

## Counts and status hierarchy

- Nine sources contribute **3,915 occurrences**; conservative proof-world deduplication leaves **3,762 representatives**, retaining all 3,915 variants and all source/duplicate provenance. There are 153 duplicate occurrences.
- **122** representatives are admitted native items with saved verified proofs and native gate receipts.
- **3,640** are legacy imports with `proof=archived_check`. Their original checks remain preserved; inventory does not give them new native admission or complexity certificates.
- All 3,762 have pending human and release status. All are template-generated and have executed evidence class; none is claim-verified sentence QA.
- Source scope covers 50 chapters: 2,327 seen / 1,435 unseen. The frozen target remains 600 seen / 400 unseen. Chapter-capped inventory capacity is 2,000 (1,200 seen / 800 unseen), so raw count/split/chapter availability is not the immediate obstacle.
- Native candidates cover 16 chapters: 70 seen / 52 unseen. Of these, 107 have measured primary-group certificates; the other 15 older `admission_v1` items remain unassigned. Including that previously separate older store explains the increase from the earlier 107-path inventory to 122 native representatives.

Counts remain conservative within the documented native/legacy equivalence rules. They are not a guarantee that all cross-schema or differently worded semantic duplicates have been eliminated.

## Required groups versus current supply

| Primary group | Policy target | Declared inventory | Certified native inventory | Gap against certified native supply |
|---|---:|---:|---:|---:|
| Short | 120 | 3,690 | 50 | 70 |
| Chain | 230 | 22 | 22 | 208 |
| Branch-combine | 220 | 3 | 3 | 217 |
| Aggregate/compare | 80 | 32 | 32 | 48 |
| Paired | 100 | 0 | 0 | 100 |
| Sentence | 250 | 0 | 0 | 250 |

Another 15 native items have unassigned groups and are excluded from these group counts. Legacy `short` is the adapter's conservative classification, not proof that a legacy question cannot acquire another group after independent re-admission and complexity checks. In particular, 162 archived character-constraint items warrant targeted inspection for reusable branching structure; do not silently relabel them or treat word/operation counts as certificates. Revalidating all 3,640 legacy items would not by itself create visual options, edited pairs or sentence claims.

The current measured native-hop distribution is 0:27, 1:35, 2:23, 3:22. Unknown hops remain unknown for 3,655 items. The 0-hop last-in-range family still has necessary visual evidence; zero here means no sequential navigation/switch operation. No new five-operation switch chain is claimed.

## Answer and evidence diversity

| Answer format | Representatives |
|---|---:|
| Count | 2,613 |
| Multiple-choice text comparison | 636 |
| Page | 278 |
| Character | 228 |
| Boolean | 4 |
| Page set | 3 |

There are **59 target character identities**, below the requested minimum 150 by 91. This is the current candidate-answer identity inventory, not an inventory of every graph-linked character available in source annotations. No conclusion that 150 is impossible is justified without a graph-grounded visual-identity preflight.

There are **zero visual-choice items**. Under the current identity floor and 15% visual-character requirement, at least 23 visual-character items would be necessary; the actual final character-answer denominator may require more. The existing 636 multiple-choice questions compare text counts and do not fill this image-choice requirement.

There are **zero certified long-relational items** against a floor of 200 and zero sentence items against 250. Long question wording alone does not fill the former. Count, identity and page priors must be checked on an actual selection, not pooled blindly across opportunity types.

The unselected pool exceeds some ratios: seen top1/top2 character priors, unseen top2 and page+1. It also exceeds per-chapter item caps. These are whole-pool diagnostics; selecting a subset can repair them. There are 184 page-answer items with unknown offsets, which cannot be treated as successes against a page+1 baseline. No joint constraint solver has been run by this review.

## Next implementation

Prioritise **P08: graph-grounded, name-free visual character references and four-option character QA**, beginning with a visual-identity/crop feasibility inventory and a small independently checked pilot. Existing crop/identity helpers are not yet a complete admitted question family.

This provides a necessary missing answer format and tests whether verified visual identities can extend beyond the 59 current named answer targets. It does not guarantee 150 eligible identities or solve the chain/branch shortages by itself. The implementation must:

1. Inventory existing trusted appearance→identity links and usable boxes across pages; keep unresolved/generic identities and uncertain links explicit.
2. Render immutable reference/option crops with image hashes and exact transform bindings; use another verified page for the correct option where available and preserve originals.
3. Bind the question and answer to graph execution with an independent checker, balanced A–D labels and distinct verified distractor identities. Avoid names unless already readable in the chapter.
4. Keep necessary-clue/page and visual/OCR checks, expose explicitly marked reference images in model input, and require pilot human review of distractor distinguishability. A different identity ID alone does not prove a visually fair option set.
5. Preserve question/evidence/generation flags and separate private identity/graph/proof metadata from model-facing assets. Unreviewed pilots are not final release candidates.

After that, extend target-first branch/long-relational families (P06/P07), inspect potentially reusable legacy constraint questions with fresh admission, implement verified pairs/claims, and only then prepare the supported Qwen stage on MN5. Qwen cannot manufacture missing graph support or certify a redundant path.

Preserve the current 1,000-QA policy and all completed outputs. Any relaxation is an explicit design decision, not an automatic consequence of shortages. No unchanged pool build or another broad quote-walk run is needed now. The full pool report is the baseline for measuring new-family yield and later selection feasibility.
