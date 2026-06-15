"""eval/harness.py — the eval loop: retrieve → generate → judge (build step 5).

The second eval concern (after production, before the analysis layer). It ties the three
swap points together for one question: retrieve context, build the prompt, generate an
answer with the model under test, score it with the judge for that question's `scoring`.
It is deliberately injected with *already-built* retriever / generator / judges (the
registries live in run_eval.py) so it imports no provider SDK and has no cycle with the
wiring layer — it depends only on the three protocols.

Comparability is the whole point, so two things are held constant across retriever
conditions and only the *context* varies:

  - **The system prompt** (`SYSTEM_PROMPT`) — identical for closed_book and every
    retriever. Its sha256 is recorded in the run manifest so a prompt change is a visible
    new factor level, not a silent confound.
  - **The prompt shape** — `Context:\n…\n\nQuestion: …`, with the Context block simply
    absent for closed_book. So closed_book's billed `input_tokens` is exactly the
    non-retrieval payload, the unit-safe subtrahend for "what did retrieval cost"
    (see retrievers/null.py and base.py on token units).

Definitive metrics (accuracy, recall curves, the H7 crossover) are computed in the
analysis layer — a notebook / dashboard that reads the per-row JSONL this writes. This
module only produces rows + a manifest and a human-readable verdict; it does no
aggregation beyond a pass count.
"""
from __future__ import annotations

import hashlib
import time
from collections.abc import Iterator, Mapping
from dataclasses import dataclass

from eval.generate.base import Generator
from eval.judge.base import Judge
from retrievers.base import Retriever

# Held constant across all retriever conditions (see module docstring). The format nudges
# steer answers into the shape the deterministic judges parse — a list per line, a bare
# number, a leading Yes/No, "None" for an empty answer — without telling the model the
# answer. Identical text for closed_book and every retriever; its hash goes in the manifest.
SYSTEM_PROMPT = (
    "You are answering biomedical questions in an automated evaluation. "
    "When Context is provided, answer using only that Context. When no Context is "
    "provided, answer from your own knowledge — do not reply that you lack context or "
    "cannot answer for that reason; give your best answer. "
    "Output only the answer itself: no headings, no preamble, no explanation, no "
    "commentary.\n"
    "Answer format:\n"
    "- If the answer is a list of entities, output each entity on its own line and nothing else.\n"
    "- If the answer is a count, output just the number.\n"
    "- If the answer is yes/no, start with \"Yes\" or \"No\".\n"
    "- If nothing satisfies the question, answer \"None\"."
)


def build_prompt(question: str, context: str) -> tuple[str, str]:
    """Return (system, user). The Context block is present iff the retriever returned one."""
    if context:
        user = f"Context:\n{context}\n\nQuestion: {question}"
    else:
        user = f"Question: {question}"
    return SYSTEM_PROMPT, user


def select_questions(
    rows: list[dict],
    limit: int,
    *,
    include_semantic: bool = False,
    types: list[str] | None = None,
) -> list[dict]:
    """Pick up to `limit` questions, round-robin across `type_id` for type coverage.

    `semantic` (type 10) is excluded by default — it needs the LLM judge, which costs spend
    and an API key — and included only when `include_semantic` is set or it is named in
    `types`. `types` is an optional list of `type_id` prefixes (e.g. ["10"] or
    ["03", "06"]); naming a type selects it explicitly, bypassing the semantic default-skip
    for that type. Round-robin across the surviving types means a small sample still spans
    them rather than clustering on a flat head-of-file slice. Deterministic given input order.
    """
    def keep(q: dict) -> bool:
        if types is not None:  # an explicit type request overrides the semantic default-skip
            return any(q["type_id"].startswith(t) for t in types)
        return include_semantic or q.get("scoring") != "semantic"

    by_type: dict[str, list[dict]] = {}
    for q in rows:
        if keep(q):
            by_type.setdefault(q["type_id"], []).append(q)

    selected: list[dict] = []
    types = sorted(by_type)
    while len(selected) < limit:
        progressed = False
        for t in types:
            if by_type[t]:
                selected.append(by_type[t].pop(0))
                progressed = True
                if len(selected) >= limit:
                    break
        if not progressed:  # all type buckets drained
            break
    return selected


def select_deterministic(rows: list[dict], limit: int) -> list[dict]:
    """Deterministic-only selection (excludes `semantic`). Thin wrapper kept as the named
    entry point for the deterministic eval path; `select_questions` is the general form."""
    return select_questions(rows, limit, include_semantic=False)


def run_question(
    retriever: Retriever,
    generator: Generator,
    judges: Mapping[str, Judge],
    question: dict,
) -> dict:
    """Run one question end-to-end and return a flat result row (one JSONL line).

    Each row carries every per-question factor (retriever, generator, scoring, billed
    tokens, latencies) plus the verdict, so the analysis layer can slice without joining.
    A question whose `scoring` has no registered judge (e.g. `semantic` before the LLM
    judge exists) is run through retrieve+generate but recorded `judged: false`.

    Robust by construction: a retrieve/generate failure (chiefly a transient generator
    API error) is caught and recorded as an `error` row with `judged: false, passed: null`,
    so it is excluded from every pass/fail denominator — a network blip is never scored as
    a wrong answer — and it never aborts the surrounding run.
    """
    row = {
        "question_id": question["question_id"],
        "type_id": question["type_id"],
        "scoring": question["scoring"],
        "question": question["question"],
        "ground_truth": question["ground_truth"],
        "retriever": retriever.name,
        "generator_provider": generator.provider,
        "generator_model": generator.model,
    }

    try:
        rr = retriever.retrieve(question["question"])
        system, user = build_prompt(question["question"], rr.context)
        gr = generator.generate(user, system=system)
    except Exception as e:  # transient API error, GraphDB hiccup, etc. — isolate, don't abort
        row |= {
            "predicted": None,
            # generate() never returned, so there is no resolved snapshot to attribute to.
            "generator_model_resolved": None,
            "generator_temperature": None,  # no generate() call happened
            "input_tokens": 0, "output_tokens": 0,
            "cache_read_input_tokens": None, "cache_creation_input_tokens": None,
            "context_tokens_proxy": None, "num_sources": 0,
            "retrieval_latency_ms": None, "generation_latency_ms": None,
            "traversal_info": {},
            "error": f"{type(e).__name__}: {e}"[:300],
            "judged": False, "passed": None, "score": None,
            "verdict": f"ERROR (not scored): {type(e).__name__}", "judge_details": {},
        }
        return row

    row |= {
        "predicted": gr.text,
        # The resolved snapshot the provider reports it actually ran (gr.model), distinct from
        # the requested/configured `generator_model` above (which may be a moving alias). Logged
        # per result so a verdict is always attributable to the exact model — base.py's contract.
        "generator_model_resolved": gr.model,
        # Sampling temperature actually requested for this generation (None = provider default /
        # unpinned). Logged beside the model so each row is self-describing about whether the
        # answer was modal (temp 0) or distribution-sampled — a reproducibility factor, not a
        # cost one. NB: deterministic-*judge* says nothing about this; they are orthogonal.
        "generator_temperature": gr.temperature,
        "input_tokens": gr.input_tokens,
        "output_tokens": gr.output_tokens,
        # Generator's billed cache tokens (when the provider reports them) — the cost panel
        # needs them: a cache *read* is far cheaper than a fresh input token, so raw
        # input_tokens overstates cost without these. Optional/additive, like the source field.
        "cache_read_input_tokens": gr.cache_read_input_tokens,
        "cache_creation_input_tokens": gr.cache_creation_input_tokens,
        "context_tokens_proxy": rr.context_tokens,
        "num_sources": len(rr.sources),
        "retrieval_latency_ms": round(rr.latency_ms, 1),
        "generation_latency_ms": round(gr.latency_ms, 1),
        # The retriever's full per-retrieval telemetry, persisted verbatim for the analysis
        # layer (writer-LLM cost for sparqlgen, hops/caps/num_linked for graph, top_k/cosine
        # distances for vector, sparql_valid, …). Stored whole rather than whitelisted so a new
        # retriever's additive keys are captured with no harness edit — the same "additive only,
        # never enumerate the roster" rule the traversal_info contract carries (retrievers/base.py).
        "traversal_info": rr.traversal_info,
    }

    judge = judges.get(question["scoring"])
    if judge is None:
        row |= {"judged": False, "passed": None, "score": None,
                "verdict": f"no judge for scoring={question['scoring']!r}", "judge_details": {}}
        return row

    jr = judge.score(
        gr.text,
        question["ground_truth"],
        answer_var=question.get("answer_var"),
        question=question["question"],
    )
    row |= {"judged": True, "passed": jr.passed, "score": jr.score,
            "verdict": jr.verdict, "judge_details": jr.details}
    return row


def iter_rows(
    retriever: Retriever,
    generator: Generator,
    judges: Mapping[str, Judge],
    questions: list[dict],
) -> Iterator[dict]:
    """Yield one result row per question, in input order. Streaming so the caller can
    persist each row as it lands (durability against a mid-run crash); per-question errors
    are isolated in `run_question`, so the generator runs to completion regardless."""
    for q in questions:
        yield run_question(retriever, generator, judges, q)


def run(
    retriever: Retriever,
    generator: Generator,
    judges: Mapping[str, Judge],
    questions: list[dict],
) -> list[dict]:
    """Eager convenience wrapper over `iter_rows` — one result row each, in input order."""
    return list(iter_rows(retriever, generator, judges, questions))


# TODO (future): record a code-version factor in the manifest — git SHA + a
# working-tree-dirty flag (and ideally embedding-model id once vector runs join). It's a
# real factorial factor (the retrievers, prompt assembly, and judges live in code), named
# in retrievers/README.md's manifest list, but deferred: a bare short SHA that ignores a
# dirty tree gives false provenance, so capture it properly or not at all.
@dataclass
class RunManifest:
    """Run-constant factors (the factorial-provenance record). Rows carry per-question
    factors; this carries everything held fixed for the whole run. See eval/README.md."""

    run_id: str
    timestamp: str
    retriever: str
    generator_provider: str
    generator_model: str
    judge: str
    questions_path: str
    num_questions: int
    system_prompt_sha256: str
    # The configured `generator_model` may be an alias; this is the exact dated snapshot the
    # provider resolved it to (from the rows, post-run). Optional/additive — None for an
    # all-errored run, or a run made before the row carried it.
    generator_model_resolved: str | None = None
    # The generator's requested sampling temperature — the run-level reproducibility setting
    # (None = unpinned / provider default). A run-constant factor, recorded beside
    # generator_model; renders into the manifest table automatically (to_dict iterates fields).
    generator_temperature: float | None = None
    # The corpus the run retrieved against — a content-addressed *reference* to a committed
    # ingest/corpus/<id>.json profile (see ingest/corpus/README.md), not a re-measurement. Lets the
    # analysis layer group results by corpus and diff scales (smoke vs full). None = a run made
    # before corpus provenance, or with no corpus declared — additive/optional like the above.
    corpus_build_id: str | None = None
    harness_version: str = "harness-v1"

    def to_dict(self) -> dict:
        return self.__dict__.copy()


def make_manifest(
    retriever: Retriever,
    generator: Generator,
    questions: list[dict],
    *,
    run_id: str,
    questions_path: str,
    judge: str = "deterministic-v1",
    generator_model_resolved: str | None = None,
    corpus_build_id: str | None = None,
) -> RunManifest:
    return RunManifest(
        run_id=run_id,
        timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        retriever=retriever.name,
        generator_provider=generator.provider,
        generator_model=generator.model,
        judge=judge,
        questions_path=questions_path,
        num_questions=len(questions),
        system_prompt_sha256=hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16],
        generator_model_resolved=generator_model_resolved,
        # Duck-typed: the configured request temperature lives on the generator object (the
        # Generator protocol doesn't mandate it), None when the adapter leaves it unset.
        generator_temperature=getattr(generator, "temperature", None),
        corpus_build_id=corpus_build_id,
    )


# --- markdown report (the tracked, human-reviewable artifact) ---------------
# The per-row JSONL + manifest are the machine-readable feed for the analysis layer
# (gitignored, reproducible). This renders the same run as a committed markdown for
# offline review — a *preliminary* snapshot, explicitly not the definitive metrics.

def _md_cell(text, limit: int = 80) -> str:
    """Escape a value for a markdown table cell: kill pipes/newlines, truncate."""
    s = str(text).replace("|", r"\|").replace("\n", " / ")
    return s[: limit - 1] + "…" if len(s) > limit else s


def _fmt_ground_truth(gt) -> str:
    """Compact ground-truth rendering — sets show their size + first few members."""
    if isinstance(gt, list):
        head = ", ".join(map(str, gt[:5]))
        return f"[{len(gt)}] {head}" + ("…" if len(gt) > 5 else "")
    return str(gt)


def to_markdown(rows: list[dict], manifest: RunManifest) -> str:
    """Render a run as a self-contained markdown report (manifest + verdicts + summary)."""
    judged = [r for r in rows if r.get("judged")]
    npass = sum(1 for r in judged if r["passed"])
    in_tok = sum(r["input_tokens"] for r in rows)
    out_tok = sum(r["output_tokens"] for r in rows)

    per_type: dict[str, list[bool]] = {}
    for r in judged:
        per_type.setdefault(r["type_id"], []).append(bool(r["passed"]))

    L: list[str] = []
    L += [f"# Eval run — {manifest.retriever} → {manifest.generator_provider}:{manifest.generator_model}", ""]
    L += [
        "> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on "
        "every run. Curated cross-run observations and validity caveats live in "
        "`eval/FINDINGS.md`.", "",
        "> **Preliminary — not the definitive metrics.** This is the latest run's auto-table "
        "snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from "
        "the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — "
        "read the verdicts, not a leaderboard.", "",
    ]
    L += ["## Run manifest", "", "| factor | value |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in manifest.to_dict().items()]
    L += ["", f"## Verdicts — {npass}/{len(judged)} passed", ""]
    L += ["| result | type | scoring | predicted | ground truth | verdict |",
          "|---|---|---|---|---|---|"]
    for r in rows:
        mark = "✅" if r.get("passed") else ("—" if r.get("passed") is None else "❌")
        L.append(
            f"| {mark} | `{r['type_id']}` | {r['scoring']} | {_md_cell(r['predicted'])} | "
            f"{_md_cell(_fmt_ground_truth(r['ground_truth']))} | {_md_cell(r['verdict'])} |"
        )
    L += ["", "## By type", "", "| type | passed |", "|---|---|"]
    L += [f"| `{t}` | {sum(per_type[t])}/{len(per_type[t])} |" for t in sorted(per_type)]
    L += ["", f"Billed tokens: **{in_tok}** in / **{out_tok}** out "
          f"(generator's tokenizer; closed-book input is the no-retrieval baseline).", ""]
    return "\n".join(L)
