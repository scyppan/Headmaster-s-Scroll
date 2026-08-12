from __future__ import annotations

import calendar
import hashlib
import re
from collections import Counter
from typing import Any, Iterable


ABILITY_SKILLS = {
    "Power": ("Charms", "Transfiguration", "Defense", "Dark Arts"),
    "Erudition": ("Arithmancy", "Runes", "History", "Muggles"),
    "Panache": ("Potions", "Alchemy", "Artificing", "Flying", "Herbology"),
    "Naturalism": ("Creatures", "Astronomy", "Divination", "Perception", "Social"),
}
ABILITY_NAMES = tuple(ABILITY_SKILLS)
SKILL_NAMES = tuple(
    skill for ability in ABILITY_NAMES for skill in ABILITY_SKILLS[ability]
)
CHARACTERISTIC_NAMES = (
    "fortitude",
    "willpower",
    "intellect",
    "creativity",
    "equanimity",
    "charisma",
    "attractiveness",
    "strength",
    "agility",
)
PARENTAL_NAMES = ("generosity", "permissiveness", "wealth")
GAME_DATE = re.compile(
    r"^(?P<year>-?[1-9]\d*)(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?"
)
EVENT_EMINENCE_PREFIX = "event-eminence-"


def _historical_year_shift(year: int, amount: int) -> int:
    """Shift a historical year without inventing a year zero."""

    shifted = year
    direction = 1 if amount >= 0 else -1
    for _ in range(abs(amount)):
        shifted += direction
        if shifted == 0:
            shifted += direction
    return shifted


def _date_key(value: Any, *, latest: bool = False) -> tuple[int, int, int] | None:
    match = GAME_DATE.match(str(value or "").strip())
    if match is None:
        return None
    year = int(match.group("year"))
    month = int(match.group("month") or (12 if latest else 1))
    if not 1 <= month <= 12:
        return None
    day = int(
        match.group("day")
        or (calendar.monthrange(year, month)[1] if latest else 1)
    )
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return year, month, day


def _school_start_year(person: dict[str, Any]) -> int | None:
    try:
        birth_year = int(person.get("birth_year"))
    except (TypeError, ValueError):
        return None
    if birth_year == 0:
        return None
    try:
        birth_month = int(person.get("birth_month"))
    except (TypeError, ValueError):
        birth_month = None
    try:
        birth_day = int(person.get("birth_day"))
    except (TypeError, ValueError):
        birth_day = None
    after_cutoff = bool(
        birth_month is not None
        and (birth_month > 9 or (birth_month == 9 and birth_day is not None and birth_day > 1))
    )
    return _historical_year_shift(birth_year, 12 if after_cutoff else 11)


def _school_year_start(person: dict[str, Any], school_year: int) -> tuple[int, int, int] | None:
    start_year = _school_start_year(person)
    if start_year is None:
        return None
    return _historical_year_shift(start_year, school_year - 1), 9, 1


def _started_school_years(
    person: dict[str, Any], game_date: tuple[int, int, int] | None
) -> list[dict[str, Any]]:
    plan = person.get("development_plan")
    records = plan.get("school_years", []) if isinstance(plan, dict) else []
    earned = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict) or bool(record.get("skipped", False)):
            continue
        try:
            year = int(record.get("year"))
        except (TypeError, ValueError):
            continue
        if not 1 <= year <= 7:
            continue
        boundary = _school_year_start(person, year)
        if game_date is None or boundary is None or boundary <= game_date:
            earned.append(record)
    return earned


def _initial_attribute_buys(person: dict[str, Any]) -> dict[str, int]:
    """Read the two explicitly selected initial attribute buys when present."""

    initial = person.get("initial_bonuses")
    explicit = person.get("initial_attribute_buys")
    if explicit in (None, "") and isinstance(initial, dict):
        explicit = initial.get("attribute_buys")
    plan = person.get("development_plan")
    if explicit in (None, "") and isinstance(plan, dict):
        explicit = plan.get("initial_attribute_buys")
    if isinstance(explicit, dict):
        return {
            ability: max(0, int(explicit.get(ability, explicit.get(ability.casefold(), 0)) or 0))
            for ability in ABILITY_NAMES
        }
    values = {ability: 0 for ability in ABILITY_NAMES}
    if isinstance(explicit, (list, tuple)):
        for candidate in explicit:
            ability = str(candidate or "").strip()
            if ability in values:
                values[ability] += 1
    return values


def _school_catalog(database: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(school.get("name", "")).strip().casefold(): school
        for school in database.get("schools", [])
        if isinstance(school, dict) and str(school.get("name", "")).strip()
    }


def _curriculum_for_year(
    school: dict[str, Any], school_year: int
) -> dict[str, Any] | None:
    for curriculum in school.get("curriculum", []) or []:
        if not isinstance(curriculum, dict):
            continue
        try:
            if int(curriculum.get("year")) == school_year:
                return curriculum
        except (TypeError, ValueError):
            continue
    return None


def _event_record_id(event_id: str, person_id: str) -> str:
    identity = f"{event_id}|{person_id}"
    return EVENT_EMINENCE_PREFIX + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]


def _all_eminence_records(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for record in plan.get("initial_eminence", []) or []:
        if isinstance(record, dict):
            yield record
    for collection_name in ("school_years", "adult_years"):
        for year in plan.get(collection_name, []) or []:
            if not isinstance(year, dict):
                continue
            for record in year.get("eminence", []) or []:
                if isinstance(record, dict):
                    yield record


def _earned_eminence(
    person: dict[str, Any],
    world: dict[str, Any],
    game_date: tuple[int, int, int] | None,
) -> Counter[str]:
    plan = person.get("development_plan")
    if not isinstance(plan, dict):
        return Counter()
    person_id = str(person.get("record_id", "") or "")
    events_by_record = {}
    for event in world.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("record_id", "") or "")
        if not event_id or not person_id:
            continue
        events_by_record[_event_record_id(event_id, person_id)] = event

    counts: Counter[str] = Counter()
    for record in _all_eminence_records(plan):
        skill = str(record.get("skill", "") or "").strip()
        if skill not in SKILL_NAMES:
            continue
        linked_event = events_by_record.get(str(record.get("record_id", "") or ""))
        if linked_event is not None and game_date is not None:
            event_date = _date_key(linked_event.get("date"))
            if event_date is not None and event_date > game_date:
                continue
        try:
            points = max(0, int(record.get("points", 1) or 0))
        except (TypeError, ValueError):
            points = 1
        counts[skill] += points
    return counts


def calculate_character_attributes(
    person: dict[str, Any],
    world: dict[str, Any],
    database: dict[str, Any],
    game_datetime: str,
) -> dict[str, Any]:
    """Build the private, date-aware player Attributes panel payload."""

    game_date = _date_key(game_datetime)
    earned_years = _started_school_years(person, game_date)

    ability_values = _initial_attribute_buys(person)
    for record in earned_years:
        ability = str(record.get("ability", "") or "").strip()
        if ability in ability_values:
            ability_values[ability] += 1

    skill_values: Counter[str] = Counter({skill: 0 for skill in SKILL_NAMES})
    initial = person.get("initial_bonuses")
    if isinstance(initial, dict):
        for skill in initial.get("skill_bonuses", []) or []:
            normalized = str(skill or "").strip()
            if normalized in skill_values:
                skill_values[normalized] += 1

    schools = _school_catalog(database)
    default_school = str(person.get("school", "") or "").strip()
    for record in earned_years:
        school_name = str(record.get("school", "") or default_school).strip()
        school = schools.get(school_name.casefold())
        # World Builder stores developmental skill buys independently of
        # school attendance and curriculum. Each occurrence is one point,
        # including repeated focus selections in the same year.
        for skill in record.get("skills", []) or []:
            skill_name = str(skill or "").strip()
            if skill_name in skill_values:
                skill_values[skill_name] += 1
        try:
            school_year = int(record.get("year"))
        except (TypeError, ValueError):
            continue
        curriculum = _curriculum_for_year(school or {}, school_year)
        if curriculum is None:
            continue
        for course in curriculum.get("core", []) or []:
            course_name = str(course or "").strip()
            if course_name in skill_values:
                skill_values[course_name] += 1
        offered = {
            str(course or "").strip()
            for course in curriculum.get("electives", []) or []
        }
        selected = {
            str(course or "").strip()
            for course in record.get("electives", []) or []
        }
        for course_name in offered & selected:
            if course_name in skill_values:
                skill_values[course_name] += 1

    skill_values.update(_earned_eminence(person, world, game_date))

    characteristics = person.get("characteristics")
    characteristic_buys: Counter[str] = Counter()
    for record in earned_years:
        name = str(record.get("characteristic", "") or "").strip().casefold()
        if name in CHARACTERISTIC_NAMES:
            characteristic_buys[name] += 1
    characteristic_values = []
    for name in CHARACTERISTIC_NAMES:
        try:
            dice = int((characteristics or {}).get(name, 1)) + characteristic_buys[name]
        except (TypeError, ValueError):
            dice = 1 + characteristic_buys[name]
        characteristic_values.append({"name": name.title(), "dice": min(5, max(1, dice))})

    parental = person.get("parental_values")
    parental_values = []
    for name in PARENTAL_NAMES:
        try:
            value = int((parental or {}).get(name, 0))
        except (TypeError, ValueError):
            value = 0
        parental_values.append({"name": name.title(), "value": value})

    traits = []
    if isinstance(initial, dict):
        traits = [str(item).strip() for item in initial.get("traits", []) or [] if str(item).strip()]

    return {
        "character_id": str(person.get("record_id", "") or ""),
        "character_name": str(person.get("displayed_name", "") or ""),
        "as_of": game_datetime,
        "attributes": [
            {"name": ability, "value": ability_values[ability]}
            for ability in ABILITY_NAMES
        ],
        "skills": [
            {"name": skill, "value": int(skill_values[skill])}
            for skill in SKILL_NAMES
        ],
        "characteristics": characteristic_values,
        "parental_values": parental_values,
        "traits": traits,
    }
