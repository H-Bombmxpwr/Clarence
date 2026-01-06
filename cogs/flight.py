# cogs/flight.py
import os
import math
import asyncio
import aiohttp
import discord
import contextlib
from datetime import datetime, timezone, date, timedelta
from discord.ext import commands
from typing import Optional, Tuple, Dict, Any, List

BASE = "https://opensky-network.org/api"

AIRPORTS = {
    "KJFK": {"name": "John F. Kennedy International", "city": "New York"},
    "KLAX": {"name": "Los Angeles International", "city": "Los Angeles"},
    "KORD": {"name": "O'Hare International", "city": "Chicago"},
    "KATL": {"name": "Hartsfield-Jackson", "city": "Atlanta"},
    "EGLL": {"name": "London Heathrow", "city": "London"},
    "LFPG": {"name": "Paris Charles de Gaulle", "city": "Paris"},
}


def _fmt_dt_unix(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except:
        return str(ts)


def _callsign_norm(cs: str) -> str:
    return (cs or "").strip().upper()


def _parse_date_str(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _heading_to_compass(deg: float) -> str:
    if deg is None:
        return "—"
    directions = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return directions[round(deg / 22.5) % 16]


class OpenSkyAPI:
    async def _get(self, session, path, params=None):
        url = f"{BASE}/{path}"
        async with session.get(url, params=params or {}, timeout=30) as resp:
            if resp.status != 200:
                raise RuntimeError(f"HTTP {resp.status}")
            return await resp.json(content_type=None)

    async def states_all(self, session):
        return await self._get(session, "states/all")

    async def flights_arrival(self, session, airport, begin, end):
        return await self._get(session, "flights/arrival", {"airport": airport.upper(), "begin": begin, "end": end})

    async def flights_departure(self, session, airport, begin, end):
        return await self._get(session, "flights/departure", {"airport": airport.upper(), "begin": begin, "end": end})

    async def flights_aircraft(self, session, icao24, begin, end):
        return await self._get(session, "flights/aircraft", {"icao24": icao24.lower(), "begin": begin, "end": end})


class FlightDetailView(discord.ui.View):
    def __init__(self, state_data, timeout=120):
        super().__init__(timeout=timeout)
        self.state = state_data

    @discord.ui.button(label="📍 Map", style=discord.ButtonStyle.primary)
    async def map_link(self, interaction: discord.Interaction, button):
        lat, lon = self.state[6], self.state[5]
        if lat and lon:
            await interaction.response.send_message(f"[View on Map](https://www.google.com/maps?q={lat},{lon})", ephemeral=True)
        else:
            await interaction.response.send_message("No position data", ephemeral=True)

    @discord.ui.button(label="🔗 FlightRadar24", style=discord.ButtonStyle.secondary)
    async def fr24(self, interaction: discord.Interaction, button):
        cs = (self.state[1] or "").strip()
        if cs:
            await interaction.response.send_message(f"https://www.flightradar24.com/{cs}", ephemeral=True)
        else:
            await interaction.response.send_message("No callsign", ephemeral=True)


class PaginatedView(discord.ui.View):
    def __init__(self, embeds, author_id, timeout=120):
        super().__init__(timeout=timeout)
        self.embeds = embeds
        self.author_id = author_id
        self.page = 0

    @discord.ui.button(label="◀️", style=discord.ButtonStyle.secondary)
    async def prev_btn(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.author_id:
            return
        self.page = max(0, self.page - 1)
        await interaction.response.edit_message(embed=self.embeds[self.page])

    @discord.ui.button(label="▶️", style=discord.ButtonStyle.secondary)
    async def next_btn(self, interaction: discord.Interaction, button):
        if interaction.user.id != self.author_id:
            return
        self.page = min(len(self.embeds) - 1, self.page + 1)
        await interaction.response.edit_message(embed=self.embeds[self.page])


class Flight(commands.Cog):
    """✈️ Flight Tracking"""

    def __init__(self, client):
        self.client = client
        self.api = OpenSkyAPI()

    def _create_flight_embed(self, state) -> discord.Embed:
        icao24 = state[0] or "—"
        callsign = (state[1] or "").strip() or "—"
        country = state[2] or "Unknown"
        on_ground = state[8]
        geo_alt = state[13]
        velocity = state[9]
        heading = state[10]
        vert_rate = state[11]
        last_contact = state[4]

        alt_ft = f"{int(geo_alt * 3.28084):,} ft" if isinstance(geo_alt, (int, float)) else "—"
        gs_kts = f"{int(velocity * 1.94384):,} kts" if isinstance(velocity, (int, float)) else "—"
        heading_str = f"{int(heading)}° ({_heading_to_compass(heading)})" if isinstance(heading, (int, float)) else "—"
        vr_fpm = f"{int(vert_rate * 196.85):+,} fpm" if isinstance(vert_rate, (int, float)) else "—"
        status = "🛬 On Ground" if on_ground else "✈️ In Flight"

        embed = discord.Embed(
            title=f"✈️ {callsign}",
            description=f"{status} | {country}",
            color=0x1e90ff if not on_ground else 0x2ecc71
        )
        embed.add_field(name="🔢 Hex", value=f"`{icao24}`", inline=True)
        embed.add_field(name="📏 Altitude", value=alt_ft, inline=True)
        embed.add_field(name="💨 Speed", value=gs_kts, inline=True)
        embed.add_field(name="🧭 Heading", value=heading_str, inline=True)
        embed.add_field(name="📈 Vert Rate", value=vr_fpm, inline=True)
        embed.add_field(name="🕐 Last Contact", value=_fmt_dt_unix(last_contact), inline=True)
        embed.set_footer(text="Data from OpenSky Network")
        return embed

    @commands.command(name="flight", aliases=["fl"], help="Track a flight by callsign. Example: flight UAL123")
    async def flight(self, ctx, *, code: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `flight <callsign>` Example: `flight UAL123`")
        
        callsign = _callsign_norm(code)
        async with ctx.typing():
            async with aiohttp.ClientSession() as s:
                try:
                    data = await self.api.states_all(s)
                except Exception as e:
                    return await ctx.send(f"❌ Error: {e}")
        
        states = data.get("states") or []
        matches = [st for st in states if _callsign_norm(st[1] or "") == callsign]
        
        if not matches:
            return await ctx.send(f"❌ No live results for **{callsign}**")
        
        if len(matches) == 1:
            embed = self._create_flight_embed(matches[0])
            view = FlightDetailView(matches[0])
            await ctx.send(embed=embed, view=view)
        else:
            embeds = [self._create_flight_embed(st) for st in matches]
            view = PaginatedView(embeds, ctx.author.id)
            await ctx.send(embed=embeds[0], view=view)

    @commands.command(name="live", help="Quick flight lookup. Example: live AAL7")
    async def live(self, ctx, *, code: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `live <callsign>`")
        
        callsign = _callsign_norm(code)
        async with aiohttp.ClientSession() as s:
            try:
                data = await self.api.states_all(s)
            except Exception as e:
                return await ctx.send(f"❌ Error: {e}")
        
        states = data.get("states") or []
        st = next((x for x in states if _callsign_norm(x[1] or "") == callsign), None)
        
        if not st:
            return await ctx.send(f"❌ No live result for **{callsign}**")
        
        alt = f"{int(st[13] * 3.28084):,}ft" if st[13] else "—"
        spd = f"{int(st[9] * 1.94384)}kts" if st[9] else "—"
        status = "🛬" if st[8] else "✈️"
        
        await ctx.send(f"{status} **{callsign}** | {st[2]} | Alt: {alt} | Speed: {spd}")

    @commands.command(name="arrivals", aliases=["arr"], help="Airport arrivals. Example: arrivals KJFK 2025-01-04")
    async def arrivals(self, ctx, code: Optional[str] = None, when: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `arrivals <ICAO> [YYYY-MM-DD]`\nExample: `arrivals KJFK 2025-01-04`")
        
        when = when or date.today().isoformat()
        try:
            d = _parse_date_str(when)
        except:
            return await ctx.send("❌ Date format: YYYY-MM-DD")
        
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = begin + 86400
        
        async with ctx.typing():
            async with aiohttp.ClientSession() as s:
                try:
                    flights = await self.api.flights_arrival(s, code, begin, end)
                except Exception as e:
                    return await ctx.send(f"❌ Error: {e}")
        
        if not flights or isinstance(flights, dict):
            return await ctx.send(f"❌ No arrivals for {code.upper()} on {d}")
        
        embed = discord.Embed(title=f"🛬 Arrivals at {code.upper()}", description=f"📅 {d}", color=0x2ecc71)
        for f in flights[:12]:
            cs = (f.get("callsign") or "—").strip()
            dep = f.get("estDepartureAirport") or "?"
            embed.add_field(name=cs, value=f"From: {dep}", inline=True)
        embed.set_footer(text=f"{len(flights)} total flights")
        await ctx.send(embed=embed)

    @commands.command(name="departures", aliases=["dep"], help="Airport departures. Example: departures KLAX 2025-01-04")
    async def departures(self, ctx, code: Optional[str] = None, when: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `departures <ICAO> [YYYY-MM-DD]`")
        
        when = when or date.today().isoformat()
        try:
            d = _parse_date_str(when)
        except:
            return await ctx.send("❌ Date format: YYYY-MM-DD")
        
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = begin + 86400
        
        async with ctx.typing():
            async with aiohttp.ClientSession() as s:
                try:
                    flights = await self.api.flights_departure(s, code, begin, end)
                except Exception as e:
                    return await ctx.send(f"❌ Error: {e}")
        
        if not flights or isinstance(flights, dict):
            return await ctx.send(f"❌ No departures for {code.upper()} on {d}")
        
        embed = discord.Embed(title=f"🛫 Departures from {code.upper()}", description=f"📅 {d}", color=0x3498db)
        for f in flights[:12]:
            cs = (f.get("callsign") or "—").strip()
            arr = f.get("estArrivalAirport") or "?"
            embed.add_field(name=cs, value=f"To: {arr}", inline=True)
        embed.set_footer(text=f"{len(flights)} total flights")
        await ctx.send(embed=embed)

    @commands.command(name="tail", help="Track by aircraft hex. Example: tail a1b2c3 2025-01-04")
    async def tail(self, ctx, icao24: Optional[str] = None, when: Optional[str] = None):
        if not icao24:
            return await ctx.send("Usage: `tail <hex> [YYYY-MM-DD]`")
        
        when = when or date.today().isoformat()
        try:
            d = _parse_date_str(when)
        except:
            return await ctx.send("❌ Date format: YYYY-MM-DD")
        
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = begin + 86400
        
        async with ctx.typing():
            async with aiohttp.ClientSession() as s:
                try:
                    flights = await self.api.flights_aircraft(s, icao24, begin, end)
                except Exception as e:
                    return await ctx.send(f"❌ Error: {e}")
        
        if not flights or isinstance(flights, dict):
            return await ctx.send(f"❌ No flights for hex `{icao24}` on {d}")
        
        embed = discord.Embed(title=f"🛩️ Aircraft {icao24.upper()}", description=f"📅 {d}", color=0x607d8b)
        for f in flights[:10]:
            cs = (f.get("callsign") or "—").strip()
            dep = f.get("estDepartureAirport") or "?"
            arr = f.get("estArrivalAirport") or "?"
            embed.add_field(name=cs, value=f"{dep} → {arr}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="airports", help="List common airport codes")
    async def airports(self, ctx):
        embed = discord.Embed(title="🏢 Common Airport Codes", color=0x3498db)
        codes = "\n".join([f"`{k}` - {v['name']} ({v['city']})" for k, v in AIRPORTS.items()])
        embed.description = codes
        await ctx.send(embed=embed)


async def setup(client):
    await client.add_cog(Flight(client))