import discord
from discord.ext import commands,tasks
from discord import Member
from discord.utils import get
from datetime import date
import functionality.functions
import os
import json
from dotenv import load_dotenv
import asyncio
from storage.Lists_Storage import load
from discord.ui import Button,View
from better_profanity import profanity

load_dotenv(dotenv_path = 'keys.env')

class Moderation(commands.Cog):
  """ 
  Moderation commands that require specific permissions to use
  """
  def __init__(self,client):
      self.client = client


  @commands.command(help="Ban a user")
  @commands.has_permissions(ban_members=True)
  async def ban(self, ctx, member: discord.Member, *, reason=None):
    # Check if the target member is the bot's owner
    if member.id == self.client.owner_id:
      await ctx.send('I cannot ban my creator.')
      return

    # Proceed to ban the member
    await member.ban(reason=reason)
    embed = discord.Embed(title="User Banned!",
                          description=f"**{member}** was banned by **{ctx.author}**!",
                          color=0x800000)
    embed.add_field(name="Reason", value=reason if reason else "No reason provided.", inline=False)
    embed.set_footer(text=f'Banned on {date.today()}')
    embed.set_thumbnail(url=member.avatar.url)
    await ctx.send(embed=embed)

  @commands.command(help="Unban a user")
  @commands.has_permissions(administrator=True)
  async def unban(self, ctx, *, member_identifier: str):
    banned_users = await ctx.guild.bans()
    member_name, member_discriminator = member_identifier.split('#', 1)

    for ban_entry in banned_users:
        user = ban_entry.user

        if (user.name, user.discriminator) == (member_name, member_discriminator):
            await ctx.guild.unban(user)
            await ctx.send(f'Unbanned {user.mention}')
            return
    
    await ctx.send(f'User {member_identifier} not found in ban list.')

  #generate a list of banned members
  
  @commands.command(help="List of banned users from the guild")
  @commands.has_permissions(ban_members=True)
  async def banlist(self, ctx):
    banned_users = await ctx.guild.bans()
    if not banned_users:
        await ctx.send("No users are currently banned.")
        return

    banned_list = '\n'.join(f'{user.name}#{user.discriminator}' for _, user in banned_users)
    # Splitting the ban list into chunks of 1024 characters to fit within the embed field limit
    banned_list_chunks = [banned_list[i:i+1024] for i in range(0, len(banned_list), 1024)]

    embed = discord.Embed(title='Banned Users:', color=0x800000)
    for index, chunk in enumerate(banned_list_chunks, start=1):
        embed.add_field(name=f'Page {index}', value=chunk, inline=False)

    await ctx.send(embed=embed)



  #get the latency of the bot
  @commands.command(help = 'Find the latency of the bot')
  async def ping(self,ctx):
    await ctx.channel.send(f" `{round(self.client.latency * 1000)}` ms")


  #list the roles in the server
  @commands.command(help = "List the guild roles")
  async def roles(self,ctx):
    roles = ""
    for role in ctx.guild.roles:
      roles = roles + str(role) + "\n"

    embedVar = discord.Embed(title = "Active Roles", description = roles, color = ctx.author.color)
    embedVar.add_field(name = "Total Roles", value = len(ctx.guild.roles), inline = False)
    await ctx.send(embed= embedVar)  


  #mute a user from all channels
  @commands.command(help="Mute a user from sending messages")
  @commands.has_permissions(manage_roles=True)
  async def mute(self, ctx, member: discord.Member):
      # Check if the member trying to mute is the bot or the server owner
      if member == ctx.guild.owner or member.bot:
          await ctx.send("I cannot mute the server owner or bots.")
          return

      # Find or create the Muted role
      muted_role = get(ctx.guild.roles, name="Muted")
      if not muted_role:
          muted_role = await ctx.guild.create_role(name="Muted", permissions=discord.Permissions(send_messages=False, speak=False))
          for channel in ctx.guild.channels:
              await channel.set_permissions(muted_role, send_messages=False, speak=False, add_reactions=False)

      await member.add_roles(muted_role)
      await ctx.send(f"{member.mention} has been muted.")


  #unmute a user
  @commands.command(help='Unmutes a user')
  @commands.has_permissions(manage_roles=True)
  async def unmute(self, ctx, member: discord.Member):
      muted_role = get(ctx.guild.roles, name="Muted")
      if not muted_role:
          await ctx.send("The 'Muted' role does not exist.")
          return

      if muted_role in member.roles:
          await member.remove_roles(muted_role)
          await ctx.send(f"{member.mention} has been unmuted.")
      else:
          await ctx.send(f"{member.mention} is not muted.")

  #change the server prefix
  @commands.command(help = "Change Server Prefix")
  @commands.has_permissions(administrator = True)
  async def prefix(self,ctx,prefix = None):
    if prefix == None:
      await ctx.send("Please send a new prefix\n i.e. `prefix $`")
    else:
      with open("storage/prefixes.json","r") as f:
        prefixes = json.load(f)

      prefixes[str(ctx.guild.id)] = prefix
  
      with open("storage/prefixes.json","w") as f:
        json.dump(prefixes,f, indent = 4)

      await ctx.send(f"Prefix changed to: `{prefix}`")
  
  #gives the administrator role
  @commands.command(help='Gives a user the administrator role', aliases=['gvad'])
  @commands.has_permissions(administrator=True)
  async def giveadmin(self, ctx, member: discord.Member):
      # Prevent granting admin role to bots or the server owner
      if member.bot or member == ctx.guild.owner:
          await ctx.send("I cannot give the Admin role to bots or the server owner.")
          return

      admin_role = get(ctx.guild.roles, name="Admin")
      if not admin_role:
          # If the Admin role does not exist, create it with administrator permissions
          admin_role = await ctx.guild.create_role(name="Admin", permissions=discord.Permissions(administrator=True), colour=discord.Colour(0x280137), hoist=True)
          await ctx.send('Admin Role created!')

      if admin_role in member.roles:
          await ctx.send(f"{member.mention} already has the Admin role.")
      else:
          await member.add_roles(admin_role)
          await ctx.send(f"{member.mention} was given the Admin role.")




  @commands.command(help='Removes the admin role', aliases=['rmad'])
  @commands.has_permissions(administrator=True)
  async def removeadmin(self, ctx, member: discord.Member):
      admin_role = get(ctx.guild.roles, name="Admin")
      if not admin_role:
          await ctx.send("The 'Admin' role does not exist.")
          return

      if admin_role not in member.roles:
          await ctx.send(f"{member.mention} does not have the Admin role.")
      else:
          await member.remove_roles(admin_role)
          await ctx.send(f"{member.mention}'s Admin role has been removed.")



  #prune x number of messages
  @commands.command(help='Delete a specified number of messages, regardless of sender', aliases=['cl'])
  @commands.has_permissions(manage_messages=True)  # Ensure the user has permission to manage messages
  @commands.bot_has_permissions(manage_messages=True)  # Ensure the bot has permission to manage messages
  async def clean(self, ctx, limit: int):
      if limit < 1 or limit > 250:  # Check for a valid limit
          await ctx.send('Please specify a limit between 1 and 250.')
          return

      purged_messages = await ctx.channel.purge(limit=limit + 1)  # +1 to include the command message itself

      # Send confirmation message that self-deletes after 5 seconds to avoid clutter
      confirmation_message = f'Cleared {len(purged_messages) - 1} messages.'  # -1 to exclude the command message
      await ctx.send(confirmation_message, delete_after=5)


  #kick a user
  @commands.command(help="Kick a user from the server")
  @commands.has_permissions(kick_members=True)
  async def kick(self, ctx, member: discord.Member, *, reason=None):
      # Prevent kicking the server owner or bots
      if member == ctx.guild.owner or member.bot:
          await ctx.send("I cannot kick the server owner or bots.")
          return

      try:
          await member.kick(reason=reason)
          reason_msg = f" Reason: {reason}" if reason else ""
          await ctx.send(f"{member.mention} has been kicked from the server.{reason_msg}")
      except discord.Forbidden:
          await ctx.send("I do not have permission to kick this user.")
      except Exception as e:
          await ctx.send(f"An error occurred: {str(e)}")

  
  #give a role to everyone
  @commands.command(help="Give a certain role to everyone in the server")
  @commands.has_permissions(manage_roles=True)
  async def assignall(self, ctx, *, role: discord.Role):
      if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
          await ctx.send("You cannot assign a role higher or equal to your top role.")
          return

      member_count = 0
      for member in ctx.guild.members:
          if not member.bot:  # Optionally skip bots
              try:
                  if role not in member.roles:
                      await member.add_roles(role)
                      member_count += 1
              except discord.Forbidden:
                  await ctx.send(f"Cannot assign {role.name} to {member.display_name}. Insufficient permissions.")
                  continue
              except Exception as e:
                  await ctx.send(f"Failed to assign {role.name} to {member.display_name}: {e}")
                  continue

      await ctx.send(f"{role.name} role has been assigned to {member_count} members.")


    #remove a role from everyone
  @commands.command(help="Remove a certain role from everyone in the server")
  @commands.has_permissions(manage_roles=True)
  async def removeall(self, ctx, *, role: discord.Role):
      if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
          await ctx.send("You cannot remove a role higher or equal to your top role.")
          return

      member_count = 0
      for member in ctx.guild.members:
          if role in member.roles:
              try:
                  await member.remove_roles(role)
                  member_count += 1
              except discord.Forbidden:
                  await ctx.send(f"Cannot remove {role.name} from {member.display_name}. Insufficient permissions.")
                  continue
              except Exception as e:
                  await ctx.send(f"Failed to remove {role.name} from {member.display_name}: {e}")
                  continue

      await ctx.send(f"{role.name} role has been removed from {member_count} members.")



  @commands.command(help="Change the hierarchy of roles", aliases=['mvrl'])
  @commands.has_permissions(manage_roles=True)
  async def moverole(self, ctx, role: discord.Role, pos: int):
      if role.position >= ctx.author.top_role.position and ctx.author != ctx.guild.owner:
          await ctx.send("You cannot move a role higher or equal to your top role.")
          return

      try:
          await role.edit(position=pos)
          await ctx.send(f"Role {role.name} moved to position {pos}.")
      except discord.Forbidden:
          await ctx.send("I do not have permission to move this role.")
      except Exception as e:
          await ctx.send(f"An error occurred while moving the role: {e}")

  
  @commands.command(help="Count the number of messages in a channel")
  async def message_count(self, ctx, channel: discord.TextChannel = None):
      channel = channel or ctx.channel
      async with ctx.typing():
          count = 0
          async for _ in channel.history(limit=None):
              count += 1
          await ctx.send(f"There are {count} messages in {channel.mention}.")


  @commands.command(help = "display the status of the bot")
  async def status(self,ctx):
    lyrics = load['lyrics']
    if len(lyrics) > 2048:
      lyrics = lyrics[:2045] + '...'

      
    def make_lyrics_embed(lyrics):
        embedVar = discord.Embed(title = 'Clarence\'s Status is currently ' + str(load["title"] + " By " + load["author"]), description = lyrics ,color = ctx.author.color)
      
        embedVar.set_thumbnail(url = load["thumbnail"]["genius"])
      
        embedVar.set_footer(text=  'Requested by ' + str(ctx.author.name),icon_url = ctx.author.avatar)
        return embedVar

    view = View()
    button_uncensor = Button(label = "Uncensor", style = discord.ButtonStyle.red, custom_id = "uncensor_status")
      
    view.add_item(button_uncensor)
      

    msg = await ctx.send(embed = make_lyrics_embed(profanity.censor(lyrics, '#')),view=view)

    res = await self.client.wait_for('interaction', check=lambda interaction: interaction.data["component_type"] == 2 and "custom_id" in interaction.data.keys())

    for item in view.children:
      if item.custom_id == res.data["custom_id"]:
        button_uncensor.disabled = True
        await msg.edit(embed = make_lyrics_embed(lyrics), view=view)
        await res.response.defer()

class Owner(commands.Cog):
  """ 
  Commands for only the bot creator
  """

  def __init__(self,client):
      self.client = client


  #search through databases of the bot
  @commands.command(help = 'database commands,  used to view the Bot databases',hidden = True)
  @commands.is_owner()
  async def database(self,ctx,arg):
    if ctx.author.id == 239605426033786881:
      if arg.lower() == "trivia":
        embedVar = functionality.functions.get_stats(ctx)
        await ctx.send(embed = embedVar)
      
      if arg.lower() == "servers":
        activeservers = self.client.guilds
        guild_list = "`Active Servers: `\n\n"
        for guild in activeservers:
          guild_list = guild_list + str(guild) + '\n'
        embedVar = discord.Embed(title = "Clarence",description = guild_list,color = 0x6a0dad).set_footer(text = 'As of ' + str(date.today()), icon_url = os.getenv('icon'))
        await ctx.send(embed = embedVar)
            
    else:
      ctx.send("Sorry you don't have admin privileges")


  #manage profanity text file
  @commands.command(help = "Manage the words the bot's filter\n parameter = add/remove",hidden = True)
  @commands.is_owner()
  async def filter(self,ctx, parameter,*, change):
   if ctx.author.id ==  239605426033786881:
    with open("storage/words.txt", "r") as f:
        lines = f.readlines()
        f.close()
    
    chg = str(change).lower() + '\n'
    
    if parameter.lower() == "add":
      
      if chg in lines or chg.strip() in lines:
        await ctx.send(change + " is already in the text file")

      else:
        with open('storage/words.txt', 'a') as f:
          f.write('\n'+ change)
          f.close()
        await ctx.send(change + " was added to the text file")

    if parameter.lower() == "remove":
      
      if chg not in lines and chg.strip() not in lines:
        await ctx.send(change + " is not in the text file")

      else:
        with open("storage/words.txt", "w") as f:
          for line in lines:
            if line.strip("\n") != change:
              f.write(line)
          f.close()
        await ctx.send(change + ' was removed from the text file')
   else:
      await ctx.send("You do not have permission to change the text file")

  #command to add a server manually to the json file if the bot was offline when added to server
  @commands.command(help = "add a server prefix to json file if offline when joined",hidden = True)
  @commands.is_owner()
  async def addserver(self,ctx,id):
    if ctx.author.id ==  239605426033786881:
      with open("storage/prefixes.json", "r") as f:
          prefixes = json.load(f)

      prefixes[str(id)] = "$"

      with open("storage/prefixes.json", "w") as f:
          json.dump(prefixes, f, indent=4)
    else:
      ctx.send("you do not have permission to use this command")

  #command to manually remove server from prefix json file if bot was offline when added to server
  @commands.command(help = "add a server prefix to json file if offline when joined",hidden = True)
  @commands.is_owner()
  async def removeserver(self,ctx,id):
    if ctx.author.id ==  239605426033786881:
      with open("storage/prefixes.json", "r") as f:
          prefixes = json.load(f)

      prefixes.pop(str(id))

      with open("storage/prefixes.json", "w") as f:
          json.dump(prefixes, f, indent=4)
    else:
      ctx.send("you do not have permission to use this command")

  
  @commands.command(help = "use clarence to send a dm", hidden = True)
  @commands.is_owner()
  async def direct(self,ctx,member: discord.Member,*,message = None):
    if ctx.author.id ==  239605426033786881:
      if message == None:
        await ctx.send("please send a message")
      else:
        await ctx.author.send(f"`You sent:` \n{message} \n `to {member.name}`")
        await member.send(message)
    else:
      await ctx.send("You do not have permission to use this command")
        

async def setup(client):
    await client.add_cog(Moderation(client))
    await client.add_cog(Owner(client))