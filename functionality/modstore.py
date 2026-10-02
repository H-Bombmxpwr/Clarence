# functionality/modstore.py
"""Shared moderation storage: per-guild config, case log, mod notes, and log-channel helpers."""
from datetime import datetime, timezone
from typing import Optional

import discord

from functionality.store import JsonStore

config = JsonStore("guild_config.json")
cases = JsonStore("cases.json")
notes = JsonStore("notes.json")

CASE_COLORS = {
    "ban": 0xe74c3c, "tempban": 0xe74c3c, "softban": 0xe67e22, "unban": 0x2ecc71,
    "kick": 0xf39c12, "timeout": 0x9b59b6, "untimeout": 0x2ecc71, "warn": 0xf1c40f,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------- config ----------------

def guild_config(guild_id: int) -> dict:
    return config.guild(guild_id)


def save_config() -> None:
    config.save()


# ---------------- cases ----------------

def _guild_cases(guild_id: int) -> dict:
    g = cases.guild(guild_id)
    g.setdefault("next_id", 1)
    g.setdefault("cases", {})
    return g


def add_case(guild_id: int, action: str, user_id: int, moderator_id: int, reason: str,
             duration: Optional[int] = None, expires: Optional[str] = None) -> dict:
    g = _guild_cases(guild_id)
    case_id = g["next_id"]
    g["next_id"] += 1
    case = {
        "id": case_id,
        "action": action,
        "user_id": user_id,
        "moderator_id": moderator_id,
        "reason": reason,
        "timestamp": now_iso(),
        "duration": duration,   # seconds, for timeouts/tempbans
        "expires": expires,     # ISO time, for tempbans
        "active": True,         # warns: False once pardoned; tempbans: False once lifted
    }
    g["cases"][str(case_id)] = case
    cases.save()
    return case


def get_case(guild_id: int, case_id: int) -> Optional[dict]:
    return _guild_cases(guild_id)["cases"].get(str(case_id))


def update_case(guild_id: int, case_id: int, **fields) -> Optional[dict]:
    case = get_case(guild_id, case_id)
    if case:
        case.update(fields)
        cases.save()
    return case


def user_cases(guild_id: int, user_id: int, action: Optional[str] = None, active_only: bool = False) -> list[dict]:
    result = [
        c for c in _guild_cases(guild_id)["cases"].values()
        if c["user_id"] == user_id
        and (action is None or c["action"] == action)
        and (not active_only or c.get("active", True))
    ]
    return sorted(result, key=lambda c: c["id"])


def all_guild_cases() -> dict[str, dict]:
    return {gid: g.get("cases", {}) for gid, g in cases.data.items()}


def migrate_legacy_warnings() -> None:
    """One-time import of the old storage/warnings.json format into the case log."""
    legacy = JsonStore("warnings.json")
    if not legacy.data or cases.data.get("_migrated_warnings"):
        return
    for gid, users in legacy.data.items():
        for uid, warns in users.items():
            for w in warns:
                case = add_case(int(gid), "warn", int(uid), int(w.get("mod_id", 0)), w.get("reason", "No reason"))
                if w.get("timestamp"):
                    case["timestamp"] = w["timestamp"]
    cases.data["_migrated_warnings"] = True
    cases.save()


# ---------------- notes ----------------

def add_note(guild_id: int, user_id: int, moderator_id: int, text: str) -> dict:
    user_notes = notes.guild(guild_id).setdefault(str(user_id), [])
    note_id = max((n["id"] for n in user_notes), default=0) + 1
    note = {"id": note_id, "text": text, "moderator_id": moderator_id, "timestamp": now_iso()}
    user_notes.append(note)
    notes.save()
    return note


def get_notes(guild_id: int, user_id: int) -> list[dict]:
    return notes.guild(guild_id).get(str(user_id), [])


def remove_note(guild_id: int, user_id: int, note_id: int) -> bool:
    user_notes = notes.guild(guild_id).get(str(user_id), [])
    for n in user_notes:
        if n["id"] == note_id:
            user_notes.remove(n)
            notes.save()
            return True
    return False


# ---------------- log channels ----------------

async def _send_to(guild: discord.Guild, channel_id: Optional[int], embed: discord.Embed) -> None:
    if not channel_id:
        return
    channel = guild.get_channel(channel_id)
    if channel is None:
        return
    try:
        await channel.send(embed=embed)
    except discord.HTTPException:
        pass


async def send_modlog(guild: discord.Guild, embed: discord.Embed) -> None:
    """Moderator actions (bans, warns, automod hits...)."""
    await _send_to(guild, guild_config(guild.id).get("log_channel_id"), embed)


async def send_eventlog(guild: discord.Guild, embed: discord.Embed) -> None:
    """Server events (edits, deletes, joins, role changes...). Falls back to the mod log."""
    cfg = guild_config(guild.id)
    await _send_to(guild, cfg.get("event_log_channel_id") or cfg.get("log_channel_id"), embed)


def log_channel_ids(guild_id: int) -> set[int]:
    cfg = guild_config(guild_id)
    return {cid for cid in (cfg.get("log_channel_id"), cfg.get("event_log_channel_id")) if cid}


def case_embed(case: dict, guild: discord.Guild) -> discord.Embed:
    action = case["action"]
    title = f"Case #{case['id']} • {action.title()}"
    if action == "warn" and not case.get("active", True):
        title += " (pardoned)"
    embed = discord.Embed(
        title=title,
        color=CASE_COLORS.get(action, 0x95a5a6),
        timestamp=datetime.fromisoformat(case["timestamp"]),
    )
    member = guild.get_member(case["user_id"])
    embed.add_field(name="User", value=f"{member.mention if member else '<@%d>' % case['user_id']} (`{case['user_id']}`)", inline=True)
    embed.add_field(name="Moderator", value=f"<@{case['moderator_id']}>", inline=True)
    if case.get("duration"):
        from datetime import timedelta
        from functionality.ui import format_duration
        embed.add_field(name="Duration", value=format_duration(timedelta(seconds=case["duration"])), inline=True)
    if case.get("expires"):
        ts = int(datetime.fromisoformat(case["expires"]).timestamp())
        embed.add_field(name="Expires", value=f"<t:{ts}:R>", inline=True)
    embed.add_field(name="Reason", value=case.get("reason") or "No reason", inline=False)
    return embed
