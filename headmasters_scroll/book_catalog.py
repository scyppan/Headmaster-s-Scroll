"""Read the canonical World Builder book catalog without loading all world data."""

from __future__ import annotations

import json
from pathlib import Path


def _fingerprint(path):
    stat = path.stat()
    return {"size": int(stat.st_size), "mtime_ns": int(stat.st_mtime_ns)}


def _indexed_books(world_path):
    index_path = world_path.parent.parent / "runtime" / "world-builder" / "index.json"
    try:
        with index_path.open("r", encoding="utf-8") as stream:
            index = json.load(stream)
        if index.get("source") != _fingerprint(world_path):
            return None
        locations = index.get("record_locations", {}).get("books", {})
        if not isinstance(locations, dict):
            return None
        books = []
        event_locations = index.get("record_locations", {}).get(
            "events", {}
        )
        with world_path.open("rb") as stream:
            for offset, length in locations.values():
                stream.seek(int(offset))
                book = json.loads(stream.read(int(length)).decode("utf-8"))
                event_id = str(
                    book.get("publication_event_id", "") or ""
                ).strip()
                event_location = event_locations.get(event_id)
                if event_location:
                    event_offset, event_length = event_location
                    stream.seek(int(event_offset))
                    event = json.loads(
                        stream.read(int(event_length)).decode("utf-8")
                    )
                    book["publication_date"] = str(
                        event.get("date", "")
                        or book.get("publication_date", "")
                    )
                    book["author_name"] = str(
                        event.get("book_author_name", "")
                        or book.get("author_name", "")
                    )
                books.append(book)
        return books
    except (OSError, ValueError, TypeError, UnicodeError, json.JSONDecodeError):
        return None


def load_world_books(world_path):
    path = Path(world_path)
    if not path.exists():
        return None
    indexed = _indexed_books(path)
    if indexed is not None:
        return indexed
    try:
        with path.open("r", encoding="utf-8") as stream:
            world = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    books = world.get("books", []) if isinstance(world, dict) else []
    if not isinstance(books, list):
        return None
    events_by_id = {
        str(event.get("record_id", "") or "").strip(): event
        for event in world.get("events", [])
        if isinstance(event, dict)
    }
    for book in books:
        if not isinstance(book, dict):
            continue
        event = events_by_id.get(
            str(book.get("publication_event_id", "") or "").strip()
        )
        if not isinstance(event, dict):
            continue
        book["publication_date"] = str(
            event.get("date", "") or book.get("publication_date", "")
        )
        book["author_name"] = str(
            event.get("book_author_name", "")
            or book.get("author_name", "")
        )
    return books


def world_book_as_legacy_catalog_record(book):
    """Adapt World Builder's typed contents for older chooser screens."""
    contents = book.get("contents", []) if isinstance(book, dict) else []

    def references(content_type):
        return [
            {
                "record_id": str(entry.get("record_id", "") or "").strip(),
                "name": str(entry.get("name", "") or "").strip(),
            }
            for entry in contents
            if isinstance(entry, dict)
            and entry.get("content_type") == content_type
            and str(entry.get("record_id", "") or "").strip()
        ]

    return {
        "record_id": str(book.get("record_id", "") or "").strip(),
        "name": str(book.get("title", "") or "").strip(),
        "author": str(book.get("author_name", "") or "").strip(),
        "categories": list(book.get("categories", []) or []),
        "description": str(book.get("description", "") or ""),
        "publication_date": str(book.get("publication_date", "") or ""),
        "spells": references("Spell"),
        "proficiencies": references("Proficiency"),
        "potions": references("Recipe"),
        "_canonical_source": "world.json",
    }


def load_legacy_book_catalog(world_path):
    books = load_world_books(world_path)
    if books is None:
        return None
    return [world_book_as_legacy_catalog_record(book) for book in books]
