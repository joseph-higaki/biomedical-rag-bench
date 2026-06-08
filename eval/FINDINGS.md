# Eval findings — curated observations

Hand-authored, durable interpretation of eval runs. **This file is never written by
`--run`** — it is the home for observations that must survive future runs. Append a dated
entry per run worth recording; don't rewrite history.

The companion `eval/LATEST_RUN.md` is the opposite: a *generated* snapshot of the most
recent `--run`, overwritten every time. The machine-readable rows live in
`eval/results/*.jsonl` (gitignored); definitive accuracy / recall / H7 metrics come from
the analysis notebook + dashboard that read those rows. This file is the connective tissue
— what a run *meant*, not its raw tables.

When an observation hardens from "this run showed X" into "this is how the benchmark
behaves," promote it to `eval/README.md` (the methodology reference). Findings graduate.

---

## Validity caveats (how to read specific conditions)

- **Closed-book is structurally torn on unanswerables (type 08).** One constant system
  prompt — held identical across all retriever conditions for comparability — cannot
  simultaneously tell the model "answer from your own knowledge, don't refuse for lack of
  context" (correct for knowledge questions 01–07/09) and "refuse, the answer set is empty"
  (correct for the unanswerable type 08). Whichever way the prompt leans, closed-book pays
  on the other side: lean toward refusing and it under-answers the knowledge questions;
  lean toward answering (current prompt) and it *hallucinates* on type 08. **This is not a
  prompt bug to tune away — it is evidence for H7.** A retriever that supplies type 08's
  actual (empty) result set is exactly what lets the model answer "None" correctly. Do not
  read closed-book's type-08 score as a knowledge measure; read it as the baseline that
  retrieval is meant to fix. Don't re-tune the prompt to chase it (and the prompt must stay
  constant across conditions regardless).

---

## Run log (newest first)

### 2026-06-08 — cross-retriever, all three arms (`claude-haiku-4-5`)

The first real cross-retriever comparison — the benchmark's actual question. Same 9
deterministic-judged questions (selection is deterministic), same generator, same prompt;
only the retriever varies. Runs: `closed_book` `20260608T103244`, `graph_neighborhood`
`20260608T105929`, `vector` `20260608T110036`.

| type | closed | graph | vector |
|---|---|---|---|
| 01_0hop_attribute | ✅ | ✅ | ✅ |
| 02_1hop_factoid | ❌ r1/11 | ✅ **r11/11** | ❌ r0/11 |
| 03_2hop_traversal | ❌ r6/18 | ❌ r0/18 | ❌ r0/18 |
| 04_3plus_hop_traversal | ❌ r0/17 | ❌ r0/17 | ❌ r0/17 |
| 05_aggregative | ❌ | ❌ (40 vs 184) | ❌ |
| 06_set_intersection | ❌ r0/3 | ❌ r2/3 | ❌ r0/3 |
| 07_set_difference | ❌ r0/2 | ❌ r0/2 | ❌ r0/2 |
| 08_negative_unanswerable | ❌ halluc | ✅ "None" | ✅ refuse |
| 09_path_existence | ❌ | ❌ | ❌ |
| **passed** | **1/9** | **3/9** | **2/9** |
| tokens in / out | 1.6k / 1.6k | 9.4k / 0.2k | 13k / 0.7k |

**Caveat: n=1 per type — directional, not evidence.** Read the *where*, not the count.

1. **H7's crossover is real and located.** Closed-book passes only the memorized 0-hop
   attribute. Graph adds exactly the two questions where *supplied membership* is the
   answer: the 1-hop factoid (F1 0.08 → **1.00** — from hallucinating 1/11 to naming all 11
   with zero extras) and the unanswerable (hallucination → correct "None"). Retrieval helps
   precisely where the answer is a graph fact the model can't memorize.

2. **The type-08 answer-vs-refuse caveat resolved live, as predicted** (see caveat above).
   With the actual (empty) neighborhood in context the model just says "None" — the tension
   only ever existed for closed-book, and retrieval closes it exactly where expected.

3. **The neighborhood retriever has a hard ceiling, and it's visible.** Graph *fails*
   2-hop / 3+-hop / path (03/04/09) with "I can only answer from the provided context" — the
   bounded k-hop doesn't reach — and 05 undercounts (40 vs 184) because the per-predicate fan
   caps truncate the set before aggregation. Tellingly, graph's 2-hop recall (0/18) is
   *worse* than closed-book's (6/18): closed-book guesses real genes from parametric
   knowledge, while graph faithfully reports only its too-shallow context and refuses the
   rest. **This is the empirical case for the deferred `graph_sparqlgen` arm** — executing the
   real query is the only way to answer deep-structural questions; the neighborhood retriever
   can't fake it.

4. **Vector (smoke store, 28 abstracts) ≈ closed-book + noise — not a fair arm yet.** It
   covers none of the question entities, so its 2 passes are parametric fallback (01) and
   refuse-for-lack-of-context (08, right answer for the wrong reason) — and it is the *most
   expensive* input (13k tokens) for the least signal. A real vector comparison needs a
   sample/full-scale corpus; that is a separate ingest, not this run.

**For the analysis layer:** grounding cut graph's *output* tokens 1.6k → 0.2k (the model
stops rambling when it has facts) but raised input 6–8×. Accuracy-per-token is the right
lens — the notebook should compute it, not just raw accuracy.

### 2026-06-08 — `closed_book → claude-haiku-4-5` (run `20260608T103244`, 1/9)

First run after fixing the three caveats the 2026-06-06 smoke exposed (commit `99ed610`).
Headline is still **1/9**, which is expected and not the metric to move — closed-book has
no graph context, and H7 predicts it fails every structural question. The point was
*validity*; the failure modes shifted in the ways that confirm the fixes landed.

- **Caveat #1 (refusal bias) — fixed, and it surfaced the type-08 tension above.** The
  assertive no-context wording works: type 02 went from a preamble-laden refusal to a clean
  bare list (`SOX9 / PAX8 / …`), extras dropped 29 → 13; types 04/06/09 now *attempt*
  (`I'll identify…`, `I need to trace…`) instead of flatly refusing. The cost is type 08,
  which now hallucinates (`Testolactone treats Breast cancer, Gynecomastia`) — the inherent
  closed-book trade-off, recorded as a caveat above rather than tuned away.

- **Caveat #2 (verbosity → set precision) — partially fixed; the rest is a model-obedience
  limit, not a judge bug.** The judge-side fix (drop markdown-header / `Section:` scaffolding
  lines from the claimed set) is in and unit-tested, but no scaffolding lines appeared this
  run. The *prose* preamble (`To answer this question, I need to…` on types 03/06/09)
  persists and still inflates "extra" — and it is the case I deliberately left unfiltered,
  because a reasoning sentence isn't deterministically separable from a real label. Type 02
  proves Haiku *can* emit a bare list; it just obeys the format inconsistently. The lever is
  a stronger model or few-shot exemplars, not the deterministic judge.

- **Caveat #3 (binary judge missed `don't`) — fixed and unit-verified.** `I don't have …`
  now scores as a refusal (apostrophe-insensitive, contraction family added). This run's
  type-08 fail is a genuine hallucination (the model answered), not a judge miss; the fix is
  proven by `tests/test_judges.py`, not by this row.

**Not yet done from here:** the real benchmark question — `graph_neighborhood` + `vector`
e2e on the same questions (needs GraphDB + Chroma up) — and the type-10 `semantic` LLM
judge. Closed-book alone is only the baseline arm.
