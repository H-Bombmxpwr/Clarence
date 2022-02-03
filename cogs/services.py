import tweepy
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



class Local(commands.Cog, description = 'Local commands within the bot'):
  """ 
  Group of commands executed locally
  """
  def __init__(self,client):
      self.client = client


  #List of Commands
  @commands.command(help = 'List of commands for the bot',aliases = ["l"])
  async def list(self,ctx):
    embeds = storage.embed_storage.make_list()
    #add in the current prefix
    for i in range(len(embeds)):
      embeds[i].set_footer(text = "Page " + str(i+1)+ "/6 - The current prefix is \"" + self.client.command_prefix + '\"',icon_url = os.getenv('icon'))
    
    pages = 6
    cur_page = 1
    msg = await ctx.send(embed = embeds[0])
    # getting the message object for editing and reacting

    await msg.add_reaction("◀️")
    await msg.add_reaction("▶️")

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"]
        # This makes sure nobody except the command sender can interact with the "menu"

    while True:
        try:
            reaction, user = await self.client.wait_for("reaction_add", timeout=60, check=check)
            # waiting for a reaction to be added - times out after x seconds, 60 in this
            # example

            if str(reaction.emoji) == "▶️" and cur_page != pages:
                cur_page += 1
                await msg.edit(embed = embeds[cur_page-1])

                await msg.remove_reaction(reaction, user)

            elif str(reaction.emoji) == "◀️" and cur_page > 1:
                cur_page -= 1
                await msg.edit(embed = embeds[cur_page-1])
                await msg.remove_reaction(reaction, user)

            else:
                await msg.remove_reaction(reaction, user)
                # removes reactions if the user tries to go forward on the last page or
                # backwards on the first page
        except asyncio.TimeoutError:
            await msg.delete()
            await ctx.delete()
            break
            # ending the loop if user doesn't react after x seconds
  
  

  # creates ASCII Art
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
  @commands.command(help = 'Ping a user x number of times')
  async def bug(self, ctx, member : discord.Member,iterate):
    try:
      id = int(member.id)
      if int(iterate) > 30:
        await ctx.send("Woah thats a little `TOO` cruel...")
      elif id == 877014219499925515:
        await ctx.send("You better not try to bug me")
    
      elif id == 239605426033786881:
        await ctx.send("I could never ping my creator like that")
      else:
        for x in range(1,int(iterate) + 1):
          await ctx.send('Hey <@' + str(id) + '> ' + str(x) + '!\n')
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
  @commands.command(help = "rolls a die")
  async def dice(self,ctx):
    await ctx.send(f"You rolled a `{random.randrange(1, 6)}`")
  
  # END LOCAL CLASS/COG 
  # START API CLASS


class Api(commands.Cog, description = 'Commands that call an outside api to return information'):
  """ 
  Group of commands executed through external api's
  """
  def __init__(self,client):
      self.client = client


  #interactive trivia
  @commands.command(help = "Interactive trivia",aliases = ["tr"])
  async def trivia(self,ctx,parameter = None):
    info = functionality.functions.get_question2()
    answers = info.getAnswerList()

    if parameter == None:
      embedVar = discord.Embed(title= "Trivia Commands", description = "`trivia multiple: ` will generate a random multiple choice question that can be answered within 60 seconds by the user\n`trivia stats: ` will give the senders trivia stats\n`trivia: ` will give a list of trivia commands", color=0x8b0000).set_thumbnail(url = 'https://lakevieweast.com/wp-content/uploads/trivia-stock-scaled.jpg')
      await ctx.send(embed=embedVar)

    if parameter.lower().startswith('s'):
      stats = functionality.functions.get_trivia_stats(ctx)
      if stats[0] == 0:
        embedVar = discord.Embed(title= "Error", description = "You have not answered a trivia question and are not in the database, use `trivia multiple: ` to answer a question", color=0x8b0000)
        await ctx.send(embed=embedVar)
      else:
        embedVar = discord.Embed(title = 'Stats for ' + str(ctx.author.name), description = 'Tracked statistics for the interactive trivia',color=0x8b0000).set_footer(icon_url = ctx.author.avatar, text = "As of " + str(date.today()))
        embedVar.add_field(name = "Number of correct", value = stats[1],inline = False)
        embedVar.add_field(name = "Total attempts", value = stats[2], inline = False)
        embedVar.add_field(name = 'Percent correct',value = str(round((stats[1]/stats[2])*100,2)) + '%', inline = False)
        await ctx.send(embed = embedVar)
    
    if parameter.lower().startswith('m'):
      embedVar = discord.Embed(title = "Random Triva Question" , description = " Category: " + info.category, color = 0x8b0000 ).set_footer(text= str(ctx.author.name) + ', Send the correct answer below' ,icon_url = 'https://lakevieweast.com/wp-content/uploads/trivia-stock-scaled.jpg')
      embedVar.add_field(name = info.question, value = "\na. " + answers[0] + "\nb. " + answers[1] + "\nc. " + answers[2] + "\nd. " + answers[3] + "\n", inline = False)
      await ctx.send(embed = embedVar)

      local = answers.index(info.correctAnswer)
      if local == 0:
        ans = 'a'
      elif local == 1:
        ans = 'b'
      elif local == 2:
        ans  = 'c'
      elif local == 3:
        ans  = 'd'
      try:
        msg = await self.client.wait_for("message", check=lambda m: m.author == ctx.author, timeout = 60)
      
      
        if msg.content.lower() == ans or msg.content.lower() == info.correctAnswer.lower():
          await msg.add_reaction('✅')
          await ctx.send("Correct! It was " + answers[local])
          temp = 1
        else:
          await msg.add_reaction('❌')
          await ctx.send("Incorrect! The correct answer was " + answers[local])
          temp = 0

        functionality.functions.update_score(ctx,temp)
      except:
          await ctx.send("Timeout Error: User took to long to respond. Bot is back to normal operations")



  #twitter commands
  @commands.command(help = 'Interact with twitter', aliases = ["tw"])
  async def twitter(self,ctx, parameter = None, second = None):

    # Authenticate to Twitter
    auth = tweepy.OAuthHandler(os.getenv('twitter_api_key'),os.getenv('twitter_secret_api_key'))
    
    auth.set_access_token(os.getenv('twitter_access_token'), 
    os.getenv('twitter_secret_access_token'))

    # Create API object
    api = tweepy.API(auth, wait_on_rate_limit=True)

    try:
      api.verify_credentials()
      print("Authentication OK")

    except:
      print("Error during authentication")
    


    if parameter == None:
      embedVar = discord.Embed(title= "Twitter Commands", description = "`twitter user <username>: ` to view a specific users details\n`twitter trends us: ` to view whats currently trending in the US\n`twitter: ` to give a list of twitter commands\n ", color=0x1da1f2).set_thumbnail(url = 'https://296y67419hmo2gej4j232hyf-wpengine.netdna-ssl.com/wp-content/uploads/2008/12/twitter-bird-light-bgs-300x300.png')
      await ctx.send(embed=embedVar)
    
    
    if parameter.lower().startswith("u"):
  
      try:

        user = api.get_user(screen_name = second)
        user_url = user.profile_image_url
        #starts the embed
        embedVar = discord.Embed(title= user.name, description = user.description, color=0x1da1f2).set_thumbnail(url = user_url)
        embedVar.add_field(name = "Follower Count:", value = user.followers_count,inline = False)
        embedVar.add_field(name = "Account Link:", value = 'https://twitter.com/' + user.screen_name)
        await ctx.send(embed=embedVar)
      except:
        embedVar = discord.Embed(title= "Error", description = "User not found or has a private account", color=0x1da1f2).set_thumbnail(url = 'https://296y67419hmo2gej4j232hyf-wpengine.netdna-ssl.com/wp-content/uploads/2008/12/twitter-bird-light-bgs-300x300.png')
        await ctx.send(embed=embedVar)

    
    if parameter.lower().startswith("t"):
      trends_result = api.get_place_trends(2379574)
      embedVar = discord.Embed(title='Trends in the US', description = 'Top 25 trends on Twitter in the US', color=0x1da1f2).set_thumbnail(url = 'https://static01.nyt.com/images/2014/08/10/magazine/10wmt/10wmt-superJumbo-v4.jpg')

      for trend in trends_result[0]["trends"]:
        embedVar.add_field(name = trend["name"], value = "\u200b", inline = False)
    
      await ctx.send(embed=embedVar)

    if parameter.lower().startswith("m"):
      if ctx.author.id == 239605426033786881:
        timeline = api.home_timeline()
        for tweet in timeline:
          await ctx.send(f"{tweet.user.name} said {tweet.text}\n \n \n \n \n \n")
      else:
        await ctx.send("Sorry you don't have permission to look at Hunter's timeline")
  
  


  #search wikepedia
  @commands.command(help = 'get a link to a wikipedia article',aliases=["wiki", "w"])
  async def wikipedia(self, ctx, *query):
        thequery = " ".join(query)
        link = wikipedia.page(thequery)
        await ctx.send(link.url)



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

  
  

  
  # wolfram query
  @commands.command(help = 'Ask a question to a computational intelligence',aliases = ['q'])
  async def query(self,ctx,*,parameter):
      wolf_url = 'https://cdn.freebiesupply.com/logos/large/2x/wolfram-language-logo-png-transparent.png'
      try:
        app_id = os.getenv('app_id')
        client1 = wolframalpha.Client(app_id)
        res = client1.query(parameter)
        answer = next(res.results)['subpod']['img']['@src']
        answertxt = next(res.results).text
      
        #embedVar = discord.Embed(title = "Computational Intelligence", desciption ="Input of computational intelligence", color = 0xdc143c ).set_image(url = input).set_thumbnail(url = wolf_url)
        #embedVar.add_field(name = "Input: ", value = parameter,inline = False)
      

        embedVar = discord.Embed(title = "Computational Intelligence", description ="Input/Output", color = 0xdc143c ).set_image(url = answer).set_thumbnail(url = wolf_url)
        embedVar.add_field(name = "Input: ", value = parameter,inline = False)
        #embedVar.add_field(name = "Output: ", value = answertxt,inline = False)
        msg = await ctx.send(embed = embedVar)

        emoji = '♠'
        await msg.add_reaction(emoji)



      except:
        embedVar = discord.Embed(title = "Computational Intelligence", desciption ="Input/ Output of computational intelligence", color = 0xdc143c).set_thumbnail(url = wolf_url)
        embedVar.add_field(name = "Error", value = "An error occurred and the bot was unable to process your request \n \n This could be due to many different things. Try rewording the question and sending it again. \n \n It is also possible the bot cannot perform the given request. \n ",inline = False)
        #embedVar.add_field(name = "Error", value = "I am currently doing work to the Wolfram query function, check back later ",inline = False)
        await ctx.send(embed = embedVar)



  # get insult
  @commands.command(help = 'Get an insult with an insult api', aliases = ['i'])
  async def insult(self,ctx):
    try:
      quote = functionality.functions.get_insult()
      embedVar = discord.Embed(title="Random Insult", description = quote, color=0xff0000)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The insult API is currently down, try again later", color=0xff0000)
      await ctx.send(embed=embedVar)
  
  
  #get compliment
  @commands.command(help = 'Get a compliment using a compliment api', aliases = ['c'])
  async def compliment(self,ctx):
    try:
      quote = functionality.functions.get_compliment()
      embedVar = discord.Embed(title="Random Compliment", description = quote, color=0x89cff0)
      await ctx.send(embed=embedVar)
    except:
      embedVar = discord.Embed(title="Error", description = "The compliment API is currently down, try again later", color=0xff0000)
      await ctx.send(embed=embedVar)



  #get joke
  @commands.command(help = 'Get a joke using a joke api', aliases = ['j'])
  async def joke(self,ctx):
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
          json = requests.get("https://some-random-api.ml/img/" + animal).json()
          embed = discord.Embed(title="Here's a " + animal, colour=0x088f8f)
          embed.set_image(url=json["link"])
          await ctx.send(embed=embed)

      except:
        embed = discord.Embed(title="Error " ,description = "A valid animal was not given, see \'$animal\'", colour = 0x088f8f)
        await ctx.send(embed=embed)


  #pull a random meme from a meme api
  @commands.command(help = "get a random meme",aliases = ["m"])
  async def meme(self,ctx):
          json = requests.get("https://some-random-api.ml/meme").json()
          embed = discord.Embed(title="Random meme", colour=0xb00b69)
          embed.set_image(url=json["image"])
          embed.set_footer(text = json["caption"])
          await ctx.send(embed=embed)


  
  #sends most common gif based on query
  @commands.command(help="Search for GIFs (filtered) on Tenor")
  async def gif(self, ctx, *, query):
        json = requests.get(
            f"https://g.tenor.com/v1/search?q={quote(query)}&contentfilter=medium&key={os.environ['TENORKEY']}"
        ).json()

        # Send first result
        try:
            await ctx.send(json["results"][0]["url"])
        except IndexError:
            await ctx.send("❌ Couldn't find any matching GIFs.")





  

def setup(client):
    client.add_cog(Local(client))
    client.add_cog(Api(client))