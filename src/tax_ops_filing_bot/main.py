"""Entry point for the Tax Ops filing bot."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def main() -> None:
    load_dotenv()
    logging.basicConfig(level=logging.INFO)

    token = os.environ.get("SLACK_BOT_TOKEN", "")
    app_token = os.environ.get("SLACK_APP_TOKEN", "")

    if not token:
        logger.info(
            "SLACK_BOT_TOKEN not set — running in scaffold/mock mode. "
            "Set SLACK_BOT_TOKEN and SLACK_APP_TOKEN to start the Bolt app."
        )
        return

    from tax_ops_filing_bot.slack.app import create_app

    app = create_app()

    if app_token:
        from slack_bolt.adapter.socket_mode import SocketModeHandler

        logger.info("Starting Bolt app in Socket Mode")
        handler = SocketModeHandler(app, app_token)
        handler.start()
    else:
        logger.info("Starting Bolt app in HTTP mode on port 3000")
        app.start(port=int(os.environ.get("PORT", "3000")))


if __name__ == "__main__":
    main()
