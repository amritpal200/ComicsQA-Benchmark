# GEN-1 full collection review — 2026-10-28

Output: `/data/151-3/comics/ComicsQA_Benchmark/items/gen1/v1/`.
50 chapters, 28,661 attempted, 12,584 gate-passed, 3,477 selected.
The reported 25,184 rejected includes 9,107 gate-passed candidates excluded by
selection quotas/capacity; these totals reconcile. No selection caps were relaxed.

Read-only verification checked all 53 manifest output hashes and all 3,477 selected
template/program, saved execution/proof and displayed answer bindings. This does
not rerun CRL against current source annotations or perform visual review.

| Family | Selected |
|---|---:|
| Text count | 880 |
| Appearance count | 813 |
| Speaker text count | 794 |
| Cross-page text count comparison | 636 |
| Next appearance | 181 |
| Character constraints | 162 |
| Single speaker | 11 |

Answer types: 2,487 integers, 636 three-way comparisons, 181 page indices, 173
character names. No boolean/presence items survived selection. The three-way
comparisons are not two-option answers. This is a count-heavy baseline, not the
planned varied-anchor/sentence-answer benchmark.

Main gate exclusions: UNKNOWN 9,951; EMPTY 2,343; no visual support 2,270;
AMBIGUOUS 1,344. These are expected conservative exclusions, not reasons to close
coverage or relax quotas automatically. Keep the baseline immutable.

Language/identity review remains necessary: the report includes a Hunter x Hunter
question using the name form `and` (“...have and as their speaker?”). A lexical
visibility check does not establish that an ordinary word is an appropriate
identity label. Review the source identity/alias and usage before approving that
item; do not silently rewrite or promote it based on the saved proof. This also
illustrates why a proof of graph execution does not certify natural-language QA.

Next: user runs `bash scripts/prepare_verb1.sh` for CPU request packs, then CKG-3
and GEN-2 implementation/evidence work can proceed before deferred MN5 Qwen
inference. Natural-language round-trip, final quota checks and human review remain
required before export. See the verbalization README for implementation limits.
