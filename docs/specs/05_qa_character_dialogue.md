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

## Answers must not be easy to guess (decided 2026-10-23)
Character-name answers are welcome. What we avoid is answers a model can get right without reading the pages:
- **Frequency guess:** main characters appear on dozens of pages (Naruto on 66, Denji on 72), so
  "who…?" is often right if the model just says the main character. Among questions whose answer is a
  character name, at most **~30%** (configurable) may have one of the chapter's most frequent
  characters as the answer (top-2 by page count). The rest should have characters the frequency guess
  gets wrong, with other plausible characters present in the same pages.
- **Small answer space:** yes/no, left/right, before/after, this/that are right by chance 50% of the
  time. Avoid them, and keep at most a small configurable share (~5%) where they are unavoidable.
  Prefer open answers with many possibilities: a character name, a page or panel reference, a count,
  an object or action, or a list (e.g. "which pages…", "who is standing left of X?" instead of
  "is A left of B?").
- **Measure it:** for every question store its chance level (1 / size of the answer space).
  Per chapter and task, report baselines: random guess, always-the-most-frequent-character, and text
  only. Rebalance generation if they score well.

## Outputs
`data/candidates/character/` and `data/candidates/dialogue/` shards, manifests, evidence pointers.

## Tests
Identity collisions, same-name characters, absent speaker labels, nonconsecutive context order, answer alias matching, uniqueness and split boundaries.

## Codex request
Keep character and dialogue submodules separately runnable; propose interfaces and tests before changes.
