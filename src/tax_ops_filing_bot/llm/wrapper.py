"""Anthropic API wrapper with structured JSON output."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from tax_ops_filing_bot.llm.prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_RETRIES = 2


class LLMExtractionError(Exception):
    """Raised when the LLM response cannot be parsed into the target model."""


class AnthropicClient:
    """Thin client over the Anthropic Messages API with JSON-to-Pydantic parsing."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str = "claude-sonnet-4-20250514",
        max_tokens: int = 2048,
    ) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens

    def complete_json(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        *,
        system: str | None = None,
    ) -> T:
        """Send messages to Claude and parse the response as ``response_model``.

        Retries up to ``_MAX_RETRIES`` times on validation failures, feeding
        the error back to the model for self-correction.
        """
        system_text = system or SYSTEM_PROMPT
        working_messages = list(messages)

        last_error: Exception | None = None
        for attempt in range(1 + _MAX_RETRIES):
            raw = self._call_api(working_messages, system_text)
            try:
                return self._parse_response(raw, response_model)
            except (json.JSONDecodeError, ValidationError, LLMExtractionError) as exc:
                last_error = exc
                logger.warning(
                    "Attempt %d/%d: parse failed — %s",
                    attempt + 1,
                    1 + _MAX_RETRIES,
                    exc,
                )
                working_messages.append({"role": "assistant", "content": raw})
                working_messages.append({
                    "role": "user",
                    "content": (
                        f"Your previous response could not be parsed: {exc}\n"
                        "Please return ONLY valid JSON matching the schema."
                    ),
                })

        raise LLMExtractionError(
            f"Failed to parse response after {1 + _MAX_RETRIES} attempts"
        ) from last_error

    def _call_api(
        self,
        messages: list[dict[str, Any]],
        system: str,
    ) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=system,
            messages=messages,
        )
        block = response.content[0]
        if block.type != "text":
            raise LLMExtractionError(f"Unexpected content block type: {block.type}")
        return block.text

    @staticmethod
    def _parse_response(raw: str, model: type[T]) -> T:
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # drop opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines)

        data = json.loads(text)
        return model.model_validate(data)
