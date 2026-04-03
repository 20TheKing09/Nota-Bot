"""Dispatch log embeds to configured channels and optional master hub."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot.core import NotaBot


LOG_LABELS = {
    "log_msg": "Messages",
    "log_voc": "Voice",
    "log_imp": "Important",
    "log_inv": "Invites",
    "log_sal": "Channels",
    "log_rol": "Roles",
    "log_mod": "Moderation",
    "log_sta": "Status",
}


async def dispatch_log(
    bot: "NotaBot",
    guild: discord.Guild,
    log_type: str,
    embed: discord.Embed,
) -> None:
    channels = await bot.db.get_log_channels(guild.id)
    cid = channels.get(log_type)
    if cid:
        ch = guild.get_channel(cid)
        if isinstance(ch, discord.TextChannel):
            try:
                await ch.send(embed=embed)
            except discord.HTTPException:
                pass

    glob = await bot.db.get_global_settings()
    if not glob.get("master_enabled") or not glob.get("master_hub_guild_id"):
        return
    raw_wl = glob.get("master_whitelist")
    try:
        whitelist = json.loads(raw_wl) if raw_wl else []
    except Exception:
        whitelist = []
    if whitelist and guild.id not in whitelist:
        return
    hub_id = int(glob["master_hub_guild_id"])
    hub = bot.get_guild(hub_id)
    if not hub:
        return
    smap_raw = glob.get("master_server_map")
    try:
        smap = json.loads(smap_raw) if smap_raw else {}
    except Exception:
        smap = {}
    target_id = None
    per_guild = smap.get(str(guild.id))
    if isinstance(per_guild, dict):
        target_id = per_guild.get(log_type)
    if not target_id:
        defs_raw = glob.get("master_defaults")
        try:
            defs = json.loads(defs_raw) if defs_raw else {}
        except Exception:
            defs = {}
        target_id = defs.get(log_type)
    if not target_id:
        return
    ch = hub.get_channel(int(target_id))
    if isinstance(ch, discord.TextChannel):
        embed.set_footer(text=f"{guild.name} · {LOG_LABELS.get(log_type, log_type)}")
        try:
            await ch.send(embed=embed)
        except discord.HTTPException:
            pass
