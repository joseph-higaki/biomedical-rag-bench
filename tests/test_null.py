"""Tests for retrievers/null.py — the closed-book baseline (build step 4).

Pins the closed_book telemetry contract: it bypasses base.build_result, so the two
stamps it would otherwise inherit are resolved by hand and asymmetrically — `mechanism`
present (universal discriminator), `context_tokenizer` absent (vacuous on zero tokens).
Hermetic: pure constant, no LLM/GraphDB/deps.
"""
from __future__ import annotations

from retrievers.base import Retriever
from retrievers.null import NullRetriever


def test_satisfies_retriever_protocol():
    assert isinstance(NullRetriever(), Retriever)


def test_empty_context_baseline():
    res = NullRetriever().retrieve("any query")
    assert res.context == "" and res.context_tokens == 0
    assert res.sources == [] and res.latency_ms == 0.0


def test_traversal_info_is_asymmetric():
    """mechanism stamped (B3, universal discriminator); context_tokenizer deliberately not."""
    info = NullRetriever().retrieve("any query").traversal_info
    assert info["mechanism"] == "none"  # B3: present on all four retrievers now
    assert info["retriever"] == "none"  # legacy key kept vestigial (additive contract)
    assert "context_tokenizer" not in info  # vacuous on empty context — omitted on purpose
