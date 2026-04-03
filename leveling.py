"""XP, levels, voice time, and admin tools."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from bot.embeds import err_embed, info_embed, level_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot

# In-memory voice join times: (guild_id, user_id) -> datetime UTC
_voice_join: dict[tuple[int, int], datetime] = {}


def level_from_xp(xp: int) -> int:
    if xp <= 0:
        return 1
    return max(1, int(math.sqrt(xp / 100.0)) + 1)


def xp_for_level(level: int) -> int:
    if level <= 1:
        return 0
    return (level - 1) ** 2 * 100


class LevelingCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot
        self._voice_task.start()

    def cog_unload(self) -> None:
        self._voice_task.cancel()

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @tasks.loop(minutes=1)
    async def _voice_task(self) -> None:
        """Award vocal XP per minute while connected (voice time is tracked on disconnect)."""
        for key in list(_voice_join.keys()):
            guild_id, user_id = key
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue
            member = guild.get_member(user_id)
            if not member or not member.voice or not member.voice.channel:
                continue
            cfg = await self.bot.db.get_level_config(guild_id)
            per_min = float(cfg.get("vocal_xp_per_min") or 5.0)
            row = await self.bot.db.get_level_row(guild_id, user_id)
            old_lvl = level_from_xp(int(row.get("xp") or 0))
            new_xp = await self.bot.db.add_level_xp(guild_id, user_id, int(per_min))
            new_lvl = level_from_xp(new_xp)
            if new_lvl > old_lvl:
                await self._maybe_level_up(guild, member, guild_id, user_id)

    @_voice_task.before_loop
    async def _before_voice(self) -> None:
        await self.bot.wait_until_ready()

    async def _maybe_level_up(
        self,
        guild: discord.Guild,
        member: discord.Member,
        guild_id: int,
        user_id: int,
    ) -> None:
        row = await self.bot.db.get_level_row(guild_id, user_id)
        xp = int(row.get("xp") or 0)
        lvl = level_from_xp(xp)
        cfg = await self.bot.db.get_level_config(guild_id)
        if not cfg.get("levelup_enabled", 1):
            return
        msg = cfg.get("levelup_message") or "🎉 {user} reached **level {level}**!"
        ch_id = cfg.get("levelup_channel_id")
        channel = guild.get_channel(ch_id) if ch_id else None
        if not isinstance(channel, discord.TextChannel):
            channel = None
        if channel:
            try:
                text = str(msg).format(user=member.mention, level=lvl, guild=guild.name)
                await channel.send(embed=level_embed("Level up!", text))
            except discord.HTTPException:
                pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or not message.guild:
            return
        guild_id = message.guild.id
        user_id = message.author.id
        cfg = await self.bot.db.get_level_config(guild_id)
        cd = float(cfg.get("msg_cooldown") or 60.0)
        import time

        last = await self.bot.db.get_msg_cooldown(guild_id, user_id)
        now = time.monotonic()
        if last is not None and (now - last) < cd:
            return
        await self.bot.db.set_msg_cooldown(guild_id, user_id, now)
        add = int(cfg.get("msg_xp") or 15)
        old = await self.bot.db.get_level_row(guild_id, user_id)
        old_lvl = level_from_xp(int(old.get("xp") or 0))
        new_xp = await self.bot.db.add_level_xp(guild_id, user_id, add)
        new_lvl = level_from_xp(new_xp)
        if new_lvl > old_lvl and message.guild:
            m = message.guild.get_member(user_id)
            if m:
                await self._maybe_level_up(message.guild, m, guild_id, user_id)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ) -> None:
        if member.bot:
            return
        gid = member.guild.id
        uid = member.id
        key = (gid, uid)

        if before.channel is None and after.channel is not None:
            _voice_join[key] = datetime.now(timezone.utc)
        elif before.channel is not None and after.channel is None:
            start = _voice_join.pop(key, None)
            if start:
                seconds = int((datetime.now(timezone.utc) - start).total_seconds())
                if seconds > 0:
                    await self.bot.db.add_voice_seconds(gid, uid, seconds)
        elif before.channel is not None and after.channel is not None and before.channel != after.channel:
            start = _voice_join.get(key)
            if start:
                seconds = int((datetime.now(timezone.utc) - start).total_seconds())
                if seconds > 0:
                    await self.bot.db.add_voice_seconds(gid, uid, seconds)
            _voice_join[key] = datetime.now(timezone.utc)

    @app_commands.command(name="rank", description="Show your message XP rank and level")
    @app_commands.describe(member="Member to inspect (optional)")
    async def rank_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        m = member or interaction.user
        assert isinstance(m, discord.Member)
        row = await self.bot.db.get_level_row(interaction.guild.id, m.id)
        xp = int(row.get("xp") or 0)
        vs = int(row.get("voice_seconds") or 0)
        lvl = level_from_xp(xp)
        need = xp_for_level(lvl + 1)
        vh, vm = vs // 3600, (vs % 3600) // 60
        text = t(
            lang,
            "level.rank.text",
            level=lvl,
            xp=xp,
            need=need,
            vh=vh,
            vm=vm,
        )
        e = level_embed(t(lang, "level.rank.title", user=str(m)), text)
        e.set_thumbnail(url=m.display_avatar.url)
        await interaction.response.send_message(embed=e)

    @app_commands.command(name="leaderboard", description="Top members by message XP")
    @app_commands.describe(limit="How many users (5–25)")
    async def leaderboard_cmd(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 5, 25] = 10,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        rows = await self.bot.db.leaderboard(interaction.guild.id, limit)
        lines = []
        for i, r in enumerate(rows, 1):
            u = interaction.guild.get_member(r["user_id"])
            name = u.display_name if u else str(r["user_id"])
            lines.append(f"`{i}.` {name} — **{r['xp']}** XP (Lv. {level_from_xp(int(r['xp']))})")
        body = "\n".join(lines) if lines else "—"
        await interaction.response.send_message(
            embed=level_embed(t(lang, "level.lb.title"), body)
        )

    @app_commands.command(name="vrank", description="Show your voice time")
    @app_commands.describe(member="Member (optional)")
    async def vrank_cmd(self, interaction: discord.Interaction, member: discord.Member | None = None) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        m = member or interaction.user
        assert isinstance(m, discord.Member)
        row = await self.bot.db.get_level_row(interaction.guild.id, m.id)
        vs = int(row.get("voice_seconds") or 0)
        vh, vm, vsec = vs // 3600, (vs % 3600) // 60, vs % 60
        await interaction.response.send_message(
            embed=level_embed(
                t(lang, "level.vrank.title"),
                f"**{vh}**h **{vm}**m **{vsec}**s in voice (tracked)",
            )
        )

    @app_commands.command(name="vleaderboard", description="Top members by voice time")
    @app_commands.describe(limit="5–25")
    async def vleaderboard_cmd(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 5, 25] = 10,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        rows = await self.bot.db.vleaderboard(interaction.guild.id, limit)
        lines = []
        for i, r in enumerate(rows, 1):
            u = interaction.guild.get_member(r["user_id"])
            name = u.display_name if u else str(r["user_id"])
            sec = int(r["voice_seconds"])
            h, m_ = sec // 3600, (sec % 3600) // 60
            lines.append(f"`{i}.` {name} — **{h}**h **{m_}**m")
        body = "\n".join(lines) if lines else "—"
        await interaction.response.send_message(
            embed=level_embed(t(lang, "level.vlb.title"), body)
        )

    level_group = app_commands.Group(name="level", description="Admin: manage member XP (administrator)")

    @level_group.command(name="addxp", description="Add XP to a member")
    @app_commands.describe(member="Member", amount="XP amount")
    @app_commands.default_permissions(administrator=True)
    async def level_addxp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.add_level_xp(interaction.guild.id, member.id, amount)
        await interaction.response.send_message(
            embed=ok_embed("XP", t(lang, "level.admin.addxp", n=amount, user=str(member)))
        )

    @level_group.command(name="removexp", description="Remove XP from a member")
    @app_commands.describe(member="Member", amount="XP to remove")
    @app_commands.default_permissions(administrator=True)
    async def level_removexp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        assert interaction.guild
        await self.bot.db.add_level_xp(interaction.guild.id, member.id, -amount)
        await interaction.response.send_message(embed=ok_embed("XP", f"Removed **{amount}** XP from {member}."))

    @level_group.command(name="setxp", description="Set exact XP for a member")
    @app_commands.describe(member="Member", xp="New XP total")
    @app_commands.default_permissions(administrator=True)
    async def level_setxp(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        xp: app_commands.Range[int, 0, 999_999_999],
    ) -> None:
        assert interaction.guild
        await self.bot.db.set_level_xp(interaction.guild.id, member.id, xp)
        await interaction.response.send_message(embed=ok_embed("XP", f"Set **{member}** to **{xp}** XP."))

    @level_group.command(name="addvocal", description="Add voice seconds to stats")
    @app_commands.describe(member="Member", seconds="Seconds to add")
    @app_commands.default_permissions(administrator=True)
    async def level_addvocal(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        seconds: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        assert interaction.guild
        await self.bot.db.add_voice_seconds(interaction.guild.id, member.id, seconds)
        await interaction.response.send_message(
            embed=ok_embed("Voice", f"Added **{seconds}**s voice time for {member}.")
        )

    @level_group.command(name="reset", description="Reset leveling data for a member")
    @app_commands.describe(member="Member")
    @app_commands.default_permissions(administrator=True)
    async def level_reset(self, interaction: discord.Interaction, member: discord.Member) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.reset_level_member(interaction.guild.id, member.id)
        await interaction.response.send_message(
            embed=ok_embed("Reset", t(lang, "level.admin.reset", user=str(member)))
        )

    lc_group = app_commands.Group(name="levelconfig", description="Configure leveling (administrator)")

    @lc_group.command(name="view", description="View current leveling configuration")
    @app_commands.default_permissions(administrator=True)
    async def lc_view(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        c = await self.bot.db.get_level_config(interaction.guild.id)
        ch = c.get("levelup_channel_id")
        ch_txt = f"<#{ch}>" if ch else "—"
        body = (
            f"**Message XP:** {c.get('msg_xp')}\n"
            f"**Cooldown (s):** {c.get('msg_cooldown')}\n"
            f"**Vocal XP/min:** {c.get('vocal_xp_per_min')}\n"
            f"**Level-up channel:** {ch_txt}\n"
            f"**Announce:** {'on' if c.get('levelup_enabled') else 'off'}\n"
            f"**Message template:** {c.get('levelup_message') or 'default'}"
        )
        await interaction.response.send_message(embed=info_embed("Level config", body))

    @lc_group.command(name="message-xp", description="XP per valid message")
    @app_commands.describe(value="XP amount")
    @app_commands.default_permissions(administrator=True)
    async def lc_msg_xp(
        self,
        interaction: discord.Interaction,
        value: app_commands.Range[int, 1, 500],
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_level_config(interaction.guild.id, msg_xp=value)
        await interaction.response.send_message(embed=ok_embed("Config", f"Message XP set to **{value}**."))

    @lc_group.command(name="message-cooldown", description="Anti-spam cooldown between message XP (seconds)")
    @app_commands.describe(seconds="Seconds (5–600)")
    @app_commands.default_permissions(administrator=True)
    async def lc_msg_cd(
        self,
        interaction: discord.Interaction,
        seconds: app_commands.Range[int, 5, 600],
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_level_config(interaction.guild.id, msg_cooldown=float(seconds))
        await interaction.response.send_message(embed=ok_embed("Config", f"Cooldown: **{seconds}**s."))

    @lc_group.command(name="vocal-xp", description="XP awarded per minute in voice (approximate)")
    @app_commands.describe(value="XP per minute (0–500)")
    @app_commands.default_permissions(administrator=True)
    async def lc_vocal_xp(
        self,
        interaction: discord.Interaction,
        value: float,
    ) -> None:
        assert interaction.guild
        v = max(0.0, min(500.0, float(value)))
        await self.bot.db.upsert_level_config(interaction.guild.id, vocal_xp_per_min=v)
        await interaction.response.send_message(embed=ok_embed("Config", f"Vocal XP/min: **{v}**."))

    @lc_group.command(name="levelup-message", description="Template: use {user} {level} {guild}")
    @app_commands.describe(text="Message template")
    @app_commands.default_permissions(administrator=True)
    async def lc_lvl_msg(self, interaction: discord.Interaction, text: str) -> None:
        assert interaction.guild
        await self.bot.db.upsert_level_config(interaction.guild.id, levelup_message=text)
        await interaction.response.send_message(embed=ok_embed("Config", "Level-up message updated."))

    @lc_group.command(name="levelup-enable", description="Enable or disable level-up announcements")
    @app_commands.describe(enabled="Announce level ups")
    @app_commands.default_permissions(administrator=True)
    async def lc_lvl_en(
        self,
        interaction: discord.Interaction,
        enabled: bool,
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_level_config(interaction.guild.id, levelup_enabled=1 if enabled else 0)
        await interaction.response.send_message(embed=ok_embed("Config", f"Announcements: **{enabled}**."))

    @lc_group.command(name="set", description="Channel for level-up messages")
    @app_commands.describe(channel="Text channel")
    @app_commands.default_permissions(administrator=True)
    async def lc_set_ch(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_level_config(interaction.guild.id, levelup_channel_id=channel.id)
        await interaction.response.send_message(embed=ok_embed("Config", f"Level-up channel: {channel.mention}."))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))  # type: ignore[arg-type]
