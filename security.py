"""Raid mode and security-related settings."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import err_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class SecurityCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        row = await self.bot.db.get_or_create_guild_row(member.guild.id)
        if not row.get("raid_mode"):
            return
        raw = row.get("security_config")
        try:
            cfg = json.loads(raw) if raw else {}
        except Exception:
            cfg = {}
        min_days = int(cfg.get("min_account_age_days", 7))
        age = (datetime.now(timezone.utc) - member.created_at).days
        if age < min_days:
            try:
                await member.kick(reason="Raid mode: account too new")
            except discord.HTTPException:
                pass

    @app_commands.command(name="raidmode", description="Kick new accounts on join (anti-raid)")
    @app_commands.describe(enabled="Enable raid mode")
    @app_commands.default_permissions(administrator=True)
    async def raidmode_cmd(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.update_guild_settings(
            interaction.guild.id, raid_mode=1 if enabled else 0
        )
        await interaction.response.send_message(
            embed=ok_embed(
                "Security",
                t(lang, "security.raid", state="on" if enabled else "off"),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="config", description="Set security JSON config (min_account_age_days)")
    @app_commands.describe(json_blob='Example: {"min_account_age_days": 14}')
    @app_commands.default_permissions(administrator=True)
    async def config_cmd(self, interaction: discord.Interaction, json_blob: str) -> None:
        assert interaction.guild
        try:
            data = json.loads(json_blob)
        except json.JSONDecodeError:
            await interaction.response.send_message(embed=err_embed("Error", "Invalid JSON."), ephemeral=True)
            return
        await self.bot.db.update_guild_settings(
            interaction.guild.id, security_config=json.dumps(data)
        )
        await interaction.response.send_message(embed=ok_embed("Config", "Saved."), ephemeral=True)

    @app_commands.command(name="set_channel", description="Default channel for bot notices (optional)")
    @app_commands.describe(channel="Text channel")
    @app_commands.default_permissions(administrator=True)
    async def set_channel_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id, bot_channel_id=channel.id
        )
        await interaction.response.send_message(
            embed=ok_embed("Bot channel", f"Set to {channel.mention}."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SecurityCog(bot))  # type: ignore[arg-type]
