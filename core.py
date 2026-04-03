"""Discord client core for Nota Bot."""

from __future__ import annotations

import logging
import os
from typing import Any

import discord
from discord.ext import commands

from bot.database import Database

log = logging.getLogger("notabot")


class NotaBot(commands.Bot):
    """Main bot instance with shared database and owner configuration."""

    db: Database
    owner_ids: set[int]

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.voice_states = True
        intents.guilds = True
        intents.moderation = True
        intents.presences = True

        raw = os.getenv("BOT_OWNER_IDS", "")
        owner_ids = {int(x.strip()) for x in raw.split(",") if x.strip().isdigit()}

        super().__init__(
            command_prefix=commands.when_mentioned_or("nota."),
            intents=intents,
            help_command=None,
        )
        self.owner_ids = owner_ids
        self.db = Database()

    async def setup_hook(self) -> None:
        await self.db.connect()
        cogs = [
            "bot.cogs.settings",
            "bot.cogs.moderation",
            "bot.cogs.channels_roles",
            "bot.cogs.leveling",
            "bot.cogs.welcome",
            "bot.cogs.logs",
            "bot.cogs.masterlog",
            "bot.cogs.security",
            "bot.cogs.confession",
            "bot.cogs.autorole",
            "bot.cogs.utilities",
            "bot.cogs.economy",
            "bot.cogs.tickets",
            "bot.cogs.owner",
        ]
        for ext in cogs:
            try:
                await self.load_extension(ext)
                log.info("Loaded %s", ext)
            except Exception as e:
                log.exception("Failed %s: %s", ext, e)
        dev_guilds = os.getenv("DEV_GUILD_IDS", "")
        tree = self.tree
        if dev_guilds:
            for gid in dev_guilds.split(","):
                gid = gid.strip()
                if gid.isdigit():
                    g = discord.Object(id=int(gid))
                    tree.copy_global_to(guild=g)
                    await tree.sync(guild=g)
                    log.info("Synced commands to dev guild %s", gid)
        else:
            await tree.sync()
            log.info("Global command sync complete")

    async def on_ready(self) -> None:
        log.info("Logged in as %s (%s)", self.user, self.user.id if self.user else "?")
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="your server · /help"
            )
        )

    async def close(self) -> None:
        await self.db.close()
        await super().close()

    async def get_lang(self, guild: discord.Guild | None) -> str:
        if not guild:
            return "en"
        return await self.db.get_guild_language(guild.id)


def is_owner(user_id: int, bot: NotaBot) -> bool:
    return user_id in bot.owner_ids
