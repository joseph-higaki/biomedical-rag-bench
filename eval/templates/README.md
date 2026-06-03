# Template registry

> **GENERATED — do not edit by hand.** Produced by `build_registry.py` from each template's YAML (`*.yaml`) and its ground-truth query frontmatter (`ground_truth/*.rq`).
> Regenerate: `uv run --extra produce python eval/templates/build_registry.py` (add `--verify` to re-check answers against GraphDB).

The `.rq` frontmatter is authoritative for the committed seed and answer; this table copies it. Templates are ordered by `type_id` (taxonomy order).

| `type_id` | Template | Question | Committed seed | Answer |
|---|---|---|---|---|
| `02_1hop_factoid` | `genes_expressed_in_anatomy` | Which genes are expressed in {anatomy}? | nasal cavity (`uberon:0001707`) | 4 results |
| `03_2hop_traversal` | `genes_associated_with_compound_treated_diseases` | Which genes are associated with the diseases that {compound} treats? | Tiludronate (`db:DB01133`) | 16 results |
| `04_3plus_hop_traversal` | `symptoms_of_pharmacologic_class_treated_diseases` | Which symptoms are presented by the diseases treated by compounds in the {drug_class} class? | Sulfonylurea Compounds (`ndfrt:N0000008054`) | 18 results |
| `05_aggregative` | `count_of_side_effects_caused_by_compound` | How many side effects does {compound} cause? | Streptomycin (`db:DB01082`) | `27` |
| `06_set_intersection` | `shared_pathways_of_two_genes` | Which pathways do both {gene_a} and {gene_b} participate in? | BRCA1 (`ncbigene:672`), BRCA2 (`ncbigene:675`) | 11 results |

## Per-template detail

### `02_1hop_factoid` — genes_expressed_in_anatomy

**Question:** Which genes are expressed in {anatomy}?

**Chain:** Anatomy --expresses--> Gene

**Committed seed:** nasal cavity (`uberon:0001707`)

**Scoring:** `set_match` · answer column `geneLabel`

**Ground-truth answer (4):**
- CD79A
- DCXR
- OMP
- RHNO1

### `03_2hop_traversal` — genes_associated_with_compound_treated_diseases

**Question:** Which genes are associated with the diseases that {compound} treats?

**Chain:** Compound --treats--> Disease --associates--> Gene

**Committed seed:** Tiludronate (`db:DB01133`)

**Scoring:** `set_match` · answer column `geneLabel`

**Ground-truth answer (16):**
- ALPL
- ALPP
- ALPPL2
- BGLAP
- CALCA
- CSF1
- DCSTAMP
- INPP5D
- NUP205
- OPTN
- PML
- RIN3
- SQSTM1
- TNFRSF11A
- TNFRSF11B
- VCP

### `04_3plus_hop_traversal` — symptoms_of_pharmacologic_class_treated_diseases

**Question:** Which symptoms are presented by the diseases treated by compounds in the {drug_class} class?

**Chain:** PharmacologicClass --includes--> Compound --treats--> Disease --presents--> Symptom

**Committed seed:** Sulfonylurea Compounds (`ndfrt:N0000008054`)

**Scoring:** `set_match` · answer column `symptomLabel`

**Ground-truth answer (18):**
- Acute Coronary Syndrome
- Albuminuria
- Birth Weight
- Body Weight
- Fetal Distress
- Fetal Hypoxia
- Fetal Macrosomia
- Fetal Weight
- Flushing
- Gastroparesis
- Microvascular Angina
- Obesity
- Obesity, Abdominal
- Overweight
- Proteinuria
- Urinary Bladder, Overactive
- Weight Gain
- Weight Loss

### `05_aggregative` — count_of_side_effects_caused_by_compound

**Question:** How many side effects does {compound} cause?

**Chain:** Compound --causes--> SideEffect (aggregated by COUNT DISTINCT)

**Committed seed:** Streptomycin (`db:DB01082`)

**Scoring:** `numerical` · answer column `n`

**Ground-truth answer:** `27`

### `06_set_intersection` — shared_pathways_of_two_genes

**Question:** Which pathways do both {gene_a} and {gene_b} participate in?

**Chain:** Gene --participates--> Pathway, intersected over two genes

**Committed seed:** BRCA1 (`ncbigene:672`), BRCA2 (`ncbigene:675`)

**Scoring:** `set_match` · answer column `pathwayLabel`

**Ground-truth answer (11):**
- Cell Cycle
- DNA Repair
- Double-Strand Break Repair
- Fanconi Anemia pathway
- Fanconi anemia pathway
- Homologous Recombination Repair
- Integrated Breast Cancer Pathway
- Integrated Pancreatic Cancer Pathway
- Meiosis
- Meiotic recombination
- Signaling Pathways in Glioblastoma

