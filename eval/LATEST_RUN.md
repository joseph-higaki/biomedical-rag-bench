# Eval run — vector → anthropic:claude-haiku-4-5

> **Generated file — do not edit.** `eval/run_eval.py --run` overwrites this on every run. Curated cross-run observations and validity caveats live in `eval/FINDINGS.md`.

> **Preliminary — not the definitive metrics.** This is the latest run's auto-table snapshot for offline review. Definitive accuracy / recall / H7 analysis comes from the notebook + dashboard that read the per-row JSONL; it is a small smoke sample — read the verdicts, not a leaderboard.

## Run manifest

| factor | value |
|---|---|
| `run_id` | 20260608T215522-vector-anthropic |
| `timestamp` | 2026-06-08T21:56:06+0200 |
| `retriever` | vector |
| `generator_provider` | anthropic |
| `generator_model` | claude-haiku-4-5 |
| `judge` | deterministic-v1+semantic-v1 |
| `questions_path` | /home/jhigaki/projects/biomedical-rag-bench/eval/questions.jsonl |
| `num_questions` | 6 |
| `system_prompt_sha256` | 96109672bcba1e4c |
| `harness_version` | harness-v1 |

## Verdicts — 5/6 passed

| result | type | scoring | predicted | ground truth | verdict |
|---|---|---|---|---|---|
| ✅ | `10_fuzzy_semantic` | semantic | Warfarin | [1] Warfarin | equivalent — Both reference and candidate name the same anticoagulant drug. |
| ✅ | `10_fuzzy_semantic` | semantic | Metformin | [1] Metformin | equivalent — Exact match to the reference answer for the first-line antidiabeti… |
| ✅ | `10_fuzzy_semantic` | semantic | p53 | [1] TP53 | equivalent — p53 is the standard protein name for the TP53 gene product; they r… |
| ❌ | `10_fuzzy_semantic` | semantic | Based on the provided context, **IGF1R** and **KRIT1** are genes whose loss/dys… | [1] CDH1 | different — Candidate names KRIT1 and IGF1R; reference is CDH1 (E-cadherin), th… |
| ✅ | `10_fuzzy_semantic` | semantic | Alzheimer's disease | [1] Alzheimer's disease | equivalent — Both reference and candidate name the same neurodegenerative disor… |
| ✅ | `10_fuzzy_semantic` | semantic | Parkinson's disease | [1] Parkinson's disease | equivalent — The candidate answer matches the reference answer exactly. |

## By type

| type | passed |
|---|---|
| `10_fuzzy_semantic` | 5/6 |

Billed tokens: **8861** in / **191** out (generator's tokenizer; closed-book input is the no-retrieval baseline).
