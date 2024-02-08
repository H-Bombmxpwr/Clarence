import discord
from discord.ext import commands
import youtube_dl
import requests
from contextlib import suppress
from youtube_search import YoutubeSearch
import json
from better_profanity import profanity
from discord.ui import Button,View
from dotenv import load_dotenv
from pytube import YouTube
from moviepy.editor import *
from discord import FFmpegPCMAudio

load_dotenv(dotenv_path = 'keys.env')
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

    
  @commands.command(help='Join a voice channel')
  async def join(self, ctx):
    if ctx.author.voice is None:
        await ctx.send("You're not in a voice channel! Join one first.")
        return

    voice_channel = ctx.author.voice.channel

    if ctx.voice_client is None:
        try:
            await voice_channel.connect()
            await ctx.send(f"Joined: {voice_channel}")
        except Exception as e:
            await ctx.send("An error occurred while trying to connect to the voice channel.")
            print(e)  # Log the error
    else:
        try:
            await ctx.voice_client.move_to(voice_channel)
        except Exception as e:
            await ctx.send("An error occurred while trying to move to the voice channel.")
            print(e)  # Log the error

  
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
        


  # @commands.command(help = "Play skip the queue",aliases = ['ps'])
  # async def playskip(self,ctx,*,song:str = None):
  #   if song == None:
  #       await ctx.send("Please send the title of a song to play")
  #       return
  #   await ctx.invoke(self.client.get_command('join'))
  #   self.client.song = str(song)
  #   self.qu = {}
  #   self.titles = {}
  #   #search the song/ check if a url was sent
  #   if str(song).find("https://www.youtube.com") == -1:
  #         yt = YoutubeSearch(str(song), max_results=1).to_json()
  #         song_id = str(json.loads(yt)['videos'][0]['id'])
  #         url = "https://www.youtube.com/watch?v=" + song_id
  #         if url == None:
  #           await ctx.send("Song not found")
  #           return
  #   else:
  #         url = str(song)

  #   with suppress(AttributeError):
  #     await ctx.trigger_typing()  

  #   #plays the url generated above
  #   FFMPEG_OPTIONS = {'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5', 'options': '-vn'}
  #   YDL_OPTIONS = {'format':"bestaudio"}
  #   vc = ctx.voice_client
  #   try:
  #     with youtube_dl.YoutubeDL(YDL_OPTIONS) as ydl:
  #       info = ydl.extract_info(url, download=False)
  #       url2 = info['formats'][0]['url']
  #       source = await discord.FFmpegOpusAudio.from_probe(url2, **FFMPEG_OPTIONS)
            
  #   except:
  #     await ctx.send("There was an error getting that song\nIt could be age restricted or private. Try a different song")
  #     return
  #   vc.stop()
  #   vc.play(source)
  #   guild_id = ctx.message.guild.id
  #   self.qu[guild_id] = [source]
  #   self.titles[guild_id] = [info.get('title',None)]
  #   await ctx.send("Now playing: " + str(info.get('title', None)) + '\n' + url)

    
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
        
        #url is now obtained, next is to save off the mp3 file
        try:
          youtube = YouTube(url)

          custom_directory_path = r'storage/audio'
          custom_filename = f'{song_id}.mp3'

          # Download the audio stream at the highest quality
          audio_stream = youtube.streams.get_audio_only()
          audio_stream.download(output_path=custom_directory_path, filename=custom_filename.replace(".mp3", ".mp4"))

          # Convert MP4 to MP3
          mp4_path = f'{custom_directory_path}/{custom_filename.replace(".mp3", ".mp4")}'
          mp3_path = f'{custom_directory_path}/{custom_filename}'

          audioclip = AudioFileClip(mp4_path)
          audioclip.write_audiofile(mp3_path)

          # Optional: Remove the original MP4 file
          audioclip.close()
          os.remove(mp4_path)
            
        except Exception as e:
          await ctx.send("There was an error getting that song. Try a different song")
          print(f"Error: {e}")
          return
        
        #now is saved as song_id.mp3
        await ctx.send(f"{url} was found, and is now playing")
        #nopw time to play the song
        guild_id = ctx.message.guild.id
        #mp3_path = os.path.join(custom_directory_path, custom_filename)
        mp3_path = os.path.join(custom_directory_path, custom_filename)
        print("source about to be made")
        print(f"MP3 Path: {mp3_path}")
        if not os.path.exists(mp3_path):
            print("File does not exist at the given path.")
        else:
            print("File exists, attempting to play.")
        try:
            source = FFmpegPCMAudio(mp3_path)
            print("FFmpeg line executed successfully.")
        except Exception as e:
            print(f"FFmpeg error: {e}")
        print("FFFMPEG WORKED")
        vc = ctx.voice_client

        if vc and vc.is_connected():
            def after_playing(error):
                if error:
                    print(f"Error after playing: {error}")
                if guild_id in self.qu and self.qu[guild_id]:
                    print("got to queue")
                    next_source = self.qu[guild_id].pop(0)
                    vc.play(next_source, after=after_playing)
                    next_title = self.titles[guild_id].pop(0)
                    future = ctx.send(f"Now playing: {next_title}")
                    self.client.loop.create_task(future)

            if not vc.is_playing():
                print("attempted to play")
                vc.play(source, after=after_playing)
                self.titles.setdefault(guild_id, []).append(song)  # Use song or a specific title
                await ctx.send(f"Now playing: {song}")
            else:
                self.qu.setdefault(guild_id, []).append(source)
                self.titles.setdefault(guild_id, []).append(song)
                await ctx.send(f"{song} added to the queue.")
        else:
            await ctx.send("Bot is not connected to a voice channel.")
        


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
    async with ctx.typing():
      if song == None and ctx.voice_client.is_connected():
          json = requests.get(f"https://some-random-api.com/others/lyrics?title={self.client.song}").json()
      elif song == None:
          await ctx.send("Please send a song to get lyrics for")
      else:
          json = requests.get(f"https://some-random-api.com/others/lyrics?title={song}").json()

      with suppress(KeyError):
            if json["error"]:
                await ctx.send("❌ " + json["error"])
                return
      

      #pf = ProfanityFilter()
      #pf.censor_char = '#'
      lyrics = json['lyrics']
      if len(lyrics) > 2048:
        lyrics = lyrics[:2045] + '...'

      
      def make_lyrics_embed(lyrics):
        embedVar = discord.Embed(title = 'Lyrics for ' + str(json["title"] + ", By " + json["author"]), description = lyrics ,color = ctx.author.color)
      
        embedVar.set_thumbnail(url = json["thumbnail"]["genius"])
      
        embedVar.set_footer(text=  'Requested by ' + str(ctx.author.name),icon_url = ctx.author.avatar)
        return embedVar

      view = View()
      button_uncensor = Button(label = "Uncensor", style = discord.ButtonStyle.red, custom_id = "uncensor")
      
      view.add_item(button_uncensor)
      

      msg = await ctx.send(embed = make_lyrics_embed(profanity.censor(lyrics, '#')),view=view)

    res = await self.client.wait_for('interaction', check=lambda interaction: interaction.data["component_type"] == 2 and "custom_id" in interaction.data.keys())

    for item in view.children:
      if item.custom_id == res.data["custom_id"]:
        button_uncensor.disabled = True
        await msg.edit(embed = make_lyrics_embed(lyrics), view=view)
        await res.response.defer()
            
  def queuel(self,ctx, id):
    if len(self.qu) > 0 and self.qu[id] != []:
        voice = ctx.guild.voice_client
        audio = self.qu[id].pop(0)
        self.titles[id].pop(0)
        voice.play(audio, after=lambda x=None: self.queuel(ctx, ctx.message.guild.id))


async def setup(client):
   await client.add_cog(Music(client))