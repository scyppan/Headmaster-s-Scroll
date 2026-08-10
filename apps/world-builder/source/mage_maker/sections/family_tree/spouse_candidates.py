from copy import deepcopy

from mage_maker.sections.family_tree.relationships import (
    person_can_give_birth,
)


def spouse_candidates(focus_person, people, excluded_ids=None):
    focus = focus_person if isinstance(focus_person, dict) else {}
    focus_id = str(focus.get("record_id", "") or "")
    focus_can_give_birth = person_can_give_birth(focus)
    focus_year = integer_year(focus.get("birth_year"))
    excluded = {str(record_id or "") for record_id in (excluded_ids or [])}
    excluded.add(focus_id)

    if focus_year is None:
        return []

    candidates = []

    for person in people:
        if not isinstance(person, dict):
            continue

        person_id = str(person.get("record_id", "") or "")
        candidate_year = integer_year(person.get("birth_year"))

        if (
            not person_id
            or person_id in excluded
            or person_can_give_birth(person) == focus_can_give_birth
            or candidate_year is None
            or abs(candidate_year - focus_year) > 7
        ):
            continue

        match = shared_location_match(focus, person)
        candidate = deepcopy(person)
        candidate["_spouse_age_gap"] = abs(candidate_year - focus_year)
        candidate["_spouse_location_match"] = bool(match)
        candidate["_spouse_match"] = match or "No overlapping location evidence"
        candidate["_spouse_recent_location"] = most_recent_location(person)
        candidates.append(candidate)

    candidates.sort(key=spouse_candidate_sort_key)
    return candidates


def spouse_candidate_sort_key(person):
    return (
        0 if person.get("_spouse_location_match") else 1,
        int(person.get("_spouse_age_gap", 99)),
        str(person.get("displayed_name", "")).casefold(),
    )


def integer_year(value):
    if isinstance(value, bool):
        return None

    try:
        year = int(value)
    except (TypeError, ValueError):
        return None

    return year if 1 <= year <= 9999 else None


def location_periods(person):
    events = person.get("timeline_events", []) if isinstance(person, dict) else []
    relocations = []

    for event in events if isinstance(events, list) else []:
        if (
            not isinstance(event, dict)
            or event.get("event_type") not in ("starting_location", "relocated")
        ):
            continue

        location = str(event.get("detail", "") or "").strip()
        event_date = str(event.get("date", "") or "").strip()
        year = integer_year(event_date.split("-", 1)[0]) if event_date else None

        if location and year is not None:
            relocations.append((year, location))

    relocations.sort(key=relocation_sort_key)
    periods = []

    for index, (start_year, location) in enumerate(relocations):
        end_year = (
            relocations[index + 1][0] - 1
            if index + 1 < len(relocations)
            else None
        )
        periods.append(
            {
                "location": location,
                "location_key": normalize_location(location),
                "start_year": start_year,
                "end_year": end_year,
            }
        )

    return periods


def shared_location_match(first_person, second_person):
    matches = []

    for first_period in location_periods(first_person):
        for second_period in location_periods(second_person):
            if first_period["location_key"] != second_period["location_key"]:
                continue

            overlap = overlapping_years(first_period, second_period)

            if overlap is not None:
                matches.append((overlap[0], overlap[1], first_period["location"]))

    if not matches:
        return ""

    matches.sort(key=location_match_sort_key)
    start_year, end_year, location = matches[0]
    year_text = str(start_year) if end_year == start_year else (
        f"{start_year} onward" if end_year is None else f"{start_year}–{end_year}"
    )
    return f"Same location: {location} ({year_text})"


def most_recent_location(person):
    periods = location_periods(person)

    if periods:
        return periods[-1]["location"]

    events = person.get("timeline_events", []) if isinstance(person, dict) else []
    location = ""

    for event in events if isinstance(events, list) else []:
        if not isinstance(event, dict) or event.get("event_type") not in (
            "starting_location",
            "relocated",
        ):
            continue

        event_location = str(event.get("detail", "") or "").strip()

        if event_location:
            location = event_location

    return location


def overlapping_years(first_period, second_period):
    start_year = max(first_period["start_year"], second_period["start_year"])
    first_end = first_period["end_year"]
    second_end = second_period["end_year"]

    if first_end is None and second_end is None:
        end_year = None
    elif first_end is None:
        end_year = second_end
    elif second_end is None:
        end_year = first_end
    else:
        end_year = min(first_end, second_end)

    if end_year is not None and start_year > end_year:
        return None

    return start_year, end_year


def normalize_location(value):
    return " ".join(str(value or "").strip().casefold().split())


def relocation_sort_key(item):
    return item[0], item[1].casefold()


def location_match_sort_key(item):
    return item[0], item[2].casefold()
