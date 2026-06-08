"""Tests for eval/analysis/load.py — the analysis-layer loader (build step 5 → 8).

Hermetic: fabricates a few run files (jsonl + manifest) in tmp_path, so the loader's three
correctness hazards are pinned without a real eval run — canonical dedup (newest run wins,
union of coverage preserved), generator-id family normalization (alias and resolved snapshot
treated as one condition), nested-telemetry explosion, and the closed_book token premium.

Skipped when pandas (the `eval` extra) isn't installed, so the default `--extra ingest`
suite stays green; run with `uv run --extra eval python -m pytest tests/test_analysis_load.py`.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("pandas")  # the eval extra; skip cleanly under the deterministic suite

from eval.analysis import load as L  # noqa: E402


def _write_run(results_dir, run_id, retriever, model, ts, rows):
    """Write one run's <run_id>.jsonl + .manifest.json with the given rows."""
    (results_dir / f"{run_id}.jsonl").write_text(
        "\n".join(json.dumps(r) for r in rows) + "\n"
    )
    (results_dir / f"{run_id}.manifest.json").write_text(json.dumps({
        "run_id": run_id, "timestamp": ts, "retriever": retriever,
        "generator_provider": "anthropic", "generator_model": model,
        "judge": "deterministic-v1", "harness_version": "harness-v1",
    }))


def _row(qid, retriever, **kw):
    base = {"question_id": qid, "type_id": "02_1hop_factoid", "scoring": "set_match",
            "retriever": retriever, "input_tokens": 100, "judged": True, "passed": True,
            "judge_details": {}, "traversal_info": {}}
    return {**base, **kw}


def test_canonical_keeps_newest_run_and_unions_coverage(tmp_path):
    # An older truncated run (q1 only) and a newer complete run (q1,q2). Canonical takes q1 from
    # the newer run (passed flips to show which won) and keeps q2 — nothing double-counted.
    _write_run(tmp_path, "r1", "vector", "m", "2026-06-01T00:00:00+0000",
               [_row("q1", "vector", passed=False)])
    _write_run(tmp_path, "r2", "vector", "m", "2026-06-02T00:00:00+0000",
               [_row("q1", "vector", passed=True), _row("q2", "vector", passed=True)])
    df = L.canonical(L.load_raw(tmp_path))
    assert len(df) == 2  # q1 once (not twice), plus q2
    assert df.loc[df.question_id == "q1", "passed"].item() is True  # newer run won
    assert df.loc[df.question_id == "q1", "run_id"].item() == "r2"


def test_generator_id_family_merges_alias_and_resolved_snapshot(tmp_path):
    # Same retriever, different question, one run logging the alias and one the resolved id.
    # They must collapse to one condition (family), not split into two.
    _write_run(tmp_path, "alias", "closed_book", "claude-haiku-4-5", "2026-06-01T00:00:00+0000",
               [_row("q1", "closed_book")])
    _write_run(tmp_path, "resolved", "closed_book", "claude-haiku-4-5-20251001",
               "2026-06-02T00:00:00+0000", [_row("q2", "closed_book")])
    df = L.load(tmp_path)
    fams = set(df["generator_model_family"].unique())
    assert fams == {"claude-haiku-4-5"}  # the snapshot date is stripped for grouping
    assert set(df["question_id"]) == {"q1", "q2"}  # both kept under the one family


def test_tidy_explodes_telemetry_and_derives_hops(tmp_path):
    rows = [_row("q1", "graph_sparqlgen",
                 judge_details={"recall": 0.5, "precision": 1.0, "f1": 0.67, "extra": ["x", "y"]},
                 traversal_info={"writer_input_tokens": 40, "sparql_valid": True})]
    _write_run(tmp_path, "s1", "graph_sparqlgen", "m", "2026-06-02T00:00:00+0000", rows)
    # a graph run whose hop budget is only in the name, not traversal_info
    _write_run(tmp_path, "g2", "graph_neighborhood_2hop", "m", "2026-06-02T00:00:00+0000",
               [_row("q1", "graph_neighborhood_2hop")])
    df = L.load(tmp_path).set_index("retriever")
    assert df.loc["graph_sparqlgen", "recall"] == 0.5
    assert df.loc["graph_sparqlgen", "writer_input_tokens"] == 40
    assert df.loc["graph_sparqlgen", "num_extra"] == 2
    assert df.loc["graph_neighborhood_2hop", "hops"] == 2  # parsed from the name


def test_guarantees_newer_schema_columns_on_an_old_corpus(tmp_path):
    # Rows from before the resolved-id / cache backfill carry none of those keys, so pandas
    # wouldn't create the columns. The loader must still expose them (as NaN) so consumers
    # (the notebook) can select them without a KeyError.
    _write_run(tmp_path, "old", "vector", "m", "2026-06-01T00:00:00+0000",
               [_row("q1", "vector")])  # _row has no resolved-id / cache / error keys
    df = L.load(tmp_path)
    for col in ["generator_model_resolved", "cache_read_input_tokens",
                "cache_creation_input_tokens", "error"]:
        assert col in df.columns and df[col].isna().all()


def test_token_premium_is_input_minus_closed_book(tmp_path):
    _write_run(tmp_path, "cb", "closed_book", "m", "2026-06-02T00:00:00+0000",
               [_row("q1", "closed_book", input_tokens=100)])
    _write_run(tmp_path, "vec", "vector", "m", "2026-06-02T00:00:00+0000",
               [_row("q1", "vector", input_tokens=150)])
    df = L.load(tmp_path).set_index("retriever")
    assert df.loc["vector", "retrieval_token_premium"] == 50
    assert df.loc["closed_book", "retrieval_token_premium"] == 0  # baseline vs itself
