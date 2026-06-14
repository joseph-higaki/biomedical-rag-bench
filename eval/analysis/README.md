# Analysis layer

**Purpose.** Turn the harness's per-run output into one tidy, deduplicated pandas DataFrame
for exploration and (eventually) a dashboard. This is the *consumer* end of the benchmark, not
part of producing results.

**Inputs → Outputs.** `eval/results/<run_id>.jsonl` + `<run_id>.manifest.json`
(+ `eval/corpus/<id>.json`) → one canonical DataFrame (see [`load.py`](load.py)).
**Key files.** `load.py` (discover + join + dedup-to-canonical-grain + reshape), `explore.ipynb`
(exploratory charts). **How to run.** Import `from eval.analysis import load` in a notebook.
**Where it sits.** Downstream of the Eval harness; reads the [Output contract](../../README.md#output-contract-downstream-interface).

## Extraction boundary (planned)

This directory is the **lift-out point** for a separate analytics repo
(`biomedical-rag-bench-analytics`). This repo's responsibility ends at the Output contract
above; analysis tooling is deliberately **not** deepened here. When the split happens:

- The new repo consumes the same `results/*.jsonl` + `*.manifest.json` + `corpus/*.json`
  artifacts (ideally from object storage), reimplementing `load.py`'s job as its own loader.
- Freeze a dirty results snapshot as the hand-off fixture so the new repo has stable input to
  parity-test against.
- The star-schema naming the new loader should adopt — e.g. the operational `retriever` field
  becoming a distinct `retriever_condition` dimension — is a requirement of *that* repo, kept
  out of here to avoid churning code that is about to move.
