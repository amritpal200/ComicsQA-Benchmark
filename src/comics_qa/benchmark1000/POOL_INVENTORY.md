# Unified candidate pool and feasibility inventory

`pool-inventory` builds an additive private store above saved legacy candidates and admitted native QA. It does not generate questions, run models, modify annotations, revalidate archived proofs, approve reviews or publish a benchmark.

## Full user-run build

From `Code/`:

```bash
bash scripts/benchmark1000.sh pool-inventory \
  --policy /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/v1/policy.json \
  --out /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/pool_v1

bash scripts/benchmark1000.sh verify-store \
  --store /data/151-3/comics/ComicsQA_Benchmark/reports/benchmark1000/pool_v1
```

This uses CPU and saved JSON artifacts, with no image/GPU inference. The policy path is the existing frozen policy (600 seen / 400 unseen on the current collection); the command reads its actual contents, never guesses splits. Another `--policy` is accepted but must satisfy the existing strict policy schema. If split counts are null, the report marks them pending.

The default [source plan](../../../configs/benchmark1000/pool_sources_v1.json) includes GEN-1 v1, GEN-2 v1/v2/v3, native admission_v1, family admission, coverage admission, targeted set admission and switch admission. GEN-2 v3 contributes its retained pool, not its empty final selection. Earlier versions expose only what their existing adapters can read. Missing sources/manifests fail explicitly; there is no silent skip or resurrection of discarded proofs.

Use `--bench-root ROOT` on another host. Repeat `--source PATH` to replace the default plan with an explicit list of completed stores/raw GEN roots. Repeat `--chapter ID` to restrict scope; sources without that chapter contribute zero candidates. Ordinary imported stores with no declared chapter list derive their scope from validated saved records. Unknown requested chapters fail. A one-chapter report is a smoke-test inventory, not a full-collection feasibility analysis.

All outputs are create-only and pinned to input manifests, policy, scope, frozen legacy baseline and implementation code. Identical commands resume interrupted/completed publication under a single writer lock. Atomic existing records are reused; the final manifest appears only after all sources, index and reports succeed. A changed source/policy/code/scope requires a fresh output root. Outputs cannot overlap inputs or source/code namespaces. Do not overwrite existing runs.

## Stored artifacts and provenance

- `config.json`: source paths and manifest hashes, full policy and its semantic hash, chapter scope and code hashes.
- `records/<content-sha>.json`: every distinct full candidate variant, unchanged. Legacy programs/proofs and native proposal/admission receipts remain private and complete.
- `sources/*.json`: exact parent-manifest bytes/hash, parsed manifest and any manifest-pinned parent report, plus retained occurrence/excluded-proposal counts. Native parent reports preserve held/duplicate decisions as provenance. These reports retain their original parent scope even for a chapter-restricted merge. Omitted older proofs cannot be reconstructed from counts.
- `index.json`: deterministic equivalence groups, representative, every variant and every source occurrence. Duplicate variants remain stored; they are not additional QA pairs.
- `report.json`: total occurrence/variant/representative counts; legacy/native status, group, split, family, answer, identities, measured visual pages, meaningful hops, unknown baseline features, necessary quota gaps and source exclusions.
- `manifest.json`: final output hashes and counts, permanently `release_status=not_approved`.

`verify-store` checks record contracts, all output hashes, exact parent ledger bindings, index regeneration, occurrence/count agreement and regenerated inventory/gap summaries. It does not rerun CRL or page ablations. Existing `check-proofs --store ...` can independently replay representatives into a separate report, but inventory itself grants no verified proof or human decision.

Native proposal stores may be supplied explicitly; unadmitted proposals are counted as excluded and never enter the representative store. Raw generation proposal roots, unknown schemas and nested unified pools are not supported inputs. Use completed native admission stores or established raw legacy sources/imported candidate stores.

## Conservative deduplication

Native duplicates must match the independently saved resolved path **and** graph/visibility/rich snapshots and chapter. Legacy duplicates must match the exact program, all source-role/content pins and optional rich snapshot. Source paths under `/evidence/` normalize their host prefix only; content hashes remain mandatory. If no legacy source pins exist, only identical complete original records collapse.

No cross-schema, paraphrase, semantic-target-only or answer-only equivalence is asserted. Different proof worlds remain different groups. Matching keys with conflicting typed answers fail, as do contradictory split assignments for a chapter. These rules can retain semantic duplicates; the count is an inventory under stated equivalence, not a final uniqueness guarantee.

A native record with a validated complexity certificate is preferred over another variant of the same native path; otherwise the stable content hash breaks ties. The chosen record is copied intact. No statuses/fields are combined across variants. All alternatives and their provenance remain available in the index. Archived checks stay archived, unknown hops stay unknown and unassigned groups stay unassigned.

## Feasibility and release limits

`report.json` separates:

- all retained representative metadata, including archived legacy candidates;
- admitted-native-only inventory;
- native groups with validated complexity certificates;
- proof, wording, human and release statuses supplied by their original records.

Availability is not release eligibility. A legacy item declared `short` does not acquire a native certificate. Long wording is not a long-relational certificate. Pending human reviews, legacy wording and missing baseline features stay visible. No decisions, aliases, proof overlays, asset reviews or release views are applied.

`feasibility` uses the exact supplied policy to report total/group/identity/chapter/long-relational shortfalls, split counts and maximum possible capacity after chapter caps. Visual-character reporting gives observed opportunities/share and the necessary minimum implied by the identity floor (23 for 150 identities at a 15% minimum). The actual final identity-answer opportunity count can demand more. Counts of declared and certified native group items are separate.

These are **necessary inventory bounds**, not a solver proof. Whole-pool ratio violations may be repaired by selecting a subset. Independent group/split bounds do not establish joint feasibility, and no solver is invoked. Pair closure, edited-image assets, baselines, human/claim review and final global allocation remain mandatory. The current namespace cannot claim a completed 1,000-item selection merely because total inventory exceeds 1,000.

Read the full collection report before choosing the next generation family, source review, policy decision or eventual Qwen request build. Preserve the pool and parents as baselines; changes produce new versions.


## Bounded verification — 2026-10-31

All 147 benchmark1000 tests pass, including matching programs in different worlds, conflicting answers/splits, immutable resume/policy binding, unknown/unsafe sources, imported stores with no declared chapter list, unadmitted proposal exclusion, archived-status preservation and source/index/report tampering with rewritten checksums.

A real one-chapter run for `blue-exorcist__c002`, using all nine default sources and the existing frozen policy, yields 131 occurrences / 131 full record variants / 118 representatives / 13 duplicate occurrences. Representatives contain 17 admitted native records and 101 legacy records retaining `proof=archived_check`. The 101 legacy records are not 101 newly admitted native QA. Family metadata covers 16 saved families. Saved gates/receipts are validated; no CRL/page-ablation re-execution occurs during inventory.

The final artifact `/tmp/comicsqa-pool-blue-c002-v2` passes `verify-store` and identical-command resume. All 142 frozen legacy files still match. The implementation agent has not run full-collection ingestion; the full default-source report is user-pending. Do not extrapolate one chapter's shortages to full collection feasibility.
