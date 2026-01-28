# cogs/music.py
"""
Music cog for Discord bot - plays audio from YouTube
Requires: yt-dlp, PyNaCl, FFmpeg (system install)
"""
import discord
from discord.ext import commands
import asyncio
import re
import shutil
import subprocess
from typing import Optional, Dict
from collections import deque
import requests
from urllib.parse import quote

# Check for FFmpeg
FFMPEG_PATH = shutil.which('ffmpeg')
if FFMPEG_PATH:
    print(f"[music] FFmpeg found at: {FFMPEG_PATH}")
    # Test FFmpeg
    try:
        result = subprocess.run([FFMPEG_PATH, '-version'], capture_output=True, text=True, timeout=5)
        print(f"[music] FFmpeg version: {result.stdout.split(chr(10))[0]}")
    except Exception as e:
        print(f"[music] FFmpeg test failed: {e}")
else:
    print("[music] WARNING: FFmpeg not found in PATH! Audio playback will fail.")

# Try to import yt-dlp
try:
    import yt_dlp
    YTDL_AVAILABLE = True
    print(f"[music] yt-dlp version: {yt_dlp.version.__version__}")
except ImportError:
    YTDL_AVAILABLE = False
    print("[music] yt-dlp not installed - run: pip install yt-dlp")

# Check for PyNaCl (voice support)
try:
    import nacl
    print(f"[music] PyNaCl available for voice support")
except ImportError:
    print("[music] WARNING: PyNaCl not installed - voice may not work")

# Setup cookies from environment variable or file
import os
import base64
COOKIES_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'constants', 'cookies.txt')

# Check for cookies in environment variable first (base64 encoded)
youtube_cookies_env = os.environ.get('YOUTUBE_COOKIES')
if youtube_cookies_env:
    try:
        cookies_content = base64.b64decode(youtube_cookies_env).decode('utf-8')
        # Write to file for yt-dlp
        os.makedirs(os.path.dirname(COOKIES_PATH), exist_ok=True)
        with open(COOKIES_PATH, 'w') as f:
            f.write(cookies_content)
        print(f"[music] Cookies loaded from YOUTUBE_COOKIES environment variable")
    except Exception as e:
        print(f"[music] ERROR decoding YOUTUBE_COOKIES: {e}")
        COOKIES_PATH = None
elif os.path.exists(COOKIES_PATH):
    print(f"[music] Cookies file found at: {COOKIES_PATH}")
else:
    print(f"[music] WARNING: No cookies available - YouTube may block requests")
    COOKIES_PATH = None

# yt-dlp options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': False,  # Enable output for debugging
    'no_warnings': False,  # Show warnings for debugging
    'default_search': 'ytsearch',
    'source_address': '0.0.0.0',
    'extract_flat': False,
}

# Add cookies if available
if COOKIES_PATH:
    YTDL_OPTIONS['cookiefile'] = COOKIES_PATH

# FFmpeg options for streaming
FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -nostdin',
    'options': '-vn -loglevel warning'
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
        import sys
        loop = loop or asyncio.get_event_loop()
        ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)

        # Add search prefix if not a URL
        original_query = query
        if not re.match(r'^https?://', query):
            query = f'ytsearch:{query}'

        print(f"[music] Extracting info for: {query}", flush=True)

        # Extract info in executor with timeout
        try:
            data = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: ytdl.extract_info(query, download=False)
                ),
                timeout=30.0  # 30 second timeout
            )
            print(f"[music] Extraction completed", flush=True)
        except asyncio.TimeoutError:
            print(f"[music] yt-dlp extraction timed out after 30s", flush=True)
            return None
        except Exception as e:
            print(f"[music] yt-dlp extraction error: {e}", flush=True)
            return None

        if not data:
            print(f"[music] No data returned for query: {original_query}", flush=True)
            return None

        # Handle search results
        print(f"[music] Data received, keys: {list(data.keys())}", flush=True)
        if 'entries' in data:
            entries = data['entries']
            print(f"[music] Found {len(entries) if entries else 0} entries", flush=True)
            if not entries:
                print(f"[music] No entries found for search: {original_query}", flush=True)
                return None
            data = entries[0]
            print(f"[music] Entry[0] type: {type(data)}", flush=True)
            if data is None:
                print(f"[music] First entry is None!", flush=True)
                return None
            print(f"[music] Entry[0] keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}", flush=True)
            print(f"[music] Using first search result: {data.get('title', 'Unknown')}", flush=True)

        stream_url = data.get('url', '')
        print(f"[music] Direct URL present: {bool(stream_url)}", flush=True)

        # If no direct URL, try to get from formats (YouTube SABR workaround)
        if not stream_url:
            print(f"[music] No direct URL, checking formats...", flush=True)
            formats = data.get('formats', [])
            print(f"[music] Number of formats available: {len(formats)}", flush=True)

            # Look for audio formats with URLs
            audio_formats = [f for f in formats if f.get('url') and f.get('acodec') != 'none']
            print(f"[music] Audio formats with URLs: {len(audio_formats)}", flush=True)

            if audio_formats:
                # Sort by quality (prefer higher abr)
                audio_formats.sort(key=lambda x: x.get('abr', 0) or 0, reverse=True)
                fmt = audio_formats[0]
                stream_url = fmt['url']
                print(f"[music] Selected format: {fmt.get('format_id')} ({fmt.get('ext')}, {fmt.get('abr')}kbps)", flush=True)

            # If still no URL, try requested_formats
            if not stream_url:
                requested = data.get('requested_formats', [])
                print(f"[music] Checking requested_formats: {len(requested)} items", flush=True)
                for fmt in requested:
                    if fmt.get('url'):
                        stream_url = fmt['url']
                        print(f"[music] Found URL in requested_formats: {fmt.get('format_id')}", flush=True)
                        break

            # Last resort: any format with a URL
            if not stream_url:
                for fmt in formats:
                    if fmt.get('url'):
                        stream_url = fmt['url']
                        print(f"[music] Last resort - using format: {fmt.get('format_id')}", flush=True)
                        break

        if not stream_url:
            print(f"[music] FAILED: No stream URL found for {data.get('title', 'Unknown')}")
            print(f"[music] Available keys: {list(data.keys())}")
            if 'formats' in data:
                # Log first few formats for debugging
                for i, fmt in enumerate(data['formats'][:3]):
                    print(f"[music] Format {i}: id={fmt.get('format_id')}, url={bool(fmt.get('url'))}, acodec={fmt.get('acodec')}")
        else:
            print(f"[music] SUCCESS: Got stream URL ({len(stream_url)} chars) for: {data.get('title', 'Unknown')}")

        return cls(
            title=data.get('title', 'Unknown'),
            url=data.get('webpage_url', query),
            stream_url=stream_url,
            duration=data.get('duration', 0),
            requester=requester,
            thumbnail=data.get('thumbnail')
        )

    def create_source(self, volume: float = 0.5) -> discord.PCMVolumeTransformer:
        """Create a fresh audio source"""
        print(f"[music] Creating FFmpeg source for: {self.title}")
        print(f"[music] Stream URL length: {len(self.stream_url) if self.stream_url else 0}")
        if not self.stream_url:
            raise ValueError("No stream URL available")
        source = discord.FFmpegPCMAudio(self.stream_url, **FFMPEG_OPTIONS)
        print(f"[music] FFmpegPCMAudio created successfully")
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
        print("[music] Music cog initialized")

    async def cog_unload(self):
        """Cleanup when cog is unloaded"""
        print("[music] Unloading music cog, disconnecting from all voice channels...")
        for vc in self.bot.voice_clients:
            try:
                await vc.disconnect(force=True)
            except Exception as e:
                print(f"[music] Error disconnecting: {e}")

    def get_queue(self, guild_id: int) -> deque:
        if guild_id not in self.queues:
            self.queues[guild_id] = deque()
        return self.queues[guild_id]

    def get_volume(self, guild_id: int) -> float:
        return self.volumes.get(guild_id, 0.5)

    def set_volume(self, guild_id: int, vol: float):
        self.volumes[guild_id] = max(0.0, min(1.0, vol))

    def get_voice_client(self, guild: discord.Guild) -> Optional[discord.VoiceClient]:
        """Get the voice client for this guild from bot's voice_clients list"""
        for vc in self.bot.voice_clients:
            if vc.guild.id == guild.id:
                return vc
        return None

    async def ensure_voice_connected(self, guild: discord.Guild, channel: discord.VoiceChannel) -> Optional[discord.VoiceClient]:
        """Ensure we have a voice connection, reconnecting if needed"""
        vc = self.get_voice_client(guild)

        if vc and vc.is_connected():
            return vc

        # Need to connect or reconnect
        print(f"[music] Connecting/reconnecting to voice channel: {channel.name}")
        try:
            if vc:
                await vc.disconnect(force=True)
            vc = await channel.connect(timeout=10.0, reconnect=True)
            print(f"[music] Voice connection established")
            return vc
        except Exception as e:
            print(f"[music] Failed to connect to voice: {e}")
            return None

    async def play_next(self, guild: discord.Guild, channel: discord.abc.Messageable):
        """Play the next song in queue"""
        guild_id = guild.id
        queue = self.get_queue(guild_id)
        print(f"[music] play_next called for guild {guild_id}, queue size: {len(queue)}")

        # Check if we should loop
        if self.loop_mode.get(guild_id) and self.current.get(guild_id):
            queue.appendleft(self.current[guild_id])

        if not queue:
            print(f"[music] Queue empty, nothing to play")
            self.current[guild_id] = None
            return

        song = queue.popleft()
        self.current[guild_id] = song
        print(f"[music] Attempting to play: {song.title}")

        vc = self.get_voice_client(guild)
        if not vc:
            print(f"[music] No voice client found!")
            self.current[guild_id] = None
            return
        if not vc.is_connected():
            print(f"[music] Voice client not connected!")
            self.current[guild_id] = None
            return

        print(f"[music] Voice client connected to: {vc.channel.name}")

        try:
            # Only re-fetch if stream URL is missing or empty
            if not song.stream_url:
                print(f"[music] No stream URL, fetching for: {song.url}")
                fresh_song = await Song.from_query(song.url, song.requester, self.bot.loop)
                if fresh_song and fresh_song.stream_url:
                    song = fresh_song
                    self.current[guild_id] = song
                    print(f"[music] Got stream URL")
                else:
                    print(f"[music] ERROR: Could not get stream URL!")
                    await channel.send(f"❌ Could not get audio stream for **{song.title}**")
                    await self.play_next(guild, channel)
                    return

            source = song.create_source(self.get_volume(guild_id))
            print(f"[music] Audio source created, starting playback...")

            def after_playing(error):
                if error:
                    print(f"[music] Playback error: {error}")
                else:
                    print(f"[music] Playback finished normally")
                # Schedule next song
                coro = self.play_next(guild, channel)
                fut = asyncio.run_coroutine_threadsafe(coro, self.bot.loop)
                try:
                    fut.result()
                except Exception as e:
                    print(f"[music] Error scheduling next: {e}")

            vc.play(source, after=after_playing)
            print(f"[music] vc.play() called successfully, is_playing: {vc.is_playing()}")

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

            await channel.send(embed=embed)

        except Exception as e:
            import traceback
            print(f"[music] Error playing: {e}")
            print(f"[music] Traceback: {traceback.format_exc()}")
            await channel.send(f"❌ Error playing **{song.title}**: {e}")
            # Try next song
            await self.play_next(guild, channel)

    @commands.command(name="join", aliases=["connect"])
    async def join(self, ctx):
        """Join your voice channel"""
        if not ctx.author.voice:
            return await ctx.send("❌ You need to be in a voice channel!")

        channel = ctx.author.voice.channel
        vc = self.get_voice_client(ctx.guild)

        if vc and vc.is_connected():
            if vc.channel.id == channel.id:
                return await ctx.send(f"✅ Already in **{channel.name}**")
            await vc.move_to(channel)
        else:
            await channel.connect(timeout=10.0, reconnect=True)

        await ctx.send(f"Joined **{channel.name}**")

    @commands.command(name="leave", aliases=["disconnect", "dc", "gtfo"])
    async def leave(self, ctx):
        """Leave the voice channel"""
        vc = self.get_voice_client(ctx.guild)
        if not vc:
            return await ctx.send("❌ I'm not in a voice channel!")

        print(f"[music] Leaving voice channel in guild {ctx.guild.id}")

        # Clear queue
        guild_id = ctx.guild.id
        self.queues[guild_id] = deque()
        self.current[guild_id] = None

        await vc.disconnect(force=True)
        await ctx.send("Disconnected!")

    @commands.command(name="play")
    async def play(self, ctx, *, query: str):
        """
        Play a song from YouTube

        Usage: play <song name or URL>
        """
        print(f"[music] Play command received: {query}")

        if not YTDL_AVAILABLE:
            return await ctx.send("❌ yt-dlp not installed. Run: `pip install yt-dlp`")

        if not FFMPEG_PATH:
            return await ctx.send("❌ FFmpeg not found. Audio playback unavailable.")

        # Check user is in voice channel
        if not ctx.author.voice:
            return await ctx.send("❌ You need to be in a voice channel!")

        voice_channel = ctx.author.voice.channel

        # Search FIRST (before connecting) - this is the slow part
        async with ctx.typing():
            try:
                print(f"[music] Searching for: {query}")
                song = await Song.from_query(query, ctx.author, self.bot.loop)

                if not song:
                    print(f"[music] No song found for query: {query}")
                    return await ctx.send(f"❌ Could not find: **{query}**")

                if not song.stream_url:
                    print(f"[music] Song found but no stream URL!")
                    return await ctx.send(f"❌ Could not get audio stream for: **{query}**")

                print(f"[music] Found song: {song.title}, stream_url: yes ({len(song.stream_url)} chars)")

            except Exception as e:
                import traceback
                print(f"[music] Search error: {e}")
                print(f"[music] Traceback: {traceback.format_exc()}")
                return await ctx.send(f"❌ Error searching: {e}")

        # NOW connect to voice (after search is done)
        vc = self.get_voice_client(ctx.guild)
        print(f"[music] Current vc: {vc}, connected: {vc.is_connected() if vc else 'N/A'}", flush=True)

        if not vc or not vc.is_connected():
            print(f"[music] Connecting to voice channel: {voice_channel.name}", flush=True)
            try:
                # Disconnect any stale voice client first
                if vc:
                    print(f"[music] Disconnecting stale voice client", flush=True)
                    try:
                        await vc.disconnect(force=True)
                    except:
                        pass
                    await asyncio.sleep(0.5)

                vc = await voice_channel.connect(timeout=15.0, reconnect=True)
                print(f"[music] Voice connect returned: {vc}", flush=True)
                print(f"[music] vc.is_connected(): {vc.is_connected()}", flush=True)
                print(f"[music] Connected to voice channel successfully", flush=True)
            except Exception as e:
                import traceback
                print(f"[music] Failed to connect to voice: {e}", flush=True)
                print(f"[music] Voice connect traceback: {traceback.format_exc()}", flush=True)
                return await ctx.send(f"❌ Could not join voice channel: {e}")
        else:
            print(f"[music] Already connected to voice", flush=True)

        # Add to queue
        print(f"[music] About to add to queue...", flush=True)
        queue = self.get_queue(ctx.guild.id)
        queue.append(song)
        print(f"[music] Added to queue, queue size: {len(queue)}", flush=True)

        # If not playing, start playback
        is_playing = vc.is_playing()
        is_paused = vc.is_paused()
        print(f"[music] Voice state - is_playing: {is_playing}, is_paused: {is_paused}")

        if not is_playing and not is_paused:
            print(f"[music] Starting playback...")
            await self.play_next(ctx.guild, ctx.channel)
        else:
            # Added to queue
            embed = discord.Embed(
                title="Added to Queue",
                description=f"**[{song.title}]({song.url})**",
                color=0x3498db
            )
            embed.add_field(name="Position", value=str(len(queue)), inline=True)
            embed.add_field(name="Duration", value=song.duration_str, inline=True)
            if song.thumbnail:
                embed.set_thumbnail(url=song.thumbnail)
            await ctx.send(embed=embed)

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
        
        await ctx.send("Stopped and cleared queue!")

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause playback"""
        if not ctx.voice_client:
            return await ctx.send("❌ Not playing anything!")
        
        if ctx.voice_client.is_playing():
            ctx.voice_client.pause()
            await ctx.send("⏸Paused!")
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
            await ctx.send("▶Resumed!")
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
                name="Now Playing",
                value=f"**{current.title}** [{current.duration_str}]",
                inline=False
            )
        
        if queue:
            lines = []
            for i, song in enumerate(list(queue)[:10], 1):
                lines.append(f"`{i}.` **{song.title}** [{song.duration_str}]")
            embed.add_field(name="Up Next", value="\n".join(lines), inline=False)
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
            title="Now Playing",
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
            return await ctx.send(f"Volume: **{current_vol}%**")
        
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
            await ctx.send("Loop **enabled**")
        else:
            await ctx.send("Loop **disabled**")

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
        
        await ctx.send("Queue shuffled!")

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
        
        await ctx.send(f"Removed **{removed.title}**")

    @commands.command(name="lyrics", aliases=["ly"])
    async def lyrics(self, ctx, *, query: str = None):
        """
        Get lyrics for a song

        Usage: lyrics <artist> - <song>
        Or just: lyrics (uses current playing song)
        """
        if not query:
            current = self.current.get(ctx.guild.id)
            if current:
                query = current.title
            else:
                return await ctx.send("❌ Specify a song or play something first!")

        async with ctx.typing():
            try:
                # Try to parse "Artist - Song" format
                # Common formats: "Artist - Song", "Song by Artist", "Artist: Song"
                artist = None
                song = None

                # Clean up common YouTube title artifacts
                clean_query = re.sub(r'\(Official.*?\)|\[Official.*?\]|\(Lyrics.*?\)|\[Lyrics.*?\]|\(Audio.*?\)|\[Audio.*?\]|\(HD\)|\[HD\]|\(HQ\)|\[HQ\]|Official Video|Official Audio|Lyric Video|Music Video', '', query, flags=re.IGNORECASE)
                clean_query = clean_query.strip()

                if ' - ' in clean_query:
                    parts = clean_query.split(' - ', 1)
                    artist = parts[0].strip()
                    song = parts[1].strip()
                elif ' by ' in clean_query.lower():
                    idx = clean_query.lower().index(' by ')
                    song = clean_query[:idx].strip()
                    artist = clean_query[idx+4:].strip()
                else:
                    # No clear separator - use the whole thing as song, leave artist empty
                    song = clean_query
                    artist = ""

                # URL encode artist and song
                artist_encoded = quote(artist) if artist else ""
                song_encoded = quote(song)

                # Try lyrics.ovh API
                if artist:
                    url = f"https://api.lyrics.ovh/v1/{artist_encoded}/{song_encoded}"
                else:
                    # If no artist, try with just the song name (less reliable)
                    url = f"https://api.lyrics.ovh/v1/_/{song_encoded}"

                resp = requests.get(url, timeout=15)

                if resp.status_code == 200:
                    data = resp.json()
                    if 'lyrics' in data and data['lyrics']:
                        lyrics_text = data['lyrics'].strip()
                        if len(lyrics_text) > 3900:
                            lyrics_text = lyrics_text[:3900] + "\n\n*...(truncated)*"

                        title_display = f"{artist} - {song}" if artist else song
                        embed = discord.Embed(
                            title=f"🎤 {title_display}",
                            description=lyrics_text,
                            color=0x1db954
                        )
                        embed.set_footer(text="Lyrics from lyrics.ovh")
                        return await ctx.send(embed=embed)

                # No lyrics found
                await ctx.send(f"❌ No lyrics found for **{query}**\nTip: Try format `lyrics Artist - Song`")
            except requests.exceptions.Timeout:
                await ctx.send("❌ Lyrics request timed out. Try again.")
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

    @commands.command(name="musicdebug", aliases=["mdebug"], hidden=True)
    @commands.is_owner()
    async def musicdebug(self, ctx):
        """Debug command to check music system status"""
        embed = discord.Embed(title="🔧 Music Debug Info", color=0xff9900)

        # Check dependencies
        embed.add_field(name="yt-dlp", value="✅ Available" if YTDL_AVAILABLE else "❌ Missing", inline=True)
        embed.add_field(name="FFmpeg", value=f"✅ {FFMPEG_PATH}" if FFMPEG_PATH else "❌ Not found", inline=True)

        try:
            import nacl
            nacl_status = "✅ Available"
        except ImportError:
            nacl_status = "❌ Missing"
        embed.add_field(name="PyNaCl", value=nacl_status, inline=True)

        # Voice client status
        vc = ctx.voice_client
        if vc:
            embed.add_field(name="Voice Connected", value=f"✅ {vc.channel.name}", inline=True)
            embed.add_field(name="Is Playing", value=str(vc.is_playing()), inline=True)
            embed.add_field(name="Is Paused", value=str(vc.is_paused()), inline=True)
        else:
            embed.add_field(name="Voice Connected", value="❌ Not connected", inline=True)

        # Queue status
        guild_id = ctx.guild.id
        queue = self.get_queue(guild_id)
        current = self.current.get(guild_id)
        embed.add_field(name="Queue Size", value=str(len(queue)), inline=True)
        embed.add_field(name="Current Song", value=current.title[:50] if current else "None", inline=True)

        # Test yt-dlp
        if YTDL_AVAILABLE:
            try:
                ytdl = yt_dlp.YoutubeDL({'quiet': True})
                embed.add_field(name="yt-dlp Version", value=yt_dlp.version.__version__, inline=True)
            except Exception as e:
                embed.add_field(name="yt-dlp Test", value=f"❌ {e}", inline=True)

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Music(bot))