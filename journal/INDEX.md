# Session journal — index

Running log of Claude Code sessions building biomedical-rag-bench. Tracked in git
(build-cost / token-usage data, now published). Detailed notes per session live
in the dated files alongside this one.

> **▶ Resume here (next session).** Build-order **step 2 in progress**: two
> templates authored + validated against GraphDB (1-hop nasal cavity, 2-hop
> Tiludronate). Ground truth is now derived from the full graph in GraphDB
> (decision B), not the smoke slice. Next:
> (1) author the remaining eight types, starting `04_3plus_hop_traversal`;
> (2) start the script-generated ground-truth/registry README early (read YAML +
> execute each `.rq` against GraphDB → generated `eval/templates/README.md`);
> (3) add a GraphDB query path to `run_query` (the engine-swap seam).
> Full context: [2026-06-03.md](2026-06-03.md) → "Next steps".

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

> Token figures are summed from the session transcript JSONL (`/cost` output does
> not reach Claude's context). Cache read is the bulk — full context re-read each
> turn. The Total column sums cleanly across rows for cumulative build cost.
