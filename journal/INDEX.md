# Session journal — index

Running log of Claude Code sessions building biomedical-rag-bench. Tracked in git
(build-cost / token-usage data, now published). Detailed notes per session live
in the dated files alongside this one.

> **▶ Resume here (next session).** Build-order step 1, **vector half**: author
> `ingest/pubmed_fetch.py` (interface `--entities <ttl>`; per-kind PubMed query
> strategy — bare gene symbols and GO-term phrases are poor queries) → climb the
> 5 → 191 → ~47k abstract ladder → Chroma → similarity query. Scripts still don't
> exist; needs `vector`/`fetch` extras (first torch install) + the shared
> `secrets/.env` loader. The **full RDF graph (11.2M triples) is loaded in
> GraphDB**. Full context: [2026-05-26.md](2026-05-26.md) → "Next steps".

**Convention.** One file per session, named `YYYY-MM-DD.md` (add `-02`, `-03` for
multiple sessions in a day). Each session: record the model, fill the token table
from `/cost` before closing, and add a row here. Sum the token columns for the
cumulative cost of building the solution.

| Date | Session | Model | Input | Output | Cache read | Cache write | Total | Focus |
|---|---|---|---|---|---|---|---|---|
| 2026-05-24 | 01 | Claude Opus 4.7 (`claude-opus-4-7`) | 3,652 | 124,584 | 4,875,390 | 167,588 | 5,171,214 | Bootstrap: uv env, Hetionet download + streaming RDF-star transform, offline SPARQL validation, test scaffold session_id: 54049866-7d28-49eb-9554-fa8ecb089e03|
| 2026-05-25 | 02 | Claude Opus 4.7 (`claude-opus-4-7`) | 10,546 | 119,069 | 9,746,508 | 236,407 | 10,112,530 | GraphDB 11 license wiring, smoke slice load + offline/live query parity, session-journal skill, commit-history AI-attribution cleanup |
| 2026-05-26 | 03 | Claude Opus 4.7 (`claude-opus-4-7`) | 725 | 29,115 | 464,797 | 44,534 | 539,171 | Full-graph ingest: 467 MB Turtle loaded to GraphDB via REST statements endpoint (11.2M triples verified), README load/verify fixes, gitignore generated ttl, PubMed fetch strategy designed |

> Token figures are summed from the session transcript JSONL (`/cost` output does
> not reach Claude's context). Cache read is the bulk — full context re-read each
> turn. The Total column sums cleanly across rows for cumulative build cost.
