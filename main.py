import discord
from discord.ext import commands
import os
from functionality.days import check_day
from storage.Lists_Storage import thedan, flag_emoji_dict, table
from cogs.help import NewHelpName
from functionality.functions import check_carrot, get_insult
import json
from functionality.trie import Trie
import asyncio
from discord.ui import Button, View
import random
import time
import requests
from dotenv import load_dotenv

load_dotenv('keys.env')

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in keys.env")


def get_prefix(client, message):
    """Get server prefix, with fallback for DMs"""
    if message.guild is None:
        return "$"
    try:
        with open("storage/prefixes.json", "r") as f:
            prefixes = json.load(f)
        return prefixes.get(str(message.guild.id), "$")
    except (FileNotFoundError, json.JSONDecodeError):
        return "$"


intents = discord.Intents.all()
client = commands.Bot(command_prefix=get_prefix, intents=intents)
client.help_command = NewHelpName()
client.synced = True

trie = Trie()


def buildTrie():
    try:
        with open("storage/words.txt", 'r') as file:
            for line in file:
                line = line.strip()
                if line:
                    trie.insert(line)
        return True
    except FileNotFoundError:
        return False


@client.event
async def on_command_error(ctx, error):
    if isinstance(error, commands.CommandNotFound):
        em = discord.Embed(
            title="Error",
            description=f"Command not found. Use `{get_prefix(client, ctx.message)}help` for a list of commands",
            color=0xff0000
        )
        await ctx.send(embed=em)
    elif isinstance(error, commands.MissingPermissions):
        await ctx.send("You don't have permission to use this command.")
    elif isinstance(error, commands.BotMissingPermissions):
        await ctx.send("I don't have the required permissions to do that.")
    elif isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"Missing required argument: {error.param.name}")
    elif isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.1f}s")
    else:
        print(f"Error: {error}")


@client.event
async def on_ready():
    print('=---------------------------------------=')
    print(f"Rate Limited = {client.is_ws_ratelimited()}")
    built = buildTrie()
    if built:
        print("Trie is built. Profanity filter is on.\n")
    else:
        print("Trie was not built, profanity filter is off\n")
    print(f'{client.user} is online')
    print(f'Connected to {len(client.guilds)} servers')
    print('=---------------------------------------=')
    
    # Set status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(client.guilds)} servers | $help"
        )
    )


@client.event
async def on_guild_join(guild):
    try:
        with open("storage/prefixes.json", "r") as f:
            prefixes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        prefixes = {}

    prefixes[str(guild.id)] = "$"

    with open("storage/prefixes.json", "w") as f:
        json.dump(prefixes, f, indent=4)
    
    # Update status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(client.guilds)} servers | $help"
        )
    )


@client.event
async def on_guild_remove(guild):
    try:
        with open("storage/prefixes.json", "r") as f:
            prefixes = json.load(f)
        prefixes.pop(str(guild.id), None)
        with open("storage/prefixes.json", "w") as f:
            json.dump(prefixes, f, indent=4)
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    
    # Update status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(client.guilds)} servers | $help"
        )
    )


@client.event
async def on_message(message):
    if message.author == client.user:
        return
    
    if message.author.bot or message.webhook_id is not None:
        return

    text = message.content.lower()
    text = text.translate(str.maketrans(table))
    author_id = message.author.id
    time_zone = -6
    mod_time = int((int(time.time()) + (time_zone * 3600)) / 86400) % 7

    # Thursday check
    if any(word in text for word in ["thursday", "thurday", "4th day of the week"]):
        if mod_time == 0:
            button = Button(label="isitthursday.org", style=discord.ButtonStyle.primary, url="http://isitthursday.org/")
            view = View()
            view.add_item(button)
            await message.channel.send("Its Thursday!", view=view)
        else:
            button = Button(label="yikes", style=discord.ButtonStyle.primary, url="https://www.merriam-webster.com/dictionary/ignoramus")
            view = View()
            view.add_item(button)
            await message.channel.send("its not thursday...", view=view)

    # Prefix reminder
    if text == "prefix" and message.guild:
        await message.channel.send(f"This server's prefix is `{get_prefix(client, message)}`")

    # Profanity filter
    isClean = True
    message_word_list = text.split()
    for word in message_word_list:
        if trie.search(word):
            isClean = False
            try:
                with open("storage/swears.json", "r") as f:
                    swears = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                swears = {}
            
            swears[str(author_id)] = swears.get(str(author_id), 0) + 1
            
            with open("storage/swears.json", "w") as f:
                json.dump(swears, f, indent=4)
            break

    # Steely Dan
    if any(word in text for word in thedan):
        await message.reply("I LOVE STEELY DAN!")

    # Day checks
    emoji = check_day(text)
    if emoji:
        await message.add_reaction(emoji)

    # Carrot agree
    if check_carrot(text, message) == 1:
        await message.channel.send(message.content + '^')

    # Defense against attacks
    if not isClean and any(word in text for word in ["clarence", "bot", "hunter", "huntie"]):
        await message.reply(get_insult())

    await client.process_commands(message)


async def main():
    async with client:
        await client.load_extension('cogs.services')
        await client.load_extension('cogs.mod')
        await client.load_extension('cogs.games')
        await client.load_extension('cogs.help')
        await client.load_extension('cogs.flight')
        await client.load_extension('cogs.poker')
        await client.load_extension('cogs.math')
        await client.load_extension('cogs.translate')
        await client.load_extension('cogs.trivia')
        # await client.load_extension('cogs.music')
        await client.load_extension('cogs.owner')
        await client.load_extension('status')
        await client.start(TOKEN)


asyncio.run(main())