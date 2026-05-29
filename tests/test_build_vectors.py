"""Tests for ingest/vector/build_vectors.py — abstract files -> Chroma-ready chunks.

Hermetic: no torch, no chromadb. build_vectors defers those heavy imports into
main(), so the chunking and parsing logic imports and tests cleanly under the
`ingest` extra. These functions decide what text gets embedded and how a hit
traces back to its source — silent-bug territory, so they are unit-tested.
"""
from __future__ import annotations

from ingest.vector import build_vectors as bv


# --- chunk_text(): the window splitter -------------------------------------

def test_chunk_text_short_abstract_is_one_chunk():
    assert bv.chunk_text("a few short words") == ["a few short words"]


def test_chunk_text_empty_is_no_chunks():
    assert bv.chunk_text("") == []
    assert bv.chunk_text("   ") == []


def test_chunk_text_long_text_splits_with_overlap():
    words = [f"w{i}" for i in range(400)]
    chunks = bv.chunk_text(" ".join(words), size=180, overlap=30)
    assert len(chunks) > 1
    # Every chunk respects the window size.
    assert all(len(c.split()) <= 180 for c in chunks)
    # Overlap: the second chunk starts 150 words (size - overlap) in, so it
    # repeats the tail of the first — context isn't severed at the boundary.
    first, second = chunks[0].split(), chunks[1].split()
    assert second[0] == "w150"
    assert first[-30:] == second[:30]


# --- parse_entity_file(): inverse of render_entity_file --------------------

def test_parse_entity_file_reads_header_and_records():
    text = (
        "# entity: ncbigene:5345\tSERPINF2\t(Gene)\n"
        "\n# pmid: 111\n# title: T1\nfirst abstract\n"
        "\n# pmid: 222\n# title: T2\nsecond abstract\n"
    )
    meta, records = bv.parse_entity_file(text)
    assert meta == {"term": "ncbigene:5345", "label": "SERPINF2", "kind": "Gene"}
    assert records == [
        {"pmid": "111", "title": "T1", "abstract": "first abstract"},
        {"pmid": "222", "title": "T2", "abstract": "second abstract"},
    ]


def test_parse_entity_file_tolerates_missing_header():
    text = "# pmid: 999\n# title: T\nbody text\n"
    meta, records = bv.parse_entity_file(text)
    assert meta == {"term": "", "label": "", "kind": ""}
    assert records == [{"pmid": "999", "title": "T", "abstract": "body text"}]


# --- load_chunks(): directory -> (ids, documents, metadatas) ---------------

def test_load_chunks_builds_traceable_ids_and_metadata(tmp_path):
    (tmp_path / "ncbigene_5345.txt").write_text(
        "# entity: ncbigene:5345\tSERPINF2\t(Gene)\n"
        "\n# pmid: 111\n# title: T1\nplasmin inhibition study\n",
        encoding="utf-8",
    )
    ids, docs, metas = bv.load_chunks(tmp_path)
    assert ids == ["ncbigene:5345:111:0"]  # <term>:<pmid>:<chunk_index>
    assert docs == ["plasmin inhibition study"]
    assert metas == [{
        "entity": "ncbigene:5345",
        "label": "SERPINF2",
        "kind": "Gene",
        "pmid": "111",
        "title": "T1",
    }]


def test_load_chunks_empty_dir(tmp_path):
    assert bv.load_chunks(tmp_path) == ([], [], [])
