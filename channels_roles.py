"""Channel and role management commands."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.embeds import err_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class ChannelsRolesCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot
        self._temp_role_loop.start()

    def cog_unload(self) -> None:
        self._temp_role_loop.cancel()

    @tasks.loop(minutes=1)
    async def _temp_role_loop(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        due = await self.bot.db.due_temp_roles(now)
        for row in due:
            guild = self.bot.get_guild(row["guild_id"])
            if not guild:
                await self.bot.db.remove_temp_role_entry(row["id"])
                continue
            member = guild.get_member(row["user_id"])
            role = guild.get_role(row["role_id"])
            if member and role:
                try:
                    await member.remove_roles(role, reason="Temporary role expired")
                except discord.HTTPException:
                    pass
            await self.bot.db.remove_temp_role_entry(row["id"])

    @_temp_role_loop.before_loop
    async def _before_temp_loop(self) -> None:
        await self.bot.wait_until_ready()

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @app_commands.command(name="lock", description="Lock the current text channel (@everyone cannot send)")
    @app_commands.default_permissions(manage_channels=True)
    async def lock_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and interaction.channel
        lang = await self._lang(interaction.guild)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(embed=err_embed("Error", "Not a text channel."), ephemeral=True)
            return
        everyone = interaction.guild.default_role
        await ch.set_permissions(everyone, send_messages=False)
        await interaction.response.send_message(embed=ok_embed("Lock", t(lang, "channels.lock.ok")))

    @app_commands.command(name="unlock", description="Unlock the current text channel")
    @app_commands.default_permissions(manage_channels=True)
    async def unlock_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and interaction.channel
        lang = await self._lang(interaction.guild)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(embed=err_embed("Error", "Not a text channel."), ephemeral=True)
            return
        everyone = interaction.guild.default_role
        await ch.set_permissions(everyone, send_messages=None)
        await interaction.response.send_message(embed=ok_embed("Unlock", t(lang, "channels.unlock.ok")))

    @app_commands.command(name="slowmode", description="Set slowmode for this channel (seconds)")
    @app_commands.describe(seconds="0 to disable, max 21600")
    @app_commands.default_permissions(manage_channels=True)
    async def slowmode_cmd(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 0, 21600],
    ) -> None:
        assert interaction.guild and interaction.channel
        lang = await self._lang(interaction.guild)
        ch = interaction.channel
        if not isinstance(ch, discord.TextChannel):
            await interaction.response.send_message(embed=err_embed("Error", "Not a text channel."), ephemeral=True)
            return
        await ch.edit(slowmode_delay=seconds)
        await interaction.response.send_message(
            embed=ok_embed("Slowmode", t(lang, "channels.slowmode.ok", seconds=seconds))
        )

    @app_commands.command(name="lockdown", description="Deny send messages in all text channels for @everyone")
    @app_commands.default_permissions(administrator=True)
    async def lockdown_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        everyone = interaction.guild.default_role
        snap: dict[str, Any] = {}
        for ch in interaction.guild.text_channels:
            ow = ch.overwrites_for(everyone)
            snap[str(ch.id)] = {"send_messages": ow.send_messages}
            await ch.set_permissions(everyone, send_messages=False)
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            lockdown_active=1,
            lockdown_snapshot=json.dumps(snap),
        )
        await interaction.response.send_message(embed=ok_embed("Lockdown", t(lang, "channels.lockdown.ok")))

    @app_commands.command(name="unlockdown", description="Restore permissions after lockdown")
    @app_commands.default_permissions(administrator=True)
    async def unlockdown_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        row = await self.bot.db.get_or_create_guild_row(interaction.guild.id)
        snap_raw = row.get("lockdown_snapshot")
        everyone = interaction.guild.default_role
        if snap_raw:
            snap = json.loads(snap_raw)
            for cid, data in snap.items():
                ch = interaction.guild.get_channel(int(cid))
                if isinstance(ch, discord.TextChannel):
                    sm = data.get("send_messages")
                    await ch.set_permissions(everyone, send_messages=sm)
        else:
            for ch in interaction.guild.text_channels:
                await ch.set_permissions(everyone, send_messages=None)
        await self.bot.db.update_guild_settings(interaction.guild.id, lockdown_active=0, lockdown_snapshot=None)
        await interaction.response.send_message(embed=ok_embed("Unlockdown", t(lang, "channels.unlockdown.ok")))

    @app_commands.command(name="hideall", description="Hide all channels except one from @everyone")
    @app_commands.describe(exempt_channel="Channel that stays visible")
    @app_commands.default_permissions(administrator=True)
    async def hideall_cmd(
        self,
        interaction: discord.Interaction,
        exempt_channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        everyone = interaction.guild.default_role
        snap: dict[str, Any] = {}
        for ch in interaction.guild.channels:
            if not isinstance(ch, (discord.TextChannel, discord.VoiceChannel, discord.ForumChannel)):
                continue
            if ch.id == exempt_channel.id:
                continue
            ow = ch.overwrites_for(everyone)
            snap[str(ch.id)] = {"view_channel": ow.view_channel}
            await ch.set_permissions(everyone, view_channel=False)
        await self.bot.db.update_guild_settings(
            interaction.guild.id,
            hideall_exempt_channel_id=exempt_channel.id,
            hideall_snapshot=json.dumps(snap),
        )
        await interaction.response.send_message(embed=ok_embed("Hide all", t(lang, "channels.hideall.ok")))

    @app_commands.command(name="unhideall", description="Restore visibility after hideall")
    @app_commands.default_permissions(administrator=True)
    async def unhideall_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        row = await self.bot.db.get_or_create_guild_row(interaction.guild.id)
        snap_raw = row.get("hideall_snapshot")
        everyone = interaction.guild.default_role
        if snap_raw:
            snap = json.loads(snap_raw)
            for cid, data in snap.items():
                ch = interaction.guild.get_channel(int(cid))
                if ch and hasattr(ch, "set_permissions"):
                    vc = data.get("view_channel")
                    await ch.set_permissions(everyone, view_channel=vc)
        await self.bot.db.update_guild_settings(
            interaction.guild.id, hideall_exempt_channel_id=None, hideall_snapshot=None
        )
        await interaction.response.send_message(embed=ok_embed("Unhide all", t(lang, "channels.unhideall.ok")))

    @app_commands.command(name="vlock", description="Lock a voice channel (connect=False for @everyone)")
    @app_commands.describe(channel="Voice channel")
    @app_commands.default_permissions(manage_channels=True)
    async def vlock_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        everyone = interaction.guild.default_role
        await channel.set_permissions(everyone, connect=False)
        await interaction.response.send_message(embed=ok_embed("VLock", t(lang, "channels.vlock.ok")))

    @app_commands.command(name="vunlock", description="Unlock a voice channel")
    @app_commands.describe(channel="Voice channel")
    @app_commands.default_permissions(manage_channels=True)
    async def vunlock_cmd(
        self,
        interaction: discord.Interaction,
        channel: discord.VoiceChannel,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        everyone = interaction.guild.default_role
        await channel.set_permissions(everyone, connect=None)
        await interaction.response.send_message(embed=ok_embed("VUnlock", t(lang, "channels.vunlock.ok")))

    @app_commands.command(name="roleadd", description="Add a role to a member")
    @app_commands.describe(member="Member", role="Role")
    @app_commands.default_permissions(manage_roles=True)
    async def roleadd_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        if await self.bot.db.is_role_locked(interaction.guild.id, member.id):
            await interaction.response.send_message(
                embed=err_embed("Error", "Role changes are locked for this member."), ephemeral=True
            )
            return
        await member.add_roles(role, reason=f"roleadd by {interaction.user}")
        await interaction.response.send_message(
            embed=ok_embed("Role", t(lang, "roles.roleadd.ok", role=role.name, user=str(member)))
        )

    @app_commands.command(name="roleremove", description="Remove a role from a member")
    @app_commands.describe(member="Member", role="Role")
    @app_commands.default_permissions(manage_roles=True)
    async def roleremove_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        if await self.bot.db.is_role_locked(interaction.guild.id, member.id):
            await interaction.response.send_message(
                embed=err_embed("Error", "Role changes are locked for this member."), ephemeral=True
            )
            return
        await member.remove_roles(role, reason=f"roleremove by {interaction.user}")
        await interaction.response.send_message(
            embed=ok_embed("Role", t(lang, "roles.roleremove.ok", role=role.name, user=str(member)))
        )

    @app_commands.command(name="rolelock", description="Prevent adding/removing roles for a member (bot-enforced)")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(manage_roles=True)
    async def rolelock_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.set_role_lock(interaction.guild.id, member.id, True)
        await interaction.response.send_message(
            embed=ok_embed("Role lock", t(lang, "roles.rolelock.ok", user=str(member)))
        )

    @app_commands.command(name="roleunlock", description="Remove role lock")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(manage_roles=True)
    async def roleunlock_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.set_role_lock(interaction.guild.id, member.id, False)
        await interaction.response.send_message(
            embed=ok_embed("Role unlock", t(lang, "roles.roleunlock.ok", user=str(member)))
        )

    @app_commands.command(name="temprole", description="Give a role that expires after N hours")
    @app_commands.describe(member="Member", role="Role", hours="Duration in hours (1–720)")
    @app_commands.default_permissions(manage_roles=True)
    async def temprole_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
        hours: app_commands.Range[int, 1, 720],
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await member.add_roles(role, reason=f"temprole by {interaction.user}")
        exp = datetime.now(timezone.utc) + timedelta(hours=hours)
        ts = int(exp.timestamp())
        await self.bot.db.add_temp_role(
            interaction.guild.id, member.id, role.id, exp.isoformat()
        )
        await interaction.response.send_message(
            embed=ok_embed(
                "Temp role",
                t(lang, "roles.temprole.ok", role=role.name, user=str(member), ts=ts),
            )
        )

    @app_commands.command(name="removetemp", description="Remove the next expiring temp role from a member")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(manage_roles=True)
    async def removetemp_cmd(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        rows = await self.bot.db.temp_roles_for_member(interaction.guild.id, member.id)
        if not rows:
            await interaction.response.send_message(embed=err_embed("Error", "No temp role entry."), ephemeral=True)
            return
        r = rows[0]
        role = interaction.guild.get_role(r["role_id"])
        if role:
            try:
                await member.remove_roles(role)
            except discord.HTTPException:
                pass
        await self.bot.db.remove_temp_role_entry(r["id"])
        await interaction.response.send_message(
            embed=ok_embed("Remove temp", t(lang, "roles.removetemp.ok", user=str(member)))
        )

    @app_commands.command(name="rankup", description="Add a role to a member (promotion)")
    @app_commands.describe(member="Member", role="Role to add")
    @app_commands.default_permissions(manage_roles=True)
    async def rankup_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await member.add_roles(role, reason=f"rankup by {interaction.user}")
        await interaction.response.send_message(
            embed=ok_embed("Rank up", t(lang, "roles.rankup.ok", user=str(member), role=role.name))
        )

    @app_commands.command(name="derank", description="Remove a role from a member (demotion)")
    @app_commands.describe(member="Member", role="Role to remove")
    @app_commands.default_permissions(manage_roles=True)
    async def derank_cmd(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        role: discord.Role,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await member.remove_roles(role, reason=f"derank by {interaction.user}")
        await interaction.response.send_message(
            embed=ok_embed("Derank", t(lang, "roles.derank.ok", user=str(member), role=role.name))
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelsRolesCog(bot))  # type: ignore[arg-type]
