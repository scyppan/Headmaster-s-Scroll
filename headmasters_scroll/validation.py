from __future__ import annotations

from typing import Any

from .errors import DataValidationError
from .board import validate_world_board
from .campaigns import validate_campaigns
from .creatures import validate_creature_database
from .catalog import validate_catalog
from .region_interactions import validate_gathering_database


TEACHING_EVENT_TYPES = {
    "taught_spell": ("spells",),
    "taught_proficiency": ("proficiencies",),
    "taught_recipe": ("potions", "preparations", "foods_and_drinks"),
}
CREATURE_RELATIONSHIP_EVENT_TYPES = {
    "tamed_creature", "bonded_creature", "irked_creature"
}


def _validate_world_character_control_links(data: dict[str, Any]) -> None:
    named_creatures = data.get("named_creatures", []) or []
    _validate_record_list(named_creatures, "named_creatures")
    creature_ids = {str(item["record_id"]) for item in named_creatures}
    for index, creature in enumerate(named_creatures):
        species_id = str(
            creature.get("species_record_id")
            or creature.get("creature_species_id")
            or ""
        ).strip()
        if not str(creature.get("name", "") or "").strip() or not species_id:
            raise DataValidationError(
                f"named_creatures[{index}] requires a name and creature-species record ID"
            )
    for index, event in enumerate(data.get("events", []) or []):
        event_type = str(event.get("event_type", "") or "")
        if event_type in TEACHING_EVENT_TYPES:
            record_id = str(
                event.get("knowledge_record_id")
                or event.get("target_record_id")
                or ""
            ).strip()
            collection = str(event.get("knowledge_collection", "") or "").strip()
            if not record_id:
                raise DataValidationError(
                    f"events[{index}] {event_type} requires a stable taught-record ID"
                )
            if collection and collection not in TEACHING_EVENT_TYPES[event_type]:
                raise DataValidationError(
                    f"events[{index}] taught record uses the wrong collection"
                )
        if event_type in CREATURE_RELATIONSHIP_EVENT_TYPES:
            creature_id = str(event.get("named_creature_id", "") or "").strip()
            if not creature_id or creature_id not in creature_ids:
                raise DataValidationError(
                    f"events[{index}] references an unknown named creature"
                )


REQUIRED_COLLECTIONS = {
    "db.json": {"wand_woods", "wand_cores", "wands", "books", "spells"},
    "world.json": {"people", "locations", "organizations", "events"},
    "periods.json": {"period_groups"},
    "campaign.json": {"campaigns"},
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
                _validate_world_character_control_links(data)
            except (TypeError, ValueError) as error:
                raise DataValidationError(str(error)) from error
        else:
            try:
                validate_creature_database(data)
                validate_gathering_database(data)
                if "tag_catalog" in data:
                    validate_catalog(data)
            except (TypeError, ValueError) as error:
                raise DataValidationError(str(error)) from error
    elif filename == "periods.json":
        if not isinstance(data.get("schema_version"), int):
            raise DataValidationError("periods.json requires an integer schema_version")
        groups = data["period_groups"]
        _validate_record_list(groups, "period_groups")
        for group in groups:
            _validate_record_list(group.get("periods"), f"period_groups[{group['record_id']}].periods")
    else:
        if not isinstance(data.get("schema_version"), int):
            raise DataValidationError("campaign.json requires an integer schema_version")
        _validate_record_list(data["campaigns"], "campaigns")
        try:
            validate_campaigns(data)
        except (TypeError, ValueError) as error:
            raise DataValidationError(str(error)) from error
