"""Status-based autorole."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import ok_embed

if TYPE_CHECKING:
    from bot.core import NotaBot


class AutoroleCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    @commands.Cog.listener()
    async def on_presence_update(self, before: discord.Member, after: discord.Member) -> None:
        row = await self.bot.db.get_or_create_guild_row(after.guild.id)
        if not row.get("autorole_enabled"):
            return
        role_id = row.get("autorole_role_id")
        trigger = (row.get("autorole_trigger") or "").lower()
        if not role_id or not trigger:
            return
        role = after.guild.get_role(int(role_id))
        if not role:
            return
        if row.get("autorole_ignore_offline") and str(after.status) == "offline":
            if role in after.roles:
                try:
                    await after.remove_roles(role, reason="autorole: offline")
                except discord.HTTPException:
                    pass
            return
        act = after.activity
        text = ""
        if act and isinstance(act, discord.CustomActivity):
            text = (act.name or "").lower()
        elif act:
            text = str(act.name).lower() if hasattr(act, "name") else ""
        custom = getattr(after, "activities", [])
        for a in custom:
            if isinstance(a, discord.CustomActivity) and a.name:
                text += " " + a.name.lower()
        if trigger in text.strip():
            if role not in after.roles:
                try:
                    await after.add_roles(role, reason="autorole: status")
                except discord.HTTPException:
                    pass
        else:
            if role in after.roles:
                try:
                    await after.remove_roles(role, reason="autorole: trigger removed")
                except discord.HTTPException:
                    pass

    setautorole = app_commands.Group(
        name="setautorole",
        description="Autorole based on custom status (manage roles)",
    )

    @setautorole.command(name="role", description="Role to grant when trigger matches")
    @app_commands.default_permissions(manage_roles=True)
    async def sa_role(self, interaction: discord.Interaction, role: discord.Role) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(interaction.guild.id, autorole_role_id=role.id)
        await interaction.response.send_message(embed=ok_embed("Autorole", f"Role: {role.mention}"), ephemeral=True)

    @setautorole.command(name="trigger", description="Substring to match in custom status")
    @app_commands.default_permissions(manage_roles=True)
    async def sa_trigger(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(interaction.guild.id, autorole_trigger=text[:100])
        await interaction.response.send_message(embed=ok_embed("Autorole", "Trigger saved."), ephemeral=True)

    @setautorole.command(name="toggle", description="Enable or disable autorole")
    @app_commands.default_permissions(manage_roles=True)
    async def sa_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id, autorole_enabled=1 if enabled else 0
        )
        await interaction.response.send_message(
            embed=ok_embed("Autorole", f"Enabled: **{enabled}**"),
            ephemeral=True,
        )

    @setautorole.command(name="offline", description="Ignore offline members (remove role)")
    @app_commands.default_permissions(manage_roles=True)
    async def sa_offline(self, interaction: discord.Interaction, ignore: bool) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id, autorole_ignore_offline=1 if ignore else 0
        )
        await interaction.response.send_message(embed=ok_embed("Autorole", "Updated."), ephemeral=True)

    @app_commands.command(name="setstatustrigger", description="Alias: set custom status trigger text")
    @app_commands.default_permissions(manage_roles=True)
    async def setstatustrigger_cmd(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(interaction.guild.id, autorole_trigger=text[:100])
        await interaction.response.send_message(embed=ok_embed("Autorole", "Trigger saved."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AutoroleCog(bot))  # type: ignore[arg-type]
