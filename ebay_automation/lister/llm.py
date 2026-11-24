"""Thin wrapper around the Anthropic SDK."""
from __future__ import annotations

from typing import TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)
# If a request is declined by a safety classifier, let the API retry it on another model.
FALLBACK = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}


class LLMError(RuntimeError):
    pass


def client() -> anthropic.Anthropic:
    return anthropic.Anthropic()


def explain(e: Exception) -> str:
    if isinstance(e, anthropic.AuthenticationError):
        return "Claude rejected the credentials. Check ANTHROPIC_API_KEY in .env."
    if isinstance(e, anthropic.RateLimitError):
        return "Claude rate limit reached. Wait a minute and retry."
    if isinstance(e, anthropic.APIStatusError):
        return f"Claude API error {e.status_code}: {e.message}"
    if isinstance(e, anthropic.APIConnectionError):
        return "Could not reach the Claude API."
    if isinstance(e, anthropic.AnthropicError) or "authentication method" in str(e):
        return "No Claude credentials found. Set ANTHROPIC_API_KEY in .env."
    return str(e)


def check_stop(resp) -> None:
    if resp.stop_reason == "refusal":
        raise LLMError("Claude declined this request.")
    if resp.stop_reason == "max_tokens":
        raise LLMError("Claude's answer was cut off; try fewer photos at once.")


def structured(model: str, system: str, content, schema: type[T], *, effort: str, max_tokens: int = 32000) -> T:
    """One call that returns a validated `schema` instance."""
    try:
        with client().beta.messages.stream(
            model=model, max_tokens=max_tokens, system=system,
            messages=[{"role": "user", "content": content}],
            output_config={"effort": effort}, output_format=schema, **FALLBACK,
        ) as stream:
            resp = stream.get_final_message()
    except (anthropic.AnthropicError, TypeError) as e:
        raise LLMError(explain(e)) from e
    check_stop(resp)
    if resp.parsed_output is None:
        raise LLMError("Claude returned no structured result.")
    return resp.parsed_output
