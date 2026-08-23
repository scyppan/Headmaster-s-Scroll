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
    "invented_spell": "spell",
    "invented_proficiency": "proficiency",
    "invented_recipe": "recipe",
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
    "joined_friend_group": "Friend Group",
    "left_friend_group": "Friend Group",
}
RECIPE_COLLECTIONS = ("recipes", "potions", "preparations", "foods_and_drinks")
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
    # Some legacy book records have no category even though their title names a
    # supported subject explicitly.  Use whole slug terms only so incidental
    # words do not assign an unrelated cover.
    title_slug = re.sub(
        r"[^a-z0-9]+",
        "-",
        str(book.get("title") or book.get("name") or "").strip().casefold(),
    ).strip("-")
    for subject in sorted(BOOK_COVER_SUBJECTS, key=len, reverse=True):
        if re.search(rf"(?:^|-){re.escape(subject)}(?:-|$)", title_slug):
            return f"book-cover:{subject}"
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
        ("recipes", "recipe", "recipes"),
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
    person_record = next(
        (
            item
            for item in world.get("people", []) or []
            if isinstance(item, dict)
            and str(item.get("record_id", "")) == person_id
        ),
        {},
    )
    readings = _effective_book_readings(world, campaign)
    readings.extend(_development_year_readings(
        person_record,
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
            "author": str(book.get("author_name") or book.get("author") or ""),
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
            event_type = str(event.get("event_type", "") or "")
            source_name = (
                f"Invented by {person_record.get('displayed_name') or person_record.get('name') or 'this character'}"
                if event_type.startswith("invented_")
                else str(
                    event.get("teacher_name")
                    or event.get("instructor_name")
                    or event.get("source_name")
                    or "Unknown teacher"
                )
            )
            grants[kind].setdefault(record_id, (collection, source_name))

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
    database: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    database = database or {}
    definition_collections = (
        "wands", "holdable_items", "accessories", "general_items", "plants",
        "raw_materials", "potions", "preparations", "foods_and_drinks", "books",
    )
    by_id = {
        str(record.get("record_id", "")): (collection, record)
        for collection in definition_collections
        for record in database.get(collection, []) or [] if isinstance(record, dict)
    }
    for parent_collection, part_collection in (
        ("creatures", "creature_parts"),
        ("plants", "plant_parts"),
    ):
        for parent in database.get(parent_collection, []) or []:
            if not isinstance(parent, dict):
                continue
            for part in parent.get("parts", []) or []:
                if not isinstance(part, dict):
                    continue
                part_id = str(part.get("record_id", "") or "").strip()
                if part_id:
                    by_id[part_id] = (part_collection, part)
    by_name: dict[str, tuple[str, dict[str, Any]]] = {}
    for _definition_id, value in by_id.items():
        name = str(value[1].get("name", "") or "").strip().casefold()
        if name and name not in by_name:
            by_name[name] = value
    equipment = (campaign_person or {}).get("equipment", {}) or {}
    equipped_ids = {str(value) for value in equipment.values() if value}

    def enrich(entry: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
        definition_id = str(
            source.get("definition_record_id")
            or source.get("item_id")
            or source.get("part_id")
            or ""
        ).strip()
        resolved = by_id.get(definition_id)
        if resolved is None:
            resolved = by_name.get(str(source.get("name", "") or "").strip().casefold())
        collection, definition = resolved if resolved else (
            str(source.get("definition_collection", "") or ""), {}
        )
        definition_id = str(definition.get("record_id", "") or definition_id)
        explicit = str(definition.get("activation_mode", "") or "").strip().casefold()
        if not explicit:
            explicit = "equipped" if collection in {"wands", "holdable_items", "accessories"} else "passive"
        slot_type = str(definition.get("equipment_slot_type", "") or "").casefold()
        if not slot_type and collection in {"wands", "holdable_items"}:
            slot_type = "focus"
        elif not slot_type and collection == "accessories":
            slot_type = "accessory"
        entry.update({
            "definition_collection": collection,
            "definition_record_id": definition_id,
            "activation_mode": explicit,
            "equipment_slot_type": slot_type,
            "equipped": entry["record_id"] in equipped_ids,
            "bonuses": deepcopy(definition.get("bonuses", []) or source.get("bonuses", []) or []),
            "in_flight_effects": deepcopy(
                definition.get("in_flight_effects", [])
                or source.get("in_flight_effects", [])
                or []
            ),
            "actions": deepcopy(definition.get("actions", []) or source.get("actions", []) or []),
            "image_asset": str(
                definition.get("image_asset", "")
                or source.get("image_asset", "")
                or ""
            ),
            "base_knuts": int(
                definition.get("base_knuts", source.get("base_knuts", 0)) or 0
            ),
            "flight_threshold": definition.get("flight_threshold"),
            "airborne": bool((campaign_person or {}).get("airborne", False)),
        })
        if not entry.get("description"):
            entry["description"] = str(definition.get("description", "") or "")
        return entry

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
            owned.append(enrich({
                "record_id": record_id,
                "name": str(item.get("name") or "Unnamed item"),
                "category": str(item.get("category") or "Item"),
                "quantity": int(quantity) if quantity.is_integer() else quantity,
                "description": str(item.get("description") or ""),
                "acquired": str(passages[-1].get("date") or ""),
                "method": str(passages[-1].get("method") or ""),
            }, item))
    for stack in (campaign_person or {}).get("campaign_inventory", []) or []:
        if not isinstance(stack, dict):
            continue
        try:
            quantity = max(0, int(stack.get("quantity", 0)))
        except (TypeError, ValueError):
            continue
        if not quantity:
            continue
        owned.append(enrich({
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
        }, stack))
    return sorted(owned, key=lambda item: (item["name"].casefold(), item["record_id"]))


def _inventory_roll_modifiers(inventory: list[dict[str, Any]]) -> dict[str, Any]:
    modifiers: dict[str, dict[str, dict[str, int]]] = {
        "abilities": {}, "skills": {}, "characteristics": {},
    }
    for item in inventory:
        mode = str(item.get("activation_mode", "passive") or "passive").casefold()
        flyable = item.get("equipment_slot_type") == "flyable"
        active = (
            bool(item.get("equipped")) and bool(item.get("airborne"))
            if flyable
            else mode == "passive" or (mode == "equipped" and item.get("equipped"))
        )
        if not active:
            continue
        source_name = "accessories" if item.get("equipment_slot_type") == "accessory" else (
            "wand" if item.get("equipment_slot_type") == "focus" else "passive"
        )
        effects = (
            item.get("in_flight_effects", []) or []
            if flyable else item.get("bonuses", []) or []
        )
        # Legacy schema-eight Flyables are accepted until DBM next saves the
        # migrated catalog. They still receive the stricter target filter.
        if flyable and not effects:
            effects = item.get("bonuses", []) or []
        for bonus in effects:
            if not isinstance(bonus, dict):
                continue
            bonus_mode = str(
                bonus.get("activation_mode", "passive") or "passive"
            ).strip().casefold()
            if bonus_mode != "passive":
                continue
            target = str(bonus.get("target", "") or "").strip()
            kind = str(bonus.get("type", "") or "").strip().casefold()
            if flyable and target not in {
                "Flying", "Perception", "Strength", "Agility"
            }:
                continue
            if target == "Social Skills":
                target = "Social"
            collection = {
                "ability": "abilities", "attribute": "abilities",
                "skill": "skills", "characteristic": "characteristics",
            }.get(kind)
            if not collection or not target:
                continue
            try:
                amount = int(bonus.get("amount", 0) or 0)
            except (TypeError, ValueError):
                continue
            bucket = modifiers[collection].setdefault(target, {})
            bucket[source_name] = int(bucket.get(source_name, 0)) + amount
    return modifiers


def recipe_requirements(
    recipe: dict[str, Any], inventory: list[dict[str, Any]],
    known_proficiency_ids: set[str] | None = None,
    known_spell_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Calculate AND/OR requirements and an authoritative consumption plan.

    Each requirement group is mandatory.  The alternatives inside a group are
    interchangeable, so ``Alembic OR Retort`` is one vessel requirement rather
    than two.  Legacy flat ingredient/vessel fields remain supported.
    """

    formulations = recipe.get("formulations")
    if isinstance(formulations, list) and formulations:
        evaluated = []
        for formulation in formulations:
            if not isinstance(formulation, dict):
                continue
            candidate = deepcopy(recipe)
            candidate.pop("formulations", None)
            for field in (
                "output_item", "output_quantity", "ingredient_requirements",
                "vessel_requirements", "proficiency_requirements",
                "spell_requirements",
            ):
                candidate[field] = deepcopy(formulation.get(field))
            result = recipe_requirements(
                candidate, inventory, known_proficiency_ids, known_spell_ids
            )
            result["formulation_id"] = str(formulation.get("record_id", ""))
            result["formulation_name"] = str(formulation.get("name", "") or "Formulation")
            evaluated.append(result)
        selected = next((item for item in evaluated if item.get("ready")), None)
        if selected is None and evaluated:
            selected = evaluated[0]
        if selected is None:
            return {"ready": False, "missing": ["valid formulation"], "formulations": []}
        result = deepcopy(selected)
        result["formulations"] = evaluated
        return result

    available_items = [item for item in inventory if isinstance(item, dict)]
    known_proficiency_ids = {
        str(value) for value in (known_proficiency_ids or set()) if str(value)
    }
    known_spell_ids = {
        str(value) for value in (known_spell_ids or set()) if str(value)
    }
    missing: list[str] = []
    consumption: dict[str, float] = {}

    def number(value: Any, default: float = 1.0) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return default

    def clean_number(value: float) -> int | float:
        return int(value) if value.is_integer() else value

    def matches(item: dict[str, Any], requirement: dict[str, Any]) -> bool:
        requirement_id = str(
            requirement.get("record_id") or requirement.get("item_id") or ""
        ).strip()
        requirement_collection = str(requirement.get("collection") or "").strip()
        item_ids = {
            str(item.get("record_id", "")),
            str(item.get("definition_record_id", "")),
            str(item.get("item_id", "")),
            str(item.get("part_id", "")),
        }
        if requirement_id:
            if requirement_id not in item_ids:
                return False
            item_collection = str(item.get("definition_collection") or "").strip()
            if requirement_collection and item_collection:
                return requirement_collection == item_collection
            return True
        requirement_name = str(
            requirement.get("name") or requirement.get("title") or ""
        ).strip().casefold()
        return bool(
            requirement_name
            and str(item.get("name", "")).strip().casefold() == requirement_name
        )

    def candidates(
        requirement: dict[str, Any], *, allow_name_fragment: bool = False,
    ) -> list[dict[str, Any]]:
        matched = [item for item in available_items if matches(item, requirement)]
        if matched or not allow_name_fragment:
            return matched
        if requirement.get("record_id") or requirement.get("item_id"):
            return matched
        name = str(
            requirement.get("name") or requirement.get("title") or ""
        ).strip().casefold()
        if not name:
            return matched
        return [
            item for item in available_items
            if name in str(item.get("name", "")).strip().casefold()
        ]

    def remaining_quantity(item: dict[str, Any]) -> float:
        stack_id = str(item.get("record_id", "")).strip()
        return max(
            0.0,
            number(item.get("quantity", 1), 1.0)
            - number(consumption.get(stack_id, 0), 0.0),
        )

    raw_ingredient_groups = recipe.get("ingredient_requirements")
    if not isinstance(raw_ingredient_groups, list):
        raw_ingredient_groups = [
            {
                "record_id": f"legacy-ingredient-{index}",
                "alternatives": [
                    raw if isinstance(raw, dict) else {"name": str(raw)}
                ],
            }
            for index, raw in enumerate(recipe.get("ingredients", []) or [])
        ]

    ingredient_rows: list[dict[str, Any]] = []
    for group in raw_ingredient_groups:
        alternatives = [
            value for value in (group.get("alternatives", []) or [])
            if isinstance(value, dict)
        ] if isinstance(group, dict) else []
        evaluated: list[dict[str, Any]] = []
        selected: tuple[dict[str, Any], list[dict[str, Any]], float] | None = None
        for alternative in alternatives:
            required = max(1.0, number(alternative.get("quantity", 1), 1.0))
            matching = candidates(alternative)
            available = sum(remaining_quantity(item) for item in matching)
            name = str(alternative.get("name") or "Item").strip() or "Item"
            row = {
                "name": name,
                "required": clean_number(required),
                "available": clean_number(available),
                "missing": clean_number(max(0.0, required - available)),
                "collection": str(alternative.get("collection") or ""),
                "record_id": str(alternative.get("record_id") or ""),
            }
            evaluated.append(row)
            if selected is None and available >= required:
                selected = (alternative, matching, required)

        ingredient_rows.append({
            "record_id": str(group.get("record_id") or "") if isinstance(group, dict) else "",
            "alternatives": evaluated,
            "selected": str(selected[0].get("name") or "") if selected else "",
            "available": selected is not None,
            "output_item": deepcopy(selected[0].get("output_item")) if selected else None,
            "output_quantity_modifier": int(selected[0].get("output_quantity_modifier", 0) or 0) if selected else 0,
        })
        if selected is None:
            label = " OR ".join(
                f"{row['missing']} {row['name']}" for row in evaluated
            ) or "ingredient"
            missing.append(label)
            continue
        _alternative, matching, required = selected
        remaining = required
        for item in matching:
            if remaining <= 0:
                break
            stack_id = str(item.get("record_id", "")).strip()
            quantity = remaining_quantity(item)
            used = min(remaining, quantity)
            if stack_id and used:
                consumption[stack_id] = consumption.get(stack_id, 0.0) + used
            remaining -= used

    raw_vessel_groups = recipe.get("vessel_requirements")
    if not isinstance(raw_vessel_groups, list):
        raw_vessel = recipe.get("required_vessel") or recipe.get("vessel")
        raw_vessel_groups = [] if not raw_vessel else [{
            "record_id": "legacy-vessel",
            "alternatives": [
                raw_vessel if isinstance(raw_vessel, dict) else {"name": raw_vessel}
            ],
        }]
    vessel_rows: list[dict[str, Any]] = []
    for group in raw_vessel_groups:
        alternatives = [
            value for value in (group.get("alternatives", []) or [])
            if isinstance(value, dict)
        ] if isinstance(group, dict) else []
        evaluated = [
            {
                "name": str(value.get("name") or "Vessel"),
                "available": bool(candidates(value, allow_name_fragment=True)),
                "collection": str(value.get("collection") or ""),
                "record_id": str(value.get("record_id") or ""),
                "output_item": deepcopy(value.get("output_item")),
                "output_quantity_modifier": int(value.get("output_quantity_modifier", 0) or 0),
            }
            for value in alternatives
        ]
        selected = next((row for row in evaluated if row["available"]), None)
        vessel_rows.append({
            "record_id": str(group.get("record_id") or "") if isinstance(group, dict) else "",
            "alternatives": evaluated,
            "selected": selected["name"] if selected else "",
            "available": selected is not None,
            "output_item": deepcopy(selected.get("output_item")) if selected else None,
            "output_quantity_modifier": int(selected.get("output_quantity_modifier", 0) or 0) if selected else 0,
        })
        if selected is None:
            missing.append(
                "vessel: " + (" OR ".join(row["name"] for row in evaluated) or "unspecified")
            )

    proficiency_rows: list[dict[str, Any]] = []
    for group in recipe.get("proficiency_requirements", []) or []:
        alternatives = [
            value for value in (group.get("alternatives", []) or [])
            if isinstance(value, dict)
        ] if isinstance(group, dict) else []
        evaluated = [
            {
                "name": str(value.get("name") or "Proficiency"),
                "record_id": str(value.get("record_id") or ""),
                "known": str(value.get("record_id") or "") in known_proficiency_ids,
            }
            for value in alternatives
        ]
        selected = next((row for row in evaluated if row["known"]), None)
        proficiency_rows.append({
            "record_id": str(group.get("record_id") or "") if isinstance(group, dict) else "",
            "alternatives": evaluated,
            "selected": selected["name"] if selected else "",
            "available": selected is not None,
        })
        if selected is None:
            missing.append(
                "proficiency: "
                + (" OR ".join(row["name"] for row in evaluated) or "unspecified")
            )

    spell_rows: list[dict[str, Any]] = []
    for group in recipe.get("spell_requirements", []) or []:
        alternatives = [
            value for value in (group.get("alternatives", []) or [])
            if isinstance(value, dict)
        ] if isinstance(group, dict) else []
        evaluated = [{
            "name": str(value.get("name") or "Spell"),
            "record_id": str(value.get("record_id") or ""),
            "known": str(value.get("record_id") or "") in known_spell_ids,
        } for value in alternatives]
        selected = next((row for row in evaluated if row["known"]), None)
        spell_rows.append({
            "record_id": str(group.get("record_id") or "") if isinstance(group, dict) else "",
            "alternatives": evaluated,
            "selected": selected["name"] if selected else "",
            "selected_record_id": selected["record_id"] if selected else "",
            "available": selected is not None,
        })
        if selected is None:
            missing.append(
                "spell: " + (" OR ".join(row["name"] for row in evaluated) or "unspecified")
            )

    output_item = deepcopy(recipe.get("output_item"))
    output_quantity = max(1, int(number(recipe.get("output_quantity", 1), 1.0)))
    for row in ingredient_rows + vessel_rows:
        if row.get("output_item"):
            output_item = deepcopy(row["output_item"])
        output_quantity += int(row.get("output_quantity_modifier", 0) or 0)
    output_quantity = max(1, output_quantity)

    return {
        "ready": not missing,
        "ingredients": ingredient_rows,
        "vessels": vessel_rows,
        "vessel": next(
            (
                {"name": row["selected"], "available": True}
                for row in vessel_rows if row["selected"]
            ),
            None,
        ),
        "proficiencies": proficiency_rows,
        "spells": spell_rows,
        "output_item": output_item,
        "output_quantity": output_quantity,
        "missing": missing,
        "consumption": {
            item_id: clean_number(quantity)
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
    knowledge = _knowledge(person_id, world, database, campaign, events)
    shared_tag_names = {
        str(item.get("record_id", "")): str(item.get("name", "") or "")
        for item in campaign.get("shared_tags", []) or [] if isinstance(item, dict)
    }
    assignments: dict[tuple[str, str], list[str]] = {}
    for item in campaign.get("tag_assignments", []) or []:
        if not isinstance(item, dict):
            continue
        tag_name = shared_tag_names.get(str(item.get("tag_id", "")))
        if tag_name:
            assignments.setdefault((str(item.get("collection", "")), str(item.get("target_record_id", ""))), []).append(tag_name)
    for public_collection, records in (("spells", knowledge["spells"]), ("proficiencies", knowledge["proficiencies"]), ("recipes", knowledge["recipes"])):
        for record in records:
            source_collection = str(record.get("collection", "") or public_collection)
            merged = [str(value) for value in record.get("tags", []) or []]
            for value in assignments.get((source_collection, str(record.get("record_id", ""))), []):
                if value not in merged:
                    merged.append(value)
            record["tags"] = merged
    inventory = _inventory(person_id, world, current, campaign_person, database)
    campaign_creatures = (campaign.get("game_state", {}).get("creatures", {}) or {}).values()
    species_index = _record_index(database, "creatures")
    campaign_pets: list[dict[str, Any]] = []
    for raw_creature in campaign_creatures:
        if not isinstance(raw_creature, dict):
            continue
        related = str(raw_creature.get("related_character_id", "") or "") == person_id
        carried = str(raw_creature.get("carried_by_character_id", "") or "") == person_id
        if not related and not carried:
            continue
        species = species_index.get(str(raw_creature.get("species_record_id", "") or ""), {})
        relationship = str(raw_creature.get("relationship_state", "") or ("captured" if carried else ""))
        campaign_pets.append({
            "record_id": str(raw_creature.get("record_id", "") or ""),
            "name": str(raw_creature.get("name", "") or raw_creature.get("species_name", "Creature")),
            "relationships": [relationship] if relationship else [],
            "relationship_group": {
                "tamed": "Tamed Pets", "bonded": "Bonded Allies",
                "lured": "Lured Creatures", "captured": "Captured Creatures",
            }.get(relationship, "Creature Relationships"),
            "species": {
                "record_id": str(species.get("record_id", "") or ""),
                "name": str(species.get("name", "") or raw_creature.get("species_name", "Creature")),
                "classification": str(species.get("classification", "") or ""),
                "size": deepcopy((raw_creature.get("generated") or {}).get("size")),
                "movement": deepcopy((raw_creature.get("generated") or {}).get("movement", {})),
                "wound_cap": deepcopy((raw_creature.get("generated") or {}).get("heavy_wound_cap")),
                "attacks": deepcopy(raw_creature.get("actions", [])),
            },
            "history": deepcopy(raw_creature.get("relationship_history", []) or []),
            "campaign_created": True,
        })
        if carried:
            inventory.append({
                "record_id": f"carried-creature:{raw_creature.get('record_id', '')}",
                "name": str(raw_creature.get("name", "") or raw_creature.get("species_name", "Creature")),
                "category": "Creatures & Plants", "quantity": 1,
                "description": "A living captured creature.", "acquired": "",
                "method": "Captured", "activation_mode": "passive",
                "equipment_slot_type": "", "equipped": False,
                "bonuses": [], "actions": [],
            })
    effective_campaign_person = deepcopy(campaign_person)
    inventory_modifiers = _inventory_roll_modifiers(inventory)
    existing_modifiers = effective_campaign_person.setdefault("roll_modifiers", {})
    for collection, records in inventory_modifiers.items():
        target_collection = existing_modifiers.setdefault(collection, {})
        for name, values in records.items():
            target = target_collection.setdefault(name, {})
            for source, amount in values.items():
                target[source] = int(target.get(source, 0) or 0) + amount
    attributes = calculate_character_attributes(
        person, effective_world, database, game_datetime, effective_campaign_person
    )
    known_proficiency_ids = {
        str(record.get("record_id", ""))
        for record in knowledge["proficiencies"]
        if isinstance(record, dict) and record.get("record_id")
    }
    known_spell_ids = {
        str(record.get("record_id", ""))
        for record in knowledge["spells"]
        if isinstance(record, dict) and record.get("record_id")
    }
    for recipe in knowledge["recipes"]:
        recipe["requirements"] = recipe_requirements(
            recipe, inventory, known_proficiency_ids, known_spell_ids
        )
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
            "portrait_asset_version": str(portrait.get("sha256") or ""),
            "birth": birth_display,
            "age": _age_at(person, current),
            "school": str(person.get("school") or ""),
            "canon": bool(person.get("canon", False)),
            "narrative": str(person.get("narrative") or person.get("notes") or ""),
            "eminence": _overview_eminence(person),
        },
        "attributes": attributes,
        **knowledge,
        "pets": [*_creature_relationships(person_id, world, database, events), *campaign_pets],
        "inventory": sorted(inventory, key=lambda item: (str(item.get("name", "")).casefold(), str(item.get("record_id", "")))),
        "equipment": deepcopy((campaign_person or {}).get("equipment", {}) or {}),
        "airborne": bool((campaign_person or {}).get("airborne", False)),
        "currency_knuts": max(0, int((campaign_person or {}).get("currency_knuts", 0) or 0)),
        "shared_tags": [
            deepcopy(item) for item in campaign.get("shared_tags", []) or []
            if isinstance(item, dict)
        ],
        "relationships": _human_relationships(person_id, world, events),
        "wounds": deepcopy(campaign_person.get("wounds", []) or []),
        "battle": deepcopy(campaign_person.get("battle")),
        "character_notes": deepcopy(campaign_person.get("character_notes", []) or []),
    }


def ability_for_skill(skill: str) -> str:
    return next((ability for ability, skills in ABILITY_SKILLS.items() if skill in skills), "")
