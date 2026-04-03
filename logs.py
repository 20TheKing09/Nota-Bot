"""Server log channels and event forwarding."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import info_embed, ok_embed
from bot.i18n import t
from bot.logutil import LOG_LABELS, dispatch_log

if TYPE_CHECKING:
    from bot.core import NotaBot

LOG_TYPES = [
    "log_msg",
    "log_voc",
    "log_imp",
    "log_inv",
    "log_sal",
    "log_rol",
    "log_mod",
    "log_sta",
]


class LogsCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @app_commands.command(name="setlog", description="Assign a log type to a channel")
    @app_commands.describe(
        log_type="Log category",
        channel="Destination channel",
    )
    @app_commands.choices(
        log_type=[
            app_commands.Choice(name=LOG_LABELS[k], value=k)
            for k in LOG_TYPES
        ]
    )
    @app_commands.default_permissions(administrator=True)
    async def setlog_cmd(
        self,
        interaction: discord.Interaction,
        log_type: str,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.set_log_channel(interaction.guild.id, log_type, channel.id)
        await interaction.response.send_message(
            embed=ok_embed(
                "Logs",
                t(lang, "logs.set", log_type=log_type, channel=channel.mention),
            ),
            ephemeral=True,
        )

    @app_commands.command(name="viewlogs", description="View configured log channels")
    @app_commands.default_permissions(administrator=True)
    async def viewlogs_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        m = await self.bot.db.get_log_channels(interaction.guild.id)
        if not m:
            await interaction.response.send_message(
                embed=info_embed(t(lang, "logs.view.title"), "—"),
                ephemeral=True,
            )
            return
        lines = [f"`{k}` → <#{v}>" for k, v in m.items()]
        await interaction.response.send_message(
            embed=info_embed(t(lang, "logs.view.title"), "\n".join(lines)),
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(
            title="Message deleted",
            description=f"Channel: {message.channel.mention}\nAuthor: {message.author}",
            color=discord.Color.dark_red(),
        )
        if message.content:
            embed.add_field(name="Content", value=message.content[:1000], inline=False)
        await dispatch_log(self.bot, message.guild, "log_msg", embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(
            title="Message edited",
            description=f"{before.channel.mention} · {before.author}",
            color=discord.Color.blue(),
        )
        embed.add_field(name="Before", value=before.content[:500] or "—", inline=False)
        embed.add_field(name="After", value=after.content[:500] or "—", inline=False)
        await dispatch_log(self.bot, before.guild, "log_msg", embed)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles == after.roles:
            return
        embed = discord.Embed(
            title="Member roles updated",
            description=f"{after.mention}",
            color=discord.Color.blurple(),
        )
        b = {r.id for r in before.roles}
        a = {r.id for r in after.roles}
        added = a - b
        removed = b - a
        if added:
            embed.add_field(
                name="Added",
                value=", ".join(f"<@&{rid}>" for rid in added) or "—",
                inline=False,
            )
        if removed:
            embed.add_field(
                name="Removed",
                value=", ".join(f"<@&{rid}>" for rid in removed) or "—",
                inline=False,
            )
        await dispatch_log(self.bot, after.guild, "log_rol", embed)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if before.channel == after.channel:
            return
        embed = discord.Embed(
            title="Voice move",
            description=f"{member.mention}",
            color=discord.Color.green(),
        )
        embed.add_field(name="Before", value=str(before.channel) if before.channel else "—", inline=True)
        embed.add_field(name="After", value=str(after.channel) if after.channel else "—", inline=True)
        await dispatch_log(self.bot, member.guild, "log_voc", embed)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LogsCog(bot))  # type: ignore[arg-type]
