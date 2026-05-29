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

> **Status: smoke test complete (build order step 1).** Scripts written and
> executed. Five abstracts fetched, embedded into Chroma, similarity query
> returning results. See "Smoke test observation" below.

## Smoke test observation

**Query:** `"loss of E-cadherin promotes tumor metastasis"`

**Results:**

| Rank | Gene | Cosine distance | Abstract topic |
|---|---|---|---|
| 1 | TRIM27 | 0.627 | Immune suppression in liver cancer |
| 2 | PSMA3 | 0.674 | Cell migration and invasion in prostate cancer |
| 3 | CDH1 | 0.676 | Hereditary breast cancer risk genes (BRCA1, BRCA2, CDH1) |

**What E-cadherin is (no biology background assumed):** CDH1 is the gene that
makes E-cadherin, a protein that acts like molecular glue holding cells together
in a tissue. When E-cadherin is lost, cells can detach and travel through the
body — the mechanism behind most cancer spreading (metastasis). It is a
well-known tumor suppressor.

**Why CDH1 ranked third:** PubMed's top result for the search term "CDH1" was a
breast cancer genetics paper listing CDH1 alongside BRCA1 and BRCA2 as an
inherited risk gene. The abstract mentions CDH1 and cancer but its language is
about genetic inheritance and family risk — not about the cell-detachment
mechanism. The embedder represents "what words appear in the text," not the
biological role of the entity being discussed.

TRIM27 ranked first because its abstract — about how liver tumors suppress the
immune system — contains language about the tumor microenvironment that is
semantically closer to "metastasis" than the CDH1 abstract's genetics language.

**Why this matters for the benchmark:** This is H2 and H4 playing out before a
single eval question is asked. Vector retrieval is sensitive to the language of
the retrieved text, not to the biological role of the entity that seeded it.
The PubMed query for "CDH1" returned an abstract where CDH1 appears in an
inheritance context rather than a mechanistic one — and the embedder had no
way to know the difference. A graph retriever can traverse directly from CDH1
to the disease nodes it connects to in Hetionet; the relationship is explicit,
not inferred from semantic proximity. That gap is what the benchmark is
designed to measure.

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
