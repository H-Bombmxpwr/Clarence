# cogs/translate.py
import discord
from discord.ext import commands
from googletrans import Translator, LANGUAGES
from typing import Dict, Optional
import asyncio

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

# Reverse map for language name lookup
LANG_NAMES = {v: k for k, v in LANGUAGES.items()}


class Translation(commands.Cog, name="Translation"):
    """Translation commands - translate text or react with flags!"""

    def __init__(self, client):
        self.client = client
        self.translator = Translator()
        # Cache of recently translated messages to avoid duplicates
        self._translated_cache: Dict[tuple, str] = {}

    def _get_language_name(self, code: str) -> str:
        """Get full language name from code"""
        code = code.lower()
        if code in LANGUAGES:
            return LANGUAGES[code].capitalize()
        return code.upper()

    async def _translate_text(self, text: str, dest: str, src: str = 'auto') -> Optional[dict]:
        """Translate text and return result dict"""
        try:
            result = self.translator.translate(text, dest=dest, src=src)
            return {
                'text': result.text,
                'src': result.src,
                'dest': result.dest,
                'src_name': self._get_language_name(result.src),
                'dest_name': self._get_language_name(result.dest)
            }
        except Exception as e:
            print(f"Translation error: {e}")
            return None

    @commands.command(name="translate", aliases=["trans", "tr"])
    async def translate(self, ctx, language_to: str, *, text_to_translate: str):
        """
        Translate text to a specified language.
        
        Usage: translate <language> <text>
        Example: translate spanish Hello, how are you?
        Example: translate ja Good morning!
        
        You can use language names (spanish, french) or codes (es, fr, ja)
        """
        # Resolve language code
        lang_code = language_to.lower()
        
        # Check if it's a language name
        if lang_code in LANGUAGES.values():
            # It's already a valid name, find the code
            for code, name in LANGUAGES.items():
                if name == lang_code:
                    lang_code = code
                    break
        elif lang_code not in LANGUAGES:
            # Try to find by partial match
            matches = [code for code, name in LANGUAGES.items() if lang_code in name.lower()]
            if matches:
                lang_code = matches[0]
            else:
                await ctx.send(f"❌ Unknown language: `{language_to}`\nUse `languages` to see available languages.")
                return

        async with ctx.typing():
            result = await self._translate_text(text_to_translate, lang_code)

        if result is None:
            await ctx.send("❌ Translation failed. Please try again.")
            return

        embed = discord.Embed(
            title="🌐 Translation",
            color=0x3498db
        )
        embed.add_field(
            name=f"Original ({result['src_name']})",
            value=text_to_translate[:1024],
            inline=False
        )
        embed.add_field(
            name=f"Translated ({result['dest_name']})",
            value=result['text'][:1024],
            inline=False
        )
        embed.set_footer(text=f"Requested by {ctx.author.display_name}")
        
        await ctx.send(embed=embed)

    @commands.command(name="languages", aliases=["langs"])
    async def list_languages(self, ctx):
        """List all supported languages for translation"""
        # Group languages alphabetically
        lang_list = sorted(LANGUAGES.items(), key=lambda x: x[1])
        
        # Create pages
        per_page = 30
        pages = []
        for i in range(0, len(lang_list), per_page):
            chunk = lang_list[i:i + per_page]
            text = "\n".join([f"`{code}` - {name.capitalize()}" for code, name in chunk])
            pages.append(text)

        # Send first page
        embed = discord.Embed(
            title="🌐 Supported Languages",
            description=pages[0],
            color=0x3498db
        )
        embed.set_footer(text=f"Page 1/{len(pages)} • {len(LANGUAGES)} languages")
        
        if len(pages) == 1:
            await ctx.send(embed=embed)
            return

        # Pagination
        current_page = 0
        msg = await ctx.send(embed=embed)
        await msg.add_reaction("◀️")
        await msg.add_reaction("▶️")

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["◀️", "▶️"] and reaction.message.id == msg.id

        while True:
            try:
                reaction, user = await self.client.wait_for("reaction_add", timeout=60, check=check)
                
                if str(reaction.emoji) == "▶️":
                    current_page = (current_page + 1) % len(pages)
                else:
                    current_page = (current_page - 1) % len(pages)

                embed.description = pages[current_page]
                embed.set_footer(text=f"Page {current_page + 1}/{len(pages)} • {len(LANGUAGES)} languages")
                await msg.edit(embed=embed)
                
                try:
                    await msg.remove_reaction(reaction, user)
                except:
                    pass

            except asyncio.TimeoutError:
                try:
                    await msg.clear_reactions()
                except:
                    pass
                break

    @commands.command(name="detect")
    async def detect_language(self, ctx, *, text: str):
        """Detect the language of text"""
        try:
            detected = self.translator.detect(text)
            lang_name = self._get_language_name(detected.lang)
            confidence = detected.confidence if hasattr(detected, 'confidence') and detected.confidence else "N/A"
            
            embed = discord.Embed(
                title="🔍 Language Detection",
                color=0x3498db
            )
            embed.add_field(name="Text", value=text[:500], inline=False)
            embed.add_field(name="Detected Language", value=f"{lang_name} (`{detected.lang}`)", inline=True)
            if confidence != "N/A":
                embed.add_field(name="Confidence", value=f"{confidence:.1%}", inline=True)
            
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"❌ Detection failed: {e}")

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        """Translate messages when flag emoji is added"""
        # Ignore bot reactions
        if payload.user_id == self.client.user.id:
            return

        # Check if it's a flag emoji we support
        emoji_str = str(payload.emoji)
        if emoji_str not in FLAG_LANG_MAP:
            return

        # Get the channel and message
        try:
            channel = self.client.get_channel(payload.channel_id)
            if channel is None:
                channel = await self.client.fetch_channel(payload.channel_id)
            
            message = await channel.fetch_message(payload.message_id)
        except Exception:
            return

        # Don't translate empty messages or bot messages
        if not message.content or message.author.bot:
            return

        # Check cache to avoid duplicate translations
        cache_key = (message.id, FLAG_LANG_MAP[emoji_str])
        if cache_key in self._translated_cache:
            return

        # Get target language
        target_lang = FLAG_LANG_MAP[emoji_str]
        
        # Translate
        result = await self._translate_text(message.content, target_lang)
        
        if result is None:
            return

        # Don't translate if same language
        if result['src'].lower() == result['dest'].lower():
            return

        # Cache the translation
        self._translated_cache[cache_key] = result['text']
        
        # Limit cache size
        if len(self._translated_cache) > 100:
            # Remove oldest entries
            keys_to_remove = list(self._translated_cache.keys())[:20]
            for key in keys_to_remove:
                del self._translated_cache[key]

        # Send translation
        embed = discord.Embed(
            title=f"Translation to {result['dest_name']}",
            color=0x3498db
        )
        embed.add_field(
            name=f"Original ({result['src_name']})",
            value=message.content[:500],
            inline=False
        )
        embed.add_field(
            name=f"Translated ({result['dest_name']})",
            value=result['text'][:500],
            inline=False
        )
        embed.set_footer(text=f"Translating message from {message.author.display_name}")

        try:
            await channel.send(embed=embed, reference=message, mention_author=False)
        except Exception:
            await channel.send(embed=embed)


async def setup(client):
    await client.add_cog(Translation(client))