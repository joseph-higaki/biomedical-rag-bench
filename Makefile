.PHONY: help hooks test registry explain ingest ingest-rdf ingest-vectors ingest-smoke ingest-load up down clean-graphdb graphdb-ready eval-full

# The model under test, fixed across all five conditions in a sweep (the hard constraint:
# the generator never varies across retriever conditions in one comparison). Override per-run:
# `make eval-full GEN=anthropic:claude-sonnet-4-6`.
GEN ?= anthropic:claude-haiku-4-5

help:  ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  %-20s %s\n", $$1, $$2}'

hooks:  ## Activate git hooks (.githooks/ — strips AI attribution from commit messages)
	git config core.hooksPath .githooks
	@echo "git hooks active: core.hooksPath -> .githooks/"

up:  ## Start GraphDB locally (background)
	docker compose up -d
	@echo "GraphDB Workbench: http://localhost:7200"

graphdb-ready:  ## Ensure GraphDB is up AND the hetionet repo is served; self-heal a stale WSL mount (down/up). Gates eval runs.
	@bash scripts/graphdb_ready.sh

down:  ## Stop GraphDB
	docker compose down

clean-graphdb:  ## Wipe GraphDB data (destructive — confirms first)
	@echo "This will delete ./graphdb-data/ and all loaded triples."
	@read -p "Type 'wipe' to confirm: " confirm && [ "$$confirm" = "wipe" ]
	docker compose down
	rm -rf ./graphdb-data

ingest: ingest-rdf ingest-vectors  ## Run the full ingestion pipeline

ingest-rdf:  ## Convert Hetionet JSON to Turtle
	uv run --extra ingest python ingest/rdf/hetionet_to_rdf.py --out data/rdf/hetionet.ttl
	@echo ""
	@echo "Now load data/rdf/hetionet.ttl into GraphDB via the Workbench."
	@echo "See ingest/rdf/README.md for the one-time repository setup."

ingest-vectors:  ## Fetch PubMed abstracts and build the Chroma collection
	uv run --extra fetch python ingest/vector/pubmed_fetch.py --entities data/rdf/hetionet.ttl --out data/abstracts/
	uv run --extra vector python ingest/vector/build_vectors.py --abstracts data/abstracts/ --out data/chroma/

ingest-smoke:  ## Smoke-test ingestion on a tiny slice (build order step 1)
	uv run --extra ingest python ingest/rdf/hetionet_to_rdf.py --limit 100 --out data/rdf/hetionet-smoke.ttl
	uv run --extra fetch python ingest/vector/pubmed_fetch.py --entities data/rdf/hetionet-smoke.ttl --out data/abstracts-smoke/
	uv run --extra vector python ingest/vector/build_vectors.py --abstracts data/abstracts-smoke/ --out data/chroma-smoke/

ingest-load:  ## Load data/rdf/hetionet.ttl into GraphDB (clears existing data first)
	@test -f data/rdf/hetionet.ttl || { echo "error: data/rdf/hetionet.ttl not found — run make ingest-rdf first"; exit 1; }
	curl -i -X DELETE 'http://localhost:7200/repositories/hetionet/statements'
	curl -i -X POST -H 'Content-Type: text/turtle' \
	     -T data/rdf/hetionet.ttl \
	     'http://localhost:7200/repositories/hetionet/statements'

registry:  ## Regenerate template registry + eval distribution table from YAML (offline)
	uv run --extra produce python produce/templates/build_registry.py

explain: graphdb-ready  ## Regenerate producer worked examples (produce/EXAMPLE.md) — needs GraphDB + full graph
	uv run --extra produce python produce/produce.py --explain --out produce/EXAMPLE.md

test:  ## Run the test suite (hermetic — no downloaded data required)
	uv run --extra ingest pytest

eval-full: graphdb-ready  ## Full eval: all 58 questions × 5 retrievers, fixed generator (override GEN=...). Real API spend.
	uv run --extra generate                python eval/run_eval.py --run --retriever closed_book             --generator $(GEN) --limit 58 --include-semantic
	uv run --extra generate --extra vector python eval/run_eval.py --run --retriever vector                  --generator $(GEN) --limit 58 --include-semantic
	uv run --extra generate --extra graph  python eval/run_eval.py --run --retriever graph_neighborhood_1hop  --generator $(GEN) --limit 58 --include-semantic
	uv run --extra generate --extra graph  python eval/run_eval.py --run --retriever graph_neighborhood_2hop  --generator $(GEN) --limit 58 --include-semantic
	uv run --extra generate --extra graph  python eval/run_eval.py --run --retriever graph_sparqlgen          --generator $(GEN) --limit 58 --include-semantic
