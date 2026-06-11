"""retrievers/sparqlgen.py — text-to-SPARQL graph retriever (build step 5+).

Mechanism 1 of the two honest graph-RAG designs (see graph.py for mechanism 2 and the
README/journal for the pair). An LLM, given the Hetionet schema vocabulary and the
question, writes ONE SPARQL `SELECT` query; the retriever executes it against GraphDB and
serializes the result rows as context. This is what production KG-RAG actually does, and
it is the mechanism the all-zero deep-structural question types (04/05/06/07/09) keep
arguing for — a single 2-hop intersection or aggregation is one query here but is not in
the bounded neighborhood `graph_neighborhood` retrieves.

The deliberate contrast with `graph_neighborhood`:

  - graph_neighborhood: deterministic entity-linking + a fixed k-hop neighborhood, NO LLM.
    Isolates the *representation* (labeled triples vs. prose) under test.
  - graph_sparqlgen (this): the LLM does BOTH the linking and the traversal planning by
    writing SPARQL. Isolates the realistic text-to-SPARQL *skill*. The LLM here is part of
    the retrieval mechanism — distinct from, and logged separately from, the fixed
    generator under test (its own token cost goes in traversal_info, never confounded with
    the generator's billed tokens).

Honesty: the retriever sees only the `query` string (the Retriever protocol). It never
touches a question's `seeds` or ground-truth SPARQL — those are for scoring. The LLM
anchors entities by `rdfs:label "Name"` lifted verbatim from the question text; it is told
never to invent URIs. So this is fully self-contained text-to-SPARQL, not URI injection.

Reasoning stays OUT (hard constraint, Project 1): the prompt is schema-vocabulary only —
node types, directed edge signatures, attributes, prefixes — no OWL/inference. The graph
is queried with `reasoning=empty`, same as every other condition.

A malformed query (GraphDB rejects it, 4xx) or a non-SELECT is a legitimate retrieval
*miss*: empty context, `sparql_valid=false` — honest measurement of text-to-SPARQL failing,
not an errored/unscored row. Transient failures (5xx, timeout, connection) propagate to the
harness's per-question isolation, exactly as graph.py's `_select` does.

Telemetry: every result logs the generated SPARQL, the writer model, its own LLM token
cost, and row counts into `traversal_info`. Additive keys only (the contract).
"""
from __future__ import annotations

import os
import re

from retrievers.base import RetrievalResult, build_result, stopwatch

DEFAULT_ENDPOINT = os.environ.get(
    "GRAPHDB_ENDPOINT", "http://localhost:7200/repositories/hetionet"
)
# The LLM that writes the SPARQL — part of the retrieval mechanism, logged with every
# result. Defaults to the cheap model for cost parity with the Haiku generator; override
# via env. Mixing writer/generator models is a factor to record, not to hide.
DEFAULT_WRITER_MODEL = os.environ.get("SPARQLGEN_MODEL", "claude-haiku-4-5")
# Pinned to 0 by default, same reason as the generator: a hot writer samples a *different
# SPARQL query* each run → a different result set → a different context → a non-reproducible
# retrieval. Reproducibility here must be set independently of the generator's temperature
# because the writer is a separate LLM call inside the mechanism (see module docstring).
DEFAULT_WRITER_TEMPERATURE = float(os.environ.get("SPARQLGEN_TEMPERATURE", "0.0"))

# The schema-vocabulary prompt — the entire knowledge the LLM gets about the graph. Node
# types and *directed* edge signatures are the load-bearing part: `expresses` runs
# Anatomy->Gene, so the LLM must write the triple in that direction. No URIs, no reasoning.
SCHEMA_PROMPT = """\
You translate a biomedical question into exactly ONE SPARQL SELECT query over the \
Hetionet knowledge graph. Output ONLY the query inside a ```sparql code fence — no prose, \
no explanation.

Always include these prefixes:
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

Anchor every named entity by its label, copied EXACTLY as written in the question:
  ?gene rdfs:label "HTR3B" .
Never invent or guess a URI.

Node types (objects of `a hetio:<Type>`): Gene, Compound, Disease, Anatomy, Pathway,
BiologicalProcess, MolecularFunction, CellularComponent, SideEffect, Symptom,
PharmacologicClass.

Directed edges, written as `?subject hetio:<edge> ?object` (subject -> object):
  Anatomy   expresses | upregulates | downregulates   Gene
  Disease   associates | upregulates | downregulates  Gene
  Disease   localizes   Anatomy
  Disease   presents    Symptom
  Disease   resembles   Disease
  Compound  treats | palliates   Disease
  Compound  binds | upregulates | downregulates   Gene
  Compound  causes      SideEffect
  Compound  resembles   Compound
  Gene      participates   Pathway | BiologicalProcess | MolecularFunction | CellularComponent
  Gene      regulates | covaries | interacts   Gene
  PharmacologicClass  includes   Compound

Literal node attributes: hetio:chromosome (on Gene), hetio:description, hetio:inchikey
(on Compound), hetio:url.

Rules:
- Use SELECT DISTINCT. Always also bind and SELECT the rdfs:label of each answer entity
  (e.g. `?disease rdfs:label ?diseaseLabel`), so results are human-readable.
- For a "how many" / count question, use (COUNT(DISTINCT ?x) AS ?n).
- `participates` is polymorphic — when the question asks for pathways, constrain the
  object with `?p a hetio:Pathway` (likewise BiologicalProcess, etc.).
- If the question cannot be expressed against this schema, output an empty fence."""

# Accept only a read query. The LLM is instructed to emit SELECT; this rejects anything
# else (INSERT/DELETE/DROP/LOAD or junk) before it reaches GraphDB — defense in depth on
# top of querying the read-only /repositories endpoint.
_SELECT_RE = re.compile(r"^\s*(?:PREFIX\b[^\n]*\n\s*)*(?:SELECT|ASK)\b", re.IGNORECASE)
_FENCE_RE = re.compile(r"```(?:sparql)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)
# A line that is ONLY a fence marker (```sparql, ```, with optional whitespace). Used to
# salvage an UNTERMINATED fence: local instruct models routinely open a ```sparql fence and
# forget the closing ```, which _FENCE_RE (requires a pair) can't match — leaving the marker
# on the query so it fails the SELECT gate. Stripping these lines recovers the query.
_FENCE_LINE_RE = re.compile(r"^\s*```(?:sparql)?\s*$", re.IGNORECASE)


class SparqlGenRetriever:
    """LLM writes SPARQL from a schema-vocab prompt; execute it on GraphDB. ~one file.

    The LLM client is injectable (`llm=`) for hermetic tests; in normal use an
    AnthropicGenerator is built lazily on first `retrieve`, so importing this module needs
    neither the `anthropic`/`generate` deps nor an API key (the same lazy pattern as
    graph.py's httpx and vector.py's chromadb). Constructing the retriever only sets
    attributes — the registry no-drift test relies on that.
    """

    name = "graph_sparqlgen"

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        writer_model: str | None = None,
        writer_temperature: float | None = None,
        max_rows: int = 200,
        llm=None,
    ) -> None:
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.writer_model = writer_model or DEFAULT_WRITER_MODEL
        # None ⇒ the env-backed default (0.0), so the zero-arg registry construction stays
        # reproducible; an explicit value (incl. a deliberate >0) is honored and logged.
        self.writer_temperature = (
            DEFAULT_WRITER_TEMPERATURE if writer_temperature is None else writer_temperature
        )
        self.max_rows = max_rows
        self._llm = llm  # duck-typed Generator: .generate(prompt, system=) -> .text/.*_tokens/.model

    # --- the LLM writer (part of the mechanism) ----------------------------
    def _ensure_llm(self):
        if self._llm is None:
            # Lazy so module import stays dependency-free; the generator adapter is neutral
            # infra (not the ground-truth tooling graph.py deliberately avoids importing).
            # Through the shared factory so writer_model may name a provider
            # (`ollama:qwen2.5-coder`); a bare model stays Anthropic (the historical default).
            from eval.generate.registry import from_spec

            self._llm = from_spec(
                self.writer_model, default_provider="anthropic", temperature=self.writer_temperature
            )
        return self._llm

    @staticmethod
    def _extract_query(text: str) -> str:
        """Pull the SPARQL out of the LLM reply.

        Prefer a complete ```sparql ... ``` block (picks the query out of any surrounding
        prose). If there's no closing fence — common with smaller local instruct models that
        open a fence and never close it — fall back to stripping any line that is only a
        fence marker, which recovers the query rather than leaving the marker on it (where it
        would fail the SELECT/ASK gate as a non-query). With no fences at all this is a no-op,
        so a bare query still passes through unchanged."""
        m = _FENCE_RE.search(text)
        if m:
            return m.group(1).strip()
        lines = [ln for ln in text.splitlines() if not _FENCE_LINE_RE.match(ln)]
        return "\n".join(lines).strip()

    def _bounded(self, query: str) -> str:
        """Append a LIMIT to a non-aggregate query that lacks one, so a hub entity can't
        return an unbounded result set. COUNT queries are already single-row.

        When we add the LIMIT we also add an ORDER BY over the projected variables if the
        query has none: a bare LIMIT without ORDER BY truncates to an ARBITRARY subset, so a
        query returning more than max_rows rows would be non-reproducible (the same class of
        bug as graph.py's hop fetch). If the projection can't be parsed (e.g. SELECT *), we
        leave it — accepting the residual risk rather than emitting an invalid ORDER BY."""
        low = query.lower()
        if "limit" in low or "count(" in low:
            return query
        ordered = query.rstrip()
        if "order by" not in low:
            sel = re.match(r"\s*SELECT\s+(?:DISTINCT\s+)?(.*?)\s+WHERE",
                           query, re.IGNORECASE | re.DOTALL)
            proj = re.findall(r"\?(\w+)", sel.group(1)) if sel else []
            if proj:
                ordered += "\nORDER BY " + " ".join(f"?{v}" for v in proj)
        return f"{ordered}\nLIMIT {self.max_rows}"

    # --- GraphDB access ----------------------------------------------------
    # Own minimal SELECT client (httpx lazy), same as graph.py: the retriever is the
    # system under test and must not depend on eval's ground-truth query seam. Returns
    # (rows, error): a 4xx is a malformed-query miss (error set, rows empty); other HTTP
    # failures (5xx/timeout/connection) raise, for the harness to isolate as a transient.
    def _select(self, query: str) -> tuple[list[dict], str | None]:
        import httpx

        try:
            resp = httpx.post(
                self.endpoint,
                data={"query": query},
                headers={"Accept": "application/sparql-results+json"},
                timeout=120.0,
            )
        except httpx.RequestError:
            raise  # connection/timeout — transient, let the harness isolate it
        if 400 <= resp.status_code < 500:
            # GraphDB rejected the query (bad SPARQL). Honest retrieval miss, not an error row.
            return [], f"HTTP {resp.status_code}: {resp.text[:200]}"
        resp.raise_for_status()  # 5xx -> raise (transient)
        return resp.json()["results"]["bindings"], None

    @staticmethod
    def _serialize(rows: list[dict]) -> tuple[str, list[str]]:
        """Render binding rows as readable lines and collect IRI values as provenance.

        Generic over whatever shape the LLM's SELECT returns: each row becomes
        `var=value | var=value`, IRI-valued bindings also feed `sources`.
        """
        lines: list[str] = []
        sources: list[str] = []
        for r in rows:
            parts = []
            for var, cell in r.items():
                val = cell.get("value", "")
                parts.append(f"{var}={val}")
                if cell.get("type") == "uri":
                    sources.append(val)
            lines.append(" | ".join(parts))
        return "\n".join(lines), sorted(set(sources))

    # --- the contract ------------------------------------------------------
    def retrieve(self, query: str) -> RetrievalResult:
        with stopwatch() as sw:
            llm = self._ensure_llm()
            gen = llm.generate(query, system=SCHEMA_PROMPT)
            sparql = self._extract_query(gen.text)

            info: dict = {
                "mechanism": "sparqlgen",
                "writer_model": getattr(gen, "model", self.writer_model),
                # Sampling temperature the writer LLM used (None = provider default / unpinned),
                # logged beside its model — the same temperature-beside-model rule the generator
                # and judge follow. This is the writer's query-generation reproducibility setting.
                "writer_temperature": getattr(gen, "temperature", None),
                # The retriever's OWN LLM cost — kept separate from the generator's billed
                # tokens so the two are never confounded (see module docstring).
                "writer_input_tokens": getattr(gen, "input_tokens", None),
                "writer_output_tokens": getattr(gen, "output_tokens", None),
                "endpoint": self.endpoint,
            }

            if not sparql or not _SELECT_RE.match(sparql):
                # No query / not a read query (empty fence, refusal, or unsafe verb): miss.
                return build_result(
                    context="", sources=[], latency_ms=sw.ms,
                    traversal_info={**info, "sparql": sparql, "sparql_valid": False,
                                    "num_rows": 0},
                )

            bounded = self._bounded(sparql)
            rows, err = self._select(bounded)
            context, sources = self._serialize(rows)

        return build_result(
            context=context,
            sources=sources,
            latency_ms=sw.ms,
            traversal_info={
                **info,
                "sparql": bounded,
                "sparql_valid": err is None,
                "num_rows": len(rows),
                **({"sparql_error": err} if err else {}),
            },
        )
