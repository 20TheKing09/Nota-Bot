"""Consistent embed styling for Nota Bot."""

from __future__ import annotations

import discord

ACCENT = 0x5865F2
SUCCESS = 0x57F287
WARNING = 0xFEE75C
ERROR = 0xED4245
INFO = 0x5865F2
LEVEL = 0xEB459E
MOD = 0xED4245
WELCOME = 0x9B84EC


def ok_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=SUCCESS)


def err_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=ERROR)


def info_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=INFO)


def warn_embed(title: str, description: str = "") -> discord.Embed:
    return discord.Embed(title=title, description=description or None, color=WARNING)


def branded_footer(text: str = "Nota Bot") -> str:
    return text


def level_embed(title: str, description: str) -> discord.Embed:
    e = discord.Embed(title=title, description=description, color=LEVEL)
    e.set_footer(text=branded_footer())
    return e
