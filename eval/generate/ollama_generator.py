"""eval/generate/ollama_generator.py — Ollama adapter (concrete Generator strategy).

The ONLY module that imports the `ollama` SDK and knows its chat/response shapes. Everything
above the `Generator` protocol stays provider-neutral (see base.py); this is a sibling of
`anthropic_generator.py` and the same swap-point story. By project policy Ollama is *not* the
generator-under-test — it serves the mechanism roles: the `graph_sparqlgen` SPARQL writer and
the semantic judge (the latter only after its own kappa calibration), wired through
`registry.from_spec`.

Maps the four neutral dimensions onto Ollama's `/api/chat`:
  - message exchange  → messages=[{"role": "user", "content": prompt}]
  - system prompt     → a leading {"role": "system"} message (Ollama has a system role)
  - token usage       → response.prompt_eval_count / .eval_count (billed truth in Ollama's
                        own tokenizer; no prompt cache, so cache_* stay None)
  - tool usage        → neutral {name, description, parameters} → Ollama's OpenAI-style
                        {"type": "function", "function": {name, description, parameters}};
                        response tool calls → neutral `tool_calls`

`num_predict`/`temperature`/`seed` go in the `options` dict. Local determinism note: Ollama
runs locally, so beyond temperature 0 a fixed `seed` gives bit-stable decoding — tighter than
a hosted model's FP/batch jitter. `seed` is exposed here; pinning it across the roles is a
later step. Ollama is a localhost daemon (`ollama serve`), not an API key — a down server
surfaces as a connection error, caught per-question by the harness.
"""
from __future__ import annotations

import time

from eval.generate.base import GenerationResult

PROVIDER = "ollama"


def _to_ollama_tools(tools: list[dict]) -> list[dict]:
    """Neutral tool specs {name, description, parameters} → Ollama's function-tool shape.

    The neutral `parameters` (the cross-provider JSON-Schema term) is also what Ollama calls
    it, nested under `function`. Translating here keeps callers writing one neutral spec.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t.get("description", ""),
                "parameters": t.get("parameters", {"type": "object", "properties": {}}),
            },
        }
        for t in tools
    ]


def _attr(obj, key):
    """Read `key` off a pydantic response object or a dict (the SDK returns the former; a
    hermetic fake may use either) — None when absent, mirroring the additive-telemetry rule."""
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


class OllamaGenerator:
    """Ollama `/api/chat` behind the Generator protocol.

    `client` is injectable for hermetic tests; in normal use it is created lazily on the first
    `generate`, so importing this module needs neither the `ollama` package nor a running
    server (the same lazy pattern the Anthropic adapter and the retrievers use).
    """

    provider = PROVIDER

    def __init__(
        self,
        model: str,
        *,
        max_tokens: int = 1024,
        temperature: float | None = None,
        seed: int | None = None,
        host: str | None = None,
        client=None,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        # None ⇒ temperature left unsent → Ollama's default sampling; an explicit value (incl.
        # a deliberate 0.0) is honored and logged beside the model, like the Anthropic adapter.
        self.temperature = temperature
        self.seed = seed
        self.host = host  # None ⇒ the SDK default (http://localhost:11434, or OLLAMA_HOST)
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import ollama

            self._client = ollama.Client(host=self.host)
        return self._client

    def generate(self, prompt, *, system=None, tools=None) -> GenerationResult:
        client = self._ensure_client()
        messages: list[dict] = []
        if system is not None:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        options: dict = {"num_predict": self.max_tokens}
        if self.temperature is not None:
            options["temperature"] = self.temperature
        if self.seed is not None:
            options["seed"] = self.seed

        kwargs: dict = {"model": self.model, "messages": messages, "options": options}
        if tools:
            kwargs["tools"] = _to_ollama_tools(tools)

        start = time.perf_counter()
        resp = client.chat(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0

        msg = _attr(resp, "message")
        text = _attr(msg, "content") or ""
        tool_calls = [
            {"name": tc.function.name, "arguments": dict(tc.function.arguments), "id": None}
            for tc in (_attr(msg, "tool_calls") or [])  # Ollama assigns no tool-call id
        ]
        return GenerationResult(
            text=text,
            model=_attr(resp, "model") or self.model,  # echoes the tag (no dated snapshot)
            provider=self.provider,
            input_tokens=_attr(resp, "prompt_eval_count") or 0,
            output_tokens=_attr(resp, "eval_count") or 0,
            latency_ms=latency_ms,
            cache_read_input_tokens=None,  # Ollama has no prompt cache
            cache_creation_input_tokens=None,
            finish_reason=_attr(resp, "done_reason"),
            temperature=self.temperature,  # what we requested (None ⇒ provider default applied)
            tool_calls=tool_calls,
            raw_usage={  # Ollama's perf/usage telemetry (durations in ns), for audit
                "prompt_eval_count": _attr(resp, "prompt_eval_count"),
                "eval_count": _attr(resp, "eval_count"),
                "total_duration": _attr(resp, "total_duration"),
                "load_duration": _attr(resp, "load_duration"),
                "prompt_eval_duration": _attr(resp, "prompt_eval_duration"),
                "eval_duration": _attr(resp, "eval_duration"),
            },
        )
