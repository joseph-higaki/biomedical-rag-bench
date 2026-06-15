#!/usr/bin/env python3
"""ingest/vector/select_corpus_entities.py — pick the targeted vector-corpus entity set.

The full Hetionet literature set is ~29k entities, and PubMed fetch is latency-bound
(~0.7 entities/sec, two sequential E-utilities round-trips each), so a full corpus is an
~11-hour fetch. This selects a *targeted* subset that makes `vector` a fair arm for the
current eval at ~1 hour instead: every entity the question set seeds on, plus a seeded
random distractor pool so retrieval is non-trivial (the model must still find the right
abstract among many). Seeds are written first so a chunked/interrupted fetch secures the
eval-critical entities before the distractors.

This is the stopgap for the targeted corpus; the evolving-baseline design still wants the
full literature corpus eventually (parallelise the fetcher, then drop the distractor cap).

Output is a minimal Turtle file — one `<term> a hetio:<Kind> ; rdfs:label "…" .` block per
entity — which is all `pubmed_fetch.parse_entities` reads. Run from the repo root:

    uv run --extra ingest python ingest/vector/select_corpus_entities.py \
        --questions produce/questions.jsonl --entities data/rdf/hetionet.ttl \
        --out data/vector-corpus-entities.ttl --distractors 1500
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pubmed_fetch import LITERATURE_KINDS, parse_entities  # noqa: E402


def _esc(label: str) -> str:
    """Re-apply Turtle string escaping (parse_entities returns unescaped labels)."""
    return (
        label.replace("\\", "\\\\").replace('"', '\\"')
        .replace("\n", "\\n").replace("\r", "\\r").replace("\t", "\\t")
    )


def seed_labels(questions_path: Path) -> set[str]:
    """The set of entity labels the (non-semantic) question set seeds on."""
    labels: set[str] = set()
    for line in questions_path.read_text().splitlines():
        if not line.strip():
            continue
        q = json.loads(line)
        if q.get("scoring") == "semantic":
            continue
        for s in q.get("seeds", []):
            if isinstance(s, dict) and "label" in s:
                labels.add(s["label"])
    return labels


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", type=Path, default=Path("produce/questions.jsonl"))
    ap.add_argument("--entities", type=Path, default=Path("data/rdf/hetionet.ttl"))
    ap.add_argument("--out", type=Path, default=Path("data/vector-corpus-entities.ttl"))
    ap.add_argument("--distractors", type=int, default=1500, help="Random non-seed entities to add.")
    ap.add_argument("--seed", type=int, default=20260608, help="RNG seed (reproducible corpus).")
    args = ap.parse_args()

    # Every literature entity, keyed by label (one representative per label).
    by_label: dict[str, tuple[str, str, str]] = {}
    everything: list[tuple[str, str, str]] = []
    for term, kind, label in parse_entities(args.entities):
        if kind in LITERATURE_KINDS:
            everything.append((term, kind, label))
            by_label.setdefault(label, (term, kind, label))

    wanted = seed_labels(args.questions)
    seeds = [by_label[l] for l in sorted(wanted) if l in by_label]
    missing = sorted(l for l in wanted if l not in by_label)

    seed_terms = {t for t, _, _ in seeds}
    pool = [e for e in everything if e[0] not in seed_terms]
    rng = random.Random(args.seed)
    distractors = rng.sample(pool, min(args.distractors, len(pool)))

    lines = ["@prefix hetio: <https://het.io/schema/> ."]
    for term, kind, label in seeds + distractors:  # seeds first: fetched before distractors
        lines += [f"{term} a hetio:{kind} ;", f'    rdfs:label "{_esc(label)}" .']
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text("\n".join(lines) + "\n")

    print(f"seeds={len(seeds)}  distractors={len(distractors)}  "
          f"total={len(seeds) + len(distractors)}  -> {args.out}")
    if missing:
        print(f"  {len(missing)} seed labels absent from literature kinds (expected — "
              f"anatomy etc.): {', '.join(missing)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
