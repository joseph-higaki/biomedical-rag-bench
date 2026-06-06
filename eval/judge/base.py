"""eval/judge/base.py — the shared scoring contract (build step 5).

Judging is the third eval concern (after production and the harness). It mirrors
the `retrievers/` design exactly: a `base.py` carrying the protocol + result shape +
shared helpers, then concrete judges per scoring strategy (deterministic.py now,
semantic.py once the LLM layer exists). The harness is judge-agnostic: it looks up a
judge by the question's `scoring` field and reads the same `JudgeResult` shape back,
so a question's verdict is computed the same way regardless of which retriever or
generator produced the answer.

What a judge scores
-------------------
A judge compares one *predicted answer* (the generator's raw text) against a
question's *ground truth* (derived from the graph at production time, never from an
LLM). It owns the extraction: pulling a number, a boolean, or an entity set out of
free-text model output and comparing it to ground truth. The scoring is type-aware
because the comparison differs by question shape — set overlap for traversals, exact
equality for counts, refusal-detection for unanswerables (see eval/README.md).

Determinism rule (eval/README.md)
---------------------------------
Deterministic scoring is preferred wherever the answer's *form* is checkable without
judgment (numbers, booleans, label sets against the graph's own vocabulary). The LLM
judge is reserved for `semantic` (type 10), where surface-form variation genuinely
needs a model to assess equivalence — and only after its agreement with human grades
(Cohen's kappa) clears the bar in the release notes. Every deterministic judge here
is pure-stdlib and hermetic: no network, no API key, free to run.

Additive-only, like the rest of the benchmark: new optional `JudgeResult` fields and
new `details` keys are fine forever; existing ones never change meaning, so a verdict
recorded by old code stays comparable to one from new code.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# A "found it in the text" match needs a normalized form shared by ground-truth
# labels and the model's free text, so punctuation/case/whitespace differences don't
# cause false misses. Lossy on non-ASCII (e.g. Greek letters in gene names) — the same
# known limitation the graph gazetteer carries; the eval/README escalation path (LLM
# entity linking) covers the cases where this proves too brittle.
_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^0-9a-z ]+")


def normalize(text: str) -> str:
    """Fold to the matchable form: lowercased, non-alphanumerics → spaces, ws collapsed."""
    return _WS.sub(" ", _NON_ALNUM.sub(" ", text.lower())).strip()


@dataclass
class JudgeResult:
    """What every judge returns. Field set is additive-only (see module docstring).

    `score` is a 0.0–1.0 quality (1.0 = fully correct; set judges report F1 so partial
    answers earn partial credit). `passed` is the boolean "counts as correct" verdict
    the headline accuracy is computed from. `verdict` is a short human-readable reason
    (handy when eyeballing a results table). `details` is the per-judge escape hatch —
    precision/recall/F1, the extracted value, the missing/extra members — additive keys
    only, the same contract `traversal_info` carries on the retriever side.
    """

    scoring: str  # Which strategy produced this verdict (mirrors the question's `scoring`).
    score: float  # 0.0–1.0 quality.
    passed: bool  # Did it count as correct (the accuracy numerator)?
    verdict: str  # Short human-readable reason.
    details: dict = field(default_factory=dict)  # Per-judge telemetry; additive keys only.


@runtime_checkable
class Judge(Protocol):
    """Structural contract: anything with `scoring` + `score(...)` is a Judge.

    A Protocol, not a base class (same choice as the Retriever protocol): judges match
    a shape rather than inherit. `runtime_checkable` lets tests assert `isinstance`.
    `ground_truth` is typed loosely because its shape is strategy-specific — a bare
    string for `string_match`, a list for the set strategies, "true"/"false" for
    `boolean` — and the judge for a given `scoring` knows which to expect.
    """

    scoring: str

    def score(
        self,
        predicted: str,
        ground_truth,
        *,
        answer_var: str | None = None,
        question: str | None = None,
    ) -> JudgeResult: ...
