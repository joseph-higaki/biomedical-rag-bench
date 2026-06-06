#!/usr/bin/env python3
"""eval/run_eval.py — the swap-point registries (retrievers, generators) + eval harness.

This file is the single place the benchmark's conditions are wired: the **retriever
registry** (`REGISTRY`, build step 4) and the **generator registry** (`GENERATORS`,
build step 5). The contract in .claude/CLAUDE.md — "adding a retriever is one file plus
a registration here, nothing else changes" — holds for generators too. Anything that
enumerates a condition iterates the registry; nothing else hard-codes the roster. Both
stay provider-agnostic: a retriever or generator names itself, and the generator's
provider SDK lives only in its adapter (see eval/generate/base.py).

The **remaining step-5 work** grows around these registries: load `questions.jsonl`, run
each registered retriever + the fixed generator against each question, score with the
pluggable judges (eval/judge/), and write per-row telemetry plus a per-run manifest (the
factorial-provenance record). That loop is the next increment — left as the explicit
TODO in `main()` rather than a stub that fabricates numbers.

Until then the CLI exercises each registry in isolation (the per-increment smoke):

    uv run python eval/run_eval.py --list
    uv run --extra vector python eval/run_eval.py --retriever vector --retrieve "..."
    uv run --extra graph  python eval/run_eval.py --retriever graph_neighborhood --retrieve "..."
    uv run --extra generate python eval/run_eval.py --ask "..." --generator anthropic:claude-haiku-4-5

(closed_book needs no extra; vector → `--extra vector`; graph → `--extra graph`;
--ask → `--extra generate` + a provider key in secrets/.env.)

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

from eval.generate.anthropic_generator import AnthropicGenerator  # noqa: E402
from eval.generate.base import Generator  # noqa: E402
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


# The generator registry: provider name -> adapter constructor (the Strategy pattern;
# see eval/generate/base.py). The harness names a generator as "provider:model" so the
# benchmark stays provider-agnostic — nothing here imports a provider SDK (the adapter
# does, lazily). New providers (ollama, openai) are one entry each.
GENERATORS: dict[str, Callable[..., Generator]] = {
    AnthropicGenerator.provider: AnthropicGenerator,
}


def build_generator(spec: str) -> Generator:
    """Build a generator from a 'provider:model' spec, e.g. 'anthropic:claude-haiku-4-5'."""
    provider, _, model = spec.partition(":")
    if not model:
        raise SystemExit(
            f"--generator must be 'provider:model' (e.g. anthropic:claude-haiku-4-5); got {spec!r}"
        )
    try:
        return GENERATORS[provider](model)
    except KeyError:
        raise SystemExit(
            f"unknown provider {provider!r}; registered: {', '.join(GENERATORS)}"
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
        "--ask",
        metavar="QUESTION",
        help="Generate one answer to QUESTION (no retrieval) and print it as JSON — the "
        "generator-registry smoke. Requires --generator.",
    )
    ap.add_argument(
        "--generator",
        metavar="PROVIDER:MODEL",
        help="Generator spec for --ask, e.g. 'anthropic:claude-haiku-4-5'.",
    )
    args = ap.parse_args()

    if args.ask:
        if not args.generator:
            raise SystemExit("--ask requires --generator PROVIDER:MODEL")
        gen = build_generator(args.generator)
        res = gen.generate(args.ask)
        print(
            json.dumps(
                {
                    "provider": res.provider,
                    "model": res.model,
                    "input_tokens": res.input_tokens,
                    "output_tokens": res.output_tokens,
                    "latency_ms": round(res.latency_ms, 1),
                    "finish_reason": res.finish_reason,
                    "tool_calls": res.tool_calls,
                    "text": res.text,
                },
                indent=2,
            )
        )
        return 0

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
