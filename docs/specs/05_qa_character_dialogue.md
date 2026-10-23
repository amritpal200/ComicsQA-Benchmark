# 05 — Character, dialogue and interaction QA

## Dependencies
Character appearance index; optional dialogue index, captions and event index. Reliable identities may be human-annotated; no requirement for consecutive pages.

## Selection
Retrieve appearances within the same chapter by persistent character ID. Select relevant, potentially nonconsecutive pages in chronological order. Include enough surrounding context for humans to identify characters without privileged IDs.

## Task families
Character re-identification, who-spoke-to-whom, pronoun resolution with evidence, repeated interactions, object transfer, character state changes, multi-constraint character selection, intersection of appearances and dialogue.

## Preparation
Create candidate relationship sets; distinguish actual speech attribution from proximity guesses; preserve name aliases and entity IDs. Optional Qwen pass after retrieval to extract proposed interaction/event relations, then verify against images/annotations.

## Generation
Use task-specific Qwen3-VL-32B-Thinking prompt and evidence pack. Prefer canonical character ID/name answers or concise fact phrases. Require uniqueness and alternative-entity checks.

## Outputs
`data/candidates/character/` and `data/candidates/dialogue/` shards, manifests, evidence pointers.

## Tests
Identity collisions, same-name characters, absent speaker labels, nonconsecutive context order, answer alias matching, uniqueness and split boundaries.

## Codex request
Keep character and dialogue submodules separately runnable; propose interfaces and tests before changes.
