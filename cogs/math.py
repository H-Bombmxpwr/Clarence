# cogs/math.py
import discord
from discord.ext import commands
import matplotlib.pyplot as plt
import os
import uuid
from functionality.structures import Bits
from functionality.functions import collatz


class Math(commands.Cog):
    """Math"""
    
    def __init__(self, client):
        self.client = client

    @commands.command(help="Render LaTeX. Example: latex \\frac{1}{2}", aliases=["tex"])
    async def latex(self, ctx, *, latex_string=None):
        if latex_string is None:
            return await ctx.send("Usage: `latex <expression>`\nExample: `latex \\frac{1}{2}`")

        png_path = f"{uuid.uuid4()}.png"

        try:
            plt.figure(figsize=(10, 2))
            plt.axis('off')
            plt.text(0.5, 0.5, r"$%s$" % latex_string, fontsize=30, color="black", ha='center', va='center')
            plt.savefig(png_path, format="png", bbox_inches='tight', pad_inches=0.1, facecolor='white')
            plt.clf()
            plt.close()

            await ctx.send(file=discord.File(png_path))
        except Exception as e:
            await ctx.send(f"Error: {e}")
        finally:
            if os.path.exists(png_path):
                os.remove(png_path)

    @commands.command(help="Convert binary/hex/decimal/ascii. Example: bits decimal 35")
    async def bits(self, ctx, typ: str = None, input_val = None):
        if typ is None:
            return await ctx.send("Usage: `bits <type> <value>`\nTypes: `ascii`, `decimal`, `hex`, `binary`\nExample: `bits decimal 35`")
        if input_val is None:
            return await ctx.send("Please add a value to convert\nExample: `bits decimal 35`")

        bit = Bits(typ, input_val)
        decimal = bit.to_decimal(typ[0].lower(), input_val)
        if decimal is None:
            return await ctx.send("Invalid value for that type")
        
        decimal, ascii_val, hexa, binary = bit.from_decimal(decimal)
        
        embed = discord.Embed(title="🔢 Number Conversion", color=0x3498db)
        embed.add_field(name="Binary", value=f"`{binary}`", inline=True)
        embed.add_field(name="Hex", value=f"`{hexa}`", inline=True)
        embed.add_field(name="Decimal", value=f"`{decimal}`", inline=True)
        embed.add_field(name="ASCII", value=f"`{ascii_val}`", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(help="Run the Collatz Conjecture. Example: collatz 27")
    async def collatz(self, ctx, num: int = None):
        if num is None:
            return await ctx.send("Usage: `collatz <positive integer>`")
        try:
            c = collatz(num)
            await ctx.send(f"**Collatz Conjecture**\nStarting number: `{num}`\nSteps to reach 1: `{c}`")
        except:
            await ctx.send("Please provide a positive integer")


async def setup(client):
    await client.add_cog(Math(client))