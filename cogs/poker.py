# cogs/poker.py
import json
import os
import asyncio
import discord
import requests
import contextlib
from io import BytesIO
from PIL import Image
from itertools import combinations
from discord.ext import commands
from typing import Optional, Dict, List, Any

START_BANK = 1000
SMALL_BLIND = 10
BIG_BLIND = 20
POKER_FILE = "storage/poker.json"
API = "https://www.deckofcardsapi.com/api/deck/"

# ---------- persistence ----------
def load_bank() -> Dict:
    os.makedirs(os.path.dirname(POKER_FILE), exist_ok=True)
    if not os.path.exists(POKER_FILE):
        with open(POKER_FILE, "w") as f:
            json.dump({}, f, indent=2)
    with open(POKER_FILE, "r") as f:
        try:
            return json.load(f)
        except Exception:
            return {}


def save_bank(data: Dict):
    with open(POKER_FILE, "w") as f:
        json.dump(data, f, indent=2)


def get_balance(gid: int, uid: int) -> int:
    data = load_bank()
    g = data.setdefault(str(gid), {})
    bal = g.get(str(uid), START_BANK)
    g[str(uid)] = bal
    save_bank(data)
    return bal


def add_balance(gid: int, uid: int, delta: int) -> int:
    data = load_bank()
    g = data.setdefault(str(gid), {})
    bal = g.get(str(uid), START_BANK) + delta
    g[str(uid)] = max(0, bal)
    save_bank(data)
    return g[str(uid)]


# ---------- hand evaluation ----------
RANK_ORDER = {'2': 2, '3': 3, '4': 4, '5': 5, '6': 6, '7': 7, '8': 8, '9': 9, '0': 10, 'J': 11, 'Q': 12, 'K': 13, 'A': 14}
RANK_NAME = {14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "Ten", 9: "Nine", 8: "Eight", 7: "Seven", 6: "Six", 5: "Five", 4: "Four", 3: "Three", 2: "Two"}
SUIT_EMOJI = {'S': '♠️', 'H': '♥️', 'D': '♦️', 'C': '♣️'}
RANK_DISPLAY = {'A': 'A', 'K': 'K', 'Q': 'Q', 'J': 'J', '0': '10', '9': '9', '8': '8', '7': '7', '6': '6', '5': '5', '4': '4', '3': '3', '2': '2'}


def parse_card(code: str):
    r, s = code[0], code[1]
    return RANK_ORDER[r], s


def card_to_str(code: str) -> str:
    """Convert card code to readable string like 'A♠️'"""
    r, s = code[0], code[1]
    return f"{RANK_DISPLAY.get(r, r)}{SUIT_EMOJI.get(s, s)}"


def _straight_high(uniq_desc):
    for i in range(len(uniq_desc) - 4):
        seq = uniq_desc[i:i + 5]
        if seq[0] - seq[4] == 4:
            return True, seq[0]
    if set([14, 5, 4, 3, 2]).issubset(set(uniq_desc)):
        return True, 5
    return False, 0


def hand_rank_5(cards):
    ranks = sorted((c[0] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    counts = {r: ranks.count(r) for r in set(ranks)}
    by_count = sorted(counts.items(), key=lambda x: (x[1], x[0]), reverse=True)

    flush_suit = None
    for s in "SHDC":
        if suits.count(s) == 5:
            flush_suit = s
            break

    uniq = sorted(set(ranks), reverse=True)
    straight, sh = _straight_high(uniq)

    if flush_suit:
        rs = sorted([c[0] for c in cards if c[1] == flush_suit], reverse=True)
        u = sorted(set(rs), reverse=True)
        sf, sfh = _straight_high(u)
        if sf:
            return (8, sfh)

    kinds = sorted(counts.values(), reverse=True)
    if kinds == [4, 1]:
        quad = by_count[0][0]
        kicker = max([r for r in ranks if r != quad])
        return (7, quad, kicker)
    if kinds == [3, 2]:
        trips = by_count[0][0]
        pair = by_count[1][0]
        return (6, trips, pair)
    if flush_suit:
        return (5, ranks)
    if straight:
        return (4, sh)
    if kinds == [3, 1, 1]:
        trips = by_count[0][0]
        kick = [r for r in ranks if r != trips][:2]
        return (3, trips, kick)
    if kinds == [2, 2, 1]:
        p1, p2 = sorted([r for r, c in by_count if c == 2], reverse=True)
        k = max([r for r in ranks if r not in (p1, p2)])
        return (2, p1, p2, k)
    if kinds == [2, 1, 1, 1]:
        p = by_count[0][0]
        kick = [r for r in ranks if r != p][:3]
        return (1, p, kick)
    return (0, ranks)


def best_7(cards7):
    best = None
    for comb in combinations(cards7, 5):
        val = hand_rank_5(comb)
        if not best or val > best:
            best = val
    return best


def codes_to_tuples(codes):
    return [parse_card(c) for c in codes]


def compare_hands(players_cards, board_codes):
    board = codes_to_tuples(board_codes)
    scores = {}
    for uid, codes in players_cards.items():
        seven = codes_to_tuples([c['code'] for c in codes]) + board
        scores[uid] = best_7(seven)
    best = max(scores.values())
    winners = [uid for uid, v in scores.items() if v == best]
    return winners, scores


def rank_to_text(rank_tuple) -> str:
    cat = rank_tuple[0]
    if cat == 8:
        return f"Straight Flush, high {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}"
    if cat == 7:
        return f"Four of a Kind, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    if cat == 6:
        return f"Full House, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s over {RANK_NAME.get(rank_tuple[2], rank_tuple[2])}s"
    if cat == 5:
        return "Flush"
    if cat == 4:
        return f"Straight, high {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}"
    if cat == 3:
        return f"Three of a Kind, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    if cat == 2:
        return f"Two Pair, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s and {RANK_NAME.get(rank_tuple[2], rank_tuple[2])}s"
    if cat == 1:
        return f"One Pair, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    return f"High Card {RANK_NAME.get(rank_tuple[1][0], rank_tuple[1][0])}"


# ---------- image helpers ----------
def _fetch_img(url: str) -> Image.Image:
    r = requests.get(url, timeout=12)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGBA")


def compose_cards_strip(card_objs: List[Dict], height: int = 200, pad: int = 8, bg=(34, 139, 34, 255)) -> Optional[BytesIO]:
    """Compose card images into a horizontal strip"""
    imgs = []
    for c in card_objs:
        try:
            im = _fetch_img(c["image"])
            h = height
            w = int(im.width * (h / im.height))
            im = im.resize((w, h), Image.LANCZOS)
            imgs.append(im)
        except Exception:
            pass
    if not imgs:
        return None
    total_w = sum(im.width for im in imgs) + pad * (len(imgs) + 1)
    canvas = Image.new("RGBA", (total_w, height + 2 * pad), bg)
    x = pad
    for im in imgs:
        canvas.paste(im, (x, pad), im)
        x += im.width + pad
    out = BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out


# ---------- UI Views ----------
class CardRevealButton(discord.ui.Button):
    """Button that shows cards only to the player who clicks it"""
    def __init__(self, poker_cog, player_id: int, label: str = "🃏 View My Cards"):
        super().__init__(style=discord.ButtonStyle.primary, label=label)
        self.poker = poker_cog
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ These aren't your cards!", ephemeral=True)
        
        cards = self.poker.hole.get(self.player_id)
        if not cards:
            return await interaction.response.send_message("No cards dealt yet.", ephemeral=True)
        
        # Create text representation
        card_str = " | ".join([card_to_str(c['code']) for c in cards])
        
        # Try to create image
        buf = compose_cards_strip(cards, height=200)
        if buf:
            file = discord.File(buf, filename="mycards.png")
            emb = discord.Embed(
                title="🎴 Your Hole Cards",
                description=f"**{card_str}**",
                color=0x2f7d5c
            )
            emb.set_image(url="attachment://mycards.png")
            await interaction.response.send_message(embed=emb, file=file, ephemeral=True)
        else:
            await interaction.response.send_message(f"🎴 Your cards: **{card_str}**", ephemeral=True)


class HandStrengthButton(discord.ui.Button):
    """Button that shows current hand strength"""
    def __init__(self, poker_cog, player_id: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="📊 Hand Strength", row=1)
        self.poker = poker_cog
        self.player_id = player_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ Not your hand!", ephemeral=True)
        
        if self.player_id not in self.poker.in_hand:
            return await interaction.response.send_message("You're not in the hand.", ephemeral=True)
        
        hole = self.poker.hole.get(self.player_id, [])
        if not hole:
            return await interaction.response.send_message("No cards dealt.", ephemeral=True)
        
        board_codes = [c["code"] for c in self.poker.board]
        if not board_codes:
            # Pre-flop - just show hole cards
            card_str = " | ".join([card_to_str(c['code']) for c in hole])
            return await interaction.response.send_message(
                f"🎴 Your hole cards: **{card_str}**\n*Board not dealt yet - hand strength unknown*",
                ephemeral=True
            )
        
        seven = codes_to_tuples([c['code'] for c in hole]) + codes_to_tuples(board_codes)
        hand_rank = best_7(seven)
        txt = rank_to_text(hand_rank)
        
        card_str = " | ".join([card_to_str(c['code']) for c in hole])
        board_str = " ".join([card_to_str(c) for c in board_codes])
        
        await interaction.response.send_message(
            f"🎴 Your cards: **{card_str}**\n"
            f"📋 Board: **{board_str}**\n"
            f"💪 Best hand: **{txt}**",
            ephemeral=True
        )


class PlayerCardsView(discord.ui.View):
    """View with buttons for a specific player"""
    def __init__(self, poker_cog, player_id: int, timeout: float = 300):
        super().__init__(timeout=timeout)
        self.add_item(CardRevealButton(poker_cog, player_id))
        self.add_item(HandStrengthButton(poker_cog, player_id))


class ActionButton(discord.ui.Button):
    """Button for poker actions"""
    def __init__(self, action: str, label: str, style: discord.ButtonStyle, player_id: int):
        super().__init__(style=style, label=label)
        self.action = action
        self.player_id = player_id
        self.clicked = False
        self.result = None

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("❌ Not your turn!", ephemeral=True)
        
        self.clicked = True
        self.result = self.action
        self.view.stop()
        await interaction.response.defer()


class ActionView(discord.ui.View):
    """View for poker betting actions"""
    def __init__(self, player_id: int, can_check: bool, call_amount: int, timeout: float = 60):
        super().__init__(timeout=timeout)
        self.player_id = player_id
        self.result = None
        
        # Fold button
        self.add_item(ActionButton("fold", "❌ Fold", discord.ButtonStyle.danger, player_id))
        
        # Check or Call
        if can_check:
            self.add_item(ActionButton("check", "✅ Check", discord.ButtonStyle.success, player_id))
        else:
            self.add_item(ActionButton("call", f"📞 Call ${call_amount}", discord.ButtonStyle.primary, player_id))
        
        # Raise and All-in
        self.add_item(ActionButton("raise", "💰 Raise", discord.ButtonStyle.secondary, player_id))
        self.add_item(ActionButton("allin", "🔥 All-In", discord.ButtonStyle.danger, player_id))

    async def on_timeout(self):
        self.result = "timeout"


class RaiseModal(discord.ui.Modal):
    """Modal for entering raise amount"""
    def __init__(self, min_raise: int, max_raise: int, player_balance: int):
        super().__init__(title="Enter Raise Amount")
        self.amount = None
        self.min_raise = min_raise
        self.max_raise = max_raise
        
        self.amount_input = discord.ui.TextInput(
            label=f"Amount (Min: ${min_raise}, Max: ${max_raise})",
            placeholder=str(min_raise),
            required=True,
            min_length=1,
            max_length=10
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            self.amount = int(self.amount_input.value)
            if self.amount < self.min_raise:
                self.amount = self.min_raise
            elif self.amount > self.max_raise:
                self.amount = self.max_raise
        except ValueError:
            self.amount = self.min_raise
        await interaction.response.defer()


# ---------- Main Cog ----------
class Poker(commands.Cog):
    """Texas Hold'em Poker - Play in chat with friends!"""

    def __init__(self, bot):
        self.bot = bot
        self.active = False
        self.msg_id = None
        self.players: List[discord.Member] = []
        self.dealer = 0
        self.deck_id = None
        self.hole: Dict[int, List[Dict]] = {}
        self.board: List[Dict] = []
        self.in_hand: set = set()
        self.bets: Dict[int, int] = {}
        self.pot = 0
        self.current_bet = 0

    def new_deck(self):
        j = requests.get(f"{API}new/shuffle/?deck_count=1", timeout=10).json()
        self.deck_id = j["deck_id"]

    def draw(self, n: int) -> List[Dict]:
        j = requests.get(f"{API}{self.deck_id}/draw/?count={n}", timeout=10).json()
        return j["cards"]

    async def post_board_image(self, ctx, label: str):
        """Post the community cards"""
        if not self.board:
            return
        
        board_str = " ".join([card_to_str(c['code']) for c in self.board])
        buf = compose_cards_strip(self.board, height=180, bg=(0, 100, 0, 255))
        
        if buf:
            file = discord.File(buf, filename="board.png")
            emb = discord.Embed(
                title=f"🃏 {label}",
                description=f"**{board_str}**\n\n💰 Pot: **${self.pot}**",
                color=0x2f7d5c
            )
            emb.set_image(url="attachment://board.png")
            await ctx.send(file=file, embed=emb)
        else:
            await ctx.send(f"**{label}**: {board_str}\n💰 Pot: ${self.pot}")

    async def send_hole_cards_to_player(self, ctx, player: discord.Member):
        """Send private hole cards view to a player"""
        view = PlayerCardsView(self, player.id)
        await ctx.send(f"🎴 {player.mention} - Click to view your cards!", view=view)

    @commands.command(help="Check your poker balance")
    async def balance(self, ctx, member: discord.Member = None):
        """Check poker balance"""
        member = member or ctx.author
        if ctx.guild is None:
            return await ctx.send("Use this in a server.")
        
        bal = get_balance(ctx.guild.id, member.id)
        emb = discord.Embed(
            title="💰 Poker Balance",
            description=f"{member.display_name}: **${bal}**",
            color=0xffd700
        )
        await ctx.send(embed=emb)

    @commands.command(help="Give money to a player (Admin only)")
    @commands.has_permissions(administrator=True)
    async def give_money(self, ctx, target: discord.Member, amount: int):
        """Admin command to give poker money"""
        if ctx.guild is None:
            return await ctx.send("Use this in a server.")
        if amount <= 0:
            return await ctx.send("Amount must be positive.")
        
        new_bal = add_balance(ctx.guild.id, target.id, amount)
        await ctx.send(f"💵 Gave **${amount}** to {target.display_name}. New balance: **${new_bal}**")

    @commands.command(help="Start a Texas Hold'em poker game!")
    async def poker(self, ctx):
        """Start a poker game - react ♠️ to join!"""
        if self.active:
            return await ctx.send("⚠️ A poker game is already running!")
        
        if ctx.guild is None:
            return await ctx.send("Poker must be played in a server.")
        
        self.active = True
        self.players = []
        self.dealer = 0

        emb = discord.Embed(
            title="🎰 Texas Hold'em Poker",
            description=(
                "**How to play:**\n"
                "• React ♠️ to join the game\n"
                "• Host clicks ✅ to start\n"
                "• Click ❌ to cancel\n\n"
                f"💵 Starting balance: ${START_BANK}\n"
                f"💰 Blinds: ${SMALL_BLIND}/${BIG_BLIND}"
            ),
            color=0x2f7d5c
        )
        emb.set_footer(text=f"Started by {ctx.author.display_name}")
        
        m = await ctx.send(embed=emb)
        self.msg_id = m.id
        
        for em in ['♠️', '✅', '❌']:
            await m.add_reaction(em)

        def check(r, u):
            return u == ctx.author and str(r.emoji) in ['✅', '❌'] and r.message.id == m.id

        while True:
            try:
                r, _ = await self.bot.wait_for("reaction_add", timeout=180, check=check)
                emo = str(r.emoji)
                
                if emo == '❌':
                    self.active = False
                    self.players = []
                    with contextlib.suppress(Exception):
                        await m.delete()
                    return await ctx.send("🚫 Game cancelled.")
                
                if emo == '✅':
                    with contextlib.suppress(Exception):
                        await m.delete()
                    if len(self.players) < 2:
                        self.active = False
                        return await ctx.send("❌ Need at least 2 players to start!")
                    break
                    
            except asyncio.TimeoutError:
                self.active = False
                self.players = []
                with contextlib.suppress(Exception):
                    await m.delete()
                return await ctx.send("⏰ Timed out. Game cancelled.")

        await self.play_loop(ctx)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if not self.active or payload.user_id == self.bot.user.id:
            return
        if self.msg_id is None or payload.message_id != self.msg_id:
            return
        if str(payload.emoji) != '♠️':
            return
        
        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return
        
        member = guild.get_member(payload.user_id)
        if not member or member.bot:
            return
        
        if member in self.players:
            ch = self.bot.get_channel(payload.channel_id)
            if ch:
                await ch.send(f"⚠️ {member.display_name} already joined!")
            return
        
        self.players.append(member)
        bal = get_balance(guild.id, member.id)
        ch = self.bot.get_channel(payload.channel_id)
        if ch:
            await ch.send(f"✅ **{member.display_name}** joined! (Balance: ${bal})")

    async def play_loop(self, ctx):
        """Main game loop"""
        while self.active and len([p for p in self.players if get_balance(ctx.guild.id, p.id) > 0]) >= 2:
            self.players = [p for p in self.players if get_balance(ctx.guild.id, p.id) > 0]
            await self.play_hand(ctx)

            # Ask to continue
            emb = discord.Embed(
                title="🎰 Continue Playing?",
                description="React ✅ to play another hand, ❌ to end.",
                color=0x2f7d5c
            )
            prompt = await ctx.send(embed=emb)
            await prompt.add_reaction('✅')
            await prompt.add_reaction('❌')

            try:
                def check(r, u):
                    return u in self.players and str(r.emoji) in ['✅', '❌'] and r.message.id == prompt.id
                
                r, _ = await self.bot.wait_for("reaction_add", timeout=30, check=check)
                with contextlib.suppress(Exception):
                    await prompt.delete()
                
                if str(r.emoji) == '❌':
                    self.active = False
                    break
            except asyncio.TimeoutError:
                with contextlib.suppress(Exception):
                    await prompt.delete()
                self.active = False
                break

        self.active = False
        
        # Show final standings
        standings = []
        for p in self.players:
            bal = get_balance(ctx.guild.id, p.id)
            standings.append((p.display_name, bal))
        
        standings.sort(key=lambda x: x[1], reverse=True)
        
        emb = discord.Embed(title="🏆 Final Standings", color=0xffd700)
        for i, (name, bal) in enumerate(standings, 1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            emb.add_field(name=f"{medal} {name}", value=f"${bal}", inline=False)
        
        await ctx.send(embed=emb)

    async def play_hand(self, ctx):
        """Play a single hand of poker"""
        gid = ctx.guild.id
        self.in_hand = set(p.id for p in self.players)
        self.hole = {}
        self.board = []
        self.bets = {p.id: 0 for p in self.players}
        self.pot = 0
        self.current_bet = 0

        self.new_deck()

        # Post blinds
        sb_pos = (self.dealer + 1) % len(self.players)
        bb_pos = (self.dealer + 2) % len(self.players)
        sb = self.players[sb_pos]
        bb = self.players[bb_pos]
        dealer = self.players[self.dealer]

        emb = discord.Embed(
            title="🎴 New Hand",
            description=(
                f"**Dealer:** {dealer.display_name}\n"
                f"**Small Blind:** {sb.display_name} (${SMALL_BLIND})\n"
                f"**Big Blind:** {bb.display_name} (${BIG_BLIND})"
            ),
            color=0x2f7d5c
        )
        await ctx.send(embed=emb)

        # Collect blinds
        add_balance(gid, sb.id, -SMALL_BLIND)
        self.bets[sb.id] = SMALL_BLIND
        self.pot += SMALL_BLIND

        add_balance(gid, bb.id, -BIG_BLIND)
        self.bets[bb.id] = BIG_BLIND
        self.pot += BIG_BLIND
        self.current_bet = BIG_BLIND

        # Deal hole cards
        for p in self.players:
            self.hole[p.id] = self.draw(2)

        # Send private card views
        await ctx.send("🎴 **Cards have been dealt!** Click the button below to view your cards privately.")
        for p in self.players:
            if p.id in self.in_hand:
                await self.send_hole_cards_to_player(ctx, p)

        # Pre-flop betting
        await ctx.send("📢 **Pre-Flop Betting**")
        await self.betting_round(ctx, start_index=(self.dealer + 3) % len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        # Flop
        self.draw(1)  # Burn
        self.board += self.draw(3)
        await self.post_board_image(ctx, "The Flop")
        await self.betting_round(ctx, start_index=(self.dealer + 1) % len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        # Turn
        self.draw(1)  # Burn
        self.board += self.draw(1)
        await self.post_board_image(ctx, "The Turn")
        await self.betting_round(ctx, start_index=(self.dealer + 1) % len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        # River
        self.draw(1)  # Burn
        self.board += self.draw(1)
        await self.post_board_image(ctx, "The River")
        await self.betting_round(ctx, start_index=(self.dealer + 1) % len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        await self.showdown(ctx)
        self.dealer = (self.dealer + 1) % len(self.players)

    async def award_uncontested(self, ctx):
        """Award pot when everyone else folds"""
        if not self.in_hand:
            return
        
        winner_id = list(self.in_hand)[0]
        winner = discord.utils.get(self.players, id=winner_id)
        add_balance(ctx.guild.id, winner_id, self.pot)
        
        emb = discord.Embed(
            title="🏆 Winner!",
            description=f"**{winner.display_name}** wins **${self.pot}** (everyone else folded)",
            color=0xffd700
        )
        await ctx.send(embed=emb)
        self.dealer = (self.dealer + 1) % len(self.players)

    async def betting_round(self, ctx, start_index: int):
        """Handle a betting round"""
        round_current = max(self.bets.values()) if self.bets else 0
        self.current_bet = round_current
        acted_since_raise = set()

        if len(self.in_hand) < 2:
            return

        while True:
            all_match = all((uid not in self.in_hand) or (self.bets[uid] == round_current) for uid in self.bets)
            everyone_acted = acted_since_raise.issuperset(self.in_hand)
            if all_match and everyone_acted:
                break

            for i in range(len(self.players)):
                idx = (start_index + i) % len(self.players)
                p = self.players[idx]
                pid = p.id

                if pid not in self.in_hand:
                    continue

                bal = get_balance(ctx.guild.id, pid)
                if bal <= 0:
                    self.in_hand.discard(pid)
                    continue

                all_match = all((uid not in self.in_hand) or (self.bets[uid] == round_current) for uid in self.bets)
                everyone_acted = acted_since_raise.issuperset(self.in_hand)
                if all_match and everyone_acted:
                    break

                need = round_current - self.bets[pid]
                can_check = (need == 0)

                # Create action view
                view = ActionView(pid, can_check, need)
                
                emb = discord.Embed(
                    title=f"🎯 {p.display_name}'s Turn",
                    description=(
                        f"💰 **Pot:** ${self.pot}\n"
                        f"📊 **Current Bet:** ${round_current}\n"
                        f"💵 **Your Bet:** ${self.bets[pid]}\n"
                        f"🏦 **Your Balance:** ${bal}\n"
                        f"{'✅ You can check' if can_check else f'📞 Call amount: ${need}'}"
                    ),
                    color=0x3498db
                )
                
                msg = await ctx.send(f"{p.mention}", embed=emb, view=view)

                # Wait for action
                await view.wait()
                
                with contextlib.suppress(Exception):
                    await msg.delete()

                # Process action
                action = None
                for item in view.children:
                    if isinstance(item, ActionButton) and item.clicked:
                        action = item.result
                        break

                if action is None or action == "timeout":
                    await ctx.send(f"⏰ {p.display_name} timed out and folds.")
                    self.in_hand.discard(pid)
                    continue

                if action == "fold":
                    await ctx.send(f"❌ {p.display_name} folds.")
                    self.in_hand.discard(pid)
                    continue

                if action == "check":
                    await ctx.send(f"✅ {p.display_name} checks.")
                    acted_since_raise.add(pid)
                    continue

                if action == "call":
                    call_amt = min(need, bal)
                    add_balance(ctx.guild.id, pid, -call_amt)
                    self.bets[pid] += call_amt
                    self.pot += call_amt
                    await ctx.send(f"📞 {p.display_name} calls ${call_amt}.")
                    acted_since_raise.add(pid)
                    continue

                if action == "allin":
                    shove = bal
                    add_balance(ctx.guild.id, pid, -shove)
                    self.bets[pid] += shove
                    self.pot += shove
                    if self.bets[pid] > round_current:
                        round_current = self.bets[pid]
                        self.current_bet = round_current
                        acted_since_raise = {pid}
                        await ctx.send(f"🔥 {p.display_name} goes **ALL-IN** to ${round_current}!")
                    else:
                        acted_since_raise.add(pid)
                        await ctx.send(f"🔥 {p.display_name} goes **ALL-IN** for ${shove}!")
                    continue

                if action == "raise":
                    min_raise = round_current + BIG_BLIND
                    max_raise = bal + self.bets[pid]
                    
                    # Ask for raise amount
                    ask = await ctx.send(f"{p.mention} Enter raise amount (min ${min_raise}, max ${max_raise}):")
                    
                    def chk(m):
                        return m.author == p and m.channel == ctx.channel
                    
                    try:
                        msg = await self.bot.wait_for('message', timeout=30, check=chk)
                        try:
                            total = int(msg.content)
                            total = max(min_raise, min(total, max_raise))
                        except ValueError:
                            total = min_raise
                    except asyncio.TimeoutError:
                        total = min_raise
                    
                    with contextlib.suppress(Exception):
                        await ask.delete()
                        await msg.delete()
                    
                    addl = total - self.bets[pid]
                    addl = min(addl, bal)
                    add_balance(ctx.guild.id, pid, -addl)
                    self.bets[pid] += addl
                    self.pot += addl

                    if self.bets[pid] > round_current:
                        round_current = self.bets[pid]
                        self.current_bet = round_current
                        acted_since_raise = {pid}
                        await ctx.send(f"💰 {p.display_name} raises to ${round_current}!")
                    else:
                        acted_since_raise.add(pid)

        # Reset for next round
        self.current_bet = 0
        self.bets = {uid: 0 for uid in self.bets}

    async def showdown(self, ctx):
        """Handle showdown"""
        board_codes = [c['code'] for c in self.board]
        pool = {uid: self.hole[uid] for uid in self.in_hand}
        winners, scores = compare_hands(pool, board_codes)
        share = self.pot // len(winners) if winners else 0

        # Show board
        await self.post_board_image(ctx, "Final Board")

        # Show all hands
        emb = discord.Embed(title="🃏 Showdown", color=0xffd700)
        
        for p in self.players:
            if p.id in self.in_hand:
                cards = self.hole[p.id]
                card_str = " | ".join([card_to_str(c['code']) for c in cards])
                hand_name = rank_to_text(scores[p.id])
                is_winner = p.id in winners
                
                emb.add_field(
                    name=f"{'🏆 ' if is_winner else ''}{p.display_name}",
                    value=f"**{card_str}**\n{hand_name}",
                    inline=True
                )

        await ctx.send(embed=emb)

        # Award pot
        winner_names = []
        for uid in winners:
            add_balance(ctx.guild.id, uid, share)
            member = discord.utils.get(self.players, id=uid)
            winner_names.append(member.display_name)

        emb = discord.Embed(
            title="🏆 Winner(s)!",
            description=f"**{', '.join(winner_names)}** win{'s' if len(winners) == 1 else ''} **${share}** each!",
            color=0xffd700
        )
        await ctx.send(embed=emb)


async def setup(bot):
    await bot.add_cog(Poker(bot))