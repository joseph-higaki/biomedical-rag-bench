"""Tests for ingest/hetionet_to_rdf.py — the JSON -> RDF-star Turtle transform.

Hermetic: the integration tests build their own tiny Hetionet-shaped JSON, so
the suite runs without the 16 MB download (and in CI). The unit tests target the
serialization helpers, where bugs are *silent* — a wrong bool/int branch or URI
mapping still produces valid Turtle, just with wrong data, which no syntax check
would catch.
"""
from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from ingest import hetionet_to_rdf as h2r


# --- literal(): the bool-before-int guard and string escaping --------------

def test_literal_bool_is_not_integer():
    # bool subclasses int in Python; if the int branch ran first, True would
    # serialize as "1" and silently corrupt every boolean edge annotation.
    assert h2r.literal(True) == "true"
    assert h2r.literal(False) == "false"


def test_literal_numbers():
    assert h2r.literal(5345) == "5345"
    assert h2r.literal(2.5) == '"2.5"^^xsd:double'
    assert h2r.literal(Decimal("2.5")) == '"2.5"^^xsd:double'


def test_literal_string_escaping():
    assert h2r.literal("plain") == '"plain"'
    assert h2r.literal('a"b') == '"a\\"b"'        # embedded quote
    assert h2r.literal("a\\b") == '"a\\\\b"'      # embedded backslash
    assert h2r.literal("l1\nl2") == '"l1\\nl2"'   # newline -> \n


# --- node_term(): per-kind URI mapping -------------------------------------

@pytest.mark.parametrize("kind, ident, expected", [
    ("Disease", "DOID:14227", "do:14227"),               # strip DOID:
    ("Anatomy", "UBERON:0001533", "uberon:0001533"),     # strip UBERON:
    ("Biological Process", "GO:0032474", "go:0032474"),  # strip GO:
    ("Compound", "DB00201", "db:DB00201"),               # keep full id
    ("Gene", 5345, "ncbigene:5345"),                     # int identifier
    ("Side Effect", "C0023448", "umls:C0023448"),
    ("Symptom", "D020150", "mesh:D020150"),
    ("Pharmacologic Class", "N0000007632", "ndfrt:N0000007632"),
    ("Pathway", "PC7_3805", "pathway:PC7_3805"),
])
def test_node_term_mapping(kind, ident, expected):
    assert h2r.node_term(kind, ident) == expected


def test_node_term_invalid_local_falls_back_to_full_iri():
    # A local part that is not a safe PN_LOCAL must become a full <IRI>.
    assert h2r.node_term("Compound", "DB(0)") == "<https://identifiers.org/drugbank/DB(0)>"


def test_class_name_strips_spaces():
    assert h2r._class_name("Biological Process") == "BiologicalProcess"
    assert h2r._class_name("Gene") == "Gene"


# --- edge_annotations(): scalar vs list expansion --------------------------

def test_edge_annotations_scalars_and_lists():
    pairs = list(h2r.edge_annotations({
        "source": "Bgee",
        "unbiased": True,
        "sources": ["A", "B"],
        "pubmed_ids": [1, 2],
    }))
    assert pairs == [
        ("source", '"Bgee"'),
        ("unbiased", "true"),
        ("sources", '"A"'),
        ("sources", '"B"'),
        ("pubmed_ids", "1"),
        ("pubmed_ids", "2"),
    ]


# --- integration: write_turtle() -> load -> SPARQL --------------------------

MINI = {
    "nodes": [
        {"kind": "Compound", "identifier": "DB00201",
         "name": 'Caffeine "stimulant"', "data": {}},   # embedded quotes
        {"kind": "Disease", "identifier": "DOID:1612",
         "name": "breast cancer", "data": {}},
        {"kind": "Gene", "identifier": 5345, "name": "SERPINF2", "data": {}},
    ],
    "edges": [
        {"source_id": ["Compound", "DB00201"], "target_id": ["Disease", "DOID:1612"],
         "kind": "treats", "direction": "both",
         "data": {"source": "DrugCentral", "license": "CC BY 4.0",
                  "unbiased": False, "sources": ["X", "Y"]}},
        {"source_id": ["Compound", "DB00201"], "target_id": ["Gene", 5345],
         "kind": "binds", "direction": "both", "data": {"unbiased": True}},
    ],
}

PREFIXES = """
PREFIX db: <https://identifiers.org/drugbank/>
PREFIX do: <http://purl.obolibrary.org/obo/DOID_>
PREFIX ncbigene: <https://identifiers.org/ncbigene/>
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def _write_mini(tmp_path: Path, limit=None) -> tuple[str, int, int]:
    src = tmp_path / "mini.json"
    src.write_text(json.dumps(MINI), encoding="utf-8")
    out = tmp_path / "mini.ttl"
    nodes, edges = h2r.write_turtle(out, src, limit)
    return out.read_text(encoding="utf-8"), nodes, edges


@pytest.fixture
def mini_turtle(tmp_path: Path) -> str:
    turtle, nodes, edges = _write_mini(tmp_path)
    assert (nodes, edges) == (3, 2)
    return turtle


def test_base_triple_present(mini_turtle, load_turtle):
    store = load_turtle(mini_turtle)
    assert store.query(PREFIXES + "ASK { db:DB00201 hetio:treats do:1612 }")


def test_label_with_quotes_roundtrips(mini_turtle, load_turtle):
    # Proves the hand-written escaping survives a real RDF parser.
    store = load_turtle(mini_turtle)
    rows = list(store.query(PREFIXES + "SELECT ?l WHERE { db:DB00201 rdfs:label ?l }"))
    assert rows[0]["l"].value == 'Caffeine "stimulant"'


def test_rdfstar_annotation_queryable(mini_turtle, load_turtle):
    store = load_turtle(mini_turtle)
    q = PREFIXES + "SELECT ?src WHERE { << db:DB00201 hetio:treats do:1612 >> hetio:source ?src }"
    assert [r["src"].value for r in store.query(q)] == ["DrugCentral"]


def test_list_valued_annotation_expands(mini_turtle, load_turtle):
    store = load_turtle(mini_turtle)
    q = PREFIXES + "SELECT ?x WHERE { << db:DB00201 hetio:treats do:1612 >> hetio:sources ?x }"
    assert sorted(r["x"].value for r in store.query(q)) == ["X", "Y"]


def test_limit_keeps_only_touched_nodes(tmp_path: Path, load_turtle):
    # --limit 1 keeps only the first edge ('treats') and the two nodes it joins;
    # the Gene (only in the dropped 'binds' edge) must not appear.
    turtle, nodes, edges = _write_mini(tmp_path, limit=1)
    assert (nodes, edges) == (2, 1)
    store = load_turtle(turtle)
    assert store.query(PREFIXES + "ASK { db:DB00201 hetio:treats do:1612 }")
    assert not store.query(PREFIXES + "ASK { ncbigene:5345 rdfs:label ?l }")
    assert not store.query(PREFIXES + "ASK { db:DB00201 hetio:binds ncbigene:5345 }")
