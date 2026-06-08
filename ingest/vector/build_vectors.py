#!/usr/bin/env python3
"""Embed cached PubMed abstracts into a Chroma collection (the vector corpus).

Reads the per-entity abstract files written by pubmed_fetch.py, splits each
abstract into word-window chunks, embeds them with a local SentenceTransformer
(all-MiniLM-L6-v2 — local, free, reproducible), and writes them to a persistent
Chroma collection at --out.

Embeddings are computed here explicitly and handed to Chroma, rather than letting
Chroma own an embedding function. That keeps the embedding model a single visible
swap point: retrievers/vector.py must embed queries with the *same* model, and
naming it here (not burying it in collection config) makes that contract obvious.

--query runs one similarity search after building. That is the build-order step-1
acceptance check: "one similarity query returning a real answer".
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "pubmed_abstracts"


def parse_entity_file(text: str) -> tuple[dict, list[dict]]:
    """Inverse of pubmed_fetch.render_entity_file.

    Returns (entity_meta, records) where entity_meta = {term, label, kind} and
    each record = {pmid, title, abstract}. Tolerant of a missing header so a
    hand-dropped abstract file still ingests (entity fields just come back empty)."""
    lines = text.splitlines()
    meta: dict = {"term": "", "label": "", "kind": ""}
    if lines and lines[0].startswith("# entity:"):
        parts = lines[0][len("# entity:"):].strip().split("\t")
        meta["term"] = parts[0] if parts else ""
        meta["label"] = parts[1] if len(parts) > 1 else ""
        meta["kind"] = parts[2].strip("()") if len(parts) > 2 else ""
        lines = lines[1:]

    records: list[dict] = []
    cur: dict | None = None
    for line in lines:
        if line.startswith("# pmid:"):
            if cur:
                records.append(cur)
            cur = {"pmid": line.split(":", 1)[1].strip(), "title": "", "abstract": ""}
        elif line.startswith("# title:") and cur is not None:
            cur["title"] = line.split(":", 1)[1].strip()
        elif line.strip() and cur is not None:
            cur["abstract"] = (cur["abstract"] + " " + line.strip()).strip()
    if cur:
        records.append(cur)
    return meta, records


def chunk_text(text: str, size: int = 180, overlap: int = 30) -> list[str]:
    """Split into ~`size`-word windows with `overlap` words of carry-over.

    all-MiniLM-L6-v2 truncates input beyond ~256 word-pieces, so a long abstract
    must be split or its tail is never embedded. Short abstracts (the common case)
    return as a single chunk. Overlap preserves context that would otherwise be
    severed at a window boundary."""
    words = text.split()
    if not words:
        return []
    if len(words) <= size:
        return [" ".join(words)]
    step = size - overlap
    return [" ".join(words[i:i + size]) for i in range(0, len(words), step) if words[i:i + size]]


def load_chunks(abstracts_dir: Path) -> tuple[list[str], list[str], list[dict]]:
    """Read every cached abstract file into Chroma-ready (ids, documents, metadatas).

    One chunk per id; id = '<term>:<pmid>:<chunk_index>' so a retrieval hit traces
    back to both the seeding entity and the source paper (PMID-level provenance)."""
    ids: list[str] = []
    docs: list[str] = []
    metas: list[dict] = []
    for path in sorted(abstracts_dir.glob("*.txt")):
        meta, records = parse_entity_file(path.read_text(encoding="utf-8"))
        for rec in records:
            for ci, chunk in enumerate(chunk_text(rec["abstract"])):
                ids.append(f'{meta["term"] or path.stem}:{rec["pmid"]}:{ci}')
                docs.append(chunk)
                metas.append({
                    "entity": meta["term"],
                    "label": meta["label"],
                    "kind": meta["kind"],
                    "pmid": rec["pmid"],
                    "title": rec["title"],
                })
    return ids, docs, metas


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--abstracts", type=Path, required=True, help="Directory of cached abstract .txt files.")
    ap.add_argument("--out", type=Path, required=True, help="Directory for the persistent Chroma collection.")
    ap.add_argument("--model", default=EMBED_MODEL, help=f"SentenceTransformer model id (default: {EMBED_MODEL}).")
    ap.add_argument("--query", default=None,
                    help="After building, run one similarity search and print the top hits (step-1 check).")
    ap.add_argument("--top-k", type=int, default=3, help="Hits to return for --query (default 3).")
    args = ap.parse_args()

    if not args.abstracts.is_dir():
        print(f"error: abstracts dir not found: {args.abstracts}", file=sys.stderr)
        return 1
    ids, docs, metas = load_chunks(args.abstracts)
    if not ids:
        print(f"error: no abstracts found in {args.abstracts}", file=sys.stderr)
        return 1

    # Deferred: keep the module importable for the hermetic test suite, which runs
    # under the `ingest` extra and pulls neither chromadb nor sentence-transformers.
    import chromadb
    from sentence_transformers import SentenceTransformer

    print(f"embedding {len(ids)} chunks with {args.model} ...", file=sys.stderr)
    model = SentenceTransformer(args.model)
    embeddings = model.encode(docs, show_progress_bar=False, normalize_embeddings=True).tolist()

    args.out.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(args.out))
    # Rebuild from scratch so re-runs are idempotent — no stale or duplicated chunks.
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    coll = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
    # Chroma caps a single add() (~5.4k); a real corpus exceeds it, so add in batches.
    BATCH = 5000
    for i in range(0, len(ids), BATCH):
        sl = slice(i, i + BATCH)
        coll.add(ids=ids[sl], documents=docs[sl], metadatas=metas[sl], embeddings=embeddings[sl])
    print(f"wrote {coll.count()} chunks to collection '{COLLECTION}' at {args.out}", file=sys.stderr)

    if args.query:
        q_emb = model.encode([args.query], normalize_embeddings=True).tolist()
        res = coll.query(query_embeddings=q_emb, n_results=args.top_k)
        print(f"\nquery: {args.query!r}", file=sys.stderr)
        for rank, (doc, meta, dist) in enumerate(
            zip(res["documents"][0], res["metadatas"][0], res["distances"][0]), 1
        ):
            snippet = doc[:200].replace("\n", " ")
            print(f"\n[{rank}] cosine_dist={dist:.4f}  {meta.get('label')} (pmid {meta.get('pmid')})", file=sys.stderr)
            print(f"     {snippet}...", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
