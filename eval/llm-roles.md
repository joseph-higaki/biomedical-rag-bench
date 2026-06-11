# The three LLM roles

This benchmark calls an LLM in **three distinct roles**. They are easy to conflate —
they all go through the same provider adapter and they all log a model + temperature — but
they sit at different points in the pipeline, carry different system prompts, and answer to
different config knobs. Confusing them is what once hid a temperature drift (session 16), so
this page names them once, in one place.

> **Source of truth is the code.** The prompts below are mirrored from the files cited under
> each role; if they ever disagree, the source file wins and this page should be updated
> (same rule as README-vs-CLAUDE.md). The model/temperature *defaults* are env-overridable.

## At a glance

| | **Generator-under-test** | **SPARQL writer** | **Semantic judge** |
|---|---|---|---|
| **What it does** | Answers the question from the retrieved context (or closed-book) | Inside `graph_sparqlgen`: writes one SPARQL `SELECT` from the schema vocabulary | Scores answer↔reference *equivalence* on type-10 (the one non-deterministic judge) |
| **Pipeline position** | the **condition under test** — varies across the experiment grid | part of the **retrieval mechanism** — its cost is logged apart from the generator's | the **scorer** — runs downstream, on the answer |
| **System prompt** | `eval/harness.py` → `SYSTEM_PROMPT` | `retrievers/sparqlgen.py` → `SCHEMA_PROMPT` | `eval/judge/semantic.py` → `_SYSTEM` |
| **Model (env / flag)** | `--generator PROVIDER:MODEL` / `GENERATOR_MODEL` | `SPARQLGEN_MODEL` (default `claude-haiku-4-5`) | `JUDGE_MODEL` (default `claude-haiku-4-5`) |
| **Temperature (env)** | `GENERATOR_TEMPERATURE` (default `0.0`) | `SPARQLGEN_TEMPERATURE` (default `0.0`) | constructor default `0.0` |
| **Can be a local model?** | **Yes** — mechanically identical (`from_spec` accepts `ollama:…`). *Experimentally* pinned to Haiku-or-better for the headline benchmark; local generators are an exploration knob (e.g. q10 / H4), never the default condition. | **Yes** — local writers are a legitimate factor; their text-to-SPARQL skill is what's being measured. | **Yes** — but a local judge is subject to its **own** kappa calibration before its verdicts are trusted. |
| **Logged where** | result row: `generator_model_resolved`, `generator_temperature`, `system_prompt_sha256` | `traversal_info`: `writer_model`, `writer_temperature`, `writer_input_tokens`, `writer_output_tokens` | `judge_details`: `judge_model`, `judge_temperature` |
| **Constancy** | **Fixed within a run** (hard constraint — never varied across retriever conditions in the same run) | per *retrieval* (its own LLM call, its own billed tokens) | per *verdict* |

## The shared invariant

**Wherever a model is logged, its temperature is logged beside it.** A "deterministic-judged"
row says nothing about the *generator's* sampling temperature; treating the two as one is the
exact conflation that let a hot generator drift undetected. So each role records both, and each
row/trace is self-describing.

## The shared seam

All three roles construct their client through one factory — `eval/generate/registry.py` →
`from_spec(spec, default_provider="anthropic", temperature=…)`. A bare model name
(`claude-haiku-4-5`) stays Anthropic; a `provider:model` spec (`ollama:qwen2.5:3b-instruct`)
routes to that provider's adapter. This is why "use a local model" is the *same* one-line change
for all three, and why no role hard-codes a provider SDK. Adapters live in
`eval/generate/{anthropic_generator,ollama_generator}.py` behind the `Generator` protocol in
`eval/generate/base.py`.

## The prompts, verbatim

### Generator-under-test — `eval/harness.py:SYSTEM_PROMPT`

```
You are answering biomedical questions in an automated evaluation. When Context is provided,
answer using only that Context. When no Context is provided, answer from your own knowledge —
do not reply that you lack context or cannot answer for that reason; give your best answer.
Output only the answer itself: no headings, no preamble, no explanation, no commentary.
Answer format:
- If the answer is a list of entities, output each entity on its own line and nothing else.
- If the answer is a count, output just the number.
- If the answer is yes/no, start with "Yes" or "No".
- If nothing satisfies the question, answer "None".
```

The user turn is `Context:\n{context}\n\nQuestion: {question}` when the retriever returned
context, else just `Question: {question}`. The same system prompt is used for `closed_book` and
every retrieval condition — so the *only* thing that varies between conditions is the context
block, which is the whole point.

### SPARQL writer — `retrievers/sparqlgen.py:SCHEMA_PROMPT`

The writer's entire knowledge of the graph is this prompt: node types, **directed** edge
signatures, literal attributes, the prefixes, and the anchoring rules. No URIs, no reasoning
(the Project-1 hard constraint). The load-bearing framing and rules:

````
You translate a biomedical question into exactly ONE SPARQL SELECT query over the Hetionet
knowledge graph. Output ONLY the query inside a ```sparql code fence — no prose, no explanation.

Always include these prefixes:
PREFIX hetio: <https://het.io/schema/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

Anchor every named entity by its label, copied EXACTLY as written in the question:
  ?gene rdfs:label "HTR3B" .
Never invent or guess a URI.
````

The full node-type list, the directed edge table (e.g. `Disease localizes Anatomy`), and the
SELECT/COUNT/ORDER rules are the rest of `SCHEMA_PROMPT` — read the source for the authoritative,
complete vocabulary. One robustness behavior is handled in `_extract_query`: small instruct
models open a ```` ```sparql ```` fence and forget to close it, so an unterminated fence is
salvaged by stripping fence-only lines (verified on `ollama:qwen2.5:3b-instruct`).

> **Known unhandled failure mode — local writers and label case.** Hetionet `rdfs:label`s
> are case-sensitive and mostly lowercase (`"asthma"`), but small instruct models reflexively
> title-case proper nouns, anchoring on `"Asthma"` and silently returning 0 rows on an
> otherwise-correct query. A prompt-level "preserve the exact case" instruction was tried and
> **reverted**: it fixed the 3B local writer but *deterministically* degraded the default haiku
> writer (it reshuffled an `associates` edge direction on one question at temperature 0). The
> proper fix — case-insensitive label anchoring at the query level, robust for every writer —
> is deferred to when the local-writer experiment is actually run. Until then, a local SPARQL
> writer's case errors are an honest measured miss.

### Semantic judge — `eval/judge/semantic.py:_SYSTEM`

```
You grade answers to a biomedical identification quiz. You are given the QUESTION, the REFERENCE
answer (the correct entity, derived from a knowledge graph), and a CANDIDATE answer from a model.
Decide only whether the CANDIDATE names the SAME biomedical entity as the REFERENCE.
Treat as the same entity: synonyms, brand vs. generic drug names (Coumadin = Warfarin), gene
symbol vs. protein vs. full name (p53 = TP53 = tumor protein p53), standard abbreviations, and
punctuation/possessive/spacing variants (Alzheimer disease = Alzheimer's disease).
Treat as NOT the same: a different entity, a broader/narrower category instead of the specific
entity, or an answer that hedges among several options or refuses without committing to one.
Respond with EXACTLY one word on the first line — EQUIVALENT or DIFFERENT — then, on a second
line, a reason of at most 15 words.
```

The judge tests *equivalence against a fixed graph-derived reference* — it never invents the
ground truth. An empty/whitespace candidate short-circuits to DIFFERENT with no model call.
Because it is the only LLM in the scoring loop, it is the one role whose own reliability must be
**calibrated** (Cohen's kappa vs. human grades) before its verdicts are cited — see the build-order
follow-up in the root README and `eval/README.md`.

## Why three, not one

- The **generator** is the subject of the experiment; everything else exists to feed and grade it.
- The **writer** is a *retrieval skill* — "can an LLM write the right query?" — deliberately
  separated so its token cost and failures are never confounded with the generator's.
- The **judge** is *measurement apparatus*; it must be cheap, reproducible, and independently
  trustworthy, which is why it is deterministic everywhere except the one type that genuinely
  needs semantic equivalence.

Keeping them distinct — distinct prompts, distinct knobs, distinct telemetry — is what lets a
single run vary one factor at a time and stay reproducible.
