import discord
from discord.ext import commands
from datetime import date
from discord.ui import Button,View
import json
import os
import requests


class Flight(commands.Cog):
  """ 
  Real-Time Flight Data
  """
  def __init__(self,client):
      self.client = client
      self.key = os.getenv("aviation_key")

  @commands.command(help = "Planes")
  async def plane(self,ctx):
    response = requests.get(self.url)
    print(response.json())
    await ctx.send("Plane function coming soon, in the mean time have this:")
    await ctx.send("https://lumiere-a.akamaihd.net/v1/images/p_planes_19869_cdb69e0c.jpeg")


  @commands.command(help = "Get info about historic flights")
  async def flight(self,ctx):

    params = {'access_key': self.key}
    api_result = requests.get('http://api.aviationstack.com/v1/flights', params)
    api_response = api_result.json()
    for flight in api_response['results']:
      if (flight['live']['is_ground'] is False):
        print(u'%s flight %s from %s (%s) to %s (%s) is in the air.' % (
            flight['airline']['name'],
            flight['flight']['iata'],
            flight['departure']['airport'],
            flight['departure']['iata'],
            flight['arrival']['airport'],
            flight['arrival']['iata']))



async def setup(client):
   await client.add_cog(Flight(client))