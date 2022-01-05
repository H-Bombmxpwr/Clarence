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
from trie import Trie
from dotenv import load_dotenv

load_dotenv()
cogs = [music,services,mod,games]

client = commands.Bot(command_prefix='$',intents = discord.Intents.all())


for i in range(len(cogs)):
  cogs[i].setup(client)

trie = Trie()
table = {
    "\"": None,
    "'": None,
    "-": None,
    "`": None,
    "~": None,
    ",": None,
    ".": None,
    ":": None,
    ";": None,
    "_": None
}


def buildTrie():
    file = open("words.txt", 'r')
    for line in file:
        line = line.strip()
        trie.insert(line)


def punish_user(user_id):
    user_id = '<@' + str(user_id) + '>'
    responses = [
        "You kiss your mother with that mouth, {}?",
        "That's some colorful language, {}.",
        "Come on now, {}. Did you really need to say that?",
        "{} - LANGUAGE!",
        "Hey now {}, watch your mouth.",
        "We don't use that kind of language here, {}."
    ]

    choice = random.choice(responses)
    choice = choice.format(user_id)

    return choice



@client.event
async def on_ready():
  print('It is still working probably \n{0.user} do be online'.format(client))
  print('=------------------------------=')
  buildTrie()
  print("Trie is built. ready to read messages.")



@client.event 
async def on_command_error(ctx, error): 
    if isinstance(error, commands.CommandNotFound): 
        em = discord.Embed(title=f"Error", description=f"Command \'" + ctx.message.content + "   \' not found. Use $about or $help for a list of commands", color=0xff0000) 
        await ctx.send(embed=em)


@client.event
async def on_message(message):
  if message.author == client.user:
    return
  
  text = message.content
  text = text.translate(str.maketrans(table))
  author_id = message.author.id

  # profanity checker
  if author_id != 877014219499925515:
        isClean = True
        message_word_list = text.split()
        for word in message_word_list:
            if trie.search(word):
                isClean = False
                break
        if not isClean:
            await message.channel.send(punish_user(author_id))



  # thursday!!!
  if any(word in message.content.lower() for word in days):
    time_zone = -6
    
    if int((int(time.time()) + (time_zone * 3600))/86400) % 7 == 0:
      await message.channel.send("```\nIt's Thursday, Happy Thursday!\n    \nhttp://isitthursday.org/\n```")
    else:
      await message.channel.send("```\nIt's not Thursday\n    \nYou bozo\n```")
 
  
  #the dan
  if any(word in message.content.lower() for word in thedan):
    emojis = ['🎸','🎹','🎷','🥁', '🎤']
    for emoji in emojis:
      await message.add_reaction(emoji)
    await message.channel.send("```\nI LOVE STEELY DAN!\n```")

  
  #Carrot agree function
  if message.author.id == 239605426033786881 and check_carrot(message.content.lower()) == 1: 
    await message.channel.send(message.content + '^')

  
  await client.process_commands(message)



keep_alive()
client.run(os.getenv('token'))