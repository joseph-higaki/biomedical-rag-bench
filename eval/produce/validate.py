#!/usr/bin/env python3
"""Validate a produced questions.jsonl against structural + count criteria.

The operator gate on the producer's output (build step 3): it inspects the emitted
eval set, not the graph, so it needs no GraphDB. This is to `produce.py` what
`build_registry.py --verify` is to the registry — a quality check living beside the
thing it guards.

What it checks (per `eval/produce/README.md` success criteria):
  - every record carries the required fields;
  - no unfilled `{placeholder}` survived substitution;
  - ground-truth shape matches the scoring type (scalar vs list);
  - the negative type's answer is the empty list; the boolean type's answers are
    'true'/'false' and roughly balanced per template;
  - set answers respect their template's `min_answer`/`max_answer` bounds;
  - `question_id`s are unique;
  - each template produced exactly its declared `count`.

Expected counts/bounds come from the templates' YAML (the single source of truth),
not a hardcoded table, so this works for a partial dry run or the full run alike.
Only templates actually present in the file are count-checked.

NOT checked here: reproducibility — that is a property of two runs, not one file
(produce twice at the same seed and `diff`), so it stays an operator step.

    uv run --extra produce python eval/produce/validate.py --questions eval/questions.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
DEFAULT_QUESTIONS = Path(__file__).parent.parent / "questions.jsonl"

REQUIRED_FIELDS = {
    "question_id", "type_id", "template_id", "question",
    "scoring", "answer_var", "ground_truth", "seeds", "sampling_seed",
}
# Scoring types whose ground truth is a single scalar; everything else is a list.
# Mirrors SCALAR_SCORINGS in produce.py (kept in sync deliberately — see that module).
SCALAR_SCORINGS = {"numerical", "string_match", "boolean"}
PLACEHOLDER_RE = re.compile(r"\{[a-z_]+\}")


def load_template_meta() -> dict[str, dict]:
    """Map template_id -> the YAML fields validation needs (count, scoring, bounds).

    yaml is imported lazily (like httpx in run_ground_truth) so the pure
    `validate_records` can be imported and unit-tested without the `produce` extra.
    """
    import yaml

    meta = {}
    for yaml_path in TEMPLATES_DIR.glob("*.yaml"):
        tpl = yaml.safe_load(yaml_path.read_text())
        meta[tpl["id"]] = {
            "count": tpl.get("count"),
            "scoring": tpl.get("scoring"),
            "min_answer": tpl.get("min_answer"),
            "max_answer": tpl.get("max_answer"),
        }
    return meta


def validate_records(records: list[dict], meta: dict[str, dict]) -> list[str]:
    """Return a list of problem descriptions; empty list means the set is valid.

    Pure: takes already-loaded records and template metadata, touches no I/O, so it
    is unit-testable with hand-built record dicts.
    """
    problems: list[str] = []

    for r in records:
        qid = r.get("question_id", "<no id>")
        missing = REQUIRED_FIELDS - r.keys()
        if missing:
            problems.append(f"{qid}: missing fields {sorted(missing)}")

        if PLACEHOLDER_RE.search(r.get("question", "")):
            problems.append(f"{qid}: unfilled placeholder in question {r.get('question')!r}")

        scoring, gt = r.get("scoring"), r.get("ground_truth")
        if scoring in SCALAR_SCORINGS:
            if not isinstance(gt, str) or gt == "":
                problems.append(f"{qid}: {scoring} ground_truth should be a non-empty scalar, got {gt!r}")
        elif not isinstance(gt, list):
            problems.append(f"{qid}: {scoring} ground_truth should be a list, got {type(gt).__name__}")

        # Type-specific contracts.
        if scoring == "binary" and gt != []:
            problems.append(f"{qid}: binary (negative) ground_truth should be [], got {gt!r}")
        if scoring == "boolean" and gt not in ("true", "false"):
            problems.append(f"{qid}: boolean ground_truth should be 'true'/'false', got {gt!r}")

        # Answer-size bounds, where the template declares them (set/post-check types).
        bounds = meta.get(r.get("template_id"), {})
        if isinstance(gt, list) and scoring == "set_match":
            lo, hi = bounds.get("min_answer"), bounds.get("max_answer")
            if lo is not None and len(gt) < lo:
                problems.append(f"{qid}: |answer|={len(gt)} below min_answer {lo}")
            if hi is not None and len(gt) > hi:
                problems.append(f"{qid}: |answer|={len(gt)} above max_answer {hi}")

    ids = [r.get("question_id") for r in records]
    dups = sorted({i for i in ids if ids.count(i) > 1})
    if dups:
        problems.append(f"duplicate question_ids: {dups}")

    produced = Counter(r.get("template_id") for r in records)
    for tid, n in produced.items():
        want = meta.get(tid, {}).get("count")
        if want is not None and n != want:
            problems.append(f"{tid}: produced {n} records, template declares count {want}")
        if meta.get(tid, {}).get("scoring") == "boolean":
            vals = [r["ground_truth"] for r in records if r.get("template_id") == tid]
            t, f = vals.count("true"), vals.count("false")
            if abs(t - f) > 1:
                problems.append(f"{tid}: boolean labels unbalanced (true={t}, false={f})")

    return problems


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=DEFAULT_QUESTIONS,
                        help=f"questions.jsonl to validate (default {DEFAULT_QUESTIONS})")
    args = parser.parse_args()

    if not args.questions.exists():
        sys.exit(f"No questions file at {args.questions}")
    records = [json.loads(line) for line in args.questions.read_text().splitlines() if line.strip()]
    meta = load_template_meta()

    problems = validate_records(records, meta)

    print(f"Validated {len(records)} question(s) from {args.questions}.")
    present = sorted({r.get("template_id") for r in records})
    absent = sorted(t for t in meta if t not in present and meta[t].get("count") is not None)
    if absent:
        print(f"  note: {len(absent)} template(s) with a count not present (partial run): {absent}")
    if problems:
        print(f"\n{len(problems)} problem(s):")
        for p in problems:
            print(f"  - {p}")
        sys.exit(1)
    print("All checks passed.")


if __name__ == "__main__":
    main()
