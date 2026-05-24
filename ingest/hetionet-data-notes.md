# Hetionet v1.0 — data-wrangling notes

Empirical notes on the Hetionet source JSON, recorded while building `hetionet_to_rdf.py`.
These are observations from the *actual* file (not docs), so the transform rests on facts, not
assumptions. Update this file when the data or mapping changes.

## Source & provenance

- **File:** `data/hetionet/hetionet-v1.0.json.bz2` (gitignored bulk).
- **Origin:** `https://media.githubusercontent.com/media/hetio/hetionet/main/hetnet/json/hetionet-v1.0.json.bz2`
  (the `raw.githubusercontent.com` path returns a 133-byte **Git LFS pointer**, not the data — use the
  `media.githubusercontent.com/media/...` LFS endpoint).
- **Integrity:** sha256 `a342ab57e9073e6c02bb5e109d1f16917e6f933be4e5c77ebbaebfa26b984c19`
  (matches the LFS pointer's `oid`). Compressed 16.1 MB; **decompressed ~712 MB**.
- **License:** CC0 (Hetionet integrated graph).

## Memory constraint (drives the streaming design)

Dev box has ~7 GB RAM. `json.load` of a 712 MB document plus an in-memory `rdflib.Graph` of the full
graph does not fit. The transform therefore **streams** with `ijson` and writes Turtle line-by-line.
See the README "Ingestion is streaming, not in-memory" decision.

## Top-level JSON structure

Pretty-printed object with these keys:

| Key | Shape | Notes |
|---|---|---|
| `metanode_kinds` | list[str] | 11 node types. |
| `metaedge_tuples` | list[[src_kind, tgt_kind, kind, direction]] | 24 metaedges. |
| `kind_to_abbrev` | dict[str,str] | Single-letter abbrevs; **collide** across kinds (scoped per metaedge in Hetionet, not globally unique). Not used by the transform. |
| `nodes` | list[obj] | 47,031 nodes. |
| `edges` | list[obj] | 2,250,197 edges. |

## Nodes

Shape: `{"kind": str, "identifier": str|int, "name": str, "data": {...}}`.
`data` carries provenance (`source`, `license`, `url`) plus kind-specific extras.

**Identifier format per kind** (this determines the URI mapping — note Gene is an `int`):

| Node kind | Example id | id type | Vocabulary | Extra `data` keys |
|---|---|---|---|---|
| Anatomy | `UBERON:0001533` | str | Uberon | `mesh_id` |
| Biological Process | `GO:0032474` | str | GO | — |
| Cellular Component | `GO:0000784` | str | GO | — |
| Molecular Function | `GO:0031753` | str | GO | — |
| Compound | `DB00201` | str | DrugBank | `inchikey`, `inchi` |
| Disease | `DOID:14227` | str | Disease Ontology | — |
| Gene | `5345` | **int** | NCBI Entrez Gene | `description`, `chromosome` |
| Pathway | `PC7_3805` | str | Pathway Commons v7 (aggregate) | — |
| Pharmacologic Class | `N0000007632` | str | NDF-RT (FDA) | `class_type` |
| Side Effect | `C0023448` | str | UMLS CUI | — |
| Symptom | `D020150` | str | MeSH descriptor | — |

## Edges

Shape: `{"source_id": [kind, id], "target_id": [kind, id], "kind": str, "direction": str, "data": {...}}`.

- `source_id` / `target_id` are `[kind, identifier]` pairs; identifier is `int` for Gene, else `str`.
- `direction`: `both` for all metaedges **except `regulates` (Gene→Gene), which is `forward`** (directed).
- `data` is heterogeneous. Key frequencies across all 2.25M edges:

| Key | Count | Value shape |
|---|---|---|
| `unbiased` | 2,250,197 (all) | bool |
| `source` | 1,552,432 | str |
| `license` | 1,163,959 | str |
| `sources` | 697,765 | list[str] |
| `method` | 305,530 | str |
| `subtypes` | 265,672 | list[str] |
| `url` | 151,531 | str |
| `z_score` | 39,858 | float |
| `log2_fold_change` | 15,354 | float |
| `pubmed_ids` | 10,282 | list[int] |
| `actions` | 9,558 | list[str] |
| `similarity` | 6,486 | float |
| `affinity_nM` | 2,189 | float |
| `urls` | 1,978 | list[str] |

Note `source` (str) and `sources` (list) both occur — different upstream conventions. List-valued keys
(`sources`, `subtypes`, `pubmed_ids`, `actions`, `urls`) expand to one annotation triple per element.

Edge `kind`/`direction` counts (16 distinct kinds; metaedges distinguish by src/tgt too):
`participates` 814,664 · `expresses` 526,407 · `regulates`(fwd) 265,672 · `interacts` 147,164 ·
`causes` 138,944 · `downregulates` 130,965 · `upregulates` 124,335 · `covaries` 61,690 ·
`associates` 12,623 · `binds` 11,571 · `resembles` 7,029 · `localizes` 3,602 · `presents` 3,357 ·
`includes` 1,029 · `treats` 755 · `palliates` 390.

## URI mapping (decisions — provisional)

Entities use stable external vocabularies where one cleanly fits; schema lives under `hetio:`.
The four named in CLAUDE.md (`db:`, `do:`, `ncbigene:`, `uberon:`) are fixed; the rest are reasonable
defaults, flagged below where no clean external vocab exists.

| Kind | Prefix | Namespace IRI | Local part |
|---|---|---|---|
| Compound | `db:` | `https://identifiers.org/drugbank/` | full id (`DB00201`) |
| Disease | `do:` | `http://purl.obolibrary.org/obo/DOID_` | strip `DOID:` |
| Gene | `ncbigene:` | `https://identifiers.org/ncbigene/` | int as str |
| Anatomy | `uberon:` | `http://purl.obolibrary.org/obo/UBERON_` | strip `UBERON:` |
| BP / CC / MF | `go:` | `http://purl.obolibrary.org/obo/GO_` | strip `GO:` |
| Side Effect | `umls:` | `https://identifiers.org/umls/` | full CUI |
| Symptom | `mesh:` | `https://identifiers.org/mesh/` | full id |
| Pharmacologic Class | `ndfrt:` | `https://identifiers.org/ndfrt/` | full id |
| Pathway | `pathway:` | `https://het.io/pathway/` | full id — **project-minted**; no clean external vocab for `PC7_*` |

Schema namespace: `hetio: <https://het.io/schema/>` — node-type classes (`hetio:Compound`, …),
relation predicates (`hetio:treats`, …), and edge-annotation predicates (`hetio:source`,
`hetio:license`, `hetio:unbiased`, …). Node label via `rdfs:label`.

## RDF-star edge representation

Each edge → one base triple plus annotations on the quoted triple:

```turtle
db:DB00201 hetio:treats do:1612 .
<< db:DB00201 hetio:treats do:1612 >>
    hetio:source "DrugCentral" ;
    hetio:license "CC BY 4.0" ;
    hetio:unbiased false ;
    hetio:direction "both" .
```

- **Direction.** Project 1 reasoning is `empty`, so symmetric (`both`) edges are **not** auto-inverted.
  Decision: emit a single source→target base triple and record `hetio:direction`; the graph retriever
  handles `both` edges with inverse-aware SPARQL (UNION / inverse paths) rather than doubling triples.
  Revisit if query ergonomics suffer.
- List-valued `data` keys → repeated annotation predicates (one object per element).
- `unbiased` is on every edge; kept as a typed boolean annotation.

## Validation tooling

`rdflib` 7.6 **cannot parse RDF-star** — not the `<< >>` quoted-triple syntax, not the `{| |}`
annotation syntax, and there is no `turtle-star` parser plugin. So generated output is validated
with **pyoxigraph** (Rust-backed Oxigraph), which parses Turtle-star and runs SPARQL-star offline.
`hetionet_to_rdf.py --validate` re-parses the smoke slice; `tests/` runs SPARQL/SPARQL-star
assertions against a tiny in-memory store. Oxigraph also stands in for GraphDB during development —
GraphDB remains the final confirmation once the slice is loaded for real.
