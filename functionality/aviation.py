# functionality/aviation.py
"""
Aviation data clients used by cogs/flight.py.

Free, no key:
  adsb.lol          live ADS-B positions        https://api.adsb.lol
  adsbdb            callsign → route, aircraft  https://www.adsbdb.com
  aviationweather   METAR / TAF                 https://aviationweather.gov/data/api/
  OurAirports       airport database (CSV)      https://ourairports.com/data/
Free tier with key (AERODATABOX_KEY, via RapidAPI):
  AeroDataBox       schedules, status, FIDS     https://aerodatabox.com
"""
import asyncio
import csv
import io
import math
import os
import re
import time
from dataclasses import dataclass
from typing import Any, Optional

import aiohttp

from functionality.store import data_path

ADSBLOL = "https://api.adsb.lol/v2"
ADSBDB = "https://api.adsbdb.com/v0"
AWC = "https://aviationweather.gov/api/data"
AERODATABOX = "https://aerodatabox.p.rapidapi.com"
AIRPORTS_CSV = "https://davidmegginson.github.io/ourairports-data/airports.csv"
AIRPORTS_MAX_AGE = 30 * 86400
HEADERS = {"User-Agent": "Clarence Discord Bot (https://github.com/H-Bombmxpwr/Clarence)"}

FLIGHT_NUMBER_RE = re.compile(r"^([A-Z]{3}|[A-Z0-9]{2})\s*(\d{1,4}[A-Z]?)$")
HEX_RE = re.compile(r"^[0-9A-F]{6}$")
REG_RE = re.compile(r"^(N\d{1,5}[A-Z]{0,2}|[A-Z0-9]{1,2}-[A-Z0-9]{2,5}|[A-Z]{1,2}\d{3,5}|[A-Z]-[A-Z]{4})$")


class ApiError(Exception):
    pass


class NoApiKey(ApiError):
    pass


# ---------------------------------------------------------------------------- HTTP with small TTL cache

_cache: dict[str, tuple[float, Any]] = {}


async def get_json(session: aiohttp.ClientSession, url: str, *, params: dict = None, headers: dict = None,
                   ttl: float = 30, allow_404: bool = True) -> Any:
    key = url + "?" + "&".join(f"{k}={v}" for k, v in sorted((params or {}).items()))
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    async with session.get(url, params=params, headers={**HEADERS, **(headers or {})},
                           timeout=aiohttp.ClientTimeout(total=20)) as r:
        if r.status == 404 and allow_404:
            data = None
        elif r.status == 204:
            data = None
        elif r.status == 429:
            raise ApiError("Rate limited by the data provider — try again in a minute.")
        elif r.status in (401, 403):
            raise ApiError(f"The data provider rejected the request (HTTP {r.status}). Check the API key.")
        elif r.status >= 400:
            raise ApiError(f"Data provider error (HTTP {r.status}).")
        else:
            data = await r.json(content_type=None)
    if len(_cache) > 500:
        _cache.clear()
    _cache[key] = (time.monotonic(), data)
    return data


# ---------------------------------------------------------------------------- helpers

def haversine_nm(lat1, lon1, lat2, lon2) -> float:
    r = 3440.065  # Earth radius in nautical miles
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def compass(deg: Optional[float]) -> str:
    if deg is None:
        return "—"
    dirs = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return dirs[round(deg / 22.5) % 16]


def flag(country_code: Optional[str]) -> str:
    if not country_code or len(country_code) != 2:
        return ""
    return "".join(chr(0x1F1E6 + ord(c) - ord("A")) for c in country_code.upper())


# ---------------------------------------------------------------------------- airports (OurAirports)

@dataclass
class Airport:
    ident: str
    type: str
    name: str
    lat: float
    lon: float
    elevation_ft: Optional[int]
    country: str
    region: str
    city: str
    scheduled: bool
    icao: str
    iata: str
    wikipedia: str
    home: str

    @property
    def code(self) -> str:
        return self.icao or self.ident

    @property
    def label(self) -> str:
        codes = "/".join(c for c in (self.iata, self.code) if c)
        return f"{codes} — {self.name}" + (f", {self.city}" if self.city else "")


class AirportDB:
    def __init__(self):
        self.airports: list[Airport] = []
        self.by_code: dict[str, Airport] = {}
        self._lock = asyncio.Lock()

    async def ensure_loaded(self, session: aiohttp.ClientSession):
        if self.airports:
            return
        async with self._lock:
            if self.airports:
                return
            path = data_path("airports.csv")
            fresh = os.path.exists(path) and time.time() - os.path.getmtime(path) < AIRPORTS_MAX_AGE
            if not fresh:
                try:
                    async with session.get(AIRPORTS_CSV, timeout=aiohttp.ClientTimeout(total=60)) as r:
                        r.raise_for_status()
                        text = await r.text()
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(text)
                except Exception:
                    if not os.path.exists(path):
                        raise ApiError("Couldn't download the airport database.")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            await asyncio.to_thread(self._parse, text)

    def _parse(self, text: str):
        airports = []
        for row in csv.DictReader(io.StringIO(text)):
            if row["type"] not in ("large_airport", "medium_airport", "small_airport", "seaplane_base"):
                continue
            try:
                ap = Airport(
                    ident=row["ident"], type=row["type"], name=row["name"],
                    lat=float(row["latitude_deg"]), lon=float(row["longitude_deg"]),
                    elevation_ft=int(row["elevation_ft"]) if row["elevation_ft"] else None,
                    country=row["iso_country"], region=row["iso_region"], city=row["municipality"],
                    scheduled=row["scheduled_service"] == "yes",
                    icao=row.get("icao_code") or (row["gps_code"] if len(row["gps_code"] or "") == 4 else ""),
                    iata=row["iata_code"], wikipedia=row["wikipedia_link"], home=row["home_link"],
                )
            except ValueError:
                continue
            airports.append(ap)
        rank = {"large_airport": 0, "medium_airport": 1, "small_airport": 2, "seaplane_base": 3}
        airports.sort(key=lambda a: (rank[a.type], not a.scheduled))
        by_code = {}
        for ap in reversed(airports):  # bigger airports win code collisions
            for code in (ap.ident, ap.icao, ap.iata):
                if code:
                    by_code[code.upper()] = ap
        self.airports, self.by_code = airports, by_code

    def lookup(self, query: str) -> Optional[Airport]:
        q = query.strip().upper()
        if q in self.by_code:
            return self.by_code[q]
        # autocomplete values look like "JFK/KJFK — John F Kennedy..."
        head = q.split(" ")[0].split("/")
        for code in head:
            if code in self.by_code:
                return self.by_code[code]
        results = self.search(query, 1)
        return results[0] if results else None

    def search(self, query: str, limit: int = 25) -> list[Airport]:
        q = query.strip().lower()
        if not q:
            return [a for a in self.airports if a.type == "large_airport"][:limit]
        # exact code matches first, then name/city matches in airport-size order (self.airports is size-sorted)
        exact, matches = [], []
        for a in self.airports:
            name, city = a.name.lower(), a.city.lower()
            if q in (a.iata.lower(), a.icao.lower(), a.ident.lower()):
                exact.append(a)
            elif name.startswith(q) or city.startswith(q) or (len(q) >= 3 and (q in name or q in city)):
                matches.append(a)
            if len(matches) >= limit * 4:
                break
        return (exact + matches)[:limit]

    def nearest(self, lat: float, lon: float, limit: int = 5) -> list[tuple[Airport, float]]:
        pool = [a for a in self.airports if a.type in ("large_airport", "medium_airport")]
        dists = sorted(((a, haversine_nm(lat, lon, a.lat, a.lon)) for a in pool), key=lambda x: x[1])
        return dists[:limit]


airport_db = AirportDB()


# ---------------------------------------------------------------------------- live ADS-B (adsb.lol)

async def live_by_callsign(session, callsign: str) -> list[dict]:
    data = await get_json(session, f"{ADSBLOL}/callsign/{callsign.upper()}", ttl=10)
    return (data or {}).get("ac") or []


async def live_by_hex(session, hex_code: str) -> list[dict]:
    data = await get_json(session, f"{ADSBLOL}/hex/{hex_code.lower()}", ttl=10)
    return (data or {}).get("ac") or []


async def live_by_reg(session, reg: str) -> list[dict]:
    data = await get_json(session, f"{ADSBLOL}/reg/{reg.upper()}", ttl=10)
    return (data or {}).get("ac") or []


async def live_near(session, lat: float, lon: float, radius_nm: int) -> list[dict]:
    data = await get_json(session, f"{ADSBLOL}/point/{lat:.4f}/{lon:.4f}/{min(radius_nm, 250)}", ttl=15)
    return (data or {}).get("ac") or []


# ---------------------------------------------------------------------------- routes / aircraft (adsbdb)

async def route_for_callsign(session, callsign: str) -> Optional[dict]:
    data = await get_json(session, f"{ADSBDB}/callsign/{callsign.upper()}", ttl=3600)
    resp = (data or {}).get("response")
    return resp.get("flightroute") if isinstance(resp, dict) else None


async def aircraft_info(session, hex_or_reg: str) -> Optional[dict]:
    data = await get_json(session, f"{ADSBDB}/aircraft/{hex_or_reg.upper()}", ttl=86400)
    resp = (data or {}).get("response")
    return resp.get("aircraft") if isinstance(resp, dict) else None


async def airline_icao(session, iata: str) -> Optional[dict]:
    data = await get_json(session, f"{ADSBDB}/airline/{iata.upper()}", ttl=86400)
    resp = (data or {}).get("response")
    if isinstance(resp, list) and resp:
        # several airlines can share an IATA code; prefer the one that has both codes
        return next((a for a in resp if a.get("icao") and a.get("iata") == iata.upper()), resp[0])
    return None


async def normalize_flight(session, query: str) -> tuple[str, Optional[str]]:
    """
    Turn 'UA 1', 'UAL1', 'ual1' into (icao_callsign, iata_flight_number).
    Returns (query, None) unchanged if it doesn't look like a flight number.
    """
    q = query.upper().replace(" ", "")
    m = FLIGHT_NUMBER_RE.match(q)
    if not m:
        return q, None
    prefix, number = m.groups()
    if len(prefix) == 3:
        return q, None
    airline = await airline_icao(session, prefix)
    if airline and airline.get("icao"):
        return f"{airline['icao']}{number}", f"{prefix}{number}"
    return q, f"{prefix}{number}"


# ---------------------------------------------------------------------------- weather (aviationweather.gov)

async def metar(session, icao: str) -> Optional[dict]:
    data = await get_json(session, f"{AWC}/metar", params={"ids": icao.upper(), "format": "json"}, ttl=300)
    return data[0] if isinstance(data, list) and data else None


async def taf(session, icao: str) -> Optional[str]:
    async with session.get(f"{AWC}/taf", params={"ids": icao.upper(), "format": "raw"}, headers=HEADERS,
                           timeout=aiohttp.ClientTimeout(total=15)) as r:
        if r.status != 200:
            return None
        text = (await r.text()).strip()
    return text or None


# ---------------------------------------------------------------------------- schedules (AeroDataBox)

def aerodatabox_enabled() -> bool:
    return bool(os.getenv("AERODATABOX_KEY"))


async def _adb(session, path: str, params: dict = None, ttl: float = 120) -> Any:
    key = os.getenv("AERODATABOX_KEY")
    if not key:
        raise NoApiKey()
    headers = {"X-RapidAPI-Key": key, "X-RapidAPI-Host": "aerodatabox.p.rapidapi.com"}
    return await get_json(session, f"{AERODATABOX}{path}", params=params, headers=headers, ttl=ttl)


async def flight_status(session, number: str, date_local: Optional[str] = None) -> list[dict]:
    path = f"/flights/number/{number.replace(' ', '')}" + (f"/{date_local}" if date_local else "")
    data = await _adb(session, path, {"withAircraftImage": "true", "withLocation": "false"})
    return data if isinstance(data, list) else []


async def airport_board(session, icao: str, start_local: str, end_local: str, direction: str = "Both") -> dict:
    """FIDS for an airport between two local times (YYYY-MM-DDTHH:mm, max 12h apart)."""
    params = {"direction": direction, "withLeg": "true", "withCancelled": "true", "withCodeshared": "false",
              "withCargo": "false", "withPrivate": "false"}
    data = await _adb(session, f"/flights/airports/icao/{icao.upper()}/{start_local}/{end_local}", params)
    return data or {"departures": [], "arrivals": []}


async def airport_board_relative(session, icao: str, offset_minutes: int = -30, duration_minutes: int = 360,
                                 direction: str = "Both") -> dict:
    """FIDS for an airport relative to the airport's current local time (duration max 720)."""
    params = {"offsetMinutes": offset_minutes, "durationMinutes": min(duration_minutes, 720), "direction": direction,
              "withLeg": "true", "withCancelled": "true", "withCodeshared": "false", "withCargo": "false",
              "withPrivate": "false"}
    data = await _adb(session, f"/flights/airports/icao/{icao.upper()}", params)
    return data or {"departures": [], "arrivals": []}
