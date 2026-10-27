# CKG-0 review decisions — 2026-10-27

Inputs: `/data/151-3/comics/ComicsQA_Benchmark/reports/ckg0/v1/` and the pinned
`core/v1/` snapshot. Review output: `reports/ckg0/review_v1/` under the same data root.
The saved full audit was reviewed; no source annotation scan or inference was rerun.

## Identity policy correction

All six audit errors concern `Unnamed woman` in Death Note chapter 1, pages
32–34. The old core identity is `death-note__unnamed-woman`. The companion stores
six appearance overrides to three generic identities:

| Page | Human character indices | Derived generic identity |
|---|---|---|
| `death-note__c001__p032` | 0, 5, 6, 11 | `death-note__c001__p032__unnamed0` |
| `death-note__c001__p033` | 7 | `death-note__c001__p033__unnamed6` |
| `death-note__c001__p034` | 6 | `death-note__c001__p034__unnamed3` |

Appearance IDs and raw source identity/name are preserved. Generic graph identities
have no name aliases. This explicitly implements the agreed generic-name policy;
it does not claim these appearances are different people or infer visual identity.
The six errors and six corresponding policy warnings are resolved **conditional
on CKG-1 applying the overrides**. Core v1 itself remains the original snapshot.

## Coverage decisions

| Family | closed_assumed | open | absent |
|---|---:|---:|---:|
| Character boxes | 1198 | 727 | 97 |
| Names | 1198 | 727 | 97 |
| Text boxes | 1872 | 53 | 97 |
| Speaker links | 922 | 1003 | 97 |

All 2,022 pages stay in chapter context. Models remain open for panels, inner
reading order and OCR. No unknown text-class meaning is inferred from raw 0/1
labels. Unlinked text alone is not evidence of missing dialogue annotations.
There are 4,519 unresolved review warnings and zero unresolved integrity errors
under the companion contract. Warnings overlap; this is not a count of bad pages.

There is no fully closed chapter for character or speaker coverage. Three chapters
have candidate closed text-box coverage only: `assassination-classroom__c001`,
`bleach__c002`, `dragon-ball__c002`. This does not certify their OCR or dialogue.

## Geometry disposition

Retain every unresolved geometry flag for its affected families. Do not relax
tolerances or clip stored annotations to raise yield. The queue ranks 1,012 human
boxes (955 characters, 54 texts, 3 tails). The 2,273 model panel-proxy boundary
flags remain separate in the unresolved issue list.

The largest human overflow is character index 3 on `black-clover__c001__p039`:
box `[1062.25,1552.25,1583.92529296875,2311.75]` on a 1400×2100 raster. A visual
spot-check of the original page shows artwork reaching the bottom/right page edge;
it does not justify recovering the off-image extent or closing page completeness.
Keep the affected families open. The next ranked issue is text index 20 on
`bleach__c001__p030`, extending 43.03 pixels left of the image; it remains pending
visual review. The queue as a whole is not visually certified.

## Handoff

CKG-1 should check review/core/audit hashes, apply identity overrides, emit supported
positive facts with evidence, and carry family-specific coverage. Exact count,
absence, first and only operations require coverage over their actual scope; CRL
must return UNKNOWN where that cannot be established. Source freshness needs
checking at graph-build time; this review only verifies the saved snapshot.

Name visibility is a pre-GEN-1 requirement (CKG-2; exact-name identity integration
can be folded into CKG-1). Enforce the ~30% frequent-name-answer and ~5% two-option
limits in GEN-1; EXP-1 confirms them and runs baselines. Page-order generation is
an independent side task. Depth remains excluded.

Validation: 21 standard-library tests passed across audit and review. The completed
review manifest pins inputs, code and output checksums. Shared progress and future
ownership must be recorded in `docs/STATUS.md`.
