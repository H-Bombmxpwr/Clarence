import discord
from discord.ext import commands
import youtube_dl
import requests
from contextlib import suppress
#from utils import Pager


class music(commands.Cog, description = 'Play Music on a voice channel and grab lyrics from a song'):
    def __init__(self, client):
        self.client = client

    @commands.command(help = 'Info for the music commands')
    async def music(self,ctx):
      embedVar = discord.Embed(title="Music Commands", descripion="", color=0xff0080).set_thumbnail(url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/Logo_of_YouTube_%282015-2017%29.svg/2560px-Logo_of_YouTube_%282015-2017%29.svg.png")

      embedVar.add_field(name= "`$join`", value = "The bot will join a voice channel if the user who called the bot is in a channel\n", inline = False)
      embedVar.add_field(name = "`$play: ` <YouTube Video Link>", value = "Will play any video off of YouTube if given a link\n", inline = False) 
      embedVar.add_field(name = "`$pause` & `$resume`", value = "Pause and Resume the player\n", inline = False)
      embedVar.add_field(name = "`$disconnect`", value = "Disconnects the player from the given voice channel\n", inline = False)
      embedVar.add_field(name = "`$lyrics: `", value = "Pulls the lyrics to a queried song\n", inline = False)
      embedVar.add_field(name = "`$music`", value = "Brings up a list of commands for the music player\n", inline = False)
      await ctx.send(embed=embedVar)

    
    @commands.command(help = 'Join a voice channel')
    async def join(self,ctx):
        if ctx.author.voice is None:
            await ctx.send("```You're not in a voice channel!\n Join one first pleb```")
        voice_channel = ctx.author.voice.channel
        print(type(voice_channel))
        if ctx.voice_client is None:
            await voice_channel.connect()
            await ctx.send("```Joined: " + str(voice_channel) + '```')
        else:
            await ctx.voice_client.move_to(voice_channel)
            await ctx.send("```Joined: " + str(voice_channel) + '```')

    @commands.command(help = 'Leave a voice channel', aliases = ['dis'])
    async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()
        await ctx.send("```Cya!```")

    @commands.command(help = 'Play a song')
    async def play(self,ctx,url):
        ctx.voice_client.stop()
        FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        YDL_OPTIONS = {'format':"bestaudio"}
        vc = ctx.voice_client

        with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']
            source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            vc.play(source)
            await ctx.send("```Now playing: " + info.get('title', None)+'```')
    
    @commands.command(help = 'Pause the current song',aliases = ['pa'])
    async def pause(self,ctx):
        await ctx.send("```Paused ⏸```")
        await ctx.voice_client.pause()
        
    
    @commands.command(help = 'Resume the current song', aliases = ['res'])
    async def resume(self,ctx):
        await ctx.send("```Resumed ▶️```")
        await ctx.voice_client.resume()


    @commands.command(help="Get lyrics for a song", aliases=["ly"])
    async def lyrics(self, ctx, *, song):
        with suppress(AttributeError):
            await ctx.trigger_typing()

        json = requests.get(f"https://some-random-api.ml/lyrics?title={song}").json()

        with suppress(KeyError):
            if json["error"]:
                await ctx.send("❌ " + json["error"])
                return

        lyrics = json['lyrics']
        if len(lyrics) > 2048:
          lyrics = lyrics[:2045] + '...'

        embedVar = discord.Embed(title = 'Lyrics for ' + str(json["title"] + ", By " + json["author"]), description = lyrics ,color = ctx.author.color).set_thumbnail(url = json["thumbnail"]["genius"]).set_footer(text=  'As requested by @' + str(ctx.author.name) ,icon_url = ctx.author.avatar_url)

        await ctx.send(embed = embedVar)

def setup(client):
    client.add_cog(music(client))