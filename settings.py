"""Guild settings: language, etc."""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from bot.embeds import err_embed, info_embed, ok_embed
from bot.i18n import t


class SettingsCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="language", description="Set or view the server UI language (English / French)")
    @app_commands.describe(
        locale="Language: en (English) or fr (French). Leave empty to view current."
    )
    @app_commands.choices(
        locale=[
            app_commands.Choice(name="English", value="en"),
            app_commands.Choice(name="Français", value="fr"),
        ]
    )
    async def language(
        self,
        interaction: discord.Interaction,
        locale: app_commands.Choice[str] | None = None,
    ) -> None:
        assert interaction.guild
        if not interaction.user.guild_permissions.manage_guild:
            lang = await self.bot.db.get_guild_language(interaction.guild.id)
            await interaction.response.send_message(
                embed=err_embed("Permission", t(lang, "generic.no_perm")), ephemeral=True
            )
            return

        if locale is None:
            lang = await self.bot.db.get_guild_language(interaction.guild.id)
            name = "English" if lang == "en" else "Français"
            await interaction.response.send_message(
                embed=info_embed(
                    "Language", t(lang, "language.current", lang=name)
                ),
                ephemeral=True,
            )
            return

        await self.bot.db.set_guild_language(interaction.guild.id, locale.value)
        name = "English" if locale.value == "en" else "Français"
        await interaction.response.send_message(
            embed=ok_embed(
                "Language",
                t(locale.value, "language.set", lang=name),
            ),
            ephemeral=True,
        )


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(SettingsCog(bot))
