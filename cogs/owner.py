# cogs/owner.py
"""Owner-only commands. Registered only in the DEV_GUILD_ID server so nobody else sees them."""
import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime, timezone
from pathlib import Path

from functionality.ui import ConfirmView

OWNER_ID = 239605426033786881  # Your Discord ID


class ServerSelectView(discord.ui.View):
    """Interactive view for browsing servers"""
    
    def __init__(self, bot, servers: list, page: int = 0, per_page: int = 10):
        super().__init__(timeout=120)
        self.bot = bot
        self.servers = servers
        self.page = page
        self.per_page = per_page
        self.max_pages = (len(servers) + per_page - 1) // per_page
        self.selected_guild = None
        self.update_buttons()

    def update_buttons(self):
        """Update button states"""
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                if item.custom_id == "prev":
                    item.disabled = self.page == 0
                elif item.custom_id == "next":
                    item.disabled = self.page >= self.max_pages - 1

    def get_embed(self) -> discord.Embed:
        """Generate the current page embed"""
        embed = discord.Embed(
            title="Bot Dashboard",
            description=f"Managing **{len(self.servers)}** servers",
            color=0x9b59b6,
            timestamp=datetime.now(timezone.utc)
        )
        
        # Stats
        total_members = sum(g.member_count for g in self.servers)
        embed.add_field(name="Total Servers", value=str(len(self.servers)), inline=True)
        embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        
        # Server list for current page
        start = self.page * self.per_page
        end = start + self.per_page
        page_servers = self.servers[start:end]
        
        server_list = ""
        for i, guild in enumerate(page_servers, start=start + 1):
            server_list += f"`{i}.` **{guild.name}**\n"
            server_list += f"   └ {guild.member_count} members | ID: `{guild.id}`\n"
        
        if server_list:
            embed.add_field(
                name=f"Servers (Page {self.page + 1}/{self.max_pages})",
                value=server_list[:1024],
                inline=False
            )
        
        embed.set_footer(text="Use buttons to navigate • Select a server number to view details")
        return embed

    @discord.ui.button(label="◀️ Previous", style=discord.ButtonStyle.secondary, custom_id="prev")
    async def previous_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page > 0:
            self.page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Refresh", style=discord.ButtonStyle.primary, custom_id="refresh")
    async def refresh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.servers = sorted(self.bot.guilds, key=lambda g: g.member_count, reverse=True)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Next ▶️", style=discord.ButtonStyle.secondary, custom_id="next")
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.page < self.max_pages - 1:
            self.page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Stats", style=discord.ButtonStyle.success, custom_id="stats", row=1)
    async def show_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(
            title="Detailed Statistics",
            color=0x3498db,
            timestamp=datetime.now(timezone.utc)
        )
        
        total_members = sum(g.member_count for g in self.servers)
        total_channels = sum(len(g.channels) for g in self.servers)
        total_roles = sum(len(g.roles) for g in self.servers)
        
        # Top servers
        top_servers = sorted(self.servers, key=lambda g: g.member_count, reverse=True)[:5]
        top_list = "\n".join([f"`{i}.` **{g.name}** ({g.member_count:,})" for i, g in enumerate(top_servers, 1)])
        
        embed.add_field(name="Total Servers", value=str(len(self.servers)), inline=True)
        embed.add_field(name="Total Members", value=f"{total_members:,}", inline=True)
        embed.add_field(name="Total Channels", value=f"{total_channels:,}", inline=True)
        embed.add_field(name="Total Roles", value=f"{total_roles:,}", inline=True)
        embed.add_field(name="Latency", value=f"{round(self.bot.latency * 1000)}ms", inline=True)
        embed.add_field(name="Cogs Loaded", value=str(len(self.bot.cogs)), inline=True)
        embed.add_field(name="Top Servers", value=top_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="Server Details", style=discord.ButtonStyle.secondary, custom_id="details", row=1)
    async def server_details(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Create a select menu for server selection
        options = []
        start = self.page * self.per_page
        end = min(start + self.per_page, len(self.servers))
        
        for i, guild in enumerate(self.servers[start:end], start=1):
            options.append(
                discord.SelectOption(
                    label=guild.name[:100],
                    value=str(guild.id),
                    description=f"{guild.member_count} members"
                )
            )
        
        if not options:
            return await interaction.response.send_message("No servers on this page.", ephemeral=True)
        
        # Send a new message with select menu
        select_view = ServerSelectMenu(self.bot, options)
        await interaction.response.send_message(
            "Select a server to view details:",
            view=select_view,
            ephemeral=True
        )


class ServerSelectMenu(discord.ui.View):
    """Dropdown menu for selecting a server"""
    
    def __init__(self, bot, options: list):
        super().__init__(timeout=60)
        self.bot = bot
        select = discord.ui.Select(
            placeholder="Choose a server...",
            options=options
        )
        select.callback = self.select_callback
        self.add_item(select)
    
    async def select_callback(self, interaction: discord.Interaction):
        guild_id = int(interaction.data['values'][0])
        guild = self.bot.get_guild(guild_id)
        
        if not guild:
            return await interaction.response.send_message("Server not found.", ephemeral=True)
        
        embed = discord.Embed(
            title=f"{guild.name}",
            color=0x3498db
        )
        
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="Server ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=str(guild.owner) if guild.owner else "Unknown", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Roles", value=str(len(guild.roles)), inline=True)
        embed.add_field(name="Boost Level", value=str(guild.premium_tier), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Bot Joined", value=f"<t:{int(guild.me.joined_at.timestamp())}:R>" if guild.me else "Unknown", inline=True)
        
        # Top channels
        text_channels = [c for c in guild.channels if isinstance(c, discord.TextChannel)][:5]
        if text_channels:
            channel_list = "\n".join([f"#{c.name}" for c in text_channels])
            embed.add_field(name="Sample Channels", value=channel_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Owner(commands.Cog):
    """Owner-only commands for bot management"""

    def __init__(self, client: commands.Bot):
        self.client = client

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != OWNER_ID:
            await interaction.response.send_message("This command is owner-only.", ephemeral=True)
            return False
        return True

    async def extension_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        available = set(self.client.extensions) | {f"cogs.{p.stem}" for p in Path("cogs").glob("*.py")} | {"status"}
        return [app_commands.Choice(name=e, value=e) for e in sorted(available) if current.lower() in e][:25]

    @app_commands.command(description="Interactive bot dashboard")
    async def dashboard(self, interaction: discord.Interaction):
        servers = sorted(self.client.guilds, key=lambda g: g.member_count or 0, reverse=True)
        view = ServerSelectView(self.client, servers)
        await interaction.response.send_message(embed=view.get_embed(), view=view, ephemeral=True)

    @app_commands.command(description="Detailed info about any server the bot is in")
    async def guildinfo(self, interaction: discord.Interaction, guild_id: str):
        guild = self.client.get_guild(int(guild_id)) if guild_id.isdigit() else None
        if not guild:
            return await interaction.response.send_message("Server not found.", ephemeral=True)
        embed = discord.Embed(title=guild.name, color=0x3498db)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        embed.add_field(name="ID", value=str(guild.id))
        embed.add_field(name="Owner", value=str(guild.owner) if guild.owner else "?")
        embed.add_field(name="Members", value=str(guild.member_count))
        embed.add_field(name="Channels", value=str(len(guild.channels)))
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>")
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description="Make the bot leave a server")
    async def leaveserver(self, interaction: discord.Interaction, guild_id: str):
        guild = self.client.get_guild(int(guild_id)) if guild_id.isdigit() else None
        if not guild:
            return await interaction.response.send_message("Server not found.", ephemeral=True)
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(f"Leave **{guild.name}**?", view=view, ephemeral=True)
        await view.wait()
        if view.value:
            await guild.leave()
            await interaction.followup.send(f"Left **{guild.name}**", ephemeral=True)

    @app_commands.command(description="DM a message to every server owner")
    async def broadcast(self, interaction: discord.Interaction, message: str):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message(f"This will DM all **{len(self.client.guilds)}** server owners.",
                                                view=view, ephemeral=True)
        await view.wait()
        if not view.value:
            return
        embed = discord.Embed(title="Message from Bot Owner", description=message, color=0x3498db,
                              timestamp=datetime.now(timezone.utc))
        embed.set_footer(text=f"From {interaction.user}")
        success = failed = 0
        for guild in self.client.guilds:
            try:
                await guild.owner.send(embed=embed)
                success += 1
            except Exception:
                failed += 1
        await interaction.followup.send(f"Sent to **{success}** owners. Failed: **{failed}**", ephemeral=True)

    @app_commands.command(description="Reload an extension")
    @app_commands.autocomplete(extension=extension_autocomplete)
    async def reload(self, interaction: discord.Interaction, extension: str):
        try:
            await self.client.reload_extension(extension)
            await self.client.sync_commands()
            await interaction.response.send_message(f"Reloaded `{extension}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"{type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(description="Load an extension")
    @app_commands.autocomplete(extension=extension_autocomplete)
    async def load(self, interaction: discord.Interaction, extension: str):
        try:
            await self.client.load_extension(extension)
            await self.client.sync_commands()
            await interaction.response.send_message(f"Loaded `{extension}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"{type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(description="Unload an extension")
    @app_commands.autocomplete(extension=extension_autocomplete)
    async def unload(self, interaction: discord.Interaction, extension: str):
        if extension == "cogs.owner":
            return await interaction.response.send_message("Unloading the owner cog would lock you out.", ephemeral=True)
        try:
            await self.client.unload_extension(extension)
            await self.client.sync_commands()
            await interaction.response.send_message(f"Unloaded `{extension}`", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(f"{type(e).__name__}: {e}", ephemeral=True)

    @app_commands.command(description="List loaded extensions and cogs")
    async def cogs(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Loaded", color=0x2ecc71,
                              description="**Extensions**\n" + "\n".join(f"`{e}`" for e in self.client.extensions)
                                          + "\n\n**Cogs**\n" + ", ".join(self.client.cogs))
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description="Force re-sync slash commands with Discord")
    async def sync(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        await self.client.sync_commands(force=True)
        await interaction.followup.send(f"Synced {len(self.client.command_ids)} global commands.", ephemeral=True)

    @app_commands.command(description="Reshuffle the lyric status rotation")
    async def reloadlyrics(self, interaction: discord.Interaction):
        status = self.client.get_cog("Status")
        if not status:
            return await interaction.response.send_message("Status cog not loaded.", ephemeral=True)
        status.reshuffle()
        await interaction.response.send_message("Lyric status order reshuffled.", ephemeral=True)

    @app_commands.command(description="Shut down the bot")
    async def shutdown(self, interaction: discord.Interaction):
        view = ConfirmView(interaction.user.id)
        await interaction.response.send_message("Shut down the bot?", view=view, ephemeral=True)
        await view.wait()
        if view.value:
            await interaction.followup.send("Shutting down...", ephemeral=True)
            await self.client.close()


async def setup(client: commands.Bot):
    if not client.dev_guild:
        print("[owner] DEV_GUILD_ID not set - owner commands are disabled")
        return
    await client.add_cog(Owner(client), guild=client.dev_guild)
