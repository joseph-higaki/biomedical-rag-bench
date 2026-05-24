.PHONY: help test ingest ingest-rdf ingest-vectors ingest-smoke up down clean-graphdb

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

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
	python ingest/hetionet_to_rdf.py --out ontology/hetionet.ttl
	@echo ""
	@echo "Now load ontology/hetionet.ttl into GraphDB via the Workbench."
	@echo "See ingest/README.md for the one-time repository setup."

ingest-vectors:  ## Fetch PubMed abstracts and build the Chroma collection
	python ingest/pubmed_fetch.py --entities ontology/hetionet.ttl --out data/abstracts/
	python ingest/build_vectors.py --abstracts data/abstracts/ --out data/chroma/

ingest-smoke:  ## Smoke-test ingestion on a tiny slice (build order step 1)
	python ingest/hetionet_to_rdf.py --limit 100 --out ontology/hetionet-smoke.ttl
	python ingest/pubmed_fetch.py --limit 5 --out data/abstracts-smoke/
	python ingest/build_vectors.py --abstracts data/abstracts-smoke/ --out data/chroma-smoke/

test:  ## Run the test suite (hermetic — no downloaded data required)
	uv run --extra ingest pytest
