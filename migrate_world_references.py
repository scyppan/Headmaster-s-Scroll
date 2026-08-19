"""Safely audit/apply canonical event and book reference storage."""

from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "apps" / "world-builder" / "source"))

from headmasters_scroll.locking import FileLock  # noqa: E402
from mage_maker.core.reference_storage import (  # noqa: E402
    compact_development_book_references,
    migrate_person_event_references,
    normalize_event_references,
)
from mage_maker.sections.books.models import normalize_book_records  # noqa: E402
from mage_maker.sections.events.models import event_linked_person_ids  # noqa: E402
from mage_maker.core.database import JsonDatabase  # noqa: E402
from headmasters_scroll.validation import validate_document  # noqa: E402


def load(path):
    with path.open("r", encoding="utf-8") as stream:
        return json.load(stream)


def content_entry(book_id, content_type, collection, reference):
    record_id = str(reference.get("record_id", "") or "").strip()
    name = str(reference.get("name", "") or "").strip()
    key = f"{book_id}|{content_type}|{collection}|{record_id or name}"
    result = {
        "entry_id": f"book-content:{hashlib.sha1(key.encode()).hexdigest()[:24]}",
        "content_type": content_type,
        "collection": collection,
        "record_id": record_id,
    }
    if not record_id:
        result["name"] = name
    return result


def migrate_book(book):
    book_id = str(book.get("record_id", "") or "").strip()
    contents = []
    seen = set()
    for content_type, collection, field_name in (
        ("Spell", "spells", "spells"),
        ("Proficiency", "proficiencies", "proficiencies"),
        ("Recipe", "potions", "potions"),
    ):
        for reference in book.get(field_name, []) or []:
            if not isinstance(reference, dict):
                continue
            identity = (
                content_type,
                collection,
                str(reference.get("record_id", "") or "").strip()
                or str(reference.get("name", "") or "").strip().casefold(),
            )
            if identity in seen:
                continue
            seen.add(identity)
            contents.append(
                content_entry(book_id, content_type, collection, reference)
            )
    return {
        "record_id": book_id,
        "title": str(book.get("name", "") or "").strip(),
        "author_person_id": "",
        "author_name": str(book.get("author", "") or "Unknown author").strip(),
        "publication_date": str(book.get("publication_date") or "1900-01-01"),
        "publication_location_id": "",
        "publication_location_name": "",
        "mass_printed": True,
        "categories": list(book.get("categories", []) or []),
        "description": str(book.get("description", "") or "").strip(),
        "notes": str(book.get("dbnotes", "") or "").strip(),
        "contents": contents,
        "holdings": [],
        "last_updated": str(book.get("last_updated", "") or ""),
    }


def compact_reading(reading):
    keep = (
        "record_id", "person_id", "book_id", "date", "source_type",
        "source_entry_id", "source_organization_id", "source_person_id",
        "source_location_id", "source_name", "price_sickles", "notes",
        "created_at", "last_updated",
    )
    return {key: deepcopy(reading[key]) for key in keep if key in reading}


def build_migration(world, database):
    migrated_world = deepcopy(world)
    migrated_database = deepcopy(database)
    books = {
        str(book.get("record_id", "") or "").strip(): book
        for book in migrated_world.get("books", [])
        if isinstance(book, dict)
    }
    used_titles = {
        str(book.get("title", "") or "").strip().casefold()
        for book in books.values()
    }
    for legacy in database.get("books", []) or []:
        migrated = migrate_book(legacy)
        if migrated["title"].casefold() in used_titles:
            qualifier = migrated.get("author_name") or migrated["record_id"]
            migrated["title"] = f"{migrated['title']} — {qualifier} edition"
        current = books.get(migrated["record_id"])
        if current is not None and current.get("title") != migrated["title"]:
            raise ValueError(f"Conflicting book ID: {migrated['record_id']}")
        books[migrated["record_id"]] = migrated
        used_titles.add(migrated["title"].casefold())
    migrated_world["books"] = normalize_book_records(list(books.values()))
    migrated_world["book_readings"] = [
        compact_reading(reading)
        for reading in migrated_world.get("book_readings", [])
        if isinstance(reading, dict)
    ]
    migrate_person_event_references(migrated_world)
    migrated_world["people"] = [
        compact_development_book_references(person)
        for person in migrated_world.get("people", [])
    ]
    migrated_database["books"] = []

    now = datetime.now(timezone.utc).isoformat()
    migrated_world.setdefault("_database", {})["schema_version"] = 37
    migrated_world["_database"]["database_version"] = "0.37.0"
    migrated_world["_database"]["last_saved"] = now
    for document in (migrated_world, migrated_database):
        metadata = document.setdefault("_headmasters_scroll", {})
        metadata.update({
            "revision_id": str(uuid4()),
            "last_modified_at": now,
            "last_modified_by": "reference-migration",
        })
    return migrated_world, migrated_database


def verify(original_world, original_database, world, database):
    errors = []
    if len(world.get("people", [])) != len(original_world.get("people", [])):
        errors.append("person count changed")
    source_book_ids = {
        str(book.get("record_id", "") or "").strip()
        for book in original_database.get("books", [])
    }
    world_book_ids = {
        str(book.get("record_id", "") or "").strip()
        for book in world.get("books", [])
    }
    if source_book_ids - world_book_ids:
        errors.append("not all DBM books reached world.json")
    event_ids = {
        str(event.get("record_id", "") or "").strip()
        for event in world.get("events", [])
    }
    people = {
        str(person.get("record_id", "") or "").strip(): person
        for person in world.get("people", [])
    }
    for person in people.values():
        if any(
            event_id not in event_ids
            for event_id in normalize_event_references(person.get("event_refs", []))
        ):
            errors.append("an event reference is unresolved")
            break
    for event in world.get("events", []):
        event_id = str(event.get("record_id", "") or "").strip()
        for person_id in event_linked_person_ids(event):
            if event_id not in normalize_event_references(
                people.get(person_id, {}).get("event_refs", [])
            ):
                errors.append("a linked person is missing an event reference")
                break
        if errors:
            break
    if database.get("books"):
        errors.append("DBM still contains canonical books")
    if errors:
        raise ValueError("Verification failed: " + "; ".join(errors))
    JsonDatabase(ROOT / "data" / "world.json").validate_database(world)
    validate_document("db.json", database)


def stage(path, value):
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    return temporary


def report_for(world, database, migrated):
    return {
        "people": len(world.get("people", [])),
        "events_before": len(world.get("events", [])),
        "events_after": len(migrated.get("events", [])),
        "embedded_timeline_bytes_removed": sum(
            len(json.dumps(person.get("timeline_events", []), ensure_ascii=False))
            for person in world.get("people", [])
            if isinstance(person, dict) and "timeline_events" in person
        ),
        "world_books_before": len(world.get("books", [])),
        "dbm_books_before": len(database.get("books", [])),
        "world_books_after": len(migrated.get("books", [])),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    world_path = ROOT / "data" / "world.json"
    database_path = ROOT / "data" / "db.json"
    world, database = load(world_path), load(database_path)
    migrated_world, migrated_database = build_migration(world, database)
    verify(world, database, migrated_world, migrated_database)
    report = report_for(world, database, migrated_world)
    print(json.dumps(report, indent=2))
    if not args.apply:
        print("Audit only; no files changed.")
        return

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = ROOT / "data" / "backups" / f"reference-normalization-{timestamp}"
    with FileLock(world_path, timeout=10), FileLock(database_path, timeout=10):
        locked_world, locked_database = load(world_path), load(database_path)
        migrated_world, migrated_database = build_migration(
            locked_world, locked_database
        )
        verify(locked_world, locked_database, migrated_world, migrated_database)
        backup.mkdir(parents=True, exist_ok=False)
        shutil.copy2(world_path, backup / "world.json")
        shutil.copy2(database_path, backup / "db.json")
        (backup / "report.json").write_text(
            json.dumps(report, indent=2) + "\n", encoding="utf-8"
        )
        world_temp = stage(world_path, migrated_world)
        database_temp = stage(database_path, migrated_database)
        try:
            os.replace(world_temp, world_path)
            os.replace(database_temp, database_path)
        finally:
            world_temp.unlink(missing_ok=True)
            database_temp.unlink(missing_ok=True)
    print(f"Applied with complete recovery copies in {backup}")


if __name__ == "__main__":
    main()
