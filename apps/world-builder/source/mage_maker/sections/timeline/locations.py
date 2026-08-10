from copy import deepcopy

from mage_maker.sections.events.models import event_time_sort_key
from mage_maker.sections.names.history import birth_name_entry
from mage_maker.sections.timeline.events import (
    normalize_timeline_event,
    normalize_timeline_events,
    person_birth_timeline_date,
)


LONG_DISTANCE_NOTE = "Father not present at time of birth."
LEGACY_LONG_DISTANCE_NOTE = (
    "Their parents were in a long distance relationship."
)
PRESERVE_PARENT_LOCATION_OVERRIDE = object()
LIFE_START_SOURCE = "life_start"
STARTING_LOCATION_EVENT_ID = "life-start:starting-location"
BORN_EVENT_ID = "life-start:born"
BIRTH_NAME_EVENT_ID = "life-start:birth-name"


class ParentLocationConflict(ValueError):
    def __init__(
        self,
        child_name,
        birthing_parent_name,
        birthing_parent_location,
        non_birthing_parent_name,
        non_birthing_parent_location,
        parent_ids,
    ):
        self.child_name = str(child_name or "This child").strip()
        self.birthing_parent_name = str(
            birthing_parent_name or "The birthing parent"
        ).strip()
        self.birthing_parent_location = str(
            birthing_parent_location or "Unknown"
        ).strip()
        self.non_birthing_parent_name = str(
            non_birthing_parent_name or "The non-birthing parent"
        ).strip()
        self.non_birthing_parent_location = str(
            non_birthing_parent_location or "Unknown"
        ).strip()
        self.parent_ids = [
            str(parent_id or "").strip()
            for parent_id in parent_ids
            if str(parent_id or "").strip()
        ]
        super().__init__(
            f"{self.birthing_parent_name} is in "
            f"{self.birthing_parent_location}, while "
            f"{self.non_birthing_parent_name} is in "
            f"{self.non_birthing_parent_location} when {self.child_name} is born."
        )


def ensure_life_start_events(
    person,
    starting_location=None,
    born_note=None,
    long_distance_parent_ids=PRESERVE_PARENT_LOCATION_OVERRIDE,
    starting_location_id=None,
):
    person_values = person if isinstance(person, dict) else {}
    events = normalize_timeline_events(person_values.get("timeline_events", []))
    starting_event = first_event_of_type(events, "starting_location")
    born_event = first_event_of_type(events, "born")
    birth_name_event = first_event_of_type(events, "birth_name")
    retained_events = [
        deepcopy(event)
        for event in events
        if event.get("event_type") not in (
            "starting_location",
            "born",
            "birth_name",
        )
        and event.get("automatic_source") != LIFE_START_SOURCE
    ]
    birth_date = person_birth_timeline_date(person_values)
    resolved_starting_location = (
        str(starting_location or "").strip()
        if starting_location is not None
        else str(
            (starting_event or {}).get("detail", "") or ""
        ).strip()
    )
    resolved_born_note = (
        str(born_note or "").strip()
        if born_note is not None
        else str((born_event or {}).get("note", "") or "").strip()
    )
    starting_values = deepcopy(starting_event) if starting_event else {}
    starting_values.update(
        {
            "event_id": str(
                starting_values.get("event_id")
                or STARTING_LOCATION_EVENT_ID
            ),
            "event_type": "starting_location",
            "detail": resolved_starting_location,
            "date": birth_date,
            "note": str(starting_values.get("note", "") or "").strip(),
            "related_person_id": "",
            "automatic_source": LIFE_START_SOURCE,
        }
    )
    born_values = deepcopy(born_event) if born_event else {}
    born_values.update(
        {
            "event_id": str(born_values.get("event_id") or BORN_EVENT_ID),
            "event_type": "born",
            "detail": "",
            "date": birth_date,
            "note": resolved_born_note,
            "related_person_id": "",
            "automatic_source": LIFE_START_SOURCE,
        }
    )

    if starting_location_id is not None:
        normalized_location_id = str(
            starting_location_id or ""
        ).strip()
        selected_location_ids = (
            [normalized_location_id]
            if normalized_location_id
            else []
        )

        for opening_event in (starting_values, born_values):
            opening_event["location_ids"] = selected_location_ids
            opening_event["locked_location_ids"] = []

            if normalized_location_id:
                opening_event["birth_location_source"] = "manual"
            else:
                opening_event.pop("birth_location_source", None)

    explicit_birth_name = birth_name_entry(person_values.get("name_details", {}))
    birth_name_values = deepcopy(birth_name_event) if birth_name_event else {}
    birth_name_values.update(
        {
            "event_id": str(
                birth_name_values.get("event_id") or BIRTH_NAME_EVENT_ID
            ),
            "event_type": "birth_name",
            "detail": str(
                (explicit_birth_name or {}).get("name_entry", "")
                or person_values.get("displayed_name", "")
                or "Unnamed magician"
            ).strip(),
            "date": birth_date,
            "note": str(
                (explicit_birth_name or {}).get("note", "") or ""
            ).strip(),
            "related_person_id": "",
            "related_name_entry_id": str(
                (explicit_birth_name or {}).get("entry_id", "") or ""
            ).strip(),
            "automatic_source": LIFE_START_SOURCE,
        }
    )

    if long_distance_parent_ids is PRESERVE_PARENT_LOCATION_OVERRIDE:
        resolved_parent_location_override_ids = (
            born_long_distance_parent_ids([born_values])
        )
    else:
        resolved_parent_location_override_ids = sorted(
            {
                str(parent_id or "").strip()
                for parent_id in long_distance_parent_ids
                if str(parent_id or "").strip()
            }
        )

    if resolved_parent_location_override_ids:
        born_values["parent_location_override_ids"] = (
            resolved_parent_location_override_ids
        )
        born_values.pop("long_distance_parent_ids", None)
    else:
        born_values.pop("parent_location_override_ids", None)
        born_values.pop("long_distance_parent_ids", None)

    return normalize_timeline_events(
        [
            normalize_timeline_event(starting_values),
            normalize_timeline_event(born_values),
            normalize_timeline_event(birth_name_values),
            *retained_events,
        ]
    )


def first_event_of_type(events, event_type):
    for event in events if isinstance(events, list) else []:
        if isinstance(event, dict) and event.get("event_type") == event_type:
            return deepcopy(event)

    return None


def starting_location_from_events(events):
    event = first_event_of_type(
        normalize_timeline_events(events),
        "starting_location",
    )
    return str((event or {}).get("detail", "") or "").strip()


def born_note_from_events(events):
    event = first_event_of_type(normalize_timeline_events(events), "born")
    return str((event or {}).get("note", "") or "").strip()


def born_long_distance_parent_ids(events):
    event = first_event_of_type(normalize_timeline_events(events), "born")
    values = (event or {}).get("parent_location_override_ids")

    if values is None:
        values = (event or {}).get("long_distance_parent_ids", [])

    if not isinstance(values, list):
        return []

    return sorted(
        {
            str(parent_id or "").strip()
            for parent_id in values
            if str(parent_id or "").strip()
        }
    )


def child_parent_location_context(
    child,
    people,
    shared_events=None,
    locations=None,
):
    child_values = child if isinstance(child, dict) else {}
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people if isinstance(person, dict)
        if str(person.get("record_id", "") or "").strip()
    }
    birthing_parent_id = str(
        child_values.get("biological_mother_id", "") or ""
    ).strip()
    non_birthing_parent_id = str(
        child_values.get("biological_father_id", "") or ""
    ).strip()
    birthing_parent = people_by_id.get(birthing_parent_id)
    non_birthing_parent = people_by_id.get(non_birthing_parent_id)
    child_birth_date = person_birth_timeline_date(child_values)
    birthing_location = location_at_date(
        birthing_parent,
        child_birth_date,
        shared_events,
        locations,
    )
    non_birthing_location = location_at_date(
        non_birthing_parent,
        child_birth_date,
        shared_events,
        locations,
    )
    conflict = bool(
        birthing_location
        and non_birthing_location
        and normalize_location(birthing_location)
        != normalize_location(non_birthing_location)
    )
    inherited_location = ""

    if birthing_location:
        inherited_location = birthing_location
    elif non_birthing_location:
        inherited_location = non_birthing_location

    return {
        "birthing_parent_id": birthing_parent_id,
        "birthing_parent_name": str(
            (birthing_parent or {}).get("displayed_name", "")
            or "The birthing parent"
        ).strip(),
        "birthing_location": birthing_location,
        "non_birthing_parent_id": non_birthing_parent_id,
        "non_birthing_parent_name": str(
            (non_birthing_parent or {}).get("displayed_name", "")
            or "The non-birthing parent"
        ).strip(),
        "non_birthing_location": non_birthing_location,
        "parent_ids": sorted(
            parent_id
            for parent_id in (birthing_parent_id, non_birthing_parent_id)
            if parent_id
        ),
        "conflict": conflict,
        "inherited_location": inherited_location,
    }


def location_at_date(
    person,
    target_date,
    shared_events=None,
    locations=None,
):
    if not isinstance(person, dict):
        return ""

    events = normalize_timeline_events(person.get("timeline_events", []))
    person_id = str(person.get("record_id", "") or "").strip()
    location_names_by_id = {
        str(location.get("record_id", "") or "").strip(): str(
            location.get("name", "") or ""
        ).strip()
        for location in locations or []
        if isinstance(location, dict)
        and str(location.get("record_id", "") or "").strip()
    }

    for shared_event in shared_events or []:
        if (
            not isinstance(shared_event, dict)
            or shared_event.get("event_type") != "relocated"
            or person_id not in shared_event.get("person_ids", [])
        ):
            continue

        location_ids = [
            str(location_id or "").strip()
            for location_id in shared_event.get("location_ids", [])
            if str(location_id or "").strip()
        ]
        location_name = (
            location_names_by_id.get(location_ids[-1], "")
            if location_ids
            else ""
        )

        if not location_name:
            location_name = str(
                shared_event.get("title", "") or ""
            ).strip()

            for prefix in ("Relocated to ", "Relocated: ", "Relocated "):
                if location_name.casefold().startswith(prefix.casefold()):
                    location_name = location_name[len(prefix):].strip()
                    break

        if location_name:
            events.append(
                {
                    "event_id": str(
                        shared_event.get("record_id", "") or ""
                    ),
                    "event_type": "relocated",
                    "detail": location_name,
                    "date": str(shared_event.get("date", "") or ""),
                    "time": str(shared_event.get("time", "") or ""),
                    "note": "",
                }
            )

    location_events = [
        event
        for event in events
        if event.get("event_type") in ("starting_location", "relocated")
        and str(event.get("detail", "") or "").strip()
    ]

    if not location_events:
        return ""

    target_key = approximate_date_key(target_date, use_period_end=True)
    eligible_events = []

    for index, event in enumerate(location_events):
        event_key = approximate_date_key(event.get("date"), use_period_end=False)

        if target_key is None or event_key is None or event_key <= target_key:
            eligible_events.append((event_key, index, event))

    if eligible_events:
        eligible_events.sort(key=location_event_sort_key)
        return str(eligible_events[-1][2].get("detail", "") or "").strip()

    starting_event = first_event_of_type(location_events, "starting_location")

    if starting_event is not None:
        return str(starting_event.get("detail", "") or "").strip()

    return ""


def approximate_date_key(value, use_period_end=False):
    date_text = str(value or "").strip()

    if not date_text:
        return None

    try:
        parts = [int(part) for part in date_text.split("-")]
    except (TypeError, ValueError):
        return None

    if not parts or not 1 <= parts[0] <= 9999:
        return None

    month = parts[1] if len(parts) > 1 else (12 if use_period_end else 1)
    day = parts[2] if len(parts) > 2 else (31 if use_period_end else 1)
    return parts[0], month, day


def location_event_sort_key(item):
    event_key, index, event = item
    return (
        event_key is not None,
        event_key or (0, 0, 0),
        0 if event.get("event_type") == "starting_location" else 1,
        event_time_sort_key(event.get("time")),
        index,
    )


def normalize_location(value):
    return " ".join(str(value or "").strip().casefold().split())


def add_long_distance_note(note):
    existing_note = remove_long_distance_note(note)

    if not existing_note:
        return LONG_DISTANCE_NOTE

    return f"{existing_note}\n\n{LONG_DISTANCE_NOTE}"


def remove_long_distance_note(note):
    note_text = str(note or "").strip()

    if not note_text:
        return ""

    retained_parts = [
        part.strip()
        for part in note_text.split("\n\n")
        if part.strip().casefold()
        not in (
            LONG_DISTANCE_NOTE.casefold(),
            LEGACY_LONG_DISTANCE_NOTE.casefold(),
        )
    ]
    return "\n\n".join(retained_parts)
