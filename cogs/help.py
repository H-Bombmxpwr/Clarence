# cogs/help.py
from datetime import date
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import Button, View

INVITE_URL = "https://discord.com/api/oauth2/authorize?client_id=877014219499925515&permissions=8&scope=bot%20applications.commands"
GITHUB_URL = "https://github.com/H-Bombmxpwr/Clarence"
OWNER_ID = 239605426033786881

# Display order + labels for the help menu (keyed by cog qualified_name)
CATEGORIES = {
    "Music": "🎵 Music",
    "Moderation": "🛡️ Moderation",
    "AutoMod": "🤖 AutoMod",
    "ServerLog": "⚙️ Server Config & Logging",
    "Flight": "✈️ Aviation",
    "Poker": "🎰 Poker",
    "Fun": "🎮 Games",
    "Trivia": "❓ Trivia",
    "Translation": "🌐 Translation",
    "Math": "🧮 Math",
    "Misc": "🔧 Utility",
    "Api": "🌐 Fun APIs",
    "Help": "ℹ️ Info",
    "Status": "🎶 Status",
}


def _cog_name(cmd: app_commands.Command | app_commands.Group) -> Optional[str]:
    if isinstance(cmd, app_commands.Group):
        for sub in cmd.walk_commands():
            if getattr(sub, "binding", None) is not None:
                return type(sub.binding).__cog_name__
        return None
    binding = getattr(cmd, "binding", None)
    return type(binding).__cog_name__ if binding else None


def collect_commands(bot: commands.Bot) -> dict[str, list[app_commands.Command]]:
    """Global slash commands (leaf commands, with group prefixes) grouped by cog."""
    grouped: dict[str, list] = {}
    for top in bot.tree.get_commands(type=discord.AppCommandType.chat_input):
        cog = _cog_name(top) or "Other"
        leaves = list(top.walk_commands()) if isinstance(top, app_commands.Group) else [top]
        for leaf in leaves:
            if isinstance(leaf, app_commands.Command):
                grouped.setdefault(cog, []).append(leaf)
    return grouped


class HelpSelect(discord.ui.Select):
    def __init__(self, bot: commands.Bot, grouped: dict[str, list]):
        self.bot = bot
        self.grouped = grouped
        options = [discord.SelectOption(label="Home", value="__home__", emoji="🏠")]
        for cog in CATEGORIES:
            if cog in grouped:
                label = CATEGORIES[cog]
                emoji, text = label.split(" ", 1)
                options.append(discord.SelectOption(label=text, value=cog, emoji=emoji,
                                                    description=f"{len(grouped[cog])} commands"))
        super().__init__(placeholder="Pick a category…", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        value = self.values[0]
        embed = home_embed(self.bot, self.grouped) if value == "__home__" else category_embed(self.bot, value, self.grouped[value])
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpView(View):
    def __init__(self, bot: commands.Bot, grouped: dict[str, list], author_id: int):
        super().__init__(timeout=300)
        self.author_id = author_id
        self.add_item(HelpSelect(bot, grouped))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Run `/help` to get your own menu.", ephemeral=True)
            return False
        return True


def home_embed(bot: commands.Bot, grouped: dict[str, list]) -> discord.Embed:
    embed = discord.Embed(title="Clarence Help", color=0x3498db,
                          description=f"All commands are slash commands — type `/` to browse them.\n"
                                      f"Use {bot.mention('help')} `command:<name>` for details on one command.\n"
                                      "Right-click a user or message → **Apps** for quick actions (User Info, Warn, Translate, Ratio).")
    for cog, label in CATEGORIES.items():
        if cog in grouped:
            names = " ".join(f"`/{c.qualified_name}`" for c in grouped[cog][:8])
            more = f" +{len(grouped[cog]) - 8} more" if len(grouped[cog]) > 8 else ""
            embed.add_field(name=label, value=(names + more)[:1024], inline=False)
    return embed


def category_embed(bot: commands.Bot, cog: str, cmds: list) -> discord.Embed:
    embed = discord.Embed(title=CATEGORIES.get(cog, cog), color=0x3498db)
    lines = [f"{bot.mention(c.qualified_name)} — {c.description}" for c in cmds]
    embed.description = "\n".join(lines)[:4000]
    return embed


class Help(commands.Cog):
    """ℹ️ Help and information"""

    def __init__(self, bot):
        self.bot = bot

    async def command_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        names = [c.qualified_name for cmds in collect_commands(self.bot).values() for c in cmds]
        return [app_commands.Choice(name=n, value=n) for n in names if current.lower() in n][:25]

    @app_commands.command(description="Show all commands, or details for one command")
    @app_commands.autocomplete(command=command_autocomplete)
    async def help(self, interaction: discord.Interaction, command: Optional[str] = None):
        grouped = collect_commands(self.bot)
        if command:
            found = next((c for cmds in grouped.values() for c in cmds if c.qualified_name == command.lower().lstrip("/")), None)
            if not found:
                return await interaction.response.send_message(f"❌ No command named `{command}`.", ephemeral=True)
            embed = discord.Embed(title=f"/{found.qualified_name}", description=found.description, color=0x3498db)
            for p in found.parameters:
                kind = p.type.name
                req = "required" if p.required else "optional"
                choices = f"\nChoices: {', '.join(c.name for c in p.choices)}" if p.choices else ""
                embed.add_field(name=f"{p.display_name} ({kind}, {req})", value=(p.description or "—") + choices, inline=False)
            perms = found.default_permissions or (found.parent.default_permissions if found.parent else None)
            if perms and perms.value:
                needed = ", ".join(name.replace("_", " ").title() for name, v in perms if v)
                embed.set_footer(text=f"Requires: {needed}")
            return await interaction.response.send_message(embed=embed, ephemeral=True)
        await interaction.response.send_message(embed=home_embed(self.bot, grouped), view=HelpView(self.bot, grouped, interaction.user.id),
                                                ephemeral=True)

    @app_commands.command(description="About Clarence")
    async def about(self, interaction: discord.Interaction):
        servers = len(self.bot.guilds)
        members = sum(g.member_count or 0 for g in self.bot.guilds)
        n_commands = sum(len(v) for v in collect_commands(self.bot).values())
        embed = discord.Embed(
            title="About Clarence",
            description="I am a multipurpose Discord bot that does a little bit of everything!\n\n"
                        f"Use {self.bot.mention('help')} to see all my commands.\n\n"
                        f"The bot is [open source]({GITHUB_URL}) on GitHub!",
            color=discord.Color.blurple())
        embed.add_field(name="Statistics", value=f"**Servers:** {servers}\n**Members:** {members:,}\n**Latency:** {round(self.bot.latency * 1000)}ms")
        embed.add_field(name="Info", value=f"**Developer:** <@{OWNER_ID}>\n**Library:** discord.py\n**Commands:** {n_commands}")
        embed.add_field(name="Contributors", value=(
            "• **Quiggles#2281** - Thursday equation\n"
            "• **1awesomet#5223** - QA & responses\n"
            "• **conradburns#6918** - Text file edits\n"
            "• **ThatchyMean1487#3395** - Bot icon"), inline=False)
        if self.bot.user.avatar:
            embed.set_thumbnail(url=self.bot.user.avatar.url)
        embed.set_footer(text=f"Online since restart • {date.today()}")
        view = View()
        view.add_item(Button(label="Invite", style=discord.ButtonStyle.link, url=INVITE_URL))
        view.add_item(Button(label="GitHub", style=discord.ButtonStyle.link, url=GITHUB_URL))
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(description="Get the bot invite link")
    async def invite(self, interaction: discord.Interaction):
        view = View()
        view.add_item(Button(label="Invite Me!", style=discord.ButtonStyle.link, url=INVITE_URL))
        await interaction.response.send_message(embed=discord.Embed(title="Invite Clarence!", color=discord.Color.green(),
                                                                    description="Thanks for wanting to add me to your server!"), view=view)

    @app_commands.command(description="View the source code")
    async def source(self, interaction: discord.Interaction):
        view = View()
        view.add_item(Button(label="GitHub", style=discord.ButtonStyle.link, url=GITHUB_URL))
        await interaction.response.send_message(embed=discord.Embed(title="Source Code", color=0x24292e,
                                                                    description="Clarence is open source! Check out the code on GitHub."), view=view)


async def setup(bot):
    await bot.add_cog(Help(bot))
