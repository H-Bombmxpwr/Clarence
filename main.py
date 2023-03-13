import discord
from discord.ext import commands, tasks
import os
from functionality.keep_alive import keep_alive
from functionality.days import check_day
from storage.Lists_Storage import thedan, days, status1
from cogs.help import NewHelpName
from functionality.functions import check_carrot
import json
from functionality.trie import Trie
from itertools import cycle
import asyncio
from discord.ui import Button,View
import random


def get_prefix(client, message):  #grab server prefix
    with open("storage/prefixes.json", "r") as f:
        prefixes = json.load(f)
      
    return prefixes[str(message.guild.id)]



client = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all())
client.help_command = NewHelpName()
client.synced = True
status_i = cycle(status1)

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
async def on_command_error(ctx, error):  #detects if a command is valid
    if isinstance(error, commands.CommandNotFound):
        em = discord.Embed(
            title=f"Error",
            description=f"Command \'" + ctx.message.content +
            "   \' not found. \nUse `list: ` or `help: ` for a list of commands",
            color=0xff0000)
        await ctx.send(embed=em)


@client.event
async def on_ready():
    print('=------------------------------=')
    print("Rate Limited = " + str(client.is_ws_ratelimited()))
    change_status.start()
    built = False
    #built = buildTrie()
    if built:
        print("Trie is built. Profanity filter is on.\n")
    else:
        print("Trie was not built, profanity filter is off\n")

    print('{0.user} is online'.format(client))
    print('=------------------------------=')
    print(status1)
    


@tasks.loop(seconds=10)
async def change_status():
    await client.change_presence(activity=discord.Activity(
        type=discord.ActivityType.listening, name=next(status_i)))
      

@client.event
async def on_guild_join(guild):  #add default prefix to the json file
    with open("storage/prefixes.json", "r") as f:
        prefixes = json.load(f)

    prefixes[str(guild.id)] = "$"

    with open("storage/prefixes.json", "w") as f:
        json.dump(prefixes, f, indent=4)


@client.event
async def on_guild_remove(guild):  #remove prefix if bot is kicked
    with open("storage/prefixes.json", "r") as f:
        prefixes = json.load(f)

    prefixes.pop(str(guild.id))

    with open("storage/prefixes.json", "w") as f:
        json.dump(prefixes, f, indent=4)


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    text = message.content.lower()
    text = text.translate(str.maketrans(table))
    author_id = message.author.id
    time_zone = -6
    

    #sends the prefix if the useer forgets what it is
    if text == "prefix":
        await message.channel.send("This server's prefix is `" +
                                   str(get_prefix(client, message)) + "`")

    #profanity filter
    #if author_id != 239605426033786881:
    #    isClean = True
    #    message_word_list = text.split()
    #    for word in message_word_list:
    #        if trie.search(word):
    #            isClean = False
    #            break
    #    if not isClean:
    #        await message.add_reaction("😮")

    #the dan
    if any(word in text for word in thedan):
        await message.reply("I LOVE STEELY DAN!")

    # thursday!!!
    if any(word in text for word in days):
            button = Button(label = "isitthursday.org", style = discord.ButtonStyle.primary, url = "http://isitthursday.org/")
            view = View()
            view.add_item(button)
            await message.channel.send("Is it thursday?", view=view)
    
      # rest of the days
    emoji = check_day(text)

    if emoji:
        await message.add_reaction(emoji)

    if message.author.id == 1078785366468853961:
      if random.randint(1,100) < 3:
        await message.add_reaction("❤️")

    #Carrot agree function
    if check_carrot(text,message) == 1:
     await message.channel.send(message.content + '^')

    await client.process_commands(message)


async def main():
    async with client:
        await client.load_extension('cogs.music')
        await client.load_extension('cogs.services')
        await client.load_extension('cogs.mod')
        await client.load_extension('cogs.games')
        await client.load_extension('cogs.help')
        await client.load_extension('cogs.flight')
        await client.load_extension('cogs.poker')
        await client.start(os.getenv('token'))


keep_alive()
asyncio.run(main())