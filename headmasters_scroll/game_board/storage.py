from __future__ import annotations

import json
import os
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ..locking import FileLock
from ..paths import RUNTIME_DIRECTORY


SCHEMA_VERSION = 1


class PrivateJsonStore:
    """Small, atomic JSON store for private runtime state."""

    def __init__(self, directory: Path):
        self.directory = Path(directory)

    def load(self, filename: str, default: dict[str, Any], validator: Callable[[dict], None]) -> dict[str, Any]:
        path = self.directory / filename
        if not path.exists():
            value = deepcopy(default)
            validator(value)
            return value
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        validator(value)
        return value

    def save(self, filename: str, value: dict[str, Any], validator: Callable[[dict], None]) -> None:
        validator(value)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / filename
        with FileLock(path):
            if path.exists():
                backup_dir = self.directory / "backups" / path.stem
                backup_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                shutil.copy2(path, backup_dir / f"{stamp}.json")
            temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
            try:
                with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                    json.dump(value, stream, ensure_ascii=False, indent=2)
                    stream.write("\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)


def _object(value: dict[str, Any]) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("Private JSON file has an unsupported schema")


def _contacts(value: dict[str, Any]) -> None:
    _object(value)
    if not isinstance(value.get("contacts"), list):
        raise ValueError("contacts.json requires a contacts list")
    ids: set[str] = set()
    for contact in value["contacts"]:
        if not isinstance(contact, dict) or not all(isinstance(contact.get(key), str) for key in ("id", "name", "email")):
            raise ValueError("Every contact requires string id, name, and email values")
        if contact["id"] in ids:
            raise ValueError("Contact IDs must be unique")
        ids.add(contact["id"])


def _settings(value: dict[str, Any]) -> None:
    _object(value)
    required = {
        "admin_host", "admin_port", "player_host", "player_port", "timezone",
        "wordpress_player_url", "allowed_origin", "public_api_base",
        "gmail_credentials_path", "gmail_sender", "admin_key",
    }
    if not required.issubset(value):
        raise ValueError("settings.json is missing required settings")
    if not isinstance(value["admin_port"], int) or not isinstance(value["player_port"], int):
        raise ValueError("Server ports must be integers")


def _active(value: dict[str, Any]) -> None:
    _object(value)
    session = value.get("session")
    if session is not None and not isinstance(session, dict):
        raise ValueError("active-session.json session must be an object or null")


def _summaries(value: dict[str, Any]) -> None:
    _object(value)
    if not isinstance(value.get("sessions"), list):
        raise ValueError("session-summaries.json requires a sessions list")


class GameBoardRepository:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or (RUNTIME_DIRECTORY / "session-host"))
        self.store = PrivateJsonStore(self.directory)

    def contacts(self) -> dict[str, Any]:
        return self.store.load("contacts.json", {"schema_version": 1, "contacts": []}, _contacts)

    def save_contacts(self, value: dict[str, Any]) -> None:
        self.store.save("contacts.json", value, _contacts)

    def settings(self) -> dict[str, Any]:
        from secrets import token_urlsafe

        default = {
            "schema_version": 1,
            "admin_host": "127.0.0.1",
            "admin_port": 8764,
            "player_host": "127.0.0.1",
            "player_port": 8765,
            "timezone": "America/Chicago",
            "wordpress_player_url": "",
            "allowed_origin": "",
            "public_api_base": "",
            "gmail_credentials_path": "credentials.json",
            "gmail_sender": "",
            "admin_key": token_urlsafe(32),
        }
        value = self.store.load("settings.json", default, _settings)
        if not (self.directory / "settings.json").exists():
            self.save_settings(value)
        return value

    def save_settings(self, value: dict[str, Any]) -> None:
        self.store.save("settings.json", value, _settings)

    def active(self) -> dict[str, Any]:
        return self.store.load("active-session.json", {"schema_version": 1, "session": None}, _active)

    def save_active(self, value: dict[str, Any]) -> None:
        self.store.save("active-session.json", value, _active)

    def summaries(self) -> dict[str, Any]:
        return self.store.load("session-summaries.json", {"schema_version": 1, "sessions": []}, _summaries)

    def save_summaries(self, value: dict[str, Any]) -> None:
        self.store.save("session-summaries.json", value, _summaries)

