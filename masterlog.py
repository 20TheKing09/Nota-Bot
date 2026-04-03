"""Centralized logging to a private hub server."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import owner_only
from bot.embeds import info_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


class MasterlogCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    masterlog = app_commands.Group(
        name="masterlog",
        description="Centralized logs hub (bot owner)",
    )

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    @masterlog.command(name="set-server", description="Set this server as the master log hub")
    @owner_only()
    async def ml_set_server(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        await self.bot.db.update_global_settings(master_hub_guild_id=interaction.guild.id)
        await interaction.response.send_message(
            embed=ok_embed("Master log", t(lang, "masterlog.set")),
            ephemeral=True,
        )

    @masterlog.command(name="toggle", description="Enable or disable centralized forwarding")
    @owner_only()
    async def ml_toggle(self, interaction: discord.Interaction, enabled: bool) -> None:
        lang = await self._lang(interaction.guild) if interaction.guild else "en"
        await self.bot.db.update_global_settings(master_enabled=1 if enabled else 0)
        await interaction.response.send_message(
            embed=ok_embed(
                "Master log",
                t(lang, "masterlog.toggle", state="on" if enabled else "off"),
            ),
            ephemeral=True,
        )

    @masterlog.command(name="view", description="View master log configuration")
    @owner_only()
    async def ml_view(self, interaction: discord.Interaction) -> None:
        lang = await self._lang(interaction.guild) if interaction.guild else "en"
        g = await self.bot.db.get_global_settings()
        body = (
            f"**Hub guild:** `{g.get('master_hub_guild_id')}`\n"
            f"**Enabled:** {bool(g.get('master_enabled'))}\n"
            f"**Defaults:** `{g.get('master_defaults')}`\n"
            f"**Per-server map:** `{g.get('master_server_map')}`\n"
            f"**Whitelist:** `{g.get('master_whitelist')}`"
        )
        await interaction.response.send_message(embed=info_embed("Master log", body), ephemeral=True)

    @masterlog.command(name="reset", description="Reset master log configuration")
    @owner_only()
    async def ml_reset(self, interaction: discord.Interaction) -> None:
        await self.bot.db.update_global_settings(
            master_hub_guild_id=None,
            master_enabled=0,
            master_defaults=None,
            master_server_map=None,
            master_whitelist=None,
        )
        await interaction.response.send_message(embed=ok_embed("Master log", "Reset."), ephemeral=True)

    @masterlog.command(name="default-set", description="Global fallback channel per log type on hub")
    @owner_only()
    async def ml_default_set(
        self,
        interaction: discord.Interaction,
        log_type: str,
        channel: discord.TextChannel,
    ) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_defaults")
        try:
            defs = json.loads(raw) if raw else {}
        except Exception:
            defs = {}
        defs[log_type] = channel.id
        await self.bot.db.update_global_settings(master_defaults=json.dumps(defs))
        await interaction.response.send_message(
            embed=ok_embed("Master log", f"`{log_type}` → {channel.mention}"),
            ephemeral=True,
        )

    @masterlog.command(name="default-remove", description="Remove a global default")
    @owner_only()
    async def ml_default_remove(self, interaction: discord.Interaction, log_type: str) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_defaults")
        try:
            defs = json.loads(raw) if raw else {}
        except Exception:
            defs = {}
        defs.pop(log_type, None)
        await self.bot.db.update_global_settings(master_defaults=json.dumps(defs))
        await interaction.response.send_message(embed=ok_embed("Master log", "Removed."), ephemeral=True)

    @masterlog.command(name="server-set", description="Map a source guild log type to hub channel")
    @owner_only()
    async def ml_server_set(
        self,
        interaction: discord.Interaction,
        source_guild_id: str,
        log_type: str,
        channel: discord.TextChannel,
    ) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_server_map")
        try:
            smap = json.loads(raw) if raw else {}
        except Exception:
            smap = {}
        if source_guild_id not in smap:
            smap[source_guild_id] = {}
        smap[source_guild_id][log_type] = channel.id
        await self.bot.db.update_global_settings(master_server_map=json.dumps(smap))
        await interaction.response.send_message(embed=ok_embed("Master log", "Mapped."), ephemeral=True)

    @masterlog.command(name="server-view", description="View mapping for a source guild id")
    @owner_only()
    async def ml_server_view(self, interaction: discord.Interaction, source_guild_id: str) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_server_map")
        try:
            smap = json.loads(raw) if raw else {}
        except Exception:
            smap = {}
        data = smap.get(source_guild_id, {})
        await interaction.response.send_message(
            embed=info_embed("Mapping", str(data)),
            ephemeral=True,
        )

    @masterlog.command(name="server-remove-config", description="Remove mapping for a source guild")
    @owner_only()
    async def ml_server_remove_cfg(self, interaction: discord.Interaction, source_guild_id: str) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_server_map")
        try:
            smap = json.loads(raw) if raw else {}
        except Exception:
            smap = {}
        smap.pop(source_guild_id, None)
        await self.bot.db.update_global_settings(master_server_map=json.dumps(smap))
        await interaction.response.send_message(embed=ok_embed("Master log", "Removed."), ephemeral=True)

    @masterlog.command(name="server-add", description="Whitelist a source guild for forwarding")
    @owner_only()
    async def ml_server_add(self, interaction: discord.Interaction, guild_id: str) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_whitelist")
        try:
            wl = json.loads(raw) if raw else []
        except Exception:
            wl = []
        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message("Invalid ID", ephemeral=True)
            return
        if gid not in wl:
            wl.append(gid)
        await self.bot.db.update_global_settings(master_whitelist=json.dumps(wl))
        await interaction.response.send_message(embed=ok_embed("Whitelist", f"Added `{gid}`."), ephemeral=True)

    @masterlog.command(name="server-remove", description="Remove a guild from whitelist")
    @owner_only()
    async def ml_server_remove(self, interaction: discord.Interaction, guild_id: str) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_whitelist")
        try:
            wl = json.loads(raw) if raw else []
        except Exception:
            wl = []
        try:
            gid = int(guild_id)
        except ValueError:
            await interaction.response.send_message("Invalid ID", ephemeral=True)
            return
        wl = [x for x in wl if x != gid]
        await self.bot.db.update_global_settings(master_whitelist=json.dumps(wl))
        await interaction.response.send_message(embed=ok_embed("Whitelist", "Removed."), ephemeral=True)

    @masterlog.command(name="server-list", description="List whitelisted source guilds")
    @owner_only()
    async def ml_server_list(self, interaction: discord.Interaction) -> None:
        g = await self.bot.db.get_global_settings()
        raw = g.get("master_whitelist")
        try:
            wl = json.loads(raw) if raw else []
        except Exception:
            wl = []
        await interaction.response.send_message(
            embed=info_embed("Whitelist", ", ".join(f"`{x}`" for x in wl) or "—"),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(MasterlogCog(bot))  # type: ignore[arg-type]
