# cogs/flight.py
"""Flight tracking, schedules, airport info and aviation weather."""
import asyncio
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import discord
from discord import app_commands
from discord.ext import commands

from functionality import aviation as av
from functionality.ui import Paginator, chunk_lines

BLUE = 0x1e90ff
NO_KEY_MSG = ("Schedules need a free AeroDataBox key. Sign up at <https://rapidapi.com/aedbx-aedbx/api/aerodatabox> "
              "(Basic plan is free), then set `AERODATABOX_KEY` in keys.env / Railway variables.")
STATUS_EMOJI = {
    "Expected": "🕒", "CheckIn": "🛄", "Boarding": "🚶", "GateClosed": "🚪", "Departed": "🛫", "EnRoute": "✈️",
    "Approaching": "🛬", "Arrived": "✅", "Delayed": "⏰", "Canceled": "❌", "CanceledUncertain": "❓",
    "Diverted": "↪️", "Unknown": "❔",
}


# ---------------------------------------------------------------------------- formatting helpers

def _alt(ac: dict) -> str:
    alt = ac.get("alt_baro")
    if alt == "ground":
        return "On ground"
    return f"{int(alt):,} ft" if isinstance(alt, (int, float)) else "—"


def _parse_adb_time(t: Optional[dict]) -> Optional[datetime]:
    if not t or not t.get("utc"):
        return None
    try:
        return datetime.fromisoformat(t["utc"].replace("Z", "+00:00"))
    except ValueError:
        return None


def _local_hm(t: Optional[dict]) -> str:
    local = (t or {}).get("local") or ""
    return local[11:16] if len(local) >= 16 else "—"


def _movement_line(m: Optional[dict], kind: str) -> str:
    """One field describing a departure/arrival movement from AeroDataBox."""
    if not m:
        return "—"
    ap = m.get("airport", {})
    name = f"**{ap.get('iata') or ap.get('icao') or '?'}** {ap.get('shortName') or ap.get('name', '')}"
    sched = m.get("scheduledTime")
    revised = m.get("revisedTime") or m.get("predictedTime")
    actual = m.get("runwayTime")
    lines = [name, f"Scheduled: `{_local_hm(sched)}` local"]
    if revised and revised.get("local") != (sched or {}).get("local"):
        lines.append(f"Estimated: `{_local_hm(revised)}` local")
    if actual:
        lines.append(f"{'Took off' if kind == 'dep' else 'Landed'}: `{_local_hm(actual)}` local")
    when = _parse_adb_time(actual or revised or sched)
    if when:
        lines.append(f"<t:{int(when.timestamp())}:R>")
    extras = []
    if m.get("terminal"):
        extras.append(f"Terminal {m['terminal']}")
    if m.get("gate"):
        extras.append(f"Gate {m['gate']}")
    if m.get("baggageBelt"):
        extras.append(f"Belt {m['baggageBelt']}")
    if extras:
        lines.append(" • ".join(extras))
    return "\n".join(lines)


def _delay_minutes(m: Optional[dict]) -> Optional[int]:
    if not m:
        return None
    sched = _parse_adb_time(m.get("scheduledTime"))
    other = _parse_adb_time(m.get("runwayTime") or m.get("revisedTime") or m.get("predictedTime"))
    if sched and other:
        return int((other - sched).total_seconds() // 60)
    return None


def _board_line(f: dict, direction: str) -> str:
    """One line on a departures/arrivals board."""
    here = f.get("departure" if direction == "Departure" else "arrival") or f.get("movement") or {}
    there = f.get("arrival" if direction == "Departure" else "departure") or {}
    other = there.get("airport", {}) if there else (f.get("movement") or {}).get("airport", {})
    status = f.get("status", "Unknown")
    delay = _delay_minutes(here)
    delay_txt = f" (+{delay}m)" if delay and delay >= 5 else ""
    gate = f" • gate {here['gate']}" if here.get("gate") else ""
    est = here.get("revisedTime") or here.get("predictedTime")
    time_txt = _local_hm(here.get("scheduledTime"))
    if est and _local_hm(est) != time_txt:
        time_txt = f"~~{time_txt}~~ {_local_hm(est)}"
    dest = other.get("iata") or other.get("icao") or "?"
    city = other.get("municipalityName") or other.get("shortName") or other.get("name") or ""
    arrow = "→" if direction == "Departure" else "←"
    return (f"`{time_txt}` {STATUS_EMOJI.get(status, '')} **{f.get('number', '?')}** {arrow} {dest} {city[:18]}"
            f"{gate}{delay_txt}")


def live_fields(embed: discord.Embed, ac: dict, dest: Optional[dict] = None):
    gs = ac.get("gs")
    heading = ac.get("track") or ac.get("true_heading")
    vr = ac.get("baro_rate") or ac.get("geom_rate")
    embed.add_field(name="Altitude", value=_alt(ac))
    embed.add_field(name="Ground speed", value=f"{int(gs)} kt" if gs is not None else "—")
    embed.add_field(name="Heading", value=f"{int(heading)}° {av.compass(heading)}" if heading is not None else "—")
    embed.add_field(name="Vertical", value=f"{int(vr):+,} fpm" if vr else "level")
    embed.add_field(name="Squawk", value=ac.get("squawk") or "—")
    if ac.get("lat") is not None:
        embed.add_field(name="Position", value=f"{ac['lat']:.3f}, {ac['lon']:.3f}")
        if dest and dest.get("latitude") is not None and gs and gs > 50 and ac.get("alt_baro") != "ground":
            remaining = av.haversine_nm(ac["lat"], ac["lon"], dest["latitude"], dest["longitude"])
            eta = datetime.now(timezone.utc) + timedelta(hours=remaining / gs)
            embed.add_field(name="To destination", value=f"{int(remaining):,} nm • ETA ~<t:{int(eta.timestamp())}:t>",
                            inline=False)
    if ac.get("emergency") and ac["emergency"] != "none":
        embed.add_field(name="Emergency", value=ac["emergency"], inline=False)


class TrackLinks(discord.ui.View):
    def __init__(self, hex_code: Optional[str], callsign: Optional[str], reg: Optional[str]):
        super().__init__(timeout=None)
        if hex_code:
            self.add_item(discord.ui.Button(label="Live map", url=f"https://globe.adsb.lol/?icao={hex_code.lower()}"))
        if callsign:
            self.add_item(discord.ui.Button(label="FlightAware", url=f"https://www.flightaware.com/live/flight/{callsign}"))
            self.add_item(discord.ui.Button(label="Flightradar24", url=f"https://www.flightradar24.com/{callsign}"))
        elif reg:
            self.add_item(discord.ui.Button(label="FlightAware", url=f"https://www.flightaware.com/live/flight/{reg.replace('-', '')}"))


class Flight(commands.Cog):
    """Flights, airports and aviation weather"""

    flight = app_commands.Group(name="flight", description="Track flights and look up schedules")
    airport = app_commands.Group(name="airport", description="Airport information and weather")

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def cog_load(self):
        asyncio.create_task(self._preload_airports())

    async def _preload_airports(self):
        await self.bot.wait_until_ready()
        try:
            await av.airport_db.ensure_loaded(self.bot.session)
        except Exception as e:
            print(f"[flight] airport database not loaded yet: {e}")

    @property
    def session(self):
        return self.bot.session

    async def resolve_airport(self, interaction: discord.Interaction, query: str) -> Optional[av.Airport]:
        await av.airport_db.ensure_loaded(self.session)
        ap = av.airport_db.lookup(query)
        if not ap:
            await interaction.followup.send(f"Couldn't find an airport matching **{query}**.")
        return ap

    async def airport_autocomplete(self, interaction: discord.Interaction, current: str) -> list[app_commands.Choice[str]]:
        if not av.airport_db.airports:
            return []
        return [app_commands.Choice(name=f"{av.flag(a.country)} {a.label}"[:100], value=(a.iata or a.code))
                for a in av.airport_db.search(current, 25)]

    async def cog_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        original = getattr(error, "original", error)
        if isinstance(original, (av.ApiError, asyncio.TimeoutError)):
            msg = NO_KEY_MSG if isinstance(original, av.NoApiKey) else f"{original or 'The data provider timed out.'}"
            if interaction.response.is_done():
                await interaction.followup.send(msg)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
            error.handled = True  # tells the global handler in main.py to skip it

    # ------------------------------------------------------------------ /flight track

    @flight.command(name="track", description="Live position, route and aircraft for a flight (e.g. UA1, DAL100, N12004)")
    @app_commands.describe(query="Flight number (UA1), ICAO callsign (UAL1), registration (N12004) or ICAO hex (a05627)")
    async def track(self, interaction: discord.Interaction, query: str):
        await interaction.response.defer()
        q = query.strip().upper().replace(" ", "")
        route = aircraft = None
        live: list[dict] = []
        callsign = iata_number = None

        if av.HEX_RE.match(q) and not av.FLIGHT_NUMBER_RE.match(q):
            live = await av.live_by_hex(self.session, q)
            aircraft = await av.aircraft_info(self.session, q)
        elif av.REG_RE.match(q) and not av.FLIGHT_NUMBER_RE.match(q):
            live = await av.live_by_reg(self.session, q)
            aircraft = await av.aircraft_info(self.session, q)
        else:
            callsign, iata_number = await av.normalize_flight(self.session, q)
            route, live = await asyncio.gather(av.route_for_callsign(self.session, callsign),
                                               av.live_by_callsign(self.session, callsign))
            if live and live[0].get("hex"):
                aircraft = await av.aircraft_info(self.session, live[0]["hex"])

        ac = live[0] if live else None
        if ac and not callsign and ac.get("flight"):
            callsign = ac["flight"].strip()
            route = await av.route_for_callsign(self.session, callsign)

        if not route and not ac and not aircraft:
            hint = "\nFor scheduled flights that aren't airborne yet, try `/flight status`." if av.aerodatabox_enabled() else ""
            return await interaction.followup.send(f"Nothing found for **{query}**. It may not be airborne or in ADS-B coverage.{hint}")

        title = " / ".join(dict.fromkeys(x for x in (iata_number, callsign) if x)) if callsign else q
        embed = discord.Embed(title=title, color=BLUE)
        if route:
            airline = route.get("airline") or {}
            o, d = route.get("origin") or {}, route.get("destination") or {}
            if airline.get("name"):
                embed.description = f"**{airline['name']}**"
            embed.add_field(name="From", value=f"{av.flag(o.get('country_iso_name'))} **{o.get('iata_code') or o.get('icao_code')}**\n{o.get('municipality', '')}")
            embed.add_field(name="To", value=f"{av.flag(d.get('country_iso_name'))} **{d.get('iata_code') or d.get('icao_code')}**\n{d.get('municipality', '')}")
            if o.get("latitude") is not None and d.get("latitude") is not None:
                embed.add_field(name="Distance", value=f"{int(av.haversine_nm(o['latitude'], o['longitude'], d['latitude'], d['longitude'])):,} nm")
        else:
            d = None

        if ac:
            embed.add_field(name="Status", value="Live" + (" (on ground)" if ac.get("alt_baro") == "ground" else " — in flight"), inline=False)
            live_fields(embed, ac, d)
            seen = ac.get("seen_pos") or ac.get("seen")
            embed.set_footer(text=f"Live data: adsb.lol • updated {seen:.0f}s ago" if seen is not None else "Live data: adsb.lol")
        else:
            embed.add_field(name="Status", value="Not currently tracked (on the ground, not yet departed, or out of coverage)", inline=False)
            embed.set_footer(text="Route data: adsbdb • routes are typical routes for this callsign")

        reg = (ac or {}).get("r") or (aircraft or {}).get("registration")
        if aircraft:
            embed.add_field(name="Aircraft", value=f"{aircraft.get('manufacturer', '')} {aircraft.get('type', '')} (`{aircraft.get('icao_type', '?')}`)\n"
                                                   f"Reg **{aircraft.get('registration', '?')}** • {aircraft.get('registered_owner', '')}", inline=False)
            if aircraft.get("url_photo"):
                embed.set_image(url=aircraft["url_photo"])
        elif ac and (ac.get("t") or reg):
            embed.add_field(name="Aircraft", value=f"{ac.get('desc') or ac.get('t') or '?'} • Reg **{reg or '?'}**", inline=False)

        hex_code = (ac or {}).get("hex") or (aircraft or {}).get("mode_s")
        await interaction.followup.send(embed=embed, view=TrackLinks(hex_code, callsign, reg))

    # ------------------------------------------------------------------ /flight aircraft

    @flight.command(name="aircraft", description="Look up an aircraft by registration or ICAO hex")
    @app_commands.describe(registration="Tail number (N12004, G-EUPT) or ICAO hex (a05627)")
    async def aircraft(self, interaction: discord.Interaction, registration: str):
        await interaction.response.defer()
        q = registration.strip().upper()
        info = await av.aircraft_info(self.session, q)
        live = await (av.live_by_hex(self.session, q) if av.HEX_RE.match(q) else av.live_by_reg(self.session, q))
        if not info and not live:
            return await interaction.followup.send(f"No aircraft found for **{registration}**.")
        info = info or {}
        ac = live[0] if live else None
        embed = discord.Embed(title=f"{info.get('registration') or (ac or {}).get('r') or q}", color=BLUE,
                              description=f"{info.get('manufacturer', '')} {info.get('type', '') or (ac or {}).get('t', '')}".strip())
        embed.add_field(name="ICAO type", value=info.get("icao_type") or (ac or {}).get("t") or "—")
        embed.add_field(name="Mode S hex", value=f"`{(info.get('mode_s') or (ac or {}).get('hex') or '—').upper()}`")
        embed.add_field(name="Owner / operator", value=info.get("registered_owner") or "—")
        embed.add_field(name="Registered in", value=f"{av.flag(info.get('registered_owner_country_iso_name'))} {info.get('registered_owner_country_name', '—')}")
        if ac:
            cs = (ac.get("flight") or "").strip()
            embed.add_field(name="Currently", value=f"Flying as **{cs or 'no callsign'}**", inline=False)
            live_fields(embed, ac)
        else:
            embed.add_field(name="Currently", value="Not being tracked right now", inline=False)
        if info.get("url_photo"):
            embed.set_image(url=info["url_photo"])
        hex_code = info.get("mode_s") or (ac or {}).get("hex")
        await interaction.followup.send(embed=embed, view=TrackLinks(hex_code, (ac or {}).get("flight", "").strip() or None,
                                                                     info.get("registration")))

    # ------------------------------------------------------------------ /flight nearby

    @flight.command(name="nearby", description="Aircraft flying near an airport right now")
    @app_commands.describe(airport="Airport code or name", radius="Radius in nautical miles")
    @app_commands.autocomplete(airport=airport_autocomplete)
    async def nearby(self, interaction: discord.Interaction, airport: str, radius: app_commands.Range[int, 5, 100] = 25):
        await interaction.response.defer()
        ap = await self.resolve_airport(interaction, airport)
        if not ap:
            return
        aircraft = await av.live_near(self.session, ap.lat, ap.lon, radius)
        if not aircraft:
            return await interaction.followup.send(f"No aircraft within {radius} nm of **{ap.label}** right now.")

        def sort_key(a):
            return a.get("dst") if a.get("dst") is not None else 999
        lines = []
        for a in sorted(aircraft, key=sort_key):
            cs = (a.get("flight") or "").strip() or a.get("r") or a.get("hex", "?").upper()
            alt = _alt(a)
            gs = f"{int(a['gs'])}kt" if a.get("gs") is not None else ""
            dist = f"{a['dst']:.0f}nm {av.compass(a.get('dir'))}" if a.get("dst") is not None else ""
            vr = a.get("baro_rate") or 0
            trend = "↗" if vr > 300 else "↘" if vr < -300 else ""
            lines.append(f"**{cs}** `{a.get('t', '?')}` {alt}{trend} {gs} • {dist}")
        pages = [discord.Embed(title=f"{len(aircraft)} aircraft near {ap.iata or ap.code}", description=c, color=BLUE)
                 .set_footer(text=f"Within {radius} nm of {ap.name} • adsb.lol") for c in chunk_lines(lines, 3500)]
        await Paginator(pages, interaction.user.id).send(interaction)

    # ------------------------------------------------------------------ schedules (AeroDataBox)

    @flight.command(name="status", description="Schedule, delays, gates and terminals for a flight number")
    @app_commands.describe(number="Flight number, e.g. UA1 or AA100", day="Date YYYY-MM-DD (defaults to today)")
    async def status(self, interaction: discord.Interaction, number: str, day: Optional[str] = None):
        if not av.aerodatabox_enabled():
            return await interaction.response.send_message(NO_KEY_MSG, ephemeral=True)
        if day:
            try:
                date.fromisoformat(day)
            except ValueError:
                return await interaction.response.send_message("Date must be YYYY-MM-DD.", ephemeral=True)
        await interaction.response.defer()
        flights = await av.flight_status(self.session, number, day)
        if not flights:
            return await interaction.followup.send(f"No schedule found for **{number.upper()}**" + (f" on {day}" if day else " today") + ".")

        pages = []
        for f in flights:
            status = f.get("status", "Unknown")
            airline = (f.get("airline") or {}).get("name", "")
            embed = discord.Embed(title=f"{f.get('number', number.upper())} — {status}",
                                  description=airline, color=0xe74c3c if status in ("Canceled", "Diverted") else BLUE)
            embed.add_field(name="Departure", value=_movement_line(f.get("departure"), "dep"))
            embed.add_field(name="Arrival", value=_movement_line(f.get("arrival"), "arr"))
            delay = _delay_minutes(f.get("departure"))
            if delay and delay >= 5:
                embed.add_field(name="Delay", value=f"{delay} min late departing", inline=False)
            ac = f.get("aircraft") or {}
            if ac:
                embed.add_field(name="Aircraft", value=f"{ac.get('model', '?')}" + (f" • {ac['reg']}" if ac.get("reg") else ""), inline=False)
                if (ac.get("image") or {}).get("url"):
                    embed.set_image(url=ac["image"]["url"])
            dist = (f.get("greatCircleDistance") or {}).get("nm")
            if dist:
                embed.add_field(name="Distance", value=f"{int(dist):,} nm")
            embed.set_footer(text="Schedule data: AeroDataBox • times are airport local")
            pages.append(embed)
        await Paginator(pages, interaction.user.id).send(interaction)

    async def _board(self, interaction: discord.Interaction, airport: str, hours: int, direction: str):
        if not av.aerodatabox_enabled():
            return await interaction.response.send_message(NO_KEY_MSG, ephemeral=True)
        await interaction.response.defer()
        ap = await self.resolve_airport(interaction, airport)
        if not ap:
            return
        if not ap.icao:
            return await interaction.followup.send(f"{ap.name} has no ICAO code, so no schedule data is available.")
        data = await av.airport_board_relative(self.session, ap.icao, -30, hours * 60, direction)
        flights = data.get("departures" if direction == "Departure" else "arrivals") or []
        if not flights:
            return await interaction.followup.send(f"No {direction.lower()}s found for **{ap.label}** in the next {hours}h.")
        lines = [_board_line(f, direction) for f in flights]
        icon = "Departures" if direction == "Departure" else "Arrivals"
        pages = []
        for chunk in chunk_lines(lines, 3000):
            embed = discord.Embed(title=f"{icon} — {ap.iata or ap.code}", description=chunk, color=BLUE)
            embed.set_author(name=ap.name)
            embed.set_footer(text=f"{len(flights)} flights • next {hours}h • airport local time • AeroDataBox")
            pages.append(embed)
        await Paginator(pages, interaction.user.id).send(interaction)

    @flight.command(name="departures", description="Departures board for an airport")
    @app_commands.describe(airport="Airport code or name", hours="How many hours ahead (max 12)")
    @app_commands.autocomplete(airport=airport_autocomplete)
    async def departures(self, interaction: discord.Interaction, airport: str, hours: app_commands.Range[int, 1, 12] = 4):
        await self._board(interaction, airport, hours, "Departure")

    @flight.command(name="arrivals", description="Arrivals board for an airport")
    @app_commands.describe(airport="Airport code or name", hours="How many hours ahead (max 12)")
    @app_commands.autocomplete(airport=airport_autocomplete)
    async def arrivals(self, interaction: discord.Interaction, airport: str, hours: app_commands.Range[int, 1, 12] = 4):
        await self._board(interaction, airport, hours, "Arrival")

    @flight.command(name="route", description="Find flights between two airports")
    @app_commands.describe(origin="Departure airport", destination="Arrival airport",
                           day="Date YYYY-MM-DD in the origin's local time (default: the next 12 hours)")
    @app_commands.autocomplete(origin=airport_autocomplete, destination=airport_autocomplete)
    async def route(self, interaction: discord.Interaction, origin: str, destination: str, day: Optional[str] = None):
        if not av.aerodatabox_enabled():
            return await interaction.response.send_message(NO_KEY_MSG, ephemeral=True)
        if day:
            try:
                date.fromisoformat(day)
            except ValueError:
                return await interaction.response.send_message("Date must be YYYY-MM-DD.", ephemeral=True)
        await interaction.response.defer()
        org = await self.resolve_airport(interaction, origin)
        dst = org and await self.resolve_airport(interaction, destination)
        if not org or not dst:
            return
        if not org.icao:
            return await interaction.followup.send(f"{org.name} has no ICAO code, so no schedule data is available.")

        if day:
            boards = await asyncio.gather(
                av.airport_board(self.session, org.icao, f"{day}T00:00", f"{day}T11:59", "Departure"),
                av.airport_board(self.session, org.icao, f"{day}T12:00", f"{day}T23:59", "Departure"))
            window = day
        else:
            boards = [await av.airport_board_relative(self.session, org.icao, -30, 720, "Departure")]
            window = "next 12 hours"
        dest_codes = {c for c in (dst.icao, dst.iata, dst.ident) if c}
        matches = []
        for b in boards:
            for f in b.get("departures") or []:
                arr_ap = (f.get("arrival") or {}).get("airport", {})
                if arr_ap.get("icao") in dest_codes or arr_ap.get("iata") in dest_codes:
                    matches.append(f)
        if not matches:
            return await interaction.followup.send(
                f"No direct flights found **{org.iata or org.code} → {dst.iata or dst.code}** ({window}).")

        lines = []
        for f in matches:
            dep, arr = f.get("departure") or {}, f.get("arrival") or {}
            status = f.get("status", "Unknown")
            airline = (f.get("airline") or {}).get("name", "")
            model = (f.get("aircraft") or {}).get("model", "")
            gate = f" • gate {dep['gate']}" if dep.get("gate") else ""
            lines.append(f"{STATUS_EMOJI.get(status, '')} **{f.get('number')}** {airline}\n"
                         f"└ `{_local_hm(dep.get('scheduledTime'))}` → `{_local_hm(arr.get('scheduledTime'))}` local"
                         f"{' • ' + model if model else ''}{gate} • {status}")
        pages = [discord.Embed(title=f"{org.iata or org.code} → {dst.iata or dst.code}", description=c, color=BLUE)
                 .set_footer(text=f"{len(matches)} flights • {window} • AeroDataBox") for c in chunk_lines(lines, 3500)]
        await Paginator(pages, interaction.user.id).send(interaction)

    # ------------------------------------------------------------------ /airport

    @airport.command(name="info", description="Airport details, current weather and nearby links")
    @app_commands.describe(airport="IATA/ICAO code or name")
    @app_commands.autocomplete(airport=airport_autocomplete)
    async def airport_info(self, interaction: discord.Interaction, airport: str):
        await interaction.response.defer()
        ap = await self.resolve_airport(interaction, airport)
        if not ap:
            return
        embed = discord.Embed(title=f"{av.flag(ap.country)} {ap.name}", color=BLUE,
                              description=f"{ap.city}, {ap.region.split('-')[-1]}, {ap.country}" if ap.city else ap.country)
        embed.add_field(name="IATA", value=ap.iata or "—")
        embed.add_field(name="ICAO", value=ap.icao or ap.ident)
        embed.add_field(name="Type", value=ap.type.replace("_", " ").title() + (" • scheduled service" if ap.scheduled else ""))
        embed.add_field(name="Elevation", value=f"{ap.elevation_ft:,} ft" if ap.elevation_ft is not None else "—")
        embed.add_field(name="Coordinates", value=f"{ap.lat:.4f}, {ap.lon:.4f}")
        if ap.icao:
            m = await av.metar(self.session, ap.icao)
            if m:
                wind = f"{m.get('wdir', 'VRB')}° @ {m.get('wspd', 0)} kt" + (f" G{m['wgst']}" if m.get("wgst") else "")
                temp = f"{m['temp']:.0f}°C / {m['temp'] * 9 / 5 + 32:.0f}°F" if m.get("temp") is not None else "—"
                embed.add_field(name=f"Weather ({m.get('fltCat', '?')})",
                                value=f"{temp} • wind {wind} • vis {m.get('visib', '?')} SM\n`{m.get('rawOb', '')}`", inline=False)
        live = await av.live_near(self.session, ap.lat, ap.lon, 10)
        embed.add_field(name="Traffic", value=f"{len(live)} aircraft within 10 nm right now", inline=False)
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label="Map", url=f"https://www.google.com/maps?q={ap.lat},{ap.lon}"))
        view.add_item(discord.ui.Button(label="Live traffic", url=f"https://globe.adsb.lol/?lat={ap.lat}&lon={ap.lon}&zoom=11"))
        if ap.wikipedia:
            view.add_item(discord.ui.Button(label="Wikipedia", url=ap.wikipedia))
        if ap.home:
            view.add_item(discord.ui.Button(label="Website", url=ap.home))
        await interaction.followup.send(embed=embed, view=view)

    @airport.command(name="weather", description="METAR and TAF for an airport")
    @app_commands.describe(airport="IATA/ICAO code or name")
    @app_commands.autocomplete(airport=airport_autocomplete)
    async def weather(self, interaction: discord.Interaction, airport: str):
        await interaction.response.defer()
        ap = await self.resolve_airport(interaction, airport)
        if not ap:
            return
        code = ap.icao or ap.ident
        m, t = await asyncio.gather(av.metar(self.session, code), av.taf(self.session, code))
        if not m and not t:
            return await interaction.followup.send(f"No weather reports available for **{ap.label}**.")
        cat_color = {"VFR": 0x2ecc71, "MVFR": 0x3498db, "IFR": 0xe74c3c, "LIFR": 0x9b59b6}
        embed = discord.Embed(title=f"Weather — {ap.iata or code} {ap.name}", color=cat_color.get((m or {}).get("fltCat"), BLUE))
        if m:
            clouds = ", ".join(f"{c['cover']} {c['base']:,} ft" for c in m.get("clouds", []) if c.get("base") is not None) or "Clear"
            obs = datetime.fromtimestamp(m["obsTime"], timezone.utc) if m.get("obsTime") else None
            embed.add_field(name="Flight category", value=m.get("fltCat", "—"))
            embed.add_field(name="Wind", value=f"{m.get('wdir', 'VRB')}° @ {m.get('wspd', 0)} kt" + (f" gust {m['wgst']}" if m.get("wgst") else ""))
            embed.add_field(name="Visibility", value=f"{m.get('visib', '—')} SM")
            if m.get("temp") is not None:
                embed.add_field(name="Temp / dew", value=f"{m['temp']:.0f}°C / {m.get('dewp', 0):.0f}°C")
            if m.get("altim"):
                embed.add_field(name="Altimeter", value=f"{m['altim']:.0f} hPa ({m['altim'] * 0.02953:.2f} inHg)")
            embed.add_field(name="Clouds", value=clouds)
            embed.add_field(name="METAR" + (f" (<t:{int(obs.timestamp())}:R>)" if obs else ""), value=f"```{m.get('rawOb', '')}```", inline=False)
        if t:
            embed.add_field(name="TAF", value=f"```{t[:1000]}```", inline=False)
        embed.set_footer(text="aviationweather.gov")
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Flight(bot))
