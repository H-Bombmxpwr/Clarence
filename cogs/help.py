import discord
from discord.ext import commands
from discord.errors import Forbidden



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
            emb = discord.Embed(title='Commands and modules', color=0x808080,
                                description=f'Use `{prefix}help <module>` to gain more information about that module ')

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
                                        color=discord.Color.green())

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
                                    color=discord.Color.blue())

        # too many cogs requested - only one at a time allowed
        elif len(input) > 1:
            emb = discord.Embed(title="Module Error!",
                                description="Please request only one module at once",
                                color=discord.Color.green())

        else:
            emb = discord.Embed(title="Error",
                                description="An error occurrd with your request, try reformatting and sending it again",
                                color=discord.Color.red())

        # sending reply embed using our own function defined above
        await send_embed(ctx, emb)

    @commands.command(help = 'List all commands of the bot')
    async def list(self,ctx):

      commands_desc = ''
      for command in self.bot.walk_commands():
          commands_desc += f'`{command.name}: `  {command.help}\n'


      embedVar = discord.Embed(title = "Complete list of commands", description = commands_desc, color = 0x280137)
      await ctx.send(embed=embedVar)


def setup(bot):
    bot.remove_command('help')
    bot.add_cog(Help(bot))