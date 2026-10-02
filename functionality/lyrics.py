# functionality/lyrics.py
"""Lyrics lookup via LRCLIB (https://lrclib.net) — free, no API key."""
import re
from difflib import SequenceMatcher
from typing import Optional

import aiohttp

API = "https://lrclib.net/api"
HEADERS = {"User-Agent": "Clarence Discord Bot (https://github.com/H-Bombmxpwr/Clarence)"}

_JUNK = re.compile(
    r"[\(\[](?:official|lyrics?|audio|video|visuali[sz]er|hd|hq|4k|remaster(?:ed)?|explicit|clean|live|mv|m/v)[^\)\]]*[\)\]]"
    r"|official (?:music )?video|official audio|lyric video|music video|\bft\.?\b.*$|\bfeat\.?\b.*$",
    re.IGNORECASE,
)


def clean_title(text: str) -> str:
    text = _JUNK.sub("", text)
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip(" -|•")


def _similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


async def fetch_lyrics(session: aiohttp.ClientSession, query: Optional[str] = None, *, title: Optional[str] = None,
                       artist: Optional[str] = None, duration_s: Optional[int] = None) -> Optional[dict]:
    """
    Find lyrics. Pass either a free-text `query` ("artist - song" or "song by artist" work best),
    or a `title`/`artist` (and optionally the track length) from a playing track.
    Returns {"title", "artist", "album", "lyrics", "instrumental"} or None.
    """
    timeout = aiohttp.ClientTimeout(total=15)

    if title:
        title = clean_title(title)
        # YouTube titles are often "Artist - Song"; prefer that over the uploader name
        if " - " in title:
            artist, title = [p.strip() for p in title.split(" - ", 1)]
        if artist:
            artist = re.sub(r"\s*-\s*Topic$|VEVO$", "", artist).strip()
            params = {"track_name": title, "artist_name": artist}
            if duration_s:
                params["duration"] = duration_s
            async with session.get(f"{API}/get", params=params, headers=HEADERS, timeout=timeout) as r:
                if r.status == 200:
                    data = await r.json()
                    if data.get("plainLyrics") or data.get("instrumental"):
                        return _shape(data)
        query = f"{artist or ''} {title}".strip()

    if not query:
        return None
    query = clean_title(query)
    search_q = re.sub(r"\s+by\s+", " ", query, flags=re.IGNORECASE).replace(" - ", " ")

    async with session.get(f"{API}/search", params={"q": search_q}, headers=HEADERS, timeout=timeout) as r:
        if r.status != 200:
            return None
        results = await r.json()

    results = [x for x in results if x.get("plainLyrics") or x.get("instrumental")]
    if not results:
        return None

    def score(x: dict) -> float:
        s = _similar(f"{x['artistName']} {x['trackName']}", search_q)
        if duration_s and x.get("duration"):
            s += 0.3 if abs(x["duration"] - duration_s) <= 3 else 0
        return s

    return _shape(max(results, key=score))


def _shape(data: dict) -> dict:
    return {
        "title": data.get("trackName") or data.get("name"),
        "artist": data.get("artistName"),
        "album": data.get("albumName"),
        "lyrics": (data.get("plainLyrics") or "").strip(),
        "instrumental": bool(data.get("instrumental")),
    }
