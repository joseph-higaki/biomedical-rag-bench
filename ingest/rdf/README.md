# RDF ingestion (graph side)

Converts Hetionet JSON to RDF-star Turtle and loads it into GraphDB. Covers
Projects 1–2: Project 1 loads the instance data with `ruleset=empty`; Project 2
adds reasoning over the same triples without changing this transform.

```
hetionet_to_rdf.py    Hetionet JSON          → ontology/hetionet.ttl
        ↓
   (manual, one-time)  ontology/hetionet.ttl  → GraphDB repository
```

`hetionet_to_rdf.py` streams the JSON with `ijson` and writes Turtle
statement-by-statement — it never materializes the full graph in memory (see the
README "Ingestion is streaming, not in-memory" decision). The URI mapping, source
structure, and the RDF-star triple-count note live in
[`hetionet-data-notes.md`](hetionet-data-notes.md).

## Prerequisite: GraphDB license

As of **GraphDB 11.0**, the Free edition is no longer license-free. The container
starts and answers reads, but **writes fail with `No license was set`** until a
free license file is in place. Request it from Ontotext (emailed), save it as
`secrets/graphdb.license`, then `make down && make up`. Full steps in
`secrets/README.md`. One-time per developer.

## One-time GraphDB repository setup

After `make up` brings GraphDB online (with the license, above) and
`make ingest-rdf` produces `ontology/hetionet.ttl`, create the `hetionet`
repository. Scripted (preferred — reproducible, ruleset baked in):

```bash
curl -X POST http://localhost:7200/rest/repositories \
     -F "config=@ingest/rdf/graphdb-repo-config.ttl"
```

The config sets **Repository ID** `hetionet` and **ruleset** `empty` (no
reasoning — the Project 1 baseline; Project 2 changes this). Or, equivalently,
through the Workbench:

1. Open http://localhost:7200 in a browser.
2. **Setup → Repositories → Create new repository.**
3. **Repository type:** GraphDB Repository.
4. **Repository ID:** `hetionet`.
5. **Ruleset:** `empty`. This disables reasoning, which is the Project 1 baseline. (Project 2 changes this.)
6. **Title:** `Hetionet (Project 1 baseline)`.
7. Leave other defaults; click **Create**.

Then load the Turtle file. The full graph is ~470 MB, which exceeds the
Workbench browser-upload cap (200 MB, `graphdb.workbench.maxUploadSize`), so load
it over the REST statements endpoint instead — it streams the file with no size
limit and is scriptable:

```bash
# Clear any existing data in the repo (e.g. a prior smoke slice). Returns HTTP 204.
curl -i -X DELETE 'http://localhost:7200/repositories/hetionet/statements'

# Stream-load the full graph. POST = add; -T streams the file (no 470 MB buffer).
# ~5–10 minutes on GraphDB's single write thread; curl blocks silently until done,
# then prints "204 No Content" — an empty body is success, not a failure.
curl -i -X POST -H 'Content-Type: text/turtle' \
     -T ontology/hetionet.ttl \
     'http://localhost:7200/repositories/hetionet/statements'
```

RDF-star quoted triples (`<< … >>`) parse under plain `text/turtle` in GraphDB 11
(RDF4J 5.x); if a build ever rejects them, retry with
`-H 'Content-Type: application/x-turtle-star'`.

The Workbench is fine for the **smoke slice** (well under the cap): **Import →
User data → Upload RDF files**, select the `.ttl`, **Target graphs:** `From data`
(so the Turtle's prefixes are honored), **Import**.

When the load completes, verify with a SPARQL query in **SPARQL** in the left nav:

```sparql
SELECT (COUNT(*) AS ?total) WHERE { ?s ?p ?o }
```

Should return **~11.2M**. This is the *triple* count, ~5× the edge count: each of
the 2.25M edges contributes its base triple plus ~4 RDF-star annotation triples
(`direction`, `source`, `license`, `pubmed_ids`, …), and each of the 47k nodes
adds a type + label triple. The `…: 2250197 edges` line printed by
`make ingest-rdf` reports **edges, not triples** — the two are not meant to match.

## Re-ingesting

The Turtle file changes if `hetionet_to_rdf.py` changes (new URI conventions, RDF-star edge properties, etc.). To re-ingest:

1. Re-run `make ingest-rdf` to regenerate `ontology/hetionet.ttl`.
2. Clear and reload over the REST statements endpoint (the two `curl` commands
   above): the `DELETE` clears the old data, the `POST` streams the new file.

Or, faster during development, use `make clean-graphdb` to wipe everything and start fresh:

```bash
make clean-graphdb     # destroys ./graphdb-data/, confirms first
make up                # restart GraphDB
# then recreate the repository as above
```

## Output

- `ontology/hetionet.ttl` — full RDF graph, loaded into GraphDB. Consumed by `retrievers/graph.py`.
