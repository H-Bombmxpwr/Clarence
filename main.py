import discord
from discord.ext import commands
import os
from functionality.keep_alive import keep_alive
from storage.Lists_Storage import thedan,days
import cogs.music,cogs.services,cogs.games,cogs.mod,cogs.help #import the cogs
from functionality.functions import check_carrot,punish_user
import time
from functionality.trie import Trie


cogs = [cogs.music,cogs.services,cogs.mod,cogs.games,cogs.help]

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
    file = open("storage/words.txt", 'r')

    for line in file:
        line = line.strip()
        trie.insert(line)
    file.close()
    return True



@client.event
async def on_ready():
  print("Attempting to build trie......")
  built = False
  built = buildTrie()
  if built:
    print("Trie is built. Profanity filter is on.\n")
  else:
    print("Trie was not built, profanity filter is off\n")
  
  print('{0.user} is back online'.format(client))
  print('=------------------------------=')
  



@client.event 
async def on_command_error(ctx, error): #detects if a command is valid
    if isinstance(error, commands.CommandNotFound): 
        em = discord.Embed(title=f"Error", description=f"Command \'" + ctx.message.content + "   \' not found. \nUse `list: ` or `help: ` for a list of commands", color=0xff0000) 
        await ctx.send(embed=em)



@client.event
async def on_message(message):
  if message.author == client.user:
    return

  text = message.content.lower()
  text = text.translate(str.maketrans(table))
  author_id = message.author.id

 
 #profanity filter
  if author_id != 239605426033786881: 
        isClean = True
        message_word_list = text.split()
        for word in message_word_list:
            if trie.search(word):
                isClean = False
                break
        if not isClean:
            await message.channel.send(punish_user(author_id,word))



  # thursday!!!
  if any(word in text for word in days):
    time_zone = -6
    
    if int((int(time.time()) + (time_zone * 3600))/86400) % 7 == 0:
      await message.channel.send("```\nIt's Thursday in the North American Central Time Zone, Happy Thursday!```")  
      await message.channel.send('http://isitthursday.org/')
    else:
      await message.channel.send("```\nIt's not Thursday in the North American Central Time Zone\n    \nYou bozo\n```")
 
  
  #the dan
  if any(word in text for word in thedan):
    emojis = ['🎸','🎹','🎷','🥁', '🎤']
    for emoji in emojis:
      await message.add_reaction(emoji)
    await message.reply("I LOVE STEELY DAN!")

  
  #Carrot agree function
  if check_carrot(text,message) == 1: 
    await message.channel.send(message.content + '^')

  
  #mystery function
  if text == os.getenv("cursed_thing"):
    emoji = '😦'
    await message.add_reaction(emoji)
    await message.channel.send("Why the actual heck do you know what a " + text + " is??")

  await client.process_commands(message)



keep_alive()
client.run(os.getenv('token'))