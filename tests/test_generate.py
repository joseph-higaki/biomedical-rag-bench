"""Tests for eval/generate/ — the provider-neutral generator contract + Anthropic adapter.

Hermetic: no network, no API key, no `anthropic` package. The adapter takes an injected
client, so we feed a fake Messages response and assert it normalizes each
provider-specific shape onto the neutral `GenerationResult` — usage → billed tokens,
`tool_use` blocks → neutral `tool_calls`, neutral tool specs → the SDK's `input_schema`.
This mapping is silent-bug territory: a wrong field would corrupt every billed-token
number and every tool record in the eval without raising.
"""
from __future__ import annotations

from types import SimpleNamespace

from eval.generate.anthropic_generator import AnthropicGenerator, _to_anthropic_tools
from eval.generate.base import Generator


class _FakeUsage:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self):
        return dict(self.__dict__)


class _FakeMessages:
    def __init__(self, response):
        self._response = response
        self.received: dict | None = None  # captures the create() kwargs for assertions

    def create(self, **kwargs):
        self.received = kwargs
        return self._response


class _FakeClient:
    def __init__(self, response):
        self.messages = _FakeMessages(response)


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool(name, inp, id="toolu_1"):
    return SimpleNamespace(type="tool_use", name=name, input=inp, id=id)


def _resp(content, *, input_tokens=10, output_tokens=5):
    return SimpleNamespace(
        content=content,
        model="claude-haiku-4-5-20251001",
        stop_reason="end_turn",
        usage=_FakeUsage(
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def test_adapter_satisfies_generator_protocol():
    g = AnthropicGenerator("claude-haiku-4-5", client=_FakeClient(_resp([_text("hi")])))
    assert isinstance(g, Generator)  # runtime_checkable structural match
    assert g.provider == "anthropic"


def test_normalizes_text_and_billed_usage_and_routes_system():
    client = _FakeClient(_resp([_text("Warfarin.")], input_tokens=123, output_tokens=7))
    g = AnthropicGenerator("claude-haiku-4-5", client=client)
    r = g.generate("Which oral anticoagulant...?", system="Answer tersely.")
    assert r.text == "Warfarin."
    assert r.model == "claude-haiku-4-5-20251001"  # resolved id, not the bare alias
    assert r.provider == "anthropic"
    assert (r.input_tokens, r.output_tokens) == (123, 7)
    assert r.finish_reason == "end_turn"
    # system → the SDK's system= channel; prompt → a user message
    assert client.messages.received["system"] == "Answer tersely."
    assert client.messages.received["messages"][0] == {"role": "user", "content": "Which oral anticoagulant...?"}


def test_concatenates_text_blocks_and_skips_nontext():
    content = [_text("A"), _tool("x", {}), _text("B")]
    g = AnthropicGenerator("m", client=_FakeClient(_resp(content)))
    assert g.generate("q").text == "AB"


def test_tool_use_blocks_normalized_to_neutral_tool_calls():
    content = [_tool("run_sparql", {"query": "SELECT *"}, id="toolu_9")]
    g = AnthropicGenerator("m", client=_FakeClient(_resp(content)))
    assert g.generate("q").tool_calls == [
        {"name": "run_sparql", "arguments": {"query": "SELECT *"}, "id": "toolu_9"}
    ]


def test_neutral_tool_specs_translate_parameters_to_input_schema():
    schema = {"type": "object", "properties": {"query": {"type": "string"}}}
    out = _to_anthropic_tools([{"name": "run_sparql", "description": "Run SPARQL.", "parameters": schema}])
    assert out == [{"name": "run_sparql", "description": "Run SPARQL.", "input_schema": schema}]


def test_tools_kwarg_only_present_when_tools_offered():
    client = _FakeClient(_resp([_text("ok")]))
    g = AnthropicGenerator("m", client=client)
    g.generate("q", tools=[{"name": "t", "parameters": {"type": "object"}}])
    assert client.messages.received["tools"][0]["input_schema"] == {"type": "object"}
    g.generate("q2")  # no tools this time
    assert "tools" not in client.messages.received
