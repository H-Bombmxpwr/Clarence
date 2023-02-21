import discord
from discord.ext import commands
import os
from datetime import date
from discord.ui import Button,View


class Help(commands.Cog):
    """
    Sends this help message
    """
    def __init__(self, bot):
        self.bot = bot
  
    @commands.command(help = "About Clarence")
    async def about(self,ctx):
      
      servers  =str(len(self.bot.guilds))
      members = str(len(self.bot.users))
      latency = str(round(self.bot.latency * 1000))
      color = discord.Color.blurple()

      button = Button(label = "Invite", style = discord.ButtonStyle.primary, url = "https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot")
      view = View()
      view.add_item(button)

      try:
                owner = ctx.guild.get_member(239605426033786881).mention

      except AttributeError as e:
                owner = "H-Bombmxpwr#2243"

      embedVar1 = discord.Embed(title = "About Me", description = "I am a bot that does a little bit of everything.\nUse `help` and `list` to look through a list of commands!\n\n The bot is [open sourced](https://github.com/H-Bombmxpwr/Clarence) on GitHub",color = color)
  
      embedVar1.add_field(name = "Basic Information", value = f"`      Developer:`{owner}\n`        Servers:` {servers}\n`        Members:` {members}\n`        Latency:` {latency} ms ",inline = False)

      embedVar1.add_field(name = "Other Contributers", value = "`        Quiggles#2281:` Thursday equation and only fan\n`       1awesomet#5223:` Quality assurance and responses\n`     conradburns#6918:` Edited and refined the text file\n` ThatchyMean1487#3395:` Drew the bot icon\n`Viciouspenguin01#9167:` Being an inspirational bully ",inline = False)
      embedVar1.set_footer(icon_url = os.getenv('icon'), text = 'Working as of ' + str(date.today()))
      await ctx.send(embed=embedVar1,view=view)

    @commands.command(help = "Invite the bot",aliases = ["in"])
    async def invite(self,ctx):
      button = Button(label = "Invite", style = discord.ButtonStyle.primary, url = "https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot")
      view = View()
      view.add_item(button)
      await ctx.send("Woah you want to invite me! Thats awesome, just click the button below", view=view)


    @commands.command(help = 'List all commands of the bot in one page',aliases = ['fl'])
    async def fulllist(self,ctx):

      commands_desc = ''
      for command in self.bot.walk_commands():
        if not command.hidden:
          commands_desc += f'`{command.name}: `  {command.help}\n'


      embedVar = discord.Embed(title = "Complete list of commands", description = commands_desc, color = 0x280137).set_footer(icon_url = os.getenv('icon'), text = "Clarence#8444")
      await ctx.send(embed=embedVar)


class NewHelpName(commands.MinimalHelpCommand): #creating a new help command
    async def send_pages(self):
        destination = self.get_destination()
        for page in self.paginator.pages:
            emby = discord.Embed(description=page,color = 0x000080)
            await destination.send(embed=emby)


async def setup(bot):
    #bot.remove_command('help')
    await bot.add_cog(Help(bot))