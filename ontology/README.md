# ontology/

**Committed schema only.** This folder holds hand-authored, version-controlled RDF schema —
never generated bulk.

- `hetionet-schema.ttl` (TBox) — **arrives in Project 2.** The class/property hierarchy and
  OWL axioms that reasoning operates over. Hand-authored source, committed.

The **generated** instance data (ABox) — `data/rdf/hetionet.ttl` and its smoke slice — is
*not* here. It is regenerable by `make ingest-rdf` (~470 MB) and lives under the gitignored
`data/` bulk root, alongside the Chroma collection and PubMed abstracts. The split is by
**provenance**: generated artifacts in `data/`, committed source here.

See the root README → Repository structure, and `ingest/rdf/README.md` for how the instance
graph is produced and loaded.
