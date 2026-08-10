from __future__ import annotations

from typing import Any

from .errors import DataValidationError
from .board import validate_world_board


REQUIRED_COLLECTIONS = {
    "db.json": {"wand_woods", "wand_cores", "wands", "books", "spells"},
    "world.json": {"people", "locations", "organizations", "events"},
    "periods.json": {"period_groups"},
}


def _validate_record_list(records: Any, label: str) -> None:
    if not isinstance(records, list):
        raise DataValidationError(f"{label} must be a list")
    seen: set[str] = set()
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            raise DataValidationError(f"{label}[{index}] must be an object")
        record_id = record.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            raise DataValidationError(f"{label}[{index}] requires a record_id")
        if record_id in seen:
            raise DataValidationError(f"Duplicate record_id {record_id!r} in {label}")
        seen.add(record_id)


def validate_document(filename: str, data: Any) -> None:
    if filename not in REQUIRED_COLLECTIONS:
        raise DataValidationError(f"Unsupported shared file: {filename}")
    if not isinstance(data, dict):
        raise DataValidationError("The JSON root must be an object")
    metadata = data.get("_headmasters_scroll")
    if not isinstance(metadata, dict):
        raise DataValidationError("Missing _headmasters_scroll metadata")
    for key in ("revision_id", "last_modified_at", "last_modified_by"):
        if not isinstance(metadata.get(key), str) or not metadata[key]:
            raise DataValidationError(f"Invalid _headmasters_scroll.{key}")
    missing = REQUIRED_COLLECTIONS[filename] - data.keys()
    if missing:
        raise DataValidationError(f"Missing required collections: {sorted(missing)}")
    if filename in {"db.json", "world.json"}:
        if not isinstance(data.get("_database"), dict):
            raise DataValidationError("Missing _database metadata")
        for name, value in data.items():
            if not name.startswith("_") and isinstance(value, list):
                _validate_record_list(value, name)
        if filename == "world.json":
            try:
                validate_world_board(data)
            except (TypeError, ValueError) as error:
                raise DataValidationError(str(error)) from error
    else:
        if not isinstance(data.get("schema_version"), int):
            raise DataValidationError("periods.json requires an integer schema_version")
        groups = data["period_groups"]
        _validate_record_list(groups, "period_groups")
        for group in groups:
            _validate_record_list(group.get("periods"), f"period_groups[{group['record_id']}].periods")
