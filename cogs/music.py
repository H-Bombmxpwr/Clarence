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
        self.qu = {}

  @commands.command(help = 'Info for the music commands')
  async def music(self,ctx):
      embedVar = discord.Embed(title="Music Commands", description = "`      join: ` The bot will join the current voice channel\n `      play: ` + <song query> plays a song\n `     music: ` Brings up a list of music commands\n`     pause: ` Pause the player\n`    lyrics: `Pulls the lyrics to a queried song\n `    resume: `  Resume the player\n`disconnect: ` Disconnects the bot from the voice channel\n", color=0xff0080).set_thumbnail(url = "https://upload.wikimedia.org/wikipedia/commons/thumb/e/e1/Logo_of_YouTube_%282015-2017%29.svg/2560px-Logo_of_YouTube_%282015-2017%29.svg.png")
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
  
  @commands.command(help = "Clear the queue",aliases = ['cq'])
  async def clearqueue(self,ctx):
    self.qu = {}
    await ctx.send("The queue has been cleared")
  
  @commands.command(help = 'Leave a voice channel', aliases = ['dis','leave'])
  async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()
        self.qu = {}
        ctx.voice_client.cleanup()
        await ctx.send("Cya!")
        


  @commands.command(help = "Play skip the queue",aliases = ['ps'])
  async def playskip(self,ctx,*,song:str = None):
    if song == None:
        await ctx.send("Please send the title of a song to play")
        return
    await ctx.invoke(self.client.get_command('join'))
    self.client.song = str(song)
    self.qu = {}
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
    FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
    YDL_OPTIONS = {'format':"bestaudio"}
    vc = ctx.voice_client
    try:
      with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
        info = ydl.extract_info(url, download=False)
        url2 = info['formats'][0]['url']
        source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            
    except:
      await ctx.send("There was an error getting that song\nIt could be age restricted or private. Try a different song")
      return
    vc.stop()
    vc.play(source)
    self.qu[0] = source
    await ctx.send("Now playing: " + str(info.get('title', None)) + '\n' + url)

    
  @commands.command(help = 'Play a song')
  async def play(self,ctx,*,song:str = None):

        if song == None:
          await ctx.send("Please send the title of a song to play")
          return
        #get the bot to join the player if it isnt already in it
        await ctx.invoke(self.client.get_command('join'))
        self.client.song = str(song)
          
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
        FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
        YDL_OPTIONS = {'format':"bestaudio"}
        vc = ctx.voice_client
        try:
          with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
            info = ydl.extract_info(url, download=False)
            url2 = info['formats'][0]['url']
            source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            
        except:
          await ctx.send("There was an error getting that song\nIt could be age restricted or private. Try a different song")
          return

        
        #checking if add to the queue or play the song instantly

        print(self.qu)
        if len(self.qu) == 0:
          self.start_playing(vc, source)
          await ctx.send("Now playing: " + str(info.get('title', None)) + '\n' + url)
        else:
          self.qu[len(self.qu)] = source
          await ctx.send(str(info.get('title',None)) + " was added to the queue")
        


  #pause the player
  @commands.command(help = 'Pause the current song',aliases = ['pa'])
  async def pause(self,ctx):
        await ctx.send("Paused ⏸")
        await ctx.voice_client.pause()
        
  #resume the player
  @commands.command(help = 'Resume the current song', aliases = ['res'])
  async def resume(self,ctx):
        await ctx.send("Resumed ▶️")
        await ctx.voice_client.resume()


    #get lyrics for the current song or any song
  @commands.command(help="Get lyrics for a song, send without a song arguement when playing a song in the voice channel to get the current songs lyrics", aliases=["ly"])
  async def lyrics(self, ctx, *, song = None):
        if song == None and ctx.voice_client.is_connected():
          json = requests.get(f"https://some-random-api.ml/lyrics?title={self.client.song}").json()
        elif song == None:
          await ctx.send("Please send a song to get lyrics for")
        else:
          json = requests.get(f"https://some-random-api.ml/lyrics?title={song}").json()
        with suppress(AttributeError):
            await ctx.trigger_typing()

        

        with suppress(KeyError):
            if json["error"]:
                await ctx.send("❌ " + json["error"])
                return

        lyrics = json['lyrics']
        if len(lyrics) > 2048:
          lyrics = lyrics[:2045] + '...'
        
        embedVar = discord.Embed(title = 'Lyrics for ' + str(json["title"] + ", By " + json["author"]), description = lyrics ,color = ctx.author.color)
        
        embedVar.set_thumbnail(url = json["thumbnail"]["genius"])
        
        embedVar.set_footer(text=  'Requested by ' + str(ctx.author.name),icon_url = ctx.author.avatar)
        await ctx.send(embed = embedVar)


  def start_playing(self,vc,source):
      print("got into player")
      self.qu[0] = source
    
      i = 0
      while i <  len(self.qu):
        try:
          vc.play(self.qu[i], after=lambda e: print('Player error: %s' % e) if e else None)

        except:
          pass
          i += 1
      print("Exited the loop with queue of:")
      print(self.qu)


async def setup(client):
   await client.add_cog(Music(client))