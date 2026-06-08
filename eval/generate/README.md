# Generation

The **model under test**. After a retriever supplies context, the generator reads that
context plus the question and produces the answer the judges score. It is the second of the
three eval swap points (retriever → **generator** → judge), and the one the benchmark
*varies across runs* to ask "does the crossover hold for a small local model vs. a frontier
hosted one?" while holding it *fixed within a run* for comparability.

`eval/README.md` owns the eval *design* (taxonomy, metrics, the factorial provenance);
this file documents the generation *subsystem*: the contract, the provider-agnostic
Strategy split, and the model-id provenance the analysis layer keys on.

> **Status (build step 5).** The provider-neutral contract (`base.py`) and the Anthropic
> adapter (`anthropic_generator.py`) are built and hermetically tested (`tests/test_generate.py`).
> One provider today; Ollama/OpenAI adapters are one sibling file + one registry entry each.

## The contract — `base.py`

```python
@dataclass
class GenerationResult:
    text: str            # the answer string handed to the judge
    model: str           # the RESOLVED id the provider reports it ran (see below)
    provider: str        # which adapter produced it (a factorial factor)
    input_tokens: int    # billed prompt tokens, in the generator's own tokenizer
    output_tokens: int   # billed completion tokens
    latency_ms: float
    cache_read_input_tokens: int | None = None      # billed-cost detail, when reported
    cache_creation_input_tokens: int | None = None
    finish_reason: str | None = None
    tool_calls: list[dict] = ...                     # normalized, provider-agnostic
    raw_usage: dict = ...                            # provider's untouched usage, for audit

class Generator(Protocol):                           # structural, runtime_checkable
    model: str
    provider: str
    def generate(self, prompt, *, system=None, tools=None) -> GenerationResult: ...
```

Additive-only, like `RetrievalResult` and `JudgeResult`: new optional fields and new
`raw_usage` keys are fine forever; existing ones never change meaning.

## Provider-agnostic by design (the Strategy pattern)

`base.py` is the neutral context; each adapter (`anthropic_generator.py` now) is a concrete
strategy that owns **all** provider/SDK specifics and is the **only** module importing the
SDK. Four dimensions stay neutral at the protocol surface — message exchange, a separate
`system` channel, normalized token `usage`, and neutral tool specs/`tool_calls` — and the
adapter maps its SDK onto each. No orchestration framework (no LiteLLM): ~3 providers,
hand-rolled. Adapters are swapped behind the `GENERATORS` registry in `eval/run_eval.py`,
beside the retriever and judge registries; adding one changes nothing above the protocol.

**Fixed within a run, varied across runs.** A hard constraint (`.claude/CLAUDE.md`): the
generator never varies across retriever conditions *inside* one run — otherwise an accuracy
difference could be the model, not the retriever. It is read from the `--generator`
spec / `GENERATOR_MODEL` and recorded in every row and the run manifest, so each result is
attributable to exactly one generator.

## The model under test — configured vs. resolved id

Two model identities exist for one run, and the analysis layer needs both:

- **Configured** — the string you pass (`--generator anthropic:claude-haiku-4-5`). Lives on
  `generator.model`, known *before* any call. It may be a **moving alias**: `claude-haiku-4-5`
  resolves to whatever snapshot is current at call time.
- **Resolved** — the exact dated snapshot the API reports it actually ran
  (`claude-haiku-4-5-20251001`), returned *in the response* as `GenerationResult.model`.

Each result row records the **resolved** id (`generator_model_resolved`) so a verdict is
attributable to the precise snapshot — the reproducibility guarantee an alias can't give —
while `generator_model` keeps the requested string. (The analysis loader normalizes a
`generator_model_family` by stripping the snapshot date, so runs that logged the alias and
runs that logged the resolved id group as one condition; see `eval/analysis/load.py`.)

## Tokens are billed truth

The token counts here are the **billed** input/output tokens in the generator's own
tokenizer, from the provider's `usage`. This is exactly the unit the retrievers' offline
`context_tokens` proxy is *not* (see [the token-units rule](../../retrievers/README.md#the-token-units-rule-read-before-doing-any-token-math)).
The one unit-safe token decomposition — `input_tokens(retriever) − input_tokens(closed_book)`
for the same model + question — uses these billed numbers, never the proxy. A retriever's
own internal LLM cost (the `graph_sparqlgen` writer, the `semantic` judge) is logged
*separately* in `traversal_info` / `judge_details` and is **never** summed with these.

## Adding a provider

Same shape as adding a retriever or judge: implement the `Generator` protocol in a new
`eval/generate/<provider>_generator.py` (the only place its SDK is imported), register it in
`GENERATORS` in `eval/run_eval.py`. Nothing above the protocol changes.
