# CKG-3 full-collection review — 2026-10-29

Input: `/data/151-3/comics/ComicsQA_Benchmark/evidence/ckg3/v1/`.
The full build completed: **50 chapters / 2,022 pages**. There is a final manifest
and no `.partial` build. No rebuild is required for this review.

## Integrity verification

- All **153 output hashes** match the manifest.
- Manifest fingerprint and saved build configuration agree; current builder code
  hashes match the build's recorded code.
- Loaded all 50 chapters through `load_rich`: verified CKG-1/2 bindings and
  checksums, recomputed richer evidence and review rules, compared full payloads.
- Chapter counts, eligible relation counts, report and manifest totals reconcile.
- The build records raw-source verification and pins **7,994 distinct source
  files**. This follow-up verified artifact bindings, not a fresh reread of every
  original image/annotation. No visual review or model inference was performed.

## Evidence available

| Measurement | Count |
|---|---:|
| All facts, including model candidates | 182,299 |
| Answer-eligible positive facts | 12,405 |
| Verified transcripts linked to human Text nodes | 11,095 |
| Verified lexical name occurrences | 1,310 |
| Verified transcripts without a human Text node | 116 |
| Verified panel pages | 0 |
| Verified text-order pages | 0 |
| Verified semantic mentions | 0 |

11,211 of 21,508 OCR observation records have verified full normalized
transcripts. Of the 20,843 human Text nodes, **11,095 (53.2%)** have verified
transcripts. They occur on 1,807 pages. The 116 verified observations without human
Text nodes do not produce answer-eligible transcript facts.

The 12,405 eligible facts are entirely `transcript` and `name_occurs`. A lexical
name occurrence does not certify that the text refers to that character. It does
not establish the speaker or addressee either; those require separate evidence.
Two-model agreement is the project's V criterion, not a measured OCR accuracy.

## Coverage and implications for GEN-2

OCR coverage is `closed_assumed` on **127 pages**, including 24 with no human text
regions and **103 with text**. The other 1,895 pages remain open. **No full chapter
has closed OCR coverage.** Completeness still inherits the human annotation
assumption; agreement never upgrades it to `closed_verified`.

Positive verified text facts can be consumed by new interpreter/proof rules.
Exact counts, no-mention claims, first/only matches and quote uniqueness require
closed coverage for the entire search scope. A unique hit among verified strings
alone is insufficient if unverified regions remain. Page-scoped quote tasks may
start with the 103 closed OCR pages that contain text; additional visual support,
name visibility, uniqueness and shortcut gates must still pass. Generic repeats
such as `read this way` (88), `huh?` (71), and `what?!` (39) also show why quote
strings are not automatically distinctive. These counts are collection-wide,
not claims about duplicates within each chapter.

Panel memberships: 37,302 geometrically unique, 605 ambiguous, 233 unassigned,
1,481 invalid geometry. Unique assignment is not panel verification. All panel
inventories remain M, so **none of the 37,302 in-panel facts or derived spatial
facts are eligible**. Candidate spatial counts include 41,187 left-of, 33,604
above, 26,168 size and 3,131 overlap facts. They must not be used merely because
there are many of them. Invalid geometry requires upstream correction; do not
approve or clip it automatically.

## Review workload

| Queue kind | Records |
|---|---:|
| Panel inventory | 2,022 |
| Panel order | 2,022 |
| Text order | 2,022 |
| Transcript | 10,413 |
| Semantic mention | 1,310 |
| Total | 17,789 |

These are review *records*, not 17,789 different pages or confirmed annotation
errors. Transcript review includes 10,297 unresolved observations plus the 116
already verified observations without human text links; the latter cannot become
human quote facts through transcription review alone. Order review is conditional
on panel verification / closed human text coverage. Prioritize actionable records
on pages needed by planned question families, not every queue record equally.

## Next implementation boundary

1. Extend CRL and the independent checker together to consume pinned CKG-3
   transcript and lexical-occurrence evidence with conservative scope coverage.
   Preserve GEN-1 and do not silently reinterpret lexical occurrences as mentions.
2. Define GEN-2 families over existing page-level H/V facts and the newly supported
   evidence. Do not wait for every page to be visually reviewed before implementing
   families whose prerequisites already hold.
3. Review selected panel inventories/orders and semantic mentions when particular
   families require them. Record individual decisions in a fresh reviewed build;
   do not promote all model panels based on this report.
4. Defer Qwen wording/answer-conditioned generation to MN5, then perform final
   validation, balancing, human review and export.

CKG-3 construction is complete; visual adjudication and richer CRL integration
are not. Caption-grounding recovery is independent of this result.
