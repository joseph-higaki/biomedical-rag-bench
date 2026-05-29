# Vector ingestion

Fetches PubMed abstracts for the Hetionet entities and embeds them into a Chroma
collection. The vector retriever queries this collection by similarity.

```
pubmed_fetch.py    ontology/hetionet.ttl  → data/abstracts/   (one .txt per entity)
        ↓
build_vectors.py   data/abstracts/        → data/chroma/      (embedded collection)
```

`pubmed_fetch.py` reads the entity set from the RDF Turtle file (not from a live
GraphDB), so the vector side only depends on `make ingest-rdf` having produced
`ontology/hetionet.ttl` — not on GraphDB being up.

> **Status: not yet built.** These scripts are scaffolded by the Makefile
> (`make ingest-vectors`, `make ingest-smoke`) but not implemented. Build order
> step 1 is the first slice: PubMed → 5 abstracts → Chroma → one similarity query
> returning a real answer.

## Evolving baseline

The vector side is intentionally the *control* in this benchmark, and it
strengthens across minor releases rather than shipping fully tuned. The embedding
model and retrieval strategy sit behind the `Retriever` interface as swap points,
so each variant is registered as an additional retriever condition — prior
results stay on the table, comparable. Which variants ship, and in what order, is
tracked in the README release strategy and the build order, not pinned here.

## PubMed rate limits

`pubmed_fetch.py` uses the NCBI E-utilities API. Without an API key the rate limit
is 3 requests/second; with a free API key (set via `NCBI_API_KEY`) it's 10/second.

For the full Hetionet entity set, expect:

- ~30–60 minutes without a key
- ~10–20 minutes with a key

Get a key at https://www.ncbi.nlm.nih.gov/account/. The key is read from the
environment; it is never committed to the repo.

## Caching

`pubmed_fetch.py` caches fetched abstracts under `data/abstracts/`. Re-running only
fetches entities that aren't already cached. This is gitignored bulk — committing
the cache would inflate the repo.

To force a refetch (e.g. PubMed updated abstracts for entities you care about),
delete the specific cached files or the whole directory.

## Outputs

- `data/abstracts/<entity-id>.txt` — one file per Hetionet entity
- `data/chroma/` — Chroma persistent collection with all abstracts embedded

Consumed by `retrievers/vector.py`.
