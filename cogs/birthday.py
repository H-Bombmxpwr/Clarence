# cogs/birthday.py
import discord
from discord.ext import commands, tasks
from datetime import datetime, timedelta, timezone, time as dt_time
import json
import os
import random

OWNER_ID = 239605426033786881
TARGET_ID = 368894819109568533
STORAGE_PATH = "storage/birthday_watch.json"

TZ_OFFSET_HOURS = -6  # CST
ASK_WINDOW_START_HOUR = 9   # 9 AM local
ASK_WINDOW_END_HOUR = 21    # 9 PM local


def _now_local() -> datetime:
    """Naive local-time datetime (CST)."""
    return (datetime.now(timezone.utc) + timedelta(hours=TZ_OFFSET_HOURS)).replace(tzinfo=None)


def _load_state() -> dict:
    try:
        with open(STORAGE_PATH, "r") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"active": False, "next_ask_iso": None, "last_asked_date": None}


def _save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
    with open(STORAGE_PATH, "w") as f:
        json.dump(state, f, indent=4)


def _random_time_on(d) -> datetime:
    hour = random.randint(ASK_WINDOW_START_HOUR, ASK_WINDOW_END_HOUR - 1)
    minute = random.randint(0, 59)
    return datetime.combine(d, dt_time(hour=hour, minute=minute))


def _schedule_next(after: datetime) -> datetime:
    """Pick a random time in today's remaining window, or tomorrow if window is past."""
    today_candidate = _random_time_on(after.date())
    if today_candidate > after:
        return today_candidate
    return _random_time_on(after.date() + timedelta(days=1))


class BirthdayView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Yes", style=discord.ButtonStyle.success, custom_id="bday_yes_persist")
    async def yes_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != TARGET_ID:
            return await interaction.response.send_message("This isn't for you.", ephemeral=True)

        await interaction.response.edit_message(content="🎉 Happy Birthday!", view=None)

        try:
            owner = await interaction.client.fetch_user(OWNER_ID)
            await owner.send(
                f"🎂 It's {interaction.user} ({interaction.user.id})'s birthday today!"
            )
        except Exception as e:
            print(f"[birthday] failed to notify owner: {e}")

        state = _load_state()
        state["active"] = False
        state["next_ask_iso"] = None
        _save_state(state)

    @discord.ui.button(label="No", style=discord.ButtonStyle.secondary, custom_id="bday_no_persist")
    async def no_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != TARGET_ID:
            return await interaction.response.send_message("This isn't for you.", ephemeral=True)
        await interaction.response.edit_message(content="Alright, no worries!", view=None)


class Birthday(commands.Cog):
    """Hidden owner-only birthday watcher."""
    __cog_command_attrs__ = {"hidden": True}

    def __init__(self, client: commands.Bot):
        self.client = client

    async def cog_load(self):
        self.client.add_view(BirthdayView())
        self.scheduler.start()

    def cog_unload(self):
        self.scheduler.cancel()

    def _is_owner(self, user_id: int) -> bool:
        return user_id == OWNER_ID

    async def _ask_target(self) -> tuple[bool, str]:
        try:
            user = self.client.get_user(TARGET_ID)
            if user is None:
                user = await self.client.fetch_user(TARGET_ID)
        except discord.NotFound:
            return False, f"user id {TARGET_ID} not found"
        except Exception as e:
            return False, f"fetch_user error: {type(e).__name__}: {e}"

        try:
            await user.send("Hey — is it your birthday today?", view=BirthdayView())
            return True, f"sent to {user} ({user.id})"
        except discord.Forbidden:
            return False, f"{user} has DMs closed or blocked the bot"
        except discord.HTTPException as e:
            return False, f"HTTP {e.status}: {e.text}"
        except Exception as e:
            return False, f"{type(e).__name__}: {e}"

    @commands.command(name="bday_start", hidden=True)
    async def bday_start(self, ctx: commands.Context):
        if not self._is_owner(ctx.author.id):
            return

        now = _now_local()
        next_ask = _schedule_next(now)
        state = {
            "active": True,
            "next_ask_iso": next_ask.isoformat(),
            "last_asked_date": None,
        }
        _save_state(state)

        try:
            await ctx.author.send(
                f"✅ Birthday watch started.\nNext ask scheduled for `{next_ask.isoformat()}` (CST).\n"
                f"DM me `ask` to trigger manually. `$bday_stop` to cancel."
            )
        except Exception:
            await ctx.send("✅ Started.")

    @commands.command(name="bday_stop", hidden=True)
    async def bday_stop(self, ctx: commands.Context):
        if not self._is_owner(ctx.author.id):
            return
        state = _load_state()
        state["active"] = False
        state["next_ask_iso"] = None
        _save_state(state)
        try:
            await ctx.author.send("🛑 Birthday watch stopped.")
        except Exception:
            await ctx.send("🛑 Stopped.")

    @commands.command(name="bday_status", hidden=True)
    async def bday_status(self, ctx: commands.Context):
        if not self._is_owner(ctx.author.id):
            return
        state = _load_state()
        try:
            await ctx.author.send(f"```json\n{json.dumps(state, indent=2)}\n```")
        except Exception:
            pass

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Manual trigger: owner DMs the bot the word "ask".
        if message.author.id != OWNER_ID:
            return
        if message.guild is not None:
            return
        if message.content.strip().lower() != "ask":
            return

        sent, reason = await self._ask_target()
        if sent:
            state = _load_state()
            state["last_asked_date"] = _now_local().date().isoformat()
            _save_state(state)
            await message.channel.send(f"✅ {reason}")
        else:
            await message.channel.send(f"❌ DM failed: {reason}")

    @tasks.loop(minutes=1)
    async def scheduler(self):
        state = _load_state()
        if not state.get("active"):
            return
        next_iso = state.get("next_ask_iso")
        if not next_iso:
            return

        try:
            next_ask = datetime.fromisoformat(next_iso)
        except ValueError:
            return

        now = _now_local()
        if now < next_ask:
            return

        today_str = now.date().isoformat()
        if state.get("last_asked_date") != today_str:
            sent, reason = await self._ask_target()
            if sent:
                state["last_asked_date"] = today_str
            else:
                print(f"[birthday] scheduled ask failed: {reason}")

        state["next_ask_iso"] = _schedule_next(now).isoformat()
        _save_state(state)

    @scheduler.before_loop
    async def before_scheduler(self):
        await self.client.wait_until_ready()


async def setup(client: commands.Bot):
    await client.add_cog(Birthday(client))
