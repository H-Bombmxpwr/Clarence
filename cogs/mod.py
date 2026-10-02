# cogs/mod.py
"""Moderation: bans, kicks, timeouts, warnings with escalation, case history, notes, and channel/role/voice tools."""
from datetime import datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands, tasks

from functionality import modstore as ms
from functionality.ui import ConfirmView, Paginator, chunk_lines, format_duration, guild_only_cog, parse_duration

MAX_TIMEOUT = timedelta(days=28)

DELETE_CHOICES = [
    app_commands.Choice(name="Don't delete any", value=0),
    app_commands.Choice(name="Previous hour", value=3600),
    app_commands.Choice(name="Previous 24 hours", value=86400),
    app_commands.Choice(name="Previous 7 days", value=604800),
]


def hierarchy_error(interaction: discord.Interaction, target: discord.abc.User) -> Optional[str]:
    """Return a reason the invoker/bot can't act on `target`, or None if allowed."""
    guild = interaction.guild
    if target.id == interaction.user.id:
        return "You can't do that to yourself."
    if target.id == guild.owner_id:
        return "You can't do that to the server owner."
    if target.id == guild.me.id:
        return "I'm not going to do that to myself."
    if isinstance(target, discord.Member):
        actor = interaction.user
        if actor.id != guild.owner_id and target.top_role >= actor.top_role:
            return f"{target.mention}'s top role is higher than or equal to yours."
        if target.top_role >= guild.me.top_role:
            return f"My top role isn't high enough to act on {target.mention}."
    return None


def role_error(interaction: discord.Interaction, role: discord.Role) -> Optional[str]:
    guild = interaction.guild
    if role.is_default() or role.managed:
        return "That role is managed by Discord/an integration and can't be assigned."
    if interaction.user.id != guild.owner_id and role >= interaction.user.top_role:
        return "That role is higher than or equal to your top role."
    if role >= guild.me.top_role:
        return "That role is higher than or equal to my top role."
    return None


async def dm_user(user: discord.abc.User, guild: discord.Guild, action: str, reason: str, duration: Optional[str] = None):
    embed = discord.Embed(title=f"You were {action} in {guild.name}", color=0xe74c3c)
    embed.add_field(name="Reason", value=reason, inline=False)
    if duration:
        embed.add_field(name="Duration", value=duration, inline=False)
    try:
        await user.send(embed=embed)
    except discord.HTTPException:
        pass


class WarnModal(discord.ui.Modal, title="Warn member"):
    reason = discord.ui.TextInput(label="Reason", style=discord.TextStyle.paragraph, max_length=500)

    def __init__(self, cog: "Moderation", member: discord.Member):
        super().__init__()
        self.cog = cog
        self.member = member

    async def on_submit(self, interaction: discord.Interaction):
        await self.cog.warn_and_respond(interaction, self.member, str(self.reason))


class Moderation(commands.Cog):
    """🛡️ Server moderation"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        ms.migrate_legacy_warnings()
        guild_only_cog(self)
        self.ctx_warn = app_commands.ContextMenu(name="Warn", callback=self.warn_context)
        self.ctx_warn.default_permissions = discord.Permissions(moderate_members=True)
        self.ctx_history = app_commands.ContextMenu(name="Mod History", callback=self.history_context)
        self.ctx_history.default_permissions = discord.Permissions(moderate_members=True)
        self.ctx_warn.guild_only = self.ctx_history.guild_only = True

    async def cog_load(self):
        self.bot.tree.add_command(self.ctx_warn)
        self.bot.tree.add_command(self.ctx_history)
        self.expire_tempbans.start()

    async def cog_unload(self):
        self.bot.tree.remove_command(self.ctx_warn.name, type=self.ctx_warn.type)
        self.bot.tree.remove_command(self.ctx_history.name, type=self.ctx_history.type)
        self.expire_tempbans.cancel()

    # ------------------------------------------------------------------ helpers

    async def record(self, guild: discord.Guild, action: str, user: discord.abc.User, moderator: discord.abc.User,
                     reason: str, duration: Optional[timedelta] = None, expires: Optional[datetime] = None) -> dict:
        case = ms.add_case(
            guild.id, action, user.id, moderator.id, reason,
            duration=int(duration.total_seconds()) if duration else None,
            expires=expires.isoformat() if expires else None,
        )
        await ms.send_modlog(guild, ms.case_embed(case, guild))
        return case

    async def issue_warning(self, guild: discord.Guild, member: discord.Member, moderator: discord.abc.User,
                            reason: str) -> tuple[dict, Optional[str]]:
        """Create a warn case, DM the user, and apply any escalation. Returns (case, escalation description)."""
        case = await self.record(guild, "warn", member, moderator, reason)
        await dm_user(member, guild, "warned", reason)
        escalation = await self.apply_escalation(guild, member)
        return case, escalation

    async def apply_escalation(self, guild: discord.Guild, member: discord.Member) -> Optional[str]:
        rules = ms.guild_config(guild.id).get("escalation", {})
        count = len(ms.user_cases(guild.id, member.id, "warn", active_only=True))
        rule = rules.get(str(count))
        if not rule:
            return None

        action = rule["action"]
        reason = f"Automatic: reached {count} warnings"
        me = guild.me
        if member.top_role >= me.top_role or member.id == guild.owner_id:
            return f"Escalation to **{action}** skipped (I can't act on this member)."
        try:
            if action == "timeout":
                duration = timedelta(seconds=rule.get("duration") or 3600)
                await member.timeout(duration, reason=reason)
                await self.record(guild, "timeout", member, me, reason, duration=duration)
                return f"Timed out for **{format_duration(duration)}** ({count} warnings)."
            if action == "kick":
                await dm_user(member, guild, "kicked", reason)
                await member.kick(reason=reason)
                await self.record(guild, "kick", member, me, reason)
                return f"Kicked ({count} warnings)."
            if action == "tempban":
                duration = timedelta(seconds=rule.get("duration") or 86400)
                expires = datetime.now(timezone.utc) + duration
                await dm_user(member, guild, "temporarily banned", reason, format_duration(duration))
                await guild.ban(member, reason=reason, delete_message_seconds=0)
                await self.record(guild, "tempban", member, me, reason, duration=duration, expires=expires)
                return f"Banned for **{format_duration(duration)}** ({count} warnings)."
            if action == "ban":
                await dm_user(member, guild, "banned", reason)
                await guild.ban(member, reason=reason, delete_message_seconds=0)
                await self.record(guild, "ban", member, me, reason)
                return f"Banned ({count} warnings)."
        except discord.HTTPException as e:
            return f"Escalation to **{action}** failed: {e.text or e}"
        return None

    async def warn_and_respond(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        if member.bot:
            return await interaction.response.send_message("❌ You can't warn bots.", ephemeral=True)
        if err := hierarchy_error(interaction, member):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await interaction.response.defer()
        case, escalation = await self.issue_warning(interaction.guild, member, interaction.user, reason)
        total = len(ms.user_cases(interaction.guild.id, member.id, "warn", active_only=True))
        embed = discord.Embed(
            title=f"⚠️ {member} warned",
            description=f"**Reason:** {reason}\n**Active warnings:** {total}",
            color=0xf1c40f,
        )
        embed.set_footer(text=f"Case #{case['id']}")
        if escalation:
            embed.add_field(name="Escalation", value=escalation, inline=False)
        await interaction.followup.send(embed=embed)

    def history_pages(self, guild: discord.Guild, user: discord.abc.User) -> list[discord.Embed]:
        user_cases = ms.user_cases(guild.id, user.id)
        notes = ms.get_notes(guild.id, user.id)
        counts = {}
        for c in user_cases:
            counts[c["action"]] = counts.get(c["action"], 0) + 1
        summary = ", ".join(f"{v} {k}" for k, v in counts.items()) or "no cases"

        lines = []
        for c in reversed(user_cases):
            ts = int(datetime.fromisoformat(c["timestamp"]).timestamp())
            flag = " ~~pardoned~~" if c["action"] == "warn" and not c.get("active", True) else ""
            lines.append(f"`#{c['id']}` **{c['action']}**{flag} <t:{ts}:d> by <@{c['moderator_id']}>\n└ {c['reason'][:150]}")
        if notes:
            lines.append("\n**📝 Notes**")
            for n in notes:
                lines.append(f"`{n['id']}.` {n['text'][:200]} — <@{n['moderator_id']}>")

        pages = []
        for chunk in chunk_lines(lines or ["Clean record."], 3800):
            embed = discord.Embed(title=f"Moderation history: {user}", description=chunk, color=0x3498db)
            embed.set_thumbnail(url=user.display_avatar.url)
            embed.set_footer(text=summary)
            pages.append(embed)
        return pages

    # ------------------------------------------------------------------ context menus

    async def warn_context(self, interaction: discord.Interaction, member: discord.Member):
        if not interaction.user.guild_permissions.moderate_members:
            return await interaction.response.send_message("❌ You need Moderate Members.", ephemeral=True)
        await interaction.response.send_modal(WarnModal(self, member))

    async def history_context(self, interaction: discord.Interaction, member: discord.Member):
        await Paginator(self.history_pages(interaction.guild, member), interaction.user.id).send(interaction, ephemeral=True)

    # ------------------------------------------------------------------ bans / kicks / timeouts

    @app_commands.command(description="Ban a user (optionally temporarily)")
    @app_commands.describe(user="User to ban (can be someone not in the server)", reason="Why they're being banned",
                           duration="Temporary ban length, e.g. 1d, 12h, 1w (leave empty for permanent)",
                           delete_messages="How much of their recent message history to delete")
    @app_commands.choices(delete_messages=DELETE_CHOICES)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def ban(self, interaction: discord.Interaction, user: discord.User, reason: Optional[str] = None,
                  duration: Optional[str] = None, delete_messages: Optional[app_commands.Choice[int]] = None):
        if err := hierarchy_error(interaction, user):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        td = None
        if duration:
            td = parse_duration(duration)
            if not td:
                return await interaction.response.send_message("❌ Invalid duration. Try `1d`, `12h`, `1w`.", ephemeral=True)
        reason = reason or "No reason provided"
        await interaction.response.defer()

        if isinstance(user, discord.Member):
            await dm_user(user, interaction.guild, "temporarily banned" if td else "banned", reason,
                          format_duration(td) if td else None)
        await interaction.guild.ban(user, reason=f"{interaction.user}: {reason}",
                                    delete_message_seconds=delete_messages.value if delete_messages else 0)
        expires = datetime.now(timezone.utc) + td if td else None
        case = await self.record(interaction.guild, "tempban" if td else "ban", user, interaction.user, reason,
                                 duration=td, expires=expires)
        await interaction.followup.send(embed=ms.case_embed(case, interaction.guild))

    async def banned_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        current = current.lower()
        choices = []
        try:
            async for entry in interaction.guild.bans(limit=1000):
                label = f"{entry.user} ({entry.user.id})"
                if current in label.lower():
                    choices.append(app_commands.Choice(name=label[:100], value=str(entry.user.id)))
                if len(choices) >= 25:
                    break
        except discord.HTTPException:
            pass
        return choices

    @app_commands.command(description="Unban a user")
    @app_commands.describe(user="Banned user (start typing a name or ID)", reason="Why they're being unbanned")
    @app_commands.autocomplete(user=banned_autocomplete)
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def unban(self, interaction: discord.Interaction, user: str, reason: Optional[str] = None):
        if not user.isdigit():
            return await interaction.response.send_message("❌ Pick a user from the list or paste their ID.", ephemeral=True)
        try:
            ban_entry = await interaction.guild.fetch_ban(discord.Object(int(user)))
        except discord.NotFound:
            return await interaction.response.send_message("❌ That user isn't banned.", ephemeral=True)
        reason = reason or "No reason provided"
        await interaction.guild.unban(ban_entry.user, reason=f"{interaction.user}: {reason}")
        self._close_tempbans(interaction.guild.id, ban_entry.user.id)
        case = await self.record(interaction.guild, "unban", ban_entry.user, interaction.user, reason)
        await interaction.response.send_message(embed=ms.case_embed(case, interaction.guild))

    @app_commands.command(description="Ban then immediately unban to wipe a member's recent messages")
    @app_commands.describe(member="Member to softban", reason="Why")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if err := hierarchy_error(interaction, member):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        reason = reason or "No reason provided"
        await interaction.response.defer()
        await dm_user(member, interaction.guild, "kicked (softban)", reason)
        await interaction.guild.ban(member, reason=f"Softban by {interaction.user}: {reason}", delete_message_seconds=86400)
        await interaction.guild.unban(member, reason="Softban")
        case = await self.record(interaction.guild, "softban", member, interaction.user, reason)
        await interaction.followup.send(embed=ms.case_embed(case, interaction.guild))

    @app_commands.command(description="Kick a member")
    @app_commands.describe(member="Member to kick", reason="Why")
    @app_commands.default_permissions(kick_members=True)
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.checks.bot_has_permissions(kick_members=True)
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if err := hierarchy_error(interaction, member):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        reason = reason or "No reason provided"
        await interaction.response.defer()
        await dm_user(member, interaction.guild, "kicked", reason)
        await member.kick(reason=f"{interaction.user}: {reason}")
        case = await self.record(interaction.guild, "kick", member, interaction.user, reason)
        await interaction.followup.send(embed=ms.case_embed(case, interaction.guild))

    @app_commands.command(description="Time out a member (they can't chat or join voice)")
    @app_commands.describe(member="Member to time out", duration="e.g. 10m, 1h, 1d (max 28d)", reason="Why")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, duration: str,
                      reason: Optional[str] = None):
        if err := hierarchy_error(interaction, member):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        td = parse_duration(duration)
        if not td or td > MAX_TIMEOUT:
            return await interaction.response.send_message("❌ Duration must be like `10m`, `2h`, `1d` and at most 28 days.", ephemeral=True)
        reason = reason or "No reason provided"
        await member.timeout(td, reason=f"{interaction.user}: {reason}")
        await dm_user(member, interaction.guild, "timed out", reason, format_duration(td))
        case = await self.record(interaction.guild, "timeout", member, interaction.user, reason, duration=td)
        await interaction.response.send_message(embed=ms.case_embed(case, interaction.guild))

    @app_commands.command(description="Remove a member's timeout")
    @app_commands.describe(member="Member to un-timeout", reason="Why")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.checks.bot_has_permissions(moderate_members=True)
    async def untimeout(self, interaction: discord.Interaction, member: discord.Member, reason: Optional[str] = None):
        if not member.is_timed_out():
            return await interaction.response.send_message(f"❌ {member.mention} isn't timed out.", ephemeral=True)
        reason = reason or "No reason provided"
        await member.timeout(None, reason=f"{interaction.user}: {reason}")
        case = await self.record(interaction.guild, "untimeout", member, interaction.user, reason)
        await interaction.response.send_message(embed=ms.case_embed(case, interaction.guild))

    # ------------------------------------------------------------------ warnings

    @app_commands.command(description="Warn a member (may trigger automatic punishments)")
    @app_commands.describe(member="Member to warn", reason="Why")
    @app_commands.default_permissions(moderate_members=True)
    @app_commands.checks.has_permissions(moderate_members=True)
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str):
        await self.warn_and_respond(interaction, member, reason)

    warnings = app_commands.Group(name="warnings", description="View and manage warnings", guild_only=True,
                                  default_permissions=discord.Permissions(moderate_members=True))

    @warnings.command(name="list", description="List a member's warnings")
    @app_commands.describe(member="Whose warnings to show", include_pardoned="Also show removed warnings")
    async def warnings_list(self, interaction: discord.Interaction, member: discord.User, include_pardoned: bool = False):
        warns = ms.user_cases(interaction.guild.id, member.id, "warn", active_only=not include_pardoned)
        if not warns:
            return await interaction.response.send_message(f"{member} has no warnings.", ephemeral=True)
        lines = []
        for w in reversed(warns):
            ts = int(datetime.fromisoformat(w["timestamp"]).timestamp())
            flag = " ~~pardoned~~" if not w.get("active", True) else ""
            lines.append(f"`#{w['id']}`{flag} <t:{ts}:R> by <@{w['moderator_id']}>\n└ {w['reason'][:200]}")
        active = sum(1 for w in warns if w.get("active", True))
        pages = [discord.Embed(title=f"⚠️ Warnings for {member}", description=chunk, color=0xf1c40f)
                 .set_footer(text=f"{active} active") for chunk in chunk_lines(lines, 3800)]
        await Paginator(pages, interaction.user.id).send(interaction, ephemeral=True)

    @warnings.command(name="remove", description="Pardon a single warning by case number")
    @app_commands.describe(case_id="Case number of the warning")
    async def warnings_remove(self, interaction: discord.Interaction, case_id: int):
        case = ms.get_case(interaction.guild.id, case_id)
        if not case or case["action"] != "warn":
            return await interaction.response.send_message("❌ No warning with that case number.", ephemeral=True)
        ms.update_case(interaction.guild.id, case_id, active=False)
        await interaction.response.send_message(f"✅ Pardoned warning `#{case_id}` for <@{case['user_id']}>.")

    @warnings.command(name="clear", description="Pardon all of a member's warnings")
    @app_commands.describe(member="Whose warnings to clear")
    async def warnings_clear(self, interaction: discord.Interaction, member: discord.User):
        warns = ms.user_cases(interaction.guild.id, member.id, "warn", active_only=True)
        for w in warns:
            w["active"] = False
        ms.cases.save()
        await interaction.response.send_message(f"✅ Cleared {len(warns)} warning(s) from {member.mention}.")

    # ------------------------------------------------------------------ cases

    case = app_commands.Group(name="case", description="Moderation case log", guild_only=True,
                              default_permissions=discord.Permissions(moderate_members=True))

    @case.command(name="view", description="Show a single case")
    async def case_view(self, interaction: discord.Interaction, case_id: int):
        case = ms.get_case(interaction.guild.id, case_id)
        if not case:
            return await interaction.response.send_message("❌ Case not found.", ephemeral=True)
        await interaction.response.send_message(embed=ms.case_embed(case, interaction.guild), ephemeral=True)

    @case.command(name="reason", description="Edit the reason on a case")
    async def case_reason(self, interaction: discord.Interaction, case_id: int, reason: str):
        case = ms.update_case(interaction.guild.id, case_id, reason=reason)
        if not case:
            return await interaction.response.send_message("❌ Case not found.", ephemeral=True)
        await interaction.response.send_message(f"✅ Updated reason for case `#{case_id}`.", embed=ms.case_embed(case, interaction.guild))

    @case.command(name="history", description="Full moderation history (cases + notes) for a user")
    async def case_history(self, interaction: discord.Interaction, user: discord.User):
        await Paginator(self.history_pages(interaction.guild, user), interaction.user.id).send(interaction, ephemeral=True)

    # ------------------------------------------------------------------ notes

    note = app_commands.Group(name="note", description="Private moderator notes on users", guild_only=True,
                              default_permissions=discord.Permissions(moderate_members=True))

    @note.command(name="add", description="Add a private note to a user")
    async def note_add(self, interaction: discord.Interaction, user: discord.User, text: app_commands.Range[str, 1, 1000]):
        n = ms.add_note(interaction.guild.id, user.id, interaction.user.id, text)
        await interaction.response.send_message(f"📝 Added note `{n['id']}` to {user.mention}.", ephemeral=True)

    @note.command(name="list", description="List notes on a user")
    async def note_list(self, interaction: discord.Interaction, user: discord.User):
        notes = ms.get_notes(interaction.guild.id, user.id)
        if not notes:
            return await interaction.response.send_message(f"No notes on {user}.", ephemeral=True)
        lines = [f"`{n['id']}.` <t:{int(datetime.fromisoformat(n['timestamp']).timestamp())}:d> <@{n['moderator_id']}>\n{n['text']}"
                 for n in notes]
        pages = [discord.Embed(title=f"📝 Notes on {user}", description=c, color=0x95a5a6) for c in chunk_lines(lines, 3800)]
        await Paginator(pages, interaction.user.id).send(interaction, ephemeral=True)

    @note.command(name="remove", description="Delete a note")
    async def note_remove(self, interaction: discord.Interaction, user: discord.User, note_id: int):
        ok = ms.remove_note(interaction.guild.id, user.id, note_id)
        await interaction.response.send_message("✅ Note removed." if ok else "❌ Note not found.", ephemeral=True)

    # ------------------------------------------------------------------ messages / channels

    @app_commands.command(description="Bulk delete messages, with optional filters")
    @app_commands.describe(amount="How many recent messages to scan (1-1000)", user="Only delete this user's messages",
                           contains="Only delete messages containing this text", bots="Only delete messages from bots",
                           attachments="Only delete messages with files/images", links="Only delete messages with links")
    @app_commands.default_permissions(manage_messages=True)
    @app_commands.checks.has_permissions(manage_messages=True)
    @app_commands.checks.bot_has_permissions(manage_messages=True, read_message_history=True)
    async def purge(self, interaction: discord.Interaction, amount: app_commands.Range[int, 1, 1000],
                    user: Optional[discord.User] = None, contains: Optional[str] = None, bots: bool = False,
                    attachments: bool = False, links: bool = False):
        def check(m: discord.Message) -> bool:
            if m.pinned:
                return False
            if user and m.author.id != user.id:
                return False
            if contains and contains.lower() not in m.content.lower():
                return False
            if bots and not m.author.bot:
                return False
            if attachments and not m.attachments:
                return False
            if links and "http://" not in m.content and "https://" not in m.content:
                return False
            return True

        await interaction.response.defer(ephemeral=True)
        deleted = await interaction.channel.purge(limit=amount, check=check, reason=f"Purge by {interaction.user}")
        await interaction.followup.send(f"🧹 Deleted **{len(deleted)}** message(s).", ephemeral=True)
        embed = discord.Embed(title="Messages purged", color=0xe67e22, timestamp=datetime.now(timezone.utc),
                              description=f"**{len(deleted)}** messages in {interaction.channel.mention} by {interaction.user.mention}")
        await ms.send_modlog(interaction.guild, embed)

    @app_commands.command(description="Set slowmode for a channel")
    @app_commands.describe(seconds="Seconds between messages (0 to disable, max 21600)", channel="Channel (defaults to this one)")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_channels=True)
    async def slowmode(self, interaction: discord.Interaction, seconds: app_commands.Range[int, 0, 21600],
                       channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        await channel.edit(slowmode_delay=seconds)
        msg = "disabled" if seconds == 0 else f"set to **{seconds}s**"
        await interaction.response.send_message(f"🐢 Slowmode {msg} in {channel.mention}.")

    async def _set_send(self, channel: discord.TextChannel, value: Optional[bool], reason: str):
        everyone = channel.guild.default_role
        ow = channel.overwrites_for(everyone)
        ow.send_messages = value
        ow.send_messages_in_threads = value
        ow.create_public_threads = value
        ow.add_reactions = value
        await channel.set_permissions(everyone, overwrite=ow, reason=reason)

    @app_commands.command(description="Lock a channel so regular members can't send messages")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def lock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None,
                   reason: Optional[str] = None):
        channel = channel or interaction.channel
        await self._set_send(channel, False, f"Locked by {interaction.user}: {reason or 'no reason'}")
        await interaction.response.send_message(f"🔒 {channel.mention} locked." + (f"\n**Reason:** {reason}" if reason else ""))

    @app_commands.command(description="Unlock a channel")
    @app_commands.default_permissions(manage_channels=True)
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def unlock(self, interaction: discord.Interaction, channel: Optional[discord.TextChannel] = None):
        channel = channel or interaction.channel
        await self._set_send(channel, None, f"Unlocked by {interaction.user}")
        await interaction.response.send_message(f"🔓 {channel.mention} unlocked.")

    lockdown = app_commands.Group(name="lockdown", description="Lock every text channel at once", guild_only=True,
                                  default_permissions=discord.Permissions(manage_guild=True))

    @lockdown.command(name="start", description="Lock all text channels (remembers previous state)")
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def lockdown_start(self, interaction: discord.Interaction, reason: Optional[str] = None):
        cfg = ms.guild_config(interaction.guild.id)
        if cfg.get("lockdown"):
            return await interaction.response.send_message("❌ The server is already in lockdown. Use `/lockdown end` first.", ephemeral=True)
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message("⚠️ Lock **every** text channel?", view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return
        everyone = interaction.guild.default_role
        saved = {}
        for channel in interaction.guild.text_channels:
            ow = channel.overwrites_for(everyone)
            if ow.send_messages is False:
                continue  # already locked; leave it alone on unlock too
            saved[str(channel.id)] = ow.send_messages
            try:
                await self._set_send(channel, False, f"Lockdown by {interaction.user}: {reason or 'no reason'}")
            except discord.HTTPException:
                saved.pop(str(channel.id))
        cfg["lockdown"] = saved
        ms.save_config()
        await interaction.channel.send(f"🚨 **Server lockdown** — {len(saved)} channels locked." + (f"\n**Reason:** {reason}" if reason else ""))
        await ms.send_modlog(interaction.guild, discord.Embed(title="🚨 Lockdown started", color=0xe74c3c,
                             description=f"By {interaction.user.mention}: {reason or 'no reason'}"))

    @lockdown.command(name="end", description="Restore channels locked by /lockdown start")
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def lockdown_end(self, interaction: discord.Interaction):
        cfg = ms.guild_config(interaction.guild.id)
        saved = cfg.get("lockdown")
        if not saved:
            return await interaction.response.send_message("❌ The server isn't in lockdown.", ephemeral=True)
        await interaction.response.defer()
        restored = 0
        for cid, previous in saved.items():
            channel = interaction.guild.get_channel(int(cid))
            if channel:
                try:
                    await self._set_send(channel, previous, f"Lockdown ended by {interaction.user}")
                    restored += 1
                except discord.HTTPException:
                    pass
        cfg.pop("lockdown", None)
        ms.save_config()
        await interaction.followup.send(f"✅ Lockdown ended — {restored} channels restored.")
        await ms.send_modlog(interaction.guild, discord.Embed(title="✅ Lockdown ended", color=0x2ecc71,
                             description=f"By {interaction.user.mention}"))

    # ------------------------------------------------------------------ members / roles

    @app_commands.command(description="Change or reset a member's nickname")
    @app_commands.describe(member="Member", nickname="New nickname (leave empty to reset)")
    @app_commands.default_permissions(manage_nicknames=True)
    @app_commands.checks.has_permissions(manage_nicknames=True)
    @app_commands.checks.bot_has_permissions(manage_nicknames=True)
    async def nick(self, interaction: discord.Interaction, member: discord.Member,
                   nickname: Optional[app_commands.Range[str, 1, 32]] = None):
        if member.id != interaction.user.id and (err := hierarchy_error(interaction, member)):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await member.edit(nick=nickname, reason=f"By {interaction.user}")
        await interaction.response.send_message(
            f"✅ {'Set' if nickname else 'Reset'} nickname for {member.mention}" + (f" to **{nickname}**." if nickname else "."))

    role = app_commands.Group(name="role", description="Role management", guild_only=True,
                              default_permissions=discord.Permissions(manage_roles=True))

    @role.command(name="add", description="Give a role to a member")
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def role_add(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if err := role_error(interaction, role):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await member.add_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ Gave {role.mention} to {member.mention}.",
                                                allowed_mentions=discord.AllowedMentions.none())

    @role.command(name="remove", description="Remove a role from a member")
    @app_commands.checks.bot_has_permissions(manage_roles=True)
    async def role_remove(self, interaction: discord.Interaction, member: discord.Member, role: discord.Role):
        if err := role_error(interaction, role):
            return await interaction.response.send_message(f"❌ {err}", ephemeral=True)
        await member.remove_roles(role, reason=f"By {interaction.user}")
        await interaction.response.send_message(f"✅ Removed {role.mention} from {member.mention}.",
                                                allowed_mentions=discord.AllowedMentions.none())

    @role.command(name="info", description="Show information about a role")
    async def role_info(self, interaction: discord.Interaction, role: discord.Role):
        embed = discord.Embed(title=f"Role: {role.name}", color=role.color)
        embed.add_field(name="ID", value=f"`{role.id}`")
        embed.add_field(name="Members", value=str(len(role.members)))
        embed.add_field(name="Position", value=str(role.position))
        embed.add_field(name="Color", value=str(role.color))
        embed.add_field(name="Hoisted", value="Yes" if role.hoist else "No")
        embed.add_field(name="Mentionable", value="Yes" if role.mentionable else "No")
        embed.add_field(name="Created", value=f"<t:{int(role.created_at.timestamp())}:R>")
        perms = [p.replace("_", " ").title() for p, v in role.permissions if v]
        embed.add_field(name="Key permissions", value=", ".join(perms)[:1024] or "None", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @role.command(name="list", description="List all server roles")
    async def role_list(self, interaction: discord.Interaction):
        roles = sorted(interaction.guild.roles[1:], key=lambda r: r.position, reverse=True)
        lines = [f"{r.mention} — {len(r.members)} members" for r in roles]
        pages = [discord.Embed(title=f"Roles ({len(roles)})", description=c, color=0x3498db) for c in chunk_lines(lines, 3800)]
        await Paginator(pages, interaction.user.id).send(interaction, ephemeral=True)

    # ------------------------------------------------------------------ voice moderation

    vc = app_commands.Group(name="vc", description="Voice channel moderation", guild_only=True,
                            default_permissions=discord.Permissions(move_members=True))

    async def _vc_edit(self, interaction: discord.Interaction, member: discord.Member, done: str, **kwargs):
        if not member.voice:
            return await interaction.response.send_message(f"❌ {member.mention} isn't in a voice channel.", ephemeral=True)
        await member.edit(reason=f"By {interaction.user}", **kwargs)
        await interaction.response.send_message(f"✅ {done} {member.mention}.")

    @vc.command(name="move", description="Move a member to another voice channel")
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def vc_move(self, interaction: discord.Interaction, member: discord.Member, channel: discord.VoiceChannel):
        await self._vc_edit(interaction, member, f"Moved to {channel.mention}:", voice_channel=channel)

    @vc.command(name="moveall", description="Move everyone from one voice channel to another")
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def vc_moveall(self, interaction: discord.Interaction, source: discord.VoiceChannel, destination: discord.VoiceChannel):
        await interaction.response.defer()
        moved = 0
        for m in list(source.members):
            try:
                await m.move_to(destination, reason=f"Moveall by {interaction.user}")
                moved += 1
            except discord.HTTPException:
                pass
        await interaction.followup.send(f"✅ Moved {moved} member(s) from {source.mention} to {destination.mention}.")

    @vc.command(name="disconnect", description="Disconnect a member from voice")
    @app_commands.checks.bot_has_permissions(move_members=True)
    async def vc_disconnect(self, interaction: discord.Interaction, member: discord.Member):
        await self._vc_edit(interaction, member, "Disconnected", voice_channel=None)

    @vc.command(name="mute", description="Server-mute or unmute a member")
    @app_commands.checks.bot_has_permissions(mute_members=True)
    async def vc_mute(self, interaction: discord.Interaction, member: discord.Member, muted: bool = True):
        await self._vc_edit(interaction, member, "Muted" if muted else "Unmuted", mute=muted)

    @vc.command(name="deafen", description="Server-deafen or undeafen a member")
    @app_commands.checks.bot_has_permissions(deafen_members=True)
    async def vc_deafen(self, interaction: discord.Interaction, member: discord.Member, deafened: bool = True):
        await self._vc_edit(interaction, member, "Deafened" if deafened else "Undeafened", deafen=deafened)

    # ------------------------------------------------------------------ info

    @app_commands.command(description="Show server information")
    async def serverinfo(self, interaction: discord.Interaction):
        g = interaction.guild
        embed = discord.Embed(title=g.name, description=g.description or "", color=0x3498db)
        if g.icon:
            embed.set_thumbnail(url=g.icon.url)
        humans = sum(1 for m in g.members if not m.bot)
        embed.add_field(name="Owner", value=f"<@{g.owner_id}>")
        embed.add_field(name="Members", value=f"{g.member_count} ({humans} humans)")
        embed.add_field(name="Created", value=f"<t:{int(g.created_at.timestamp())}:R>")
        embed.add_field(name="Channels", value=f"{len(g.text_channels)} text • {len(g.voice_channels)} voice")
        embed.add_field(name="Roles", value=str(len(g.roles)))
        embed.add_field(name="Boosts", value=f"Level {g.premium_tier} ({g.premium_subscription_count})")
        embed.add_field(name="Verification", value=str(g.verification_level).title())
        cases_total = len(ms.cases.guild(g.id).get("cases", {}))
        embed.add_field(name="Mod cases", value=str(cases_total))
        embed.set_footer(text=f"ID: {g.id}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="List banned users")
    @app_commands.default_permissions(ban_members=True)
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.checks.bot_has_permissions(ban_members=True)
    async def banlist(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        bans = [e async for e in interaction.guild.bans(limit=None)]
        if not bans:
            return await interaction.followup.send("No bans.", ephemeral=True)
        lines = [f"**{e.user}** (`{e.user.id}`) — {(e.reason or 'no reason')[:80]}" for e in bans]
        pages = [discord.Embed(title=f"Bans ({len(bans)})", description=c, color=0xe74c3c) for c in chunk_lines(lines, 3800)]
        await Paginator(pages, interaction.user.id).send(interaction, ephemeral=True)

    # ------------------------------------------------------------------ tempban expiry

    def _close_tempbans(self, guild_id: int, user_id: int):
        for c in ms.user_cases(guild_id, user_id, "tempban", active_only=True):
            c["active"] = False
        ms.cases.save()

    @tasks.loop(minutes=1)
    async def expire_tempbans(self):
        now = datetime.now(timezone.utc)
        for gid, guild_cases in ms.all_guild_cases().items():
            guild = self.bot.get_guild(int(gid))
            if guild is None:
                continue
            for case in list(guild_cases.values()):
                if case["action"] != "tempban" or not case.get("active") or not case.get("expires"):
                    continue
                if datetime.fromisoformat(case["expires"]) > now:
                    continue
                case["active"] = False
                ms.cases.save()
                try:
                    user = await self.bot.fetch_user(case["user_id"])
                    await guild.unban(user, reason=f"Tempban expired (case #{case['id']})")
                    await self.record(guild, "unban", user, guild.me, f"Tempban expired (case #{case['id']})")
                except discord.HTTPException:
                    pass

    @expire_tempbans.before_loop
    async def before_expire(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Moderation(bot))
