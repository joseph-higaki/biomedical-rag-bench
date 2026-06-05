"""Tests for eval/produce/validate.py — the produced-eval-set quality gate.

Hermetic: no GraphDB, no network, no `produce` extra. `validate_records` is a pure
function over in-memory record dicts, so these tests build records by hand and assert
which problems it flags. This is exactly the "silent bug" surface the suite targets —
a malformed questions.jsonl (an unfilled placeholder, a scalar where a set belongs, a
short count) still looks like a plausible file; nothing at runtime would catch it, so
the gate itself must be tested.
"""
from __future__ import annotations

from eval.produce.validate import validate_records


def rec(**over) -> dict:
    """A valid set_match record; override fields to construct specific faults."""
    base = dict(
        question_id="02_1hop_factoid__expr__00",
        type_id="02_1hop_factoid",
        template_id="expr",
        question="Which genes are expressed in nasal cavity?",
        scoring="set_match",
        answer_var="geneLabel",
        ground_truth=["CDH1", "TP53"],
        seeds=[{"bind_var": "anatomy", "label": "nasal cavity", "uri": "uberon:0001707"}],
        sampling_seed="seed:expr",
    )
    base.update(over)
    return base


# Meta as load_template_meta() would return it, but hand-built (no YAML, no I/O).
META = {
    "expr": {"count": 1, "scoring": "set_match", "min_answer": 2, "max_answer": 25},
    "neg": {"count": 2, "scoring": "binary", "min_answer": None, "max_answer": None},
    "path": {"count": 4, "scoring": "boolean", "min_answer": None, "max_answer": None},
}


def has(problems, *substrings) -> bool:
    """True if some problem mentions all the given substrings."""
    return any(all(s in p for s in substrings) for p in problems)


# --- the happy path -------------------------------------------------------

def test_clean_set_match_record_has_no_problems():
    assert validate_records([rec()], META) == []


def test_clean_mixed_set_passes():
    records = [
        rec(),
        rec(question_id="08_negative_unanswerable__neg__00", type_id="08_negative_unanswerable",
            template_id="neg", scoring="binary", answer_var="diseaseLabel", ground_truth=[],
            question="Which diseases does Digoxin treat?"),
        rec(question_id="08_negative_unanswerable__neg__01", type_id="08_negative_unanswerable",
            template_id="neg", scoring="binary", answer_var="diseaseLabel", ground_truth=[],
            question="Which diseases does Apixaban treat?"),
    ]
    assert validate_records(records, META) == []


# --- per-record structural faults -----------------------------------------

def test_missing_required_field_flagged():
    r = rec()
    del r["sampling_seed"]
    assert has(validate_records([r], META), "missing fields", "sampling_seed")


def test_unfilled_placeholder_flagged():
    r = rec(question="Which genes are expressed in {anatomy}?")
    assert has(validate_records([r], META), "unfilled placeholder")


def test_scalar_scoring_with_list_ground_truth_flagged():
    # numerical answer must be a scalar string, not a list.
    r = rec(scoring="numerical", answer_var="n", ground_truth=["58"])
    assert has(validate_records([r], META), "should be a non-empty scalar")


def test_set_scoring_with_scalar_ground_truth_flagged():
    r = rec(ground_truth="CDH1")
    assert has(validate_records([r], META), "should be a list")


# --- type-specific contracts ----------------------------------------------

def test_binary_negative_must_be_empty_list():
    r = rec(question_id="08__neg__00", template_id="neg", scoring="binary",
            answer_var="diseaseLabel", ground_truth=["fatigue"],
            question="Which diseases does Caffeine treat?")
    assert has(validate_records([r], META), "binary", "should be []")


def test_boolean_must_be_true_or_false():
    r = rec(question_id="09__path__00", template_id="path", scoring="boolean",
            answer_var="boolean", ground_truth="yes",
            question="Is there a path from A to B?")
    assert has(validate_records([r], META), "boolean ground_truth should be")


def test_boolean_label_imbalance_flagged():
    # 4 trues, 0 falses for a boolean template — no signal.
    records = [
        rec(question_id=f"09__path__0{i}", template_id="path", scoring="boolean",
            answer_var="boolean", ground_truth="true", question=f"Is there a path {i}?")
        for i in range(4)
    ]
    assert has(validate_records(records, META), "unbalanced")


# --- answer-size bounds ----------------------------------------------------

def test_set_answer_below_min_flagged():
    r = rec(ground_truth=["CDH1"])  # 1 < min_answer 2
    assert has(validate_records([r], META), "below min_answer")


def test_set_answer_above_max_flagged():
    r = rec(ground_truth=[f"G{i}" for i in range(30)])  # 30 > max_answer 25
    assert has(validate_records([r], META), "above max_answer")


# --- set-level faults ------------------------------------------------------

def test_duplicate_ids_flagged():
    records = [rec(), rec()]  # same question_id twice
    assert has(validate_records(records, META), "duplicate question_ids")


def test_count_mismatch_flagged():
    # expr declares count 1, but two records carry distinct ids -> produced 2.
    records = [rec(), rec(question_id="02_1hop_factoid__expr__01", ground_truth=["A", "B"])]
    assert has(validate_records(records, META), "expr", "produced 2", "count 1")
