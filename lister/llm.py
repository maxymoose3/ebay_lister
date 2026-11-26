"""Thin wrapper around the Google Gen AI SDK (Gemini), used for photo ID and listing text."""
from __future__ import annotations

from typing import TypeVar

from google import genai
from google.genai import errors, types
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(RuntimeError):
    pass


def image(jpeg: bytes) -> types.Part:
    return types.Part.from_bytes(data=jpeg, mime_type="image/jpeg")


def explain(e: Exception) -> str:
    if isinstance(e, errors.APIError):
        if e.code in (401, 403):
            return "Gemini rejected the credentials. Check GEMINI_API_KEY in .env."
        if e.code == 429:
            return "Gemini rate limit reached. Wait a minute and retry."
        return f"Gemini API error {e.code}: {e.message}"
    if isinstance(e, ValueError) and "api key" in str(e).lower():
        return "No Gemini credentials found. Set GEMINI_API_KEY in .env."
    return f"Could not reach the Gemini API: {e}"


def structured(model: str, system: str, content: list | str, schema: type[T], *, thinking: str = "high") -> T:
    """One call that returns a validated `schema` instance."""
    try:
        # Keep a reference for the whole call: the SDK closes its HTTP client when the
        # Client object is garbage-collected, so `genai.Client().models...` can fail mid-call.
        with genai.Client() as client:
            resp = client.models.generate_content(
                model=model, contents=content,
                config=types.GenerateContentConfig(
                    system_instruction=system, response_mime_type="application/json", response_schema=schema,
                    thinking_config=types.ThinkingConfig(thinking_level=thinking),
                ),
            )
    except Exception as e:  # SDK raises APIError, ValueError (no key) or httpx errors
        raise LLMError(explain(e)) from e
    cand = resp.candidates[0] if resp.candidates else None
    reason = cand.finish_reason if cand else None
    if reason == types.FinishReason.MAX_TOKENS:
        raise LLMError("Gemini's answer was cut off; try fewer photos at once.")
    if reason in (types.FinishReason.SAFETY, types.FinishReason.PROHIBITED_CONTENT) or not cand:
        raise LLMError("Gemini declined this request.")
    if not isinstance(resp.parsed, schema):
        raise LLMError("Gemini returned no structured result.")
    return resp.parsed
