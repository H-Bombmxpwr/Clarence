# cogs/owner.py
import discord
from discord.ext import commands
from datetime import date, datetime, timezone
from typing import Optional
import json
import os

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
            title="🤖 Bot Dashboard",
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
            title=f"📋 {guild.name}",
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
            embed.add_field(name="📝 Sample Channels", value=channel_list, inline=False)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Owner(commands.Cog):
    """Owner-only commands for bot management"""

    def __init__(self, client: commands.Bot):
        self.client = client

    def is_owner(self, user_id: int) -> bool:
        """Check if user is the bot owner"""
        return user_id == OWNER_ID

    @commands.command(name="dashboard", aliases=["dash", "admin"], hidden=True)
    async def dashboard(self, ctx: commands.Context):
        """
        Interactive bot dashboard (Owner only)
        
        Shows all servers, statistics, and management options.
        """
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        servers = sorted(self.client.guilds, key=lambda g: g.member_count, reverse=True)
        view = ServerSelectView(self.client, servers)
        await ctx.send(embed=view.get_embed(), view=view)

    @commands.command(name="servers", aliases=["guilds"], hidden=True)
    async def servers(self, ctx: commands.Context):
        """List all servers the bot is in (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        servers = sorted(self.client.guilds, key=lambda g: g.member_count, reverse=True)
        
        embed = discord.Embed(
            title=f"🤖 Active Servers ({len(servers)})",
            color=0x9b59b6,
            timestamp=datetime.now(timezone.utc)
        )
        
        server_list = ""
        for i, guild in enumerate(servers[:20], 1):
            server_list += f"`{i}.` **{guild.name}** ({guild.member_count})\n"
        
        embed.description = server_list
        embed.set_footer(text=f"Total: {sum(g.member_count for g in servers):,} members")
        
        await ctx.send(embed=embed)

    @commands.command(name="serverinfo_owner", aliases=["guildinfo"], hidden=True)
    async def server_info_owner(self, ctx: commands.Context, guild_id: int = None):
        """Get detailed info about a specific server (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        if guild_id is None:
            return await ctx.send("Usage: `serverinfo_owner <guild_id>`")
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            return await ctx.send("❌ Server not found.")
        
        embed = discord.Embed(title=guild.name, color=0x3498db)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        
        embed.add_field(name="ID", value=str(guild.id), inline=True)
        embed.add_field(name="Owner", value=str(guild.owner) if guild.owner else "?", inline=True)
        embed.add_field(name="Members", value=str(guild.member_count), inline=True)
        embed.add_field(name="Channels", value=str(len(guild.channels)), inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        
        await ctx.send(embed=embed)

    @commands.command(name="leave_server", hidden=True)
    async def leave_server(self, ctx: commands.Context, guild_id: int):
        """Make the bot leave a server (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        guild = self.client.get_guild(guild_id)
        if not guild:
            return await ctx.send("❌ Server not found.")
        
        name = guild.name
        await guild.leave()
        await ctx.send(f"✅ Left **{name}**")

    @commands.command(name="broadcast", hidden=True)
    async def broadcast(self, ctx: commands.Context, *, message: str):
        """Send a message to all server owners (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        # Confirmation
        await ctx.send(f"⚠️ This will DM all **{len(self.client.guilds)}** server owners. Type `confirm` to proceed.")
        
        def check(m):
            return m.author == ctx.author and m.channel == ctx.channel and m.content.lower() == "confirm"
        
        try:
            await self.client.wait_for("message", check=check, timeout=30)
        except:
            return await ctx.send("❌ Broadcast cancelled.")
        
        success = 0
        failed = 0
        
        embed = discord.Embed(
            title="📢 Message from Bot Owner",
            description=message,
            color=0x3498db,
            timestamp=datetime.now(timezone.utc)
        )
        embed.set_footer(text=f"From {ctx.author}")
        
        for guild in self.client.guilds:
            if guild.owner:
                try:
                    await guild.owner.send(embed=embed)
                    success += 1
                except:
                    failed += 1
        
        await ctx.send(f"✅ Sent to **{success}** owners. Failed: **{failed}**")

    @commands.command(name="reload", hidden=True)
    async def reload_cog(self, ctx: commands.Context, cog_name: str):
        """Reload a cog (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        try:
            await self.client.reload_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Reloaded `{cog_name}`")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="load", hidden=True)
    async def load_cog(self, ctx: commands.Context, cog_name: str):
        """Load a cog (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        try:
            await self.client.load_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Loaded `{cog_name}`")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="unload", hidden=True)
    async def unload_cog(self, ctx: commands.Context, cog_name: str):
        """Unload a cog (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        try:
            await self.client.unload_extension(f"cogs.{cog_name}")
            await ctx.send(f"✅ Unloaded `{cog_name}`")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @commands.command(name="cogs", hidden=True)
    async def list_cogs(self, ctx: commands.Context):
        """List all loaded cogs (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        cog_list = "\n".join([f"✅ `{name}`" for name in self.client.cogs])
        embed = discord.Embed(
            title="🔧 Loaded Cogs",
            description=cog_list or "No cogs loaded",
            color=0x2ecc71
        )
        await ctx.send(embed=embed)

    @commands.command(name="shutdown", hidden=True)
    async def shutdown(self, ctx: commands.Context):
        """Shutdown the bot (Owner only)"""
        if not self.is_owner(ctx.author.id):
            return await ctx.send("❌ This command is owner-only.")
        
        await ctx.send("👋 Shutting down...")
        await self.client.close()


async def setup(client: commands.Bot):
    await client.add_cog(Owner(client))