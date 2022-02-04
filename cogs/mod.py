import discord
from discord.ext import commands,tasks
from discord import Member
from discord.utils import get
from datetime import date
import asyncio
import functionality.functions
import os


class Moderation(commands.Cog):
  """ 
  Moderation commands that require specific permissions to use
  """
  def __init__(self,client):
      self.client = client


  #ban a user
  @commands.command()
  @commands.has_permissions(ban_members = True)
  async def ban(self,ctx, member : discord.Member, *, reason = None):
    if member.id != 239605426033786881:
      await member.ban(reason = reason)
      embed=discord.Embed(title="User Banned!", description="**{0}** was banned by **{1}**!".format(member, ctx.message.author), color=0x800000).set_footer(icon_url = member.avatar, text = 'banned on ' + str(date.today()))
      await ctx.send(embed=embed)
    else:
      await ctx.send('I cannot ban my creator')

#The below code unbans player.
  @commands.command()
  @commands.has_permissions(administrator = True)
  async def unban(self,ctx, *, member):
    banned_users = await ctx.guild.bans()
    print(banned_users)
    member_name, member_discriminator = member.split("#")

    for ban_entry in banned_users:
        user = ban_entry.user

        if (user.name, user.discriminator) == (member_name, member_discriminator):
            await ctx.guild.unban(user)
            await ctx.send(f'Unbanned {user.mention}')
            return

  #generate a list of banned members
  @commands.command(help = "List of banned users from the guild")
  async def banlist(self,ctx):
    banned_users = await ctx.guild.bans()
    banned_list = ''
    for ban_entry in banned_users:
        user = ban_entry.user
        banned_list = banned_list + str(user) + '\n'

    await ctx.send(embed = discord.Embed(title = 'Banned Users: ', description = banned_list, color = 0x800000))


  #move roles around in positon
  @commands.command(help = "Change the hierarchy of roles",aliases = ['mvrl'])
  async def moverole(self,ctx, role: discord.Role, pos: int):
    all_roles = await ctx.guild.fetch_roles()
    num_roles = len(all_roles)
    print(f'The server has {num_roles} roles.')
    try:
        await role.edit(position=pos)
        await ctx.send("Role moved.")
    except discord.Forbidden:
        await ctx.send("You do not have permission to do that")
    except discord.HTTPException:
        await ctx.send("Failed to move role")
    except discord.InvalidArgument:
        await ctx.send("Invalid argument")



  #get the latency of the bot
  @commands.command(help = 'Find the latency of the bot')
  async def ping(self,ctx):
    await ctx.channel.send(f" `{round(self.client.latency * 1000)}` ms")


  #list the roles in the server
  @commands.command(help = "List the guild roles")
  async def roles(self,ctx):
    roles = "`Current Roles: `\n"
    for role in ctx.guild.roles:
      roles = roles + str(role) + "\n"

    roles = roles + "\n`Total roles: ` \n" + str(len(ctx.guild.roles))
    embedVar = discord.Embed(title = "Roles in Server", description = roles, inline = False, color = 0xffffff)
    await ctx.send(embed= embedVar)  


  #mute a user from all channels
  @commands.command(help = "Mute a user from sending messages")
  async def mute(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
      #checking if the muted role exists, and if doesn't makes the muted role
      if get(ctx.guild.roles, name="Muted"):
        print("role exits")
      else:
        
        perms = discord.Permissions(send_messages = False, read_message_history = True, connect = False,read_messages = True)

        muted = await ctx.guild.create_role(name="Muted", colour=discord.Colour(0x800000), permissions=perms)
        
        for channel in ctx.guild.channels:
          await channel.set_permissions(muted, send_messages=False, read_messages=True, read_message_history=True,connect = False)
        
        await ctx.send('Mute Role created!')
      #gives the muted role to the selected member
      
      try:
          add_role= discord.utils.get(ctx.guild.roles, name='Muted')
          if member.id != 239605426033786881:
            await member.add_roles(add_role)
            embed=discord.Embed(title="User Muted!", description="**{0}** was muted by **{1}**!".format(member, ctx.message.author), color=0x800000).set_footer(icon_url = member.avatar, text = 'muted on ' + str(date.today()))
            await ctx.send(embed=embed)
          else:
            await ctx.send("I can't mute my creator")      
          
      except:
            await ctx.send("Not able to update role")
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)


  #unmute a user
  @commands.command(help = 'Unmutes a user')
  async def unmute(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
     try:
      role = get(ctx.guild.roles, name='Muted')
      await member.remove_roles(role)
      embed=discord.Embed(title="User Unmuted!", description="**{0}** was unmuted by **{1}**!".format(member, ctx.message.author), color=0x800000)
      await ctx.send(embed=embed)
     except:
      embed=discord.Embed(title="Mute/Unmute Error", description="User is not muted", color=0x800000)
      await ctx.send(embed=embed)
    
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)



  #gives the administrator role
  @commands.command(help = 'gives a user the administrator role',aliases = ['gvad'])
  async def giveadmin(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
      #checking if the muted role exists, and if doesn't makes the muted role
      if get(ctx.guild.roles, name="Admin"):
        print("role exits")
      else:
        perms = discord.Permissions(administrator = True)
        await ctx.guild.create_role(name="Admin", colour=discord.Colour(0x280137), permissions=perms, hoist = True)
        await ctx.send('Admin Role created!')
      #gives the muted role to the selected member
      try:
          add_role= discord.utils.get(ctx.guild.roles, name='Admin')
          await member.add_roles(add_role)      
          embed=discord.Embed(title="New Admin!", description="**{0}** was given admin by **{1}**!".format(member, ctx.message.author), color=0x6a0dad).set_footer(icon_url = member.avatar, text = 'given on ' + str(date.today()))
          await ctx.send(embed=embed)
      except:
            await ctx.send("Not able to give role")
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)


  #removes the administrator role
  @commands.command(help = 'removes the admin role',aliases = ['rmad'])
  async def removeadmin(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
     try:
      role = get(ctx.guild.roles, name='Admin')
      await member.remove_roles(role)
      embed=discord.Embed(title="Admin Removed!", description="**{0}** was stripped of admin by **{1}**!".format(member, ctx.message.author), color=0x6a0dad)
      await ctx.send(embed=embed)
     except:
      embed=discord.Embed(title="Admin Removal Error", description="The admin role was not able to be removed", color=0x6a0dad)
      await ctx.send(embed=embed)
    
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)


  #prune x number of members
  @commands.command(help = 'delete x number of messages, regardless of sender',aliases = ['cl'])
  async def clean(self,ctx,limit :int):
    if ctx.message.author.guild_permissions.administrator or ctx.author.id == 239605426033786881:
      if limit > 250:
        await ctx.send('``` You cannot delete more than 250 messages at a time```')
      else:
        await ctx.channel.purge(limit=limit)
        await ctx.send('```' + str(limit) + ' messages cleared by {}'.format(ctx.author.name) + '```')
        await ctx.message.delete()
    else:
       await ctx.send("Either you or the bot does not have the necessary permissions to perform this task")




class Owner(commands.Cog):
  """ 
  Commands for only the bot creator
  """

  def __init__(self,client):
      self.client = client


  #search through databases of the bot
  @commands.command(help = 'database commands,  used to view the Bot databases',hidden = True)
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
        embedVar = discord.Embed(title = "Smrt Bot",description = guild_list,color = 0x6a0dad).set_footer(text = 'As of ' + str(date.today()), icon_url = os.getenv('icon'))
        await ctx.send(embed = embedVar)
            
    else:
      ctx.send("Sorry you don't have admin privileges")


  #manage profanity text file
  @commands.command(help = "Manage the words the bot's filter\n parameter = add/remove",hidden = True)
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



  



  #set the status of the bot
  @commands.command(help = 'Set the status of the bot',hidden = True)
  async def status(self,ctx, status,*, text):
    if ctx.author.id == 239605426033786881:
      if status.lower() == 'playing':
      # Setting `Playing ` status
        await self.client.change_presence(activity=discord.Game(name=text))
        await ctx.send("Status changed to: \'`Playing " + text + "\'`")
      
      elif status.lower() == 'listening':
        # Setting `Listening ` status
        await self.client.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name=text))
        await ctx.send("Status changed to: \'`Listening to " + text + "\'`")

      elif status.lower() == 'watching':
        # Setting `Watching ` status
        await self.client.change_presence(activity=discord.Activity(type=discord.ActivityType.watching, name=text))
        await ctx.send("Status changed to: \'`Watching " + text + "\'`")
      
      else:
        await ctx.send("Invalid actvity sent")

    else:
      await ctx.send('You do not have permission to change the bots status')



def setup(client):
    client.add_cog(Moderation(client))
    client.add_cog(Owner(client))