# Producer worked examples

> **GENERATED — do not edit by hand.** Produced by `produce.py --explain` (run `make explain`). One trace per taxonomy type; the SPARQL and answers are live from GraphDB at generation time, so they shift if the graph changes (same contract as the registry's committed answers).

Each section traces one template end to end: the **candidate query** that defines the sampling pool, the **seeded pick**, the **instantiated ground-truth query**, the **answer**, and the emitted **record**. Verbose artifacts (full `.rq`, JSON record) are folded — click to expand. For the design behind this, see [`README.md`](README.md).

## Contents

- [`01_0hop_attribute` — chromosome_of_gene](#type-01_0hop_attribute)
- [`02_1hop_factoid` — genes_expressed_in_anatomy](#type-02_1hop_factoid)
- [`03_2hop_traversal` — genes_associated_with_compound_treated_diseases](#type-03_2hop_traversal)
- [`04_3plus_hop_traversal` — symptoms_of_pharmacologic_class_treated_diseases](#type-04_3plus_hop_traversal)
- [`05_aggregative` — count_of_side_effects_caused_by_compound](#type-05_aggregative)
- [`06_set_intersection` — shared_pathways_of_two_genes](#type-06_set_intersection)
- [`07_set_difference` — pathways_in_one_gene_excluding_another](#type-07_set_difference)
- [`08_negative_unanswerable` — diseases_treated_by_compound_negative](#type-08_negative_unanswerable)
- [`09_path_existence` — path_between_compound_and_disease_via_gene](#type-09_path_existence)
- [`10_fuzzy_semantic` — first_line_type2_diabetes_drug_fuzzy](#type-10_fuzzy_semantic)

---

<a id="type-01_0hop_attribute"></a>
## `01_0hop_attribute` — chromosome_of_gene

**Scoring:** string_match · **count:** 3 · **seed:** `20260605:chromosome_of_gene`

**1. Candidate pool** — sample mode `has_edge`. Pool: **20908** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Gene ;
     hetio:chromosome ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **HTR3B** (`https://identifiers.org/ncbigene/9177`) from the 20908-entity pool.

**3. Answer** — `11`

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX ncbigene: <https://identifiers.org/ncbigene/>

SELECT ?chromosome WHERE {
  VALUES ?gene { <https://identifiers.org/ncbigene/9177> }
  ?gene hetio:chromosome ?chromosome .
}
```

</details>

> **How this type samples:** `has_edge` **direct** (type 01): the sampled edge *is* the answer edge, so the placeholder's fan bound already shaped the answer — picks are drawn straight from the pool, no post-check.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "01_0hop_attribute__chromosome_of_gene__00",
  "type_id": "01_0hop_attribute",
  "template_id": "chromosome_of_gene",
  "question": "On which chromosome is the gene HTR3B located?",
  "scoring": "string_match",
  "answer_var": "chromosome",
  "ground_truth": "11",
  "seeds": [
    {
      "bind_var": "gene",
      "label": "HTR3B",
      "uri": "https://identifiers.org/ncbigene/9177"
    }
  ],
  "sampling_seed": "20260605:chromosome_of_gene"
}
```

</details>

**Question:** On which chromosome is the gene HTR3B located?

---

<a id="type-02_1hop_factoid"></a>
## `02_1hop_factoid` — genes_expressed_in_anatomy

**Scoring:** set_match · **count:** 5 · **seed:** `20260605:genes_expressed_in_anatomy`

**1. Candidate pool** — sample mode `has_edge`. Pool: **98** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Anatomy ;
     hetio:expresses ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?o) >= 2 && COUNT(DISTINCT ?o) <= 25)
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **semicircular canal** (`http://purl.obolibrary.org/obo/UBERON_0001840`) from the 98-entity pool.

**3. Answer** — **11** result(s) — BMP4, CHD7, COCH, CRLF1, HMX3, IGLL5, OC90, OTOP1, OTOS, SHC4 … (+1 more)

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX uberon: <http://purl.obolibrary.org/obo/UBERON_>

SELECT ?gene ?geneLabel WHERE {
  VALUES ?anatomy { <http://purl.obolibrary.org/obo/UBERON_0001840> }
  ?anatomy hetio:expresses ?gene .
  ?gene rdfs:label ?geneLabel .
}
ORDER BY ?geneLabel
```

</details>

> **How this type samples:** `has_edge` **direct** (type 02): the sampled edge *is* the answer edge, so the placeholder's fan bound already shaped the answer — picks are drawn straight from the pool, no post-check.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "02_1hop_factoid__genes_expressed_in_anatomy__00",
  "type_id": "02_1hop_factoid",
  "template_id": "genes_expressed_in_anatomy",
  "question": "Which genes are expressed in semicircular canal?",
  "scoring": "set_match",
  "answer_var": "geneLabel",
  "ground_truth": [
    "BMP4",
    "CHD7",
    "COCH",
    "CRLF1",
    "HMX3",
    "IGLL5",
    "OC90",
    "OTOP1",
    "OTOS",
    "SHC4",
    "UBIAD1"
  ],
  "seeds": [
    {
      "bind_var": "anatomy",
      "label": "semicircular canal",
      "uri": "http://purl.obolibrary.org/obo/UBERON_0001840"
    }
  ],
  "sampling_seed": "20260605:genes_expressed_in_anatomy"
}
```

</details>

**Question:** Which genes are expressed in semicircular canal?

---

<a id="type-03_2hop_traversal"></a>
## `03_2hop_traversal` — genes_associated_with_compound_treated_diseases

**Scoring:** set_match · **count:** 7 · **seed:** `20260605:genes_associated_with_compound_treated_diseases`

**1. Candidate pool** — sample mode `has_edge`. Pool: **387** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Compound ;
     hetio:treats ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **Allopurinol** (`https://identifiers.org/drugbank/DB00437`) from the 387-entity pool.

**3. Answer** — **18** result(s) — ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1, IL15, IL1RN, LRRC16A, NLRP3, POMC … (+8 more)

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?gene ?geneLabel WHERE {
  VALUES ?compound { <https://identifiers.org/drugbank/DB00437> }
  ?compound hetio:treats ?disease .
  ?disease hetio:associates ?gene .
  ?gene rdfs:label ?geneLabel .
}
ORDER BY ?geneLabel
```

</details>

> **How this type samples:** `has_edge` **post-check** (type 03): the answer is multi-hop, so the sampled head edge doesn't bound the answer size. The producer runs the `.rq` per candidate and keeps only answers in `[2, 25]`.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "03_2hop_traversal__genes_associated_with_compound_treated_diseases__00",
  "type_id": "03_2hop_traversal",
  "template_id": "genes_associated_with_compound_treated_diseases",
  "question": "Which genes are associated with the diseases that Allopurinol treats?",
  "scoring": "set_match",
  "answer_var": "geneLabel",
  "ground_truth": [
    "ABCG2",
    "ALDH16A1",
    "BCKDHA",
    "CASP1",
    "HPRT1",
    "IL15",
    "IL1RN",
    "LRRC16A",
    "NLRP3",
    "POMC",
    "PRPS1",
    "PRPS2",
    "SLC17A1",
    "SLC17A3",
    "SLC22A11",
    "SLC22A12",
    "SLC2A9",
    "UMOD"
  ],
  "seeds": [
    {
      "bind_var": "compound",
      "label": "Allopurinol",
      "uri": "https://identifiers.org/drugbank/DB00437"
    }
  ],
  "sampling_seed": "20260605:genes_associated_with_compound_treated_diseases"
}
```

</details>

**Question:** Which genes are associated with the diseases that Allopurinol treats?

---

<a id="type-04_3plus_hop_traversal"></a>
## `04_3plus_hop_traversal` — symptoms_of_pharmacologic_class_treated_diseases

**Scoring:** set_match · **count:** 8 · **seed:** `20260605:symptoms_of_pharmacologic_class_treated_diseases`

**1. Candidate pool** — sample mode `has_edge`. Pool: **345** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:PharmacologicClass ;
     hetio:includes ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **Norepinephrine Uptake Inhibitors** (`https://identifiers.org/ndfrt/N0000000102`) from the 345-entity pool.

**3. Answer** — **17** result(s) — Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight, Obesity, Obesity Hypoventilation Syndrome, Obesity, Abdominal, Obesity, Morbid, Overweight … (+7 more)

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX ndfrt: <https://identifiers.org/ndfrt/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?symptom ?symptomLabel WHERE {
  VALUES ?drugClass { <https://identifiers.org/ndfrt/N0000000102> }
  ?drugClass hetio:includes ?compound .
  ?compound hetio:treats ?disease .
  ?disease hetio:presents ?symptom .
  ?symptom rdfs:label ?symptomLabel .
}
ORDER BY ?symptomLabel
```

</details>

> **How this type samples:** `has_edge` **post-check** (type 04): the answer is multi-hop, so the sampled head edge doesn't bound the answer size. The producer runs the `.rq` per candidate and keeps only answers in `[2, 25]`.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "04_3plus_hop_traversal__symptoms_of_pharmacologic_class_treated_diseases__00",
  "type_id": "04_3plus_hop_traversal",
  "template_id": "symptoms_of_pharmacologic_class_treated_diseases",
  "question": "Which symptoms are presented by the diseases treated by compounds in the Norepinephrine Uptake Inhibitors class?",
  "scoring": "set_match",
  "answer_var": "symptomLabel",
  "ground_truth": [
    "Body Weight",
    "Bulimia",
    "Hyperphagia",
    "Hypoventilation",
    "Ideal Body Weight",
    "Obesity",
    "Obesity Hypoventilation Syndrome",
    "Obesity, Abdominal",
    "Obesity, Morbid",
    "Overweight",
    "Pediatric Obesity",
    "Prader-Willi Syndrome",
    "Sarcopenia",
    "Sleep Apnea, Obstructive",
    "Thinness",
    "Weight Gain",
    "Weight Loss"
  ],
  "seeds": [
    {
      "bind_var": "drugClass",
      "label": "Norepinephrine Uptake Inhibitors",
      "uri": "https://identifiers.org/ndfrt/N0000000102"
    }
  ],
  "sampling_seed": "20260605:symptoms_of_pharmacologic_class_treated_diseases"
}
```

</details>

**Question:** Which symptoms are presented by the diseases treated by compounds in the Norepinephrine Uptake Inhibitors class?

---

<a id="type-05_aggregative"></a>
## `05_aggregative` — count_of_side_effects_caused_by_compound

**Scoring:** numerical · **count:** 8 · **seed:** `20260605:count_of_side_effects_caused_by_compound`

**1. Candidate pool** — sample mode `has_edge`. Pool: **1071** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Compound ;
     hetio:causes ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **Galantamine** (`https://identifiers.org/drugbank/DB00674`) from the 1071-entity pool.

**3. Answer** — `184`

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX hetio: <https://het.io/schema/>

SELECT (COUNT(DISTINCT ?sideEffect) AS ?n) WHERE {
  VALUES ?compound { <https://identifiers.org/drugbank/DB00674> }
  ?compound hetio:causes ?sideEffect .
  ?sideEffect a hetio:SideEffect .
}
```

</details>

> **How this type samples:** `has_edge` **direct** (type 05): the sampled edge *is* the answer edge, so the placeholder's fan bound already shaped the answer — picks are drawn straight from the pool, no post-check.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "05_aggregative__count_of_side_effects_caused_by_compound__00",
  "type_id": "05_aggregative",
  "template_id": "count_of_side_effects_caused_by_compound",
  "question": "How many side effects does Galantamine cause?",
  "scoring": "numerical",
  "answer_var": "n",
  "ground_truth": "184",
  "seeds": [
    {
      "bind_var": "compound",
      "label": "Galantamine",
      "uri": "https://identifiers.org/drugbank/DB00674"
    }
  ],
  "sampling_seed": "20260605:count_of_side_effects_caused_by_compound"
}
```

</details>

**Question:** How many side effects does Galantamine cause?

---

<a id="type-06_set_intersection"></a>
## `06_set_intersection` — shared_pathways_of_two_genes

**Scoring:** set_match · **count:** 5 · **seed:** `20260605:shared_pathways_of_two_genes`

**1. Anchor pool** — `has_edge` on the first placeholder. Pool: **7292** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Gene ;
     hetio:participates ?o ;
     rdfs:label ?label .
     ?o a hetio:Pathway .
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?o) >= 2 && COUNT(DISTINCT ?o) <= 25)
ORDER BY ?e ?label
```

**2. Anchor pick** — **HMMR** (`https://identifiers.org/ncbigene/3161`).

**3. Partner pool** — for that anchor, the partner overlap query yields **468** candidates; the RNG drew **NUP155** (`https://identifiers.org/ncbigene/9631`).

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?shared) AS ?overlap) WHERE {
  <https://identifiers.org/ncbigene/3161> hetio:participates ?shared .
  ?e hetio:participates ?shared ;
     a hetio:Gene ;
     rdfs:label ?label .
  ?shared a hetio:Pathway .
  FILTER (?e != <https://identifiers.org/ncbigene/3161>)
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?shared) >= 2)
ORDER BY ?e ?label
```

**4. Answer** — **3** result(s) — Carbohydrate metabolism, Disease, Metabolism

<details>
<summary>instantiated ground-truth query (both `VALUES` rewritten)</summary>

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX ncbigene: <https://identifiers.org/ncbigene/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel WHERE {
  VALUES ?geneA { <https://identifiers.org/ncbigene/3161> }
  VALUES ?geneB { <https://identifiers.org/ncbigene/9631> }
  ?geneA hetio:participates ?pathway .
  ?geneB hetio:participates ?pathway .
  ?pathway a hetio:Pathway ;
           rdfs:label ?pathwayLabel .
}
ORDER BY ?pathwayLabel
```

</details>

> **How this type samples:** `paired` **set** (type 06): two random entities almost never share a target, so the partner query returns only co-participating entities (overlap ≥ `2`), collapsing the O(n²) pair space. One partner per anchor whose `.rq` answer lands in bounds.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "06_set_intersection__shared_pathways_of_two_genes__00",
  "type_id": "06_set_intersection",
  "template_id": "shared_pathways_of_two_genes",
  "question": "Which pathways do both HMMR and NUP155 participate in?",
  "scoring": "set_match",
  "answer_var": "pathwayLabel",
  "ground_truth": [
    "Carbohydrate metabolism",
    "Disease",
    "Metabolism"
  ],
  "seeds": [
    {
      "bind_var": "geneA",
      "label": "HMMR",
      "uri": "https://identifiers.org/ncbigene/3161"
    },
    {
      "bind_var": "geneB",
      "label": "NUP155",
      "uri": "https://identifiers.org/ncbigene/9631"
    }
  ],
  "sampling_seed": "20260605:shared_pathways_of_two_genes"
}
```

</details>

**Question:** Which pathways do both HMMR and NUP155 participate in?

---

<a id="type-07_set_difference"></a>
## `07_set_difference` — pathways_in_one_gene_excluding_another

**Scoring:** set_match · **count:** 5 · **seed:** `20260605:pathways_in_one_gene_excluding_another`

**1. Anchor pool** — `has_edge` on the first placeholder. Pool: **6306** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Gene ;
     hetio:participates ?o ;
     rdfs:label ?label .
     ?o a hetio:Pathway .
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?o) >= 3 && COUNT(DISTINCT ?o) <= 25)
ORDER BY ?e ?label
```

**2. Anchor pick** — **FSTL3** (`https://identifiers.org/ncbigene/10272`).

**3. Partner pool** — for that anchor, the partner overlap query yields **1955** candidates; the RNG drew **DUSP3** (`https://identifiers.org/ncbigene/1845`).

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?shared) AS ?overlap) WHERE {
  <https://identifiers.org/ncbigene/10272> hetio:participates ?shared .
  ?e hetio:participates ?shared ;
     a hetio:Gene ;
     rdfs:label ?label .
  ?shared a hetio:Pathway .
  FILTER (?e != <https://identifiers.org/ncbigene/10272>)
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?shared) >= 1)
ORDER BY ?e ?label
```

**4. Answer** — **2** result(s) — Antagonism of Activin by Follistatin, Signaling by Activin

<details>
<summary>instantiated ground-truth query (both `VALUES` rewritten)</summary>

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX ncbigene: <https://identifiers.org/ncbigene/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?pathway ?pathwayLabel WHERE {
  VALUES ?geneA { <https://identifiers.org/ncbigene/10272> }
  VALUES ?geneB { <https://identifiers.org/ncbigene/1845> }
  ?geneA hetio:participates ?pathway .
  ?pathway a hetio:Pathway ;
           rdfs:label ?pathwayLabel .
  FILTER NOT EXISTS { ?geneB hetio:participates ?pathway . }
}
ORDER BY ?pathwayLabel
```

</details>

> **How this type samples:** `paired` **set** (type 07): two random entities almost never share a target, so the partner query returns only co-participating entities (overlap ≥ `1`), collapsing the O(n²) pair space. One partner per anchor whose `.rq` answer lands in bounds.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "07_set_difference__pathways_in_one_gene_excluding_another__00",
  "type_id": "07_set_difference",
  "template_id": "pathways_in_one_gene_excluding_another",
  "question": "Which pathways does FSTL3 participate in that DUSP3 does not?",
  "scoring": "set_match",
  "answer_var": "pathwayLabel",
  "ground_truth": [
    "Antagonism of Activin by Follistatin",
    "Signaling by Activin"
  ],
  "seeds": [
    {
      "bind_var": "geneA",
      "label": "FSTL3",
      "uri": "https://identifiers.org/ncbigene/10272"
    },
    {
      "bind_var": "geneB",
      "label": "DUSP3",
      "uri": "https://identifiers.org/ncbigene/1845"
    }
  ],
  "sampling_seed": "20260605:pathways_in_one_gene_excluding_another"
}
```

</details>

**Question:** Which pathways does FSTL3 participate in that DUSP3 does not?

---

<a id="type-08_negative_unanswerable"></a>
## `08_negative_unanswerable` — diseases_treated_by_compound_negative

**Scoring:** binary · **count:** 7 · **seed:** `20260605:diseases_treated_by_compound_negative`

**1. Candidate pool** — sample mode `lacks_edge`. Pool: **673** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?p) AS ?pfan) WHERE {
  ?e a hetio:Compound ;
     hetio:causes ?p ;
     rdfs:label ?label .
  FILTER NOT EXISTS { ?e hetio:treats ?x }
}
GROUP BY ?e ?label
HAVING (COUNT(DISTINCT ?p) >= 10)
ORDER BY ?e ?label
```

**2. The pick** — the seeded RNG drew **Testolactone** (`https://identifiers.org/drugbank/DB00894`) from the 673-entity pool.

**3. Answer** — **none** — the empty set; the correct response is refusal, not a guess

<details>
<summary>instantiated ground-truth query (`VALUES` rewritten)</summary>

```sparql
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT DISTINCT ?disease ?diseaseLabel WHERE {
  VALUES ?compound { <https://identifiers.org/drugbank/DB00894> }
  ?compound hetio:treats ?disease .
  ?disease rdfs:label ?diseaseLabel .
}
ORDER BY ?diseaseLabel
```

</details>

> **How this type samples:** `lacks_edge` (type 08 negative): `FILTER NOT EXISTS` makes the answer provably empty, while `presence_edge` keeps the entity well-attested — a *tempting hallucination* for the vector retriever, not a trivial unknown (H2).

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "08_negative_unanswerable__diseases_treated_by_compound_negative__00",
  "type_id": "08_negative_unanswerable",
  "template_id": "diseases_treated_by_compound_negative",
  "question": "Which diseases does Testolactone treat?",
  "scoring": "binary",
  "answer_var": "diseaseLabel",
  "ground_truth": [],
  "seeds": [
    {
      "bind_var": "compound",
      "label": "Testolactone",
      "uri": "https://identifiers.org/drugbank/DB00894"
    }
  ],
  "sampling_seed": "20260605:diseases_treated_by_compound_negative"
}
```

</details>

**Question:** Which diseases does Testolactone treat?

---

<a id="type-09_path_existence"></a>
## `09_path_existence` — path_between_compound_and_disease_via_gene

**Scoring:** boolean · **count:** 4 · **seed:** `20260605:path_between_compound_and_disease_via_gene`

**1. Anchor pool** — `has_edge` on the first placeholder. Pool: **1389** entities.

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT ?e ?label (COUNT(DISTINCT ?o) AS ?fan) WHERE {
  ?e a hetio:Compound ;
     hetio:binds ?o ;
     rdfs:label ?label .
}
GROUP BY ?e ?label
ORDER BY ?e ?label
```

**2. Anchor pick** — **Nitroglycerin** (`https://identifiers.org/drugbank/DB00727`).

**3. Partner pool** — for that anchor, the bridge query (`exists=True`) yields **8** candidates; the RNG drew **salivary gland cancer** (`http://purl.obolibrary.org/obo/DOID_8850`).

```sparql
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
SELECT DISTINCT ?e ?label WHERE {
  <https://identifiers.org/drugbank/DB00727> hetio:binds ?bridge .
  ?e hetio:associates ?bridge ;
     a hetio:Disease ;
     rdfs:label ?label .
}
ORDER BY ?e ?label
```

**4. Answer** — `true`

<details>
<summary>instantiated ground-truth query (both `VALUES` rewritten)</summary>

```sparql
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX do: <http://purl.obolibrary.org/obo/DOID_>
PREFIX hetio: <https://het.io/schema/>

ASK {
  VALUES ?compound { <https://identifiers.org/drugbank/DB00727> }
  VALUES ?disease { <http://purl.obolibrary.org/obo/DOID_8850> }
  ?compound hetio:binds / ^hetio:associates ?disease .
}
```

</details>

> **How this type samples:** `paired` **boolean** (type 09 path existence): a boolean answer is signal-free unless both labels appear, so the producer balances `count//2` true and the rest false, steering each partner via the bridge query, then stores the ASK `.rq`'s own result as ground truth.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "09_path_existence__path_between_compound_and_disease_via_gene__00",
  "type_id": "09_path_existence",
  "template_id": "path_between_compound_and_disease_via_gene",
  "question": "Is there a path from Nitroglycerin to salivary gland cancer through a gene the compound binds and the disease is associated with?",
  "scoring": "boolean",
  "answer_var": "boolean",
  "ground_truth": "true",
  "seeds": [
    {
      "bind_var": "compound",
      "label": "Nitroglycerin",
      "uri": "https://identifiers.org/drugbank/DB00727"
    },
    {
      "bind_var": "disease",
      "label": "salivary gland cancer",
      "uri": "http://purl.obolibrary.org/obo/DOID_8850"
    }
  ],
  "sampling_seed": "20260605:path_between_compound_and_disease_via_gene"
}
```

</details>

**Question:** Is there a path from Nitroglycerin to salivary gland cancer through a gene the compound binds and the disease is associated with?

---

<a id="type-10_fuzzy_semantic"></a>
## `10_fuzzy_semantic` — first_line_type2_diabetes_drug_fuzzy

**Scoring:** semantic · **count:** 1 · **seed:** `20260605:first_line_type2_diabetes_drug_fuzzy`

**1. No sampling.** This template has no `{placeholder}`: the reference entity is fixed inside the `.rq` (a label lookup). Identifying the unnamed entity from the discourse *is* the task, so there is no blank to fill.

**2. Answer** — **1** result(s) — Metformin

<details>
<summary>the fixed ground-truth query (`.rq`)</summary>

```sparql
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

SELECT ?compound ?compoundLabel WHERE {
  VALUES ?compound { db:DB00331 }
  ?compound a hetio:Compound ;
            rdfs:label ?compoundLabel .
}
```

</details>

> **How this type samples:** 0-placeholder fuzzy (type 10), `count: 1` by definition (one fixed reference). The other 5 fuzzy templates share this exact shape — only the hand-picked reference differs.

<details>
<summary>emitted questions.jsonl record</summary>

```json
{
  "question_id": "10_fuzzy_semantic__first_line_type2_diabetes_drug_fuzzy__00",
  "type_id": "10_fuzzy_semantic",
  "template_id": "first_line_type2_diabetes_drug_fuzzy",
  "question": "Which first-line oral drug for type 2 diabetes lowers blood glucose mainly by suppressing hepatic glucose production, and derives from a guanidine compound found in French lilac?",
  "scoring": "semantic",
  "answer_var": "compoundLabel",
  "ground_truth": [
    "Metformin"
  ],
  "seeds": [],
  "sampling_seed": "20260605:first_line_type2_diabetes_drug_fuzzy"
}
```

</details>

**Question:** Which first-line oral drug for type 2 diabetes lowers blood glucose mainly by suppressing hepatic glucose production, and derives from a guanidine compound found in French lilac?

---
