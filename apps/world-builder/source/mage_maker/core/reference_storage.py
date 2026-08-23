"""Compact reference storage for canonical World Builder records.

The UI historically kept a second copy of profile timeline events inside every
person.  Canonical events now live only in ``world.events``; people retain
stable IDs and optional per-person overrides.  This module is intentionally
free of Tk dependencies so migrations and tests can use the same rules.
"""

from copy import deepcopy
import hashlib

from mage_maker.sections.events.models import (
    event_linked_person_ids,
    normalize_world_event,
)
from mage_maker.sections.timeline.events import normalize_timeline_events


DERIVED_PROFILE_EVENT_TYPES = {
    "starting_location",
    "born",
    "birth_name",
    "started_school",
}
DERIVED_PROFILE_SOURCES = {
    "life_start",
    "birth_date",
    "starting_location",
    "school_start",
    "death_date",
}


def colored_tag_record_id(tag):
    """Return a stable identity for one reusable colored profile tag."""
    text = str((tag or {}).get("text", "") or "").strip()
    background = str(
        (tag or {}).get("background_color", "") or ""
    ).strip().lower()
    digest = hashlib.sha1(
        f"{text.casefold()}|{background}".encode("utf-8")
    ).hexdigest()[:24]
    return f"person-tag:{digest}"


def externalize_person_support_records(database):
    """Move repeated/large person support fields into indexed collections."""
    if not isinstance(database, dict):
        return False
    people = database.get("people", []) or []
    tag_catalog = {
        str(record.get("record_id", "") or "").strip(): record
        for record in database.setdefault("person_tag_catalog", [])
        if isinstance(record, dict)
        and str(record.get("record_id", "") or "").strip()
    }
    legacy_imports = {
        str(record.get("record_id", "") or "").strip(): record
        for record in database.setdefault("legacy_person_imports", [])
        if isinstance(record, dict)
        and str(record.get("record_id", "") or "").strip()
    }
    changed = False
    for person in people:
        if not isinstance(person, dict):
            continue
        person_id = str(person.get("record_id", "") or "").strip()
        if not person_id:
            continue
        if "tags" in person:
            tag_ids = []
            for raw_tag in person.get("tags", []) or []:
                if not isinstance(raw_tag, dict):
                    continue
                text = str(raw_tag.get("text", "") or "").strip()
                if not text:
                    continue
                record_id = colored_tag_record_id(raw_tag)
                tag_catalog[record_id] = {
                    "record_id": record_id,
                    "text": text,
                    "background_color": str(
                        raw_tag.get("background_color", "") or ""
                    ).strip(),
                }
                if record_id not in tag_ids:
                    tag_ids.append(record_id)
            person["tag_ids"] = tag_ids
            person.pop("tags", None)
            changed = True
        if "imported_fields" in person:
            imported_fields = person.pop("imported_fields", None)
            if isinstance(imported_fields, dict) and imported_fields:
                record_id = f"legacy-import:{person_id}"
                legacy_imports[record_id] = {
                    "record_id": record_id,
                    "person_id": person_id,
                    "fields": deepcopy(imported_fields),
                }
                person["legacy_import_id"] = record_id
            else:
                person.pop("legacy_import_id", None)
            changed = True
    normalized_tags = sorted(
        tag_catalog.values(), key=lambda item: item["record_id"]
    )
    normalized_imports = sorted(
        legacy_imports.values(), key=lambda item: item["record_id"]
    )
    if database.get("person_tag_catalog") != normalized_tags:
        database["person_tag_catalog"] = normalized_tags
        changed = True
    if database.get("legacy_person_imports") != normalized_imports:
        database["legacy_person_imports"] = normalized_imports
        changed = True
    return changed


def normalize_event_references(value):
    """Return unique event IDs from either new or legacy reference shapes."""
    candidates = value if isinstance(value, (list, tuple)) else []
    references = []
    seen = set()
    for candidate in candidates:
        event_id = str(
            candidate.get("event_id", "")
            if isinstance(candidate, dict)
            else candidate
        ).strip()
        if event_id and event_id not in seen:
            seen.add(event_id)
            references.append(event_id)
    return references


def compact_reference(value, id_fields=("record_id", "book_id")):
    """Keep only a stable ID, retaining labels solely for unresolved legacy data."""
    if isinstance(value, str):
        text = value.strip()
        return {"name": text} if text else None
    if not isinstance(value, dict):
        return None
    for field_name in id_fields:
        record_id = str(value.get(field_name, "") or "").strip()
        if record_id:
            return {"record_id": record_id}
    name = str(
        value.get("name") or value.get("title") or value.get("book_title") or ""
    ).strip()
    author = str(value.get("author") or value.get("author_name") or "").strip()
    if not name:
        return None
    result = {"name": name}
    if author:
        result["author"] = author
    return result


def compact_development_book_references(person):
    """Replace development-plan book snapshots with stable references."""
    normalized = deepcopy(person)
    plan = normalized.get("development_plan")
    if not isinstance(plan, dict):
        return normalized
    for section_name in ("school_years", "adult_years"):
        for year in plan.get(section_name, []) or []:
            if not isinstance(year, dict):
                continue
            for field_name in ("assigned_books", "books"):
                compact = []
                seen = set()
                for value in year.get(field_name, []) or []:
                    reference = compact_reference(value)
                    if not reference:
                        continue
                    identity = reference.get("record_id") or (
                        str(reference.get("name", "")).casefold(),
                        str(reference.get("author", "")).casefold(),
                    )
                    if identity in seen:
                        continue
                    seen.add(identity)
                    compact.append(reference)
                year[field_name] = compact
    normalized["development_plan"] = plan
    return normalized


def is_derived_timeline_event(event):
    event_type = str(event.get("event_type", "") or "").strip()
    source = str(event.get("automatic_source", "") or "").strip()
    return event_type in DERIVED_PROFILE_EVENT_TYPES or source in DERIVED_PROFILE_SOURCES


def profile_event_record_id(person_id, timeline_event_id):
    digest = hashlib.sha1(
        f"{person_id}|{timeline_event_id}".encode("utf-8")
    ).hexdigest()[:24]
    return f"profile-event:{digest}"


def timeline_event_to_world(person_id, event, record_id=None):
    """Convert one non-derived profile event to its canonical world record."""
    normalized = normalize_timeline_events([event])[0]
    canonical_id = str(
        record_id
        or normalized.get("_canonical_event_id")
        or profile_event_record_id(person_id, normalized["event_id"])
    ).strip()
    linked_people = [
        str(value or "").strip()
        for value in normalized.get("person_ids", []) or []
        if str(value or "").strip()
    ]
    if person_id not in linked_people:
        linked_people.insert(0, person_id)
    event_type = str(normalized.get("event_type", "custom") or "custom")
    title = str(normalized.get("detail", "") or "").strip()
    if not title:
        title = event_type.replace("_", " ").title()
    world = {
        "record_id": canonical_id,
        "event_type": event_type,
        "title": title,
        "date": normalized.get("date", ""),
        "time": normalized.get("time", ""),
        "description": normalized.get("note", ""),
        "person_ids": linked_people,
        "location_ids": normalized.get("location_ids", []),
        "locked_location_ids": normalized.get("locked_location_ids", []),
        "profile_owner_person_id": person_id,
        "profile_timeline_event_id": normalized["event_id"],
        "profile_timeline_event_type": event_type,
        "profile_related_person_id": normalized.get("related_person_id", ""),
        "profile_related_name_entry_id": normalized.get(
            "related_name_entry_id", ""
        ),
        "profile_automatic_source": normalized.get("automatic_source", ""),
    }
    for field_name in (
        "witness_person_ids",
        "affected_person_ids",
        "perpetrator_person_ids",
        "victim_person_ids",
        "unnamed_muggle_victim_count",
        "unnamed_mage_victim_count",
    ):
        if field_name in normalized:
            world[field_name] = normalized[field_name]
    return normalize_world_event(world)


def world_event_to_timeline(event, person_id, overrides=None):
    """Hydrate a canonical profile event for the legacy timeline editor."""
    if not isinstance(event, dict):
        return None
    owner_id = str(event.get("profile_owner_person_id", "") or "").strip()
    timeline_id = str(event.get("profile_timeline_event_id", "") or "").strip()
    if owner_id != str(person_id or "").strip() or not timeline_id:
        return None
    value = {
        "event_id": timeline_id,
        "event_type": event.get("profile_timeline_event_type")
        or event.get("event_type")
        or "custom",
        "detail": event.get("title", ""),
        "date": event.get("date", ""),
        "time": event.get("time", ""),
        "note": event.get("description", ""),
        "related_person_id": event.get("profile_related_person_id", ""),
        "related_name_entry_id": event.get(
            "profile_related_name_entry_id", ""
        ),
        "automatic_source": event.get("profile_automatic_source", ""),
        "person_ids": event.get("person_ids", []),
        "location_ids": event.get("location_ids", []),
        "locked_location_ids": event.get("locked_location_ids", []),
        "witness_person_ids": event.get("witness_person_ids", []),
        "affected_person_ids": event.get("affected_person_ids", []),
        "perpetrator_person_ids": event.get("perpetrator_person_ids", []),
        "victim_person_ids": event.get("victim_person_ids", []),
        "unnamed_muggle_victim_count": event.get(
            "unnamed_muggle_victim_count",
            0,
        ),
        "unnamed_mage_victim_count": event.get(
            "unnamed_mage_victim_count",
            0,
        ),
        "_canonical_event_id": event.get("record_id", ""),
    }
    if isinstance(overrides, dict):
        value.update(deepcopy(overrides))
    return normalize_timeline_events([value])[0]


def migrate_person_event_references(database):
    """Externalize embedded person timelines and rebuild compact references."""
    people = database.get("people", []) if isinstance(database, dict) else []
    events = database.get("events", []) if isinstance(database, dict) else []
    normalized_events = [
        normalize_world_event(event)
        for event in events
        if isinstance(event, dict)
    ]
    events_by_id = {event["record_id"]: event for event in normalized_events}
    changed = False

    for person in people:
        if not isinstance(person, dict):
            continue
        person_id = str(person.get("record_id", "") or "").strip()
        if not person_id:
            continue
        refs = normalize_event_references(person.get("event_refs", []))
        has_canonical_death = any(
            event_id in events_by_id
            and str(events_by_id[event_id].get("event_type", ""))
            in ("died", "murder")
            for event_id in refs
        ) or any(
            person_id in event_linked_person_ids(event)
            and str(event.get("event_type", "")) in ("died", "murder")
            for event in events_by_id.values()
        )
        for timeline_event in normalize_timeline_events(
            person.get("timeline_events", [])
        ):
            if is_derived_timeline_event(timeline_event):
                if (
                    timeline_event.get("event_type") == "died"
                    and not has_canonical_death
                    and str(timeline_event.get("date", "") or "").strip()
                ):
                    canonical = timeline_event_to_world(
                        person_id, timeline_event
                    )
                    canonical.pop("profile_owner_person_id", None)
                    canonical.pop("profile_timeline_event_id", None)
                    canonical.pop("profile_timeline_event_type", None)
                    canonical.pop("profile_related_person_id", None)
                    canonical.pop("profile_related_name_entry_id", None)
                    canonical.pop("profile_automatic_source", None)
                    events_by_id[canonical["record_id"]] = canonical
                    refs.append(canonical["record_id"])
                    has_canonical_death = True
                continue
            canonical = timeline_event_to_world(person_id, timeline_event)
            events_by_id[canonical["record_id"]] = canonical
            if canonical["record_id"] not in refs:
                refs.append(canonical["record_id"])
        compacted = compact_development_book_references(person)
        person.clear()
        person.update(compacted)
        if "timeline_events" in person:
            person.pop("timeline_events", None)
            changed = True
        person["event_refs"] = refs

    # Every canonical event is discoverable through the linked person's small
    # reference list.  The event remains authoritative for all shared fields.
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in people
        if isinstance(person, dict)
    }
    for event in events_by_id.values():
        for person_id in event_linked_person_ids(event):
            person = people_by_id.get(person_id)
            if person is None:
                continue
            refs = normalize_event_references(person.get("event_refs", []))
            if event["record_id"] not in refs:
                refs.append(event["record_id"])
                person["event_refs"] = refs
                changed = True

    migrated_events = list(events_by_id.values())
    migrated_events.sort(key=lambda event: (
        str(event.get("date", "")),
        str(event.get("time", "")),
        str(event.get("record_id", "")),
    ))
    if migrated_events != events:
        database["events"] = migrated_events
        changed = True
    return changed
