# Template registry

> **GENERATED — do not edit by hand.** Produced by `build_registry.py` from each template's YAML (`*.yaml`) and its ground-truth query frontmatter (`ground_truth/*.rq`).
> Regenerate: `uv run --extra produce python produce/templates/build_registry.py` (add `--verify` to re-check answers against GraphDB).

The `.rq` frontmatter is authoritative for the committed seed and answer; this table copies it. Templates are ordered by `type_id` (taxonomy order).

| `type_id` | Template | Question | Committed seed | Answer |
|---|---|---|---|---|
| `01_0hop_attribute` | `chromosome_of_gene` | On which chromosome is the gene {gene} located? | CDH1 (`ncbigene:999`) | `16` |
| `02_1hop_factoid` | `genes_expressed_in_anatomy` | Which genes are expressed in {anatomy}? | nasal cavity (`uberon:0001707`) | 4 results |
| `03_2hop_traversal` | `genes_associated_with_compound_treated_diseases` | Which genes are associated with the diseases that {compound} treats? | Tiludronate (`db:DB01133`) | 16 results |
| `04_3plus_hop_traversal` | `symptoms_of_pharmacologic_class_treated_diseases` | Which symptoms are presented by the diseases treated by compounds in the {drug_class} class? | Sulfonylurea Compounds (`ndfrt:N0000008054`) | 18 results |
| `05_aggregative` | `count_of_side_effects_caused_by_compound` | How many side effects does {compound} cause? | Streptomycin (`db:DB01082`) | `27` |
| `06_set_intersection` | `shared_pathways_of_two_genes` | Which pathways do both {gene_a} and {gene_b} participate in? | BRCA1 (`ncbigene:672`), BRCA2 (`ncbigene:675`) | 11 results |
| `07_set_difference` | `pathways_in_one_gene_excluding_another` | Which pathways does {gene_a} participate in that {gene_b} does not? | BRCA2 (`ncbigene:675`), BRCA1 (`ncbigene:672`) | 7 results |
| `08_negative_unanswerable` | `diseases_treated_by_compound_negative` | Which diseases does {compound} treat? | Caffeine (`db:DB00201`) | none (negative) |
| `09_path_existence` | `path_between_compound_and_disease_via_gene` | Is there a path from {compound} to {disease} through a gene the compound binds and the disease is associated with? | Tamoxifen (`db:DB00675`), breast cancer (`do:1612`) | `True` |
| `10_fuzzy_semantic` | `anticoagulant_vitamin_k_antagonist_fuzzy` | Which oral anticoagulant, a vitamin K antagonist first developed as a rodenticide, has a narrow therapeutic window requiring regular INR monitoring? | Warfarin (`db:DB00682`) | 1 results |
| `10_fuzzy_semantic` | `first_line_type2_diabetes_drug_fuzzy` | Which first-line oral drug for type 2 diabetes lowers blood glucose mainly by suppressing hepatic glucose production, and derives from a guanidine compound found in French lilac? | Metformin (`db:DB00331`) | 1 results |
| `10_fuzzy_semantic` | `gene_guarding_genome_against_dna_damage_fuzzy` | Which gene, often called the "guardian of the genome," halts the cell cycle or triggers apoptosis in response to DNA damage and is the most frequently mutated gene in human cancers? | TP53 (`ncbigene:7157`) | 1 results |
| `10_fuzzy_semantic` | `gene_whose_loss_promotes_metastasis_fuzzy` | Which gene's loss promotes tumor metastasis through breakdown of cell-cell adhesion? | CDH1 (`ncbigene:999`) | 1 results |
| `10_fuzzy_semantic` | `neurodegenerative_amyloid_tau_dementia_fuzzy` | Which progressive neurodegenerative disorder is characterized by extracellular amyloid-beta plaques and intracellular tau neurofibrillary tangles, leading to gradual memory loss and cognitive decline? | Alzheimer's disease (`do:10652`) | 1 results |
| `10_fuzzy_semantic` | `neurodegenerative_dopaminergic_movement_disorder_fuzzy` | Which neurodegenerative movement disorder arises from the loss of dopaminergic neurons in the substantia nigra and presents with resting tremor, rigidity, and bradykinesia? | Parkinson's disease (`do:14330`) | 1 results |

## Per-template detail

### `01_0hop_attribute` — chromosome_of_gene

**Question:** On which chromosome is the gene {gene} located?

**Chain:** Gene property lookup hetio:chromosome (0-hop, no edge traversal)

**Committed seed:** CDH1 (`ncbigene:999`)

**Scoring:** `string_match` · answer column `chromosome`

**Ground-truth answer:** `16`

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

### `07_set_difference` — pathways_in_one_gene_excluding_another

**Question:** Which pathways does {gene_a} participate in that {gene_b} does not?

**Chain:** Gene --participates--> Pathway, set difference (gene_a pathways minus gene_b)

**Committed seed:** BRCA2 (`ncbigene:675`), BRCA1 (`ncbigene:672`)

**Scoring:** `set_match` · answer column `pathwayLabel`

**Ground-truth answer (7):**
- ATR signaling pathway
- FOXM1 transcription factor network
- Homologous DNA pairing and strand exchange
- Homologous recombination
- Presynaptic phase of homologous DNA pairing and strand exchange
- Validated transcriptional targets of deltaNp63 isoforms
- p73 transcription factor network

### `08_negative_unanswerable` — diseases_treated_by_compound_negative

**Question:** Which diseases does {compound} treat?

**Chain:** Compound --treats--> Disease (no such edge for this seed)

**Committed seed:** Caffeine (`db:DB00201`)

**Scoring:** `binary` · answer column `diseaseLabel`

**Ground-truth answer:** none — the queried edge does not exist; the correct response is refusal, not a guess.

### `09_path_existence` — path_between_compound_and_disease_via_gene

**Question:** Is there a path from {compound} to {disease} through a gene the compound binds and the disease is associated with?

**Chain:** Compound --binds--> Gene <--associates-- Disease (ASK — does the path exist?)

**Committed seed:** Tamoxifen (`db:DB00675`), breast cancer (`do:1612`)

**Scoring:** `boolean` · answer column `boolean`

**Ground-truth answer:** `True`

### `10_fuzzy_semantic` — anticoagulant_vitamin_k_antagonist_fuzzy

**Question:** Which oral anticoagulant, a vitamin K antagonist first developed as a rodenticide, has a narrow therapeutic window requiring regular INR monitoring?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** Warfarin (`db:DB00682`)

**Scoring:** `semantic` · answer column `compoundLabel`

**Ground-truth answer (1):**
- Warfarin

### `10_fuzzy_semantic` — first_line_type2_diabetes_drug_fuzzy

**Question:** Which first-line oral drug for type 2 diabetes lowers blood glucose mainly by suppressing hepatic glucose production, and derives from a guanidine compound found in French lilac?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** Metformin (`db:DB00331`)

**Scoring:** `semantic` · answer column `compoundLabel`

**Ground-truth answer (1):**
- Metformin

### `10_fuzzy_semantic` — gene_guarding_genome_against_dna_damage_fuzzy

**Question:** Which gene, often called the "guardian of the genome," halts the cell cycle or triggers apoptosis in response to DNA damage and is the most frequently mutated gene in human cancers?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** TP53 (`ncbigene:7157`)

**Scoring:** `semantic` · answer column `geneLabel`

**Ground-truth answer (1):**
- TP53

### `10_fuzzy_semantic` — gene_whose_loss_promotes_metastasis_fuzzy

**Question:** Which gene's loss promotes tumor metastasis through breakdown of cell-cell adhesion?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** CDH1 (`ncbigene:999`)

**Scoring:** `semantic` · answer column `geneLabel`

**Ground-truth answer (1):**
- CDH1

### `10_fuzzy_semantic` — neurodegenerative_amyloid_tau_dementia_fuzzy

**Question:** Which progressive neurodegenerative disorder is characterized by extracellular amyloid-beta plaques and intracellular tau neurofibrillary tangles, leading to gradual memory loss and cognitive decline?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** Alzheimer's disease (`do:10652`)

**Scoring:** `semantic` · answer column `diseaseLabel`

**Ground-truth answer (1):**
- Alzheimer's disease

### `10_fuzzy_semantic` — neurodegenerative_dopaminergic_movement_disorder_fuzzy

**Question:** Which neurodegenerative movement disorder arises from the loss of dopaminergic neurons in the substantia nigra and presents with resting tremor, rigidity, and bradykinesia?

**Chain:** reference-entity label lookup (fuzzy/semantic — no traversal derives this answer)

**Committed seed:** Parkinson's disease (`do:14330`)

**Scoring:** `semantic` · answer column `diseaseLabel`

**Ground-truth answer (1):**
- Parkinson's disease

