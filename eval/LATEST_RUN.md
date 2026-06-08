# Eval run — vector → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260608T161819-vector-anthropic |
| `timestamp` | 2026-06-08T16:20:28+0200 |
| `retriever` | vector |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 52 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `harness_version` | harness-v1 |

## Verdicts — 8/52 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | I cannot find information about the chromosome location of HTR3B in the provide… | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | Based on the provided context, the genes mentioned as being expressed in semici… | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | set F1=0.00 (recall 0/11, 7 extra) |
| ❌ | `03_2hop_traversal` | set_match | Based on the context provided, the only disease mentioned in relation to allopu… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 8 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the Context provided for Norepinephrine Uptake Inhibitors, the documen… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.00 (recall 0/17, 9 extra) |
| ❌ | `05_aggregative` | numerical | The provided context does not specify a total number of side effects caused by … | 184 | expected 184; not among no numbers |
| ❌ | `06_set_intersection` | set_match | I cannot answer this question based on the provided Context. The Context does n… | [3] Carbohydrate metabolism, Disease, Metabolism | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [2] Antagonism of Activin by Follistatin, Signaling by Activin | prose answer: recall 0/2 (precision not measurable) |
| ✅ | `08_negative_unanswerable` | binary | I cannot find information about Testolactone or diseases it treats in the provi… | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | No /  / The provided context contains information about salivary gland cancer a… | true | answer false vs expected True |
| ❌ | `01_0hop_attribute` | string_match | I cannot answer this question based on the provided context. The context does n… | 12 | value '12' not found in answer |
| ❌ | `02_1hop_factoid` | set_match | None | [2] CFL1, SMU1 | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context discus… | [19] AKT1, BAP1, CD4, CD5, CD8A… | set F1=0.00 (recall 0/19, 10 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I cannot answer this question based on the provided context. The context docume… | [14] Acute Coronary Syndrome, Albuminuria, Birth Weight, Body Weight, Flushing… | prose answer: recall 0/14 (precision not measurable) |
| ❌ | `05_aggregative` | numerical | The provided context does not contain information about Aminocaproic Acid or it… | 55 | expected 55; not among [450] |
| ❌ | `06_set_intersection` | set_match | None | [3] GPCR downstream signaling, Signaling Pathways, Signaling by GPCR | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None /  / The provided context contains information about YWHAZ's participation… | [3] GPCR downstream signaling, Olfactory Signaling Pathway, Signaling by GPCR | set F1=0.00 (recall 0/3, 4 extra) |
| ❌ | `08_negative_unanswerable` | binary | Based on the provided context, Digoxin treats: /  / Heart failure with reduced … | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `09_path_existence` | boolean | No. /  / The context shows that bortezomib resistance is associated with GALNT1… | true | answer false vs expected True |
| ✅ | `01_0hop_attribute` | string_match | I cannot answer this question based on the provided context. The context discus… | 8 | value '8' found in answer |
| ❌ | `02_1hop_factoid` | set_match | None | [12] AQP2, BSND, CLCNKB, CLDN16, DDX4… | prose answer: recall 0/12 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided Context. The Context discus… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 9 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, I cannot find information about compounds in the… | [20] Acute Coronary Syndrome, Acute Pain, Albuminuria, Amaurosis Fugax, Angina … | set F1=0.00 (recall 0/20, 6 extra) |
| ❌ | `05_aggregative` | numerical | None. | 46 | expected 46; not among no numbers |
| ❌ | `06_set_intersection` | set_match | Based on the provided context, CDH4 is not mentioned in any of the documents. T… | [2] Cell junction organization, Cell-Cell communication | set F1=0.00 (recall 0/2, 8 extra) |
| ❌ | `07_set_difference` | set_match | I cannot answer this question based on the provided context. The context contai… | [8] ABC-family proteins mediated transport, ABCA transporters in lipid homeosta… | prose answer: recall 0/8 (precision not measurable) |
| ✅ | `08_negative_unanswerable` | binary | I cannot answer this question based on the provided Context. The Context contai… | [0]  | correctly refused / asserted none |
| ✅ | `09_path_existence` | boolean | I cannot determine a path from Pyridoxal to brain cancer through the provided c… | false | answer false vs expected False |
| ❌ | `02_1hop_factoid` | set_match | None /  / The context provided discusses genes expressed in cardiac tissue (car… | [14] APEX1, CCK, EOMES, FOS, HTR3A… | set F1=0.00 (recall 0/14, 6 extra) |
| ❌ | `03_2hop_traversal` | set_match | Based on the provided context, there is no information about which diseases Ind… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 4 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, the only Cholinergic Muscarinic Agonist-related … | [25] Amaurosis Fugax, Amblyopia, Anisocoria, Blindness, Choroid Hemorrhage… | set F1=0.00 (recall 0/25, 9 extra) |
| ❌ | `05_aggregative` | numerical | The context provided does not contain information about the total number or com… | 263 | expected 263; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [3] Degradation of the extracellular matrix, Extracellular matrix organization,… | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | I cannot answer this question based on the provided context. The context does n… | [10] Alzheimers Disease, Binding and Uptake of Ligands by Scavenger Receptors, … | prose answer: recall 0/10 (precision not measurable) |
| ❌ | `08_negative_unanswerable` | binary | Based on the provided context, Methadone is used to treat: /  / Opioid use diso… | [0]  | did not refuse — likely hallucinated an answer |
| ✅ | `09_path_existence` | boolean | No. /  / While the context mentions several genes associated with osteoporosis … | false | answer false vs expected False |
| ❌ | `02_1hop_factoid` | set_match | None | [2] SACS, SIX3 | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context contai… | [24] APC, ATP4A, BARX1, BMP4, CDH13… | set F1=0.00 (recall 0/24, 14 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I cannot answer this question based on the provided context. The context docume… | [13] Acute Coronary Syndrome, Acute Pain, Angina Pectoris, Angina Pectoris, Var… | set F1=0.00 (recall 0/13, 7 extra) |
| ❌ | `05_aggregative` | numerical | None. /  / The provided context does not contain any information about Pirbuter… | 59 | expected 59; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [2] Gene Expression, Generic Transcription Pathway | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | Based on the provided context, I can only identify information about MAGOH's pa… | [6] Cleavage of Growing Transcript in the Termination Region, Nonsense Mediated… | set F1=0.00 (recall 0/6, 7 extra) |
| ✅ | `08_negative_unanswerable` | binary | I cannot find information about Apixaban in the provided context. The context c… | [0]  | correctly refused / asserted none |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context discus… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | prose answer: recall 0/18 (precision not measurable) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the provided context, there is no information about Phosphodiesterase … | [13] Anorexia, Diarrhea, Fatigue, Fever, Fever of Unknown Origin… | set F1=0.00 (recall 0/13, 7 extra) |
| ❌ | `05_aggregative` | numerical | I cannot determine a specific number of side effects that caffeine causes based… | 58 | expected 58; not among [42247558] |
| ❌ | `08_negative_unanswerable` | binary | Based on the provided context, zolmitriptan is used to treat: /  / Migraine | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `03_2hop_traversal` | set_match | Based on the context provided, I cannot identify which genes are associated wit… | [23] CD4, CD40LG, CD8A, CYLD, HLA-DRB1… | set F1=0.00 (recall 0/23, 11 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, the symptoms presented by diseases treated by th… | [22] Blindness, Chorea, Diplopia, Down Syndrome, Edema… | set F1=0.00 (recall 0/22, 4 extra) |
| ❌ | `05_aggregative` | numerical | Based on the provided context, the study on ziprasidone focused specifically on… | 387 | expected 387; not among [3, 59, 95, 2, 3, 6, 35] |
| ✅ | `08_negative_unanswerable` | binary | None | [0]  | correctly refused / asserted none |
| ❌ | `04_3plus_hop_traversal` | set_match | None. /  / The context provided does not contain information about Histamine H2… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.00 (recall 0/17, 2 extra) |
| ❌ | `05_aggregative` | numerical | None | 269 | expected 269; not among no numbers |

## By type

| type | passed |
|---|---|
| `01_0hop_attribute` | 2/3 |
| `02_1hop_factoid` | 0/5 |
| `03_2hop_traversal` | 0/7 |
| `04_3plus_hop_traversal` | 0/8 |
| `05_aggregative` | 0/8 |
| `06_set_intersection` | 0/5 |
| `07_set_difference` | 0/5 |
| `08_negative_unanswerable` | 4/7 |
| `09_path_existence` | 2/4 |

Billed tokens: **69308** in / **4264** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
