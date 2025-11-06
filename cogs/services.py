import discord
from discord import Member
from discord.ext import commands
import os
import functionality.functions
import requests
import wolframalpha
import xkcd
from typing import Optional
from datetime import date
import asyncio
import storage.embed_storage
from urllib.parse import quote
from pyfiglet import Figlet
import random
import wikipedia
from discord.ui import Button,View
from contextlib import suppress
from dotenv import load_dotenv

import traceback
import logging

load_dotenv(dotenv_path = 'keys.env')


class Misc(commands.Cog, description = 'Local commands within the bot'):
  """ 
  Group of commands executed locally
  """
  def __init__(self,client):
      self.client = client
  
    #hello command
  @commands.command(help = "Hello!", aliases = ["hi","hey","whatsup","heyy","sup"])
  async def hello(self,ctx):
    user = "<@" + str(ctx.author.id) + ">"
    responses = ["Hi!", "Hello!","What's up!","What does it do?","Hey!","Sup!","Big Chillin!","Hey Hey Hey","Lets Go!"]
    await ctx.send(f"{random.choice(responses)} {user}")


  #creates ASCII Art
  @commands.command(help="Return text in ASCII art", aliases=["figlet"])
  @commands.cooldown(1, 3, commands.BucketType.user)
  async def ascii(self, ctx, *, text):
        if len(text) >= 16:
            return await ctx.send(
                "❌ Your text is too long, please use text that is lesser than 16 characters."
            )

        ascii_text = Figlet(font="small").renderText(text)

        await ctx.send(f"```\n{ascii_text}\n```")

  #ping a user a bunch of times
  @commands.command(help = 'Ping a user x number of times', aliases  = ["annoy"])
  async def bug(self, ctx, member : discord.Member,iterate,*,message = "we need you"):
    try:
      id = int(member.id)
      if int(iterate) > 30:
        await ctx.send("Woah thats a little `TOO` cruel...")
      elif id == 877014219499925515:
        await ctx.send("You better not try to bug me")
    
      elif id == 239605426033786881:
        await ctx.send("I could never bug my creator like that")
      else:
        for x in range(1,int(iterate) + 1):
          await ctx.send('Hey <@' + str(id) + '> ' + str(message) + ", " + str(x) + '!\n')
    except:
      await ctx.send("Error: Invalid syntax")


  #get general info about anyone in a given server
  @commands.command(help = 'Get info of any user in the server')
  async def userinfo(self, ctx, target: Optional[Member]):
    target = target or ctx.author

    embed = discord.Embed(title="User information",color=target.color)
    embed.set_image(url=target.avatar)
    fields = [("Name", str(target), True),
    ("ID", target.id, True),
		("Bot?", target.bot, True),
		("Top role", target.top_role.mention, True),
		("Status", str(target.status).title(), True),
		("Activity", f"{str(target.activity.type).split('.')[-1].title() if target.activity else 'N/A'} {target.activity.name if target.activity else ''}", True),
		("Created on", target.created_at.strftime("%d/%m/%Y %H:%M:%S"), True),
		("Joined on", target.joined_at.strftime("%d/%m/%Y %H:%M:%S"), True),
		("Booster?", bool(target.premium_since), True)]

    for name, value, inline in fields:
      embed.add_field(name=name, value=value, inline=inline)

    await ctx.send(embed=embed)


  #simple dice rolling command
  @commands.command(help = "rolls a die, optional arguement for number of sides")
  async def dice(self,ctx,sides = 6):
    await ctx.send(f"You rolled a `{random.randrange(1, sides)}`")
  
  # END LOCAL CLASS
  
    
  # START API CLASS


class Api(commands.Cog, description = 'Commands that call an outside api to return information'):
  """ 
  Group of commands executed through external api's
  """
  def __init__(self,client):
      self.client = client
  

  #ai generation
  @commands.command(help = "ai image generation")
  async def ai(self,ctx,*,query = None):
    if query == None:
      await ctx.send("Please send a query to generate")
      return

    try:
      async with ctx.typing():
        r = requests.post(
        "https://api.deepai.org/api/text2img",
        data={
          'text': query,
        },
        headers={'api-key': os.getenv('ai')}
        )
        embedVar = discord.Embed(title = "AI Generation", description = f"prompt: {query}",color = 0xFFFF00)
        embedVar.set_image(url = r.json()['output_url'])
        embedVar.set_footer(text = f"Requested by {ctx.author.name}", icon_url = ctx.author.avatar)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title = "AI Generation",description = "There was an error in generating the given request, please try again.",color = 0xFFFF00)
      embedVar.set_footer(text = f"Requested by {ctx.author.name}", icon_url = ctx.author.avatar)
      await ctx.send(embed=embedVar)

  #search wikepedia
  @commands.command(help = 'get a link to a wikipedia article',aliases=["wiki", "w"])
  async def wikipedia(self, ctx, *, query = None):

    if query == None:
      await ctx.send("Please attach something to search for to this function")
    else:
      thequery = str(query)
      with suppress(AttributeError):
            await ctx.trigger_typing()
      try: 
        if wikipedia.suggest(thequery) != None:
          thequery = wikipedia.suggest(thequery)
        
        link = wikipedia.page(thequery) #get the page object
        button = Button(label = link.original_title, style = discord.ButtonStyle.primary, url = link.url) #create link button
        view = View()
        wiki = "https://upload.wikimedia.org/wikipedia/commons/6/61/Wikipedia-logo-transparent.png"
        
        embed = discord.Embed(title = link.title, description = wikipedia.summary(thequery, sentences=3), color = 0xC0C0C0).set_image(url = link.images[0]).set_thumbnail(url = wiki)

        view.add_item(button)
        await ctx.send(embed=embed,view=view)
      except:
        embed = discord.Embed(title = "Wikipedia Error", description = "Something failed with your query, try rewording and sending again", color = 0xC0C0C0).set_thumbnail(url = wiki)
        await ctx.send(embed=embed)



  # lichess queries
  @commands.command(help = 'Interact with lichess.org')
  async def lichess(self,ctx,parameter = None):
      response = requests.get("https://lichess.org/api/puzzle/daily")
      json_request = response.json()
      #starts the embed
      embedVar = discord.Embed(title="Lichess Daily Puzzle", description = "Gives the lichess daily puzzle", color=0xffffff).set_thumbnail(url = "https://images.prismic.io/lichess/5cfd2630-2a8f-4fa9-8f78-04c2d9f0e5fe_lichess-box-1024.png?auto=compress,format")
      embedVar.add_field(name = "pgn: ", value = json_request["game"]["pgn"],inline = False)
      embedVar.add_field(name = "Rating: ", value = json_request["puzzle"]["rating"],inline = False)
      embedVar.add_field(name = "Themes: ", value = json_request["puzzle"]["themes"],inline = False)
      embedVar.add_field(name = "Solution: ", value = json_request["puzzle"]["solution"],inline = False)
      await ctx.send(embed=embedVar)

  
  
  #color function
  @commands.command(help = "Get any color")
  async def color(self,ctx,para = None ,color = None):
    color, image = functionality.functions.get_color(para,color)
    await ctx.send("Color function in the works, check back later")
    
  
  @commands.command(help='Ask a question to a computational intelligence', aliases=['q'])
  async def query(self, ctx, *, parameter: str | None = None):

      if not parameter:
          await ctx.send("Usage: `query <your question>`")
          return

      app_id = os.getenv("APP_ID")
      if not app_id:
          await ctx.send("Wolfram Alpha APP_ID not set.")
          return

      async with ctx.typing():
          client = wolframalpha.Client(app_id)
          res = client.query(parameter)

          # Normalize pods -> list
          pods = res.get('pod', [])
          if isinstance(pods, dict):
              pods = [pods]

          # If nothing useful came back
          if not pods:
              await ctx.send("No results.")
              return

          # Stable-sort: primary pod first (if any), otherwise keep API order
          def _is_primary(p): 
              return 0 if str(p.get('@primary', 'false')).lower() == 'true' else 1
          pods = sorted(pods, key=_is_primary)

          # Embed helpers (inner-only)
          def _as_list(x):
              if x is None: return []
              return x if isinstance(x, list) else [x]

          def _chunk_text(txt, limit=1000):
              # Discord field value max ~1024; keep some headroom
              txt = txt.strip()
              if not txt:
                  return []
              if len(txt) <= limit:
                  return [txt]
              chunks = []
              for para in txt.split("\n\n"):
                  if len(para) <= limit:
                      chunks.append(para)
                  else:
                      # Hard-wrap very long paragraphs
                      chunks.extend(textwrap.wrap(para, width=limit, replace_whitespace=False))
              # Merge tiny trailing pieces
              merged = []
              buf = ""
              for c in chunks:
                  if len(buf) + 1 + len(c) <= limit:
                      buf = f"{buf}\n{c}".strip()
                  else:
                      if buf: merged.append(buf)
                      buf = c
              if buf: merged.append(buf)
              return merged

          def _build_embed(title, subtitle=None, color=0x2D9BF0):
              desc = subtitle or ""
              return discord.Embed(title=title, description=desc, color=color)

          # Build & send embeds (cap to avoid spam)
          sent = 0
          MAX_EMBEDS = 10

          for pod in pods:
              if sent >= MAX_EMBEDS:
                  await ctx.send("…additional results omitted.")
                  break

              title = pod.get('@title', 'Result')
              subpods = _as_list(pod.get('subpod'))

              # If there are many subpods, we’ll spread them across multiple embeds if needed
              embed = _build_embed(title=title)

              image_set = False
              fields_used = 0

              for idx, sp in enumerate(subpods, start=1):
                  # Pull text and image
                  txt = (sp.get('plaintext') or "").strip()
                  img = sp.get('img') or {}
                  img_url = img.get('@src')

                  # Add text in chunks to avoid field size limits
                  if txt:
                      chunks = _chunk_text(txt)
                      for j, ch in enumerate(chunks, start=1):
                          name = f"Answer" if fields_used == 0 else f"More ({fields_used+1})"
                          # Keep field name short; Discord field name limit is 256 chars
                          if len(name) > 240:
                              name = name[:240] + "…"
                          embed.add_field(name=name, value=ch, inline=False)
                          fields_used += 1

                          # If we’re out of field slots, flush and start a fresh embed
                          if fields_used >= 20:  # keep a little safety margin (Discord max is 25)
                              await ctx.send(embed=embed)
                              sent += 1
                              if sent >= MAX_EMBEDS:
                                  break
                              embed = _build_embed(title=title + " (cont.)")
                              image_set = False
                              fields_used = 0
                      if sent >= MAX_EMBEDS:
                          break

                  # Prefer setting one main image; link extras
                  if img_url:
                      if not image_set:
                          embed.set_image(url=img_url)
                          image_set = True
                      else:
                          # Add a link for additional images
                          embed.add_field(name="Image", value=f"[Open image]({img_url})", inline=False)
                          fields_used += 1
                          if fields_used >= 20:
                              await ctx.send(embed=embed)
                              sent += 1
                              if sent >= MAX_EMBEDS:
                                  break
                              embed = _build_embed(title=title + " (cont.)")
                              image_set = False
                              fields_used = 0
                  if sent >= MAX_EMBEDS:
                      break

              # If this pod had no plaintext or images, skip empty embed
              if len(embed.fields) == 0 and not embed.image.url:
                  continue

              await ctx.send(embed=embed)
              sent += 1

          # Add a compact “Open Full Results” link if available
          try:
              if 'datatypes' in res or 'numpods' in res:
                  # Res doesn't provide a canonical "share" URL for arbitrary queries, but echo the query
                  await ctx.send(f"Full computation may include interactive pods not shown here. Query: `{parameter}`")
          except Exception:
              pass




  # get insult
  @commands.command(help = 'Get an insult with an insult api', aliases = ['i'])
  async def insult(self,ctx,member : discord.Member = None):
    with suppress(AttributeError):
            await ctx.trigger_typing()
    try:
      quote = functionality.functions.get_insult()
      if member == None:
        embedVar = discord.Embed(title="Random Insult", description = quote, color=0xff0000)
      else:
        id = int(member.id)
        mention = '<@' + str(id) + '>'
        embedVar = discord.Embed(title="Random Insult", description = f"{mention}, {quote}", color=0xff0000)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The insult API is currently down, try again later", color=0xff0000)
      await ctx.send(embed=embedVar)
  
  
  #get compliment
  @commands.command(help = 'Get a compliment using a compliment api', aliases = ['c'])
  async def compliment(self,ctx,member : discord.Member = None):
    with suppress(AttributeError):
            await ctx.trigger_typing()
    try:
      quote = functionality.functions.get_compliment()
      if member == None:
        embedVar = discord.Embed(title="Random Compliment", description = quote, color=0x89CFF0)
      else:
        id = int(member.id)
        mention = '<@' + str(id) + '>'
        embedVar = discord.Embed(title="Random Compliment", description = f"{mention}, {quote}", color=0x89CFF0)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The compliment API is currently down, try again later", color=0x89CFF0)
      await ctx.send(embed=embedVar)

  #get pickup line
  @commands.command(help = "Get a random pickup line", aliases = ['p'])
  async def pickup(self,ctx,member : discord.Member = None):
    with suppress(AttributeError):
            await ctx.trigger_typing()
    try:
      if member == None:
        quote = functionality.functions.get_pickup()
        embedVar = discord.Embed(title="Random Pickup Line", description = quote, color=0xFF69B4)
      else:
        id = int(member.id)
        mention = '<@' + str(id) + '>'
        embedVar = discord.Embed(title="Random Pickup Line", description = f"Hey {mention}, {quote}", color=0xFF69B4)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The pickup line API is currently down, try again later", color=0xFF69B4)
      await ctx.send(embed=embedVar)

  #get joke
  @commands.command(help = 'Get a joke using a joke api', aliases = ['j'])
  async def joke(self,ctx):
    with suppress(AttributeError):
            await ctx.trigger_typing()
    try:
      quote = functionality.functions.get_joke()
      embedVar = discord.Embed(title="Random " + quote["category"]+ " Joke\n", description = quote["setup"] + '\n\n' + quote["delivery"], color=0xffa500)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The joke API is currently down, try again later", color=0xff0000)
      await ctx.send(embed=embedVar)



  @commands.command(help = 'Coin market cap queries')
  async def coin(self,ctx):
    #quote = functions.coin_market_cap()
    #print(quote)
    await ctx.send('Crypto function coming soon\nIn the mean time, have a coin flip: '+ random.choice(["`Heads`", "`Tails`"]))



  #xkcd comic random
  @commands.command(help="Get the latest/random xkcd comic")
  async def xkcd(self, ctx, *, type="latest"):
      if type.lower() == "random":
        comic = xkcd.getRandomComic()
      elif type.lower() == "latest":
            comic = xkcd.getLatestComic()
      else:
        return await ctx.send(
                "❌ Please use `random` or `latest`! Leaving it blank will give you the latest comic."
            )
      embed = discord.Embed(title=f"Comic {comic.number}: {comic.title}",url=comic.link, colour=0x40e0d0,description=f"[Click here if you need an explanation]({comic.getExplanation()})")

      embed.set_footer(text=comic.getAltText())
      embed.set_image(url=comic.getImageLink())
      await ctx.send(embed=embed)


  
  #get an image of an animal if it is supported  
  @commands.command(help="Get a random animal image", aliases=["an"])
  async def animal(self, ctx,animal = None):
    if animal == None:
      embed = discord.Embed(title = "List of valid animals",color = 0x088f8f).set_image(url = 'https://cdn.discordapp.com/attachments/898257362132008970/906283416666918952/unknown.png')
      await ctx.send(embed=embed)
    
    else:
      try:
          
          if animal.lower() == "red" or animal.lower() == "redpanda":
            animal = "red_panda"
          json = requests.get("https://some-random-api.com/animal/" + animal).json()
          embed = discord.Embed(title="Here's a " + animal,description = "Fun fact: " + str(json["fact"]), colour=0x088f8f)
          embed.set_image(url=json["image"])
          await ctx.send(embed=embed)

      except:
        embed = discord.Embed(title="Error " ,description = "A valid animal was not given, see \'$animal\'", colour = 0x088f8f)
        await ctx.send(embed=embed)

  
  #sends most common gif based on query
  @commands.command(help="Search for GIFs (filtered) on Tenor")
  async def gif(self, ctx, *, query):
        with suppress(AttributeError):
            await ctx.trigger_typing()
        json = requests.get(
            f"https://g.tenor.com/v1/search?q={quote(query)}&contentfilter=medium&key={os.environ['TENORKEY']}"
        ).json()

        # Send first result
        try:
            await ctx.send(json["results"][0]["url"])
        except IndexError:
            await ctx.send("❌ Couldn't find any matching GIFs.")



async def setup(client):
    await client.add_cog(Misc(client))
    await client.add_cog(Api(client))