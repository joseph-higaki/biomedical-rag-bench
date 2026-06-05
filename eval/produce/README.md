# Eval producer (build step 3)

How hand-authored templates become the frozen `questions.jsonl` eval set, and the
design reasoning behind the sampler. This document is layered: read **Level 1** for
the mental model, **Level 2** for the moving parts, **Level 3** for the sampling
strategy (including the paired-sampling design shift and *why* it was needed), and
**Level 4** as a reference. Each level is self-contained; stop when you have what you
need.

Related docs: [`eval/README.md`](../README.md) owns the question *taxonomy*, target
*distribution*, and *scoring* strategy (the "what" and "why" of the eval design);
this file owns the *production mechanism* (the "how"). The generated
[`eval/templates/README.md`](../templates/README.md) is the human-readable registry
of each template's committed example seed and answer.

---

## Level 1 — The mental model (one minute)

We need ~58 benchmark questions whose answers are *known to be correct*. We refuse to
let an LLM invent questions or answers (it would hallucinate). Instead:

1. A human writes a small number of **templates** — one per question *type*. A
   template is a question with a blank in it ("Which genes are expressed in
   `{anatomy}`?") plus the **SPARQL query that computes the true answer** once the
   blank is filled.
2. The **producer** fills each blank by **sampling real entities from the Hetionet
   graph**, runs the query to get the true answer, and writes one line of
   `questions.jsonl` per filled-in question.

So the producer is a **question factory**: templates are the molds, the graph is the
raw material, and `questions.jsonl` is the output. The ground truth is never written
by hand or by an LLM — it is *computed from the graph* by the template's own query.
That is the whole point: the answers are correct by construction.

The single non-obvious part is **how to choose which entities to fill the blanks
with** so the resulting question is usable. That is the "sampling" problem, and it is
where all the complexity lives (Level 3).

---

## Level 2 — The moving parts

### Two files per template

Each question type is described by a **pair** of files in `eval/templates/`:

| File | What it is | Example |
|---|---|---|
| `<name>.yaml` | The template: question text with `{blanks}`, which scoring to use, and **how to sample** the blanks. | `genes_expressed_in_anatomy.yaml` |
| `ground_truth/<name>.rq` | The SPARQL query that computes the true answer. Has a `VALUES` line the producer rewrites with the sampled entity. | `ground_truth/genes_expressed_in_anatomy.rq` |

The `.rq` is runnable on its own (it ships with a committed example entity), which is
how step 2 validated each query by hand. The producer reuses the same `.rq` but
swaps the example entity for each sampled one.

> **Why two files?** The `.rq` must stay a standalone, runnable SPARQL query (so a
> human can paste it into GraphDB and check it). The YAML carries the producer-only
> metadata (sampling rules, scoring) that has no place inside a SPARQL file. They are
> joined by the `ground_truth:` path field in the YAML.

### The producer loop

`produce.py` does the same five steps for every template:

```
for each template:
    1. read the YAML placeholder spec (what to sample, and how)
    2. run a CANDIDATE QUERY to get a pool of valid entities
    3. seeded-sample `count` entities from that pool
    4. for each pick: rewrite the .rq's VALUES line, run it against GraphDB
    5. write one questions.jsonl record (question text + true answer + provenance)
```

Steps 1, 4, 5 are plumbing. **Step 2 — the candidate query — is the design problem**
and the subject of Level 3.

### What "filling the blank" actually means

A blank (placeholder) has **two faces**:

- its **label** fills the `{anatomy}` token in the human-readable question text;
- its **URI** is injected into the `VALUES ?anatomy { ... }` line of the SPARQL query.

So one sampled entity (say *nasal cavity*, URI `uberon:0001707`) becomes both the
words a model reads *and* the graph node the ground-truth query traverses from. That
is how the question text and its computed answer stay in lockstep.

### Reproducibility

Sampling is random but **seeded**, so the same code + seed + graph always produces
the same questions. The seed is per-template (keyed on `(seed, template_id)`), so
adding or editing one template never reshuffles another's draws.

---

## Level 3 — Sampling: the actual complexity

The producer never samples a *random* entity and hopes the answer is usable. It runs
a **candidate query** — a SPARQL query that returns *only entities for which the
answer is well-formed* — and samples from that pool. This is the "constrained
candidate-query" strategy (chosen over "sample randomly, then throw away bad ones").

Why constrained and not sample-then-reject? Because for some question types a random
entity is almost never valid (two random genes almost never share a pathway), so
rejection sampling would loop forever. Pushing the constraint *into* the query makes
the pool valid by construction — no rejection, and the seeded draw is deterministic.

There are three sampling **modes**, declared per placeholder as `sample: <mode>`:

### Mode `has_edge` — "the answer must be non-empty"

Used by types 01 (attribute), 02 (factoid), 05 (count). The candidate query returns
only nodes that actually carry the edge under test, so the answer set is never empty:

```sparql
# "anatomies that express at least one gene"
SELECT ?e ?label WHERE { ?e a hetio:Anatomy ; hetio:expresses ?o ; rdfs:label ?label . }
```

**Fan bound.** A real wrinkle surfaced immediately: "genes expressed in the central
nervous system" returns **11,261 genes** — not an enumerable question. So `has_edge`
takes optional `min_fan`/`max_fan` bounds that count the answer size per entity and
exclude hubs, via a `HAVING` clause:

```sparql
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE { ... }
GROUP BY ?e ?label HAVING (COUNT(DISTINCT ?o) >= 2 && COUNT(DISTINCT ?o) <= 25)
```

This is the *reproducible* form of what step 2 did by hand (it picked bounded seeds
like "nasal cavity" deliberately). Fan bounds apply to **set-valued** answers; they
are omitted on **numerical** types (a count of 387 side effects is still a single
number — it does not bloat the record).

### Mode `lacks_edge` — "the answer must be empty (a negative)"

Used by type 08 (negative/unanswerable). The whole point is a question whose true
answer is *nothing*, so the system should refuse. The candidate query requires the
target edge to be **absent** but a different `presence_edge` to be **present**:

```sparql
# "compounds that treat NOTHING but cause side effects" (real, studied drugs)
SELECT ?e ?label WHERE {
  ?e a hetio:Compound ; hetio:causes ?p ; rdfs:label ?label .
  FILTER NOT EXISTS { ?e hetio:treats ?x }
}
GROUP BY ?e ?label HAVING (COUNT(DISTINCT ?p) >= 10)
```

The presence constraint matters: a negative about an *unknown* compound is a trivial
"never heard of it." A negative about **Digoxin** or **Apixaban** — real drugs that
treat things in the real world but have no `treats` edge in Hetionet — is a *tempting
hallucination* for the vector retriever. That tension is the H2 test.

### Multi-hop answers (`has_edge` + an answer post-check)

Types 03 (2-hop) and 04 (3-hop) are single-placeholder `has_edge` templates, but with
a twist: the sampled head edge does **not** determine the answer. Sampling a compound
that `treats` something says nothing about how many *genes* are two hops away — a
treated disease may associate zero genes, or hundreds. So the fan bound (which counts
the head edge) is on the wrong hop, and `has_edge` alone neither guarantees a non-empty
answer nor bounds its size.

The fix lives in the producer, not a new candidate query: when a template declares
`min_answer`/`max_answer`, `sample_single` switches from "take `count` picks directly"
to "shuffle candidates, run the real `.rq` per candidate, and keep only those whose
answer lands in bounds, until `count` are collected." Same bound-check shape as
`paired`. Single-hop types (01/02/05) omit the bounds and use the direct path, because
there the sampled edge *is* the answer edge and the fan bound already shaped it.

### Mode `paired` — "two entities with a non-empty intersection/difference"

Used by types 06 (intersection) and 07 (difference). This is the hard one, and where
the design shifted. **Read the next section for the full story.**

---

## Level 3.5 — The paired-sampling design shift (what changed and why)

Pair sampling went through **two** bugs, each instructive. Both come down to a single
principle stated at the end. Concrete numbers below are from this codebase against the
full Hetionet graph.

### The naive design

Types 06/07 sample a *pair* of genes and ask about the overlap (06) or the difference
(07) of their pathway sets. The first implementation was:

1. Sample an anchor gene **A** (any gene that participates in pathways).
2. Query for partner candidates **B** that share ≥1 participates-target with A (the
   structurally hard constraint — random gene pairs almost never overlap).
3. For each partner, **run the ground-truth `.rq` and check the answer size**; accept
   the first whose answer lands in `[min_answer, max_answer]`.

### Bug 1 — the unbounded-anchor explosion (max_answer)

The first run nearly hung: step 3 runs a SPARQL round-trip **per partner**, and with
the anchor unbounded, a *hub* anchor poisons the loop. BRCA1 participates in hundreds
of pathways and shares pathways with **10,146 genes**; its intersection/difference
with nearly any partner is far bigger than 25, so the size check rejects partner after
partner — each a separate query. ~10,000 wasted queries for one anchor.

**Fix — bound the anchor's own fan.** A set-size fact: for anchor A and partner B,
writing `|A|` for "number of pathways A is in":

- **intersection** `|A ∩ B| ≤ |A|` — you can't share more than you have.
- **difference** `|A − B| = |A| − |A ∩ B| ≤ |A|` — removing shared items only shrinks A.

Both answers are **capped by `|A|`**. Sample only anchors with `|A| ≤ 25` (a `max_fan`
bound on the anchor placeholder, reusing `has_edge`) and the answer is guaranteed ≤ 25
for *every* partner — the `max_answer` rejection vanishes before we look at a partner.

### Bug 2 — the polymorphic-edge mismatch (min_answer)

After Bug 1 the run still took **~2.5 minutes**. A profile (`time` showed it was
CPU-bound, not network-bound — the first clue) revealed **1,211 `.rq` calls** to place
just 10 questions: ~110 *rejected* partners per anchor, despite a `min_overlap: 2`
filter on the pairing query that should have made every partner valid.

The cause: **`hetio:participates` is polymorphic.** It connects a gene to four node
types, and Pathway is the *minority*:

```
559,504  BiologicalProcess
 97,222  MolecularFunction
 84,372  Pathway          <- the only type the .rq counts
 73,566  CellularComponent
```

The pairing query counted shared participates-*targets* (mostly Biological Processes);
the `.rq` counts shared **Pathways**. So `overlap ≥ 2` was usually satisfied by two
shared Biological Processes while the Pathway intersection was 0 — and the per-partner
`.rq` rejected it. `min_overlap`, `min_fan`, `max_fan` were all counting the wrong
thing.

**Fix — mirror the `.rq`'s type filter in the candidate queries.** A `target_type:
hetio:Pathway` on the placeholder adds `?o a hetio:Pathway` (and `?shared a
hetio:Pathway`) to the candidate/pairing queries, so the overlap count *is* the
intersection size. Now `min_overlap: 2` makes every partner valid, the `.rq` runs
about once per anchor, and the same workload drops from **~2.5 min to ~3 s** (≈50×).

A backstop guard, `PARTNER_ATTEMPT_CAP` (default 200), caps partners tried per anchor
so no future template can reproduce an explosion regardless of its math.

### The one principle

Both bugs are the same mistake: **a candidate/pairing query must mirror every
constraint the `.rq` applies.** When it doesn't, the sampled pool — and any count
derived from it (fan, overlap) — diverges from the actual answer, and the producer
pays for the gap in per-candidate rejection. The producer stays type-*agnostic*
(it never computes the answer from overlap — the `.rq` remains the single source of
ground truth); the *template* declares the constraints (`target_type`, `min_overlap`,
fan bounds) that keep the pool faithful to its query.

### Why none of this biases the eval

These bounds change *which* entities get sampled, never *how* the answer is computed —
the answer always comes from running the real `.rq`. They encode a deliberate
eval-design choice ("questions must be enumerable and well-formed"), the same choice
step 2 made by hand-picking bounded seeds. Every bound lives in the template YAML,
versioned and reproducible.

---

## Level 4 — Reference

### `questions.jsonl` record schema

One JSON object per line:

| Field | Meaning |
|---|---|
| `question_id` | `<type_id>__<template_id>__<NN>` — stable, sortable. |
| `type_id` | Taxonomy type (e.g. `06_set_intersection`). |
| `template_id` | Which template produced it. |
| `question` | The instantiated natural-language question (blanks filled). |
| `scoring` | How the judge scores it (`set_match`, `numerical`, `string_match`, `boolean`, `binary`, `semantic`). |
| `answer_var` | Which SPARQL SELECT column carries the answer. |
| `ground_truth` | The computed true answer. A **sorted list** for set/binary types (empty `[]` = a negative), a **scalar** for numerical/string/boolean. |
| `seeds` | The sampled entities: `[{bind_var, label, uri}]` (two entries for paired types). Provenance for re-deriving the question. |
| `sampling_seed` | The per-template RNG key, for reproducibility. |

The rewritten query is **not** stored — it is reconstructable from `(template +
seeds)`, so storing it would be redundant bloat.

### Per-template YAML fields the producer reads

| Field | Where | Meaning |
|---|---|---|
| `count` | template | How many instances to produce (the type's target from `eval/README.md`). |
| `scoring`, `answer_var` | template | Scoring type; which SELECT column is the answer. |
| `min_answer`, `max_answer` | template | Bounds on the final answer size for paired types. |
| `placeholders.<name>.node_type` | placeholder | RDF type to sample (`hetio:Gene`, …). |
| `placeholders.<name>.sample` | placeholder | `has_edge` \| `lacks_edge` \| `paired`. |
| `placeholders.<name>.edge` | placeholder | The edge under test. |
| `placeholders.<name>.target_type` | placeholder | Constrains the edge's *object* type, mirroring a type filter in the `.rq`. Required for polymorphic edges like `hetio:participates`; omit for monomorphic edges. |
| `placeholders.<name>.min_fan` / `max_fan` | placeholder | Fan bounds on the sampled entity's answer (keeps sets enumerable; bounds the anchor — hence the answer — in paired types). |
| `placeholders.<name>.min_overlap` / `max_overlap` | placeholder | (`paired` partner only) bounds how many `target_type` objects the pair must share; pre-validates the pool so the `.rq` runs ~once per anchor. |
| `placeholders.<name>.presence_edge` / `min_presence_fan` | placeholder | (`lacks_edge` only) edge the entity must *have* so it stays well-attested. |
| `placeholders.<name>.bind_var` | placeholder | The `?var` in the `.rq`'s `VALUES` line to rewrite. |
| `placeholders.<name>.label_into` | placeholder | The `{token}` in the question text to fill with the label. |

### Sample-mode → candidate-query map

| Mode | Used by types | Pool constraint |
|---|---|---|
| `has_edge` | 01, 02, 05 | node carries `edge`; optional fan bound |
| `lacks_edge` | 08 | node lacks `edge` but has `presence_edge` |
| `paired` | 06, 07 | fan-bounded anchor + partner sharing ≥1 `edge`-target |

Type **09** (path existence, boolean) is also paired but needs *true/false label
balancing* rather than answer-size bounding — its own increment, not yet implemented.
Type **10** (fuzzy/semantic) is **not sampled**: the answer entity is intentionally
not named in the question, so those ~6 instances are hand-authored 1:1.

### Running it

```bash
# One template (isolated smoke):
uv run --extra produce python eval/produce/produce.py \
    --template genes_expressed_in_anatomy --out /tmp/q.jsonl

# All templates -> eval/questions.jsonl (the real artifact):
uv run --extra produce python eval/produce/produce.py
```

GraphDB (the full Hetionet graph) must be running; override the endpoint with
`--endpoint` or `GRAPHDB_ENDPOINT`. The producer reuses `run_query` from
[`eval/templates/run_ground_truth.py`](../templates/run_ground_truth.py) — the single
GraphDB execution seam shared with the registry generator.

### Build-increment status

| Increment | Sample mode(s) | Types | State |
|---|---|---|---|
| 1–2 | `has_edge` (single placeholder) | 01, 02, 05 | done |
| 3 | `lacks_edge` | 08 | done |
| 4 | `paired` + anchor fan bound + `target_type` | 06, 07 | done |
| 5 | multi-hop single placeholder + answer post-check | 03, 04 | done |
| 6 | `paired` + true/false balance | 09 | pending |
| — | hand-authored (not sampled) | 10 | pending |
