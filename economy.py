"""Server economy: virtual currency, daily, transfers."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import err_embed, info_embed, ok_embed
from bot.i18n import t

if TYPE_CHECKING:
    from bot.core import NotaBot


def _today_utc() -> datetime.date:
    return datetime.now(timezone.utc).date()


def _parse_daily_date(raw: str | None) -> datetime.date | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.date()
    except ValueError:
        return None


class EconomyCog(commands.Cog):
    economy = app_commands.Group(
        name="economy",
        description="Virtual currency (per server)",
    )

    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def _lang(self, g: discord.Guild) -> str:
        return await self.bot.db.get_guild_language(g.id)

    def _fmt_money(self, cfg: dict, amount: int) -> str:
        sym = cfg.get("currency_symbol") or "🪙"
        name = cfg.get("currency_name") or "coin"
        return f"{sym} **{amount:,}** {name}"

    @economy.command(name="balance", description="Show your or another member's balance")
    @app_commands.describe(member="Member to check (optional)")
    async def econ_balance(
        self,
        interaction: discord.Interaction,
        member: discord.Member | None = None,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        m = member or interaction.user
        assert isinstance(m, discord.Member)
        w = await self.bot.db.get_wallet(interaction.guild.id, m.id)
        bal = int(w.get("balance") or 0)
        await interaction.response.send_message(
            embed=info_embed(
                "Balance" if lang == "en" else "Solde",
                f"{m.mention}: {self._fmt_money(cfg, bal)}",
            )
        )

    @economy.command(name="daily", description="Claim your daily reward (once per UTC day)")
    async def econ_daily(self, interaction: discord.Interaction) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        base = int(cfg.get("daily_base") or 100)
        w = await self.bot.db.get_wallet(interaction.guild.id, interaction.user.id)
        last = _parse_daily_date(w.get("last_daily"))
        today = _today_utc()
        if last == today:
            msg = (
                "You already claimed your daily today. Come back tomorrow!"
                if lang == "en"
                else "Tu as déjà récupéré ton daily aujourd'hui. Reviens demain !"
            )
            await interaction.response.send_message(embed=err_embed("Daily", msg), ephemeral=True)
            return
        now_iso = datetime.now(timezone.utc).isoformat()
        await self.bot.db.add_balance(interaction.guild.id, interaction.user.id, base)
        await self.bot.db.set_last_daily(interaction.guild.id, interaction.user.id, now_iso)
        new_w = await self.bot.db.get_wallet(interaction.guild.id, interaction.user.id)
        bal = int(new_w.get("balance") or 0)
        msg = (
            f"You received {self._fmt_money(cfg, base)}. Total: {self._fmt_money(cfg, bal)}."
            if lang == "en"
            else f"Tu as reçu {self._fmt_money(cfg, base)}. Total : {self._fmt_money(cfg, bal)}."
        )
        await interaction.response.send_message(embed=ok_embed("Daily", msg))

    @economy.command(name="pay", description="Pay another member")
    @app_commands.describe(member="Recipient", amount="Amount to send")
    async def econ_pay(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 10_000_000],
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        if member.id == interaction.user.id:
            await interaction.response.send_message(
                embed=err_embed("Pay", "You cannot pay yourself."),
                ephemeral=True,
            )
            return
        if member.bot:
            await interaction.response.send_message(
                embed=err_embed("Pay", "Cannot pay a bot."),
                ephemeral=True,
            )
            return
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        w = await self.bot.db.get_wallet(interaction.guild.id, interaction.user.id)
        bal = int(w.get("balance") or 0)
        if bal < amount:
            msg = "Insufficient balance." if lang == "en" else "Solde insuffisant."
            await interaction.response.send_message(embed=err_embed("Pay", msg), ephemeral=True)
            return
        await self.bot.db.add_balance(interaction.guild.id, interaction.user.id, -amount)
        await self.bot.db.add_balance(interaction.guild.id, member.id, amount)
        msg = (
            f"You sent {self._fmt_money(cfg, amount)} to {member.mention}."
            if lang == "en"
            else f"Tu as envoyé {self._fmt_money(cfg, amount)} à {member.mention}."
        )
        await interaction.response.send_message(embed=ok_embed("Pay", msg))

    @economy.command(name="leaderboard", description="Richest members on this server")
    @app_commands.describe(limit="How many users (5–25)")
    async def econ_leaderboard(
        self,
        interaction: discord.Interaction,
        limit: app_commands.Range[int, 5, 25] = 10,
    ) -> None:
        assert interaction.guild
        lang = await self._lang(interaction.guild)
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        rows = await self.bot.db.economy_leaderboard(interaction.guild.id, limit)
        title = "Economy leaderboard" if lang == "en" else "Classement économie"
        if not rows:
            await interaction.response.send_message(embed=info_embed(title, "—"))
            return
        lines = []
        for i, r in enumerate(rows, 1):
            u = interaction.guild.get_member(r["user_id"])
            name = u.display_name if u else str(r["user_id"])
            lines.append(f"`{i}.` {name} — {self._fmt_money(cfg, int(r['balance']))}")
        await interaction.response.send_message(embed=info_embed(title, "\n".join(lines)))

    @economy.command(name="give", description="Add currency to a member (administrator)")
    @app_commands.describe(member="Member", amount="Amount to add")
    @app_commands.default_permissions(administrator=True)
    async def econ_give(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000_000],
    ) -> None:
        assert interaction.guild
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        await self.bot.db.add_balance(interaction.guild.id, member.id, amount)
        await interaction.response.send_message(
            embed=ok_embed("Economy", f"Added {self._fmt_money(cfg, amount)} to {member.mention}."),
            ephemeral=True,
        )

    @economy.command(name="take", description="Remove currency from a member (administrator)")
    @app_commands.describe(member="Member", amount="Amount to remove")
    @app_commands.default_permissions(administrator=True)
    async def econ_take(
        self,
        interaction: discord.Interaction,
        member: discord.Member,
        amount: app_commands.Range[int, 1, 1_000_000_000],
    ) -> None:
        assert interaction.guild
        cfg = await self.bot.db.get_economy_config(interaction.guild.id)
        await self.bot.db.add_balance(interaction.guild.id, member.id, -amount)
        await interaction.response.send_message(
            embed=ok_embed("Economy", f"Removed {self._fmt_money(cfg, amount)} from {member.mention}."),
            ephemeral=True,
        )

    @economy.command(name="currency", description="Set currency name, symbol, and daily reward (administrator)")
    @app_commands.describe(
        name="Currency name (e.g. nota coin)",
        symbol="Emoji or short symbol",
        daily="Daily reward amount",
    )
    @app_commands.default_permissions(administrator=True)
    async def econ_currency(
        self,
        interaction: discord.Interaction,
        name: str,
        symbol: str,
        daily: app_commands.Range[int, 1, 1_000_000],
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_economy_config(
            interaction.guild.id,
            currency_name=name[:40],
            currency_symbol=symbol[:8],
            daily_base=daily,
        )
        await interaction.response.send_message(
            embed=ok_embed("Economy", f"Currency: **{name}** {symbol} · Daily: **{daily}**."),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(EconomyCog(bot))  # type: ignore[arg-type]
