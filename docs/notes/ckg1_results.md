# CKG-1 full build analysis — 2026-10-27

Artifact: `/data/151-3/comics/ComicsQA_Benchmark/evidence/ckg/v1/`.
The report scope is `full_collection`. All 104 output checksums match the manifest;
the pinned core/audit/review dependency hashes and builder code match current files.
All 50 graphs passed structural validation. Report totals equal the graph totals.
Source images/annotations were checked by the builder; this analysis did not repeat
the source scan or inference.

## Contents

| Measurement | Count |
|---|---:|
| Chapters | 50 |
| Pages | 2,022 |
| Human-annotated pages | 1,925 |
| Pages without human annotations | 97 |
| Nodes across chapter files | 65,282 |
| Facts | 204,298 |
| Coverage certificates | 16,176 |
| Human character appearances | 18,778 |
| Human text regions | 20,843 |
| Human tails | 7,416 |
| Model panels | 9,712 |

Character nodes occur 6,461 times across chapter files. There are 6,349 distinct
identity IDs: 313 exact-name identities and 6,036 page-local generic groups. The
112 extra node occurrences are named identities included in both chapter graphs.
Generic groups are page-local and must not be interpreted as 6,036 distinct people
across the collection. The reduction from core v1's 314 named identities reflects
the deliberate `Unnamed woman` policy correction, not a lost named character.

## Relation checks

| Relation | Count |
|---|---:|
| `page_in` | 2,022 |
| `next_page` | 1,972 |
| `on_page` | 56,749 |
| `is_char` | 18,778 |
| `named` | 425 |
| `alias` | 969 |
| `spoken_by` | 13,627 |
| `has_tail` | 8,684 |
| `is_line` | 13,627 |
| `present` | 10,682 |
| `speaks_on` | 3,828 |
| `co_present` | 72,935 |

For each chapter, identity links, speaker links, tail links, line status, presence,
speaking presence and co-presence were independently reconstructed from core plus
the reviewed identity overrides and compared with graph tuples. All matched. Six
overrides were applied, yielding three generic identities. The 97 unannotated
pages remain in context and their human coverage remains absent.

There are 194,586 H facts, including deterministic derivations and dataset structure,
and 9,712 M facts for panel membership on pages. H is a provenance/policy label,
not a claim that all these facts were individually visually verified. Every M fact
remains ineligible under the H/V answer-critical policy. Every identity's name
visibility remains `not_checked`, as expected before CKG-2.

## Coverage and limits

| Family | closed_assumed | open | absent |
|---|---:|---:|---:|
| Character boxes | 1,198 | 727 | 97 |
| Names | 1,198 | 727 | 97 |
| Text boxes | 1,872 | 53 | 97 |
| Speaker links | 922 | 1,003 | 97 |

These states exactly match the reviewed coverage artifact. Panel, inner reading
order and OCR coverage remain open on all 2,022 pages. Supplied-image page sequence
is closed_assumed on all pages; this does not certify human annotation completeness.
No full chapter is closed for character/name/speaker coverage; three are closed
for text boxes only. Exact counts/absence/first/only must use closed relevant scopes
or return UNKNOWN in CRL. Positive witnessed relations remain available.

Co-presence forms 35.7% of all facts and should not be mistaken for question yield.
One page, `kuroko-s-basketball__c002__p012`, has 153 annotated identity groups,
creating 11,628 unordered pairs. This explains most of that chapter's 13,928 facts;
the tuples agree with the supplied annotations, but this is not a visual identity
audit. GEN-1 should apply its planned chapter/page/family quotas rather than sample
graph facts uniformly, which would overrepresent crowded pages and generic groups.

The chapter JSONs occupy 402,516,614 bytes (about 403 MB), including repeated explicit
provenance and derived relations. Size is acceptable for the present collection;
do not duplicate these artifacts into model-facing QA exports.

## Next stage

CKG-1 is complete for the collection and ready for CKG-2: align PaddleOCR and MAGI
OCR, find exact-name/unambiguous-alias candidates, and store verified chapter name
visibility with page/text evidence. Model output status `ok` alone is insufficient.
Then implement CRL and its proof checker before question generation. Name visibility
does not close missing character or speaker coverage.
