# Eval run — closed_book → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260608T103244-closed_book-anthropic |
| `timestamp` | 2026-06-08T10:32:44+0200 |
| `retriever` | closed_book |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 9 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `harness_version` | harness-v1 |

## Verdicts — 1/9 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | Chromosome 11 | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | SOX9 / PAX8 / FGF3 / FGF10 / BMP4 / NEUROG1 / ATOH1 / GBX2 / OTP / HMXL1 / EN1 … | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | set F1=0.08 (recall 1/11, 13 extra) |
| ❌ | `03_2hop_traversal` | set_match | To answer this question, I need to identify what diseases allopurinol treats an… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.35 (recall 6/18, 20 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I'll identify the diseases treated by Norepinephrine Uptake Inhibitors and thei… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.00 (recall 0/17, 45 extra) |
| ❌ | `05_aggregative` | numerical | Galantamine causes numerous side effects. The most commonly reported include na… | 184 | expected 184; not among [20, 15, 25] |
| ❌ | `06_set_intersection` | set_match | I need to identify the pathways that both HMMR (Hyaluronan-mediated motility re… | [3] Carbohydrate metabolism, Disease, Metabolism | set F1=0.00 (recall 0/3, 12 extra) |
| ❌ | `07_set_difference` | set_match | I don't have access to a specific context that comprehensively compares FSTL3 a… | [2] Antagonism of Activin by Follistatin, Signaling by Activin | set F1=0.00 (recall 0/2, 12 extra) |
| ❌ | `08_negative_unanswerable` | binary | Testolactone treats the following diseases: /  / Breast cancer / Gynecomastia | [0]  | did not refuse — likely hallucinated an answer |
| ❌ | `09_path_existence` | boolean | I need to trace a path from Nitroglycerin → gene (that Nitroglycerin binds) → s… | true | answer false vs expected True |

## By type

| type | passed |
|---|---|
| `01_0hop_attribute` | 1/1 |
| `02_1hop_factoid` | 0/1 |
| `03_2hop_traversal` | 0/1 |
| `04_3plus_hop_traversal` | 0/1 |
| `05_aggregative` | 0/1 |
| `06_set_intersection` | 0/1 |
| `07_set_difference` | 0/1 |
| `08_negative_unanswerable` | 0/1 |
| `09_path_existence` | 0/1 |

Billed tokens: **1569** in / **1643** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
