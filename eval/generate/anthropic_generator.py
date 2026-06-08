"""eval/generate/anthropic_generator.py — Anthropic adapter (concrete Generator strategy).

The ONLY module that imports the `anthropic` SDK and knows its message/usage/tool shapes.
Everything above the `Generator` protocol stays provider-neutral (see base.py). Adding an
Ollama or OpenAI generator is a sibling adapter + one registry entry — nothing else
changes, the same swap-point story as the retrievers.

Maps the four neutral dimensions onto the Anthropic Messages API:
  - message exchange  → messages=[{"role": "user", "content": prompt}]
  - system prompt     → the top-level `system=` parameter
  - token usage       → response.usage.{input,output,cache_*}_tokens  (billed truth)
  - tool usage        → neutral {name, description, parameters} → Anthropic's
                        {name, description, input_schema}; `tool_use` response blocks →
                        neutral `tool_calls`

No `effort`/`thinking` params: Haiku rejects `effort`, and the model under test should
answer plainly, so the call is a bare completion. Credentials and the model id live only
here — the harness never names a provider.
"""
from __future__ import annotations

import time
from pathlib import Path

from eval.generate.base import GenerationResult

PROVIDER = "anthropic"
# secrets/.env (gitignored) is the dev fallback for ANTHROPIC_API_KEY; repo-root relative.
_SECRETS_ENV = Path(__file__).resolve().parents[2] / "secrets" / ".env"


def _to_anthropic_tools(tools: list[dict]) -> list[dict]:
    """Neutral tool specs {name, description, parameters} → Anthropic {…, input_schema}.

    The neutral shape uses `parameters` for the JSON Schema (the cross-provider term);
    Anthropic calls it `input_schema`. Translating here — rather than passing through —
    is the point: the caller writes one tool spec, each adapter speaks its SDK's dialect.
    """
    return [
        {
            "name": t["name"],
            "description": t.get("description", ""),
            "input_schema": t.get("parameters", {"type": "object", "properties": {}}),
        }
        for t in tools
    ]


class AnthropicGenerator:
    """Anthropic Messages API behind the Generator protocol.

    `client` is injectable for hermetic tests; in normal use it is created lazily on the
    first `generate`, so importing this module needs neither the `anthropic` package nor
    an API key (the same lazy-import pattern the retrievers use for httpx/chromadb).
    """

    provider = PROVIDER

    def __init__(self, model: str, *, max_tokens: int = 1024, max_retries: int = 5, client=None) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self._client = client

    def _ensure_client(self):
        if self._client is None:
            import anthropic
            from dotenv import load_dotenv

            load_dotenv(_SECRETS_ENV, override=False)  # real env vars win
            # The SDK retries transient failures (429 / 5xx / overloaded) with exponential
            # backoff; the default of 2 is too few for a long batch under sustained load —
            # one un-recovered blip would otherwise surface as an isolated error row. Any
            # error that survives all retries is still caught per-question in the harness.
            self._client = anthropic.Anthropic(max_retries=self.max_retries)  # reads ANTHROPIC_API_KEY
        return self._client

    def generate(self, prompt, *, system=None, tools=None) -> GenerationResult:
        client = self._ensure_client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system is not None:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = _to_anthropic_tools(tools)

        start = time.perf_counter()
        resp = client.messages.create(**kwargs)
        latency_ms = (time.perf_counter() - start) * 1000.0

        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        tool_calls = [
            {"name": b.name, "arguments": b.input, "id": getattr(b, "id", None)}
            for b in resp.content
            if getattr(b, "type", None) == "tool_use"
        ]
        u = resp.usage
        return GenerationResult(
            text=text,
            model=resp.model,  # resolved id (a bare alias resolves to a dated snapshot)
            provider=self.provider,
            input_tokens=u.input_tokens,
            output_tokens=u.output_tokens,
            latency_ms=latency_ms,
            cache_read_input_tokens=getattr(u, "cache_read_input_tokens", None),
            cache_creation_input_tokens=getattr(u, "cache_creation_input_tokens", None),
            finish_reason=resp.stop_reason,
            tool_calls=tool_calls,
            raw_usage=u.model_dump() if hasattr(u, "model_dump") else {},
        )
