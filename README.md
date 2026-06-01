# biomedical-rag-bench

A falsifiable, evolving evaluation harness for retrieval-augmented generation over biomedical knowledge. Compares retriever strategies — vector similarity, RDF graph traversal, OWL reasoning, labeled property graphs — under a shared evaluation contract so results are directly comparable across approaches.

The benchmark grows by adding retriever conditions; the eval harness, question set, generator interface, and telemetry schema are shared across all conditions and evolve under additive-only constraints.

## Status

Work in progress. Releases ship per project; the repo evolves on `main`.

| Project | Tag | Status |
|---|---|---|
| Project 1 — Vector RAG vs RDF GraphRAG | `v1.0.0` | In development |
| Project 2 — OWL reasoning over RDF | `v2.0.0` | Planned |
| Project 3 — RDF vs LPG (Neo4j) | `v3.0.0` | Planned |

## Project 1 — Vector RAG vs RDF GraphRAG

### Hypothesis

Pure GraphRAG over RDF outperforms vector-only RAG on multi-hop, entity-dense queries, but loses on single-fact lookup and fuzzy semantic queries. Crossover is governed by query hop-count and entity density. This is the claim under test, not the assumed conclusion.

### Sub-hypotheses

Each is measurable and reported in the results table per release:

- **H1 — Token efficiency.** Graph uses 5–20x fewer context tokens on 2+ hop questions; gap narrows or reverses on single-hop factoids.
- **H2 — Relational hallucination.** Graph materially reduces hallucinations on relational claims; little effect on attributive hallucinations.
- **H3 — Multi-hop recall.** Graph recall stays flat as hop-count grows; vector recall decays roughly geometrically.
- **H4 — Fuzzy/semantic recall.** Vector wins clearly; graph may be unable to answer at all.
- **H5 — Compute/latency.** Vector: cheap query, cheap indexing. Graph: cheap query, expensive indexing (LLM-driven extraction is the cost center).
- **H6 — Citability.** Graph gives claim-level provenance; vector gives only chunk-level.
- **H7 — Retrieval necessity.** On 0-hop attribute and 1-hop factoid questions about well-known entities, closed-book performance approaches or matches retrieval-augmented performance, indicating retrieval is unnecessary on those classes. On multi-hop, aggregative, set-operation, and negative/unanswerable questions, closed-book performance is materially worse than either retriever, indicating retrieval is necessary. The benchmark's primary finding is the crossover between question classes, not the average advantage across all questions.

### Early observations

Recorded as they emerge during build; not yet backed by a full eval run.

**Vector retrieval retrieves by language, not by biological role.** The first
similarity query run against the smoke corpus (`"loss of E-cadherin promotes
tumor metastasis"`) returned CDH1 — the E-cadherin gene — in third place, not
first. The top-ranked result was TRIM27 (liver cancer immunosuppression), whose
abstract happened to use language semantically closer to "metastasis" than the
CDH1 abstract did. The CDH1 abstract PubMed returned was about inherited breast
cancer risk (CDH1 listed alongside BRCA1/BRCA2), not about E-cadherin's role in
cell detachment — so the embedder correctly represented the *text* it received,
but the text didn't reflect the biological mechanism behind the query.

This is an early, concrete instance of H2 and H4: vector recall is bounded by
what language appeared in the seeding abstracts, not by the entity's role in the
knowledge graph. The graph retriever has an explicit CDH1→Disease edge;
the vector retriever has only the text PubMed returned for the search term
"CDH1". Full writeup in `ingest/vector/README.md` (Smoke test observation).

### Findings

Published per release in `.github/release-notes/<version>.md` and on the GitHub Releases page.

## Architecture

### One interface, many retrievers, one harness

Every retriever — vector, graph, future Neo4j, future OWL-reasoning — implements the same protocol and returns the same shape. The eval harness is retriever-agnostic and calls each in turn against the shared question set.

```python
# retrievers/base.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class RetrievalResult:
    context: str              # Text handed to the generator
    context_tokens: int
    latency_ms: float
    sources: list[str]        # URIs (graph) or chunk IDs (vector)
    traversal_info: dict      # Retriever-specific. Additive-only across versions.

class Retriever(Protocol):
    name: str
    def retrieve(self, query: str) -> RetrievalResult: ...
```

Two reasons this pattern matters:

**Comparability.** Every retriever produces the same fields. Tokens, latency, sources, and the retrieved context are measured identically across conditions. Differences between retrievers reflect representation differences, not measurement differences.

**Extensibility.** Adding a new retriever in a future project is one file in `retrievers/` plus a registration in the eval harness. No core code changes. The harness doesn't know or care which retriever is which.

The `traversal_info` field is free-form by design — vector retrievers log top-k scores, graph retrievers log the SPARQL query and hop count, future Neo4j retrievers will log the Cypher query. New fields are added across versions; existing fields are never renamed or removed. This rule keeps prior results re-runnable against newer code.

A third condition registers alongside vector and graph: a `NullRetriever` (name `closed_book`) that returns empty context — `context=""`, `context_tokens=0`, `sources=[]`, `traversal_info={"retriever": "none"}`, ~20 lines in `retrievers/null.py`. It is not a retrieval mechanism under test; it is a **baseline** that measures how much retrieval contributes to answer quality, independent of which retriever is used. Without a closed-book baseline the benchmark cannot distinguish "graph beats vector" from "both retrievers add nothing beyond what the generator LLM already knows from training data" — a critical distinction for biomedical knowledge well-represented in frontier-model training data (most of Hetionet's famous entities). The baseline lets findings make the sharper claim: on question class X retrieval is necessary and graph outperforms vector; on question class Y retrieval is unnecessary because the LLM already knows.

### Hetionet plus PubMed — shared underlying knowledge

The vector and graph retrievers operate over the same biomedical knowledge in different representations:

- **Graph side.** [Hetionet](https://github.com/hetio/hetionet) v1.0 (CC0, 47k nodes / 2.25M edges, 11 node types, 24 edge types). Converted to RDF Turtle using stable biomedical URIs (DrugBank IDs as `db:`, Disease Ontology as `do:`, Entrez Gene as `ncbigene:`, Uberon as `uberon:`). Edge properties (source database, license) attach via RDF-star.
- **Vector side.** PubMed abstracts fetched via NCBI E-utilities for entities present in Hetionet. Embedded with `sentence-transformers/all-MiniLM-L6-v2` into a Chroma collection.

The comparison is representation, not content. Both sides see the same entities.

### Ingestion is streaming, not in-memory

**Decision (provisional, May 2026).** The Hetionet JSON → Turtle transform streams both sides: the source is parsed incrementally with `ijson` and Turtle is written statement-by-statement. It never materializes the full document via `json.load`, nor builds the full graph in an in-memory `rdflib.Graph`.

**Why.** Decompressed, the Hetionet graph is ~712 MB of JSON (47k nodes, 2.25M edges), and the RDF-star expansion multiplies the statement count. On a 7 GB-RAM dev box, the naive `json.load` + in-memory `Graph` build does not fit. Streaming keeps memory bounded and roughly constant regardless of dataset size. The cost is hand-written Turtle serialization instead of a library serializer; correctness is guarded by round-tripping the smoke slice through `pyoxigraph` (Rust-backed Oxigraph, which parses Turtle-star and runs SPARQL-star offline) and asserting a sample query returns the expected answer. `rdflib` 7.6 has no RDF-star support, so it cannot parse the edge annotations — see `ingest/rdf/hetionet-data-notes.md`.

**Revisit if** the transform proves too slow or the hand-written serializer accumulates escaping bugs that a library serializer would have handled. The swap point is contained to `ingest/rdf/hetionet_to_rdf.py`; nothing downstream cares how the Turtle was produced.

### Stack

- **Triplestore.** Ontotext GraphDB Free v11.3.2, via the official Docker image. As of GraphDB 11.0 the Free edition requires a (still free) license file: the container reads without it but writes fail with `No license was set`, so a license is mandatory for ingestion — request it from Ontotext and mount it at `secrets/graphdb.license` (see `ingest/README.md`). Reasoning ruleset is `empty` in baseline (reasoning becomes a Project 2 variable).
- **Vector store.** Chroma, embedded mode, zero-config.
- **Embeddings.** `sentence-transformers/all-MiniLM-L6-v2`. Local, free, reproducible.
- **Generation LLM.** Set via `GENERATOR_MODEL` env var. Baseline result runs use a frontier hosted model; iteration runs use Haiku or a small local Llama. The benchmark is generator-agnostic by design — results tables identify the generator used.
- **Eval.** Type-aware scoring: deterministic scoring for nine of the ten question types (string/set/numerical/boolean comparison against graph-derived ground truth); LLM-as-judge only for fuzzy/semantic questions, calibrated against human grades via Cohen's kappa. Full strategy in `eval/README.md`.
- **Orchestration.** Plain Python. No LangChain, no LlamaIndex. Hand-rolled retrievers, ~100 lines each. Abstraction layers obscure what is being measured.

### File layout

```
biomedical-rag-bench/
├── CLAUDE.md                   # Directional context for Claude Code sessions
├── README.md                   # This file — canonical project documentation
├── LICENSE                     # MIT
├── docker-compose.yml          # Local GraphDB
├── Makefile                    # Top-level orchestration (ingest, test, etc.)
├── .github/
│   ├── workflows/
│   │   └── release.yml         # Tag push → GitHub Release automation
│   └── release-notes/
│       └── v1.0.0.md           # Per-release findings, written before tagging
├── .claude/                    # Claude Code workspace (gitignored skills excluded)
├── data/                       # Gitignored bulk: Hetionet JSON, PubMed cache
├── ingest/
│   ├── README.md               # Pipeline overview + Make targets; links into rdf/ and vector/
│   ├── rdf/                    # Graph-side ingestion (RDF; Projects 1–2)
│   │   ├── README.md           # GraphDB license, repository setup, full-graph load
│   │   ├── hetionet_to_rdf.py  # JSON → Turtle (uses RDF-star)
│   │   ├── hetionet-data-notes.md  # Source structure, URI mapping, triple-count note
│   │   └── graphdb-repo-config.ttl # Reproducible repo config (ruleset=empty)
│   └── vector/                 # Vector-side ingestion (planned; build order step 1)
│       ├── README.md           # PubMed rate limits, caching, embedding build
│       ├── pubmed_fetch.py     # NCBI E-utilities → abstracts cache
│       └── build_vectors.py    # Abstracts → Chroma collection
├── retrievers/
│   ├── base.py                 # Retriever protocol — the swap point
│   ├── vector.py               # Top-k similarity
│   ├── graph.py                # SPARQL templates + entity linking
│   └── null.py                 # Closed-book baseline (empty context)
├── eval/
│   ├── README.md               # Question taxonomy, scoring strategy, eval architecture
│   ├── questions.jsonl         # Frozen eval set; ground truth derived from graph traversal (template-generated)
│   ├── run_eval.py             # Runs all registered retrievers
│   └── analyze.ipynb           # Charts and findings
├── ontology/
│   ├── hetionet.ttl            # ABox (instance data)
│   └── hetionet-schema.ttl     # TBox (near-empty in Project 1)
└── deployment/
    └── ec2-userdata.sh         # EC2 bootstrap (post-Project 1 milestone)
```

## Release strategy

The repository evolves on `main`. Each project ships a SemVer tag promoted to a GitHub Release.

- **MAJOR bump** = breaks comparability of prior results (eval metric change, ground truth correction, question removed).
- **MINOR bump** = adds capability without breaking prior results (new retriever, new questions, new telemetry fields).
- **PATCH bump** = bug fix that corrects prior results.

Release notes live in `.github/release-notes/<version>.md`, versioned alongside the code. Pushing a tag matching `v*.*.*` triggers a GitHub Action that creates the GitHub Release from the corresponding notes file. Writeups and external links should always reference the tag URL, not `main` — only tagged releases are reproducible.

## Reproducing results

```bash
# Clone and check out a specific release
git clone https://github.com/joseph-higaki/biomedical-rag-bench
cd biomedical-rag-bench
git checkout v1.0.0

# Start GraphDB locally
docker compose up -d

# Run the ingestion pipeline (see ingest/README.md for details)
make ingest

# Load ontology/hetionet.ttl into GraphDB via the Workbench
# (one-time, ~2 minutes; instructions in ingest/README.md)

# Run the eval
uv run python eval/run_eval.py --generator <model-id>
```

Expected runtime end-to-end: ~2 hours on a modern laptop, dominated by PubMed fetch (rate-limited by NCBI) and embedding generation.

## Build order

Project 1 follows a strict build order — each step validates before the next begins. Tracked as a checklist; granular per-session progress lives in the session journal.

- [x] **1. Smoke test the pipeline end-to-end on a tiny slice.**
  - [x] Hetionet JSON → RDF-star Turtle via a streaming transform; 100-edge connected slice
  - [x] SPARQL and SPARQL-star return real answers (validated offline with pyoxigraph)
  - [x] Load the slice into GraphDB and confirm the same queries against the live triplestore (queries match Oxigraph; see `ingest/rdf/hetionet-data-notes.md` for the RDF-star count note)
  - [x] PubMed → 5 abstracts → Chroma → one similarity query returning a real answer
- [ ] **2. Author question templates.** One or more templates per question type in the ten-type taxonomy. Each template specifies the question shape, the ground-truth query, the question type, and the entity sampling strategy. Templates are authored, not LLM-generated. *Isolated smoke: run each template's ground-truth query against the smoke slice and confirm it returns the expected answer.*
  - [ ] **Template registry generator.** Generate the docs table in `eval/templates/README.md` from the YAML templates so it cannot drift from source. Build once enough templates exist to make drift a real risk (fits alongside the step 3 producer tooling). Single source of truth stays the YAML.
- [ ] **3. Build the eval producer.** Loads templates, samples entities programmatically (seeded), runs the ground-truth query for each instantiated question, writes `questions.jsonl` with ground truth. Targets ~58 questions across the ten types per the weighting in `eval/README.md`. *Isolated smoke: run the producer on one template against the smoke slice and confirm it emits valid instantiated questions with ground truth.*
- [ ] **4. Build the retriever interface and three retrievers.** vector, graph, and closed-book null retriever. All implement the `Retriever` protocol in `retrievers/base.py`. *Isolated smoke: exercise each retriever on one query against the smoke slice and confirm it returns a `RetrievalResult` with populated telemetry.*
- [ ] **5. Build the eval harness and judges.** Harness loads `questions.jsonl`, runs each retriever + generator against each question, records telemetry. Judges implement a pluggable `Judge` protocol — one per scoring type (set match, numerical, binary, LLM judge for fuzzy/semantic). *Isolated smoke: score known correct/incorrect answer pairs through each judge and confirm expected verdicts.*
  - [ ] **Architecture sequence diagram.** Once producer → harness → judge all exist, add a sequence diagram to the root README Architecture section synthesizing the end-to-end flow (templates → questions.jsonl → retriever+generator → judge → metrics). Keep it in sync as stages evolve.
- [ ] **6. Verify the full eval pipeline on the smoke slice.** With each piece already smoke-tested in isolation (steps 2–5), run the integrated pipeline end-to-end on a small subset of questions and confirm metrics are produced for all three retriever conditions.
- [ ] **7. Scale to full Hetionet and full question set (~58).**
- [ ] **8. Run eval, calibrate LLM judge, analyze, tag `v1.0.0`, create release, write up findings.**

Question content is determined by hand-authored templates instantiated over the Hetionet graph. Each template specifies (1) a question shape in natural language with entity placeholders, (2) the SPARQL traversal that produces ground truth, (3) the question type from the finite taxonomy, and (4) the entity sampling strategy. Entity sampling is programmatic and seeded for reproducibility; sampling logic is versioned in the repo. Ground truth is derived from graph traversal, never from LLM generation. LLM assistance is permitted only for (a) optional phrasing variation of mechanically-generated questions (stylistic only, content unchanged) and (b) judge scoring on fuzzy/semantic questions where exact-match scoring is inappropriate. All other question types use deterministic scoring.

Questions span a finite ten-type taxonomy defined by graph-theoretic complexity, not surface phrasing; see `eval/README.md` for the taxonomy, target distribution, and scoring strategy.

Question set is append-only across projects. New questions can be added; existing questions are not removed or modified, so prior results remain comparable.

## License

MIT. See `LICENSE`.

## Citation

If this benchmark informs your work, link to the specific release tag. Generic links to `main` will not be reproducible.
