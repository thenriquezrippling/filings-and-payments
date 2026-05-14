"""Smoke tests for Phase 1 scaffolding."""

from __future__ import annotations

from pydantic import BaseModel

import tax_ops_filing_bot
from tax_ops_filing_bot.llm.wrapper import AnthropicClient
from tax_ops_filing_bot.main import main


class _DummyModel(BaseModel):
    x: int = 1


def test_package_version() -> None:
    assert tax_ops_filing_bot.__version__ == "0.1.0"


def test_main_callable() -> None:
    main()


def test_anthropic_client_init() -> None:
    client = AnthropicClient(api_key="test-key")
    assert client._model == "claude-sonnet-4-20250514"
