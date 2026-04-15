"""Summary agent — Claude-backed LangGraph node.

Produces a TL;DR (≤100 words) plus 3–7 highlight bullets. Retries on parse
failure up to `max_retries`, then falls back to `empty_summary()` so a
meeting with a flaky summary step still lands decisions and action items.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.agents._base import PipelineState, SummaryData, empty_summary
from app.config import get_settings

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_TOKENS = 2048

MAX_TLDR_WORDS = 100

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "summary.md"


class _AnthropicClient(Protocol):
    messages: Any


class _SummarySchema(BaseModel):
    tldr: str
    highlights: list[str] = Field(min_length=3, max_length=7)

    @field_validator("tldr")
    @classmethod
    def _enforce_word_count(cls, v: str) -> str:
        if len(v.split()) > MAX_TLDR_WORDS:
            raise ValueError(f"tldr must be at most {MAX_TLDR_WORDS} words")
        return v


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


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


def _parse_summary(raw: str) -> SummaryData:
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError("expected a JSON object")
    validated = _SummarySchema.model_validate(payload)
    return cast(SummaryData, {"tldr": validated.tldr, "highlights": list(validated.highlights)})


def extract_summary(
    transcript: str,
    *,
    client: _AnthropicClient | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> SummaryData:
    """Extract a summary. Falls back to `empty_summary()` on any failure path."""
    if not transcript.strip():
        return empty_summary()
    if client is None:
        client = _default_client()
    if client is None:
        logger.info("Summary agent: no Anthropic client available; returning empty summary")
        return empty_summary()

    system_prompt = _load_prompt()

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": transcript}],
            )
            return _parse_summary(_extract_text(message))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning(
                "Summary parse failure on attempt %d/%d: %s", attempt, max_retries, exc
            )
        except Exception as exc:
            logger.warning(
                "Summary API failure on attempt %d/%d: %s", attempt, max_retries, exc
            )

    logger.warning("Summary agent exhausted %d retries; returning empty summary", max_retries)
    return empty_summary()


def summary_node(
    state: PipelineState,
    *,
    client: _AnthropicClient | None = None,
) -> PipelineState:
    """LangGraph node adapter."""
    transcript = state.get("transcript", "")
    summary = extract_summary(transcript, client=client)
    return {"summary": summary}
