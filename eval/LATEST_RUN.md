# Eval run — vector → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260608T110036-vector-anthropic |
| `timestamp` | 2026-06-08T11:00:36+0200 |
| `retriever` | vector |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 9 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `harness_version` | harness-v1 |

## Verdicts — 2/9 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `01_0hop_attribute` | string_match | I cannot find information about the chromosome location of HTR3B in the provide… | 11 | value '11' found in answer |
| ❌ | `02_1hop_factoid` | set_match | None | [11] BMP4, CHD7, COCH, CRLF1, HMX3… | prose answer: recall 0/11 (precision not measurable) |
| ❌ | `03_2hop_traversal` | set_match | Based on the provided context, there is no information about Allopurinol or the… | [18] ABCG2, ALDH16A1, BCKDHA, CASP1, HPRT1… | set F1=0.00 (recall 0/18, 6 extra) |
| ❌ | `04_3plus_hop_traversal` | set_match | I cannot answer this question based on the provided context. The context docume… | [17] Body Weight, Bulimia, Hyperphagia, Hypoventilation, Ideal Body Weight… | set F1=0.00 (recall 0/17, 7 extra) |
| ❌ | `05_aggregative` | numerical | I cannot find information about Galantamine's side effects in the provided cont… | 184 | expected 184; not among [27] |
| ❌ | `06_set_intersection` | set_match | None /  / The provided context does not contain information about HMMR or NUP15… | [3] Carbohydrate metabolism, Disease, Metabolism | set F1=0.00 (recall 0/3, 6 extra) |
| ❌ | `07_set_difference` | set_match | None. /  / The provided context does not contain information about FSTL3 or DUS… | [2] Antagonism of Activin by Follistatin, Signaling by Activin | set F1=0.00 (recall 0/2, 4 extra) |
| ✅ | `08_negative_unanswerable` | binary | I cannot answer this question based on the provided context. The context discus… | [0]  | correctly refused / asserted none |
| ❌ | `09_path_existence` | boolean | No. /  / The provided context contains information about CDH1, PSMA3, and METTL… | true | answer false vs expected True |

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
| `08_negative_unanswerable` | 1/1 |
| `09_path_existence` | 0/1 |

Billed tokens: **13002** in / **748** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
