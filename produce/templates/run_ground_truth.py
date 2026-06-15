#!/usr/bin/env python3
"""Run a template's ground-truth .rq against GraphDB and print the rows.

Step-2 isolated validation: confirms a hand-authored ground-truth query returns
the answer we expect, before the step-3 producer relies on it. The query result
here is throwaway validation — it is NOT the ground truth stored in
questions.jsonl. The producer (step 3) runs the same query, with the VALUES line
rewritten per sampled entity, and records *that* result as ground truth. See
eval/README.md for the production/harness/judging split.

One engine: GraphDB. Decision B made the full Hetionet graph in GraphDB canonical
for ground truth, and only GraphDB can serve that role here — the full graph
(712 MB) does not fit pyoxigraph's in-memory store, and a slice that does fit can't
carry multi-hop ground truth (its neighborhoods are disjoint). Validating queries
on a different engine than the one that produces ground truth would also risk
dialect divergence (Oxigraph and GraphDB already disagree on RDF-star quoted-triple
handling — see ingest/rdf/hetionet-data-notes.md). `run_query` is the single
execution seam the registry generator and the step-3 producer share. Endpoint
defaults to the local container; override with GRAPHDB_ENDPOINT.

Usage:
    uv run --extra graph python produce/templates/run_ground_truth.py \\
        --query produce/templates/ground_truth/genes_expressed_in_anatomy.rq
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

# The local GraphDB container holding the full Hetionet graph. Override for a
# remote endpoint (e.g. the EC2 milestone) without touching code.
DEFAULT_GRAPHDB_ENDPOINT = os.environ.get(
    "GRAPHDB_ENDPOINT", "http://localhost:7200/repositories/hetionet"
)


def run_query(query_text: str, *, endpoint: str | None = None) -> list[dict[str, str]]:
    """Execute a SPARQL SELECT against GraphDB; return rows as {variable -> value}.

    This is the reusable query-execution seam shared by build_registry.py and the
    step-3 producer. URIs and labels alike come back as plain lexical strings, so
    callers compare on value. httpx is imported lazily so importing this module
    doesn't require the `graph` extra unless a query is actually run.
    """
    import httpx

    resp = httpx.post(
        endpoint or DEFAULT_GRAPHDB_ENDPOINT,
        data={"query": query_text},
        headers={"Accept": "application/sparql-results+json"},
        timeout=120.0,
    )
    resp.raise_for_status()
    payload = resp.json()

    # ASK queries (path-existence type) return {"boolean": true/false}, not a result
    # set. Surface it as a single synthetic row so callers treat it like any scalar.
    if "boolean" in payload:
        return [{"boolean": str(payload["boolean"]).lower()}]

    variables = payload["head"]["vars"]
    return [
        {var: binding[var]["value"] for var in variables if var in binding}
        for binding in payload["results"]["bindings"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", type=Path, required=True, help="SPARQL SELECT (.rq) to run")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_GRAPHDB_ENDPOINT,
        help=f"GraphDB SPARQL endpoint (default {DEFAULT_GRAPHDB_ENDPOINT})",
    )
    args = parser.parse_args()

    rows = run_query(args.query.read_text(), endpoint=args.endpoint)

    print(f"{len(rows)} row(s) from {args.query.name} against {args.endpoint}:")
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
