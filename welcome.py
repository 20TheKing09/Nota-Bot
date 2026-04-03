"""Welcome and goodbye cards (embed-based)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import WELCOME, info_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class WelcomeCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    welcome = app_commands.Group(
        name="welcome",
        description="Configure welcome / goodbye messages (manage server)",
    )

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        row = await self.bot.db.get_or_create_guild_row(member.guild.id)
        if not row.get("welcome_enabled"):
            return
        raw = row.get("welcome_channel_ids")
        if not raw:
            return
        try:
            ids = json.loads(raw)
        except Exception:
            ids = []
        msg = row.get("welcome_message") or "Welcome to **{guild}**, {user}!"
        color = row.get("welcome_color") or WELCOME
        text = msg.format(user=member.mention, guild=member.guild.name, name=member.display_name)
        embed = discord.Embed(
            title="Welcome",
            description=text,
            color=color if isinstance(color, int) else WELCOME,
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(text=f"Member #{member.guild.member_count}")
        for cid in ids[:5]:
            ch = member.guild.get_channel(int(cid))
            if isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(embed=embed)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        row = await self.bot.db.get_or_create_guild_row(member.guild.id)
        if not row.get("goodbye_enabled"):
            return
        raw = row.get("goodbye_channel_ids") or row.get("welcome_channel_ids")
        if not raw:
            return
        try:
            ids = json.loads(raw)
        except Exception:
            ids = []
        msg = row.get("goodbye_message") or "**{name}** left the server."
        text = msg.format(user=member.mention, guild=member.guild.name, name=member.display_name)
        embed = discord.Embed(title="Goodbye", description=text, color=discord.Color.dark_gray())
        for cid in ids[:5]:
            ch = member.guild.get_channel(int(cid))
            if isinstance(ch, discord.TextChannel):
                try:
                    await ch.send(embed=embed)
                except discord.HTTPException:
                    pass

    @welcome.command(name="set-salon", description="Set channels for welcome/goodbye (comma-separated IDs)")
    @app_commands.describe(
        welcome_channels="Channel IDs for welcome (comma-separated)",
        goodbye_channels="Channel IDs for goodbye (optional, defaults to welcome)",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_set_salon(
        self,
        interaction: discord.Interaction,
        welcome_channels: str,
        goodbye_channels: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        w_ids = [int(x.strip()) for x in welcome_channels.split(",") if x.strip().isdigit()]
        g_ids = (
            [int(x.strip()) for x in goodbye_channels.split(",") if x.strip().isdigit()]
            if goodbye_channels
            else w_ids
        )
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            welcome_channel_ids=json.dumps(w_ids),
            goodbye_channel_ids=json.dumps(g_ids),
        )
        await interaction.response.send_message(
            embed=ok_embed("Welcome", f"Welcome channels: `{w_ids}`\nGoodbye channels: `{g_ids}`"),
            ephemeral=True,
        )

    @welcome.command(name="toggle", description="Enable welcome and/or goodbye")
    @app_commands.describe(welcome="Welcome on", goodbye="Goodbye on")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_toggle(
        self,
        interaction: discord.Interaction,
        welcome: bool,
        goodbye: bool,
    ) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            welcome_enabled=1 if welcome else 0,
            goodbye_enabled=1 if goodbye else 0,
        )
        await interaction.response.send_message(
            embed=ok_embed("Welcome", f"Welcome: **{welcome}** · Goodbye: **{goodbye}**"),
            ephemeral=True,
        )

    @welcome.command(name="message", description="Set welcome and goodbye message templates")
    @app_commands.describe(
        welcome="Use {user} {guild} {name}",
        goodbye="Goodbye template",
    )
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_message(
        self,
        interaction: discord.Interaction,
        welcome: str,
        goodbye: str | None = None,
    ) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            welcome_message=welcome,
            goodbye_message=goodbye or "**{name}** left us.",
        )
        await interaction.response.send_message(embed=ok_embed("Welcome", "Messages updated."), ephemeral=True)

    @welcome.command(name="view", description="View current welcome configuration")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        row = await self.bot.db.get_or_create_guild_row(interaction.guild.id)
        w_on = "on" if row.get("welcome_enabled") else "off"
        g_on = "on" if row.get("goodbye_enabled") else "off"
        ch = row.get("welcome_channel_ids") or "—"
        await interaction.response.send_message(
            embed=info_embed(
                "Config",
                t(lang, "welcome.view", on=w_on, off=g_on, ch=str(ch)),
            ),
            ephemeral=True,
        )

    @welcome.command(name="test", description="Send a test welcome embed here")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_test(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and interaction.user
        row = await self.bot.db.get_or_create_guild_row(interaction.guild.id)
        msg = row.get("welcome_message") or "Welcome to **{guild}**, {user}!"
        color = row.get("welcome_color") or WELCOME
        text = msg.format(
            user=interaction.user.mention,
            guild=interaction.guild.name,
            name=interaction.user.display_name,
        )
        embed = discord.Embed(title="Welcome (test)", description=text, color=color if isinstance(color, int) else WELCOME)
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @welcome.command(name="reset", description="Reset welcome/goodbye configuration")
    @app_commands.default_permissions(manage_guild=True)
    async def welcome_reset(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            welcome_enabled=0,
            goodbye_enabled=0,
            welcome_channel_ids=None,
            goodbye_channel_ids=None,
            welcome_message=None,
            goodbye_message=None,
            welcome_color=None,
        )
        await interaction.response.send_message(embed=ok_embed("Welcome", "Reset."), ephemeral=True)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(WelcomeCog(bot))  # type: ignore[arg-type]
