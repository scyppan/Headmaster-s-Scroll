import hashlib
import random
from copy import deepcopy

from mage_maker.core.dates import (
    historical_year_after,
    historical_year_distance,
    historical_year_shift,
)
from mage_maker.sections.development.initial_bonuses import (
    preferred_development_skills,
)
from mage_maker.sections.development.models import (
    ACADEMIC_YEARS_TO_ADULTHOOD,
    DEVELOPMENT_SKILL_OPTIONS,
    calculate_development_start_year,
    development_year_page_title,
    new_eminence_record,
    non_magical_development_plan,
    normalize_development_plan,
    normalize_eminence_record,
    normalize_eminence_records,
)
from mage_maker.sections.development.school_years import (
    random_school_year_record,
)
from mage_maker.sections.events.models import (
    normalize_world_event,
    split_world_event_date,
    world_event_year,
)


EVENT_EMINENCE_RECORD_PREFIX = "event-eminence-"


def event_eminence_record_id(event_id, person_id):
    identity = (
        f"{str(event_id or '').strip()}|"
        f"{str(person_id or '').strip()}"
    )
    return EVENT_EMINENCE_RECORD_PREFIX + hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:24]


def event_eminence_record_is_linked(record):
    return str(
        (record or {}).get("record_id", "") or ""
    ).startswith(EVENT_EMINENCE_RECORD_PREFIX)


def event_eminence_target(person, event):
    person_values = person if isinstance(person, dict) else {}

    if bool(person_values.get("non_magical")):
        return None

    normalized_event = normalize_world_event(event)
    event_year = world_event_year(normalized_event.get("date"))

    if event_year is None:
        return None

    stored_plan = person_values.get("development_plan")
    school_attended = (
        bool(str(person_values.get("school", "") or "").strip())
        if "school" in person_values
        else bool(
            stored_plan.get("school_started", False)
            if isinstance(stored_plan, dict)
            else False
        )
    )
    academic_start_year = calculate_development_start_year(
        person_values.get("birth_year"),
        person_values.get("birth_month"),
        person_values.get("birth_day"),
        school_attended=school_attended,
    )

    if academic_start_year is None:
        return None

    _, event_month_text, _ = split_world_event_date(
        normalized_event.get("date", "")
    )

    if school_attended:
        event_month = (
            int(event_month_text)
            if event_month_text
            else 9
        )
        event_school_year_start = (
            event_year
            if event_month >= 9
            else historical_year_shift(event_year, -1)
        )
        school_year = (
            historical_year_distance(
                academic_start_year,
                event_school_year_start,
            )
            + 1
        )

        if 1 <= school_year <= ACADEMIC_YEARS_TO_ADULTHOOD:
            page = {
                "page_key": f"school:{school_year}",
                "page_type": "school",
                "school_year": school_year,
                "adult_year": None,
                "calendar_year": event_school_year_start,
                "calendar_end_year": historical_year_after(
                    event_school_year_start
                ),
                "age_range": None,
                "school_attended": True,
            }
            page["title"] = development_year_page_title(page)
            return page

    return {
        "page_key": f"event:{normalized_event['record_id']}",
        "page_type": "event",
        "school_year": None,
        "adult_year": None,
        "calendar_year": event_year,
        "calendar_end_year": event_year,
        "age_range": None,
        "school_attended": school_attended,
        "title": str(event_year),
    }


def event_eminence_default_skill(development_plan, target):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    preferred_skills = preferred_development_skills(plan)

    if preferred_skills:
        return preferred_skills[0]

    if target.get("page_type") == "school":
        school_year = int(target.get("school_year"))
        target_record = next(
            (
                record
                for record in plan.get("school_years", [])
                if record.get("year") == school_year
            ),
            None,
        )

        if target_record and target_record.get("skills"):
            return target_record["skills"][0]

    for school_year_record in reversed(
        plan.get("school_years", [])
    ):
        if school_year_record.get("skills"):
            return school_year_record["skills"][0]

    return DEVELOPMENT_SKILL_OPTIONS[0]


def suggested_event_eminence_skill(
    development_plan,
    person_id,
    event_identity="",
):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    candidates = preferred_development_skills(plan)

    if not candidates:
        candidates = list(DEVELOPMENT_SKILL_OPTIONS)

    identity = (
        f"{str(person_id or '').strip()}|"
        f"{str(event_identity or '').strip()}|"
        f"{plan.get('schema', 'Scattershot')}"
    )
    selected_index = int(
        hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        16,
    ) % len(candidates)
    return candidates[selected_index]


def remove_event_eminence_record(development_plan, record_id):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    selected_record = None
    retained_initial = []

    for record in normalize_eminence_records(
        plan.get("initial_eminence", [])
    ):
        if record["record_id"] == record_id:
            selected_record = selected_record or record
        else:
            retained_initial.append(record)

    plan["initial_eminence"] = retained_initial

    for collection_name in ("school_years", "adult_years"):
        for year_record in plan.get(collection_name, []):
            retained_records = []

            for record in normalize_eminence_records(
                year_record.get("eminence", [])
            ):
                if record["record_id"] == record_id:
                    selected_record = selected_record or record
                else:
                    retained_records.append(record)

            year_record["eminence"] = retained_records

    return normalize_development_plan(plan), selected_record


def remove_all_event_eminence_records(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    removed_records = {}
    retained_initial = []

    for record in normalize_eminence_records(
        plan.get("initial_eminence", [])
    ):
        if event_eminence_record_is_linked(record):
            removed_records[record["record_id"]] = record
        else:
            retained_initial.append(record)

    plan["initial_eminence"] = retained_initial

    for collection_name in ("school_years", "adult_years"):
        for year_record in plan.get(collection_name, []):
            retained_records = []

            for record in normalize_eminence_records(
                year_record.get("eminence", [])
            ):
                if event_eminence_record_is_linked(record):
                    removed_records[record["record_id"]] = record
                else:
                    retained_records.append(record)

            year_record["eminence"] = retained_records

    return normalize_development_plan(plan), removed_records


def add_event_eminence_record(development_plan, target, record):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    normalized_record = normalize_eminence_record(record)
    page_type = str(target.get("page_type", "") or "")

    if page_type == "school":
        school_year = int(target.get("school_year"))
        plan.pop("calendar_year_progression", None)
        plan["school_started"] = True
        plan["academic_years_advanced"] = max(
            int(plan.get("academic_years_advanced", 0)),
            school_year - 1,
        )
        plan = normalize_development_plan(
            plan,
            default_schema="Scattershot",
        )
        school_years_by_number = {
            int(year_record.get("year")): year_record
            for year_record in plan.get("school_years", [])
        }

        for year_number in range(1, school_year + 1):
            if year_number in school_years_by_number:
                continue

            seed_text = (
                f"{normalized_record.get('record_id', '')}|"
                f"school-year-{year_number}"
            )
            seed = int(
                hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16],
                16,
            )
            school_years_by_number[year_number] = (
                random_school_year_record(
                    year_number,
                    plan,
                    randomizer=random.Random(seed),
                )
            )

        plan["school_years"] = [
            school_years_by_number[year_number]
            for year_number in sorted(school_years_by_number)
        ]
        target_record = next(
            (
                year_record
                for year_record in plan.get("school_years", [])
                if year_record.get("year") == school_year
            ),
            None,
        )
    elif page_type == "adult":
        adult_year = int(target.get("adult_year"))
        target_record = next(
            (
                year_record
                for year_record in plan.get("adult_years", [])
                if year_record.get("adult_year") == adult_year
            ),
            None,
        )
    elif page_type == "event":
        plan["initial_eminence"] = normalize_eminence_records(
            [
                *plan.get("initial_eminence", []),
                normalized_record,
            ]
        )
        return normalize_development_plan(plan)
    else:
        target_record = None

    if target_record is None:
        return normalize_development_plan(plan)

    target_record["eminence"] = normalize_eminence_records(
        [
            *target_record.get("eminence", []),
            normalized_record,
        ]
    )
    return normalize_development_plan(plan)


def event_eminence_record(
    event,
    person,
    target,
    existing_record=None,
):
    normalized_event = normalize_world_event(event)
    person_id = str(person.get("record_id", "") or "").strip()
    record_id = event_eminence_record_id(
        normalized_event["record_id"],
        person_id,
    )
    selected_skill = str(
        normalized_event.get("eminence_skills", {}).get(
            person_id,
            "",
        )
        or ""
    ).strip()

    if selected_skill not in DEVELOPMENT_SKILL_OPTIONS:
        selected_skill = ""

    if existing_record is not None:
        retained_record = normalize_eminence_record(existing_record)
        retained_record["record_id"] = record_id

        if selected_skill:
            retained_record["skill"] = selected_skill

        return normalize_eminence_record(retained_record)

    record = new_eminence_record(
        normalized_event["title"],
        normalized_event.get("description", ""),
        selected_skill
        or event_eminence_default_skill(
            person.get("development_plan"),
            target,
        ),
    )
    record["record_id"] = record_id
    return normalize_eminence_record(record)


def normalized_event_map(events):
    event_map = {}

    for event in events or ():
        normalized_event = normalize_world_event(event)
        event_map[normalized_event["record_id"]] = normalized_event

    return event_map


def prepare_event_eminence_updates(
    database,
    previous_events=(),
    current_events=(),
):
    previous_by_id = normalized_event_map(previous_events)
    current_by_id = normalized_event_map(current_events)
    event_ids = set(previous_by_id) | set(current_by_id)
    affected_person_ids = set()

    for event in [
        *previous_by_id.values(),
        *current_by_id.values(),
    ]:
        affected_person_ids.update(
            event.get("eminence_person_ids", [])
        )

    if not affected_person_ids:
        return {}

    people_by_id = {
        str(person.get("record_id", "") or "").strip(): person
        for person in database.list_people()
        if isinstance(person, dict)
        and str(person.get("record_id", "") or "").strip()
    }
    working_people = {
        person_id: deepcopy(people_by_id[person_id])
        for person_id in affected_person_ids
        if person_id in people_by_id
    }

    for event_id in event_ids:
        previous_event = previous_by_id.get(event_id)
        current_event = current_by_id.get(event_id)
        previous_person_ids = set(
            (previous_event or {}).get(
                "eminence_person_ids",
                [],
            )
        )
        current_person_ids = set(
            (current_event or {}).get(
                "eminence_person_ids",
                [],
            )
        )

        for person_id in previous_person_ids | current_person_ids:
            person = working_people.get(person_id)

            if person is None:
                continue

            record_id = event_eminence_record_id(
                event_id,
                person_id,
            )
            plan, existing_record = remove_event_eminence_record(
                person.get("development_plan"),
                record_id,
            )
            person["development_plan"] = plan

            if bool(person.get("non_magical")):
                person["development_plan"] = (
                    non_magical_development_plan(
                        person.get("development_plan")
                    )
                )
                continue

            if (
                current_event is None
                or person_id not in current_person_ids
            ):
                continue

            target = event_eminence_target(person, current_event)

            if target is None:
                continue

            person["development_plan"] = add_event_eminence_record(
                person["development_plan"],
                target,
                event_eminence_record(
                    current_event,
                    person,
                    target,
                    existing_record,
                ),
            )

    updates = {}

    for person_id, person in working_people.items():
        original_person = people_by_id[person_id]
        normalized_plan = (
            non_magical_development_plan(
                person.get("development_plan")
            )
            if person.get("non_magical")
            else normalize_development_plan(
                person.get("development_plan"),
                default_schema="Scattershot",
            )
        )
        original_plan = (
            non_magical_development_plan(
                original_person.get("development_plan")
            )
            if original_person.get("non_magical")
            else normalize_development_plan(
                original_person.get("development_plan"),
                default_schema="Scattershot",
            )
        )

        if normalized_plan != original_plan:
            updates[person_id] = normalized_plan

    return updates


def apply_event_eminence_updates(database, updates):
    for person_id, development_plan in updates.items():
        database.update_person(
            person_id,
            {"development_plan": development_plan},
        )

    return bool(updates)


def reconcile_person_event_eminence(person, events):
    person_values = deepcopy(person) if isinstance(person, dict) else {}

    if bool(person_values.get("non_magical")):
        return non_magical_development_plan(
            person_values.get("development_plan")
        )

    person_id = str(
        person_values.get("record_id", "") or ""
    ).strip()
    plan, existing_records = remove_all_event_eminence_records(
        person_values.get("development_plan")
    )
    person_values["development_plan"] = plan

    for event in normalized_event_map(events).values():
        if person_id not in event.get("eminence_person_ids", []):
            continue

        target = event_eminence_target(person_values, event)

        if target is None:
            continue

        record_id = event_eminence_record_id(
            event["record_id"],
            person_id,
        )
        person_values["development_plan"] = (
            add_event_eminence_record(
                person_values["development_plan"],
                target,
                event_eminence_record(
                    event,
                    person_values,
                    target,
                    existing_records.get(record_id),
                ),
            )
        )

    return normalize_development_plan(
        person_values.get("development_plan"),
        default_schema="Scattershot",
    )
