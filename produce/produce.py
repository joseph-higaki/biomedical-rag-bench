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

All sample modes are supported: single-placeholder `has_edge` (01/02/05, with an
optional multi-hop answer post-check for 03/04), `lacks_edge` (08), `paired` set
(06/07), `paired` boolean (09), and 0-placeholder fixed (10). See the build-increment
table in produce/README.md.

    uv run --extra produce python produce/produce.py \\
        --template genes_expressed_in_anatomy --out /tmp/q.jsonl

`--explain` emits a markdown worked-example trace (candidate query, seeded pick,
instantiated query, answer, record) instead of producing questions; see `make explain`.
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
# folder (produce/), so we reach the seam by putting the templates dir on the
# path rather than duplicating it. If a third consumer appears, extract run_query to
# a shared eval module; one sys.path insert doesn't yet justify that refactor.
TEMPLATES_DIR = Path(__file__).parent / "templates"
sys.path.insert(0, str(TEMPLATES_DIR))
from run_ground_truth import DEFAULT_GRAPHDB_ENDPOINT, run_query  # noqa: E402

DEFAULT_OUT = Path(__file__).parent / "questions.jsonl"
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


def _run_pool(query: str, *, endpoint: str) -> list[tuple[str, str]]:
    """Run a candidate query and dedup its rows to (uri, label) pairs.

    Every sample mode's candidate query selects `?e` (entity URI) and `?label` and is
    `ORDER BY`'d, so keeping the first label per entity is deterministic. Shared by all
    four candidate queries so the dedup rule lives in one place.
    """
    pool: dict[str, str] = {}
    for row in run_query(query, endpoint=endpoint):
        pool.setdefault(row["e"], row["label"])
    return list(pool.items())


def has_edge_query(
    node_type: str,
    edge: str,
    *,
    target_type: str | None = None,
    min_fan: int | None = None,
    max_fan: int | None = None,
) -> str:
    """Build the `has_edge` candidate query. See `has_edge_candidates` for the rationale.

    Split from execution so `--explain` can display the exact SPARQL the producer runs.
    """
    target_constraint = f"\n     ?o a {target_type} ." if target_type else ""
    having = []
    if min_fan is not None:
        having.append(f"COUNT(DISTINCT ?o) >= {min_fan}")
    if max_fan is not None:
        having.append(f"COUNT(DISTINCT ?o) <= {max_fan}")
    having_clause = f"\nHAVING ({' && '.join(having)})" if having else ""
    return f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {{
  ?e a {node_type} ;
     {edge} ?o ;
     rdfs:label ?label .{target_constraint}
}}
GROUP BY ?e ?label{having_clause}
ORDER BY ?e ?label"""


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
    return _run_pool(
        has_edge_query(node_type, edge, target_type=target_type, min_fan=min_fan, max_fan=max_fan),
        endpoint=endpoint,
    )


def lacks_edge_query(
    node_type: str,
    edge: str,
    presence_edge: str,
    *,
    min_presence_fan: int | None = None,
) -> str:
    """Build the `lacks_edge` candidate query. See `lacks_edge_candidates` for the rationale."""
    having = (
        f"\nHAVING (COUNT(DISTINCT ?p) >= {min_presence_fan})" if min_presence_fan else ""
    )
    return f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?p) AS ?pfan) WHERE {{
  ?e a {node_type} ;
     {presence_edge} ?p ;
     rdfs:label ?label .
  FILTER NOT EXISTS {{ ?e {edge} ?x }}
}}
GROUP BY ?e ?label{having}
ORDER BY ?e ?label"""


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
    return _run_pool(
        lacks_edge_query(node_type, edge, presence_edge, min_presence_fan=min_presence_fan),
        endpoint=endpoint,
    )


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


def paired_query(
    anchor_uri: str,
    partner_edge: str,
    partner_node_type: str,
    *,
    target_type: str | None = None,
    min_overlap: int | None = None,
    max_overlap: int | None = None,
) -> str:
    """Build the `paired` overlap candidate query. See `paired_candidates` for the rationale."""
    having = []
    if min_overlap is not None:
        having.append(f"COUNT(DISTINCT ?shared) >= {min_overlap}")
    if max_overlap is not None:
        having.append(f"COUNT(DISTINCT ?shared) <= {max_overlap}")
    having_clause = f"\nHAVING ({' && '.join(having)})" if having else ""

    # Mirror the .rq's object-type filter so the overlap count matches the actual
    # intersection (see has_edge_query: participates is polymorphic).
    target_constraint = f"\n  ?shared a {target_type} ." if target_type else ""
    return f"""{PREFIXES}
SELECT ?e ?label (COUNT(DISTINCT ?shared) AS ?overlap) WHERE {{
  <{anchor_uri}> {partner_edge} ?shared .
  ?e {partner_edge} ?shared ;
     a {partner_node_type} ;
     rdfs:label ?label .{target_constraint}
  FILTER (?e != <{anchor_uri}>)
}}
GROUP BY ?e ?label{having_clause}
ORDER BY ?e ?label"""


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
    return _run_pool(
        paired_query(
            anchor_uri, partner["edge"], partner["node_type"],
            target_type=target_type, min_overlap=min_overlap, max_overlap=max_overlap,
        ),
        endpoint=endpoint,
    )


def bridge_query(anchor_uri: str, anchor_edge: str, partner_edge: str, partner_node_type: str, *, exists: bool) -> str:
    """Build the type-09 `bridge` candidate query. See `bridge_candidates` for the rationale."""
    pe, pnt = partner_edge, partner_node_type
    if exists:
        body = f"""  <{anchor_uri}> {anchor_edge} ?bridge .
  ?e {pe} ?bridge ;
     a {pnt} ;
     rdfs:label ?label ."""
    else:
        body = f"""  ?e a {pnt} ;
     {pe} ?anyTarget ;
     rdfs:label ?label .
  FILTER NOT EXISTS {{
    <{anchor_uri}> {anchor_edge} ?bridge .
    ?e {pe} ?bridge .
  }}"""
    return f"""{PREFIXES}
SELECT DISTINCT ?e ?label WHERE {{
{body}
}}
ORDER BY ?e ?label"""


def bridge_candidates(anchor_uri: str, anchor_edge: str, partner: dict, *, exists: bool, endpoint: str) -> list[tuple[str, str]]:
    """Partners (dis)connected from the anchor through a shared bridge node (type 09).

    Path existence asks whether anchor and partner reach a common node via *different*
    edges — compound `binds` a gene, disease `associates` that same gene. Unlike 06/07
    (one shared edge), the two sides use distinct edges, so this is its own query.

    `exists=True`  -> partners that DO share a bridge node (the ASK will be true).
    `exists=False` -> partners that have their own edge (well-attested) but share NO
                       bridge with the anchor (the ASK will be false).

    A boolean type needs both, or the label carries no signal. We mirror the .rq's
    property path (`binds / ^associates`), which applies no node-type filter, so neither
    do we.
    """
    return _run_pool(
        bridge_query(anchor_uri, anchor_edge, partner["edge"], partner["node_type"], exists=exists),
        endpoint=endpoint,
    )


def _seed_entry(spec: dict, uri: str, label: str) -> dict:
    """One seed binding, carrying label_into for question-text substitution (stripped before write)."""
    return {"bind_var": spec["bind_var"], "label": label, "uri": uri, "label_into": spec["label_into"]}


def sample_fixed(tpl: dict, rq_text: str, endpoint: str) -> list[dict]:
    """No-placeholder template (type 10 fuzzy): nothing is sampled.

    The reference entity is hand-chosen inside the .rq (a label lookup), not drawn from
    the graph — identifying the unnamed entity from the discourse is the task, so the
    question text has no blank to fill. We run the .rq once and emit a single record;
    the ground truth is the reference label the lookup returns. These templates are
    `count: 1` by definition (one fixed reference apiece).
    """
    rows = run_query(rq_text, endpoint=endpoint)
    return [{"seeds": [], "ground_truth": shape_ground_truth(rows, tpl["answer_var"], tpl["scoring"]),
             "ground_truth_query": _clean_query(rq_text)}]


def sample_single(tpl: dict, spec: dict, rq_text: str, rng: random.Random, endpoint: str) -> list[dict]:
    """Single-placeholder sampling: pick entities, run the .rq, emit one record each.

    Two regimes by whether the template sets answer-size bounds:
    - Direct (no min/max_answer): the sampled edge is the answer edge; the placeholder's fan
      bound already shaped the answer — draw `count` straight from the pool.
    - Answer post-check (min/max_answer set): answer is multi-hop, fan bound is on the wrong hop,
      so shuffle, run the .rq per candidate, keep only in-bounds until `count` collected.
    """
    pool = candidate_pool(spec, endpoint=endpoint)
    if not pool:
        sys.exit(f"{tpl['id']}: candidate pool is empty — check node_type/edge")

    def make(uri: str, label: str) -> dict:
        query = rewrite_values(rq_text, spec["bind_var"], uri)
        rows = run_query(query, endpoint=endpoint)
        return {
            "seeds": [_seed_entry(spec, uri, label)],
            "ground_truth": shape_ground_truth(rows, tpl["answer_var"], tpl["scoring"]),
            "ground_truth_query": _clean_query(query),
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
        # Boolean path-existence (type 09) is paired too, but routed to
        # sample_paired_boolean by instantiate before reaching here.
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
                        "ground_truth_query": _clean_query(query),
                    }
                )
                break  # one partner per anchor — move on for variety
    if len(instances) < tpl["count"]:
        print(f"  ! {tpl['id']}: found {len(instances)} bounded pairs of {tpl['count']} requested")
    return instances


def sample_paired_boolean(tpl: dict, placeholders: dict, rq_text: str, rng: random.Random, endpoint: str) -> list[dict]:
    """Two-placeholder boolean sampling (type 09 path existence) with label balance.

    A boolean ground truth is signal-free unless both labels appear, so we sample a
    balanced mix: `count // 2` pairs whose path exists (true) and the rest whose path
    does not (false). For each shuffled anchor we draw a partner of the still-needed
    label via `bridge_candidates(exists=...)`, then run the ASK .rq and store *its*
    result as ground truth (the .rq stays the source of truth; the bridge query only
    steers which label we go looking for). One instance per anchor, for variety.
    """
    specs = list(placeholders.values())
    anchor, partner = specs[0], specs[1]
    need = {True: tpl["count"] // 2, False: tpl["count"] - tpl["count"] // 2}

    anchor_pool = has_edge_candidates(
        anchor["node_type"], anchor["edge"], endpoint=endpoint, target_type=anchor.get("target_type"),
    )
    rng.shuffle(anchor_pool)

    instances = []
    for a_uri, a_label in anchor_pool:
        if need[True] + need[False] == 0:
            break
        # Prefer filling the true quota first; fall through to false once true is done.
        for want in (True, False):
            if need[want] <= 0:
                continue
            pool = bridge_candidates(a_uri, anchor["edge"], partner, exists=want, endpoint=endpoint)
            if not pool:
                continue
            b_uri, b_label = rng.choice(pool)
            query = rewrite_values(rewrite_values(rq_text, anchor["bind_var"], a_uri), partner["bind_var"], b_uri)
            gt = shape_ground_truth(run_query(query, endpoint=endpoint), tpl["answer_var"], tpl["scoring"])
            # The ASK must agree with the label we steered toward; if not, the bridge
            # query and the .rq disagree — skip rather than store a mislabeled pair.
            if str(gt).lower() != str(want).lower():
                print(f"  ! {tpl['id']}: ASK={gt} but steered {want} for {a_label}+{b_label}; skipping")
                continue
            instances.append(
                {
                    "seeds": [_seed_entry(anchor, a_uri, a_label), _seed_entry(partner, b_uri, b_label)],
                    "ground_truth": gt,
                    "ground_truth_query": _clean_query(query),
                }
            )
            need[want] -= 1
            break  # one instance per anchor
    if need[True] + need[False] > 0:
        print(f"  ! {tpl['id']}: short by true={need[True]} false={need[False]} of {tpl['count']}")
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

    if len(placeholders) == 0:
        instances = sample_fixed(tpl, rq_text, endpoint)
    elif len(placeholders) == 1:
        instances = sample_single(tpl, next(iter(placeholders.values())), rq_text, rng, endpoint)
    elif len(placeholders) == 2:
        if tpl["scoring"] == "boolean":
            instances = sample_paired_boolean(tpl, placeholders, rq_text, rng, endpoint)
        else:
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
                # The instantiated ground-truth SPARQL that produced `ground_truth` (VALUES
                # rewritten to the sampled URIs, comments stripped — logically identical to what
                # ran; the full .rq with frontmatter lives at templates/ground_truth/<template_id>.rq).
                # Persisted so a future analysis can diff it against graph_sparqlgen's generated
                # query (traversal_info.sparql_generated) without re-deriving from the template.
                "ground_truth_query": inst["ground_truth_query"],
                # Strip the internal label_into; it's a substitution aid, not provenance.
                "seeds": [{k: s[k] for k in ("bind_var", "label", "uri")} for s in inst["seeds"]],
                "sampling_seed": f"{seed}:{tpl['id']}",
            }
        )
    return records


# One template per taxonomy type, in type order — the curated set `--explain` renders
# into EXAMPLE.md. Types whose template count > 1 (only type 10) pick one representative;
# its siblings share the same code path and are named in that section's regime note.
EXPLAIN_ARCHETYPES = [
    "chromosome_of_gene",                               # 01 has_edge · direct · string_match
    "genes_expressed_in_anatomy",                       # 02 has_edge · direct · set_match
    "genes_associated_with_compound_treated_diseases",  # 03 has_edge · post-check · set_match
    "symptoms_of_pharmacologic_class_treated_diseases", # 04 has_edge · post-check · set_match
    "count_of_side_effects_caused_by_compound",         # 05 has_edge · direct · numerical
    "shared_pathways_of_two_genes",                     # 06 paired · set_match
    "pathways_in_one_gene_excluding_another",           # 07 paired · set_match
    "diseases_treated_by_compound_negative",            # 08 lacks_edge · binary
    "path_between_compound_and_disease_via_gene",       # 09 paired · boolean
    "first_line_type2_diabetes_drug_fuzzy",             # 10 fixed (1 of 6 fuzzy siblings)
]


def _clean_query(text: str) -> str:
    """Drop a `.rq`'s leading comment/frontmatter block and aligned trailing comments.

    For display only: comments are inert, so the shown query is logically identical to
    what ran, but without the registry frontmatter (redundant with the registry doc) or
    the stale `# <committed-seed>` trailing comment that `rewrite_values` leaves on the
    rewritten VALUES line. Aligned trailing comments use 2+ spaces, so the regex never
    touches the single `#` inside a `<...#>` IRI on a PREFIX line.
    """
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].strip() == "" or lines[i].lstrip().startswith("#")):
        i += 1
    body = [re.sub(r"\s{2,}#.*$", "", ln).rstrip() for ln in lines[i:]]
    while body and body[-1] == "":
        body.pop()
    return "\n".join(body)


def _sparql(q: str) -> str:
    return f"```sparql\n{q}\n```"


def _details(summary: str, body: str) -> str:
    return f"<details>\n<summary>{summary}</summary>\n\n{body}\n\n</details>"


def _format_answer(gt, scoring: str) -> str:
    """One-line headline of the ground truth, truncated for legibility."""
    if isinstance(gt, list):
        if not gt:
            return "**none** — the empty set; the correct response is refusal, not a guess"
        shown = ", ".join(gt[:10])
        more = f" … (+{len(gt) - 10} more)" if len(gt) > 10 else ""
        return f"**{len(gt)}** result(s) — {shown}{more}"
    return f"`{gt}`"


def explain_template(tpl: dict, *, seed: str, endpoint: str) -> str:
    """Render one template's faithful trace as a markdown section.

    Faithful by construction: the emitted record comes from `instantiate` (the real
    producer path), the candidate SPARQL from the same `*_query` builders the producer
    runs, and the instantiated `.rq` from `rewrite_values`. Nothing here re-derives the
    sampling logic — it narrates what the real functions did.
    """
    placeholders = tpl.get("placeholders") or {}
    rq_text = tpl["_rq_path"].read_text()
    records = instantiate(tpl, seed=seed, endpoint=endpoint)
    tid, type_id, scoring = tpl["id"], tpl["type"], tpl["scoring"]

    lines = [
        f'<a id="type-{type_id}"></a>',
        f"## `{type_id}` — {tid}",
        "",
        f"**Scoring:** {scoring} · **count:** {tpl['count']} · "
        f"**seed:** `{seed}:{tid}`",
        "",
    ]
    if not records:
        lines += ["_Producer emitted no instances (pool empty or bounds unmet)._", ""]
        return "\n".join(lines)

    inst = records[0]

    if len(placeholders) == 0:
        # Fixed: no placeholder, no candidate query — the reference is hand-coded in the .rq.
        lines += [
            "**1. No sampling.** This template has no `{placeholder}`: the reference "
            "entity is fixed inside the `.rq` (a label lookup). Identifying the unnamed "
            "entity from the discourse *is* the task, so there is no blank to fill.",
            "",
            f"**2. Answer** — {_format_answer(inst['ground_truth'], scoring)}",
            "",
            _details("the fixed ground-truth query (`.rq`)", _sparql(_clean_query(rq_text))),
            "",
            f"> **How this type samples:** 0-placeholder fuzzy (type 10), `count: 1` by "
            f"definition (one fixed reference). The other 5 fuzzy templates share this exact "
            f"shape — only the hand-picked reference differs.",
            "",
        ]
    elif len(placeholders) == 1:
        spec = next(iter(placeholders.values()))
        mode = spec["sample"]
        s = inst["seeds"][0]
        if mode == "has_edge":
            cand_q = has_edge_query(
                spec["node_type"], spec["edge"], target_type=spec.get("target_type"),
                min_fan=spec.get("min_fan"), max_fan=spec.get("max_fan"),
            )
            pool_n = len(candidate_pool(spec, endpoint=endpoint))
            post = tpl.get("min_answer") is not None or tpl.get("max_answer") is not None
            note = (
                f"`has_edge` **post-check** (type {type_id[:2]}): the answer is multi-hop, so "
                f"the sampled head edge doesn't bound the answer size. The producer runs the "
                f"`.rq` per candidate and keeps only answers in "
                f"`[{tpl.get('min_answer')}, {tpl.get('max_answer')}]`."
                if post else
                f"`has_edge` **direct** (type {type_id[:2]}): the sampled edge *is* the answer "
                f"edge, so the placeholder's fan bound already shaped the answer — picks are "
                f"drawn straight from the pool, no post-check."
            )
        else:  # lacks_edge
            cand_q = lacks_edge_query(
                spec["node_type"], spec["edge"], spec["presence_edge"],
                min_presence_fan=spec.get("min_presence_fan"),
            )
            pool_n = len(candidate_pool(spec, endpoint=endpoint))
            note = (
                "`lacks_edge` (type 08 negative): `FILTER NOT EXISTS` makes the answer "
                "provably empty, while `presence_edge` keeps the entity well-attested — a "
                "*tempting hallucination* for the vector retriever, not a trivial unknown (H2)."
            )
        inst_rq = rewrite_values(rq_text, spec["bind_var"], s["uri"])
        lines += [
            f"**1. Candidate pool** — sample mode `{mode}`. Pool: **{pool_n}** entities.",
            "",
            _sparql(cand_q),
            "",
            f"**2. The pick** — the seeded RNG drew **{s['label']}** (`{s['uri']}`) "
            f"from the {pool_n}-entity pool.",
            "",
            f"**3. Answer** — {_format_answer(inst['ground_truth'], scoring)}",
            "",
            _details("instantiated ground-truth query (`VALUES` rewritten)", _sparql(_clean_query(inst_rq))),
            "",
            f"> **How this type samples:** {note}",
            "",
        ]
    else:  # two placeholders: paired set or paired boolean
        specs = list(placeholders.values())
        anchor, partner = specs[0], specs[1]
        a, b = inst["seeds"][0], inst["seeds"][1]
        anchor_q = has_edge_query(
            anchor["node_type"], anchor["edge"], target_type=anchor.get("target_type"),
            min_fan=anchor.get("min_fan"), max_fan=anchor.get("max_fan"),
        )
        anchor_n = len(has_edge_candidates(
            anchor["node_type"], anchor["edge"], endpoint=endpoint,
            target_type=anchor.get("target_type"),
            min_fan=anchor.get("min_fan"), max_fan=anchor.get("max_fan"),
        ))
        if scoring == "boolean":
            exists = str(inst["ground_truth"]).lower() == "true"
            partner_q = bridge_query(
                a["uri"], anchor["edge"], partner["edge"], partner["node_type"], exists=exists,
            )
            partner_n = len(bridge_candidates(
                a["uri"], anchor["edge"], partner, exists=exists, endpoint=endpoint,
            ))
            partner_label = f"bridge query (`exists={exists}`)"
            note = (
                "`paired` **boolean** (type 09 path existence): a boolean answer is signal-free "
                "unless both labels appear, so the producer balances `count//2` true and the "
                "rest false, steering each partner via the bridge query, then stores the ASK "
                "`.rq`'s own result as ground truth."
            )
        else:
            partner_q = paired_query(
                a["uri"], partner["edge"], partner["node_type"],
                target_type=partner.get("target_type"),
                min_overlap=partner.get("min_overlap"), max_overlap=partner.get("max_overlap"),
            )
            partner_n = len(paired_candidates(
                a["uri"], partner, endpoint=endpoint, target_type=partner.get("target_type"),
                min_overlap=partner.get("min_overlap"), max_overlap=partner.get("max_overlap"),
            ))
            partner_label = "partner overlap query"
            note = (
                f"`paired` **set** (type {type_id[:2]}): two random entities almost never share "
                f"a target, so the partner query returns only co-participating entities (overlap "
                f"≥ `{partner.get('min_overlap')}`), collapsing the O(n²) pair space. One partner "
                f"per anchor whose `.rq` answer lands in bounds."
            )
        inst_rq = rewrite_values(
            rewrite_values(rq_text, anchor["bind_var"], a["uri"]), partner["bind_var"], b["uri"]
        )
        lines += [
            f"**1. Anchor pool** — `has_edge` on the first placeholder. Pool: **{anchor_n}** entities.",
            "",
            _sparql(anchor_q),
            "",
            f"**2. Anchor pick** — **{a['label']}** (`{a['uri']}`).",
            "",
            f"**3. Partner pool** — for that anchor, the {partner_label} yields **{partner_n}** "
            f"candidates; the RNG drew **{b['label']}** (`{b['uri']}`).",
            "",
            _sparql(partner_q),
            "",
            f"**4. Answer** — {_format_answer(inst['ground_truth'], scoring)}",
            "",
            _details("instantiated ground-truth query (both `VALUES` rewritten)", _sparql(_clean_query(inst_rq))),
            "",
            f"> **How this type samples:** {note}",
            "",
        ]

    lines += [
        _details("emitted questions.jsonl record", f"```json\n{json.dumps(inst, indent=2)}\n```"),
        "",
        f"**Question:** {inst.get('question') or records[0].get('question')}",
        "",
        "---",
        "",
    ]
    return "\n".join(lines)


def render_explain(template_ids: list[str], *, seed: str, endpoint: str) -> str:
    """Render the full EXAMPLE.md: GENERATED banner, table of contents, one section per type."""
    sections = []
    toc = []
    for tid in template_ids:
        tpl = load_template(tid)
        toc.append(f"- [`{tpl['type']}` — {tid}](#type-{tpl['type']})")
        print(f"Explaining {tid} ({tpl['type']}) ...", file=sys.stderr)
        sections.append(explain_template(tpl, seed=seed, endpoint=endpoint))

    header = [
        "# Producer worked examples",
        "",
        "> **GENERATED — do not edit by hand.** Produced by `produce.py --explain`"
        " (run `make explain`). One trace per taxonomy type; the SPARQL and answers are"
        " live from GraphDB at generation time, so they shift if the graph changes"
        " (same contract as the registry's committed answers).",
        "",
        "Each section traces one template end to end: the **candidate query** that defines"
        " the sampling pool, the **seeded pick**, the **instantiated ground-truth query**,"
        " the **answer**, and the emitted **record**. Verbose artifacts (full `.rq`, JSON"
        " record) are folded — click to expand. For the design behind this, see"
        " [`README.md`](README.md).",
        "",
        "## Contents",
        "",
        *toc,
        "",
        "---",
        "",
    ]
    return "\n".join(header) + "\n" + "\n".join(sections)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--template",
        action="append",
        dest="templates",
        help="template id to produce (repeatable). Default: all *.yaml templates.",
    )
    parser.add_argument(
        "--out", type=Path, default=None,
        help=f"output path. Produce mode: JSONL (default {DEFAULT_OUT}). "
        "Explain mode: markdown file (default stdout).",
    )
    parser.add_argument("--seed", default=DEFAULT_SEED, help=f"sampling seed (default {DEFAULT_SEED})")
    parser.add_argument(
        "--endpoint",
        default=DEFAULT_GRAPHDB_ENDPOINT,
        help=f"GraphDB SPARQL endpoint (default {DEFAULT_GRAPHDB_ENDPOINT})",
    )
    parser.add_argument(
        "--explain", action="store_true",
        help="emit a markdown worked-example trace instead of producing questions.jsonl. "
        "Defaults to one template per taxonomy type; narrow with --template.",
    )
    args = parser.parse_args()

    if args.explain:
        template_ids = args.templates or EXPLAIN_ARCHETYPES
        doc = render_explain(template_ids, seed=args.seed, endpoint=args.endpoint)
        if args.out:
            args.out.write_text(doc)
            print(f"Wrote worked examples for {len(template_ids)} template(s) to {args.out}", file=sys.stderr)
        else:
            print(doc)
        return

    template_ids = args.templates or sorted(p.stem for p in TEMPLATES_DIR.glob("*.yaml"))
    out = args.out or DEFAULT_OUT

    all_records: list[dict] = []
    for tid in template_ids:
        tpl = load_template(tid)
        print(f"Producing {tid} ({tpl['type']}) ...")
        all_records.extend(instantiate(tpl, seed=args.seed, endpoint=args.endpoint))

    out.write_text("\n".join(json.dumps(r) for r in all_records) + "\n")
    print(f"Wrote {len(all_records)} question(s) to {out}")


if __name__ == "__main__":
    main()
