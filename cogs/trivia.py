# cogs/trivia.py
import html
import random
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from functionality.store import JsonStore

stats = JsonStore("trivia.json")
LETTERS = "ABCD"


def bump_stats(guild_id: int, user_id: int, correct: bool) -> dict:
    u = stats.guild(guild_id).setdefault(str(user_id), {"correct": 0, "attempts": 0, "streak": 0, "best_streak": 0})
    u.setdefault("streak", 0)
    u.setdefault("best_streak", 0)
    u["attempts"] += 1
    if correct:
        u["correct"] += 1
        u["streak"] += 1
        u["best_streak"] = max(u["best_streak"], u["streak"])
    else:
        u["streak"] = 0
    stats.save()
    return u


class TriviaView(discord.ui.View):
    def __init__(self, player: discord.abc.User, guild_id: int, answers: list[str], correct_idx: int):
        super().__init__(timeout=30)
        self.player = player
        self.guild_id = guild_id
        self.answers = answers
        self.correct_idx = correct_idx
        self.message: Optional[discord.Message] = None
        for i, answer in enumerate(answers):
            button = discord.ui.Button(label=f"{LETTERS[i]}. {answer}"[:80], style=discord.ButtonStyle.secondary, row=i // 2)
            button.callback = self.make_callback(i)
            self.add_item(button)

    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.id:
                return await interaction.response.send_message("This isn't your question — use `/trivia play`!", ephemeral=True)
            self.stop()
            correct = idx == self.correct_idx
            self.reveal(idx)
            u = bump_stats(self.guild_id, self.player.id, correct) if self.guild_id else None
            streak = f" • streak {u['streak']}" if u and correct and u["streak"] > 1 else ""
            text = f"Correct!{streak}" if correct else f"Wrong! It was **{self.answers[self.correct_idx]}**"
            await interaction.response.edit_message(content=text, view=self)
        return callback

    def reveal(self, picked: Optional[int]):
        for i, item in enumerate(self.children):
            item.disabled = True
            if i == self.correct_idx:
                item.style = discord.ButtonStyle.success
            elif i == picked:
                item.style = discord.ButtonStyle.danger

    async def on_timeout(self):
        self.reveal(None)
        if self.guild_id:
            bump_stats(self.guild_id, self.player.id, False)
        if self.message:
            try:
                await self.message.edit(content=f"Time's up! It was **{self.answers[self.correct_idx]}**", view=self)
            except discord.HTTPException:
                pass


class Trivia(commands.Cog):
    """Trivia Games"""

    trivia = app_commands.Group(name="trivia", description="Trivia questions")

    def __init__(self, client):
        self.client = client

    @trivia.command(name="play", description="Answer a multiple-choice trivia question")
    @app_commands.choices(difficulty=[app_commands.Choice(name=d.title(), value=d) for d in ("easy", "medium", "hard")])
    async def play(self, interaction: discord.Interaction, difficulty: Optional[app_commands.Choice[str]] = None):
        params = {"amount": 1, "type": "multiple"}
        if difficulty:
            params["difficulty"] = difficulty.value
        try:
            async with self.client.session.get("https://opentdb.com/api.php", params=params, timeout=10) as r:
                data = await r.json(content_type=None)
            q = data["results"][0]
        except Exception:
            return await interaction.response.send_message("The trivia API is busy — try again in a few seconds.", ephemeral=True)

        correct = html.unescape(q["correct_answer"])
        answers = [correct] + [html.unescape(a) for a in q["incorrect_answers"]]
        random.shuffle(answers)
        embed = discord.Embed(title=html.unescape(q["question"])[:256], color=0x8b0000,
                              description=f"**Category:** {html.unescape(q['category'])} • **{q['difficulty'].title()}**")
        embed.set_footer(text=f"{interaction.user.display_name}, you have 30 seconds")
        view = TriviaView(interaction.user, interaction.guild_id or 0, answers, answers.index(correct))
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @trivia.command(name="stats", description="View trivia stats")
    @app_commands.guild_only()
    async def stats_cmd(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        s = stats.guild(interaction.guild_id).get(str(member.id), {"correct": 0, "attempts": 0})
        pct = (100.0 * s["correct"] / s["attempts"]) if s["attempts"] else 0.0
        embed = discord.Embed(title="Trivia Stats", description=f"Stats for {member.display_name}", color=0x2e8b57)
        embed.add_field(name="Correct", value=str(s["correct"]))
        embed.add_field(name="Attempts", value=str(s["attempts"]))
        embed.add_field(name="Accuracy", value=f"{pct:.1f}%")
        embed.add_field(name="Best streak", value=str(s.get("best_streak", 0)))
        await interaction.response.send_message(embed=embed)

    @trivia.command(name="leaderboard", description="Top trivia players on this server")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction):
        rows = sorted(stats.guild(interaction.guild_id).items(), key=lambda kv: kv[1]["correct"], reverse=True)[:10]
        if not rows:
            return await interaction.response.send_message("Nobody has played yet!", ephemeral=True)
        lines = [f"`{i}.` <@{uid}> — **{s['correct']}** correct ({100 * s['correct'] / max(s['attempts'], 1):.0f}%)"
                 for i, (uid, s) in enumerate(rows, 1)]
        await interaction.response.send_message(embed=discord.Embed(title="Trivia leaderboard", description="\n".join(lines), color=0xffd700),
                                                allowed_mentions=discord.AllowedMentions.none())


async def setup(client):
    await client.add_cog(Trivia(client))
