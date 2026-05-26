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

## Prerequisite: GraphDB license

As of **GraphDB 11.0**, the Free edition is no longer license-free. The container
starts and answers reads, but **writes fail with `No license was set`** until a
free license file is in place. Request it from Ontotext (emailed), save it as
`secrets/graphdb.license`, then `make down && make up`. Full steps in
`secrets/README.md`. This is a one-time per-developer step.

## One-time GraphDB repository setup

After `make up` brings GraphDB online (with the license, above) and
`make ingest-rdf` produces `ontology/hetionet.ttl`, create the `hetionet`
repository. Scripted (preferred — reproducible, ruleset baked in):

```bash
curl -X POST http://localhost:7200/rest/repositories \
     -F "config=@ingest/graphdb-repo-config.ttl"
```

The config sets **Repository ID** `hetionet` and **ruleset** `empty` (no
reasoning — the Project 1 baseline; Project 2 changes this). Or, equivalently,
through the Workbench:

1. Open http://localhost:7200 in a browser.
2. **Setup → Repositories → Create new repository.**
3. **Repository type:** GraphDB Repository.
4. **Repository ID:** `hetionet`.
5. **Ruleset:** `empty`. This disables reasoning, which is the Project 1 baseline. (Project 2 changes this.)
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
     -T ontology/hetionet.ttl \
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

1. Re-run `make ingest-rdf` to regenerate `ontology/hetionet.ttl`.
2. Clear and reload over the REST statements endpoint (the two `curl` commands
   above): the `DELETE` clears the old data, the `POST` streams the new file.

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
