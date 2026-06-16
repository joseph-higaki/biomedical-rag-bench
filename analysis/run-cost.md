# Run cost — per-query LLM spend (methodology + the tokens→$ plan)

**What this is.** The *query-time* cost of an eval run: the LLM tokens spent at **generation**,
**SPARQL-writing** (`graph_sparqlgen` only), and **judging**. It is the **opex** complement of
[`build-cost.md`](build-cost.md)'s **capex** — that page covers the one-time cost of *building* each
backend's index (no LLM tokens; graph builds offline, vector embeds locally at $0); this page covers
the recurring cost of *running* a query. Total cost of ownership = build + run, and because build's
external dollar cost is ~$0 here, **the dollar cost of this benchmark is almost entirely run cost.**

**Relation to H5.** The per-backend slice of this — mean `retrieval_context_input_tokens` — is
**H5's query-token-cost leg** (alongside query latency and the build profile); this page is the
methodology H5 leans on. The rest here (writer spend, judge spend, the generic tokens→$ price dim)
is *cross-cutting* cost accounting that spans factors H5 doesn't model — the judge cost tracks
question *type*, not the backend. So: H5 uses the per-backend aggregate; this doc owns the full
method. (`retrieval_context_input_tokens` *per type* is instead H1's token-efficiency test.)

Like the rest of `analysis/`, this is consumer-side interpretation and a candidate to lift into the
analytics repo (see [`README.md`](README.md) → Extraction boundary).

## The rule: never sum tokens; sum dollars

Raw token counts are **not additive**, for two distinct reasons — keep them separate:

1. **Wrong tokenizer (subtraction).** The offline `context_tokens` proxy and the billed `usage`
   counts are different currencies; subtracting them is a units error. This is the
   [token-units rule](../retrievers/README.md#the-token-units-rule-read-before-doing-any-token-math).
   The one legitimate *token* decomposition is `retrieval_context_input_tokens` =
   `input_tokens(retriever) − input_tokens(closed_book)`, **same model, same direction (input)** —
   it never crosses a price boundary, so the two counts share a rate.

2. **Wrong price (addition).** Even all-billed counts don't add across components: generator, writer,
   and judge can each run a **different model**, and every model prices **input, cached-read,
   cache-creation, and output** tokens at **different rates**. Adding counts across two models — or
   even input + output within one — sums quantities at unequal prices. Economically meaningless.

The only additive unit is **dollars**: convert each token tier to cost at its own rate, *then* sum.

## The tokens→$ plan (downstream analytics step)

The fact table is already **wide** — each tier is its own telemetry column, per component:

| Component | Columns |
|---|---|
| Generator | `input_tokens`, `output_tokens`, `cache_read_input_tokens`, `cache_creation_input_tokens` |
| SPARQL writer (`graph_sparqlgen`) | `writer_input_tokens`, `writer_output_tokens` |
| Judge (fuzzy/semantic) | `judge_input_tokens`, `judge_output_tokens` |

Because direction is encoded in the column names, **no `token_type` dimension is needed**. The price
side is a small dim at grain **`(date, model)`** with matching **per-tier rate columns**
(`input_rate`, `output_rate`, `cache_read_rate`, `cache_creation_rate`). Note **four** generator
tiers, not three — cache *creation* (the write, ~1.25× input on Anthropic) and cache *read* (~0.1×
input) price differently.

Pipeline:

1. Join each component's `(date, model)` to the price dim. Date matters because rates change over
   time; the run logs the model it actually used (`generator_model_resolved` / `writer_model` /
   `judge_model`).
2. Multiply each token column by its tier rate → a **per-component dollar cost**.
3. **Sum the dollars** across components for the run's total. You add dollars, never tokens.

A long/melted price dim keyed by `token_type` is an *equivalent* modeling choice, not a requirement —
the wide fact already separates the tiers, so wide-rate-columns is the lower-friction join.

## What's reportable in-repo today

Until the price dim exists, the notebook keeps the two cost columns **separate and same-unit**, never
summed:

- `retrieval_context_input_tokens` — the unit-safe input-token weight the retrieved context adds vs
  the no-context baseline (rule 1 above). Populated for all rows.
- `writer_input_tokens` — the SPARQL-writer spend inside `graph_sparqlgen`; `NaN` for the four
  no-writer retrievers (correct by design, not missing). See `explore.ipynb` → "Cost".

The dollar total is deferred to the analytics repo, where the price dim lives.
