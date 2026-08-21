from copy import deepcopy
from datetime import datetime, timezone

from headmasters_scroll.creatures import generate_creature_instance


SOLIDIFIED_STATS = (
    "size",
    "heavy_wound_cap",
    "magical_resistance",
    "intelligence",
    "social_skill",
    "movement",
)


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def solidify_named_creature(record, species, rng=None):
    """Materialize a named creature's random values exactly once.

    The marker is deliberately authoritative. Once set, later edits to the
    species definition (or to the named creature's biography) never reroll
    the individual creature.
    """

    result = deepcopy(record) if isinstance(record, dict) else {}
    if result.get("statistics_solidified"):
        return result, False

    existing_generated = result.get("generated")
    has_existing_stats = (
        isinstance(existing_generated, dict)
        and all(field in existing_generated for field in SOLIDIFIED_STATS)
    )
    has_existing_actions = "actions" in result and isinstance(
        result.get("actions"), list
    )

    if not has_existing_stats or not has_existing_actions:
        generated = generate_creature_instance(
            species,
            1,
            {
                "location_id": "world-builder",
                "floor_id": "",
                "map_id": "world-builder",
                "x": 0.5,
                "y": 0.5,
            },
            rng=rng,
        )
        if not has_existing_stats:
            result["generated"] = deepcopy(generated["generated"])
        if not has_existing_actions:
            result["actions"] = deepcopy(generated["actions"])

    result["statistics_solidified"] = True
    result.setdefault("statistics_solidified_at", utc_now())
    return result, True


def creature_relationship_events(events, named_creature_id):
    creature_id = str(named_creature_id or "").strip()
    relationship_types = {
        "tamed_creature",
        "bonded_creature",
        "irked_creature",
    }
    return [
        deepcopy(event)
        for event in events or ()
        if isinstance(event, dict)
        and str(event.get("named_creature_id", "") or "").strip()
        == creature_id
        and str(event.get("event_type", "") or "").strip()
        in relationship_types
    ]
