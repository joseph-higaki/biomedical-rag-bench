"""eval/generate/base.py — the provider-neutral generation contract (build step 5).

The **generator is the model under test**: it reads the retrieved context + the
question and produces the answer the judges score. The benchmark is generator-agnostic
by design (a hard constraint in .claude/CLAUDE.md and the root README) — `GENERATOR_MODEL`
is swapped *across* runs (a small/local model for iteration, a frontier hosted model for
the headline run) and held *fixed within* a run, logged with every result. So nothing
above this contract may know which provider is running: the harness depends only on the
`Generator` protocol and reads the same `GenerationResult` back, exactly as it depends
only on the `Retriever` and `Judge` protocols. This is the swap point for providers.

This is the **Strategy pattern**. This module is the neutral context; each adapter
(`anthropic_generator.py` now; an Ollama/OpenAI adapter later) is a concrete strategy
that owns *all* provider/SDK specifics and is the **only** place that imports the SDK.
Four things stay agnostic at this surface, and the adapter maps its SDK onto each:

  - **Message exchange** — a `prompt` in, an answer `text` out. The adapter builds the
    SDK's message envelope (Anthropic `messages=[{role, content}]`, etc.).
  - **System prompt** — a separate `system` channel, held constant by the harness.
    Providers with no system concept fold it into the prompt inside the adapter.
  - **Token usage** — normalized into `GenerationResult`'s billed counts below,
    whatever shape the SDK's `usage` object takes.
  - **Tool usage** — neutral JSON-schema tool specs in (`tools=`), normalized tool
    invocations out (`tool_calls`). The adapter translates to/from the SDK's tool format.

Adapters are swapped behind a registry (in `eval/run_eval.py`, beside the retriever and
judge registries). No orchestration framework (no LiteLLM): ~3 providers, hand-rolled.

Tokens here are the BILLED truth — real input/output tokens in the generator's own
tokenizer, from the provider's `usage` metadata. This is exactly the unit the retrievers'
offline `context_tokens` proxy is *not* (see retrievers/base.py on units): the one
unit-safe token decomposition, input_tokens(retriever) − input_tokens(closed_book) for
the same model + question, uses these billed numbers — never the proxy.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class GenerationResult:
    """What every generator returns. Field set is additive-only, like RetrievalResult.

    `model` is the *resolved* id the provider reports it actually ran (e.g. a bare alias
    resolves to a dated snapshot) — that resolved id is logged with every eval row, so a
    result is always attributable to the exact model. `provider` is a factorial factor.
    The token counts are billed truth (see module docstring). Cache/finish fields are
    optional because not every provider reports them; `raw_usage` keeps the provider's
    untouched usage object for audit.
    """

    text: str  # The answer string handed to the judge.
    model: str  # Resolved model id the provider reports — logged with every result.
    provider: str  # Which adapter produced it (factorial factor).
    input_tokens: int  # Billed prompt tokens, in the generator's own tokenizer.
    output_tokens: int  # Billed completion tokens.
    latency_ms: float  # Wall-clock of the generate call.
    # Optional, additive — populated when the provider reports them.
    cache_read_input_tokens: int | None = None
    cache_creation_input_tokens: int | None = None
    finish_reason: str | None = None
    # The sampling temperature the adapter *requested* for this call: a float when pinned,
    # or None when left unset (the provider's default sampling applied — Anthropic's is 1.0).
    # None is the honest record of "not pinned", distinct from an explicit 0.0; logged beside
    # the model at every interaction so a row says whether the answer was modal or sampled.
    temperature: float | None = None
    # Normalized tool invocations the model requested, provider-agnostic: each is
    # {"name": str, "arguments": dict, "id": str | None}. Empty when no tools were used
    # or offered. The adapter maps its SDK's tool-use blocks onto this shape, so the
    # harness can record tool usage as a factorial factor without knowing the provider.
    tool_calls: list[dict] = field(default_factory=list)
    raw_usage: dict = field(default_factory=dict)  # Provider's raw usage, for audit.


@runtime_checkable
class Generator(Protocol):
    """Structural contract: anything with `model` + `provider` + `generate(...)` matches.

    A Protocol, not a base class — the same choice as Retriever and Judge. `system` is an
    optional separate channel (the system prompt / framing) so the harness can hold it
    constant and decompose token cost cleanly; providers that have no system concept fold
    it into the prompt inside their adapter.
    """

    model: str
    provider: str

    def generate(
        self,
        prompt: str,
        *,
        system: str | None = None,
        tools: list[dict] | None = None,
    ) -> GenerationResult: ...
