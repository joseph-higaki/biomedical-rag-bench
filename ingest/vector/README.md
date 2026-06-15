# Vector ingestion

**Purpose.** Fetch PubMed abstracts for the Hetionet entities and embed them into a Chroma
collection; the `vector` retriever queries it by similarity.

**Inputs → Outputs.**

```
pubmed_fetch.py    data/rdf/hetionet.ttl  → data/abstracts/   (one .txt per entity)
        ↓
build_vectors.py   data/abstracts/        → data/chroma/      (embedded collection)
```

**Key files.** `pubmed_fetch.py` (NCBI E-utilities → abstract cache), `build_vectors.py`
(abstracts → Chroma), `select_corpus_entities.py` (entity selection).
**How to run.** `make ingest-vectors`, or each script with `--help` (`--extra fetch` /
`--extra vector`).
**Where it sits.** The Vector half of Knowledge Ingestion (root README → Architecture). A hard
prerequisite is `make ingest-rdf`: `pubmed_fetch.py` reads the entity set from the shared
`data/rdf/hetionet.ttl` — not from a live GraphDB — so the vector side never needs GraphDB up.

> **Status: full corpus built.** Scripts written, executed, and scaled to the full
> literature-kind entity set (`full-*` corpus profile in `eval/corpus/`: 77,424 abstracts →
> 152,943 chunks). The original five-abstract smoke test (build order step 1) is preserved
> below as the "Smoke test observation".

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

## PubMed rate limits and concurrency

`pubmed_fetch.py` uses the NCBI E-utilities API. The cap is **on the whole client**:
3 requests/second anonymously, 10/second with a free API key (`NCBI_API_KEY`).

The fetcher is **concurrent** — a thread pool (`--workers`, default 8) behind a single
global rate limiter (`--rate`, default 9/s keyed, 2.7/s anon, just under the caps). This
matters because the work is *latency-bound, not CPU-bound*: a serial loop keeps one request
in flight at a time and idles on network round-trips, so it never approaches the rate cap.
Concurrency overlaps the latency and fills the pipe up to the cap — two requests per entity
(esearch + efetch) at ~9/s ≈ 4.5 entities/s.

For the full literature-kind entity set (~29k genes/diseases/compounds/symptoms/side-effects/
pharmacologic-classes):

- **~1.5–2 hours with a key** (was ~11 h serial)
- proportionally slower anonymously (2.7/s)

The run is **resumable and idempotent** (see Caching) — a crash or Ctrl-C loses nothing, and
re-running picks up only the entities not yet cached. Each network call is retried with
backoff, so a transient NCBI blip doesn't drop an entity. Get a key at
https://www.ncbi.nlm.nih.gov/account/; it is read from the environment, never committed.

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
