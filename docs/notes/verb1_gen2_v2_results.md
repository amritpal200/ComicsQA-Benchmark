# GEN-2 v2 request-pack review — 2026-10-29

Pack: `/data/151-3/comics/ComicsQA_Benchmark/items/verb1/gen2_v2_requests/`.
Source: `/data/151-3/comics/ComicsQA_Benchmark/items/gen2/v2/`.

Completed preparation resume verified successfully. All 52 output hashes match. All five
request IDs are unique, match their private records, and bind to the exact five original
selected items. Source manifest SHA256 matches the actual GEN-2 v2 manifest. Saved independent
proof checks all accept; template round trips passed. Both generation baselines and this pack
were left unchanged during v3 implementation.

There are 50 chapter records and five requests: three quote-speaker depiction counts and two
quote-speaker identities, all from Chainsaw Man c001. The other 49 chapters correctly have zero
requests because GEN-2 v2 selected zero items there. Preparation does not generate extra QA or
restore rejected candidates. The garbled terminal prompt suffix is not present in the parsed,
hash-verified artifacts.

`prepared_not_inferred` means CPU preparation only. No Qwen execution, response ingestion,
free-form parse-back, G10 approval or human review is implied. This pack is valid as the small
v2 baseline but inherits v2's lack of chapter/family/name-answer diversity.

V3 now retains gate-passing candidate pools, moves new concentration checks within splits,
keeps the original chapter-level frequent-name/two-option limits, and supports snapshot-bound
reviewed aliases. No actual aliases were approved by this implementation. A bounded pending
review example is `/tmp/comicsqa-gen2-alias-review-example.json` (four Blue Exorcist c002 aliases).
Among v2's 38 gate-passing name candidates, only two ZOMBIE DEVIL answers are nonfrequent under
the retained chapter-level metric. Reviewed aliases/additional eligible questions are needed to
resolve that bottleneck; changing selection scope alone cannot supply name diversity.

Preserve this completed pack. After reviewing/generating/selecting v3, prepare a new pack using
`prepare_verb1_gen2.sh --source .../items/gen2/v3 --out .../items/verb1/gen2_v3_requests`.
