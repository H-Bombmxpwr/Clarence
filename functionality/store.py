# functionality/store.py
"""Tiny JSON-file persistence used by the cogs."""
import json
import os
from pathlib import Path
from typing import Any, Callable

# Point DATA_DIR at a persistent volume (e.g. a Railway volume mounted at /data)
STORAGE_DIR = Path(os.getenv("DATA_DIR") or "storage")


def data_path(filename: str) -> str:
    """Path for a data file inside the persistent storage directory."""
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    return str(STORAGE_DIR / filename)


class JsonStore:
    """A JSON document kept in memory and written atomically on save()."""

    def __init__(self, filename: str, default: Callable[[], Any] = dict):
        self.path = STORAGE_DIR / filename
        self._default = default
        self.data = self._load()

    def _load(self) -> Any:
        try:
            return json.loads(self.path.read_text("utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return self._default()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, ensure_ascii=False), "utf-8")
        os.replace(tmp, self.path)

    def guild(self, guild_id: int) -> dict:
        """Return (creating if needed) the sub-dict for a guild."""
        return self.data.setdefault(str(guild_id), {})
