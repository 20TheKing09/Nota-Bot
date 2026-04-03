"""Async SQLite persistence for Nota Bot."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import aiosqlite

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "notabot.db"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DB_PATH
        self._conn: Optional[aiosqlite.Connection] = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA foreign_keys = ON")
        await self._init_schema()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if not self._conn:
            raise RuntimeError("Database not connected")
        return self._conn

    async def _fetchall(self, query: str, params: tuple[Any, ...] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(query, params) as cur:
            rows = await cur.fetchall()
            return list(rows)

    async def _fetchone(
        self, query: str, params: tuple[Any, ...] = ()
    ) -> aiosqlite.Row | None:
        async with self.conn.execute(query, params) as cur:
            return await cur.fetchone()

    async def _init_schema(self) -> None:
        await self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS guild_settings (
                guild_id INTEGER PRIMARY KEY,
                language TEXT NOT NULL DEFAULT 'en',
                raid_mode INTEGER NOT NULL DEFAULT 0,
                security_config TEXT,
                bot_channel_id INTEGER,
                confession_channel_id INTEGER,
                confession_log_id INTEGER,
                confession_enabled INTEGER NOT NULL DEFAULT 0,
                welcome_enabled INTEGER NOT NULL DEFAULT 0,
                goodbye_enabled INTEGER NOT NULL DEFAULT 0,
                welcome_channel_ids TEXT,
                goodbye_channel_ids TEXT,
                welcome_message TEXT,
                goodbye_message TEXT,
                welcome_color INTEGER,
                autorole_enabled INTEGER NOT NULL DEFAULT 0,
                autorole_role_id INTEGER,
                autorole_trigger TEXT,
                autorole_ignore_offline INTEGER NOT NULL DEFAULT 0,
                lockdown_active INTEGER NOT NULL DEFAULT 0,
                lockdown_snapshot TEXT,
                hideall_exempt_channel_id INTEGER,
                hideall_snapshot TEXT,
                master_hub_guild_id INTEGER,
                master_enabled INTEGER NOT NULL DEFAULT 0,
                master_defaults TEXT,
                master_server_map TEXT,
                master_whitelist TEXT
            );

            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER NOT NULL,
                reason TEXT,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_warns_guild_user ON warns(guild_id, user_id);

            CREATE TABLE IF NOT EXISTS blacklist (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                moderator_id INTEGER,
                reason TEXT,
                created_at TEXT NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS level_data (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                xp INTEGER NOT NULL DEFAULT 0,
                voice_seconds INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS level_config (
                guild_id INTEGER PRIMARY KEY,
                msg_xp INTEGER NOT NULL DEFAULT 15,
                msg_cooldown REAL NOT NULL DEFAULT 60.0,
                vocal_xp_per_min REAL NOT NULL DEFAULT 5.0,
                levelup_channel_id INTEGER,
                levelup_enabled INTEGER NOT NULL DEFAULT 1,
                levelup_message TEXT
            );

            CREATE TABLE IF NOT EXISTS log_channels (
                guild_id INTEGER NOT NULL,
                log_type TEXT NOT NULL,
                channel_id INTEGER NOT NULL,
                PRIMARY KEY (guild_id, log_type)
            );

            CREATE TABLE IF NOT EXISTS temp_roles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                role_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_temp_roles_exp ON temp_roles(expires_at);

            CREATE TABLE IF NOT EXISTS role_locks (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                locked INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS whitelist_users (
                user_id INTEGER PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS message_xp_cooldown (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                last_at REAL NOT NULL,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS backups_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                filename TEXT NOT NULL,
                scope TEXT NOT NULL,
                created_at TEXT NOT NULL,
                label TEXT
            );

            CREATE TABLE IF NOT EXISTS global_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                master_hub_guild_id INTEGER,
                master_enabled INTEGER NOT NULL DEFAULT 0,
                master_defaults TEXT,
                master_server_map TEXT,
                master_whitelist TEXT
            );
            INSERT OR IGNORE INTO global_settings (id) VALUES (1);

            CREATE TABLE IF NOT EXISTS economy_wallet (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                balance INTEGER NOT NULL DEFAULT 0,
                last_daily TEXT,
                PRIMARY KEY (guild_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS economy_config (
                guild_id INTEGER PRIMARY KEY,
                currency_name TEXT NOT NULL DEFAULT 'coin',
                currency_symbol TEXT NOT NULL DEFAULT '🪙',
                daily_base INTEGER NOT NULL DEFAULT 100
            );

            CREATE TABLE IF NOT EXISTS ticket_settings (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                support_role_id INTEGER,
                transcript_channel_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS tickets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                channel_id INTEGER NOT NULL UNIQUE,
                status TEXT NOT NULL DEFAULT 'open',
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tickets_guild_user ON tickets(guild_id, user_id);
            """
        )
        await self.conn.commit()

    async def get_guild_language(self, guild_id: int) -> str:
        row = await self._fetchone(
            "SELECT language FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        if not row:
            return "en"
        return row["language"] or "en"

    async def set_guild_language(self, guild_id: int, language: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO guild_settings (guild_id, language) VALUES (?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET language = excluded.language
            """,
            (guild_id, language),
        )
        await self.conn.commit()

    async def get_or_create_guild_row(self, guild_id: int) -> dict[str, Any]:
        r = await self._fetchone("SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,))
        if r:
            return dict(r)
        await self.conn.execute(
            "INSERT INTO guild_settings (guild_id) VALUES (?)", (guild_id,)
        )
        await self.conn.commit()
        r2 = await self._fetchone(
            "SELECT * FROM guild_settings WHERE guild_id = ?", (guild_id,)
        )
        return dict(r2) if r2 else {}

    async def update_guild_settings(self, guild_id: int, **fields: Any) -> None:
        if not fields:
            return
        await self.get_or_create_guild_row(guild_id)
        keys = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        values.append(guild_id)
        await self.conn.execute(
            f"UPDATE guild_settings SET {keys} WHERE guild_id = ?", values
        )
        await self.conn.commit()

    # --- Warns ---
    async def add_warn(
        self, guild_id: int, user_id: int, moderator_id: int, reason: str | None
    ) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO warns (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, user_id, moderator_id, reason, _utc_now()),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def get_warns(self, guild_id: int, user_id: int) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT * FROM warns WHERE guild_id = ? AND user_id = ? ORDER BY id DESC
            """,
            (guild_id, user_id),
        )
        return [dict(r) for r in rows]

    async def clear_warns(self, guild_id: int, user_id: int) -> int:
        cur = await self.conn.execute(
            "DELETE FROM warns WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()
        return int(cur.rowcount or 0)

    # --- Blacklist ---
    async def add_blacklist(
        self,
        guild_id: int,
        user_id: int,
        moderator_id: int | None,
        reason: str | None,
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO blacklist (guild_id, user_id, moderator_id, reason, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                moderator_id = excluded.moderator_id,
                reason = excluded.reason,
                created_at = excluded.created_at
            """,
            (guild_id, user_id, moderator_id, reason, _utc_now()),
        )
        await self.conn.commit()

    async def remove_blacklist(self, guild_id: int, user_id: int) -> bool:
        cur = await self.conn.execute(
            "DELETE FROM blacklist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()
        return cur.rowcount > 0

    async def list_blacklist(self, guild_id: int) -> list[dict[str, Any]]:
        rows = await self._fetchall("SELECT * FROM blacklist WHERE guild_id = ?", (guild_id,))
        return [dict(r) for r in rows]

    async def is_blacklisted(self, guild_id: int, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM blacklist WHERE guild_id = ? AND user_id = ? LIMIT 1",
            (guild_id, user_id),
        )
        return row is not None

    # --- Level ---
    async def get_level_row(self, guild_id: int, user_id: int) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT * FROM level_data WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row:
            return dict(row)
        return {"guild_id": guild_id, "user_id": user_id, "xp": 0, "voice_seconds": 0}

    async def set_level_xp(self, guild_id: int, user_id: int, xp: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO level_data (guild_id, user_id, xp) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET xp = excluded.xp
            """,
            (guild_id, user_id, xp),
        )
        await self.conn.commit()

    async def add_level_xp(self, guild_id: int, user_id: int, delta: int) -> int:
        row = await self.get_level_row(guild_id, user_id)
        new_xp = max(0, row.get("xp", 0) + delta)
        await self.set_level_xp(guild_id, user_id, new_xp)
        return new_xp

    async def add_voice_seconds(self, guild_id: int, user_id: int, seconds: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO level_data (guild_id, user_id, voice_seconds) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                voice_seconds = level_data.voice_seconds + excluded.voice_seconds
            """,
            (guild_id, user_id, seconds),
        )
        await self.conn.commit()

    async def reset_level_member(self, guild_id: int, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM level_data WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        await self.conn.commit()

    async def leaderboard(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT user_id, xp FROM level_data WHERE guild_id = ?
            ORDER BY xp DESC LIMIT ?
            """,
            (guild_id, limit),
        )
        return [dict(r) for r in rows]

    async def vleaderboard(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT user_id, voice_seconds FROM level_data WHERE guild_id = ?
            ORDER BY voice_seconds DESC LIMIT ?
            """,
            (guild_id, limit),
        )
        return [dict(r) for r in rows]

    async def get_level_config(self, guild_id: int) -> dict[str, Any]:
        row = await self._fetchone("SELECT * FROM level_config WHERE guild_id = ?", (guild_id,))
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "msg_xp": 15,
            "msg_cooldown": 60.0,
            "vocal_xp_per_min": 5.0,
            "levelup_channel_id": None,
            "levelup_enabled": 1,
            "levelup_message": None,
        }

    async def upsert_level_config(self, guild_id: int, **fields: Any) -> None:
        base = await self.get_level_config(guild_id)
        base.update({k: v for k, v in fields.items() if v is not None})
        await self.conn.execute(
            """
            INSERT INTO level_config (
                guild_id, msg_xp, msg_cooldown, vocal_xp_per_min,
                levelup_channel_id, levelup_enabled, levelup_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                msg_xp = excluded.msg_xp,
                msg_cooldown = excluded.msg_cooldown,
                vocal_xp_per_min = excluded.vocal_xp_per_min,
                levelup_channel_id = excluded.levelup_channel_id,
                levelup_enabled = excluded.levelup_enabled,
                levelup_message = excluded.levelup_message
            """,
            (
                guild_id,
                base.get("msg_xp", 15),
                base.get("msg_cooldown", 60.0),
                base.get("vocal_xp_per_min", 5.0),
                base.get("levelup_channel_id"),
                base.get("levelup_enabled", 1),
                base.get("levelup_message"),
            ),
        )
        await self.conn.commit()

    # --- Logs ---
    async def set_log_channel(
        self, guild_id: int, log_type: str, channel_id: int
    ) -> None:
        await self.conn.execute(
            """
            INSERT INTO log_channels (guild_id, log_type, channel_id) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, log_type) DO UPDATE SET channel_id = excluded.channel_id
            """,
            (guild_id, log_type, channel_id),
        )
        await self.conn.commit()

    async def remove_log_channel(self, guild_id: int, log_type: str) -> None:
        await self.conn.execute(
            "DELETE FROM log_channels WHERE guild_id = ? AND log_type = ?",
            (guild_id, log_type),
        )
        await self.conn.commit()

    async def get_log_channels(self, guild_id: int) -> dict[str, int]:
        rows = await self._fetchall(
            "SELECT log_type, channel_id FROM log_channels WHERE guild_id = ?",
            (guild_id,),
        )
        return {r["log_type"]: r["channel_id"] for r in rows}

    # --- Whitelist (bot owner feature) ---
    async def whitelist_add(self, user_id: int) -> None:
        await self.conn.execute(
            "INSERT OR IGNORE INTO whitelist_users (user_id) VALUES (?)", (user_id,)
        )
        await self.conn.commit()

    async def whitelist_remove(self, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM whitelist_users WHERE user_id = ?", (user_id,)
        )
        await self.conn.commit()

    async def whitelist_list(self) -> list[int]:
        rows = await self._fetchall("SELECT user_id FROM whitelist_users")
        return [r["user_id"] for r in rows]

    async def is_whitelisted(self, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM whitelist_users WHERE user_id = ? LIMIT 1", (user_id,)
        )
        return row is not None

    # --- Temp roles ---
    async def add_temp_role(
        self, guild_id: int, user_id: int, role_id: int, expires_at: str
    ) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO temp_roles (guild_id, user_id, role_id, expires_at)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, user_id, role_id, expires_at),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def temp_roles_for_member(
        self, guild_id: int, user_id: int
    ) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT * FROM temp_roles WHERE guild_id = ? AND user_id = ?
            ORDER BY id DESC
            """,
            (guild_id, user_id),
        )
        return [dict(r) for r in rows]

    async def remove_temp_role_entry(self, entry_id: int) -> None:
        await self.conn.execute("DELETE FROM temp_roles WHERE id = ?", (entry_id,))
        await self.conn.commit()

    async def due_temp_roles(self, now_iso: str) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM temp_roles WHERE expires_at <= ?", (now_iso,)
        )
        return [dict(r) for r in rows]

    # --- Role lock ---
    async def set_role_lock(self, guild_id: int, user_id: int, locked: bool) -> None:
        await self.conn.execute(
            """
            INSERT INTO role_locks (guild_id, user_id, locked) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET locked = excluded.locked
            """,
            (guild_id, user_id, 1 if locked else 0),
        )
        await self.conn.commit()

    async def is_role_locked(self, guild_id: int, user_id: int) -> bool:
        row = await self._fetchone(
            "SELECT locked FROM role_locks WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        return bool(row and row["locked"])

    # --- XP cooldown ---
    async def get_msg_cooldown(self, guild_id: int, user_id: int) -> float | None:
        row = await self._fetchone(
            "SELECT last_at FROM message_xp_cooldown WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if not row:
            return None
        return float(row["last_at"])

    async def set_msg_cooldown(self, guild_id: int, user_id: int, last_at: float) -> None:
        await self.conn.execute(
            """
            INSERT INTO message_xp_cooldown (guild_id, user_id, last_at) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET last_at = excluded.last_at
            """,
            (guild_id, user_id, last_at),
        )
        await self.conn.commit()

    # --- Backup meta ---
    async def add_backup_meta(
        self,
        guild_id: int,
        filename: str,
        scope: str,
        label: str | None = None,
    ) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO backups_meta (guild_id, filename, scope, created_at, label)
            VALUES (?, ?, ?, ?, ?)
            """,
            (guild_id, filename, scope, _utc_now(), label),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def list_backups(self, guild_id: int) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM backups_meta WHERE guild_id = ? ORDER BY id DESC",
            (guild_id,),
        )
        return [dict(r) for r in rows]

    async def rename_backup(self, backup_id: int, guild_id: int, new_label: str) -> bool:
        cur = await self.conn.execute(
            """
            UPDATE backups_meta SET label = ? WHERE id = ? AND guild_id = ?
            """,
            (new_label, backup_id, guild_id),
        )
        await self.conn.commit()
        return int(cur.rowcount or 0) > 0

    async def get_global_settings(self) -> dict[str, Any]:
        row = await self._fetchone("SELECT * FROM global_settings WHERE id = 1", ())
        if row:
            return dict(row)
        return {
            "id": 1,
            "master_hub_guild_id": None,
            "master_enabled": 0,
            "master_defaults": None,
            "master_server_map": None,
            "master_whitelist": None,
        }

    async def update_global_settings(self, **fields: Any) -> None:
        if not fields:
            return
        keys = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values())
        values.append(1)
        await self.conn.execute(
            f"UPDATE global_settings SET {keys} WHERE id = ?", values
        )
        await self.conn.commit()

    # --- Economy ---
    async def get_economy_config(self, guild_id: int) -> dict[str, Any]:
        row = await self._fetchone("SELECT * FROM economy_config WHERE guild_id = ?", (guild_id,))
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "currency_name": "coin",
            "currency_symbol": "🪙",
            "daily_base": 100,
        }

    async def upsert_economy_config(self, guild_id: int, **fields: Any) -> None:
        base = await self.get_economy_config(guild_id)
        base.update({k: v for k, v in fields.items() if v is not None})
        await self.conn.execute(
            """
            INSERT INTO economy_config (guild_id, currency_name, currency_symbol, daily_base)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                currency_name = excluded.currency_name,
                currency_symbol = excluded.currency_symbol,
                daily_base = excluded.daily_base
            """,
            (
                guild_id,
                base.get("currency_name", "coin"),
                base.get("currency_symbol", "🪙"),
                base.get("daily_base", 100),
            ),
        )
        await self.conn.commit()

    async def get_wallet(self, guild_id: int, user_id: int) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT * FROM economy_wallet WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        )
        if row:
            return dict(row)
        return {"guild_id": guild_id, "user_id": user_id, "balance": 0, "last_daily": None}

    async def set_balance(self, guild_id: int, user_id: int, balance: int) -> None:
        await self.conn.execute(
            """
            INSERT INTO economy_wallet (guild_id, user_id, balance) VALUES (?, ?, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET balance = excluded.balance
            """,
            (guild_id, user_id, max(0, balance)),
        )
        await self.conn.commit()

    async def add_balance(self, guild_id: int, user_id: int, delta: int) -> int:
        w = await self.get_wallet(guild_id, user_id)
        new_b = max(0, int(w.get("balance") or 0) + delta)
        await self.set_balance(guild_id, user_id, new_b)
        return new_b

    async def set_last_daily(self, guild_id: int, user_id: int, iso: str) -> None:
        await self.conn.execute(
            """
            INSERT INTO economy_wallet (guild_id, user_id, balance, last_daily) VALUES (?, ?, 0, ?)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET last_daily = excluded.last_daily
            """,
            (guild_id, user_id, iso),
        )
        await self.conn.commit()

    async def economy_leaderboard(self, guild_id: int, limit: int = 10) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            """
            SELECT user_id, balance FROM economy_wallet WHERE guild_id = ?
            ORDER BY balance DESC LIMIT ?
            """,
            (guild_id, limit),
        )
        return [dict(r) for r in rows]

    # --- Tickets ---
    async def get_ticket_settings(self, guild_id: int) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT * FROM ticket_settings WHERE guild_id = ?", (guild_id,)
        )
        if row:
            return dict(row)
        return {
            "guild_id": guild_id,
            "category_id": None,
            "support_role_id": None,
            "transcript_channel_id": None,
        }

    async def upsert_ticket_settings(self, guild_id: int, **fields: Any) -> None:
        base = await self.get_ticket_settings(guild_id)
        base.update({k: v for k, v in fields.items()})
        await self.conn.execute(
            """
            INSERT INTO ticket_settings (guild_id, category_id, support_role_id, transcript_channel_id)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(guild_id) DO UPDATE SET
                category_id = excluded.category_id,
                support_role_id = excluded.support_role_id,
                transcript_channel_id = excluded.transcript_channel_id
            """,
            (
                guild_id,
                base.get("category_id"),
                base.get("support_role_id"),
                base.get("transcript_channel_id"),
            ),
        )
        await self.conn.commit()

    async def get_open_ticket(self, guild_id: int, user_id: int) -> dict[str, Any] | None:
        row = await self._fetchone(
            """
            SELECT * FROM tickets WHERE guild_id = ? AND user_id = ? AND status = 'open'
            LIMIT 1
            """,
            (guild_id, user_id),
        )
        return dict(row) if row else None

    async def add_ticket(self, guild_id: int, user_id: int, channel_id: int) -> int:
        cur = await self.conn.execute(
            """
            INSERT INTO tickets (guild_id, user_id, channel_id, status, created_at)
            VALUES (?, ?, ?, 'open', ?)
            """,
            (guild_id, user_id, channel_id, _utc_now()),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def close_ticket_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        row = await self._fetchone(
            "SELECT * FROM tickets WHERE channel_id = ? AND status = 'open'", (channel_id,)
        )
        if not row:
            return None
        await self.conn.execute(
            "UPDATE tickets SET status = 'closed' WHERE channel_id = ?", (channel_id,)
        )
        await self.conn.commit()
        return dict(row)

    async def get_ticket_by_channel(self, channel_id: int) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        return dict(row) if row else None
