# Eval run — graph_sparqlgen → ollama:qwen2.5:3b-instruct

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `analysis/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260627T005323-graph_sparqlgen-ollama |
| `timestamp` | 2026-06-27T01:02:27+0200 |
| `retriever` | graph_sparqlgen |
| `generator_provider` | ollama |
| `generator_model` | qwen2.5:3b-instruct |
| `judge` | deterministic-v1+semantic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/produce/questions.jsonl |
| `num_questions` | 58 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `prompts` | generator=generator-v1 (96109672bcba1e4c) · writer=writer-v1 (dc05e2994f0d7ab1) · judge_semantic=judge-semantic-v1 (c513fede583abb52) |
| `generator_model_resolved` | qwen2.5:3b-instruct |
| `generator_temperature` | 0.0 |
| `corpus_build_id` | full-2c102cb0 |
| `harness_version` | harness-v1 |

## Verdicts — 11/58 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | 11 | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | CHD7 / OTOS / COCH / OTOP1 / SHC4 | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | set F1=0.62 (recall 5/11, 0 extra) |
| ❌ | `03_2hop_traversal` | set_match | None | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | prose answer: recall 0/18 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | prose answer: recall 0/17 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 184 | expected 184; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [3] Carbohydrate metabolism, Disease, Metabolism | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [2] Antagonism of Activin by Follistatin, Signaling by Activin | prose answer: recall 0/2 (precision not measurable) |
| ✅ | `08_negative_unanswerable` | binary | None | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | None | true | answer false vs expected True |
| ✅ | `10_fuzzy_semantic` | semantic | Warfarin | [1] Warfarin | equivalent — Both reference and candidate name the same anticoagulant drug. |
| ✅ | `01_0hop_attribute` | string_match | chromosome=12 | 12 | value '12' found in answer |
| ❌ | `02_1hop_factoid` | set_match | None | [2] CFL1, SMU1 | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | None | [19] AKT1, BAP1, CD4, CD5, CD8A… | prose answer: recall 0/19 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [14] Acute Coronary Syndrome, Albuminuria, Birth Weight, Body Weight, Flushing… | prose answer: recall 0/14 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 55 | expected 55; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [3] GPCR downstream signaling, Signaling Pathways, Signaling by GPCR | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [3] GPCR downstream signaling, Olfactory Signaling Pathway, Signaling by GPCR | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Heart failure / Atrial fibrillation | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `09_path_existence` | boolean | No | true | answer false vs expected True |
| ❌ | `10_fuzzy_semantic` | semantic | Noémie | [1] Metformin | different — The candidate "Noémie" is a person's name, not a drug. The correct … |
| ❌ | `01_0hop_attribute` | string_match | chr8 | 8 | value '8' not found in answer |
| ✅ | `02_1hop_factoid` | set_match | SLC12A1 / KCNJ1 / CLDN16 / SLC12A3 / UMOD / AQP2 / DDX4 / SLC9A3 / REN / CLCNKB… | [12] AQP2, BSND, CLCNKB, CLDN16, DDX4… | set F1=1.00 (recall 12/12, 0 extra) |
| ❌ | `03_2hop_traversal` | set_match | https://identifiers.org/ncbigene/834 / https://identifiers.org/ncbigene/55867 /… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 3 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [20] Acute Coronary Syndrome, Acute Pain, Albuminuria, Amaurosis Fugax, Angina … | prose answer: recall 0/20 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 46 | expected 46; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [2] Cell junction organization, Cell-Cell communication | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [8] ABC-family proteins mediated transport, ABCA transporters in lipid homeosta… | prose answer: recall 0/8 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Cysteamine treats cystinuria. | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `09_path_existence` | boolean | No | false | answer false vs expected False |
| ✅ | `10_fuzzy_semantic` | semantic | gene=https://identifiers.org/ncbigene/7157 | [1] TP53 | equivalent — The URL identifier 7157 refers to TP53 gene in NCBI Gene database. |
| ❌ | `02_1hop_factoid` | set_match | None | [14] APEX1, CCK, EOMES, FOS, HTR3A… | prose answer: recall 0/14 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | None | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | prose answer: recall 0/18 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [25] Amaurosis Fugax, Amblyopia, Anisocoria, Blindness, Choroid Hemorrhage… | prose answer: recall 0/25 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 263 | expected 263; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [3] Degradation of the extracellular matrix, Extracellular matrix organization,… | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [10] Alzheimers Disease, Binding and Uptake of Ligands by Scavenger Receptors, … | prose answer: recall 0/10 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Opioid addiction | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `09_path_existence` | boolean | No | false | answer false vs expected False |
| ✅ | `10_fuzzy_semantic` | semantic | CDH1 | [1] CDH1 | equivalent — Both reference and candidate identify the same gene: CDH1 (E-cadhe… |
| ❌ | `02_1hop_factoid` | set_match | None | [2] SACS, SIX3 | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | None | [24] APC, ATP4A, BARX1, BMP4, CDH13… | prose answer: recall 0/24 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [13] Acute Coronary Syndrome, Acute Pain, Angina Pectoris, Angina Pectoris, Var… | prose answer: recall 0/13 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 59 | expected 59; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [2] Gene Expression, Generic Transcription Pathway | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [6] Cleavage of Growing Transcript in the Termination Region, Nonsense Mediated… | prose answer: recall 0/6 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Antithrombotic | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `10_fuzzy_semantic` | semantic | Alzheimer's disease | [1] Alzheimer's disease | equivalent — Both reference and candidate name the same neurodegenerative disor… |
| ❌ | `03_2hop_traversal` | set_match | None | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | prose answer: recall 0/18 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [13] Anorexia, Diarrhea, Fatigue, Fever, Fever of Unknown Origin… | prose answer: recall 0/13 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 58 | expected 58; not among no numbers |
| ❌ | `08_negative_unanswerable` | binary | Migraine | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `10_fuzzy_semantic` | semantic | Parkinson's disease | [1] Parkinson's disease | equivalent — The candidate answer matches the reference answer exactly. |
| ❌ | `03_2hop_traversal` | set_match | None | [23] CD4, CD40LG, CD8A, CYLD, HLA-DRB1… | prose answer: recall 0/23 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [22] Blindness, Chorea, Diplopia, Down Syndrome, Edema… | prose answer: recall 0/22 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 387 | expected 387; not among no numbers |
| ❌ | `08_negative_unanswerable` | binary | Pulmonary arterial hypertension / Coronary artery disease / Deep vein thrombosis | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `04_3plus_hop_traversal` | set_match | None | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | prose answer: recall 0/17 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | None | 269 | expected 269; not among no numbers |

## By type

| type | passed |
|---|---|
| `01_0hop_attribute` | 2/3 |
| `02_1hop_factoid` | 1/5 |
| `03_2hop_traversal` | 0/7 |
| `04_3plus_hop_traversal` | 0/8 |
| `05_aggregative` | 0/8 |
| `06_set_intersection` | 0/5 |
| `07_set_difference` | 0/5 |
| `08_negative_unanswerable` | 1/7 |
| `09_path_existence` | 2/4 |
| `10_fuzzy_semantic` | 5/6 |

Billed tokens: **21760** in / **299** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
