# cogs/poker.py
import json, os, asyncio, discord, requests, contextlib
from io import BytesIO
from PIL import Image  # pip install pillow
from itertools import combinations
from discord.ext import commands

START_BANK   = 1000
SMALL_BLIND  = 10
BIG_BLIND    = 20
POKER_FILE   = "storage/poker.json"
API          = "https://www.deckofcardsapi.com/api/deck/"

# ---------- persistence ----------
def load_bank():
    os.makedirs(os.path.dirname(POKER_FILE), exist_ok=True)
    if not os.path.exists(POKER_FILE):
        with open(POKER_FILE, "w") as f: json.dump({}, f, indent=2)
    with open(POKER_FILE, "r") as f:
        try: return json.load(f)
        except Exception: return {}

def save_bank(data):
    with open(POKER_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_balance(gid, uid):
    data = load_bank()
    g = data.setdefault(str(gid), {})
    bal = g.get(str(uid), START_BANK)
    g[str(uid)] = bal
    save_bank(data)
    return bal

def add_balance(gid, uid, delta):
    data = load_bank()
    g = data.setdefault(str(gid), {})
    bal = g.get(str(uid), START_BANK) + delta
    g[str(uid)] = max(0, bal)
    save_bank(data)
    return g[str(uid)]

# ---------- hand evaluation ----------
RANK_ORDER = {'2':2,'3':3,'4':4,'5':5,'6':6,'7':7,'8':8,'9':9,'0':10,'J':11,'Q':12,'K':13,'A':14}
RANK_NAME  = {14:"Ace",13:"King",12:"Queen",11:"Jack",10:"Ten",9:"Nine",8:"Eight",7:"Seven",6:"Six",5:"Five",4:"Four",3:"Three",2:"Two"}

def parse_card(code):
    r, s = code[0], code[1]  # e.g., "AS" or "0H"
    return RANK_ORDER[r], s

def _straight_high(uniq_desc):
    for i in range(len(uniq_desc)-4):
        seq = uniq_desc[i:i+5]
        if seq[0]-seq[4] == 4:
            return True, seq[0]
    if set([14,5,4,3,2]).issubset(set(uniq_desc)): return True, 5
    return False, 0

def hand_rank_5(cards):
    ranks = sorted((c[0] for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    counts = {r: ranks.count(r) for r in set(ranks)}
    by_count = sorted(counts.items(), key=lambda x:(x[1], x[0]), reverse=True)

    flush_suit = None
    for s in "SHDC":
        if suits.count(s) == 5:
            flush_suit = s
            break

    uniq = sorted(set(ranks), reverse=True)
    straight, sh = _straight_high(uniq)

    if flush_suit:
        rs = sorted([c[0] for c in cards if c[1]==flush_suit], reverse=True)
        u  = sorted(set(rs), reverse=True)
        sf, sfh = _straight_high(u)
        if sf: return (8, sfh)

    kinds = sorted(counts.values(), reverse=True)
    if kinds == [4,1]:
        quad = by_count[0][0]; kicker = max([r for r in ranks if r!=quad])
        return (7, quad, kicker)
    if kinds == [3,2]:
        trips = by_count[0][0]; pair = by_count[1][0]
        return (6, trips, pair)
    if flush_suit:
        return (5, ranks)
    if straight:
        return (4, sh)
    if kinds == [3,1,1]:
        trips = by_count[0][0]
        kick  = [r for r in ranks if r!=trips][:2]
        return (3, trips, kick)
    if kinds == [2,2,1]:
        p1, p2 = sorted([r for r,c in by_count if c==2], reverse=True)
        k = max([r for r in ranks if r not in (p1,p2)])
        return (2, p1, p2, k)
    if kinds == [2,1,1,1]:
        p = by_count[0][0]
        kick = [r for r in ranks if r!=p][:3]
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
    winners = [uid for uid,v in scores.items() if v==best]
    return winners, scores

def rank_to_text(rank_tuple):
    cat = rank_tuple[0]
    if cat == 8:  return f"Straight Flush, high {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}"
    if cat == 7:  return f"Four of a Kind, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    if cat == 6:  return f"Full House, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s over {RANK_NAME.get(rank_tuple[2], rank_tuple[2])}s"
    if cat == 5:  return "Flush"
    if cat == 4:  return f"Straight, high {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}"
    if cat == 3:  return f"Three of a Kind, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    if cat == 2:  return f"Two Pair, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s and {RANK_NAME.get(rank_tuple[2], rank_tuple[2])}s"
    if cat == 1:  return f"One Pair, {RANK_NAME.get(rank_tuple[1], rank_tuple[1])}s"
    return f"High Card {RANK_NAME.get(rank_tuple[1][0], rank_tuple[1][0])}"

# ---------- image helpers ----------
def _fetch_img(url):
    r = requests.get(url, timeout=12)
    r.raise_for_status()
    return Image.open(BytesIO(r.content)).convert("RGBA")

def compose_cards_strip(card_objs, height=320, pad=8, bg=(24,24,24,255)):
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
    total_w = sum(im.width for im in imgs) + pad*(len(imgs)+1)
    canvas  = Image.new("RGBA", (total_w, height + 2*pad), bg)
    x = pad
    for im in imgs:
        canvas.paste(im, (x, pad), im)
        x += im.width + pad
    out = BytesIO()
    canvas.save(out, format="PNG")
    out.seek(0)
    return out

# ---------- small UI views (define BEFORE the cog) ----------
class ShowCardsView(discord.ui.View):
    def __init__(self, poker_cog, player_id: int, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.poker = poker_cog
        self.player_id = player_id

    @discord.ui.button(label="Show my cards (private)", style=discord.ButtonStyle.primary)
    async def show_cards(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("That button isn’t for you.", ephemeral=True)
        cards = self.poker.hole.get(self.player_id)
        if not cards:
            return await interaction.response.send_message("No hole cards yet.", ephemeral=True)
        buf = compose_cards_strip(cards, height=320)
        if buf is None:
            codes = " ".join([c["code"] for c in cards])
            return await interaction.response.send_message(f"Your cards: {codes}", ephemeral=True)
        file = discord.File(buf, filename="mycards.png")
        emb = discord.Embed(title="Your Hole Cards")
        emb.set_image(url="attachment://mycards.png")
        await interaction.response.send_message(embed=emb, file=file, ephemeral=True)

class ShowHintView(discord.ui.View):
    def __init__(self, poker_cog, player_id: int, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.poker = poker_cog
        self.player_id = player_id

    @discord.ui.button(label="Show my best hand (private)", style=discord.ButtonStyle.secondary)
    async def show_hint(self, interaction: discord.Interaction, _button: discord.ui.Button):
        if interaction.user.id != self.player_id:
            return await interaction.response.send_message("That button isn’t for you.", ephemeral=True)
        if self.player_id not in self.poker.in_hand:
            return await interaction.response.send_message("You’re not in the current hand.", ephemeral=True)
        board_codes = [c["code"] for c in self.poker.board]
        if not board_codes:
            return await interaction.response.send_message("Board not dealt yet.", ephemeral=True)
        hole = self.poker.hole.get(self.player_id, [])
        seven = codes_to_tuples([c['code'] for c in hole] + board_codes)
        txt = rank_to_text(best_7(seven))
        await interaction.response.send_message(f"Your best hand right now: **{txt}**", ephemeral=True)

class PrivateTools(discord.ui.View):
    def __init__(self, poker_cog, player_id: int, timeout: float = 120):
        super().__init__(timeout=timeout)
        self.add_item(ShowCardsView(poker_cog, player_id).children[0])
        self.add_item(ShowHintView(poker_cog, player_id).children[0])

# ---------- cog ----------
class Poker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.active = False
        self.msg_id = None
        self.players = []           # list[discord.Member]
        self.dealer = 0
        self.deck_id = None
        self.hole = {}              # uid -> [card, card]
        self.board = []             # community cards
        self.in_hand = set()
        self.bets = {}
        self.pot = 0
        self.current_bet = 0

    # ---- helpers ----
    async def ask_reaction(self, ctx, message, user, valid, timeout=60):
        def check(r,u): return u==user and str(r.emoji) in valid and r.message.id==message.id
        try:
            r,_ = await self.bot.wait_for('reaction_add', timeout=timeout, check=check)
            return str(r.emoji)
        except asyncio.TimeoutError:
            return None

    def new_deck(self):
        j = requests.get(f"{API}new/shuffle/?deck_count=1", timeout=10).json()
        self.deck_id = j["deck_id"]

    def draw(self, n):
        j = requests.get(f"{API}{self.deck_id}/draw/?count={n}", timeout=10).json()
        return j["cards"]

    async def post_state(self, ctx, title):
        names = ", ".join([p.display_name for p in self.players])
        await ctx.send(f"**{title}**\nPlayers: {names}\nDealer: {self.players[self.dealer].display_name}\nPot: ${self.pot}  Current bet: ${self.current_bet}")

    async def post_board_image(self, ctx, label):
        buf = compose_cards_strip(self.board, height=320)
        if buf is None:
            codes = ' '.join([c['code'] for c in self.board])
            await ctx.send(f"**{label}**: {codes}")
            return
        file = discord.File(buf, filename="board.png")
        emb = discord.Embed(title=label, color=0x2f7d5c)
        emb.set_image(url="attachment://board.png")
        await ctx.send(file=file, embed=emb)

    async def post_private_tools_for_players(self, ctx, label_for_tools=""):
        for p in self.players:
            if p.id in self.in_hand:
                with contextlib.suppress(Exception):
                    await ctx.send(f"{p.mention} {label_for_tools}".strip(), view=PrivateTools(self, p.id))


    @commands.command(name="give_money", help="Admin: give money to a user. Usage: give_money @user 250", hidden = True)
    @commands.has_permissions(administrator=True)
    async def give_money(self, ctx, target: discord.Member = None, amount: int | None = None):
        # Guild-only
        if ctx.guild is None:
            return await ctx.send("This command must be used in a server.")
        # Args check
        if target is None or amount is None:
            return await ctx.send("Usage: `give_money @user <amount>`")
        if amount <= 0:
            return await ctx.send("Amount must be a positive integer.")
        # Update bank
        new_bal = add_balance(ctx.guild.id, target.id, amount)
        await ctx.send(f"Gave **${amount}** to **{target.display_name}**. New balance: **${new_bal}**.")

    # ---- commands ----
    @commands.command(help="Start a Texas Hold’em game. React ♠️ to join. ✅ to start, ❌ to cancel.")
    async def poker(self, ctx):
        if self.active:
            return await ctx.send("A poker game is already running.")
        self.active = True
        self.players = []
        self.dealer = 0

        e = discord.Embed(
            title="Poker",
            description="React ♠️ to join.\nWhen ready, the host presses ✅.\nPress ❌ to cancel.",
            color=0x2f7d5c
        )
        m = await ctx.send(embed=e)
        self.msg_id = m.id
        for em in ['♠️','✅','❌']:
            await m.add_reaction(em)

        def check(r,u):
            return u==ctx.author and str(r.emoji) in ['✅','❌'] and r.message.id==m.id

        while True:
            try:
                r,_ = await self.bot.wait_for("reaction_add", timeout=180, check=check)
                emo = str(r.emoji)
                if emo == '❌':
                    self.active=False; self.players=[]
                    with contextlib.suppress(Exception):
                        await m.delete()
                    return await ctx.send("Game cancelled.")
                if emo == '✅':
                    with contextlib.suppress(Exception):
                        await m.delete()
                    if len(self.players) < 2:
                        self.active=False
                        return await ctx.send("Need at least 2 players.")
                    break
            except asyncio.TimeoutError:
                self.active=False; self.players=[]
                with contextlib.suppress(Exception):
                    await m.delete()
                return await ctx.send("Timed out. Game cancelled.")

        await self.play_loop(ctx)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if not self.active or user.bot:
            return
        if self.msg_id and reaction.message.id == self.msg_id and str(reaction.emoji) == '♠️':
            if user in self.players:
                await reaction.message.channel.send(f"{user.display_name} already joined.")
            else:
                self.players.append(user)
                bal = get_balance(reaction.message.guild.id, user.id)
                await reaction.message.channel.send(f"{user.display_name} joined with ${bal}.")

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
                await ch.send(f"{member.display_name} already joined.")
            return
        self.players.append(member)
        bal = get_balance(guild.id, member.id)
        ch = self.bot.get_channel(payload.channel_id)
        if ch:
            await ch.send(f"{member.display_name} joined with ${bal}.")

    # ---- game loop ----
    async def play_loop(self, ctx):
        while self.active and len([p for p in self.players if get_balance(ctx.guild.id, p.id)>0]) >= 2:
            self.players = [p for p in self.players if get_balance(ctx.guild.id, p.id) > 0]
            await self.play_hand(ctx)

            prompt = await ctx.send("Continue to next hand? React ✅ (continue) or ❌ (end). Default = **end** in 15s.")
            for em in ['✅','❌']: await prompt.add_reaction(em)
            try:
                await asyncio.sleep(15)
                prompt = await prompt.channel.fetch_message(prompt.id)
                yes = next((r.count for r in prompt.reactions if str(r.emoji)=='✅'), 0)
                no  = next((r.count for r in prompt.reactions if str(r.emoji)=='❌'), 0)
                if any(r.me and str(r.emoji)=='✅' for r in prompt.reactions): yes -= 1
                if any(r.me and str(r.emoji)=='❌' for r in prompt.reactions): no  -= 1
            finally:
                with contextlib.suppress(Exception):
                    await prompt.delete()

            majority = (len(self.players)//2) + 1
            if yes >= majority:
                continue
            else:
                self.active = False
                await ctx.send("Game ended.")
        self.active=False
        await ctx.send("Poker session finished.")

    async def play_hand(self, ctx):
        gid = ctx.guild.id
        self.in_hand = set(p.id for p in self.players)
        self.hole = {}
        self.board = []
        self.bets = {p.id:0 for p in self.players}
        self.pot = 0
        self.current_bet = 0

        self.new_deck()

        sb_pos = (self.dealer+1) % len(self.players)
        bb_pos = (self.dealer+2) % len(self.players)
        sb = self.players[sb_pos]; bb = self.players[bb_pos]
        await ctx.send(f"Blinds: {sb.display_name} posts ${SMALL_BLIND}, {bb.display_name} posts ${BIG_BLIND}")
        add_balance(gid, sb.id, -SMALL_BLIND); self.bets[sb.id] = SMALL_BLIND; self.pot += SMALL_BLIND
        add_balance(gid, bb.id, -BIG_BLIND);  self.bets[bb.id] = BIG_BLIND;  self.pot += BIG_BLIND
        self.current_bet = BIG_BLIND

        for p in self.players:
            self.hole[p.id] = self.draw(2)

        await self.post_state(ctx, "Preflop")
        for p in self.players:
            if p.id in self.in_hand:
                with contextlib.suppress(Exception):
                    await ctx.send(f"{p.mention}", view=PrivateTools(self, p.id))
        await self.betting_round(ctx, start_index=(self.dealer+3)%len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        self.draw(1)
        self.board += self.draw(3)
        await self.post_board_image(ctx, "Flop")
        await self.post_private_tools_for_players(ctx, "(flop)")
        await self.betting_round(ctx, start_index=(self.dealer+1)%len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        self.draw(1)
        self.board += self.draw(1)
        await self.post_board_image(ctx, "Turn")
        await self.post_private_tools_for_players(ctx, "(turn)")
        await self.betting_round(ctx, start_index=(self.dealer+1)%len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        self.draw(1)
        self.board += self.draw(1)
        await self.post_board_image(ctx, "River")
        await self.post_private_tools_for_players(ctx, "(river)")
        await self.betting_round(ctx, start_index=(self.dealer+1)%len(self.players))
        if len(self.in_hand) < 2:
            return await self.award_uncontested(ctx)

        await self.showdown(ctx)
        self.dealer = (self.dealer + 1) % len(self.players)

    async def award_uncontested(self, ctx):
        if not self.in_hand:
            return
        winner_id = list(self.in_hand)[0]
        winner = discord.utils.get(self.players, id=winner_id)
        add_balance(ctx.guild.id, winner_id, self.pot)
        await ctx.send(f"{winner.display_name} wins the pot of ${self.pot} uncontested.")
        self.dealer = (self.dealer + 1) % len(self.players)

    async def betting_round(self, ctx, start_index, preflop: bool = False):
        """
        Full betting logic per street.
        - preflop=True: keep blinds in self.bets and set round_current to BIG_BLIND.
        - postflop: reset per-street bets to 0.
        Ends when every remaining player has acted since last raise AND has matched round_current.
        """
        # initialize per-street state
        if preflop:
            # self.bets already contains blinds for SB/BB set in play_hand
            round_current = max(self.bets.values()) if self.bets else 0  # typically BIG_BLIND
        else:
            # fresh street: zero the per-street commitments
            self.bets = {uid: 0 for uid in self.bets}
            round_current = 0

        self.current_bet = round_current
        acted_since_raise = set()

        # If only one player is left (e.g., everyone else folded earlier), stop now
        if len(self.in_hand) < 2:
            return

        while True:
            # termination check at top of loop
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
                    # broke → auto-fold
                    self.in_hand.discard(pid)
                    continue

                # re-check end conditions between turns
                all_match = all((uid not in self.in_hand) or (self.bets[uid] == round_current) for uid in self.bets)
                everyone_acted = acted_since_raise.issuperset(self.in_hand)
                if all_match and everyone_acted:
                    break

                need = round_current - self.bets[pid]
                can_check = (need == 0)

                options = ['❌'] + (['✅'] if can_check else ['📞']) + ['💰', '🧨']
                desc = ("❌ fold  ✅ check  💰 bet/raise  🧨 all-in"
                        if can_check else
                        f"❌ fold  📞 call ${need}  💰 raise  🧨 all-in")

                e = discord.Embed(
                    title=f"{p.display_name}'s action",
                    description=f"Pot ${self.pot}  Round bet ${round_current}\n"
                                f"Your round: ${self.bets[pid]}  Your bank ${bal}\n{desc}",
                    color=0x4caf50
                )
                m = await ctx.send(embed=e)
                for em in options:
                    await m.add_reaction(em)

                choice = await self.ask_reaction(ctx, m, p, set(options), timeout=50)
                with contextlib.suppress(Exception):
                    await m.delete()

                if choice is None:
                    await ctx.send(f"{p.display_name} timed out and folds.")
                    self.in_hand.discard(pid)
                    continue

                if choice == '❌':
                    self.in_hand.discard(pid)
                    continue

                if choice == '✅' and can_check:
                    await ctx.send(f"{p.display_name} checks.")
                    acted_since_raise.add(pid)
                    continue

                if choice == '📞' and not can_check:
                    call_amt = min(need, get_balance(ctx.guild.id, pid))
                    add_balance(ctx.guild.id, pid, -call_amt)
                    self.bets[pid] += call_amt
                    self.pot += call_amt
                    await ctx.send(f"{p.display_name} calls ${call_amt}.")
                    acted_since_raise.add(pid)
                    continue

                if choice == '🧨':
                    shove = get_balance(ctx.guild.id, pid)
                    add_balance(ctx.guild.id, pid, -shove)
                    self.bets[pid] += shove
                    self.pot += shove
                    if self.bets[pid] > round_current:
                        round_current = self.bets[pid]
                        self.current_bet = round_current
                        acted_since_raise = {pid}
                        await ctx.send(f"{p.display_name} goes **ALL-IN** to ${round_current}.")
                    else:
                        acted_since_raise.add(pid)
                        await ctx.send(f"{p.display_name} goes **ALL-IN** for ${shove}.")
                    continue

                if choice == '💰':
                    # Minimum total for this street:
                    #  - if betting starts: >= BIG_BLIND
                    #  - else: >= round_current + BIG_BLIND
                    min_total = (round_current + BIG_BLIND) if round_current > 0 else BIG_BLIND
                    ask = await ctx.send(f"{p.mention} enter total bet for this street (min ${min_total}):")

                    def chk(m): return m.author == p and m.channel == ctx.channel and m.content.isdigit()

                    try:
                        msg = await self.bot.wait_for('message', timeout=35, check=chk)
                        total = int(msg.content)
                    except asyncio.TimeoutError:
                        with contextlib.suppress(Exception):
                            await ask.delete()
                        await ctx.send(f"{p.display_name} timed out; treating as check/call.")
                        if can_check:
                            acted_since_raise.add(pid)
                        else:
                            call_amt = min(need, get_balance(ctx.guild.id, pid))
                            add_balance(ctx.guild.id, pid, -call_amt)
                            self.bets[pid] += call_amt
                            self.pot += call_amt
                            acted_since_raise.add(pid)
                            await ctx.send(f"{p.display_name} calls ${call_amt}.")
                        continue
                    finally:
                        with contextlib.suppress(Exception):
                            await ask.delete()
                            with contextlib.suppress(Exception):
                                await msg.delete()

                    total = max(total, min_total)
                    addl = total - self.bets[pid]
                    addl = min(addl, get_balance(ctx.guild.id, pid))
                    add_balance(ctx.guild.id, pid, -addl)
                    self.bets[pid] += addl
                    self.pot += addl

                    # If this player pushed the round higher, it’s a raise
                    if self.bets[pid] > round_current:
                        round_current = self.bets[pid]
                        self.current_bet = round_current
                        acted_since_raise = {pid}  # reset; others must respond
                        await ctx.send(f"{p.display_name} raises to ${round_current}.")
                    else:
                        acted_since_raise.add(pid)

        self.current_bet = 0
        self.bets = {uid:0 for uid in self.bets}

    async def showdown(self, ctx):
        board_codes = [c['code'] for c in self.board]
        pool = {uid:self.hole[uid] for uid in self.in_hand}
        winners, scores = compare_hands(pool, board_codes)
        share = self.pot // len(winners) if winners else 0
        names = []
        for uid in winners:
            add_balance(ctx.guild.id, uid, share)
            member = discord.utils.get(self.players, id=uid)
            names.append(member.display_name)

        await self.post_board_image(ctx, "Board")
        lines = []
        for p in self.players:
            if p.id in self.in_hand:
                codes = ' '.join([c['code'] for c in self.hole[p.id]])
                lines.append(f"{p.display_name}: {codes}  —  {rank_to_text(scores[p.id])}")
        if lines:
            await ctx.send("Hands:\n" + "\n".join(lines))

        await ctx.send(f"Winner(s): {', '.join(names)} each win ${share}.  Pot ${self.pot}.")
        self.dealer = (self.dealer + 1) % len(self.players)

async def setup(bot):
    await bot.add_cog(Poker(bot))
