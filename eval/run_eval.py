#!/usr/bin/env python3
"""eval/run_eval.py — retriever registry (build step 4) + eval harness (step 5).

Today this file carries the **retriever registry**: the single place that maps a
retriever's `name` to its constructor. The contract in .claude/CLAUDE.md — "adding a
retriever is one file in `retrievers/` plus a registration here, nothing else changes"
— is enforced by this dict. Anything that needs to enumerate retrievers iterates
`REGISTRY`; nothing else hard-codes the roster.

The **full harness is build step 5** and grows around this registry: load
`questions.jsonl`, run each registered retriever + the fixed generator against each
question, score with the pluggable judges, and write per-row telemetry plus a per-run
manifest (the factorial-provenance record). That loop depends on the generator/judge
layer, which does not exist yet, so it is left as the explicit TODO in `main()` rather
than a stub that fakes a generator and produces meaningless numbers.

Until then the CLI exercises the registry directly — the step-4 isolated smoke for the
swap point:

    uv run python eval/run_eval.py --list
    uv run --extra vector python eval/run_eval.py --retriever vector --retrieve "..."
    uv run --extra graph  python eval/run_eval.py --retriever graph_neighborhood --retrieve "..."

(closed_book needs no extra; vector needs `--extra vector`; graph needs `--extra graph`.)

Run path-based from the repo root (see README); the sys.path insert below puts the
repo root on the path so `retrievers.*` imports resolve, mirroring produce.py.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from retrievers.base import Retriever  # noqa: E402
from retrievers.graph import NeighborhoodGraphRetriever  # noqa: E402
from retrievers.null import NullRetriever  # noqa: E402
from retrievers.vector import VectorRetriever  # noqa: E402

# The registry: retriever `name` -> zero-arg constructor. Keyed off each class's own
# `name` attribute so the registry key and the RetrievalResult's reported name cannot
# drift. Importing the modules is cheap — their heavy deps (httpx, chromadb,
# sentence-transformers) are imported lazily inside `retrieve`, so the registry loads
# with no extra installed and `--list` runs anywhere. `graph_sparqlgen` joins once the
# LLM-in-retriever layer exists (step 5+).
REGISTRY: dict[str, Callable[[], Retriever]] = {
    NullRetriever.name: NullRetriever,
    VectorRetriever.name: VectorRetriever,
    NeighborhoodGraphRetriever.name: NeighborhoodGraphRetriever,
}


def build_retriever(name: str) -> Retriever:
    """Instantiate the registered retriever `name`, or fail with the known roster."""
    try:
        return REGISTRY[name]()
    except KeyError:
        raise SystemExit(
            f"unknown retriever {name!r}; registered: {', '.join(REGISTRY)}"
        )


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--list", action="store_true", help="Print the registered retriever names and exit."
    )
    ap.add_argument(
        "--retriever",
        default="closed_book",
        choices=list(REGISTRY),
        help="Which registered retriever to run for --retrieve (default: closed_book).",
    )
    ap.add_argument(
        "--retrieve",
        metavar="QUESTION",
        help="Run one retrieval for QUESTION and print the RetrievalResult as JSON (registry smoke).",
    )
    ap.add_argument(
        "--generator",
        metavar="MODEL_ID",
        help="(build step 5) Generator model id for the full eval loop — not implemented yet.",
    )
    args = ap.parse_args()

    if args.generator:
        # The generator + judge + manifest loop is build step 5; refuse rather than
        # fabricate. See the module docstring.
        print(
            "error: the generator/judge eval loop is build step 5 and is not implemented yet.\n"
            "       For now use --list or --retrieve to exercise the retriever registry.",
            file=sys.stderr,
        )
        return 2

    if args.list or not args.retrieve:
        for name in REGISTRY:
            print(name)
        return 0

    retriever = build_retriever(args.retriever)
    res = retriever.retrieve(args.retrieve)
    print(
        json.dumps(
            {
                "retriever": retriever.name,
                "context_tokens": res.context_tokens,
                "latency_ms": round(res.latency_ms, 1),
                "num_sources": len(res.sources),
                "sources": res.sources,
                "traversal_info": res.traversal_info,
                "context": res.context,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
