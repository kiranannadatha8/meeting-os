"""Action item extraction agent (T12).

Contract:
- Returns `list[ActionItemData]` with `title`, `owner`, `due_date`, `source_quote`
- `owner` is a free-text name or `None` when unspecified — never hallucinated
- `due_date` is an ISO date string (YYYY-MM-DD) or `None`
- Retries up to 3 times on parse failure, then falls back to `[]`

Date resolution itself (e.g. "by Friday" → 2026-04-17) is Claude's job given a
reference date injected into the prompt; the agent is responsible for passing
that reference and for validating whatever Claude returns.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from app.agents.action_item import DEFAULT_MODEL, action_node, extract_action_items


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


_VALID_PAYLOAD = """[
    {"title": "Write ADR for pgvector",
     "owner": "Kiran",
     "due_date": "2026-04-17",
     "source_quote": "Kiran will write the ADR by Friday"},
    {"title": "Audit auth flow",
     "owner": "the infra team",
     "due_date": null,
     "source_quote": "infra team should audit auth"},
    {"title": "Update the onboarding doc",
     "owner": null,
     "due_date": null,
     "source_quote": "someone should update onboarding"}
]"""


def test_extract_action_items_returns_validated_items() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("transcript", client=client, reference_date=date(2026, 4, 14))

    assert len(out) == 3
    assert out[0] == {
        "title": "Write ADR for pgvector",
        "owner": "Kiran",
        "due_date": "2026-04-17",
        "source_quote": "Kiran will write the ADR by Friday",
    }
    assert api.calls[0]["model"] == DEFAULT_MODEL


def test_extract_action_items_preserves_none_owner_and_none_due_date() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("transcript", client=client, reference_date=date(2026, 4, 14))

    # The second item has an owner but no due date
    assert out[1]["owner"] == "the infra team"
    assert out[1]["due_date"] is None
    # The third item has neither — None must round-trip as None, not ""
    assert out[2]["owner"] is None
    assert out[2]["due_date"] is None


def test_extract_action_items_injects_reference_date_into_prompt() -> None:
    api = _FakeMessagesAPI(responses=["[]"])
    client = _FakeAnthropicClient(api)

    extract_action_items("t", client=client, reference_date=date(2026, 4, 14))

    system_prompt = api.calls[0]["system"]
    assert "2026-04-14" in system_prompt


def test_extract_action_items_rejects_invalid_due_date_string() -> None:
    bad = '[{"title": "x", "owner": null, "due_date": "next Friday", "source_quote": "q"}]'
    api = _FakeMessagesAPI(responses=[bad, bad, bad])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("t", client=client, max_retries=3)

    assert out == []


def test_extract_action_items_retries_then_succeeds() -> None:
    api = _FakeMessagesAPI(responses=["not-json", _VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("t", client=client, max_retries=3)

    assert len(out) == 3
    assert len(api.calls) == 2


def test_extract_action_items_falls_back_to_empty_after_retry_exhaustion() -> None:
    api = _FakeMessagesAPI(responses=["garbage", "still-bad", "nope"])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("t", client=client, max_retries=3)

    assert out == []
    assert len(api.calls) == 3


def test_extract_action_items_falls_back_on_api_exception() -> None:
    api = _FakeMessagesAPI(
        responses=[RuntimeError("429"), RuntimeError("500"), RuntimeError("boom")]
    )
    client = _FakeAnthropicClient(api)

    out = extract_action_items("t", client=client, max_retries=3)

    assert out == []


def test_extract_action_items_empty_transcript_short_circuits() -> None:
    api = _FakeMessagesAPI(responses=[])
    client = _FakeAnthropicClient(api)

    out = extract_action_items("", client=client)

    assert out == []
    assert api.calls == []


def test_action_node_matches_langgraph_agent_contract() -> None:
    api = _FakeMessagesAPI(responses=[_VALID_PAYLOAD])
    client = _FakeAnthropicClient(api)

    update = action_node({"meeting_id": "m", "transcript": "t"}, client=client)

    assert set(update.keys()) == {"action_items"}
    assert len(update["action_items"]) == 3


def test_action_node_returns_empty_when_api_key_missing(monkeypatch) -> None:
    monkeypatch.setattr("app.agents.action_item._default_client", lambda: None)

    update = action_node({"meeting_id": "m", "transcript": "hello"})

    assert update == {"action_items": []}
