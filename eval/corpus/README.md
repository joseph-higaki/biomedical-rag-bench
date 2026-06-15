# Corpus profiles

**Purpose.** The size and shape of the data each run is evaluated against — the *haystack*. Every
eval condition retrieves over one of these corpora, so "how big is the problem" is a first-class
factor, not a footnote. This directory holds one **corpus-build profile** (`<id>.json`) per
built corpus, produced by [`ingest/corpus_profile.py`](../../ingest/corpus_profile.py).

**Where it sits.** The corpus *dimension* of the analysis star schema: `ingest/corpus_profile.py`
emits these here, `run_eval.py` stamps the `corpus_build_id` into each run manifest, and the
analysis layer joins on it. Generated data, not hand-edited.

This file is the authoritative source for *what the profiles mean* and how each number is
measured. The **numbers themselves are not hand-maintained in prose** — the `*.json` files are
the single source of truth (same discipline as the question distribution in
[`eval/README.md`](../README.md)). The table below is a snapshot of two **named build ids**;
regenerate it from the JSON rather than editing digits in place.

## What a profile is

A profile measures a corpus from its *built* artifacts and is keyed by a `corpus_build_id`:

```
"<scale>-<fp8>"   e.g. full-2c102cb0, smoke-30c621e8
```

Readable at a glance (`smoke` / `sample` / `full`) **and** content-addressed: `fp8` is
`sha256(ttl_sha256 + vector_signature)[:8]`, so changing either backend — a regenerated graph,
a re-embedded store — mints a new id. The id is the join key: [`run_eval`](../run_eval.py)
stamps it into each run manifest as a one-field *reference* (not a re-measurement), so the
analysis layer can group results by corpus and the smoke/full comparison is just two rows.

## How each number is measured

Two backends, each read from what retrieval actually sees, with provenance recorded alongside:

**Graph** (`graph_*`, `sparqlgen` retrievers) — the Turtle source `bytes` + full `sha256` are
always recorded. Counts come from **SPARQL against a live endpoint serving the corpus**, because
the loaded store is what the retrievers query:

| metric | definition |
|---|---|
| `triples` | every asserted statement (`COUNT(*)`) |
| `nodes` | distinct subjects typed with a `het.io/schema/` metanode class (11 classes) |
| `edges` | node→node relationships: triples whose **subject and object are both typed nodes** |

`edges` is defined *structurally* (a link between two nodes) rather than by enumerating the 24
metaedge predicate names — robust to predicate naming, and it excludes attribute/annotation
triples (which point to literals or non-node IRIs). It cross-checks exactly against the per-edge
`direction`/`unbiased` annotation count (2,250,197).

A corpus with **no serving endpoint** (the smoke slice is never loaded into GraphDB) records ttl
provenance only — counts stay `null` with `source: "ttl-provenance-only…"`. Honest absence beats
a number measured against the wrong store; it also keeps smoke and full commensurable (both would
be live-store SPARQL, or neither).

**Vector** (`vector` retriever) — `n_chunks` and `store_bytes` from the Chroma store (what the
retriever searches); `n_abstracts` and `n_words` from the **source abstracts** via the canonical
`parse_entity_file`. Word count comes from the source text, **not** the Chroma documents: chunks
overlap by `chunk_overlap` words, so summing chunk words would double-count the overlaps. The
`embed_model` and chunk window are read from [`build_vectors.py`](../../ingest/vector/build_vectors.py)
so the profile reflects the real build config instead of a copy that can drift.

## Snapshot — `smoke-30c621e8` vs `full-2c102cb0`

Measured 2026-06-11, transcribed from `smoke-30c621e8.json` and `full-2c102cb0.json` in this
directory. If these change, [regenerate](#regenerate) — which overwrites those files — then
re-transcribe from them.

| metric | `smoke-30c621e8` | `full-2c102cb0` |
|---|--:|--:|
| **graph** — triples | — *(unloaded)* | 11,275,571 |
| nodes | — | 47,031 |
| edges | — | 2,250,197 |
| ttl bytes | 45,594 | 490,931,418 |
| **vector** — abstracts | 15 | 77,424 |
| words | 3,402 | 18,429,751 |
| chunks | 28 | 152,943 |
| store bytes | 774,308 | 1,696,505,746 |
| embed model | all-MiniLM-L6-v2 | all-MiniLM-L6-v2 |

The vector ratios cluster tightly (~5,400×), so smoke is a faithful scale model of full, not a
skewed fixture. The graph dashes are the deliberate "smoke has no GraphDB repo" cut above.

## Regenerate

Needs the `profile` extra (`chromadb` + `httpx` — no sentence-transformers; counting never
embeds). `--endpoint` is omitted for unloaded slices.

```bash
# smoke (ttl provenance only)
uv run --extra profile python -m ingest.corpus_profile --scale smoke \
    --ttl data/rdf/hetionet-smoke.ttl --abstracts data/abstracts-smoke --chroma data/chroma-smoke

# full (live SPARQL counts)
uv run --extra profile python -m ingest.corpus_profile --scale full \
    --ttl data/rdf/hetionet.ttl --abstracts data/abstracts --chroma data/chroma \
    --endpoint http://localhost:7200/repositories/hetionet
```
