.PHONY: help hooks test registry explain ingest ingest-rdf ingest-vectors ingest-smoke ingest-load up down clean-graphdb graphdb-ready eval-full export-full-runs \
        eval-full-haiku-haiku-haiku eval-full-haiku-qwen-haiku eval-full-haiku-sonnet-haiku \
        eval-full-sonnet-haiku-haiku eval-full-sonnet-qwen-haiku \
        eval-full-qwen-haiku-haiku eval-full-qwen-qwen-haiku

# Per-role model knobs for a sweep, each a `provider:model` spec. NO defaults on purpose: a sweep
# must name its models — a blank model fails fast in the harness, never a silent fallback to some
# model the run didn't choose (matches --*-model_family having no default). GEN is held fixed across
# all five conditions (hard constraint: the generator never varies within a sweep). Used by the
# ad-hoc `eval-full`; the named eval-full-<gen>-<writer>-<judge> targets pin their own specs.
#   GEN    — generator under test (every condition)
#   WRITER — SPARQL writer (graph_sparqlgen only)
#   JUDGE  — semantic judge (type-10 questions only)
GEN ?=
WRITER ?=
JUDGE ?=

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

# One full sweep — 58 questions × 5 retrievers for a single (generator, writer, judge) triple.
# $(1)=generator $(2)=writer $(3)=judge, each a provider:model spec. The generator is identical
# across all five conditions (hard constraint); the writer fires only on graph_sparqlgen and the
# judge only on type-10, but passing all three to every line is harmless (each LLM is lazy) and
# keeps the conditions uniform. Real API spend — five runs, ~290 trials.
define eval_full_sweep
	uv run --extra generate python eval/run_eval.py --run --retriever closed_book --generator_model_family $(1) --writer_model_family $(2) --judge_model_family $(3) --limit 58 --include-semantic
	uv run --extra generate --extra vector python eval/run_eval.py --run --retriever vector --generator_model_family $(1) --writer_model_family $(2) --judge_model_family $(3) --limit 58 --include-semantic
	uv run --extra generate --extra graph python eval/run_eval.py --run --retriever graph_neighborhood_1hop --generator_model_family $(1) --writer_model_family $(2) --judge_model_family $(3) --limit 58 --include-semantic
	uv run --extra generate --extra graph python eval/run_eval.py --run --retriever graph_neighborhood_2hop --generator_model_family $(1) --writer_model_family $(2) --judge_model_family $(3) --limit 58 --include-semantic
	uv run --extra generate --extra graph python eval/run_eval.py --run --retriever graph_sparqlgen --generator_model_family $(1) --writer_model_family $(2) --judge_model_family $(3) --limit 58 --include-semantic
endef

eval-full: graphdb-ready  ## Full sweep, ad-hoc models: make eval-full GEN=... WRITER=... JUDGE=... (all three required, provider:model). Real API spend.
	@[ -n "$(GEN)" ] && [ -n "$(WRITER)" ] && [ -n "$(JUDGE)" ] || { echo "eval-full needs GEN, WRITER, JUDGE (provider:model each) — or run a named eval-full-<gen>-<writer>-<judge> target"; exit 1; }
	$(call eval_full_sweep,$(GEN),$(WRITER),$(JUDGE))

eval-full-haiku-haiku-haiku: graphdb-ready  ## sweep: gen=haiku  writer=haiku       judge=haiku
	$(call eval_full_sweep,anthropic:claude-haiku-4-5,anthropic:claude-haiku-4-5,anthropic:claude-haiku-4-5)

eval-full-haiku-qwen-haiku: graphdb-ready  ## sweep: gen=haiku  writer=qwen-coder  judge=haiku
	$(call eval_full_sweep,anthropic:claude-haiku-4-5,ollama:qwen2.5-coder:1.5b,anthropic:claude-haiku-4-5)

eval-full-haiku-sonnet-haiku: graphdb-ready  ## sweep: gen=haiku  writer=sonnet      judge=haiku
	$(call eval_full_sweep,anthropic:claude-haiku-4-5,anthropic:claude-sonnet-4-6,anthropic:claude-haiku-4-5)

eval-full-sonnet-haiku-haiku: graphdb-ready  ## sweep: gen=sonnet writer=haiku       judge=haiku
	$(call eval_full_sweep,anthropic:claude-sonnet-4-6,anthropic:claude-haiku-4-5,anthropic:claude-haiku-4-5)

eval-full-sonnet-qwen-haiku: graphdb-ready  ## sweep: gen=sonnet writer=qwen-coder  judge=haiku
	$(call eval_full_sweep,anthropic:claude-sonnet-4-6,ollama:qwen2.5-coder:1.5b,anthropic:claude-haiku-4-5)

eval-full-qwen-haiku-haiku: graphdb-ready  ## sweep: gen=qwen-instruct writer=haiku       judge=haiku
	$(call eval_full_sweep,ollama:qwen2.5:3b-instruct,anthropic:claude-haiku-4-5,anthropic:claude-haiku-4-5)

eval-full-qwen-qwen-haiku: graphdb-ready  ## sweep: gen=qwen-instruct writer=qwen-coder  judge=haiku
	$(call eval_full_sweep,ollama:qwen2.5:3b-instruct,ollama:qwen2.5-coder:1.5b,anthropic:claude-haiku-4-5)

export-full-runs:  ## Copy complete runs (58 q) from eval/results to the analytics repo ingestion_sample/
	uv run python scripts/copy_full_runs.py \
		eval/results \
		/home/jhigaki/projects/rag-bench-analytics/ingestion_sample
