"""Entry point — load environment and start Nota Bot."""

from __future__ import annotations

import logging
import os
import sys

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("notabot.main")


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        log.error("Set DISCORD_TOKEN in .env (see .env.example).")
        sys.exit(1)
    owners = os.getenv("BOT_OWNER_IDS", "")
    if not owners.strip():
        log.warning("BOT_OWNER_IDS is empty — owner-only commands will be unusable.")

    from bot.core import NotaBot

    bot = NotaBot()
    bot.run(token)


if __name__ == "__main__":
    main()
