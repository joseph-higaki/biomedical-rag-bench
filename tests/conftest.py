"""Shared pytest fixtures for biomedical-rag-bench.

Scaffold for the whole suite. As retriever and eval tests arrive, add their
shared setup here (a stub Retriever returning a canned RetrievalResult, a small
fixture question set, etc.) rather than duplicating it across test modules.
"""
from __future__ import annotations

import io
from pathlib import Path

import pyoxigraph as ox
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def load_turtle():
    """Load Turtle(-star) text into an in-memory Oxigraph store.

    Oxigraph is the offline stand-in for GraphDB: it parses RDF-star and runs
    SPARQL-star, so graph-side tests assert on real query results without a
    running triplestore. Returns the loaded store."""
    def _load(turtle_text: str) -> ox.Store:
        store = ox.Store()
        store.load(input=io.BytesIO(turtle_text.encode("utf-8")), format=ox.RdfFormat.TURTLE)
        return store

    return _load
