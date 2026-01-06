# cogs/music.py
"""
Music cog for Discord bot - plays audio from YouTube
Requires: yt-dlp, PyNaCl, FFmpeg (system install)
"""
import discord
from discord.ext import commands
import asyncio
import re
from typing import Optional, Dict
from collections import deque
import requests
from urllib.parse import quote

# Try to import yt-dlp
try:
    import yt_dlp
    YTDL_AVAILABLE = True
except ImportError:
    YTDL_AVAILABLE = False
    print("[music] yt-dlp not installed - run: pip install yt-dlp")

# yt-dlp options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
}

# FFmpeg options for streaming
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}


class Song:
    """Represents a song in the queue"""
    def __init__(self, title: str, url: str, stream_url: str, duration: int, 
                 requester: discord.Member, thumbnail: str = None):
        self.title = title
        self.url = url  # webpage URL
        self.stream_url = stream_url  # direct audio stream
        self.duration = duration
        self.requester = requester
        self.thumbnail = thumbnail

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "?"
        mins, secs = divmod(int(self.duration), 60)
        hours, mins = divmod(mins, 60)
        if hours:
            return f"{hours}:{mins:02d}:{secs:02d}"
        return f"{mins}:{secs:02d}"

    @classmethod
    async def from_query(cls, query: str, requester: discord.Member, loop=None):
        """Search/extract song info from query"""
        loop = loop or asyncio.get_event_loop()
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
        
        # Add search prefix if not a URL
        if not re.match(r'^https?://', query):
            query = f'ytsearch:{query}'
        
        # Extract info in executor
        data = await loop.run_in_executor(
            None, 
            lambda: ytdl.extract_info(query, download=False)
        )
        
        if not data:
            return None
        
        # Handle search results
        if 'entries' in data:
            if not data['entries']:
                return None
            data = data['entries'][0]
        
        return cls(
            title=data.get('title', 'Unknown'),
            url=data.get('webpage_url', query),
            stream_url=data.get('url', ''),
            duration=data.get('duration', 0),
            requester=requester,
            thumbnail=data.get('thumbnail')
        )

    def create_source(self, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        """Create a fresh audio source"""
        source = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        return discord.PCMVolumeTransformer(source, volume=volume)


class Music(commands.Cog):
    """🎵 Music Player - Play songs from YouTube!"""

    def __init__(self, bot):
        self.bot = bot
        # Per-guild data
        self.queues: Dict[int, deque] = {}  # guild_id -> deque of Songs
        self.current: Dict[int, Optional[Song]] = {}  # guild_id -> current Song
        self.volumes: Dict[int, float] = {}  # guild_id -> volume (0.0-1.0)
        self.loop_mode: Dict[int, bool] = {}  # guild_id -> loop enabled

    def get_queue(self, guild_id: int) -> deque:
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
        return self.queues[guild_id]

    def get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, 0.5)

    def set_volume(self, guild_id: int, vol: float):
        self.volumes[guild_id] = max(0.0, min(1.0, vol))

    def get_voice_client(self, ctx) -> Optional[discord.VoiceClient]:
        """Get the voice client for this guild"""
        return ctx.voice_client

    async def play_next(self, ctx):
        """Play the next song in queue"""
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        
        # Check if we should loop
        if self.loop_mode.get(guild_id) and self.current.get(guild_id):
            queue.appendleft(self.current[guild_id])
        
        if not queue:
            self.current[guild_id] = None
            return
        
        song = queue.popleft()
        self.current[guild_id] = song
        
        vc = self.get_voice_client(ctx)
        if not vc or not vc.is_connected():
            self.current[guild_id] = None
            return
        
        try:
            # Re-fetch stream URL (they expire!)
            fresh_song = await Song.from_query(song.url, song.requester, self.bot.loop)
            if fresh_song:
                song = fresh_song
                self.current[guild_id] = song
            
            source = song.create_source(self.get_volume(guild_id))
            
            def after_playing(error):
                if error:
                    print(f"[music] Playback error: {error}")
                # Schedule next song
                coro = self.play_next(ctx)
                fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"[music] Error scheduling next: {e}")
            
            vc.play(source, after=after_playing)
            
            # Send now playing embed
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**[{song.title}]({song.url})**",
                color=0x1db954
            )
            embed.add_field(name="Duration", value=song.duration_str, inline=True)
            embed.add_field(name="Requested by", value=song.requester.mention, inline=True)
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            print(f"[music] Error playing: {e}")
            await ctx.send(f"❌ Error playing **{song.title}**: {e}")
            # Try next song
            await self.play_next(ctx)

    @commands.command(name="join", aliases=["connect"])
    async def join(self, ctx):
        """Join your voice channel"""
        if not ctx.author.voice:
            return await ctx.send("❌ You need to be in a voice channel!")
        
        channel = ctx.author.voice.channel
        
        if ctx.voice_client:
            if ctx.voice_client.channel == channel:
                return await ctx.send(f"✅ Already in **{channel.name}**")
            await ctx.voice_client.move_to(channel)
        else:
            await channel.connect()
        
        await ctx.send(f"🔊 Joined **{channel.name}**")

    @commands.command(name="leave", aliases=["disconnect", "dc", "gtfo"])
    async def leave(self, ctx):
        """Leave the voice channel"""
        if not ctx.voice_client:
            return await ctx.send("❌ I'm not in a voice channel!")
        
        # Clear queue
        guild_id = ctx.guild.id
        self.queues[guild_id] = deque()
        self.current[guild_id] = None
        
        await ctx.voice_client.disconnect()
        await ctx.send("👋 Disconnected!")

    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        """
        Play a song from YouTube
        
        Usage: play <song name or URL>
        """
        if not YTDL_AVAILABLE:
            return await ctx.send("❌ yt-dlp not installed. Run: `pip install yt-dlp`")
        
        # Auto-join if not in voice
        if not ctx.voice_client:
            if not ctx.author.voice:
                return await ctx.send("❌ You need to be in a voice channel!")
            await ctx.author.voice.channel.connect()
        
        async with ctx.typing():
            try:
                song = await Song.from_query(query, ctx.author, self.bot.loop)
                
                if not song:
                    return await ctx.send(f"❌ Could not find: **{query}**")
                
                queue = self.get_queue(ctx.guild.id)
                queue.append(song)
                
                # If not playing, start playback
                if not ctx.voice_client.is_playing() and not ctx.voice_client.is_paused():
                    await self.play_next(ctx)
                else:
                    # Added to queue
                    embed = discord.Embed(
                        title="📋 Added to Queue",
                        description=f"**[{song.title}]({song.url})**",
                        color=0x3498db
                    )
                    embed.add_field(name="Position", value=str(len(queue)), inline=True)
                    embed.add_field(name="Duration", value=song.duration_str, inline=True)
                    if song.thumbnail:
                        embed.set_thumbnail(url=song.thumbnail)
                    await ctx.send(embed=embed)
                    
            except Exception as e:
                print(f"[music] Play error: {e}")
                await ctx.send(f"❌ Error: {e}")

    @commands.command(name="skip", aliases=["s", "next"])
    async def skip(self, ctx):
        """Skip the current song"""
        if not ctx.voice_client or not ctx.voice_client.is_playing():
            return await ctx.send("❌ Nothing is playing!")
        
        ctx.voice_client.stop()  # This triggers after_playing -> play_next
        await ctx.send("⏭️ Skipped!")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop playback and clear queue"""
        if not ctx.voice_client:
            return await ctx.send("❌ Not playing anything!")
        
        guild_id = ctx.guild.id
        self.queues[guild_id] = deque()
        self.current[guild_id] = None
        self.loop_mode[guild_id] = False
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.stop()
        
        await ctx.send("⏹️ Stopped and cleared queue!")

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause playback"""
        if not ctx.voice_client:
            return await ctx.send("❌ Not playing anything!")
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸️ Paused!")
        elif ctx.voice_client.is_paused():
            await ctx.send("Already paused. Use `resume` to continue.")
        else:
            await ctx.send("❌ Nothing is playing!")

    @commands.command(name="resume", aliases=["unpause"])
    async def resume(self, ctx):
        """Resume playback"""
        if not ctx.voice_client:
            return await ctx.send("❌ Not in a voice channel!")
        
        if ctx.voice_client.is_paused():
            ctx.voice_client.resume()
            await ctx.send("▶️ Resumed!")
        else:
            await ctx.send("❌ Not paused!")

    @commands.command(name="queue", aliases=["q"])
    async def queue_cmd(self, ctx):
        """View the queue"""
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        current = self.current.get(guild_id)
        
        embed = discord.Embed(title="🎵 Music Queue", color=0x3498db)
        
        if current:
            embed.add_field(
                name="🔊 Now Playing",
                value=f"**{current.title}** [{current.duration_str}]",
                inline=False
            )
        
        if queue:
            lines = []
            for i, song in enumerate(list(queue)[:10], 1):
                lines.append(f"`{i}.` **{song.title}** [{song.duration_str}]")
            embed.add_field(name="📋 Up Next", value="\n".join(lines), inline=False)
            if len(queue) > 10:
                embed.set_footer(text=f"And {len(queue) - 10} more...")
        elif not current:
            embed.description = "Queue is empty! Use `play <song>` to add music."
        
        await ctx.send(embed=embed)

    @commands.command(name="nowplaying", aliases=["np", "current"])
    async def nowplaying(self, ctx):
        """Show current song"""
        current = self.current.get(ctx.guild.id)
        
        if not current:
            return await ctx.send("❌ Nothing is playing!")
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{current.title}]({current.url})**",
            color=0x1db954
        )
        embed.add_field(name="Duration", value=current.duration_str, inline=True)
        embed.add_field(name="Requested by", value=current.requester.mention, inline=True)
        embed.add_field(name="Volume", value=f"{int(self.get_volume(ctx.guild.id) * 100)}%", inline=True)
        if current.thumbnail:
            embed.set_thumbnail(url=current.thumbnail)
        
        await ctx.send(embed=embed)

    @commands.command(name="volume", aliases=["vol", "v"])
    async def volume(self, ctx, vol: int = None):
        """Set volume (0-100)"""
        guild_id = ctx.guild.id
        
        if vol is None:
            current_vol = int(self.get_volume(guild_id) * 100)
            return await ctx.send(f"🔊 Volume: **{current_vol}%**")
        
        if vol < 0 or vol > 100:
            return await ctx.send("❌ Volume must be 0-100!")
        
        self.set_volume(guild_id, vol / 100)
        
        # Update current source if playing
        if ctx.voice_client and ctx.voice_client.source:
            ctx.voice_client.source.volume = vol / 100
        
        await ctx.send(f"🔊 Volume: **{vol}%**")

    @commands.command(name="loop", aliases=["repeat"])
    async def loop(self, ctx):
        """Toggle loop mode"""
        guild_id = ctx.guild.id
        self.loop_mode[guild_id] = not self.loop_mode.get(guild_id, False)
        
        if self.loop_mode[guild_id]:
            await ctx.send("🔁 Loop **enabled**")
        else:
            await ctx.send("🔁 Loop **disabled**")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        """Shuffle the queue"""
        import random
        queue = self.get_queue(ctx.guild.id)
        
        if len(queue) < 2:
            return await ctx.send("❌ Need at least 2 songs to shuffle!")
        
        songs = list(queue)
        random.shuffle(songs)
        self.queues[ctx.guild.id] = deque(songs)
        
        await ctx.send("🔀 Queue shuffled!")

    @commands.command(name="clear")
    async def clear(self, ctx):
        """Clear the queue"""
        self.queues[ctx.guild.id] = deque()
        await ctx.send("🗑️ Queue cleared!")

    @commands.command(name="remove")
    async def remove(self, ctx, position: int):
        """Remove a song from queue by position"""
        queue = self.get_queue(ctx.guild.id)
        
        if position < 1 or position > len(queue):
            return await ctx.send(f"❌ Invalid position (1-{len(queue)})")
        
        songs = list(queue)
        removed = songs.pop(position - 1)
        self.queues[ctx.guild.id] = deque(songs)
        
        await ctx.send(f"🗑️ Removed **{removed.title}**")

    @commands.command(name="lyrics", aliases=["ly"])
    async def lyrics(self, ctx, *, query: str = None):
        """Get lyrics for a song"""
        if not query:
            current = self.current.get(ctx.guild.id)
            if current:
                query = current.title
            else:
                return await ctx.send("❌ Specify a song or play something first!")
        
        async with ctx.typing():
            try:
                url = f"https://some-random-api.com/others/lyrics?title={quote(query)}"
                resp = requests.get(url, timeout=10)
                
                if resp.status_code == 200:
                    data = resp.json()
                    if 'lyrics' in data:
                        lyrics = data['lyrics']
                        if len(lyrics) > 3900:
                            lyrics = lyrics[:3900] + "\n\n*...(truncated)*"
                        
                        embed = discord.Embed(
                            title=f"🎤 {data.get('title', query)}",
                            description=lyrics,
                            color=0x1db954
                        )
                        embed.set_footer(text=f"Artist: {data.get('author', 'Unknown')}")
                        return await ctx.send(embed=embed)
                
                await ctx.send(f"❌ No lyrics found for **{query}**")
            except Exception as e:
                await ctx.send(f"❌ Error fetching lyrics: {e}")

    @commands.command(name="musichelp", aliases=["mh"])
    async def musichelp(self, ctx):
        """Show music commands"""
        embed = discord.Embed(title="🎵 Music Commands", color=0x1db954)
        
        cmds = [
            ("`play <song>`", "Play a song"),
            ("`skip`", "Skip current"),
            ("`pause` / `resume`", "Pause/resume"),
            ("`stop`", "Stop & clear"),
            ("`queue`", "View queue"),
            ("`nowplaying`", "Current song"),
            ("`volume <0-100>`", "Set volume"),
            ("`loop`", "Toggle loop"),
            ("`shuffle`", "Shuffle queue"),
            ("`lyrics [song]`", "Get lyrics"),
            ("`join` / `leave`", "Voice control"),
        ]
        
        for name, val in cmds:
            embed.add_field(name=name, value=val, inline=True)
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Music(bot))