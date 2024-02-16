import discord
from discord.ext import commands
import requests
import asyncio
from dotenv import load_dotenv

load_dotenv(dotenv_path='keys.env')

class Poker(commands.Cog):
    """ 
    Games to play with the bot
    """
    def __init__(self, client):
        self.client = client
        self.link = "https://www.deckofcardsapi.com/api/deck/"
        self.game_state = {
        "players": [],
        "player_bets": {},  # To track player bets
        "player_cards": {},  # To track the cards each player has
        "deck_id": None,
        "community_cards": [],
        "pot": 0,
        "current_bet": 0,
        "dealer_index": 0,  # Tracks the dealer's position
        "current_player_index": 0  # Tracks whose turn it is
    }
        self.active_game = False
        self.game_state["dealer_index"] = 0
    
    def advance_dealer(self):
        # Rotate the dealer position
        self.game_state["dealer_index"] = (self.game_state["dealer_index"] + 1) % len(self.game_state['players'])

    def make_new_deck(self):
        new_deck = requests.get(f"{self.link}new/shuffle/?deck_count=1").json()
        return new_deck["deck_id"]

    def draw_x_cards(self, id, count):
        # Make sure to handle the case where the API request fails or doesn't return the expected result
        response = requests.get(f"{self.link}{id}/draw/?count={count}")
        if response.status_code == 200:
            drawn_cards = response.json().get("cards", [])
            return drawn_cards
        else:
            print(f"Failed to draw cards: HTTP {response.status_code}")
            return []

    @commands.command(help="Start a poker game")
    async def poker(self, ctx):
        if self.active_game:
            await ctx.send("A game is already in progress.")
            return

        # Initialize an empty list of players instead of automatically adding the command issuer
        self.game_state['players'] = []
        self.game_state['player_bets'] = {}  # Reset player bets for the new game
        self.active_game = True
        self.game_message_id = None  # Initialize this to None here

        embedVar = discord.Embed(
            title="Poker",
            description="Click the ♠️ emoji to add yourself to the game. When all players are in, click the ✅. If you wish to cancel the game, click ❌.",
            color=0x35654d
        )
        embedVar.set_footer(text=f"Poker game requested by {ctx.author.name}")
        msg = await ctx.send(embed=embedVar)
        self.game_message_id = msg.id  # Store the game message ID for reference in reaction checks

        await msg.add_reaction('♠️')
        await msg.add_reaction('✅')
        await msg.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) in ["✅", "❌"]

        while True:
            try:
                reaction, user = await self.client.wait_for("reaction_add", timeout=60.0, check=check)

                if str(reaction.emoji) == '❌':
                    await self.cancel_game(ctx)
                    await msg.delete()
                    break
                elif str(reaction.emoji) == '✅':
                    await self.start_game(ctx)
                    await msg.delete()
                    break
            except asyncio.TimeoutError:
                await self.cancel_game(ctx)
                await msg.delete()
                break

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
      if self.active_game and not user.bot:
          if reaction.message.id == self.game_message_id:  # Check if the reaction is on the game message
              if str(reaction.emoji) == '♠️':
                  # Check if the player is already in the game
                  if user in self.game_state['players']:
                      await reaction.message.channel.send(f"{user.display_name} is already in the game.")
                  else:
                      # Add the player to the game and set their betting amount
                      await self.add_player(user)
                      await reaction.message.channel.send(f"{user.display_name} was added to the game with a starting amount of $1000.")
                  await reaction.remove(user)  # Optional: remove the reaction after processing

    async def add_player(self, user):
        if user not in self.game_state['players']:
            self.game_state['players'].append(user)
            # Initialize the player's betting amount
            self.game_state['player_bets'][user.id] = 1000  # You might want to track bets in a separate dict

    async def start_game(self, ctx):
      # Create and shuffle a new deck
      self.game_state['deck_id'] = self.make_new_deck()
      self.active_game = True
      self.game_state["player_cards"] = {}
      # Deal 2 cards to each player
      for player in self.game_state['players']:
          player_cards = self.draw_x_cards(self.game_state['deck_id'], 2)
          self.game_state["player_cards"][player.id] = player_cards
          
          # Prepare to send each player their cards via DM
          if player.dm_channel is None:
              await player.create_dm()

          # Send the images of the cards
          for card in player_cards:
              try:
                  # Sending the image of the card
                  embed = discord.Embed(title="Your Poker Cards", description="Here are your cards:")
                  embed.set_image(url=card["image"])  # Use the correct key for the image URL
                  await player.dm_channel.send(embed=embed)
              except Exception as e:
                  await ctx.send(f"Failed to send cards to {player.name}: {e}")

      self.game_state["current_player_index"] = (self.game_state["dealer_index"] + 1) % len(self.game_state['players'])
      # Advance the dealer for the next round
      await self.betting_phase(ctx)
      self.advance_dealer()



    async def handle_call(self, ctx, player, highest_bet):
      player_id = player.id
      player_bet = self.game_state['player_bets'].get(player_id, 0)
      call_amount = highest_bet - player_bet

      # Check if the player has enough in their bank to call
      if self.game_state['player_bets'].get(player_id, 1000) >= call_amount:
          # Update the player's bank and the pot
          self.game_state['player_bets'][player_id] -= call_amount
          self.game_state['pot'] += call_amount

          await ctx.send(f"{player.display_name} calls with ${call_amount}, matching the highest bet. Total pot is now ${self.game_state['pot']}.")
      else:
          await ctx.send(f"{player.display_name}, you do not have enough funds to call.")


    async def handle_bet(self, ctx, player, highest_bet, bet_message):
      await bet_message.clear_reactions()
      bet_prompt_msg = await ctx.send(f"{player.mention}, enter your bet amount (must be higher than ${highest_bet}):")

      def bet_check(m):
          return m.author == player and m.content.isdigit() and int(m.content) > highest_bet

      try:
          bet_msg = await self.client.wait_for('message', timeout=30.0, check=bet_check)
      except asyncio.TimeoutError:
          await ctx.send(f"{player.display_name} did not respond with a bet amount in time.")
          return

      bet_amount = int(bet_msg.content)
      player_id = player.id

      # Check if the player has enough in their bank to cover the bet
      if self.game_state['player_bets'].get(player_id, 1000) >= bet_amount:
          # Update the player's bank and the pot
          self.game_state['player_bets'][player_id] -= bet_amount
          self.game_state['pot'] += bet_amount

          # Set the new highest bet
          self.game_state["current_bet"] = bet_amount

          await ctx.send(f"{player.display_name} bets ${bet_amount}. Total pot is now ${self.game_state['pot']}.")
      else:
          await ctx.send(f"{player.display_name}, you do not have enough funds to make this bet.")

      await bet_prompt_msg.delete()
      await bet_msg.delete()

    async def betting_phase(self, ctx):
      if not self.active_game or not self.game_state['players']:
          await ctx.send("No active poker game at the moment.")
          return

      highest_bet = 0
      players_acted = set()

      while True:
          all_have_acted = len(players_acted) == len(self.game_state['players'])
          all_have_matched_bet = all(self.game_state['player_bets'].get(player.id, 0) >= highest_bet for player in self.game_state['players'])

          if all_have_acted and all_have_matched_bet:
              break  # Exit loop when all players have acted and matched the highest bet

          for player_index in range(len(self.game_state['players'])):
              current_player = self.game_state['players'][player_index]
              player_id = current_player.id

              if player_id in players_acted and all_have_matched_bet:
                  continue  # Skip if the player has acted and all players have matched the highest bet

              # Constructing the embed with actions explanation
              actions_description = "💰 to raise/bet\n"
              if highest_bet > 0:
                  actions_description += "📞 to call (match the current highest bet)\n"
              else:
                  actions_description += "✅ to check (only if no bet has been made)\n"
              actions_description += "❌ to fold"

              embed = discord.Embed(title=f"{current_player.display_name}'s Turn to Bet",
                                    description=f"Current highest bet: ${highest_bet}\nYour bank: ${self.game_state['player_bets'].get(player_id, 1000)}\nTotal pot: ${self.game_state['pot']}",
                                    color=0x00ff00)
              embed.add_field(name="Options", value=actions_description, inline=False)
              bet_message = await ctx.send(embed=embed)

              valid_reactions = set()
              if highest_bet == 0 or self.game_state['player_bets'].get(player_id, 0) < highest_bet:
                  valid_reactions.add('💰')  # Allow raising/betting if the player hasn't met the highest bet
              if highest_bet > 0 and self.game_state['player_bets'].get(player_id, 0) < highest_bet:
                  valid_reactions.add('📞')  # Allow calling only if there's a bet to meet
              if highest_bet == 0:
                  valid_reactions.add('✅')  # Allow checking only if no bet has been placed
              valid_reactions.add('❌')  # Folding is always an option

              for emoji in valid_reactions:
                  await bet_message.add_reaction(emoji)

              reaction, user = await self.wait_for_reaction(ctx, bet_message, current_player, valid_reactions)

              if reaction.emoji == '💰':
                  await self.handle_bet(ctx, current_player, highest_bet, bet_message)
                  highest_bet = self.game_state["current_bet"]
              elif reaction.emoji == '📞':
                  await self.handle_call(ctx, current_player, highest_bet)
              elif reaction.emoji == '✅' and highest_bet == 0:
                  await ctx.send(f"{current_player.display_name} checks.")
              elif reaction.emoji == '❌':
                  await ctx.send(f"{current_player.display_name} folds.")
                  self.game_state['players'].remove(current_player)

              players_acted.add(player_id)
              await bet_message.delete()

              if len(self.game_state['players']) <= 1:  # Check if the game can continue
                  await ctx.send("Game cannot continue with less than 2 players.")
                  return

    
    async def wait_for_reaction(self, ctx, message, player, valid_reactions):
      def check(reaction, user):
          return user == player and str(reaction.emoji) in valid_reactions and reaction.message.id == message.id
      try:
          reaction, user = await self.client.wait_for('reaction_add', timeout=60.0, check=check)
          return reaction, user
      except asyncio.TimeoutError:
          await ctx.send(f"{player.display_name} did not respond in time and has been folded.")
          self.game_state['players'].remove(player)
          await message.delete()
          return None, None
    
    
    async def cancel_game(self, ctx):
        self.game_state = {
        "players": [],
        "player_bets": {},  # To track player bets
        "player_cards": {},  # To track the cards each player has
        "deck_id": None,
        "community_cards": [],
        "pot": 0,
        "current_bet": 0,
        "dealer_index": 0,  # Tracks the dealer's position
        "current_player_index": 0  # Tracks whose turn it is
    }
        self.game_state["dealer_index"] = 0
        self.active_game = False
        self.game_message_id = None  # Reset the game message ID
        await ctx.send("The poker game has been canceled.")


    @commands.command(help="Shows the current status of the poker game", aliases=["ps"])
    async def poker_status(self, ctx):
        if not self.active_game:
            await ctx.send("No active poker game at the moment.")
            return

        status_description = "👥 Players in the game:\n"
        for player in self.game_state['players']:
            # Retrieve the player's current bet from the game state
            player_bet = self.game_state['player_bets'].get(player.id, 0)
            status_description += f"- {player.display_name}: ${player_bet}\n"

        embedVar = discord.Embed(
            title="Poker Game Status",
            description=status_description,
            color=0x35654d
        )
        status_message = await ctx.send(embed=embedVar)
        await status_message.add_reaction('❌')

        def check(reaction, user):
            return user == ctx.author and str(reaction.emoji) == '❌'

        try:
            reaction, user = await self.client.wait_for("reaction_add", timeout=60.0, check=check)
            if str(reaction.emoji) == '❌':
                await self.cancel_game(ctx)
                await status_message.delete()
        except asyncio.TimeoutError:
            await status_message.delete()  # Clean up the message if no cancellation occurs

async def setup(client):
    await client.add_cog(Poker(client))
