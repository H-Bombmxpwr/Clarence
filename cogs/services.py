# cogs/services.py
import discord
from discord.ext import commands
import os
import functionality.functions as funcs
import requests
import xkcd
from typing import Optional
from datetime import date
from urllib.parse import quote
from pyfiglet import Figlet
import random
import wikipedia
from discord.ui import Button, View
from contextlib import suppress


class Misc(commands.Cog, name="Misc"):
    """🔧 Local Utility Commands"""
    
    def __init__(self, client):
        self.client = client

    @commands.command(help="Say hello!", aliases=["hi", "hey", "sup"])
    async def hello(self, ctx):
        responses = ["Hi!", "Hello!", "What's up!", "Hey!", "Sup!", "Big Chillin!", "Hey Hey Hey", "Let's Go!"]
        await ctx.send(f"{random.choice(responses)} {ctx.author.mention}")

    @commands.command(help="Generate ASCII art from text", aliases=["figlet"])
    @commands.cooldown(1, 3, commands.BucketType.user)
    async def ascii(self, ctx, *, text: str):
        if len(text) > 16:
            return await ctx.send("❌ Text too long (max 16 characters)")
        
        ascii_text = Figlet(font="small").renderText(text)
        await ctx.send(f"```\n{ascii_text}\n```")

    @commands.command(help="Ping/annoy a user multiple times", aliases=["annoy"])
    async def bug(self, ctx, member: discord.Member, times: int, *, message: str = "we need you"):
        if times > 30:
            return await ctx.send("❌ Max 30 pings!")
        if member.id == self.client.user.id:
            return await ctx.send("❌ I'm not gonna bug myself!")
        
        for i in range(1, times + 1):
            await ctx.send(f"Hey {member.mention} {message}, {i}!")

    @commands.command(help="Get info about a user")
    async def userinfo(self, ctx, target: Optional[discord.Member] = None):
        target = target or ctx.author

        embed = discord.Embed(title="👤 User Information", color=target.color)
        embed.set_thumbnail(url=target.display_avatar.url)
        
        embed.add_field(name="Name", value=str(target), inline=True)
        embed.add_field(name="ID", value=target.id, inline=True)
        embed.add_field(name="Bot?", value="Yes" if target.bot else "No", inline=True)
        embed.add_field(name="Top Role", value=target.top_role.mention, inline=True)
        embed.add_field(name="Status", value=str(target.status).title(), inline=True)
        
        activity = "N/A"
        if target.activity:
            activity = f"{target.activity.type.name.title()}: {target.activity.name}"
        embed.add_field(name="Activity", value=activity, inline=True)
        
        embed.add_field(name="Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Joined", value=f"<t:{int(target.joined_at.timestamp())}:R>", inline=True)

        await ctx.send(embed=embed)


class Api(commands.Cog, name="Api"):
    """API-powered Commands"""
    
    def __init__(self, client):
        self.client = client

    @commands.command(help="Generate AI art (if configured)")
    async def ai(self, ctx, *, query: str = None):
        if not query:
            return await ctx.send("Usage: `ai <description>`")
        
        api_key = os.getenv('ai')
        if not api_key:
            return await ctx.send("❌ AI generation not configured")
        
        async with ctx.typing():
            try:
                r = requests.post(
                    "https://api.deepai.org/api/text2img",
                    data={'text': query},
                    headers={'api-key': api_key},
                    timeout=30
                )
                data = r.json()
                if 'output_url' in data:
                    embed = discord.Embed(title="AI Generation", description=f"Prompt: {query}", color=0xFFFF00)
                    embed.set_image(url=data['output_url'])
                    await ctx.send(embed=embed)
                else:
                    await ctx.send("❌ Generation failed")
            except Exception as e:
                await ctx.send(f"❌ Error: {e}")

    @commands.command(help="Search Wikipedia", aliases=["wiki", "w"])
    async def wikipedia(self, ctx, *, query: str = None):
        if not query:
            return await ctx.send("Usage: `wikipedia <query>`")
        
        async with ctx.typing():
            try:
                suggestion = wikipedia.suggest(query)
                if suggestion:
                    query = suggestion
                
                page = wikipedia.page(query)
                summary = wikipedia.summary(query, sentences=3)
                
                embed = discord.Embed(
                    title=page.title,
                    description=summary,
                    color=0xC0C0C0
                )
                if page.images:
                    embed.set_image(url=page.images[0])
                
                view = View()
                view.add_item(Button(label="Read More", url=page.url))
                
                await ctx.send(embed=embed, view=view)
            except wikipedia.exceptions.DisambiguationError as e:
                options = "\n".join(e.options[:5])
                await ctx.send(f"❓ Multiple results found:\n{options}\n\nBe more specific!")
            except Exception as e:
                await ctx.send(f"❌ Error: {e}")

    @commands.command(help="Get an insult", aliases=['i'])
    async def insult(self, ctx, member: discord.Member = None):
        try:
            quote = funcs.get_insult()
            if member:
                await ctx.send(f"{member.mention}, {quote}")
            else:
                await ctx.send(quote)
        except:
            await ctx.send("❌ Insult API is down")

    @commands.command(help="Get a compliment", aliases=['c'])
    async def compliment(self, ctx, member: discord.Member = None):
        try:
            quote = funcs.get_compliment()
            if member:
                await ctx.send(f"{member.mention}, {quote}")
            else:
                await ctx.send(quote)
        except:
            await ctx.send("❌ Compliment API is down")

    @commands.command(help="Get a pickup line", aliases=['p'])
    async def pickup(self, ctx, member: discord.Member = None):
        try:
            quote = funcs.get_pickup()
            target = f"Hey {member.mention}, " if member else ""
            await ctx.send(f"💕 {target}{quote}")
        except:
            await ctx.send("❌ Pickup line API is down")

    @commands.command(help="Get a joke", aliases=['j'])
    async def joke(self, ctx):
        try:
            joke = funcs.get_joke()
            embed = discord.Embed(
                title=f"{joke['category']} Joke",
                description=f"{joke['setup']}\n\n||{joke['delivery']}||",
                color=0xffa500
            )
            await ctx.send(embed=embed)
        except:
            await ctx.send("❌ Joke API is down")

    @commands.command(help="Get latest/random xkcd comic")
    async def xkcd(self, ctx, mode: str = "latest"):
        try:
            if mode.lower() == "random":
                comic = xkcd.getRandomComic()
            else:
                comic = xkcd.getLatestComic()
            
            embed = discord.Embed(
                title=f"xkcd #{comic.number}: {comic.title}",
                url=comic.link,
                color=0x40e0d0
            )
            embed.set_image(url=comic.getImageLink())
            embed.set_footer(text=comic.getAltText())
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(help="Get a random animal image", aliases=["an"])
    async def animal(self, ctx, animal: str = None):
        animals = ["dog", "cat", "panda", "fox", "bird", "koala", "red_panda", "raccoon", "kangaroo"]
        
        if not animal:
            embed = discord.Embed(title="🐾 Available Animals", description="\n".join(animals), color=0x088f8f)
            return await ctx.send(embed=embed)
        
        if animal.lower() in ["red", "redpanda"]:
            animal = "red_panda"
        
        try:
            r = requests.get(f"https://some-random-api.com/animal/{animal}", timeout=10)
            if r.status_code == 200:
                data = r.json()
                embed = discord.Embed(title=f"🐾 {animal.title()}", color=0x088f8f)
                embed.set_image(url=data["image"])
                if "fact" in data:
                    embed.add_field(name="Fun Fact", value=data["fact"][:500])
                await ctx.send(embed=embed)
            else:
                await ctx.send(f"❌ Unknown animal: {animal}")
        except:
            await ctx.send("❌ API error")

    @commands.command(help="Search for GIFs")
    async def gif(self, ctx, *, query: str):
        tenor_key = os.getenv('TENORKEY')
        if not tenor_key:
            return await ctx.send("❌ GIF search not configured")
        
        async with ctx.typing():
            try:
                r = requests.get(
                    f"https://g.tenor.com/v1/search?q={quote(query)}&contentfilter=medium&key={tenor_key}",
                    timeout=10
                )
                data = r.json()
                if data.get("results"):
                    await ctx.send(data["results"][0]["url"])
                else:
                    await ctx.send("❌ No GIFs found")
            except:
                await ctx.send("❌ GIF search failed")

    @commands.command(help="Flip a coin")
    async def coin(self, ctx):
        result = random.choice(["Heads", "Tails"])
        await ctx.send(f"🪙 **{result}!**")


async def setup(client):
    await client.add_cog(Misc(client))
    await client.add_cog(Api(client))