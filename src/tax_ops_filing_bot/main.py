"""Entry point. Phase 1: scaffold only — no Slack Bolt app startup."""

from __future__ import annotations

import logging

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)
    logger.info("tax_ops_filing_bot scaffold — Bolt app not started (Phase 1)")


if __name__ == "__main__":
    main()
