# cogs/games.py
import discord
from discord.ext import commands
from functionality.functions import fix_lines
from functionality.structures import FizzBuzz, Card
from datetime import date
import requests
from discord import NotFound
from contextlib import suppress
from constants.lists import emojis
import random
import json
from PIL import Image
from typing import Union
from io import BytesIO
import asyncio
import aiohttp
from discord.ui import View, Button


DECK_API_BASE = "https://www.deckofcardsapi.com/api/deck"  # API base :contentReference[oaicite:1]{index=1}

class DeletePickupView(View):
    def __init__(self, *, author_id: int, channel: discord.abc.Messageable, to_delete: list[discord.Message]):
        super().__init__(timeout=300)  # 5 minutes
        self.author_id = author_id
        self.channel = channel
        self.to_delete = to_delete

        self.add_item(self.DeleteButton())

    class DeleteButton(Button):
        def __init__(self):
            super().__init__(label="Delete pickup", style=discord.ButtonStyle.danger)

        async def callback(self, interaction: discord.Interaction):
            view: "DeletePickupView" = self.view  # type: ignore

            # Only allow the user who invoked the command to delete
            if interaction.user.id != view.author_id:
                await interaction.response.send_message("Only the command invoker can delete these messages.", ephemeral=True)
                return

            # Acknowledge immediately to avoid interaction timeouts
            await interaction.response.send_message("Deleting…", ephemeral=True)

            # Try bulk delete first (fast, <=100 messages). Requires Manage Messages.
            try:
                # Bulk delete works only in text channels and for messages < 14 days old.
                if isinstance(view.channel, (discord.TextChannel, discord.Thread)):
                    await view.channel.delete_messages(view.to_delete)
                else:
                    # Fallback: delete individually for non-standard channels
                    for m in view.to_delete:
                        try:
                            await m.delete()
                        except (discord.Forbidden, discord.NotFound):
                            pass
            except (discord.Forbidden, discord.HTTPException):
                # Fallback: attempt individual deletes (will at least delete bot messages)
                for m in view.to_delete:
                    try:
                        await m.delete()
                    except (discord.Forbidden, discord.NotFound):
                        pass

            # Disable the button after attempt
            for item in view.children:
                item.disabled = True
            try:
                await interaction.message.edit(content="Pickup cleanup attempted.", view=view)
            except (discord.Forbidden, discord.NotFound):
                pass


class Fun(commands.Cog):
    """Fun Games and Entertainment"""
    
    def __init__(self, client):
        self.client = client

    @commands.command(help="View or set your NFT")
    async def nft(self, ctx, *, addition=None):
        try:
            with open("storage/nft.json", "r") as f:
                nfts = json.load(f)
        except:
            nfts = {}

        user = f"<@{ctx.author.id}>"
        if addition is not None:
            nfts[str(ctx.author.id)] = addition
            with open("storage/nft.json", "w") as f:
                json.dump(nfts, f, indent=4)
            await ctx.send(f"Your **NEW** NFT, {user}:\n{nfts[str(ctx.author.id)]}")
        else:
            if str(ctx.author.id) in nfts:
                await ctx.send(f"Your NFT, {user}:\n{nfts[str(ctx.author.id)]}")
            else:
                await ctx.send(f"You don't have an NFT. Set one with `nft <url or text>`")

    @commands.command(help="Play FizzBuzz!", aliases=['fizz', 'buzz'])
    async def fizzbuzz(self, ctx, mode=None):
        if mode == 'r':
            return await ctx.send("**FizzBuzz Rules:**\n• If divisible by 3: `Fizz`\n• If divisible by 5: `Buzz`\n• If divisible by both: `FizzBuzz`\n• Otherwise: the number")
        
        count = 1
        await ctx.send("🎮 **FizzBuzz started!** Send your answers. Type `q` to quit.")

        while True:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                msg = await self.client.wait_for("message", check=check, timeout=60)
            except:
                return await ctx.send("⏰ Time's up!")

            if msg.content.lower() == 'q':
                return await ctx.send(f"Game over! You reached **{count - 1}**")

            current = FizzBuzz(count)
            if msg.content.lower() == current.solve(count).lower():
                await msg.add_reaction('✅')
                count += 1
            else:
                await msg.add_reaction('❌')
                return await ctx.send(f"❌ Wrong! The answer was **{current.solve(count)}**. You reached **{count - 1}**")
            
    @commands.command(help="52 card pickup", hidden=True)
    async def fiftytwo(self, ctx: commands.Context, member: discord.Member = None):
        if member is None:
            await ctx.send("Please @ a person to play the game as an argument to the function")
            return

        if member.id == 239605426033786881:
            await ctx.send("Hunter would not like to play that game right now")
            return
        if member.id == 877014219499925515:
            await ctx.send("I am throwing the cards, not picking them up")
            return
        if member.id == ctx.author.id:
            await ctx.send("Who would want to play this game with themselves?")
            return

        # Create a new shuffled deck, then draw 52 cards in one request (more efficient)
        async with aiohttp.ClientSession() as session:
            async with session.get(f"{DECK_API_BASE}/new/shuffle/?deck_count=1") as r:
                deck_data = await r.json()
            deck_id = deck_data["deck_id"]

            async with session.get(f"{DECK_API_BASE}/{deck_id}/draw/?count=52") as r:
                draw_data = await r.json()

        cards = draw_data.get("cards", [])
        if len(cards) < 52:
            await ctx.send("Deck API did not return 52 cards.")
            return

        # Track messages to delete: the original command message + the 52 card messages
        messages_to_delete: list[discord.Message] = [ctx.message]

        mention = member.mention

        for c in cards:
            # API fields include: value, suit, image (png), etc. :contentReference[oaicite:2]{index=2}
            value = c.get("value", "CARD")
            suit = c.get("suit", "SUIT")
            img_url = c.get("image")

            embed = discord.Embed(title=f"{value} of {suit}")
            if img_url:
                embed.set_image(url=img_url)

            msg = await ctx.send(content=f"{mention}", embed=embed)
            messages_to_delete.append(msg)

            # Avoid hitting rate limits from 52 rapid sends
            await asyncio.sleep(0.35)

        # Button that deletes the 52 cards + the invoking message (53 total)
        view = DeletePickupView(author_id=ctx.author.id, channel=ctx.channel, to_delete=messages_to_delete)
        await ctx.send("Cleanup:", view=view)

    @commands.command(help="Get something to do when bored")
    async def bored(self, ctx):
        try:
            r = requests.get("https://www.boredapi.com/api/activity?participants=1&price=0", timeout=10)
            if r.status_code == 200:
                await ctx.send(f"**Idea:** {r.json()['activity']}")
            else:
                await ctx.send("❌ Couldn't fetch an activity. Try again!")
        except:
            await ctx.send("❌ API error. Try again!")

    @commands.command(help="Ratio a message by adding reactions")
    async def ratio(self, ctx, msg_id=None):
        if msg_id is None:
            return await ctx.send("Usage: `ratio <message_id>`\nRight-click a message → Copy ID")
        
        try:
            msg = await ctx.fetch_message(int(msg_id))
            for _ in range(min(10, len(emojis))):
                await msg.add_reaction(random.choice(emojis))
            await ctx.send("Ratio'd!")
        except:
            await ctx.send("❌ Message not found")

    @commands.command(help="Count to a number!")
    async def count(self, ctx, endpoint: int = None):
        if not endpoint or endpoint <= 0:
            return await ctx.send("Usage: `count <positive number>`")

        count = 1
        mistakes = 0
        await ctx.send(f"🔢 Count to **{endpoint}**! Type `give up` to quit.")

        while count <= endpoint:
            def check(m):
                return m.author == ctx.author and m.channel == ctx.channel

            try:
                msg = await self.client.wait_for("message", check=check, timeout=60)
            except:
                return await ctx.send("⏰ Time's up!")

            if msg.content.lower() == 'give up':
                return await ctx.send(f"😔 You gave up at **{count}**")

            if msg.content == str(count):
                await msg.add_reaction('✅')
                count += 1
            else:
                await msg.add_reaction('❌')
                mistakes += 1
                await ctx.send(f"❌ Wrong! You're on **{count}**")
                if mistakes >= 20:
                    return await ctx.send("Too many mistakes. Game over!")

        embed = discord.Embed(title="🎉 CONGRATS!", description=f"You counted to **{endpoint}**!", color=0xFFD700)
        await ctx.send(embed=embed)

    @commands.command(help="Get a random quote from 2070 Paradigm Shift")
    async def paradigm(self, ctx, number: int = 1):
        if number > 30:
            return await ctx.send("Max 30 lines!")
        
        try:
            with open("constants/paradigm.txt", "r") as f:
                lines = [l.strip() for l in f.readlines() if l.strip() and l.strip() != "\n"]
            
            for i in range(min(number, len(lines))):
                await ctx.send(f"**{i+1}:** {random.choice(lines)}")
        except:
            await ctx.send("❌ Could not load paradigm file")

    @commands.command(help="Get a facepalm GIF", aliases=["palm", "fp"])
    async def facepalm(self, ctx):
        try:
            r = requests.get("https://some-random-api.com/animu/face-palm", timeout=10)
            if r.status_code == 200:
                await ctx.send(r.json().get("link", "No GIF found"))
        except:
            await ctx.send("❌ API error")

    @commands.command(help="Tell someone to shut up")
    async def shutup(self, ctx, member: discord.Member = None):
        if member is None:
            messages = [m async for m in ctx.channel.history(limit=50)]
            for msg in messages:
                if msg.author.id != ctx.author.id and msg.author.id != self.client.user.id:
                    member = msg.author
                    break
        
        if member:
            await ctx.send(f"Shut up {member.mention}!")
        else:
            await ctx.send("No one to shut up!")

    @commands.command(help="Convert an image to emojis", aliases=["em"])
    async def emojify(self, ctx, source: Union[discord.Member, str] = None, size: int = 14):
        COLORS = {
            (0, 0, 0): "⬛",
            (0, 0, 255): "🟦",
            (255, 0, 0): "🟥",
            (255, 255, 0): "🟨",
            (255, 165, 0): "🟧",
            (255, 255, 255): "⬜",
            (0, 255, 0): "🟩",
        }

        def euclidean_distance(c1, c2):
            return sum((a - b) ** 2 for a, b in zip(c1, c2)) ** 0.5

        def find_closest_emoji(color):
            closest = min(COLORS.keys(), key=lambda c: euclidean_distance(color, c))
            return COLORS[closest]

        if source is None:
            source = ctx.author

        url = source.display_avatar.url if isinstance(source, discord.Member) else source

        try:
            r = requests.get(url, stream=True, timeout=10)
            img = Image.open(BytesIO(r.content)).convert("RGB")
            img = img.resize((size, size), Image.NEAREST)

            result = ""
            for y in range(size):
                for x in range(size):
                    result += find_closest_emoji(img.getpixel((x, y)))
                result += "\n"

            if size > 14:
                result = f"```{result}```"

            await ctx.send(result)
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(help="Roll a dice", aliases=["roll"])
    async def dice(self, ctx, sides: int = 6):
        result = random.randint(1, sides)
        await ctx.send(f"You rolled a **{result}** (d{sides})")

    @commands.command(help="Flip a coin")
    async def coinflip(self, ctx):
        result = random.choice(["Heads", "Tails"])
        emoji = "🪙"
        await ctx.send(f"{emoji} **{result}!**")

    @commands.command(help="8ball - Ask a question!")
    async def eightball(self, ctx, *, question: str = None):
        if not question:
            return await ctx.send("Usage: `8ball <question>`")
        
        responses = [
            "It is certain.", "It is decidedly so.", "Without a doubt.",
            "Yes – definitely.", "You may rely on it.", "As I see it, yes.",
            "Most likely.", "Outlook good.", "Yes.", "Signs point to yes.",
            "Reply hazy, try again.", "Ask again later.", "Better not tell you now.",
            "Cannot predict now.", "Concentrate and ask again.",
            "Don't count on it.", "My reply is no.", "My sources say no.",
            "Outlook not so good.", "Very doubtful."
        ]
        
        embed = discord.Embed(title="🎱 Magic 8-Ball", color=0x000000)
        embed.add_field(name="Question", value=question, inline=False)
        embed.add_field(name="Answer", value=random.choice(responses), inline=False)
        await ctx.send(embed=embed)






async def setup(client):
    await client.add_cog(Fun(client))