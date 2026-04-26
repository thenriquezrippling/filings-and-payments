"""Anthropic API wrapper — implemented in Phase 2."""

from __future__ import annotations

from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class AnthropicClient:
    """Thin client over the Anthropic Messages API with JSON-to-Pydantic parsing."""

    def __init__(self, api_key: str, *, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model

    def complete_json(self, _messages: list[dict[str, Any]], _response_model: type[T]) -> T:
        """Return structured output validated as ``response_model``."""
        raise NotImplementedError("AnthropicClient.complete_json is implemented in Phase 2")
