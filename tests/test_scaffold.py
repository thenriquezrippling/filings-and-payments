"""Smoke tests for scaffolding and package structure."""

from __future__ import annotations

import tax_ops_filing_bot
from tax_ops_filing_bot.main import main


def test_package_version() -> None:
    assert tax_ops_filing_bot.__version__ == "0.1.0"


def test_main_callable() -> None:
    """main() should run without error in scaffold mode (missing env vars)."""
    main()


def test_package_imports() -> None:
    """All subpackages should be importable."""
    import tax_ops_filing_bot.models  # noqa: F401
    import tax_ops_filing_bot.llm  # noqa: F401
    import tax_ops_filing_bot.jira  # noqa: F401
    import tax_ops_filing_bot.services  # noqa: F401
    import tax_ops_filing_bot.slack  # noqa: F401

    assert tax_ops_filing_bot.models.FilingIssueDraft is not None
    assert tax_ops_filing_bot.llm.AnthropicClient is not None
    assert tax_ops_filing_bot.jira.JiraClient is not None
    assert tax_ops_filing_bot.services.IntakeService is not None
    assert tax_ops_filing_bot.services.SyncService is not None
