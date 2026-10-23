# 06 — Graph-first, constraint and hybrid multi-hop QA

## Dependencies
Chapter graph + supporting evidence builders. Do not run before graph and provenance validation.

## Algorithm
1. Construct chapter graph and candidate typed relations.
2. Enumerate meaningful, diverse graph paths / conjunctive queries / set intersections / temporal-spatial constraints.
3. Execute query **before** language generation; require a unique supported answer (or explicit valid set answer).
4. Retrieve original pages/panels for all required facts, including disambiguating context.
5. Optionally ask Qwen3-VL-32B-Thinking to select interesting paths or propose additional relationships; revalidate all new relations.
6. Ask Qwen to verbalize the verified program into a natural question, not invent the answer.
7. Re-execute and audit question constraints; reject unsupported, tautological, artificial or ambiguous chains.

## Task families
Multi-character, multi-page, spatial+dialogue, temporal+identity, exclusion (only with complete evidence), reverse reasoning, entity intersections, object-state chains.

## Difficulty
Record semantic reasoning steps separately from raw graph edges; control distractors, distance between pages, independent constraints, number of entities. Human must be able to follow a concise evidence trail.

## Outputs
`data/candidates/graph/` and `data/candidates/hybrid/` with executable query/graph path in **private** metadata.

## Tests
Unique answers, alternative candidates, incomplete annotation negation, nonexistent graph edge, graph path reconstruction, multiple-page evidence completeness.

## Codex request
Show sample queries against real graph schema and an ambiguity-check plan before implementation.
