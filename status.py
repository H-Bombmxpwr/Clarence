# status.py
import json
import random
import discord
from discord.ext import commands, tasks

LYRICS_PATH = "storage/lyrics.json"
STATUS_SPACER = "               "
OWNER_ID = 239605426033786881


def _load_blocks(path: str = LYRICS_PATH):
    """Return list of song blocks [{header, lines}]"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return []

    blocks = []
    for entry in data:
        song = (entry.get("song") or "Unknown").strip()
        artist = (entry.get("artist") or "Unknown").strip()
        header = f"{song} by {artist}"
        lyrics = (entry.get("lyrics") or "").replace("\r", "")
        lines = [ln.strip() for ln in lyrics.split("\n") if ln.strip()]
        if not lines:
            lines = ["(instrumental)"]
        blocks.append({"header": header, "lines": lines})
    return blocks


class Status(commands.Cog):
    """Rotating lyric presence (hidden cog)"""
    __cog_command_attrs__ = {"hidden": True}

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._blocks: list[dict] = []
        self._entries: list[str] = []
        self._map_index_to_block: list[int] = []
        self._map_index_to_line_in_block: list[int] = []
        self._idx: int = 0
        self._last_shown_idx: int = 0

    def _shuffle_blocks(self):
        random.shuffle(self._blocks)

    def _rebuild_entries(self):
        """Flatten blocks into entries and build mapping tables."""
        self._entries = []
        self._map_index_to_block = []
        self._map_index_to_line_in_block = []
        for b_i, block in enumerate(self._blocks):
            self._entries.append(block["header"])
            self._map_index_to_block.append(b_i)
            self._map_index_to_line_in_block.append(-1)
            for l_i, line in enumerate(block["lines"]):
                self._entries.append(line)
                self._map_index_to_block.append(b_i)
                self._map_index_to_line_in_block.append(l_i)
            self._entries.append(STATUS_SPACER)
            self._map_index_to_block.append(b_i)
            self._map_index_to_line_in_block.append(-1)
        if not self._entries:
            self._entries = [STATUS_SPACER]
            self._map_index_to_block = [0]
            self._map_index_to_line_in_block = [-1]
        self._idx %= len(self._entries)
        self._last_shown_idx %= len(self._entries)

    @tasks.loop(seconds=10)
    async def _rotate_status(self):
        if not self._entries:
            self._blocks = _load_blocks()
            self._shuffle_blocks()
            self._rebuild_entries()
        cur = self._entries[self._idx]
        self._last_shown_idx = self._idx
        await self.bot.change_presence(
            activity=discord.Activity(type=discord.ActivityType.listening, name=cur)
        )
        self._idx = (self._idx + 1) % len(self._entries)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self._entries:
            self._blocks = _load_blocks()
            self._shuffle_blocks()
            self._rebuild_entries()
        if not self._rotate_status.is_running():
            self._rotate_status.start()

    @commands.command(name="preview_status")
    async def preview_status(self, ctx: commands.Context, aliases=["ps"]):
        """Show previous, current, and next songs, with current line highlighted red."""
        if not self._entries:
            emb = discord.Embed(
                title="Status Rotation Preview",
                description="No lyrics found in storage/lyrics.json",
                color=0x00A38D,
            )
            return await ctx.send(embed=emb)

        cur_i = self._last_shown_idx
        cur_block = self._map_index_to_block[cur_i]
        cur_line = self._map_index_to_line_in_block[cur_i]
        prev_block = (cur_block - 1) % len(self._blocks)
        next_block = (cur_block + 1) % len(self._blocks)

        def fmt_block(i, highlight_line: int | None = None):
            b = self._blocks[i]
            formatted = [f"__{b['header']}__"]
            for l_i, ln in enumerate(b["lines"]):
                if highlight_line is not None and l_i == highlight_line:
                    # Highlight in red (diff style)
                    formatted.append(f"```diff\n- {ln}\n```")
                else:
                    formatted.append(ln)
            return "\n".join(formatted)

        prev_txt = fmt_block(prev_block)
        cur_txt = fmt_block(cur_block, highlight_line=cur_line if cur_line >= 0 else None)
        next_txt = fmt_block(next_block)

        emb = discord.Embed(
            title="Status Rotation (Preview)",
            description=f"{prev_txt}\n\n{cur_txt}\n\n{next_txt}",
            color=0x00A38D,
        )
        await ctx.send(embed=emb)

    @commands.command(name="reload_lyrics", hidden=True)
    async def reload_lyrics(self, ctx: commands.Context):
        """Owner-only: reshuffle order of the songs."""
        if ctx.author.id != OWNER_ID:
            return
        if not self._blocks:
            self._blocks = _load_blocks()
        self._shuffle_blocks()
        self._rebuild_entries()
        await ctx.send("Lyric status order reshuffled.")


async def setup(client: commands.Bot):
    await client.add_cog(Status(client))
