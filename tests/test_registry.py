"""Tests for the retriever REGISTRY — the no-drift invariant (build step 5).

The registry maps a condition name to a zero-arg constructor. The headline guarantee is
that the *key* equals the constructed retriever's reported `name`: the manifest and every
result row record `retriever.name`, and the analysis layer groups by it, so a key that
disagreed with the reported name would silently mislabel a whole run. When the key came
free from a class attribute that was self-evident; now that the graph condition embeds its
hop budget in a per-instance name, this test is what keeps the two from drifting.

Hermetic: constructing a retriever only sets attributes — the heavy deps (httpx, chromadb,
sentence-transformers) load lazily inside `retrieve`, never at construction — so this runs
with no optional extra installed and touches no network.
"""
from __future__ import annotations

from eval.run_eval import REGISTRY
from retrievers.base import Retriever


def test_registry_key_matches_reported_name():
    for key, ctor in REGISTRY.items():
        r = ctor()
        assert isinstance(r, Retriever)  # runtime_checkable protocol
        assert r.name == key, f"registry key {key!r} != reported name {r.name!r}"


def test_graph_hop_variants_registered_with_their_budgets():
    # Both hop budgets are present as distinct named conditions, and the name embeds the
    # exact budget the instance carries (which is also logged in traversal_info).
    assert "graph_neighborhood_1hop" in REGISTRY
    assert "graph_neighborhood_2hop" in REGISTRY
    assert REGISTRY["graph_neighborhood_1hop"]().hops == 1
    assert REGISTRY["graph_neighborhood_2hop"]().hops == 2
