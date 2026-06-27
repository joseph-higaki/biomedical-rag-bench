# RDF ingestion (graph side)

**Purpose.** Convert Hetionet JSON to RDF-star Turtle and load it into GraphDB. Covers
Projects 1–3 (Project 1 loads instance data with `ruleset=empty`; Project 2 re-serves the
same triples via OBDA; Project 3 adds reasoning over them — none change this transform). The
folder is `rdf/`, not `graph/`, so it reads distinctly against the future `lpg/` (Project 4's
Neo4j path — also a graph).

**Inputs → Outputs.**

```
hetionet_to_rdf.py    Hetionet JSON          → data/rdf/hetionet.ttl
        ↓
   (manual, one-time)  data/rdf/hetionet.ttl  → GraphDB repository
```

**Key files.** `hetionet_to_rdf.py` (streaming JSON → Turtle), `graphdb-repo-config.ttl`
(reproducible repo config, `ruleset=empty`), [`hetionet-data-notes.md`](hetionet-data-notes.md)
(URI mapping, source structure, RDF-star triple-count note).
**How to run.** `make ingest-rdf`, then the one-time repo setup + load below.
**Where it sits.** The Graph half of Knowledge Ingestion (root README → Architecture). The
`data/rdf/hetionet.ttl` it emits is the **shared artifact**: it loads into GraphDB *and* seeds
vector ingestion (`pubmed_fetch.py` reads the entity set from the `.ttl`), so this step is a
hard prerequisite of the vector side.

`hetionet_to_rdf.py` streams the JSON with `ijson` and writes Turtle statement-by-statement —
it never materializes the full graph in memory (see [Why streaming, not in-memory](#why-streaming-not-in-memory)).

## Why streaming, not in-memory

**Decision (provisional, May 2026).** The Hetionet JSON → Turtle transform streams both sides: the source is parsed incrementally with `ijson` and Turtle is written statement-by-statement. It never materializes the full document via `json.load`, nor builds the full graph in an in-memory `rdflib.Graph`.

**Why.** Decompressed, the Hetionet graph is ~712 MB of JSON (47k nodes, 2.25M edges), and the RDF-star expansion multiplies the statement count. On a 7 GB-RAM dev box, the naive `json.load` + in-memory `Graph` build does not fit. Streaming keeps memory bounded and roughly constant regardless of dataset size. The cost is hand-written Turtle serialization instead of a library serializer; correctness is guarded by round-tripping the smoke slice through `pyoxigraph` (Rust-backed Oxigraph, which parses Turtle-star and runs SPARQL-star offline) and asserting a sample query returns the expected answer. `rdflib` 7.6 has no RDF-star support, so it cannot parse the edge annotations — see [`hetionet-data-notes.md`](hetionet-data-notes.md).

**Revisit if** the transform proves too slow or the hand-written serializer accumulates escaping bugs that a library serializer would have handled. The swap point is contained to `hetionet_to_rdf.py`; nothing downstream cares how the Turtle was produced.

## Prerequisite: GraphDB license

GraphDB 11 requires a free (email-gated) license file before **writes** succeed — reads work
without it. One-time per developer; full steps are owned by
[`secrets/README.md`](../../secrets/README.md).

## One-time GraphDB repository setup

After `make up` brings GraphDB online (with the license, above) and
`make ingest-rdf` produces `data/rdf/hetionet.ttl`, create the `hetionet`
repository. Scripted (preferred — reproducible, ruleset baked in):

```bash
curl -X POST http://localhost:7200/rest/repositories \
     -F "config=@ingest/rdf/graphdb-repo-config.ttl"
```

The config sets **Repository ID** `hetionet` and **ruleset** `empty` (no
reasoning — the Project 1 baseline; Project 3 changes this). Or, equivalently,
through the Workbench:

1. Open http://localhost:7200 in a browser.
2. **Setup → Repositories → Create new repository.**
3. **Repository type:** GraphDB Repository.
4. **Repository ID:** `hetionet`.
5. **Ruleset:** `empty`. This disables reasoning, which is the Project 1 baseline. (Project 3 changes this.)
6. **Title:** `Hetionet (Project 1 baseline)`.
7. Leave other defaults; click **Create**.

Then load the Turtle file. The full graph is ~470 MB, which exceeds the
Workbench browser-upload cap (200 MB, `graphdb.workbench.maxUploadSize`), so load
it over the REST statements endpoint instead — it streams the file with no size
limit and is scriptable:

```bash
# Clear any existing data in the repo (e.g. a prior smoke slice). Returns HTTP 204.
curl -i -X DELETE 'http://localhost:7200/repositories/hetionet/statements'

# Stream-load the full graph. POST = add; -T streams the file (no 470 MB buffer).
# ~5–10 minutes on GraphDB's single write thread; curl blocks silently until done,
# then prints "204 No Content" — an empty body is success, not a failure.
curl -i -X POST -H 'Content-Type: text/turtle' \
     -T data/rdf/hetionet.ttl \
     'http://localhost:7200/repositories/hetionet/statements'
```

RDF-star quoted triples (`<< … >>`) parse under plain `text/turtle` in GraphDB 11
(RDF4J 5.x); if a build ever rejects them, retry with
`-H 'Content-Type: application/x-turtle-star'`.

The Workbench is fine for the **smoke slice** (well under the cap): **Import →
User data → Upload RDF files**, select the `.ttl`, **Target graphs:** `From data`
(so the Turtle's prefixes are honored), **Import**.

When the load completes, verify with a SPARQL query in **SPARQL** in the left nav:

```sparql
SELECT (COUNT(*) AS ?total) WHERE { ?s ?p ?o }
```

Should return **~11.2M**. This is the *triple* count, ~5× the edge count: each of
the 2.25M edges contributes its base triple plus ~4 RDF-star annotation triples
(`direction`, `source`, `license`, `pubmed_ids`, …), and each of the 47k nodes
adds a type + label triple. The `…: 2250197 edges` line printed by
`make ingest-rdf` reports **edges, not triples** — the two are not meant to match.

## Re-ingesting

The Turtle file changes if `hetionet_to_rdf.py` changes (new URI conventions, RDF-star edge properties, etc.). To re-ingest:

1. Re-run `make ingest-rdf` to regenerate `data/rdf/hetionet.ttl`.
2. Clear and reload over the REST statements endpoint (the two `curl` commands
   above): the `DELETE` clears the old data, the `POST` streams the new file.

Or, faster during development, use `make clean-graphdb` to wipe everything and start fresh:

```bash
make clean-graphdb     # destroys ./graphdb-data/, confirms first
make up                # restart GraphDB
# then recreate the repository as above
```

## Output

- `data/rdf/hetionet.ttl` — full RDF graph, loaded into GraphDB. Consumed by `retrievers/graph.py`.
