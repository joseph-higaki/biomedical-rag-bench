"""eval/judge/semantic.py — the LLM judge for type-10 fuzzy/semantic questions (build step 5).

The one non-deterministic judge, and the only one that needs a model. Nine of the ten
question types compare a number / boolean / label-set against graph-derived ground truth
with pure-stdlib extraction (deterministic.py); type 10 cannot. Its questions are clinical
descriptions whose answer is a single canonical entity ("Which oral anticoagulant, a
vitamin K antagonist first developed as a rodenticide…" → Warfarin), and a correct model
answer legitimately varies in surface form: a brand name (Coumadin ≡ Warfarin), a gene
symbol vs. protein name (p53 ≡ TP53), an abbreviation, or a possessive/punctuation variant
(Alzheimer disease ≡ "Alzheimer's disease"). Deciding *same entity?* across that variation
is the judgment the determinism rule (eval/README.md) reserves for an LLM.

Why this is honest, not circular
--------------------------------
The ground truth is still graph-derived, never LLM-authored — the judge only assesses
*equivalence* between the model's answer and that fixed reference, it does not invent the
answer. To keep the judge from grading the generator's wording charitably to itself, its
model is a SEPARATE, configurable knob (`JUDGE_MODEL`), logged in `details` with every
verdict, and it is pinned to temperature 0 for reproducibility. The judge is the system's
*measuring instrument*, not a second contestant.

NOT YET TRUSTED — calibration is a release gate
-----------------------------------------------
Per eval/README.md the LLM judge is trusted only after its agreement with human grades
(Cohen's kappa) is reported in the release notes and clears > 0.7. This module builds the
*mechanism*; it does not declare the instrument calibrated. Every verdict therefore records
what a human grader needs to adjudicate it — the reference, the candidate, the verdict, and
the model's stated reason — so the held-out kappa study can be run against real verdicts.

Provider-neutral like the rest: the judge depends only on the `Generator` protocol (it
calls `.generate(prompt, system=)` and reads `.text` / `.usage`), with a concrete
AnthropicGenerator built lazily as the default and injectable for hermetic tests — the same
pattern the retrievers and the sparqlgen writer use.
"""
from __future__ import annotations

import os

from eval.judge.base import JudgeResult

# The judge model is its own factor, separate from the generator under test (see docstring).
DEFAULT_JUDGE_MODEL = os.environ.get("JUDGE_MODEL", "claude-haiku-4-5")

_SYSTEM = (
    "You grade answers to a biomedical identification quiz. You are given the QUESTION, the "
    "REFERENCE answer (the correct entity, derived from a knowledge graph), and a CANDIDATE "
    "answer from a model. Decide only whether the CANDIDATE names the SAME biomedical entity "
    "as the REFERENCE.\n"
    "Treat as the same entity: synonyms, brand vs. generic drug names (Coumadin = Warfarin), "
    "gene symbol vs. protein vs. full name (p53 = TP53 = tumor protein p53), standard "
    "abbreviations, and punctuation/possessive/spacing variants (Alzheimer disease = "
    "Alzheimer's disease).\n"
    "Treat as NOT the same: a different entity, a broader/narrower category instead of the "
    "specific entity, or an answer that hedges among several options or refuses without "
    "committing to one.\n"
    "Respond with EXACTLY one word on the first line — EQUIVALENT or DIFFERENT — then, on a "
    "second line, a reason of at most 15 words."
)


class SemanticJudge:
    """`semantic` — LLM-assessed entity equivalence for type-10 questions.

    Injectable `llm` (any object exposing `.generate(prompt, system=) -> result with
    `.text` and billed-token attrs) for hermetic tests; the default AnthropicGenerator is
    built lazily at temperature 0, so importing/constructing needs no `anthropic` dep and no
    API key. An empty or whitespace candidate short-circuits to DIFFERENT with no model call
    (a non-answer cannot be equivalent, and the call would be wasted spend).
    """

    scoring = "semantic"

    def __init__(self, *, model: str | None = None, temperature: float = 0.0, llm=None) -> None:
        self.model = model or DEFAULT_JUDGE_MODEL
        # Pinned to 0 for a reproducible instrument; an explicit, logged attribute (not buried
        # in the lazy build) so every verdict records the temperature beside the judge model.
        self.temperature = temperature
        self._llm = llm

    def _ensure_llm(self):
        if self._llm is None:
            from eval.generate.anthropic_generator import AnthropicGenerator

            # self.temperature (0 by default) + a short cap: the verdict is one word plus a
            # brief reason, and a judge must be as reproducible as the provider allows.
            self._llm = AnthropicGenerator(self.model, max_tokens=128, temperature=self.temperature)
        return self._llm

    @staticmethod
    def _reference(ground_truth) -> str:
        gt = ground_truth if isinstance(ground_truth, list) else [ground_truth]
        labels = [str(x) for x in gt]
        return " OR ".join(labels) if len(labels) > 1 else (labels[0] if labels else "")

    @staticmethod
    def _parse(text: str) -> tuple[bool, str]:
        """First-line verdict token → (is_equivalent, reason). Robust to extra prose."""
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        verdict_line = lines[0].upper() if lines else ""
        reason = lines[1] if len(lines) > 1 else ""
        # `not DIFFERENT and EQUIVALENT` so a stray "not equivalent" can't read as a pass.
        is_equiv = "EQUIVALENT" in verdict_line and "DIFFERENT" not in verdict_line
        return is_equiv, reason

    def score(self, predicted, ground_truth, *, answer_var=None, question=None) -> JudgeResult:
        reference = self._reference(ground_truth)
        candidate = (predicted or "").strip()

        if not candidate:  # non-answer: cannot be equivalent; don't spend a model call
            return JudgeResult(
                scoring=self.scoring, score=0.0, passed=False,
                verdict="empty answer — not equivalent",
                details={"judge_model": self.model, "judge_temperature": self.temperature,
                         "reference": reference, "candidate": "", "llm_called": False},
            )

        llm = self._ensure_llm()
        user = f"QUESTION: {question or ''}\nREFERENCE: {reference}\nCANDIDATE: {candidate}"
        gr = llm.generate(user, system=_SYSTEM)
        is_equiv, reason = self._parse(gr.text)

        return JudgeResult(
            scoring=self.scoring,
            score=1.0 if is_equiv else 0.0,
            passed=is_equiv,
            verdict=f"{'equivalent' if is_equiv else 'different'} — {reason}" if reason
                    else ("equivalent" if is_equiv else "different"),
            details={
                "judge_model": getattr(gr, "model", self.model),
                "judge_temperature": getattr(gr, "temperature", self.temperature),
                "reference": reference,
                "candidate": candidate[:200],
                "reason": reason,
                "raw_verdict": gr.text[:200],
                # The judge's own LLM cost — a measuring-instrument cost, logged separately
                # from the generator's billed tokens, never summed with them.
                "judge_input_tokens": getattr(gr, "input_tokens", None),
                "judge_output_tokens": getattr(gr, "output_tokens", None),
                "llm_called": True,
            },
        )
