# cogs/trivia.py
import json, os, asyncio, discord
from discord.ext import commands

# ✅ make sure this import is present
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
        except Exception:
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

# ---------- question normalization ----------

def _normalize_question(raw):
    """
    Accepts multiple shapes and returns:
    {
      'category': str,
      'question': str,
      'correct': str,
      'answers': [str, str, str, str]
    }
    """
    if raw is None:
        raise ValueError("Question source returned None")

    # object style
    if hasattr(raw, "question") and hasattr(raw, "correctAnswer"):
        answers = None
        if hasattr(raw, "getAnswerList") and callable(raw.getAnswerList):
            answers = list(raw.getAnswerList() or [])
        elif hasattr(raw, "answers"):
            answers = list(getattr(raw, "answers") or [])
        return {
            "category": getattr(raw, "category", "General"),
            "question": getattr(raw, "question"),
            "correct": getattr(raw, "correctAnswer"),
            "answers": answers,
        }

    # dict style
    if isinstance(raw, dict):
        answers = raw.get("answers") or raw.get("answer_list") or raw.get("options")
        if answers is not None:
            answers = list(answers)
        return {
            "category": raw.get("category", "General"),
            "question": raw.get("question"),
            "correct": raw.get("correctAnswer") or raw.get("correct") or raw.get("answer"),
            "answers": answers,
        }

    # fallback
    raise ValueError(f"Unrecognized question format: {type(raw)}")

class Trivia(commands.Cog):
    def __init__(self, client):
        self.client = client

    @commands.command(help="Interactive trivia", aliases=["tr"])
    async def trivia(self, ctx):
        # fetch & normalize
        try:
            raw = funcs.get_question2()
            q = _normalize_question(raw)
        except Exception as e:
            await ctx.send(f"Trivia source error: {e}")
            return

        # validate payload
        category = q.get("category") or "General"
        question = q.get("question")
        correct = q.get("correct")
        answers = q.get("answers")

        if not question or not correct or not answers:
            await ctx.send("Question data malformed (missing fields).")
            return
        if len(answers) != 4:
            await ctx.send("Question must have exactly 4 answer choices.")
            return
        if correct not in answers:
            # if source forgot to include the correct option, append it and trim to 4
            answers = list(answers) + [correct]
            # de-duplicate while preserving order
            seen, fixed = set(), []
            for a in answers:
                if a not in seen:
                    seen.add(a)
                    fixed.append(a)
            answers = fixed[:4]
            if correct not in answers:
                await ctx.send("Correct answer not present in choice list.")
                return

        # map a/b/c/d -> index
        letter_map = "abcd"
        try:
            correct_idx = answers.index(correct)
        except ValueError:
            await ctx.send("Correct answer index resolution failed.")
            return
        correct_key = letter_map[correct_idx]

        # embed
        lines = [f"{letter_map[i]}. {answers[i]}" for i in range(4)]
        embed = discord.Embed(
            title="Random Trivia Question",
            description=f"Category: {category}",
            color=0x8b0000
        )
        embed.add_field(
            name=question,
            value="\n".join(lines),
            inline=False
        )
        embed.set_footer(
            text=f"{ctx.author.name}, reply with a/b/c/d or the full answer text",
            icon_url="https://lakevieweast.com/wp-content/uploads/trivia-stock-scaled.jpg"
        )
        await ctx.send(embed=embed)

        # wait for reply
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel

        try:
            msg = await self.client.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            await ctx.send("Timeout: no response. Try `trivia` again.")
            return

        user_reply = msg.content.strip().lower()

        # evaluate (allow a/b/c/d OR the exact answer text)
        is_letter = user_reply in list(letter_map)
        guess_idx = letter_map.index(user_reply) if is_letter else None
        is_text_match = user_reply == correct.lower()
        is_correct = (guess_idx == correct_idx) if is_letter else is_text_match

        await msg.add_reaction('✅' if is_correct else '❌')
        reveal = answers[correct_idx]
        if is_correct:
            await ctx.send(f"Correct! It was **{reveal}**.")
        else:
            await ctx.send(f"Incorrect. The correct answer was **{reveal}**.")

        _bump_stats(ctx.guild.id, ctx.author.id, is_correct)

    @commands.command(help="Show your trivia stats", aliases=["ts"])
    async def trivia_stats(self, ctx, member: discord.Member = None):
        member = member or ctx.author
        stats = _get_stats(ctx.guild.id, member.id)
        correct = stats["correct"]
        attempts = stats["attempts"]
        pct = (100.0 * correct / attempts) if attempts else 0.0

        e = discord.Embed(
            title="Trivia Stats",
            description=f"Stats for {member.display_name}",
            color=0x2e8b57
        )
        e.add_field(name="Correct", value=str(correct), inline=True)
        e.add_field(name="Attempts", value=str(attempts), inline=True)
        e.add_field(name="Accuracy", value=f"{pct:.1f}%", inline=True)
        await ctx.send(embed=e)

async def setup(client):
    await client.add_cog(Trivia(client))
