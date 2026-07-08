# Assessment — How importing an RO upper ontology (under OWL 2 QL) would help the SPARQL writer

**Status:** Analysis / design note. Feeds Project 2 (OBDA) and Project 3 (reasoning).
**Date:** 2026-07-03.
**Scope of evidence:** all `graph_sparqlgen` telemetry under `eval/results/`
(`*graph_sparqlgen*.jsonl`, June 9 – June 27 2026), read on the `traversal_info.sparql` /
`sparql_generated` (generated query), `sparql_valid`, `num_rows` keys, joined per row to the
ground-truth SPARQL in `produce/questions.jsonl` on `question_id`, split by `passed`.
**Writers observed:** `claude-haiku-4-5`, `claude-sonnet-4-6` (capable), `qwen2.5-coder:1.5b`
(weak, local). The eval fixed-generator is a separate model and is *not* the subject here.

---

## 1. Honest headline

Importing an RO-based upper ontology and running it under **OWL 2 QL** would **not** have moved
the pass rate of the capable-writer `graph_sparqlgen` runs, because in those runs the SPARQL
retrieval is almost never the thing that fails. It **would** eliminate one specific, real class
of retrieval miss — writing an edge in the wrong direction — that today is only suppressed by a
hand-maintained direction table in the prompt and by the ground-truth author reaching for
SPARQL's inverse-path operator. That class is rare for a strong writer (2 clear rows) and common
for a weak one. So the payoff of RO import is **robustness and maintainability of the writer**,
not a headline accuracy jump. Anyone who claims "RO would have fixed the failing queries" has not
looked at where the failures actually sit.

The rest of this note proves that with the telemetry, then shows *didactically* what each RO
feature (inverse, symmetric, domain/range, disjointness) does for the writer — and, just as
important, what it does **not** do.

---

## 2. What the telemetry actually shows

Every failing `graph_sparqlgen` row falls into exactly one **failure locus**, derived from
`sparql_valid` + `num_rows` + whether the ground truth is a genuine non-empty answer:

| Locus | Meaning | The SPARQL was… |
|---|---|---|
| `INVALID` | GraphDB rejected it (4xx) or no query was extracted | the problem |
| `EMPTY_MISS` | valid, `num_rows = 0`, but a real answer exists | the problem |
| `EMPTY_CORRECT` | valid, `num_rows = 0`, and the answer *is* empty/false | **correct**; generation then hallucinated |
| `ROWS_GEN_FAIL` | valid, returned the right rows | **correct**; generation dropped/refused them |

Aggregated over all `graph_sparqlgen` runs (excluding `20260612T172411`, a whole-run environment
failure — every row is `HTTP 404: Unknown repository: hetionet`, not a writer error):

| Writer class | PASS | ROWS_GEN_FAIL | EMPTY_CORRECT | EMPTY_MISS | INVALID |
|---|---|---|---|---|---|
| capable (haiku / sonnet) | 305 | 537 | 125 | 27 | 2 |
| weak (`qwen2.5-coder:1.5b`) | 9 | 0 | 0 | 0 | 49 |

Read the capable-writer row carefully, because it is the whole argument:

- **537 `ROWS_GEN_FAIL` + 125 `EMPTY_CORRECT` = 662 failures where the SPARQL was already right.**
  The retriever fetched the correct rows (or correctly fetched nothing), and the *fixed generator*
  then refused ("I cannot answer based on the provided context"), dropped rows below the F1
  threshold, or — on the negative/unanswerable type — ignored an empty result and answered from
  parametric memory. **No ontology change touches these.** They are a generation-side story.
- **Only 2 `INVALID` and 27 `EMPTY_MISS`** are retrieval-side. And 26 of the 27 `EMPTY_MISS` are
  the `09_path_existence` type. When you open those, **24 wrote the edge in the correct direction**
  and missed for other reasons (label matching, the boolean-path structure); **2 reversed the
  `associates` edge** — the direction trap this note is about.

The weak writer is the mirror image: it never reaches `ROWS_GEN_FAIL` because it rarely produces a
runnable query at all (49/49 failures are `INVALID` — truncated output, undefined prefixes, and
malformed projections), and the queries it *does* form show the exact category errors RO guards
against (Section 5.1 / 5.4).

**Conclusion of the evidence:** the direction/type failure class that RO addresses is genuine but
small under a strong writer, and it is the *dominant retrieval failure* under a weak writer. RO's
value scales inversely with writer capability — which is precisely the argument for a
cheaper/local writer, or for not having to trust the prompt.

---

## 3. The premise, made precise — OWL 2 QL and why "one SELECT expansion" holds

The framing is correct, and it is worth stating exactly *why*, because the "why" also tells you
which RO axioms are safe to import and which will silently do nothing (or worse).

OWL 2 QL is the OWL profile deliberately restricted to be **FO-rewritable**: for any conjunctive
query `q` and QL ontology `T`, there is a *first-order* query `q'` (a plain SELECT with UNIONs and
JOINs) such that evaluating `q'` on the raw ABox returns exactly the certain answers of `q` under
`T`. No inferred triples are materialized; the reasoning is *compiled into the query*. That is why
Ontop can serve a virtual graph over a relational database — the TBox becomes SQL, not rows.
([W3C OWL 2 Profiles](https://www.w3.org/TR/owl2-profiles/))

The restriction cuts both ways. Axioms are in QL **iff** they preserve FO-rewritability:

| Axiom | In OWL 2 QL? | Effect on the writer |
|---|---|---|
| `owl:inverseOf` (inverse object property) | **Yes** | direction-agnostic querying (§5.1) |
| `owl:SymmetricProperty` | **Yes** | both-ends querying of one stored direction (§5.2) |
| `rdfs:domain` / `rdfs:range` | **Yes** | type inference; fewer explicit type guards (§5.3) |
| `owl:disjointWith` (disjoint classes) | **Yes** | *consistency* check; catches mis-typed anchors (§5.4) |
| `rdfs:subPropertyOf` / `rdfs:subClassOf` | **Yes** | hierarchy folding (not exercised here) |
| `owl:TransitiveProperty` | **No** | anatomy `part_of` roll-ups can't be QL-rewritten (§5.5) |
| property chains (role composition) | **No** (EL/RL) | multi-hop shortcuts must stay explicit hops |
| functional / inverse-functional | **No** | — |

Transitivity is excluded *by design*: a transitive property forces the rewriting to enumerate
paths of unbounded length, which is not first-order. ([W3C OWL 2 Profiles](https://www.w3.org/TR/owl2-profiles/))
So the honest boundary is: **inverse, symmetric, domain/range, and disjointness — the four
features named in the ask — are all QL-safe. Transitivity is not.** Keep that in view for §5.5.

---

## 4. Where the writer's schema knowledge lives today

Open `retrievers/sparqlgen.py`. The entire knowledge the writer has about the graph is the prose
`SCHEMA_PROMPT`, whose load-bearing block is a hand-typed **directed-edge signature table**:

```
Anatomy   expresses | upregulates | downregulates   Gene
Disease   associates | upregulates | downregulates  Gene
Compound  treats | palliates   Disease
Gene      participates   Pathway | BiologicalProcess | ...
```

with a code comment that says the quiet part out loud:

> `expresses` runs Anatomy->Gene, so the LLM must write the triple in that direction.

That table **is an informal ontology**. Every row is a `rdfs:domain`/`rdfs:range` pair; the whole
table is the graph's object-property signature; the "polymorphic `participates`" note is a
range-disjunction. It is maintained by hand, in English, and enforced only by the writer choosing
to obey it. Its failure modes are exactly what you would predict: a strong writer mostly obeys it,
a weak writer ignores it (Section 5.1/5.4), and a human editing it can silently desync it from the
graph — the very drift the `CLAUDE.md` "additive telemetry" and "two Turtle files" rules exist to
prevent elsewhere.

RO import is the move from *that prose* to *declared, machine-checked axioms* that (a) the writer
can consult, (b) a reasoner can enforce at query time, and (c) a validator can test against the
data. The remaining sections show, feature by feature, what that buys.

---

## 5. Didactic examples

The Hetionet metaedges map cleanly onto RO/BFO relations. Verified IRIs are marked ✔; where
Hetionet's modeling has no exact RO counterpart I mark it *(model as…)* rather than invent an IRI.

| Hetionet edge (stored direction) | RO / BFO relation | QL feature it unlocks |
|---|---|---|
| `Anatomy expresses Gene` | `RO:0002206 expressed in` ✔, inverse `RO:0002292 expresses` ✔ | inverse |
| `Disease associates Gene` | *(model: `hetio:associatedWith owl:inverseOf hetio:associates`)* | inverse |
| `Gene participates Pathway/BP/MF/CC` | `RO:0000056 participates in` ✔ / `RO:0000057 has participant` ✔ | inverse + range |
| `Gene interacts Gene` | `RO:0002434 interacts with` ✔ (**symmetric**) | symmetric |
| `Gene covaries Gene`; `Disease/Compound resembles …` | *(model as `owl:SymmetricProperty`)* | symmetric |
| `Disease localizes Anatomy` | `RO:0001025 located in` ✔ / `RO:0001015 location of` ✔ | inverse |
| node typing (`Gene`, `Anatomy`, …) | `owl:disjointWith` between types | disjointness |

Sources for the ✔ IRIs are in Section 7.

### 5.1 Inverse properties — the direction trap (this is the one the telemetry proves)

**The failure in the data.** Two capable-writer `09_path_existence` rows returned zero rows and
so answered "no path" when a path exists. Example (`claude-haiku-4-5`, Bortezomib → liver cancer):

```sparql
SELECT DISTINCT ?compound ?gene ?disease WHERE {
  ?compound rdfs:label "Bortezomib" .
  ?compound hetio:binds ?gene .
  ?gene hetio:associates ?disease .     # ← REVERSED: associates is stored Disease→Gene
  ?disease rdfs:label "liver cancer" .
}
```

`associates` is stored **Disease→Gene**. The writer, following the English ("a gene the disease is
associated with"), made the *gene* the subject. Zero rows. A false negative on a reachability
question — the worst kind, because it looks like a confident "no."

**How the ground truth avoids it.** The hand-authored ground-truth query does not trust the
writer to know the direction — it uses SPARQL's **inverse-path operator `^`**:

```sparql
ASK { VALUES ?compound { db:DB00727 } VALUES ?disease { <…DOID_8850> }
      ?compound hetio:binds / ^hetio:associates ?disease . }   # ^ = traverse associates backwards
```

`^hetio:associates` says "walk `associates` from object to subject." That `^` is a **per-query,
manual workaround for a missing declared inverse.** Every author of every direction-sensitive
query has to remember to reach for it.

**What RO import does.** Declare the inverse once, in the TBox:

```turtle
hetio:associatedWith owl:inverseOf hetio:associates .   # QL-safe
```

Now the writer can write the *intuitive* forward direction and be correct:

```sparql
?compound hetio:binds ?gene .
?gene     hetio:associatedWith ?disease .   # reads with the sentence; no ^ , no memorized direction
```

Under OWL 2 QL the rewriter substitutes `?gene hetio:associatedWith ?disease` back to the stored
`?disease hetio:associates ?gene` before hitting the data — **the direction becomes un-gettable-
wrong**, for the writer *and* for the ground-truth author. `expresses`/`expressed in`
(`RO:0002206`/`RO:0002292`) is the same story for "which genes are expressed in *anatomy*" — the
weak writer got that one backwards too (`?gene hetio:expresses ?anatomy`, §5.4).

This is the single feature with direct telemetry support. Note it is worth doing even though it is
only 2 capable-writer rows: a false "no path" is a high-cost error, and the fix also lets you
delete four rows of prompt prose.

### 5.2 Symmetric properties — one stored direction, both-ended questions

**Honesty first:** the *current* 58-question set does not contain a direction-sensitive question
over a symmetric edge — the only symmetric-family edge that appears in any ground-truth query is
`binds` (which is not symmetric), inside the path template. So this is a **structural** argument
about the schema and the questions the set *will* grow into, not a present-telemetry miss. It is
included because `resembles`/`interacts`/`covaries` are genuine symmetric Hetionet metaedges and
the append-only question rule means such questions are a matter of when, not if.

**The problem.** `Disease resembles Disease` is undirected in Hetionet's source but stored as a
single directed triple, say `A resembles B`. Ask "which diseases resemble B?" and the natural
query finds nothing:

```sparql
?d hetio:resembles ?x . ?x rdfs:label "B" .   # matches A resembles B? No — B is the object, A the subject
```

Today you would have to write the UNION by hand, or an inverse path, for every such query.

**What RO import does.** Declare symmetry once:

```turtle
hetio:resembles a owl:SymmetricProperty .   # QL-safe;  cf. RO:0002434 interacts with, which is symmetric
```

Under QL this is *exactly* the "expand into UNIONs" the profile promises — the single triple
pattern rewrites to:

```sparql
{ ?d hetio:resembles ?x } UNION { ?x hetio:resembles ?d }
```

generated by the reasoner, not by the writer. `RO:0002434 interacts with` is declared symmetric
upstream, so importing it gives `Gene interacts Gene` this behavior for free; `covaries` and
`resembles` are modeled locally as `owl:SymmetricProperty`.

### 5.3 Domain / range — delete the type guards, tame polymorphic `participates`

The prompt currently instructs the writer to add explicit type guards, most visibly for the
overloaded `participates`:

> `participates` is polymorphic — when the question asks for pathways, constrain the object with
> `?p a hetio:Pathway`.

and capable writers dutifully emit `?gene a hetio:Gene`, `?pathway a hetio:Pathway`, etc. With
`rdfs:domain`/`rdfs:range` declared (QL-safe):

```turtle
hetio:expresses  rdfs:domain hetio:Anatomy ; rdfs:range hetio:Gene .
hetio:participates rdfs:domain hetio:Gene .   # range stays a union of process types
```

the reasoner infers `?gene a hetio:Gene` from its use in an `expresses`/`participates` position,
so the writer can drop the guard and still be correct — fewer tokens, fewer places to get a type
name wrong. This does not add answers on its own; it *simplifies the query the writer must
produce*, which is the thing we are measuring.

### 5.4 Disjointness — catches the mis-typed anchor, but adds **zero** rows

This is the feature most easily oversold, so state its mechanics exactly.

**The failure in the data.** The weak writer, on "which genes are expressed in semicircular
canal?", produced:

```sparql
?gene rdfs:label "Semicircular Canal" .   # ← an ANATOMY bound as a gene
?gene hetio:expresses ?anatomy .            # ← and the edge reversed, too
```

It labeled an anatomy node as `?gene` and reversed `expresses`. A category error.

**What disjointness does — and doesn't.** Declare the types disjoint (QL-safe):

```turtle
hetio:Gene owl:disjointWith hetio:Anatomy .
```

With `expresses` also carrying `rdfs:range hetio:Gene`, a reasoner can now *detect* that binding
the object of `expresses` to something typed `Anatomy` makes the ABox **inconsistent** — a signal
a validation layer (or Ontop's consistency check) surfaces as "this query is unsatisfiable against
the ontology." That is real value: it turns a silent 0-row miss into a diagnosable error, and it
is the kind of check you can run *offline* over a candidate query before execution.

**But — and this is the precise point most write-ups miss — disjointness does not add a single
answer row.** OWL 2 QL query answering returns *certain answers*; disjointness is a negative
constraint, so under an assumed-consistent ABox it contributes nothing to the rewritten SELECT.
Its role is **consistency and validation, not retrieval.** The ask lumps "a disjoint or inverse
property" together; they are not the same kind of tool. Inverse/symmetric *change the answer set*
(they are the UNION/JOIN expansions of the premise); domain/range *simplify the query*;
disjointness *rejects a wrong query*. Only the first family would have turned a telemetry miss into
a hit; disjointness would have turned it into a clearer failure.

### 5.5 The QL boundary — what RO could model that QL still won't rewrite

RO/Uberon model anatomy with `part of` (`BFO:0000050`), which is **transitive**: the loop of Henle
is part of the nephron is part of the kidney. A tempting extension is "genes expressed anywhere in
the kidney," rolled up through `part_of`. **OWL 2 QL cannot do this** — transitivity is outside the
profile precisely because it breaks FO-rewritability (§3). Under Ontop you would get either no
roll-up or an error, not a silent wrong answer, but the point stands: importing RO does not make
the anatomy hierarchy queryable *in QL*. That capability is what Project 3 (reasoning over a richer
profile, or materialization) is for. Naming this boundary is the honest complement to the premise:
"any reasoning becomes one SELECT expansion" is true **because** QL threw transitivity overboard.

---

## 6. Net assessment

- **For accuracy on the current runs:** negligible. The capable-writer failures are 96% generation-
  side (`ROWS_GEN_FAIL` + `EMPTY_CORRECT`); RO touches none of them. Do not sell RO import as an
  accuracy fix for Project 1's `graph_sparqlgen` numbers — the telemetry won't back it.
- **For the writer's robustness:** real and QL-safe. Inverse properties (`§5.1`) close the
  direction-reversal class outright — the one class with direct telemetry support and a high error
  cost (false "no path"). Symmetric properties (`§5.2`) make one-directional storage answerable from
  both ends by construction. Both scale hardest for cheap/local writers, which is the interesting
  direction for cost — the weak writer's failures are exactly here.
- **For maintainability:** RO import replaces the hand-typed direction table and type-guard prose in
  `SCHEMA_PROMPT` with declared axioms the reasoner enforces and a validator can test against the
  data — removing a silent drift surface, consistent with the repo's "pin the contract in code, not
  prose" stance.
- **For validation:** disjointness + domain/range (`§5.3`/`§5.4`) turn category-error queries from
  silent 0-row misses into diagnosable inconsistencies — valuable, but explicitly **not** a source
  of new answers.
- **Boundary:** transitive `part_of` roll-ups are out of scope for QL (`§5.5`); that is a Project 3
  concern, not something RO-under-QL delivers.

**Recommendation:** land the inverse-property axioms for the direction-sensitive edges
(`associates`, `expresses`, `participates`, `localizes`) and the symmetric axioms for
`resembles`/`interacts`/`covaries` as part of the Project 2 TBox (`ontology/hetionet-schema.ttl`),
under OWL 2 QL. Treat it as a **writer-robustness and maintainability** change with a small,
well-characterized retrieval upside — not as an accuracy lever for the fixed generator. The
generator-side failures that dominate the telemetry need a different intervention (context
serialization / the "trust the retrieved rows" problem), out of scope for this note.

---

## 7. Sources

- OWL 2 QL profile, allowed/forbidden axioms and FO-rewritability rationale —
  [W3C OWL 2 Web Ontology Language Profiles (2nd ed.)](https://www.w3.org/TR/owl2-profiles/)
- `RO:0002206 expressed in`, inverse `RO:0002292 expresses` —
  [OBO Relation Ontology](https://oborel.github.io/) ·
  [ro-base.obo](https://github.com/oborel/obo-relations/blob/master/ro-base.obo)
- `RO:0000056 participates in` / `RO:0000057 has participant`; `RO:0002434 interacts with`
  (symmetric) — [OBO Relation Ontology](https://oborel.github.io/)
- `RO:0001025 located in` / `RO:0001015 location of`; `BFO:0000050 part of` (transitive) —
  [OBO Relation Ontology](http://obofoundry.org/ontology/ro.html)
- Telemetry: `eval/results/*graph_sparqlgen*.jsonl`; ground truth: `produce/questions.jsonl`;
  writer prompt: `retrievers/sparqlgen.py` (`SCHEMA_PROMPT`).
