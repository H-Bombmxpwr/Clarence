# cogs/automod.py
"""Configurable automatic moderation: spam, mention spam, invites, links, banned words, excessive caps."""
import re
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Optional
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from functionality import modstore as ms
from functionality.ui import chunk_lines, format_duration, parse_duration

INVITE_RE = re.compile(r"(discord(?:app)?\.com/invite|discord\.gg|dsc\.gg)/[\w-]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)
LEET = str.maketrans({"0": "o", "1": "i", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "9": "g",
                      "@": "a", "$": "s", "!": "i", "|": "i", "€": "e"})

FILTERS = {
    "spam": "Message flooding",
    "mentions": "Mass mentions",
    "invites": "Discord invite links",
    "links": "All links (except allowed domains)",
    "words": "Banned words",
    "caps": "Excessive capital letters",
}
FILTER_CHOICES = [app_commands.Choice(name=f"{k} — {v}", value=k) for k, v in FILTERS.items()]

DEFAULTS = {
    "enabled": False,
    "action": "delete",          # delete | warn | timeout
    "timeout_seconds": 300,
    "filters": {
        "spam": {"enabled": False, "messages": 5, "seconds": 5},
        "mentions": {"enabled": False, "max": 5},
        "invites": {"enabled": False},
        "links": {"enabled": False, "allowed_domains": ["tenor.com", "giphy.com", "youtube.com", "youtu.be"]},
        "words": {"enabled": False, "words": [], "use_builtin": False},
        "caps": {"enabled": False, "percent": 70, "min_length": 10},
    },
    "exempt_roles": [],
    "exempt_channels": [],
}


def _merge_defaults(cfg: dict, defaults: dict) -> dict:
    for k, v in defaults.items():
        if k not in cfg:
            cfg[k] = v.copy() if isinstance(v, (dict, list)) else v
        elif isinstance(v, dict):
            _merge_defaults(cfg[k], v)
    return cfg


def automod_config(guild_id: int) -> dict:
    return _merge_defaults(ms.guild_config(guild_id).setdefault("automod", {}), DEFAULTS)


def _load_builtin_words() -> set[str]:
    try:
        with open("constants/words.txt", encoding="utf-8") as f:
            return {line.strip().lower() for line in f if line.strip()}
    except FileNotFoundError:
        return set()


class AutoMod(commands.Cog):
    """Automatic moderation"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.recent: dict[tuple[int, int], deque] = defaultdict(lambda: deque(maxlen=50))
        self._builtin_words: Optional[set[str]] = None

    @property
    def builtin_words(self) -> set[str]:
        if self._builtin_words is None:
            self._builtin_words = _load_builtin_words()
        return self._builtin_words

    # ------------------------------------------------------------------ detection

    def check_message(self, message: discord.Message, cfg: dict) -> Optional[str]:
        """Return the reason a message violates automod, or None."""
        f = cfg["filters"]
        content = message.content

        if f["spam"]["enabled"]:
            key = (message.guild.id, message.author.id)
            now = time.monotonic()
            stamps = self.recent[key]
            stamps.append(now)
            window = [t for t in stamps if now - t <= f["spam"]["seconds"]]
            if len(window) >= f["spam"]["messages"]:
                stamps.clear()
                return f"Spam ({len(window)} messages in {f['spam']['seconds']}s)"

        if f["mentions"]["enabled"]:
            count = len(set(message.raw_mentions)) + len(message.raw_role_mentions) + (5 if message.mention_everyone else 0)
            if count >= f["mentions"]["max"]:
                return f"Mass mentions ({count})"

        if f["invites"]["enabled"] and INVITE_RE.search(content):
            return "Discord invite link"

        if f["links"]["enabled"]:
            allowed = [d.lower() for d in f["links"]["allowed_domains"]]
            for url in URL_RE.findall(content):
                host = (urlparse(url).hostname or "").lower()
                if not any(host == d or host.endswith("." + d) for d in allowed):
                    return f"Link not allowed ({host})"

        if f["words"]["enabled"]:
            normalized = content.lower().translate(LEET)
            tokens = set(re.findall(r"[a-z]+", normalized))
            squashed = re.sub(r"[^a-z]", "", normalized)
            custom = [w.lower() for w in f["words"]["words"]]
            for w in custom:
                # custom words also match inside other text, e.g. "b a d w o r d"
                if w in tokens or (len(w) >= 4 and w in squashed):
                    return "Banned word"
            if f["words"]["use_builtin"] and tokens & self.builtin_words:
                return "Banned word"

        if f["caps"]["enabled"]:
            letters = [c for c in content if c.isalpha()]
            if len(letters) >= f["caps"]["min_length"]:
                pct = 100 * sum(c.isupper() for c in letters) / len(letters)
                if pct >= f["caps"]["percent"]:
                    return f"Excessive caps ({pct:.0f}%)"
        return None

    def is_exempt(self, message: discord.Message, cfg: dict) -> bool:
        member = message.author
        if not isinstance(member, discord.Member):
            return True
        if member.guild_permissions.manage_messages or member.id == message.guild.owner_id:
            return True
        if message.channel.id in cfg["exempt_channels"] or getattr(message.channel, "category_id", None) in cfg["exempt_channels"]:
            return True
        return any(r.id in cfg["exempt_roles"] for r in member.roles)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot or not message.content:
            return
        cfg = automod_config(message.guild.id)
        if not cfg["enabled"] or self.is_exempt(message, cfg):
            return
        reason = self.check_message(message, cfg)
        if reason:
            await self.punish(message, cfg, reason)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.content != after.content:
            # don't count edits towards spam
            cfg = automod_config(after.guild.id) if after.guild else None
            if not cfg or not cfg["enabled"] or after.author.bot or self.is_exempt(after, cfg):
                return
            spam = cfg["filters"]["spam"]["enabled"]
            cfg["filters"]["spam"]["enabled"] = False
            try:
                reason = self.check_message(after, cfg)
            finally:
                cfg["filters"]["spam"]["enabled"] = spam
            if reason:
                await self.punish(after, cfg, reason)

    async def punish(self, message: discord.Message, cfg: dict, reason: str):
        member = message.author
        guild = message.guild
        try:
            await message.delete()
        except discord.HTTPException:
            pass

        action_taken = "Message deleted"
        if cfg["action"] == "warn":
            mod = self.bot.get_cog("Moderation")
            if mod:
                case, escalation = await mod.issue_warning(guild, member, guild.me, f"AutoMod: {reason}")
                action_taken = f"Warned (case #{case['id']})" + (f" — {escalation}" if escalation else "")
        elif cfg["action"] == "timeout" and member.top_role < guild.me.top_role:
            duration = timedelta(seconds=cfg["timeout_seconds"])
            try:
                await member.timeout(duration, reason=f"AutoMod: {reason}")
                mod = self.bot.get_cog("Moderation")
                if mod:
                    await mod.record(guild, "timeout", member, guild.me, f"AutoMod: {reason}", duration=duration)
                action_taken = f"Timed out for {format_duration(duration)}"
            except discord.HTTPException:
                pass

        try:
            await message.channel.send(f"{member.mention}, your message was removed: **{reason}**.", delete_after=6)
        except discord.HTTPException:
            pass

        embed = discord.Embed(title="AutoMod", color=0xe67e22, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{member.mention} (`{member.id}`)")
        embed.add_field(name="Channel", value=message.channel.mention)
        embed.add_field(name="Trigger", value=reason)
        embed.add_field(name="Action", value=action_taken, inline=False)
        embed.add_field(name="Content", value=message.content[:1000] or "(empty)", inline=False)
        await ms.send_modlog(guild, embed)

    # ------------------------------------------------------------------ configuration commands

    automod = app_commands.Group(name="automod", description="Configure automatic moderation", guild_only=True,
                                 default_permissions=discord.Permissions(manage_guild=True))
    words = app_commands.Group(name="words", description="Banned word list", parent=automod)
    exempt = app_commands.Group(name="exempt", description="Roles/channels AutoMod ignores", parent=automod)

    @automod.command(name="status", description="Show the current AutoMod configuration")
    async def status(self, interaction: discord.Interaction):
        cfg = automod_config(interaction.guild.id)
        f = cfg["filters"]
        on = lambda b: "✅" if b else "❌"
        embed = discord.Embed(title="AutoMod", color=0x2ecc71 if cfg["enabled"] else 0x95a5a6,
                              description=f"**{'Enabled' if cfg['enabled'] else 'Disabled'}** • action: **{cfg['action']}**"
                                          + (f" ({format_duration(timedelta(seconds=cfg['timeout_seconds']))})" if cfg["action"] == "timeout" else ""))
        embed.add_field(name=f"{on(f['spam']['enabled'])} spam", value=f"{f['spam']['messages']} msgs / {f['spam']['seconds']}s")
        embed.add_field(name=f"{on(f['mentions']['enabled'])} mentions", value=f"max {f['mentions']['max']}")
        embed.add_field(name=f"{on(f['invites']['enabled'])} invites", value="discord.gg links")
        embed.add_field(name=f"{on(f['links']['enabled'])} links", value="allowed: " + (", ".join(f["links"]["allowed_domains"]) or "none")[:200])
        embed.add_field(name=f"{on(f['words']['enabled'])} words", value=f"{len(f['words']['words'])} custom" + (" + built-in list" if f["words"]["use_builtin"] else ""))
        embed.add_field(name=f"{on(f['caps']['enabled'])} caps", value=f"≥{f['caps']['percent']}% of ≥{f['caps']['min_length']} letters")
        roles = " ".join(f"<@&{r}>" for r in cfg["exempt_roles"]) or "none"
        chans = " ".join(f"<#{c}>" for c in cfg["exempt_channels"]) or "none"
        embed.add_field(name="Exempt", value=f"Roles: {roles}\nChannels: {chans}\n*Members with Manage Messages are always exempt.*", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @automod.command(name="toggle", description="Turn AutoMod on or off for this server (off by default)")
    async def toggle(self, interaction: discord.Interaction, enabled: bool):
        cfg = automod_config(interaction.guild.id)
        cfg["enabled"] = enabled
        note = ""
        if enabled and not any(f["enabled"] for f in cfg["filters"].values()):
            # First time on: start with sensible filters rather than an AutoMod that does nothing
            for name in ("spam", "mentions", "invites"):
                cfg["filters"][name]["enabled"] = True
            note = "\nTurned on the **spam**, **mentions** and **invites** filters to start. Adjust with `/automod filter`."
        ms.save_config()
        await interaction.response.send_message(f"AutoMod **{'enabled' if enabled else 'disabled'}** for this server.{note}", ephemeral=True)

    @automod.command(name="filter", description="Enable or disable an individual filter")
    @app_commands.choices(name=FILTER_CHOICES)
    async def filter(self, interaction: discord.Interaction, name: app_commands.Choice[str], enabled: bool):
        cfg = automod_config(interaction.guild.id)
        cfg["filters"][name.value]["enabled"] = enabled
        ms.save_config()
        extra = "" if cfg["enabled"] else " (AutoMod itself is off — use `/automod toggle`)"
        await interaction.response.send_message(f"Filter **{name.value}** {'enabled' if enabled else 'disabled'}.{extra}", ephemeral=True)

    @automod.command(name="action", description="What happens to someone who triggers AutoMod")
    @app_commands.describe(action="delete only, delete + warn (counts toward escalation), or delete + timeout",
                           timeout="Timeout length when action is timeout, e.g. 5m")
    @app_commands.choices(action=[app_commands.Choice(name="Delete message", value="delete"),
                                  app_commands.Choice(name="Delete + warn", value="warn"),
                                  app_commands.Choice(name="Delete + timeout", value="timeout")])
    async def action(self, interaction: discord.Interaction, action: app_commands.Choice[str], timeout: Optional[str] = None):
        cfg = automod_config(interaction.guild.id)
        cfg["action"] = action.value
        if timeout:
            td = parse_duration(timeout)
            if not td or td > timedelta(days=28):
                return await interaction.response.send_message("Invalid timeout (e.g. `5m`, `1h`, max 28d).", ephemeral=True)
            cfg["timeout_seconds"] = int(td.total_seconds())
        ms.save_config()
        await interaction.response.send_message(f"AutoMod action set to **{action.name}**.", ephemeral=True)

    @automod.command(name="spam", description="Configure the spam filter threshold")
    async def spam(self, interaction: discord.Interaction, messages: app_commands.Range[int, 2, 30],
                   seconds: app_commands.Range[int, 1, 60]):
        cfg = automod_config(interaction.guild.id)
        cfg["filters"]["spam"].update(messages=messages, seconds=seconds)
        ms.save_config()
        await interaction.response.send_message(f"Spam = **{messages}** messages within **{seconds}s**.", ephemeral=True)

    @automod.command(name="mentions", description="Configure the mass-mention limit")
    async def mentions(self, interaction: discord.Interaction, max_mentions: app_commands.Range[int, 2, 50]):
        automod_config(interaction.guild.id)["filters"]["mentions"]["max"] = max_mentions
        ms.save_config()
        await interaction.response.send_message(f"Mass mention limit = **{max_mentions}**.", ephemeral=True)

    @automod.command(name="caps", description="Configure the caps filter")
    async def caps(self, interaction: discord.Interaction, percent: app_commands.Range[int, 50, 100],
                   min_length: app_commands.Range[int, 5, 200] = 10):
        automod_config(interaction.guild.id)["filters"]["caps"].update(percent=percent, min_length=min_length)
        ms.save_config()
        await interaction.response.send_message(f"Caps filter = **{percent}%** of messages with ≥{min_length} letters.", ephemeral=True)

    @automod.command(name="allowdomain", description="Allow or disallow a domain for the links filter")
    async def allowdomain(self, interaction: discord.Interaction, domain: str, remove: bool = False):
        domain = domain.lower().removeprefix("https://").removeprefix("http://").removeprefix("www.").strip("/")
        allowed = automod_config(interaction.guild.id)["filters"]["links"]["allowed_domains"]
        if remove:
            if domain in allowed:
                allowed.remove(domain)
        elif domain not in allowed:
            allowed.append(domain)
        ms.save_config()
        await interaction.response.send_message(f"Allowed domains: {', '.join(allowed) or 'none'}", ephemeral=True)

    @words.command(name="add", description="Add banned words (comma separated)")
    async def words_add(self, interaction: discord.Interaction, words: str):
        lst = automod_config(interaction.guild.id)["filters"]["words"]["words"]
        added = [w.strip().lower() for w in words.split(",") if w.strip() and w.strip().lower() not in lst]
        lst.extend(added)
        ms.save_config()
        await interaction.response.send_message(f"Added {len(added)} word(s). List has {len(lst)}.", ephemeral=True)

    @words.command(name="remove", description="Remove banned words (comma separated)")
    async def words_remove(self, interaction: discord.Interaction, words: str):
        lst = automod_config(interaction.guild.id)["filters"]["words"]["words"]
        removed = [w.strip().lower() for w in words.split(",") if w.strip().lower() in lst]
        for w in removed:
            lst.remove(w)
        ms.save_config()
        await interaction.response.send_message(f"Removed {len(removed)} word(s).", ephemeral=True)

    @words.command(name="list", description="Show the banned word list")
    async def words_list(self, interaction: discord.Interaction):
        f = automod_config(interaction.guild.id)["filters"]["words"]
        text = ", ".join(f"||{w}||" for w in f["words"]) or "No custom words."
        builtin = f"\n\nBuilt-in list ({len(self.builtin_words)} words): **{'on' if f['use_builtin'] else 'off'}**"
        await interaction.response.send_message(chunk_lines([text], 1800)[0] + builtin, ephemeral=True)

    @words.command(name="builtin", description="Also use the bot's built-in profanity list")
    async def words_builtin(self, interaction: discord.Interaction, enabled: bool):
        automod_config(interaction.guild.id)["filters"]["words"]["use_builtin"] = enabled
        ms.save_config()
        await interaction.response.send_message(f"Built-in word list **{'on' if enabled else 'off'}**.", ephemeral=True)

    @exempt.command(name="role", description="Exempt a role from AutoMod (or remove the exemption)")
    async def exempt_role(self, interaction: discord.Interaction, role: discord.Role, remove: bool = False):
        lst = automod_config(interaction.guild.id)["exempt_roles"]
        if remove and role.id in lst:
            lst.remove(role.id)
        elif not remove and role.id not in lst:
            lst.append(role.id)
        ms.save_config()
        await interaction.response.send_message(f"{role.mention} {'is no longer' if remove else 'is now'} exempt.", ephemeral=True)

    @exempt.command(name="channel", description="Exempt a channel or category from AutoMod (or remove the exemption)")
    async def exempt_channel(self, interaction: discord.Interaction,
                             channel: discord.TextChannel | discord.CategoryChannel | discord.VoiceChannel,
                             remove: bool = False):
        lst = automod_config(interaction.guild.id)["exempt_channels"]
        if remove and channel.id in lst:
            lst.remove(channel.id)
        elif not remove and channel.id not in lst:
            lst.append(channel.id)
        ms.save_config()
        await interaction.response.send_message(f"{channel.mention} {'is no longer' if remove else 'is now'} exempt.", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
