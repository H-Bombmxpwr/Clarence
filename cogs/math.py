# cogs/math.py
import asyncio
from io import BytesIO
from typing import Literal

import discord
from discord import app_commands
from discord.ext import commands
from matplotlib.figure import Figure

from functionality.functions import collatz
from functionality.structures import Bits


def render_latex(expr: str) -> BytesIO:
    # Figure (not pyplot) is safe to use from a worker thread
    fig = Figure(figsize=(10, 2))
    fig.text(0.5, 0.5, f"${expr}$", fontsize=30, color="black", ha="center", va="center")
    buf = BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight", pad_inches=0.1, facecolor="white")
    buf.seek(0)
    return buf


class Math(commands.Cog):
    """🧮 Math"""

    def __init__(self, client):
        self.client = client

    @app_commands.command(description=r"Render LaTeX, e.g. \frac{1}{2}")
    async def latex(self, interaction: discord.Interaction, expression: str):
        await interaction.response.defer()
        try:
            buf = await asyncio.to_thread(render_latex, expression)
            await interaction.followup.send(file=discord.File(buf, filename="latex.png"))
        except Exception as e:
            await interaction.followup.send(f"❌ Couldn't render that: `{str(e).splitlines()[0][:200]}`")

    @app_commands.command(description="Convert between binary, hex, decimal and ASCII")
    @app_commands.describe(kind="What kind of value you're giving", value="The value to convert, e.g. 35, 0x23, 100011, #")
    async def bits(self, interaction: discord.Interaction, kind: Literal["decimal", "hex", "binary", "ascii"], value: str):
        bit = Bits(kind, value)
        decimal = bit.to_decimal(kind[0], value.removeprefix("0x").removeprefix("0b") if kind != "ascii" else value)
        if decimal is None:
            return await interaction.response.send_message("❌ Invalid value for that type", ephemeral=True)
        decimal, ascii_val, hexa, binary = bit.from_decimal(decimal)
        embed = discord.Embed(title="🔢 Number Conversion", color=0x3498db)
        embed.add_field(name="Binary", value=f"`{binary}`", inline=True)
        embed.add_field(name="Hex", value=f"`{hexa}`", inline=True)
        embed.add_field(name="Decimal", value=f"`{decimal}`", inline=True)
        embed.add_field(name="ASCII", value=f"`{ascii_val}`", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Run the Collatz conjecture on a number")
    async def collatz(self, interaction: discord.Interaction, number: app_commands.Range[int, 1, 10 ** 15]):
        steps = await asyncio.to_thread(collatz, number)
        await interaction.response.send_message(f"**Collatz Conjecture**\nStarting number: `{number}`\nSteps to reach 1: `{steps}`")


async def setup(client):
    await client.add_cog(Math(client))
