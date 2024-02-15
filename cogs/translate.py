import discord
from discord.ext import commands
from googletrans import Translator, LANGUAGES

class Translation(commands.Cog, name="Translation Commands"):
    def __init__(self, client):
        self.client = client
        self.translator = Translator()
    
    @commands.command(name="translate", aliases=["trans"], help="Translates text to a specified language. Auto Detects the language you send")
    async def translate(self, ctx, language_to, *, text_to_translate):
        # Check if the desired language is supported
        if language_to not in LANGUAGES.values():
            await ctx.send(f"Sorry, I do not support the language '{language_to}'.")
            return
        
        # Attempt to translate the text
        try:
            result = self.translator.translate(text_to_translate, dest=language_to)
            embed = discord.Embed(title="Translation", color=0x00ff00)
            embed.add_field(name=f"Translated to {LANGUAGES[result.dest].capitalize()}", value=result.text, inline=False)
            embed.set_footer(text=f"Detected language: {LANGUAGES[result.src].capitalize()}")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred while translating: {e}")

async def setup(client):
    await client.add_cog(Translation(client))
