from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD_BUILDER_SOURCE = ROOT / "apps" / "world-builder" / "source"
if str(WORLD_BUILDER_SOURCE) not in sys.path:
    sys.path.insert(0, str(WORLD_BUILDER_SOURCE))

from headmasters_scroll.book_catalog import load_legacy_book_catalog
from mage_maker.core.database import JsonDatabase
from mage_maker.core.world_index import (
    WorldIndexCache,
    scan_record_locations,
)
from mage_maker.core.reference_storage import (
    compact_development_book_references,
    externalize_person_support_records,
    migrate_person_event_references,
    world_event_to_timeline,
)


def test_profile_tags_and_legacy_imports_are_externalized_and_hydrated(tmp_path):
    world = {
        "people": [{
            "record_id": "person-1",
            "displayed_name": "Ada",
            "tags": [{"text": "Canon", "background_color": "#aabbcc"}],
            "imported_fields": {"Original field": "Large legacy value"},
            "event_refs": [],
        }],
        "events": [],
    }
    assert externalize_person_support_records(world) is True
    stored_person = world["people"][0]
    assert "tags" not in stored_person
    assert "imported_fields" not in stored_person
    assert stored_person["tag_ids"] == [world["person_tag_catalog"][0]["record_id"]]
    assert stored_person["legacy_import_id"] == "legacy-import:person-1"

    database = JsonDatabase(tmp_path / "world.json")
    database.data = world
    database.fully_loaded = True
    database.rebuild_record_indexes()
    hydrated = database.read_person("person-1")
    assert hydrated["tags"] == [{
        "text": "Canon", "background_color": "#aabbcc"
    }]
    assert hydrated["imported_fields"] == {
        "Original field": "Large legacy value"
    }
    assert externalize_person_support_records(world) is False


from mage_maker.sections.development.book_dialog import (
    book_display_text,
    resolve_selected_books,
)


def test_person_timelines_externalize_and_derived_events_are_not_duplicated():
    world = {
        "people": [{
            "record_id": "person-1",
            "displayed_name": "Ada",
            "birth_year": 1980,
            "timeline_events": [
                {
                    "event_id": "life-start:born",
                    "event_type": "born",
                    "detail": "Born",
                    "date": "1980-01-01",
                    "automatic_source": "life_start",
                },
                {
                    "event_id": "custom-1",
                    "event_type": "custom",
                    "detail": "Found a wand",
                    "date": "1991-09-01",
                    "note": "Oak and phoenix feather",
                },
            ],
        }],
        "events": [],
    }

    assert migrate_person_event_references(world) is True
    person = world["people"][0]
    assert "timeline_events" not in person
    assert len(person["event_refs"]) == 1
    assert len(world["events"]) == 1
    event = world["events"][0]
    assert event["title"] == "Found a wand"
    assert event["description"] == "Oak and phoenix feather"
    hydrated = world_event_to_timeline(event, "person-1")
    assert hydrated["event_id"] == "custom-1"
    assert hydrated["detail"] == "Found a wand"


def test_development_books_keep_only_ids_when_available():
    person = {
        "development_plan": {
            "school_years": [{
                "assigned_books": [{
                    "record_id": "book-1",
                    "name": "Copied title",
                    "author": "Copied author",
                }],
                "books": [],
            }],
            "adult_years": [],
        }
    }
    compact = compact_development_book_references(person)
    assert compact["development_plan"]["school_years"][0][
        "assigned_books"
    ] == [{"record_id": "book-1"}]


def test_dbm_can_read_world_books_from_compact_index(tmp_path):
    data = tmp_path / "data"
    runtime = tmp_path / "runtime" / "world-builder"
    data.mkdir()
    runtime.mkdir(parents=True)
    world_path = data / "world.json"
    book = {
        "record_id": "book-1",
        "title": "Reference Magic",
        "author_name": "A. Author",
        "contents": [{
            "entry_id": "entry-1",
            "content_type": "Spell",
            "collection": "spells",
            "record_id": "spell-1",
        }],
    }
    raw = json.dumps({"books": [book]}, separators=(",", ":"))
    world_path.write_text(raw, encoding="utf-8")
    encoded = json.dumps(book, separators=(",", ":"))
    offset = raw.index(encoded)
    stat = world_path.stat()
    (runtime / "index.json").write_text(json.dumps({
        "source": {"size": stat.st_size, "mtime_ns": stat.st_mtime_ns},
        "record_locations": {"books": {"book-1": [offset, len(encoded)]}},
    }), encoding="utf-8")

    books = load_legacy_book_catalog(world_path)
    assert books[0]["name"] == "Reference Magic"
    assert books[0]["spells"] == [{"record_id": "spell-1", "name": ""}]


def test_selected_book_references_resolve_current_catalog_labels():
    catalog = [{
        "record_id": "book-1",
        "name": "Current title",
        "author": "Current author",
    }]
    selected = [{"record_id": "book-1"}]

    resolved = resolve_selected_books(catalog, selected)
    assert resolved == catalog
    assert book_display_text(resolved[0]) == "Current title — Current author"


def test_indexed_person_hydrates_book_labels_without_storing_them(tmp_path):
    source = tmp_path / "data" / "world.json"
    source.parent.mkdir()
    data = {
        "_database": {"schema_version": 38},
        "_headmasters_scroll": {"revision_id": "revision-1"},
        "people": [{
            "record_id": "person-1",
            "displayed_name": "Ada",
            "development_plan": {
                "school_years": [{
                    "assigned_books": [{"record_id": "book-1"}],
                    "books": [],
                }],
                "adult_years": [],
            },
            "event_refs": [],
            "tag_ids": ["person-tag:canon"],
            "legacy_import_id": "legacy-import:person-1",
        }],
        "books": [{
            "record_id": "book-1",
            "title": "Current title",
            "author_name": "Current author",
            "contents": [],
            "holdings": [],
        }],
        "events": [],
        "person_tag_catalog": [{
            "record_id": "person-tag:canon",
            "text": "Canon",
            "background_color": "#AABBCC",
        }],
        "legacy_person_imports": [{
            "record_id": "legacy-import:person-1",
            "person_id": "person-1",
            "fields": {"Source": "Legacy import"},
        }],
    }
    source.write_text(json.dumps(data, indent=2), encoding="utf-8")
    cache_path = tmp_path / "runtime" / "index.json"
    cache = WorldIndexCache(source, cache_path)
    cache.build(data, scan_record_locations(source))
    cache.write()
    database = JsonDatabase(source)
    database.world_index = WorldIndexCache(source, cache_path)

    assert database.load_index_only() is True
    person = database.read_person("person-1")
    assert person["development_plan"]["school_years"][0][
        "assigned_books"
    ] == [{
        "record_id": "book-1",
        "name": "Current title",
        "author": "Current author",
    }]
    assert person["tags"] == [{
        "text": "Canon", "background_color": "#AABBCC"
    }]
    assert person["imported_fields"] == {"Source": "Legacy import"}
    stored = json.loads(source.read_text(encoding="utf-8"))
    assert stored["people"][0]["development_plan"]["school_years"][0][
        "assigned_books"
    ] == [{"record_id": "book-1"}]
