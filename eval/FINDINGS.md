# Eval findings — curated observations

Hand-authored, durable interpretation of eval runs. **This file is never written by
`--run`** — it is the home for observations that must survive future runs. Append a dated
entry per run worth recording; don't rewrite history.

The companion `eval/LATEST_RUN.md` is the opposite: a *generated* snapshot of the most
recent `--run`, overwritten every time. The machine-readable rows live in
`eval/results/*.jsonl` (gitignored); definitive accuracy / recall / H7 metrics come from
the analysis notebook + dashboard that read those rows. This file is the connective tissue
— what a run *meant*, not its raw tables.

When an observation hardens from "this run showed X" into "this is how the benchmark
behaves," promote it to `eval/README.md` (the methodology reference). Findings graduate.

---

## Validity caveats (how to read specific conditions)

- **Closed-book is structurally torn on unanswerables (type 08).** One constant system
  prompt — held identical across all retriever conditions for comparability — cannot
  simultaneously tell the model "answer from your own knowledge, don't refuse for lack of
  context" (correct for knowledge questions 01–07/09) and "refuse, the answer set is empty"
  (correct for the unanswerable type 08). Whichever way the prompt leans, closed-book pays
  on the other side: lean toward refusing and it under-answers the knowledge questions;
  lean toward answering (current prompt) and it *hallucinates* on type 08. **This is not a
  prompt bug to tune away — it is evidence for H7.** A retriever that supplies type 08's
  actual (empty) result set is exactly what lets the model answer "None" correctly. Do not
  read closed-book's type-08 score as a knowledge measure; read it as the baseline that
  retrieval is meant to fix. Don't re-tune the prompt to chase it (and the prompt must stay
  constant across conditions regardless).

- **Type 08 rewards empty context — read it conditionally.** The unanswerable type passes
  when the model asserts "None". A retriever that supplies *no relevant content* refuses by
  default and so scores high on 08 for the wrong reason: the `vector` smoke store (28
  abstracts) got **7/7 on 08 while scoring 0 on every content question (02–07)**. A high 08
  score is therefore only meaningful for a retriever that *otherwise retrieves*. The analysis
  layer must not rank retrievers on aggregate accuracy without isolating this, or it will
  rate a useless retriever highly. Read 08 alongside whether the retriever had real content.
  **Demonstrated directly:** rebuilding `vector` on a real entity-covering corpus dropped 08
  from 7/7 → 4/7 (the refuse-on-empty crutch removed) while content questions stayed 0, so the
  *fairer* corpus *lowered* the headline (11 → 8/52). Aggregate accuracy is the wrong top-line.

- **More hops is not more capability — `hops` and the fan caps are coupled.** At the default
  caps (`max_per_predicate=25`, `max_triples=200`, tuned for 1 hop), raising `hops` 1→2 is a
  **net loss**: `graph_neighborhood_2hop` scored 12/52 vs `1hop`'s 13/52 at **2.6× the input
  tokens and 2.7× tokens-per-correct**. The 200-triple budget fills with 2-hop fan-out,
  *burying* the 1-hop answer (type 02 collapses 5/5 → 1/5) while barely unlocking 2-hop (03:
  0 → 1/7). Read `2hop` as a cautionary negative result, not "the deeper graph condition." A
  hop bump needs a proportional cap bump (a joint hops×caps sweep) — or the structural answer
  (query execution, `graph_sparqlgen`). `graph_neighborhood_1hop` is the honest neighborhood
  baseline.

---

## Run log (newest first)

### 2026-06-08 (later) — `vector` on the real targeted corpus (run `20260608T161819`)

Built a targeted vector corpus — every question-seed entity (61) + 1,500 random distractors
→ 1,893 entity files → **10,735 chunks** in `data/chroma` (commits `e367508` parser fix that
had been silently excluding all genes/compounds, `ff3560f` seeded selection, `2fa29a1`
batched build + default re-point). Re-ran `vector` against it — **the first *fair*
dense-retrieval arm** (the earlier 11/52 was the 28-abstract smoke store).

| type | closed | vec(smoke) | **vec(real)** | graph_1hop |
|---|---|---|---|---|
| 02_1hop_factoid | 0/5 | 0/5 | **0/5** | 5/5 |
| 08_negative_unanswerable | 0/7 | 7/7 | **4/7** | 4/7 |
| **total** | 4/52 | 11/52 | **8/52** | 13/52 |

1. **Dense literature retrieval cannot answer structured graph questions even with full entity
   coverage.** `vec(real)` is **0/52 on every content question (02–07)** though the corpus now
   contains every question entity. Worked example — *"Which genes are expressed in semicircular
   canal?"* (truth: 11 Hetionet genes): vector retrieved 5 topically-relevant abstracts and the
   model answered `tmc1 / tmc2a / …` — TMC/hearing genes named *in the abstract prose*, not the
   Hetionet expressed-in set (F1=0.00). The answer is a graph *relationship*, not a sentence in
   any abstract; topical similarity returns plausible-but-wrong sets. **The benchmark's thesis
   (H2/H4/H7), now demonstrated with a fair corpus** — not an artifact of a thin store.

2. **A fairer corpus *lowered* the headline (11 → 8) — the type-08 artifact, demonstrated**
   (→ caveat above). The smoke store's extra points were refuse-on-empty passes on 08; real
   content removes that crutch (7/7 → 4/7) while content stays 0, so the net is a drop.

`graph_neighborhood_1hop` (13/52) **remains the only arm that answers structured questions**
(02: 5/5) — the neighborhood literally contains the relationships vector's prose can't encode.
The fair vector arm *sharpens* the graph's advantage rather than closing it.

> The full-set entry below still lists `vector` at 11/52 (smoke); `vec(real)` 8/52 above is now
> the canonical vector arm. The other three conditions are unchanged.

### 2026-06-08 — full deterministic set (52 q), all four conditions (`claude-haiku-4-5`)

The first statistically meaningful cross-retriever run: all 52 deterministic-judged
questions (3–8 per type; the 6 `semantic` type-10 questions excluded — no LLM judge yet),
same generator/prompt, only the retriever varies. Runs: `closed_book` `20260608T123559`,
`vector` `20260608T123740`, `graph_neighborhood_1hop` `20260608T123906`,
`graph_neighborhood_2hop` `20260608T124417`. **Supersedes the n=1 smoke entries** (those
just proved the loop ran; this has denominators).

| type | closed | vector | 1hop | 2hop |
|---|---|---|---|---|
| 01_0hop_attribute | 2/3 | 2/3 | 3/3 | 3/3 |
| 02_1hop_factoid | 0/5 | 0/5 | **5/5** | 1/5 |
| 03_2hop_traversal | 0/7 | 0/7 | 0/7 | 1/7 |
| 04_3plus_hop_traversal | 0/8 | 0/8 | 0/8 | 0/8 |
| 05_aggregative | 0/8 | 0/8 | 0/8 | 0/8 |
| 06_set_intersection | 0/5 | 0/5 | 0/5 | 0/5 |
| 07_set_difference | 0/5 | 0/5 | 0/5 | 0/5 |
| 08_negative_unanswerable | 0/7 | 7/7 | 4/7 | 6/7 |
| 09_path_existence | 2/4 | 2/4 | 1/4 | 1/4 |
| **passed** | **4/52** | **11/52** | **13/52** | **12/52** |
| input tok / q | 173 | 1421 | 929 | 2427 |
| tok / correct answer | 4375 | 7026 | **4073** | 10962 |

1. **`1hop` is the sweet spot; `2hop` is strictly dominated** — fewer correct (12 vs 13) at
   2.6× the input tokens and 2.7× the cost per correct answer. Naively bumping hops was a net
   loss (→ the coupled-knobs caveat above). The most important and least obvious result here.

2. **The 1-hop factoid is H7 confirmed at n=5** — closed 0/5, vector 0/5, **1hop 5/5**. When
   the answer *is* a 1-hop neighborhood, retrieval takes the model from total failure to
   perfect, and neither parametric nor (smoke) vector retrieval comes close.

3. **Deep-structural questions are unreachable by neighborhood dumping at any tested budget.**
   04 (3+hop), 05 (aggregation), 06/07 (set ops) are **0 across all four conditions**, and 09
   (path) is *worse* with graph (1/4) than baseline (2/4) — the bounded neighborhood lacks the
   path, so the model says "No" (false negative). Aggregation and path-existence need query
   *execution* (COUNT, ASK), not a context dump. **The multi-question mechanism case for
   `graph_sparqlgen`** — a tuning gap could be swept away; a mechanism gap can't.

4. **Two scores are artifacts (→ caveats above).** `vector`'s 11/52 is *entirely* parametric
   fallback (01) + refuse-on-empty (08) + lucky polarity (09), with **0 from real retrieval
   (02–07)**. And type 08 rewards empty context, inflating any content-poor retriever.

5. **First run under crash-safe streaming + per-question error isolation** (commit `a922768`).
   The prior `2hop` full run was lost to a transient Anthropic API error mid-batch; this one
   carries `err=0`, and a future blip would isolate as an unscored row rather than discard 51
   good ones.

**The takeaway:** `graph_neighborhood_1hop` is the real baseline-beater and the honest
neighborhood condition; `2hop` is a documented negative result; `vector` needs a real corpus
before it counts; and the all-zero structural types are the concrete argument for building
`graph_sparqlgen` next.

> **Superseded — n=1 smoke entries (2026-06-08).** Earlier the same day, single-question-
> per-type smokes established the loop end-to-end: `closed_book` 1/9 (confirming the three
> 2026-06-06 caveat fixes from commit `99ed610` — refusal-bias prompt, set-precision
> extraction, binary-judge `don't` — landed) and the first three-arm comparison
> (closed 1/9, graph 3/9, vector 2/9). The full-set run above subsumes both with real
> denominators; retained here only as provenance for the caveat-fix verification.
