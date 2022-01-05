import discord
from discord.ext import commands,tasks
from discord import Member
from discord.utils import get
from datetime import date
import asyncio
import functions
import os

class moderation(commands.Cog, description = 'Moderation commands that require specific permissions to use'):
  def __init__(self,client):
      self.client = client

    
  @commands.command(help = "Mute a user from sending messages")
  async def mute(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
      #checking if the muted role exists, and if doesn't makes the muted role
      if get(ctx.guild.roles, name="Muted"):
        print("role exits")
      else:
        perms = discord.Permissions(send_messages = False, read_messages_history = True, connect = False,read_messages = False)
        await ctx.guild.create_role(name="Muted", colour=discord.Colour(0x800000), permissions=perms)
        await ctx.send('Mute Role created!')
      #gives the muted role to the selected member
      try:
          add_role= discord.utils.get(ctx.guild.roles, name='Muted')
          await member.add_roles(add_role)      
          embed=discord.Embed(title="User Muted!", description="**{0}** was muted by **{1}**!".format(member, ctx.message.author), color=0x800000).set_footer(icon_url = member.avatar_url, text = 'muted on ' + str(date.today()))
          await ctx.send(embed=embed)
      except:
            await ctx.send("Not able to update role")
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)


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



  @commands.command(help = 'gives a user the administrator role')
  async def giveadmin(self,ctx, member: discord.Member):
    if ctx.message.author.guild_permissions.administrator or ctx.message.author.id == 239605426033786881:
      #checking if the muted role exists, and if doesn't makes the muted role
      if get(ctx.guild.roles, name="Admin"):
        print("role exits")
      else:
        perms = discord.Permissions(administrator = True)
        await ctx.guild.create_role(name="Admin", colour=discord.Colour(0x6a0dad), permissions=perms, hoist = True)
        await ctx.send('Admin Role created!')
      #gives the muted role to the selected member
      try:
          add_role= discord.utils.get(ctx.guild.roles, name='Admin')
          await member.add_roles(add_role)      
          embed=discord.Embed(title="New Admin!", description="**{0}** was given admin by **{1}**!".format(member, ctx.message.author), color=0x6a0dad).set_footer(icon_url = member.avatar_url, text = 'given on ' + str(date.today()))
          await ctx.send(embed=embed)
      except:
            await ctx.send("Not able to give role")
    else:
        embed=discord.Embed(title="Permission Denied.", description="You don't have permission to use this command.", color=0xff00f6)
        await ctx.send(embed=embed)


  @commands.command(help = 'removes the admin role')
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


  @commands.command(help = 'delete x number of messages, regardless of sender',aliases = ['cl'])
  async def clean(self,ctx,limit :int):
    if ctx.message.author.guild_permissions.administrator:
        await ctx.channel.purge(limit=limit)
        await ctx.send('```' + str(limit) + ' messages cleared by {}'.format(ctx.author.name) + '```')
        await ctx.message.delete()
    if ctx.message.author.guild_permissions.administrator == 0:
       await ctx.send("Either you are the bot does not have the necessary permissions to perform this task")



  #search through databases of the bot
  @commands.command(help = 'database commands,  used to view the Bot databases')
  async def database(self,ctx,arg):
    if ctx.author.id == 239605426033786881:
      if arg.lower() == "trivia":
        embedVar = functions.get_stats(ctx)
        await ctx.send(embed = embedVar)
      
      if arg.lower() == "servers":
        activeservers = self.client.guilds
        embedVar = discord.Embed(title = "Current servers",description = "List of servers the bot is in",color = 0x6a0dad).set_footer(text = 'As of ' + str(date.today()), icon_url = os.getenv('icon'))
        for guild in activeservers:
          embedVar.add_field(name = guild.name, value = 'Members: ' + str(guild.member_count),inline = False)
        await ctx.send(embed = embedVar)
            
    else:
      ctx.send("Sorry you don't have admin privileges")


  #manage profanity text file
  @commands.command(help = "Manage the words the bot filters\n parameter = add/remove")
  async def filter(self,ctx, parameter,*, change):
   if ctx.author.id ==  239605426033786881:
    with open("words.txt", "r") as f:
        lines = f.readlines()
    
    if parameter.lower() == "add":
      
      if change.lower() in lines:
        await ctx.send(change + " is already in the text file")

      else:
        with open('words.txt', 'a') as f:
          f.write('\n'+ change)
          f.close()
        await ctx.send(change + " was added to the text file")

    if parameter.lower() == "remove":
      
      if change.lower() not in lines:
        await ctx.send(change + " is not in the text file")

      else:
        with open("words.txt", "w") as f:
          for line in lines:
            if line.strip("\n") != change:
              f.write(line)
        await ctx.send(change + ' was removed from the text file')
   else:
     ctx.send("You do not have permission to change the text file")



      

    



def setup(client):
    client.add_cog(moderation(client))