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
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
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


class RateLimiter:
    """Global token bucket spacing request *starts* to stay under NCBI's per-second cap.

    The cap is on the whole client, not per thread, so concurrency alone would burst past
    it. Each `acquire()` claims the next time-slot — slots are handed out `interval` apart and
    monotonically — then sleeps until its slot *outside* the lock, so N worker threads don't
    serialize on the lock while waiting. Result: at most `rate` request-starts per second
    across all workers, which is exactly NCBI's constraint, while in-flight latency overlaps.
    This is the whole point of the parallel fetcher: the serial loop was latency-bound (one
    request in flight at a time), not rate-bound — concurrency fills the pipe up to the cap.
    """

    def __init__(self, rate_per_sec: float) -> None:
        self._interval = 1.0 / rate_per_sec
        self._lock = threading.Lock()
        self._next_slot = time.monotonic()

    def acquire(self) -> None:
        with self._lock:
            slot = max(time.monotonic(), self._next_slot)
            self._next_slot = slot + self._interval
        delay = slot - time.monotonic()
        if delay > 0:
            time.sleep(delay)


def fetch_one(client, limiter, term, kind, label, out, per_entity, api_key, retries=2):
    """Fetch + cache one entity's abstracts. Returns a (status, term[, detail]) tuple.

    Resume-safe: an already-cached file is a no-op (`skipped`). Each network call is
    rate-limited and retried with backoff, so a transient blip over a 29k-entity run doesn't
    silently drop an entity — and any entity that still fails is simply re-attempted on the
    next run (the cache makes the whole job idempotent). Mirrors the serial version's
    per-entity outcomes so the tally is unchanged."""
    import httpx

    dest = out / entity_filename(term)
    if dest.exists():
        return ("skipped", term)
    for attempt in range(retries + 1):
        try:
            limiter.acquire()
            pmids = esearch(client, label, per_entity, api_key)
            if not pmids:
                return ("no_hits", term)
            limiter.acquire()
            records = parse_abstracts_xml(efetch(client, pmids, api_key))
            break
        except (httpx.HTTPError, ET.ParseError) as e:
            if attempt == retries:
                return ("error", term, str(e))
            time.sleep(0.5 * (attempt + 1))  # linear backoff; NCBI 429s clear quickly
    if not records:
        return ("no_abstracts", term)
    dest.write_text(render_entity_file(term, kind, label, records), encoding="utf-8")
    return ("fetched", term)


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
    ap.add_argument("--workers", type=int, default=8,
                    help="Concurrent fetch threads (default 8). The global rate cap, not this, "
                    "bounds throughput; this just keeps enough requests in flight to reach it.")
    ap.add_argument("--rate", type=float, default=None,
                    help="Max request starts/sec across all workers. Default: 9 with an NCBI "
                    "API key, 2.7 without (just under NCBI's 10/s and 3/s caps).")
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
    rate = args.rate if args.rate else (9.0 if api_key else 2.7)  # under 10/s keyed, 3/s anon
    kinds = set(args.kinds.split(",")) if args.kinds else LITERATURE_KINDS
    args.out.mkdir(parents=True, exist_ok=True)

    # Materialize the target entity list (streams the ~470 MB ttl once; ~29k small tuples).
    targets = [(t, k, lbl) for t, k, lbl in parse_entities(args.entities) if k in kinds]
    if args.limit is not None:
        targets = targets[: args.limit]
    limiter = RateLimiter(rate)
    counts: dict[str, int] = {}
    t0 = time.monotonic()
    print(f"fetching {len(targets)} entities @ ≤{rate}/s, {args.workers} workers "
          f"({'keyed' if api_key else 'anonymous'})", file=sys.stderr)

    # httpx.Client is thread-safe; one shared client pools connections across workers.
    with httpx.Client(headers={"User-Agent": "biomedical-rag-bench/0.1"}) as client:
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [
                pool.submit(fetch_one, client, limiter, t, k, lbl, args.out, args.per_entity, api_key)
                for t, k, lbl in targets
            ]
            for i, fut in enumerate(as_completed(futures), 1):
                status, term, *detail = fut.result()
                counts[status] = counts.get(status, 0) + 1
                if status in ("error", "no_hits", "no_abstracts"):
                    print(f"  {status}: {term} {detail[0] if detail else ''}", file=sys.stderr)
                if i % 250 == 0 or i == len(futures):  # heartbeat for a multi-hour run
                    el = time.monotonic() - t0
                    print(f"  …{i}/{len(futures)}  ({i/el:.1f} entity/s, {el/60:.1f} min)  "
                          f"{counts}", file=sys.stderr)

    summary = ", ".join(f"{n} {s}" for s, n in sorted(counts.items()))
    print(f"done: {summary} -> {args.out}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
