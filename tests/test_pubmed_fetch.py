"""Tests for ingest/vector/pubmed_fetch.py — the NCBI E-utilities fetch step.

Hermetic: no network. The pure functions tested here (entity parsing, filename
mapping, efetch-XML parsing) are where bugs are *silent* — a mis-paired label or
a swallowed abstract still produces a plausible-looking cache file, which no
runtime error would surface. Network calls (esearch/efetch) are exercised by the
smoke run, not here.
"""
from __future__ import annotations

from ingest.vector import pubmed_fetch as pf


# --- parse_entities(): node line + following label line --------------------

def _write(tmp_path, body):
    p = tmp_path / "slice.ttl"
    p.write_text(body, encoding="utf-8")
    return p


def test_parse_entities_pairs_term_kind_label(tmp_path):
    ttl = (
        "@prefix hetio: <https://het.io/schema/> .\n"
        'ncbigene:5345 a hetio:Gene ;\n    rdfs:label "SERPINF2" .\n'
        'do:14227 a hetio:Disease ;\n    rdfs:label "lung cancer" .\n'
    )
    assert list(pf.parse_entities(_write(tmp_path, ttl))) == [
        ("ncbigene:5345", "Gene", "SERPINF2"),
        ("do:14227", "Disease", "lung cancer"),
    ]


def test_parse_entities_reads_label_followed_by_more_triples(tmp_path):
    # Regression: Gene/Compound nodes carry trailing hetio:chromosome / description /
    # inchikey attributes (the node-attribute extension), so their rdfs:label line ends
    # with `;`, not `.`. The label terminator must accept either, or every gene and
    # compound — the bulk of the question entities — is silently dropped from the corpus.
    ttl = (
        'ncbigene:5345 a hetio:Gene ;\n'
        '    rdfs:label "SERPINF2" ;\n'
        '    hetio:chromosome "17" ;\n'
        '    hetio:description "serpin peptidase inhibitor" .\n'
        'db:DB00201 a hetio:Compound ;\n'
        '    rdfs:label "Caffeine" ;\n'
        '    hetio:inchikey "InChIKey=RYYVLZVUVIJVGH-UHFFFAOYSA-N" .\n'
        'do:14227 a hetio:Disease ;\n    rdfs:label "lung cancer" .\n'
    )
    assert list(pf.parse_entities(_write(tmp_path, ttl))) == [
        ("ncbigene:5345", "Gene", "SERPINF2"),
        ("db:DB00201", "Compound", "Caffeine"),
        ("do:14227", "Disease", "lung cancer"),
    ]


def test_parse_entities_ignores_edges_and_rdfstar(tmp_path):
    # Base edge triples and RDF-star annotation lines must not be mistaken for
    # node declarations — their predicate is hetio:<kind>, never `a`.
    ttl = (
        'ncbigene:5345 a hetio:Gene ;\n    rdfs:label "SERPINF2" .\n'
        "db:DB00201 hetio:treats do:14227 .\n"
        '<< db:DB00201 hetio:treats do:14227 >> hetio:direction "both" .\n'
    )
    assert list(pf.parse_entities(_write(tmp_path, ttl))) == [
        ("ncbigene:5345", "Gene", "SERPINF2"),
    ]


def test_parse_entities_unescapes_label(tmp_path):
    ttl = 'ncbigene:1 a hetio:Gene ;\n    rdfs:label "alpha \\"X\\" beta" .\n'
    [(_, _, label)] = list(pf.parse_entities(_write(tmp_path, ttl)))
    assert label == 'alpha "X" beta'


# --- entity_filename(): filesystem-safe ------------------------------------

def test_entity_filename_sanitizes_colon():
    assert pf.entity_filename("ncbigene:5345") == "ncbigene_5345.txt"
    assert pf.entity_filename("do:14227") == "do_14227.txt"


# --- parse_abstracts_xml(): efetch PubmedArticleSet ------------------------

_XML = b"""<?xml version="1.0"?>
<PubmedArticleSet>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>111</PMID>
      <Article>
        <ArticleTitle>Role of <i>SERPINF2</i> in clotting</ArticleTitle>
        <Abstract>
          <AbstractText Label="BACKGROUND">Plasmin inhibition matters.</AbstractText>
          <AbstractText Label="RESULTS">SERPINF2 binds plasmin.</AbstractText>
        </Abstract>
      </Article>
    </MedlineCitation>
  </PubmedArticle>
  <PubmedArticle>
    <MedlineCitation>
      <PMID>222</PMID>
      <Article><ArticleTitle>A letter with no abstract</ArticleTitle></Article>
    </MedlineCitation>
  </PubmedArticle>
</PubmedArticleSet>"""


def test_parse_abstracts_concatenates_segments_and_keeps_nested_text():
    recs = pf.parse_abstracts_xml(_XML)
    assert len(recs) == 1  # the abstract-less letter is dropped
    rec = recs[0]
    assert rec["pmid"] == "111"
    assert rec["title"] == "Role of SERPINF2 in clotting"  # nested <i> flattened
    assert rec["abstract"] == "Plasmin inhibition matters. SERPINF2 binds plasmin."


def test_parse_abstracts_empty_set():
    assert pf.parse_abstracts_xml(b"<PubmedArticleSet></PubmedArticleSet>") == []


# --- render_entity_file(): the cache format build_vectors reads back -------

def test_render_entity_file_roundtrips_through_parse():
    # Cross-module contract: what pubmed_fetch writes, build_vectors must read.
    from ingest.vector import build_vectors as bv

    records = [
        {"pmid": "111", "title": "T1", "abstract": "first abstract text"},
        {"pmid": "222", "title": "T2", "abstract": "second abstract text"},
    ]
    text = pf.render_entity_file("ncbigene:5345", "Gene", "SERPINF2", records)
    meta, parsed = bv.parse_entity_file(text)
    assert meta == {"term": "ncbigene:5345", "label": "SERPINF2", "kind": "Gene"}
    assert parsed == records
