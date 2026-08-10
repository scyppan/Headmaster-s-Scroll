from copy import deepcopy

from mage_maker.sections.names.history import normalize_name_details
from mage_maker.sections.timeline.events import (
    normalize_timeline_event,
    normalize_timeline_events,
)


NAME_CHANGE_EVENT_SOURCE = "name_change"


def is_name_change_entry(entry):
    if not isinstance(entry, dict):
        return False

    name_type = " ".join(
        str(entry.get("name_type", "") or "").strip().casefold().split()
    )
    return name_type not in ("birth name", "birthname")


def synchronize_name_change_events(name_details, timeline_events):
    details = normalize_name_details(name_details)
    events = normalize_timeline_events(timeline_events)
    dated_entries = [
        entry
        for entry in details["entries"]
        if is_name_change_entry(entry) and entry.get("date")
    ]
    entry_ids = {entry["entry_id"] for entry in dated_entries}
    retained_events = [
        deepcopy(event)
        for event in events
        if not (
            event.get("automatic_source") == NAME_CHANGE_EVENT_SOURCE
            and str(event.get("related_name_entry_id", "") or "") not in entry_ids
        )
    ]

    for entry in dated_entries:
        entry_id = entry["entry_id"]
        matching_event = next(
            (
                event
                for event in retained_events
                if event.get("automatic_source") == NAME_CHANGE_EVENT_SOURCE
                and str(event.get("related_name_entry_id", "") or "") == entry_id
            ),
            None,
        )
        event_values = deepcopy(matching_event) if matching_event is not None else {}
        event_values.update(
            {
                "event_id": str(
                    event_values.get("event_id") or f"name-change:{entry_id}"
                ),
                "event_type": "name_change",
                "detail": entry["name_entry"],
                "date": entry["date"],
                "note": entry["note"],
                "related_person_id": "",
                "related_name_entry_id": entry_id,
                "automatic_source": NAME_CHANGE_EVENT_SOURCE,
            }
        )
        synchronized_event = normalize_timeline_event(event_values)

        if matching_event is None:
            retained_events.append(synchronized_event)
        else:
            retained_events[retained_events.index(matching_event)] = synchronized_event

    return normalize_timeline_events(retained_events)


def name_entry_for_timeline_event(name_details, event):
    details = normalize_name_details(name_details)
    event_values = event if isinstance(event, dict) else {}
    related_entry_id = str(
        event_values.get("related_name_entry_id", "") or ""
    ).strip()

    for entry in details["entries"]:
        if entry["entry_id"] == related_entry_id:
            return deepcopy(entry)

    return None
