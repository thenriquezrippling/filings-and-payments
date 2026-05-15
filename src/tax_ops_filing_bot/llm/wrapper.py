"""Anthropic API wrapper with structured JSON output."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

import anthropic
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


class AnthropicClient:
    """Thin client over the Anthropic Messages API with JSON-to-Pydantic parsing."""

    def __init__(self, api_key: str, *, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)

    def complete_json(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        *,
        system: str | None = None,
        max_tokens: int = 4096,
    ) -> T:
        """Send messages to the Anthropic API and parse the response as ``response_model``."""
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": messages,
        }
        if system is not None:
            kwargs["system"] = system

        logger.info("Calling Anthropic model=%s", self._model)
        response = self._client.messages.create(**kwargs)

        raw_text = response.content[0].text
        raw_text = raw_text.strip()
        if raw_text.startswith("```"):
            raw_text = raw_text.split("\n", 1)[1]
            raw_text = raw_text.rsplit("```", 1)[0]
            raw_text = raw_text.strip()

        parsed = json.loads(raw_text)
        return response_model.model_validate(parsed)
