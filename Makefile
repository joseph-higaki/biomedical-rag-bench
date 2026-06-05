.PHONY: help hooks test registry ingest ingest-rdf ingest-vectors ingest-smoke ingest-load up down clean-graphdb

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

hooks:  ## Activate git hooks (.githooks/ — strips AI attribution from commit messages)
	git config core.hooksPath .githooks
	@echo "git hooks active: core.hooksPath -> .githooks/"

up:  ## Start GraphDB locally (background)
	docker compose up -d
	@echo "GraphDB Workbench: http://localhost:7200"

down:  ## Stop GraphDB
	docker compose down

clean-graphdb:  ## Wipe GraphDB data (destructive — confirms first)
	@echo "This will delete ./graphdb-data/ and all loaded triples."
	@read -p "Type 'wipe' to confirm: " confirm && [ "$$confirm" = "wipe" ]
	docker compose down
	rm -rf ./graphdb-data

ingest: ingest-rdf ingest-vectors  ## Run the full ingestion pipeline

ingest-rdf:  ## Convert Hetionet JSON to Turtle
	uv run --extra ingest python ingest/rdf/hetionet_to_rdf.py --out ontology/hetionet.ttl
	@echo ""
	@echo "Now load ontology/hetionet.ttl into GraphDB via the Workbench."
	@echo "See ingest/rdf/README.md for the one-time repository setup."

ingest-vectors:  ## Fetch PubMed abstracts and build the Chroma collection
	uv run --extra fetch python ingest/vector/pubmed_fetch.py --entities ontology/hetionet.ttl --out data/abstracts/
	uv run --extra vector python ingest/vector/build_vectors.py --abstracts data/abstracts/ --out data/chroma/

ingest-smoke:  ## Smoke-test ingestion on a tiny slice (build order step 1)
	uv run --extra ingest python ingest/rdf/hetionet_to_rdf.py --limit 100 --out ontology/hetionet-smoke.ttl
	uv run --extra fetch python ingest/vector/pubmed_fetch.py --entities ontology/hetionet-smoke.ttl --out data/abstracts-smoke/
	uv run --extra vector python ingest/vector/build_vectors.py --abstracts data/abstracts-smoke/ --out data/chroma-smoke/

ingest-load:  ## Load ontology/hetionet.ttl into GraphDB (clears existing data first)
	@test -f ontology/hetionet.ttl || { echo "error: ontology/hetionet.ttl not found — run make ingest-rdf first"; exit 1; }
	curl -i -X DELETE 'http://localhost:7200/repositories/hetionet/statements'
	curl -i -X POST -H 'Content-Type: text/turtle' \
	     -T ontology/hetionet.ttl \
	     'http://localhost:7200/repositories/hetionet/statements'

registry:  ## Regenerate template registry + eval distribution table from YAML (offline)
	uv run --extra produce python eval/templates/build_registry.py

test:  ## Run the test suite (hermetic — no downloaded data required)
	uv run --extra ingest pytest
