"""Anthropic API wrapper with JSON-to-Pydantic parsing and a deterministic mock mode."""

from __future__ import annotations

import json
import logging
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


class AnthropicClient:
    """Thin client over the Anthropic Messages API with JSON-to-Pydantic parsing.

    When ``api_key`` is the sentinel ``"mock"`` (or empty), the client operates
    in **deterministic mode**: it skips the real API and returns a default
    instance of the requested ``response_model`` so the full workflow can be
    exercised without credentials.
    """

    MOCK_SENTINEL = "mock"

    def __init__(self, api_key: str, *, model: str = "claude-sonnet-4-20250514") -> None:
        self._api_key = api_key
        self._model = model
        self._is_mock = api_key in (self.MOCK_SENTINEL, "")

    @property
    def is_mock(self) -> bool:
        return self._is_mock

    def complete_json(self, messages: list[dict[str, Any]], response_model: type[T]) -> T:
        """Return structured output validated as ``response_model``.

        In mock mode a default instance is built from the model's field
        defaults (fields without defaults get placeholder strings / ints).
        """
        if self._is_mock:
            logger.info("AnthropicClient running in mock mode — returning defaults")
            return self._build_default(response_model)

        return self._call_api(messages, response_model)

    def _call_api(self, messages: list[dict[str, Any]], response_model: type[T]) -> T:
        """Real Anthropic API call — requires the ``anthropic`` package and a valid key."""
        import anthropic  # deferred so mock mode works without the package installed

        client = anthropic.Anthropic(api_key=self._api_key)

        system_msg = None
        api_messages: list[dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system_msg = m["content"]
            else:
                api_messages.append({"role": m["role"], "content": m["content"]})

        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 1024,
            "messages": api_messages,
        }
        if system_msg:
            kwargs["system"] = system_msg

        response = client.messages.create(**kwargs)
        raw_text = response.content[0].text
        data = json.loads(raw_text)
        return response_model.model_validate(data)

    @staticmethod
    def _build_default(response_model: type[T]) -> T:
        """Build a default instance by filling required fields with placeholders."""
        from pydantic_core import PydanticUndefined

        defaults: dict[str, Any] = {}
        for name, field_info in response_model.model_fields.items():
            if field_info.default is not PydanticUndefined:
                continue
            if field_info.default_factory is not None:
                continue
            annotation = field_info.annotation
            origin = getattr(annotation, "__origin__", None)
            if annotation is str or origin is str:
                defaults[name] = f"<{name}>"
            elif annotation is int:
                defaults[name] = 0
            else:
                defaults[name] = f"<{name}>"
        return response_model.model_validate(defaults)
