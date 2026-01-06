# cogs/music.py
import discord
from discord.ext import commands
import asyncio
import os
import re
from typing import Optional, Dict, List
from collections import deque
import json

# Try to import yt-dlp (fork of youtube-dl)
try:
    import yt_dlp as youtube_dl
    YTDL_AVAILABLE = True
except ImportError:
    YTDL_AVAILABLE = False

# For lyrics
import requests
from urllib.parse import quote

# yt-dlp options
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}


class Song:
    """Represents a song in the queue"""
    def __init__(self, source: str, title: str, url: str, duration: int, requester: discord.Member, thumbnail: str = None):
        self.source = source
        self.title = title
        self.url = url
        self.duration = duration
        self.requester = requester
        self.thumbnail = thumbnail

    @property
    def duration_str(self) -> str:
        if self.duration:
            mins, secs = divmod(self.duration, 60)
            hours, mins = divmod(mins, 60)
            if hours:
                return f"{hours}:{mins:02d}:{secs:02d}"
            return f"{mins}:{secs:02d}"
        return "Unknown"


class GuildMusicState:
    """Per-guild music state"""
    def __init__(self):
        self.queue: deque = deque()
        self.current: Optional[Song] = None
        self.voice_client: Optional[discord.VoiceClient] = None
        self.volume: float = 0.5
        self.loop: bool = False
        self.skip_votes: set = set()


class Music(commands.Cog):
    """🎵 Music Commands - Play music in voice channels!"""

    def __init__(self, bot):
        self.bot = bot
        self.states: Dict[int, GuildMusicState] = {}

    def get_state(self, guild_id: int) -> GuildMusicState:
        if guild_id not in self.states:
            self.states[guild_id] = GuildMusicState()
        return self.states[guild_id]

    def cleanup(self, guild_id: int):
        if guild_id in self.states:
            del self.states[guild_id]

    async def ensure_voice(self, ctx) -> bool:
        """Ensure user is in a voice channel and bot can connect"""
        if ctx.author.voice is None:
            await ctx.send("❌ You need to be in a voice channel!")
            return False
        
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client is None:
            try:
                state.voice_client = await ctx.author.voice.channel.connect()
            except discord.ClientException:
                await ctx.send("❌ Already connected to a voice channel.")
                return False
            except Exception as e:
                await ctx.send(f"❌ Could not connect: {e}")
                return False
        elif state.voice_client.channel != ctx.author.voice.channel:
            await state.voice_client.move_to(ctx.author.voice.channel)
        
        return True

    async def search_youtube(self, query: str) -> Optional[dict]:
        """Search YouTube and return video info"""
        if not YTDL_AVAILABLE:
            return None
        
        ytdl = youtube_dl.YoutubeDL(YTDL_OPTIONS)
        
        try:
            # Check if it's a URL
            if not re.match(r'^https?://', query):
                query = f"ytsearch:{query}"
            
            info = ytdl.extract_info(query, download=False)
            
            if 'entries' in info:
                info = info['entries'][0]
            
            return info
        except Exception as e:
            print(f"YouTube search error: {e}")
            return None

    async def play_next(self, ctx):
        """Play the next song in queue"""
        state = self.get_state(ctx.guild.id)
        
        if state.loop and state.current:
            # Re-add current song to front of queue
            state.queue.appendleft(state.current)
        
        if not state.queue:
            state.current = None
            # Disconnect after 5 minutes of inactivity
            await asyncio.sleep(300)
            if state.voice_client and not state.current and not state.queue:
                await state.voice_client.disconnect()
                self.cleanup(ctx.guild.id)
            return
        
        state.current = state.queue.popleft()
        state.skip_votes.clear()
        
        try:
            source = discord.FFmpegPCMAudio(state.current.source, **FFMPEG_OPTIONS)
            source = discord.PCMVolumeTransformer(source, volume=state.volume)
            
            def after_playing(error):
                if error:
                    print(f"Player error: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(ctx), self.bot.loop)
            
            state.voice_client.play(source, after=after_playing)
            
            embed = discord.Embed(
                title="🎵 Now Playing",
                description=f"**[{state.current.title}]({state.current.url})**",
                color=0x1db954
            )
            embed.add_field(name="Duration", value=state.current.duration_str, inline=True)
            embed.add_field(name="Requested by", value=state.current.requester.mention, inline=True)
            if state.current.thumbnail:
                embed.set_thumbnail(url=state.current.thumbnail)
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error playing: {e}")
            await self.play_next(ctx)

    @commands.command(name="join", aliases=["connect"])
    async def join(self, ctx):
        """Join your voice channel"""
        if ctx.author.voice is None:
            return await ctx.send("❌ You need to be in a voice channel!")
        
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client:
            await state.voice_client.move_to(ctx.author.voice.channel)
        else:
            state.voice_client = await ctx.author.voice.channel.connect()
        
        await ctx.send(f"🔊 Joined **{ctx.author.voice.channel.name}**")

    @commands.command(name="leave", aliases=["disconnect", "dc"])
    async def leave(self, ctx):
        """Leave the voice channel"""
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client:
            await state.voice_client.disconnect()
            self.cleanup(ctx.guild.id)
            await ctx.send("👋 Disconnected!")
        else:
            await ctx.send("❌ Not connected to a voice channel.")

    @commands.command(name="play", aliases=["pl"])
    async def play(self, ctx, *, query: str):
        """
        Play a song from YouTube
        
        Usage: play <song name or URL>
        Example: play never gonna give you up
        """
        if not YTDL_AVAILABLE:
            return await ctx.send("❌ Music playback is not available (yt-dlp not installed).")
        
        if not await self.ensure_voice(ctx):
            return
        
        state = self.get_state(ctx.guild.id)
        
        async with ctx.typing():
            info = await self.search_youtube(query)
            
            if not info:
                return await ctx.send("❌ Could not find that song.")
            
            song = Song(
                source=info.get('url'),
                title=info.get('title', 'Unknown'),
                url=info.get('webpage_url', ''),
                duration=info.get('duration', 0),
                requester=ctx.author,
                thumbnail=info.get('thumbnail')
            )
            
            state.queue.append(song)
            
            if state.voice_client.is_playing() or state.current:
                embed = discord.Embed(
                    title="📋 Added to Queue",
                    description=f"**[{song.title}]({song.url})**",
                    color=0x3498db
                )
                embed.add_field(name="Position", value=str(len(state.queue)), inline=True)
                embed.add_field(name="Duration", value=song.duration_str, inline=True)
                await ctx.send(embed=embed)
            else:
                await self.play_next(ctx)

    @commands.command(name="playskip", aliases=["ps"])
    async def playskip(self, ctx, *, query: str):
        """Skip current song and play this one immediately"""
        if not YTDL_AVAILABLE:
            return await ctx.send("❌ Music playback not available.")
        
        if not await self.ensure_voice(ctx):
            return
        
        state = self.get_state(ctx.guild.id)
        
        async with ctx.typing():
            info = await self.search_youtube(query)
            if not info:
                return await ctx.send("❌ Could not find that song.")
            
            song = Song(
                source=info.get('url'),
                title=info.get('title', 'Unknown'),
                url=info.get('webpage_url', ''),
                duration=info.get('duration', 0),
                requester=ctx.author,
                thumbnail=info.get('thumbnail')
            )
            
            # Add to front of queue
            state.queue.appendleft(song)
            
            # Skip current
            if state.voice_client.is_playing():
                state.voice_client.stop()
            else:
                await self.play_next(ctx)

    @commands.command(name="skip", aliases=["s"])
    async def skip(self, ctx):
        """Skip the current song (requires votes or DJ/Admin)"""
        state = self.get_state(ctx.guild.id)
        
        if not state.voice_client or not state.voice_client.is_playing():
            return await ctx.send("❌ Nothing is playing.")
        
        # Check if user has DJ role or is admin
        is_privileged = ctx.author.guild_permissions.administrator
        dj_role = discord.utils.get(ctx.guild.roles, name="DJ")
        if dj_role and dj_role in ctx.author.roles:
            is_privileged = True
        
        # Requester can always skip their own song
        if state.current and state.current.requester == ctx.author:
            is_privileged = True
        
        if is_privileged:
            state.voice_client.stop()
            await ctx.send("⏭️ Skipped!")
        else:
            # Vote skip
            state.skip_votes.add(ctx.author.id)
            listeners = len([m for m in state.voice_client.channel.members if not m.bot])
            needed = max(2, listeners // 2)
            
            if len(state.skip_votes) >= needed:
                state.voice_client.stop()
                await ctx.send("⏭️ Vote skip passed!")
            else:
                await ctx.send(f"⏭️ Skip vote: {len(state.skip_votes)}/{needed}")

    @commands.command(name="pause")
    async def pause(self, ctx):
        """Pause the current song"""
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client and state.voice_client.is_playing():
            state.voice_client.pause()
            await ctx.send("⏸️ Paused!")
        else:
            await ctx.send("❌ Nothing is playing.")

    @commands.command(name="resume", aliases=["unpause"])
    async def resume(self, ctx):
        """Resume playback"""
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client and state.voice_client.is_paused():
            state.voice_client.resume()
            await ctx.send("▶️ Resumed!")
        else:
            await ctx.send("❌ Nothing is paused.")

    @commands.command(name="stop")
    async def stop(self, ctx):
        """Stop playback and clear queue"""
        state = self.get_state(ctx.guild.id)
        
        if state.voice_client:
            state.queue.clear()
            state.current = None
            state.voice_client.stop()
            await ctx.send("⏹️ Stopped and cleared queue!")
        else:
            await ctx.send("❌ Not playing anything.")

    @commands.command(name="queue", aliases=["q"])
    async def queue(self, ctx, page: int = 1):
        """View the music queue"""
        state = self.get_state(ctx.guild.id)
        
        if not state.current and not state.queue:
            return await ctx.send("📋 Queue is empty!")
        
        embed = discord.Embed(title="🎵 Music Queue", color=0x3498db)
        
        if state.current:
            embed.add_field(
                name="Now Playing",
                value=f"**[{state.current.title}]({state.current.url})** [{state.current.duration_str}]\nRequested by {state.current.requester.mention}",
                inline=False
            )
        
        if state.queue:
            per_page = 10
            start = (page - 1) * per_page
            end = start + per_page
            queue_list = list(state.queue)[start:end]
            
            queue_text = ""
            for i, song in enumerate(queue_list, start=start + 1):
                queue_text += f"`{i}.` **[{song.title}]({song.url})** [{song.duration_str}]\n"
            
            if queue_text:
                embed.add_field(name="Up Next", value=queue_text[:1024], inline=False)
            
            total_pages = (len(state.queue) + per_page - 1) // per_page
            embed.set_footer(text=f"Page {page}/{total_pages} • {len(state.queue)} song(s) in queue")
        
        await ctx.send(embed=embed)

    @commands.command(name="nowplaying", aliases=["np"])
    async def nowplaying(self, ctx):
        """Show the currently playing song"""
        state = self.get_state(ctx.guild.id)
        
        if not state.current:
            return await ctx.send("❌ Nothing is playing.")
        
        embed = discord.Embed(
            title="🎵 Now Playing",
            description=f"**[{state.current.title}]({state.current.url})**",
            color=0x1db954
        )
        embed.add_field(name="Duration", value=state.current.duration_str, inline=True)
        embed.add_field(name="Requested by", value=state.current.requester.mention, inline=True)
        embed.add_field(name="Volume", value=f"{int(state.volume * 100)}%", inline=True)
        if state.current.thumbnail:
            embed.set_thumbnail(url=state.current.thumbnail)
        
        await ctx.send(embed=embed)

    @commands.command(name="volume", aliases=["vol"])
    async def volume(self, ctx, vol: int = None):
        """Set the volume (0-100)"""
        state = self.get_state(ctx.guild.id)
        
        if vol is None:
            return await ctx.send(f"🔊 Current volume: **{int(state.volume * 100)}%**")
        
        if vol < 0 or vol > 100:
            return await ctx.send("❌ Volume must be between 0 and 100.")
        
        state.volume = vol / 100
        
        if state.voice_client and state.voice_client.source:
            state.voice_client.source.volume = state.volume
        
        await ctx.send(f"🔊 Volume set to **{vol}%**")

    @commands.command(name="loop")
    async def loop(self, ctx):
        """Toggle loop mode for current song"""
        state = self.get_state(ctx.guild.id)
        state.loop = not state.loop
        
        if state.loop:
            await ctx.send("🔁 Loop **enabled**")
        else:
            await ctx.send("🔁 Loop **disabled**")

    @commands.command(name="shuffle")
    async def shuffle(self, ctx):
        """Shuffle the queue"""
        import random
        state = self.get_state(ctx.guild.id)
        
        if len(state.queue) < 2:
            return await ctx.send("❌ Not enough songs to shuffle.")
        
        queue_list = list(state.queue)
        random.shuffle(queue_list)
        state.queue = deque(queue_list)
        
        await ctx.send("🔀 Queue shuffled!")

    @commands.command(name="remove")
    async def remove(self, ctx, position: int):
        """Remove a song from the queue by position"""
        state = self.get_state(ctx.guild.id)
        
        if position < 1 or position > len(state.queue):
            return await ctx.send(f"❌ Invalid position. Queue has {len(state.queue)} songs.")
        
        queue_list = list(state.queue)
        removed = queue_list.pop(position - 1)
        state.queue = deque(queue_list)
        
        await ctx.send(f"🗑️ Removed **{removed.title}** from queue.")

    @commands.command(name="clear")
    async def clear_queue(self, ctx):
        """Clear the entire queue"""
        state = self.get_state(ctx.guild.id)
        state.queue.clear()
        await ctx.send("🗑️ Queue cleared!")

    # ----------------------------
    # Lyrics Commands
    # ----------------------------

    @commands.command(name="lyrics", aliases=["ly"])
    async def lyrics(self, ctx, *, query: str = None):
        """
        Get lyrics for a song
        
        Usage: lyrics <song name> or lyrics (for current song)
        Example: lyrics never gonna give you up
        """
        state = self.get_state(ctx.guild.id)
        
        # Use current song if no query
        if query is None:
            if state.current:
                query = state.current.title
            else:
                return await ctx.send("❌ Please specify a song name or play a song first!")
        
        async with ctx.typing():
            # Try lyrics.ovh API
            lyrics = await self._fetch_lyrics_ovh(query)
            
            if not lyrics:
                # Try some-random-api
                lyrics = await self._fetch_lyrics_sra(query)
            
            if not lyrics:
                return await ctx.send(f"❌ Could not find lyrics for **{query}**")
            
            # Split lyrics if too long
            title = lyrics.get('title', query)
            artist = lyrics.get('artist', 'Unknown')
            text = lyrics.get('lyrics', '')
            
            if len(text) > 4000:
                text = text[:4000] + "...\n\n*(Lyrics truncated)*"
            
            # Split into multiple embeds if needed
            chunks = [text[i:i+1024] for i in range(0, len(text), 1024)]
            
            embed = discord.Embed(
                title=f"🎵 {title}",
                description=f"**Artist:** {artist}",
                color=0x1db954
            )
            
            for i, chunk in enumerate(chunks[:6]):  # Max 6 fields
                embed.add_field(
                    name="Lyrics" if i == 0 else "\u200b",
                    value=chunk,
                    inline=False
                )
            
            if len(chunks) > 6:
                embed.set_footer(text="Lyrics truncated due to length")
            
            await ctx.send(embed=embed)

    async def _fetch_lyrics_ovh(self, query: str) -> Optional[dict]:
        """Fetch lyrics from lyrics.ovh"""
        try:
            # Try to split artist and title
            parts = query.split(' - ', 1)
            if len(parts) == 2:
                artist, title = parts
            else:
                # Search with query as is
                artist = ""
                title = query
            
            if artist:
                url = f"https://api.lyrics.ovh/v1/{quote(artist)}/{quote(title)}"
            else:
                # This API needs both artist and title, so this might not work
                return None
            
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'lyrics' in data:
                    return {
                        'title': title,
                        'artist': artist,
                        'lyrics': data['lyrics']
                    }
        except Exception as e:
            print(f"lyrics.ovh error: {e}")
        return None

    async def _fetch_lyrics_sra(self, query: str) -> Optional[dict]:
        """Fetch lyrics from some-random-api"""
        try:
            url = f"https://some-random-api.com/lyrics?title={quote(query)}"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if 'lyrics' in data:
                    return {
                        'title': data.get('title', query),
                        'artist': data.get('author', 'Unknown'),
                        'lyrics': data['lyrics']
                    }
        except Exception as e:
            print(f"SRA lyrics error: {e}")
        return None

    @commands.command(name="music", aliases=["musichelp"])
    async def music_help(self, ctx):
        """Show all music commands"""
        embed = discord.Embed(
            title="🎵 Music Commands",
            description="Play music in voice channels!",
            color=0x1db954
        )
        
        commands_list = [
            ("`play <query>`", "Play a song from YouTube"),
            ("`playskip <query>`", "Skip current and play immediately"),
            ("`pause`", "Pause playback"),
            ("`resume`", "Resume playback"),
            ("`skip`", "Skip current song"),
            ("`stop`", "Stop and clear queue"),
            ("`queue`", "View the queue"),
            ("`nowplaying`", "Show current song"),
            ("`volume <0-100>`", "Set volume"),
            ("`loop`", "Toggle loop mode"),
            ("`shuffle`", "Shuffle the queue"),
            ("`remove <pos>`", "Remove from queue"),
            ("`clear`", "Clear the queue"),
            ("`join`", "Join voice channel"),
            ("`leave`", "Leave voice channel"),
            ("`lyrics [song]`", "Get song lyrics"),
        ]
        
        for cmd, desc in commands_list:
            embed.add_field(name=cmd, value=desc, inline=True)
        
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Music(bot))