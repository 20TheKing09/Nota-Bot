"""Support tickets: panel button, private channel per user."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import ACCENT, err_embed, ok_embed

if TYPE_CHECKING:
    from bot.core import NotaBot

PANEL_CUSTOM_ID = "notabot:tkopen"
CLOSE_CUSTOM_ID = "notabot:tkclose"


def _safe_channel_name(name: str) -> str:
    s = re.sub(r"[^a-z0-9\-]", "", name.lower())[:90]
    return s or "user"


class TicketPanelView(discord.ui.View):
    """Persistent: open ticket (one global custom_id for all servers)."""

    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Open ticket",
        style=discord.ButtonStyle.primary,
        custom_id=PANEL_CUSTOM_ID,
        emoji="🎫",
    )
    async def open_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not interaction.guild or not isinstance(interaction.user, discord.Member):
            await interaction.response.send_message(
                "Use this on a server.", ephemeral=True
            )
            return
        bot = interaction.client
        db = getattr(bot, "db", None)
        if db is None:
            await interaction.response.send_message("Database unavailable.", ephemeral=True)
            return
        settings = await db.get_ticket_settings(interaction.guild.id)
        cat_id = settings.get("category_id")
        if not cat_id:
            await interaction.response.send_message(
                embed=err_embed(
                    "Tickets",
                    "Tickets are not configured. Ask an admin to run `/ticket setup`.",
                ),
                ephemeral=True,
            )
            return
        category = interaction.guild.get_channel(int(cat_id))
        if not isinstance(category, discord.CategoryChannel):
            await interaction.response.send_message(
                embed=err_embed("Tickets", "Invalid category."),
                ephemeral=True,
            )
            return
        existing = await db.get_open_ticket(interaction.guild.id, interaction.user.id)
        if existing:
            ch = interaction.guild.get_channel(existing["channel_id"])
            if ch:
                await interaction.response.send_message(
                    f"You already have an open ticket: {ch.mention}",
                    ephemeral=True,
                )
                return
        support_role_id = settings.get("support_role_id")
        overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            ),
            interaction.guild.me: discord.PermissionOverwrite(
                view_channel=True, send_messages=True, manage_channels=True
            ),
        }
        if support_role_id:
            role = interaction.guild.get_role(int(support_role_id))
            if role:
                overwrites[role] = discord.PermissionOverwrite(
                    view_channel=True, send_messages=True, read_message_history=True
                )
        name = f"ticket-{_safe_channel_name(interaction.user.display_name)}"
        try:
            channel = await interaction.guild.create_text_channel(
                name=name[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Ticket by {interaction.user}",
            )
        except discord.HTTPException as e:
            await interaction.response.send_message(
                embed=err_embed("Tickets", str(e)),
                ephemeral=True,
            )
            return
        await db.add_ticket(interaction.guild.id, interaction.user.id, channel.id)
        await interaction.response.send_message(
            embed=ok_embed("Ticket", f"Created {channel.mention}"),
            ephemeral=True,
        )
        welcome = discord.Embed(
            title="Support ticket",
            description=f"{interaction.user.mention}, describe your issue here.\n"
            "Staff can use the button below to close this ticket.",
            color=ACCENT,
        )
        await channel.send(
            embed=welcome,
            view=TicketCloseView(),
        )


class TicketCloseView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Close ticket",
        style=discord.ButtonStyle.danger,
        custom_id=CLOSE_CUSTOM_ID,
        emoji="🔒",
    )
    async def close_ticket(
        self,
        interaction: discord.Interaction,
        button: discord.ui.Button,
    ) -> None:
        if not interaction.guild or not interaction.channel:
            return
        bot = interaction.client
        db = getattr(bot, "db", None)
        if db is None:
            await interaction.response.send_message("Database unavailable.", ephemeral=True)
            return
        row = await db.get_ticket_by_channel(interaction.channel.id)
        if not row or row.get("status") != "open":
            await interaction.response.send_message(
                "This is not an active ticket channel.", ephemeral=True
            )
            return
        can_close = (
            interaction.user.guild_permissions.manage_channels
            or interaction.user.guild_permissions.administrator
            or row["user_id"] == interaction.user.id
        )
        if not can_close:
            await interaction.response.send_message(
                "You cannot close this ticket.", ephemeral=True
            )
            return
        settings = await db.get_ticket_settings(interaction.guild.id)
        transcript_id = settings.get("transcript_channel_id")
        if isinstance(interaction.channel, discord.TextChannel):
            lines = []
            async for msg in interaction.channel.history(limit=50, oldest_first=True):
                lines.append(f"[{msg.created_at:%Y-%m-%d %H:%M}] {msg.author}: {msg.content[:500]}")
            blob = "\n".join(lines)[:3500]
            if transcript_id:
                tch = interaction.guild.get_channel(int(transcript_id))
                if isinstance(tch, discord.TextChannel):
                    try:
                        e = discord.Embed(
                            title="Ticket transcript",
                            description=f"Closed by {interaction.user.mention}\nChannel ID: `{interaction.channel.id}`",
                            color=discord.Color.dark_gray(),
                        )
                        if blob:
                            e.add_field(name="Last messages (preview)", value=blob[:1024], inline=False)
                        await tch.send(embed=e)
                    except discord.HTTPException:
                        pass
        await db.close_ticket_by_channel(interaction.channel.id)
        await interaction.response.send_message("Closing ticket…", ephemeral=True)
        if isinstance(interaction.channel, discord.TextChannel):
            try:
                await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
            except discord.HTTPException:
                pass


class TicketsCog(commands.Cog):
    ticket = app_commands.Group(
        name="ticket",
        description="Support ticket system (manage channels)",
    )

    def __init__(self, bot: NotaBot) -> None:
        self.bot = bot

    async def cog_load(self) -> None:
        self.bot.add_view(TicketPanelView())
        self.bot.add_view(TicketCloseView())

    @ticket.command(name="setup", description="Choose category for new tickets and optional support role")
    @app_commands.describe(
        category="Category where ticket channels are created",
        support_role="Role that can see all tickets",
        transcript_channel="Optional channel for close summaries",
    )
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_setup(
        self,
        interaction: discord.Interaction,
        category: discord.CategoryChannel,
        support_role: discord.Role | None = None,
        transcript_channel: discord.TextChannel | None = None,
    ) -> None:
        assert interaction.guild
        await self.bot.db.upsert_ticket_settings(
            interaction.guild.id,
            category_id=category.id,
            support_role_id=support_role.id if support_role else None,
            transcript_channel_id=transcript_channel.id if transcript_channel else None,
        )
        await interaction.response.send_message(
            embed=ok_embed(
                "Tickets",
                f"Category: {category.mention}\n"
                f"Support role: {support_role.mention if support_role else '—'}\n"
                f"Transcripts: {transcript_channel.mention if transcript_channel else '—'}\n\n"
                "Use `/ticket panel` in a public channel to post the open button.",
            ),
            ephemeral=True,
        )

    @ticket.command(name="panel", description="Post the ticket panel with button in this channel")
    @app_commands.default_permissions(manage_channels=True)
    async def ticket_panel(self, interaction: discord.Interaction) -> None:
        assert interaction.guild and interaction.channel
        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message(
                embed=err_embed("Tickets", "Use in a text channel."),
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="Need help?",
            description="Click the button below to open a private ticket with the staff.",
            color=ACCENT,
        )
        embed.set_footer(text="Nota Bot · tickets")
        await interaction.response.send_message(
            embed=embed,
            view=TicketPanelView(),
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TicketsCog(bot))  # type: ignore[arg-type]
