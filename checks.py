"""Permission and ownership checks."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands

if TYPE_CHECKING:
    from bot.database import Database


def is_bot_owner(bot: discord.Client, user_id: int) -> bool:
    owners = getattr(bot, "owner_ids", None)
    if owners is None:
        return False
    return user_id in owners


async def interaction_owner_only(
    interaction: discord.Interaction,
) -> app_commands.AppCommandError | None:
    bot = interaction.client
    if not is_bot_owner(bot, interaction.user.id):
        return app_commands.CheckFailure("Owner only.")
    return None


def owner_only():
    async def predicate(interaction: discord.Interaction) -> bool:
        if not is_bot_owner(interaction.client, interaction.user.id):
            await interaction.response.send_message(
                "This command is restricted to the bot owner.", ephemeral=True
            )
            return False
        return True

    return app_commands.check(predicate)


def admin_or_whitelist(db: "Database"):
    async def predicate(interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            return False
        if is_bot_owner(interaction.client, interaction.user.id):
            return True
        if await db.is_whitelisted(interaction.user.id):
            return True
        member = interaction.user
        if isinstance(member, discord.Member) and member.guild_permissions.administrator:
            return True
        await interaction.response.send_message(
            "You need Administrator permission.", ephemeral=True
        )
        return False

    return app_commands.check(predicate)
