import discord
from discord.ext import commands
import youtube_dl
import requests
from contextlib import suppress
from youtube_search import YoutubeSearch
import json


class Music(commands.Cog):
  """ 
  Module for playing music in a voice channel
  """
  def __init__(self, client):
        self.client = client

  @commands.command(help = 'Info for the music commands')
  async def music(self,ctx):
      embedVar = discord.Embed(title="Music Commands", descripion="", color=0xff0080).set_thumbnail(url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/Logo_of_YouTube_%282015-2017%29.svg/2560px-Logo_of_YouTube_%282015-2017%29.svg.png")

      embedVar.add_field(name = "\u200b" ,value= "`      join: ` The bot will join the current voice channel\n `      play: ` + <song query> plays a song\n `     music: ` Brings up a list of music commands\n`     pause: ` Pause the player\n`    lyrics: `Pulls the lyrics to a queried song\n `    resume: `  Resume the player\n`disconnect: ` Disconnects the bot from the voice channel\n", inline = False)
      await ctx.send(embed=embedVar)

    
  @commands.command(help = 'Join a voice channel')
  async def join(self,ctx):
        if ctx.author.voice is None:
            await ctx.send("You're not in a voice channel!\nJoin one first pleb")
        voice_channel = ctx.author.voice.channel
      
        if ctx.voice_client is None:
            await voice_channel.connect()
            await ctx.send("Joined: " + str(voice_channel))
        else:
            await ctx.voice_client.move_to(voice_channel)
  
   
  @commands.command(help = 'Leave a voice channel', aliases = ['dis','leave'])
  async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()
        await ctx.send("Cya!")

  @commands.command(help = 'Play a song')
  async def play(self,ctx,*,song:str):
        
        #get the bot to join the player if it isnt alredy in it
        await ctx.invoke(self.client.get_command('join'))
        
        #search the song/ check if a url was sent
        if str(song).find("https://www.youtube.com") == -1:
          yt = YoutubeSearch(str(song), max_results=1).to_json()
          song_id = str(json.loads(yt)['videos'][0]['id'])
          url = "https://www.youtube.com/watch?v=" + song_id
          if url == None:
            await ctx.send("Song not found")
            return
        else:
          url = str(song)

        with suppress(AttributeError):
          await ctx.trigger_typing()  
        
        #plays the url generated above
        ctx.voice_client.stop()
        FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        YDL_OPTIONS = {'format':"bestaudio"}
        vc = ctx.voice_client
        try:
          with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']
            source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            vc.play(source)
            await ctx.send("Now playing: " + info.get('title', None) + '\n' + url)
        except:
          await ctx.send("There was an error getting that song\nIt could be age restricted or private. Try a different song")
    
  @commands.command(help = 'Pause the current song',aliases = ['pa'])
  async def pause(self,ctx):
        await ctx.send("Paused ⏸")
        await ctx.voice_client.pause()
        
    
  @commands.command(help = 'Resume the current song', aliases = ['res'])
  async def resume(self,ctx):
        await ctx.send("Resumed ▶️")
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

        embedVar = discord.Embed(title = 'Lyrics for ' + str(json["title"] + ", By " + json["author"]), description = lyrics ,color = ctx.author.color).set_thumbnail(url = json["thumbnail"]["genius"]).set_footer(text=  'Requested by ' + str(ctx.author.name) ,icon_url = ctx.author.avatar_url)

        await ctx.send(embed = embedVar)

def setup(client):
    client.add_cog(Music(client))