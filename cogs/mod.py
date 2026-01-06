# cogs/mod.py
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
import re

import discord
from discord.ext import commands

# ----------------------------
# Config / Storage
# ----------------------------
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = STORAGE_DIR / "guild_config.json"
WARNS_FILE = STORAGE_DIR / "warnings.json"

_guild_cfg = {}
_warnings = {}


def _load_cfg():
    global _guild_cfg
    if CONFIG_FILE.exists():
        try:
            _guild_cfg = json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            _guild_cfg = {}


def _save_cfg():
    CONFIG_FILE.write_text(json.dumps(_guild_cfg, indent=2, ensure_ascii=False))


def _load_warns():
    global _warnings
    if WARNS_FILE.exists():
        try:
            _warnings = json.loads(WARNS_FILE.read_text("utf-8"))
        except Exception:
            _warnings = {}


def _save_warns():
    WARNS_FILE.write_text(json.dumps(_warnings, indent=2, ensure_ascii=False))


def get_prefix_for(guild_id: int, default: str = "$") -> str:
    g = _guild_cfg.get(str(guild_id), {})
    return g.get("prefix", default)


def set_prefix_for(guild_id: int, prefix: str):
    g = _guild_cfg.setdefault(str(guild_id), {})
    g["prefix"] = prefix
    _save_cfg()
    # Also update prefixes.json for compatibility
    try:
        with open("storage/prefixes.json", "r") as f:
            prefixes = json.load(f)
    except:
        prefixes = {}
    prefixes[str(guild_id)] = prefix
    with open("storage/prefixes.json", "w") as f:
        json.dump(prefixes, f, indent=4)


def get_log_channel_id(guild_id: int) -> Optional[int]:
    g = _guild_cfg.get(str(guild_id), {})
    return g.get("log_channel_id")


def set_log_channel_id(guild_id: int, channel_id: Optional[int]):
    g = _guild_cfg.setdefault(str(guild_id), {})
    if channel_id is None:
        g.pop("log_channel_id", None)
    else:
        g["log_channel_id"] = int(channel_id)
    _save_cfg()


async def send_log(guild: discord.Guild, embed: discord.Embed):
    cid = get_log_channel_id(guild.id)
    if not cid:
        return
    ch = guild.get_channel(cid)
    if ch is None:
        try:
            ch = await guild.fetch_channel(cid)
        except Exception:
            return
    try:
        await ch.send(embed=embed)
    except Exception:
        pass


def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    _load_warns()
    g = _warnings.setdefault(str(guild_id), {})
    u = g.setdefault(str(user_id), [])
    warn_num = len(u) + 1
    u.append({
        "id": warn_num,
        "reason": reason,
        "mod_id": moderator_id,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    _save_warns()
    return warn_num


def get_warnings(guild_id: int, user_id: int) -> list:
    _load_warns()
    g = _warnings.get(str(guild_id), {})
    return g.get(str(user_id), [])


def clear_warnings(guild_id: int, user_id: int) -> int:
    _load_warns()
    g = _warnings.get(str(guild_id), {})
    count = len(g.get(str(user_id), []))
    if str(user_id) in g:
        del g[str(user_id)]
        _save_warns()
    return count


class Moderation(commands.Cog):
    """Server Moderation Commands"""

    def __init__(self, client: commands.Bot):
        self.client = client
        _load_cfg()
        _load_warns()

    @staticmethod
    def _can_act(acting: discord.Member, target: discord.Member) -> bool:
        if target == acting.guild.owner:
            return False
        if acting == target:
            return False
        return acting.top_role > target.top_role

    @staticmethod
    def _bot_can_act(guild: discord.Guild, target: discord.Member) -> bool:
        me = guild.me
        if me is None:
            return False
        return me.top_role > target.top_role

    @commands.command(help="Change server prefix. Usage: prefix !")
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx: commands.Context, new_prefix: Optional[str] = None):
        if ctx.guild is None:
            return await ctx.send("Use in a server.")
        if new_prefix is None:
            current = get_prefix_for(ctx.guild.id)
            return await ctx.send(f"Current prefix: `{current}`")
        if len(new_prefix) > 5:
            return await ctx.send("Prefix too long (max 5).")
        set_prefix_for(ctx.guild.id, new_prefix)
        embed = discord.Embed(title="Prefix Changed", description=f"New prefix: `{new_prefix}`", color=0x2ecc71)
        await ctx.send(embed=embed)

    @commands.command(help="Set mod log channel")
    @commands.has_permissions(administrator=True)
    async def setlog(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if ctx.guild is None:
            return await ctx.send("Use in a server.")
        if channel is None:
            set_log_channel_id(ctx.guild.id, None)
            return await ctx.send("Logging disabled.")
        set_log_channel_id(ctx.guild.id, channel.id)
        await ctx.send(f"Mod logs will be sent to {channel.mention}")

    @commands.command(help="Ban a user")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if not self._can_act(ctx.author, member):
            return await ctx.send("Cannot ban: role hierarchy.")
        if not self._bot_can_act(ctx.guild, member):
            return await ctx.send("I cannot ban this user.")
        reason = reason or "No reason"
        try:
            await member.send(embed=discord.Embed(title=f"Banned from {ctx.guild.name}", description=f"Reason: {reason}", color=0xe74c3c))
        except:
            pass
        await member.ban(reason=f"{ctx.author}: {reason}")
        embed = discord.Embed(title="User Banned", color=0xe74c3c, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="Moderator", value=str(ctx.author), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        await send_log(ctx.guild, embed)

    @commands.command(help="Unban a user by ID or name#1234")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, *, user_id: str):
        try:
            uid = int(user_id)
            user = await self.client.fetch_user(uid)
            await ctx.guild.unban(user)
            await ctx.send(f"Unbanned {user}")
        except:
            await ctx.send("User not found or not banned.")

    @commands.command(help="Kick a user")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if not self._can_act(ctx.author, member):
            return await ctx.send("Cannot kick: role hierarchy.")
        reason = reason or "No reason"
        await member.kick(reason=f"{ctx.author}: {reason}")
        embed = discord.Embed(title="User Kicked", color=0xf39c12, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User", value=f"{member}", inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)
        await send_log(ctx.guild, embed)

    @commands.command(help="Timeout a user. Usage: mute @user 1h reason")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def mute(self, ctx: commands.Context, member: discord.Member, duration: str = "1h", *, reason: Optional[str] = None):
        if not self._can_act(ctx.author, member):
            return await ctx.send("Cannot mute: role hierarchy.")
        dur_map = {'m': 60, 'h': 3600, 'd': 86400}
        match = re.match(r'^(\d+)([mhd])$', duration.lower())
        if not match:
            return await ctx.send("Invalid duration (e.g., 30m, 1h, 1d)")
        secs = int(match.group(1)) * dur_map[match.group(2)]
        if secs > 28 * 86400:
            return await ctx.send("Max 28 days.")
        until = datetime.now(timezone.utc) + timedelta(seconds=secs)
        await member.timeout(until, reason=reason or "No reason")
        embed = discord.Embed(title="User Muted", color=0x9b59b6)
        embed.add_field(name="User", value=str(member), inline=True)
        embed.add_field(name="Duration", value=duration, inline=True)
        embed.add_field(name="Expires", value=f"<t:{int(until.timestamp())}:R>", inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="Remove timeout")
    @commands.has_permissions(moderate_members=True)
    @commands.bot_has_permissions(moderate_members=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        if not member.timed_out_until:
            return await ctx.send(f"{member.mention} is not muted.")
        await member.timeout(None)
        await ctx.send(f"{member.mention} has been unmuted.")

    @commands.command(help="Warn a user")
    @commands.has_permissions(moderate_members=True)
    async def warn(self, ctx: commands.Context, member: discord.Member, *, reason: str):
        warn_num = add_warning(ctx.guild.id, member.id, ctx.author.id, reason)
        total = len(get_warnings(ctx.guild.id, member.id))
        embed = discord.Embed(title="Warning Issued", color=0xf1c40f)
        embed.add_field(name="User", value=str(member), inline=True)
        embed.add_field(name="Warning #", value=str(warn_num), inline=True)
        embed.add_field(name="Total", value=str(total), inline=True)
        embed.add_field(name="Reason", value=reason, inline=False)
        await ctx.send(embed=embed)

    @commands.command(help="View warnings")
    @commands.has_permissions(moderate_members=True)
    async def warnings(self, ctx: commands.Context, member: discord.Member):
        warns = get_warnings(ctx.guild.id, member.id)
        if not warns:
            return await ctx.send(f"{member} has no warnings.")
        embed = discord.Embed(title=f"Warnings for {member}", color=0xf1c40f)
        for w in warns[-10:]:
            embed.add_field(name=f"#{w['id']}", value=w['reason'][:100], inline=False)
        embed.set_footer(text=f"Total: {len(warns)}")
        await ctx.send(embed=embed)

    @commands.command(help="Clear all warnings")
    @commands.has_permissions(administrator=True)
    async def clearwarns(self, ctx: commands.Context, member: discord.Member):
        count = clear_warnings(ctx.guild.id, member.id)
        await ctx.send(f"Cleared {count} warning(s) from {member}")

    @commands.command(help="Purge messages")
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def purge(self, ctx: commands.Context, amount: int, member: Optional[discord.Member] = None):
        if amount < 1 or amount > 500:
            return await ctx.send("1-500 messages.")
        await ctx.message.delete()
        check = (lambda m: m.author == member) if member else None
        deleted = await ctx.channel.purge(limit=amount, check=check)
        msg = await ctx.send(f"🧹 Deleted {len(deleted)} messages.")
        await asyncio.sleep(3)
        try:
            await msg.delete()
        except:
            pass

    @commands.command(help="Alias for purge")
    @commands.has_permissions(manage_messages=True)
    async def clean(self, ctx: commands.Context, amount: int):
        await self.purge(ctx, amount)

    @commands.command(help="Set slowmode (seconds)")
    @commands.has_permissions(manage_channels=True)
    async def slowmode(self, ctx: commands.Context, seconds: int = 0):
        if seconds < 0 or seconds > 21600:
            return await ctx.send("0-21600 seconds.")
        await ctx.channel.edit(slowmode_delay=seconds)
        await ctx.send(f"Slowmode {'disabled' if seconds == 0 else f'set to {seconds}s'}")

    @commands.command(help="Lock channel")
    @commands.has_permissions(manage_channels=True)
    async def lock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        ow = channel.overwrites_for(ctx.guild.default_role)
        ow.send_messages = False
        await channel.set_permissions(ctx.guild.default_role, overwrite=ow)
        await ctx.send(f"{channel.mention} locked.")

    @commands.command(help="Unlock channel")
    @commands.has_permissions(manage_channels=True)
    async def unlock(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        ow = channel.overwrites_for(ctx.guild.default_role)
        ow.send_messages = None
        await channel.set_permissions(ctx.guild.default_role, overwrite=ow)
        await ctx.send(f"{channel.mention} unlocked.")

    @commands.command(help="Add role to user")
    @commands.has_permissions(manage_roles=True)
    async def addrole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        if role >= ctx.author.top_role and ctx.author != ctx.guild.owner:
            return await ctx.send("Cannot assign higher role.")
        await member.add_roles(role)
        await ctx.send(f"Added {role.mention} to {member.mention}")

    @commands.command(help="Remove role from user")
    @commands.has_permissions(manage_roles=True)
    async def removerole(self, ctx: commands.Context, member: discord.Member, *, role: discord.Role):
        await member.remove_roles(role)
        await ctx.send(f"Removed {role.mention} from {member.mention}")

    @commands.command(help="List server roles")
    async def roles(self, ctx: commands.Context):
        roles = sorted(ctx.guild.roles[1:], key=lambda r: r.position, reverse=True)
        desc = "\n".join([f"{r.mention} ({len(r.members)})" for r in roles[:25]])
        embed = discord.Embed(title="Server Roles", description=desc, color=0x3498db)
        await ctx.send(embed=embed)

    @commands.command(help="Server info")
    async def serverinfo(self, ctx: commands.Context):
        g = ctx.guild
        embed = discord.Embed(title=g.name, color=0x3498db)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        embed.add_field(name="Owner", value=g.owner.mention if g.owner else "?", inline=True)
        embed.add_field(name="Members", value=g.member_count, inline=True)
        embed.add_field(name="Channels", value=len(g.channels), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Boost Lvl", value=g.premium_tier, inline=True)
        await ctx.send(embed=embed)

    @commands.command(help="View ban list")
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx: commands.Context):
        bans = [e async for e in ctx.guild.bans()]
        if not bans:
            return await ctx.send("No bans.")
        desc = "\n".join([f"{e.user} ({e.user.id})" for e in bans[:20]])
        embed = discord.Embed(title=f"Ban List ({len(bans)})", description=desc, color=0xe74c3c)
        await ctx.send(embed=embed)

    @commands.command(help="Bot latency")
    async def ping(self, ctx: commands.Context):
        await ctx.send(f"Pong! `{round(self.client.latency * 1000)}ms`")

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(title="Message Deleted", color=0xf39c12, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Author", value=str(message.author), inline=True)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content[:500] if message.content else "(empty)"
        embed.add_field(name="Content", value=content, inline=False)
        await send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="Message Edited", color=0x3498db, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Author", value=str(before.author), inline=True)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        embed.add_field(name="Before", value=before.content[:400] or "(empty)", inline=False)
        embed.add_field(name="After", value=after.content[:400] or "(empty)", inline=False)
        await send_log(before.guild, embed)


async def setup(client: commands.Bot):
    await client.add_cog(Moderation(client))