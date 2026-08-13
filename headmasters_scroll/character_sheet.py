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
from .character_attributes import ABILITY_SKILLS, calculate_character_attributes


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
        "ingredients", "brew_time", "additional_instructions", "raw_effect",
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
    for reading in _effective_book_readings(world, campaign):
        if not isinstance(reading, dict) or str(reading.get("person_id", "")) != person_id:
            continue
        book_id = str(reading.get("book_id", ""))
        book = world_books.get(book_id) or db_books.get(book_id)
        if not book:
            continue
        for kind, collection, record_id, source in _book_contents(book):
            if kind in grants and record_id:
                grants[kind].setdefault(record_id, (collection, f"Read {source}"))

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
            grants[kind].setdefault(record_id, (collection, f"Taught on {event.get('date', '')}"))

    result = {"spells": [], "proficiencies": [], "recipes": []}
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
            result["recipes"].append(_public_record(record, collection or requested_collection, source))
    for collection in result:
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


def _inventory(person_id: str, world: dict[str, Any], current: tuple[int, int, int]) -> list[dict[str, Any]]:
    owned: list[dict[str, Any]] = []
    for item in world.get("items", []) or []:
        if not isinstance(item, dict):
            continue
        passages = [entry for entry in item.get("passage_history", []) or [] if isinstance(entry, dict) and _is_effective(entry.get("date"), current)]
        passages.sort(key=lambda entry: (date_key(entry.get("date")) or (-999999, 1, 1), str(entry.get("time", ""))))
        if passages and str(passages[-1].get("person_id", "")) == person_id:
            owned.append({
                "record_id": str(item.get("record_id", "")),
                "name": str(item.get("name") or "Unnamed item"),
                "category": str(item.get("category") or "Item"),
                "description": str(item.get("description") or ""),
                "acquired": str(passages[-1].get("date") or ""),
                "method": str(passages[-1].get("method") or ""),
            })
    return sorted(owned, key=lambda item: (item["name"].casefold(), item["record_id"]))


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
    attributes = calculate_character_attributes(person, effective_world, database, game_datetime)
    knowledge = _knowledge(person_id, world, database, campaign, events)
    campaign_person = (campaign.get("game_state", {}).get("people", {}) or {}).get(person_id, {})
    birth_parts = [person.get("birth_year"), person.get("birth_month"), person.get("birth_day")]
    portrait = ((person.get("board") or {}).get("portrait") or {}) if isinstance(person.get("board"), dict) else {}
    return {
        "character_id": person_id,
        "character_name": str(person.get("displayed_name") or ""),
        "as_of": game_datetime,
        "history_policy": campaign.get("history_policy", "keep"),
        "overview": {
            "name": str(person.get("displayed_name") or ""),
            "portrait_asset_id": str(portrait.get("asset_id") or ""),
            "birth": "-".join(str(item) for item in birth_parts if item not in (None, "")),
            "school": str(person.get("school") or ""),
            "canon": bool(person.get("canon", False)),
            "narrative": str(person.get("narrative") or person.get("notes") or ""),
            "eminence": _overview_eminence(person),
            "game_datetime": game_datetime,
        },
        "attributes": attributes,
        **knowledge,
        "pets": _creature_relationships(person_id, world, database, events),
        "inventory": _inventory(person_id, world, current),
        "relationships": _human_relationships(person_id, world, events),
        "wounds": deepcopy(campaign_person.get("wounds", []) or []),
        "battle": deepcopy(campaign_person.get("battle")),
        "character_notes": deepcopy(campaign_person.get("character_notes", []) or []),
    }


def ability_for_skill(skill: str) -> str:
    return next((ability for ability, skills in ABILITY_SKILLS.items() if skill in skills), "")
