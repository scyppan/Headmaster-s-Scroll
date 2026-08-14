from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from headmasters_scroll.creatures import migrate_creature_database, validate_creature_database


def main() -> None:
    path = ROOT / "data" / "db.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    result = migrate_creature_database(document)
    validate_creature_database(document)
    now = datetime.now(timezone.utc)
    metadata = document.setdefault("_headmasters_scroll", {})
    metadata.update({
        "revision_id": str(uuid4()),
        "last_modified_at": now.isoformat().replace("+00:00", "Z"),
        "last_modified_by": "creature-encounter-migration",
    })
    backup_dir = ROOT / "data" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    backup = backup_dir / f"db.creature-migration.{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    shutil.copy2(path, backup)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        json.loads(temporary.read_text(encoding="utf-8"))
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print(json.dumps({**result, "backup": str(backup)}, indent=2))


if __name__ == "__main__":
    main()
