# cogs/serverlog.py
"""Server event logging, welcome/goodbye messages, autoroles, and the /config command group."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from functionality import modstore as ms
from functionality.ui import format_duration, parse_duration

DEFAULT_WELCOME = "Welcome to **{server}**, {user}! You're member #{count}."
DEFAULT_GOODBYE = "**{name}** has left the server."

ESCALATION_ACTIONS = [
    app_commands.Choice(name="Timeout", value="timeout"),
    app_commands.Choice(name="Kick", value="kick"),
    app_commands.Choice(name="Temporary ban", value="tempban"),
    app_commands.Choice(name="Ban", value="ban"),
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def render_template(template: str, member: discord.Member) -> str:
    return (template.replace("{user}", member.mention)
            .replace("{name}", member.display_name)
            .replace("{server}", member.guild.name)
            .replace("{count}", str(member.guild.member_count)))


class ServerLog(commands.Cog):
    """📋 Server logging, welcome messages and configuration"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------ message events

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot or message.channel.id in ms.log_channel_ids(message.guild.id):
            return
        embed = discord.Embed(title="🗑️ Message deleted", color=0xe67e22, timestamp=_now())
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.add_field(name="Channel", value=message.channel.mention)
        embed.add_field(name="Author", value=message.author.mention)
        embed.add_field(name="Content", value=(message.content or "(no text)")[:1024], inline=False)
        if message.attachments:
            embed.add_field(name="Attachments", value="\n".join(a.filename for a in message.attachments)[:1024], inline=False)
        embed.set_footer(text=f"User ID: {message.author.id}")
        await ms.send_eventlog(message.guild, embed)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[discord.Message]):
        if not messages or not messages[0].guild:
            return
        guild = messages[0].guild
        if messages[0].channel.id in ms.log_channel_ids(guild.id):
            return
        embed = discord.Embed(title="🗑️ Bulk delete", color=0xe67e22, timestamp=_now(),
                              description=f"**{len(messages)}** messages deleted in {messages[0].channel.mention}")
        await ms.send_eventlog(guild, embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not before.guild or before.author.bot or before.content == after.content:
            return
        embed = discord.Embed(title="✏️ Message edited", color=0x3498db, timestamp=_now(),
                              description=f"[Jump to message]({after.jump_url}) in {after.channel.mention}")
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.add_field(name="Before", value=(before.content or "(empty)")[:1024], inline=False)
        embed.add_field(name="After", value=(after.content or "(empty)")[:1024], inline=False)
        embed.set_footer(text=f"User ID: {before.author.id}")
        await ms.send_eventlog(before.guild, embed)

    # ------------------------------------------------------------------ member events

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        guild = member.guild
        cfg = ms.guild_config(guild.id)

        age = _now() - member.created_at
        embed = discord.Embed(title="📥 Member joined", color=0x2ecc71, timestamp=_now(),
                              description=f"{member.mention} ({member})")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Account created", value=f"<t:{int(member.created_at.timestamp())}:R>"
                        + (" ⚠️ **new account**" if age < timedelta(days=7) else ""))
        embed.add_field(name="Member count", value=str(guild.member_count))
        embed.set_footer(text=f"User ID: {member.id}")
        await ms.send_eventlog(guild, embed)

        role_ids = cfg.get("autoroles_bots" if member.bot else "autoroles", [])
        roles = [r for r in (guild.get_role(rid) for rid in role_ids) if r and r < guild.me.top_role]
        if roles:
            try:
                await member.add_roles(*roles, reason="Autorole")
            except discord.HTTPException:
                pass

        welcome = cfg.get("welcome", {})
        if welcome.get("channel_id") and not member.bot:
            channel = guild.get_channel(welcome["channel_id"])
            if channel:
                emb = discord.Embed(description=render_template(welcome.get("message") or DEFAULT_WELCOME, member), color=0x2ecc71)
                emb.set_thumbnail(url=member.display_avatar.url)
                try:
                    await channel.send(content=member.mention, embed=emb)
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        guild = member.guild
        roles = [r.mention for r in member.roles[1:]]
        embed = discord.Embed(title="📤 Member left", color=0xe74c3c, timestamp=_now(), description=f"{member.mention} ({member})")
        if member.joined_at:
            embed.add_field(name="Joined", value=f"<t:{int(member.joined_at.timestamp())}:R>")
        embed.add_field(name="Roles", value=" ".join(roles)[:1024] or "None", inline=False)
        embed.set_footer(text=f"User ID: {member.id}")
        await ms.send_eventlog(guild, embed)

        goodbye = ms.guild_config(guild.id).get("goodbye", {})
        if goodbye.get("channel_id") and not member.bot:
            channel = guild.get_channel(goodbye["channel_id"])
            if channel:
                try:
                    await channel.send(render_template(goodbye.get("message") or DEFAULT_GOODBYE, member))
                except discord.HTTPException:
                    pass

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        changes = []
        if before.nick != after.nick:
            changes.append(f"**Nickname:** {before.nick or '(none)'} → {after.nick or '(none)'}")
        added = [r.mention for r in after.roles if r not in before.roles]
        removed = [r.mention for r in before.roles if r not in after.roles]
        if added:
            changes.append(f"**Roles added:** {' '.join(added)}")
        if removed:
            changes.append(f"**Roles removed:** {' '.join(removed)}")
        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until and after.timed_out_until > _now():
                changes.append(f"**Timed out** until <t:{int(after.timed_out_until.timestamp())}:f>")
            else:
                changes.append("**Timeout removed**")
        if not changes:
            return
        embed = discord.Embed(title="👤 Member updated", color=0x9b59b6, timestamp=_now(),
                              description=f"{after.mention}\n" + "\n".join(changes))
        embed.set_footer(text=f"User ID: {after.id}")
        await ms.send_eventlog(after.guild, embed)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔨 User banned", description=f"{user.mention} ({user})", color=0xe74c3c, timestamp=_now())
        await ms.send_eventlog(guild, embed)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔓 User unbanned", description=f"{user.mention} ({user})", color=0x2ecc71, timestamp=_now())
        await ms.send_eventlog(guild, embed)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        if member.bot or before.channel == after.channel:
            return
        if before.channel is None:
            desc, color = f"{member.mention} joined {after.channel.mention}", 0x2ecc71
        elif after.channel is None:
            desc, color = f"{member.mention} left {before.channel.mention}", 0xe74c3c
        else:
            desc, color = f"{member.mention} moved {before.channel.mention} → {after.channel.mention}", 0x3498db
        await ms.send_eventlog(member.guild, discord.Embed(title="🔊 Voice", description=desc, color=color, timestamp=_now()))

    # ------------------------------------------------------------------ channel / role events

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        await ms.send_eventlog(channel.guild, discord.Embed(title="📁 Channel created", color=0x2ecc71, timestamp=_now(),
                                                            description=f"{channel.mention} (`{channel.name}`)"))

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        await ms.send_eventlog(channel.guild, discord.Embed(title="📁 Channel deleted", color=0xe74c3c, timestamp=_now(),
                                                            description=f"`#{channel.name}`"))

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        await ms.send_eventlog(role.guild, discord.Embed(title="🏷️ Role created", color=0x2ecc71, timestamp=_now(),
                                                         description=f"{role.mention} (`{role.name}`)"))

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        await ms.send_eventlog(role.guild, discord.Embed(title="🏷️ Role deleted", color=0xe74c3c, timestamp=_now(),
                                                         description=f"`{role.name}`"))

    # ------------------------------------------------------------------ /config

    config = app_commands.Group(name="config", description="Server configuration for Clarence", guild_only=True,
                                default_permissions=discord.Permissions(manage_guild=True))
    logging = app_commands.Group(name="logging", description="Private log channels for moderators", parent=config)
    autorole = app_commands.Group(name="autorole", description="Roles given automatically on join", parent=config)
    escalation = app_commands.Group(name="escalation", description="Automatic punishments at warning thresholds", parent=config)

    @config.command(name="view", description="Show this server's Clarence configuration")
    async def view(self, interaction: discord.Interaction):
        cfg = ms.guild_config(interaction.guild.id)
        ch = lambda cid: f"<#{cid}>" if cid else "not set"
        embed = discord.Embed(title=f"⚙️ Configuration — {interaction.guild.name}", color=0x3498db)
        embed.add_field(name="Mod log", value=ch(cfg.get("log_channel_id")))
        embed.add_field(name="Event log", value=ch(cfg.get("event_log_channel_id")) + (" (using mod log)" if not cfg.get("event_log_channel_id") and cfg.get("log_channel_id") else ""))
        w, g = cfg.get("welcome", {}), cfg.get("goodbye", {})
        embed.add_field(name="Welcome", value=f"{ch(w.get('channel_id'))}\n{(w.get('message') or DEFAULT_WELCOME)[:200]}", inline=False)
        embed.add_field(name="Goodbye", value=f"{ch(g.get('channel_id'))}\n{(g.get('message') or DEFAULT_GOODBYE)[:200]}", inline=False)
        embed.add_field(name="Autoroles (humans)", value=" ".join(f"<@&{r}>" for r in cfg.get("autoroles", [])) or "none")
        embed.add_field(name="Autoroles (bots)", value=" ".join(f"<@&{r}>" for r in cfg.get("autoroles_bots", [])) or "none")
        embed.add_field(name="Escalation", value=self._escalation_text(cfg), inline=False)
        embed.add_field(name="AutoMod", value=f"{'On' if cfg.get('automod', {}).get('enabled') else 'Off'} — see `/automod status`", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @staticmethod
    def _mod_roles(guild: discord.Guild) -> list[discord.Role]:
        mod_perms = ("administrator", "manage_guild", "ban_members", "kick_members", "moderate_members", "manage_messages")
        return [r for r in guild.roles
                if not r.is_default() and not r.managed and any(getattr(r.permissions, p) for p in mod_perms)]

    @logging.command(name="enable", description="Create private log channels that only moderators can see")
    @app_commands.checks.bot_has_permissions(manage_channels=True, manage_roles=True)
    async def logging_enable(self, interaction: discord.Interaction):
        guild = interaction.guild
        cfg = ms.guild_config(guild.id)
        existing = [guild.get_channel(cfg.get(k) or 0) for k in ("log_channel_id", "event_log_channel_id")]
        if all(existing):
            return await interaction.response.send_message(
                f"Logging is already enabled: {existing[0].mention} (mod actions) and {existing[1].mention} (server events).", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        read_only = discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, embed_links=True, read_message_history=True),
        }
        mod_roles = self._mod_roles(guild)
        for role in mod_roles:
            overwrites[role] = read_only

        category = await guild.create_category("🔒 Clarence Logs", overwrites=overwrites, reason=f"Logging enabled by {interaction.user}")
        modlog = existing[0] or await guild.create_text_channel(
            "mod-log", category=category, topic="Moderation actions, AutoMod hits and cases", reason="Clarence logging")
        eventlog = existing[1] or await guild.create_text_channel(
            "server-log", category=category, topic="Message edits/deletes, joins/leaves, role and voice changes", reason="Clarence logging")
        cfg["log_channel_id"] = modlog.id
        cfg["event_log_channel_id"] = eventlog.id
        cfg["log_category_id"] = category.id
        ms.save_config()

        roles_text = ", ".join(r.mention for r in mod_roles) or "only admins (no moderator roles found)"
        await interaction.followup.send(
            f"✅ Logging enabled.\n• {modlog.mention} — moderation actions\n• {eventlog.mention} — server events\n"
            f"Visible to: {roles_text}\nUse `/config logging addrole` to give another role access.", ephemeral=True)
        await modlog.send(embed=discord.Embed(title="📋 Logging enabled", color=0x2ecc71,
                                              description=f"Set up by {interaction.user.mention}. Moderation actions will appear here."))

    @logging.command(name="disable", description="Stop logging (optionally delete the log channels)")
    @app_commands.describe(delete_channels="Also delete the channels Clarence created")
    async def logging_disable(self, interaction: discord.Interaction, delete_channels: bool = False):
        guild = interaction.guild
        cfg = ms.guild_config(guild.id)
        ids = [cfg.pop(k, None) for k in ("log_channel_id", "event_log_channel_id", "log_category_id")]
        ms.save_config()
        if delete_channels and guild.me.guild_permissions.manage_channels:
            for cid in ids:
                channel = guild.get_channel(cid or 0)
                if channel:
                    try:
                        await channel.delete(reason=f"Logging disabled by {interaction.user}")
                    except discord.HTTPException:
                        pass
        await interaction.response.send_message("Logging disabled" + (" and channels deleted." if delete_channels else "."), ephemeral=True)

    @logging.command(name="addrole", description="Give (or remove) a role's access to the log channels")
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def logging_addrole(self, interaction: discord.Interaction, role: discord.Role, remove: bool = False):
        cfg = ms.guild_config(interaction.guild.id)
        targets = [interaction.guild.get_channel(cfg.get(k) or 0) for k in ("log_category_id", "log_channel_id", "event_log_channel_id")]
        targets = [t for t in targets if t]
        if not targets:
            return await interaction.response.send_message("❌ Logging isn't enabled. Use `/config logging enable`.", ephemeral=True)
        overwrite = None if remove else discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False)
        for t in targets:
            await t.set_permissions(role, overwrite=overwrite, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ {role.mention} {'can no longer' if remove else 'can now'} see the logs.", ephemeral=True)

    @logging.command(name="channels", description="Use existing channels for logs instead of creating new ones")
    @app_commands.describe(modlog="Channel for moderation actions", eventlog="Channel for server events (empty = same as modlog)")
    async def logging_channels(self, interaction: discord.Interaction, modlog: discord.TextChannel,
                               eventlog: Optional[discord.TextChannel] = None):
        cfg = ms.guild_config(interaction.guild.id)
        cfg["log_channel_id"] = modlog.id
        cfg["event_log_channel_id"] = eventlog.id if eventlog else None
        ms.save_config()
        await interaction.response.send_message(
            f"Mod log → {modlog.mention}, event log → {(eventlog or modlog).mention}.", ephemeral=True)

    @config.command(name="welcome", description="Welcome message for new members. Placeholders: {user} {name} {server} {count}")
    @app_commands.describe(channel="Where to post (leave empty to disable)", message="Custom message text")
    async def welcome(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None,
                      message: Optional[app_commands.Range[str, 1, 1500]] = None):
        cfg = ms.guild_config(interaction.guild.id).setdefault("welcome", {})
        cfg["channel_id"] = channel.id if channel else None
        if message:
            cfg["message"] = message
        ms.save_config()
        if not channel:
            return await interaction.response.send_message("Welcome messages disabled.", ephemeral=True)
        preview = render_template(cfg.get("message") or DEFAULT_WELCOME, interaction.user)
        await interaction.response.send_message(f"Welcome messages → {channel.mention}\n**Preview:** {preview}", ephemeral=True)

    @config.command(name="goodbye", description="Message when members leave. Placeholders: {user} {name} {server} {count}")
    async def goodbye(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None,
                      message: Optional[app_commands.Range[str, 1, 1500]] = None):
        cfg = ms.guild_config(interaction.guild.id).setdefault("goodbye", {})
        cfg["channel_id"] = channel.id if channel else None
        if message:
            cfg["message"] = message
        ms.save_config()
        if not channel:
            return await interaction.response.send_message("Goodbye messages disabled.", ephemeral=True)
        preview = render_template(cfg.get("message") or DEFAULT_GOODBYE, interaction.user)
        await interaction.response.send_message(f"Goodbye messages → {channel.mention}\n**Preview:** {preview}", ephemeral=True)

    @autorole.command(name="add", description="Give a role to everyone who joins")
    @app_commands.describe(for_bots="Apply to bots instead of humans")
    async def autorole_add(self, interaction: discord.Interaction, role: discord.Role, for_bots: bool = False):
        if role.managed or role.is_default() or role >= interaction.guild.me.top_role:
            return await interaction.response.send_message("❌ I can't assign that role (it's managed or above my top role).", ephemeral=True)
        key = "autoroles_bots" if for_bots else "autoroles"
        lst = ms.guild_config(interaction.guild.id).setdefault(key, [])
        if role.id not in lst:
            lst.append(role.id)
        ms.save_config()
        await interaction.response.send_message(f"✅ {role.mention} will be given to new {'bots' if for_bots else 'members'}.", ephemeral=True)

    @autorole.command(name="remove", description="Stop giving a role on join")
    async def autorole_remove(self, interaction: discord.Interaction, role: discord.Role):
        cfg = ms.guild_config(interaction.guild.id)
        for key in ("autoroles", "autoroles_bots"):
            if role.id in cfg.get(key, []):
                cfg[key].remove(role.id)
        ms.save_config()
        await interaction.response.send_message(f"✅ {role.mention} removed from autoroles.", ephemeral=True)

    @staticmethod
    def _escalation_text(cfg: dict) -> str:
        rules = cfg.get("escalation", {})
        if not rules:
            return "No rules — warnings never auto-punish."
        lines = []
        for count in sorted(rules, key=int):
            r = rules[count]
            dur = f" ({format_duration(timedelta(seconds=r['duration']))})" if r.get("duration") else ""
            lines.append(f"**{count}** warnings → {r['action']}{dur}")
        return "\n".join(lines)

    @escalation.command(name="set", description="At N active warnings, automatically punish the member")
    @app_commands.describe(warnings="Number of active warnings that triggers this", action="Punishment",
                           duration="Length for timeout/tempban, e.g. 1h, 1d")
    @app_commands.choices(action=ESCALATION_ACTIONS)
    async def escalation_set(self, interaction: discord.Interaction, warnings: app_commands.Range[int, 1, 50],
                             action: app_commands.Choice[str], duration: Optional[str] = None):
        rule = {"action": action.value}
        if action.value in ("timeout", "tempban"):
            td = parse_duration(duration or ("1h" if action.value == "timeout" else "1d"))
            if not td or (action.value == "timeout" and td > timedelta(days=28)):
                return await interaction.response.send_message("❌ Invalid duration (timeouts max 28d).", ephemeral=True)
            rule["duration"] = int(td.total_seconds())
        cfg = ms.guild_config(interaction.guild.id)
        cfg.setdefault("escalation", {})[str(warnings)] = rule
        ms.save_config()
        await interaction.response.send_message(f"✅ Escalation rules:\n{self._escalation_text(cfg)}", ephemeral=True)

    @escalation.command(name="remove", description="Remove the rule for a warning count")
    async def escalation_remove(self, interaction: discord.Interaction, warnings: int):
        cfg = ms.guild_config(interaction.guild.id)
        cfg.get("escalation", {}).pop(str(warnings), None)
        ms.save_config()
        await interaction.response.send_message(f"✅ Escalation rules:\n{self._escalation_text(cfg)}", ephemeral=True)

    @escalation.command(name="list", description="Show escalation rules")
    async def escalation_list(self, interaction: discord.Interaction):
        await interaction.response.send_message(self._escalation_text(ms.guild_config(interaction.guild.id)), ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(ServerLog(bot))
