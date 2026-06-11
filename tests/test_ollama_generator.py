"""Tests for the Ollama adapter — the second concrete Generator strategy.

Hermetic: no network, no `ollama` package, no running daemon. The adapter takes an injected
client, so we feed a fake `chat()` response and assert it normalizes Ollama's shapes onto the
neutral `GenerationResult` — prompt_eval_count/eval_count → billed tokens, the system prompt
→ a leading system message, response tool calls → neutral `tool_calls`, neutral tool specs →
Ollama's function-tool shape. Same silent-bug surface as the Anthropic adapter test.
"""
from __future__ import annotations

from types import SimpleNamespace

from eval.generate.base import Generator
from eval.generate.ollama_generator import OllamaGenerator, _to_ollama_tools


class _FakeChatClient:
    def __init__(self, response):
        self._response = response
        self.received: dict | None = None  # captures chat() kwargs for assertions

    def chat(self, **kwargs):
        self.received = kwargs
        return self._response


def _toolcall(name, args):
    return SimpleNamespace(function=SimpleNamespace(name=name, arguments=args))


def _resp(text="", *, tool_calls=None, prompt_eval_count=10, eval_count=5,
          model="qwen2.5-coder:7b", done_reason="stop"):
    return SimpleNamespace(
        message=SimpleNamespace(content=text, tool_calls=tool_calls or []),
        model=model,
        done_reason=done_reason,
        prompt_eval_count=prompt_eval_count,
        eval_count=eval_count,
        total_duration=1, load_duration=1, prompt_eval_duration=1, eval_duration=1,
    )


def test_adapter_satisfies_generator_protocol():
    g = OllamaGenerator("qwen2.5-coder:7b", client=_FakeChatClient(_resp("hi")))
    assert isinstance(g, Generator)  # runtime_checkable structural match
    assert g.provider == "ollama"


def test_normalizes_text_and_billed_usage_and_routes_system():
    client = _FakeChatClient(_resp("Warfarin.", prompt_eval_count=123, eval_count=7))
    g = OllamaGenerator("qwen2.5-coder:7b", client=client)
    r = g.generate("Which oral anticoagulant...?", system="Answer tersely.")
    assert r.text == "Warfarin."
    assert r.model == "qwen2.5-coder:7b"
    assert r.provider == "ollama"
    assert (r.input_tokens, r.output_tokens) == (123, 7)
    assert r.finish_reason == "stop"
    assert r.cache_read_input_tokens is None  # Ollama has no prompt cache
    # system → a leading system message; prompt → a trailing user message
    assert client.received["messages"] == [
        {"role": "system", "content": "Answer tersely."},
        {"role": "user", "content": "Which oral anticoagulant...?"},
    ]


def test_no_system_message_when_system_absent():
    client = _FakeChatClient(_resp("ok"))
    OllamaGenerator("m", client=client).generate("q")
    assert client.received["messages"] == [{"role": "user", "content": "q"}]


def test_response_tool_calls_normalized_to_neutral_shape():
    client = _FakeChatClient(_resp(tool_calls=[_toolcall("run_sparql", {"query": "SELECT *"})]))
    g = OllamaGenerator("m", client=client)
    assert g.generate("q").tool_calls == [
        {"name": "run_sparql", "arguments": {"query": "SELECT *"}, "id": None}
    ]


def test_neutral_tool_specs_translate_to_ollama_function_shape():
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    out = _to_ollama_tools([{"name": "run_sparql", "description": "Run SPARQL.", "parameters": schema}])
    assert out == [
        {"type": "function",
         "function": {"name": "run_sparql", "description": "Run SPARQL.", "parameters": schema}}
    ]


def test_options_carry_num_predict_and_temperature_and_seed_only_when_set():
    # Default: no temperature/seed sent → Ollama's default sampling; num_predict always set.
    client = _FakeChatClient(_resp("ok"))
    OllamaGenerator("m", max_tokens=128, client=client).generate("q")
    assert client.received["options"] == {"num_predict": 128}
    # Pinned for a reproducible writer/judge: temperature + a local seed go into options.
    OllamaGenerator("m", temperature=0.0, seed=7, client=client).generate("q")
    assert client.received["options"] == {"num_predict": 1024, "temperature": 0.0, "seed": 7}


def test_tools_kwarg_only_present_when_tools_offered():
    client = _FakeChatClient(_resp("ok"))
    g = OllamaGenerator("m", client=client)
    g.generate("q", tools=[{"name": "t", "parameters": {"type": "object"}}])
    assert client.received["tools"][0]["function"]["parameters"] == {"type": "object"}
    g.generate("q2")  # no tools this time
    assert "tools" not in client.received
