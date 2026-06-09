# Eval run — graph_sparqlgen → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260609T135010-graph_sparqlgen-anthropic |
| `timestamp` | 2026-06-09T13:52:45+0200 |
| `retriever` | graph_sparqlgen |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 52 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `generator_model_resolved` | claude-haiku-4-5-20251001 |
| `generator_temperature` | None |
| `harness_version` | harness-v1 |

## Verdicts — 15/52 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | 11 | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | CHD7 / OTOS / UBIAD1 / OC90 / COCH / BMP4 / CRLF1 / OTOP1 / HMX3 | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | set F1=0.90 (recall 9/11, 0 extra) |
| ✅ | `03_2hop_traversal` | set_match | ABCG2 / PRPS2 / CASP1 / SLC22A11 / SLC17A1 / SLC2A9 / NLRP3 / IL15 / POMC / ALD… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=1.00 (recall 18/18, 0 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I cannot answer this question based on the provided Context. The Context lists … | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.00 (recall 0/17, 5 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine a specific number of side effects from the context provided,… | 184 | expected 184; matched [184, 184] |
| ❌ | `06_set_intersection` | set_match | I don't have information in the provided context about which pathways HMMR and … | [3] Carbohydrate metabolism, Disease, Metabolism | set F1=0.67 (recall 3/3, 3 extra) |
| ❌ | `07_set_difference` | set_match | I don't have information in the provided Context about which specific genes (FS… | [2] Antagonism of Activin by Follistatin, Signaling by Activin | set F1=0.00 (recall 0/2, 4 extra) |
| ❌ | `08_negative_unanswerable` | binary | Testolactone is used to treat: /  / Breast cancer / Gynecomastia | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `09_path_existence` | boolean | Yes | true | answer true vs expected True |
| ✅ | `01_0hop_attribute` | string_match | 12 | 12 | value '12' found in answer |
| ❌ | `02_1hop_factoid` | set_match | None | [2] CFL1, SMU1 | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context lists … | [19] AKT1, BAP1, CD4, CD5, CD8A… | set F1=0.00 (recall 0/19, 4 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Overweight / Weight Loss / Obesity, Abdominal / Flushing / Urinary Bladder, Ove… | [14] Acute Coronary Syndrome, Albuminuria, Birth Weight, Body Weight, Flushing… | set F1=0.90 (recall 14/14, 3 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine the number of side effects from the provided context, which … | 55 | expected 55; matched [55, 20, 30] |
| ❌ | `06_set_intersection` | set_match | I don't have information in the provided context about which pathways OR56A4 an… | [3] GPCR downstream signaling, Signaling Pathways, Signaling by GPCR | set F1=0.00 (recall 0/3, 5 extra) |
| ✅ | `07_set_difference` | set_match | Signaling by GPCR / GPCR downstream signaling / Olfactory Signaling Pathway | [3] GPCR downstream signaling, Olfactory Signaling Pathway, Signaling by GPCR | set F1=1.00 (recall 3/3, 0 extra) |
| ❌ | `08_negative_unanswerable` | binary | Atrial fibrillation / Heart failure / Atrial flutter / Supraventricular tachyca… | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `09_path_existence` | boolean | Yes | true | answer true vs expected True |
| ✅ | `01_0hop_attribute` | string_match | 8 | 8 | value '8' found in answer |
| ❌ | `02_1hop_factoid` | set_match | SLC12A1 / KCNJ1 / CLDN16 / UMOD / BSND / SLC9A3 | [12] AQP2, BSND, CLCNKB, CLDN16, DDX4… | set F1=0.67 (recall 6/12, 0 extra) |
| ❌ | `03_2hop_traversal` | set_match | ABCG2 / SLC22A11 / SLC17A1 / SLC2A9 / NLRP3 / CASP1 / IL1RN / SLC22A12 / UMOD | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.67 (recall 9/18, 0 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Chest Pain / Acute Pain / Sleep Apnea, Obstructive / Angina Pectoris, Variant /… | [20] Acute Coronary Syndrome, Acute Pain, Albuminuria, Amaurosis Fugax, Angina … | set F1=0.68 (recall 20/20, 13 extra) |
| ✅ | `05_aggregative` | numerical | 46 | 46 | expected 46; matched [46] |
| ❌ | `06_set_intersection` | set_match | I need to determine which pathways both LIMS2 and CDH4 participate in based on … | [2] Cell junction organization, Cell-Cell communication | set F1=0.40 (recall 2/2, 6 extra) |
| ❌ | `07_set_difference` | set_match | I cannot answer this question based on the provided context. The context lists … | [8] ABC-family proteins mediated transport, ABCA transporters in lipid homeosta… | prose answer: recall 0/8 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Cystinosis / Homocystinuria / Disulfiduria | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `09_path_existence` | boolean | I need to determine if there's a path from Pyridoxal (a form of vitamin B6) to … | false | answer true vs expected False |
| ❌ | `02_1hop_factoid` | set_match | I cannot answer this question based on the provided context. The context lists … | [14] APEX1, CCK, EOMES, FOS, HTR3A… | prose answer: recall 0/14 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based solely on the provided Context. The Context… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.92 (recall 18/18, 3 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Vision, Low / Scotoma / Vitreous Hemorrhage / Edema / Pallor / Eye Hemorrhage /… | [25] Amaurosis Fugax, Amblyopia, Anisocoria, Blindness, Choroid Hemorrhage… | set F1=0.94 (recall 24/25, 2 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine from the provided context how many side effects Naltrexone c… | 263 | expected 263; matched [263] |
| ❌ | `06_set_intersection` | set_match | None | [3] Degradation of the extracellular matrix, Extracellular matrix organization,… | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | I cannot determine which pathways LRP1 participates in that ARHGDIB does not ba… | [10] Alzheimers Disease, Binding and Uptake of Ligands by Scavenger Receptors, … | prose answer: recall 0/10 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Opioid use disorder / Pain (chronic) / Pain (acute) | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `09_path_existence` | boolean | I need to determine if there's a path from Duloxetine (a drug) to osteoporosis … | false | answer true vs expected False |
| ❌ | `02_1hop_factoid` | set_match | Based on the provided context, I cannot determine which of these genes are expr… | [2] SACS, SIX3 | set F1=0.25 (recall 2/2, 6 extra) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question using only the provided context. The context list… | [24] APC, ATP4A, BARX1, BMP4, CDH13… | prose answer: recall 0/24 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | Chest Pain / Acute Pain / Sleep Apnea, Obstructive / Angina Pectoris, Variant /… | [13] Acute Coronary Syndrome, Acute Pain, Angina Pectoris, Angina Pectoris, Var… | set F1=0.59 (recall 13/13, 11 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine the number of side effects Pirbuterol causes from the provid… | 59 | expected 59; matched [59, 2] |
| ❌ | `06_set_intersection` | set_match | I cannot determine which pathways both ZNF257 and ZNF682 participate in based o… | [2] Gene Expression, Generic Transcription Pathway | set F1=0.67 (recall 2/2, 1 extra) |
| ❌ | `07_set_difference` | set_match | I don't have information in the provided context about which specific proteins … | [6] Cleavage of Growing Transcript in the Termination Region, Nonsense Mediated… | set F1=0.00 (recall 0/6, 5 extra) |
| ❌ | `08_negative_unanswerable` | binary | Venous thromboembolism / Atrial fibrillation / Acute coronary syndrome / Pulmon… | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context lists … | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.90 (recall 18/18, 4 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I cannot answer this question based on the provided Context. The Context lists … | [13] Anorexia, Diarrhea, Fatigue, Fever, Fever of Unknown Origin… | set F1=0.00 (recall 0/13, 5 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine the number of side effects caffeine causes from the provided… | 58 | expected 58; matched [58, 58] |
| ❌ | `08_negative_unanswerable` | binary | Migraine / Cluster headache | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `03_2hop_traversal` | set_match | I need to determine which diseases Rifampicin treats, then identify which genes… | [23] CD4, CD40LG, CD8A, CYLD, HLA-DRB1… | set F1=0.84 (recall 23/23, 9 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Vocal Cord Paralysis / Diplopia / Scotoma / Hypergammaglobulinemia / Neurologic… | [22] Blindness, Chorea, Diplopia, Down Syndrome, Edema… | set F1=0.87 (recall 22/22, 6 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine the number of side effects from the provided context, which … | 387 | expected 387; matched [387, 20, 387, 387] |
| ❌ | `08_negative_unanswerable` | binary | Pulmonary arterial hypertension / Pulmonary hypertension / Raynaud's phenomenon… | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `04_3plus_hop_traversal` | set_match | I need to answer which symptoms are presented by diseases treated by compounds … | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.07 (recall 1/17, 12 extra) |
| ✅ | `05_aggregative` | numerical | I cannot determine the number of side effects Zonisamide causes from the provid… | 269 | expected 269; matched [269, 20, 30] |

## By type

| type | passed |
|---|---|
| `01_0hop_attribute` | 3/3 |
| `02_1hop_factoid` | 0/5 |
| `03_2hop_traversal` | 1/7 |
| `04_3plus_hop_traversal` | 0/8 |
| `05_aggregative` | 8/8 |
| `06_set_intersection` | 0/5 |
| `07_set_difference` | 1/5 |
| `08_negative_unanswerable` | 0/7 |
| `09_path_existence` | 2/4 |

Billed tokens: **22782** in / **4683** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
