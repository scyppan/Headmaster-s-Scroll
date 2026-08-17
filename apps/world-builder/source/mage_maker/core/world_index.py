"""Disposable, compact indexes for the World Builder canonical JSON file.

The index is deliberately a derived read model. ``world.json`` remains the
only authority and deleting this file is always safe. Stored byte ranges make
it possible to read one top-level record without decoding the complete world.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


INDEX_FORMAT_VERSION = 3
INDEXED_COLLECTIONS = (
    "people",
    "locations",
    "organizations",
    "events",
    "items",
    "books",
    "book_readings",
    "maps",
    "board_groups",
    "named_creatures",
)

PEOPLE_LIST_FIELDS = (
    "record_id",
    "displayed_name",
    "birth_year",
    "birth_month",
    "birth_day",
    "deceased",
    "death_year",
    "death_month",
    "death_day",
    "canon",
    "player_character",
    "non_magical",
    "unfinished",
    "mage_group_id",
    "school",
    "biological_mother_id",
    "biological_father_id",
    "biological_mother_status",
    "biological_father_status",
    "can_give_birth",
    "does_not_have_children",
    "famous_person",
    "mate_ids",
    "spouse_relationships",
    "blood_status",
    "developmental_environment",
    "parental_values",
    "created_at",
)


def source_fingerprint(path: Path) -> dict[str, int]:
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def _record_id(record: dict) -> str:
    return str(
        record.get("record_id")
        or record.get("event_id")
        or record.get("reading_id")
        or ""
    ).strip()


def _name_details_text(value) -> str:
    entries = value.get("entries", []) if isinstance(value, dict) else []
    return " ".join(
        " ".join(
            str(entry.get(field, "") or "")
            for field in ("name_type", "name_entry", "date", "note")
        )
        for entry in entries
        if isinstance(entry, dict)
    )


def people_list_summary(person: dict) -> dict:
    from mage_maker.sections.development.characteristics import (
        initial_values_are_complete,
    )

    summary = {field: person.get(field) for field in PEOPLE_LIST_FIELDS}
    summary["_search_text"] = " ".join(
        str(value or "")
        for value in (
            person.get("displayed_name"),
            _name_details_text(person.get("name_details")),
            person.get("school"),
            person.get("birth_year"),
            person.get("death_year"),
        )
    ).casefold()
    # Computing this once prevents every sidebar refresh from walking every
    # multi-year development plan.
    summary["_has_initial_values"] = initial_values_are_complete(person)
    return summary


def record_summary(collection: str, record: dict) -> dict:
    """Return the deliberately small search/list representation of a record."""
    if collection == "people":
        return people_list_summary(record)
    field_names = {
        "locations": ("record_id", "name", "parent_location_id", "has_floors"),
        "organizations": (
            "record_id", "name", "organization_type", "parent_organization_id",
            "location_id", "is_faction",
        ),
        "events": ("event_id", "record_id", "title", "event_type", "date", "time"),
        "items": ("record_id", "name", "category", "item_type"),
        "books": ("record_id", "title", "author_name", "category"),
        "book_readings": ("reading_id", "record_id", "person_id", "book_id", "date"),
        "maps": ("record_id", "name", "location_id", "floor_id"),
        "board_groups": ("record_id", "name", "location_id"),
        "named_creatures": ("record_id", "name", "species_id", "location_id"),
    }.get(collection, ("record_id", "name"))
    summary = {field: record.get(field) for field in field_names if field in record}
    summary.setdefault("record_id", _record_id(record))
    summary["_search_text"] = " ".join(
        str(value or "") for key, value in summary.items() if not key.startswith("_")
    ).casefold()
    return summary


def _linked_ids(record: dict, singular: str, plural: str) -> set[str]:
    values = set()
    singular_value = str(record.get(singular, "") or "").strip()
    if singular_value:
        values.add(singular_value)
    raw_values = record.get(plural, [])
    if isinstance(raw_values, list):
        values.update(str(value or "").strip() for value in raw_values)
    values.discard("")
    return values


class WorldIndexCache:
    """Load and atomically replace the compact World Builder read index."""

    def __init__(self, source_path: Path, cache_path: Path | None = None):
        self.source_path = Path(source_path)
        project_root = self.source_path.parent.parent
        self.cache_path = Path(
            cache_path
            or project_root / "runtime" / "world-builder" / "index.json"
        )
        self.payload: dict = {}

    def is_current(self) -> bool:
        return bool(
            self.payload
            and self.payload.get("format_version") == INDEX_FORMAT_VERSION
            and self.payload.get("source") == source_fingerprint(self.source_path)
        )

    def load(self) -> bool:
        try:
            with self.cache_path.open("r", encoding="utf-8") as stream:
                payload = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError):
            self.payload = {}
            return False
        if not isinstance(payload, dict):
            self.payload = {}
            return False
        self.payload = payload
        return self.is_current()

    def build(self, data: dict, record_locations: dict | None = None) -> dict:
        summaries = {
            collection: [
                record_summary(collection, record)
                for record in data.get(collection, []) or []
                if isinstance(record, dict)
            ]
            for collection in INDEXED_COLLECTIONS
        }
        ids: dict[str, dict[str, int]] = {}
        for collection in INDEXED_COLLECTIONS:
            ids[collection] = {
                record_id: index
                for index, record in enumerate(data.get(collection, []) or [])
                if isinstance(record, dict)
                and (record_id := _record_id(record))
            }

        event_links = {
            "people": defaultdict(list),
            "locations": defaultdict(list),
            "organizations": defaultdict(list),
            "items": defaultdict(list),
            "types": defaultdict(list),
            "dates": defaultdict(list),
        }
        for event in data.get("events", []) or []:
            if not isinstance(event, dict):
                continue
            event_id = _record_id(event)
            if not event_id:
                continue
            for person_id in _linked_ids(event, "person_id", "person_ids"):
                event_links["people"][person_id].append(event_id)
            for location_id in _linked_ids(event, "location_id", "location_ids"):
                event_links["locations"][location_id].append(event_id)
            for organization_id in _linked_ids(
                event, "organization_id", "organization_ids"
            ):
                event_links["organizations"][organization_id].append(event_id)
            for item_id in _linked_ids(event, "item_id", "item_ids"):
                event_links["items"][item_id].append(event_id)
            event_type = str(event.get("event_type", "") or "").strip()
            event_date = str(event.get("date", "") or "").strip()
            if event_type:
                event_links["types"][event_type].append(event_id)
            if event_date:
                event_links["dates"][event_date].append(event_id)

        location_children = defaultdict(list)
        for location in data.get("locations", []) or []:
            if not isinstance(location, dict):
                continue
            record_id = _record_id(location)
            parent_id = str(location.get("parent_location_id", "") or "").strip()
            if record_id:
                location_children[parent_id].append(record_id)

        organization_children = defaultdict(list)
        for organization in data.get("organizations", []) or []:
            if not isinstance(organization, dict):
                continue
            record_id = _record_id(organization)
            parent_id = str(
                organization.get("parent_organization_id", "") or ""
            ).strip()
            if record_id:
                organization_children[parent_id].append(record_id)

        metadata = data.get("_headmasters_scroll", {})
        database_metadata = data.get("_database", {})
        self.payload = {
            "format_version": INDEX_FORMAT_VERSION,
            "built_at": datetime.now(timezone.utc).isoformat(),
            "source": source_fingerprint(self.source_path),
            "revision_id": (
                metadata.get("revision_id", "")
                if isinstance(metadata, dict)
                else ""
            ),
            "schema_version": (
                database_metadata.get("schema_version")
                if isinstance(database_metadata, dict)
                else None
            ),
            # Settings are small but are needed by the People list before the
            # editable canonical document finishes loading.
            "application_settings": (
                data.get("_application_settings", {})
                if isinstance(data.get("_application_settings"), dict)
                else {}
            ),
            "counts": {
                name: len(data.get(name, []) or [])
                for name in INDEXED_COLLECTIONS
            },
            "summaries": summaries,
            "ids": ids,
            "record_locations": record_locations or {},
            "links": {
                "events": {
                    name: dict(values) for name, values in event_links.items()
                },
                "location_children": dict(location_children),
                "organization_children": dict(organization_children),
            },
        }
        return self.payload

    def write(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.cache_path.with_name(
            f".{self.cache_path.name}.{os.getpid()}.{uuid4().hex}.tmp"
        )
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(
                    self.payload,
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

    def people_summaries(self) -> list[dict]:
        values = self.payload.get("summaries", {}).get("people", [])
        return [dict(value) for value in values if isinstance(value, dict)]

    def summaries(self, collection: str) -> list[dict]:
        values = self.payload.get("summaries", {}).get(
            str(collection or ""),
            [],
        )
        return [dict(value) for value in values if isinstance(value, dict)]

    def linked_event_ids(self, relationship: str, record_id: str) -> list[str]:
        values = (
            self.payload.get("links", {})
            .get("events", {})
            .get(str(relationship or ""), {})
            .get(str(record_id or ""), [])
        )
        return [str(value) for value in values]


def scan_record_locations(
    path: Path,
    record_ids_by_collection: dict[str, list[str]] | None = None,
) -> dict[str, dict[str, list[int]]]:
    """Return byte ranges for object members of top-level collection arrays."""

    raw = Path(path).read_bytes()
    length = len(raw)

    def whitespace(position: int) -> int:
        while position < length and raw[position] in b" \t\r\n":
            position += 1
        return position

    def string_end(position: int) -> int:
        position += 1
        escaped = False
        while position < length:
            value = raw[position]
            if escaped:
                escaped = False
            elif value == 92:
                escaped = True
            elif value == 34:
                return position + 1
            position += 1
        raise ValueError("Unterminated JSON string while building World Builder index")

    def value_end(position: int) -> int:
        position = whitespace(position)
        if position >= length:
            raise ValueError("Unexpected end of world.json")
        first = raw[position]
        if first == 34:
            return string_end(position)
        if first in (123, 91):
            stack = [125 if first == 123 else 93]
            position += 1
            in_string = False
            escaped = False
            while position < length:
                value = raw[position]
                if in_string:
                    if escaped:
                        escaped = False
                    elif value == 92:
                        escaped = True
                    elif value == 34:
                        in_string = False
                elif value == 34:
                    in_string = True
                elif value == 123:
                    stack.append(125)
                elif value == 91:
                    stack.append(93)
                elif stack and value == stack[-1]:
                    stack.pop()
                    if not stack:
                        return position + 1
                position += 1
            raise ValueError("Unterminated JSON value while building World Builder index")
        while position < length and raw[position] not in b",]}":
            position += 1
        return position

    locations: dict[str, dict[str, list[int]]] = {}
    position = whitespace(0)
    if position >= length or raw[position] != 123:
        raise ValueError("world.json root must be an object")
    position += 1
    while True:
        position = whitespace(position)
        if position >= length or raw[position] == 125:
            break
        key_start = position
        key_end = string_end(key_start)
        key = json.loads(raw[key_start:key_end].decode("utf-8"))
        position = whitespace(key_end)
        if raw[position] != 58:
            raise ValueError("Invalid world.json object member")
        position = whitespace(position + 1)
        if key in INDEXED_COLLECTIONS and raw[position] == 91:
            collection_locations: dict[str, list[int]] = {}
            known_ids = (
                record_ids_by_collection.get(key, [])
                if isinstance(record_ids_by_collection, dict)
                else []
            )
            record_index = 0
            position += 1
            while True:
                position = whitespace(position)
                if raw[position] == 93:
                    position += 1
                    break
                start = position
                record_id = (
                    str(known_ids[record_index] or "").strip()
                    if record_index < len(known_ids)
                    else ""
                )
                end = None
                if record_id and raw[start] == 123:
                    # Canonical files are written with a two-space indent, so
                    # a top-level collection record ends at a four-space
                    # closing brace. ``bytes.find`` performs this large scan
                    # in native code instead of walking tens of megabytes one
                    # Python byte at a time. Nested objects close at six or
                    # more spaces, and newlines inside strings are escaped.
                    closing = raw.find(b"\n    }", start)
                    if closing >= 0:
                        proposed_end = closing + len(b"\n    }")
                        following = whitespace(proposed_end)
                        if (
                            following < length
                            and raw[following] in (44, 93)
                        ):
                            end = proposed_end
                if end is None:
                    end = value_end(start)
                if not record_id:
                    try:
                        record = json.loads(raw[start:end].decode("utf-8"))
                    except (UnicodeError, json.JSONDecodeError):
                        record = None
                    if isinstance(record, dict):
                        record_id = _record_id(record)
                if record_id:
                    collection_locations[record_id] = [start, end - start]
                record_index += 1
                position = whitespace(end)
                if raw[position] == 44:
                    position += 1
                    continue
                if raw[position] == 93:
                    position += 1
                    break
                raise ValueError("Invalid collection array in world.json")
            locations[key] = collection_locations
        else:
            position = value_end(position)
        position = whitespace(position)
        if position < length and raw[position] == 44:
            position += 1
            continue
        if position < length and raw[position] == 125:
            break
    return locations


def read_indexed_record(
    source_path: Path,
    index_payload: dict,
    collection: str,
    record_id: str,
) -> dict | None:
    location = (
        index_payload.get("record_locations", {})
        .get(str(collection or ""), {})
        .get(str(record_id or ""))
    )
    if not isinstance(location, list) or len(location) != 2:
        return None
    offset, size = (int(location[0]), int(location[1]))
    with Path(source_path).open("rb") as stream:
        stream.seek(offset)
        raw = stream.read(size)
    value = json.loads(raw.decode("utf-8"))
    return value if isinstance(value, dict) else None
