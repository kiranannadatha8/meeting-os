"""Summary agent (T13).

Contract:
- Returns `{"tldr": str, "highlights": list[str]}` — validated
- `tldr` ≤100 words
- `highlights` has 3-7 entries
- Retries up to 3 times on parse failure; falls back to `empty_summary()`
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.agents._base import empty_summary
from app.agents.summary import DEFAULT_MODEL, extract_summary, summary_node


@dataclass
class _FakeTextBlock:
    text: str
    type: str = "text"


@dataclass
class _FakeMessage:
    content: list[_FakeTextBlock]


class _FakeMessagesAPI:
    def __init__(self, responses: list[str | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> _FakeMessage:
        self.calls.append(kwargs)
        nxt = self._responses.pop(0)
        if isinstance(nxt, Exception):
            raise nxt
        return _FakeMessage(content=[_FakeTextBlock(text=nxt)])


class _FakeAnthropicClient:
    def __init__(self, messages: _FakeMessagesAPI) -> None:
        self.messages = messages


_VALID_PAYLOAD = """{
    "tldr": "The team decided to adopt pgvector and ship the MVP on Railway.",
    "highlights": [
        "Adopted pgvector over a standalone vector DB",
        "Committed to Railway for the demo deploy",
        "Deferred Slack MCP to a post-MVP phase"
    ]
}"""


def test_extract_summary_returns_validated_summary() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_summary("transcript", client=client)

    assert out["tldr"].startswith("The team decided")
    assert len(out["highlights"]) == 3
    assert api.calls[0]["model"] == DEFAULT_MODEL


def test_extract_summary_rejects_tldr_over_100_words() -> None:
    long_tldr = " ".join(["word"] * 120)
    bad = f'{{"tldr": "{long_tldr}", "highlights": ["a", "b", "c"]}}'
    api = _FakeMessagesAPI(responses=[bad, bad, bad])
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert out == empty_summary()


def test_extract_summary_rejects_too_few_highlights() -> None:
    bad = '{"tldr": "ok", "highlights": ["only-one", "only-two"]}'
    api = _FakeMessagesAPI(responses=[bad, bad, bad])
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert out == empty_summary()


def test_extract_summary_rejects_too_many_highlights() -> None:
    too_many = '{"tldr": "ok", "highlights": ["1","2","3","4","5","6","7","8"]}'
    api = _FakeMessagesAPI(responses=[too_many, too_many, too_many])
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert out == empty_summary()


def test_extract_summary_retries_then_succeeds() -> None:
    api = _FakeMessagesAPI(responses=["not-json", _VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert len(out["highlights"]) == 3
    assert len(api.calls) == 2


def test_extract_summary_falls_back_to_empty_after_retry_exhaustion() -> None:
    api = _FakeMessagesAPI(responses=["bad", "bad", "bad"])
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert out == empty_summary()
    assert len(api.calls) == 3


def test_extract_summary_falls_back_on_api_exception() -> None:
    api = _FakeMessagesAPI(
        responses=[RuntimeError("429"), RuntimeError("500"), RuntimeError("boom")]
    )
    client = _FakeAnthropicClient(api)

    out = extract_summary("t", client=client, max_retries=3)

    assert out == empty_summary()


def test_extract_summary_empty_transcript_short_circuits() -> None:
    api = _FakeMessagesAPI(responses=[])
    client = _FakeAnthropicClient(api)

    out = extract_summary("", client=client)

    assert out == empty_summary()
    assert api.calls == []


def test_summary_node_matches_langgraph_agent_contract() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    update = summary_node({"meeting_id": "m", "transcript": "t"}, client=client)

    assert set(update.keys()) == {"summary"}
    assert update["summary"]["tldr"].startswith("The team decided")
    assert len(update["summary"]["highlights"]) == 3


def test_summary_node_returns_empty_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.summary._default_client", lambda: None)

    update = summary_node({"meeting_id": "m", "transcript": "hello"})

    assert update == {"summary": empty_summary()}
