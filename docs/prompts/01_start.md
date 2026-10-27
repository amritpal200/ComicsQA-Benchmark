# First message to Codex

Read `AGENTS.md`, `docs/ROADMAP.md`, and `docs/specs/00_architecture.md` and `docs/specs/01_foundation.md`.

I am building a manga VQA benchmark using full PopManga human annotations, MAGI-3 structural annotations, Qwen-32B-Instruct panel captions/page summaries, a second MAGI-3 character-grounding stage (captions → character boxes → names), and optional depth maps. Annotation processing is on my CVC GPU server; question generation will be on MN5 with Qwen3-VL-32B-Thinking.

First inspect the existing repository and any accessible real dataset samples. Do **not** invent annotation fields. Propose the shared data schemas, dependency DAG, folder structure, data storage strategy, first implementation milestone and tests. Clearly distinguish existing artifacts from proposed components. **Do not write code yet. Wait for my approval.**
