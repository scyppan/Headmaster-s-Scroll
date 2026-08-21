import random
import sys
from pathlib import Path


WORLD_BUILDER_SOURCE = (
    Path(__file__).resolve().parents[1] / "apps" / "world-builder" / "source"
)
if str(WORLD_BUILDER_SOURCE) not in sys.path:
    sys.path.insert(0, str(WORLD_BUILDER_SOURCE))

from mage_maker.sections.creatures.models import (
    creature_relationship_events,
    solidify_named_creature,
)


def species():
    return {
        "record_id": "species-owl",
        "name": "Owl",
        "awareness_proficiency_id": "owl-awareness",
        "size": {"low": 1, "high": 2},
        "wound_cap": {"low": 1, "high": 3},
        "magical_resistance": {"low": 0, "high": 2},
        "intelligence": {"low": 2, "high": 5},
        "social_skill": {"low": 1, "high": 4},
        "movement": {
            "flying": {"enabled": "Yes", "low": 4, "high": 8}
        },
        "attacks": [{
            "record_id": "owl-talons",
            "name": "Talons",
            "roll": {"low": 2, "high": 7},
        }],
        "abilities": [],
        "parts": [],
    }


def test_named_creature_stats_are_generated_once_and_never_rerolled():
    record = {
        "record_id": "hedwig",
        "name": "Hedwig",
        "species_record_id": "species-owl",
        "species_name": "Owl",
    }
    first, changed = solidify_named_creature(
        record, species(), random.Random(4)
    )
    second, changed_again = solidify_named_creature(
        first, species(), random.Random(999)
    )

    assert changed is True
    assert changed_again is False
    assert second["generated"] == first["generated"]
    assert second["actions"] == first["actions"]
    assert second["statistics_solidified_at"] == first[
        "statistics_solidified_at"
    ]


def test_existing_complete_stats_are_preserved_during_marker_migration():
    record = {
        "record_id": "existing",
        "generated": {
            "size": 4,
            "heavy_wound_cap": 5,
            "magical_resistance": 6,
            "intelligence": 7,
            "social_skill": 8,
            "movement": {"walking": 9},
        },
        "actions": [],
    }
    migrated, changed = solidify_named_creature(
        record, species(), random.Random(1)
    )

    assert changed is True
    assert migrated["generated"] == record["generated"]
    assert migrated["actions"] == []


def test_relationship_history_is_normalized_as_event_references():
    events = [
        {
            "record_id": "one",
            "event_type": "bonded_creature",
            "named_creature_id": "hedwig",
            "person_ids": ["harry"],
            "date": "1991-07-31",
        },
        {
            "record_id": "two",
            "event_type": "tamed_creature",
            "named_creature_id": "other",
        },
        {
            "record_id": "three",
            "event_type": "custom",
            "named_creature_id": "hedwig",
        },
    ]

    assert [
        event["record_id"]
        for event in creature_relationship_events(events, "hedwig")
    ] == ["one"]
