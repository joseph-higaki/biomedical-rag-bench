# Ingestion pipeline

Three sequential scripts produce the artifacts the retrievers depend on. Orchestrated by the top-level `Makefile`.

## Pipeline

```
hetionet_to_rdf.py    Hetionet JSON          → ontology/hetionet.ttl
        ↓
   (manual)           ontology/hetionet.ttl  → GraphDB repository
        ↓
pubmed_fetch.py       ontology/hetionet.ttl  → data/abstracts/
        ↓
build_vectors.py      data/abstracts/        → data/chroma/
```

Each step is independently runnable. Step 2 (loading Turtle into GraphDB) is manual the first time so the repository configuration is explicit; after that it's a no-op unless the Turtle file changes.

## Make targets

If you haven't used Make before: `make <target>` runs the recipe defined in the `Makefile` at the repo root. Make is a thin orchestration layer — each target is a small shell script. Two reasons we use it:

1. **Dependencies are explicit.** `make ingest` depends on `ingest-rdf` and `ingest-vectors`, declared in the Makefile. Run `make ingest` and both run in the right order.
2. **Self-documenting.** Run `make help` (defined in the Makefile) to list available targets and what they do.

The targets relevant to ingestion:

| Target | Description |
|---|---|
| `make ingest-smoke` | Smoke-test the pipeline on a tiny slice (100 triples, 5 abstracts). Run this first when bootstrapping. |
| `make ingest-rdf` | Convert full Hetionet JSON to Turtle. Writes `ontology/hetionet.ttl`. |
| `make ingest-vectors` | Fetch PubMed abstracts and build the Chroma vector collection. |
| `make ingest` | Run `ingest-rdf` then `ingest-vectors`. |

Each script also supports `--help` directly if you want to run them outside of Make:

```bash
python ingest/hetionet_to_rdf.py --help
```

## One-time GraphDB repository setup

The first time you run the pipeline, after `make up` brings GraphDB online and `make ingest-rdf` produces `ontology/hetionet.ttl`, create the GraphDB repository through the Workbench:

1. Open http://localhost:7200 in a browser.
2. **Setup → Repositories → Create new repository.**
3. **Repository type:** GraphDB Repository.
4. **Repository ID:** `hetionet`.
5. **Ruleset:** `empty`. This disables reasoning, which is the Project 1 baseline. (Project 2 changes this.)
6. **Title:** `Hetionet (Project 1 baseline)`.
7. Leave other defaults; click **Create**.

Then load the Turtle file:

1. **Import → User data → Upload RDF files.**
2. Select `ontology/hetionet.ttl`.
3. **Target graphs:** `From data` (so the Turtle's prefixes are honored).
4. Click **Import**. Loading 2.25M triples takes ~5–10 minutes on a laptop with GraphDB's single write thread.

When the load completes, verify with a SPARQL query in **SPARQL** in the left nav:

```sparql
SELECT (COUNT(*) AS ?total) WHERE { ?s ?p ?o }
```

Should return ~2.25M.

## Re-ingesting

The Turtle file changes if `hetionet_to_rdf.py` changes (new URI conventions, RDF-star edge properties, etc.). To re-ingest:

1. Re-run `make ingest-rdf` to regenerate `ontology/hetionet.ttl`.
2. In the Workbench, **Setup → Repositories → hetionet → Clear repository.**
3. Re-import as above.

Or, faster during development, use `make clean-graphdb` to wipe everything and start fresh:

```bash
make clean-graphdb     # destroys ./graphdb-data/, confirms first
make up                # restart GraphDB
# then recreate the repository as above
```

## PubMed rate limits

`pubmed_fetch.py` uses the NCBI E-utilities API. Without an API key, the rate limit is 3 requests/second. With a free API key (set via `NCBI_API_KEY` env var), it's 10 requests/second.

For the full Hetionet entity set, expect:

- ~30–60 minutes without a key
- ~10–20 minutes with a key

Get a key at https://www.ncbi.nlm.nih.gov/account/. The key is read from the environment; it is never committed to the repo.

## Caching

`pubmed_fetch.py` caches fetched abstracts under `data/abstracts/`. Re-running the script only fetches entities that aren't already cached. This is gitignored bulk — committing the cache would inflate the repo.

If you want to force a refetch (e.g. PubMed updated abstracts for entities you care about), delete the specific cached files or the whole directory.

## Outputs

After `make ingest` completes successfully, the following exist:

- `ontology/hetionet.ttl` — full RDF graph, loaded into GraphDB
- `data/abstracts/<entity-id>.txt` — one file per Hetionet entity
- `data/chroma/` — Chroma persistent collection with all abstracts embedded

The retrievers (`retrievers/vector.py`, `retrievers/graph.py`) consume these.
