# cogs/trivia.py
import json, os, asyncio, discord
from discord.ext import commands
import functionality.functions as funcs

TRIVIA_FILE = "storage/trivia.json"

def _load_trivia_stats():
    os.makedirs(os.path.dirname(TRIVIA_FILE), exist_ok=True)
    if not os.path.exists(TRIVIA_FILE):
        with open(TRIVIA_FILE, "w") as f:
            json.dump({}, f)
    with open(TRIVIA_FILE, "r") as f:
        try:
            return json.load(f)
        except:
            return {}

def _save_trivia_stats(data):
    with open(TRIVIA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def _bump_stats(guild_id: int, user_id: int, correct: bool):
    data = _load_trivia_stats()
    g = data.setdefault(str(guild_id), {})
    u = g.setdefault(str(user_id), {"correct": 0, "attempts": 0})
    u["attempts"] += 1
    if correct:
        u["correct"] += 1
    _save_trivia_stats(data)
    return u

def _get_stats(guild_id: int, user_id: int):
    data = _load_trivia_stats()
    g = data.get(str(guild_id), {})
    return g.get(str(user_id), {"correct": 0, "attempts": 0})

def _normalize_question(raw):
    if raw is None:
        raise ValueError("Question source returned None")
    if hasattr(raw, "question") and hasattr(raw, "correctAnswer"):
        answers = list(raw.getAnswerList()) if hasattr(raw, "getAnswerList") else []
        return {
            "category": getattr(raw, "category", "General"),
            "question": getattr(raw, "question"),
            "correct": getattr(raw, "correctAnswer"),
            "answers": answers,
        }
    if isinstance(raw, dict):
        answers = raw.get("answers") or raw.get("answer_list") or []
        return {
            "category": raw.get("category", "General"),
            "question": raw.get("question"),
            "correct": raw.get("correctAnswer") or raw.get("correct"),
            "answers": list(answers),
        }
    raise ValueError(f"Unrecognized question format: {type(raw)}")


class Trivia(commands.Cog):
    """Trivia Games"""
    def __init__(self, client):
        self.client = client

    @commands.command(help="Play interactive trivia!", aliases=["tri"])
    async def trivia(self, ctx):
        try:
            raw = funcs.get_question2()
            q = _normalize_question(raw)
        except Exception as e:
            return await ctx.send(f"❌ Trivia error: {e}")

        category = q.get("category") or "General"
        question = q.get("question")
        correct = q.get("correct")
        answers = q.get("answers")

        if not question or not correct or not answers or len(answers) != 4:
            return await ctx.send("❌ Question data malformed.")

        if correct not in answers:
            answers = list(answers) + [correct]
            answers = list(dict.fromkeys(answers))[:4]

        letter_map = "abcd"
        correct_idx = answers.index(correct)
        correct_key = letter_map[correct_idx]

        lines = [f"{letter_map[i]}. {answers[i]}" for i in range(4)]
        embed = discord.Embed(
            title="Trivia",
            description=f"**Category:** {category}",
            color=0x8b0000
        )
        embed.add_field(name=question, value="\n".join(lines), inline=False)
        embed.set_footer(text=f"{ctx.author.name}, reply with a/b/c/d")
        await ctx.send(embed=embed)

        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            return await ctx.send("Time's up!")

        user_reply = msg.content.strip().lower()
        is_letter = user_reply in list(letter_map)
        guess_idx = letter_map.index(user_reply) if is_letter else None
        is_correct = (guess_idx == correct_idx) if is_letter else (user_reply == correct.lower())

        await msg.add_reaction('✅' if is_correct else '❌')
        if is_correct:
            await ctx.send(f"✅ Correct! It was **{correct}**")
        else:
            await ctx.send(f"❌ Wrong! The answer was **{correct}**")

        _bump_stats(ctx.guild.id, ctx.author.id, is_correct)

    @commands.command(help="View trivia stats", aliases=["ts"])
    async def trivia_stats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        stats = _get_stats(ctx.guild.id, member.id)
        pct = (100.0 * stats["correct"] / stats["attempts"]) if stats["attempts"] else 0.0

        embed = discord.Embed(title="📊 Trivia Stats", description=f"Stats for {member.display_name}", color=0x2e8b57)
        embed.add_field(name="Correct", value=str(stats["correct"]), inline=True)
        embed.add_field(name="Attempts", value=str(stats["attempts"]), inline=True)
        embed.add_field(name="Accuracy", value=f"{pct:.1f}%", inline=True)
        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(Trivia(client))