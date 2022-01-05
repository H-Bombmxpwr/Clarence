import discord
from discord.ext import commands
import os
import random
from keep_alive import keep_alive
from Lists_Storage import *
from functions import *
import music,services,games,mod #import the cogs
from functions import check_carrot
import time


cogs = [music,services,mod,games]

client = commands.Bot(command_prefix='$',intents = discord.Intents.all())


for i in range(len(cogs)):
  cogs[i].setup(client)



@client.event
async def on_ready():
  print('It is still working probably \n{0.user} do be online'.format(client))
  print('=------------------------------=')
  



@client.event 
async def on_command_error(ctx, error): 
    if isinstance(error, commands.CommandNotFound): 
        em = discord.Embed(title=f"Error", description=f"Command \'" + ctx.message.content + "   \' not found. Use $about or $help for a list of commands", color=0xff0000) 
        await ctx.send(embed=em)


@client.event
async def on_message(message):
  if message.author == client.user:
    return

  with open('words.txt', 'r') as f:
    words = f.read()
    badwords = words.split()
    f.close()


  msg = message.content.lower()
  if any(word in msg for word in badwords):
            await message.channel.send(punish_user(message.author.id))



  # thursday!!!
  if any(word in msg for word in days):
    time_zone = -6
    
    if int((int(time.time()) + (time_zone * 3600))/86400) % 7 == 0:
      await message.channel.send("```\nIt's Thursday, Happy Thursday!\n    \nhttp://isitthursday.org/\n```")
    else:
      await message.channel.send("```\nIt's not Thursday\n    \nYou bozo\n```")
 
  
  #the dan
  if any(word in msg for word in thedan):
    emojis = ['🎸','🎹','🎷','🥁', '🎤']
    for emoji in emojis:
      await message.add_reaction(emoji)
    await message.channel.send("```\nI LOVE STEELY DAN!\n```")

  
  #Carrot agree function
  if message.author.id == 239605426033786881 and check_carrot(msg) == 1: 
    await message.channel.send(message.content + '^')

  
  await client.process_commands(message)



keep_alive()
client.run(os.getenv('token'))