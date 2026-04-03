"""Anonymous confession posts."""

from __future__ import annotations

from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import err_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class ConfessionCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @app_commands.command(name="confession", description="Send an anonymous confession to the server")
    @app_commands.describe(text="Your confession (max 2000 chars)")
    async def confession_cmd(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        row = await self.bot.db.get_or_create_guild_row(interaction.guild.id)
        if not row.get("confession_enabled"):
            await interaction.response.send_message(
                embed=err_embed("Confession", t(lang, "confession.disabled")),
                ephemeral=True,
            )
            return
        cid = row.get("confession_channel_id")
        if not cid:
            await interaction.response.send_message(
                embed=err_embed("Confession", "Not configured."),
                ephemeral=True,
            )
            return
        ch = interaction.guild.get_channel(int(cid))
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(embed=err_embed("Error", "Invalid channel."), ephemeral=True)
            return
        embed = discord.Embed(
            title="Anonymous confession",
            description=text[:2000],
            color=discord.Color.teal(),
        )
        embed.set_footer(text=f"ID · {interaction.user.id % 10000:04d}")
        try:
            await ch.send(embed=embed)
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        log_id = row.get("confession_log_id")
        if log_id:
            log_ch = interaction.guild.get_channel(int(log_id))
            if isinstance(log_ch, discord.TextChannel):
                try:
                    await log_ch.send(
                        f"Confession author: {interaction.user} ({interaction.user.id})",
                        allowed_mentions=discord.AllowedMentions.none(),
                    )
                except discord.HTTPException:
                    pass
        await interaction.response.send_message(
            embed=ok_embed("Confession", t(lang, "confession.sent")),
            ephemeral=True,
        )

    cs_config = app_commands.Group(
        name="cs-config",
        description="Configure confession system (administrator)",
    )

    @cs_config.command(name="channel", description="Channel where confessions are posted")
    @app_commands.default_permissions(administrator=True)
    async def cs_ch(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            confession_channel_id=channel.id,
            confession_enabled=1,
        )
        await interaction.response.send_message(
            embed=ok_embed("Confession", f"Output: {channel.mention}"),
            ephemeral=True,
        )

    @cs_config.command(name="log", description="Staff-only log channel (optional)")
    @app_commands.default_permissions(administrator=True)
    async def cs_log(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel | None = None,
    ) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            confession_log_id=channel.id if channel else None,
        )
        await interaction.response.send_message(embed=ok_embed("Confession", "Log updated."), ephemeral=True)

    @cs_config.command(name="toggle", description="Enable or disable confessions")
    @app_commands.default_permissions(administrator=True)
    async def cs_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        assert interaction.guild
        await self.bot.db.update_guild_settings(
            interaction.guild.id, confession_enabled=1 if enabled else 0
        )
        await interaction.response.send_message(
            embed=ok_embed("Confession", f"Enabled: **{enabled}**"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ConfessionCog(bot))  # type: ignore[arg-type]
