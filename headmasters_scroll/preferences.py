from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .manifests import APP_ID
from .paths import PREFERENCES_DIRECTORY


class Preferences:
    def __init__(self, app_id: str, directory: Path = PREFERENCES_DIRECTORY):
        if not APP_ID.fullmatch(app_id):
            raise ValueError("Invalid app id")
        self.path = directory / f"{app_id}.json"

    def load(self) -> dict[str, Any]:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def save(self, value: dict[str, Any]) -> None:
        if not isinstance(value, dict):
            raise TypeError("Preferences must be an object")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(f".json.{os.getpid()}.tmp")
        try:
            temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
            os.replace(temporary, self.path)
        finally:
            temporary.unlink(missing_ok=True)

