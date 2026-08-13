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
TRAIT_SKILL_BONUSES = {
    "Star gazer": ("Astronomy", 3),
    "Bookworm": ("History", 3),
    "Animal lover": ("Creatures", 1),
    "People person": ("Social", 1),
    "Clairvoyant": ("Divination", 3),
    "Navigator": ("Flying", 2),
    "Observant": ("Perception", 1),
    "Green thumb": ("Herbology", 3),
    "Curious": ("Arithmancy", 1),
    "Inventive": ("Artificing", 1),
    "Runologist": ("Runes", 2),
}


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


def _started_developmental_years(
    person: dict[str, Any], game_date: tuple[int, int, int] | None
) -> list[dict[str, Any]]:
    """Return started developmental years, including years school was missed.

    Missing school suppresses curriculum credit, not the character's annual
    developmental ability choice.
    """

    plan = person.get("development_plan")
    records = plan.get("school_years", []) if isinstance(plan, dict) else []
    earned = []
    for record in records if isinstance(records, list) else []:
        if not isinstance(record, dict):
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
    # Legacy World Builder records predate the explicit ability-buy field.
    # Their two initial skill choices identify the corresponding abilities.
    if isinstance(initial, dict):
        for candidate in initial.get("skill_bonuses", []) or []:
            skill = str(candidate or "").strip()
            for ability, skills in ABILITY_SKILLS.items():
                if skill in skills:
                    values[ability] += 1
                    break
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


def _number(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _named_modifier_sources(
    sources: Iterable[dict[str, Any]], collection: str, name: str
) -> Counter[str]:
    """Collect optional equipment/temporary roll modifiers without exposing data.

    World Builder records and campaign state can both contribute to the same
    private projection.  The normalized ``roll_modifiers`` contract is used by
    new records, while the two older top-level names remain readable.
    """

    aliases = {
        "wand": ("wand", "wandbonus", "wand_bonus"),
        "accessories": ("accessories", "accessory", "accessory_bonus"),
        "passive": ("passive", "passive_bonus"),
        "temporary": ("temporary", "temporary_bonus", "temp_bonus"),
        "wand_quality": ("wand_quality", "wandquality"),
        "trait_bonus": ("trait_bonus", "trait"),
        "background": ("background", "background_bonus"),
    }
    result: Counter[str] = Counter()
    collection_aliases = tuple(dict.fromkeys((
        collection,
        "attributes" if collection == "abilities" else collection,
    )))
    legacy_key = "attribute_modifiers" if collection == "abilities" else "skill_modifiers"
    for source in sources:
        if not isinstance(source, dict):
            continue
        candidates: list[Any] = []
        roll_modifiers = source.get("roll_modifiers")
        if isinstance(roll_modifiers, dict):
            for key in collection_aliases:
                bucket = roll_modifiers.get(key)
                if isinstance(bucket, dict):
                    candidates.append(bucket.get(name, bucket.get(name.casefold())))
        legacy = source.get(legacy_key)
        if isinstance(legacy, dict):
            candidates.append(legacy.get(name, legacy.get(name.casefold())))
        for candidate in candidates:
            if isinstance(candidate, (int, float, str)):
                result["temporary"] += _number(candidate)
                continue
            if not isinstance(candidate, dict):
                continue
            for normalized, keys in aliases.items():
                value = next((candidate[key] for key in keys if key in candidate), 0)
                result[normalized] += _number(value)
    return result


def calculate_character_attributes(
    person: dict[str, Any],
    world: dict[str, Any],
    database: dict[str, Any],
    game_datetime: str,
    campaign_person: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the private, date-aware player Attributes panel payload."""

    game_date = _date_key(game_datetime)
    earned_years = _started_school_years(person, game_date)
    developmental_years = _started_developmental_years(person, game_date)

    ability_values = _initial_attribute_buys(person)
    for record in developmental_years:
        ability = str(record.get("ability", "") or "").strip()
        if ability in ability_values:
            ability_values[ability] += 1

    skill_values: Counter[str] = Counter({skill: 0 for skill in SKILL_NAMES})
    skill_sources: dict[str, Counter[str]] = {
        skill: Counter({
            "initial_buys": 0,
            "developmental_buys": 0,
            "core_courses": 0,
            "elective_courses": 0,
            "eminence": 0,
        })
        for skill in SKILL_NAMES
    }
    initial = person.get("initial_bonuses")
    if isinstance(initial, dict):
        for skill in initial.get("skill_bonuses", []) or []:
            normalized = str(skill or "").strip()
            if normalized in skill_values:
                skill_values[normalized] += 1
                skill_sources[normalized]["initial_buys"] += 1

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
                skill_sources[skill_name]["developmental_buys"] += 1
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
                skill_sources[course_name]["core_courses"] += 1
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
                skill_sources[course_name]["elective_courses"] += 1

    earned_eminence = _earned_eminence(person, world, game_date)
    skill_values.update(earned_eminence)
    for skill, points in earned_eminence.items():
        if skill in skill_sources:
            skill_sources[skill]["eminence"] += int(points)

    characteristics = person.get("characteristics")
    characteristic_buys: Counter[str] = Counter()
    for record in developmental_years:
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
    trait_skill_bonuses: Counter[str] = Counter()
    for trait in traits:
        definition = TRAIT_SKILL_BONUSES.get(trait)
        if definition:
            trait_skill_bonuses[definition[0]] += definition[1]

    modifier_sources = (person, campaign_person or {})
    ability_records = []
    for ability in ABILITY_NAMES:
        modifiers = _named_modifier_sources(modifier_sources, "abilities", ability)
        base = int(ability_values[ability])
        bonus = sum(modifiers[key] for key in ("wand", "accessories", "passive", "temporary"))
        ability_records.append({
            "name": ability,
            "value": base,
            "bonus": int(bonus),
            "total": base + int(bonus),
            "breakdown": {
                "base": base,
                "wand": int(modifiers["wand"]),
                "accessories": int(modifiers["accessories"]),
                "passive": int(modifiers["passive"]),
                "temporary": int(modifiers["temporary"]),
            },
        })

    skill_records = []
    spell_skills = {"Charms", "Dark Arts", "Defense", "Transfiguration"}
    for skill in SKILL_NAMES:
        modifiers = _named_modifier_sources(modifier_sources, "skills", skill)
        buys = int(skill_sources[skill]["initial_buys"] + skill_sources[skill]["developmental_buys"])
        background = int(modifiers["background"])
        if skill == "Muggles" and not background:
            blood_status = str(person.get("blood_status") or person.get("bloodstatus") or "").casefold()
            if blood_status in {"muggleborn", "muggle-raised halfblood"}:
                background = 10
        trait_bonus = int(modifiers["trait_bonus"] or trait_skill_bonuses[skill])
        base = int(skill_values[skill]) + background + trait_bonus
        wand_quality = int(modifiers["wand_quality"]) if skill in spell_skills else 0
        bonus = sum(modifiers[key] for key in ("wand", "accessories", "passive", "temporary")) + wand_quality
        breakdown = {
            "background": background,
            "buys": buys,
            "core_courses": int(skill_sources[skill]["core_courses"]),
            "elective_courses": int(skill_sources[skill]["elective_courses"]),
            "trait_bonus": trait_bonus,
            "wand": int(modifiers["wand"]),
            "accessories": int(modifiers["accessories"]),
            "eminence": int(skill_sources[skill]["eminence"]),
            "wand_quality": wand_quality,
            "passive": int(modifiers["passive"]),
            "temporary": int(modifiers["temporary"]),
            "base": base,
            "total": base + int(bonus),
        }
        labels = (
            ("Background", "background"),
            ("Buys", "buys"),
            ("Core courses", "core_courses"),
            ("Elective courses", "elective_courses"),
            ("Trait bonus", "trait_bonus"),
            ("Wand", "wand"),
            ("Accessories", "accessories"),
            ("Eminence", "eminence"),
            ("Wand quality", "wand_quality"),
            ("Passive", "passive"),
            ("Temporary", "temporary"),
        )
        skill_records.append({
            "name": skill,
            "value": base,
            "bonus": int(bonus),
            "total": base + int(bonus),
            "breakdown": breakdown,
            # Every source is intentionally present, including zeroes.  The
            # legacy Character Controls tooltip used this complete ledger.
            "sources": [
                {"label": label, "points": int(breakdown[key])}
                for label, key in labels
                if not (key == "background" and skill != "Muggles")
                and not (key == "wand_quality" and skill not in spell_skills)
            ],
        })

    return {
        "character_id": str(person.get("record_id", "") or ""),
        "character_name": str(person.get("displayed_name", "") or ""),
        "as_of": game_datetime,
        "attributes": ability_records,
        "skills": skill_records,
        "characteristics": characteristic_values,
        "parental_values": parental_values,
        "traits": traits,
    }
