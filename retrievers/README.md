# Retrievers

The swap point of the benchmark. Every retriever — vector, graph, the closed-book
baseline, future OWL/Neo4j conditions — implements one contract and returns one
shape, so the eval harness is retriever-agnostic and differences between conditions
reflect **representation** differences, not measurement differences.

This file is the authoritative source for retriever *design*: the contract, the
token-units rule, the per-retriever mechanisms, and the telemetry each contributes.
The root `README.md` owns the hypotheses and build order; `eval/README.md` owns the
eval/scoring design and the per-run experiment manifest.

> **Status (build step 5).** All five conditions built, smoke-validated, and registered in
> [`eval/run_eval.py`](../eval/run_eval.py): `closed_book`, `vector`, `graph_neighborhood_1hop`,
> `graph_neighborhood_2hop`, and `graph_sparqlgen` (the LLM-in-retriever text-to-SPARQL arm).

## The contract

Defined in [`base.py`](base.py) — that file is canonical; this is the summary.

```python
@dataclass
class RetrievalResult:
    context: str          # text handed to the generator
    context_tokens: int   # OFFLINE PROXY (see units rule) — not billed truth
    latency_ms: float     # wall-clock of the retrieval, measured identically
    sources: list[str]    # URIs (graph) or chunk ids (vector) — provenance
    traversal_info: dict  # per-retriever telemetry; additive keys only

class Retriever(Protocol):
    name: str
    def retrieve(self, query: str) -> RetrievalResult: ...
```

A **Protocol**, not a base class: retrievers match the shape structurally, they don't
inherit. Adding one is a single file here plus a registration in `eval/run_eval.py` —
no core code changes.

**Telemetry is additive only** (a hard constraint): new `RetrievalResult` fields are
optional-only, and `traversal_info` keys are never renamed or removed. This keeps
prior results re-runnable against newer code.

Three shared seams in `base.py` enforce *measured-identically* so the cross-retriever
numbers are comparable, not merely similar-looking:

- `count_tokens(text)` — the one proxy token counter (see below).
- `stopwatch()` — uniform `latency_ms` (perf_counter, milliseconds).
- `build_result(...)` — assembles the result, always counting tokens through the one
  seam and stamping the proxy tokenizer id into `traversal_info`. Every retriever
  should build through it (the `closed_book` constant is the deliberate exception).

## The token-units rule (read before doing any token math)

`context_tokens` is an **offline proxy** — `count_tokens` (canonical WordPunct,
`wordpunct-v1`) run on the context string, no LLM call. Its only honest job is a
same-tokenizer, no-API-key, *relative* dev sanity check ("is graph injecting 10× the
payload vector is?") and to populate telemetry before any generator exists.

It is **not** the billed truth. Exact token cost comes from the generator's own
`usage` metadata at generation time (step 5), in the generator's tokenizer. The proxy
and the generator tokenizer are **different currencies**: subtracting one from the
other (e.g. `billed_input − proxy_context`) is a units error and yields a meaningless
number. To keep that catchable, every result records `traversal_info["context_tokenizer"]`
so the analysis layer can assert a matching unit before arithmetic.

The proxy notably **undercounts** URI-dense graph context (opaque ids like `DOID_1612`
are one `\w+` token to the proxy but several to a real BPE tokenizer), so its error is
*correlated with the condition under test* — another reason it is dev-only. The one
legitimate token decomposition uses billed numbers only:
`input_tokens(retriever) − input_tokens(closed_book)`, same model, same question.

## Telemetry & provenance

The eval is a **factorial experiment**: each result is a cell in a grid of factors
(retriever × question type × generator model × judge × graph budget × …), and the EDA
can only test a hypothesis by a factor if every row records that factor's level. There
are two altitudes:

- **Per-retrieval** → `traversal_info` (this subsystem): mechanism, hops, fan caps,
  linked entities, the SPARQL, counts, `context_tokenizer`.
- **Per-run manifest** → the harness's job (build step 5): generator model, judge
  model, embedding model, git SHA, dataset version, seed, timestamp.

The full factor list, the manifest schema, and the tidy-table join are authoritative
in `eval/README.md`. Retrievers own only their per-retrieval slice.

## Roster

| `name` | File | Mechanism | Status |
|---|---|---|---|
| `closed_book` | [`null.py`](null.py) | empty context (baseline) | ✅ built |
| `vector` | [`vector.py`](vector.py) | embed question → top-k Chroma chunks | ✅ built |
| `graph_neighborhood_1hop` | [`graph.py`](graph.py) | entity-link → 1-hop subgraph | ✅ built |
| `graph_neighborhood_2hop` | [`graph.py`](graph.py) | entity-link → 2-hop subgraph | ✅ built |
| `graph_sparqlgen` | [`sparqlgen.py`](sparqlgen.py) | LLM writes SPARQL from schema vocab | ✅ built |

The hop budget is **embedded in the registered name** (`graph_neighborhood_<n>hop`) rather
than passed as a separate factor: the budget defines what the condition can answer, so it
is a condition in its own right, not a tuning parameter of one condition. Encoding it in
the name keeps each budget a single grouping key (no extra manifest factor) and
auto-namespaces its result files; the value is also in `traversal_info["hops"]`, the
source of truth. (Reserve name-encoding for the curated budgets you actually compare — if
you ever sweep many knobs, that knob graduates to a real factor.)

Two graph *mechanisms*, two research questions: `graph_neighborhood` isolates the
*representation* (no LLM, deterministic); `graph_sparqlgen` measures the realistic
*system* (text-to-SPARQL, as deployed in the wild). Both are valid; the architecture
carries both as separate registered conditions.

### `closed_book` — the baseline

Returns `context=""`. **Not a retrieval mechanism under test** — the baseline that
measures how much retrieval contributes at all, independent of which retriever. Without
it the benchmark can't tell "graph beats vector" from "both add nothing the generator
didn't already know" (a real risk for memorized biomedical entities — H7). It doubles
as the per-question *token* baseline: injecting no context, its billed `input_tokens`
is exactly the non-retrieval payload, the unit-safe subtrahend in the rule above. A
hand-built constant — deliberately bypasses `build_result` (nothing to tokenize, no
work to time).

### `vector` — the control ✅

Embeds the question with the **same** model `build_vectors.py` used
(`all-MiniLM-L6-v2` — the embedding model is a single visible swap point; query and
corpus must share it), queries the persistent Chroma collection by cosine similarity,
returns the top-k chunks as context. `sources` = chunk ids / PMIDs; `traversal_info`
logs top-k scores. The corpus is built by [vector ingestion](../ingest/vector/README.md);
it is intentionally the **control** — it strengthens across releases as registered
variants, never reaches "fully tuned". Sensitive to the *language* of retrieved text,
not the entity's role (see the ingestion README's CDH1/E-cadherin worked example).

### `graph_neighborhood` — link + traverse ✅

Parallels vector deliberately: where vector embeds-and-searches, this links-and-traverses.

1. **Entity linking (gazetteer).** Loads every node `rdfs:label` once (~47k, a few MB;
   the 11M triples stay in GraphDB), builds a `{label → URI}` dictionary, and greedy
   longest-matches the question's words against it. Links "CDH1" → its URI from the
   **question text alone** — no LLM. Honest: it never touches the question's `seeds` or
   ground-truth query (those are for scoring). Type-10 fuzzy questions name no entity,
   so linking finds nothing → graph retrieval is weak there *by design* (feeds H7).
2. **Bounded k-hop neighborhood.** A SPARQL traversal around the anchors, both edge
   directions, including literal attributes (so 0-hop `chromosome` answers survive),
   with **per-predicate and total fan caps**. The caps are the knob that defines what
   the condition can answer: too small and multi-hop answers aren't in context; too
   large and context is token-heavy noise. Defaults conservative (`hops=1`,
   `max_per_predicate=25`, `max_triples=200`); bumping to `hops=2` before the multi-hop
   eval is a calibration step (build order 6/7). Per-predicate capping matters: on CDH1
   the hundreds of `interacts` edges don't crowd out the few answer-bearing `associates`
   (disease) edges — each predicate gets its own slots.
3. **Serialization.** URIs resolved to labels, rendered as readable triples
   (`CDH1 associates breast cancer`) — token-frugal *and* legible to the generator,
   never raw IRIs. `sources` = the entity URIs in the *served* (post-cap) triples.

`traversal_info`: `mechanism`, `hops`, `max_per_predicate`, `max_triples`,
`linked_entities`, `num_linked`, `num_triples`, `sparql`, `endpoint`, `context_tokenizer`.

### `graph_sparqlgen` — text-to-SPARQL ✅

The de-facto real-world graph-RAG method: an LLM writes one SPARQL `SELECT` from the
question plus a **schema-vocabulary summary** (the `SCHEMA_PROMPT` constant — node types +
*directed* edge signatures + literal attributes, **not** OWL reasoning, so the Project 1
"reasoning stays empty" constraint holds), the retriever runs it and serializes the result
rows. Entities are anchored by `rdfs:label "Name"` lifted verbatim from the question — the
LLM is told never to invent a URI, so it stays honest (no `seeds`, no ground-truth query),
exactly like `graph_neighborhood`'s gazetteer.

The LLM is **part of the retrieval mechanism**, distinct from the fixed generator under
test: its writer model and *own* token cost are logged separately in `traversal_info`
(`writer_model`, `writer_input_tokens`, `writer_output_tokens`), never confounded with the
generator's billed tokens. The writer model defaults via `SPARQLGEN_MODEL` and is injectable
(`llm=`) for hermetic tests.

Failure is measured, not hidden: a non-SELECT reply or a GraphDB-rejected (4xx) query is an
honest retrieval **miss** — empty context, `sparql_valid=false` — while transient (5xx /
timeout / connection) failures propagate to the harness's per-question isolation, the same
split `graph.py` uses. A SELECT-only guard + auto-`LIMIT` bound the query before execution.

What the first full run showed (→ `eval/FINDINGS.md`): query *execution* cracks the
structural types neighborhood-dumping can't (aggregation **8/8**, the only arm ever to score
there), and **recall is excellent** — the complete answer set lands in context on the large
majority of content questions. The binary exact-set score understates it: the dominant
failure is **precision** (underconstrained queries returning supersets), not missing rows —
text-to-SPARQL relocates answer-hallucination into *query*-imprecision, as predicted.

## When a retriever gets its own folder/README

Document at the granularity of the **swap point** (this contract), not the
implementation. A retriever earns its own folder + README only when it stops being a
~one-file implementation and becomes a multi-file sub-package — the same trigger that
gave `eval/produce/` its folder. Until then, it's a section here, where the
side-by-side comparison that is this benchmark's whole point stays legible.
