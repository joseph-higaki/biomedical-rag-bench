"""retrievers/vector.py — dense-retrieval control (build step 4).

The benchmark's *control* condition: embed the question with the same
SentenceTransformer the corpus was built with, query the persistent Chroma
collection by cosine similarity, and hand the top-k chunks to the generator as
context. No LLM in the retriever — deterministic given the store and the query.

It parallels the graph retriever deliberately: where `graph_neighborhood` links
the question's named entities and traverses their subgraph, this embeds the whole
question and returns the nearest chunks. Both fetch context around the question's
anchors and let the fixed generator reason, so a difference in answer quality
traces to *representation* (free-text abstracts vs. labeled triples), not to the
mechanism doing the fetching.

The embedding model is a single visible swap point. `build_vectors.py` names it at
ingestion; this names the identical default and must stay in sync — query and
corpus embeddings are only comparable in the same vector space. Passing a `--model`
to ingestion means passing the same `model` here.

Honesty: the retriever sees only the `query` string (the Retriever protocol). It
never touches a question's `seeds` or ground-truth — those are for scoring.

Telemetry: every result logs the store path, collection, model, k, and the per-hit
cosine distances into `traversal_info`, so a factorial EDA can slice by any of them.
Additive keys only (the contract).
"""
from __future__ import annotations

import os

from retrievers.base import RetrievalResult, build_result, stopwatch

# Must match build_vectors.py — query and corpus share one embedding space.
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION = "pubmed_abstracts"
DEFAULT_STORE = os.environ.get("CHROMA_STORE", "data/chroma-smoke")


class VectorRetriever:
    """Embed the question → top-k nearest Chroma chunks. ~one file, no LLM.

    `top_k` is the analogue of the graph retriever's fan caps: the knob that sets how
    much context the condition gets. It defaults conservative and is logged with every
    result so a run records exactly what budget produced it.

    The Chroma client and the embedding model are loaded lazily on first `retrieve`
    and cached for the life of the process — the model load (a few hundred MB) is the
    bulk of first-call latency, same first-call-cost pattern as the graph gazetteer.
    """

    name = "vector"

    def __init__(
        self,
        store: str | None = None,
        *,
        collection: str = COLLECTION,
        model: str = EMBED_MODEL,
        top_k: int = 5,
    ) -> None:
        self.store = store or DEFAULT_STORE
        self.collection = collection
        self.model_name = model
        self.top_k = top_k
        self._model = None  # lazy SentenceTransformer
        self._coll = None  # lazy Chroma collection handle

    # --- store / model access ---------------------------------------------
    # Imported lazily so the module imports without the `vector` extra (chromadb,
    # sentence-transformers), same pattern as graph.py's httpx and build_vectors.py.
    def _ensure_loaded(self) -> None:
        if self._model is None:
            import chromadb
            from sentence_transformers import SentenceTransformer

            self._model = SentenceTransformer(self.model_name)
            client = chromadb.PersistentClient(path=self.store)
            self._coll = client.get_collection(self.collection)

    # --- the contract ------------------------------------------------------
    def retrieve(self, query: str) -> RetrievalResult:
        with stopwatch() as sw:
            self._ensure_loaded()
            assert self._model is not None and self._coll is not None
            # normalize_embeddings to match the corpus (cosine space); query() returns
            # nearest-first, so ids/documents/distances are already rank-ordered.
            q_emb = self._model.encode(
                [query], normalize_embeddings=True
            ).tolist()
            res = self._coll.query(
                query_embeddings=q_emb,
                n_results=self.top_k,
                include=["documents", "metadatas", "distances"],
            )
            ids = res["ids"][0]
            docs = res["documents"][0]
            metas = res["metadatas"][0]
            dists = res["distances"][0]

            # One labeled block per chunk so the generator can attribute a claim to its
            # source paper; mirrors graph.py serializing one line per triple.
            blocks = [
                f"[{m.get('label') or m.get('entity')} — PMID {m.get('pmid')}] {d}"
                for d, m in zip(docs, metas)
            ]
            context = "\n\n".join(blocks)
            sources = ids  # '<term>:<pmid>:<chunk>' — traces to entity + paper

        return build_result(
            context=context,
            sources=sources,
            latency_ms=sw.ms,
            traversal_info={
                "mechanism": "dense",
                "store": self.store,
                "collection": self.collection,
                "embed_model": self.model_name,
                "top_k": self.top_k,
                "num_chunks": len(ids),
                "cosine_distances": [round(d, 4) for d in dists],
                "pmids": [m.get("pmid") for m in metas],
            },
        )
