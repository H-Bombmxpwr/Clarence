from dotenv import load_dotenv

load_dotenv('keys.env')  # before other imports so DATA_DIR etc. are visible to them

import asyncio
import hashlib
import json
import logging
import os
import time
import traceback

import aiohttp
import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

from constants.lists import thedan, table
from functionality.days import check_day
from functionality.functions import check_carrot, get_insult
from functionality.store import data_path
from functionality.trie import Trie

TOKEN = os.getenv('DISCORD_TOKEN')
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in keys.env")

# Owner-only commands are registered only in this server so nobody else sees them
DEV_GUILD_ID = int(os.getenv('DEV_GUILD_ID') or 0)
COMMAND_HASH_FILE = data_path(".command_hash")

EXTENSIONS = [
    'cogs.services',
    'cogs.mod',
    'cogs.automod',
    'cogs.serverlog',
    'cogs.games',
    'cogs.help',
    'cogs.flight',
    'cogs.poker',
    'cogs.math',
    'cogs.translate',
    'cogs.trivia',
    'cogs.music',
    'cogs.owner',
    'status',
]

log = logging.getLogger("clarence")


class Clarence(commands.Bot):
    def __init__(self):
        # Slash-command only: the prefix is never used, but commands.Bot requires one
        # Everything except presences: presence updates are by far the busiest gateway event and
        # caching them costs a lot of RAM/CPU, and nothing but /userinfo's activity line used them.
        intents = discord.Intents.all()
        intents.presences = False
        super().__init__(command_prefix=commands.when_mentioned, intents=intents, help_command=None)
        self.session: aiohttp.ClientSession = None
        self.dev_guild = discord.Object(DEV_GUILD_ID) if DEV_GUILD_ID else None
        self.command_ids: dict[str, int] = {}

    async def setup_hook(self):
        self.session = aiohttp.ClientSession()
        self.tree.on_error = on_app_command_error

        for ext in EXTENSIONS:
            try:
                await self.load_extension(ext)
            except Exception:
                log.exception("Failed to load extension %s", ext)

        await self.sync_commands()

    async def sync_commands(self, force: bool = False):
        """Sync slash commands with Discord, but only when they've actually changed (sync is rate limited)."""
        payload = {
            "global": [c.to_dict(self.tree) for c in self.tree.get_commands()],
            "dev": [c.to_dict(self.tree) for c in self.tree.get_commands(guild=self.dev_guild)] if self.dev_guild else [],
            "dev_id": DEV_GUILD_ID,
        }
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        try:
            with open(COMMAND_HASH_FILE) as f:
                previous = f.read().strip()
        except FileNotFoundError:
            previous = None

        if force or digest != previous:
            synced = await self.tree.sync()
            if self.dev_guild:
                await self.tree.sync(guild=self.dev_guild)
            with open(COMMAND_HASH_FILE, "w") as f:
                f.write(digest)
            log.info("Synced %d global commands", len(synced))
        else:
            synced = await self.tree.fetch_commands()
            log.info("Commands unchanged, skipped sync")
        self.command_ids = {c.name: c.id for c in synced}

    def mention(self, qualified_name: str) -> str:
        """Clickable </command:id> mention, falling back to plain /command."""
        cid = self.command_ids.get(qualified_name.split()[0])
        return f"</{qualified_name}:{cid}>" if cid else f"/{qualified_name}"

    async def close(self):
        if self.session:
            await self.session.close()
        await super().close()


client = Clarence()

trie = Trie()


def buildTrie():
    try:
        with open("constants/words.txt", 'r') as file:
            for line in file:
                line = line.strip()
                if line:
                    trie.insert(line)
        return True
    except FileNotFoundError:
        return False


async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if getattr(error, "handled", False):  # a cog's error handler already replied
        return
    if isinstance(error, app_commands.MissingPermissions):
        msg = f"You need the **{', '.join(error.missing_permissions).replace('_', ' ')}** permission to use this."
    elif isinstance(error, app_commands.BotMissingPermissions):
        msg = f"I need the **{', '.join(error.missing_permissions).replace('_', ' ')}** permission to do that."
    elif isinstance(error, app_commands.CommandOnCooldown):
        msg = f"This command is on cooldown. Try again in {error.retry_after:.1f}s."
    elif isinstance(error, app_commands.NoPrivateMessage):
        msg = "This command can only be used in a server."
    elif isinstance(error, app_commands.CheckFailure):
        msg = "You can't use this command."
    else:
        original = getattr(error, "original", error)
        if isinstance(original, discord.Forbidden):
            msg = "I don't have permission to do that (check my role position and channel permissions)."
        else:
            name = interaction.command.qualified_name if interaction.command else "?"
            print(f"Error in /{name}:")
            traceback.print_exception(type(original), original, original.__traceback__)
            msg = f"Something went wrong: `{type(original).__name__}: {str(original)[:200]}`"

    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"{msg}", ephemeral=True)
        else:
            await interaction.response.send_message(f"{msg}", ephemeral=True)
    except discord.HTTPException:
        pass


@client.event
async def on_ready():
    print('=---------------------------------------=')
    print(f"Rate Limited = {client.is_ws_ratelimited()}")
    built = False
    # built = buildTrie()
    if built:
        print("Trie is built. Profanity filter is on.\n")
    else:
        print("Trie was not built, profanity filter is off\n")
    print(f'{client.user} is online')
    print(f'Connected to {len(client.guilds)} servers')
    print(f'Dev guild for owner commands: {DEV_GUILD_ID or "not set (owner commands disabled)"}')
    print('=---------------------------------------=')


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

    # Profanity filter
    isClean = True
    message_word_list = text.split()
    for word in message_word_list:
        if trie.search(word):
            isClean = False
            try:
                with open(data_path("swears.json"), "r") as f:
                    swears = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                swears = {}

            swears[str(author_id)] = swears.get(str(author_id), 0) + 1

            with open(data_path("swears.json"), "w") as f:
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
        await message.reply(await asyncio.to_thread(get_insult))


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    async with client:
        await client.start(TOKEN)


asyncio.run(main())
