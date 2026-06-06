# Retrievers

The swap point of the benchmark. Every retriever — vector, graph, the closed-book
baseline, future OWL/Neo4j conditions — implements one contract and returns one
shape, so the eval harness is retriever-agnostic and differences between conditions
reflect **representation** differences, not measurement differences.

This file is the authoritative source for retriever *design*: the contract, the
token-units rule, the per-retriever mechanisms, and the telemetry each contributes.
The root `README.md` owns the hypotheses and build order; `eval/README.md` owns the
eval/scoring design and the per-run experiment manifest.

> **Status (build step 4).** `closed_book` and `graph_neighborhood` built and
> smoke-validated. `vector` in progress. `graph_sparqlgen` deferred to step 5+.

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
| `vector` | `vector.py` | embed question → top-k Chroma chunks | 🚧 in progress |
| `graph_neighborhood` | [`graph.py`](graph.py) | entity-link → bounded k-hop subgraph | ✅ built |
| `graph_sparqlgen` | `sparqlgen.py` | LLM writes SPARQL from schema vocab | 🔜 step 5+ |

Two graph conditions, two research questions: `graph_neighborhood` isolates the
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

### `vector` — the control 🚧

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

### `graph_sparqlgen` — text-to-SPARQL 🔜 (step 5+)

The de-facto real-world graph-RAG method: an LLM writes SPARQL from the question plus a
**schema-vocabulary summary** (node types + predicates, derivable now from two
`SELECT DISTINCT` queries — **not** OWL reasoning, so the Project 1 "reasoning stays
empty" constraint holds), runs it, serializes results. Deferred because it needs an LLM
*inside* the retriever, and the generator/provider-adapter layer is build step 5 — it
reuses that infrastructure. Note: "graph hallucinates less" is a **hypothesis to
measure**, not an assumption — text-to-SPARQL relocates answer-hallucination into
query-hallucination (valid-but-wrong predicates/directions, or malformed SPARQL → empty
context). Likely graduates to its own `retrievers/sparqlgen/` folder + README if it
grows past one file (schema-summary builder + prompt + SPARQL validator).

## When a retriever gets its own folder/README

Document at the granularity of the **swap point** (this contract), not the
implementation. A retriever earns its own folder + README only when it stops being a
~one-file implementation and becomes a multi-file sub-package — the same trigger that
gave `eval/produce/` its folder. Until then, it's a section here, where the
side-by-side comparison that is this benchmark's whole point stays legible.
