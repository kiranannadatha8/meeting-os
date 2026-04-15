"""Action item extraction agent — Claude-backed LangGraph node.

Same retry/fallback-to-empty shape as the decision agent, with two
differences:

1. The prompt is injected with today's date so Claude can resolve relative
   due dates ("by Friday") to absolute ISO dates. Tests pass an explicit
   `reference_date`; production uses `date.today()`.
2. The Pydantic schema tolerates `owner=None` and `due_date=None`, and
   validates `due_date` as a real ISO date — not a free-text string — so
   the pipeline can safely persist it to the `action_items.due_date`
   column without further parsing.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, ValidationError

from app.agents._base import ActionItemData, PipelineState
from app.config import get_settings

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_TOKENS = 2048

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "action_item.md"


class _AnthropicClient(Protocol):
    messages: Any


class _ActionItemSchema(BaseModel):
    title: str
    owner: str | None = None
    due_date: date | None = None
    source_quote: str


def _load_prompt(today: date) -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8").replace("{today}", today.isoformat())


def _default_client() -> _AnthropicClient | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    from typing import cast

    from anthropic import Anthropic

    return cast(_AnthropicClient, Anthropic(api_key=settings.anthropic_api_key))


def _extract_text(message: Any) -> str:
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", "text") == "text":
            return getattr(block, "text", "")
    return ""


def _parse_items(raw: str) -> list[ActionItemData]:
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("expected a JSON array of action-item objects")
    validated = [_ActionItemSchema.model_validate(item) for item in payload]
    items: list[ActionItemData] = []
    for item in validated:
        items.append(
            cast(
                ActionItemData,
                {
                    "title": item.title,
                    "owner": item.owner,
                    "due_date": item.due_date.isoformat() if item.due_date else None,
                    "source_quote": item.source_quote,
                },
            )
        )
    return items


def extract_action_items(
    transcript: str,
    *,
    client: _AnthropicClient | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    reference_date: date | None = None,
) -> list[ActionItemData]:
    """Extract action items from `transcript`. Returns `[]` if empty, if no
    client is available, or if every attempt fails to produce valid output."""
    if not transcript.strip():
        return []
    if client is None:
        client = _default_client()
    if client is None:
        logger.info("Action agent: no Anthropic client available; returning empty list")
        return []

    today = reference_date or date.today()
    system_prompt = _load_prompt(today)

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": transcript}],
            )
            return _parse_items(_extract_text(message))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning(
                "Action parse failure on attempt %d/%d: %s", attempt, max_retries, exc
            )
        except Exception as exc:
            logger.warning(
                "Action API failure on attempt %d/%d: %s", attempt, max_retries, exc
            )

    logger.warning("Action agent exhausted %d retries; returning empty list", max_retries)
    return []


def action_node(
    state: PipelineState,
    *,
    client: _AnthropicClient | None = None,
) -> PipelineState:
    """LangGraph node adapter."""
    transcript = state.get("transcript", "")
    items = extract_action_items(transcript, client=client)
    return {"action_items": items}
