from __future__ import annotations

import json
import sys
from pathlib import Path


WORLD_BUILDER_SOURCE = (
    Path(__file__).resolve().parents[1] / "apps" / "world-builder" / "source"
)
if str(WORLD_BUILDER_SOURCE) not in sys.path:
    sys.path.insert(0, str(WORLD_BUILDER_SOURCE))

from mage_maker.core.database import JsonDatabase
from mage_maker.core.world_index import (
    WorldIndexCache,
    read_indexed_record,
    scan_record_locations,
)


def indexed_world():
    return {
        "_database": {"schema_version": 36},
        "_headmasters_scroll": {"revision_id": "revision-one"},
        "people": [
            {
                "record_id": "person-one",
                "displayed_name": "Indexed Magician",
                "birth_year": 1980,
                "development_plan": {"very_large": [1, 2, 3]},
            }
        ],
        "locations": [
            {"record_id": "place-one", "name": "Indexed Place"}
        ],
        "organizations": [],
        "events": [
            {
                "record_id": "event-one",
                "title": "Indexed Event",
                "event_type": "custom",
                "date": "2000-01-01",
                "person_ids": ["person-one"],
                "location_ids": ["place-one"],
            }
        ],
        "items": [],
        "books": [],
        "book_readings": [],
        "maps": [],
        "board_groups": [],
        "named_creatures": [],
    }


def test_index_reads_one_record_and_keeps_summaries_compact(tmp_path):
    source = tmp_path / "world.json"
    source.write_text(json.dumps(indexed_world(), indent=2), encoding="utf-8")
    locations = scan_record_locations(source)
    cache = WorldIndexCache(source, tmp_path / "index.json")
    cache.build(indexed_world(), locations)
    cache.write()

    reloaded = WorldIndexCache(source, tmp_path / "index.json")
    assert reloaded.load() is True
    person = read_indexed_record(
        source,
        reloaded.payload,
        "people",
        "person-one",
    )
    assert person["displayed_name"] == "Indexed Magician"
    summary = reloaded.people_summaries()[0]
    assert summary["record_id"] == "person-one"
    assert "development_plan" not in summary
    assert reloaded.linked_event_ids("people", "person-one") == [
        "event-one"
    ]


def test_index_rejects_stale_and_corrupt_caches(tmp_path):
    source = tmp_path / "world.json"
    source.write_text(json.dumps(indexed_world()), encoding="utf-8")
    cache_path = tmp_path / "index.json"
    cache = WorldIndexCache(source, cache_path)
    cache.build(indexed_world(), scan_record_locations(source))
    cache.write()
    assert WorldIndexCache(source, cache_path).load() is True

    changed = indexed_world()
    changed["locations"].append(
        {"record_id": "place-two", "name": "New Place"}
    )
    source.write_text(json.dumps(changed), encoding="utf-8")
    assert WorldIndexCache(source, cache_path).load() is False

    cache_path.write_text("{broken", encoding="utf-8")
    assert WorldIndexCache(source, cache_path).load() is False


def test_current_schema_does_not_run_migrations_or_mark_changes(tmp_path):
    data = indexed_world()
    before = json.dumps(data, sort_keys=True)
    database = JsonDatabase(tmp_path / "world.json")
    assert database.migrate_database(data) is False
    assert json.dumps(data, sort_keys=True) == before


def test_private_preferences_do_not_dirty_or_modify_world_data(tmp_path):
    source = tmp_path / "data" / "world.json"
    source.parent.mkdir()
    source.write_text(json.dumps(indexed_world()), encoding="utf-8")
    before = source.read_bytes()
    database = JsonDatabase(source)
    database.dirty = False

    assert database.set_preference("_recent_people", ["person-one"]) is True
    assert database.get_preference("_recent_people") == ["person-one"]
    assert database.dirty is False
    assert source.read_bytes() == before
