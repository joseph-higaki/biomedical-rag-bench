#!/usr/bin/env python3
"""Hetionet v1.0 JSON -> RDF-star Turtle. Streaming and low-memory.

The source decompresses to ~712 MB; the dev box has ~7 GB RAM. So we never call
json.load() and never build an in-memory rdflib.Graph. Input is parsed
incrementally with ijson; Turtle is written statement-by-statement. See
ingest/rdf/hetionet-data-notes.md for the source structure and the URI mapping, and
the README "Ingestion is streaming, not in-memory" decision for the rationale.

Validate generated Turtle by round-tripping the smoke slice through pyoxigraph
(see --validate); if it re-parses, the hand-written Turtle-star is sound. (rdflib
7.6 has no RDF-star support, so it cannot parse the edge annotations.)
"""
from __future__ import annotations

import argparse
import bz2
import re
import sys
from decimal import Decimal
from pathlib import Path

import ijson

# --- Namespaces ------------------------------------------------------------
# Entities use stable external vocabularies; schema lives under hetio:.
PREFIXES: dict[str, str] = {
    "db": "https://identifiers.org/drugbank/",
    "do": "http://purl.obolibrary.org/obo/DOID_",
    "ncbigene": "https://identifiers.org/ncbigene/",
    "uberon": "http://purl.obolibrary.org/obo/UBERON_",
    "go": "http://purl.obolibrary.org/obo/GO_",
    "umls": "https://identifiers.org/umls/",
    "mesh": "https://identifiers.org/mesh/",
    "ndfrt": "https://identifiers.org/ndfrt/",
    "pathway": "https://het.io/pathway/",  # project-minted: no clean vocab for PC7_*
    "hetio": "https://het.io/schema/",
    "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "xsd": "http://www.w3.org/2001/XMLSchema#",
}

# node kind -> (prefix, strip_colon_prefix). When True, "DOID:14227" -> "14227"
# because the namespace IRI already encodes the "DOID_" stem (OBO style).
NODE_KIND: dict[str, tuple[str, bool]] = {
    "Compound": ("db", False),
    "Disease": ("do", True),
    "Gene": ("ncbigene", False),
    "Anatomy": ("uberon", True),
    "Biological Process": ("go", True),
    "Cellular Component": ("go", True),
    "Molecular Function": ("go", True),
    "Side Effect": ("umls", False),
    "Symptom": ("mesh", False),
    "Pharmacologic Class": ("ndfrt", False),
    "Pathway": ("pathway", False),
}

# PN_LOCAL local parts that match this are emitted as readable prefixed names;
# anything else falls back to a full <IRI>. Hetionet ids are clean, but this
# keeps the serializer correct if that ever stops being true.
_PN_LOCAL_SAFE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.\-]*$")


def _class_name(kind: str) -> str:
    """'Biological Process' -> 'BiologicalProcess' (a hetio: class local name)."""
    return kind.replace(" ", "")


def node_term(kind: str, identifier) -> str:
    """[kind, identifier] -> a Turtle term ('db:DB00201' or '<...>')."""
    prefix, strip = NODE_KIND[kind]
    local = str(identifier)
    if strip and ":" in local:
        local = local.split(":", 1)[1]
    if _PN_LOCAL_SAFE.match(local):
        return f"{prefix}:{local}"
    return f"<{PREFIXES[prefix]}{local}>"


def _esc(s: str) -> str:
    """Escape a string for a Turtle double-quoted literal."""
    return (
        s.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def literal(value) -> str:
    """Python value -> Turtle literal. Order matters: bool is a subclass of int
    in Python, so it must be checked first or True would serialize as 1."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, (float, Decimal)):
        # xsd:double is unambiguous for z_score / fold-change / affinity values.
        return f'"{value}"^^xsd:double'
    return '"' + _esc(str(value)) + '"'


def stream_nodes(src: Path):
    opener = bz2.open if src.suffix == ".bz2" else open
    with opener(src, "rb") as f:
        yield from ijson.items(f, "nodes.item")


def stream_edges(src: Path):
    opener = bz2.open if src.suffix == ".bz2" else open
    with opener(src, "rb") as f:
        yield from ijson.items(f, "edges.item")


def edge_annotations(data: dict):
    """Yield (predicate_local, turtle_object) pairs for an edge's data dict.
    List-valued keys (sources, subtypes, pubmed_ids, ...) expand to one pair
    per element, faithful to the source."""
    for key, val in data.items():
        if isinstance(val, list):
            for item in val:
                yield key, literal(item)
        else:
            yield key, literal(val)


# Curated node data attributes carried into the graph as hetio:<key> literals.
# Deliberately a small, high-value subset: chromosome/description ground 0-hop
# attribute questions and aid LLM/semantic grounding; inchikey gives compounds a
# stable structural attribute. This is NOT the full node data dict — representing
# every node and edge property in RDF is a deferred to-do. Keyed by raw node kind.
NODE_DATA_KEYS: dict[str, tuple[str, ...]] = {
    "Gene": ("chromosome", "description"),
    "Compound": ("inchikey",),
}


def write_turtle(out: Path, src: Path, limit: int | None) -> tuple[int, int]:
    """Write the Turtle file. Returns (nodes_emitted, edges_emitted).

    With --limit N, restrict to the first N edges and only the nodes they touch,
    so the slice is connected and answers a real SPARQL query. This costs a
    second pass over the input (to learn which nodes are wanted before emitting
    them); the wanted-set is tiny, so memory stays bounded."""
    wanted: set[tuple[str, str]] | None = None
    if limit is not None:
        wanted = set()
        for i, e in enumerate(stream_edges(src)):
            if i >= limit:
                break
            for role in ("source_id", "target_id"):
                k, ident = e[role]
                wanted.add((k, str(ident)))

    nodes_emitted = edges_emitted = 0
    with out.open("w", encoding="utf-8") as w:
        for prefix, iri in PREFIXES.items():
            w.write(f"@prefix {prefix}: <{iri}> .\n")
        w.write("\n# --- Nodes (type + label + curated data attributes) ---\n")

        for node in stream_nodes(src):
            kind, ident = node["kind"], node["identifier"]
            if wanted is not None and (kind, str(ident)) not in wanted:
                continue
            term = node_term(kind, ident)
            clauses = [
                f"a hetio:{_class_name(kind)}",
                f"rdfs:label {literal(node['name'])}",
            ]
            data = node.get("data") or {}
            for key in NODE_DATA_KEYS.get(kind, ()):
                if data.get(key) not in (None, ""):
                    clauses.append(f"hetio:{key} {literal(data[key])}")
            w.write(f"{term} " + " ;\n    ".join(clauses) + " .\n")
            nodes_emitted += 1

        w.write("\n# --- Edges (base triple + RDF-star annotations) ---\n")
        for i, e in enumerate(stream_edges(src)):
            if limit is not None and i >= limit:
                break
            s = node_term(*e["source_id"])
            o = node_term(*e["target_id"])
            p = f"hetio:{e['kind']}"
            w.write(f"{s} {p} {o} .\n")

            anns = [("direction", f'"{e["direction"]}"')]
            anns += [(k, obj) for k, obj in edge_annotations(e.get("data") or {})]
            star = f"<< {s} {p} {o} >>"
            parts = " ;\n    ".join(f"hetio:{k} {obj}" for k, obj in anns)
            w.write(f"{star} {parts} .\n")
            edges_emitted += 1

    return nodes_emitted, edges_emitted


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=Path("data/hetionet/hetionet-v1.0.json.bz2"),
                    help="Hetionet JSON (.json or .json.bz2). Default: data/hetionet/hetionet-v1.0.json.bz2")
    ap.add_argument("--out", type=Path, required=True, help="Output Turtle file.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Smoke slice: keep only the first N EDGES and the nodes they touch (connected, queryable). Omit for the full graph.")
    ap.add_argument("--validate", action="store_true",
                    help="After writing, re-parse the output with rdflib to confirm the Turtle is well-formed. Use on the smoke slice (loads the file into memory).")
    args = ap.parse_args()

    if not args.source.exists():
        print(f"error: source not found: {args.source}", file=sys.stderr)
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)

    nodes, edges = write_turtle(args.out, args.source, args.limit)
    scope = f"smoke slice (first {args.limit} edges)" if args.limit else "full graph"
    print(f"wrote {args.out}: {nodes} nodes, {edges} edges  [{scope}]", file=sys.stderr)

    if args.validate:
        import pyoxigraph as ox
        store = ox.Store()
        store.load(path=str(args.out), format=ox.RdfFormat.TURTLE)  # raises on malformed Turtle-star
        print(f"validate: pyoxigraph re-parsed {len(store)} triples cleanly (RDF-star aware)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
