#!/usr/bin/env python3
"""Run a template's ground-truth .rq against a Turtle graph and print the rows.

Step-2 isolated smoke: validates that a hand-authored ground-truth query returns
the answer we expect, against the smoke slice, before the step-3 producer relies
on it. The query result here is throwaway validation — it is NOT the ground truth
stored in questions.jsonl. The producer (step 3) runs the same query, with the
VALUES line rewritten per sampled entity, and records *that* result as ground
truth. See eval/README.md for the production/harness/judging split.

Engine note: this runs against pyoxigraph (in-memory, hermetic, no GraphDB
container or license needed) because the smoke slice is tiny and the check should
be independent. The full-scale producer queries GraphDB instead — same SPARQL,
different engine. `run_query` is the seam those two share: step 3 lifts it behind
an engine interface (pyoxigraph for slices, GraphDB for the full graph) without
the caller knowing which is running.

Usage:
    uv run --extra ingest python eval/templates/run_ground_truth.py \\
        --graph ontology/hetionet-smoke.ttl \\
        --query eval/templates/ground_truth/genes_expressed_in_anatomy.rq
"""
from __future__ import annotations

import argparse
from pathlib import Path

import pyoxigraph as ox


def run_query(graph_path: Path, query_path: Path) -> list[dict[str, str]]:
    """Load a Turtle graph into an in-memory store, run a SELECT, return rows.

    This is the reusable query-execution seam. Each row maps SELECT variable name
    -> term lexical value (URIs and labels alike come back as plain strings).
    """
    store = ox.Store()
    store.load(path=str(graph_path), format=ox.RdfFormat.TURTLE)

    solutions = store.query(query_path.read_text())
    variables = [v.value for v in solutions.variables]
    return [
        {var: row[var].value for var in variables if row[var] is not None}
        for row in solutions
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph", type=Path, required=True, help="Turtle graph to load")
    parser.add_argument("--query", type=Path, required=True, help="SPARQL SELECT (.rq) to run")
    args = parser.parse_args()

    rows = run_query(args.graph, args.query)

    print(f"{len(rows)} row(s) from {args.query.name} against {args.graph.name}:")
    for row in rows:
        print(f"  {row}")


if __name__ == "__main__":
    main()
