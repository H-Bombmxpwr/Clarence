# cogs/poker.py
"""
Texas Hold'em, played in a channel with everyone who joins.

- One table per channel; players join from the lobby or between hands
- Proper button/blind rotation (including heads-up rules), min-raise rules, all-ins and side pots
- Hole cards are shown privately with the "My cards" button
- Chip balances persist per server in poker.json (inside DATA_DIR)
"""
import asyncio
import random
import time
from collections import deque
from dataclasses import dataclass, field
from io import BytesIO
from itertools import combinations
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from PIL import Image

from functionality.store import JsonStore

START_BANK = 1000
REFILL_AMOUNT = 500
REFILL_COOLDOWN = 24 * 3600
MAX_PLAYERS = 9
TURN_TIMEOUT = 60
BETWEEN_HANDS = 10
CARD_IMG = "https://deckofcardsapi.com/static/img/{}.png"
GREEN = 0x2f7d5c

RANKS = "23456789TJQKA"
SUITS = "SHDC"
SUIT_EMOJI = {"S": "♠️", "H": "♥️", "D": "♦️", "C": "♣️"}
RANK_NAME = {14: "Ace", 13: "King", 12: "Queen", 11: "Jack", 10: "Ten", 9: "Nine", 8: "Eight", 7: "Seven",
             6: "Six", 5: "Five", 4: "Four", 3: "Three", 2: "Two"}
CATEGORY = ["High Card", "One Pair", "Two Pair", "Three of a Kind", "Straight", "Flush", "Full House",
            "Four of a Kind", "Straight Flush"]


# ============================================================================ cards & hand evaluation

def card_str(card: str) -> str:
    rank = "10" if card[0] == "T" else card[0]
    return f"{rank}{SUIT_EMOJI[card[1]]}"


def cards_str(cards: list[str]) -> str:
    return " ".join(card_str(c) for c in cards) or "—"


def _value(card: str) -> int:
    return RANKS.index(card[0]) + 2


def _straight_high(values: set[int]) -> int:
    vals = set(values)
    if 14 in vals:
        vals.add(1)  # wheel
    for high in range(14, 4, -1):
        if all(v in vals for v in range(high - 4, high + 1)):
            return high
    return 0


def rank_five(cards: tuple[str, ...]) -> tuple:
    values = sorted((_value(c) for c in cards), reverse=True)
    suits = [c[1] for c in cards]
    counts = {v: values.count(v) for v in set(values)}
    groups = sorted(counts.items(), key=lambda kv: (kv[1], kv[0]), reverse=True)  # by count, then value
    flush = len(set(suits)) == 1
    straight = _straight_high(set(values)) if len(counts) == 5 else 0

    if straight and flush:
        return (8, straight)
    if groups[0][1] == 4:
        return (7, groups[0][0], groups[1][0])
    if groups[0][1] == 3 and groups[1][1] == 2:
        return (6, groups[0][0], groups[1][0])
    if flush:
        return (5, *values)
    if straight:
        return (4, straight)
    if groups[0][1] == 3:
        return (3, groups[0][0], *[v for v, _ in groups[1:]])
    if groups[0][1] == 2 and groups[1][1] == 2:
        return (2, groups[0][0], groups[1][0], groups[2][0])
    if groups[0][1] == 2:
        return (1, groups[0][0], *[v for v, _ in groups[1:]])
    return (0, *values)


def best_hand(cards: list[str]) -> tuple:
    return max(rank_five(combo) for combo in combinations(cards, 5))


def describe(rank: tuple) -> str:
    cat = rank[0]
    n = lambda v: RANK_NAME[v]
    if cat == 8:
        return "Royal Flush" if rank[1] == 14 else f"Straight Flush, {n(rank[1])} high"
    if cat == 7:
        return f"Four of a Kind, {n(rank[1])}s"
    if cat == 6:
        return f"Full House, {n(rank[1])}s full of {n(rank[2])}s"
    if cat == 5:
        return f"Flush, {n(rank[1])} high"
    if cat == 4:
        return f"Straight, {n(rank[1])} high"
    if cat == 3:
        return f"Three of a Kind, {n(rank[1])}s"
    if cat == 2:
        return f"Two Pair, {n(rank[1])}s and {n(rank[2])}s"
    if cat == 1:
        return f"Pair of {n(rank[1])}s"
    return f"{n(rank[1])} High"


def new_deck() -> list[str]:
    deck = [r + s for r in RANKS for s in SUITS]
    random.SystemRandom().shuffle(deck)
    return deck


# ============================================================================ images

_img_cache: dict[str, Image.Image] = {}


async def _card_image(session, card: str) -> Optional[Image.Image]:
    code = ("0" if card[0] == "T" else card[0]) + card[1]
    if code not in _img_cache:
        try:
            async with session.get(CARD_IMG.format(code), timeout=10) as r:
                r.raise_for_status()
                _img_cache[code] = Image.open(BytesIO(await r.read())).convert("RGBA")
        except Exception:
            return None
    return _img_cache[code]


async def cards_image(session, cards: list[str], height: int = 160) -> Optional[discord.File]:
    imgs = [await _card_image(session, c) for c in cards]
    if not imgs or any(i is None for i in imgs):
        return None

    def compose() -> BytesIO:
        pad = 8
        scaled = [im.resize((int(im.width * height / im.height), height), Image.LANCZOS) for im in imgs]
        canvas = Image.new("RGBA", (sum(i.width for i in scaled) + pad * (len(scaled) + 1), height + 2 * pad), (0, 100, 0, 255))
        x = pad
        for im in scaled:
            canvas.paste(im, (x, pad), im)
            x += im.width + pad
        buf = BytesIO()
        canvas.save(buf, format="PNG")
        buf.seek(0)
        return buf

    return discord.File(await asyncio.to_thread(compose), filename="cards.png")


# ============================================================================ bank

bank = JsonStore("poker.json")


def account(guild_id: int, user_id: int) -> dict:
    g = bank.guild(guild_id)
    acct = g.get(str(user_id))
    if acct is None or isinstance(acct, int):  # migrate old {uid: balance} format
        acct = {"balance": START_BANK if acct is None else acct, "hands": 0, "won": 0, "biggest_pot": 0,
                "net": 0, "last_refill": 0}
        g[str(user_id)] = acct
    return acct


# ============================================================================ table state

@dataclass
class Seat:
    member: discord.Member
    stack: int
    sat_with: int
    hole: list[str] = field(default_factory=list)
    folded: bool = False
    all_in: bool = False
    street_bet: int = 0     # chips put in on the current street
    hand_total: int = 0     # chips put in this hand
    leaving: bool = False
    timeouts: int = 0

    @property
    def id(self) -> int:
        return self.member.id

    @property
    def name(self) -> str:
        return self.member.display_name

    def pay(self, amount: int) -> int:
        amount = min(amount, self.stack)
        self.stack -= amount
        self.street_bet += amount
        self.hand_total += amount
        if self.stack == 0:
            self.all_in = True
        return amount


class RaiseModal(discord.ui.Modal, title="Raise"):
    amount = discord.ui.TextInput(label="Raise to (total bet this round)", max_length=10)

    def __init__(self, table: "Table", seat: Seat):
        super().__init__(timeout=TURN_TIMEOUT)
        self.table = table
        self.seat = seat
        lo, hi = table.raise_bounds(seat)
        self.amount.placeholder = f"{lo} – {hi}"
        self.amount.label = f"Raise to (min {lo}, all-in {hi})"[:45]

    async def on_submit(self, interaction: discord.Interaction):
        lo, hi = self.table.raise_bounds(self.seat)
        try:
            value = int(str(self.amount).replace(",", "").replace("$", "").strip())
        except ValueError:
            return await interaction.response.send_message("Enter a number.", ephemeral=True)
        if value >= hi:
            value = hi
        elif value < lo:
            return await interaction.response.send_message(f"The minimum raise is to **{lo}**.", ephemeral=True)
        await interaction.response.defer()
        self.table.resolve(self.seat, ("raise", value))


class TableView(discord.ui.View):
    """Buttons on the table message. Rebuilt on every update so labels stay current."""

    def __init__(self, table: "Table"):
        super().__init__(timeout=None)
        self.table = table
        t = table
        seat = t.current
        acting = t.state == "playing" and seat is not None

        if t.state in ("lobby", "between"):
            self.add_button("Join", discord.ButtonStyle.success, self.join, emoji="🪑")
            self.add_button("Leave", discord.ButtonStyle.secondary, self.leave)
            if t.state == "lobby":
                self.add_button("Start", discord.ButtonStyle.primary, self.start, emoji="▶️")
                self.add_button("Cancel", discord.ButtonStyle.danger, self.cancel)
            return

        # hole cards are only ever shown as replies only the clicking player can see (Discord can't push
        # those unprompted, so each player taps this once per hand)
        self.add_button("My cards", discord.ButtonStyle.primary, self.my_cards, emoji="🃏")
        if acting:
            to_call = t.to_call(seat)
            self.add_button("Fold", discord.ButtonStyle.danger, self.fold)
            if to_call == 0:
                self.add_button("Check", discord.ButtonStyle.success, self.check)
            else:
                self.add_button(f"Call {min(to_call, seat.stack)}", discord.ButtonStyle.success, self.call)
            lo, hi = t.raise_bounds(seat)
            if hi > t.current_bet and lo <= hi and to_call < seat.stack:
                self.add_button("Bet" if t.current_bet == 0 else "Raise", discord.ButtonStyle.primary, self.raise_)
            self.add_button(f"All-in ({seat.stack})", discord.ButtonStyle.secondary, self.allin, emoji="🔥")
        self.add_button("Join next hand", discord.ButtonStyle.secondary, self.join, row=1)
        self.add_button("Leave table", discord.ButtonStyle.secondary, self.leave, row=1)

    def add_button(self, label, style, callback, emoji=None, row=None):
        button = discord.ui.Button(label=label, style=style, emoji=emoji, row=row)
        button.callback = callback
        self.add_item(button)

    async def _own_turn(self, interaction: discord.Interaction) -> Optional[Seat]:
        seat = self.table.current
        if self.table.state != "playing" or not seat or interaction.user.id != seat.id:
            await interaction.response.send_message("It's not your turn.", ephemeral=True)
            return None
        return seat

    async def fold(self, interaction: discord.Interaction):
        if seat := await self._own_turn(interaction):
            await interaction.response.defer()
            self.table.resolve(seat, ("fold", 0))

    async def check(self, interaction: discord.Interaction):
        if seat := await self._own_turn(interaction):
            await interaction.response.defer()
            self.table.resolve(seat, ("check", 0))

    async def call(self, interaction: discord.Interaction):
        if seat := await self._own_turn(interaction):
            await interaction.response.defer()
            self.table.resolve(seat, ("call", 0))

    async def raise_(self, interaction: discord.Interaction):
        if seat := await self._own_turn(interaction):
            await interaction.response.send_modal(RaiseModal(self.table, seat))

    async def allin(self, interaction: discord.Interaction):
        if seat := await self._own_turn(interaction):
            await interaction.response.defer()
            self.table.resolve(seat, ("allin", 0))

    async def my_cards(self, interaction: discord.Interaction):
        seat = self.table.seat_of(interaction.user.id)
        if not seat or not seat.hole:
            return await interaction.response.send_message("You aren't in this hand.", ephemeral=True)
        text = f"Your cards: **{cards_str(seat.hole)}**"
        if len(self.table.board) >= 3:
            text += f"\nBoard: {cards_str(self.table.board)}\nYou have: **{describe(best_hand(seat.hole + self.table.board))}**"
        text += f"\nStack: **{seat.stack}**" + (" • folded" if seat.folded else "")
        await interaction.response.defer(ephemeral=True, thinking=True)
        image = await cards_image(self.table.cog.bot.session, seat.hole, height=140)
        if image:
            await interaction.followup.send(text, file=image, ephemeral=True)
        else:
            await interaction.followup.send(text, ephemeral=True)

    async def join(self, interaction: discord.Interaction):
        await self.table.join(interaction)

    async def leave(self, interaction: discord.Interaction):
        await self.table.leave(interaction)

    async def start(self, interaction: discord.Interaction):
        t = self.table
        if interaction.user.id != t.host.id:
            return await interaction.response.send_message("Only the host can start the game.", ephemeral=True)
        if len(t.seats) < 2:
            return await interaction.response.send_message("Need at least 2 players.", ephemeral=True)
        await interaction.response.defer()
        t.start_task()

    async def cancel(self, interaction: discord.Interaction):
        t = self.table
        if interaction.user.id != t.host.id and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Only the host can cancel.", ephemeral=True)
        await interaction.response.edit_message(content="Game cancelled.", embed=None, view=None, attachments=[])
        t.cog.tables.pop(t.channel.id, None)


class Table:
    def __init__(self, cog: "Poker", channel: discord.TextChannel, host: discord.Member, small_blind: int):
        self.cog = cog
        self.channel = channel
        self.guild = channel.guild
        self.host = host
        self.sb = small_blind
        self.bb = small_blind * 2
        self.seats: list[Seat] = []        # seated players, in seat order
        self.waiting: list[Seat] = []      # joined mid-hand, sit down next hand
        self.state = "lobby"               # lobby | playing | between | ended
        self.button = -1
        self.hand_no = 0
        self.message: Optional[discord.Message] = None
        self.log: deque[str] = deque(maxlen=8)
        self.ending = False

        # per-hand state
        self.in_hand: list[Seat] = []
        self.deck: list[str] = []
        self.board: list[str] = []
        self.current: Optional[Seat] = None
        self.current_bet = 0
        self.min_raise = 0
        self.street = ""
        self._future: Optional[asyncio.Future] = None
        self._task: Optional[asyncio.Task] = None
        self._board_file_cards: list[str] = []

    # ------------------------------------------------------------------ seating

    def seat_of(self, user_id: int) -> Optional[Seat]:
        return next((s for s in self.seats + self.waiting if s.id == user_id), None)

    async def join(self, interaction: discord.Interaction):
        user = interaction.user
        if self.seat_of(user.id):
            return await interaction.response.send_message("You're already at the table.", ephemeral=True)
        if self.cog.seated_anywhere(user.id):
            return await interaction.response.send_message("You're already playing at another table.", ephemeral=True)
        if len(self.seats) + len(self.waiting) >= MAX_PLAYERS:
            return await interaction.response.send_message("The table is full.", ephemeral=True)
        balance = account(self.guild.id, user.id)["balance"]
        if balance < self.bb:
            return await interaction.response.send_message(
                f"You only have **{balance}** chips (big blind is {self.bb}). Try `/poker refill`.", ephemeral=True)
        seat = Seat(member=user, stack=balance, sat_with=balance)
        if self.state == "playing":
            self.waiting.append(seat)
            await interaction.response.send_message("You'll be dealt in next hand.", ephemeral=True)
        else:
            self.seats.append(seat)
            await interaction.response.defer()
        self.log.append(f"**{seat.name}** sat down with {balance}")
        await self.update()

    async def leave(self, interaction: discord.Interaction):
        seat = self.seat_of(interaction.user.id)
        if not seat:
            return await interaction.response.send_message("You're not at the table.", ephemeral=True)
        if seat in self.waiting:
            self.waiting.remove(seat)
        elif self.state == "playing":
            # never reshuffle seats mid-hand; the game loop removes leaving players before the next deal
            seat.leaving = True
            await interaction.response.send_message("You'll leave the table after this hand.", ephemeral=True)
            if self.current is seat:
                self.resolve(seat, ("fold", 0))
            return
        else:
            self.seats.remove(seat)
            self.settle_seat(seat)
        await interaction.response.defer()
        self.log.append(f"**{seat.name}** left with {seat.stack}")
        if self.state == "lobby" and seat.id == self.host.id and self.seats:
            self.host = self.seats[0].member
        await self.update()

    def settle_seat(self, seat: Seat):
        acct = account(self.guild.id, seat.id)
        acct["balance"] = seat.stack
        bank.save()

    # ------------------------------------------------------------------ betting helpers

    def to_call(self, seat: Seat) -> int:
        return max(0, self.current_bet - seat.street_bet)

    def raise_bounds(self, seat: Seat) -> tuple[int, int]:
        """(minimum legal raise-to amount, all-in amount)"""
        all_in_to = seat.street_bet + seat.stack
        min_to = self.current_bet + self.min_raise if self.current_bet else self.bb
        return min(min_to, all_in_to), all_in_to

    def resolve(self, seat: Seat, action: tuple[str, int]):
        if self._future and not self._future.done() and self.current is seat:
            self._future.set_result(action)

    def pot_total(self) -> int:
        return sum(s.hand_total for s in self.in_hand)

    # ------------------------------------------------------------------ rendering

    def embed(self) -> discord.Embed:
        if self.state == "lobby":
            e = discord.Embed(title="Texas Hold'em — waiting for players", color=GREEN,
                              description=f"Blinds **{self.sb}/{self.bb}** • host {self.host.mention}\n"
                                          f"Press **Join** to sit down with your chip balance. The host presses **Start** (2–{MAX_PLAYERS} players).")
            e.add_field(name=f"Players ({len(self.seats)})",
                        value="\n".join(f"{s.member.mention} — {s.stack}" for s in self.seats) or "Nobody yet", inline=False)
            return e

        title = f"Hand #{self.hand_no}" + (f" — {self.street}" if self.street else "")
        e = discord.Embed(title=title, color=GREEN)
        e.description = f"**Board:** {cards_str(self.board)}\n**Pot:** {self.pot_total()}" + (
            f" • to call: {self.current_bet}" if self.current_bet else "")
        lines = []
        for i, s in enumerate(self.seats):
            tags = []
            if i == self.button:
                tags.append("🔘")
            if s is self.current:
                tags.append("👉")
            status = "folded" if s.folded else "ALL-IN" if s.all_in else ""
            bet = f" • bet {s.street_bet}" if s.street_bet else ""
            if s not in self.in_hand:
                status = "sitting out"
            name = f"~~{s.name}~~" if s.folded else f"**{s.name}**"
            lines.append(f"{''.join(tags)} {name} — {s.stack}{bet}" + (f" • *{status}*" if status else ""))
        for s in self.waiting:
            lines.append(f"{s.name} — {s.stack} • *next hand*")
        e.add_field(name="Table", value="\n".join(lines)[:1024], inline=False)
        if self.log:
            e.add_field(name="Action", value="\n".join(self.log)[:1024], inline=False)
        if self.state == "playing" and self.current:
            e.set_footer(text=f"{self.current.name} to act • {TURN_TIMEOUT}s • press My cards to see your hand")
        elif self.state == "between":
            e.set_footer(text=f"Next hand in {BETWEEN_HANDS}s • join or leave now")
        if self.board:
            e.set_image(url="attachment://cards.png")
        return e

    async def update(self):
        kwargs = {"embed": self.embed(), "view": TableView(self) if self.state != "ended" else None}
        if self.board != self._board_file_cards:
            file = await cards_image(self.cog.bot.session, self.board) if self.board else None
            kwargs["attachments"] = [file] if file else []
            self._board_file_cards = list(self.board)
        try:
            if self.message:
                await self.message.edit(**kwargs)
            else:
                files = kwargs.pop("attachments", [])
                self.message = await self.channel.send(files=files, **kwargs)
        except discord.NotFound:
            files = kwargs.pop("attachments", None) or []
            self.message = await self.channel.send(files=files, **kwargs)
        except discord.HTTPException:
            pass

    # ------------------------------------------------------------------ game loop

    def start_task(self):
        if not self._task:
            self._task = asyncio.create_task(self.run())

    async def run(self):
        try:
            while not self.ending:
                self.seats.extend(self.waiting)
                self.waiting.clear()
                for s in [s for s in self.seats if s.stack < self.bb or s.leaving]:
                    self.seats.remove(s)
                    self.settle_seat(s)
                    self.log.append(f"**{s.name}** left the table with {s.stack}")
                if len(self.seats) < 2:
                    break
                await self.play_hand()
                if self.ending:
                    break
                self.state = "between"
                self.current = None
                await self.update()
                await asyncio.sleep(BETWEEN_HANDS)
        except Exception as e:
            print(f"[poker] game crashed: {e!r}")
            await self.channel.send("The poker game hit an error and ended. Balances from completed hands were saved.")
        finally:
            await self.finish()

    async def finish(self):
        self.state = "ended"
        self.current = None
        for s in self.seats + self.waiting:
            self.settle_seat(s)
        self.cog.tables.pop(self.channel.id, None)
        everyone = self.seats + self.waiting
        if everyone:
            e = discord.Embed(title="Game over — final stacks", color=0xffd700)
            for i, s in enumerate(sorted(everyone, key=lambda s: s.stack, reverse=True), 1):
                medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(i, f"{i}.")
                delta = s.stack - s.sat_with
                e.add_field(name=f"{medal} {s.name}", value=f"{s.stack} ({'+' if delta >= 0 else ''}{delta})", inline=False)
            await self.channel.send(embed=e)
        if self.message:
            try:
                await self.message.edit(view=None)
            except discord.HTTPException:
                pass

    def next_index(self, start: int, cond) -> int:
        n = len(self.seats)
        for step in range(1, n + 1):
            i = (start + step) % n
            if cond(self.seats[i]):
                return i
        return start

    async def play_hand(self):
        self.hand_no += 1
        self.state = "playing"
        self.log.clear()
        self.deck = new_deck()
        self.board = []
        self.current_bet = 0
        self.min_raise = self.bb
        for s in self.seats:
            s.hole, s.folded, s.all_in, s.street_bet, s.hand_total = [], False, False, 0, 0
        self.in_hand = [s for s in self.seats if s.stack > 0]

        # button and blinds
        self.button = self.next_index(self.button, lambda s: s in self.in_hand)
        if len(self.in_hand) == 2:  # heads-up: button posts the small blind
            sb_i = self.button
        else:
            sb_i = self.next_index(self.button, lambda s: s in self.in_hand)
        bb_i = self.next_index(sb_i, lambda s: s in self.in_hand)
        sb_seat, bb_seat = self.seats[sb_i], self.seats[bb_i]
        sb_paid = sb_seat.pay(self.sb)
        bb_paid = bb_seat.pay(self.bb)
        self.current_bet = self.bb  # a short all-in big blind still means a full big blind to call
        self.log.append(f"Blinds: {sb_seat.name} {sb_paid}, {bb_seat.name} {bb_paid}")

        for _ in range(2):
            for s in self.in_hand:
                s.hole.append(self.deck.pop())
        self.log.append("Cards dealt — tap **My cards** to see yours (only you can see it)")

        # pre-flop: first to act is left of the big blind (heads-up that's the button/small blind)
        self.street = "Pre-flop"
        first = self.next_index(bb_i, lambda s: s in self.in_hand)
        await self.betting_round(first)

        for street, count in (("Flop", 3), ("Turn", 1), ("River", 1)):
            if self.players_left() < 2:
                break
            self.deck.pop()  # burn
            self.board += [self.deck.pop() for _ in range(count)]
            self.street = street
            for s in self.in_hand:
                s.street_bet = 0
            self.current_bet = 0
            self.min_raise = self.bb
            self.log.append(f"— {street}: {cards_str(self.board)}")
            if self.can_bet():
                first = self.next_index(self.button, lambda s: s in self.in_hand and not s.folded)
                await self.betting_round(first)
            else:
                await self.update()
                await asyncio.sleep(2)  # all-in run-out: show each street

        await self.showdown()

    def players_left(self) -> int:
        return sum(1 for s in self.in_hand if not s.folded)

    def can_bet(self) -> bool:
        return sum(1 for s in self.in_hand if not s.folded and not s.all_in) >= 2

    async def betting_round(self, first_index: int):
        n = len(self.seats)
        pending = {s.id for s in self.in_hand if not s.folded and not s.all_in}
        i = first_index
        while pending and self.players_left() > 1:
            seat = self.seats[i % n]
            i += 1
            if seat.id not in pending:
                continue
            if seat.folded or seat.all_in or seat not in self.in_hand:
                pending.discard(seat.id)
                continue
            # last player with chips who has already matched the bet has nothing to decide
            others_can_act = any(not s.folded and not s.all_in and s is not seat for s in self.in_hand)
            if not others_can_act and self.to_call(seat) == 0:
                pending.discard(seat.id)
                continue

            action, amount = await self.get_action(seat)
            pending.discard(seat.id)
            to_call = self.to_call(seat)

            if action == "fold":
                seat.folded = True
                self.log.append(f"{seat.name} folds")
            elif action == "check" and to_call == 0:
                self.log.append(f"{seat.name} checks")
            elif action in ("call", "check"):
                paid = seat.pay(to_call)
                self.log.append(f"{seat.name} calls {paid}" + (" (all-in)" if seat.all_in else ""))
            elif action in ("raise", "allin"):
                target = seat.street_bet + seat.stack if action == "allin" else amount
                if target <= self.current_bet:  # all-in for less than a call
                    paid = seat.pay(target - seat.street_bet)
                    self.log.append(f"{seat.name} calls all-in for {paid}")
                    continue
                raise_size = target - self.current_bet
                seat.pay(target - seat.street_bet)
                verb = "bets" if self.current_bet == 0 else "raises to"
                self.log.append(f"{seat.name} {verb} {target}" + (" (all-in)" if seat.all_in else ""))
                if raise_size >= self.min_raise:
                    # full raise: everyone else gets to act again
                    self.min_raise = raise_size
                    pending = {s.id for s in self.in_hand if not s.folded and not s.all_in and s is not seat}
                else:
                    # short all-in: players who haven't matched it still need to act
                    pending |= {s.id for s in self.in_hand if not s.folded and not s.all_in
                                and s is not seat and s.street_bet < target}
                self.current_bet = target
        self.current = None

    async def get_action(self, seat: Seat) -> tuple[str, int]:
        if seat.leaving:
            return ("fold", 0)
        self.current = seat
        loop = asyncio.get_running_loop()
        self._future = loop.create_future()
        await self.update()
        ping = None
        try:
            to_call = self.to_call(seat)
            ping = await self.channel.send(
                f"{seat.member.mention}, your turn — " + (f"**{to_call}** to call." if to_call else "you can check."),
                allowed_mentions=discord.AllowedMentions(users=True))
        except discord.HTTPException:
            pass
        try:
            result = await asyncio.wait_for(self._future, timeout=TURN_TIMEOUT)
            seat.timeouts = 0
        except asyncio.TimeoutError:
            seat.timeouts += 1
            result = ("check", 0) if self.to_call(seat) == 0 else ("fold", 0)
            self.log.append(f"{seat.name} timed out")
            if seat.timeouts >= 2:
                seat.leaving = True
                self.log.append(f"{seat.name} will be removed for inactivity")
        if ping:
            try:
                await ping.delete()
            except discord.HTTPException:
                pass
        self._future = None
        return result

    # ------------------------------------------------------------------ showdown & pots

    def build_pots(self) -> list[tuple[int, list[Seat]]]:
        """Split contributions into main/side pots: [(amount, eligible seats)]."""
        contributors = [s for s in self.in_hand if s.hand_total > 0]
        levels = sorted({s.hand_total for s in contributors if not s.folded})
        pots, prev = [], 0
        for level in levels:
            amount = sum(min(s.hand_total, level) - min(s.hand_total, prev) for s in contributors)
            eligible = [s for s in contributors if not s.folded and s.hand_total >= level]
            if amount:
                pots.append((amount, eligible))
            prev = level
        # chips from folded players above the highest live contribution go to the last pot
        leftover = sum(max(0, s.hand_total - prev) for s in contributors)
        if leftover and pots:
            pots[-1] = (pots[-1][0] + leftover, pots[-1][1])
        return pots

    async def showdown(self):
        self.current = None
        self.street = "Showdown"
        live = [s for s in self.in_hand if not s.folded]
        total_pot = self.pot_total()
        winnings: dict[int, int] = {}

        if len(live) == 1:
            winner = live[0]
            winnings[winner.id] = total_pot
            winner.stack += total_pot
            self.log.append(f"{winner.name} wins {total_pot} (everyone folded)")
            ranks = {}
        else:
            ranks = {s.id: best_hand(s.hole + self.board) for s in live}
            # odd chips go to the first winner left of the button
            order = [self.seats[(self.button + k) % len(self.seats)] for k in range(1, len(self.seats) + 1)]
            for amount, eligible in self.build_pots():
                best = max(ranks[s.id] for s in eligible)
                winners = [s for s in order if s in eligible and ranks[s.id] == best]
                share, odd = divmod(amount, len(winners))
                for k, w in enumerate(winners):
                    won = share + (1 if k < odd else 0)
                    w.stack += won
                    winnings[w.id] = winnings.get(w.id, 0) + won

        # results message
        e = discord.Embed(title=f"Hand #{self.hand_no} results", color=0xffd700,
                          description=f"**Board:** {cards_str(self.board)}\n**Pot:** {total_pot}")
        for s in self.in_hand:
            won = winnings.get(s.id, 0)
            if s.folded:
                continue
            hand = describe(ranks[s.id]) if ranks else ""
            e.add_field(name=f"{s.name}" + (f" +{won}" if won else ""),
                        value=f"{cards_str(s.hole) if ranks else '(cards hidden)'}\n{hand}", inline=True)
        await self.channel.send(embed=e)
        for wid, amount in winnings.items():
            name = next(s.name for s in self.in_hand if s.id == wid)
            if ranks:
                self.log.append(f"{name} wins {amount}")

        # persist balances and stats
        for s in self.in_hand:
            acct = account(self.guild.id, s.id)
            acct["hands"] += 1
            acct["net"] += s.stack - acct["balance"]
            acct["balance"] = s.stack
            if winnings.get(s.id):
                acct["won"] += 1
                acct["biggest_pot"] = max(acct["biggest_pot"], winnings[s.id])
        bank.save()
        await self.update()


# ============================================================================ cog

class Poker(commands.Cog):
    """Texas Hold'em"""

    poker = app_commands.Group(name="poker", description="Texas Hold'em poker", guild_only=True)

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tables: dict[int, Table] = {}

    def seated_anywhere(self, user_id: int) -> bool:
        return any(table.seat_of(user_id) for table in self.tables.values())

    async def cog_unload(self):
        for table in list(self.tables.values()):
            table.ending = True
            if table._task:
                table._task.cancel()
            for s in table.seats + table.waiting:
                table.settle_seat(s)

    @poker.command(name="start", description="Open a poker table in this channel")
    @app_commands.describe(small_blind="Small blind (big blind is double)")
    @app_commands.choices(small_blind=[app_commands.Choice(name=f"{v}/{v * 2}", value=v) for v in (5, 10, 25, 50, 100)])
    async def start(self, interaction: discord.Interaction, small_blind: Optional[app_commands.Choice[int]] = None):
        if interaction.channel.id in self.tables:
            return await interaction.response.send_message("There's already a table in this channel.", ephemeral=True)
        sb = small_blind.value if small_blind else 10
        balance = account(interaction.guild.id, interaction.user.id)["balance"]
        table = Table(self, interaction.channel, interaction.user, sb)
        self.tables[interaction.channel.id] = table
        if balance >= sb * 2 and not self.seated_anywhere(interaction.user.id):
            table.seats.append(Seat(member=interaction.user, stack=balance, sat_with=balance))
        await interaction.response.send_message(embed=table.embed(), view=TableView(table))
        table.message = await interaction.original_response()

    @poker.command(name="end", description="End the poker game in this channel after the current hand")
    async def end(self, interaction: discord.Interaction):
        table = self.tables.get(interaction.channel.id)
        if not table:
            return await interaction.response.send_message("No game in this channel.", ephemeral=True)
        if interaction.user.id != table.host.id and not interaction.user.guild_permissions.manage_messages:
            return await interaction.response.send_message("Only the host or a moderator can end the game.", ephemeral=True)
        if table.state == "lobby":
            self.tables.pop(interaction.channel.id, None)
            await table.message.edit(content="Game cancelled.", embed=None, view=None)
            return await interaction.response.send_message("Cancelled.", ephemeral=True)
        table.ending = True
        await interaction.response.send_message("The game will end after this hand.")
        if table.state == "between" and table._task:
            table._task.cancel()

    @poker.command(name="balance", description="Check chip balance and stats")
    async def balance(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        member = member or interaction.user
        acct = account(interaction.guild.id, member.id)
        bank.save()
        e = discord.Embed(title=f"{member.display_name}", color=0xffd700)
        e.add_field(name="Chips", value=f"{acct['balance']:,}")
        e.add_field(name="Hands played", value=str(acct["hands"]))
        e.add_field(name="Hands won", value=str(acct["won"]))
        e.add_field(name="Net", value=f"{'+' if acct['net'] >= 0 else ''}{acct['net']:,}")
        e.add_field(name="Biggest pot", value=f"{acct['biggest_pot']:,}")
        await interaction.response.send_message(embed=e)

    @poker.command(name="leaderboard", description="Richest players on this server")
    async def leaderboard(self, interaction: discord.Interaction):
        g = bank.guild(interaction.guild.id)
        rows = []
        for uid in list(g):
            acct = account(interaction.guild.id, int(uid))
            rows.append((acct["balance"], int(uid), acct))
        rows.sort(reverse=True)
        if not rows:
            return await interaction.response.send_message("Nobody has played yet. `/poker start`!", ephemeral=True)
        lines = [f"{['🥇', '🥈', '🥉'][i] if i < 3 else f'`{i + 1}.`'} <@{uid}> — **{bal:,}** ({a['won']}/{a['hands']} hands won)"
                 for i, (bal, uid, a) in enumerate(rows[:15])]
        await interaction.response.send_message(embed=discord.Embed(title="Poker leaderboard", description="\n".join(lines), color=0xffd700),
                                                allowed_mentions=discord.AllowedMentions.none())

    @poker.command(name="refill", description=f"Broke? Get {REFILL_AMOUNT} chips (once a day)")
    async def refill(self, interaction: discord.Interaction):
        acct = account(interaction.guild.id, interaction.user.id)
        if self.seated_anywhere(interaction.user.id):
            return await interaction.response.send_message("You can't refill while sitting at a table.", ephemeral=True)
        if acct["balance"] >= REFILL_AMOUNT:
            return await interaction.response.send_message(f"You still have {acct['balance']} chips.", ephemeral=True)
        wait = acct["last_refill"] + REFILL_COOLDOWN - time.time()
        if wait > 0:
            return await interaction.response.send_message(f"You can refill again <t:{int(time.time() + wait)}:R>.", ephemeral=True)
        acct["balance"] = REFILL_AMOUNT
        acct["last_refill"] = time.time()
        bank.save()
        await interaction.response.send_message(f"Refilled to **{REFILL_AMOUNT}** chips.")

    @poker.command(name="give", description="Give chips to a player (admin)")
    @app_commands.default_permissions(administrator=True)
    @app_commands.checks.has_permissions(administrator=True)
    async def give(self, interaction: discord.Interaction, member: discord.Member, amount: app_commands.Range[int, -1_000_000, 1_000_000]):
        if self.seated_anywhere(member.id):
            return await interaction.response.send_message("They're sitting at a table — try after the game.", ephemeral=True)
        acct = account(interaction.guild.id, member.id)
        acct["balance"] = max(0, acct["balance"] + amount)
        bank.save()
        await interaction.response.send_message(f"{member.mention} now has **{acct['balance']:,}** chips.")


async def setup(bot: commands.Bot):
    await bot.add_cog(Poker(bot))
