#!/usr/bin/env python3
"""Fetch PubMed abstracts for Hetionet entities via NCBI E-utilities.

Reads the entity set from the RDF Turtle file (not a live GraphDB), so the
vector side depends only on `make ingest-rdf` having produced the .ttl. For each
entity it runs an esearch by label, takes the top abstracts, and caches them one
file per entity under --out. Re-running skips entities already cached: PubMed is
rate-limited, so the cache is the expensive artifact and the embedding step
downstream is cheap to repeat.

NCBI allows 3 requests/sec anonymously, 10/sec with a free API key (NCBI_API_KEY,
read from the environment or a .env file). We pace requests to stay under the cap.

Why abstracts, not full text: abstracts are licensing-friendly, fetchable through
one API, and the right chunk granularity for the vector control. See the README
"Hetionet plus PubMed" section.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from pathlib import Path

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"

# Entity kinds whose rdfs:label is a usable PubMed query term. GO terms, pathways,
# and anatomy labels are ontology phrases that search poorly, so the literature
# corpus is seeded from genes, diseases, compounds, and clinical terms. These are
# the space-stripped hetio: class local names as written in the Turtle file.
LITERATURE_KINDS = {"Gene", "Disease", "Compound", "Symptom", "SideEffect", "PharmacologicClass"}

# The serializer writes each node as two lines: `<term> a hetio:<Kind> ;` then
# `    rdfs:label "<label>" .`. We pair a node line with the label line that follows.
_NODE_RE = re.compile(r"^(\S+)\s+a\s+hetio:(\w+)\s*;")
# The label may terminate the node block (`… "Label" .`) or be followed by more triples
# (`… "Label" ;`) — Gene/Compound nodes carry trailing hetio:chromosome / description /
# inchikey attributes after the label (the session-09 node-attribute extension), so the
# terminator is `;` there, `.` for kinds with no extra attributes. Accept either, or every
# Gene and Compound — the bulk of the question entities — is silently dropped from the corpus.
_LABEL_RE = re.compile(r'^\s*rdfs:label\s+"(.*)"\s*[;.]\s*$')


def _unescape(s: str) -> str:
    """Reverse the Turtle string escaping applied by hetionet_to_rdf._esc."""
    return (
        s.replace('\\"', '"')
        .replace("\\n", "\n")
        .replace("\\r", "\r")
        .replace("\\t", "\t")
        .replace("\\\\", "\\")
    )


def parse_entities(ttl_path: Path):
    """Yield (term, kind, label) for each node declaration in the Turtle file.

    Streams line by line — the full hetionet.ttl is ~470 MB, so we never read it
    whole. Edge triples and RDF-star annotation lines don't match _NODE_RE (their
    predicate is `hetio:<kind>`, never `a`), so only node declarations are emitted.
    Kind filtering is the caller's job; this yields every node faithfully."""
    with ttl_path.open(encoding="utf-8") as f:
        pending: tuple[str, str] | None = None
        for line in f:
            m = _NODE_RE.match(line)
            if m:
                pending = (m.group(1), m.group(2))
                continue
            if pending is not None:
                lm = _LABEL_RE.match(line)
                if lm:
                    term, kind = pending
                    yield term, kind, _unescape(lm.group(1))
                pending = None


def entity_filename(term: str) -> str:
    """'ncbigene:5345' -> 'ncbigene_5345.txt'; safe across filesystems."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", term) + ".txt"


def _text(elem) -> str:
    """Flatten an XML element's text, including nested tags (<i>, <sup>, ...)."""
    return " ".join(t.strip() for t in elem.itertext() if t.strip())


def parse_abstracts_xml(xml_bytes: bytes) -> list[dict]:
    """Parse an efetch PubmedArticleSet into [{pmid, title, abstract}].

    Articles with no <Abstract> (letters, some reviews) are skipped — an empty
    string would embed as meaningless noise. Multi-segment structured abstracts
    (BACKGROUND/METHODS/...) are concatenated in document order."""
    root = ET.fromstring(xml_bytes)
    out: list[dict] = []
    for art in root.iter("PubmedArticle"):
        pmid_el = art.find(".//MedlineCitation/PMID")
        title_el = art.find(".//Article/ArticleTitle")
        abstract = " ".join(s for s in (_text(a) for a in art.findall(".//Abstract/AbstractText")) if s)
        if not abstract or pmid_el is None:
            continue
        out.append({
            "pmid": pmid_el.text or "",
            "title": _text(title_el) if title_el is not None else "",
            "abstract": abstract,
        })
    return out


def render_entity_file(term: str, kind: str, label: str, records: list[dict]) -> str:
    """Serialize one entity's abstracts to the cached .txt format that
    build_vectors.parse_entity_file reads back. Line-oriented: each abstract is a
    single line (efetch text is whitespace-joined), so the format stays trivial."""
    lines = [f"# entity: {term}\t{label}\t({kind})"]
    for rec in records:
        lines += ["", f"# pmid: {rec['pmid']}", f"# title: {rec['title']}", rec["abstract"]]
    return "\n".join(lines) + "\n"


def esearch(client, term: str, retmax: int, api_key: str | None) -> list[str]:
    params = {"db": "pubmed", "term": term, "retmax": retmax, "retmode": "json"}
    if api_key:
        params["api_key"] = api_key
    r = client.get(f"{EUTILS}/esearch.fcgi", params=params, timeout=30.0)
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])


def efetch(client, pmids: list[str], api_key: str | None) -> bytes:
    params = {"db": "pubmed", "id": ",".join(pmids), "rettype": "abstract", "retmode": "xml"}
    if api_key:
        params["api_key"] = api_key
    r = client.get(f"{EUTILS}/efetch.fcgi", params=params, timeout=30.0)
    r.raise_for_status()
    return r.content


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--entities", type=Path, default=Path("ontology/hetionet-smoke.ttl"),
                    help="Turtle file to read entities from. Default: the smoke slice.")
    ap.add_argument("--out", type=Path, required=True, help="Directory for cached abstract files.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Fetch for at most N literature-kind entities (smoke slice). Omit for all.")
    ap.add_argument("--per-entity", type=int, default=3, help="Top abstracts to fetch per entity (default 3).")
    ap.add_argument("--kinds", default=None,
                    help="Comma-separated hetio class names to include. Default: literature-friendly kinds.")
    args = ap.parse_args()

    if not args.entities.exists():
        print(f"error: entities file not found: {args.entities}", file=sys.stderr)
        return 1

    # Deferred: keep the module importable for the hermetic test suite, which
    # runs under the `ingest` extra and has neither httpx nor python-dotenv.
    import httpx
    try:
        from dotenv import find_dotenv, load_dotenv
        # A bare load_dotenv() looks for a file named ".env" in the cwd and never
        # finds secrets/.env. find_dotenv walks up the tree for the given relative
        # path, so this resolves the same secrets/.env regardless of cwd.
        load_dotenv(find_dotenv("secrets/.env", usecwd=True))
    except ModuleNotFoundError:
        pass

    api_key = os.environ.get("NCBI_API_KEY")
    delay = 0.11 if api_key else 0.34  # stay under 10/s (keyed) or 3/s (anonymous)
    kinds = set(args.kinds.split(",")) if args.kinds else LITERATURE_KINDS
    args.out.mkdir(parents=True, exist_ok=True)

    considered = fetched = skipped = 0
    with httpx.Client(headers={"User-Agent": "biomedical-rag-bench/0.1"}) as client:
        for term, kind, label in parse_entities(args.entities):
            if kind not in kinds:
                continue
            if args.limit is not None and considered >= args.limit:
                break
            considered += 1
            dest = args.out / entity_filename(term)
            if dest.exists():
                skipped += 1
                continue
            try:
                pmids = esearch(client, label, args.per_entity, api_key)
                time.sleep(delay)
                if not pmids:
                    print(f"  no PubMed hits: {term} ({label})", file=sys.stderr)
                    continue
                records = parse_abstracts_xml(efetch(client, pmids, api_key))
                time.sleep(delay)
            except httpx.HTTPError as e:
                print(f"  fetch failed: {term} ({label}): {e}", file=sys.stderr)
                continue
            if not records:
                print(f"  no abstracts: {term} ({label})", file=sys.stderr)
                continue
            dest.write_text(render_entity_file(term, kind, label, records), encoding="utf-8")
            fetched += 1
            print(f"  {term} ({label}) -> {len(records)} abstract(s)", file=sys.stderr)

    print(f"done: {fetched} fetched, {skipped} cached, {considered} considered -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
