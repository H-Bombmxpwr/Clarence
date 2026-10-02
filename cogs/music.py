# cogs/music.py
"""
Rythm-style music player backed by Lavalink (via wavelink).

Needs a Lavalink v4 server — see lavalink/ and the README. Configure with:
  LAVALINK_URI       (default http://localhost:2333)
  LAVALINK_PASSWORD  (default youshallnotpass)

No YouTube cookies/accounts are used. If YouTube refuses a track (common on datacenter IPs),
the bot automatically retries the same song from SoundCloud.
"""
import asyncio
import logging
import os
import re
import time
from typing import Optional, cast

import discord
import wavelink
from discord import app_commands
from discord.ext import commands

from functionality.lyrics import fetch_lyrics
from functionality.store import JsonStore
from functionality.ui import Paginator, chunk_lines, guild_only_cog

log = logging.getLogger("clarence.music")

URL_RE = re.compile(r"^https?://", re.IGNORECASE)
LAVALINK_URI = os.getenv("LAVALINK_URI", "http://localhost:2333").strip().rstrip("/")
if not URL_RE.match(LAVALINK_URI):
    # e.g. "lavalink.railway.internal:2333" — aiohttp needs a scheme
    LAVALINK_URI = f"http://{LAVALINK_URI}"
LAVALINK_PASSWORD = os.getenv("LAVALINK_PASSWORD", "youshallnotpass")
MAX_PLAYLIST = 500
EMBED_COLOR = 0x1db954
# Discord rate-limits message edits, and Lavalink only reports the position every 5s anyway
PROGRESS_INTERVAL = 5
RESTART_THRESHOLD_MS = 5000  # Previous restarts the song if we're further in than this

# Searches tried, in order, for plain-text queries
SEARCH_SOURCES = [wavelink.TrackSource.YouTubeMusic, wavelink.TrackSource.YouTube, wavelink.TrackSource.SoundCloud]

FILTER_PRESETS = {
    "off": "No filter",
    "bassboost": "Bass boost",
    "nightcore": "Nightcore (faster + higher)",
    "vaporwave": "Vaporwave (slower + lower)",
    "8d": "8D audio (rotating)",
    "karaoke": "Karaoke (reduce vocals)",
    "soft": "Soft (low-pass)",
}


def fmt_ms(ms: int) -> str:
    seconds = int(ms // 1000)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def parse_timestamp(text: str) -> Optional[int]:
    """'1:30', '01:02:03' or '90' -> milliseconds."""
    parts = text.strip().split(":")
    if not all(p.isdigit() for p in parts) or len(parts) > 3:
        return None
    seconds = 0
    for p in parts:
        seconds = seconds * 60 + int(p)
    return seconds * 1000


def progress_bar(position: int, length: int, width: int = 18) -> str:
    if not length:
        return "LIVE"
    filled = int(width * min(position / length, 1))
    return "▬" * filled + "🔘" + "▬" * (width - filled)


def track_line(track: wavelink.Playable, index: Optional[int] = None) -> str:
    prefix = f"`{index}.` " if index is not None else ""
    title = discord.utils.escape_markdown(track.title)[:70]
    length = "LIVE" if track.is_stream else fmt_ms(track.length)
    requester = track.extras.requester if hasattr(track.extras, "requester") else None
    req = f" • <@{requester}>" if requester else ""
    return f"{prefix}[{title}]({track.uri}) `{length}`{req}"


class MusicPlayer(wavelink.Player):
    """Player with a home text channel and the current now-playing message."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.home: Optional[discord.abc.Messageable] = None
        self.np_message: Optional[discord.Message] = None
        self.progress_task: Optional[asyncio.Task] = None
        self.filter_name: str = "off"

    def stop_progress(self):
        if self.progress_task:
            self.progress_task.cancel()
            self.progress_task = None


class NowPlayingControls(discord.ui.View):
    """Previous / pause-play / next / loop / queue. Buttons update the now-playing embed in place."""

    def __init__(self, cog: "Music", player: MusicPlayer):
        super().__init__(timeout=None)
        self.cog = cog
        self.sync(player)

    def sync(self, player: MusicPlayer):
        """Make the button icons reflect the player's state."""
        self.pause_resume.emoji = "▶️" if player.paused else "⏸️"
        mode = player.queue.mode
        self.loop.emoji = "🔂" if mode is wavelink.QueueMode.loop else "🔁"
        self.loop.style = discord.ButtonStyle.secondary if mode is wavelink.QueueMode.normal else discord.ButtonStyle.success

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        player = cast(MusicPlayer, interaction.guild.voice_client) if interaction.guild else None
        if not player or not player.connected:
            await interaction.response.send_message("Nothing is playing.", ephemeral=True)
            return False
        if not interaction.user.voice or interaction.user.voice.channel != player.channel:
            await interaction.response.send_message("Join my voice channel to use the controls.", ephemeral=True)
            return False
        return True

    async def refresh(self, interaction: discord.Interaction, player: MusicPlayer):
        self.sync(player)
        if player.current:
            await interaction.response.edit_message(embed=self.cog.now_playing_embed(player), view=self)
        else:
            await interaction.response.edit_message(view=self)

    @discord.ui.button(emoji="⏮️", style=discord.ButtonStyle.secondary)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = cast(MusicPlayer, interaction.guild.voice_client)
        history = player.queue.history
        # Like most players: restart the song unless we're near its start and there's one before it.
        # history[-1] is the current track (wavelink adds tracks to history as they start).
        if not player.current or player.position > RESTART_THRESHOLD_MS or len(history) < 2:
            if player.current and player.current.is_seekable:
                await player.seek(0)
            return await self.refresh(interaction, player)
        await interaction.response.defer()
        previous = history[-2]
        player.queue.put_at(0, player.current)  # so Next comes back to it
        del history[-2:]  # play() re-adds the previous track
        await player.play(previous)  # track_start updates the embed

    @discord.ui.button(emoji="⏸️", style=discord.ButtonStyle.primary)
    async def pause_resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = cast(MusicPlayer, interaction.guild.voice_client)
        await player.pause(not player.paused)
        await self.refresh(interaction, player)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = cast(MusicPlayer, interaction.guild.voice_client)
        if player.queue:
            # Play the next track directly: skip() would repeat the current song in loop-track mode
            await interaction.response.defer()
            track = player.queue.peek(0)
            player.queue.delete(0)
            await player.play(track)  # track_start updates the embed
        elif player.autoplay is wavelink.AutoPlayMode.enabled:
            await interaction.response.defer()
            await player.skip(force=True)
        else:
            await player.skip(force=True)
            player.stop_progress()
            embed = discord.Embed(title="Queue finished", color=EMBED_COLOR, description="Add more with `/play`.")
            await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(emoji="🔁", style=discord.ButtonStyle.secondary)
    async def loop(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = cast(MusicPlayer, interaction.guild.voice_client)
        order = [wavelink.QueueMode.normal, wavelink.QueueMode.loop, wavelink.QueueMode.loop_all]
        player.queue.mode = order[(order.index(player.queue.mode) + 1) % 3]
        await self.refresh(interaction, player)

    @discord.ui.button(emoji="📜", style=discord.ButtonStyle.secondary)
    async def show_queue(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = cast(MusicPlayer, interaction.guild.voice_client)
        await Paginator(self.cog.queue_pages(player), interaction.user.id).send(interaction, ephemeral=True)


class Music(commands.Cog):
    """Music player — play songs in voice with a queue"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.settings = JsonStore("music.json")  # per-guild volume
        self._alone_tasks: dict[int, asyncio.Task] = {}
        self._play_locks: dict[int, asyncio.Lock] = {}
        guild_only_cog(self)

    async def cog_load(self):
        if not wavelink.Pool.nodes:
            node = wavelink.Node(uri=LAVALINK_URI, password=LAVALINK_PASSWORD, inactive_player_timeout=300)
            # Pool.connect retries until Lavalink is reachable, so don't block startup on it
            asyncio.create_task(self._connect_node(node))

    async def _connect_node(self, node: wavelink.Node):
        await self.bot.wait_until_ready()
        try:
            await wavelink.Pool.connect(nodes=[node], client=self.bot, cache_capacity=100)
        except Exception:
            log.exception("Could not connect to Lavalink at %s", LAVALINK_URI)

    async def cog_unload(self):
        for vc in list(self.bot.voice_clients):
            await vc.disconnect(force=True)

    # ------------------------------------------------------------------ helpers

    def volume_for(self, guild_id: int) -> int:
        return self.settings.guild(guild_id).get("volume", 60)

    @staticmethod
    def node_ready() -> bool:
        return any(n.status is wavelink.NodeStatus.CONNECTED for n in wavelink.Pool.nodes.values())

    async def get_player(self, interaction: discord.Interaction, *, connect: bool = False) -> Optional[MusicPlayer]:
        """Validate voice state and return the guild's player (optionally connecting). Sends an error and returns None on failure."""
        async def fail(msg: str):
            if interaction.response.is_done():
                await interaction.followup.send(f"{msg}", ephemeral=True)
            else:
                await interaction.response.send_message(f"{msg}", ephemeral=True)

        if not self.node_ready():
            await fail("The music server (Lavalink) isn't connected right now. Try again in a minute.")
            return None
        voice = interaction.user.voice
        player = cast(Optional[MusicPlayer], interaction.guild.voice_client)

        if not voice or not voice.channel:
            await fail("Join a voice channel first.")
            return None
        if player and player.connected:
            if player.channel != voice.channel:
                if player.playing and any(not m.bot for m in player.channel.members):
                    await fail(f"I'm already playing in {player.channel.mention}.")
                    return None
                await player.move_to(voice.channel)
            return player
        if not connect:
            await fail("I'm not playing anything.")
            return None

        perms = voice.channel.permissions_for(interaction.guild.me)
        if not perms.connect or not perms.speak:
            await fail(f"I don't have permission to join/speak in {voice.channel.mention}.")
            return None
        player = await voice.channel.connect(cls=MusicPlayer, self_deaf=True)
        player.autoplay = wavelink.AutoPlayMode.partial
        player.inactive_timeout = 300
        await player.set_volume(self.volume_for(interaction.guild.id))
        return player

    async def search(self, query: str) -> wavelink.Search:
        if URL_RE.match(query):
            return await wavelink.Playable.search(query, source=None)
        for source in SEARCH_SOURCES:
            try:
                results = await wavelink.Playable.search(query, source=source)
            except wavelink.LavalinkLoadException as e:
                log.warning("Search via %s failed: %s", source, e)
                continue
            if results:
                return results
        return []

    async def stop_player(self, player: MusicPlayer):
        player.queue.clear()
        player.auto_queue.clear()
        player.queue.mode = wavelink.QueueMode.normal
        player.autoplay = wavelink.AutoPlayMode.partial
        await player.skip(force=True)

    async def enqueue(self, interaction: discord.Interaction, query: str, *, front: bool = False, skip_current: bool = False):
        await interaction.response.defer()
        player = await self.get_player(interaction, connect=True)
        if not player:
            return
        player.home = interaction.channel

        try:
            results = await self.search(query)
        except wavelink.LavalinkLoadException as e:
            return await interaction.followup.send(f"Couldn't load that: {e.error}")
        if not results:
            return await interaction.followup.send(f"No results for **{discord.utils.escape_markdown(query)}**.")

        requester = {"requester": interaction.user.id}
        if isinstance(results, wavelink.Playlist):
            tracks = results.tracks[:MAX_PLAYLIST]
            for t in tracks:
                t.extras = requester
            if front:
                for t in reversed(tracks):
                    player.queue.put_at(0, t)
            else:
                player.queue.put(tracks)
            embed = discord.Embed(title="Playlist queued", color=EMBED_COLOR,
                                  description=f"**[{results.name}]({results.url or query})** — {len(tracks)} tracks")
            if results.artwork:
                embed.set_thumbnail(url=results.artwork)
        else:
            track = results[0]
            track.extras = requester
            if front:
                player.queue.put_at(0, track)
            else:
                player.queue.put(track)
            starting = not player.playing or skip_current
            position = 1 if front else player.queue.count
            embed = discord.Embed(title="Starting" if starting else "Added to queue", color=EMBED_COLOR,
                                  description=track_line(track))
            if not starting:
                embed.add_field(name="Position", value=str(position))
                ahead = (player.current.length - player.position if player.current else 0) + sum(
                    t.length for t in list(player.queue)[: position - 1])
                embed.add_field(name="Plays in", value=f"~{fmt_ms(ahead)}")
            if track.artwork:
                embed.set_thumbnail(url=track.artwork)
        embed.set_footer(text=f"Requested by {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
        await interaction.followup.send(embed=embed)

        # two quick /play calls must not both start playback
        async with self._play_locks.setdefault(interaction.guild.id, asyncio.Lock()):
            if skip_current and player.playing and player.queue:
                # Take the new track off the front directly: queue.get() would repeat the current song in loop mode
                track = player.queue.peek(0)
                player.queue.delete(0)
                await player.play(track)
            elif not player.playing and player.queue:
                await player.play(player.queue.get(), volume=self.volume_for(interaction.guild.id))

    def now_playing_embed(self, player: MusicPlayer) -> discord.Embed:
        track = player.current
        embed = discord.Embed(title="Now Playing", color=EMBED_COLOR,
                              description=f"**[{discord.utils.escape_markdown(track.title)}]({track.uri})**\nby {track.author}")
        if track.artwork:
            embed.set_thumbnail(url=track.artwork)
        length = "LIVE" if track.is_stream else fmt_ms(track.length)
        progress = f"{progress_bar(player.position, track.length)}\n`{fmt_ms(player.position)} / {length}`"
        if player.paused:
            progress += " • paused"
        elif not track.is_stream:
            # Discord renders this as a live countdown on each viewer's screen
            ends_at = int(time.time() + max(track.length - player.position, 0) / 1000)
            progress += f" • ends <t:{ends_at}:R>"
        embed.add_field(name="Progress", value=progress, inline=False)
        requester = getattr(track.extras, "requester", None)
        embed.add_field(name="Requested by", value=f"<@{requester}>" if requester else "Autoplay")
        mode = {wavelink.QueueMode.normal: "off", wavelink.QueueMode.loop: "track", wavelink.QueueMode.loop_all: "queue"}[player.queue.mode]
        embed.add_field(name="Loop", value=mode)
        embed.add_field(name="Volume", value=f"{player.volume}%")
        if player.queue:
            embed.add_field(name="Up next", value=track_line(player.queue.peek(0)), inline=False)
        footer = [f"{player.queue.count} in queue", f"source: {track.source}"]
        if player.autoplay is wavelink.AutoPlayMode.enabled:
            footer.append("autoplay on")
        if player.filter_name != "off":
            footer.append(f"filter: {player.filter_name}")
        embed.set_footer(text=" • ".join(footer))
        return embed

    def queue_pages(self, player: MusicPlayer) -> list[discord.Embed]:
        tracks = list(player.queue)
        total = sum(t.length for t in tracks) + ((player.current.length - player.position) if player.current else 0)
        header = f"**Now playing:** {track_line(player.current)}\n\n" if player.current else ""
        mode = {wavelink.QueueMode.normal: "off", wavelink.QueueMode.loop: "track", wavelink.QueueMode.loop_all: "queue"}[player.queue.mode]
        footer = f"{len(tracks)} tracks • {fmt_ms(total)} total • loop: {mode}"

        pages = []
        for start in range(0, max(len(tracks), 1), 10):
            lines = [track_line(t, i) for i, t in enumerate(tracks[start:start + 10], start + 1)]
            embed = discord.Embed(title="Queue", color=EMBED_COLOR,
                                  description=header + ("\n".join(lines) if lines else "*Nothing queued after this.*"))
            embed.set_footer(text=footer)
            pages.append(embed)
        return pages

    # ------------------------------------------------------------------ wavelink events

    @commands.Cog.listener()
    async def on_wavelink_node_ready(self, payload: wavelink.NodeReadyEventPayload):
        log.info("Lavalink node %s ready (resumed=%s)", payload.node.identifier, payload.resumed)

    @commands.Cog.listener()
    async def on_wavelink_track_start(self, payload: wavelink.TrackStartEventPayload):
        player = cast(Optional[MusicPlayer], payload.player)
        if not player:
            return
        # wavelink stops auto-advancing for good after 3 consecutive failed tracks, and only
        # clears the count on paths it never reaches once stuck. A track playing means we're healthy.
        player._error_count = 0
        if not player.home:
            return
        player.stop_progress()
        embed, view = self.now_playing_embed(player), NowPlayingControls(self, player)
        old = player.np_message
        # Edit in place while it's still the latest message in the channel; otherwise re-post at the bottom
        if old and getattr(player.home, "last_message_id", None) == old.id:
            try:
                await old.edit(embed=embed, view=view)
            except discord.HTTPException:
                player.np_message = None
        else:
            if old:
                try:
                    await old.delete()
                except discord.HTTPException:
                    pass
            try:
                player.np_message = await player.home.send(embed=embed, view=view)
            except discord.HTTPException:
                player.np_message = None
        if player.np_message:
            player.progress_task = asyncio.create_task(self._update_progress(player))

    async def _update_progress(self, player: MusicPlayer):
        """Keep the now-playing progress bar moving until the track changes."""
        track = player.current
        while True:
            await asyncio.sleep(PROGRESS_INTERVAL)
            if not player.connected or player.current is not track or not player.np_message:
                return
            if player.paused:
                continue
            try:
                await player.np_message.edit(embed=self.now_playing_embed(player))
            except discord.NotFound:
                player.np_message = None
                return
            except discord.HTTPException as e:
                log.debug("Progress update failed: %s", e)

    @commands.Cog.listener()
    async def on_wavelink_track_exception(self, payload: wavelink.TrackExceptionEventPayload):
        player = cast(Optional[MusicPlayer], payload.player)
        track = payload.track
        if not player:
            return
        message = (payload.exception or {}).get("message", "unknown error")
        log.warning("Track exception for %s (%s): %s", track.title, track.source, message)

        # Lavalink follows this with a track-end event, and wavelink's autoplay would react to it
        # before our SoundCloud search finishes: in loop-track mode it replays the broken track forever,
        # otherwise it jumps ahead in the queue. Pause autoplay (synchronously, before any await, so it's
        # in place before that event is handled) and pick the next track ourselves.
        autoplay = player.autoplay
        player.autoplay = wavelink.AutoPlayMode.disabled
        try:
            fallback = None
            # YouTube often blocks server IPs — try the same song on SoundCloud instead
            if track.source != "soundcloud" and not getattr(track.extras, "fallback", False):
                try:
                    alt = await wavelink.Playable.search(f"{track.author} {track.title}", source=wavelink.TrackSource.SoundCloud)
                except wavelink.LavalinkLoadException:
                    alt = []
                if alt:
                    fallback = alt[0]
                    fallback.extras = {"requester": getattr(track.extras, "requester", None), "fallback": True}

            if player.home:
                note = (f"Couldn't stream **{track.title}** from {track.source}; trying SoundCloud instead."
                        if fallback else f"Couldn't play **{track.title}**: {message}")
                try:
                    await player.home.send(note)
                except discord.HTTPException:
                    pass

            if player.current is not None:
                return  # something else (e.g. /playskip) already started a track
            if fallback:
                await player.play(fallback)  # in loop-track mode this becomes the looped track
            elif player.queue:
                # Take it off the front directly: queue.get() would hand back the broken track in loop mode
                nxt = player.queue.peek(0)
                player.queue.delete(0)
                await player.play(nxt)
        finally:
            player.autoplay = autoplay

    @commands.Cog.listener()
    async def on_wavelink_track_stuck(self, payload: wavelink.TrackStuckEventPayload):
        if payload.player:
            await payload.player.skip(force=True)

    @commands.Cog.listener()
    async def on_wavelink_inactive_player(self, player: wavelink.Player):
        player = cast(MusicPlayer, player)
        if player.home:
            try:
                await player.home.send("Left the voice channel after 5 minutes of inactivity.")
            except discord.HTTPException:
                pass
        await player.disconnect()

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        player = cast(Optional[MusicPlayer], member.guild.voice_client)
        if not player or not isinstance(player, MusicPlayer) or not player.channel:
            return
        if member.id == self.bot.user.id and after.channel is None:
            return  # we were disconnected; wavelink cleans up
        humans = [m for m in player.channel.members if not m.bot]
        gid = member.guild.id
        if humans:
            task = self._alone_tasks.pop(gid, None)
            if task:
                task.cancel()
        elif gid not in self._alone_tasks:
            self._alone_tasks[gid] = asyncio.create_task(self._leave_if_alone(player, gid))

    async def _leave_if_alone(self, player: MusicPlayer, gid: int):
        try:
            await asyncio.sleep(120)
            if player.channel and not any(not m.bot for m in player.channel.members):
                if player.home:
                    await player.home.send("Everyone left, so I did too.")
                await player.disconnect()
        except asyncio.CancelledError:
            pass
        finally:
            self._alone_tasks.pop(gid, None)

    # ------------------------------------------------------------------ autocomplete

    async def query_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if len(current) < 3 or URL_RE.match(current) or not self.node_ready():
            return []
        try:
            results = await asyncio.wait_for(wavelink.Playable.search(current), timeout=2.5)
        except Exception:
            return []
        if isinstance(results, wavelink.Playlist):
            return []
        choices = []
        for t in results[:10]:
            if t.uri and len(t.uri) <= 100:
                name = f"{t.title} — {t.author} [{fmt_ms(t.length)}]"
                choices.append(app_commands.Choice(name=name[:100], value=t.uri))
        return choices

    # ------------------------------------------------------------------ playback commands

    @app_commands.command(description="Play a song or playlist (search, YouTube/SoundCloud/Spotify link)")
    @app_commands.describe(query="Song name or URL")
    @app_commands.autocomplete(query=query_autocomplete)
    async def play(self, interaction: discord.Interaction, query: str):
        await self.enqueue(interaction, query)

    @app_commands.command(description="Add a song to the front of the queue")
    @app_commands.describe(query="Song name or URL")
    @app_commands.autocomplete(query=query_autocomplete)
    async def playnext(self, interaction: discord.Interaction, query: str):
        await self.enqueue(interaction, query, front=True)

    @app_commands.command(description="Skip the current song and play this one right away")
    @app_commands.describe(query="Song name or URL")
    @app_commands.autocomplete(query=query_autocomplete)
    async def playskip(self, interaction: discord.Interaction, query: str):
        await self.enqueue(interaction, query, front=True, skip_current=True)

    @app_commands.command(description="Join your voice channel")
    async def join(self, interaction: discord.Interaction):
        player = await self.get_player(interaction, connect=True)
        if player:
            player.home = interaction.channel
            await interaction.response.send_message(f"Joined {player.channel.mention}")

    @app_commands.command(description="Leave the voice channel and clear the queue")
    async def leave(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            await player.disconnect()
            await interaction.response.send_message("Disconnected.")

    @app_commands.command(description="Skip the current song")
    async def skip(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if not player:
            return
        if not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        skipped = await player.skip(force=True)
        await interaction.response.send_message(f"Skipped **{skipped.title}**")

    @app_commands.command(description="Skip to a position in the queue")
    async def skipto(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 10000]):
        player = await self.get_player(interaction)
        if not player:
            return
        if position > player.queue.count:
            return await interaction.response.send_message(f"The queue only has {player.queue.count} tracks.", ephemeral=True)
        del player.queue[: position - 1]
        await player.skip(force=True)
        await interaction.response.send_message(f"Skipped to **{player.queue.peek(0).title if player.queue else 'position %d' % position}**")

    @app_commands.command(description="Pause playback")
    async def pause(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            await player.pause(True)
            await interaction.response.send_message("Paused.")

    @app_commands.command(description="Resume playback")
    async def resume(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            await player.pause(False)
            await interaction.response.send_message("Resumed.")

    @app_commands.command(description="Stop playback and clear the queue (stays in the channel)")
    async def stop(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            await self.stop_player(player)
            await interaction.response.send_message("Stopped and cleared the queue.")

    @app_commands.command(description="Show what's playing")
    async def nowplaying(self, interaction: discord.Interaction):
        player = cast(Optional[MusicPlayer], interaction.guild.voice_client)
        if not player or not player.current:
            return await interaction.response.send_message("Nothing is playing.", ephemeral=True)
        await interaction.response.send_message(embed=self.now_playing_embed(player), view=NowPlayingControls(self, player))

    @app_commands.command(description="Show the queue")
    async def queue(self, interaction: discord.Interaction):
        player = cast(Optional[MusicPlayer], interaction.guild.voice_client)
        if not player or (not player.current and not player.queue):
            return await interaction.response.send_message("The queue is empty. Add something with `/play`.", ephemeral=True)
        await Paginator(self.queue_pages(player), interaction.user.id).send(interaction)

    @app_commands.command(description="Shuffle the queue")
    async def shuffle(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            player.queue.shuffle()
            await interaction.response.send_message("Queue shuffled.")

    @app_commands.command(description="Set loop mode")
    @app_commands.choices(mode=[app_commands.Choice(name="Off", value="off"),
                                app_commands.Choice(name="Current track", value="track"),
                                app_commands.Choice(name="Whole queue", value="queue")])
    async def loop(self, interaction: discord.Interaction, mode: app_commands.Choice[str]):
        player = await self.get_player(interaction)
        if player:
            player.queue.mode = {"off": wavelink.QueueMode.normal, "track": wavelink.QueueMode.loop,
                                 "queue": wavelink.QueueMode.loop_all}[mode.value]
            await interaction.response.send_message(f"Loop: **{mode.name}**")

    @app_commands.command(description="Remove a track from the queue")
    async def remove(self, interaction: discord.Interaction, position: app_commands.Range[int, 1, 10000]):
        player = await self.get_player(interaction)
        if not player:
            return
        if position > player.queue.count:
            return await interaction.response.send_message(f"The queue only has {player.queue.count} tracks.", ephemeral=True)
        track = player.queue.peek(position - 1)
        player.queue.delete(position - 1)
        await interaction.response.send_message(f"Removed **{track.title}**")

    @app_commands.command(description="Move a track to a different position in the queue")
    async def move(self, interaction: discord.Interaction, from_position: app_commands.Range[int, 1, 10000],
                   to_position: app_commands.Range[int, 1, 10000]):
        player = await self.get_player(interaction)
        if not player:
            return
        count = player.queue.count
        if from_position > count or to_position > count:
            return await interaction.response.send_message(f"The queue only has {count} tracks.", ephemeral=True)
        track = player.queue.peek(from_position - 1)
        player.queue.delete(from_position - 1)
        player.queue.put_at(to_position - 1, track)
        await interaction.response.send_message(f"Moved **{track.title}** to position {to_position}.")

    @app_commands.command(description="Clear the queue (keeps the current song)")
    async def clearqueue(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player:
            player.queue.clear()
            await interaction.response.send_message("Queue cleared.")

    @app_commands.command(description="Set the volume (0-150)")
    async def volume(self, interaction: discord.Interaction, level: app_commands.Range[int, 0, 150]):
        player = await self.get_player(interaction)
        if player:
            await player.set_volume(level)
            self.settings.guild(interaction.guild.id)["volume"] = level
            self.settings.save()
            await interaction.response.send_message(f"Volume set to **{level}%**")

    @app_commands.command(description="Jump to a time in the current song (e.g. 1:30)")
    async def seek(self, interaction: discord.Interaction, position: str):
        player = await self.get_player(interaction)
        if not player:
            return
        if not player.current or not player.current.is_seekable:
            return await interaction.response.send_message("This track can't be seeked.", ephemeral=True)
        ms = parse_timestamp(position)
        if ms is None or ms > player.current.length:
            return await interaction.response.send_message("Give a time like `1:30` within the song length.", ephemeral=True)
        await player.seek(ms)
        await interaction.response.send_message(f"Seeked to `{fmt_ms(ms)}`")

    @app_commands.command(description="Restart the current song")
    async def replay(self, interaction: discord.Interaction):
        player = await self.get_player(interaction)
        if player and player.current:
            await player.seek(0)
            await interaction.response.send_message("Restarted the song.")

    @app_commands.command(description="When the queue runs out, keep playing similar songs")
    async def autoplay(self, interaction: discord.Interaction, enabled: bool):
        player = await self.get_player(interaction)
        if player:
            player.autoplay = wavelink.AutoPlayMode.enabled if enabled else wavelink.AutoPlayMode.partial
            await interaction.response.send_message(f"Autoplay **{'on' if enabled else 'off'}**.")

    @app_commands.command(description="Apply an audio filter")
    @app_commands.choices(preset=[app_commands.Choice(name=v, value=k) for k, v in FILTER_PRESETS.items()])
    async def filter(self, interaction: discord.Interaction, preset: app_commands.Choice[str]):
        player = await self.get_player(interaction)
        if not player:
            return
        filters = wavelink.Filters()
        if preset.value == "bassboost":
            filters.equalizer.set(bands=[{"band": 0, "gain": 0.25}, {"band": 1, "gain": 0.2}, {"band": 2, "gain": 0.15},
                                         {"band": 3, "gain": 0.1}, {"band": 4, "gain": 0.05}])
        elif preset.value == "nightcore":
            filters.timescale.set(speed=1.2, pitch=1.2, rate=1.0)
        elif preset.value == "vaporwave":
            filters.timescale.set(speed=0.85, pitch=0.8, rate=1.0)
        elif preset.value == "8d":
            filters.rotation.set(rotation_hz=0.2)
        elif preset.value == "karaoke":
            filters.karaoke.set(level=1.0, mono_level=1.0, filter_band=220.0, filter_width=100.0)
        elif preset.value == "soft":
            filters.low_pass.set(smoothing=20.0)
        await player.set_filters(filters, seek=True)
        player.filter_name = preset.value
        await interaction.response.send_message(f"Filter: **{preset.name}**")

    # ------------------------------------------------------------------ lyrics

    @app_commands.command(description="Get lyrics for a song (defaults to what's playing)")
    @app_commands.describe(song="Song to search for, e.g. 'Steely Dan - Peg' (leave empty for the current song)")
    async def lyrics(self, interaction: discord.Interaction, song: Optional[str] = None):
        await interaction.response.defer()
        player = cast(Optional[MusicPlayer], interaction.guild.voice_client) if interaction.guild else None
        try:
            if song:
                result = await fetch_lyrics(self.bot.session, song)
            elif player and player.current:
                t = player.current
                result = await fetch_lyrics(self.bot.session, title=t.title, artist=t.author, duration_s=t.length // 1000)
                song = f"{t.author} - {t.title}"
            else:
                return await interaction.followup.send("Nothing is playing — give me a song name, e.g. `/lyrics song:Peg Steely Dan`.")
        except asyncio.TimeoutError:
            return await interaction.followup.send("The lyrics service timed out. Try again.")

        if not result:
            return await interaction.followup.send(f"No lyrics found for **{discord.utils.escape_markdown(song)}**. "
                                                   "Try `Artist - Song`.")
        title = f"{result['artist']} — {result['title']}"[:256]
        if result["instrumental"] and not result["lyrics"]:
            return await interaction.followup.send(embed=discord.Embed(title=title, description="*Instrumental*", color=EMBED_COLOR))

        pages = []
        for chunk in chunk_lines(result["lyrics"].split("\n"), 3500):
            embed = discord.Embed(title=title, description=chunk, color=EMBED_COLOR)
            embed.set_footer(text=(f"{result['album']} • " if result["album"] else "") + "Lyrics from LRCLIB")
            pages.append(embed)
        await Paginator(pages, interaction.user.id).send(interaction)


async def setup(bot: commands.Bot):
    await bot.add_cog(Music(bot))
