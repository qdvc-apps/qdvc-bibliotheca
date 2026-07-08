"""Application configuration, stored as YAML at an XDG config location."""

import os
from pathlib import Path

import yaml

from . import APP_NAME


def xdg_config_home() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base)
    return Path.home() / ".config"


def config_dir() -> Path:
    d = xdg_config_home() / "qdvc-bibliotheca"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    return config_dir() / "config.yml"


DEFAULTS = {
    "last_workspace": None,      # str path or None
    "recent_workspaces": [],     # list[str]
    "window": {"width": 1100, "height": 720},
}


class Config:
    """Thin wrapper over the config.yml file."""

    def __init__(self, data: dict | None = None):
        self._data = dict(DEFAULTS)
        if data:
            self._data.update(data)

    # --- persistence -----------------------------------------------------
    @classmethod
    def load(cls) -> "Config":
        p = config_path()
        if p.exists():
            try:
                with p.open("r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh) or {}
                return cls(data)
            except (OSError, yaml.YAMLError):
                pass
        return cls()

    def save(self) -> None:
        p = config_path()
        try:
            with p.open("w", encoding="utf-8") as fh:
                yaml.safe_dump(self._data, fh, sort_keys=True,
                               allow_unicode=True)
        except OSError:
            pass

    # --- accessors -------------------------------------------------------
    @property
    def last_workspace(self):
        return self._data.get("last_workspace")

    @last_workspace.setter
    def last_workspace(self, value):
        self._data["last_workspace"] = value

    @property
    def recent_workspaces(self) -> list:
        return self._data.setdefault("recent_workspaces", [])

    def push_recent(self, path: str, limit: int = 10) -> None:
        recents = self.recent_workspaces
        if path in recents:
            recents.remove(path)
        recents.insert(0, path)
        del recents[limit:]

    @property
    def window(self) -> dict:
        return self._data.setdefault("window", {"width": 1100, "height": 720})

    def get(self, key, default=None):
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
