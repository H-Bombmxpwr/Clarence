# cogs/help.py
import discord
from discord.ext import commands
from datetime import date, datetime, timezone
from discord.ui import Button, View
from typing import Optional


class HelpView(discord.ui.View):
    """Paginated help view"""
    
    def __init__(self, bot, ctx, timeout=120):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.ctx = ctx
        self.page = 0
        self.pages = self._generate_pages()
    
    def _generate_pages(self) -> list:
        """Generate help pages"""
        pages = []
        
        # Main page
        main_embed = discord.Embed(
            title="Clarence Help",
            description=(
                "Use the buttons below to navigate through commands!\n\n"
                "**Tip:** Use `help <command>` for detailed info about a command."
            ),
            color=0x3498db
        )
        main_embed.add_field(
            name="Categories",
            value=(
                "**Games** - Fun games and entertainment\n"
                "**Moderation** - Server management\n"
                "**Music** - Music playback & lyrics\n"
                "**Translation** - Language translation\n"
                "**Flight** - Flight tracking\n"
                "**Poker** - Texas Hold'em\n"
                "**Math** - Math utilities\n"
                "**Services** - APIs & utilities\n"
                "**Trivia** - Trivia games"
            ),
            inline=False
        )
        pages.append(main_embed)
        
        # Generate category pages
        categories = {
            "Games": ["Fun"],
            "Moderation": ["Moderation"],
            "Music": ["Music"],
            "Translation": ["Translation"],
            "Flight": ["Flight"],
            "Poker": ["Poker"],
            "Math": ["Math"],
            "Services": ["Misc", "Api"],
            "Trivia": ["Trivia"]
        }
        
        for cat_name, cog_names in categories.items():
            embed = discord.Embed(title=f"{cat_name} Commands", color=0x3498db)
            
            for cog_name in cog_names:
                cog = self.bot.get_cog(cog_name)
                if cog:
                    cmds = cog.get_commands()
                    if cmds:
                        cmd_list = []
                        for cmd in cmds[:15]:  # Limit to 15 commands per cog
                            if not cmd.hidden:
                                help_text = cmd.help.split('\n')[0] if cmd.help else "No description"
                                cmd_list.append(f"`{cmd.name}` - {help_text[:50]}")
                        
                        if cmd_list:
                            embed.add_field(
                                name=f"{cog_name}",
                                value="\n".join(cmd_list),
                                inline=False
                            )
            
            if embed.fields:
                pages.append(embed)
        
        return pages
    
    def get_current_embed(self) -> discord.Embed:
        embed = self.pages[self.page]
        embed.set_footer(text=f"Page {self.page + 1}/{len(self.pages)}")
        return embed
    
    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your help menu!", ephemeral=True)
        
        self.page = (self.page - 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.get_current_embed())
    
    @discord.ui.button(label="Home", style=discord.ButtonStyle.primary)
    async def home_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your help menu!", ephemeral=True)
        
        self.page = 0
        await interaction.response.edit_message(embed=self.get_current_embed())
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.ctx.author:
            return await interaction.response.send_message("Not your help menu!", ephemeral=True)
        
        self.page = (self.page + 1) % len(self.pages)
        await interaction.response.edit_message(embed=self.get_current_embed())


class Help(commands.Cog):
    """Help and Information commands"""
    
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="about", help="About Clarence")
    async def about(self, ctx):
        """Display information about the bot"""
        servers = len(self.bot.guilds)
        members = sum(g.member_count for g in self.bot.guilds)
        latency = round(self.bot.latency * 1000)
        
        # Get bot owner
        try:
            owner = ctx.guild.get_member(239605426033786881)
            owner_text = owner.mention if owner else "@hbombmxpwr"
        except:
            owner_text = "@hbombmxpwr"
        
        embed = discord.Embed(
            title="About Clarence",
            description=(
                "I am a multipurpose Discord bot that does a little bit of everything!\n\n"
                f"Use `{ctx.prefix}help` to see all my commands.\n\n"
                "The bot is [open source](https://github.com/H-Bombmxpwr/Clarence) on GitHub!"
            ),
            color=discord.Color.blurple()
        )
        
        embed.add_field(
            name="Statistics",
            value=(
                f"**Servers:** {servers}\n"
                f"**Members:** {members:,}\n"
                f"**Latency:** {latency}ms"
            ),
            inline=True
        )
        
        embed.add_field(
            name="Info",
            value=(
                f"**Developer:** {owner_text}\n"
                f"**Library:** discord.py\n"
                f"**Commands:** {len([c for c in self.bot.commands if not c.hidden])}"
            ),
            inline=True
        )
        
        embed.add_field(
            name="Contributors",
            value=(
                "• **Quiggles#2281** - Thursday equation\n"
                "• **1awesomet#5223** - QA & responses\n"
                "• **conradburns#6918** - Text file edits\n"
                "• **ThatchyMean1487#3395** - Bot icon"
            ),
            inline=False
        )
        
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        
        embed.set_footer(text=f"Online since restart • {date.today()}")
        
        # Add buttons
        view = View()
        view.add_item(Button(
            label="Invite",
            style=discord.ButtonStyle.green,
            url="https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot"
        ))
        view.add_item(Button(
            label="GitHub",
            style=discord.ButtonStyle.secondary,
            url="https://github.com/H-Bombmxpwr/Clarence"
        ))
        view.add_item(Button(
            label="Support",
            style=discord.ButtonStyle.primary,
            url="https://discord.gg/your-support-server"  # Replace with actual support server
        ))
        
        await ctx.send(embed=embed, view=view)

    @commands.command(name="invite", aliases=["in"], help="Get the bot invite link")
    async def invite(self, ctx):
        """Get the invite link for the bot"""
        embed = discord.Embed(
            title="Invite Clarence!",
            description="Thanks for wanting to add me to your server!",
            color=discord.Color.green()
        )
        
        view = View()
        view.add_item(Button(
            label="Invite Me!",
            style=discord.ButtonStyle.primary,
            url="https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot"
        ))
        
        await ctx.send(embed=embed, view=view)

    @commands.command(name="source", aliases=["src", "github"], help="View the source code")
    async def source(self, ctx):
        """Get the GitHub repository link"""
        embed = discord.Embed(
            title="Source Code",
            description="Clarence is open source! Check out the code on GitHub.",
            color=0x24292e
        )
        
        view = View()
        view.add_item(Button(
            label="GitHub",
            style=discord.ButtonStyle.secondary,
            url="https://github.com/H-Bombmxpwr/Clarence"
        ))
        
        await ctx.send(embed=embed, view=view)

    @commands.command(name="commands", aliases=["cmds", "list"])
    async def commands_list(self, ctx):
        """Show a list of all commands with interactive pagination"""
        view = HelpView(self.bot, ctx)
        await ctx.send(embed=view.get_current_embed(), view=view)


class NewHelpName(commands.MinimalHelpCommand):
    """Custom help command with better formatting"""
    
    def get_command_signature(self, command):
        return f'{self.context.clean_prefix}{command.qualified_name} {command.signature}'
    
    async def send_bot_help(self, mapping):
        """Send the main help page"""
        ctx = self.context
        
        embed = discord.Embed(
            title="Clarence Help",
            description=(
                f"Use `{ctx.prefix}help <command>` for more info on a command.\n"
                f"Use `{ctx.prefix}help <category>` for more info on a category.\n\n"
                f"**Tip:** Use `{ctx.prefix}commands` for an interactive help menu!"
            ),
            color=0x3498db
        )
        
        for cog, commands in mapping.items():
            filtered = await self.filter_commands(commands, sort=True)
            if filtered:
                cog_name = cog.qualified_name if cog else "Other"
                command_names = [f"`{c.name}`" for c in filtered[:10]]
                if command_names:
                    embed.add_field(
                        name=f"{cog_name}",
                        value=" ".join(command_names),
                        inline=False
                    )
        
        embed.set_footer(text=f"Type {ctx.prefix}help <command> for more info")
        
        destination = self.get_destination()
        await destination.send(embed=embed)
    
    async def send_cog_help(self, cog):
        """Send help for a specific cog/category"""
        embed = discord.Embed(
            title=f"{cog.qualified_name}",
            description=cog.description or "No description",
            color=0x3498db
        )
        
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        for command in filtered:
            help_text = command.help.split('\n')[0] if command.help else "No description"
            embed.add_field(
                name=f"`{self.context.prefix}{command.name}`",
                value=help_text,
                inline=False
            )
        
        destination = self.get_destination()
        await destination.send(embed=embed)
    
    async def send_command_help(self, command):
        """Send help for a specific command"""
        embed = discord.Embed(
            title=f"{command.qualified_name}",
            description=command.help or "No description available",
            color=0x3498db
        )
        
        embed.add_field(
            name="Usage",
            value=f"`{self.get_command_signature(command)}`",
            inline=False
        )
        
        if command.aliases:
            embed.add_field(
                name="Aliases",
                value=", ".join([f"`{alias}`" for alias in command.aliases]),
                inline=False
            )
        
        destination = self.get_destination()
        await destination.send(embed=embed)
    
    async def send_group_help(self, group):
        """Send help for a command group"""
        embed = discord.Embed(
            title=f"{group.qualified_name}",
            description=group.help or "No description",
            color=0x3498db
        )
        
        filtered = await self.filter_commands(group.commands, sort=True)
        for command in filtered:
            embed.add_field(
                name=f"`{self.context.prefix}{command.qualified_name}`",
                value=command.help.split('\n')[0] if command.help else "No description",
                inline=False
            )
        
        destination = self.get_destination()
        await destination.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Help(bot))
    bot.help_command = NewHelpName()