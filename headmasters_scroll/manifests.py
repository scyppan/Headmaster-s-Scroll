from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from .errors import ManifestError
from .paths import APPS_DIRECTORY, PROJECT_ROOT


APP_ID = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


@dataclass(frozen=True)
class AppManifest:
    app_id: str
    name: str
    enabled: bool
    entry_command: tuple[str, ...]
    icon: Path | None
    directory: Path


def load_manifests(apps_directory: Path = APPS_DIRECTORY) -> list[AppManifest]:
    manifests: list[AppManifest] = []
    seen: set[str] = set()
    if not apps_directory.exists():
        return manifests
    for path in sorted(apps_directory.glob("*/app.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ManifestError(f"Cannot read {path}: {error}") from error
        app_id, name, enabled = raw.get("id"), raw.get("name"), raw.get("enabled")
        command = raw.get("entry_command", [])
        if not isinstance(app_id, str) or not APP_ID.fullmatch(app_id):
            raise ManifestError(f"Invalid app id in {path}")
        if app_id in seen:
            raise ManifestError(f"Duplicate app id: {app_id}")
        if not isinstance(name, str) or not name.strip() or not isinstance(enabled, bool):
            raise ManifestError(f"Invalid name or enabled state in {path}")
        if not isinstance(command, list) or not all(isinstance(token, str) and token for token in command):
            raise ManifestError(f"entry_command must be a list of strings in {path}")
        if enabled and not command:
            raise ManifestError(f"Enabled app {app_id} has no entry command")
        icon_value = raw.get("icon")
        icon = path.parent / icon_value if isinstance(icon_value, str) and icon_value else None
        if icon is not None and not icon.is_file():
            raise ManifestError(f"Missing icon for {app_id}: {icon}")
        if enabled:
            for token in command:
                if token.startswith("{root}/"):
                    resolved = PROJECT_ROOT / token.removeprefix("{root}/")
                    if not resolved.exists():
                        raise ManifestError(f"Missing entrypoint for {app_id}: {resolved}")
        seen.add(app_id)
        manifests.append(AppManifest(app_id, name.strip(), enabled, tuple(command), icon, path.parent))
    return manifests

