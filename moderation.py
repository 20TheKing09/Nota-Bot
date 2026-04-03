"""Moderation: ban, kick, warns, blacklist, purge, etc."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import err_embed, info_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


def _reason_suffix(reason: str | None) -> str:
    if not reason:
        return ""
    return f" Reason: {reason}"


class ModerationCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        pass

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        if await self.bot.db.is_blacklisted(member.guild.id, member.id):
            try:
                await member.kick(reason="Blacklisted")
            except discord.HTTPException:
                pass

    async def _get_lang(self, guild: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(guild.id)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", reason="Reason (optional)")
    @app_commands.default_permissions(ban_members=True)
    async def ban_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                embed=err_embed("Error", t(lang, "generic.no_perm")), ephemeral=True
            )
            return
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            await interaction.response.send_message(
                embed=err_embed("Error", "You cannot ban this member."), ephemeral=True
            )
            return
        try:
            await member.ban(reason=reason or f"Banned by {interaction.user}", delete_message_days=1)
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=err_embed("Error", str(e)), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=ok_embed(
                "Ban",
                t(lang, "mod.ban.ok", user=str(member), reason=_reason_suffix(reason)),
            )
        )

    @app_commands.command(name="unban", description="Unban a user by ID")
    @app_commands.describe(user_id="The banned user's ID")
    @app_commands.default_permissions(ban_members=True)
    async def unban_cmd(self, interaction: discord.Interaction, user_id: str) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        if not interaction.user.guild_permissions.ban_members:
            await interaction.response.send_message(
                embed=err_embed("Error", t(lang, "generic.no_perm")), ephemeral=True
            )
            return
        try:
            uid = int(user_id)
        except ValueError:
            await interaction.response.send_message(embed=err_embed("Error", "Invalid ID."), ephemeral=True)
            return
        user = discord.Object(id=uid)
        try:
            await interaction.guild.unban(user)
        except discord.NotFound:
            await interaction.response.send_message(
                embed=err_embed("Error", "User is not banned."), ephemeral=True
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=ok_embed("Unban", t(lang, "mod.unban.ok", user_id=uid))
        )

    @app_commands.command(name="kick", description="Kick a member")
    @app_commands.describe(member="Member to kick", reason="Reason (optional)")
    @app_commands.default_permissions(kick_members=True)
    async def kick_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        if not interaction.user.guild_permissions.kick_members:
            await interaction.response.send_message(
                embed=err_embed("Error", t(lang, "generic.no_perm")), ephemeral=True
            )
            return
        if member.top_role >= interaction.user.top_role and interaction.guild.owner_id != interaction.user.id:
            await interaction.response.send_message(
                embed=err_embed("Error", "You cannot kick this member."), ephemeral=True
            )
            return
        try:
            await member.kick(reason=reason or f"Kicked by {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=ok_embed(
                "Kick",
                t(lang, "mod.kick.ok", user=str(member), reason=_reason_suffix(reason)),
            )
        )

    @app_commands.command(name="timeout", description="Timeout a member (Discord native)")
    @app_commands.describe(member="Member", minutes="Duration in minutes (1–40320)", reason="Reason")
    @app_commands.default_permissions(moderate_members=True)
    async def timeout_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320],
        reason: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        if not interaction.user.guild_permissions.moderate_members:
            await interaction.response.send_message(
                embed=err_embed("Error", t(lang, "generic.no_perm")), ephemeral=True
            )
            return
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        try:
            await member.timeout(until, reason=reason or f"Timeout by {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        rs = f" {reason}" if reason else ""
        await interaction.response.send_message(
            embed=ok_embed(
                "Timeout",
                t(
                    lang,
                    "mod.timeout.ok",
                    user=str(member),
                    minutes=minutes,
                    reason=rs,
                ),
            )
        )

    @app_commands.command(name="untimeout", description="Remove a member's timeout")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(moderate_members=True)
    async def untimeout_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        try:
            await member.timeout(None)
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=ok_embed("Untimeout", t(lang, "mod.untimeout.ok", user=str(member)))
        )

    @app_commands.command(name="mute", description="Mute via timeout (same as timeout)")
    @app_commands.describe(member="Member", minutes="Duration (1–40320)", reason="Reason")
    @app_commands.default_permissions(moderate_members=True)
    async def mute_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        minutes: app_commands.Range[int, 1, 40320] = 60,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        until = discord.utils.utcnow() + timedelta(minutes=minutes)
        try:
            await member.timeout(until, reason=reason or f"Mute by {interaction.user}")
        except discord.HTTPException as e:
            await interaction.response.send_message(embed=err_embed("Error", str(e)), ephemeral=True)
            return
        rs = f" {reason}" if reason else ""
        await interaction.response.send_message(
            embed=ok_embed(
                "Mute",
                t(lang, "mod.mute.ok", user=str(member), minutes=minutes, reason=rs),
            )
        )

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member", reason="Reason")
    @app_commands.default_permissions(moderate_members=True)
    async def warn_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str = "No reason provided",
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        wid = await self.bot.db.add_warn(
            interaction.guild.id, member.id, interaction.user.id, reason
        )
        warns = await self.bot.db.get_warns(interaction.guild.id, member.id)
        n = len(warns)
        rs = f" `{reason}`" if reason else ""
        await interaction.response.send_message(
            embed=ok_embed(
                "Warn",
                t(lang, "mod.warn.ok", user=str(member), n=n, reason=rs),
            )
        )

    @app_commands.command(name="warns", description="List warnings for a member")
    @app_commands.describe(member="Member")
    async def warns_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        rows = await self.bot.db.get_warns(interaction.guild.id, member.id)
        if not rows:
            await interaction.response.send_message(
                embed=info_embed(t(lang, "mod.warns.title", user=str(member)), t(lang, "mod.warns.empty"))
            )
            return
        lines = [
            t(
                lang,
                "mod.warns.line",
                id=r["id"],
                mod=r["moderator_id"],
                reason=r["reason"] or "—",
            )
            for r in rows[:15]
        ]
        await interaction.response.send_message(
            embed=info_embed(
                t(lang, "mod.warns.title", user=str(member)),
                "\n".join(lines),
            )
        )

    @app_commands.command(name="clearwarns", description="Clear all warnings for a member")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(moderate_members=True)
    async def clearwarns_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        n = await self.bot.db.clear_warns(interaction.guild.id, member.id)
        await interaction.response.send_message(
            embed=ok_embed("Clear warns", t(lang, "mod.clearwarns.ok", n=n, user=str(member)))
        )

    @app_commands.command(name="blacklist", description="Blacklist a user (kick on join)")
    @app_commands.describe(member="Member", reason="Reason")
    @app_commands.default_permissions(administrator=True)
    async def blacklist_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        reason: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        await self.bot.db.add_blacklist(
            interaction.guild.id, member.id, interaction.user.id, reason
        )
        try:
            await member.kick(reason="Blacklisted")
        except discord.HTTPException:
            pass
        await interaction.response.send_message(
            embed=ok_embed("Blacklist", t(lang, "mod.blacklist.ok", user=str(member)))
        )

    @app_commands.command(name="unblacklist", description="Remove a user from the blacklist")
    @app_commands.describe(user="User ID to remove")
    @app_commands.default_permissions(administrator=True)
    async def unblacklist_cmd(self, interaction: discord.Interaction, user: discord.User) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        ok = await self.bot.db.remove_blacklist(interaction.guild.id, user.id)
        if not ok:
            await interaction.response.send_message(
                embed=err_embed("Error", "Not blacklisted."), ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=ok_embed("Unblacklist", t(lang, "mod.unblacklist.ok", user=str(user)))
        )

    @app_commands.command(name="blacklistlist", description="Show blacklisted user IDs")
    @app_commands.default_permissions(administrator=True)
    async def blacklistlist_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        rows = await self.bot.db.list_blacklist(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(
                embed=info_embed(t(lang, "mod.blacklistlist.title"), t(lang, "mod.blacklistlist.empty"))
            )
            return
        body = "\n".join(f"<@{r['user_id']}> (`{r['user_id']}`)" for r in rows[:25])
        await interaction.response.send_message(
            embed=info_embed(t(lang, "mod.blacklistlist.title"), body)
        )

    @app_commands.command(name="clear", description="Delete recent messages (max 100)")
    @app_commands.describe(amount="Number of messages to scan (1–100)")
    @app_commands.default_permissions(manage_messages=True)
    async def clear_cmd(
        self,
        interaction: discord.Interaction,
        amount: app_commands.Range[int, 1, 100],
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(
                embed=err_embed("Error", "Use in a text channel."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        deleted = await ch.purge(limit=amount, check=lambda m: not m.pinned)
        n = len(deleted)
        await interaction.followup.send(
            embed=ok_embed("Purge", t(lang, "mod.clear.ok", n=n)), ephemeral=True
        )

    @app_commands.command(name="clearroom", description="Purge many messages from this channel")
    @app_commands.describe(batches="How many batches of 100 (1–20)")
    @app_commands.default_permissions(manage_messages=True)
    async def clearroom_cmd(
        self,
        interaction: discord.Interaction,
        batches: app_commands.Range[int, 1, 20] = 5,
    ) -> None:
        assert interaction.guild
        lang = await self._get_lang(interaction.guild)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(
                embed=err_embed("Error", "Use in a text channel."), ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        total = 0
        for _ in range(batches):
            batch = await ch.purge(limit=100, check=lambda m: not m.pinned)
            total += len(batch)
            if len(batch) < 100:
                break
            await asyncio.sleep(1.2)
        await interaction.followup.send(
            embed=ok_embed("Clear room", t(lang, "mod.clearroom.ok", n=total)), ephemeral=True
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ModerationCog(bot))  # type: ignore[arg-type]
