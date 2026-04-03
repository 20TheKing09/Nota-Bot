"""Owner-only: whitelist, backups, sync, dangerous reset."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiofiles
import discord
from discord import app_commands
from discord.ext import commands

from bot.checks import owner_only
from bot.embeds import err_embed, info_embed, ok_embed, warn_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot

BACKUP_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "backups"


class OwnerCog(commands.Cog):
    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    @app_commands.command(name="sync", description="Re-register slash commands (owner)")
    @owner_only()
    async def sync_cmd(self, interaction: discord.Interaction) -> None:
        lang = "en"
        if interaction.guild:
            lang = await self.bot.db.get_guild_language(interaction.guild.id)
        synced = await self.bot.tree.sync()
        n = len(synced)
        await interaction.response.send_message(
            embed=ok_embed("Sync", t(lang, "owner.sync", n=n)),
            ephemeral=True,
        )

    @app_commands.command(name="whitelist_add", description="Add user to bot-level whitelist")
    @app_commands.describe(user="User")
    @owner_only()
    async def whitelist_add_cmd(self, interaction: discord.Interaction, user: discord.User) -> None:
        lang = await self.bot.db.get_guild_language(interaction.guild.id) if interaction.guild else "en"
        await self.bot.db.whitelist_add(user.id)
        await interaction.response.send_message(
            embed=ok_embed("Whitelist", t(lang, "owner.whitelist.add")),
            ephemeral=True,
        )

    @app_commands.command(name="whitelist_remove", description="Remove user from whitelist")
    @owner_only()
    async def whitelist_remove_cmd(self, interaction: discord.Interaction, user: discord.User) -> None:
        lang = await self.bot.db.get_guild_language(interaction.guild.id) if interaction.guild else "en"
        await self.bot.db.whitelist_remove(user.id)
        await interaction.response.send_message(
            embed=ok_embed("Whitelist", t(lang, "owner.whitelist.remove")),
            ephemeral=True,
        )

    @app_commands.command(name="whitelist_list", description="List whitelisted user IDs")
    @owner_only()
    async def whitelist_list_cmd(self, interaction: discord.Interaction) -> None:
        ids = await self.bot.db.whitelist_list()
        body = ", ".join(f"`{i}`" for i in ids) or "—"
        await interaction.response.send_message(embed=info_embed("Whitelist", body), ephemeral=True)

    @app_commands.command(name="whitelist_clear", description="Clear the whitelist")
    @owner_only()
    async def whitelist_clear_cmd(self, interaction: discord.Interaction) -> None:
        for uid in await self.bot.db.whitelist_list():
            await self.bot.db.whitelist_remove(uid)
        await interaction.response.send_message(embed=ok_embed("Whitelist", "Cleared."), ephemeral=True)

    @app_commands.command(name="whitelist", description="Quick whitelist add (alias)")
    @owner_only()
    async def whitelist_alias(self, interaction: discord.Interaction, user: discord.User) -> None:
        await self.bot.db.whitelist_add(user.id)
        await interaction.response.send_message(embed=ok_embed("Whitelist", f"Added {user}."), ephemeral=True)

    @app_commands.command(name="unwhitelist", description="Quick whitelist remove (alias)")
    @owner_only()
    async def unwhitelist_alias(self, interaction: discord.Interaction, user: discord.User) -> None:
        await self.bot.db.whitelist_remove(user.id)
        await interaction.response.send_message(embed=ok_embed("Whitelist", f"Removed {user}."), ephemeral=True)

    def _serialize_guild(self, guild: discord.Guild, scope: str) -> dict[str, Any]:
        data: dict[str, Any] = {"guild_id": guild.id, "scope": scope, "at": datetime.now(timezone.utc).isoformat()}
        if scope in ("all", "roles"):
            data["roles"] = [
                {
                    "id": r.id,
                    "name": r.name,
                    "color": r.color.value,
                    "permissions": r.permissions.value,
                    "position": r.position,
                    "mentionable": r.mentionable,
                    "hoist": r.hoist,
                }
                for r in guild.roles
                if not r.is_default()
            ]
        if scope in ("all", "channels"):
            data["channels"] = []
            for c in guild.channels:
                data["channels"].append(
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": str(c.type),
                        "position": c.position,
                        "category_id": c.category_id,
                    }
                )
        return data

    @app_commands.command(name="backup_create", description="Create a JSON backup (owner)")
    @app_commands.describe(
        scope="What to include",
        label="Optional label",
    )
    @app_commands.choices(
        scope=[
            app_commands.Choice(name="Everything (metadata)", value="all"),
            app_commands.Choice(name="Roles", value="roles"),
            app_commands.Choice(name="Channels", value="channels"),
        ]
    )
    @owner_only()
    async def backup_create_cmd(
        self,
        interaction: discord.Interaction,
        scope: str,
        label: str | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self.bot.db.get_guild_language(interaction.guild.id)
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        payload = self._serialize_guild(interaction.guild, scope)
        fname = f"backup_{interaction.guild.id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
        path = BACKUP_DIR / fname
        async with aiofiles.open(path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(payload, indent=2))
        await self.bot.db.add_backup_meta(interaction.guild.id, fname, scope, label)
        await interaction.response.send_message(
            embed=ok_embed("Backup", t(lang, "backup.created", name=fname, scope=scope)),
            ephemeral=True,
        )

    @app_commands.command(name="backup_list", description="List backups for this server")
    @owner_only()
    async def backup_list_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self.bot.db.get_guild_language(interaction.guild.id)
        rows = await self.bot.db.list_backups(interaction.guild.id)
        if not rows:
            await interaction.response.send_message(embed=info_embed(t(lang, "backup.list.title"), "—"), ephemeral=True)
            return
        lines = [f"`#{r['id']}` `{r['filename']}` · {r['scope']} · {r.get('label') or '—'}" for r in rows[:15]]
        await interaction.response.send_message(
            embed=info_embed(t(lang, "backup.list.title"), "\n".join(lines)),
            ephemeral=True,
        )

    @app_commands.command(name="backup_rename", description="Rename a backup label")
    @owner_only()
    async def backup_rename_cmd(
        self,
        interaction: discord.Interaction,
        backup_id: int,
        new_label: str,
    ) -> None:
        assert interaction.guild
        lang = await self.bot.db.get_guild_language(interaction.guild.id)
        ok = await self.bot.db.rename_backup(backup_id, interaction.guild.id, new_label[:80])
        if not ok:
            await interaction.response.send_message(embed=err_embed("Error", "Not found."), ephemeral=True)
            return
        await interaction.response.send_message(
            embed=ok_embed("Backup", t(lang, "backup.rename.ok")),
            ephemeral=True,
        )

    @app_commands.command(name="backup_restore", description="Restore roles from backup file (dangerous)")
    @app_commands.describe(backup_id="ID from backup_list")
    @owner_only()
    async def backup_restore_cmd(self, interaction: discord.Interaction, backup_id: int) -> None:
        assert interaction.guild
        rows = await self.bot.db.list_backups(interaction.guild.id)
        meta = next((r for r in rows if r["id"] == backup_id), None)
        if not meta:
            await interaction.response.send_message(embed=err_embed("Error", "Unknown backup."), ephemeral=True)
            return
        path = BACKUP_DIR / meta["filename"]
        if not path.is_file():
            await interaction.response.send_message(embed=err_embed("Error", "File missing."), ephemeral=True)
            return
        async with aiofiles.open(path, "r", encoding="utf-8") as f:
            raw = await f.read()
        data = json.loads(raw)
        roles = data.get("roles") or []
        created = 0
        for rdata in sorted(roles, key=lambda x: x.get("position", 0)):
            try:
                await interaction.guild.create_role(
                    name=rdata.get("name", "restored")[:100],
                    permissions=discord.Permissions(rdata.get("permissions", 0)),
                    color=discord.Color(rdata.get("color", 0)),
                    hoist=bool(rdata.get("hoist")),
                    mentionable=bool(rdata.get("mentionable")),
                    reason="backup restore",
                )
                created += 1
            except discord.HTTPException:
                break
        await interaction.response.send_message(
            embed=warn_embed("Restore", f"Created **{created}** roles (best-effort)."),
            ephemeral=True,
        )

    @app_commands.command(name="server_reset", description="Clear all bot database settings for this server (owner)")
    @owner_only()
    async def server_reset_cmd(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        gid = interaction.guild.id
        await self.bot.db.conn.execute("DELETE FROM guild_settings WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM warns WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM blacklist WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM level_data WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM level_config WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM log_channels WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM temp_roles WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM role_locks WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.execute("DELETE FROM message_xp_cooldown WHERE guild_id = ?", (gid,))
        await self.bot.db.conn.commit()
        await interaction.response.send_message(
            embed=warn_embed("Server reset", "All Nota Bot data for this server was deleted from the database."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(OwnerCog(bot))  # type: ignore[arg-type]
