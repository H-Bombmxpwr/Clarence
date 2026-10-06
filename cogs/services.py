# cogs/services.py
import asyncio
import os
import random
from typing import Literal, Optional
from urllib.parse import quote

import discord
import wikipedia
import xkcd
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View
from pyfiglet import Figlet

import functionality.functions as funcs

COMPLIMENTS = [
    "You light up every room you walk into.", "Your sense of humor is elite.", "You're more fun than bubble wrap.",
    "You have impeccable taste.", "You're the human version of a perfectly ripe avocado.",
    "Talking to you is the best part of my day.", "You'd survive a horror movie for sure.",
    "You're even better than a unicorn, because you're real.", "Your playlist is probably fantastic.",
    "You make bad days better.", "You're one of a kind — the good kind.", "You have main character energy.",
]


def user_info_embed(target: discord.Member | discord.User) -> discord.Embed:
    embed = discord.Embed(title="User Information", color=getattr(target, "color", None) or 0x3498db)
    embed.set_thumbnail(url=target.display_avatar.url)
    embed.add_field(name="Name", value=str(target), inline=True)
    embed.add_field(name="ID", value=target.id, inline=True)
    embed.add_field(name="Bot?", value="Yes" if target.bot else "No", inline=True)
    embed.add_field(name="Created", value=f"<t:{int(target.created_at.timestamp())}:R>", inline=True)
    if isinstance(target, discord.Member):
        embed.add_field(name="Joined", value=f"<t:{int(target.joined_at.timestamp())}:R>" if target.joined_at else "?", inline=True)
        embed.add_field(name="Top Role", value=target.top_role.mention, inline=True)
        if target.activity:  # only known when the presences intent is on (it's off to save memory/CPU)
            embed.add_field(name="Activity", value=f"{target.activity.type.name.title()}: {target.activity.name}", inline=True)
        roles = [r.mention for r in reversed(target.roles[1:])]
        if roles:
            embed.add_field(name=f"Roles ({len(roles)})", value=" ".join(roles)[:1024], inline=False)
    return embed


class Misc(commands.Cog, name="Misc"):
    """Local Utility Commands"""

    def __init__(self, client):
        self.client = client
        self.ctx_userinfo = app_commands.ContextMenu(name="User Info", callback=self.userinfo_context)

    async def cog_load(self):
        self.client.tree.add_command(self.ctx_userinfo)

    async def cog_unload(self):
        self.client.tree.remove_command(self.ctx_userinfo.name, type=self.ctx_userinfo.type)

    @app_commands.command(description="Say hello!")
    async def hello(self, interaction: discord.Interaction):
        responses = ["Hi!", "Hello!", "What's up!", "Hey!", "Sup!", "Big Chillin!", "Hey Hey Hey", "Let's Go!"]
        await interaction.response.send_message(f"{random.choice(responses)} {interaction.user.mention}")

    @app_commands.command(description="Generate ASCII art from text")
    @app_commands.checks.cooldown(1, 3)
    async def ascii(self, interaction: discord.Interaction, text: app_commands.Range[str, 1, 16]):
        ascii_text = Figlet(font="small").renderText(text)
        await interaction.response.send_message(f"```\n{ascii_text}\n```")

    @app_commands.command(description="Ping/annoy a user multiple times")
    @app_commands.guild_only()
    async def bug(self, interaction: discord.Interaction, member: discord.Member, times: app_commands.Range[int, 1, 30],
                  message: str = "we need you"):
        if member.id == self.client.user.id:
            return await interaction.response.send_message("I'm not gonna bug myself!", ephemeral=True)
        await interaction.response.send_message(f"Hey {member.mention} {message}, 1!")
        for i in range(2, times + 1):
            await interaction.channel.send(f"Hey {member.mention} {message}, {i}!")

    @app_commands.command(description="Get info about a user")
    async def userinfo(self, interaction: discord.Interaction, target: Optional[discord.User] = None):
        await interaction.response.send_message(embed=user_info_embed(target or interaction.user))

    async def userinfo_context(self, interaction: discord.Interaction, member: discord.User):
        await interaction.response.send_message(embed=user_info_embed(member), ephemeral=True)

    @app_commands.command(description="Check the bot's latency")
    async def ping(self, interaction: discord.Interaction):
        await interaction.response.send_message(f"Pong! `{round(self.client.latency * 1000)}ms`")


class Api(commands.Cog, name="Api"):
    """API-powered Commands"""

    def __init__(self, client):
        self.client = client

    @property
    def session(self):
        return self.client.session

    @app_commands.command(description="Generate AI art (if configured)")
    async def ai(self, interaction: discord.Interaction, prompt: str):
        api_key = os.getenv('ai')
        if not api_key:
            return await interaction.response.send_message("AI generation not configured", ephemeral=True)
        await interaction.response.defer()
        try:
            async with self.session.post("https://api.deepai.org/api/text2img", data={'text': prompt},
                                         headers={'api-key': api_key}, timeout=60) as r:
                data = await r.json(content_type=None)
            if 'output_url' in data:
                embed = discord.Embed(title="AI Generation", description=f"Prompt: {prompt}", color=0xFFFF00)
                embed.set_image(url=data['output_url'])
                await interaction.followup.send(embed=embed)
            else:
                await interaction.followup.send("Generation failed")
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(description="Search Wikipedia")
    async def wikipedia(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()

        def lookup():
            page = wikipedia.page(query, auto_suggest=True)
            return page, wikipedia.summary(page.title, sentences=3, auto_suggest=False)

        try:
            page, summary = await asyncio.to_thread(lookup)
            embed = discord.Embed(title=page.title, url=page.url, description=summary, color=0xC0C0C0)
            images = [i for i in page.images if i.lower().endswith((".jpg", ".jpeg", ".png"))]
            if images:
                embed.set_thumbnail(url=images[0])
            view = View()
            view.add_item(Button(label="Read More", url=page.url))
            await interaction.followup.send(embed=embed, view=view)
        except wikipedia.exceptions.DisambiguationError as e:
            options = "\n".join(f"• {o}" for o in e.options[:8])
            await interaction.followup.send(f"**{query}** could mean:\n{options}\n\nBe more specific!")
        except wikipedia.exceptions.PageError:
            await interaction.followup.send(f"No Wikipedia page found for **{query}**.")
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(description="Get an insult")
    async def insult(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        try:
            quote_ = await asyncio.to_thread(funcs.get_insult)
        except Exception:
            return await interaction.response.send_message("Insult API is down", ephemeral=True)
        await interaction.response.send_message(f"{member.mention}, {quote_}" if member else quote_)

    @app_commands.command(description="Give someone a compliment")
    async def compliment(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        text = random.choice(COMPLIMENTS)
        await interaction.response.send_message(f"{member.mention}, {text}" if member else text)

    @app_commands.command(description="Get a pickup line")
    async def pickup(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        try:
            async with self.session.get("https://rizzapi.vercel.app/random", timeout=10) as r:
                line = (await r.json(content_type=None))["text"]
        except Exception:
            return await interaction.response.send_message("Pickup line API is down", ephemeral=True)
        target = f"Hey {member.mention}, " if member else ""
        await interaction.response.send_message(f"{target}{line}")

    @app_commands.command(description="Get a joke")
    async def joke(self, interaction: discord.Interaction):
        try:
            async with self.session.get("https://v2.jokeapi.dev/joke/Any?type=twopart", timeout=10) as r:
                joke = await r.json(content_type=None)
            embed = discord.Embed(title=f"{joke['category']} Joke",
                                  description=f"{joke['setup']}\n\n||{joke['delivery']}||", color=0xffa500)
            await interaction.response.send_message(embed=embed)
        except Exception:
            await interaction.response.send_message("Joke API is down", ephemeral=True)

    @app_commands.command(description="Get the latest or a random xkcd comic")
    async def xkcd(self, interaction: discord.Interaction, mode: Literal["latest", "random"] = "latest"):
        await interaction.response.defer()
        try:
            comic = await asyncio.to_thread(xkcd.getRandomComic if mode == "random" else xkcd.getLatestComic)
            embed = discord.Embed(title=f"xkcd #{comic.number}: {comic.title}", url=comic.link, color=0x40e0d0)
            embed.set_image(url=comic.getImageLink())
            embed.set_footer(text=comic.getAltText())
            await interaction.followup.send(embed=embed)
        except Exception as e:
            await interaction.followup.send(f"Error: {e}")

    @app_commands.command(description="Get a random animal picture")
    async def animal(self, interaction: discord.Interaction, animal: Literal["dog", "cat", "fox", "duck"] = "dog"):
        urls = {
            "dog": ("https://dog.ceo/api/breeds/image/random", lambda d: d["message"]),
            "cat": ("https://api.thecatapi.com/v1/images/search", lambda d: d[0]["url"]),
            "fox": ("https://randomfox.ca/floof/", lambda d: d["image"]),
            "duck": ("https://random-d.uk/api/v2/random", lambda d: d["url"].replace("http://", "https://")),
        }
        url, pick = urls[animal]
        try:
            async with self.session.get(url, timeout=10) as r:
                image = pick(await r.json(content_type=None))
        except Exception:
            return await interaction.response.send_message("Animal API error", ephemeral=True)
        embed = discord.Embed(title=f"{animal.title()}", color=0x088f8f)
        embed.set_image(url=image)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Search for a GIF")
    async def gif(self, interaction: discord.Interaction, query: str):
        tenor_key = os.getenv('TENORKEY')
        if not tenor_key:
            return await interaction.response.send_message("GIF search not configured", ephemeral=True)
        try:
            async with self.session.get(f"https://tenor.googleapis.com/v2/search?q={quote(query)}&key={tenor_key}&limit=1&contentfilter=medium",
                                        timeout=10) as r:
                data = await r.json(content_type=None)
            if data.get("results"):
                await interaction.response.send_message(data["results"][0]["url"])
            else:
                await interaction.response.send_message("No GIFs found", ephemeral=True)
        except Exception:
            await interaction.response.send_message("GIF search failed", ephemeral=True)


async def setup(client):
    await client.add_cog(Misc(client))
    await client.add_cog(Api(client))
