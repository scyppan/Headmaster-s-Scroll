from __future__ import annotations

import json
import os
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from headmasters_scroll.paths import RUNTIME_DIRECTORY, data_path


CATALOG_FORMAT_VERSION = 2


def source_fingerprint(path: Path) -> dict[str, int]:
    stat = Path(path).stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


class MapperCatalogCache:
    """Disposable warm-start cache containing only Mapper-owned collections."""

    def __init__(
        self,
        source_path: Path | None = None,
        cache_path: Path | None = None,
    ) -> None:
        self.source_path = Path(source_path or data_path("world.json"))
        self.cache_path = Path(
            cache_path
            or RUNTIME_DIRECTORY / "mapper" / "catalog-index.json"
        )

    def load(self) -> dict | None:
        try:
            with self.cache_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
            if not isinstance(payload, dict):
                return None
            if payload.get("format_version") != CATALOG_FORMAT_VERSION:
                return None
            if payload.get("source") != source_fingerprint(self.source_path):
                return None
            locations = payload.get("locations")
            maps = payload.get("maps")
            addresses = payload.get("addresses")
            if (
                not isinstance(locations, list)
                or not isinstance(maps, list)
                or not isinstance(addresses, list)
            ):
                return None
            return {
                "locations": deepcopy(locations),
                "maps": deepcopy(maps),
                "addresses": deepcopy(addresses),
                "revision_id": str(payload.get("revision_id", "") or ""),
            }
        except (OSError, UnicodeError, ValueError, json.JSONDecodeError):
            return None

    def write(self, document: dict) -> None:
        metadata = document.get("_headmasters_scroll", {})
        payload = {
            "format_version": CATALOG_FORMAT_VERSION,
            "source": source_fingerprint(self.source_path),
            "revision_id": (
                str(metadata.get("revision_id", "") or "")
                if isinstance(metadata, dict)
                else ""
            ),
            "locations": deepcopy(document.get("locations", []) or []),
            "maps": deepcopy(document.get("maps", []) or []),
            "addresses": deepcopy(document.get("addresses", []) or []),
        }
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_name(
            f".{self.cache_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    payload,
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.cache_path)
        finally:
            temporary.unlink(missing_ok=True)
