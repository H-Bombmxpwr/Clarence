import asyncio
import json
import logging
import os
from datetime import date, datetime
from pathlib import Path
from typing import Optional

import discord
from discord.ext import commands
from discord.utils import get

# ----------------------------
# Config / constants
# ----------------------------
STORAGE_DIR = Path("storage")
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_FILE = STORAGE_DIR / "guild_config.json"  # per-guild settings incl. prefix & log channel

# In-memory config cache (persisted to JSON)
_guild_cfg = {}


def _load_cfg():
    global _guild_cfg
    if CONFIG_FILE.exists():
        try:
            _guild_cfg = json.loads(CONFIG_FILE.read_text("utf-8"))
        except Exception:
            _guild_cfg = {}
    else:
        _guild_cfg = {}


def _save_cfg():
    try:
        CONFIG_FILE.write_text(json.dumps(_guild_cfg, indent=2, ensure_ascii=False))
    except Exception:
        pass


def get_prefix_for(guild_id: int, default: str = "$") -> str:
    g = _guild_cfg.get(str(guild_id), {})
    return g.get("prefix", default)


def set_prefix_for(guild_id: int, prefix: str):
    g = _guild_cfg.setdefault(str(guild_id), {})
    g["prefix"] = prefix
    _save_cfg()


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


async def send_log(guild: discord.Guild, embed: discord.Embed, fallback_text: Optional[str] = None):
    cid = get_log_channel_id(guild.id)
    if cid is None:
        return
    ch = guild.get_channel(cid)
    if ch is None:
        # Try to fetch
        try:
            ch = await guild.fetch_channel(cid)
        except Exception:
            return
    try:
        await ch.send(embed=embed)
    except Exception:
        if fallback_text:
            try:
                await ch.send(fallback_text)
            except Exception:
                pass


# Basic runtime logger
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


class Moderation(commands.Cog):
    """Moderation commands with robust permission checks and mod-logging."""

    def __init__(self, client: commands.Bot):
        self.client = client
        _load_cfg()

    # ----------------------------
    # Helpers
    # ----------------------------
    @staticmethod
    def _can_act(acting: discord.Member, target: discord.Member) -> bool:
        """Return True if acting member can act on target (role hierarchy check)."""
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

    # ----------------------------
    # Prefix & logging channel management
    # ----------------------------
    @commands.command(help="Change server command prefix (Admin only)")
    @commands.has_permissions(administrator=True)
    async def prefix(self, ctx: commands.Context, prefix: Optional[str] = None):
        if not prefix:
            cur = get_prefix_for(ctx.guild.id)
            await ctx.send(f"Current prefix is `{cur}`. To change: `prefix !`.")
            return
        if len(prefix) > 5:
            await ctx.send("Prefix too long (max 5 chars).")
            return
        set_prefix_for(ctx.guild.id, prefix)
        await ctx.send(f"Prefix changed to `{prefix}`")
        embed = discord.Embed(title="Prefix Changed", description=f"New prefix: `{prefix}`", color=0x2ECC71, timestamp=datetime.utcnow())
        await send_log(ctx.guild, embed)

    @commands.command(help="Set the moderation log channel. Use without args to clear.")
    @commands.has_permissions(administrator=True)
    async def setlog(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        if channel is None:
            set_log_channel_id(ctx.guild.id, None)
            await ctx.send("Logging channel cleared.")
            return
        set_log_channel_id(ctx.guild.id, channel.id)
        await ctx.send(f"Logging channel set to {channel.mention}")
        embed = discord.Embed(title="Logging Channel Set", description=f"Channel: {channel.mention}", color=0x3498DB, timestamp=datetime.utcnow())
        await send_log(ctx.guild, embed)

    # ----------------------------
    # Core moderation commands
    # ----------------------------
    @commands.command(help="Ban a user. Usage: ban @user [reason]")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def ban(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if member.id == self.client.owner_id:
            await ctx.send("I cannot ban my creator.")
            return
        if not self._can_act(ctx.author, member):
            await ctx.send("You cannot ban someone with an equal or higher role.")
            return
        if not self._bot_can_act(ctx.guild, member):
            await ctx.send("I cannot ban that user due to role hierarchy.")
            return
        try:
            await member.ban(reason=reason, delete_message_days=0)
        except discord.Forbidden:
            await ctx.send("I lack permission to ban this user.")
            return
        except Exception as e:
            await ctx.send(f"Failed to ban: {type(e).__name__}")
            return
        embed = discord.Embed(title="User Banned", color=0xE74C3C, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        await ctx.send(embed=embed)
        await send_log(ctx.guild, embed)

    @commands.command(help="Unban a user. Usage: unban name#1234")
    @commands.has_permissions(ban_members=True)
    @commands.bot_has_permissions(ban_members=True)
    async def unban(self, ctx: commands.Context, *, member_identifier: str):
        if "#" not in member_identifier:
            await ctx.send("Provide the tag like `name#1234`.")
            return
        name, discriminator = member_identifier.rsplit("#", 1)
        bans = await ctx.guild.bans()
        for entry in bans:
            user = entry.user
            if (user.name, user.discriminator) == (name, discriminator):
                try:
                    await ctx.guild.unban(user)
                except Exception as e:
                    await ctx.send(f"Failed to unban: {type(e).__name__}")
                    return
                await ctx.send(f"Unbanned {user.mention}")
                embed = discord.Embed(title="User Unbanned", color=0x2ECC71, timestamp=datetime.utcnow())
                embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
                embed.add_field(name="By", value=f"{ctx.author}", inline=True)
                await send_log(ctx.guild, embed)
                return
        await ctx.send(f"User {member_identifier} not found in ban list.")

    @commands.command(help="List banned users")
    @commands.has_permissions(ban_members=True)
    async def banlist(self, ctx: commands.Context):
        banned = await ctx.guild.bans()
        if not banned:
            await ctx.send("No users are currently banned.")
            return
        # Chunk into pages by 25 entries
        pages = [banned[i:i+25] for i in range(0, len(banned), 25)]
        for idx, page in enumerate(pages, start=1):
            desc = "\n".join(f"{e.user} ({e.user.id})" for e in page)
            embed = discord.Embed(title=f"Banned Users — Page {idx}/{len(pages)}", description=desc, color=0x8E44AD)
            await ctx.send(embed=embed)

    @commands.command(help="Kick a user. Usage: kick @user [reason]")
    @commands.has_permissions(kick_members=True)
    @commands.bot_has_permissions(kick_members=True)
    async def kick(self, ctx: commands.Context, member: discord.Member, *, reason: Optional[str] = None):
        if member.bot or member == ctx.guild.owner:
            await ctx.send("I cannot kick the server owner or bots.")
            return
        if not self._can_act(ctx.author, member):
            await ctx.send("You cannot kick someone with an equal or higher role.")
            return
        if not self._bot_can_act(ctx.guild, member):
            await ctx.send("I cannot kick that user due to role hierarchy.")
            return
        try:
            await member.kick(reason=reason)
        except discord.Forbidden:
            await ctx.send("I lack permission to kick this user.")
            return
        except Exception as e:
            await ctx.send(f"An error occurred: {type(e).__name__}")
            return
        await ctx.send(f"{member.mention} has been kicked.")
        embed = discord.Embed(title="User Kicked", color=0xD35400, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        embed.add_field(name="Reason", value=reason or "No reason provided.", inline=False)
        await send_log(ctx.guild, embed)

    # ----------------------------
    # Roles & muting
    # ----------------------------
    @commands.command(help="Mute a user (create Muted role + enforce overwrites)")
    @commands.has_permissions(manage_roles=True, manage_channels=True)
    @commands.bot_has_permissions(manage_roles=True, manage_channels=True)
    async def mute(self, ctx, member: discord.Member, *, reason: Optional[str] = None):
        if member == ctx.guild.owner or member.bot:
            await ctx.send("I cannot mute the server owner or bots.")
            return
        if not self._can_act(ctx.author, member) or not self._bot_can_act(ctx.guild, member):
            await ctx.send("Cannot mute due to role hierarchy.")
            return

        async with ctx.typing():
            muted_role = await self._ensure_muted_role_and_overwrites(ctx.guild)
            if muted_role in member.roles:
                await ctx.send(f"{member.mention} is already muted.")
                return
            await member.add_roles(muted_role, reason=reason)

        await ctx.send(f"{member.mention} is now muted: can view only what they already could, but cannot send/speak anywhere.")



    @commands.command(help="Unmute a user")
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def unmute(self, ctx: commands.Context, member: discord.Member):
        muted_role = get(ctx.guild.roles, name="Muted")
        if not muted_role:
            await ctx.send("The 'Muted' role does not exist.")
            return
        if muted_role not in member.roles:
            await ctx.send(f"{member.mention} is not muted.")
            return
        try:
            await member.remove_roles(muted_role)
        except Exception as e:
            await ctx.send(f"Failed to remove role: {type(e).__name__}")
            return
        await ctx.send(f"{member.mention} has been unmuted.")
        embed = discord.Embed(title="User Unmuted", color=0x1ABC9C, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        await send_log(ctx.guild, embed)

    @commands.command(help="Give Admin role (creates one if missing)", aliases=["gvad"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def giveadmin(self, ctx: commands.Context, member: discord.Member):
        if member.bot or member == ctx.guild.owner:
            await ctx.send("I cannot give the Admin role to bots or the server owner.")
            return
        if not self._can_act(ctx.author, member) or not self._bot_can_act(ctx.guild, member):
            await ctx.send("Cannot assign role due to hierarchy.")
            return
        admin_role = get(ctx.guild.roles, name="Admin")
        if not admin_role:
            try:
                admin_role = await ctx.guild.create_role(
                    name="Admin",
                    permissions=discord.Permissions(administrator=True),
                    colour=discord.Colour(0x280137),
                    hoist=True,
                )
            except Exception as e:
                await ctx.send(f"Failed to create Admin role: {type(e).__name__}")
                return
        if admin_role in member.roles:
            await ctx.send(f"{member.mention} already has the Admin role.")
            return
        try:
            await member.add_roles(admin_role)
        except Exception as e:
            await ctx.send(f"Failed to add Admin role: {type(e).__name__}")
            return
        await ctx.send(f"{member.mention} was given the Admin role.")
        embed = discord.Embed(title="Admin Role Granted", color=0x9B59B6, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        await send_log(ctx.guild, embed)



    # inside class Moderation(commands.Cog):

    async def _ensure_muted_role_and_overwrites(self, guild: discord.Guild) -> discord.Role:
        """
        Create/get 'Muted' and apply channel overwrites that DO NOT grant visibility.
        We only DENY talk perms (send/speak/etc). Visibility (view_channel/connect) is left as None.
        Effect: user stays able to see only what they already could, but cannot send/speak anywhere.
        """
        muted = discord.utils.get(guild.roles, name="Muted")
        if muted is None:
            muted = await guild.create_role(name="Muted", colour=discord.Colour.dark_grey())

        # Iterate all channels and write DENY overwrites for the Muted role.
        for ch in guild.channels:
            try:
                ow = ch.overwrites_for(muted)

                if isinstance(ch, (discord.TextChannel, discord.ForumChannel)):
                    # keep ow.view_channel as-is (None). Only deny “talking”.
                    ow.send_messages = False
                    ow.add_reactions = False
                    ow.send_messages_in_threads = False
                    ow.create_public_threads = False
                    ow.create_private_threads = False
                    ow.attach_files = False
                    ow.embed_links = False
                    await ch.set_permissions(muted, overwrite=ow)

                elif isinstance(ch, discord.Thread):
                    # threads need explicit denies too; do not modify visibility
                    ow.send_messages = False
                    ow.add_reactions = False
                    await ch.set_permissions(muted, overwrite=ow)

                elif isinstance(ch, discord.VoiceChannel):
                    # do NOT set connect/view_channel; only deny speaking
                    ow.speak = False
                    ow.stream = False
                    ow.use_voice_activation = False
                    await ch.set_permissions(muted, overwrite=ow)

                elif isinstance(ch, discord.StageChannel):
                    # do NOT set connect/view_channel; only deny speaking/request
                    ow.speak = False
                    ow.request_to_speak = False
                    ow.stream = False
                    ow.use_voice_activation = False
                    await ch.set_permissions(muted, overwrite=ow)

                # Categories: skip changing visibility. Generally no need to set denies here;
                # child channel overwrites are sufficient. If you want to be thorough, you could
                # mirror the same denies on categories, but it’s optional and can interact with inheritance.

            except Exception:
                continue

        return muted


    @commands.command(help="Remove Admin role", aliases=["rmad"])
    @commands.has_permissions(administrator=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def removeadmin(self, ctx: commands.Context, member: discord.Member):
        admin_role = get(ctx.guild.roles, name="Admin")
        if not admin_role:
            await ctx.send("The 'Admin' role does not exist.")
            return
        if admin_role not in member.roles:
            await ctx.send(f"{member.mention} does not have the Admin role.")
            return
        if not self._can_act(ctx.author, member) or not self._bot_can_act(ctx.guild, member):
            await ctx.send("Cannot remove role due to hierarchy.")
            return
        try:
            await member.remove_roles(admin_role)
        except Exception as e:
            await ctx.send(f"Failed to remove Admin role: {type(e).__name__}")
            return
        await ctx.send(f"{member.mention}'s Admin role has been removed.")
        embed = discord.Embed(title="Admin Role Removed", color=0xC0392B, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{member} ({member.id})", inline=False)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        await send_log(ctx.guild, embed)

    # ----------------------------
    # Utilities
    # ----------------------------
    @commands.command(help="List roles in the server")
    async def roles(self, ctx: commands.Context):
        roles = "\n".join(r.mention for r in ctx.guild.roles[::-1])  # top first
        embed = discord.Embed(title="Active Roles", description=roles, color=ctx.author.color)
        embed.add_field(name="Total Roles", value=len(ctx.guild.roles), inline=False)
        await ctx.send(embed=embed)

    @commands.command(help="Ping (bot latency)")
    async def ping(self, ctx: commands.Context):
        await ctx.send(f" `{round(self.client.latency * 1000)}` ms")

    @commands.command(help="Delete the last N messages (1-250)", aliases=["cl"]) 
    @commands.has_permissions(manage_messages=True)
    @commands.bot_has_permissions(manage_messages=True)
    async def clean(self, ctx: commands.Context, limit: int):
        if limit < 1 or limit > 250:
            await ctx.send("Please specify a limit between 1 and 250.")
            return
        purged = await ctx.channel.purge(limit=limit + 1)
        count = max(0, len(purged) - 1)
        msg = await ctx.send(f"Cleared {count} messages.")
        try:
            await msg.delete(delay=5)
        except Exception:
            pass
        embed = discord.Embed(title="Messages Purged", color=0xF1C40F, timestamp=datetime.utcnow())
        embed.add_field(name="Channel", value=ctx.channel.mention, inline=True)
        embed.add_field(name="By", value=f"{ctx.author}", inline=True)
        embed.add_field(name="Count", value=str(count), inline=True)
        await send_log(ctx.guild, embed)

    @commands.command(help="Move a role to a specific position", aliases=["mvrl"]) 
    @commands.has_permissions(manage_roles=True)
    @commands.bot_has_permissions(manage_roles=True)
    async def moverole(self, ctx: commands.Context, role: discord.Role, pos: int):
        if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
            await ctx.send("You cannot move a role higher or equal to your top role.")
            return
        try:
            await role.edit(position=pos)
            await ctx.send(f"Role {role.name} moved to position {pos}.")
        except discord.Forbidden:
            await ctx.send("I do not have permission to move this role.")
        except Exception as e:
            await ctx.send(f"An error occurred while moving the role: {type(e).__name__}")

    @commands.command(help="Count messages in a channel")
    async def message_count(self, ctx: commands.Context, channel: Optional[discord.TextChannel] = None):
        channel = channel or ctx.channel
        async with ctx.typing():
            count = 0
            async for _ in channel.history(limit=None):
                count += 1
        await ctx.send(f"There are {count} messages in {channel.mention}.")

    # ----------------------------
    # Passive logging events
    # ----------------------------
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="Member Banned (Audit)", color=0xE74C3C, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="Member Unbanned (Audit)", color=0x2ECC71, timestamp=datetime.utcnow())
        embed.add_field(name="User", value=f"{user} ({user.id})", inline=False)
        await send_log(guild, embed)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if message.guild is None or message.author.bot:
            return
        embed = discord.Embed(title="Message Deleted", color=0xF39C12, timestamp=datetime.utcnow())
        embed.add_field(name="Author", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="Channel", value=message.channel.mention, inline=True)
        content = message.content or "(no text)"
        if len(content) > 1000:
            content = content[:1000] + "…"
        embed.add_field(name="Content", value=content, inline=False)
        await send_log(message.guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if before.guild is None or before.author.bot:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(title="Message Edited", color=0x3498DB, timestamp=datetime.utcnow())
        embed.add_field(name="Author", value=f"{before.author} ({before.author.id})", inline=False)
        embed.add_field(name="Channel", value=before.channel.mention, inline=True)
        b = before.content or "(no text)"
        a = after.content or "(no text)"
        if len(b) > 700:
            b = b[:700] + "…"
        if len(a) > 700:
            a = a[:700] + "…"
        embed.add_field(name="Before", value=b, inline=False)
        embed.add_field(name="After", value=a, inline=False)
        await send_log(before.guild, embed)


class Owner(commands.Cog):
    """Owner-only utilities."""

    def __init__(self, client: commands.Bot):
        self.client = client

    @commands.command(help="Show active servers (owner only)", hidden=True)
    @commands.is_owner()
    async def servers(self, ctx: commands.Context):
        activeservers = self.client.guilds
        guild_list = "\n".join(f"{g.name} ({g.id})" for g in activeservers)
        embed = discord.Embed(title="Active Servers", description=guild_list, color=0x6A0DAD)
        embed.set_footer(text=f"As of {date.today()}")
        await ctx.send(embed=embed)

    @commands.command(help="Manually add a server prefix (owner only)", hidden=True)
    @commands.is_owner()
    async def addserver(self, ctx: commands.Context, id: int):
        set_prefix_for(id, get_prefix_for(id))
        await ctx.send("Server entry ensured in config.")

    @commands.command(help="Manually remove a server from config (owner only)", hidden=True)
    @commands.is_owner()
    async def removeserver(self, ctx: commands.Context, id: int):
        _guild_cfg.pop(str(id), None)
        _save_cfg()
        await ctx.send("Server removed from config.")


async def setup(client: commands.Bot):
    await client.add_cog(Moderation(client))
    await client.add_cog(Owner(client))
