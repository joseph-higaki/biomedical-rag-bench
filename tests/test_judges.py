"""Tests for eval/judge/ — the deterministic scoring judges (build step 5 smoke).

This is the README's stated isolated smoke for the judging concern: score known
correct/incorrect answer pairs through each judge and confirm the expected verdict.
Hermetic and stdlib-only (the deterministic judges take no network or API key); the
semantic/LLM judge is a separate increment and is not exercised here.

These tests pin the *judgment*, which is where a silent scoring bug would otherwise
go unnoticed — a too-lenient set judge inflates every retriever's accuracy equally and
quietly invalidates the whole comparison.
"""
from __future__ import annotations

from eval.judge.base import Judge, normalize
from eval.judge.deterministic import DETERMINISTIC_JUDGES


def _j(scoring: str) -> Judge:
    return DETERMINISTIC_JUDGES[scoring]


def test_registry_covers_the_nine_deterministic_strategies():
    assert set(DETERMINISTIC_JUDGES) == {
        "string_match", "set_match", "numerical", "binary", "boolean",
    }
    for s, judge in DETERMINISTIC_JUDGES.items():
        assert isinstance(judge, Judge)  # runtime_checkable protocol
        assert judge.scoring == s        # key cannot drift from the verdict's strategy
        assert judge.version == "v1"     # per-strategy version stamped into per-row judge_id


def test_normalize_folds_case_punctuation_whitespace():
    assert normalize("Non-Small  Cell!") == "non small cell"


# --- string_match (type 01) -------------------------------------------------

def test_string_match_found_in_prose():
    r = _j("string_match").score("The gene HTR3B is located on chromosome 11.", "11")
    assert r.passed and r.score == 1.0


def test_string_match_does_not_match_substring_of_a_longer_number():
    # "11" must not be found inside "111" — token-level, not substring.
    r = _j("string_match").score("It sits on chromosome 111.", "11")
    assert not r.passed


# --- set_match (types 02/03/04/06/07) ---------------------------------------

def test_set_match_exact_list_passes_with_f1_one():
    gt = ["BMP4", "CHD7", "COCH"]
    answer = "- BMP4\n- CHD7\n- COCH"
    r = _j("set_match").score(answer, gt)
    assert r.passed and r.score == 1.0
    assert r.details["basis"] == "set" and r.details["precision"] == 1.0


def test_set_match_missing_member_fails_with_partial_recall():
    gt = ["BMP4", "CHD7", "COCH"]
    r = _j("set_match").score("- BMP4\n- CHD7", gt)
    assert not r.passed
    assert r.details["recall"] == round(2 / 3, 4)
    assert "COCH" in r.details["missing"]


def test_set_match_over_claim_fails_on_precision():
    gt = ["BMP4", "CHD7"]
    # All ground truth present (recall 1.0) but an extra false member → not exact.
    r = _j("set_match").score("- BMP4\n- CHD7\n- FAKE1", gt)
    assert r.details["recall"] == 1.0
    assert not r.passed and r.details["extra"]


def test_set_match_ignores_markdown_header_in_precision():
    # FINDINGS caveat #2: a title line is scaffolding, not a claimed entity — counting it
    # as an over-claim wrongly tanked precision. The header must not appear in `extra`.
    gt = ["BMP4", "CHD7", "COCH"]
    answer = "# Genes Expressed in Semicircular Canal\n- BMP4\n- CHD7\n- COCH"
    r = _j("set_match").score(answer, gt)
    assert r.passed and r.score == 1.0
    assert not r.details["extra"]


def test_set_match_ignores_label_lead_in_in_precision():
    # A bare "Section:" lead-in is likewise scaffolding, not a member.
    gt = ["BMP4", "CHD7"]
    r = _j("set_match").score("The genes are:\n- BMP4\n- CHD7", gt)
    assert r.passed and not r.details["extra"]


def test_set_match_prose_is_recall_only():
    gt = ["BMP4", "CHD7", "COCH"]
    r = _j("set_match").score("The genes are BMP4, CHD7 and COCH.", gt)
    assert r.details["basis"] == "recall_only"
    assert r.details["precision"] is None
    assert r.passed  # full recall; precision intentionally not asserted on prose


# --- numerical (type 05) ----------------------------------------------------

def test_numerical_matches_count_among_other_numbers():
    r = _j("numerical").score("Galantamine causes 184 side effects across studies.", "184")
    assert r.passed and r.details["extracted"] == [184]


def test_numerical_handles_thousands_separator_and_wrong_value():
    assert _j("numerical").score("about 1,184 effects", "1184").passed
    assert not _j("numerical").score("around 200 effects", "184").passed


# --- binary (type 08, empty ground truth = unanswerable) --------------------

def test_binary_refusal_passes_on_empty_ground_truth():
    r = _j("binary").score("Testolactone does not treat any diseases.", [])
    assert r.passed and r.details["refusal_detected"]


def test_binary_hallucinated_answer_fails():
    r = _j("binary").score("Testolactone treats breast cancer and prostate cancer.", [])
    assert not r.passed


def test_binary_detects_contraction_refusal():
    # FINDINGS caveat #3: "I don't have …" must register as a refusal. The earlier regex
    # had `doesn't` but not the `don't` contraction, so this scored as a hallucination.
    r = _j("binary").score("I don't have specific context about Testolactone's uses.", [])
    assert r.passed and r.details["refusal_detected"]


def test_binary_detects_refusal_with_typographic_apostrophe():
    # Models emit a curly apostrophe (U+2019); the cue must match regardless of typography.
    r = _j("binary").score("I don’t have information on that compound.", [])
    assert r.passed and r.details["refusal_detected"]


# --- boolean (type 09) ------------------------------------------------------

def test_boolean_affirmative_matches_true():
    assert _j("boolean").score("Yes, there is a path.", "true").passed


def test_boolean_negative_matches_false():
    assert _j("boolean").score("No, no such path exists.", "false").passed


def test_boolean_polarity_mismatch_fails():
    assert not _j("boolean").score("Yes, definitely.", "false").passed


def test_boolean_ambiguous_fails_rather_than_guesses():
    r = _j("boolean").score("It is unclear.", "true")
    assert not r.passed and r.details["ambiguous"]


# --- semantic judge: prompt provenance (hermetic via injected LLM) -----------

class _FakeJudgeLLM:
    """Duck-typed Generator returning a canned EQUIVALENT verdict — no key, no network."""
    def generate(self, prompt, *, system=None, tools=None):
        from eval.generate.base import GenerationResult
        return GenerationResult(text="EQUIVALENT\nsame entity", model="fake-judge",
                                provider="fake", input_tokens=5, output_tokens=3, latency_ms=1.0)


def test_semantic_judge_stamps_prompt_sha_when_llm_called():
    from eval.judge.semantic import SEMANTIC_PROMPT, SemanticJudge
    r = SemanticJudge(llm=_FakeJudgeLLM()).score("Warfarin", "Coumadin", question="generic name?")
    assert r.passed  # EQUIVALENT
    assert r.details["judge_system_prompt_sha256"] == SEMANTIC_PROMPT["sha256"]


def test_semantic_judge_stamps_prompt_sha_on_empty_candidate_shortcut():
    # the empty-answer short-circuit makes no LLM call but still records the judge instrument
    from eval.judge.semantic import SEMANTIC_PROMPT, SemanticJudge
    r = SemanticJudge(llm=_FakeJudgeLLM()).score("", "Coumadin")
    assert r.details["llm_called"] is False
    assert r.details["judge_system_prompt_sha256"] == SEMANTIC_PROMPT["sha256"]
