from copy import deepcopy

from mage_maker.core.dates import (
    format_date_parts,
    person_death_age_text,
)
from mage_maker.sections.locations.models import descendant_ids, locations_by_id
from mage_maker.sections.locations.period_definitions import (
    EARLIEST_CALCULATION_YEAR,
    LATEST_CALCULATION_YEAR,
)
from mage_maker.sections.timeline.locations import location_at_date, normalize_location


REPRODUCTIVE_MINIMUM_AGE = 18
PERIOD_CATEGORY_KEYS = (
    "born",
    "died",
    "reproductively_active",
    "living",
)


def normalize_period_years(start_year, end_year):
    normalized_start = normalized_period_year(start_year)
    normalized_end = normalized_period_year(end_year)

    if normalized_start is None or normalized_end is None:
        raise ValueError(
            "Enter both period years between -99999 and 99999, excluding 0."
        )

    if normalized_end < normalized_start:
        raise ValueError("The ending year cannot be earlier than the starting year.")

    return normalized_start, normalized_end


def categorized_people_for_period(
    people,
    locations,
    start_year,
    end_year,
    location_id="",
    reproductive_without_children=False,
):
    period_start, period_end = normalize_period_years(start_year, end_year)
    normalized_people = [
        person
        for person in people if isinstance(person, dict)
    ]
    normalized_locations = [
        location
        for location in locations if isinstance(location, dict)
    ]
    location_scope = location_keys_in_scope(location_id, normalized_locations)
    results = {category_key: [] for category_key in PERIOD_CATEGORY_KEYS}
    parent_ids = {
        str(parent_id or "").strip()
        for child in normalized_people
        for parent_id in (
            child.get("biological_mother_id"),
            child.get("biological_father_id"),
        )
        if str(parent_id or "").strip()
    }

    for person in normalized_people:
        birth_year = normalized_year(person.get("birth_year"))
        death_year = (
            normalized_year(person.get("death_year"))
            if bool(person.get("deceased"))
            else None
        )
        birth_date = format_date_parts(
            person.get("birth_year"),
            person.get("birth_month"),
            person.get("birth_day"),
            unknown="",
        )
        death_date = (
            format_date_parts(
                person.get("death_year"),
                person.get("death_month"),
                person.get("death_day"),
                unknown="",
            )
            if bool(person.get("deceased"))
            else ""
        )

        if (
            birth_year is not None
            and period_start <= birth_year <= period_end
            and person_matches_location_at_date(person, birth_date, location_scope)
        ):
            results["born"].append(
                period_person_result(
                    person,
                    birth_date,
                    location_at_date(person, birth_date),
                )
            )

        if (
            death_year is not None
            and period_start <= death_year <= period_end
            and person_matches_location_at_date(person, death_date, location_scope)
        ):
            results["died"].append(
                period_person_result(
                    person,
                    death_date,
                    location_at_date(person, death_date),
                )
            )

        if birth_year is None:
            continue

        living_start = max(period_start, birth_year)
        living_end = period_end if death_year is None else min(period_end, death_year)

        if (
            living_start <= living_end
            and person_matches_location_during(
                person,
                living_start,
                living_end,
                location_scope,
            )
        ):
            results["living"].append(
                period_person_result(
                    person,
                    lifespan_text(person),
                    location_during(person, living_start, living_end, location_scope),
                )
            )

        reproductive_start = max(
            period_start,
            birth_year + REPRODUCTIVE_MINIMUM_AGE,
        )
        reproductive_end = period_end if death_year is None else min(
            period_end,
            death_year,
        )

        if (
            reproductive_start <= reproductive_end
            and person_matches_location_during(
                person,
                reproductive_start,
                reproductive_end,
                location_scope,
            )
            and (
                not reproductive_without_children
                or str(person.get("record_id", "") or "").strip() not in parent_ids
            )
        ):
            results["reproductively_active"].append(
                period_person_result(
                    person,
                    lifespan_text(person),
                    location_during(
                        person,
                        reproductive_start,
                        reproductive_end,
                        location_scope,
                    ),
                )
            )

    results["born"].sort(key=dated_result_sort_key)
    results["died"].sort(key=dated_result_sort_key)
    results["reproductively_active"].sort(key=person_result_sort_key)
    results["living"].sort(key=person_result_sort_key)
    return results


def location_keys_in_scope(location_id, locations):
    selected_id = str(location_id or "").strip()

    if not selected_id:
        return None

    records = locations_by_id(locations)

    if selected_id not in records:
        raise ValueError("The selected location no longer exists.")

    scoped_ids = descendant_ids(selected_id, locations)
    scoped_ids.add(selected_id)
    return {
        normalize_location(records[record_id].get("name", ""))
        for record_id in scoped_ids
        if record_id in records
        and normalize_location(records[record_id].get("name", ""))
    }


def person_matches_location_at_date(person, date_value, location_scope):
    if location_scope is None:
        return True

    location_name = location_at_date(person, date_value)
    return normalize_location(location_name) in location_scope


def person_matches_location_during(person, start_year, end_year, location_scope):
    if location_scope is None:
        return True

    return bool(location_during(person, start_year, end_year, location_scope))


def location_during(person, start_year, end_year, location_scope=None):
    for location_period in person_location_periods(person):
        location_start = location_period["start_year"]
        location_end = location_period["end_year"]
        overlap_end = end_year if location_end is None else min(end_year, location_end)

        if location_start > end_year or overlap_end < start_year:
            continue

        if (
            location_scope is not None
            and location_period["location_key"] not in location_scope
        ):
            continue

        return location_period["location"]

    return ""


def person_location_periods(person):
    events = person.get("timeline_events", []) if isinstance(person, dict) else []
    relocations = []

    for event in events if isinstance(events, list) else []:
        if (
            not isinstance(event, dict)
            or event.get("event_type") not in ("starting_location", "relocated")
        ):
            continue

        location_name = str(event.get("detail", "") or "").strip()
        date_text = str(event.get("date", "") or "").strip()
        year_text = date_text.split("-", 1)[0] if date_text else ""
        event_year = normalized_year(year_text)

        if location_name and event_year is not None:
            relocations.append((event_year, location_name))

    relocations.sort(key=location_event_sort_key)
    periods = []

    for index, (event_year, location_name) in enumerate(relocations):
        end_year = (
            relocations[index + 1][0] - 1
            if index + 1 < len(relocations)
            else None
        )
        periods.append(
            {
                "location": location_name,
                "location_key": normalize_location(location_name),
                "start_year": event_year,
                "end_year": end_year,
            }
        )

    return periods


def normalized_year(value):
    if isinstance(value, bool):
        return None

    try:
        year = int(value)
    except (TypeError, ValueError):
        return None

    return year if 1 <= year <= 9999 else None


def normalized_period_year(value):
    if isinstance(value, bool):
        return None

    try:
        year = int(value)
    except (TypeError, ValueError):
        return None

    if (
        year == 0
        or year < EARLIEST_CALCULATION_YEAR
        or year > LATEST_CALCULATION_YEAR
    ):
        return None

    return year


def location_event_sort_key(item):
    return item[0], item[1].casefold()


def period_person_result(person, date_text, location_name):
    result = deepcopy(person)
    result["period_date_text"] = str(date_text or "").strip()
    result["period_location"] = str(location_name or "").strip()
    return result


def lifespan_text(person):
    birth_date = format_date_parts(
        person.get("birth_year"),
        person.get("birth_month"),
        person.get("birth_day"),
        unknown="?",
    )
    death_date = (
        format_date_parts(
            person.get("death_year"),
            person.get("death_month"),
            person.get("death_day"),
            unknown="",
        )
        if bool(person.get("deceased"))
        else ""
    )

    if death_date:
        death_age_text = person_death_age_text(person)
        age_suffix = (
            f" ({death_age_text})"
            if death_age_text
            else ""
        )
        return f"{birth_date} to {death_date}{age_suffix}"

    return f"born {birth_date}"


def dated_result_sort_key(person):
    date_text = str(person.get("period_date_text", "") or "")
    date_parts = date_text.split("-") if date_text else []
    date_key = (
        normalized_year(date_parts[0]) if date_parts else None,
        normalized_year(date_parts[1]) if len(date_parts) > 1 else None,
        normalized_year(date_parts[2]) if len(date_parts) > 2 else None,
    )
    return (
        date_key[0] if date_key[0] is not None else 10000,
        date_key[1] if date_key[1] is not None else 0,
        date_key[2] if date_key[2] is not None else 0,
        str(person.get("displayed_name", "") or "").casefold(),
    )


def person_result_sort_key(person):
    birth_year = normalized_year(person.get("birth_year"))
    birth_month = normalized_year(person.get("birth_month"))
    birth_day = normalized_year(person.get("birth_day"))
    return (
        birth_year if birth_year is not None else 10000,
        birth_month if birth_month is not None else 13,
        birth_day if birth_day is not None else 32,
        str(person.get("displayed_name", "") or "").casefold(),
    )
