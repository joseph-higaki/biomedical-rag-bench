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
# (set_match, binary, semantic) is stored as a sorted list. `binary` (type 08
# negative) is a list on purpose: its ground truth is the *empty* set — the correct
# response is refusal — and [] carries that, whereas a scalar would flatten it to a
# meaningless None. `boolean` (type 09 path existence) is the genuine scalar true/false.
SCALAR_SCORINGS = {"numerical", "string_match", "boolean"}

# Safety net for paired sampling: try at most this many partners per anchor before
# giving up on it and moving to the next. With a bounded anchor fan the answer-size
# check almost never rejects, so this cap is rarely reached — it exists so a future
# template can never reproduce the unbounded-anchor query explosion.
PARTNER_ATTEMPT_CAP = 200


def has_edge_candidates(
    node_type: str,
    edge: str,
    *,
    endpoint: str,
    target_type: str | None = None,
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

    `target_type` constrains the edge's object to a node type, mirroring a type filter
    in the .rq. This is REQUIRED for polymorphic edges: hetio:participates reaches
    Pathway, BiologicalProcess, MolecularFunction, and CellularComponent, but the
    pathway .rq counts only Pathways. Without the filter, the fan count (and any pair
    overlap) measures the wrong thing and disagrees with the .rq answer.
    """
    target_constraint = f"\n     ?o a {target_type} ." if target_type else ""
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
     rdfs:label ?label .{target_constraint}
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


def lacks_edge_candidates(
    node_type: str,
    edge: str,
    presence_edge: str,
    *,
    endpoint: str,
    min_presence_fan: int | None = None,
) -> list[tuple[str, str]]:
    """Return (uri, label) for nodes of `node_type` that LACK `edge` but carry `presence_edge`.

    The `lacks_edge` sample mode's candidate query (type 08 negative). `FILTER NOT
    EXISTS` on `edge` makes the ground-truth answer provably empty — the point of a
    negative question. The `presence_edge` requirement keeps the entity well-attested
    (e.g. a Compound with side effects, hence real PubMed abstracts), so the negative
    is a *tempting hallucination* for the vector retriever rather than a trivial
    unknown-entity case (H2). `min_presence_fan` raises that bar to genuinely studied
    entities. Pushing both constraints into the pool keeps sampling rejection-free.
    """
    having = (
        f"\nHAVING (COUNT(DISTINCT ?p) >= {min_presence_fan})" if min_presence_fan else ""
    )
    query = f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?p) AS ?pfan) WHERE {{
  ?e a {node_type} ;
     {presence_edge} ?p ;
     rdfs:label ?label .
  FILTER NOT EXISTS {{ ?e {edge} ?x }}
}}
GROUP BY ?e ?label{having}
ORDER BY ?e ?label"""
    rows = run_query(query, endpoint=endpoint)
    pool: dict[str, str] = {}
    for row in rows:
        pool.setdefault(row["e"], row["label"])
    return list(pool.items())


def candidate_pool(spec: dict, *, endpoint: str) -> list[tuple[str, str]]:
    """Dispatch a single-placeholder spec to its sample mode's candidate query."""
    mode = spec["sample"]
    if mode == "has_edge":
        return has_edge_candidates(
            spec["node_type"],
            spec["edge"],
            endpoint=endpoint,
            target_type=spec.get("target_type"),
            min_fan=spec.get("min_fan"),
            max_fan=spec.get("max_fan"),
        )
    if mode == "lacks_edge":
        if "presence_edge" not in spec:
            sys.exit(
                f"lacks_edge placeholder needs a `presence_edge` so the entity stays "
                "well-attested (a tempting hallucination, not a trivial unknown)"
            )
        return lacks_edge_candidates(
            spec["node_type"],
            spec["edge"],
            spec["presence_edge"],
            endpoint=endpoint,
            min_presence_fan=spec.get("min_presence_fan"),
        )
    raise NotImplementedError(
        f"sample mode {mode!r} not yet supported (single-placeholder has_edge/lacks_edge only)"
    )


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


def paired_candidates(
    anchor_uri: str,
    partner: dict,
    *,
    endpoint: str,
    target_type: str | None = None,
    min_overlap: int | None = None,
    max_overlap: int | None = None,
) -> list[tuple[str, str]]:
    """Partners sharing `edge`-targets with the anchor, within an overlap bound.

    The structurally hard part of pair sampling: two random genes almost never share
    a pathway, so blind pairing would reject endlessly. This query returns only genes
    that co-participate in the anchor's targets, collapsing the O(n^2) pair space to a
    small valid set.

    `min_overlap`/`max_overlap` (declared per template on the partner placeholder)
    bound how many targets the pair must share, via HAVING. This is what keeps the
    per-partner answer check from churning: type 06 sets `min_overlap: 2` because the
    overlap *is* the intersection answer, so every returned partner already clears the
    `min_answer` floor and the .rq runs about once per anchor. Crucially the producer
    stays type-agnostic — it just enforces whatever overlap the *template* declares; it
    never computes the answer from the overlap. The .rq remains the single source of
    the stored ground truth.
    """
    having = []
    if min_overlap is not None:
        having.append(f"COUNT(DISTINCT ?shared) >= {min_overlap}")
    if max_overlap is not None:
        having.append(f"COUNT(DISTINCT ?shared) <= {max_overlap}")
    having_clause = f"\nHAVING ({' && '.join(having)})" if having else ""

    # Mirror the .rq's object-type filter so the overlap count matches the actual
    # intersection (see has_edge_candidates: participates is polymorphic).
    target_constraint = f"\n  ?shared a {target_type} ." if target_type else ""
    query = f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?shared) AS ?overlap) WHERE {{
  <{anchor_uri}> {partner['edge']} ?shared .
  ?e {partner['edge']} ?shared ;
     a {partner['node_type']} ;
     rdfs:label ?label .{target_constraint}
  FILTER (?e != <{anchor_uri}>)
}}
GROUP BY ?e ?label{having_clause}
ORDER BY ?e ?label"""
    rows = run_query(query, endpoint=endpoint)
    pool: dict[str, str] = {}
    for row in rows:
        pool.setdefault(row["e"], row["label"])
    return list(pool.items())


def _seed_entry(spec: dict, uri: str, label: str) -> dict:
    """One seed binding, carrying label_into for question-text substitution (stripped before write)."""
    return {"bind_var": spec["bind_var"], "label": label, "uri": uri, "label_into": spec["label_into"]}


def sample_single(tpl: dict, spec: dict, rq_text: str, rng: random.Random, endpoint: str) -> list[dict]:
    """Single-placeholder sampling: pick entities, run the .rq, emit one record each.

    Two regimes, chosen by whether the template declares answer-size bounds:

    - **Direct** (no `min_answer`/`max_answer`): the sampled edge *is* the answer edge
      (single hop), so the placeholder's own fan bound already shaped the answer.
      Draw `count` picks straight from the pool.
    - **Answer post-check** (`min_answer`/`max_answer` set): the answer is multi-hop —
      the sampled head edge (e.g. a compound's `treats`) does NOT determine the answer
      size (the genes two hops downstream), and may even be empty. The fan bound is on
      the wrong hop. So we shuffle, run the real .rq per candidate, and keep only those
      whose answer lands in bounds, until `count` are collected. This is the
      single-placeholder analogue of the bound-check `sample_paired` does.
    """
    pool = candidate_pool(spec, endpoint=endpoint)
    if not pool:
        sys.exit(f"{tpl['id']}: candidate pool is empty — check node_type/edge")

    def make(uri: str, label: str) -> dict:
        rows = run_query(rewrite_values(rq_text, spec["bind_var"], uri), endpoint=endpoint)
        return {
            "seeds": [_seed_entry(spec, uri, label)],
            "ground_truth": shape_ground_truth(rows, tpl["answer_var"], tpl["scoring"]),
        }

    min_answer = tpl.get("min_answer")
    max_answer = tpl.get("max_answer")
    if min_answer is None and max_answer is None:
        count = min(tpl["count"], len(pool))
        if count < tpl["count"]:
            print(f"  ! {tpl['id']}: pool has only {len(pool)} candidates, sampling {count} of {tpl['count']}")
        return [make(uri, label) for uri, label in rng.sample(pool, count)]

    lo = min_answer if min_answer is not None else 1
    rng.shuffle(pool)
    instances = []
    for uri, label in pool:
        if len(instances) >= tpl["count"]:
            break
        inst = make(uri, label)
        n = len(inst["ground_truth"])
        if n >= lo and (max_answer is None or n <= max_answer):
            instances.append(inst)
    if len(instances) < tpl["count"]:
        print(f"  ! {tpl['id']}: found {len(instances)} bounded answers of {tpl['count']} requested")
    return instances


def sample_paired(tpl: dict, placeholders: dict, rq_text: str, rng: random.Random, endpoint: str) -> list[dict]:
    """Two-placeholder sampling (types 06/07): anchor + overlap-constrained partner.

    Insertion order is significant: the first placeholder is the anchor (geneA /
    minuend), the second the partner (geneB / subtrahend). For each shuffled anchor we
    draw the first partner whose actual answer (intersection or difference, from the
    .rq) lands in [min_answer, max_answer]; overlap is already guaranteed, so this only
    filters answer *size*, not validity. One anchor yields at most one instance, for
    entity variety.
    """
    specs = list(placeholders.values())
    anchor, partner = specs[0], specs[1]
    if anchor["sample"] != "paired" or partner["sample"] != "paired":
        raise NotImplementedError(f"{tpl['id']}: two-placeholder templates require sample: paired on both")
    if tpl["scoring"] != "set_match":
        # Boolean path-existence (type 09) is also paired but needs true/false label
        # balancing rather than answer-size bounding — its own increment.
        raise NotImplementedError(f"{tpl['id']}: paired scoring {tpl['scoring']!r} not yet supported")

    min_answer = tpl.get("min_answer", 1)
    max_answer = tpl.get("max_answer")
    anchor_pool = has_edge_candidates(
        anchor["node_type"], anchor["edge"], endpoint=endpoint,
        target_type=anchor.get("target_type"),
        min_fan=anchor.get("min_fan"), max_fan=anchor.get("max_fan"),
    )
    rng.shuffle(anchor_pool)

    instances = []
    for a_uri, a_label in anchor_pool:
        if len(instances) >= tpl["count"]:
            break
        partner_pool = paired_candidates(
            a_uri, partner, endpoint=endpoint,
            target_type=partner.get("target_type"),
            min_overlap=partner.get("min_overlap"), max_overlap=partner.get("max_overlap"),
        )
        rng.shuffle(partner_pool)
        for b_uri, b_label in partner_pool[:PARTNER_ATTEMPT_CAP]:
            query = rewrite_values(rewrite_values(rq_text, anchor["bind_var"], a_uri), partner["bind_var"], b_uri)
            gt = shape_ground_truth(run_query(query, endpoint=endpoint), tpl["answer_var"], tpl["scoring"])
            if len(gt) >= min_answer and (max_answer is None or len(gt) <= max_answer):
                instances.append(
                    {
                        "seeds": [_seed_entry(anchor, a_uri, a_label), _seed_entry(partner, b_uri, b_label)],
                        "ground_truth": gt,
                    }
                )
                break  # one partner per anchor — move on for variety
    if len(instances) < tpl["count"]:
        print(f"  ! {tpl['id']}: found {len(instances)} bounded pairs of {tpl['count']} requested")
    return instances


def instantiate(tpl: dict, *, seed: str, endpoint: str) -> list[dict]:
    """Sample entities for one template and return its questions.jsonl records."""
    placeholders = tpl.get("placeholders") or {}
    if "count" not in tpl:
        sys.exit(f"{tpl['id']}: template is missing a `count:` field")

    # Per-template RNG keyed on (seed, template_id): adding or reordering templates
    # never reshuffles another template's draws.
    rng = random.Random(f"{seed}:{tpl['id']}")
    rq_text = tpl["_rq_path"].read_text()

    if len(placeholders) == 1:
        instances = sample_single(tpl, next(iter(placeholders.values())), rq_text, rng, endpoint)
    elif len(placeholders) == 2:
        instances = sample_paired(tpl, placeholders, rq_text, rng, endpoint)
    else:
        raise NotImplementedError(f"{tpl['id']}: {len(placeholders)} placeholders not supported")

    records = []
    for i, inst in enumerate(instances):
        question = tpl["question"]
        for s in inst["seeds"]:
            question = question.replace(f"{{{s['label_into']}}}", s["label"])
        records.append(
            {
                "question_id": f"{tpl['type']}__{tpl['id']}__{i:02d}",
                "type_id": tpl["type"],
                "template_id": tpl["id"],
                "question": question,
                "scoring": tpl["scoring"],
                "answer_var": tpl["answer_var"],
                "ground_truth": inst["ground_truth"],
                # Strip the internal label_into; it's a substitution aid, not provenance.
                "seeds": [{k: s[k] for k in ("bind_var", "label", "uri")} for s in inst["seeds"]],
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
