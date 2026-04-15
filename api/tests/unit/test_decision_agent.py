"""Decision extraction agent (T11).

Prompts Claude Sonnet 4.6 for structured decisions with Pydantic validation,
retries up to 3 times on parse failure, then falls back to an empty list.
Tests inject a fake Anthropic client so no network calls fire.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents.decision import DEFAULT_MODEL, decision_node, extract_decisions


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]


class _FakeMessagesAPI:
    """Canned-response Anthropic `messages` API. `responses` is a list where
    each element is either a JSON string (returned as a single text block) or
    an Exception (raised on that call)."""

    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeMessagesAPI: no canned responses left")
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _FakeMessage(content=[_FakeTextBlock(text=nxt)])


class _FakeAnthropicClient:
    def __init__(self, messages: _FakeMessagesAPI) -> None:
        self.messages = messages


_VALID_PAYLOAD = """[
    {"title": "Adopt pgvector", "rationale": "Native to Postgres",
     "source_quote": "let us use pgvector"},
    {"title": "Ship to Railway", "rationale": "fast to deploy",
     "source_quote": "we will ship on Railway"}
]"""


def test_extract_decisions_returns_validated_decisions() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_decisions("some transcript", client=client)

    assert len(out) == 2
    assert out[0] == {
        "title": "Adopt pgvector",
        "rationale": "Native to Postgres",
        "source_quote": "let us use pgvector",
    }
    assert api.calls[0]["model"] == DEFAULT_MODEL


def test_extract_decisions_retries_then_succeeds_on_parse_failure() -> None:
    api = _FakeMessagesAPI(responses=["not-json-at-all", _VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_decisions("transcript", client=client, max_retries=3)

    assert len(out) == 2
    assert len(api.calls) == 2


def test_extract_decisions_falls_back_to_empty_list_after_max_retries() -> None:
    api = _FakeMessagesAPI(responses=["garbage", "still-garbage", "nope"])
    client = _FakeAnthropicClient(api)

    out = extract_decisions("transcript", client=client, max_retries=3)

    assert out == []
    assert len(api.calls) == 3


def test_extract_decisions_falls_back_on_api_exception() -> None:
    api = _FakeMessagesAPI(
        responses=[RuntimeError("rate limited"), RuntimeError("still flaky"), RuntimeError("nope")]
    )
    client = _FakeAnthropicClient(api)

    out = extract_decisions("transcript", client=client, max_retries=3)

    assert out == []
    assert len(api.calls) == 3


def test_extract_decisions_rejects_missing_required_fields() -> None:
    partial = '[{"title": "only a title"}]'
    api = _FakeMessagesAPI(responses=[partial, partial, partial])
    client = _FakeAnthropicClient(api)

    out = extract_decisions("transcript", client=client, max_retries=3)

    assert out == []


def test_extract_decisions_empty_transcript_short_circuits() -> None:
    api = _FakeMessagesAPI(responses=[])
    client = _FakeAnthropicClient(api)

    out = extract_decisions("", client=client)

    assert out == []
    assert api.calls == []


def test_decision_node_matches_langgraph_agent_contract() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    update = decision_node({"meeting_id": "m1", "transcript": "t"}, client=client)

    assert set(update.keys()) == {"decisions"}
    assert len(update["decisions"]) == 2


def test_decision_node_returns_empty_when_api_key_missing(monkeypatch) -> None:
    """With no credentials configured, the node silently returns an empty list
    rather than crashing the whole meeting pipeline."""
    monkeypatch.setattr("app.agents.decision._default_client", lambda: None)

    update = decision_node({"meeting_id": "m1", "transcript": "hello"})

    assert update == {"decisions": []}
