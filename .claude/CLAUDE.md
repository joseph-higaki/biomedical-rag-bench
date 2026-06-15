# CLAUDE.md

Directional context for Claude Code sessions on this repository. The README is the canonical source of truth for what this project is and why; this file holds constraints and conventions Claude must respect when generating or modifying code.

If something here disagrees with the README, the README wins and this file should be updated.

## Project orientation

Read @README.md first. It covers the hypothesis, architecture, stack, file layout, build order, and release strategy. Do not duplicate that content here.

## Hard constraints

These rules govern code generation and may not be relaxed without explicit instruction.

- **Telemetry is additive only.** New retrievers may add keys to `RetrievalResult.traversal_info`. They never remove or rename existing keys. The `RetrievalResult` dataclass fields themselves are also additive — new optional fields only, never breaking changes. See @retrievers/base.py for the contract.
- **Question set is append-only.** New questions may be added to @eval/questions.jsonl. Existing questions are not removed, reworded, or relabeled. Ground-truth corrections require a MAJOR version bump and explicit user instruction.
- **Generator LLM is fixed within a run.** Never vary the generator across retriever conditions in the same eval run. The model is read from `GENERATOR_MODEL` env var and logged with every result.
- **No LangChain, LlamaIndex, or similar orchestration frameworks.** Hand-rolled retrievers, ~100 lines each. Abstraction layers obscure what is being measured.
- **Reasoning ruleset stays `empty` on the GraphDB repository in Project 1.** Reasoning is the variable Project 2 introduces.
- **Question content comes from hand-authored templates, not free-form LLM generation.** Each template specifies a question shape, the ground-truth query (SPARQL), the question type, and the entity sampling strategy; questions are instantiated by seeded programmatic sampling over the graph. Ground truth is derived from graph traversal, never LLM-generated. LLM assistance is permitted only for (a) optional stylistic phrasing variation of mechanically-generated questions (content unchanged) and (b) judge scoring on fuzzy/semantic questions. See @eval/README.md for the taxonomy and scoring strategy.

## Conventions

- **Retriever registration.** New retrievers go in `retrievers/<name>.py`, implement the `Retriever` protocol from @retrievers/base.py, and are registered in @eval/run_eval.py. Nothing else changes when adding a retriever.
- **URI namespaces.** Use existing biomedical vocabularies (`db:`, `do:`, `ncbigene:`, `uberon:`) for entity URIs. Hetionet schema lives under `hetio:`. Edge properties use RDF-star, not reification.
- **Two Turtle files, split by provenance.** The generated ABox / instance data is `data/rdf/hetionet.ttl` (regenerable by `make ingest-rdf`, gitignored under the `data/` bulk root). The hand-authored TBox is @ontology/hetionet-schema.ttl (committed source). Keep them separate; Project 2 populates the schema file without touching the generated instance data. `ontology/` holds committed schema only — never generated bulk.
- **Local development is default.** Code should run from a Python environment with `docker compose up` providing GraphDB. EC2 deployment is a separate milestone documented in `deployment/`. No code path should assume cloud-only.
- **Python runs through `uv`.** This project uses `uv` — there is no `python`/`python3` on PATH and no `requirements.txt`. Invoke Python as `uv run python …`. Base `dependencies` are empty; deps live in capability-scoped extras (`[project.optional-dependencies]`), so match the extra to the script: `hetionet_to_rdf.py` + the test suite → `--extra ingest` (ijson, pyoxigraph); `pubmed_fetch.py` → `--extra fetch` (httpx, dotenv); `build_vectors.py` → `--extra vector` (chromadb, sentence-transformers). E.g. `uv run --extra fetch python ingest/vector/pubmed_fetch.py …`. Never call bare `python`, `python3`, or `pip`.
- **Pin versions in code.** `pyproject.toml` plus `uv.lock` is the source of truth for dependencies. Versions referenced in prose are documentation, not configuration.

## Skill policy

Skills under `.claude/skills/` codify procedural workflows. Two rules govern them:

- **Proven before codified.** New workflows start as documented checklists (in a skill file the user follows manually) and only earn automation after at least one successful end-to-end execution. Don't author skills that autonomously execute untested procedures.
- **Guide rather than execute when steps are destructive or one-way.** For procedures involving git pushes, tags, deletions, deployments, or anything with permanent side effects, skills must present each command for the user to run rather than executing it autonomously. Claude is the briefing officer; the user is the operator. This holds even after the workflow is proven — automation can be added selectively for steps that are safe and boring, but irreversible steps stay user-executed.

When a procedural workflow becomes routine — adding a retriever, regenerating the question set, debugging GraphDB, running the eval — author a skill under `.claude/skills/<name>/SKILL.md`. CLAUDE.md holds constraints and policies; skills hold procedures.
