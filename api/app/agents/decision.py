"""Decision extraction agent — Claude-backed LangGraph node.

`extract_decisions` is the transport-agnostic core: it calls the Anthropic
client, validates the JSON response against a Pydantic schema, retries on
transient or parse failure, and falls back to an empty list after exhausting
the retry budget. `decision_node` is the LangGraph adapter.

The Anthropic client is injectable so unit tests never hit the network. In
production, `_default_client()` returns a real client when
`anthropic_api_key` is configured; otherwise it returns `None` and the node
silently produces an empty list — preferable to crashing the whole pipeline
on a missing credential.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Protocol, cast

from pydantic import BaseModel, ValidationError

from app.agents._base import DecisionData, PipelineState
from app.config import get_settings

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_RETRIES = 3
DEFAULT_MAX_TOKENS = 2048

logger = logging.getLogger(__name__)

_PROMPT_PATH = Path(__file__).parent / "prompts" / "decision.md"


class _AnthropicClient(Protocol):
    """Structural type matching the surface we use of `anthropic.Anthropic`."""

    messages: Any


class _DecisionSchema(BaseModel):
    title: str
    rationale: str
    source_quote: str


def _load_prompt() -> str:
    return _PROMPT_PATH.read_text(encoding="utf-8")


def _default_client() -> _AnthropicClient | None:
    settings = get_settings()
    if not settings.anthropic_api_key:
        return None
    from typing import cast

    from anthropic import Anthropic  # local import keeps unit tests offline

    return cast(_AnthropicClient, Anthropic(api_key=settings.anthropic_api_key))


def _extract_text(message: Any) -> str:
    for block in getattr(message, "content", []) or []:
        if getattr(block, "type", "text") == "text":
            return getattr(block, "text", "")
    return ""


def _parse_decisions(raw: str) -> list[DecisionData]:
    """Parse + validate one model response. Raises on any failure."""
    payload = json.loads(raw)
    if not isinstance(payload, list):
        raise ValueError("expected a JSON array of decision objects")
    validated = [_DecisionSchema.model_validate(item) for item in payload]
    return [cast(DecisionData, item.model_dump()) for item in validated]


def extract_decisions(
    transcript: str,
    *,
    client: _AnthropicClient | None = None,
    model: str = DEFAULT_MODEL,
    max_retries: int = DEFAULT_MAX_RETRIES,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> list[DecisionData]:
    """Extract decisions from `transcript`. Returns `[]` if empty, if no
    client is available, or if every attempt fails to produce valid output."""
    if not transcript.strip():
        return []
    if client is None:
        client = _default_client()
    if client is None:
        logger.info("Decision agent: no Anthropic client available; returning empty list")
        return []

    system_prompt = _load_prompt()

    for attempt in range(1, max_retries + 1):
        try:
            message = client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system_prompt,
                messages=[{"role": "user", "content": transcript}],
            )
            return _parse_decisions(_extract_text(message))
        except (json.JSONDecodeError, ValidationError, ValueError) as exc:
            logger.warning(
                "Decision parse failure on attempt %d/%d: %s", attempt, max_retries, exc
            )
        except Exception as exc:  # network / rate-limit / SDK errors
            logger.warning(
                "Decision API failure on attempt %d/%d: %s", attempt, max_retries, exc
            )

    logger.warning("Decision agent exhausted %d retries; returning empty list", max_retries)
    return []


def decision_node(
    state: PipelineState,
    *,
    client: _AnthropicClient | None = None,
) -> PipelineState:
    """LangGraph node adapter. `client` param is for tests; production uses the default."""
    transcript = state.get("transcript", "")
    decisions = extract_decisions(transcript, client=client)
    return {"decisions": decisions}
