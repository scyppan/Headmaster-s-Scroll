from __future__ import annotations

import sys
from pathlib import Path


WORLD_BUILDER_SOURCE = (
    Path(__file__).resolve().parents[1] / "apps" / "world-builder" / "source"
)
if str(WORLD_BUILDER_SOURCE) not in sys.path:
    sys.path.insert(0, str(WORLD_BUILDER_SOURCE))

from mage_maker.sections.events.models import normalize_world_event_time
from mage_maker.core.database import JsonDatabase


def test_world_builder_accepts_suite_colon_time_and_normalizes_it():
    assert normalize_world_event_time("08:00") == "0800"
    assert normalize_world_event_time("23:59") == "2359"


def test_world_builder_rejects_invalid_colon_time():
    try:
        normalize_world_event_time("24:00")
    except ValueError:
        return
    raise AssertionError("Invalid time should be rejected")


def test_current_world_data_passes_world_builder_migration_and_validation():
    world_path = Path(__file__).resolve().parents[1] / "data" / "world.json"
    database = JsonDatabase(world_path)
    database.load()
    assert database.data.get("people") is not None
    assert database.dirty is False
    assert len(database.list_people_list_summaries()) == len(
        database.data["people"]
    )
