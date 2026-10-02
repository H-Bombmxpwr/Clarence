# cogs/games.py
import asyncio
import random
from io import BytesIO
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from PIL import Image

from constants.lists import emojis
from functionality.store import JsonStore
from functionality.structures import FizzBuzz

DECK_API_BASE = "https://www.deckofcardsapi.com/api/deck"
OWNER_ID = 239605426033786881

nfts = JsonStore("nft.json")


class DeletePickupView(View):
    def __init__(self, *, author_id: int, channel: discord.abc.Messageable, to_delete: list[discord.Message]):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.channel = channel
        self.to_delete = to_delete

    @discord.ui.button(label="Delete pickup", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Only the command invoker can delete these messages.", ephemeral=True)
        await interaction.response.send_message("Deleting…", ephemeral=True)
        try:
            for i in range(0, len(self.to_delete), 100):
                await self.channel.delete_messages(self.to_delete[i:i + 100])
        except (discord.Forbidden, discord.HTTPException, AttributeError):
            for m in self.to_delete:
                try:
                    await m.delete()
                except (discord.Forbidden, discord.NotFound):
                    pass
        button.disabled = True
        try:
            await interaction.message.edit(content="Pickup cleanup attempted.", view=self)
        except (discord.Forbidden, discord.NotFound):
            pass


class FizzBuzzView(View):
    """Press the right button for each number. One wrong answer ends the game."""

    def __init__(self, player: discord.abc.User):
        super().__init__(timeout=30)
        self.player = player
        self.count = 1
        self.message: Optional[discord.Message] = None

    def embed(self, note: str = "") -> discord.Embed:
        e = discord.Embed(title="FizzBuzz", color=0x5865f2,
                          description=f"What comes next?\n\n# {self.count}?\n\n{note}")
        e.set_footer(text="Multiple of 3 → Fizz • of 5 → Buzz • of both → FizzBuzz • otherwise → Number")
        return e

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message("Start your own game with `/fizzbuzz`!", ephemeral=True)
            return False
        return True

    async def answer(self, interaction: discord.Interaction, guess: str):
        correct = FizzBuzz(self.count).solve(self.count)
        if correct.isdigit():
            correct = "Number"
        if guess == correct:
            self.count += 1
            await interaction.response.edit_message(embed=self.embed(f"Score: **{self.count - 1}**"), view=self)
        else:
            self.stop()
            await interaction.response.edit_message(
                embed=discord.Embed(title="Game over", color=0xe74c3c,
                                    description=f"**{self.count}** was **{correct}**, not {guess}.\nYou reached **{self.count - 1}**!"),
                view=None)

    @discord.ui.button(label="Number", style=discord.ButtonStyle.secondary)
    async def number(self, interaction, button):
        await self.answer(interaction, "Number")

    @discord.ui.button(label="Fizz", style=discord.ButtonStyle.primary)
    async def fizz(self, interaction, button):
        await self.answer(interaction, "Fizz")

    @discord.ui.button(label="Buzz", style=discord.ButtonStyle.success)
    async def buzz(self, interaction, button):
        await self.answer(interaction, "Buzz")

    @discord.ui.button(label="FizzBuzz", style=discord.ButtonStyle.danger)
    async def fizzbuzz(self, interaction, button):
        await self.answer(interaction, "FizzBuzz")

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(embed=discord.Embed(title="Time's up!", color=0x95a5a6,
                                                            description=f"You reached **{self.count - 1}**."), view=None)
            except discord.HTTPException:
                pass


class Fun(commands.Cog):
    """Fun Games and Entertainment"""

    def __init__(self, client):
        self.client = client
        self.ctx_ratio = app_commands.ContextMenu(name="Ratio", callback=self.ratio_context)

    async def cog_load(self):
        self.client.tree.add_command(self.ctx_ratio)

    async def cog_unload(self):
        self.client.tree.remove_command(self.ctx_ratio.name, type=self.ctx_ratio.type)

    @property
    def session(self):
        return self.client.session

    @app_commands.command(description="View or set your NFT")
    @app_commands.describe(new_nft="Set a new NFT (any text or URL); leave empty to view yours")
    async def nft(self, interaction: discord.Interaction, new_nft: Optional[str] = None):
        uid = str(interaction.user.id)
        if new_nft is not None:
            nfts.data[uid] = new_nft
            nfts.save()
            return await interaction.response.send_message(f"Your **NEW** NFT, {interaction.user.mention}:\n{new_nft}")
        if uid in nfts.data:
            await interaction.response.send_message(f"Your NFT, {interaction.user.mention}:\n{nfts.data[uid]}")
        else:
            await interaction.response.send_message("You don't have an NFT. Set one with `/nft new_nft:<url or text>`", ephemeral=True)

    @app_commands.command(description="Play FizzBuzz with buttons")
    async def fizzbuzz(self, interaction: discord.Interaction):
        view = FizzBuzzView(interaction.user)
        await interaction.response.send_message(embed=view.embed(), view=view)
        view.message = await interaction.original_response()

    @app_commands.command(description="52 card pickup")
    @app_commands.guild_only()
    async def fiftytwo(self, interaction: discord.Interaction, member: discord.Member):
        if member.id == OWNER_ID:
            return await interaction.response.send_message("Hunter would not like to play that game right now")
        if member.id == self.client.user.id:
            return await interaction.response.send_message("I am throwing the cards, not picking them up")
        if member.id == interaction.user.id:
            return await interaction.response.send_message("Who would want to play this game with themselves?")

        await interaction.response.send_message(f"{member.mention}, 52 card pickup!")
        async with self.session.get(f"{DECK_API_BASE}/new/draw/?count=52") as r:
            cards = (await r.json()).get("cards", [])
        if len(cards) < 52:
            return await interaction.followup.send("Deck API did not return 52 cards.")

        messages: list[discord.Message] = [await interaction.original_response()]
        for c in cards:
            embed = discord.Embed(title=f"{c.get('value', 'CARD')} of {c.get('suit', 'SUIT')}")
            if c.get("image"):
                embed.set_image(url=c["image"])
            messages.append(await interaction.channel.send(content=member.mention, embed=embed))
            await asyncio.sleep(0.35)  # avoid rate limits from 52 rapid sends
        await interaction.channel.send("Cleanup:", view=DeletePickupView(author_id=interaction.user.id,
                                                                         channel=interaction.channel, to_delete=messages))

    @app_commands.command(description="Get something to do when bored")
    async def bored(self, interaction: discord.Interaction):
        try:
            async with self.session.get("https://bored-api.appbrewery.com/random", timeout=10) as r:
                data = await r.json(content_type=None)
            await interaction.response.send_message(f"**Idea:** {data['activity']} *({data.get('type', 'misc')})*")
        except Exception:
            await interaction.response.send_message("Couldn't fetch an activity. Try again!", ephemeral=True)

    async def ratio_context(self, interaction: discord.Interaction, message: discord.Message):
        await interaction.response.send_message("Ratio'd!", ephemeral=True)
        for emoji in random.sample(emojis, k=min(10, len(emojis))):
            try:
                await message.add_reaction(emoji)
            except discord.HTTPException:
                break

    @app_commands.command(description="Count to a number by typing each number in chat")
    async def count(self, interaction: discord.Interaction, endpoint: app_commands.Range[int, 1, 1000]):
        count, mistakes = 1, 0
        await interaction.response.send_message(f"{interaction.user.mention}, count to **{endpoint}**! Type each number. Type `give up` to quit.")

        def check(m):
            return m.author == interaction.user and m.channel == interaction.channel

        while count <= endpoint:
            try:
                msg = await self.client.wait_for("message", check=check, timeout=60)
            except asyncio.TimeoutError:
                return await interaction.channel.send("Time's up!")
            if msg.content.lower() == 'give up':
                return await interaction.channel.send(f"You gave up at **{count}**")
            if msg.content.strip() == str(count):
                await msg.add_reaction('✅')
                count += 1
            else:
                await msg.add_reaction('❌')
                mistakes += 1
                await interaction.channel.send(f"Wrong! You're on **{count}**")
                if mistakes >= 20:
                    return await interaction.channel.send("Too many mistakes. Game over!")
        await interaction.channel.send(embed=discord.Embed(title="CONGRATS!", description=f"You counted to **{endpoint}**!", color=0xFFD700))

    @app_commands.command(description="Random quotes from 2070 Paradigm Shift")
    async def paradigm(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 30] = 1):
        try:
            with open("constants/paradigm.txt", "r") as f:
                lines = [l.strip() for l in f if l.strip()]
        except OSError:
            return await interaction.response.send_message("Could not load paradigm file", ephemeral=True)
        picked = "\n".join(f"**{i + 1}:** {random.choice(lines)}" for i in range(number))
        await interaction.response.send_message(picked[:2000])

    @app_commands.command(description="Get a facepalm GIF")
    async def facepalm(self, interaction: discord.Interaction):
        try:
            async with self.session.get("https://nekos.best/api/v2/facepalm", timeout=10) as r:
                data = await r.json(content_type=None)
            await interaction.response.send_message(data["results"][0]["url"])
        except Exception:
            await interaction.response.send_message("🤦", ephemeral=False)

    @app_commands.command(description="Tell someone to shut up")
    async def shutup(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        if member is None:
            async for msg in interaction.channel.history(limit=50):
                if msg.author.id not in (interaction.user.id, self.client.user.id) and not msg.author.bot:
                    member = msg.author
                    break
        if member:
            await interaction.response.send_message(f"Shut up {member.mention}!")
        else:
            await interaction.response.send_message("No one to shut up!", ephemeral=True)

    @app_commands.command(description="Convert someone's avatar (or an image URL) to emojis")
    @app_commands.describe(member="Whose avatar to use", url="Or an image URL", size="Width/height in emojis")
    async def emojify(self, interaction: discord.Interaction, member: Optional[discord.User] = None,
                      url: Optional[str] = None, size: app_commands.Range[int, 4, 20] = 14):
        COLORS = {
            (0, 0, 0): "⬛", (0, 0, 255): "🟦", (255, 0, 0): "🟥", (255, 255, 0): "🟨",
            (255, 165, 0): "🟧", (255, 255, 255): "⬜", (0, 255, 0): "🟩", (128, 0, 128): "🟪", (139, 69, 19): "🟫",
        }

        def closest(color):
            return COLORS[min(COLORS, key=lambda c: sum((a - b) ** 2 for a, b in zip(color, c)))]

        source = url or (member or interaction.user).display_avatar.with_format("png").url
        await interaction.response.defer()
        try:
            async with self.session.get(source, timeout=10) as r:
                raw = await r.read()
            img = Image.open(BytesIO(raw)).convert("RGB").resize((size, size), Image.NEAREST)
            rows = ["".join(closest(img.getpixel((x, y))) for x in range(size)) for y in range(size)]
            await interaction.followup.send("\n".join(rows)[:2000])
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(description="Roll a die")
    async def dice(self, interaction: discord.Interaction, sides: app_commands.Range[int, 2, 1000] = 6):
        await interaction.response.send_message(f"You rolled a **{random.randint(1, sides)}** (d{sides})")

    @app_commands.command(description="Flip a coin")
    async def coinflip(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"**{random.choice(['Heads', 'Tails'])}!**")

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.", "Yes – definitely.", "You may rely on it.",
            "As I see it, yes.", "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.", "Cannot predict now.",
            "Concentrate and ask again.", "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful.",
        ]
        embed = discord.Embed(title="Magic 8-Ball", color=0x000000)
        embed.add_field(name="Question", value=question[:1024], inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        await interaction.response.send_message(embed=embed)


async def setup(client):
    await client.add_cog(Fun(client))
