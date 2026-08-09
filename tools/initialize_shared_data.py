"""One-time, idempotent metadata and period-ID initialization."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from headmasters_scroll.paths import ALLOWED_DATA_FILES, DATA_DIRECTORY
from headmasters_scroll.validation import validate_document


def _stable_id(filename: str, kind: str, position: str, name: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"headmasters-scroll:{filename}:{kind}:{position}:{name}"))


def initialize_file(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    if path.name == "periods.json":
        for group_index, group in enumerate(data.get("period_groups", [])):
            if not group.get("record_id"):
                group["record_id"] = _stable_id(path.name, "group", str(group_index), str(group.get("name", "")))
                changed = True
            for period_index, period in enumerate(group.get("periods", [])):
                if not period.get("record_id"):
                    position = f"{group_index}/{period_index}"
                    period["record_id"] = _stable_id(path.name, "period", position, str(period.get("name", "")))
                    changed = True
    if not isinstance(data.get("_headmasters_scroll"), dict):
        data["_headmasters_scroll"] = {
            "revision_id": _stable_id(path.name, "initial-revision", "0", "canonical"),
            "last_modified_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_modified_by": "foundation-migration",
        }
        changed = True
    validate_document(path.name, data)
    if changed:
        temporary = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return changed


def main() -> None:
    for filename in sorted(ALLOWED_DATA_FILES):
        path = DATA_DIRECTORY / filename
        print(f"{filename}: {'initialized' if initialize_file(path) else 'already initialized'}")


if __name__ == "__main__":
    main()

