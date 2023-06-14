import discord
from discord.ext import commands
from functionality.functions import fix_lines
from functionality.structures import FizzBuzz,Card
from datetime import date
import requests
from discord import NotFound
from contextlib import suppress
from storage.Lists_Storage import emojis
import random
import json
from PIL import Image
from typing import Union
from dotenv import load_dotenv

load_dotenv(dotenv_path = 'keys.env')


class Fun(commands.Cog):
  """ 
  Games to play with the bot
  """
  def __init__(self,client):
      self.client = client



  @commands.command(help = "do you own an nft with Clarence?")
  async def nft(self,ctx,*, addition = None):
    with open("storage/nft.json", "r") as f:
        nfts = json.load(f)

    user = "<@" + str(ctx.author.id) + ">"
    if addition != None:
      nfts[str(ctx.author.id)] = addition
  
      with open("storage/nft.json","w") as f:
        json.dump(nfts,f, indent = 4)
      await ctx.send(f"Your `NEW` nft, {user}:")
      await ctx.send(f"{nfts[str(ctx.author.id)]}")
    else:
      try:
          instance = nfts[str(ctx.author.id)]
          await ctx.send(f"Your nft, {user}:")
          await ctx.send(f"{instance}")
      except:
        await ctx.send(f"You do not have an nft on file {user}, please send one using `$nft <your_nft>`")
    

  #fizzbuzz game
  @commands.command(help = "play fizzbuzz",aliases = ['fizz','buzz'])
  async def fizzbuzz(self,ctx, iterate = None):
    if iterate == None:
      check = 0
      count = 1
      await ctx.send("```Fizzbuzz activated! 1 player mode. Send one number at a time below\n\nPress 'q' at any point to leave. Use 'fizzbuzz r' for a list of rules```")
      
      while check == 0:
        msg = await self.client.wait_for("message", check=lambda m: m.author == ctx.author, timeout = 60)
    
        
        if msg.content.lower() == 'q':
          check = 1
          functionality.functions.update_fizzbuzz(ctx,count)
          await ctx.send("```FizzBuzz canceled by player```")
          return

        varint = int(count)
        current = FizzBuzz(varint)
        if msg.content.lower() == current.solve(varint).lower():
          await msg.add_reaction('✅')
          count = count + 1
        else:
          await msg.add_reaction('❌')
          await ctx.send('```' + str(msg.content) + ' is incorrect, the correct answer was ' + current.solve(varint) + '```')
          functionality.functions.update_fizzbuzz(ctx,count)
          return

    if iterate.startswith('r'):
      await ctx.send('``` FizzBuzzz is a simple game\n If a number is divisible by 3, send fizz\n If a number is divisible by 5, send buzz\n If is it divisible by both, send fizzbuzz\n Else, send the original number\n\n i.e. 1,2,fizz,4,buzz,fizz....```')

    if iterate.startswith('s'):
      stats = functionality.functions.get_fizzbuzz_stats(ctx)
      if stats[0] == 0:
        ctx.send("You have not played fizzbuzz yet, use $fizzbuzz to play")
      else:
        embedVar = discord.Embed(title = 'Stats for @' + str(ctx.author.name), description = 'Tracked statistics for fizzbuzz',color=0x32CD32).set_footer(icon_url = ctx.author.avatar, text = "As of " + str(date.today()))
        embedVar.add_field(name = "Highest number achieved", value = stats[0],inline = False)
        await ctx.send(embed = embedVar)

    if iterate.startswith('p'):
      await ctx.send('```How many terms do you with to print?```')
      msg = await self.client.wait_for("message", check=lambda m: m.author == ctx.author, timeout = 60)

      await ctx.send("```First " + str(msg.content) + ' terms of FizzBuzz```')
      for i in range(1,int(msg.content) + 1):
        await ctx.send(FizzBuzz(i).solve(i))

   
   
   
   
  @commands.command(help="Gives you something to do if you're bored")
  async def bored(self, ctx):
        r = requests.get("https://www.boredapi.com/api/activity?participants=1&price=0")

        if r.status_code != 200:
            await ctx.send(
                "❌ The Bored API has returned an error. Please try again later."
            )
            return

        json = r.json()
        await ctx.send(json["activity"])

  #ratio a message
  @commands.command(help = "Ratio a worthy foe")
  async def ratio(self,ctx,msg_id = None):
    if msg_id == None:
      await ctx.send("To ratio a message, right click on the message and click `Copy ID`. Pass the id as an argument to this function. You need to be in developer mode to be able to see `Copy ID`")
    else:
      with suppress(AttributeError):
        ratio = await ctx.send("Searching for the message...")
        await ctx.trigger_typing()
    
      for channel in ctx.guild.channels:
        try:
          msg = await ctx.fetch_message(msg_id)
        except NotFound:
          continue

      await ratio.edit("Message found, initiating ratio💪")


      for i in range(1,10):
        await msg.add_reaction(random.choice(emojis))


  #counting game
  @commands.command(help = "count to passed integer")
  async def count(self,ctx,endpoint: int = None):
    if endpoint == None:
      await ctx.send("Please send an integer arguement to count to")
      return
    elif endpoint <=0:
      await ctx.send("You can only count to positive integers")
      return
    else:
      count = 1
      funny = 0
      await ctx.send(f"You are now counting to {endpoint}. HAHAHAHA, better start counting")
      
      while count - 1 != endpoint:
        msg = await self.client.wait_for("message", check=lambda m: m.author == ctx.author, timeout = 60)
    
        
        if msg.content.lower() == 'give up':
          await msg.add_reaction('😆')
          await ctx.send("You gave up, how pathetic")
          return
        
        

        
        if msg.content.lower() == str(count):
          await msg.add_reaction('✅')
          count = count + 1
        else:
          await msg.add_reaction('❌')
          funny = funny + 1
          await ctx.send(str(msg.content) + ' is very wrong, you are on ' + str(count))
          if funny == 5:
            await ctx.send("You are bad at this, yikes")
          if funny == 10:
            await ctx.send("10 mess ups!! Embarrasing")
          if funny == 15:
            await ctx.send("This is just sad...")
          if funny == 20:
            await ctx.send("I can't take this anymore, I am ending this out of pity")
            return
      
      embed = discord.Embed(title = "CONGRATS YOU FINSIHED", description = "Lets play again sometime :)", color = 0xFFD700).set_image(url = 'https://img.freepik.com/free-vector/congrats-greeting-card_53876-82116.jpg?size=338&ext=jpg')
      await ctx.send(embed=embed)

  
  @commands.command(help = "52 card pickup",hidden = True)
  async def fiftytwo(self,ctx,member: discord.Member = None):
    if member == None:
      await ctx.send("Please @ a person to play the game as an arguement to the function")
    
    if member.id == 239605426033786881:
      await ctx.send("Hunter would not like to play that game right now")
    elif member.id == 877014219499925515:
      await ctx.send("I am throwing the cards, not picking them up")
    elif member.id == ctx.author.id:
      await ctx.send("Who would want to play this game with themselves?")
    else:

      colors = ['hearts', 'diamonds', 'spades', 'clubs']
      deck_o = [Card(value, color) for value in range(1, 14) for color in colors]
    
      #random.shuffle(deck)
      deck = []
    
      for i in range(0,52):
        deck.append(str(deck_o[i].value) + " of " + str(deck_o[i].color))
    
      #find and replace number with word

      deck = [d.replace('11', 'Jack') for d in deck]
      deck = [d.replace('12', 'Queen') for d in deck]
      deck = [d.replace('13', 'King') for d in deck]
      deck = [d.replace('1', 'Ace') for d in deck]
      deck = [d.replace('Ace0', '10') for d in deck]

      #shuffle da deck
      random.shuffle(deck)

      id = '<@' + str(member.id) + '>'
      for i in range(0,52):
        await ctx.send(f"{id}, {deck[i]}")

  #send a random quote from 2070 paradigm shift
  @commands.command(help = "2070 Paradigm Shift, send '$paradigm source' to get the source video")
  async def paradigm(self,ctx,number = 1):
        if number > 30:
          await ctx.send(f"{number} is a few too many lines, try again with a smaller number")
          return
        with open("storage/paradigm.txt", "r") as f:
          lines = f.readlines()
          f.close()
        
        pruned_lines = fix_lines(lines)
        quotes = list(pruned_lines)
        for i in range(0,number):
          quote = random.choice(quotes)
          await ctx.send(f"{i+1}: {quote}")

  @commands.command(help = "When you need facepalm", aliases = ["palm"])
  async def facepalm(self, ctx):
    await ctx.send(requests.get("https://some-random-api.com/animu/face-palm").json()["link"])


  @commands.command(help = "tell the last person that sent a message to shut up")
  async def shutup(self, ctx, member: discord.Member = None):
    sender_id = ctx.author.id
    if member == None:
      messages = messages = [message async for message in ctx.guild.get_channel(ctx.channel.id).history(limit=50)]
      for msg in messages:
        if msg.author.id != sender_id and msg.author.id != 877014219499925515:
          await ctx.send("Shutup <@" + str(msg.author.id) + ">")
          break
    else:
      await ctx.send("Shutup <@" + str(member.id) + ">")


  @commands.command(help = "emojify an image", aliases = ["em"])
  async def emojify(self,ctx,url: Union[discord.Member, str], size: int = 14):

    COLORS = {
    (0, 0, 0): "⬛",
    (0, 0, 255): "🟦",
    (255, 0, 0): "🟥",
    (255, 255, 0): "🟨",
    #(190, 100, 80):  "🟫",
    (255, 165, 0): "🟧",
    #(160, 140, 210): "🟪",
    (255, 255, 255): "⬜",
    (0, 255, 0): "🟩",
    }


    def euclidean_distance(c1, c2):
      r1, g1, b1 = c1
      r2, g2, b2 = c2
      d = ((r2 - r1) ** 2 + (g2 - g1) ** 2 + (b2 - b1) ** 2) ** 0.5
  
      return d


    def find_closest_emoji(color):
      c = sorted(list(COLORS), key=lambda k: euclidean_distance(color, k))
      return COLORS[c[0]]


    def emojify_image(img, size=14):
      WIDTH, HEIGHT = (size, size)
      small_img = img.resize((WIDTH, HEIGHT), Image.NEAREST)
  
      emoji = ""
      small_img = small_img.load()
      for y in range(HEIGHT):
          for x in range(WIDTH):
              emoji += find_closest_emoji(small_img[x, y])
          emoji += "\n"
      return emoji
    
    if not isinstance(url, str):
        url = url.display_avatar.url

    def get_emojified_image():
        r = requests.get(url, stream=True)
        image = Image.open(r.raw).convert("RGB")
        res = emojify_image(image, size)

        if size > 14:
            res = f"```{res}```"
        return res

    result = await self.client.loop.run_in_executor(None, get_emojified_image)
    await ctx.send(result)
      
        
async def setup(client):
    await client.add_cog(Fun(client))
