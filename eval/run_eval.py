#!/usr/bin/env python3
"""eval/run_eval.py — the swap-point registries (retrievers, generators) + eval harness.

This file is the single place the benchmark's conditions are wired: the **retriever
registry** (`REGISTRY`, build step 4) and the **generator registry** (`GENERATORS`,
build step 5). The contract in .claude/CLAUDE.md — "adding a retriever is one file plus
a registration here, nothing else changes" — holds for generators too. Anything that
enumerates a condition iterates the registry; nothing else hard-codes the roster. Both
stay provider-agnostic: a retriever or generator names itself, and the generator's
provider SDK lives only in its adapter (see eval/generate/base.py).

The eval loop that consumes these registries lives in `eval/harness.py`: it loads
`questions.jsonl`, runs each registered retriever + the fixed generator against each
question, scores with the pluggable judges (eval/judge/), and writes per-row telemetry
plus a per-run manifest (the factorial-provenance record). This module wires the
registries and drives that loop from the CLI — `--run` for the full loop, the other
flags to exercise a single registry in isolation:

    uv run python eval/run_eval.py --list
    uv run --extra vector python eval/run_eval.py --retriever vector --retrieve "..."
    uv run --extra graph  python eval/run_eval.py --retriever graph_neighborhood_1hop --retrieve "..."
    uv run --extra generate python eval/run_eval.py --ask "..." --generator_model_family anthropic:claude-haiku-4-5
    uv run --extra generate python eval/run_eval.py --run --retriever closed_book \
        --generator_model_family anthropic:claude-haiku-4-5 \
        --judge_model_family anthropic:claude-haiku-4-5 --types 10   # type-10, LLM-judged

(closed_book needs no extra; vector → `--extra vector`; graph → `--extra graph`;
--ask/--run → `--extra generate` + a provider key in secrets/.env. `graph_sparqlgen` and a
semantic `--run` each call an LLM, so they need `--extra generate` too — combine extras,
e.g. `--extra generate --extra graph` for graph_sparqlgen.)

Run path-based from the repo root (see README); the sys.path insert below puts the
repo root on the path so `retrievers.*` imports resolve, mirroring produce.py.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from eval import harness  # noqa: E402
from eval.generate.registry import GENERATORS, from_spec  # noqa: E402,F401  (GENERATORS re-exported)
from eval.generate.base import Generator  # noqa: E402
from eval.judge.base import Judge  # noqa: E402
from eval.judge.deterministic import DETERMINISTIC_JUDGES  # noqa: E402
from eval.judge.semantic import SEMANTIC_PROMPT, SemanticJudge  # noqa: E402
from retrievers.base import Retriever  # noqa: E402
from retrievers.graph import NeighborhoodGraphRetriever  # noqa: E402
from retrievers.null import NullRetriever  # noqa: E402
from retrievers.sparqlgen import WRITER_PROMPT, SparqlGenRetriever  # noqa: E402
from retrievers.vector import VectorRetriever  # noqa: E402

CORPUS_DIR = REPO_ROOT / "ingest" / "corpus"  # committed corpus-build profiles (ingest/corpus/README.md)


def _active_corpus_build_id() -> str | None:
    """The corpus_build_id to stamp into the run manifest — the run-constant *corpus* factor.

    Resolution: $CORPUS_BUILD_ID, else the committed ingest/corpus/ACTIVE pointer. A declared id
    must name an existing ingest/corpus/<id>.json, so a typo or an unbuilt corpus fails fast rather
    than recording an unverifiable reference. Undeclared resolves to None with a warning: the run
    still proceeds (legacy-compatible, additive) but isn't corpus-attributable. The pointer is a
    *declaration* — keep it consistent with the GraphDB repo / CHROMA_STORE the run actually
    queries (the same operator contract as GENERATOR_MODEL); it is not auto-detected."""
    active = os.environ.get("CORPUS_BUILD_ID") or None
    if active is None:
        pointer = CORPUS_DIR / "ACTIVE"
        active = pointer.read_text().strip() if pointer.exists() else None
    if active is None:
        print("  warning: no corpus declared (set CORPUS_BUILD_ID or write ingest/corpus/ACTIVE); "
              "manifest corpus_build_id will be null", file=sys.stderr)
        return None
    if not (CORPUS_DIR / f"{active}.json").exists():
        raise SystemExit(f"corpus_build_id '{active}' has no profile at ingest/corpus/{active}.json "
                         f"— run ingest/corpus_profile.py or fix CORPUS_BUILD_ID / ingest/corpus/ACTIVE")
    return active


# The registry: retriever `name` -> zero-arg constructor. The key must equal the
# constructed retriever's reported `name` so the registry key and the RetrievalResult's
# reported name cannot drift (pinned by tests/test_registry.py). For the parameter-free
# retrievers the key is just the class's `name`; for the graph condition each hop budget
# is its own named entry — embedding the budget in the name keeps it a single condition
# key (no extra manifest factor) and auto-namespaces its result files via run_id. The hop
# value is also in traversal_info, so this is a grouping label, not the source of truth.
# Importing the modules is cheap — heavy deps (httpx, chromadb, sentence-transformers) are
# lazy inside `retrieve`, so the registry loads with no extra installed and `--list` runs
# anywhere. `graph_sparqlgen` is the LLM-in-retriever text-to-SPARQL condition; its writer
# LLM is lazy too, so it also constructs with no key (the registry no-drift test relies on that).
def _graph(hops: int) -> Callable[[], Retriever]:
    """Bind a hop budget into a zero-arg constructor; the instance names itself
    graph_neighborhood_<hops>hop, so the registry key and reported name stay in lockstep."""
    return lambda: NeighborhoodGraphRetriever(hops=hops)


REGISTRY: dict[str, Callable[[], Retriever]] = {
    NullRetriever.name: NullRetriever,
    VectorRetriever.name: VectorRetriever,
    "graph_neighborhood_1hop": _graph(1),
    "graph_neighborhood_2hop": _graph(2),
    SparqlGenRetriever.name: SparqlGenRetriever,
}


def build_retriever(name: str, *, writer_model: str | None = None) -> Retriever:
    """Instantiate the registered retriever `name`, or fail with the known roster.

    `writer_model` is forwarded only to graph_sparqlgen — the sole LLM-in-retriever condition,
    whose SPARQL writer is a run knob (--writer_model_family). Every other retriever is built
    zero-arg through the registry, preserving the no-drift contract (tests/test_registry.py).
    None ⇒ the retriever's own env/blank fallback (a blank writer fails when sparqlgen runs)."""
    try:
        ctor = REGISTRY[name]
    except KeyError:
        raise SystemExit(
            f"unknown retriever {name!r}; registered: {', '.join(REGISTRY)}"
        )
    if name == SparqlGenRetriever.name:
        return SparqlGenRetriever(writer_model=writer_model)
    return ctor()


# The generator registry + factory now live in eval/generate/registry.py — the single
# construction point shared by the generator-under-test (here), the graph_sparqlgen writer,
# and the semantic judge, so any of them can name a non-Anthropic provider. Re-exported for
# back-compat (callers that did `from eval.run_eval import GENERATORS`).


# The judge map is built per-run in main(): the five deterministic judges are hermetic (no LLM)
# and always present; `semantic` (type 10) is the one LLM judge, added only when a semantic
# question is actually in the batch, and only then needing --judge_model_family. Building it
# per-run (not as a module constant) is what lets the judge model be a CLI knob — see build_judges.
def build_judges(needs_semantic: bool, *, judge_model: str | None) -> dict[str, Judge]:
    """The harness's judge map. Deterministic-only by default; the LLM SemanticJudge is added
    (with the run's judge model) iff a semantic question is in the batch. The judge's LLM is
    lazy, so a deterministic-only run never touches `judge_model` and may leave it blank."""
    if not needs_semantic:
        return DETERMINISTIC_JUDGES
    return {**DETERMINISTIC_JUDGES, SemanticJudge.scoring: SemanticJudge(model=judge_model)}

# The per-role prompt registry stamped into every run's manifest: a complete snapshot of the
# system prompts live in this code, keyed by role. Recorded in full regardless of which roles a
# given run exercised (a closed_book run still records the writer/judge prompts of this build);
# the rows tell you which roles actually fired via `retriever` and `judge_id`. Run-constant, so
# it lives once in the manifest, never per row — analytics joins a row to its role's prompt text
# by run_id. This is the composition root, the one place that imports all three roles' prompts.
PROMPT_REGISTRY = {
    "generator": harness.GENERATOR_PROMPT,
    "writer": WRITER_PROMPT,
    "judge_semantic": SEMANTIC_PROMPT,
}


# Reproducible by default: the model under test runs at temperature 0 (greedy/modal) so a
# re-run reproduces a run rather than re-sampling it — the determinism rule (eval/README.md)
# and the cure for the run-to-run jitter the temperature factoid exposed. Override via env to
# study temperature as a factor (it is logged per result). NB: temp 0 is low-variance, not
# bit-identical — floating-point/batching on hosted models can still flip an occasional token.
GENERATOR_TEMPERATURE = float(os.environ.get("GENERATOR_TEMPERATURE", "0.0"))


# TODO(knobs): the three MODEL knobs are now CLI args (--generator_model_family /
# --writer_model_family / --judge_model_family), so a run names its models on the command line
# rather than via scattered env vars. Still env-only — the remaining consolidation work, tracked
# in _troubleshoot-eval/troubleshoot.md:
#   - GENERATOR_TEMPERATURE / SPARQLGEN_TEMPERATURE   (sampling temps — here + retrievers/sparqlgen.py)
#   - GRAPHDB_ENDPOINT                                (retrievers/graph.py, retrievers/sparqlgen.py)
#   - CHROMA_STORE                                    (retrievers/vector.py)
#   - CORPUS_BUILD_ID                                 (ingest/corpus/ACTIVE)
# Fold these into one RunConfig the harness threads down to the retriever/generator constructors,
# keeping env vars only as fallback. Each is already logged in the manifest — this changes where a
# knob is *set*, not where it's *recorded*, so the provenance contract is unaffected.
def build_generator(spec: str) -> Generator:
    """Build the generator-under-test from a 'provider:model' spec, e.g.
    'anthropic:claude-haiku-4-5'. Temperature is pinned to GENERATOR_TEMPERATURE (0.0 default)
    — the run-constant sampling setting, logged with every result and in the manifest. No
    default provider: the model under test must be named explicitly so a run is attributable."""
    return from_spec(spec, temperature=GENERATOR_TEMPERATURE)


def _print_verdicts(rows: list[dict], manifest: harness.RunManifest, rows_path: Path) -> None:
    """Human-readable verdict table + a pass count and per-type breakdown (no real stats —
    definitive metrics are the analysis layer's job; this is the run's eyeball check)."""
    print(f"\nrun {manifest.run_id}  ({manifest.retriever} → "
          f"{manifest.generator_provider}:{manifest.generator_model})\n")
    per_type: dict[str, list[bool]] = {}
    in_tok = out_tok = 0
    for r in rows:
        in_tok += r["input_tokens"]
        out_tok += r["output_tokens"]
        if not r.get("judged"):  # error / unjudged row — shown, but not a verdict
            mark = "ERR " if "error" in r else "—   "
            print(f"  [{mark}] {r['type_id']:<26} {r['verdict']}")
            continue
        mark = "PASS" if r["passed"] else "FAIL"
        per_type.setdefault(r["type_id"], []).append(bool(r["passed"]))
        pred = (r["predicted"] or "").replace("\n", " / ")
        pred = pred[:64] + "…" if len(pred) > 64 else pred
        print(f"  [{mark}] {r['type_id']:<26} {r['verdict']}")
        print(f"         predicted: {pred!r}")

    judged = [r for r in rows if r.get("judged")]
    errors = [r for r in rows if "error" in r]
    npass = sum(1 for r in judged if r["passed"])
    err_note = f"   ·   {len(errors)} errored (excluded)" if errors else ""
    print(f"\n  {npass}/{len(judged)} passed   ·   billed tokens: {in_tok} in / {out_tok} out{err_note}")
    print("  by type:")
    for t in sorted(per_type):
        p = per_type[t]
        print(f"    {t:<28} {sum(p)}/{len(p)}")
    print(f"\n  rows:     {rows_path}")
    print(f"  manifest: {rows_path.with_suffix('.manifest.json')}\n")


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
        "generator-registry smoke. Requires --generator_model_family.",
    )
    ap.add_argument(
        "--generator_model_family",
        metavar="PROVIDER:MODEL",
        help="Generator-under-test spec for --ask / --run, e.g. 'anthropic:claude-haiku-4-5' "
        "or 'ollama:qwen2.5:3b-instruct'. Explicit provider required (no default) so a run is "
        "attributable. Required for --run / --ask.",
    )
    ap.add_argument(
        "--writer_model_family",
        metavar="PROVIDER:MODEL",
        help="SPARQL-writer spec for the graph_sparqlgen retriever (e.g. 'ollama:qwen2.5-coder'; "
        "a bare model ⇒ anthropic). No default — graph_sparqlgen aborts if unset when it runs. "
        "Falls back to $SPARQLGEN_MODEL.",
    )
    ap.add_argument(
        "--judge_model_family",
        metavar="PROVIDER:MODEL",
        help="Semantic-judge spec for type-10 questions (a bare model ⇒ anthropic). No default — "
        "a run with semantic questions aborts if unset. Falls back to $JUDGE_MODEL.",
    )
    ap.add_argument(
        "--run",
        action="store_true",
        help="Run the eval loop (retrieve→generate→judge) over a sample; write results + manifest.",
    )
    ap.add_argument(
        "--limit", type=int, default=8,
        help="Max questions for --run, round-robin across types (default 8).",
    )
    ap.add_argument(
        "--include-semantic", action="store_true",
        help="Include type-10 semantic questions, scored by the LLM SemanticJudge "
        "(costs spend + needs an API key; excluded by default).",
    )
    ap.add_argument(
        "--types", metavar="PREFIXES",
        help="Comma-separated type_id prefixes to run in isolation, e.g. '10' or '03,06'. "
        "Naming a type selects it explicitly (a named semantic type is included).",
    )
    ap.add_argument(
        "--questions", type=Path, default=REPO_ROOT / "produce" / "questions.jsonl",
        help="Question set for --run.",
    )
    ap.add_argument(
        "--out", type=Path, default=REPO_ROOT / "eval" / "results",
        help="Directory for --run JSONL rows + manifest (gitignored, machine-readable).",
    )
    ap.add_argument(
        "--report", type=Path, default=REPO_ROOT / "eval" / "LATEST_RUN.md",
        help="Generated markdown snapshot for --run (overwritten every run; default "
        "eval/LATEST_RUN.md). Curated cross-run observations live in analysis/FINDINGS.md.",
    )
    args = ap.parse_args()

    if args.run:
        if not args.generator_model_family:
            raise SystemExit("--run requires --generator_model_family PROVIDER:MODEL")
        rows_in = [json.loads(ln) for ln in args.questions.read_text().splitlines() if ln.strip()]
        type_prefixes = [t.strip() for t in args.types.split(",")] if args.types else None
        selected = harness.select_questions(
            rows_in, args.limit, include_semantic=args.include_semantic, types=type_prefixes
        )
        if not selected:
            raise SystemExit(f"no questions selected from {args.questions}")
        # Carry the LLM judge iff a semantic question is actually in the batch (robust to both
        # --include-semantic and an explicit --types 10); deterministic-only stays hermetic-judged.
        needs_semantic = any(q.get("scoring") == "semantic" for q in selected)
        # Fail fast, before any billed call, for a supporting-cast model that WILL fire this run.
        # The writer (graph_sparqlgen) and judge (semantic) also self-guard in _ensure_llm; this
        # just moves the failure ahead of the run loop, mirroring the generator + corpus pre-flight
        # — a blank required model should never get as far as spending on row 1. Env is the fallback.
        if args.retriever == SparqlGenRetriever.name and not (
            args.writer_model_family or os.environ.get("SPARQLGEN_MODEL")
        ):
            raise SystemExit(
                "retriever graph_sparqlgen needs a SPARQL writer — set --writer_model_family "
                "PROVIDER:MODEL (or $SPARQLGEN_MODEL)."
            )
        if needs_semantic and not (args.judge_model_family or os.environ.get("JUDGE_MODEL")):
            raise SystemExit(
                "this run includes semantic (type-10) questions — set --judge_model_family "
                "PROVIDER:MODEL (or $JUDGE_MODEL)."
            )
        retriever = build_retriever(args.retriever, writer_model=args.writer_model_family)
        generator = build_generator(args.generator_model_family)
        # Resolve the corpus factor up front: a bad pointer fails before the (billed) run loop.
        corpus_build_id = _active_corpus_build_id()
        judges = build_judges(needs_semantic, judge_model=args.judge_model_family)
        judge_label = "deterministic-v1+semantic-v1" if needs_semantic else "deterministic-v1"

        # Stream rows to disk as they land: the run_id (hence the file path) is fixed
        # before the loop, and each row is written + flushed on arrival, so a mid-run
        # crash leaves every completed row on disk rather than discarding the batch.
        run_id = f"{time.strftime('%Y%m%dT%H%M%S')}-{retriever.name}-{generator.provider}"
        args.out.mkdir(parents=True, exist_ok=True)
        rows_path = args.out / f"{run_id}.jsonl"
        rows: list[dict] = []
        with rows_path.open("w") as fh:
            for row in harness.iter_rows(retriever, generator, judges, selected):
                fh.write(json.dumps(row) + "\n")
                fh.flush()
                rows.append(row)

        # The exact snapshot the provider resolved the (possibly-alias) model to — taken from
        # the first successful row, so the manifest pins it at the run level too.
        resolved = next((r["generator_model_resolved"] for r in rows
                         if r.get("generator_model_resolved")), None)
        manifest = harness.make_manifest(
            retriever, generator, selected, run_id=run_id,
            questions_path=str(args.questions), judge=judge_label,
            generator_model_resolved=resolved, corpus_build_id=corpus_build_id,
            prompts=PROMPT_REGISTRY,
        )
        (args.out / f"{run_id}.manifest.json").write_text(
            json.dumps(manifest.to_dict(), indent=2)
        )
        # Generated markdown snapshot (overwritten each run; curated notes live in FINDINGS.md).
        args.report.write_text(harness.to_markdown(rows, manifest))
        _print_verdicts(rows, manifest, rows_path)
        print(f"  report:   {args.report}\n")
        return 0

    if args.ask:
        if not args.generator_model_family:
            raise SystemExit("--ask requires --generator_model_family PROVIDER:MODEL")
        gen = build_generator(args.generator_model_family)
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
