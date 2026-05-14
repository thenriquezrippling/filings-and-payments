"""Entry point: load env and start the Slack Bolt app."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

_REQUIRED_ENV_VARS = [
    "SLACK_BOT_TOKEN",
    "JIRA_BASE_URL",
    "JIRA_EMAIL",
    "JIRA_API_TOKEN",
    "ANTHROPIC_API_KEY",
]


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    missing = [v for v in _REQUIRED_ENV_VARS if not os.environ.get(v)]
    if missing:
        logger.info(
            "tax_ops_filing_bot: missing env vars %s — running in scaffold mode",
            missing,
        )
        return

    from tax_ops_filing_bot.slack.app import create_app

    app = create_app()

    app_token = os.environ.get("SLACK_APP_TOKEN")
    if app_token:
        logger.info("Starting in Socket Mode")
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        handler = SocketModeHandler(app, app_token)
        handler.start()
    else:
        logger.info("Starting HTTP server on port %s", os.environ.get("PORT", "3000"))
        app.start(port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
