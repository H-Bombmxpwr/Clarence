import discord
from discord.ext import commands, tasks
import os
from functionality.keep_alive import keep_alive
from functionality.days import check_day
from storage.Lists_Storage import thedan, status1, flag_emoji_dict, table, load
from cogs.help import NewHelpName
from functionality.functions import check_carrot, get_insult
import json
from functionality.trie import Trie
from itertools import cycle
import asyncio
from discord.ui import Button,View
import random
import time
import requests
from dotenv import load_dotenv
from googletrans import Translator

load_dotenv(dotenv_path = 'keys.env')

def get_prefix(client, message):  #grab server prefix
    with open("storage/prefixes.json", "r") as f:
        prefixes = json.load(f)
      
    return prefixes[str(message.guild.id)]


#status1 = ["Hey!", "We back!"]
client = commands.Bot(command_prefix=get_prefix, intents=discord.Intents.all()) #the whole bot itself
client.help_command = NewHelpName()
client.synced = True
status_i = cycle(status1) # for the song status 
# for translating messages

trie = Trie() # for the built in profanity filter


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
    print('=---------------------------------------=')
    print("Rate Limited = " + str(client.is_ws_ratelimited()))
    change_status.start()
    built = False
    built = buildTrie()
    if built:
        print("Trie is built. Profanity filter is on.\n")
    else:
        print("Trie was not built, profanity filter is off\n")
    print(f'Status song: {load["title"]} by  {load["author"]}')

    print('{0.user} is online'.format(client))
    print('=---------------------------------------=')
    


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


@client.event #reactions for google translate feature
async def on_reaction_add(reaction, user):
    # Check if the reaction is a flag emoji
    print("reactin")
    if reaction.emoji in flag_emoji_dict:
        # Get the language code corresponding to the flag emoji
        translator = Translator()
        lang_code = flag_emoji_dict[reaction.emoji]
    
        # Get the original message
        message = reaction.message
        print(message.content)
        # Translate the message to the desired language
        detected_lang = translator.detect(message.content)
        print(detected_lang.lang)
        translated_message = translator.translate(message.content, dest=lang_code).text
        print(translated_message)
        pronunciation_message =translator.translate(message.content, dest=lang_code).pronunciation
        print(pronunciation_message)
        

        embed = discord.Embed(title='Translated Text', description=f'{translated_message}', color=0x00ff00)
        embed.add_field(name="Original Text", value=message.content, inline=False)
        embed.add_field(name="Translated from:", value=f'{detected_lang.lang.capitalize()} ({detected_lang.confidence*100:.2f}%)')
        embed.add_field(name="Pronunciation:", value=pronunciation_message, inline=False)
        await reaction.message.channel.send(content=f'{user.mention}',embed=embed)

@client.event
async def on_message(message):
    if message.author == client.user:
        return

    text = message.content.lower()
    text = text.translate(str.maketrans(table))
    author_id = message.author.id
    time_zone = -6
    mod_time = int((int(time.time()) + (time_zone * 3600)) / 86400) % 7

    if any(word in text for word in ["thursday","thurday","4th day of the week"]):
          if  mod_time == 0:
            button = Button(label = "isitthursday.org", style = discord.ButtonStyle.primary, url = "http://isitthursday.org/")
            view = View()
            view.add_item(button)
            await message.channel.send("Its Thursday!", view=view)
            await message.channel.send(requests.get("isitthrusday.org"))
          else:
            button = Button(label = "yikes", style = discord.ButtonStyle.primary, url = "https://www.merriam-webster.com/dictionary/bozo")
            view = View()
            view.add_item(button)
            await message.channel.send("its not thursday...", view=view)

    #sends the prefix if the useer forgets what it is
    if text == "prefix":
        await message.channel.send("This server's prefix is `" +
                                   str(get_prefix(client, message)) + "`")

    #profanity filter
    isClean = True
    message_word_list = text.split()
    for word in message_word_list:
        if trie.search(word):
            isClean = False
            
            if not isClean:
                with open("storage/swears.json", "r") as f:
                    swears = json.load(f)
                if str(author_id) in swears.keys():
                    swears[str(author_id)] = swears[str(author_id)] + 1
                    
                else:
                    swears[str(author_id)] = 1
                f.close()
                with open("storage/swears.json","w") as f:
                        json.dump(swears,f, indent = 4)

    #the dan
    if any(word in text for word in thedan):
        await message.channel.reply("I LOVE STEELY DAN!")

    
      # rest of the days
    emoji = check_day(text)
    if emoji:
        await message.add_reaction(emoji)


    #Carrot agree function
    if check_carrot(text,message) == 1:
     await message.channel.send(message.content + '^')

    

    #defense to attacks towards clarence, really not well written but funny
    if not isClean and any(word in text for word in ["clarence","bot","hunter","huntie"]):
      await message.reply(get_insult())

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
        await client.load_extension('cogs.math')
        await client.start(os.getenv('token'))


keep_alive()
asyncio.run(main())