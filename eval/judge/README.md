# Judging

The third eval concern (after [production](../produce/README.md) and the harness):
scoring a generated answer against ground truth. It mirrors the
[`retrievers/`](../../retrievers/README.md) design — a `base.py` contract plus
pluggable implementations — so the harness is judge-agnostic: it looks a judge up by
the question's `scoring` field and reads the same `JudgeResult` back, whatever
retriever or generator produced the answer.

`eval/README.md` owns the eval *design* (taxonomy, distribution, the determinism
rationale). This file documents the judging *subsystem*: the contract, the per-strategy
judges, and the extraction limits.

> **Status (build step 5).** All six judges built and tested: the five **deterministic**
> judges (`string_match`, `set_match`, `numerical`, `binary`, `boolean`,
> `tests/test_judges.py`) and the **`semantic`** LLM judge (type 10,
> `tests/test_semantic_judge.py`). The harness loop calls them via `eval/run_eval.py --run`;
> add `--include-semantic` (or `--types 10`) to score type-10 with the LLM judge.
> **Calibration pending:** the semantic judge is *not yet trusted* per the determinism rule —
> formal Cohen's kappa over a ≥20-question human-graded hold-out is a release gate, blocked on
> expanding the append-only type-10 set (only 6 today). First-run verdicts were manually
> spot-checked (12/12 correct, including the cross-vocabulary `p53`≡`TP53` accept).

## The contract — `base.py`

```python
@dataclass
class JudgeResult:
    scoring: str    # which strategy produced this verdict
    score: float    # 0.0–1.0 quality (set judges report F1 for partial credit)
    passed: bool    # counts-as-correct — the accuracy numerator
    verdict: str    # short human-readable reason
    details: dict   # per-judge telemetry (precision/recall/F1, extracted value, …)

class Judge(Protocol):              # structural, runtime_checkable — match, don't inherit
    scoring: str
    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult: ...
```

Additive-only, like `RetrievalResult` and `traversal_info`: new optional `JudgeResult`
fields and new `details` keys are fine forever; existing ones never change meaning, so a
verdict from old code stays comparable to one from new code.

`predicted` is the generator's **raw text**. Each judge owns its extraction — pulling a
number, a boolean, or an entity set out of free text and comparing it to the graph-derived
ground truth. The `answer_var`/`question` keywords are part of the shared signature so the
harness calls every judge identically; a future synonym-aware judge will use them.

**Guiding rule:** lenient about *form* (phrasing, list style, surrounding prose), strict
about *content* (is the right value / set / polarity actually asserted?). Where extraction
can't be done deterministically without guessing, the judge reports what it can verify and
**flags** the rest rather than over-claiming — see the limits below.

## Strategy → judge map

Keyed by the question's `scoring` field (set at production time). Nine of ten types are
deterministic; only `semantic` needs an LLM.

| `scoring` | Question types | Judge | Verdict basis |
|---|---|---|---|
| `string_match` | 01 (0-hop attribute) | `StringMatchJudge` | ground-truth value present as a token run | ✅ |
| `set_match` | 02, 03, 04, 06, 07 | `SetMatchJudge` | set overlap vs ground-truth labels (F1 / recall) | ✅ |
| `numerical` | 05 (aggregative) | `NumericalJudge` | expected count among extracted numbers | ✅ |
| `binary` | 08 (negative/unanswerable) | `BinaryJudge` | refusal detected (empty ground truth) | ✅ |
| `boolean` | 09 (path existence) | `BooleanJudge` | yes/no polarity matches | ✅ |
| `semantic` | 10 (fuzzy/semantic) | `SemanticJudge` (LLM) | model-assessed entity equivalence | ✅ (uncalibrated) |

Built from each judge's own `scoring` attribute (`DETERMINISTIC_JUDGES` in
`deterministic.py`) so the lookup key can't drift from the strategy a verdict reports.

## Per-judge notes

- **`string_match`** — token-level containment, not substring, so the chromosome `"11"`
  is not matched inside `"111"`. Lenient about surrounding prose.
- **`set_match`** — **recall** is always measured: each ground-truth label is searched as
  a token run over the whole answer (form-independent). **Precision** (did the model
  over-claim?) is only measured when the answer is **list-shaped** (≥2 lines or
  bullet/numbered markers) and so can be split into discrete claims; then `score` is F1
  and `passed` requires an exact set. On **prose** answers, comma-splitting would shred
  multi-word labels and invent false members, so precision is skipped (`basis="recall_only"`,
  `precision=None`) and `passed` requires full recall only. These per-question precision /
  recall / F1 values are defined — and rolled up into the benchmark-level metrics
  (accuracy, and the type-08 sensitivity/specificity that test H2) — in the
  [Metrics section of `eval/README.md`](../README.md#metrics).
- **`numerical`** — passes iff the expected count is one of the integers extracted from the
  answer (handles thousands separators), so other numbers in the sentence don't matter.
- **`binary`** — for the designed empty-ground-truth case, passes iff the answer asserts
  emptiness/negation. It verifies an explicit **refusal**; it does *not* prove the absence
  of hallucinated entities (see limits).
- **`boolean`** — detects an affirmative vs negative cue; an ambiguous answer (both or
  neither) fails with `ambiguous=True` rather than guessing.
- **`semantic`** (LLM, `semantic.py`) — for type-10's clinical-description questions, whose
  answer is one canonical entity. The model decides *same entity?* between the candidate and
  the graph-derived reference, accepting synonyms / brand vs. generic / gene-symbol vs.
  protein / possessive variants and rejecting different entities or non-committal hedges. The
  judge is a **separate, configurable model** (`JUDGE_MODEL`, default `claude-haiku-4-5`),
  pinned to temperature 0, with its own LLM cost logged in `details` (`judge_input_tokens` /
  `judge_output_tokens`) — never summed with the generator's billed tokens. An empty/refusal
  answer short-circuits to *different* with no model call. This is the one case the
  deterministic judges structurally can't reach: token-match fails `p53` against `TP53` (no
  shared token), but they are the same gene — exactly the equivalence the LLM judge supplies.
  **Not trusted until kappa-calibrated** (see Status + limits).

## Known extraction limits (and the escalation path)

Two things can't be done deterministically without guessing, so they are flagged, not faked:

1. **Precision on prose set answers.** Separating real labels from surrounding words needs
   entity recognition. `set_match` reports recall-only and marks it.
2. **True hallucination detection** for `binary`. Proving the model named *fake* entities
   needs entity linking; the deterministic judge verifies refusal instead.

Both are the **escalate to LLM-assisted entity linking** path in `eval/README.md`: adopt it
for a specific type only if a manual spot-check shows the deterministic judge is too brittle
there. The `semantic` LLM judge (type 10) is calibrated against human grades (Cohen's kappa,
reported in the release notes) before it is trusted.

## Adding a judge

Same shape as adding a retriever: implement the `Judge` protocol in a file under
`eval/judge/`, expose it in the strategy registry, register the harness lookup. Nothing
else changes — the harness reads `JudgeResult` and never branches on which judge ran.
