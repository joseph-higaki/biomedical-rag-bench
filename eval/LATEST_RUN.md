# Eval run — graph_neighborhood_2hop → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260608T124417-graph_neighborhood_2hop-anthropic |
| `timestamp` | 2026-06-08T12:44:17+0200 |
| `retriever` | graph_neighborhood_2hop |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 52 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `harness_version` | harness-v1 |

## Verdicts — 12/52 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | 11 | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | I've reviewed the context provided, which contains extensive information about … | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | set F1=0.00 (recall 0/11, 6 extra) |
| ✅ | `03_2hop_traversal` | set_match | ABCG2 / ALDH16A1 / BCKDHA / CASP1 / HPRT1 / IL15 / IL1RN / LRRC16A / NLRP3 / PO… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=1.00 (recall 18/18, 0 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | To answer this question, I need to: /  / 1. Identify compounds in the Norepinep… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.05 (recall 1/17, 23 extra) |
| ❌ | `05_aggregative` | numerical | I cannot answer this question based on the provided context. The context does n… | 184 | expected 184; not among no numbers |
| ❌ | `06_set_intersection` | set_match | None | [3] Carbohydrate metabolism, Disease, Metabolism | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | Looking at the Context provided: /  / **FSTL3 participations:** / - covaries wi… | [2] Antagonism of Activin by Follistatin, Signaling by Activin | set F1=0.00 (recall 0/2, 15 extra) |
| ✅ | `08_negative_unanswerable` | binary | I cannot find information in the provided Context about which diseases Testolac… | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | No | true | answer false vs expected True |
| ✅ | `01_0hop_attribute` | string_match | 12 | 12 | value '12' found in answer |
| ❌ | `02_1hop_factoid` | set_match | Based on the context provided, there is no information about genes being expres… | [2] CFL1, SMU1 | set F1=0.00 (recall 0/2, 4 extra) |
| ❌ | `03_2hop_traversal` | set_match | To answer this question, I need to: /  / 1. Identify the diseases that Octreoti… | [19] AKT1, BAP1, CD4, CD5, CD8A… | set F1=0.08 (recall 2/19, 29 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I need to identify the diseases treated by compounds in the Ergolines class, th… | [14] Acute Coronary Syndrome, Albuminuria, Birth Weight, Body Weight, Flushing… | set F1=0.00 (recall 0/14, 36 extra) |
| ❌ | `05_aggregative` | numerical | 0 | 55 | expected 55; not among [0] |
| ❌ | `06_set_intersection` | set_match | None | [3] GPCR downstream signaling, Signaling Pathways, Signaling by GPCR | prose answer: recall 0/3 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | None | [3] GPCR downstream signaling, Olfactory Signaling Pathway, Signaling by GPCR | prose answer: recall 0/3 (precision not measurable) |
| ✅ | `08_negative_unanswerable` | binary | The context provided does not contain information about which diseases Digoxin … | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | No | true | answer false vs expected True |
| ✅ | `01_0hop_attribute` | string_match | 8 | 8 | value '8' found in answer |
| ❌ | `02_1hop_factoid` | set_match | Based on the provided context, the genes with explicit information about expres… | [12] AQP2, BSND, CLCNKB, CLDN16, DDX4… | set F1=0.40 (recall 3/12, 0 extra) |
| ❌ | `03_2hop_traversal` | set_match | I need to find what diseases Probenecid treats, then identify genes associated … | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.31 (recall 5/18, 9 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I need to find the diseases treated by compounds in the Nicotinic Acids class, … | [20] Acute Coronary Syndrome, Acute Pain, Albuminuria, Amaurosis Fugax, Angina … | set F1=0.00 (recall 0/20, 11 extra) |
| ❌ | `05_aggregative` | numerical | I cannot find information about Nateglinide in the provided context. The contex… | 46 | expected 46; not among [0] |
| ❌ | `06_set_intersection` | set_match | Based on the provided Context, there is no information indicating that LIMS2 or… | [2] Cell junction organization, Cell-Cell communication | set F1=0.00 (recall 0/2, 5 extra) |
| ❌ | `07_set_difference` | set_match | I need to find the pathways that ABCD1 participates in, then identify which one… | [8] ABC-family proteins mediated transport, ABCA transporters in lipid homeosta… | set F1=0.00 (recall 0/8, 20 extra) |
| ✅ | `08_negative_unanswerable` | binary | None | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | Yes | false | answer true vs expected False |
| ❌ | `02_1hop_factoid` | set_match | I cannot find information in the provided context about which genes are express… | [14] APEX1, CCK, EOMES, FOS, HTR3A… | set F1=0.00 (recall 0/14, 5 extra) |
| ❌ | `03_2hop_traversal` | set_match | I need to find what diseases Indomethacin treats, then identify genes associate… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 9 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, I can only identify symptoms from the diseases t… | [25] Amaurosis Fugax, Amblyopia, Anisocoria, Blindness, Choroid Hemorrhage… | set F1=0.00 (recall 0/25, 8 extra) |
| ❌ | `05_aggregative` | numerical | I need to find all the side effects that Naltrexone causes in the provided cont… | 263 | expected 263; not among [0] |
| ❌ | `06_set_intersection` | set_match | I need to find pathways that both CAPN1 and LAMA3 participate in based on the p… | [3] Degradation of the extracellular matrix, Extracellular matrix organization,… | set F1=0.00 (recall 0/3, 25 extra) |
| ❌ | `07_set_difference` | set_match | I need to find pathways that LRP1 participates in but ARHGDIB does not. /  / Le… | [10] Alzheimers Disease, Binding and Uptake of Ligands by Scavenger Receptors, … | set F1=0.06 (recall 1/10, 20 extra) |
| ✅ | `08_negative_unanswerable` | binary | I cannot find information about which diseases Methadone treats in the provided… | [0]  | correctly refused / asserted none |
| ✅ | `09_path_existence` | boolean | No. | false | answer false vs expected False |
| ✅ | `02_1hop_factoid` | set_match | SACS / SIX3 | [2] SACS, SIX3 | set F1=1.00 (recall 2/2, 0 extra) |
| ❌ | `03_2hop_traversal` | set_match | I need to find: / 1. Diseases that Omeprazole treats / 2. Genes associated with… | [24] APC, ATP4A, BARX1, BMP4, CDH13… | set F1=0.84 (recall 24/24, 9 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I need to identify which compounds are in the P2Y12 Receptor Antagonists class,… | [13] Acute Coronary Syndrome, Acute Pain, Angina Pectoris, Angina Pectoris, Var… | set F1=0.00 (recall 0/13, 11 extra) |
| ❌ | `05_aggregative` | numerical | 0 | 59 | expected 59; not among [0] |
| ❌ | `06_set_intersection` | set_match | None | [2] Gene Expression, Generic Transcription Pathway | prose answer: recall 0/2 (precision not measurable) |
| ❌ | `07_set_difference` | set_match | Based on the Context provided, I need to identify pathways that MAGOH participa… | [6] Cleavage of Growing Transcript in the Termination Region, Nonsense Mediated… | set F1=0.00 (recall 0/6, 25 extra) |
| ✅ | `08_negative_unanswerable` | binary | Based on the provided context, there is no information about which diseases Api… | [0]  | correctly refused / asserted none |
| ❌ | `03_2hop_traversal` | set_match | I cannot answer this question based on the provided context. The context does n… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 4 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, Anagrelide is the only compound listed in the Ph… | [13] Anorexia, Diarrhea, Fatigue, Fever, Fever of Unknown Origin… | set F1=0.19 (recall 3/13, 15 extra) |
| ❌ | `05_aggregative` | numerical | 0 | 58 | expected 58; not among [0] |
| ✅ | `08_negative_unanswerable` | binary | Based on the provided context, I can only find that Zolmitriptan resembles othe… | [0]  | correctly refused / asserted none |
| ❌ | `03_2hop_traversal` | set_match | I need to find which diseases Rifampicin treats, then identify which genes are … | [23] CD4, CD40LG, CD8A, CYLD, HLA-DRB1… | set F1=0.00 (recall 0/23, 5 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I can answer what diseases are treated by Thyroid Hormone Synthesis Inhibitors … | [22] Blindness, Chorea, Diplopia, Down Syndrome, Edema… | set F1=0.00 (recall 0/22, 5 extra) |
| ❌ | `05_aggregative` | numerical | I need to find information about side effects caused by Ziprasidone in the prov… | 387 | expected 387; not among no numbers |
| ❌ | `08_negative_unanswerable` | binary | Based on the Context provided, Epoprostenol treats: /  / systemic scleroderma | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `04_3plus_hop_traversal` | set_match | Based on the context provided, I can only identify that Cimetidine (a Histamine… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.09 (recall 1/17, 7 extra) |
| ❌ | `05_aggregative` | numerical | I cannot find information in the provided context about side effects caused by … | 269 | expected 269; not among [0] |

## By type

| type | passed |
|---|---|
| `01_0hop_attribute` | 3/3 |
| `02_1hop_factoid` | 1/5 |
| `03_2hop_traversal` | 1/7 |
| `04_3plus_hop_traversal` | 0/8 |
| `05_aggregative` | 0/8 |
| `06_set_intersection` | 0/5 |
| `07_set_difference` | 0/5 |
| `08_negative_unanswerable` | 6/7 |
| `09_path_existence` | 1/4 |

Billed tokens: **126208** in / **5342** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
