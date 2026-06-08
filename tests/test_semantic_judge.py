"""Tests for eval/judge/semantic.py — the type-10 LLM judge (build step 5).

Hermetic: a fake LLM returns a canned verdict, so the judge's *logic* — verdict parsing,
the empty-answer short-circuit, reference rendering, equivalence/difference scoring, and
the separate judge-cost telemetry — is pinned without the `anthropic` dep or an API key.
The model's grading quality is a separate concern, gated by the kappa calibration in the
release notes (eval/README.md), not asserted here.
"""
from __future__ import annotations

from dataclasses import dataclass

from eval.judge.base import Judge
from eval.judge.semantic import SemanticJudge


@dataclass
class FakeGen:
    text: str
    model: str = "fake-judge-1"
    input_tokens: int = 30
    output_tokens: int = 6


class FakeLLM:
    def __init__(self, reply: str):
        self._reply = reply
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt, *, system=None, tools=None):
        self.calls.append((prompt, system))
        return FakeGen(self._reply)


def _judge(reply):
    return SemanticJudge(llm=FakeLLM(reply))


# --- protocol / construction ------------------------------------------------

def test_matches_judge_protocol_and_scoring_key():
    j = SemanticJudge()  # no key, no network — llm is lazy
    assert isinstance(j, Judge)
    assert j.scoring == "semantic"


# --- verdict logic ----------------------------------------------------------

def test_equivalent_verdict_passes_and_records_judge_cost():
    j = _judge("EQUIVALENT\nCoumadin is the brand name for warfarin.")
    r = j.score("Coumadin", ["Warfarin"], question="Which anticoagulant…?")
    assert r.passed and r.score == 1.0
    d = r.details
    assert d["judge_model"] == "fake-judge-1"
    assert d["reference"] == "Warfarin" and d["candidate"] == "Coumadin"
    assert d["reason"].startswith("Coumadin is the brand")
    # the judge's own LLM cost is recorded separately, never the generator's billed tokens
    assert d["judge_input_tokens"] == 30 and d["judge_output_tokens"] == 6
    assert d["llm_called"] is True


def test_different_verdict_fails():
    j = _judge("DIFFERENT\nAspirin is a different drug.")
    r = j.score("Aspirin", ["Warfarin"], question="Q?")
    assert not r.passed and r.score == 0.0


def test_not_equivalent_phrasing_does_not_read_as_a_pass():
    # A first line that contains both words must not pass on the substring "EQUIVALENT".
    j = _judge("NOT EQUIVALENT / DIFFERENT\nwrong entity")
    r = j.score("Aspirin", ["Warfarin"], question="Q?")
    assert not r.passed


def test_empty_answer_short_circuits_without_calling_the_model():
    llm = FakeLLM("EQUIVALENT")  # would pass if (wrongly) called
    j = SemanticJudge(llm=llm)
    r = j.score("   ", ["Warfarin"], question="Q?")
    assert not r.passed and r.score == 0.0
    assert r.details["llm_called"] is False
    assert llm.calls == []  # never spent a model call on a non-answer


def test_reference_renders_a_multi_label_ground_truth():
    llm = FakeLLM("EQUIVALENT\nok")
    j = SemanticJudge(llm=llm)
    j.score("p53", ["TP53", "tumor protein p53"], question="Q?")
    _, system = llm.calls[0]
    # the user prompt carried both reference labels joined with OR
    user = llm.calls[0][0]
    assert "TP53 OR tumor protein p53" in user
    assert "EQUIVALENT or DIFFERENT" in system  # the grading rubric is the system channel
