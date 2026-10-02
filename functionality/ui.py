# functionality/ui.py
"""Reusable UI pieces for slash commands."""
import re
from datetime import timedelta
from typing import Optional

import discord

_DURATION_RE = re.compile(r"(\d+)\s*(w|d|h|m|s)", re.IGNORECASE)
_UNIT_SECONDS = {"w": 604800, "d": 86400, "h": 3600, "m": 60, "s": 1}


def parse_duration(text: str) -> Optional[timedelta]:
    """Parse strings like '30m', '1h30m', '2d', '1w'. Returns None if invalid."""
    text = (text or "").strip().replace(" ", "")
    if not text:
        return None
    if text.isdigit():
        return timedelta(minutes=int(text))
    matches = list(_DURATION_RE.finditer(text))
    if not matches or "".join(m.group(0) for m in matches).lower() != text.lower():
        return None
    seconds = sum(int(m.group(1)) * _UNIT_SECONDS[m.group(2).lower()] for m in matches)
    return timedelta(seconds=seconds) if seconds > 0 else None


def format_duration(td: timedelta) -> str:
    seconds = int(td.total_seconds())
    parts = []
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60), ("s", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size}{unit}")
            seconds %= size
    return " ".join(parts) or "0s"


def chunk_lines(lines: list[str], limit: int = 4000) -> list[str]:
    """Join lines into chunks that each fit within `limit` characters."""
    chunks, current = [], ""
    for line in lines:
        while len(line) > limit:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks or [""]


async def reply(interaction: discord.Interaction, content: str = None, *, ephemeral: bool = True, **kwargs):
    """Respond to an interaction whether or not it has already been responded to/deferred."""
    if interaction.response.is_done():
        return await interaction.followup.send(content, ephemeral=ephemeral, **kwargs)
    return await interaction.response.send_message(content, ephemeral=ephemeral, **kwargs)


class Paginator(discord.ui.View):
    """Button pagination over a list of embeds."""

    def __init__(self, pages: list[discord.Embed], author_id: Optional[int] = None, timeout: float = 180):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.author_id = author_id
        self.index = 0
        self.message: Optional[discord.Message] = None
        if len(pages) > 1:
            for i, page in enumerate(pages, 1):
                footer = page.footer.text if page.footer and page.footer.text else ""
                page.set_footer(text=f"Page {i}/{len(pages)}" + (f" • {footer}" if footer else ""))
        self._sync_buttons()

    def _sync_buttons(self):
        last = len(self.pages) - 1
        self.first.disabled = self.prev.disabled = self.index == 0
        self.next.disabled = self.last.disabled = self.index >= last

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if self.author_id and interaction.user.id != self.author_id:
            await interaction.response.send_message("These buttons aren't for you.", ephemeral=True)
            return False
        return True

    async def _go(self, interaction: discord.Interaction, index: int):
        self.index = max(0, min(index, len(self.pages) - 1))
        self._sync_buttons()
        await interaction.response.edit_message(embed=self.pages[self.index], view=self)

    @discord.ui.button(label="≪", style=discord.ButtonStyle.secondary)
    async def first(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, 0)

    @discord.ui.button(label="◀", style=discord.ButtonStyle.primary)
    async def prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, self.index - 1)

    @discord.ui.button(label="▶", style=discord.ButtonStyle.primary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, self.index + 1)

    @discord.ui.button(label="≫", style=discord.ButtonStyle.secondary)
    async def last(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._go(interaction, len(self.pages) - 1)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    async def send(self, interaction: discord.Interaction, *, ephemeral: bool = False):
        """Send the first page (with buttons only if there is more than one page)."""
        view = self if len(self.pages) > 1 else discord.utils.MISSING
        if interaction.response.is_done():
            self.message = await interaction.followup.send(embed=self.pages[0], view=view, ephemeral=ephemeral, wait=True)
        else:
            await interaction.response.send_message(embed=self.pages[0], view=view, ephemeral=ephemeral)
            self.message = await interaction.original_response()


class ConfirmView(discord.ui.View):
    """Yes/No confirmation restricted to one user. Check `.value` after `await view.wait()`."""

    def __init__(self, author_id: int, timeout: float = 30):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This isn't your confirmation.", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        await interaction.response.edit_message(view=None)
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)
        self.stop()


def guild_only_cog(cog) -> None:
    """Mark every top-level slash command in a (non-group) cog as server-only."""
    for cmd in cog.get_app_commands():
        cmd.guild_only = True
