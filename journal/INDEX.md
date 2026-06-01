# Session journal — index

Running log of Claude Code sessions building biomedical-rag-bench. Tracked in git
(build-cost / token-usage data, now published). Detailed notes per session live
in the dated files alongside this one.

> **▶ Resume here (next session).** Build-order **step 1 complete**; build order
> reframed to 8 steps with a ten-type taxonomy (see `eval/README.md`). Next:
> (1) step 2 — author question templates (one+ per type in the ten-type taxonomy);
> (2) populate `secrets/.env` with `NCBI_API_KEY` (10/s vs 3/s);
> (3) run the sample test (191 entities, all 9 kinds).
> Full context: [2026-05-30.md](2026-05-30.md) → "Next steps".

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

> Token figures are summed from the session transcript JSONL (`/cost` output does
> not reach Claude's context). Cache read is the bulk — full context re-read each
> turn. The Total column sums cleanly across rows for cumulative build cost.
