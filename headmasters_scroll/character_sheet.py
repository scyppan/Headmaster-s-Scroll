from __future__ import annotations

"""Private, date-effective player character-sheet projection.

The browser receives this projection rather than any canonical data file.  It
contains only the linked character and records that character is authorized to
know at the campaign's current date.
"""

import calendar
import re
from copy import deepcopy
from typing import Any, Iterable

from .campaigns import HISTORY_DISCARD
from .character_attributes import (
    ABILITY_SKILLS,
    _historical_year_shift,
    _school_year_start,
    calculate_character_attributes,
)


DATE_PATTERN = re.compile(
    r"^(?P<year>-?[1-9]\d*)(?:-(?P<month>\d{2})(?:-(?P<day>\d{2}))?)?"
)
TEACHING_TYPES = {
    "taught_spell": "spell",
    "taught_proficiency": "proficiency",
    "taught_recipe": "recipe",
}
CREATURE_TYPES = {
    "tamed_creature": "pet",
    "bonded_creature": "ally",
    "irked_creature": "irked",
}
RELATIONSHIP_TYPES = {
    "began_friendship": "Friendship",
    "romance": "Romance",
    "got_married": "Marriage",
    "breakup": "Breakup",
    "gave_birth": "Family",
    "had_child": "Family",
    "born": "Family",
    "family": "Family",
    "relationship": "Other",
}
RECIPE_COLLECTIONS = ("potions", "preparations", "foods_and_drinks")
BOOK_COVER_SUBJECTS = {
    "alchemy", "arithmancy", "artificing", "astronomy", "charms", "creatures",
    "dark-arts", "defense", "divination", "flying", "herbology",
    "history", "muggles", "potions", "runes", "transfiguration",
}


def _book_cover_asset_id(book: dict[str, Any]) -> str:
    """Choose a local subject cover without exposing a filesystem path."""

    for category in book.get("categories", []) or []:
        slug = re.sub(r"[^a-z0-9]+", "-", str(category).strip().casefold()).strip("-")
        if slug in BOOK_COVER_SUBJECTS:
            return f"book-cover:{slug}"
    return ""


def date_key(value: Any, *, latest: bool = False) -> tuple[int, int, int] | None:
    match = DATE_PATTERN.match(str(value or "").strip())
    if match is None:
        return None
    year = int(match.group("year"))
    month = int(match.group("month") or (12 if latest else 1))
    if not 1 <= month <= 12:
        return None
    day = int(match.group("day") or (calendar.monthrange(year, month)[1] if latest else 1))
    if not 1 <= day <= calendar.monthrange(year, month)[1]:
        return None
    return year, month, day


def _is_effective(value: Any, boundary: tuple[int, int, int]) -> bool:
    candidate = date_key(value)
    return candidate is not None and candidate <= boundary


def effective_campaign_events(
    world: dict[str, Any], campaign: dict[str, Any]
) -> list[dict[str, Any]]:
    """Resolve the campaign branch without copying universal history."""

    state = campaign.get("game_state", {}) if isinstance(campaign, dict) else {}
    current = date_key(state.get("current_game_datetime"))
    if current is None:
        current = date_key(campaign.get("game_world_start_date")) or (1, 1, 1)
    world_boundary = current
    if campaign.get("history_policy") == HISTORY_DISCARD:
        world_boundary = date_key(campaign.get("game_world_start_date")) or current

    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source, boundary in (
        (world.get("events", []) or [], world_boundary),
        (campaign.get("events", []) or [], current),
    ):
        for raw in source:
            if not isinstance(raw, dict) or not _is_effective(raw.get("date"), boundary):
                continue
            record_id = str(raw.get("record_id", "") or "")
            identity = record_id or repr(sorted(raw.items()))
            if identity in seen:
                continue
            seen.add(identity)
            result.append(deepcopy(raw))
    result.sort(key=lambda item: (date_key(item.get("date")) or (-999999, 1, 1), str(item.get("time", "")), str(item.get("record_id", ""))))
    return result


def _effective_book_readings(
    world: dict[str, Any], campaign: dict[str, Any]
) -> list[dict[str, Any]]:
    """Apply the same campaign-history branch to dated book readings."""

    current = date_key(
        (campaign.get("game_state", {}) or {}).get("current_game_datetime")
    ) or date_key(campaign.get("game_world_start_date")) or (1, 1, 1)
    boundary = current
    if campaign.get("history_policy") == HISTORY_DISCARD:
        boundary = date_key(campaign.get("game_world_start_date")) or current
    return [
        deepcopy(reading)
        for reading in world.get("book_readings", []) or []
        if isinstance(reading, dict)
        and _is_effective(reading.get("date"), boundary)
    ]


def _book_history_boundary(campaign: dict[str, Any]) -> tuple[int, int, int]:
    current = date_key(
        (campaign.get("game_state", {}) or {}).get("current_game_datetime")
    ) or date_key(campaign.get("game_world_start_date")) or (1, 1, 1)
    if campaign.get("history_policy") == HISTORY_DISCARD:
        return date_key(campaign.get("game_world_start_date")) or current
    return current


def _development_year_readings(
    person: dict[str, Any], database: dict[str, Any], campaign: dict[str, Any]
) -> list[dict[str, str]]:
    """Derive books that the character necessarily finished by the branch date.

    Curriculum books are read at the start of an attended school year.  The
    recreational slots in both school and adult years mature on September 1,
    January 1, and June 1 respectively.  This is a projection only: it does not
    duplicate deterministic biography into world.json or campaign.json.
    """

    plan = person.get("development_plan")
    if not isinstance(plan, dict):
        return []
    boundary = _book_history_boundary(campaign)
    schools = {
        str(item.get("name", "")).strip().casefold(): item
        for item in database.get("schools", []) or []
        if isinstance(item, dict) and str(item.get("name", "")).strip()
    }
    readings: list[dict[str, str]] = []

    def add(book: Any, when: tuple[int, int, int], source: str) -> None:
        if when > boundary:
            return
        if isinstance(book, dict):
            book_id = str(book.get("record_id") or book.get("book_id") or "")
        else:
            book_id = str(book or "")
        if book_id:
            readings.append({
                "person_id": str(person.get("record_id") or ""),
                "book_id": book_id,
                "date": f"{when[0]}-{when[1]:02d}-{when[2]:02d}",
                "source": source,
            })

    def recreational(records: list[Any], start: tuple[int, int, int], source: str) -> None:
        next_year = _historical_year_shift(start[0], 1)
        dates = ((start[0], 9, 1), (next_year, 1, 1), (next_year, 6, 1))
        for index, book in enumerate(records[:3]):
            add(book, dates[index], source)

    school_records = plan.get("school_years", []) or []
    for raw_year in school_records if isinstance(school_records, list) else []:
        if not isinstance(raw_year, dict):
            continue
        try:
            school_year = int(raw_year.get("year"))
        except (TypeError, ValueError):
            continue
        start = _school_year_start(person, school_year)
        if start is None:
            continue
        school_name = str(raw_year.get("school") or person.get("school") or "").strip()
        school = schools.get(school_name.casefold())
        if school is not None and not bool(raw_year.get("skipped", False)):
            curriculum = next((
                item for item in school.get("curriculum", []) or []
                if isinstance(item, dict) and str(item.get("year")) == str(school_year)
            ), {})
            allowed_courses = {
                str(value).strip().casefold()
                for value in curriculum.get("core", []) or []
                if str(value).strip()
            }
            offered_electives = {
                str(value).strip().casefold()
                for value in curriculum.get("electives", []) or []
                if str(value).strip()
            }
            selected_electives = {
                str(value).strip().casefold()
                for value in raw_year.get("electives", []) or []
                if str(value).strip()
            }
            allowed_courses.update(offered_electives & selected_electives)
            for assignment in school.get("course_books", []) or []:
                if not isinstance(assignment, dict):
                    continue
                if str(assignment.get("year")) != str(school_year):
                    continue
                if str(assignment.get("course", "")).strip().casefold() not in allowed_courses:
                    continue
                add(
                    assignment,
                    start,
                    "",
                )
        recreational(
            list(raw_year.get("books", []) or []),
            start,
            f"Recreational reading, school year {school_year}",
        )

    school_one = _school_year_start(person, 1)
    for raw_year in plan.get("adult_years", []) or []:
        if not isinstance(raw_year, dict) or school_one is None:
            continue
        try:
            adult_year = int(raw_year.get("adult_year") or raw_year.get("year"))
        except (TypeError, ValueError):
            continue
        start_year = _historical_year_shift(school_one[0], 7 + adult_year - 1)
        recreational(
            list(raw_year.get("books", []) or []),
            (start_year, 9, 1),
            f"Recreational reading, adult year {adult_year}",
        )
    return readings


def _record_index(database: dict[str, Any], collection: str) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("record_id", "")): item
        for item in database.get(collection, []) or []
        if isinstance(item, dict) and item.get("record_id")
    }


def _public_record(record: dict[str, Any], collection: str, source: str) -> dict[str, Any]:
    allowed = {
        "record_id", "name", "title", "description", "skill", "subtype",
        "tradition", "threshold", "required_materials", "required_proficiencies",
        "ingredients", "required_vessel", "vessel", "brew_time",
        "additional_instructions", "raw_effect",
        "effect_in_potions", "effect_in_other_potions", "raw_effects",
        "effects_in_potions", "history", "rationale", "incantation", "tags",
        "creature_type", "classification", "size", "wound_cap",
        "movement", "attacks", "abilities", "magical", "sentient",
        "magical_resistance", "intelligence", "social_skill",
        "can_be_lured", "can_be_tamed", "can_bond",
        "additional_social_rules", "in_situ_instinct",
    }
    result = {key: deepcopy(value) for key, value in record.items() if key in allowed}
    result["record_id"] = str(record.get("record_id", ""))
    result["name"] = str(record.get("name") or record.get("title") or "Unknown")
    result["collection"] = collection
    result["source"] = source
    return result


def _person_is_in_event(event: dict[str, Any], person_id: str) -> bool:
    person_ids = event.get("person_ids", []) or []
    return person_id in {str(item) for item in person_ids} or str(event.get("person_id", "")) == person_id


def _book_contents(book: dict[str, Any]) -> Iterable[tuple[str, str, str, str]]:
    for item in book.get("contents", []) or []:
        if not isinstance(item, dict):
            continue
        content_type = str(item.get("content_type", "")).casefold()
        yield (
            content_type,
            str(item.get("collection", "")),
            str(item.get("record_id", "")),
            str(book.get("title") or book.get("name") or "Book"),
        )
    for key, kind, collection in (
        ("spells", "spell", "spells"),
        ("proficiencies", "proficiency", "proficiencies"),
        ("potions", "recipe", "potions"),
        ("preparations", "recipe", "preparations"),
    ):
        for item in book.get(key, []) or []:
            if isinstance(item, dict):
                yield kind, collection, str(item.get("record_id", "")), str(book.get("name") or book.get("title") or "Book")


def _knowledge(
    person_id: str,
    world: dict[str, Any],
    database: dict[str, Any],
    campaign: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    catalogs = {
        "spell": _record_index(database, "spells"),
        "proficiency": _record_index(database, "proficiencies"),
    }
    recipe_catalog: dict[str, tuple[str, dict[str, Any]]] = {}
    for collection in RECIPE_COLLECTIONS:
        for record_id, record in _record_index(database, collection).items():
            recipe_catalog[record_id] = (collection, record)

    world_books = _record_index(world, "books")
    db_books = _record_index(database, "books")
    grants: dict[str, dict[str, tuple[str, str]]] = {
        "spell": {}, "proficiency": {}, "recipe": {},
    }
    read_books: dict[str, dict[str, Any]] = {}
    readings = _effective_book_readings(world, campaign)
    readings.extend(_development_year_readings(
        next((item for item in world.get("people", []) or [] if isinstance(item, dict) and str(item.get("record_id", "")) == person_id), {}),
        database,
        campaign,
    ))
    for reading in readings:
        if not isinstance(reading, dict) or str(reading.get("person_id", "")) != person_id:
            continue
        book_id = str(reading.get("book_id", ""))
        book = world_books.get(book_id) or db_books.get(book_id)
        if not book:
            continue
        public_book = read_books.setdefault(book_id, {
            "record_id": book_id,
            "title": str(book.get("title") or book.get("name") or "Book"),
            "author": str(book.get("author") or ""),
            "description": str(book.get("description") or ""),
            "categories": [str(item) for item in book.get("categories", []) or []],
            "cover_asset_id": _book_cover_asset_id(book),
            "read_at": str(reading.get("date") or ""),
            "contents": {"spells": [], "proficiencies": [], "recipes": []},
        })
        for kind, collection, record_id, source in _book_contents(book):
            if kind in grants and record_id:
                # The source is the actual book, not the year/course timing
                # which caused that book to be read.
                reading_source = str(source or book.get("title") or book.get("name") or "Book")
                grants[kind].setdefault(record_id, (collection, reading_source))
                content_key = {
                    "spell": "spells",
                    "proficiency": "proficiencies",
                    "recipe": "recipes",
                }[kind]
                if record_id not in public_book["contents"][content_key]:
                    public_book["contents"][content_key].append(record_id)

    for event in events:
        kind = TEACHING_TYPES.get(str(event.get("event_type", "")))
        if kind is None or not _person_is_in_event(event, person_id):
            continue
        record_id = str(
            event.get("knowledge_record_id")
            or event.get(f"{kind}_id")
            or event.get("target_record_id")
            or ""
        )
        collection = str(event.get("knowledge_collection", ""))
        if kind == "spell":
            collection = "spells"
        elif kind == "proficiency":
            collection = "proficiencies"
        elif not collection:
            collection = "potions"
        if record_id:
            teacher = str(
                event.get("teacher_name")
                or event.get("instructor_name")
                or event.get("source_name")
                or "Unknown teacher"
            )
            grants[kind].setdefault(record_id, (collection, teacher))

    result = {
        "books": sorted(
            read_books.values(),
            key=lambda item: (item["title"].casefold(), item["record_id"]),
        ),
        "spells": [], "proficiencies": [], "recipes": [],
    }
    for record_id, (_, source) in grants["spell"].items():
        if record_id in catalogs["spell"]:
            result["spells"].append(_public_record(catalogs["spell"][record_id], "spells", source))
    for record_id, (_, source) in grants["proficiency"].items():
        if record_id in catalogs["proficiency"]:
            result["proficiencies"].append(_public_record(catalogs["proficiency"][record_id], "proficiencies", source))
    for record_id, (requested_collection, source) in grants["recipe"].items():
        resolved = recipe_catalog.get(record_id)
        if resolved:
            collection, record = resolved
            public = _public_record(record, collection or requested_collection, source)
            if not public.get("required_vessel") and not public.get("vessel") and collection == "potions":
                public["required_vessel"] = "Cauldron"
            result["recipes"].append(public)
    for collection in ("spells", "proficiencies", "recipes"):
        result[collection].sort(key=lambda item: (item["name"].casefold(), item["record_id"]))
    return result


def _creature_relationships(
    person_id: str, world: dict[str, Any], database: dict[str, Any], events: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    named = _record_index(world, "named_creatures")
    species = _record_index(database, "creatures")
    relationships: dict[str, dict[str, Any]] = {}
    for event in events:
        relation = CREATURE_TYPES.get(str(event.get("event_type", "")))
        if relation is None or not _person_is_in_event(event, person_id):
            continue
        named_id = str(event.get("named_creature_id") or event.get("creature_id") or "")
        creature = named.get(named_id)
        if creature is None:
            continue
        item = relationships.setdefault(named_id, {
            "record_id": named_id,
            "name": str(creature.get("name") or "Unnamed creature"),
            "species_id": str(creature.get("species_record_id") or creature.get("creature_species_id") or ""),
            "relationships": [],
            "history": [],
        })
        if relation not in item["relationships"]:
            item["relationships"].append(relation)
        item["history"].append({"relationship": relation, "date": event.get("date", ""), "note": event.get("description") or event.get("note") or ""})
    for item in relationships.values():
        species_record = species.get(item["species_id"])
        if species_record:
            item["species"] = _public_record(species_record, "creatures", "World Builder")
    return sorted(relationships.values(), key=lambda item: (item["name"].casefold(), item["record_id"]))


def _human_relationships(person_id: str, world: dict[str, Any], events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    people = _record_index(world, "people")
    result: list[dict[str, Any]] = []
    for event in events:
        group = RELATIONSHIP_TYPES.get(str(event.get("event_type", "")))
        if group is None or not _person_is_in_event(event, person_id):
            continue
        related = [str(item) for item in event.get("person_ids", []) or [] if str(item) != person_id]
        for field in (
            "baby_person_ids",
            "birthing_parent_person_ids",
            "non_birthing_parent_person_ids",
        ):
            related.extend(
                str(item)
                for item in event.get(field, []) or []
                if str(item) != person_id
            )
        related_id = str(event.get("related_person_id", ""))
        if related_id and related_id != person_id:
            related.append(related_id)
        names = [str(people[item].get("displayed_name") or "Unknown") for item in dict.fromkeys(related) if item in people]
        result.append({
            "record_id": str(event.get("record_id", "")),
            "type": group,
            "event_type": str(event.get("event_type", "")),
            "date": str(event.get("date", "")),
            "people": names,
            "detail": str(event.get("description") or event.get("note") or event.get("detail") or ""),
        })
    result.sort(key=lambda item: (item["type"], date_key(item["date"]) or (-999999, 1, 1)))
    return result


def _overview_eminence(person: dict[str, Any]) -> int:
    plan = person.get("development_plan")
    if not isinstance(plan, dict):
        return 0
    total = 0
    for record in plan.get("initial_eminence", []) or []:
        if isinstance(record, dict):
            try:
                total += max(0, int(record.get("points", 1) or 0))
            except (TypeError, ValueError):
                continue
    for collection in ("school_years", "adult_years"):
        for year in plan.get(collection, []) or []:
            if not isinstance(year, dict):
                continue
            for record in year.get("eminence", []) or []:
                if isinstance(record, dict):
                    try:
                        total += max(0, int(record.get("points", 1) or 0))
                    except (TypeError, ValueError):
                        continue
    return total


def _age_at(person: dict[str, Any], current: tuple[int, int, int]) -> int | None:
    try:
        birth = (
            int(person.get("birth_year")),
            int(person.get("birth_month") or 1),
            int(person.get("birth_day") or 1),
        )
    except (TypeError, ValueError):
        return None
    if birth > current:
        return None
    years = current[0] - birth[0]
    # Historical calendars have no year zero.
    if birth[0] < 0 < current[0]:
        years -= 1
    if (current[1], current[2]) < (birth[1], birth[2]):
        years -= 1
    return max(0, years)


def _inventory(
    person_id: str, world: dict[str, Any], current: tuple[int, int, int],
    campaign_person: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    owned: list[dict[str, Any]] = []
    consumed = (campaign_person or {}).get("consumed_inventory", {}) or {}
    for item in world.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        passages = [entry for entry in item.get("passage_history", []) or [] if isinstance(entry, dict) and _is_effective(entry.get("date"), current)]
        passages.sort(key=lambda entry: (date_key(entry.get("date")) or (-999999, 1, 1), str(entry.get("time", ""))))
        if passages and str(passages[-1].get("person_id", "")) == person_id:
            record_id = str(item.get("record_id", ""))
            try:
                quantity = max(0.0, float(item.get("quantity", 1) or 0))
                quantity -= max(0.0, float(consumed.get(record_id, 0) or 0))
            except (TypeError, ValueError):
                quantity = 1.0
            if quantity <= 0:
                continue
            owned.append({
                "record_id": record_id,
                "name": str(item.get("name") or "Unnamed item"),
                "category": str(item.get("category") or "Item"),
                "quantity": int(quantity) if quantity.is_integer() else quantity,
                "description": str(item.get("description") or ""),
                "acquired": str(passages[-1].get("date") or ""),
                "method": str(passages[-1].get("method") or ""),
            })
    for stack in (campaign_person or {}).get("campaign_inventory", []) or []:
        if not isinstance(stack, dict):
            continue
        try:
            quantity = max(0, int(stack.get("quantity", 0)))
        except (TypeError, ValueError):
            continue
        if not quantity:
            continue
        owned.append({
            "record_id": str(stack.get("record_id") or ""),
            "item_id": str(stack.get("item_id") or stack.get("part_id") or ""),
            "part_id": str(stack.get("part_id") or ""),
            "name": str(stack.get("name") or "Creature part"),
            "category": str(stack.get("category") or "Creature Part"),
            "quantity": quantity,
            "description": "Harvested during this campaign.",
            "acquired": str(stack.get("acquired_at") or ""),
            "method": "Harvested",
            "source_creature_id": str(stack.get("source_creature_id") or ""),
            "source_species_id": str(stack.get("source_species_id") or ""),
        })
    return sorted(owned, key=lambda item: (item["name"].casefold(), item["record_id"]))


def recipe_requirements(
    recipe: dict[str, Any], inventory: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate recipe readiness and an authoritative item-consumption plan."""

    available_items = [item for item in inventory if isinstance(item, dict)]
    ingredient_rows: list[dict[str, Any]] = []
    missing: list[str] = []
    consumption: dict[str, float] = {}

    for raw in recipe.get("ingredients", []) or []:
        ingredient = raw if isinstance(raw, dict) else {"name": str(raw)}
        name = str(ingredient.get("name") or ingredient.get("title") or "").strip()
        item_id = str(
            ingredient.get("item_id") or ingredient.get("record_id") or ""
        ).strip()
        if not name and not item_id:
            continue
        try:
            required = max(0.0, float(ingredient.get("quantity", 1) or 1))
        except (TypeError, ValueError):
            required = 1.0
        candidates = [
            item for item in available_items
            if (
                item_id and item_id in {
                    str(item.get("record_id", "")),
                    str(item.get("item_id", "")),
                    str(item.get("part_id", "")),
                }
            ) or (
                not item_id and name
                and str(item.get("name", "")).strip().casefold() == name.casefold()
            )
        ]
        available = 0.0
        for item in candidates:
            try:
                available += max(0.0, float(item.get("quantity", 1) or 0))
            except (TypeError, ValueError):
                available += 1.0
        shortfall = max(0.0, required - available)
        display_name = name or next(
            (str(item.get("name") or "Item") for item in candidates), "Item"
        )
        ingredient_rows.append({
            "name": display_name,
            "required": int(required) if required.is_integer() else required,
            "available": int(available) if available.is_integer() else available,
            "missing": int(shortfall) if shortfall.is_integer() else shortfall,
        })
        if shortfall:
            amount = int(shortfall) if shortfall.is_integer() else shortfall
            missing.append(f"{amount} {display_name}")
            continue
        remaining = required
        for item in candidates:
            if remaining <= 0:
                break
            try:
                quantity = max(0.0, float(item.get("quantity", 1) or 0))
            except (TypeError, ValueError):
                quantity = 1.0
            used = min(remaining, quantity)
            record_id = str(item.get("record_id", "")).strip()
            if record_id and used:
                consumption[record_id] = consumption.get(record_id, 0.0) + used
            remaining -= used

    raw_vessel = recipe.get("required_vessel") or recipe.get("vessel")
    vessel: dict[str, Any] | None = None
    if raw_vessel:
        vessel_value = raw_vessel if isinstance(raw_vessel, dict) else {"name": raw_vessel}
        vessel_name = str(vessel_value.get("name") or vessel_value.get("title") or "Vessel").strip()
        vessel_id = str(vessel_value.get("item_id") or vessel_value.get("record_id") or "").strip()
        vessel_key = vessel_name.casefold()
        vessel_available = any(
            (vessel_id and vessel_id in {
                str(item.get("record_id", "")),
                str(item.get("item_id", "")),
                str(item.get("part_id", "")),
            })
            or (
                not vessel_id
                and vessel_key
                and vessel_key in str(item.get("name", "")).strip().casefold()
            )
            for item in available_items
        )
        vessel = {"name": vessel_name, "available": vessel_available}
        if not vessel_available:
            missing.append(f"vessel: {vessel_name}")

    return {
        "ready": not missing,
        "ingredients": ingredient_rows,
        "vessel": vessel,
        "missing": missing,
        "consumption": {
            item_id: int(quantity) if quantity.is_integer() else quantity
            for item_id, quantity in consumption.items()
        },
    }


def build_character_sheet(
    person: dict[str, Any],
    world: dict[str, Any],
    database: dict[str, Any],
    campaign: dict[str, Any],
) -> dict[str, Any]:
    person_id = str(person.get("record_id", ""))
    game_datetime = str(campaign.get("game_state", {}).get("current_game_datetime") or f"{campaign.get('game_world_start_date')}T08:00")
    current = date_key(game_datetime) or (1, 1, 1)
    events = effective_campaign_events(world, campaign)
    effective_world = deepcopy(world)
    effective_world["events"] = events
    campaign_person = (campaign.get("game_state", {}).get("people", {}) or {}).get(person_id, {})
    attributes = calculate_character_attributes(
        person, effective_world, database, game_datetime, campaign_person
    )
    knowledge = _knowledge(person_id, world, database, campaign, events)
    inventory = _inventory(person_id, world, current, campaign_person)
    for recipe in knowledge["recipes"]:
        recipe["requirements"] = recipe_requirements(recipe, inventory)
    birth_parts = [person.get("birth_year"), person.get("birth_month"), person.get("birth_day")]
    try:
        birth_display = (
            f"{int(person.get('birth_day')):02d} "
            f"{calendar.month_abbr[int(person.get('birth_month'))]} "
            f"{int(person.get('birth_year'))}"
        )
    except (TypeError, ValueError, IndexError):
        birth_display = "-".join(str(item) for item in birth_parts if item not in (None, ""))
    portrait = ((person.get("board") or {}).get("portrait") or {}) if isinstance(person.get("board"), dict) else {}
    return {
        "character_id": person_id,
        "character_name": str(person.get("displayed_name") or ""),
        "as_of": game_datetime,
        "overview": {
            "name": str(person.get("displayed_name") or ""),
            "portrait_asset_id": str(portrait.get("asset_id") or ""),
            "birth": birth_display,
            "age": _age_at(person, current),
            "school": str(person.get("school") or ""),
            "canon": bool(person.get("canon", False)),
            "narrative": str(person.get("narrative") or person.get("notes") or ""),
            "eminence": _overview_eminence(person),
        },
        "attributes": attributes,
        **knowledge,
        "pets": _creature_relationships(person_id, world, database, events),
        "inventory": inventory,
        "relationships": _human_relationships(person_id, world, events),
        "wounds": deepcopy(campaign_person.get("wounds", []) or []),
        "battle": deepcopy(campaign_person.get("battle")),
        "character_notes": deepcopy(campaign_person.get("character_notes", []) or []),
    }


def ability_for_skill(skill: str) -> str:
    return next((ability for ability, skills in ABILITY_SKILLS.items() if skill in skills), "")
