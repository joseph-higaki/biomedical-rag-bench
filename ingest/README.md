# Ingestion pipeline

Two ingestion paths, one per representation. Both start from the same Hetionet
source and the same biomedical entities; they differ only in the artifact they
produce. The split mirrors the project's core comparison — graph vs. vector — and
keeps each side's operational detail (and its growing documentation) self-contained.

| Side | Folder | Produces | Consumed by |
|---|---|---|---|
| Graph (RDF) | [`rdf/`](rdf/README.md) | `ontology/hetionet.ttl` → GraphDB | `retrievers/graph.py` |
| Vector | [`vector/`](vector/README.md) | `data/chroma/` (embedded PubMed abstracts) | `retrievers/vector.py` |

`rdf/` covers Projects 1–2 (RDF representation; Project 2 adds reasoning over the
same triples). A future `lpg/` will hold Project 3's Neo4j path. `vector/` evolves
across minor releases as the vector baseline strengthens (naive → hybrid → domain
embedder) — see [`vector/README.md`](vector/README.md).

## Pipeline

```
rdf/hetionet_to_rdf.py    Hetionet JSON          → ontology/hetionet.ttl
        ↓
   (manual, one-time)     ontology/hetionet.ttl  → GraphDB repository
        ↓
vector/pubmed_fetch.py    ontology/hetionet.ttl  → data/abstracts/
        ↓
vector/build_vectors.py   data/abstracts/        → data/chroma/
```

Each step is independently runnable. The graph and vector sides are independent
after the RDF Turtle exists — `pubmed_fetch.py` reads the entity set from the
Turtle file, not from a live GraphDB.

## Make targets

If you haven't used Make before: `make <target>` runs the recipe defined in the
`Makefile` at the repo root. Make is a thin orchestration layer — each target is a
small shell script. Two reasons we use it:

1. **Dependencies are explicit.** `make ingest` depends on `ingest-rdf` and
   `ingest-vectors`, declared in the Makefile. Run `make ingest` and both run in
   the right order.
2. **Self-documenting.** Run `make help` to list available targets and what they do.

| Target | Description |
|---|---|
| `make ingest-smoke` | Smoke-test the whole pipeline on a tiny slice (100 edges, 5 abstracts). Run first when bootstrapping. |
| `make ingest-rdf` | Convert full Hetionet JSON to Turtle. Writes `ontology/hetionet.ttl`. Detail in [`rdf/`](rdf/README.md). |
| `make ingest-vectors` | Fetch PubMed abstracts and build the Chroma collection. Detail in [`vector/`](vector/README.md). |
| `make ingest` | Run `ingest-rdf` then `ingest-vectors`. |

Each script also supports `--help` directly if you want to run it outside Make:

```bash
python ingest/rdf/hetionet_to_rdf.py --help
```
