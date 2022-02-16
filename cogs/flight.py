import discord
from discord.ext import commands
from datetime import date
from discord.ui import Button,View
import json


class Flight(commands.Cog):
  """ 
  Real-Time Flight Data
  """
  def __init__(self,client):
      self.client = client

  @commands.command(help = "Planes")
  async def plane(self,ctx):
    await ctx.send("I like planes")
    await ctx.send("https://lumiere-a.akamaihd.net/v1/images/p_planes_19869_cdb69e0c.jpeg")
    await ctx.send("https://m.media-amazon.com/images/I/51G21JUHiCL._SX342_.jpg")
  



def setup(client):
    client.add_cog(Flight(client))