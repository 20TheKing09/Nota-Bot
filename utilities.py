"""General utilities: info, say, embed, random, test, help."""

from __future__ import annotations

import random as rnd
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import owner_only
from bot.embeds import ACCENT, info_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class UtilitiesCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @app_commands.command(name="help", description="Overview of Nota Bot commands")
    async def help_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        embed = discord.Embed(
            title="Nota Bot",
            description=(
                "Moderation · channels & roles · leveling · economy · tickets · welcome · logs · "
                "masterlog · security · confession · autorole · utilities · owner tools.\n\n"
                "Use `/language` to switch the server UI between **English** and **Français**."
            ),
            color=ACCENT,
        )
        embed.add_field(
            name="Moderation",
            value="`/ban` `/unban` `/kick` `/timeout` `/untimeout` `/mute` `/warn` `/warns` `/clearwarns` "
            "`/blacklist` `/unblacklist` `/blacklistlist` `/clear` `/clearroom`",
            inline=False,
        )
        embed.add_field(
            name="Channels & roles",
            value="`/lock` `/unlock` `/slowmode` `/lockdown` `/unlockdown` `/hideall` `/unhideall` "
            "`/vlock` `/vunlock` `/roleadd` `/roleremove` `/rolelock` `/roleunlock` `/temprole` "
            "`/removetemp` `/rankup` `/derank`",
            inline=False,
        )
        embed.add_field(
            name="Leveling",
            value="`/rank` `/leaderboard` `/vrank` `/vleaderboard` `/level` `/levelconfig`",
            inline=False,
        )
        embed.add_field(
            name="Economy",
            value="`/economy balance` `/economy daily` `/economy pay` `/economy leaderboard` "
            "`/economy give` `/economy take` `/economy currency`",
            inline=False,
        )
        embed.add_field(
            name="Tickets",
            value="`/ticket setup` `/ticket panel` (button **Open ticket**)",
            inline=False,
        )
        embed.set_footer(text="Restricted commands marked · manage server permissions required")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="avatar", description="Show a member's avatar")
    @app_commands.describe(member="Member (default: you)")
    async def avatar_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        m = member or interaction.user
        assert isinstance(m, discord.Member)
        embed = discord.Embed(title=t(lang, "util.avatar"), color=ACCENT)
        embed.set_image(url=m.display_avatar.url)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="serverinfo", description="Server information")
    async def serverinfo_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        g = interaction.guild
        embed = discord.Embed(title=g.name, color=ACCENT)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="ID", value=str(g.id), inline=True)
        embed.add_field(name="Owner", value=str(g.owner), inline=True)
        embed.add_field(name="Members", value=str(g.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(g.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(g.roles)), inline=True)
        embed.add_field(name="Boost tier", value=str(g.premium_tier), inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="userinfo", description="Member information")
    @app_commands.describe(member="Member (default: you)")
    async def userinfo_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild
        m = member or interaction.user
        assert isinstance(m, discord.Member)
        embed = discord.Embed(title=str(m), color=m.color if m.color.value else ACCENT)
        embed.set_thumbnail(url=m.display_avatar.url)
        embed.add_field(name="ID", value=str(m.id), inline=True)
        embed.add_field(name="Joined", value=discord.utils.format_dt(m.joined_at, "R") if m.joined_at else "—", inline=True)
        embed.add_field(name="Created", value=discord.utils.format_dt(m.created_at, "R"), inline=True)
        embed.add_field(name="Top role", value=m.top_role.mention, inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="say", description="Make the bot send a message (owner)")
    @app_commands.describe(channel="Target channel", text="Message content")
    @owner_only()
    async def say_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        text: str,
    ) -> None:
        await interaction.response.send_message("Sent.", ephemeral=True)
        await channel.send(text[:2000])

    @app_commands.command(name="embed", description="Send a custom embed (owner)")
    @app_commands.describe(
        channel="Target channel",
        title="Embed title",
        body="Embed description",
        color="Hex color e.g. 5865F2",
    )
    @owner_only()
    async def embed_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        title: str,
        body: str,
        color: str = "5865F2",
    ) -> None:
        try:
            c = int(color.lstrip("#"), 16)
        except ValueError:
            c = ACCENT
        embed = discord.Embed(title=title[:256], description=body[:4000], color=c)
        await interaction.response.send_message("Sent.", ephemeral=True)
        await channel.send(embed=embed)

    @app_commands.command(name="random", description="Pick two random members (excluding bots)")
    async def random_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        humans = [m for m in interaction.guild.members if not m.bot]
        if len(humans) < 2:
            await interaction.response.send_message("Not enough members.", ephemeral=True)
            return
        a, b = rnd.sample(humans, 2)
        await interaction.response.send_message(
            embed=info_embed("Random", t(lang, "util.random", a=a.mention, b=b.mention))
        )

    @app_commands.command(name="test", description="Bot latency and shard info")
    async def test_cmd(self, interaction: discord.Interaction) -> None:
        lang = await self._lang(interaction.guild) if interaction.guild else "en"
        ms = int(self.bot.latency * 1000) if self.bot.latency else 0
        await interaction.response.send_message(
            embed=info_embed(
                "Test",
                t(lang, "util.test", ms=ms, gw=ms),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(UtilitiesCog(bot))  # type: ignore[arg-type]
