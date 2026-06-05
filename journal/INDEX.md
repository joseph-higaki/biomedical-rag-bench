# Session journal — index

Running log of Claude Code sessions building biomedical-rag-bench. Tracked in git
(build-cost / token-usage data, now published). Detailed notes per session live
in the dated files alongside this one.

> **▶ Resume here (next session).** Build-order **step 3 complete**: the eval
> producer (`eval/produce/`) instantiates all ten types into
> **`eval/questions.jsonl` (58 questions)**, validated by `validate.py`. Five sampler
> regimes (fixed / single-direct / single-post-check / paired / paired-boolean);
> constrained candidate-query sampling throughout. Central lesson: a candidate query
> must mirror every constraint the `.rq` applies (the polymorphic-`participates` bug).
> Next: **step 4 — three retrievers** (vector, graph, closed-book null) behind the
> `Retriever` protocol. Carried into step 4: graph retriever must be inverse-aware for
> `both`-direction edges; add `NCBI_API_KEY` to `secrets/.env` before the vector-side
> PubMed fetch.
> Full context: [2026-06-05.md](2026-06-05.md) → "Next steps".

**Convention.** One file per session, named `YYYY-MM-DD.md` (add `-02`, `-03` for
multiple sessions in a day). Each session: record the model, fill the token table
from `/cost` before closing, and add a row here. Sum the token columns for the
cumulative cost of building the solution.

| Date | Session | Model | Input | Output | Cache read | Cache write | Total | Focus |
|---|---|---|---|---|---|---|---|---|
| 2026-05-24 | 01 | Claude Opus 4.7 (`claude-opus-4-7`) | 3,652 | 124,584 | 4,875,390 | 167,588 | 5,171,214 | Bootstrap: uv env, Hetionet download + streaming RDF-star transform, offline SPARQL validation, test scaffold session_id: 54049866-7d28-49eb-9554-fa8ecb089e03|
| 2026-05-25 | 02 | Claude Opus 4.7 (`claude-opus-4-7`) | 10,546 | 119,069 | 9,746,508 | 236,407 | 10,112,530 | GraphDB 11 license wiring, smoke slice load + offline/live query parity, session-journal skill, commit-history AI-attribution cleanup |
| 2026-05-26 | 03 | Claude Opus 4.7 (`claude-opus-4-7`) | 725 | 29,115 | 464,797 | 44,534 | 539,171 | Full-graph ingest: 467 MB Turtle loaded to GraphDB via REST statements endpoint (11.2M triples verified), README load/verify fixes, gitignore generated ttl, PubMed fetch strategy designed |
| 2026-05-27 | 04 | Claude Opus 4.7 (`claude-opus-4-7`) | 12,904 | 73,643 | 1,523,666 | 143,480 | 1,753,693 | Vector half written: ingest/ split into rdf/ and vector/; pubmed_fetch.py + build_vectors.py + hermetic tests; not yet executed |
| 2026-05-29 | 05 | Claude Opus 4.8 (`claude-opus-4-8`) | 5,581 | 42,555 | 2,753,412 | 122,062 | 2,923,610 | Step 1 complete: committed session 04 work, fixed uv extras, CPU torch pin, smoke test end-to-end, E-cadherin/CDH1 retrieval observation documented |
| 2026-05-30 | 06 | Claude Opus 4.8 (`claude-opus-4-8`) | 4,391 | 23,317 | 1,193,709 | 97,631 | 1,319,048 | Docs: recorded 9 design decisions — H7, closed-book baseline, ten-type taxonomy + eval/README.md, type-aware scoring (RAGAS dropped), 8-step build order, CLAUDE.md template-gen reconciliation |
| 2026-06-01 | 07 | Claude Opus 4.8 (`claude-opus-4-8`) | 5,585 | 32,342 | 1,253,796 | 44,668 | 1,336,391 | Step 2 started: declarative YAML template format + separate `.rq` ground-truth query; first template authored (type 2, genes-expressed-in-anatomy), not yet smoke-tested; per-step isolated-smoke checks added to build order; "oracle"→"ground_truth" rename |
| 2026-06-03 | 08 | Claude Opus 4.8 (`claude-opus-4-8`) | 18,104 | 82,809 | 3,471,047 | 92,231 | 3,664,191 | Step 2: 2-hop template authored (Compound→treats→Disease→associates→Gene); decision B — ground truth derived from full GraphDB, not the smoke slice (slice neighborhoods disjoint); 1-hop re-seeded adrenal→nasal cavity for bounded answer; `type_id` convention; `run_ground_truth.py` runner; README steps 2/3/6 reframed |
| 2026-06-04 | 09 | Claude Opus 4.8 (`claude-opus-4-8`) | 4,938 | 171,021 | 14,997,091 | 206,240 | 15,379,290 | Step 2 complete: all ten question types authored + validated against full GraphDB; `build_registry.py` registry generator + `--verify`; GraphDB-only query engine (pyoxigraph dropped); `.rq` registry frontmatter (multi-seed); node-attribute transform extension (chromosome/description/inchikey) + full re-ingest to ground type 01 (0-hop attribute) |
| 2026-06-05 | 10 | Claude Opus 4.8 (`claude-opus-4-8`) | 21,983 | 208,996 | 26,418,755 | 661,400 | 27,311,134 | Step 3 complete: eval producer (`eval/produce/`) across 7 increments — 5 sampler regimes (fixed/single-direct/single-post-check/paired/paired-boolean), constrained candidate-query sampling; `validate.py` gate + 13 hermetic tests; 4-level producer README; 5 fuzzy questions authored; full run → `eval/questions.jsonl` (58 across all ten types, validated). Key fix: `target_type` mirrors the `.rq` (polymorphic `participates`) — ~50× speedup |

> Token figures are summed from the session transcript JSONL (`/cost` output does
> not reach Claude's context). Cache read is the bulk — full context re-read each
> turn. The Total column sums cleanly across rows for cumulative build cost.
