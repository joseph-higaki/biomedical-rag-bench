"""Tests for retrievers/sparqlgen.py — the text-to-SPARQL retriever (build step 5+).

Hermetic: a fake LLM (canned reply) writes the "SPARQL", and `_select` is stubbed, so the
retrieve() wiring — fence extraction, the SELECT-only guard, LIMIT bounding, row
serialization, writer-token telemetry, and the malformed-query miss — is pinned without
GraphDB, the `anthropic`/`httpx` deps, or an API key. The pure helpers are exercised
directly. The httpx 4xx-vs-raise branch inside `_select` is adapter-level detail covered by
the live smoke; here we pin how retrieve() *handles* a returned miss.
"""
from __future__ import annotations

from dataclasses import dataclass

from retrievers.base import Retriever
from retrievers.sparqlgen import SparqlGenRetriever


@dataclass
class FakeGen:
    text: str
    model: str = "fake-writer-1"
    input_tokens: int = 40
    output_tokens: int = 12


class FakeLLM:
    """Duck-typed Generator: records the call and returns a canned reply."""

    def __init__(self, reply: str):
        self._reply = reply
        self.calls: list[tuple[str, str | None]] = []

    def generate(self, prompt, *, system=None, tools=None):
        self.calls.append((prompt, system))
        return FakeGen(self._reply)


_FENCED = "Here you go:\n```sparql\nSELECT DISTINCT ?d ?dLabel WHERE {\n  ?c rdfs:label \"X\" .\n  ?c hetio:treats ?d . ?d rdfs:label ?dLabel .\n}\n```\n"


def _retriever(reply, **kw):
    return SparqlGenRetriever(llm=FakeLLM(reply), **kw)


# --- protocol + construction ------------------------------------------------

def test_matches_retriever_protocol_and_names_itself():
    r = SparqlGenRetriever()  # no key, no network — llm is lazy
    assert isinstance(r, Retriever)
    assert r.name == "graph_sparqlgen"


# --- pure helpers -----------------------------------------------------------

def test_extract_query_prefers_fenced_block():
    q = SparqlGenRetriever._extract_query(_FENCED)
    assert q.startswith("SELECT DISTINCT ?d") and "```" not in q


def test_extract_query_falls_back_to_raw_when_unfenced():
    assert SparqlGenRetriever._extract_query("  SELECT ?x WHERE {}  ") == "SELECT ?x WHERE {}"


def test_extract_query_strips_unterminated_fence():
    # Smaller local instruct models open a ```sparql fence and forget the closing ```; the
    # marker must not survive onto the query (it would fail the SELECT gate as a non-query).
    reply = "```sparql\nSELECT ?x WHERE {}"
    q = SparqlGenRetriever._extract_query(reply)
    assert q == "SELECT ?x WHERE {}" and "```" not in q


def test_bounded_appends_limit_only_when_absent():
    r = _retriever("", max_rows=50)
    assert r._bounded("SELECT ?x WHERE {}").endswith("LIMIT 50")
    # already-limited and aggregate queries are left untouched
    assert r._bounded("SELECT ?x WHERE {} LIMIT 5").count("LIMIT") == 1
    assert "LIMIT" not in r._bounded("SELECT (COUNT(DISTINCT ?x) AS ?n) WHERE {}")


def test_serialize_renders_rows_and_collects_iri_sources():
    rows = [
        {"d": {"type": "uri", "value": "http://ex/d1"}, "dLabel": {"type": "literal", "value": "Asthma"}},
        {"d": {"type": "uri", "value": "http://ex/d2"}, "dLabel": {"type": "literal", "value": "Gout"}},
    ]
    ctx, sources = SparqlGenRetriever._serialize(rows)
    assert ctx == "d=http://ex/d1 | dLabel=Asthma\nd=http://ex/d2 | dLabel=Gout"
    assert sources == ["http://ex/d1", "http://ex/d2"]  # sorted, deduped, literals excluded


# --- retrieve() wiring ------------------------------------------------------

def test_happy_path_extracts_executes_and_logs_writer_cost(monkeypatch):
    r = _retriever(_FENCED)
    monkeypatch.setattr(r, "_select", lambda q: ([{"dLabel": {"type": "literal", "value": "Asthma"}}], None))
    res = r.retrieve("What does X treat?")

    assert res.context == "dLabel=Asthma"
    ti = res.traversal_info
    assert ti["mechanism"] == "sparqlgen" and ti["sparql_valid"] is True and ti["num_rows"] == 1
    assert ti["sparql"].rstrip().endswith("LIMIT 200")  # bounded before execution
    # the writer LLM's own cost is logged, separate from the generator's billed tokens
    assert ti["writer_model"] == "fake-writer-1"
    assert ti["writer_input_tokens"] == 40 and ti["writer_output_tokens"] == 12
    assert "sparql_error" not in ti


def test_non_select_is_a_miss_and_never_hits_the_endpoint(monkeypatch):
    # An empty fence / refusal / unsafe verb must not be executed.
    called = False
    def boom(_q):
        nonlocal called
        called = True
        return ([], None)
    for reply in ["```sparql\n```", "DELETE WHERE { ?s ?p ?o }", "I cannot answer that."]:
        r = _retriever(reply)
        monkeypatch.setattr(r, "_select", boom)
        res = r.retrieve("Q?")
        assert res.context == "" and res.sources == []
        assert res.traversal_info["sparql_valid"] is False and res.traversal_info["num_rows"] == 0
    assert called is False


def test_malformed_query_is_a_miss_not_an_error(monkeypatch):
    # GraphDB rejected the query (4xx surfaced by _select as an error string): empty context,
    # sparql_valid False, the error recorded — but retrieve() does not raise.
    r = _retriever(_FENCED)
    monkeypatch.setattr(r, "_select", lambda q: ([], "HTTP 400: malformed query"))
    res = r.retrieve("Q?")
    assert res.context == ""
    assert res.traversal_info["sparql_valid"] is False
    assert res.traversal_info["sparql_error"].startswith("HTTP 400")


def test_passes_schema_as_system_and_question_as_prompt():
    llm = FakeLLM("```sparql\n```")
    r = SparqlGenRetriever(llm=llm)
    r.retrieve("Which genes are expressed in nasal cavity?")
    prompt, system = llm.calls[0]
    assert prompt == "Which genes are expressed in nasal cavity?"
    assert "expresses" in system and "Never invent or guess a URI" in system
