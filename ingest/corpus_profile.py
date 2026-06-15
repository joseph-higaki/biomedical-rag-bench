#!/usr/bin/env python3
"""ingest/corpus_profile.py — measure a built corpus → committed corpus-build profile.

The corpus is a factor in every eval, but the run manifest never recorded *which* corpus a
run drew from — see the dedup note in eval/analysis/load.py: existing runs span "a rebuilt
corpus", and nothing pins which. This script measures a built corpus once and emits a
committed, citable profile JSON keyed by a human-readable **and** content-addressed
`corpus_build_id` (e.g. `full-a1b2c3d4`). run_eval stamps that id into each manifest as a
one-field *reference* (not a re-measurement), so the analysis layer can group by corpus and
quantitatively diff smoke vs full — and an audience can see how big the data under test is.

Two backends, measured from their *built* artifacts:

  graph  — the Turtle source (bytes + sha256) is always recorded as provenance. Triple and
           node counts come from SPARQL against an --endpoint *serving this corpus*, because
           the live store is what the graph retrievers actually query. With no such endpoint
           (e.g. the smoke slice, which is never loaded into GraphDB) the counts stay null and
           `source` says so — honest absence over a number measured against the wrong store.

  vector — the Chroma store gives n_chunks + store bytes (what the vector retriever searches);
           the source abstracts give n_abstracts + n_words via the canonical parse_entity_file
           (the true text size, free of the chunk overlap that would inflate a chunk-word sum).
           Embed model + chunk window are read from build_vectors so the profile always
           reflects the real build config rather than a transcribed copy of it.

`corpus_build_id` = "<scale>-<fp8>", fp8 = sha256(ttl_sha256 + vector signature)[:8]: readable
at a glance, but changes whenever the graph source or the vector build changes, so a rebuilt
corpus gets a new id and the smoke/full diff is just two rows keyed by it.

Runs with the `profile` extra (chromadb + httpx — no sentence-transformers; counting never
embeds):

  # smoke (no endpoint: graph counts stay null, ttl provenance still recorded)
  uv run --extra profile python -m ingest.corpus_profile --scale smoke \
      --ttl data/rdf/hetionet-smoke.ttl --abstracts data/abstracts-smoke --chroma data/chroma-smoke

  # full (endpoint serving the corpus: triples + nodes populated)
  uv run --extra profile python -m ingest.corpus_profile --scale full \
      --ttl data/rdf/hetionet.ttl --abstracts data/abstracts --chroma data/chroma \
      --endpoint http://localhost:7200/repositories/hetionet
"""
from __future__ import annotations

import argparse
import hashlib
import inspect
import json
import time
from pathlib import Path

# build_vectors is the single source of truth for the abstract-file format and the vector
# build config. Its top-level imports are light (no chromadb / sentence-transformers — those
# are lazy inside main), so importing these costs nothing and keeps the profile in sync with
# the real ingest rather than re-stating constants that could drift.
from ingest.vector.build_vectors import COLLECTION, EMBED_MODEL, chunk_text, parse_entity_file

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "eval" / "corpus"
HETIO_SCHEMA = "https://het.io/schema/"  # metanode classes live here; see retrievers/graph.py

# Chunk window the corpus was built with, read from chunk_text's signature defaults so the
# profile records what the build actually used (build_vectors only encodes it there).
_CHUNK_DEFAULTS = {k: v.default for k, v in inspect.signature(chunk_text).parameters.items()
                   if v.default is not inspect.Parameter.empty}


def _sha256_file(path: Path) -> str:
    """Full hex sha256 of a file, streamed so a 490 MB ttl never lands in memory."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _dir_bytes(path: Path) -> int:
    """Total bytes of a store directory (Chroma is a dir: sqlite + hnsw segment files)."""
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())


def _sparql_scalar(endpoint: str, query: str) -> int:
    """Run a COUNT query and return the single integer binding. httpx is imported lazily so
    the module loads (and the smoke path runs) with no endpoint and no httpx installed."""
    import httpx

    resp = httpx.post(
        endpoint,
        data={"query": query},
        headers={"Accept": "application/sparql-results+json"},
        timeout=120,
    )
    resp.raise_for_status()
    bindings = resp.json()["results"]["bindings"]
    if not bindings:
        return 0
    var = next(iter(bindings[0]))  # the lone projected variable (?n)
    return int(bindings[0][var]["value"])


def graph_profile(ttl_path: Path, endpoint: str | None) -> dict:
    """ttl provenance always; triples/nodes/edges via SPARQL only against a serving endpoint.

    Counts, each validated against the live full repo:
      triples — every asserted statement (11,275,571).
      nodes   — distinct subjects typed with a hetio metanode class (47,031 across 11 classes).
      edges   — node→node relationships: triples whose subject AND object are both typed nodes
                (2,250,197). Defining an edge structurally (a link between two nodes) rather than
                by enumerating the 24 metaedge predicate names is robust to predicate naming and
                excludes attribute/annotation triples (which point to literals or non-node IRIs).
                Cross-checks exactly against the per-edge `direction`/`unbiased` annotation count."""
    prof = {
        "ttl_path": str(ttl_path),
        "ttl_bytes": ttl_path.stat().st_size,
        "ttl_sha256": _sha256_file(ttl_path),
        "endpoint": endpoint,
        "triples": None,
        "nodes": None,
        "edges": None,
    }
    if endpoint:
        prof["triples"] = _sparql_scalar(endpoint, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
        prof["nodes"] = _sparql_scalar(
            endpoint,
            f'SELECT (COUNT(DISTINCT ?s) AS ?n) WHERE {{ ?s a ?t '
            f'FILTER(STRSTARTS(STR(?t), "{HETIO_SCHEMA}")) }}',
        )
        prof["edges"] = _sparql_scalar(
            endpoint,
            f'SELECT (COUNT(*) AS ?n) WHERE {{ ?s ?p ?o . '
            f'?s a ?st . FILTER(STRSTARTS(STR(?st), "{HETIO_SCHEMA}")) '
            f'?o a ?ot . FILTER(STRSTARTS(STR(?ot), "{HETIO_SCHEMA}")) '
            f'FILTER(?p != rdf:type) }}',
        )
        prof["source"] = "sparql (live store)"
    else:
        prof["source"] = "ttl-provenance-only (no endpoint serving this corpus)"
    return prof


def vector_profile(abstracts_dir: Path, chroma_path: Path) -> dict:
    """n_chunks/bytes from the Chroma store; n_abstracts/n_words from the source abstracts.

    Word count comes from the source text (via the canonical parser), not from the Chroma
    documents — chunks overlap by `chunk_overlap` words, so summing chunk words would
    double-count the overlaps and overstate the corpus size."""
    import chromadb

    client = chromadb.PersistentClient(path=str(chroma_path))
    n_chunks = client.get_collection(COLLECTION).count()

    n_abstracts = 0
    n_words = 0
    for path in sorted(abstracts_dir.glob("*.txt")):
        _meta, records = parse_entity_file(path.read_text(encoding="utf-8"))
        n_abstracts += len(records)
        n_words += sum(len(rec["abstract"].split()) for rec in records)

    return {
        "chroma_path": str(chroma_path),
        "collection": COLLECTION,
        "store_bytes": _dir_bytes(chroma_path),
        "n_chunks": n_chunks,
        "n_abstracts": n_abstracts,
        "n_words": n_words,
        "abstracts_dir": str(abstracts_dir),
        # The build-time config, not read back from the store (Chroma persists only hnsw:space).
        # retrievers/vector.py must embed queries with this same model; see build_vectors.py.
        "embed_model": EMBED_MODEL,
        "chunk_size": _CHUNK_DEFAULTS.get("size"),
        "chunk_overlap": _CHUNK_DEFAULTS.get("overlap"),
    }


def build_id(scale: str, ttl_sha256: str, vector: dict) -> str:
    """'<scale>-<fp8>' — readable, but content-addressed so a rebuild mints a new id.

    The fingerprint folds the graph source hash and a vector signature (collection + chunk
    count + embed model), so changing either backend changes the id."""
    vsig = f'{vector["collection"]}:{vector["n_chunks"]}:{vector["embed_model"]}'
    fp8 = hashlib.sha256((ttl_sha256 + vsig).encode()).hexdigest()[:8]
    return f"{scale}-{fp8}"


def profile_corpus(scale: str, ttl: Path, abstracts: Path, chroma: Path,
                   endpoint: str | None) -> dict:
    graph = graph_profile(ttl, endpoint)
    vector = vector_profile(abstracts, chroma)
    return {
        "corpus_build_id": build_id(scale, graph["ttl_sha256"], vector),
        "scale": scale,
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "graph": graph,
        "vector": vector,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--scale", required=True, choices=["smoke", "sample", "full"],
                    help="Run-scale label (eval/analysis terminology). Prefixes the build id.")
    ap.add_argument("--ttl", type=Path, required=True, help="Turtle source for the graph corpus.")
    ap.add_argument("--abstracts", type=Path, required=True,
                    help="Directory of source abstract files (the *.txt the vector store was built from).")
    ap.add_argument("--chroma", type=Path, required=True, help="Persistent Chroma store directory.")
    ap.add_argument("--endpoint", default=None,
                    help="SPARQL endpoint serving THIS corpus (omit for unloaded slices like smoke).")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"Directory for the profile JSON (default {DEFAULT_OUT}).")
    args = ap.parse_args()

    prof = profile_corpus(args.scale, args.ttl, args.abstracts, args.chroma, args.endpoint)
    args.out.mkdir(parents=True, exist_ok=True)
    out_path = args.out / f'{prof["corpus_build_id"]}.json'
    out_path.write_text(json.dumps(prof, indent=2) + "\n")
    print(f'wrote {out_path}')
    print(json.dumps(prof, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
