#!/usr/bin/env python3
"""Eval-set producer (build step 3) — instantiate templates into questions.jsonl.

Stage 1 of the eval pipeline (see eval/README.md): takes the hand-authored YAML
templates plus the Hetionet graph in GraphDB and emits a frozen, reproducible eval
set with ground truth. For each template it:

  1. reads the placeholder spec (node_type, sample mode, edge, bind_var, label_into),
  2. runs a *candidate query* for the sample mode — a SPARQL query that returns only
     entities for which the ground-truth answer is well-formed (e.g. has_edge returns
     only nodes that actually carry the edge, so the answer is never empty),
  3. seeded-samples `count` candidates from that pool,
  4. rewrites the .rq's `VALUES ?<bind_var> { ... }` line(s) with each pick and runs
     the ground-truth query via the shared `run_query` seam,
  5. writes one questions.jsonl record per instantiation.

Constrained candidate-query sampling (not sample-then-filter) is deliberate: the
candidate pool *is* the valid set, so picks never need rejection. This matters most
for the paired types (06/07/09) where random pairs almost never satisfy the
constraint; it also makes seeded sampling deterministic (the pool is fixed, so the
RNG draws reproducibly).

INCREMENT 1 supports only single-placeholder `has_edge` templates (types 01/02/05).
`lacks_edge` and `paired` raise NotImplementedError until their increments land, so
the supported surface is explicit.

    uv run --extra produce python eval/produce/produce.py \\
        --template genes_expressed_in_anatomy --out /tmp/q.jsonl
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from pathlib import Path

import yaml

# run_query is the single GraphDB execution seam, owned by the step-2 runner and
# shared with build_registry.py. The producer is a distinct concern in its own
# folder (eval/produce/), so we reach the seam by putting the templates dir on the
# path rather than duplicating it. If a third consumer appears, extract run_query to
# a shared eval module; one sys.path insert doesn't yet justify that refactor.
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
sys.path.insert(0, str(TEMPLATES_DIR))
from run_ground_truth import DEFAULT_GRAPHDB_ENDPOINT, run_query  # noqa: E402

DEFAULT_OUT = Path(__file__).parent.parent / "questions.jsonl"
DEFAULT_SEED = "20260605"

# The candidate query only ever references node types and edges, both in the hetio:
# namespace, plus rdfs:label. URIs go into the ground-truth query as full <...> IRIs,
# so the .rq's own PREFIX block covers the rest — no other prefixes needed here.
PREFIXES = """\
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>"""

# Scoring types whose ground truth is a single value, not a set. Everything else
# (set_match, semantic) is stored as a sorted list.
SCALAR_SCORINGS = {"numerical", "string_match", "boolean"}


def has_edge_candidates(
    node_type: str,
    edge: str,
    *,
    endpoint: str,
    min_fan: int | None = None,
    max_fan: int | None = None,
) -> list[tuple[str, str]]:
    """Return (uri, label) for nodes of `node_type` carrying `edge`, within fan bounds.

    This is the `has_edge` sample mode's candidate query. Requiring the edge in the
    WHERE clause keeps the pool to entities whose ground-truth answer is non-empty.
    The optional `min_fan`/`max_fan` HAVING clause additionally excludes hub nodes
    whose answer set is too large to be an enumerable eval question (e.g. "genes
    expressed in the central nervous system" -> 11k genes). This is the constrained-
    sampling analogue of step 2 hand-picking bounded seeds; we push the bound into
    the pool rather than rejecting after the fact. ORDER BY fixes a stable pool so
    seeded sampling is reproducible.
    """
    having = []
    if min_fan is not None:
        having.append(f"COUNT(DISTINCT ?o) >= {min_fan}")
    if max_fan is not None:
        having.append(f"COUNT(DISTINCT ?o) <= {max_fan}")
    having_clause = f"\nHAVING ({' && '.join(having)})" if having else ""

    query = f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {{
  ?e a {node_type} ;
     {edge} ?o ;
     rdfs:label ?label .
}}
GROUP BY ?e ?label{having_clause}
ORDER BY ?e ?label"""
    rows = run_query(query, endpoint=endpoint)
    # A node could in principle carry more than one label; keep the first (the pool
    # is sorted, so "first" is deterministic).
    pool: dict[str, str] = {}
    for row in rows:
        pool.setdefault(row["e"], row["label"])
    return list(pool.items())


def rewrite_values(query_text: str, bind_var: str, uri: str) -> str:
    """Replace `VALUES ?<bind_var> { ... }` with the sampled URI as a full IRI.

    Injecting `<full-iri>` sidesteps prefix concerns: GraphDB returns expanded URIs
    from the candidate query, and an angle-bracketed IRI is valid wherever a prefixed
    name is. The trailing comment on the VALUES line (`# ... producer rewrites this`)
    is preserved because the pattern only matches up to the closing brace.
    """
    pattern = r"VALUES\s+\?" + re.escape(bind_var) + r"\s*\{[^}]*\}"
    replacement = f"VALUES ?{bind_var} {{ <{uri}> }}"
    new_text, n = re.subn(pattern, replacement, query_text)
    if n != 1:
        raise ValueError(
            f"expected exactly one `VALUES ?{bind_var}` block to rewrite, found {n}"
        )
    return new_text


def shape_ground_truth(rows: list[dict[str, str]], answer_var: str, scoring: str):
    """Collapse query rows into the stored ground-truth shape for this scoring type."""
    values = [row[answer_var] for row in rows if answer_var in row]
    if scoring in SCALAR_SCORINGS:
        return values[0] if values else None
    return sorted(values)


def load_template(template_id: str) -> dict:
    yaml_path = TEMPLATES_DIR / f"{template_id}.yaml"
    if not yaml_path.exists():
        sys.exit(f"No template YAML at {yaml_path}")
    tpl = yaml.safe_load(yaml_path.read_text())
    tpl["_rq_path"] = TEMPLATES_DIR / tpl["ground_truth"]
    return tpl


def instantiate(tpl: dict, *, seed: str, endpoint: str) -> list[dict]:
    """Sample entities for one template and return its questions.jsonl records."""
    placeholders = tpl.get("placeholders") or {}
    if len(placeholders) != 1:
        raise NotImplementedError(
            f"{tpl['id']}: {len(placeholders)} placeholders — increment 1 supports "
            "single-placeholder has_edge templates only"
        )
    name, spec = next(iter(placeholders.items()))
    if spec["sample"] != "has_edge":
        raise NotImplementedError(
            f"{tpl['id']}: sample mode {spec['sample']!r} not yet supported "
            "(increment 1 = has_edge)"
        )
    if "count" not in tpl:
        sys.exit(f"{tpl['id']}: template is missing a `count:` field")

    pool = has_edge_candidates(
        spec["node_type"],
        spec["edge"],
        endpoint=endpoint,
        min_fan=spec.get("min_fan"),
        max_fan=spec.get("max_fan"),
    )
    if not pool:
        sys.exit(f"{tpl['id']}: candidate pool is empty — check node_type/edge")

    # Per-template RNG keyed on (seed, template_id): adding or reordering templates
    # never reshuffles another template's draws.
    rng = random.Random(f"{seed}:{tpl['id']}")
    count = min(tpl["count"], len(pool))
    if count < tpl["count"]:
        print(
            f"  ! {tpl['id']}: pool has only {len(pool)} candidates, "
            f"sampling {count} of requested {tpl['count']}"
        )
    picks = rng.sample(pool, count)

    rq_text = tpl["_rq_path"].read_text()
    records = []
    for i, (uri, label) in enumerate(picks):
        query = rewrite_values(rq_text, spec["bind_var"], uri)
        rows = run_query(query, endpoint=endpoint)
        question = tpl["question"].replace(f"{{{spec['label_into']}}}", label)
        records.append(
            {
                "question_id": f"{tpl['type']}__{tpl['id']}__{i:02d}",
                "type_id": tpl["type"],
                "template_id": tpl["id"],
                "question": question,
                "scoring": tpl["scoring"],
                "answer_var": tpl["answer_var"],
                "ground_truth": shape_ground_truth(rows, tpl["answer_var"], tpl["scoring"]),
                "seeds": [{"bind_var": spec["bind_var"], "label": label, "uri": uri}],
                "sampling_seed": f"{seed}:{tpl['id']}",
            }
        )
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        action="append",
        dest="templates",
        help="template id to produce (repeatable). Default: all *.yaml templates.",
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"output JSONL (default {DEFAULT_OUT})")
    parser.add_argument("--seed", default=DEFAULT_SEED, help=f"sampling seed (default {DEFAULT_SEED})")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_GRAPHDB_ENDPOINT,
        help=f"GraphDB SPARQL endpoint (default {DEFAULT_GRAPHDB_ENDPOINT})",
    )
    args = parser.parse_args()

    if args.templates:
        template_ids = args.templates
    else:
        template_ids = sorted(p.stem for p in TEMPLATES_DIR.glob("*.yaml"))

    all_records: list[dict] = []
    for tid in template_ids:
        tpl = load_template(tid)
        print(f"Producing {tid} ({tpl['type']}) ...")
        all_records.extend(instantiate(tpl, seed=args.seed, endpoint=args.endpoint))

    args.out.write_text("\n".join(json.dumps(r) for r in all_records) + "\n")
    print(f"Wrote {len(all_records)} question(s) to {args.out}")


if __name__ == "__main__":
    main()
