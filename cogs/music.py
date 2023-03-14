import discord
from discord.ext import commands
import youtube_dl
import requests
from contextlib import suppress
from youtube_search import YoutubeSearch
import json
from profanity_filter import ProfanityFilter
from discord.ui import Button,View

class Music(commands.Cog):
  """ 
  Module for playing music in a voice channel
  """
  def __init__(self, client):
        self.client = client
        self.qu = {}
        self.titles = {}

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
    vc = ctx.voice_client
    guild_id = ctx.message.guild.id
    if vc.is_playing() and len(self.qu[guild_id]) > 1:
      self.qu[guild_id] = [self.qu[guild_id].pop(0)]
      self.titles[guild_id] = [self.titles[guild_id].pop(0)]
      await ctx.send("The queue has been cleared")
    else:
      await ctx.send("There is nothing queued, play some songs first")
  
  @commands.command(help = 'Leave a voice channel', aliases = ['dis','leave'])
  async def disconnect(self,ctx):
        await ctx.voice_client.disconnect()
        self.qu = {}
        self.titles = {}
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
    self.titles = {}
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
    guild_id = ctx.message.guild.id
    self.qu[guild_id] = [source]
    self.titles[guild_id] = [info.get('title',None)]
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

        guild_id = ctx.message.guild.id
        title = str(info.get('title',None))
        if not vc.is_playing():
          async with ctx.typing():
            vc.play(source, after=lambda x=None: self.queuel(ctx, guild_id))
            vc.is_playing()
            self.titles[guild_id] = [title]
            await ctx.send("Now playing: " + title + '\n' + url)
        else:
          if guild_id in self.qu:
            self.qu[guild_id].append(source)
          else:
            self.qu[guild_id] = [source]
            
          self.titles[guild_id].append(title)
          await ctx.send(str(info.get('title',None)) + " was added to the queue")
        


  #pause the player
  @commands.command(help = 'Pause the current song',aliases = ['pa'])
  async def pause(self,ctx):
        if (ctx.author.voice is not None):
          await ctx.send("Paused ⏸")
          await ctx.voice_client.pause()
        else:
          await ctx.send("You are not in a voice channel, nice try")
        
  #resume the player
  @commands.command(help = 'Resume the current song', aliases = ['res'])
  async def resume(self,ctx):
        if (ctx.author.voice is not None):
          await ctx.send("Resumed ▶️")
          await ctx.voice_client.resume()
        else:
          await ctx.send("You are not in a voice channel, nice try")

  #displays the current queue, pretty rouhg code and will need some work in the future
  @commands.command(help = "Display the current queue",aliases = ['qu'])
  async def queue(self,ctx):
    guild_id = ctx.message.guild.id
    if len(self.qu) == 0:
      await ctx.send("There is no queue, play a some songs first!")
    else:
      list_titles = self.titles[guild_id]
      songs = ""
      for i in range(len(list_titles)):
        songs = songs + "`" + str(i+1) + ".`" +  list_titles[i]
        if i == 0:
          songs = songs + "`(now playing)` \n\n"
        else:
          songs = songs + '\n\n'
      embedVar = discord.Embed(title = "Current Queue: ",description = songs,color = 0x800000)
      await ctx.send(embed = embedVar)

  #get lyrics for the current song or any song
  @commands.command(help="Get lyrics for a song, send without a song arguement when playing a song in the voice channel to get the current songs lyrics", aliases=["ly"])
  async def lyrics(self, ctx, *, song = None):
        if song == None and ctx.voice_client.is_connected():
          json = requests.get(f"https://some-random-api.ml/lyrics?title={self.client.song}").json()
        elif song == None:
          await ctx.send("Please send a song to get lyrics for")
        else:
          json = requests.get(f"https://some-random-api.ml/lyrics?title={song}").json()

        with suppress(KeyError):
            if json["error"]:
                await ctx.send("❌ " + json["error"])
                return
        with suppress(AttributeError):
            await ctx.trigger_typing()

        pf = ProfanityFilter()
        pf.censor_char = '#'
        lyrics = json['lyrics']
        if len(lyrics) > 2048:
          lyrics = lyrics[:2045] + '...'

        
        def make_lyrics_embed(lyrics):
          embedVar = discord.Embed(title = 'Lyrics for ' + str(json["title"] + ", By " + json["author"]), description = lyrics ,color = ctx.author.color)
        
          embedVar.set_thumbnail(url = json["thumbnail"]["genius"])
        
          embedVar.set_footer(text=  'Requested by ' + str(ctx.author.name),icon_url = ctx.author.avatar)
          return embedVar

        view = View()
        button_censor = Button(label = "Censored", style = discord.ButtonStyle.green,custom_id = "censor")
        
        button_uncensor = Button(label = "Uncensored", style = discord.ButtonStyle.red, custom_id = "uncensor")
        
        view.add_item(button_censor)
        view.add_item(button_uncensor)
        
        

        msg = await ctx.send(embed = make_lyrics_embed(pf.censor(lyrics)),view=view)
        print("pensi")

        def check_button(i: discord.Interaction, button):
          return i.author == ctx.author and i.message == msg
        print("lel")
        interaction, button = await self.client.wait_for('button_click', check=check_button)
        print("here")
        if button.custom_id == "censor":
          await msg.edit(embed = make_lyrics_embed(pf.censor(lyrics), view=view))
        
        if button.custom_id == "uncensor":
          await msg.edit(embed = make_lyrics_embed(lyrics), view=view)


                   
  def queuel(self,ctx, id):
    if len(self.qu) > 0 and self.qu[id] != []:
        voice = ctx.guild.voice_client
        audio = self.qu[id].pop(0)
        self.titles[id].pop(0)
        voice.play(audio, after=lambda x=None: self.queuel(ctx, ctx.message.guild.id))


async def setup(client):
   await client.add_cog(Music(client))