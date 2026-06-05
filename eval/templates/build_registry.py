#!/usr/bin/env python3
"""Generate the docs that must not drift from the templates.

Two outputs, both derived from the YAML templates (the single source of truth):
  - eval/templates/README.md — the full human-readable template registry (below);
  - the per-type distribution table in eval/README.md — summed from each template's
    `count:` field and spliced between generated-block markers, leaving that file's
    hand-authored design prose intact.

For each YAML template the registry joins two authoritative sources and renders one
Markdown table, sorted by `type_id` (zero-padded, so lexical order = taxonomy order):

  - the YAML template  -> identity, question shape, scoring
  - the ground-truth .rq's `# --- registry ---` frontmatter -> seed, chain, and the
    committed ground-truth answer

The .rq frontmatter is authoritative for the answer; this script copies it into the
docs so the docs cannot drift from the .rq. Plain generation is a pure text
transform — no GraphDB needed.

    uv run --extra produce python eval/templates/build_registry.py

`--verify` re-runs every query against GraphDB (decision B: the full graph is
canonical) and asserts the live answer still equals the committed one, catching
drift if the graph changes under a committed answer. Exits non-zero on any mismatch.

    uv run --extra produce python eval/templates/build_registry.py --verify

README.md is GENERATED. Edit the YAML or the .rq frontmatter, then regenerate.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

# Same-directory sibling module; sys.path[0] is this dir when run as a script.
from run_ground_truth import DEFAULT_GRAPHDB_ENDPOINT, run_query

TEMPLATES_DIR = Path(__file__).parent
README_PATH = TEMPLATES_DIR / "README.md"
# The per-type distribution table is spliced into eval/README.md between markers,
# so that hand-authored design doc keeps its prose while the numbers stay derived.
EVAL_README_PATH = TEMPLATES_DIR.parent / "README.md"
DIST_BEGIN = "<!-- BEGIN GENERATED: distribution (build_registry.py) -->"
DIST_END = "<!-- END GENERATED: distribution -->"

FRONTMATTER_START = "# --- registry ---"
FRONTMATTER_END = "# --- end registry ---"


def parse_rq_frontmatter(rq_path: Path) -> dict:
    """Extract the `# --- registry ---` YAML block from a ground-truth .rq.

    The block lives in `#` comments so the .rq stays runnable standalone. We strip
    the comment prefix and YAML-load the remainder.
    """
    lines = rq_path.read_text().splitlines()
    try:
        start = lines.index(FRONTMATTER_START)
        end = lines.index(FRONTMATTER_END)
    except ValueError as exc:
        raise ValueError(f"{rq_path.name}: missing registry frontmatter block") from exc

    body = []
    for line in lines[start + 1 : end]:
        # Drop the leading "# " (or bare "#"). Anything inside the fence is frontmatter.
        body.append(line[2:] if line.startswith("# ") else line.lstrip("#"))
    data = yaml.safe_load("\n".join(body)) or {}

    # `chain` and `answer` are always required. The seed may be a single entity
    # (`seed` + `seed_uri`) or several (`seeds:` list), the latter for multi-traversal
    # templates like set intersection/difference. Singular form stays valid, so older
    # single-seed .rq files need no migration.
    missing = {"chain", "answer"} - data.keys()
    if not (data.get("seeds") or {"seed", "seed_uri"} <= data.keys()):
        missing.add("seed/seed_uri or seeds")
    if missing:
        raise ValueError(f"{rq_path.name}: frontmatter missing keys {sorted(missing)}")
    return data


def load_templates() -> list[dict]:
    """Load every YAML template joined with its .rq frontmatter, sorted by type_id."""
    templates = []
    for yaml_path in sorted(TEMPLATES_DIR.glob("*.yaml")):
        tpl = yaml.safe_load(yaml_path.read_text())
        rq_path = TEMPLATES_DIR / tpl["ground_truth"]
        templates.append(
            {
                "id": tpl["id"],
                "type_id": tpl["type"],
                "question": tpl["question"],
                "scoring": tpl["scoring"],
                "answer_var": tpl["answer_var"],
                "count": tpl.get("count"),
                "rq_path": rq_path,
                **parse_rq_frontmatter(rq_path),
            }
        )
    return sorted(templates, key=lambda t: t["type_id"])


def _format_seed(t: dict) -> str:
    """Render the committed seed(s): one entity, or several (set intersection/difference)."""
    if t.get("seeds"):
        return ", ".join(f"{s['label']} (`{s['uri']}`)" for s in t["seeds"])
    return f"{t['seed']} (`{t['seed_uri']}`)"


def _answer_count(answer) -> str:
    if isinstance(answer, list):
        # An empty set is the ground truth for a negative/unanswerable question:
        # the edge does not exist, so the correct response is refusal.
        return f"{len(answer)} results" if answer else "none (negative)"
    return f"`{answer}`"


def _answer_detail(answer) -> str:
    if isinstance(answer, list):
        if not answer:
            return (
                "**Ground-truth answer:** none — the queried edge does not exist; "
                "the correct response is refusal, not a guess."
            )
        header = f"**Ground-truth answer ({len(answer)}):**\n"
        return header + "\n".join(f"- {item}" for item in answer)
    return f"**Ground-truth answer:** `{answer}`"


def render(templates: list[dict]) -> str:
    out = [
        "# Template registry",
        "",
        "> **GENERATED — do not edit by hand.** Produced by `build_registry.py` from"
        " each template's YAML (`*.yaml`) and its ground-truth query frontmatter"
        " (`ground_truth/*.rq`).",
        "> Regenerate: `uv run --extra produce python eval/templates/build_registry.py`"
        " (add `--verify` to re-check answers against GraphDB).",
        "",
        "The `.rq` frontmatter is authoritative for the committed seed and answer;"
        " this table copies it. Templates are ordered by `type_id` (taxonomy order).",
        "",
        "| `type_id` | Template | Question | Committed seed | Answer |",
        "|---|---|---|---|---|",
    ]
    for t in templates:
        question = t["question"].replace("|", "\\|")
        out.append(
            f"| `{t['type_id']}` | `{t['id']}` | {question} "
            f"| {_format_seed(t)} | {_answer_count(t['answer'])} |"
        )

    out += ["", "## Per-template detail", ""]
    for t in templates:
        out += [
            f"### `{t['type_id']}` — {t['id']}",
            "",
            f"**Question:** {t['question']}",
            "",
            f"**Chain:** {t['chain']}",
            "",
            f"**Committed seed:** {_format_seed(t)}",
            "",
            f"**Scoring:** `{t['scoring']}` · answer column `{t['answer_var']}`",
            "",
            _answer_detail(t["answer"]),
            "",
        ]
    return "\n".join(out) + "\n"


def render_distribution(templates: list[dict]) -> str:
    """Render the per-type question-count table, summed from each template's `count`.

    Keyed by `type_id` — the only distribution key the YAML carries. Friendly type
    names live solely in the taxonomy table in eval/README.md (their single home),
    so this table cross-references by id rather than copying them.
    """
    by_type: dict[str, int] = {}
    for t in templates:
        if t["count"] is not None:
            by_type[t["type_id"]] = by_type.get(t["type_id"], 0) + t["count"]

    rows = [f"| `{tid}` | {n} |" for tid, n in sorted(by_type.items())]
    total = sum(by_type.values())
    return "\n".join(
        ["| `type_id` | Count |", "|-----------|-------|", *rows, f"| **Total** | **{total}** |"]
    )


def splice_block(path: Path, begin: str, end: str, content: str) -> None:
    """Replace the text between `begin` and `end` markers in `path` with `content`.

    Lets a generator own one block of an otherwise hand-authored file. Fails loudly
    if the markers are missing or out of order, rather than silently appending.
    """
    text = path.read_text()
    try:
        i = text.index(begin) + len(begin)
        j = text.index(end, i)
    except ValueError as exc:
        raise ValueError(f"{path.name}: missing distribution markers {begin!r}/{end!r}") from exc
    path.write_text(text[:i] + "\n" + content + "\n" + text[j:])


def verify(templates: list[dict], endpoint: str) -> bool:
    """Re-run each query against GraphDB; assert the live answer == committed answer."""
    all_ok = True
    for t in templates:
        rows = run_query(t["rq_path"].read_text(), endpoint=endpoint)
        live = [row[t["answer_var"]] for row in rows]
        committed = t["answer"]

        if isinstance(committed, list):
            ok = set(live) == set(committed)
            detail = "" if ok else (
                f"  + extra:   {sorted(set(live) - set(committed))}\n"
                f"  - missing: {sorted(set(committed) - set(live))}"
            )
        else:
            # Scalar: numerical count or ASK boolean. Compare case-insensitively so
            # the JSON boolean "true" matches a YAML `true` (Python True -> "True").
            ok = len(live) == 1 and str(live[0]).lower() == str(committed).lower()
            detail = "" if ok else f"  live={live} committed={committed!r}"

        print(f"  [{'OK' if ok else 'MISMATCH'}] {t['id']}")
        if not ok:
            print(detail)
            all_ok = False
    return all_ok


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--verify",
        action="store_true",
        help="re-run each query against GraphDB and assert the committed answer still holds",
    )
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_GRAPHDB_ENDPOINT,
        help=f"GraphDB SPARQL endpoint for --verify (default {DEFAULT_GRAPHDB_ENDPOINT})",
    )
    args = parser.parse_args()

    templates = load_templates()

    if args.verify:
        print(f"Verifying {len(templates)} template(s) against {args.endpoint} ...")
        if not verify(templates, args.endpoint):
            sys.exit("Registry verification FAILED — committed answers drifted from the graph.")
        print("All committed answers match the graph.")

    README_PATH.write_text(render(templates))
    print(f"Wrote {README_PATH.relative_to(TEMPLATES_DIR.parent.parent)} ({len(templates)} templates).")

    splice_block(EVAL_README_PATH, DIST_BEGIN, DIST_END, render_distribution(templates))
    print(f"Spliced distribution table into {EVAL_README_PATH.relative_to(TEMPLATES_DIR.parent.parent)}.")


if __name__ == "__main__":
    main()
