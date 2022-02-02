import discord
from discord.ext import commands
import functionality.functions
from functionality.structures import FizzBuzz
from datetime import date
import requests

class Games(commands.Cog):
  """ 
  Games to play with the bot
  """
  def __init__(self,client):
      self.client = client


  #fizzbuzz game
  @commands.command(help = "play fizzbuzz")
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
        embedVar = discord.Embed(title = 'Stats for @' + str(ctx.author.name), description = 'Tracked statistics for fizzbuzz',color=0x32CD32).set_footer(icon_url = ctx.author.avatar_url, text = "As of " + str(date.today()))
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








def setup(client):
    client.add_cog(Games(client))
