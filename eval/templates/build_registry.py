#!/usr/bin/env python3
"""Generate eval/templates/README.md — the human-readable template registry.

For each YAML template it joins two authoritative sources and renders one Markdown
registry, sorted by `type_id` (zero-padded, so lexical order = taxonomy order):

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

    missing = {"seed", "seed_uri", "chain", "answer"} - data.keys()
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
                "rq_path": rq_path,
                **parse_rq_frontmatter(rq_path),
            }
        )
    return sorted(templates, key=lambda t: t["type_id"])


def _answer_count(answer) -> str:
    return f"{len(answer)} results" if isinstance(answer, list) else f"`{answer}`"


def _answer_detail(answer) -> str:
    if isinstance(answer, list):
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
            f"| {t['seed']} (`{t['seed_uri']}`) | {_answer_count(t['answer'])} |"
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
            f"**Committed seed:** {t['seed']} (`{t['seed_uri']}`)",
            "",
            f"**Scoring:** `{t['scoring']}` · answer column `{t['answer_var']}`",
            "",
            _answer_detail(t["answer"]),
            "",
        ]
    return "\n".join(out) + "\n"


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
            ok = len(live) == 1 and str(live[0]) == str(committed)
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


if __name__ == "__main__":
    main()
