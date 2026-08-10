import uuid
from copy import deepcopy

from mage_maker.core.dates import format_date_parts, normalize_partial_date
from mage_maker.sections.development.models import (
    calculate_school_start_year,
    school_year_calendar_year,
)
from mage_maker.sections.events.types import (
    EVENT_LABEL_TYPES,
    EVENT_TYPE_LABELS,
    canonical_event_type,
    event_type_options,
)
from mage_maker.sections.events.models import (
    event_time_sort_key,
    normalize_association_values,
    normalize_job_event_metadata,
    normalize_world_event_time,
)


EVENT_TYPES = event_type_options("person", include_automatic=True)
DEATH_DATE_EVENT_SOURCE = "death_date"
SCHOOL_START_EVENT_SOURCE = "school_start"
DEATH_DATE_EVENT_ID = "automatic:death"
SCHOOL_START_EVENT_ID = "automatic:school-start"


def normalize_timeline_events(events):
    if events in (None, ""):
        return []

    if not isinstance(events, list):
        raise TypeError("Timeline events must be a list.")

    normalized_events = []
    seen_ids = set()

    for event in events:
        normalized_event = normalize_timeline_event(event)
        event_id = normalized_event["event_id"]

        if event_id in seen_ids:
            normalized_event["event_id"] = str(uuid.uuid4())

        seen_ids.add(normalized_event["event_id"])
        normalized_events.append(normalized_event)

    return sort_timeline_events(normalized_events)


def normalize_timeline_event(event):
    if not isinstance(event, dict):
        raise TypeError("Every timeline event must be an object.")

    normalized = deepcopy(event)
    normalized["event_id"] = str(normalized.get("event_id") or uuid.uuid4()).strip()
    normalized["event_type"] = canonical_event_type(
        normalized.get("event_type") or "custom"
    )
    normalized = normalize_job_event_metadata(normalized)
    normalized["detail"] = str(normalized.get("detail") or "").strip()
    normalized["date"] = normalize_event_date(normalized.get("date"))
    normalized["time"] = normalize_world_event_time(
        normalized.get("time")
    )
    normalized["note"] = str(normalized.get("note") or "").strip()
    normalized["related_person_id"] = str(
        normalized.get("related_person_id") or ""
    ).strip()
    normalized["related_name_entry_id"] = str(
        normalized.get("related_name_entry_id") or ""
    ).strip()
    normalized["automatic_source"] = str(
        normalized.get("automatic_source") or ""
    ).strip()

    if "person_ids" in normalized:
        normalized["person_ids"] = normalize_association_values(
            normalized.get("person_ids")
        )

    if "witness_person_ids" in normalized:
        normalized["witness_person_ids"] = normalize_association_values(
            normalized.get("witness_person_ids")
        )

    if "affected_person_ids" in normalized:
        normalized["affected_person_ids"] = normalize_association_values(
            normalized.get("affected_person_ids")
        )

    if normalized["event_type"] == "murder":
        normalized["perpetrator_person_ids"] = (
            normalize_association_values(
                normalized.get("perpetrator_person_ids")
            )
        )
        normalized["victim_person_ids"] = normalize_association_values(
            normalized.get("victim_person_ids")
        )
        normalized["witness_person_ids"] = normalize_association_values(
            normalized.get("witness_person_ids")
        )
        normalized["affected_person_ids"] = normalize_association_values(
            normalized.get("affected_person_ids")
        )
        normalized["person_ids"] = normalize_association_values(
            [
                *normalized["perpetrator_person_ids"],
                *normalized["victim_person_ids"],
                *normalized["witness_person_ids"],
                *normalized["affected_person_ids"],
            ]
        )
    else:
        normalized.pop("perpetrator_person_ids", None)
        normalized.pop("victim_person_ids", None)

    if (
        "location_ids" in normalized
        or "locked_location_ids" in normalized
    ):
        normalized["location_ids"] = normalize_association_values(
            normalized.get("location_ids")
        )
        normalized["locked_location_ids"] = normalize_association_values(
            normalized.get("locked_location_ids")
        )

        for location_id in normalized["locked_location_ids"]:
            if location_id not in normalized["location_ids"]:
                normalized["location_ids"].append(location_id)

    if normalized["event_type"] not in EVENT_TYPE_LABELS:
        normalized["event_type"] = "custom"

    if normalized["event_type"] == "custom" and not normalized["detail"]:
        raise ValueError("A custom timeline event needs an event description.")

    return normalized


def normalize_event_date(value):
    return normalize_partial_date(value, "Timeline date")


def sort_timeline_events(events):
    return sorted(
        deepcopy(list(events)),
        key=timeline_event_sort_key,
    )


def timeline_event_sort_key(event):
    event_type = str(event.get("event_type") or "custom")
    life_start_priority = {
        "starting_location": 0,
        "born": 1,
        "birth_name": 2,
    }.get(event_type)
    event_date = str(event.get("date") or "")

    if life_start_priority is not None:
        return (
            life_start_priority,
            0,
            0,
            0,
            event_time_sort_key(event.get("time")),
            str(event.get("event_id") or ""),
        )

    if not event_date:
        return (
            4,
            10000,
            13,
            32,
            event_time_sort_key(event.get("time")),
            str(event.get("event_id") or ""),
        )

    parts = [int(part) for part in event_date.split("-")]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 0
    day = parts[2] if len(parts) > 2 else 0
    return (
        3,
        year,
        month,
        day,
        event_time_sort_key(event.get("time")),
        str(event.get("event_id") or ""),
    )


def job_timeline_summary(event):
    event_type = str(event.get("event_type") or "started_job")
    action = (
        "Received a raise"
        if event_type == "received_raise"
        else "Started a job"
    )
    job_title = str(event.get("job_title") or "").strip()
    organization_name = str(
        event.get("organization_name") or ""
    ).strip()

    if (
        " (within " in organization_name
        and organization_name.endswith(")")
    ):
        organization_name = (
            organization_name[:-1].replace(" (within ", " within ", 1)
        )

    if job_title and organization_name:
        return f"{action} • {job_title} ({organization_name})"

    if job_title:
        return f"{action} • {job_title}"

    if organization_name:
        return f"{action} • {organization_name}"

    return action


def timeline_event_summary(event):
    event_type = str(event.get("event_type") or "custom")
    detail = str(event.get("detail") or "").strip()

    if event_type == "starting_location":
        return f"Starting location: {detail or 'Unknown'}"

    if event_type == "born":
        return "Born"

    if event_type == "birth_name":
        return f"Birth name: {detail}" if detail else "Birth name"

    if event_type == "gave_birth":
        return f"Gave birth to {detail}" if detail else "Gave birth"

    if event_type == "had_child":
        return "Had a child"

    if event_type == "got_married":
        return f"Marriage to {detail}" if detail else "Marriage"

    if event_type == "romance":
        return f"Romance: {detail}" if detail else "Romance"

    if event_type == "breakup":
        return f"Breakup: {detail}" if detail else "Breakup"

    if event_type == "travel":
        return f"Travel: {detail}" if detail else "Travel"

    if event_type == "died":
        return f"Death: {detail}" if detail else "Death"

    if event_type == "murder":
        return detail or "Murder"

    if event_type == "returns_as_ghost":
        return detail or "Returns as ghost"

    if event_type == "started_school":
        if event.get("automatic_source") == SCHOOL_START_EVENT_SOURCE:
            if event.get("started_late"):
                return (
                    f"Started at {detail} a bit late"
                    if detail
                    else "Started school a bit late"
                )

            return "Started school"

        return f"Started at {detail} school" if detail else "Started at school"

    if event_type == "opened_business":
        return (
            f"Opened a business: {detail}"
            if detail
            else "Opened a business"
        )

    if event_type == "started_job":
        return job_timeline_summary(event)

    if event_type == "received_raise":
        return job_timeline_summary(event)

    if event_type == "work_change":
        return (
            f"Change in work: {detail}"
            if detail
            else "Change in work"
        )

    if event_type == "relocated":
        return f"Relocated to {detail}" if detail else "Relocated"

    if event_type == "name_change":
        return f"Name change: {detail}" if detail else "Name change"

    return detail or "Custom event"


def timeline_detail_label(event_type):
    labels = {
        "starting_location": "Location",
        "born": "Birth detail",
        "birth_name": "Birth name",
        "gave_birth": "Child or event detail",
        "had_child": "Child's name",
        "got_married": "Spouse or event detail",
        "romance": "Romance detail",
        "breakup": "Breakup detail",
        "died": "Death detail",
        "murder": "Murder detail",
        "returns_as_ghost": "Ghost return detail",
        "started_school": "School name",
        "opened_business": "Business name",
        "started_job": "Job",
        "received_raise": "Job",
        "work_change": "New role, employer, or work change",
        "relocated": "New location",
        "travel": "Destination or travel detail",
        "name_change": "New name",
        "custom": "Event description",
    }
    return labels.get(event_type, "Event detail")


def murder_people_label(person_ids, people):
    people_by_id = {
        str(person.get("record_id", "") or "").strip(): str(
            person.get("displayed_name", "") or "Unnamed person"
        ).strip()
        for person in people or ()
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    names = [
        people_by_id.get(person_id, "Missing person")
        for person_id in normalize_association_values(person_ids)
    ]

    if len(names) == 1:
        return names[0]

    if len(names) == 2:
        return f"{names[0]} and {names[1]}"

    return f"{len(names)} people" if names else "no one"


def birth_timeline_summary(event, current_person_id, people):
    event_values = event if isinstance(event, dict) else {}
    selected_person_id = str(current_person_id or "").strip()
    baby_ids = normalize_association_values(
        event_values.get("baby_person_ids")
    )
    birthing_parent_ids = normalize_association_values(
        event_values.get("birthing_parent_person_ids")
    )
    non_birthing_parent_ids = normalize_association_values(
        event_values.get("non_birthing_parent_person_ids")
    )
    baby_label = murder_people_label(baby_ids, people)

    if selected_person_id in baby_ids:
        return "Born"

    if selected_person_id in birthing_parent_ids:
        return f"Bore a child: {baby_label}"

    if selected_person_id in non_birthing_parent_ids:
        return f"sired a child: {baby_label}"

    return str(event_values.get("title", "") or "Birth").strip()


def marriage_timeline_summary(event, current_person_id, people):
    event_values = event if isinstance(event, dict) else {}
    selected_person_id = str(current_person_id or "").strip()
    spouse_ids = [
        person_id
        for person_id in normalize_association_values(
            event_values.get("person_ids")
        )
        if person_id != selected_person_id
    ]

    if spouse_ids:
        return f"Married {murder_people_label(spouse_ids, people)}"

    return str(event_values.get("title", "") or "Marriage").strip()


def murder_timeline_summary(event, current_person_id, people):
    event_values = event if isinstance(event, dict) else {}
    selected_person_id = str(current_person_id or "").strip()
    perpetrator_ids = normalize_association_values(
        event_values.get("perpetrator_person_ids")
    )
    victim_ids = normalize_association_values(
        event_values.get("victim_person_ids")
    )
    witness_ids = normalize_association_values(
        event_values.get("witness_person_ids")
    )
    affected_ids = normalize_association_values(
        event_values.get("affected_person_ids")
    )

    if selected_person_id in perpetrator_ids:
        return f"Murders {murder_people_label(victim_ids, people)}"

    if selected_person_id in victim_ids:
        return (
            f"Murdered by {murder_people_label(perpetrator_ids, people)}"
        )

    if selected_person_id in witness_ids:
        return (
            "Witnessed the murder of "
            f"{murder_people_label(victim_ids, people)}"
        )

    if selected_person_id in affected_ids:
        return (
            "Affected by death of "
            f"{murder_people_label(victim_ids, people)}"
        )

    return str(event_values.get("title", "") or "Murder").strip()


def person_birth_timeline_date(person):
    if not isinstance(person, dict):
        return ""

    year = person.get("birth_year")
    month = person.get("birth_month")
    day = person.get("birth_day")

    if year in (None, ""):
        return ""

    date_parts = [str(year).zfill(4)]

    if month not in (None, ""):
        date_parts.append(str(month).zfill(2))

    if day not in (None, ""):
        date_parts.append(str(day).zfill(2))

    return "-".join(date_parts)


def automatic_child_timeline_event(child, existing_event=None):
    if not isinstance(child, dict):
        raise TypeError("A child timeline event needs a person record.")

    child_id = str(child.get("record_id", "") or "").strip()

    if not child_id:
        raise ValueError("A child timeline event needs a person identifier.")

    child_name = str(
        child.get("displayed_name", "") or "Unnamed child"
    ).strip()
    event = deepcopy(existing_event) if isinstance(existing_event, dict) else {}
    previous_detail = str(event.get("detail") or "").strip()
    previous_note = str(event.get("note") or "").strip()
    event.setdefault("event_id", f"had-child:{child_id}")

    if not previous_note or previous_note == f"Child: {previous_detail}":
        event["note"] = f"Child: {child_name}"

    event["event_type"] = "had_child"
    event["detail"] = child_name
    event["date"] = person_birth_timeline_date(child)
    event["related_person_id"] = child_id
    event["automatic_source"] = "child_assignment"
    return normalize_timeline_event(event)


def person_death_timeline_date(person):
    if not isinstance(person, dict):
        return ""

    if not bool(person.get("deceased")):
        return ""

    if person.get("death_year") in (None, ""):
        return ""

    return format_date_parts(
        person.get("death_year"),
        person.get("death_month"),
        person.get("death_day"),
        unknown="",
    )


def automatic_death_timeline_event(person, existing_event=None):
    death_date = person_death_timeline_date(person)

    if not death_date:
        return None

    event = deepcopy(existing_event) if isinstance(existing_event, dict) else {}
    event["event_id"] = str(
        event.get("event_id") or DEATH_DATE_EVENT_ID
    )
    event["event_type"] = "died"
    event["detail"] = str(event.get("detail", "") or "").strip()
    event["date"] = death_date
    event["note"] = str(event.get("note", "") or "").strip()
    event["related_person_id"] = ""
    event["automatic_source"] = DEATH_DATE_EVENT_SOURCE
    return normalize_timeline_event(event)


def first_attended_school_year(person):
    if not isinstance(person, dict):
        return None

    if bool(person.get("non_magical")):
        return None

    if not str(person.get("school", "") or "").strip():
        return None

    development_plan = person.get("development_plan")

    if not isinstance(development_plan, dict):
        return None

    school_year_records = development_plan.get("school_years", [])

    if not isinstance(school_year_records, list):
        return None

    attended_years = []

    for school_year_record in school_year_records:
        if not isinstance(school_year_record, dict):
            continue

        if bool(school_year_record.get("skipped", False)):
            continue

        try:
            school_year = int(school_year_record.get("year"))
        except (TypeError, ValueError):
            continue

        if 1 <= school_year <= 7:
            attended_years.append(school_year)

    if attended_years:
        return min(attended_years)

    if bool(development_plan.get("school_started")) and not school_year_records:
        return 1

    return None


def automatic_school_start_timeline_event(
    person,
    existing_event=None,
    organizations=None,
):
    first_school_year = first_attended_school_year(person)

    if first_school_year is None:
        return None

    academic_start_year = calculate_school_start_year(
        person.get("birth_year"),
        person.get("birth_month"),
        person.get("birth_day"),
    )
    calendar_year = school_year_calendar_year(
        academic_start_year,
        first_school_year,
    )

    if calendar_year is None:
        return None

    school_name = str(person.get("school", "") or "").strip()
    event = deepcopy(existing_event) if isinstance(existing_event, dict) else {}
    event["event_id"] = str(
        event.get("event_id") or SCHOOL_START_EVENT_ID
    )
    event["event_type"] = "started_school"
    event["detail"] = school_name
    event["date"] = format_date_parts(
        calendar_year,
        9,
        1,
        unknown="",
    )
    event["note"] = ""
    event["related_person_id"] = ""
    event["automatic_source"] = SCHOOL_START_EVENT_SOURCE
    event["school_year"] = first_school_year
    event["started_late"] = first_school_year > 1

    if organizations is not None:
        location_ids = []
        normalized_school_name = school_name.casefold()

        for organization in organizations or ():
            if not isinstance(organization, dict):
                continue

            organization_name = str(
                organization.get("name", "") or ""
            ).strip()
            organization_type = str(
                organization.get("organization_type", "") or ""
            ).strip()

            if (
                organization_type.casefold() != "school"
                or organization_name.casefold()
                != normalized_school_name
            ):
                continue

            location_id = str(
                organization.get("campus_location_id", "")
                or organization.get("location_id", "")
                or ""
            ).strip()

            if location_id:
                location_ids.append(location_id)

            break

        event["location_ids"] = location_ids
        event["locked_location_ids"] = list(location_ids)

    return normalize_timeline_event(event)


def synchronize_profile_timeline_events(
    person,
    timeline_events=None,
    create_death_event=True,
    organizations=None,
):
    person_values = person if isinstance(person, dict) else {}
    source_events = normalize_timeline_events(
        person_values.get("timeline_events", [])
        if timeline_events is None
        else timeline_events
    )
    automatic_events = {}
    retained_events = []
    has_profile_death_date = bool(
        person_death_timeline_date(person_values)
    )

    for event in source_events:
        automatic_source = str(
            event.get("automatic_source", "") or ""
        ).strip()

        if automatic_source == DEATH_DATE_EVENT_SOURCE:
            automatic_events.setdefault(automatic_source, event)
            continue

        if (
            has_profile_death_date
            and event.get("event_type") == "died"
        ):
            automatic_events.setdefault(DEATH_DATE_EVENT_SOURCE, event)
            continue

        if automatic_source == SCHOOL_START_EVENT_SOURCE:
            automatic_events.setdefault(automatic_source, event)
            continue

        retained_events.append(event)

    death_event = (
        automatic_death_timeline_event(
            person_values,
            automatic_events.get(DEATH_DATE_EVENT_SOURCE),
        )
        if create_death_event
        else None
    )
    school_event = automatic_school_start_timeline_event(
        person_values,
        automatic_events.get(SCHOOL_START_EVENT_SOURCE),
        organizations,
    )

    if death_event is not None:
        retained_events.append(death_event)

    if school_event is not None:
        retained_events.append(school_event)

    return normalize_timeline_events(retained_events)
