# cogs/translate.py
import asyncio
from typing import Dict, Optional

import discord
from discord import app_commands
from discord.ext import commands
from googletrans import LANGUAGES, Translator

from functionality.ui import Paginator, chunk_lines

# Flag emoji to language code mapping
FLAG_LANG_MAP: Dict[str, str] = {
    "🇺🇸": "en", "🇬🇧": "en",
    "🇩🇪": "de",
    "🇫🇷": "fr",
    "🇪🇸": "es", "🇲🇽": "es",
    "🇮🇹": "it",
    "🇵🇹": "pt", "🇧🇷": "pt",
    "🇷🇺": "ru",
    "🇨🇳": "zh-cn", "🇹🇼": "zh-tw",
    "🇯🇵": "ja",
    "🇰🇷": "ko",
    "🇸🇦": "ar", "🇦🇪": "ar",
    "🇮🇳": "hi",
    "🇳🇱": "nl",
    "🇵🇱": "pl",
    "🇹🇷": "tr",
    "🇻🇳": "vi",
    "🇹🇭": "th",
    "🇮🇩": "id",
    "🇬🇷": "el",
    "🇨🇿": "cs",
    "🇷🇴": "ro",
    "🇭🇺": "hu",
    "🇸🇪": "sv",
    "🇩🇰": "da",
    "🇳🇴": "no",
    "🇫🇮": "fi",
    "🇺🇦": "uk",
    "🇮🇱": "he",
    "🇮🇪": "ga",
    "🇵🇭": "tl",
    "🇿🇦": "af",
}


def language_name(code: str) -> str:
    code = code.lower()
    return LANGUAGES[code].title() if code in LANGUAGES else code.upper()


def resolve_language(text: str) -> Optional[str]:
    """Accept a code ('es') or a name ('spanish', 'span')."""
    q = text.lower().strip()
    if q in LANGUAGES:
        return q
    for code, name in LANGUAGES.items():
        if name == q:
            return code
    return next((code for code, name in LANGUAGES.items() if q in name), None)


class Translation(commands.Cog, name="Translation"):
    """🌐 Translate text — or react to a message with a flag!"""

    def __init__(self, client):
        self.client = client
        self.translator = Translator()
        self._translated_cache: Dict[tuple, str] = {}
        self.ctx_translate = app_commands.ContextMenu(name="Translate to English", callback=self.translate_context)

    async def cog_load(self):
        self.client.tree.add_command(self.ctx_translate)

    async def cog_unload(self):
        self.client.tree.remove_command(self.ctx_translate.name, type=self.ctx_translate.type)

    async def _translate_text(self, text: str, dest: str, src: str = 'auto') -> Optional[dict]:
        try:
            result = await asyncio.to_thread(self.translator.translate, text, dest=dest, src=src)
            return {'text': result.text, 'src': result.src, 'dest': result.dest,
                    'src_name': language_name(result.src), 'dest_name': language_name(result.dest)}
        except Exception as e:
            print(f"Translation error: {e}")
            return None

    def _embed(self, original: str, result: dict, footer: str) -> discord.Embed:
        embed = discord.Embed(title="🌐 Translation", color=0x3498db)
        embed.add_field(name=f"Original ({result['src_name']})", value=original[:1024], inline=False)
        embed.add_field(name=f"Translated ({result['dest_name']})", value=result['text'][:1024], inline=False)
        embed.set_footer(text=footer)
        return embed

    async def language_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        q = current.lower()
        matches = [(code, name) for code, name in LANGUAGES.items() if q in name or q == code]
        return [app_commands.Choice(name=f"{name.title()} ({code})", value=code) for code, name in matches[:25]]

    @app_commands.command(description="Translate text to another language")
    @app_commands.describe(language="Target language", text="Text to translate")
    @app_commands.autocomplete(language=language_autocomplete)
    async def translate(self, interaction: discord.Interaction, language: str, text: str):
        code = resolve_language(language)
        if not code:
            return await interaction.response.send_message(f"❌ Unknown language: `{language}`. See `/languages`.", ephemeral=True)
        await interaction.response.defer()
        result = await self._translate_text(text, code)
        if result is None:
            return await interaction.followup.send("❌ Translation failed. Please try again.")
        await interaction.followup.send(embed=self._embed(text, result, f"Requested by {interaction.user.display_name}"))

    async def translate_context(self, interaction: discord.Interaction, message: discord.Message):
        if not message.content:
            return await interaction.response.send_message("That message has no text.", ephemeral=True)
        await interaction.response.defer(ephemeral=True)
        result = await self._translate_text(message.content, "en")
        if result is None:
            return await interaction.followup.send("❌ Translation failed.", ephemeral=True)
        await interaction.followup.send(embed=self._embed(message.content, result, f"Message from {message.author.display_name}"),
                                        ephemeral=True)

    @app_commands.command(description="List all supported languages")
    async def languages(self, interaction: discord.Interaction):
        lines = [f"`{code}` — {name.title()}" for code, name in sorted(LANGUAGES.items(), key=lambda x: x[1])]
        pages = [discord.Embed(title="🌐 Supported Languages", description=c, color=0x3498db)
                 .set_footer(text=f"{len(LANGUAGES)} languages") for c in chunk_lines(lines, 900)]
        await Paginator(pages, interaction.user.id).send(interaction, ephemeral=True)

    @app_commands.command(description="Detect the language of some text")
    async def detect(self, interaction: discord.Interaction, text: str):
        try:
            detected = await asyncio.to_thread(self.translator.detect, text)
        except Exception as e:
            return await interaction.response.send_message(f"❌ Detection failed: {e}", ephemeral=True)
        lang = detected.lang if isinstance(detected.lang, str) else detected.lang[0]
        embed = discord.Embed(title="🔍 Language Detection", color=0x3498db)
        embed.add_field(name="Text", value=text[:500], inline=False)
        embed.add_field(name="Detected Language", value=f"{language_name(lang)} (`{lang}`)", inline=True)
        confidence = detected.confidence if isinstance(detected.confidence, (int, float)) else None
        if confidence:
            embed.add_field(name="Confidence", value=f"{confidence:.1%}", inline=True)
        await interaction.response.send_message(embed=embed)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Translate a message when someone reacts with a flag emoji."""
        if payload.user_id == self.client.user.id:
            return
        emoji_str = str(payload.emoji)
        if emoji_str not in FLAG_LANG_MAP:
            return
        try:
            channel = self.client.get_channel(payload.channel_id) or await self.client.fetch_channel(payload.channel_id)
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return
        if not message.content or message.author.bot:
            return

        target_lang = FLAG_LANG_MAP[emoji_str]
        cache_key = (message.id, target_lang)
        if cache_key in self._translated_cache:
            return
        result = await self._translate_text(message.content, target_lang)
        if result is None or result['src'].lower() == result['dest'].lower():
            return
        self._translated_cache[cache_key] = result['text']
        if len(self._translated_cache) > 100:
            for key in list(self._translated_cache)[:20]:
                del self._translated_cache[key]

        embed = self._embed(message.content, result, f"Translating message from {message.author.display_name}")
        embed.title = f"Translation to {result['dest_name']}"
        try:
            await channel.send(embed=embed, reference=message, mention_author=False)
        except Exception:
            await channel.send(embed=embed)


async def setup(client):
    await client.add_cog(Translation(client))
