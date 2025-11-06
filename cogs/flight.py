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
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

# ----------------- utils -----------------

def _fmt_dt_unix(ts: Optional[int]) -> str:
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(int(ts), tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    except Exception:
        return str(ts)

def _paginate(items: List[Any], page: int, per_page: int = 10) -> Tuple[List[Any], int]:
    total_pages = max(1, math.ceil(len(items) / per_page))
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    return items[start:end], total_pages

def _callsign_norm(cs: str) -> str:
    # OpenSky callsigns are up to 8 chars, often space padded; normalize.
    return (cs or "").strip().upper()

def _parse_date_str(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()

# ----------------- OAuth2 (client credentials) -----------------

class OpenSkyAuth:
    def __init__(self):
        self.client_id = os.getenv("OPENSKY_CLIENT_ID")
        self.client_secret = os.getenv("OPENSKY_CLIENT_SECRET")
        self._token: Optional[str] = None
        self._exp_ts: int = 0

    @property
    def has_creds(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def bearer(self, session: aiohttp.ClientSession) -> Optional[str]:
        now = int(datetime.now(tz=timezone.utc).timestamp())
        if self._token and now < self._exp_ts - 30:
            return self._token
        if not self.has_creds:
            return None
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }
        async with session.post(TOKEN_URL, data=data, timeout=25) as resp:
            body = await resp.text()
            if resp.status != 200:
                raise RuntimeError(f"Token HTTP {resp.status} | {body[:200]}")
            j = await resp.json(content_type=None)
            self._token = j["access_token"]
            self._exp_ts = now + int(j.get("expires_in", 1500))
            return self._token

# ----------------- API -----------------

class OpenSkyAPI:
    def __init__(self, auth: OpenSkyAuth):
        self.auth = auth

    async def _get(self, session: aiohttp.ClientSession, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{BASE}/{path}"
        delays = [0.0, 0.7, 1.5]
        last_err = None
        for d in delays:
            if d:
                await asyncio.sleep(d)
            try:
                headers: Dict[str, str] = {}
                tok = await self.auth.bearer(session)
                if tok:
                    headers["Authorization"] = f"Bearer {tok}"
                async with session.get(url, params=params or {}, headers=headers, timeout=30) as resp:
                    text = await resp.text()
                    if resp.status != 200:
                        raise RuntimeError(f"HTTP {resp.status} on {path} | {text[:200]}")
                    try:
                        return await resp.json(content_type=None)
                    except Exception:
                        return text
            except Exception as e:
                last_err = e
                continue
        raise RuntimeError(str(last_err) if last_err else "OpenSky request failed")

    async def states_all(self, session: aiohttp.ClientSession, at: Optional[int] = None, bbox: Optional[List[float]] = None) -> Dict[str, Any]:
        params: Dict[str, Any] = {}
        if at is not None:
            params["time"] = at
        if bbox is not None:
            params["bbox"] = ",".join(str(x) for x in bbox)
        return await self._get(session, "states/all", params)

    async def flights_arrival(self, session: aiohttp.ClientSession, airport_icao: str, begin: int, end: int) -> Any:
        return await self._get(session, "flights/arrival", {"airport": airport_icao.upper(), "begin": begin, "end": end})

    async def flights_departure(self, session: aiohttp.ClientSession, airport_icao: str, begin: int, end: int) -> Any:
        return await self._get(session, "flights/departure", {"airport": airport_icao.upper(), "begin": begin, "end": end})

    async def flights_aircraft(self, session: aiohttp.ClientSession, icao24: str, begin: int, end: int) -> Any:
        return await self._get(session, "flights/aircraft", {"icao24": icao24.lower(), "begin": begin, "end": end})

# ----------------- formatting -----------------

def _mk_state_line(state: List[Any]) -> str:
    """
    State vector fields:
      [0] icao24, [1] callsign, [2] origin_country, [3] time_position, [4] last_contact,
      [5] lon, [6] lat, [7] baro_alt_m, [8] on_ground, [9] vel_ms, [10] true_track_deg,
      [11] vz_ms, [12] sensors, [13] geo_alt_m, [14] squawk, [15] spi, [16] pos_src, [17] category
    """
    if not state:
        return "—"
    icao24 = state[0] or "—"
    callsign = (state[1] or "").strip()
    country = state[2] or "—"
    lon = state[5]
    lat = state[6]
    geo_alt_m = state[13]
    vel_ms = state[9]
    track_deg = state[10]
    last = state[4]

    alt_ft = f"{int(geo_alt_m * 3.28084)} ft" if isinstance(geo_alt_m, (int, float)) else "—"
    gs_kt = f"{int(vel_ms * 1.94384)} kts" if isinstance(vel_ms, (int, float)) else "—"
    track_txt = f"{int(track_deg)}°" if isinstance(track_deg, (int, float)) else "—"
    ts = _fmt_dt_unix(last)

    return (
        f"{callsign or '—'}  (hex {icao24})  {country}\n"
        f"Alt: {alt_ft} | GS: {gs_kt} | Track: {track_txt}\n"
        f"Last: {ts}"
    )

def _mk_flight_line(f: Dict[str, Any]) -> str:
    # flights_* record: icao24, firstSeen, estDepartureAirport, lastSeen, estArrivalAirport, callsign
    cs = (f.get("callsign") or "").strip()
    dep = f.get("estDepartureAirport") or "—"
    arr = f.get("estArrivalAirport") or "—"
    fs = _fmt_dt_unix(f.get("firstSeen"))
    ls = _fmt_dt_unix(f.get("lastSeen"))
    return f"{cs or '—'}  {dep} → {arr}\nTime: {fs} → {ls}"

# ----------------- Cog -----------------

class Flight(commands.Cog):
    """
    OpenSky flight commands (OAuth2 client-credentials; anonymous fallback).

    Commands (UTC):
      flight <CALLSIGN>                 – Live states (first page shows up to 5 matches)
      live <CALLSIGN>                   – Compact live card
      arrivals <ICAO> <YYYY-MM-DD>     – Recorded arrivals on date
      departures <ICAO> <YYYY-MM-DD>   – Recorded departures on date
      tail <ICAO24> <YYYY-MM-DD>       – Flights for hex on date
      osdiag                            – Connectivity/auth diagnostics
    """

    def __init__(self, client):
        self.client = client
        self.auth = OpenSkyAuth()
        self.api = OpenSkyAPI(self.auth)
        if not self.auth.has_creds:
            print("[flight] OpenSky in anonymous mode (rate-limited). Set OPENSKY_CLIENT_ID/OPENSKY_CLIENT_SECRET.")

    # ---------- commands ----------

    @commands.command(help="Flight status by callsign (e.g., UAL123). Example: flight UAL123")
    async def flight(self, ctx, *, code: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `flight <CALLSIGN>`  e.g., `flight UAL123`")
        callsign = _callsign_norm(code)
        async with aiohttp.ClientSession() as s:
            try:
                data = await self.api.states_all(s)
            except Exception as e:
                return await ctx.send(f"OpenSky error: {e}")
        states = data.get("states") or []
        matches = [st for st in states if _callsign_norm((st[1] or "").replace(" ", "")) == callsign.replace(" ", "")]
        if not matches:
            return await ctx.send("No live result for that callsign.")

        page = 1
        while True:
            page_items, total = _paginate(matches, page, 5)
            emb = discord.Embed(
                title=f"Live states: {callsign}",
                color=0x1e90ff,
                description="\n\n".join(_mk_state_line(st) for st in page_items),
            )
            emb.set_footer(text=f"Page {page}/{total}")
            msg = await ctx.send(embed=emb)

            if total == 1:
                break
            for r in ("◀️", "▶️", "❌"):
                await msg.add_reaction(r)
            try:
                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in ("◀️", "▶️", "❌")
                reaction, _ = await self.client.wait_for("reaction_add", timeout=25, check=check)
            except asyncio.TimeoutError:
                break

            if str(reaction.emoji) == "◀️":
                page = max(1, page - 1)
            elif str(reaction.emoji) == "▶️":
                page = min(total, page + 1)
            else:  # ❌
                with contextlib.suppress(Exception):
                    await msg.delete()
                break
            with contextlib.suppress(Exception):
                await msg.delete()

    @commands.command(help="Live track by callsign (compact). Example: live AAL7")
    async def live(self, ctx, *, code: Optional[str] = None):
        if not code:
            return await ctx.send("Usage: `live <CALLSIGN>`  e.g., `live AAL7`")
        callsign = _callsign_norm(code)
        async with aiohttp.ClientSession() as s:
            try:
                data = await self.api.states_all(s)
            except Exception as e:
                return await ctx.send(f"OpenSky error: {e}")
        states = data.get("states") or []
        st = next((x for x in states if _callsign_norm((x[1] or "").replace(" ", "")) == callsign.replace(" ", "")), None)
        if not st:
            return await ctx.send("No live result for that callsign.")
        emb = discord.Embed(title=f"Live: {callsign}", description=_mk_state_line(st), color=0x00bcd4)
        await ctx.send(embed=emb)

    @commands.command(help="Arrivals for ICAO airport (UTC). Example: arrivals KJFK 2025-11-05")
    async def arrivals(self, ctx, code: Optional[str] = None, when: Optional[str] = None):
        if not code or not when:
            return await ctx.send("Usage: `arrivals <ICAO> <YYYY-MM-DD>`  e.g., `arrivals KJFK 2025-11-05`")
        try:
            d = _parse_date_str(when)
        except ValueError:
            return await ctx.send("Date must be YYYY-MM-DD.")
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = int((datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp())

        async with aiohttp.ClientSession() as s:
            try:
                flights = await self.api.flights_arrival(s, code, begin, end)
            except Exception as e:
                return await ctx.send(f"OpenSky error: {e}")

        if not flights:
            return await ctx.send("No results.")
        if isinstance(flights, dict):
            return await ctx.send(f"Unexpected response for arrivals: {flights}")

        page = 1
        while True:
            page_items, total = _paginate(flights, page, 8)
            title = f"Arrivals for {code.upper()} on {d.isoformat()} (UTC)"
            emb = discord.Embed(title=title, color=0x2f855a,
                                description="\n\n".join(_mk_flight_line(f) for f in page_items))
            emb.set_footer(text=f"Page {page}/{total}")
            msg = await ctx.send(embed=emb)

            if total == 1:
                break
            for r in ("◀️", "▶️", "❌"):
                await msg.add_reaction(r)
            try:
                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in ("◀️", "▶️", "❌")
                reaction, _ = await self.client.wait_for("reaction_add", timeout=25, check=check)
            except asyncio.TimeoutError:
                break

            if str(reaction.emoji) == "◀️":
                page = max(1, page - 1)
            elif str(reaction.emoji) == "▶️":
                page = min(total, page + 1)
            else:
                with contextlib.suppress(Exception):
                    await msg.delete()
                break
            with contextlib.suppress(Exception):
                await msg.delete()

    @commands.command(help="Departures for ICAO airport (UTC). Example: departures KLAX 2025-11-05")
    async def departures(self, ctx, code: Optional[str] = None, when: Optional[str] = None):
        if not code or not when:
            return await ctx.send("Usage: `departures <ICAO> <YYYY-MM-DD>`  e.g., `departures KLAX 2025-11-05`")
        try:
            d = _parse_date_str(when)
        except ValueError:
            return await ctx.send("Date must be YYYY-MM-DD.")
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = int((datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp())

        async with aiohttp.ClientSession() as s:
            try:
                flights = await self.api.flights_departure(s, code, begin, end)
            except Exception as e:
                return await ctx.send(f"OpenSky error: {e}")

        if not flights:
            return await ctx.send("No results.")
        if isinstance(flights, dict):
            return await ctx.send(f"Unexpected response for departures: {flights}")

        page = 1
        while True:
            page_items, total = _paginate(flights, page, 8)
            title = f"Departures for {code.upper()} on {d.isoformat()} (UTC)"
            emb = discord.Embed(title=title, color=0x2f855a,
                                description="\n\n".join(_mk_flight_line(f) for f in page_items))
            emb.set_footer(text=f"Page {page}/{total}")
            msg = await ctx.send(embed=emb)

            if total == 1:
                break
            for r in ("◀️", "▶️", "❌"):
                await msg.add_reaction(r)
            try:
                def check(reaction, user):
                    return user == ctx.author and reaction.message.id == msg.id and str(reaction.emoji) in ("◀️", "▶️", "❌")
                reaction, _ = await self.client.wait_for("reaction_add", timeout=25, check=check)
            except asyncio.TimeoutError:
                break

            if str(reaction.emoji) == "◀️":
                page = max(1, page - 1)
            elif str(reaction.emoji) == "▶️":
                page = min(total, page + 1)
            else:
                with contextlib.suppress(Exception):
                    await msg.delete()
                break
            with contextlib.suppress(Exception):
                await msg.delete()

    @commands.command(
        help=(
            "Flights for an aircraft hex (ICAO24) on a UTC date.\n"
            "Examples:\n  tail a1b2c3 2025-11-04\n  tail abc123 2025-11-05"
        )
    )
    async def tail(self, ctx, icao24: Optional[str] = None, when: Optional[str] = None):
        if not icao24 or not when:
            return await ctx.send("Usage: `tail <ICAO24> <YYYY-MM-DD>`  e.g., `tail a1b2c3 2025-11-04`")
        icao24 = icao24.lower()
        try:
            d = _parse_date_str(when)
        except ValueError:
            return await ctx.send("Date must be YYYY-MM-DD.")
        begin = int(datetime(d.year, d.month, d.day, tzinfo=timezone.utc).timestamp())
        end = int((datetime(d.year, d.month, d.day, tzinfo=timezone.utc) + timedelta(days=1)).timestamp())

        async with aiohttp.ClientSession() as s:
            try:
                flights = await self.api.flights_aircraft(s, icao24, begin, end)
            except Exception as e:
                return await ctx.send(f"OpenSky error: {e}")

        if isinstance(flights, dict):
            return await ctx.send(f"Unexpected response for tail: {flights}")
        if not flights:
            return await ctx.send("No results.")

        page_items, total = _paginate(flights, 1, 8)
        emb = discord.Embed(
            title=f"Flights for {icao24} on {d.isoformat()} (UTC)",
            color=0x607d8b,
            description="\n\n".join(_mk_flight_line(f) for f in page_items),
        )
        emb.set_footer(text=f"Page 1/{total}")
        await ctx.send(embed=emb)

    @commands.command(help="Diagnostics for OpenSky connectivity and auth mode. Example: osdiag")
    async def osdiag(self, ctx):
        mode = "auth" if self.auth.has_creds else "anon"
        async with aiohttp.ClientSession() as s:
            try:
                data = await self.api.states_all(s)
                count = len(data.get("states") or [])
                await ctx.send(f"OpenSky OK. Mode={mode}. States returned: {count}")
            except Exception as e:
                await ctx.send(f"OpenSky error: {e}")

async def setup(client):
    await client.add_cog(Flight(client))
