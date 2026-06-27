# Project 2 — OBDA / Virtual Knowledge Graph (architecture decision)

**Status:** Planned (`v2.0.0`). Supersedes the earlier roadmap where Project 2 was "OWL
reasoning over RDF" — reasoning is now **Project 3**, LPG is **Project 4**. This file is the
canonical design record for Project 2; the README roadmap table points here.

> Why the renumber: OWL reasoning is a *factor that aims to change accuracy* (a measurement
> experiment, same class as Project 1). OBDA is a *serving-architecture track that aims to
> hold accuracy flat*. They are different in kind, so they get different project slots rather
> than sharing one. Reasoning keeps its prior design — a manifest factor, not a retriever
> (see Project 3 in the README and the `reasoning-factor-not-retriever` memory).

---

## What Project 2 demonstrates

**Ontology-Based Data Access (OBDA), a.k.a. the Virtual Knowledge Graph (VKG) pattern:** a
biomedical question is answered against a *meaning-rich ontology* (the TBox — classes,
properties, `rdfs:domain`/`range`, labels, definitions) that **resolves down to physically
served ABox** — possibly across heterogeneous stores — without the generator-under-test being
able to tell where the bytes came from.

It is one move along three axes that Project 1 left fixed. Keeping them named keeps the
experiment honest (varying one knob at a time):

| Axis | Project 1 (today) | Project 2 (OBDA) |
|---|---|---|
| **A — where schema knowledge comes from** | static prompt (`retrievers/sparqlgen.py:SCHEMA_PROMPT`) | retrieved from the ontology TBox |
| **B — reasoning** | `empty` (off) | stays `empty` — reasoning is *Project 3*, not this |
| **C — where the ABox physically lives** | one GraphDB | one GraphDB → one Postgres → polyglot (Postgres + lakehouse) behind a federation engine |

Project 2 moves A and C. It deliberately does **not** touch B.

---

## The defining invariant: accuracy is held at parity, not improved

This is the single most important framing and the easiest to get wrong.

**Going up the Project 2 phase ladder, answer-accuracy metrics do not aim to improve —
parity is the target ("maintain at best").** The later phases are *architectural tests*, not
retrieval-quality experiments. A phase that "didn't move accuracy" is a **PASS**, not a
failure.

The reason is structural, not aspirational: **the generator-under-test is blind to serving
topology.** If the OBDA mappings are faithful, the same question produces the same SPARQL,
the same result bindings, and therefore the same context block — whether those rows came from
GraphDB, from one Postgres, or from Postgres + an Iceberg lakehouse stitched by Trino. The
generator cannot see the difference, so it cannot reward it.

Consequences that follow directly:

- **Validation is by context-parity, not by a RAG score.** Each phase is correct iff, for
  every question, it returns the *same bindings* as the GraphDB baseline (modulo ordering).
  This is the same parity discipline already planned for the analytics spin-off (dbt replica
  vs. `load.py`), applied here to the *serving* layer. The only metric that legitimately moves
  between phases is **fidelity loss from virtualization** — rows dropped or mangled by a
  mapping gap, a type coercion, or a join-pushdown limit. That is a data-quality metric, not
  an answer-accuracy metric, and it should be reported as such.
- **Phase 2.0 (ontology querying) is the *one* phase that could legitimately move accuracy**,
  because it changes schema linking (Axis A), not just serving. On Hetionet's tiny schema (~11
  node types, ~24 edges, which already fits in the static prompt) expect ≈ parity anyway; the
  value of 2.0 is the mechanism that *scales* to ontologies that do not fit a prompt. A clean
  "no gain on a schema that fits in the prompt" result is itself a publishable finding.

---

## Development sequence (the phase ladder)

Each phase is a new retriever behind the existing `Retriever` protocol (`retrievers/base.py`),
registered in `eval/run_eval.py` — nothing else changes when adding one. This is the stated
direction of travel: **Project 2 is delivered as a series of retrievers.**

### Phase 2.0 — Ontology querying (schema-retrieval text-to-SPARQL)

The starting point. Instead of pasting the schema into the prompt, the writer **hits the TBox
instead of the ABox first**: it queries the ontology (`ontology/hetionet-schema.ttl`) to
ground the question semantically — which classes and properties are in play, their
`domain`/`range` (the directed-edge signatures, now formal rather than hand-typed), and their
`rdfs:label`/`comment`/`skos:definition` glosses — then generates the ABox query from that
retrieved, meaning-rich schema fragment.

- **ABox location:** unchanged (GraphDB).
- **What it replaces:** the static `SCHEMA_PROMPT` becomes a *projection of the committed
  TBox*, killing prompt-vs-graph drift by construction.
- **New retriever:** e.g. `retrievers/graph_obda.py` (name TBD), compared against
  `graph_sparqlgen` with the generator held fixed.
- **Accuracy expectation:** ≈ parity on Hetionet (schema fits the prompt); the win is
  scalability and drift-elimination.

### Phase 2.1 — Ontop over PostgreSQL (single relational source)

The first true OBDA serving phase, and the simplest. The ABox migrates to a single Postgres
instance; **Ontop** maps SPARQL → SQL over it via R2RML/OBDA mappings + the ontology. No
federation engine — single source means Trino is absent.

- **Architectural test.** Same SPARQL surface as 2.0, parity context.
- **New telemetry wrinkle:** a retrieval *miss* can now be a *mapping* gap, not bad SPARQL.
  The honest-miss semantics from `sparqlgen.py` must be extended so a miss is attributed to
  the right layer (LLM query vs. mapping vs. source) — additive telemetry keys only, per the
  hard constraint.

### Phase 2.2 — Ontop over Trino over (PostgreSQL, X) (polyglot)

The full polyglot demonstration. The ABox is split across **two physical stores**; **Trino**
federates them into one virtual SQL source; **Ontop** maps the ontology onto that single
Trino surface. (Ontop binds to one SQL source per instance — it does not route triples-maps
to different adapters — so spanning stores requires a federation engine *underneath* it, which
is exactly Trino's job. Ontop's own federation tutorial uses this engine-underneath pattern.)

- **Architectural test.** Parity again — the writer's SPARQL and the generator's context are
  identical to 2.1; only the physical plumbing changed.
- **Why federation underneath, not above (multiple Ontop endpoints + SPARQL `SERVICE`):**
  engine-underneath keeps a *single clean SPARQL surface*, so the writer never needs to know
  which store holds genes vs. compounds — the exact physical-layout knowledge the ontology is
  supposed to hide.

---

## Tool decisions

### Ontop — the OBDA / VKG layer

Translates one SPARQL query into one SQL query and pushes it down to a single SQL source
(R2RML/`.obda` mappings + the ontology). It is the SPARQL↔ontology layer; it is **not** a
federation engine and binds to one SQL connection per instance. Postgres, Trino, and DuckDB
are all supported dialects.

### Trino — the federation layer (Phase 2.2 only)

A federated SQL engine that presents many physical stores (Postgres + a lakehouse) as one SQL
surface for Ontop to map over. Trino speaks SQL, not SPARQL, and knows nothing of the
ontology, so it cannot replace Ontop — the two are **stacked layers**, not alternatives. Trino
appears only at 2.2; single-store 2.1 is Ontop-over-Postgres with no Trino.

> **Why Trino specifically (a deliberate, non-technical selection criterion).** This is a
> portfolio project; Trino is chosen because target employers run **Starburst** (the
> commercial Trino distribution). Recording this openly because it is a résumé-driven choice,
> not a purely technical optimum — Dremio/Denodo/Teiid are Ontop's headline federation
> partners and would serve the same architectural role.

### X (the second SQL source) — **Apache Iceberg tables on local MinIO, via Trino's Iceberg connector**

Chosen over a literal Snowflake/Databricks dependency or a Delta-Lake table. Rationale,
verified against current (2025–2026) vendor state:

- **Hits both target stacks at once.** Snowflake shipped full native Iceberg support (Apr
  2025); Databricks shipped full native Iceberg via Unity Catalog (Jun 2025); Iceberg v3 is GA
  on both in 2026. Iceberg is the **convergence/vendor-neutral** format (Apache Polaris
  catalog). Delta would signal Databricks only — keep it as the fallback if you decide to
  signal Databricks specifically.
- **Honors the project's hard rules — local-first and cost-conscious.** Snowflake and
  Databricks are cloud-only paid SaaS and would break `docker compose up`. Iceberg tables on
  local **MinIO** give the identical lakehouse semantics at zero cloud cost. Trino is a
  first-class Iceberg engine, so this is the paved path.
- **Richer architectural contrast than Postgres + DuckDB.** Postgres (OLTP row store) +
  Iceberg-on-MinIO (columnar lakehouse) is a genuine polyglot story and the more
  resume-legible one.

Suggested split: genes in Postgres, compounds in Iceberg-on-MinIO (the specific partition is
arbitrary — what matters is that one query must cross both stores).

---

## Constraints this honors (consistency check)

- **Generator stays fixed and blind.** The model under test does not vary across Project 2
  phases; it cannot perceive serving topology. (Generator-fixed-within-a-run hard constraint.)
- **Reasoning stays `empty`.** Project 2 does not touch OWL inference; that is Project 3.
- **Telemetry is additive only.** New miss-attribution and provenance keys are *added* to
  `RetrievalResult.traversal_info`; nothing is renamed or removed.
- **Question set is append-only / ground truth graph-derived.** Unchanged — the ABox is
  re-served, not re-authored.
- **Local-first, cost-conscious.** Postgres, Trino, MinIO, Ontop all run in `docker compose`;
  no cloud SaaS is a dependency.
- **No orchestration frameworks.** Each phase is a hand-rolled retriever (~one file) behind
  the `Retriever` protocol.

## Open / deferred

- Exact retriever names and registration order.
- Where the OBDA mappings (`.obda`/R2RML) and the per-phase store-loading live in the repo
  tree (a Project-2 `ingest/` sibling vs. a `serving/` root).
- The **label case-sensitivity** miss class already documented for local writers
  (`eval/llm-roles.md`) interacts with SQL-backed anchoring; resolve it at the query level
  (case-insensitive label match) when 2.1 lands.
- Whether Phase 2.0 ships before any serving migration (recommended — it is the only
  accuracy-relevant phase and needs the GraphDB baseline still in place to compare against).
