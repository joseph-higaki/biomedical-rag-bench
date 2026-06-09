"""retrievers/graph.py — neighborhood graph retriever (build step 4).

Mechanism 2 of the two honest graph-RAG designs (see the session journal / README):
entity-link the question to graph nodes, pull a bounded k-hop neighborhood around
them from GraphDB, and serialize it as readable labeled triples for the generator.
No LLM in the retriever — deterministic, so the graph *condition* isolates the
representation under test rather than confounding it with text-to-SPARQL skill. The
realistic text-to-SPARQL system is a separate `graph_sparqlgen` condition, built
once the generator/LLM layer exists (step 5+).

It parallels the vector retriever deliberately: vector embeds the question and
returns top-k nearby chunks; this links the question's named entities and returns
their nearby subgraph. Both fetch context around the question's anchors and let the
fixed generator reason — so differences trace to representation, not mechanism.

Honesty: the retriever sees only the `query` string (the Retriever protocol). It
never touches a question's `seeds` or ground-truth SPARQL — those are for scoring.
Entity linking works off the question text plus the public label dictionary only.

Telemetry: every result records its full config into `traversal_info` (mechanism,
hops, fan caps, the entities it linked, the SPARQL it ran, counts) so a factorial
EDA can slice results by any of these factors. Additive keys only (the contract).
"""
from __future__ import annotations

import os
import re
from collections import defaultdict

from retrievers.base import RetrievalResult, build_result, stopwatch

SCHEMA = "https://het.io/schema/"  # hetio: — the edge/attribute namespace
RDFS_LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
DEFAULT_ENDPOINT = os.environ.get(
    "GRAPHDB_ENDPOINT", "http://localhost:7200/repositories/hetionet"
)
# Over-fetch ceiling per hop query; the real bound is the per-predicate / total caps
# applied in Python (SPARQL can't easily cap per-predicate without subquery noise). The hop
# queries pair this LIMIT with an ORDER BY: a bare LIMIT without ORDER BY returns an ARBITRARY
# subset (SPARQL guarantees no order otherwise), so when a hub node's expansion exceeds the
# ceiling the fetched subset — and thus the capped neighborhood — varied run to run. The
# ORDER BY makes the truncation a stable prefix, so retrieval is reproducible.
_FETCH_LIMIT = 5000


def _normalize(text: str) -> str:
    """Fold to the matchable form shared by gazetteer keys and question n-grams.

    Non-alphanumerics → spaces, lowercased, whitespace collapsed, so "non-small cell"
    and "non small cell" match, and punctuation in the question never blocks a hit.
    Lossy on non-ASCII (e.g. Greek in gene names) — a known precision limitation.
    """
    return " ".join(re.sub(r"[^0-9a-z]+", " ", text.lower()).split())


class NeighborhoodGraphRetriever:
    """Entity-link + bounded k-hop neighborhood over GraphDB. ~one file, no LLM.

    Caps (`hops`, `max_per_predicate`, `max_triples`) are the knob that defines what
    the graph condition can answer: too small and multi-hop answers aren't in the
    retrieved context; too large and the context is token-heavy noise. They default
    conservative (1 hop) and are logged with every result so a run records exactly
    what budget produced it. Bumping to hops=2 before the multi-hop eval is a tuning
    step (build order 6/7), calibrated against the question set.
    """

    # The base label; the live `name` embeds the hop budget (set per instance below) so
    # each configured budget is its own registry condition — graph_neighborhood_1hop /
    # graph_neighborhood_2hop. The hop value is also in traversal_info, so the name is the
    # grouping label and the telemetry is the source of truth. See run_eval.REGISTRY.
    base_name = "graph_neighborhood"

    def __init__(
        self,
        endpoint: str | None = None,
        *,
        hops: int = 1,
        max_per_predicate: int = 25,
        max_triples: int = 200,
    ) -> None:
        self.endpoint = endpoint or DEFAULT_ENDPOINT
        self.hops = hops
        self.name = f"{self.base_name}_{hops}hop"
        self.max_per_predicate = max_per_predicate
        self.max_triples = max_triples
        self._gazetteer: dict[str, tuple[str, str]] | None = None  # norm_label -> (uri, label)
        self._max_ngram = 1

    # --- GraphDB access ----------------------------------------------------
    # The retriever owns a minimal SELECT client rather than importing eval's
    # run_query seam: the retriever is the system *under test* and must not depend on
    # the ground-truth tooling. httpx is imported lazily so the module imports without
    # the `graph` extra (same pattern as run_ground_truth.py).
    def _select(self, query: str) -> list[dict[str, dict]]:
        import httpx

        resp = httpx.post(
            self.endpoint,
            data={"query": query},
            headers={"Accept": "application/sparql-results+json"},
            timeout=120.0,
        )
        resp.raise_for_status()
        return resp.json()["results"]["bindings"]

    # --- entity linking (gazetteer) ---------------------------------------
    def _load_gazetteer(self) -> dict[str, tuple[str, str]]:
        """Load every node label once into a {normalized_label -> (uri, label)} dict.

        ~47k nodes — a few MB in Python. The 11M triples stay in GraphDB; only the
        label dictionary is cached here. First-collision-wins on duplicate labels.
        """
        if self._gazetteer is None:
            rows = self._select(
                f"SELECT ?e ?l WHERE {{ ?e <{RDFS_LABEL}> ?l }}"
            )
            gaz: dict[str, tuple[str, str]] = {}
            for r in rows:
                label = r["l"]["value"]
                key = _normalize(label)
                if key and key not in gaz:
                    gaz[key] = (r["e"]["value"], label)
            self._gazetteer = gaz
            self._max_ngram = min(10, max((len(k.split()) for k in gaz), default=1))
        return self._gazetteer

    def _link(self, question: str) -> list[tuple[str, str]]:
        """Greedy longest-match the question's words against the gazetteer.

        Returns deduped (uri, label) anchors. Longest n-gram wins so "breast cancer"
        links as one entity, not "breast" + "cancer", and consumes its span.
        """
        gaz = self._load_gazetteer()
        words = _normalize(question).split()
        found: dict[str, str] = {}  # uri -> label, dedup
        i = 0
        while i < len(words):
            for span in range(min(self._max_ngram, len(words) - i), 0, -1):
                cand = " ".join(words[i : i + span])
                if cand in gaz:
                    uri, label = gaz[cand]
                    found[uri] = label
                    i += span
                    break
            else:
                i += 1
        return list(found.items())

    # --- neighborhood expansion -------------------------------------------
    def _hop_queries(self, uris: list[str]) -> tuple[str, str]:
        """Outgoing (entity edges + literal attributes) and incoming (entity edges)."""
        values = " ".join(f"<{u}>" for u in uris)
        outgoing = f"""SELECT ?aLabel ?p ?o ?oLabel (ISIRI(?o) AS ?oIri) WHERE {{
  VALUES ?anchor {{ {values} }}
  ?anchor <{RDFS_LABEL}> ?aLabel ; ?p ?o .
  FILTER(STRSTARTS(STR(?p), "{SCHEMA}"))
  OPTIONAL {{ ?o <{RDFS_LABEL}> ?oLabel }}
}} ORDER BY ?aLabel ?p ?o LIMIT {_FETCH_LIMIT}"""
        incoming = f"""SELECT ?s ?sLabel ?p ?aLabel WHERE {{
  VALUES ?anchor {{ {values} }}
  ?anchor <{RDFS_LABEL}> ?aLabel .
  ?s ?p ?anchor .
  FILTER(STRSTARTS(STR(?p), "{SCHEMA}"))
  ?s <{RDFS_LABEL}> ?sLabel .
}} ORDER BY ?s ?p ?aLabel LIMIT {_FETCH_LIMIT}"""
        return outgoing, incoming

    def _neighborhood(
        self, anchors: list[str]
    ) -> tuple[list[tuple[str, str, str, str | None]], list[str]]:
        """BFS k hops from the anchors. Returns (kept_rows, queries_run).

        Each row is (subject_label, predicate_localname, object_text, neighbor_uri):
        object is a neighbor's label (entity edge) or a literal value (attribute);
        neighbor_uri is the connected entity's URI (None for a literal attribute), so
        `sources` can be derived from the *kept* rows rather than the full fetch. Capped
        per predicate and overall, deterministically (sorted before capping).
        """
        rows: list[tuple[str, str, str, str | None]] = []
        queries: list[str] = []
        frontier = list(anchors)
        visited: set[str] = set()

        for _ in range(self.hops):
            frontier = [u for u in frontier if u not in visited]
            if not frontier:
                break
            visited.update(frontier)
            outgoing, incoming = self._hop_queries(frontier)
            queries.extend([outgoing, incoming])

            next_frontier: set[str] = set()
            for r in self._select(outgoing):
                pred = r["p"]["value"].rsplit("/", 1)[-1]
                if r.get("oIri", {}).get("value") == "true":
                    ouri = r["o"]["value"]
                    obj = r.get("oLabel", {}).get("value") or ouri.rsplit("/", 1)[-1]
                    rows.append((r["aLabel"]["value"], pred, obj, ouri))
                    next_frontier.add(ouri)
                else:  # literal attribute (chromosome, description, ...) — no neighbor URI
                    rows.append((r["aLabel"]["value"], pred, r["o"]["value"], None))
            for r in self._select(incoming):
                pred = r["p"]["value"].rsplit("/", 1)[-1]
                suri = r["s"]["value"]
                rows.append((r["sLabel"]["value"], pred, r["aLabel"]["value"], suri))
                next_frontier.add(suri)
            frontier = list(next_frontier)

        return self._cap(rows), queries

    def _cap(
        self, rows: list[tuple[str, str, str, str | None]]
    ) -> list[tuple[str, str, str, str | None]]:
        """Apply per-predicate and total caps deterministically (sorted by display text)."""
        per_pred: dict[str, int] = defaultdict(int)
        kept: list[tuple[str, str, str, str | None]] = []
        for t in sorted(set(rows), key=lambda x: (x[0], x[1], x[2])):
            if len(kept) >= self.max_triples:
                break
            if per_pred[t[1]] >= self.max_per_predicate:
                continue
            per_pred[t[1]] += 1
            kept.append(t)
        return kept

    # --- the contract ------------------------------------------------------
    def retrieve(self, query: str) -> RetrievalResult:
        with stopwatch() as sw:
            anchors = self._link(query)
            if not anchors:
                # Honest miss (e.g. type-10 fuzzy names no entity): no graph context.
                return build_result(
                    context="",
                    sources=[],
                    latency_ms=sw.ms,
                    traversal_info={
                        "mechanism": "neighborhood",
                        "hops": self.hops,
                        "linked_entities": {},
                        "num_linked": 0,
                        "num_triples": 0,
                        "endpoint": self.endpoint,
                    },
                )
            kept, queries = self._neighborhood([u for u, _ in anchors])
            context = "\n".join(f"{s} {p} {o}" for s, p, o, _ in kept)
            # Provenance reflects what's actually in the served context: the linked
            # anchors plus the neighbor URIs of the *kept* (post-cap) triples.
            sources = sorted({u for u, _ in anchors} | {t[3] for t in kept if t[3]})

        return build_result(
            context=context,
            sources=sources,
            latency_ms=sw.ms,
            traversal_info={
                "mechanism": "neighborhood",
                "hops": self.hops,
                "max_per_predicate": self.max_per_predicate,
                "max_triples": self.max_triples,
                "linked_entities": {label: uri for uri, label in anchors},
                "num_linked": len(anchors),
                "num_triples": len(kept),
                "sparql": queries,
                "endpoint": self.endpoint,
            },
        )
