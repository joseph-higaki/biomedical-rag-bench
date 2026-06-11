"""eval/generate/registry.py — the provider registry + factory (the one construction point).

Every LLM role in the project is built through here: the generator-under-test (run_eval),
the `graph_sparqlgen` SPARQL writer, and the semantic judge. Centralizing construction is
what lets any of those three name a non-Anthropic provider — `ollama:qwen2.5-coder` for the
writer or judge — by adding a single registry entry, while the generator-under-test stays
Anthropic by policy. Adapters lazy-import their SDKs (see anthropic_generator.py), so
importing this module pulls in no provider package and needs no API key.

Spec grammar: ``provider:model`` (e.g. ``anthropic:claude-haiku-4-5``,
``ollama:qwen2.5-coder:7b`` — the model may itself contain colons; only the first segment is
the provider). A bare ``model`` with no provider segment is accepted only where a
``default_provider`` is supplied — the writer/judge, historically Anthropic-only, so their
existing bare-model config keeps working. The generator-under-test passes no default, so it
requires the explicit form and a run is never ambiguous about which provider produced it.
"""
from __future__ import annotations

from collections.abc import Callable

from eval.generate.anthropic_generator import AnthropicGenerator
from eval.generate.base import Generator

# provider name -> adapter constructor (the Strategy pattern; see base.py). The constructor's
# first positional arg is the model id; the rest are keyword options (temperature, max_tokens,
# …) each adapter maps onto its SDK. New providers (ollama, openai) are one entry each.
GENERATORS: dict[str, Callable[..., Generator]] = {
    AnthropicGenerator.provider: AnthropicGenerator,
}


def make_generator(provider: str, model: str, **kwargs) -> Generator:
    """Construct the adapter registered for `provider` with `model` + keyword options."""
    try:
        return GENERATORS[provider](model, **kwargs)
    except KeyError:
        raise SystemExit(
            f"unknown generator provider {provider!r}; registered: {', '.join(GENERATORS)}"
        )


def from_spec(spec: str, *, default_provider: str | None = None, **kwargs) -> Generator:
    """Build a generator from a `provider:model` spec.

    `default_provider` set ⇒ a bare `model` (no provider segment) resolves against it
    (back-compat for the writer/judge). Left None ⇒ the explicit `provider:model` form is
    required (the generator-under-test, so a run is always attributable to a named provider).
    """
    provider, sep, model = spec.partition(":")
    if not sep:  # no provider segment in the spec
        if default_provider is None:
            raise SystemExit(
                "generator spec must be 'provider:model' "
                f"(e.g. anthropic:claude-haiku-4-5); got {spec!r}"
            )
        provider, model = default_provider, spec
    return make_generator(provider, model, **kwargs)
