"""Smoke tests for Phase 1 scaffolding."""

from __future__ import annotations

import pytest
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


def test_anthropic_client_mock_mode() -> None:
    client = AnthropicClient(api_key="mock")
    assert client.is_mock
    result = client.complete_json([], _DummyModel)
    assert isinstance(result, _DummyModel)
    assert result.x == 1


def test_anthropic_client_real_mode_requires_key() -> None:
    client = AnthropicClient(api_key="sk-ant-real-key")
    assert not client.is_mock
