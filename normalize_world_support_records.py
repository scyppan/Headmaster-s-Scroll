"""Audit/apply indexed support-record normalization for World Builder people."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "world-builder" / "source"))

from headmasters_scroll.store import SharedJsonStore  # noqa: E402
from mage_maker.core.database import JsonDatabase  # noqa: E402
from mage_maker.core.reference_storage import (  # noqa: E402
    externalize_person_support_records,
)


def encoded_size(value: object) -> int:
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")))


def snapshot_support(world: dict) -> dict[str, tuple[list[dict], dict]]:
    tags = {
        item["record_id"]: item
        for item in world.get("person_tag_catalog", []) or []
        if isinstance(item, dict) and item.get("record_id")
    }
    imports = {
        item["record_id"]: item
        for item in world.get("legacy_person_imports", []) or []
        if isinstance(item, dict) and item.get("record_id")
    }
    result = {}
    for person in world.get("people", []) or []:
        if not isinstance(person, dict):
            continue
        if "tags" in person:
            person_tags = deepcopy(person.get("tags", []) or [])
        else:
            person_tags = []
            for tag_id in person.get("tag_ids", []) or []:
                tag = deepcopy(tags[tag_id])
                tag.pop("record_id", None)
                person_tags.append(tag)
        if "imported_fields" in person:
            imported_fields = deepcopy(person.get("imported_fields", {}) or {})
        else:
            imported = imports.get(person.get("legacy_import_id", ""), {})
            imported_fields = deepcopy(imported.get("fields", {}) or {})
        result[str(person.get("record_id", "") or "")] = (
            person_tags,
            imported_fields,
        )
    return result


def hydrated_support(world: dict) -> dict[str, tuple[list[dict], dict]]:
    tags = {
        item["record_id"]: item
        for item in world.get("person_tag_catalog", []) or []
    }
    imports = {
        item["record_id"]: item
        for item in world.get("legacy_person_imports", []) or []
    }
    result = {}
    for person in world.get("people", []) or []:
        person_tags = []
        for tag_id in person.get("tag_ids", []) or []:
            tag = deepcopy(tags[tag_id])
            tag.pop("record_id", None)
            person_tags.append(tag)
        imported = imports.get(person.get("legacy_import_id", ""), {})
        result[str(person.get("record_id", "") or "")] = (
            person_tags,
            deepcopy(imported.get("fields", {}) or {}),
        )
    return result


def build(source: dict) -> dict:
    migrated = deepcopy(source)
    externalize_person_support_records(migrated)
    metadata = migrated.setdefault("_database", {})
    metadata["schema_version"] = 38
    metadata["database_version"] = "0.38.0"
    return migrated


def verify(source: dict, migrated: dict) -> None:
    if len(source.get("people", [])) != len(migrated.get("people", [])):
        raise ValueError("Person count changed")
    if snapshot_support(source) != hydrated_support(migrated):
        raise ValueError("Hydrated person tags or legacy imports changed")
    if any(
        "tags" in person or "imported_fields" in person
        for person in migrated.get("people", []) or []
    ):
        raise ValueError("An embedded person support field remains")
    JsonDatabase(ROOT / "data" / "world.json").validate_database(migrated)


def report(source: dict, migrated: dict) -> dict:
    people_before = sum(
        encoded_size(person)
        for person in source.get("people", []) or []
        if isinstance(person, dict)
    )
    people_after = sum(
        encoded_size(person)
        for person in migrated.get("people", []) or []
        if isinstance(person, dict)
    )
    return {
        "people": len(migrated.get("people", [])),
        "catalogued_colored_tags": len(migrated.get("person_tag_catalog", [])),
        "externalized_legacy_imports": len(migrated.get("legacy_person_imports", [])),
        "bytes_removed_from_basic_person_records": people_before - people_after,
        "basic_person_record_reduction_percent": round(
            ((people_before - people_after) / people_before * 100)
            if people_before else 0,
            2,
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    store = SharedJsonStore(ROOT / "data", lock_timeout=10.0)
    source = store.read_document("world.json")
    migrated = build(source)
    verify(source, migrated)
    print(json.dumps(report(source, migrated), indent=2))
    if not arguments.apply:
        print("Audit only; no files changed.")
        return
    session = store.load("world.json")
    migrated = build(session.data)
    verify(session.base_data, migrated)
    session.data = migrated
    outcome = store.save(session, "world-normalizer")
    if not outcome.saved:
        raise RuntimeError("world.json changed during normalization; rerun the audit")
    print("Applied. The shared store created a recoverable timestamped backup.")


if __name__ == "__main__":
    main()
