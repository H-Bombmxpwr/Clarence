import discord
from discord.ext import commands
from discord.errors import Forbidden
import os
from datetime import date
from discord.ui import Button,View



async def send_embed(ctx, embed):
    
    try:
        await ctx.send(embed=embed)
    except Forbidden:
        try:
            await ctx.send("Hey, seems like I can't send embeds. Please check my permissions :)")
        except Forbidden:
            await ctx.author.send(
                f"Hey, seems like I can't send any message in {ctx.channel.name} on {ctx.guild.name}\n"
                f"May you inform the server team about this issue?", embed=embed)


class Help(commands.Cog):
    """
    Sends this help message
    """

    def __init__(self, bot):
        self.bot = bot

    @commands.command(help = "Provides help for the modules within the bot")
    async def help(self, ctx, *input):
        prefix = self.bot.command_prefix
        version =  "12.19.234"
        owner = 239605426033786881
        owner_name = 	"H-Bombmxpwr#2243"

        # checks if cog parameter was given
        # if not: sending all modules and commands not associated with a cog
        if not input:
            # checks if owner is on this server - used to 'tag' owner
            try:
                owner = ctx.guild.get_member(owner).mention

            except AttributeError as e:
                owner = owner_name

            # starting to build embed
            emb = discord.Embed(title='Commands and modules', color=0x280137,
                                description=f'Use `{prefix}help <module>` to gain more information about that module\nUse `{prefix}list: ` for a complete list of commands ')

            # iterating trough cogs, gathering descriptions
            cogs_desc = ''
            for cog in self.bot.cogs:
                cogs_desc += f'`{cog}: ` {self.bot.cogs[cog].__doc__}\n'

            # adding 'list' of cogs to embed
            emb.add_field(name='Modules', value=cogs_desc, inline=False)

            # integrating through uncategorized commands
            commands_desc = ''
            for command in self.bot.walk_commands():
                # if cog not in a cog
                # listing command if cog name is None and command isn't hidden
                if not command.cog_name and not command.hidden:
                    commands_desc += f'{command.name} - {command.help}\n'

            # adding those commands to embed
            if commands_desc:
                emb.add_field(name='Not belonging to a module', value=commands_desc, inline=False)

            # setting information about author
            emb.add_field(name="About", value=f"\
                                    Made and maintained by {owner}\n ")
            emb.set_footer(text=f"Bot is running {version}")

        # block called when one cog-name is given
        # trying to find matching cog and it's commands
        elif len(input) == 1:

            # iterating trough cogs
            for cog in self.bot.cogs:
                # check if cog is the matching one
                if cog.lower() == input[0].lower():

                    # making title - getting description from doc-string below class
                    emb = discord.Embed(title=f'{cog} - Commands', description=self.bot.cogs[cog].__doc__,
                                        color=0x280137)

                    # getting commands from cog
                    for command in self.bot.get_cog(cog).get_commands():
                        # if cog is not hidden
                        if not command.hidden:
                            emb.add_field(name=f"`{prefix}{command.name}: `", value=command.help, inline=False)
                    # found cog - breaking loop
                    break

            # if input not found
            # yes, for-loops have an else statement, it's called when no 'break' was issued
            else:
                emb = discord.Embed(title="Module error!",
                                    description=f"There is no module by that name, modules are groups of commands",
                                    color=discord.Color.red())

        # too many cogs requested - only one at a time allowed
        elif len(input) > 1:
            emb = discord.Embed(title="Module Error!",
                                description="Please request only one module at once",
                                color=discord.Color.red())

        else:
            emb = discord.Embed(title="Error",
                                description="An error occurrd with your request, try reformatting and sending it again",
                                color=discord.Color.red())

        # sending reply embed using our own function defined above
        await send_embed(ctx, emb)

    @commands.command(help = 'List all commands of the bot in one page',aliases = ['l'])
    async def fulllist(self,ctx):

      commands_desc = ''
      for command in self.bot.walk_commands():
        if not command.hidden:
          commands_desc += f'`{command.name}: `  {command.help}\n'


      embedVar = discord.Embed(title = "Complete list of commands", description = commands_desc, color = 0x280137).set_footer(icon_url = os.getenv('icon'), text = "Smrt Bot#8444")
      await ctx.send(embed=embedVar)

    @commands.command(help = "About Smrt Bot")
    async def about(self,ctx):
      servers  =str(len(self.bot.guilds))
      members = str(len(self.bot.users))
      color = 0x808080

      button = Button(label = "Invite", style = discord.ButtonStyle.primary, url = "https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot")
      view = View()
      view.add_item(button)

      try:
                owner = ctx.guild.get_member(239605426033786881).mention

      except AttributeError as e:
                owner = "H-Bombmxpwr#2243"

      embedVar1 = discord.Embed(title = "About Me", description = "I am a bot that does a little bit of everything. Use `" + self.bot.command_prefix + "help` and `" + self.bot.command_prefix + "list` to look through a list of commands!",color = color)
  
      embedVar1.add_field(name = "Basic information", value = f"`      Developer:`{owner}\n`        Servers:` {servers}\n`  Total Members:` {members}",inline = False)

      embedVar1.add_field(name = "Other Contributers", value = "`    conradburns#6918:` Edited and refined the text file\n`ThatchyMean1487#3395:` Drew the bot icon\n`      1awesomet#5223:` Quality assurance and responses\n`       Quiggles#2281:` Thursday modular equation",inline = False)
      embedVar1.set_footer(icon_url = os.getenv('icon'), text = 'Working as of ' + str(date.today()))
      embedVar1.set_image(url = 'https://static.wikia.nocookie.net/simpsons/images/2/2c/Homer_Goes_to_College_41.JPG/revision/latest?cb=20130715173527')
      await ctx.send(embed=embedVar1,view=view)

    @commands.command(help = "Invite the bot")
    async def invite(self,ctx):
      button = Button(label = "Invite", style = discord.ButtonStyle.primary, url = "https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot")
      view = View()
      view.add_item(button)
      await ctx.send("Woah you want to invite me! Thats awesome, just click the button below", view=view)
      


def setup(bot):
    bot.remove_command('help')
    bot.add_cog(Help(bot))