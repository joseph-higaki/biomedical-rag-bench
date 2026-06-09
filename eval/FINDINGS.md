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
  loss **on efficiency and profile** — though *not* on raw count, once sampling noise is
  removed. At temperature 0 `graph_neighborhood_2hop` **ties** `1hop` at 13/52, but pays
  **2.6× the input tokens** for it and has a worse *shape*: the 200-triple budget fills with
  2-hop fan-out, *burying* the 1-hop answer (type 02 collapses 5/5 → 1/5) while barely
  unlocking 2-hop (03: 0 → 1/7) — it trades robust wins for marginal ones at far higher cost.
  Read `2hop` as a cautionary "no free lunch", not "the deeper graph condition." A hop bump
  needs a proportional cap bump (a joint hops×caps sweep) — or the structural answer (query
  execution, `graph_sparqlgen`). `graph_neighborhood_1hop` is the honest neighborhood baseline.

  > **History/correction.** This caveat once read "strictly dominated — fewer correct (12 vs
  > 13)." That run-to-run gap was **not** a property of 2hop — it was a *retriever
  > non-determinism bug*: an unordered SPARQL `LIMIT` in the hop fetch (now fixed with `ORDER
  > BY`) returned a different capped neighborhood each call, so the buried type-01 attribute was
  > present-or-absent at random. Deterministically, 2hop **ties 1hop at 13/13 — but hollowly**:
  > 2hop's type-01 2/3 is *parametric fallback* (the attribute is buried, so the model answers
  > from its own knowledge, = closed_book) and its edge comes from the type-08 refuse-on-noise
  > artifact, while 1hop's 13 is real retrieval (01 read from context 3/3, 02 5/5). Same count,
  > opposite substance — "dominated on efficiency and profile" is the durable claim; "fewer
  > correct" was a bug artifact. See the 2026-06-09 (retrieval fixed) run entry.

- **Binary exact-set pass *understates* `graph_sparqlgen` — read recall, not just pass.**
  The set/aggregate judges pass only on an exact set (F1=1.0). For a *neighborhood* dump that
  is fine — it rarely retrieves the precise set anyway. For *query execution* it is the wrong
  top-line: text-to-SPARQL routinely returns the **complete** answer set (recall 1.0) and
  fails the binary only on a few extra rows (precision < 1.0). On the first full run, **14 of
  30 content questions had recall 1.0 while only 2 passed exact-set**. Reporting `graph_sparqlgen`
  at its binary pass rate alone would call a retriever that fetched the whole answer a failure.
  The analysis layer must report **recall and F1 distributions** for this condition, not just
  exact-set accuracy. (The precision leak is itself the finding — see the run entry below — not
  a judge to loosen: an exact-set judge is correct for "did you return *exactly* the set".)

- **A retriever's own LLM is a mechanism cost, not a generator cost — keep them separate.**
  `graph_sparqlgen` calls an LLM *inside* retrieval to write the SPARQL. That writer's tokens
  are logged under `traversal_info` (`writer_model`, `writer_input_tokens/_output_tokens`) and
  are **not** part of the generator's billed `input_tokens/output_tokens` the harness records.
  The two must never be summed as one "cost" — they are different roles (retrieval skill vs.
  the model under test) and may be different models (`SPARQLGEN_MODEL` ≠ `GENERATOR_MODEL`). A
  fair cost comparison against the neighborhood arms must add the writer cost back in explicitly;
  it is recorded precisely so that addition is possible, not so it is silently folded in.

---

## Run log (newest first)

### 2026-06-09 (retrieval fixed) — reproducibility audit exposes a retriever non-determinism bug

Running the temp-0 sweep **twice and diffing every verdict** (the audit the temp-0 entry below
left open) found **2 of 260 cells flipped** — both the `graph_2hop` buried-needle type-01 cells —
and **0 flips in the other four conditions**. The flips falsify the temp-0 entry's root-cause
claim. Re-run arms: `graph_neighborhood_1hop` `20260609T173424`, `graph_neighborhood_2hop`
`20260609T173551`, `graph_sparqlgen` `20260609T173859` (closed_book/vector unchanged, code-unaffected).

1. **The instability was a *retriever* bug, not generator variance — temperature 0 never fixed
   it.** `graph.py._hop_queries` fetched with `LIMIT 5000` and **no `ORDER BY`**; a bare SPARQL
   `LIMIT` returns an *arbitrary* subset, so when a hub node's 2-hop expansion exceeds the
   ceiling (the `chromosome` GO hub does) GraphDB handed back a different subset each call →
   different capped neighborhood → the anchor's buried `chromosome` attribute present-or-absent.
   **Proven:** two identical retrievals with *no LLM in the path* produced different context
   hashes. This corrects the temp-0 entry below, whose findings #1–#2 attributed the 12↔11 flip
   to generator sampling "pinned out at temp 0" — wrong: the cells still flipped at temp 0
   because the variance is upstream of the generator.

2. **Fix: `ORDER BY` before `LIMIT`** in both hop queries (`graph.py`) and the same latent
   `LIMIT`-without-`ORDER BY` in `sparqlgen._bounded`. Retrieval is now a stable prefix —
   verified deterministic (identical context hash across repeated retrievals). With retrieval
   deterministic and the generator at temp 0, the baseline is reproducible by construction.

3. **Corrected deterministic baseline: `4 / 9 / 13 / 13 / 16`** (closed / vector / 1hop / 2hop /
   sparqlgen). 2hop totals **13**, not the temp-0 entry's lucky-draw framing — but **its 13 is
   hollow, and the fix is what revealed that.** Deterministically the 2-hop fan-out *buries* the
   0-hop attribute: all three type-01 answers are "I cannot find <gene> in the provided context",
   so 2hop type-01 = **2/3 is pure parametric fallback** (HTR3B→11, PTDSS1→8 from the model's own
   knowledge; obscure R3HDM2→12 fails) — **identical to closed_book's 2/3, zero retrieval
   contribution.** Contrast 1hop type-01 = 3/3, which reads the value straight from its under-cap
   neighborhood (`11`, `12`, `chromosome 8`). 2hop's remaining points are the type-08
   refuse-on-noisy-context artifact (**7/7** vs 1hop 4/7). So **1hop earns 13 through retrieval**
   (02: 5/5), **2hop earns 13 through artifacts** (parametric 01 + noisy 08) while its real
   retrieval collapses (02: 5/5 → 1/5) at 2.6× the cost. Same count, opposite substance — the
   "dominated on efficiency and profile" caveat holds and is sharpened, not overturned.

4. **The audit was worth exactly one repeat.** A 2nd run found the bug; a 3rd would only have
   re-rolled the dice. The lesson generalizes: *nondeterminism anywhere upstream of the judge
   makes a score a draw* — the judge was pinned, the generator was pinned, but an unordered
   `LIMIT` in retrieval slipped the net. The 35%-of-answers-reworded / 0.8%-verdict-flip split
   (from the temp-0 repeat) also stands: the deterministic judges absorb wording noise; the only
   flips were missing-data, now fixed.

> The temp-0 entry below is retained as the record of what that run *appeared* to show; its
> findings #1–#2 (generator-variance attribution) are **superseded by this entry** — read them
> together. The `4 / 9 / 13 / 13 / 16` totals are unchanged; only the *why* and the hollowness of
> 2hop's 13 are corrected.

### 2026-06-09 (temp 0) — reproducible baseline: all sampling pinned to temperature 0 (5 conditions, 52 q)

> **Correction (see the entry above).** This entry's findings #1–#2 attribute the graph_2hop
> 12↔11 flip to *generator* sampling variance "eliminated by temperature 0". That is wrong: a
> two-run audit showed the cells still flip at temp 0, because the variance was an **unordered
> SPARQL `LIMIT` in the retriever**, not the generator. Fixed with `ORDER BY`; 2hop's 13 is
> reproducible but hollow (parametric type-01 + type-08 artifact). The totals below stand; the
> mechanism does not.

The first sweep with **every LLM call pinned to temperature 0** — the generator under test
(`GENERATOR_TEMPERATURE=0`), the `graph_sparqlgen` SPARQL-writer (`SPARQLGEN_TEMPERATURE=0`),
and the already-pinned semantic judge. Same full corpus + new-telemetry harness as the temp-1.0
sweep directly below; the *only* change is sampling policy, so this isolates temperature.
Every row logs `generator_temperature=0.0`. Runs: `closed_book` `20260609T153917`, `vector`
`20260609T154127`, `graph_neighborhood_1hop` `20260609T154316`, `graph_neighborhood_2hop`
`20260609T154527`, `graph_sparqlgen` `20260609T154741`.

| type | closed | vector | 1hop | 2hop | sparqlgen |
|---|---|---|---|---|---|
| 01_0hop_attribute | 2/3 | 2/3 | 3/3 | **3/3** | 3/3 |
| 02_1hop_factoid | 0/5 | 0/5 | 5/5 | 1/5 | 0/5 |
| 03_2hop_traversal | 0/7 | 0/7 | 0/7 | 1/7 | 2/7 |
| 04_3plus_hop_traversal | 0/8 | 0/8 | 0/8 | 0/8 | 0/8 |
| 05_aggregative | 0/8 | 0/8 | 0/8 | 0/8 | 8/8 |
| 06_set_intersection | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| 07_set_difference | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| 08_negative_unanswerable | 0/7 | 5/7 | 4/7 | 6/7 | 0/7 |
| 09_path_existence | 2/4 | 2/4 | 1/4 | 2/4 | 3/4 |
| **passed** | **4/52** | **9/52** | **13/52** | **13/52** | **16/52** |

vs. the temp-1.0 sweep below: `4 / 9 / 13 / 11 / 15` → `4 / 9 / 13 / 13 / 16`.

1. **The graph_2hop instability was generator variance, now pinned out — confirming the
   buried-needle diagnosis.** Type 01 (0-hop attribute) went **1/3 → 3/3 and held**. The
   chromosome triple is present-but-buried in the 200-triple 2-hop dump (→ the temp-1.0
   entry's diagnosis); at temperature 1.0 whether the generator located that single line was
   a coin-flip (1/3 unlucky), and at temperature 0 greedy decoding finds it **reliably** (3/3).
   The 12↔11 flip across runs is fully explained and eliminated.

2. **This overturns a previously-recorded claim: 2hop is NOT "strictly dominated" on count.**
   The temp-1.0 sweeps showed 2hop 11–12 vs 1hop 13 and the caveat read "strictly dominated —
   fewer correct." That gap was *itself* temp-1.0 sampling noise on type 01; **at temp 0 they
   tie, 13/13.** The honest claim survives in weaker form — 2hop is dominated on **efficiency
   and profile**, not count: it costs ~2.6× the input tokens for the same total and trades
   1hop's robust `02` wins (5/5 → 1/5) for marginal `03` (0 → 1). The coupled-knobs / hop-bump
   argument stands; "fewer correct" does not. The caveat above has been corrected accordingly.

3. **sparqlgen reaches a reproducible 16/52** (vs 15), gaining `03` (1→2) and `09` (2→3) and
   losing `07` (1→0) relative to the sampled run — modal SPARQL writing differs slightly from
   the temp-1.0 average, but is now stable rather than a per-run draw. `05` aggregation holds
   8/8. Recall-not-pass still applies (→ the binary-understates-sparqlgen caveat).

4. **closed_book / vector / 1hop are unchanged (4 / 9 / 13)** — their single generator call was
   already near-deterministic on these answer shapes, so pinning moved nothing. The thesis is
   intact and now *stable*: structured (13/13/16) > dense (9) > parametric (4), no run-to-run
   wobble.

**Status of this baseline.** This is the canonical reproducible baseline; the temp-1.0 numbers
below are retained as the provenance for *why* it was pinned (the variance they exposed), not as
a competing leaderboard. Caveat: temperature 0 is **low-variance, not bit-identical** — FP/batch
nondeterminism on a hosted model can still flip an occasional token; a double-run to quantify
residual variance is not yet done.

### 2026-06-09 — canonical re-run: full-corpus `vector` + new-telemetry harness (5 conditions, 52 q)

The first sweep on the rebuilt telemetry harness (resolved-model id + `traversal_info` + cache
tokens persisted per row) and the **full PubMed corpus** (152,943 chunks, 27,070 entity files —
the prior `vector` arm was the 1,893-entity targeted store). All five registered conditions,
same `claude-haiku-4-5` generator, deterministic judges only (the 6 type-10 questions excluded).
Runs: `closed_book` `20260609T134244`, `vector` `20260609T134442`, `graph_neighborhood_1hop`
`20260609T134623`, `graph_neighborhood_2hop` `20260609T134758`, `graph_sparqlgen` `20260609T135010`.

| type | closed | **vec(full)** | 1hop | 2hop | sparqlgen |
|---|---|---|---|---|---|
| 01_0hop_attribute | 2/3 | 2/3 | 3/3 | **1/3** | 3/3 |
| 02_1hop_factoid | 0/5 | 0/5 | 5/5 | 1/5 | 0/5 |
| 03_2hop_traversal | 0/7 | 0/7 | 0/7 | 1/7 | 1/7 |
| 04_3plus_hop_traversal | 0/8 | 0/8 | 0/8 | 0/8 | 0/8 |
| 05_aggregative | 0/8 | 0/8 | 0/8 | 0/8 | 8/8 |
| 06_set_intersection | 0/5 | 0/5 | 0/5 | 0/5 | 0/5 |
| 07_set_difference | 0/5 | 0/5 | 0/5 | 0/5 | 1/5 |
| 08_negative_unanswerable | 0/7 | 5/7 | 4/7 | 6/7 | 0/7 |
| 09_path_existence | 2/4 | 2/4 | 1/4 | 2/4 | 2/4 |
| **passed** | **4/52** | **9/52** | **13/52** | **11/52** | **15/52** |

1. **The headline: a full corpus does not rescue dense retrieval — `vector` 8 → 9/52.** Feeding
   the model the *entire* corpus (152,943 chunks vs. the targeted 10,735) instead of the
   question-seed store moved the binary by **one question** and left **02–07 at 0/5..0/8** —
   still zero on every content type. This closes the strongest form of the "vector only lost
   because it was under-fed" objection: with full entity coverage *and* 14× the chunks, dense
   literature retrieval still cannot answer structured graph questions, because the answers are
   graph *relationships*, not sentences in any abstract (→ the 2026-06-08 `vec(real)` worked
   example). The graph thesis (H2/H4/H7) now holds against a maximal vector baseline. The +1
   is noise on type 07's edge, not a capability shift.

2. **`graph_2hop` 12 → 11 is generator variance on a *deterministic* pathology, not a
   regression.** The entire delta is type 01 (0-hop attribute) **3/3 → 1/3**, with type 09
   +1 the other way. Diagnosed directly: for R3HDM2 (truth: chr 12) and PTDSS1 (chr 8) the
   model returned *"the context does not contain information…"* — yet the attribute triple
   **is in the 200-triple dump** (`R3HDM2 chromosome 12` is present). It is *buried*: at
   `hops=2` the neighborhood explodes through the **`chromosome` GO hub (GO_0005694)** — every
   gene that "participates chromosome" becomes a 2-hop neighbor — so the `max_triples=200` cap
   fills with chromosome-hub fan-out and drowns the gene's own 0-hop attribute. The `1hop`
   dump (82 triples, R3HDM2-centric) keeps the same triple findable. Because the retriever is
   deterministic, the 200-triple context is byte-identical to the old run; only the generator's
   needle-in-haystack success changed (old 3/3 lucky, this 1/3). **The true `2hop` type-01
   score is unstable, not 3/3.** This *extends* the coupled-knobs caveat: 2-hop fan-out doesn't
   just fail to unlock deep types — it corrupts the *trivial* 0-hop lookups by burying them,
   and the binary is run-to-run unstable because it depends on the generator spotting one line
   in 200. Another count against bumping `hops` without a proportional cap bump.

3. **New telemetry verified end-to-end.** Every row carries `generator_model_resolved`
   (`claude-haiku-4-5-20251001`), `traversal_info`, and cache-token fields; `graph_sparqlgen`
   rows persist the executed `sparql`, `sparql_valid`, `num_rows`, and the **writer-LLM cost
   logged apart** (`writer_input_tokens/_output_tokens/_model`) — the mechanism-vs-generator
   cost separation is now in the data, not just the design. The 1hop/sparqlgen/closed_book
   totals reproduce the prior baseline exactly (13/15/4), so the harness rebuild changed the
   schema, not the measurements.

> `vec(full)` 9/52 is now the canonical `vector` arm, superseding `vec(real)` 8/52 and the
> older 11/52 smoke. The graph/closed_book conditions are unchanged in capability (`2hop`'s
> −1 is the variance above, not a real shift).

### 2026-06-08 (latest) — `semantic` LLM judge online; first type-10 verdicts

Built the LLM judge for type-10 (`eval/judge/semantic.py`): given the question, the
graph-derived reference entity, and the candidate, it returns EQUIVALENT / DIFFERENT
(temperature 0, judge model logged + costed separately from the generator). Ran the 6 type-10
questions in isolation (`--types 10`) for two retrievers, same `claude-haiku-4-5` generator.
Runs: `closed_book` `20260608T215424`, `vector` `20260608T215522`. **Both 5/6.**

1. **The judge earns its existence on one verdict the deterministic judges *cannot* reach.**
   On the TP53 question, `closed_book` answered **"TP53"** and `vector` answered **"p53"** —
   both judged **equivalent** (correctly: p53 is the TP53 protein). A deterministic
   token-match passes "TP53" and **fails "p53"** (no shared token), so without the LLM judge
   the *same correct answer* scores differently by surface form. This is precisely the
   surface-form equivalence type-10 reserves for an LLM — demonstrated, not assumed.

2. **The judge is discriminating, not lenient.** The one FAIL in each run is a genuinely
   wrong answer the judge correctly rejected with a sound biological reason: the CDH1
   "loss promotes metastasis via cell-cell adhesion" question drew **"CDKN2A (p16)"**
   (closed_book) and **"IGF1R / KRIT1"** (vector, distracted by retrieved abstracts) — both
   different genes, both marked *different*. The judge passed 5 true synonyms/variants
   (Warfarin, Metformin, TP53/p53, Alzheimer's, Parkinson's) and rejected 2 wrong entities.

3. **On these 6, retrieval neither helped nor hurt the score (both 5/6) — H4 not yet
   testable.** The type-10 entities are textbook-famous, so the parametric baseline already
   nails them (H7 territory); `vector`'s extra context changed *wording* (p53 vs TP53) and
   on the CDH1 item actively *distracted* the generator into a wrong answer. A real H4 test
   ("vector wins on fuzzy/semantic") needs type-10 questions whose answer is **not** a
   household-name entity — a question-set expansion (append-only, a separate authorized task),
   not a judge problem.

4. **Calibration is pending — the judge is built, not yet trusted.** Per the determinism rule
   (eval/README.md) the LLM judge is trusted only after Cohen's kappa > 0.7 over a ≥20-question
   human-graded hold-out, reported in the release notes. Only 6 type-10 questions exist today,
   too few for a meaningful kappa. First-run verdicts were **manually spot-checked: 12/12
   agreed** with human grading (incl. the p53/TP53 accept and both CDH1 rejects) — promising,
   but not the formal study. **Do not cite type-10 accuracy as calibrated** until kappa lands.

### 2026-06-08 (earlier) — `graph_sparqlgen` first full run (52 q, run `20260608T203128`)

The new condition: an LLM writes one SPARQL `SELECT` from the question + a schema-vocabulary
prompt, the retriever runs it and serializes the rows (see retrievers/README.md). Writer model
= generator model here (`claude-haiku-4-5`), logged separately. **The new high — 15/52** — and
the first arm to score on the deep-structural types every prior condition left at zero.

| type | closed | vec(real) | 1hop | **sparqlgen** |
|---|---|---|---|---|
| 01_0hop_attribute | 2/3 | 2/3 | 3/3 | **3/3** |
| 02_1hop_factoid | 0/5 | 0/5 | 5/5 | **0/5** |
| 03_2hop_traversal | 0/7 | 0/7 | 0/7 | **2/7** |
| 04_3plus_hop_traversal | 0/8 | 0/8 | 0/8 | **0/8** |
| 05_aggregative | 0/8 | 0/8 | 0/8 | **8/8** |
| 06_set_intersection | 0/5 | 0/5 | 0/5 | **0/5** |
| 07_set_difference | 0/5 | 0/5 | 0/5 | **0/5** |
| 08_negative_unanswerable | 0/7 | 4/7 | 4/7 | **0/7** |
| 09_path_existence | 2/4 | 2/4 | 1/4 | **2/4** |
| **passed** | **4/52** | **8/52** | **13/52** | **15/52** |

1. **Query execution cracks the structural types neighborhood-dumping can't — aggregation
   8/8.** Type 05 (COUNT) was **0/52 across every other condition**; `graph_sparqlgen` is
   **8/8**. This is a *mechanism* result, not tuning: a count is one `COUNT(DISTINCT)` query,
   and no amount of context-dumping makes the model reliably enumerate-and-count a 27- or
   184-member set from triples. The all-zero structural types in the prior full run were the
   concrete argument for building this; the argument held.

2. **Binary 15/52 badly understates it — recall is excellent, precision leaks (→ caveat
   above).** Of the **30 content questions (02/03/04/06/07), only 2 passed exact-set but 14
   retrieved the *complete* answer set (recall 1.0)**; most "failures" are F1 0.6–0.95 — the
   right rows plus a few extras. The dominant failure mode is **precision**: underconstrained
   queries return a superset. Worst offenders are exactly the queries SPARQL makes easy to get
   *almost* right — **07 set-difference** (the LLM returns A's set without subtracting B's, so
   recall 1.0 but 7 extra) and **04 3+hop** (a hop pulls in a broader set, up to 13 extra).
   Type **02** is the cruel case: recall 9/11 with **0 extra** → F1=0.90 → FAIL. Text-to-SPARQL
   relocated answer-hallucination into *query*-imprecision, exactly as the README predicted.

3. **Six content failures are the *generator* hedging, not retrieval.** Rows tagged "prose
   answer: recall 0/N" had 14–20 result rows in context, but the generator emitted "I cannot
   answer based on the provided context" instead of listing them (recall 0). The answer was
   *present and correct*; the generator refused to format it. This is a generator/prompt
   interaction on long structured contexts — a confound to watch, not a retrieval miss.

4. **Type 08 flips negative: empty query → empty context → hallucination (0/7).** A correct
   unanswerable returns the empty set, so `graph_sparqlgen` serves **empty context**, which (per
   the type-08 caveat) drops the model into closed-book and it *hallucinates* a treated disease.
   The neighborhood arm scores 4/7 here precisely because it serves the compound's *other* edges
   (non-empty context without a `treats` edge → the model says "None"). A targeted query has no
   such cushion. This is the type-08 caveat sharpened: a retriever that answers the *exact*
   question can score worse on 08 than one that dumps a neighborhood — read 08 conditionally.

5. **Cost: 23,371 generator in / 4,529 out for 52 q**, *plus* a separate writer-LLM cost logged
   per row (not summed — see caveat). Writer queries are short (~40–90 output tokens each).
   `errs=0` under the crash-safe streaming path.

**The takeaway:** `graph_sparqlgen` is the mechanism the structural types needed — it executes
the question instead of approximating it, and its *recall* is the project's strongest evidence
yet for the graph thesis (H2/H4). Closing the gap to a high binary score is now a **precision**
problem (tighter query constraints / a SPARQL-shape prompt) and a **generator-formatting**
problem, not a retrieval-capability one. Next: a recall/precision-aware view in the analysis
notebook, and the type-10 semantic judge.

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
