"""Tests for eval/harness.py — the retrieve→generate→judge loop wiring (build step 5).

Hermetic: a fake retriever and a fake generator (canned outputs) drive the real
deterministic judges, so the loop's *wiring* is tested without GraphDB, Chroma, a model,
or an API key. The wiring is where a mix-up would be silent — passing the wrong field to
the judge, dropping the context block, mislabeling a factor — so it is pinned here; the
adapters themselves are tested in their own suites.
"""
from __future__ import annotations

from eval import harness
from eval.generate.base import GenerationResult
from eval.judge.deterministic import DETERMINISTIC_JUDGES
from retrievers.base import RetrievalResult


class FakeRetriever:
    name = "fake"

    def __init__(self, context="", sources=None, context_tokens=0, traversal_info=None):
        self._ctx, self._sources, self._ct = context, sources or [], context_tokens
        self._info = traversal_info or {}

    def retrieve(self, query):
        return RetrievalResult(
            context=self._ctx, context_tokens=self._ct, latency_ms=1.0,
            sources=self._sources, traversal_info=self._info,
        )


class FakeGenerator:
    provider, model = "fake", "fake-1"

    def __init__(self, text):
        self._text = text

    def generate(self, prompt, *, system=None, tools=None):
        return GenerationResult(
            text=self._text, model=self.model, provider=self.provider,
            input_tokens=12, output_tokens=3, latency_ms=2.0,
        )


def _q(**kw):
    base = {"question_id": "q1", "type_id": "01_0hop_attribute",
            "scoring": "string_match", "question": "On which chromosome is HTR3B?",
            "ground_truth": "11", "answer_var": "chromosome"}
    return {**base, **kw}


# --- build_prompt -----------------------------------------------------------

def test_build_prompt_omits_context_block_when_empty():
    system, user = harness.build_prompt("Q?", "")
    assert "Context:" not in user and user == "Question: Q?"
    assert system == harness.SYSTEM_PROMPT


def test_build_prompt_includes_context_block_when_present():
    system, user = harness.build_prompt("Q?", "CDH1 associates breast cancer")
    assert user.startswith("Context:\nCDH1 associates breast cancer")
    assert "Question: Q?" in user
    assert system == harness.SYSTEM_PROMPT  # identical system prompt either way


# --- select_deterministic ---------------------------------------------------

def test_select_excludes_semantic_and_round_robins_for_type_coverage():
    rows = [
        {"type_id": "t1", "scoring": "set_match"},
        {"type_id": "t1", "scoring": "set_match"},
        {"type_id": "t2", "scoring": "numerical"},
        {"type_id": "t3", "scoring": "semantic"},  # excluded — no LLM judge yet
    ]
    sel = harness.select_deterministic(rows, 8)
    assert all(q["scoring"] != "semantic" for q in sel)
    assert len(sel) == 3
    # one per type before a type repeats
    assert [q["type_id"] for q in sel][:2] == ["t1", "t2"]


def test_select_respects_limit():
    rows = [{"type_id": f"t{i}", "scoring": "numerical"} for i in range(5)]
    assert len(harness.select_deterministic(rows, 2)) == 2


def test_include_semantic_admits_type_ten():
    rows = [{"type_id": "01", "scoring": "string_match"},
            {"type_id": "10_fuzzy_semantic", "scoring": "semantic"}]
    assert len(harness.select_questions(rows, 8, include_semantic=True)) == 2
    assert len(harness.select_questions(rows, 8, include_semantic=False)) == 1


def test_types_filter_selects_named_types_and_overrides_semantic_skip():
    rows = [{"type_id": "01_0hop_attribute", "scoring": "string_match"},
            {"type_id": "03_2hop_traversal", "scoring": "set_match"},
            {"type_id": "10_fuzzy_semantic", "scoring": "semantic"}]
    # a named semantic type is selected without needing include_semantic
    sem = harness.select_questions(rows, 8, types=["10"])
    assert [q["type_id"] for q in sem] == ["10_fuzzy_semantic"]
    # prefix match selects the right subset, excludes the rest
    two = harness.select_questions(rows, 8, types=["01", "03"])
    assert {q["type_id"] for q in two} == {"01_0hop_attribute", "03_2hop_traversal"}


# --- run_question -----------------------------------------------------------

def test_run_question_passes_on_correct_answer_and_records_factors():
    row = harness.run_question(
        FakeRetriever(context="", context_tokens=0),
        FakeGenerator("It is on chromosome 11."),
        DETERMINISTIC_JUDGES,
        _q(),
    )
    assert row["judged"] and row["passed"]
    assert row["retriever"] == "fake"
    assert (row["generator_provider"], row["generator_model"]) == ("fake", "fake-1")
    assert (row["input_tokens"], row["output_tokens"]) == (12, 3)
    assert row["scoring"] == "string_match" and row["type_id"] == "01_0hop_attribute"


def test_run_question_persists_retriever_telemetry_for_analysis():
    # The analysis layer reads retriever telemetry (writer cost, hops, sparql_valid, …) off
    # the row, so it must survive verbatim — stored whole, not whitelisted.
    info = {"mechanism": "sparqlgen", "writer_input_tokens": 40, "sparql_valid": True}
    row = harness.run_question(
        FakeRetriever(context="ctx", traversal_info=info),
        FakeGenerator("chromosome 11"), DETERMINISTIC_JUDGES, _q(),
    )
    assert row["traversal_info"] == info


def test_error_row_carries_empty_telemetry_for_schema_consistency():
    row = harness.run_question(FakeRetriever(), RaisingGenerator(), DETERMINISTIC_JUDGES, _q())
    assert row["traversal_info"] == {} and row["cache_read_input_tokens"] is None


def test_run_question_fails_on_wrong_answer():
    row = harness.run_question(FakeRetriever(), FakeGenerator("chromosome 22"),
                               DETERMINISTIC_JUDGES, _q())
    assert row["judged"] and not row["passed"]


def test_run_question_unjudged_when_no_judge_for_scoring():
    # semantic has no deterministic judge — runs retrieve+generate, records judged: false.
    row = harness.run_question(FakeRetriever(), FakeGenerator("Warfarin"),
                               DETERMINISTIC_JUDGES, _q(scoring="semantic"))
    assert row["judged"] is False and row["passed"] is None
    assert row["predicted"] == "Warfarin"  # still ran the generator


class RaisingGenerator:
    """Simulates a transient generator API error (e.g. a 529 that survives retries)."""
    provider, model = "fake", "fake-1"

    def generate(self, prompt, *, system=None, tools=None):
        raise RuntimeError("overloaded_error: 529")


def test_run_question_isolates_a_generator_error_as_an_unscored_row():
    # A failed call must not be scored as a wrong answer: judged false, passed null, the
    # error captured, and the question's factors still recorded for provenance.
    row = harness.run_question(FakeRetriever(), RaisingGenerator(), DETERMINISTIC_JUDGES, _q())
    assert row["judged"] is False and row["passed"] is None
    assert "529" in row["error"] and row["predicted"] is None
    assert row["type_id"] == "01_0hop_attribute" and row["retriever"] == "fake"
    assert row["input_tokens"] == 0  # nothing billed


def test_iter_rows_continues_past_a_failing_question():
    # One bad call in the middle must not abort the run — all rows are produced, in order.
    qs = [_q(question_id="a"), _q(question_id="b"), _q(question_id="c")]

    class FlakyGen:
        provider, model = "fake", "fake-1"
        def __init__(self): self.n = 0
        def generate(self, prompt, *, system=None, tools=None):
            self.n += 1
            if self.n == 2:
                raise RuntimeError("overloaded_error: 529")
            return GenerationResult(text="It is on chromosome 11.", model=self.model,
                                    provider=self.provider, input_tokens=12, output_tokens=3,
                                    latency_ms=2.0)

    rows = list(harness.iter_rows(FakeRetriever(), FlakyGen(), DETERMINISTIC_JUDGES, qs))
    assert [r["question_id"] for r in rows] == ["a", "b", "c"]  # none dropped
    assert rows[0]["passed"] and rows[2]["passed"]              # good ones scored
    assert rows[1]["judged"] is False and "error" in rows[1]    # bad one isolated


def test_make_manifest_carries_run_constant_factors():
    m = harness.make_manifest(FakeRetriever(), FakeGenerator("x"), [_q(), _q()],
                              run_id="testrun", questions_path="eval/questions.jsonl")
    d = m.to_dict()
    assert d["retriever"] == "fake" and d["generator_model"] == "fake-1"
    assert d["num_questions"] == 2 and d["run_id"] == "testrun"
    assert len(d["system_prompt_sha256"]) == 16  # prompt version pinned
    assert "git_sha" not in d  # code-version factor deferred (see harness TODO)
