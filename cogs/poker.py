import discord
from discord.ext import commands
import requests
import json
import asyncio
from dotenv import load_dotenv

load_dotenv(dotenv_path = 'keys.env')
class Poker(commands.Cog):
  """ 
  Games to play with the bot
  """
  def __init__(self,client):
    self.client = client
    self.link = "https://www.deckofcardsapi.com/api/deck/"

  #makes a new deck and returns the ID of the deck being used
  def make_new_deck(self):
    new_deck = requests.get(f"{self.link}new/shuffle/?deck_count=1").json()
    return new_deck["deck_id"]

  def draw_x_cards(self,id,count):
    drawn_cards = requests.get(f"{self.link}{id}/draw/?count={count}").json()
    return drawn_cards["cards"]


  @commands.command(help = "start a poker game")
  async def poker(self,ctx):
   
    embedVar = discord.Embed(title = "Poker", description = f"Click the ♠️ emoji to add yourself ot the game. When all players are in, click the ✅. If you wish to cancel the game click ❌. \n\nNote only {ctx.author.name} can start or cancel the game. The game will time out  after 1 min if no reactions are detected", color = 0x35654d).set_footer(text = f"Poker game requested by {ctx.author.name}")
    
    msg = await ctx.send(embed=embedVar)
   
    await msg.add_reaction('♠️')
    await msg.add_reaction('✅')
    await msg.add_reaction('❌')

    def check(reaction, user):
        return user == ctx.author and str(reaction.emoji) in ["✅", "❌"]

    while True:
      try:
        reaction, user = await self.client.wait_for("reaction_add", timeout=60, check=check)

        #cancel the game
        if str(reaction.emoji) == "❌":
          await msg.delete()
          await ctx.send("The game was canceled by the sender.")
          return
        #start the game
        elif str(reaction.emoji) == "✅":
          msg = await msg.channel.fetch_message(msg.id)
          reaction = msg.reactions[0]
          users = [user async for user in reaction.users()]
          for user in users:
            if user.id == 877014219499925515:
              users.remove(user)
              break
          await msg.clear_reactions()
          embedVar = discord.Embed(title = "Starting Poker game!", description = f"This game as {len(users)} total players:", color = 0x35654d)
          for user in users:
            embedVar.add_field(name = user.name, value = "", inline = False)
          await msg.edit(embed = embedVar)
          break
          
        else:
          await msg.remove_reaction(reaction, user)
        
      except asyncio.TimeoutError:
          await msg.delete()
          await ctx.send("The poker game timed out, try requesting a new game")
          await ctx.delete()
          return

    #gotten here means the game has started
    deck_id = self.make_new_deck() #creating a new deck
    print(deck_id)

    #dm all the players their cards draw the number of cards needed upfront and then parse and send

    #generate the flop
    flop = self.draw_x_cards(deck_id,4) #draw 4 as first is burn

    for card in flop[1:]: #skip the first draw to act as a burn
      await ctx.send(card["images"]["png"])
    
    

      



async def setup(client):
    await client.add_cog(Poker(client))

  
    
      
