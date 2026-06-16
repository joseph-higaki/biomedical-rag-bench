#!/usr/bin/env python3
"""analysis/load.py — the analysis layer's data loader (build step 5 → 8).

The harness writes one JSONL row per question×run plus a per-run manifest (gitignored,
machine-readable). This module turns that pile of run files into ONE tidy pandas DataFrame —
the single seam both the exploratory notebook and the eventual polished notebook/dashboard
import, so the load + dedup + reshape logic lives in exactly one place (and is unit-tested),
not copy-pasted across notebooks.

Three jobs, each a real correctness hazard if done ad hoc in a notebook cell:

  1. **Discover + join.** Pair every `<run_id>.jsonl` with its `<run_id>.manifest.json` and
     stamp each row with run-constant factors (retriever, generator_model, judge, timestamp).

  2. **Dedup to canonical rows.** `eval/results/` accumulates superseded runs — n=1 smokes, a
     `2hop` run that died at 3/52 mid-batch, re-runs on a rebuilt corpus. Naively concatenating
     double-counts them. We dedup at the **(retriever, generator_model_family, writer_model_family,
     question_id)** grain,
     keeping the latest run's row: that simultaneously supersedes truncated/smoke runs AND
     preserves the *union* of question coverage (e.g. closed_book's deterministic-52 run and its
     separate type-10 run merge into one closed_book condition, no question lost).

  3. **Reshape to columns.** Explode the nested `judge_details` (recall/precision/f1/extra) and
     `traversal_info` (writer-LLM cost, sparql_valid, hops, top_k, num_linked) into flat columns,
     derive `hops` from the retriever name, and compute **retrieval context-input tokens**
     (`input_tokens − closed_book input_tokens` for the same question+model — the one unit-safe
     token decomposition the contract sanctions, see retrievers/base.py).

Telemetry columns are NaN for rows produced before the harness persisted `traversal_info`
(commit 8b4c434) — that is expected and is exactly why the canonical conditions get re-run on
the new schema. `python -m analysis.load` prints a data-contract audit (canonical runs +
column coverage) — the exploratory pass's first deliverable.

Needs the `eval` extra (pandas): `uv run --extra eval python -m analysis.load`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESULTS = REPO_ROOT / "eval" / "results"
DEFAULT_CORPUS = REPO_ROOT / "ingest" / "corpus"  # committed corpus-build profiles (ingest/corpus/README.md)

# judge_details / traversal_info keys lifted into top-level columns. Read with .get, so a key
# absent from a given row (old schema, or a different retriever/scoring) lands as NaN rather
# than raising — additive-only telemetry means we never assume a key is present.
_JUDGE_COLS = ["recall", "precision", "f1", "expected_count", "found_count",
               "judge_input_tokens", "judge_output_tokens", "judge_model", "judge_temperature"]
_TRAVERSAL_COLS = ["mechanism", "writer_model", "writer_input_tokens", "writer_output_tokens",
                   "sparql_valid", "num_rows", "num_linked", "num_triples", "top_k", "hops",
                   "writer_temperature"]
_HOPS_RE = re.compile(r"_(\d+)hop")
# Top-level row fields that only newer runs carry (additive harness changes). pandas creates a
# column only if some row has the key, so on an all-old corpus these would be *absent* — not
# just NaN — and break consumers that select them. The loader guarantees them as NaN columns so
# its output schema is stable; whether they're populated is the telemetry-coverage question.
_GUARANTEED_COLS = ["generator_model_resolved", "cache_read_input_tokens",
                    "cache_creation_input_tokens", "error", "generator_temperature"]
# Manifests carry the generator id inconsistently — some runs logged the alias
# (`claude-haiku-4-5`), some the resolved snapshot it expands to (`claude-haiku-4-5-20251001`).
# Stripping the trailing -YYYYMMDD yields a `generator_model_family` that treats them as one
# condition for grouping/dedup, while the exact `generator_model` is kept for provenance.
# (Root cause is a harness inconsistency — the row should persist the resolved id per
# retrievers/base.py's contract; this normalization unblocks analysis until re-runs land.)
_MODEL_DATE_RE = re.compile(r"-\d{8}$")


def discover_runs(results_dir: Path = DEFAULT_RESULTS) -> list[dict]:
    """Pair each rows file with its manifest. Returns run-metadata dicts (no rows yet)."""
    runs = []
    for jsonl in sorted(results_dir.glob("*.jsonl")):
        manifest_path = jsonl.with_suffix(".manifest.json")
        if not manifest_path.exists():
            continue  # an orphan rows file with no provenance — skip rather than guess factors
        runs.append({"rows_path": jsonl, **json.loads(manifest_path.read_text())})
    return runs


def load_raw(results_dir: Path = DEFAULT_RESULTS) -> pd.DataFrame:
    """All rows from all runs, each stamped with its run's manifest factors.

    `run_ts` is parsed to a real datetime so the canonical dedup can order runs; the row's own
    `retriever`/`generator_model` already match the manifest, but we take them from the manifest
    as the authoritative run-level factor.
    """
    frames = []
    for run in discover_runs(results_dir):
        rows = [json.loads(ln) for ln in run["rows_path"].read_text().splitlines() if ln.strip()]
        if not rows:
            continue
        df = pd.DataFrame(rows)
        df["run_id"] = run["run_id"]
        df["run_ts"] = pd.to_datetime(run["timestamp"])
        # Run-level factors come from the manifest (authoritative), not the rows — so the
        # columns exist even if a row's schema drifts, and a run is always attributable.
        df["retriever"] = run["retriever"]
        df["generator_provider"] = run.get("generator_provider")
        df["generator_model"] = run["generator_model"]
        df["judge"] = run.get("judge")
        df["harness_version"] = run.get("harness_version")
        # The corpus factor: a reference to a committed profile (ingest/corpus/<id>.json). None on
        # legacy runs made before provenance — joined to scale metrics in load() below.
        df["corpus_build_id"] = run.get("corpus_build_id")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    out = pd.concat(frames, ignore_index=True)
    out["generator_model_family"] = out["generator_model"].str.replace(_MODEL_DATE_RE, "", regex=True)
    # The SPARQL writer is a second model inside graph_sparqlgen, logged under traversal_info.
    # Lift it (+ a date-normalized family) HERE, before canonical(), so the dedup key can treat
    # two writers as distinct conditions. Mirrors generator_model_family exactly: same date strip,
    # so a writer's alias/resolved forms collapse to one id; raw writer_model is kept for provenance.
    # NaN for retrievers with no writer (closed_book/vector/graph_neighborhood) — a stable single
    # value, so it never splits those conditions in the key.
    ti = out["traversal_info"] if "traversal_info" in out.columns else pd.Series([{}] * len(out))
    out["writer_model"] = ti.apply(lambda d: d.get("writer_model") if isinstance(d, dict) else None)
    out["writer_model_family"] = out["writer_model"].str.replace(_MODEL_DATE_RE, "", regex=True)
    return out


def corpus_profiles(corpus_dir: Path = DEFAULT_CORPUS) -> pd.DataFrame:
    """One row per corpus_build_id from ingest/corpus/<id>.json: scale metrics, prefixed `corpus_`.

    These join onto results by corpus_build_id so the analysis can read "how big was the corpus"
    beside each verdict and diff smoke vs full. The `corpus_` prefix avoids collision with run/
    judge columns; the explicit `columns=` keeps the schema stable even with no profiles on disk.
    ACTIVE (a bare id, not JSON) isn't matched by the glob, so it's skipped."""
    recs = []
    for path in sorted(corpus_dir.glob("*.json")):
        prof = json.loads(path.read_text())
        g, v = prof.get("graph", {}), prof.get("vector", {})
        recs.append({
            "corpus_build_id": prof["corpus_build_id"],
            "corpus_scale": prof.get("scale"),
            "corpus_triples": g.get("triples"), "corpus_nodes": g.get("nodes"),
            "corpus_edges": g.get("edges"),
            "corpus_abstracts": v.get("n_abstracts"), "corpus_words": v.get("n_words"),
            "corpus_chunks": v.get("n_chunks"),
        })
    return pd.DataFrame(recs, columns=[
        "corpus_build_id", "corpus_scale", "corpus_triples", "corpus_nodes", "corpus_edges",
        "corpus_abstracts", "corpus_words", "corpus_chunks"])


def canonical(df: pd.DataFrame) -> pd.DataFrame:
    """One row per (retriever, generator_model_family, writer_model_family, question_id): latest by ts.

    `sort_values` then `drop_duplicates(keep="last")` is the pandas idiom for "newest wins":
    after sorting ascending by run timestamp, the last duplicate in each group is the most
    recent, so keeping it supersedes truncated and smoke runs while keeping every question that
    only some runs covered.

    The writer family is in the key because the graph_sparqlgen SPARQL writer is an experimental
    factor: two runs differing only in writer (same retriever, generator, question) are distinct
    conditions, not supersessions — without it, the newer writer silently overwrites the older and
    the writer comparison is lost. NaN writer (no-writer retrievers) is one value, so it collapses
    those rows exactly as before.
    """
    if df.empty:
        return df
    key = ["retriever", "generator_model_family", "writer_model_family", "question_id"]
    return (df.sort_values("run_ts")
              .drop_duplicates(subset=key, keep="last")
              .reset_index(drop=True))


def _explode(df: pd.DataFrame, col: str, keys: list[str]) -> pd.DataFrame:
    """Lift selected keys out of a dict-valued column into flat columns (NaN when absent)."""
    src = df[col] if col in df.columns else pd.Series([{}] * len(df))
    for k in keys:
        df[k] = src.apply(lambda d, k=k: d.get(k) if isinstance(d, dict) else None)
    return df


def _add_retrieval_context_input_tokens(df: pd.DataFrame) -> pd.DataFrame:
    """retrieval_context_input_tokens = input_tokens − closed_book input_tokens (same question+model).

    The input-side token weight the retrieved context contributes, isolated by subtracting the
    no-context baseline: same generator, same question, billed tokens only (a unit-safe delta — same
    direction, same tokenizer). closed_book's own value is ~0 by construction.
    """
    cb = (df[df["retriever"] == "closed_book"][["question_id", "generator_model_family", "input_tokens"]]
          .rename(columns={"input_tokens": "_cb_input_tokens"}))
    df = df.merge(cb, on=["question_id", "generator_model_family"], how="left")
    df["retrieval_context_input_tokens"] = df["input_tokens"] - df["_cb_input_tokens"]
    return df.drop(columns=["_cb_input_tokens"])


def tidy(df: pd.DataFrame) -> pd.DataFrame:
    """Reshape canonical rows for analysis: explode nested telemetry, derive hops, add context-input tokens."""
    if df.empty:
        return df
    df = _explode(df, "judge_details", _JUDGE_COLS)
    df = _explode(df, "traversal_info", _TRAVERSAL_COLS)
    # Verdict → numeric (True→1.0, False→0.0, None→NaN). Errored/unjudged rows carry passed=None,
    # which forces the column to object dtype (bool + None); object means/pivots stay object and
    # break anything needing real floats (e.g. imshow). Coerce once here so every chart gets numbers.
    df["passed"] = pd.to_numeric(df["passed"], errors="coerce")
    # hops: prefer the value the graph retriever logged; else parse the name (graph_*_<n>hop).
    name_hops = df["retriever"].str.extract(_HOPS_RE)[0].astype("Float64")
    df["hops"] = df["hops"].astype("Float64").fillna(name_hops)
    df["num_extra"] = df["judge_details"].apply(lambda d: len(d.get("extra", [])) if isinstance(d, dict) else 0)
    df = _add_retrieval_context_input_tokens(df)
    for c in _GUARANTEED_COLS:  # stable output schema even on a pre-backfill corpus
        if c not in df.columns:
            df[c] = pd.NA
    return df


def load(results_dir: Path = DEFAULT_RESULTS) -> pd.DataFrame:
    """The pipeline: discover → load → canonical → tidy, then left-join corpus profiles."""
    df = tidy(canonical(load_raw(results_dir)))
    if df.empty:
        return df
    return df.merge(corpus_profiles(), on="corpus_build_id", how="left")


def _audit(df: pd.DataFrame) -> str:
    """A human-readable data-contract report: canonical conditions + telemetry coverage."""
    if df.empty:
        return "no runs found (or no manifests) under the results dir."
    lines = ["Canonical conditions (retriever × generator × writer, newest run per question):", ""]
    grp = (df.groupby(["retriever", "generator_model_family", "writer_model_family"], dropna=False)
             .agg(n=("question_id", "nunique"),
                  judged=("judged", "sum"),
                  passed=("passed", "sum"),
                  run=("run_id", lambda s: sorted(s.unique())[-1]))
             .reset_index())
    for _, r in grp.iterrows():
        writer = r["writer_model_family"] if pd.notna(r["writer_model_family"]) else "-"
        lines.append(f"  {r['retriever']:<26} {r['generator_model_family']:<22} writer={writer:<22} "
                     f"n={int(r['n']):<3} judged={int(r['judged']):<3} passed={int(r['passed']):<3} "
                     f"({r['run']})")
    # Telemetry coverage: how many canonical rows carry the new (post-backfill) columns.
    lines += ["", "Telemetry coverage (non-null canonical rows / total):"]
    total = len(df)
    for c in ["writer_input_tokens", "sparql_valid", "top_k", "hops",
              "recall", "retrieval_context_input_tokens", "cache_read_input_tokens",
              "generator_temperature", "writer_temperature", "judge_temperature"]:
        nn = int(df[c].notna().sum()) if c in df.columns else 0
        lines.append(f"  {c:<28} {nn}/{total}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(_audit(load()))
