"""eval/judge/base.py — the shared scoring contract (build step 5).

Mirrors retrievers/: a protocol + result shape + helpers, then concrete judges per strategy
(deterministic.py + the semantic LLM judge). The harness looks up a judge by the question's
`scoring` field and reads the same JudgeResult back. A judge compares the generator's raw
text against graph-derived ground truth, owning extraction; scoring is type-aware.

Determinism rule: deterministic scoring wherever form is checkable (numbers, booleans, label
sets) — pure-stdlib, hermetic. The LLM judge is reserved for `semantic` (type 10), only after
its Cohen's kappa vs human grades clears the bar. Additive-only JudgeResult fields/keys.
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
