# H5 build-cost — methodology + recorded profile

**What this is.** H5 ("compute / indexing") has two halves. Query latency is scored from
per-retrieval `latency_ms` telemetry like any other metric. The *other* half — the one-time
cost of building each backend's index — is not a per-question score; it is a small profile
measured **once per backend at a stated corpus scale**. This page defines that profile, says
where each number comes from, and records the current full-corpus values.

It lives in `analysis/` because it is a *consumer-side* interpretation of build artifacts,
not part of producing results. It is a candidate to be lifted into the analytics repo with
the rest of this directory (see [`analysis/README.md`](README.md) → Extraction boundary).

> **Scope boundary.** This page is the one-time **capex** of building each backend's index. The
> recurring **opex** — per-query LLM token spend at generation / SPARQL-writing / judging, and the
> tokens→dollars pricing plan — is its sibling, [`run-cost.md`](run-cost.md). Keep them separate:
> a single "cost" number would conflate index construction with inference spend.

> **Naming note.** This was previously filed under the README's "structural" hypotheses
> bucket. That label was wrong: build cost is *measured*, not observed by inspection. It is
> per-backend rather than per-question — that is the only real distinction from H1/H2/H3/H7.

## Why it is not one number

The two backends spend their one-time cost on different things, so a single "build cost"
scalar would compare apples to oranges. Report a **profile** across a few commensurable
dimensions instead.

| Backend | Stage 1 | Stage 2 | Cost character |
|---|---|---|---|
| **Graph** (`make ingest-rdf` → `make ingest-load`) | Hetionet JSON → Turtle (offline, CPU, deterministic) | stream-load Turtle into GraphDB; **GraphDB builds its triple indexes here** | index construction; no external API |
| **Vector** (`make ingest-vectors`) | fetch PubMed abstracts (network/API-bound, rate-limited) | chunk + embed with `sentence-transformers`, persist Chroma | embedding inference + network fetch |

## The dimensions

For each backend, at a fixed corpus scale:

1. **Wall-clock per stage** — how long each build stage takes. The direct "how expensive to
   build" number.
2. **One-time external cost** — network requests / dollars. Graph: none (offline convert +
   local load). Vector: PubMed fetch volume (wall-clock here is dominated by rate-limit
   politeness, not compute); $0 if embeddings run locally (they do — MiniLM on-device).
3. **On-disk footprint** — the persisted index size. The storage cost of the representation.
4. **Corpus denominator** — triples/nodes/edges (graph) and abstracts/chunks/words (vector).
   A build time without its denominator is uninterpretable; always report the scale.

## Where each number comes from

- **Footprint + denominator** are already captured per corpus build in
  `ingest/corpus/<corpus_build_id>.json` (emitted by `ingest/corpus_profile.py`). That file
  is the authoritative source for scale; do not hand-transcribe counts elsewhere.
- **Wall-clock + peak memory** are not yet captured by any script. Measure by hand (below).
  Per the repo's "proven before codified" policy, only wrap this in a manifest emitter if
  build re-runs become frequent.
- **Query latency** (the scored half of H5) comes from `latency_ms` on every result row via
  the analysis loader — out of scope for this page.

### Capture procedure (wall-clock + footprint)

```bash
mkdir -p build
/usr/bin/time -v make ingest-rdf      2> build/graph-convert.time
/usr/bin/time -v make ingest-load     2> build/graph-load.time     # needs GraphDB up
/usr/bin/time -v make ingest-vectors  2> build/vector.time
du -sh data/rdf/hetionet.ttl graphdb-data data/abstracts data/chroma
```

`/usr/bin/time -v` reports elapsed wall-clock, peak RSS, and CPU% per stage — enough to
characterize where the cost went without instrumenting the scripts.

## Recorded profile — corpus `full-2c102cb0` (measured 2026-06-11)

Footprint and scale below are from the corpus profile + on-disk `du` (2026-06-15). **Build
wall-clock is not yet captured** — run the procedure above and fill the table.

### Graph backend

| Dimension | Value | Source |
|---|---|---|
| Triples | 11,275,571 | corpus profile |
| Nodes / edges | 47,031 / 2,250,197 | corpus profile |
| Source Turtle (`data/rdf/hetionet.ttl`) | 469 MB | `du` |
| GraphDB index (`graphdb-data/`) | 923 MB | `du` |
| Convert wall-clock (`ingest-rdf`) | _TODO_ | `/usr/bin/time` |
| Load + index wall-clock (`ingest-load`) | _TODO_ | `/usr/bin/time` |
| External API | none (offline) | — |

### Vector backend

| Dimension | Value | Source |
|---|---|---|
| Abstracts | 77,424 | corpus profile |
| Chunks (vectors) | 152,943 | corpus profile |
| Words | 18,429,751 | corpus profile |
| Embed model | `sentence-transformers/all-MiniLM-L6-v2` (180-token chunks, 30 overlap) | corpus profile |
| Abstracts on disk (`data/abstracts/`) | 201 MB | `du` |
| Chroma store (`data/chroma/`) | 1.6 GB | `du` |
| Fetch wall-clock (`pubmed_fetch`) | _TODO_ | `/usr/bin/time` |
| Embed + persist wall-clock (`build_vectors`) | _TODO_ | `/usr/bin/time` |
| External API | PubMed fetch (rate-limited); embeddings local, $0 | — |

## Reading it — the honest verdict

The README's *predicted* H5 verdict was "graph: cheap query, expensive index." **Do not
report that as settled — let the numbers decide.** On footprint alone the asymmetry already
points the other way: Chroma (1.6 GB) is the largest single artifact, larger than GraphDB's
index (923 MB), and embedding ~153k chunks through a transformer is plausibly the slowest
build stage of either backend. If the wall-clock confirms "vector was the more expensive
build," that is the more interesting and more honest finding — exactly the kind of claim
that should rest on `time`/`du` output rather than the intuition that graphs are heavy.

The defensible part of the original claim is *query*-side: graph and vector are both cheap
to query at run time (`latency_ms` will show this). "Expensive to build" is the part that
needs measurement before it is asserted.

## Data-hygiene notes (fix when convenient)

- The corpus profile's `graph.ttl_path` still reads `ontology/hetionet.ttl`; the generated
  Turtle moved to `data/rdf/hetionet.ttl` (commit 1405191). Regenerate the profile to refresh.
- `data/chroma/` holds **two** collection UUIDs — a rebuild left an orphan. The footprint
  above is the whole directory; isolate the live collection before quoting a precise
  vector-index size.
