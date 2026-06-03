# Eval

This directory owns the evaluation design for the benchmark: the question type
taxonomy, the target question distribution, the architectural separation of the
eval pipeline, and the per-type scoring strategy. The root `README.md` owns the
hypotheses (H1–H7), architecture overview, release strategy, and build order;
this file is the authoritative source for eval design detail.

Until an `eval/templates/` folder exists, the taxonomy and per-template detail
live here. When that folder is created, taxonomy detail and per-template
examples may move to `eval/templates/README.md` and this file will link to it.

## Question type taxonomy

The taxonomy contains exactly ten types. Each maps to a primary hypothesis and a
predicted winner. The taxonomy is defined by graph-theoretic complexity, not by
surface phrasing — two surface-different questions of the same type test the same
retrieval capability.

| # | `type_id` | Type | Graph operation | Predicted winner | Primary hypothesis |
|---|-----------|------|-----------------|------------------|--------------------|
| 1 | `01_0hop_attribute` | 0-hop attribute | Node property lookup | Tie / closed-book | H7 |
| 2 | `02_1hop_factoid` | 1-hop factoid | Single edge traversal | Tie or vector by tokens | H1, H7 |
| 3 | `03_2hop_traversal` | 2-hop traversal | Two edges chained | Graph | H3 |
| 4 | `04_3plus_hop_traversal` | 3+ hop traversal | Three or more edges | Graph (decisively) | H3 |
| 5 | `05_aggregative` | Aggregative (count/min/max) | Aggregation over edges | Graph | H3 |
| 6 | `06_set_intersection` | Set intersection | Two traversals, intersection | Graph | H3 |
| 7 | `07_set_difference` | Set difference | Two traversals, complement | Graph | H2, H3 |
| 8 | `08_negative_unanswerable` | Negative / unanswerable | Edge does not exist | Graph (vector hallucinates) | H2 |
| 9 | `09_path_existence` | Path existence | Reachability between nodes | Graph | H3, H6 |
| 10 | `10_fuzzy_semantic` | Fuzzy / semantic | No graph operation; matches discourse | Vector | H4 |

**Note on filtered traversal.** Property-predicate filtering on top of edge
traversal is intentionally absorbed into types 3 and 4. If a template requires
both edge traversal and a property predicate, classify by edge count.

A finite, structurally-defined taxonomy makes the eval auditable and findings
precisely framed: each finding references a specific question type by number, and
each type traces back to a hypothesis.

## Target distribution

Target ~58 questions total, weighted toward thesis-bearing categories — the types
where a hypothesis predicts a material advantage to one retriever.

| Type | Target count |
|------|--------------|
| 0-hop attribute | 3 |
| 1-hop factoid | 5 |
| 2-hop traversal | 7 |
| 3+ hop traversal | 8 |
| Aggregative | 8 |
| Set intersection | 5 |
| Set difference | 5 |
| Negative / unanswerable | 7 |
| Path existence | 4 |
| Fuzzy / semantic | 6 |
| **Total** | **58** |

Types 3–9 are where the core thesis is tested, so they get higher per-category
counts for stronger statistical signal. Types 1, 2, and 10 are tie- or
vector-favoring; smaller samples suffice because the hypothesis is "they perform
similarly" rather than "graph wins by X." Exact counts are targets, not
contracts — final counts may differ within ±2 per category after template
authoring.

## Architectural concerns

The eval system has three pipeline stages, organized as separate concerns within
`eval/`. Each has different runtime characteristics, inputs, outputs, and
evolution timelines, so they remain visibly distinct with their own READMEs where
warranted.

1. **Eval set production.** Takes hand-authored templates plus the Hetionet
   graph, produces a frozen eval set (`questions.jsonl`) with ground truth. Runs
   once per dataset version. Reproducible via seeded sampling.
2. **Eval harness.** Loads `questions.jsonl`, runs each registered retriever +
   generator combination against each question, records structured per-question
   telemetry. Runs once per system-under-test.
3. **Judging.** Scores system outputs against ground truth. Type-aware:
   deterministic scoring for nine of ten question types; LLM-as-judge only for
   fuzzy/semantic.

The exact folder layout is determined when implementation begins (build order
step 3+). The three concerns should remain visibly distinct. Top-level
eval-related folders outside `eval/` are avoided — all eval concerns live under
`eval/`.

Judges follow the same pluggable protocol pattern as `retrievers/`: a `base.py`
protocol plus concrete implementations per type.

This mirrors the pattern already used in `ingest/` (`rdf/` and `vector/` as
sibling concerns) and `retrievers/` (`base.py` + pluggable implementations).
Mixing production, running, and judging into one flat folder will not scale as
the eval grows.

## Judging

Deterministic scoring is more reliable than LLM-judge scoring where feasible, so
the LLM judge is reserved for cases where surface-form variation genuinely
requires it.

| Type | Scoring | LLM judge needed? |
|------|---------|-------------------|
| 0-hop attribute | String match against graph property | No |
| 1-hop factoid | Set comparison vs graph traversal result | No |
| 2-hop traversal | Set comparison | No |
| 3+ hop traversal | Set comparison | No |
| Aggregative | Numerical exact match | No |
| Set intersection | Set comparison | No |
| Set difference | Set comparison | No |
| Negative / unanswerable | Binary: refused or hallucinated | No |
| Path existence | Boolean | No |
| Fuzzy / semantic | Semantic equivalence | Yes |

**Entity extraction** from natural-language answers defaults to synonym-aware
string matching using Hetionet's recorded labels and synonyms. Where synonym
matching proves too brittle (high false-negative rate on manual spot-check),
escalate to LLM-assisted entity linking for that specific question type.

**Calibration.** For fuzzy/semantic, hold out ~20 questions for human spot-check.
Manually grade them, compute Cohen's kappa against the LLM judge's grades, and
report kappa in the release notes. Trust the LLM judge for the remainder if
kappa > 0.7; redesign otherwise.
