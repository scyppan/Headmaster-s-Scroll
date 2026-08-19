import re
import uuid
from copy import deepcopy

from mage_maker.core.wizarding_currency import normalize_monthly_salary
from mage_maker.sections.events.types import (
    EVENT_LABEL_TYPES,
    EVENT_TYPE_LABELS,
    canonical_event_type,
    event_type_label,
    event_type_options,
)
from mage_maker.sections.locations.period_definitions import (
    EARLIEST_CALCULATION_YEAR,
    LATEST_CALCULATION_YEAR,
)
from mage_maker.sections.items.links import (
    normalize_item_event_link_types,
    normalize_item_event_new_owners,
)

WORLD_EVENT_TYPES = event_type_options("period")
WORLD_EVENT_TYPE_LABELS = EVENT_TYPE_LABELS
WORLD_EVENT_LABEL_TYPES = EVENT_LABEL_TYPES
WORLD_EVENT_DATE_PATTERN = re.compile(
    r"^(-?\d{1,5})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$"
)
WORLD_EVENT_TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3])[0-5]\d$")
WORLD_EVENT_COLON_TIME_PATTERN = re.compile(r"^((?:[01]\d|2[0-3])):([0-5]\d)$")
JOB_EVENT_TYPES = frozenset(("started_job", "received_raise"))
DEATH_EVENT_TYPES = frozenset(("died", "murder"))
BIRTH_EVENT_TYPE = "born"
BIRTH_EVENT_SOURCE = "birth_event"
GHOST_EVENT_TYPE = "returns_as_ghost"
BIRTH_ROLE_FIELDS = (
    "baby_person_ids",
    "birthing_parent_person_ids",
    "non_birthing_parent_person_ids",
)
ANCILLARY_PERSON_ROLE_FIELDS = (
    "witness_person_ids",
    "affected_person_ids",
)
JOB_EVENT_ONLY_FIELDS = (
    "organization_job_id",
    "job_title",
    "job_assignment_id",
    "job_end_date",
    "salary",
    "special_appointment_name",
    "job_concurrent",
    "died_in_office",
    "died_in_office_death_event_id",
    "died_in_office_created_death_event",
    "source_job_event_id",
)


def normalize_job_event_metadata(event):
    normalized = deepcopy(event) if isinstance(event, dict) else {}
    event_type = canonical_event_type(
        normalized.get("event_type")
    )

    if event_type not in JOB_EVENT_TYPES:
        for field_name in JOB_EVENT_ONLY_FIELDS:
            normalized.pop(field_name, None)

        return normalized

    normalized["organization_id"] = str(
        normalized.get("organization_id", "") or ""
    ).strip()
    normalized["organization_name"] = str(
        normalized.get("organization_name", "") or ""
    ).strip()

    normalized["organization_job_id"] = str(
        normalized.get("organization_job_id", "") or ""
    ).strip()
    normalized["job_title"] = str(
        normalized.get("job_title", "") or ""
    ).strip()
    normalized["job_assignment_id"] = str(
        normalized.get("job_assignment_id", "") or ""
    ).strip()
    normalized["special_appointment_name"] = str(
        normalized.get("special_appointment_name", "") or ""
    ).strip()
    normalized["job_concurrent"] = bool(
        normalized.get("job_concurrent", False)
    )
    normalized["died_in_office"] = bool(
        normalized.get("died_in_office", False)
    )
    normalized["died_in_office_death_event_id"] = str(
        normalized.get("died_in_office_death_event_id", "") or ""
    ).strip()
    normalized["died_in_office_created_death_event"] = bool(
        normalized.get(
            "died_in_office_created_death_event",
            False,
        )
    )
    normalized["source_job_event_id"] = str(
        normalized.get("source_job_event_id", "") or ""
    ).strip()
    salary_value = normalized.get("salary")
    normalized["salary"] = (
        None
        if salary_value in (None, "")
        else normalize_monthly_salary(salary_value)
    )
    job_end_date = str(
        normalized.get("job_end_date", "") or ""
    ).strip()
    normalized["job_end_date"] = (
        normalize_world_event_date(job_end_date)
        if job_end_date
        else ""
    )

    if event_type == "received_raise":
        normalized["job_end_date"] = ""
        normalized["special_appointment_name"] = ""
        normalized["job_concurrent"] = False
        normalized["died_in_office"] = False
        normalized["died_in_office_death_event_id"] = ""
        normalized["died_in_office_created_death_event"] = False

    return normalized


def normalize_character_control_event_metadata(event):
    """Retain and validate typed knowledge and creature links on any event."""

    normalized = deepcopy(event) if isinstance(event, dict) else {}
    event_type = canonical_event_type(normalized.get("event_type"))
    teaching_collections = {
        "taught_spell": ("spells",),
        "taught_proficiency": ("proficiencies",),
        "taught_recipe": (
            "potions",
            "preparations",
            "foods_and_drinks",
        ),
    }
    if event_type in teaching_collections:
        normalized["knowledge_record_id"] = str(
            normalized.get("knowledge_record_id", "") or ""
        ).strip()
        normalized["knowledge_collection"] = str(
            normalized.get("knowledge_collection", "") or ""
        ).strip()
        normalized["knowledge_name"] = " ".join(
            str(normalized.get("knowledge_name", "") or "").strip().split()
        )
        if not normalized["knowledge_record_id"]:
            raise ValueError("A teaching event needs a linked record.")
        if (
            normalized["knowledge_collection"]
            and normalized["knowledge_collection"]
            not in teaching_collections[event_type]
        ):
            raise ValueError("The taught record uses the wrong collection.")
    else:
        normalized.pop("knowledge_record_id", None)
        normalized.pop("knowledge_collection", None)
        normalized.pop("knowledge_name", None)

    if event_type in (
        "tamed_creature",
        "bonded_creature",
        "irked_creature",
    ):
        normalized["named_creature_id"] = str(
            normalized.get("named_creature_id", "") or ""
        ).strip()
        normalized["named_creature_name"] = " ".join(
            str(normalized.get("named_creature_name", "") or "").strip().split()
        )
        if not normalized["named_creature_id"]:
            raise ValueError(
                "A creature-relationship event needs a named creature."
            )
    else:
        normalized.pop("named_creature_id", None)
        normalized.pop("named_creature_name", None)
    return normalized


def normalize_world_event(event):
    if not isinstance(event, dict):
        raise TypeError("Every event must be an object.")

    normalized = deepcopy(event)
    normalized["record_id"] = str(
        normalized.get("record_id") or uuid.uuid4()
    ).strip()
    normalized["event_type"] = canonical_event_type(
        normalized.get("event_type") or "other"
    )
    normalized = normalize_job_event_metadata(normalized)
    normalized = normalize_character_control_event_metadata(normalized)
    normalized["title"] = " ".join(
        str(normalized.get("title", "") or "").strip().split()
    )
    requested_date = str(normalized.get("date", "") or "").strip()
    normalized["date"] = (
        ""
        if normalized["event_type"] == BIRTH_EVENT_TYPE
        and not requested_date
        else normalize_world_event_date(requested_date)
    )
    normalized["time"] = normalize_world_event_time(
        normalized.get("time")
    )
    normalized["description"] = str(
        normalized.get("description", "") or ""
    ).strip()
    normalized["person_ids"] = normalize_association_values(
        normalized.get("person_ids")
    )
    has_witness_role = (
        "witness_person_ids" in normalized
        or normalized["event_type"] == "murder"
    )
    has_affected_role = (
        "affected_person_ids" in normalized
        or normalized["event_type"] == "murder"
    )

    if has_witness_role:
        normalized["witness_person_ids"] = (
            normalize_association_values(
                normalized.get("witness_person_ids")
            )
        )

    if has_affected_role:
        normalized["affected_person_ids"] = (
            normalize_association_values(
                normalized.get("affected_person_ids")
            )
        )
    if normalized["event_type"] == BIRTH_EVENT_TYPE:
        fallback_baby_ids = normalize_association_values(
            normalized.get("person_ids")
        )[:1]
        singular_baby_id = str(
            normalized.get("baby_person_id", "") or ""
        ).strip()
        normalized["baby_person_ids"] = normalize_association_values(
            normalized.get("baby_person_ids")
            or ([singular_baby_id] if singular_baby_id else fallback_baby_ids)
        )
        normalized["birthing_parent_person_ids"] = (
            normalize_association_values(
                normalized.get("birthing_parent_person_ids")
                or (
                    [normalized.get("birthing_parent_person_id")]
                    if normalized.get("birthing_parent_person_id")
                    else []
                )
            )
        )
        normalized["non_birthing_parent_person_ids"] = (
            normalize_association_values(
                normalized.get("non_birthing_parent_person_ids")
                or (
                    [normalized.get("non_birthing_parent_person_id")]
                    if normalized.get("non_birthing_parent_person_id")
                    else []
                )
            )
        )
        normalized["person_ids"] = normalize_association_values(
            [
                *normalized["baby_person_ids"],
                *normalized["birthing_parent_person_ids"],
                *normalized["non_birthing_parent_person_ids"],
            ]
        )
        normalized.pop("baby_person_id", None)
        normalized.pop("birthing_parent_person_id", None)
        normalized.pop("non_birthing_parent_person_id", None)
        normalized.pop("perpetrator_person_ids", None)
        normalized.pop("victim_person_ids", None)
    elif normalized["event_type"] == "murder":
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
        for field_name in BIRTH_ROLE_FIELDS:
            normalized.pop(field_name, None)

        normalized.pop("perpetrator_person_ids", None)
        normalized.pop("victim_person_ids", None)
    requested_eminence_person_ids = normalize_association_values(
        normalized.get("eminence_person_ids")
    )
    linked_person_ids = set(event_linked_person_ids(normalized))
    normalized["eminence_person_ids"] = [
        person_id
        for person_id in requested_eminence_person_ids
        if person_id in linked_person_ids
    ]
    normalized["eminence_skills"] = normalize_eminence_skill_values(
        normalized.get("eminence_skills"),
        normalized["eminence_person_ids"],
    )
    if normalized["event_type"] in (BIRTH_EVENT_TYPE, "died"):
        normalized["eminence_person_ids"] = []
        normalized["eminence_skills"] = {}
    elif normalized["event_type"] == "murder":
        victim_ids = set(normalized["victim_person_ids"])
        normalized["eminence_person_ids"] = [
            person_id
            for person_id in normalized["eminence_person_ids"]
            if person_id not in victim_ids
        ]
        normalized["eminence_skills"] = {
            person_id: skill
            for person_id, skill in normalized["eminence_skills"].items()
            if person_id in normalized["eminence_person_ids"]
        }
    normalized["period_names"] = normalize_association_values(
        normalized.get("period_names")
    )
    normalized["location_ids"] = normalize_association_values(
        normalized.get("location_ids")
    )
    normalized["address_ids"] = normalize_association_values(
        normalized.get("address_ids")
    )
    owner_reference = normalized.get("owner_reference")
    if isinstance(owner_reference, dict):
        owner_type = str(
            owner_reference.get("owner_type", "") or ""
        ).strip().lower()
        owner_record_id = str(
            owner_reference.get("record_id", "") or ""
        ).strip()
        if owner_type in {"person", "organization"} and owner_record_id:
            normalized["owner_reference"] = {
                "owner_type": owner_type,
                "record_id": owner_record_id,
            }
        else:
            normalized.pop("owner_reference", None)
    else:
        normalized.pop("owner_reference", None)
    normalized["item_ids"] = normalize_association_values(
        normalized.get("item_ids")
    )
    normalized["item_link_types"] = normalize_item_event_link_types(
        normalized.get("item_link_types"),
        normalized["item_ids"],
        normalized["event_type"],
    )
    normalized["item_new_owners"] = normalize_item_event_new_owners(
        normalized.get("item_new_owners"),
        normalized["item_ids"],
        normalized["item_link_types"],
    )
    normalized["locked_location_ids"] = normalize_association_values(
        normalized.get("locked_location_ids")
    )

    if (
        normalized["event_type"] in (
            BIRTH_EVENT_TYPE,
            *DEATH_EVENT_TYPES,
        )
        and len(normalized["location_ids"]) > 1
    ):
        normalized["location_ids"] = normalized["location_ids"][-1:]
        normalized["locked_location_ids"] = [
            location_id
            for location_id in normalized["locked_location_ids"]
            if location_id in normalized["location_ids"]
        ][-1:]

    for location_id in normalized["locked_location_ids"]:
        if location_id not in normalized["location_ids"]:
            normalized["location_ids"].append(location_id)

    normalized["organization_id"] = str(
        normalized.get("organization_id", "") or ""
    ).strip()
    normalized["organization_name"] = str(
        normalized.get("organization_name", "") or ""
    ).strip()

    if normalized["event_type"] == "discovery":
        normalized["discovery_book_id"] = str(
            normalized.get("discovery_book_id", "") or ""
        ).strip()
        normalized["discovery_content_id"] = str(
            normalized.get("discovery_content_id", "") or ""
        ).strip()
    else:
        normalized.pop("discovery_book_id", None)
        normalized.pop("discovery_content_id", None)

    if normalized["event_type"] not in EVENT_TYPE_LABELS:
        normalized["event_type"] = "other"

    if not normalized["title"]:
        raise ValueError("An event needs a title.")

    return normalized


def normalize_world_events(events):
    if events in (None, ""):
        return []

    if not isinstance(events, list):
        raise TypeError("Events must be a list.")

    normalized_events = []
    used_ids = set()

    for event in events:
        normalized = normalize_world_event(event)

        if normalized["record_id"] in used_ids:
            raise ValueError(
                f'Duplicate event record_id: {normalized["record_id"]}'
            )

        used_ids.add(normalized["record_id"])
        normalized_events.append(normalized)

    normalized_events.sort(key=world_event_sort_key)
    return normalized_events


def normalize_association_values(values):
    if values in (None, ""):
        return []

    if not isinstance(values, (list, tuple, set)):
        raise TypeError("Event associations must be a list.")

    normalized_values = []
    used_values = set()

    for value in values:
        normalized = str(value or "").strip()

        if not normalized or normalized in used_values:
            continue

        used_values.add(normalized)
        normalized_values.append(normalized)

    return normalized_values


def event_linked_person_ids(event):
    event_values = event if isinstance(event, dict) else {}
    return normalize_association_values(
        [
            *normalize_association_values(
                event_values.get("person_ids")
            ),
            *normalize_association_values(
                event_values.get("witness_person_ids")
            ),
            *normalize_association_values(
                event_values.get("affected_person_ids")
            ),
        ]
    )


def birth_event_baby_ids(event):
    event_values = event if isinstance(event, dict) else {}

    if canonical_event_type(
        event_values.get("event_type")
    ) != BIRTH_EVENT_TYPE:
        return []

    baby_ids = normalize_association_values(
        event_values.get("baby_person_ids")
    )

    if baby_ids:
        return baby_ids

    return normalize_association_values(
        event_values.get("person_ids")
    )[:1]


def birth_event_person_ids(event):
    event_values = event if isinstance(event, dict) else {}

    if canonical_event_type(
        event_values.get("event_type")
    ) != BIRTH_EVENT_TYPE:
        return []

    return normalize_association_values(
        [
            *birth_event_baby_ids(event_values),
            *normalize_association_values(
                event_values.get("birthing_parent_person_ids")
            ),
            *normalize_association_values(
                event_values.get("non_birthing_parent_person_ids")
            ),
        ]
    )


def death_event_person_ids(event):
    event_values = event if isinstance(event, dict) else {}
    event_type = canonical_event_type(event_values.get("event_type"))

    if event_type == "died":
        return normalize_association_values(
            event_values.get("person_ids")
        )

    if event_type == "murder":
        return normalize_association_values(
            event_values.get("victim_person_ids")
        )

    return []


def death_event_date_sort_key(value):
    date_text = str(value or "").strip()
    match = WORLD_EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        return 100000, 13, 32

    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def death_source_sort_key(event):
    event_values = event if isinstance(event, dict) else {}
    return (
        death_event_date_sort_key(event_values.get("date")),
        str(
            event_values.get(
                "record_id",
                event_values.get("event_id", ""),
            )
            or ""
        ),
    )


def synchronize_people_death_records(database_data, person_ids=None):
    if not isinstance(database_data, dict):
        return False

    people = database_data.get("people", [])
    world_events = database_data.get("events", [])

    if not isinstance(people, list) or not isinstance(world_events, list):
        return False

    selected_ids = (
        {
            str(person_id or "").strip()
            for person_id in person_ids
            if str(person_id or "").strip()
        }
        if person_ids is not None
        else None
    )
    changed = False

    for person in people:
        if not isinstance(person, dict):
            continue

        person_id = str(person.get("record_id", "") or "").strip()

        if selected_ids is not None and person_id not in selected_ids:
            continue

        death_sources = [
            event
            for event in world_events
            if isinstance(event, dict)
            and person_id in death_event_person_ids(event)
        ]
        death_sources.extend(
            event
            for event in person.get("timeline_events", []) or []
            if isinstance(event, dict)
            and canonical_event_type(event.get("event_type")) == "died"
            and str(event.get("date", "") or "").strip()
        )
        death_sources.sort(key=death_source_sort_key)

        if death_sources:
            death_year, death_month, death_day = split_world_event_date(
                death_sources[0].get("date")
            )
            death_values = {
                "deceased": True,
                "death_year": int(death_year),
                "death_month": (
                    int(death_month) if death_month else None
                ),
                "death_day": int(death_day) if death_day else None,
            }
        else:
            death_values = {
                "deceased": False,
                "death_year": None,
                "death_month": None,
                "death_day": None,
            }

        if any(
            person.get(field_name) != value
            for field_name, value in death_values.items()
        ):
            person.update(death_values)
            changed = True

    return changed


def normalize_eminence_skill_values(values, earned_person_ids=()):
    if values in (None, ""):
        candidate_values = {}
    elif isinstance(values, dict):
        candidate_values = values
    else:
        raise TypeError("Event Eminence skills must be an object.")

    earned_ids = {
        str(person_id or "").strip()
        for person_id in earned_person_ids or ()
        if str(person_id or "").strip()
    }
    normalized_values = {}

    for person_id, skill in candidate_values.items():
        normalized_person_id = str(person_id or "").strip()
        normalized_skill = str(skill or "").strip()

        if (
            normalized_person_id in earned_ids
            and normalized_skill
        ):
            normalized_values[normalized_person_id] = normalized_skill

    return normalized_values


def normalize_world_event_date(value):
    date_text = str(value or "").strip()

    if not date_text:
        raise ValueError("An event needs a year.")

    plain_year_match = re.fullmatch(r"-?\d+", date_text)

    if plain_year_match is not None:
        plain_year = int(date_text)

        if (
            plain_year == 0
            or plain_year < EARLIEST_CALCULATION_YEAR
            or plain_year > LATEST_CALCULATION_YEAR
        ):
            raise ValueError(
                "Event year must be between -99999 and 99999, excluding 0."
            )

    match = WORLD_EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        raise ValueError(
            "Event date must use YYYY, YYYY-MM, or YYYY-MM-DD."
        )

    year = int(match.group(1))
    month = int(match.group(2)) if match.group(2) else None
    day = int(match.group(3)) if match.group(3) else None

    if (
        year == 0
        or year < EARLIEST_CALCULATION_YEAR
        or year > LATEST_CALCULATION_YEAR
    ):
        raise ValueError(
            "Event year must be between -99999 and 99999, excluding 0."
        )

    if month is not None and not 1 <= month <= 12:
        raise ValueError("Event month must be between 1 and 12.")

    if day is not None and not 1 <= day <= 31:
        raise ValueError("Event day must be between 1 and 31.")

    if day is not None and month is None:
        raise ValueError("Event day requires a month.")

    normalized = str(year)

    if month is not None:
        normalized += f"-{month:02d}"

    if day is not None:
        normalized += f"-{day:02d}"

    return normalized


def normalize_world_event_time(value):
    time_text = str(value or "").strip()

    if not time_text:
        return ""

    # Game Board and session controls display times as HH:MM.  Accept that
    # suite-wide representation when loading and store World Builder's
    # canonical four-digit form internally.
    colon_match = WORLD_EVENT_COLON_TIME_PATTERN.fullmatch(time_text)
    if colon_match is not None:
        return "".join(colon_match.groups())

    if WORLD_EVENT_TIME_PATTERN.fullmatch(time_text) is None:
        raise ValueError(
            "Event time must use four digits from 0000 to 2359, "
            "with no colon."
        )

    return time_text


def event_time_sort_key(value):
    time_text = str(value or "").strip()

    if WORLD_EVENT_TIME_PATTERN.fullmatch(time_text) is None:
        return 2400

    return int(time_text)


def split_world_event_date(value):
    if not str(value or "").strip():
        return "", "", ""

    normalized = normalize_world_event_date(value)

    match = WORLD_EVENT_DATE_PATTERN.fullmatch(normalized)
    return (
        match.group(1),
        match.group(2) or "",
        match.group(3) or "",
    )


def world_event_date_is_on_or_after(event_date, reference_date):
    event_year, event_month, event_day = split_world_event_date(
        event_date
    )
    reference_year, reference_month, reference_day = (
        split_world_event_date(reference_date)
    )
    normalized_event_year = int(event_year)
    normalized_reference_year = int(reference_year)

    if normalized_event_year != normalized_reference_year:
        return normalized_event_year > normalized_reference_year

    if event_month and reference_month:
        normalized_event_month = int(event_month)
        normalized_reference_month = int(reference_month)

        if normalized_event_month != normalized_reference_month:
            return normalized_event_month > normalized_reference_month

    if event_day and reference_day:
        return int(event_day) >= int(reference_day)

    return True


def world_event_year(value):
    date_text = str(value or "").strip()
    match = WORLD_EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        return None

    year = int(match.group(1))
    return year if year != 0 else None


def world_event_sort_key(event):
    date_text = str(event.get("date", "") or "")
    match = WORLD_EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        date_key = (100000, 13, 32)
    else:
        date_key = (
            int(match.group(1)),
            int(match.group(2) or 0),
            int(match.group(3) or 0),
        )

    return (
        date_key,
        event_time_sort_key(event.get("time")),
        str(event.get("title", "") or "").casefold(),
        str(event.get("record_id", "") or ""),
    )


def person_birth_event_date(person):
    person_values = person if isinstance(person, dict) else {}
    year = person_values.get("birth_year")
    month = person_values.get("birth_month")
    day = person_values.get("birth_day")

    if year in (None, ""):
        return ""

    date_value = str(int(year))

    if month not in (None, ""):
        date_value += f"-{int(month):02d}"

    if day not in (None, ""):
        date_value += f"-{int(day):02d}"

    return normalize_world_event_date(date_value)


def person_birth_event_location_ids(person):
    person_values = person if isinstance(person, dict) else {}
    timeline_events = person_values.get("timeline_events", [])

    if not isinstance(timeline_events, list):
        return []

    for requested_type in ("born", "starting_location"):
        for timeline_event in timeline_events:
            if not isinstance(timeline_event, dict):
                continue

            if canonical_event_type(
                timeline_event.get("event_type")
            ) != requested_type:
                continue

            location_ids = normalize_association_values(
                timeline_event.get("location_ids")
            )

            if location_ids:
                return location_ids[-1:]

    return []


def person_birth_event_description(person):
    person_values = person if isinstance(person, dict) else {}
    timeline_events = person_values.get("timeline_events", [])

    if not isinstance(timeline_events, list):
        return ""

    for timeline_event in timeline_events:
        if not isinstance(timeline_event, dict):
            continue

        if canonical_event_type(
            timeline_event.get("event_type")
        ) != BIRTH_EVENT_TYPE:
            continue

        return str(timeline_event.get("note", "") or "").strip()

    return ""


def birth_event_from_person(person, existing_event=None):
    person_values = person if isinstance(person, dict) else {}
    person_id = str(person_values.get("record_id", "") or "").strip()
    birth_date = person_birth_event_date(person_values)

    if not person_id:
        return None

    event = (
        deepcopy(existing_event)
        if isinstance(existing_event, dict)
        else {}
    )
    birthing_parent_id = str(
        person_values.get("biological_mother_id", "") or ""
    ).strip()
    non_birthing_parent_id = str(
        person_values.get("biological_father_id", "") or ""
    ).strip()

    if (
        not birth_date
        and not birthing_parent_id
        and not non_birthing_parent_id
        and not isinstance(existing_event, dict)
    ):
        return None
    existing_description = str(
        event.get("description", "") or ""
    ).strip()
    existing_locations = normalize_association_values(
        event.get("location_ids")
    )[-1:]
    event.update(
        {
            "record_id": str(
                event.get("record_id") or f"birth:{person_id}"
            ).strip(),
            "event_type": BIRTH_EVENT_TYPE,
            "title": "Birth",
            "date": birth_date,
            "description": (
                existing_description
                or person_birth_event_description(person_values)
            ),
            "baby_person_ids": [person_id],
            "birthing_parent_person_ids": (
                [birthing_parent_id] if birthing_parent_id else []
            ),
            "non_birthing_parent_person_ids": (
                [non_birthing_parent_id]
                if non_birthing_parent_id
                else []
            ),
            "person_ids": [
                person_id,
                *([birthing_parent_id] if birthing_parent_id else []),
                *(
                    [non_birthing_parent_id]
                    if non_birthing_parent_id
                    else []
                ),
            ],
            "eminence_person_ids": [],
            "eminence_skills": {},
            "period_names": [],
            "location_ids": (
                existing_locations
                or person_birth_event_location_ids(person_values)
            ),
            "locked_location_ids": [],
            "automatic_source": BIRTH_EVENT_SOURCE,
        }
    )
    return normalize_world_event(event)


def synchronize_birth_events_from_people(database_data, person_ids=None):
    if not isinstance(database_data, dict):
        return False

    people = database_data.get("people", [])
    stored_events = database_data.get("events", [])

    if not isinstance(people, list) or not isinstance(stored_events, list):
        return False

    selected_ids = (
        {
            str(person_id or "").strip()
            for person_id in person_ids
            if str(person_id or "").strip()
        }
        if person_ids is not None
        else {
            str(person.get("record_id", "") or "").strip()
            for person in people
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
    )
    normalized_events = normalize_world_events(stored_events)
    known_location_ids = {
        str(location.get("record_id", "") or "").strip()
        for location in database_data.get("locations", [])
        if isinstance(location, dict)
        and str(location.get("record_id", "") or "").strip()
    }
    existing_birth_events = {}

    for event in normalized_events:
        baby_ids = birth_event_baby_ids(event)

        if (
            event.get("event_type") == BIRTH_EVENT_TYPE
            and len(baby_ids) == 1
            and baby_ids[0] not in existing_birth_events
        ):
            existing_birth_events[baby_ids[0]] = event

    retained_events = [
        event
        for event in normalized_events
        if not (
            event.get("event_type") == BIRTH_EVENT_TYPE
            and any(
                baby_id in selected_ids
                for baby_id in birth_event_baby_ids(event)
            )
        )
    ]

    for person in people:
        if not isinstance(person, dict):
            continue

        person_id = str(person.get("record_id", "") or "").strip()

        if person_id not in selected_ids:
            continue

        synchronized_event = birth_event_from_person(
            person,
            existing_birth_events.get(person_id),
        )

        if synchronized_event is not None:
            synchronized_event["location_ids"] = [
                location_id
                for location_id in synchronized_event.get(
                    "location_ids",
                    [],
                )
                if location_id in known_location_ids
            ][-1:]
            synchronized_event["locked_location_ids"] = [
                location_id
                for location_id in synchronized_event.get(
                    "locked_location_ids",
                    [],
                )
                if location_id in synchronized_event["location_ids"]
            ]
            retained_events.append(synchronized_event)

    synchronized_events = normalize_world_events(retained_events)
    changed = synchronized_events != normalized_events

    if changed:
        database_data["events"] = synchronized_events

    timeline_changed = False

    for person in people:
        if not isinstance(person, dict):
            continue

        timeline_events = person.get("timeline_events", [])

        if not isinstance(timeline_events, list):
            continue

        retained_timeline_events = [
            event
            for event in timeline_events
            if not (
                isinstance(event, dict)
                and str(event.get("automatic_source", "") or "")
                == "child_assignment"
            )
        ]

        if retained_timeline_events != timeline_events:
            person["timeline_events"] = retained_timeline_events
            timeline_changed = True

    return changed or timeline_changed


def world_event_type_label(event):
    return event_type_label(event)


normalize_event = normalize_world_event
normalize_events = normalize_world_events
event_sort_key = world_event_sort_key
event_year = world_event_year
