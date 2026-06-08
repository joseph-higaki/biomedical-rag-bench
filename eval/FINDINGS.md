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
