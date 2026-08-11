import re
import uuid
from copy import deepcopy

from mage_maker.core.dates import format_date_parts
from mage_maker.sections.family_tree.spouse_relationships import (
    normalize_spouse_relationships,
)
from mage_maker.sections.timeline.events import (
    normalize_timeline_events,
    timeline_event_summary,
)
from mage_maker.sections.timeline.locations import location_at_date, normalize_location
from mage_maker.sections.events.models import (
    event_time_sort_key,
    normalize_world_event_date,
    normalize_world_events,
    normalize_world_event_time,
    world_event_year,
)
from mage_maker.sections.events.types import (
    canonical_event_type,
    event_visible_outside_person,
)
from mage_maker.sections.locations.period_definitions import (
    EARLIEST_CALCULATION_YEAR,
    LATEST_CALCULATION_YEAR,
)


LOCATION_EVENT_DATE_PATTERN = re.compile(
    r"^(-?\d{1,5})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$"
)
LOCATION_FOUNDATION_EVENT_TYPES = frozenset(
    (
        "founding",
        "wizarding_community_established",
    )
)
LOCATION_EXTINCTION_EVENT_TYPE = "extinction"


def normalize_location_event(event):
    if not isinstance(event, dict):
        raise TypeError("Every location event must be an object.")

    normalized = deepcopy(event)
    normalized["event_id"] = str(
        normalized.get("event_id") or uuid.uuid4()
    ).strip()
    event_date = str(normalized.get("date", "") or "").strip()
    normalized["date"] = (
        normalize_world_event_date(event_date)
        if event_date
        else ""
    )
    normalized["time"] = normalize_world_event_time(
        normalized.get("time")
    )
    normalized["title"] = str(normalized.get("title", "") or "").strip()
    normalized["note"] = str(normalized.get("note", "") or "").strip()
    normalized["event_type"] = canonical_event_type(
        normalized.get("event_type") or "other"
    )

    if (
        normalized["event_type"] == LOCATION_EXTINCTION_EVENT_TYPE
        and not normalized["date"]
    ):
        raise ValueError("An extinction event needs a date.")

    if not normalized["title"]:
        raise ValueError("A location event needs a title.")

    return normalized


def normalize_location_events(events):
    if events in (None, ""):
        return []

    if not isinstance(events, list):
        raise TypeError("Location events must be a list.")

    normalized_events = []
    seen_ids = set()

    for event in events:
        normalized = normalize_location_event(event)

        if normalized["event_id"] in seen_ids:
            normalized["event_id"] = str(uuid.uuid4())

        seen_ids.add(normalized["event_id"])
        normalized_events.append(normalized)

    normalized_events.sort(key=location_event_sort_key)
    return normalized_events


def location_event_is_foundation(event):
    if not isinstance(event, dict):
        return False

    return (
        canonical_event_type(event.get("event_type"))
        in LOCATION_FOUNDATION_EVENT_TYPES
    )


def location_foundation_event_state(
    location,
    world_events=None,
    world_events_are_normalized=False,
):
    if not isinstance(location, dict):
        return {
            "valid": False,
            "first_event_id": "",
            "foundation_event_id": "",
            "foundation_event_type": "",
            "foundation_event_date": "",
        }

    location_id = str(
        location.get("record_id", "") or ""
    ).strip()
    direct_events = []

    for event in normalize_location_events(
        location.get("timeline_events", [])
    ):
        direct_events.append(
            {
                "event_id": str(
                    event.get("event_id", "") or ""
                ).strip(),
                "event_type": canonical_event_type(
                    event.get("event_type")
                ),
                "title": str(event.get("title", "") or ""),
                "date": str(event.get("date", "") or ""),
                "time": str(event.get("time", "") or ""),
            }
        )

    normalized_world_events = (
        list(world_events or [])
        if world_events_are_normalized
        else normalize_world_events(world_events or [])
    )

    for event in normalized_world_events:
        if (
            not location_id
            or location_id not in event.get("location_ids", [])
            or bool(event.get("organization_event"))
        ):
            continue

        direct_events.append(
            {
                "event_id": str(
                    event.get("record_id", "") or ""
                ).strip(),
                "event_type": canonical_event_type(
                    event.get("event_type")
                ),
                "title": str(event.get("title", "") or ""),
                "date": str(event.get("date", "") or ""),
                "time": str(event.get("time", "") or ""),
            }
        )

    direct_events.sort(key=location_event_sort_key)
    first_event = direct_events[0] if direct_events else None
    foundation_event = next(
        (
            event
            for event in direct_events
            if location_event_is_foundation(event)
        ),
        None,
    )
    return {
        "valid": bool(
            first_event is not None
            and location_event_is_foundation(first_event)
        ),
        "first_event_id": (
            first_event["event_id"]
            if first_event is not None
            else ""
        ),
        "foundation_event_id": (
            foundation_event["event_id"]
            if foundation_event is not None
            else ""
        ),
        "foundation_event_type": (
            foundation_event["event_type"]
            if foundation_event is not None
            else ""
        ),
        "foundation_event_date": (
            foundation_event["date"]
            if foundation_event is not None
            else ""
        ),
    }


def location_extinction_event_state(
    location,
    world_events=None,
    world_events_are_normalized=False,
):
    if not isinstance(location, dict):
        return {
            "exists": False,
            "event_id": "",
            "date": "",
            "year": None,
        }

    location_id = str(
        location.get("record_id", "") or ""
    ).strip()
    extinction_events = []

    for event in normalize_location_events(
        location.get("timeline_events", [])
    ):
        if (
            canonical_event_type(event.get("event_type"))
            != LOCATION_EXTINCTION_EVENT_TYPE
        ):
            continue

        extinction_events.append(
            {
                "event_id": str(
                    event.get("event_id", "") or ""
                ).strip(),
                "date": str(event.get("date", "") or ""),
                "time": str(event.get("time", "") or ""),
            }
        )

    normalized_world_events = (
        list(world_events or [])
        if world_events_are_normalized
        else normalize_world_events(world_events or [])
    )

    for event in normalized_world_events:
        if (
            canonical_event_type(event.get("event_type"))
            != LOCATION_EXTINCTION_EVENT_TYPE
            or not location_id
            or location_id not in event.get("location_ids", [])
            or bool(event.get("organization_event"))
        ):
            continue

        extinction_events.append(
            {
                "event_id": str(
                    event.get("record_id", "") or ""
                ).strip(),
                "date": str(event.get("date", "") or ""),
                "time": str(event.get("time", "") or ""),
            }
        )

    extinction_events.sort(key=location_event_sort_key)
    extinction_event = (
        extinction_events[0] if extinction_events else None
    )
    extinction_date = (
        extinction_event["date"]
        if extinction_event is not None
        else ""
    )
    return {
        "exists": extinction_event is not None,
        "event_id": (
            extinction_event["event_id"]
            if extinction_event is not None
            else ""
        ),
        "date": extinction_date,
        "year": world_event_year(extinction_date),
    }


def synchronize_location_extinction_records(
    database_data,
    create_legacy_events=False,
):
    if not isinstance(database_data, dict):
        return False

    locations = database_data.get("locations", [])
    world_events = database_data.get("events", [])

    if not isinstance(locations, list) or not isinstance(world_events, list):
        return False

    world_events_by_location_id = {}

    for event in normalize_world_events(world_events):
        if (
            canonical_event_type(event.get("event_type"))
            != LOCATION_EXTINCTION_EVENT_TYPE
            or bool(event.get("organization_event"))
        ):
            continue

        for location_id in event.get("location_ids", []):
            normalized_location_id = str(
                location_id or ""
            ).strip()

            if not normalized_location_id:
                continue

            world_events_by_location_id.setdefault(
                normalized_location_id,
                [],
            ).append(event)

    changed = False

    for location in locations:
        if not isinstance(location, dict):
            continue

        location_id = str(
            location.get("record_id", "") or ""
        ).strip()

        state = location_extinction_event_state(
            location,
            world_events_by_location_id.get(location_id, []),
            world_events_are_normalized=True,
        )

        if (
            create_legacy_events
            and not state["exists"]
            and bool(location.get("extinct"))
            and location.get("extinction_year") not in (None, "")
        ):
            location_name = str(
                location.get("name", "") or "Unnamed location"
            ).strip()
            legacy_event = normalize_location_event(
                {
                    "event_id": f"location-extinction:{location_id}",
                    "event_type": LOCATION_EXTINCTION_EVENT_TYPE,
                    "title": f"Extinction of {location_name}",
                    "date": format_date_parts(
                        location.get("extinction_year"),
                        None,
                        None,
                        unknown="",
                    ),
                    "note": "",
                }
            )
            location["timeline_events"] = normalize_location_events(
                [
                    *location.get("timeline_events", []),
                    legacy_event,
                ]
            )
            state = location_extinction_event_state(
                location,
                world_events_by_location_id.get(location_id, []),
                world_events_are_normalized=True,
            )
            changed = True

        expected_extinct = bool(state["exists"])
        expected_year = state["year"] if expected_extinct else ""

        if location.get("extinct") is not expected_extinct:
            location["extinct"] = expected_extinct
            changed = True

        if location.get("extinction_year", "") != expected_year:
            location["extinction_year"] = expected_year
            changed = True

    return changed


def normalize_location_record(values):
    if not isinstance(values, dict):
        raise TypeError("A location must be an object.")

    normalized = deepcopy(values)
    normalized["name"] = str(normalized.get("name", "") or "").strip()
    normalized["parent_location_id"] = str(
        normalized.get("parent_location_id", "") or ""
    ).strip()
    normalized["campus_organization_id"] = str(
        normalized.get("campus_organization_id", "") or ""
    ).strip()
    normalized["demographics"] = str(
        normalized.get("demographics", "") or ""
    ).strip()
    normalized["notes"] = str(normalized.get("notes", "") or "").strip()
    normalized["is_building"] = bool(normalized.get("is_building", False))
    normalized["has_floors"] = bool(
        normalized.get(
            "has_floors",
            normalized.get("floors") or normalized.get("is_building", False),
        )
    )
    floors = []
    floor_ids = set()
    for index, floor in enumerate(normalized.get("floors", []) or []):
        if not isinstance(floor, dict):
            raise TypeError("Every floor must be an object.")
        floor_id = str(floor.get("record_id", "") or "").strip()
        floor_name = str(floor.get("name", "") or "").strip()
        if not floor_id or not floor_name:
            raise ValueError("Every floor needs a stable ID and name.")
        if floor_id in floor_ids:
            raise ValueError("Floor IDs must be unique within a location.")
        floor_ids.add(floor_id)
        floors.append({
            **deepcopy(floor),
            "record_id": floor_id,
            "name": floor_name,
            "sort_order": index,
            "primary_map_id": str(floor.get("primary_map_id", "") or "").strip(),
        })
    if floors and not normalized["has_floors"]:
        raise ValueError("A location with named floors must have Has floors enabled.")
    normalized["floors"] = floors
    normalized["default_map_id"] = str(
        normalized.get("default_map_id", "") or ""
    ).strip()
    normalized["extinct"] = bool(normalized.get("extinct"))
    normalized["extinction_year"] = normalize_extinction_year(
        normalized.get("extinction_year"),
        normalized["extinct"],
    )
    normalized["timeline_events"] = normalize_location_events(
        normalized.get("timeline_events", [])
    )

    if not normalized["name"]:
        raise ValueError("A location must have a name.")

    return normalized


def normalize_extinction_year(value, extinct):
    if not extinct:
        return ""

    if isinstance(value, bool):
        raise ValueError("Enter the year this location became extinct.")

    normalized_text = str(value if value is not None else "").strip()

    if not normalized_text:
        raise ValueError("Enter the year this location became extinct.")

    try:
        normalized_year = int(normalized_text)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Enter the year this location became extinct."
        ) from error

    if (
        normalized_year == 0
        or normalized_year < EARLIEST_CALCULATION_YEAR
        or normalized_year > LATEST_CALCULATION_YEAR
    ):
        raise ValueError(
            "The extinction year must be between -99999 and 99999, excluding 0."
        )

    return normalized_year


def location_extinction_state(location, period_start_year, period_end_year):
    if not isinstance(location, dict) or not bool(location.get("extinct")):
        return ""

    try:
        extinction_year = int(location.get("extinction_year"))
        start_year = int(period_start_year)
        end_year = int(period_end_year)
    except (TypeError, ValueError):
        return ""

    if extinction_year < start_year:
        return "before"

    if start_year <= extinction_year <= end_year:
        return "during"

    return "after"


def locations_by_id(locations):
    return {
        str(location.get("record_id", "") or "").strip(): location
        for location in locations
        if isinstance(location, dict)
        and str(location.get("record_id", "") or "").strip()
    }


def location_depth(location_id, locations):
    records = locations_by_id(locations)
    current_id = str(location_id or "").strip()
    visited = set()
    depth = 0

    while current_id:
        if current_id in visited:
            raise ValueError("Location nesting contains a cycle.")

        visited.add(current_id)
        current = records.get(current_id)

        if current is None:
            break

        parent_id = str(current.get("parent_location_id", "") or "").strip()

        if not parent_id:
            break

        depth += 1
        current_id = parent_id

    return depth


def location_path(location_id, locations):
    records = locations_by_id(locations)
    return location_path_from_records(location_id, records)


def location_path_from_records(location_id, records):
    current_id = str(location_id or "").strip()
    visited = set()
    names = []

    while current_id:
        if current_id in visited:
            raise ValueError("Location nesting contains a cycle.")

        visited.add(current_id)
        current = records.get(current_id)

        if current is None:
            break

        names.append(str(current.get("name", "") or "Unnamed").strip())
        current_id = str(current.get("parent_location_id", "") or "").strip()

    names.reverse()
    return " › ".join(names)


def location_paths_by_id(locations):
    records = locations_by_id(locations)
    return {
        record_id: location_path_from_records(
            record_id,
            records,
        )
        for record_id in records
    }


def ancestor_locations(location_id, locations):
    records = locations_by_id(locations)
    current_id = str(location_id or "").strip()
    ancestors = []
    visited = set()

    while current_id:
        if current_id in visited:
            raise ValueError("Location nesting contains a cycle.")

        visited.add(current_id)
        current = records.get(current_id)

        if current is None:
            break

        ancestors.append(current)
        current_id = str(current.get("parent_location_id", "") or "").strip()

    return ancestors


def recent_location_label(location_id, locations):
    normalized_location_id = str(location_id or "").strip()

    if not normalized_location_id:
        return "The World"

    ancestors = ancestor_locations(
        normalized_location_id,
        locations,
    )

    if not ancestors:
        return "Unknown location"

    path_records = list(reversed(ancestors))
    names = [
        str(location.get("name", "") or "Unnamed").strip()
        for location in path_records
    ]
    world_level = len(names) + 1
    current_name = names[-1]

    if world_level <= 3:
        return current_name

    if world_level == 4:
        return f"{current_name}, {names[-2]}"

    if world_level == 5:
        return f"{current_name} ({names[-2]}, {names[-3]})"

    return (
        f"{current_name} "
        f"(an area in {names[2]}, {names[1]})"
    )


def founding_event_title(location_id, locations):
    normalized_location_id = str(location_id or "").strip()
    location = locations_by_id(locations).get(normalized_location_id)
    location_name = str(
        (location or {}).get("name", "") or ""
    ).strip()

    if not location_name:
        return ""

    return f"Founding of {location_name}"


def descendant_ids(location_id, locations):
    selected_id = str(location_id or "").strip()
    descendants = set()
    changed = True

    while changed:
        changed = False

        for location in locations:
            record_id = str(location.get("record_id", "") or "").strip()
            parent_id = str(
                location.get("parent_location_id", "") or ""
            ).strip()

            if record_id in descendants or record_id == selected_id:
                continue

            if parent_id == selected_id or parent_id in descendants:
                descendants.add(record_id)
                changed = True

    return descendants


def location_event_sort_key(event):
    return (
        location_event_date_key(event.get("date")),
        event_time_sort_key(event.get("time")),
        0 if location_event_is_foundation(event) else 1,
        str(event.get("title", "") or "").casefold(),
        str(event.get("event_id", "") or ""),
    )


def location_event_date_key(value):
    date_text = str(value or "").strip()
    match = LOCATION_EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        return 100000, 13, 32

    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def location_event_year(value):
    date_key = location_event_date_key(value)

    if date_key[0] == 100000:
        return None

    return date_key[0]


def person_location_events(people, locations):
    known_locations = {
        normalize_location(location.get("name", "")): location
        for location in locations
        if normalize_location(location.get("name", ""))
    }
    locations_by_record_id = {
        str(location.get("record_id", "") or "").strip(): location
        for location in locations
        if isinstance(location, dict)
        and str(location.get("record_id", "") or "").strip()
    }
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    generated_events = []
    seen_events = set()

    for person in people_by_id.values():
        person_id = str(person.get("record_id", "") or "").strip()
        person_name = str(
            person.get("displayed_name", "") or "Unnamed magician"
        ).strip()

        for event in normalize_timeline_events(person.get("timeline_events", [])):
            event_type = str(event.get("event_type", "") or "")

            if not event_visible_outside_person(event_type):
                continue

            event_date = str(event.get("date", "") or "")
            event_location_ids = [
                str(location_id or "").strip()
                for location_id in event.get("location_ids", [])
                if str(location_id or "").strip()
                in locations_by_record_id
            ]

            if not event_location_ids:
                location_name = location_at_date(person, event_date)
                location = known_locations.get(
                    normalize_location(location_name)
                )

                if location is not None:
                    event_location_ids.append(
                        str(location.get("record_id", "") or "").strip()
                    )

            if not event_location_ids or not event_date:
                continue

            detail = str(event.get("detail", "") or "").strip()
            title = (
                f"{person_name} was born"
                if event_type == "born"
                else f"{person_name} married {detail}"
                if detail
                and event_type == "got_married"
                else f"{person_name} got married"
                if event_type == "got_married"
                else f"{person_name}: {timeline_event_summary(event)}"
            )
            unique_key = (
                person_id,
                event_type,
                event_date,
                str(event.get("time", "") or ""),
                detail.casefold(),
            )

            if unique_key in seen_events:
                continue

            seen_events.add(unique_key)
            generated_events.append(
                {
                    "event_id": f"mage:{person_id}:{event.get('event_id', '')}",
                    "date": event_date,
                    "time": str(event.get("time", "") or ""),
                    "title": title,
                    "note": str(event.get("note", "") or "").strip(),
                    "origin_location_id": event_location_ids[0],
                    "location_ids": event_location_ids,
                    "related_person_id": person_id,
                    "person_ids": list(
                        dict.fromkeys(
                            [
                                person_id,
                                *event.get("person_ids", []),
                            ]
                        )
                    ),
                    "event_type": event_type,
                    "famous_person": bool(person.get("famous_person")),
                    "event_kind": "mage",
                }
            )

        for relationship in normalize_spouse_relationships(
            person.get("spouse_relationships", [])
        ):
            mate_id = relationship["person_id"]

            if not relationship["married"] or person_id >= mate_id:
                continue

            mate = people_by_id.get(mate_id)

            if mate is None:
                continue

            marriage_date = format_date_parts(
                relationship.get("marriage_year"),
                relationship.get("marriage_month"),
                relationship.get("marriage_day"),
                unknown="",
            )
            location_name = location_at_date(person, marriage_date)
            location = known_locations.get(normalize_location(location_name))

            if location is None:
                continue

            mate_name = str(
                mate.get("displayed_name", "") or "Unnamed magician"
            ).strip()
            couple_names = sorted((person_name, mate_name), key=str.casefold)
            unique_key = (
                "spouse_relationship",
                tuple(sorted((person_id, mate_id))),
                marriage_date,
            )

            if unique_key in seen_events:
                continue

            seen_events.add(unique_key)
            generated_events.append(
                {
                    "event_id": f"marriage:{person_id}:{mate_id}",
                    "date": marriage_date,
                    "title": f"{couple_names[0]} married {couple_names[1]}",
                    "note": "",
                    "origin_location_id": location.get("record_id", ""),
                    "related_person_id": person_id,
                    "person_ids": [person_id, mate_id],
                    "event_type": "got_married",
                    "famous_person": bool(
                        person.get("famous_person")
                        or mate.get("famous_person")
                    ),
                    "event_kind": "mage",
                }
            )

    return generated_events


def visible_location_timeline(
    location_id,
    locations,
    people,
    world_events=None,
):
    selected_id = str(location_id or "").strip()
    visible_origins = ancestor_locations(selected_id, locations)
    person_events = person_location_events(people, locations)
    visible_events = []
    distances_by_id = {
        str(location.get("record_id", "") or ""): distance
        for distance, location in enumerate(visible_origins)
    }

    for propagation_distance, origin in enumerate(visible_origins):
        origin_id = str(origin.get("record_id", "") or "").strip()
        origin_name = str(origin.get("name", "") or "Unnamed").strip()
        origin_depth = location_depth(origin_id, locations)

        for event in normalize_location_events(origin.get("timeline_events", [])):
            if not event_visible_outside_person(event.get("event_type")):
                continue

            visible_event = deepcopy(event)

            if visible_event.get("event_type") == "founding":
                visible_event["title"] = (
                    founding_event_title(origin_id, locations)
                    or visible_event.get("title", "")
                )

            visible_event.update(
                {
                    "origin_location_id": origin_id,
                    "origin_location_name": origin_name,
                    "source_level": origin_depth,
                    "propagation_distance": propagation_distance,
                    "event_kind": "location",
                    "related_person_id": "",
                }
            )
            visible_events.append(visible_event)

        for event in person_events:
            event_location_ids = list(
                event.get("location_ids", [])
                or [event.get("origin_location_id", "")]
            )
            closest_origin_id = closest_linked_location_id(
                event_location_ids,
                distances_by_id,
            )

            if closest_origin_id != origin_id:
                continue

            visible_event = deepcopy(event)
            visible_event.update(
                {
                    "origin_location_id": origin_id,
                    "origin_location_name": origin_name,
                    "source_level": origin_depth,
                    "propagation_distance": propagation_distance,
                }
            )
            visible_events.append(visible_event)

    visible_events.extend(
        world_events_for_location_timeline(
            selected_id,
            locations,
            world_events,
        )
    )
    visible_events.sort(key=location_event_sort_key)
    return visible_events


def world_events_for_location_timeline(
    location_id,
    locations,
    world_events,
):
    selected_id = str(location_id or "").strip()

    if not selected_id:
        return []

    visible_origins = ancestor_locations(selected_id, locations)
    origins_by_id = {
        str(location.get("record_id", "") or ""): location
        for location in visible_origins
    }
    distances_by_id = {
        str(location.get("record_id", "") or ""): distance
        for distance, location in enumerate(visible_origins)
    }
    visible_events = []

    for event in normalize_world_events(world_events or []):
        if not event_visible_outside_person(event.get("event_type")):
            continue

        linked_origin_ids = [
            location_id
            for location_id in event["location_ids"]
            if location_id in origins_by_id
        ]

        if not linked_origin_ids:
            continue

        origin_id = closest_linked_location_id(
            linked_origin_ids,
            distances_by_id,
        )
        origin = origins_by_id[origin_id]
        title = event["title"]

        if event.get("event_type") == "founding":
            title = (
                founding_event_title(origin_id, locations)
                or title
            )

        visible_events.append(
            {
                "event_id": event["record_id"],
                "record_id": event["record_id"],
                "date": event["date"],
                "time": event.get("time", ""),
                "title": title,
                "note": event["description"],
                "origin_location_id": origin_id,
                "origin_location_name": str(
                    origin.get("name", "") or "Unnamed"
                ).strip(),
                "source_level": location_depth(origin_id, locations),
                "propagation_distance": distances_by_id[origin_id],
                "event_kind": "global",
                "related_person_id": (
                    event["person_ids"][0]
                    if event["person_ids"]
                    else ""
                ),
                "person_ids": list(event["person_ids"]),
                "period_names": list(event["period_names"]),
                "location_ids": list(event["location_ids"]),
                "event_type": event["event_type"],
            }
        )

    return visible_events


def closest_linked_location_id(location_ids, distances_by_id):
    closest_id = ""
    closest_distance = None

    for location_id in location_ids:
        distance = distances_by_id.get(location_id)

        if distance is None:
            continue

        if closest_distance is None or distance < closest_distance:
            closest_id = location_id
            closest_distance = distance

    return closest_id


def location_events_for_period(
    start_year,
    end_year,
    location_id,
    locations,
    people,
    famous_people_only=False,
):
    try:
        normalized_start_year = int(start_year)
        normalized_end_year = int(end_year)
    except (TypeError, ValueError) as error:
        raise ValueError("The selected period does not have valid years.") from error

    if normalized_end_year < normalized_start_year:
        raise ValueError("The ending year cannot be earlier than the starting year.")

    records = locations_by_id(locations)
    selected_id = str(location_id or "").strip()

    if selected_id and selected_id not in records:
        raise ValueError("The selected location no longer exists.")

    if selected_id:
        visible_origin_ids = descendant_ids(selected_id, locations)
        visible_origin_ids.add(selected_id)
        selected_ancestors = ancestor_locations(selected_id, locations)
        ancestor_distances = {
            str(location.get("record_id", "") or ""): distance
            for distance, location in enumerate(selected_ancestors)
        }
        visible_origin_ids.update(ancestor_distances)
    else:
        visible_origin_ids = set(records)
        ancestor_distances = {}

    visible_events = []
    used_event_keys = set()

    for origin_id in visible_origin_ids:
        origin = records.get(origin_id)

        if origin is None:
            continue

        origin_name = str(origin.get("name", "") or "Unnamed").strip()
        source_level = location_depth(origin_id, locations)
        propagation_distance = ancestor_distances.get(origin_id, 0)

        for event in normalize_location_events(origin.get("timeline_events", [])):
            if not event_visible_outside_person(event.get("event_type")):
                continue

            event_year = location_event_year(event.get("date"))

            if (
                event_year is None
                or event_year < normalized_start_year
                or event_year > normalized_end_year
            ):
                continue

            event_key = (
                "location",
                origin_id,
                str(event.get("event_id", "") or ""),
            )

            if event_key in used_event_keys:
                continue

            used_event_keys.add(event_key)
            visible_event = deepcopy(event)

            if visible_event.get("event_type") == "founding":
                visible_event["title"] = (
                    founding_event_title(origin_id, locations)
                    or visible_event.get("title", "")
                )

            visible_event.update(
                {
                    "origin_location_id": origin_id,
                    "origin_location_name": origin_name,
                    "source_level": source_level,
                    "propagation_distance": propagation_distance,
                    "event_kind": "location",
                    "related_person_id": "",
                }
            )
            visible_events.append(visible_event)

    for event in person_location_events(people, locations):
        if famous_people_only and not bool(event.get("famous_person")):
            continue

        event_location_ids = [
            str(event_location_id or "").strip()
            for event_location_id in (
                event.get("location_ids", [])
                or [event.get("origin_location_id", "")]
            )
            if str(event_location_id or "").strip()
            in visible_origin_ids
        ]

        if not event_location_ids:
            continue

        origin_id = (
            closest_linked_location_id(
                event_location_ids,
                ancestor_distances,
            )
            or event_location_ids[0]
        )
        event_year = location_event_year(event.get("date"))

        if (
            event_year is None
            or event_year < normalized_start_year
            or event_year > normalized_end_year
        ):
            continue

        event_key = (
            "mage",
            origin_id,
            str(event.get("event_id", "") or ""),
        )

        if event_key in used_event_keys:
            continue

        used_event_keys.add(event_key)
        visible_event = deepcopy(event)
        visible_event.update(
            {
                "origin_location_name": str(
                    records.get(origin_id, {}).get("name", "") or "Unnamed"
                ).strip(),
                "source_level": location_depth(origin_id, locations),
                "propagation_distance": ancestor_distances.get(origin_id, 0),
            }
        )
        visible_events.append(visible_event)

    visible_events.sort(key=location_event_sort_key)
    return visible_events
