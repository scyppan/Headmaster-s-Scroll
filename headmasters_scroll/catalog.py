from __future__ import annotations

import re
from collections import Counter
from copy import deepcopy
from typing import Any, Iterable
from uuid import NAMESPACE_URL, uuid5

from .effects import (
    IN_FLIGHT_EFFECT_TARGETS,
    TARGET_SCOPES,
    normalize_bonuses,
    normalize_in_flight_effects,
    normalize_target_scope,
    validate_bonuses,
    validate_in_flight_effects,
)


BOOK_CATEGORIES = (
    "Alchemy", "Arithmancy", "Artificing", "Astronomy", "Charms",
    "Creatures", "Dark Arts", "Defense", "Divination", "Herbology",
    "History", "Muggles", "Potions", "Runes", "Transfiguration",
)

CANONICAL_TAGS = (
    "Damage", "Shielding", "Healing", "Restoration", "Control", "Movement",
    "Travel", "Detection", "Concealment", "Revelation", "Transformation",
    "Summoning", "Banishing", "Enhancement", "Hindrance", "Mental", "Social",
    "Communication", "Environmental", "Countermagic", "Crafting", "Brewing",
    "Cooking", "Research", "Identification", "Harvesting", "Creature Care",
    "Ritual", "Poison", "Disease", "Ingredient Processing", "Utility",
    "Creature Awareness",
)

_CATEGORY_TERMS = {
    "Alchemy": ("alchemy", "alchemical"),
    "Arithmancy": ("arithmancy", "arithmet", "mathematic", "numerology"),
    "Artificing": ("artific", "enchanting objects", "magical object", "wandmaking"),
    "Astronomy": ("astronomy", "astronomical", "celestial", "constellation", "star ", "moon"),
    "Charms": ("charm", "incantation"),
    "Creatures": ("creature", "beast", "dragon", "animal", "familiar"),
    "Dark Arts": ("dark art", "curse", "necrom", "forbidden magic"),
    "Defense": ("defense", "defence", "protect", "shield", "counter-curse", "duelling"),
    "Divination": ("divination", "diviner", "palmistry", "prophecy", "fortune", "tarot"),
    "Herbology": ("herbology", "plant", "botan", "flora", "fung"),
    "History": ("history", "historical", "war ", "biography", "chronicle"),
    "Muggles": ("muggle", "non-magical", "technology"),
    "Potions": ("potion", "draught", "elixir", "brewing", "cauldron"),
    "Runes": ("rune", "runic", "glyph"),
    "Transfiguration": ("transfiguration", "transform", "switching", "conjuration"),
}

_TAG_TERMS = {
    "Damage": ("damage", "wound", "explode", "explosion", "burn", "strike", "attack", "venomous"),
    "Shielding": ("shield", "barrier", "protect", "guard against"),
    "Healing": ("heal", "healing", "cure", "remedy", "mend wound"),
    "Restoration": ("restore", "repair", "replenish", "revive"),
    "Control": ("control", "restrain", "bind", "immobil", "command"),
    "Movement": ("move", "flight", "flying", "levitat", "speed", "slow"),
    "Travel": ("travel", "transport", "teleport", "portkey", "journey"),
    "Detection": ("detect", "sense", "locate", "track", "observe"),
    "Concealment": ("conceal", "hide", "invisible", "disguise", "subterfuge"),
    "Revelation": ("reveal", "unmask", "make visible", "identify"),
    "Transformation": ("transform", "transfigur", "switch", "turns into", "changes into"),
    "Summoning": ("summon", "conjur", "call forth"),
    "Banishing": ("banish", "repel", "dismiss", "send away"),
    "Enhancement": ("enhance", "increase", "improve", "strengthen", "bonus"),
    "Hindrance": ("hinder", "reduce", "penalty", "weaken", "impair"),
    "Mental": ("mind", "memory", "thought", "emotion", "fear", "confus"),
    "Social": ("social", "persuad", "charm a person", "deceiv", "conversation"),
    "Communication": ("communicat", "message", "speak", "language", "signal"),
    "Environmental": ("weather", "water", "fire", "air", "earth", "temperature", "light"),
    "Countermagic": ("counterspell", "counter-", "dispel", "undo spell", "anti-magic"),
    "Crafting": ("craft", "make", "create", "construction", "artific"),
    "Brewing": ("brew", "potion", "draught", "elixir", "cauldron"),
    "Cooking": ("cook", "bake", "food", "drink", "meal", "recipe"),
    "Research": ("research", "study", "theory", "history", "lore"),
    "Identification": ("identify", "recognize", "classification", "awareness"),
    "Harvesting": ("harvest", "extract", "collect", "butcher", "gather"),
    "Creature Care": ("creature", "beast", "tame", "bond", "lure", "animal"),
    "Ritual": ("ritual", "ceremony", "rite"),
    "Poison": ("poison", "venom", "toxic", "antidote"),
    "Disease": ("disease", "infection", "illness", "spattergroit"),
    "Ingredient Processing": ("solution", "infusion", "powder", "chopped", "crushed", "soak", "distill"),
}

_SKILL_CATEGORY = {
    "alchemy": "Alchemy", "arithmancy": "Arithmancy", "artificing": "Artificing",
    "astronomy": "Astronomy", "charms": "Charms", "creatures": "Creatures",
    "dark arts": "Dark Arts", "defense": "Defense", "defence": "Defense",
    "divination": "Divination", "herbology": "Herbology", "history": "History",
    "muggles": "Muggles", "potions": "Potions", "runes": "Runes",
    "transfiguration": "Transfiguration",
}

# Human-reviewed corrections for legacy books which have no structured subject
# links and whose titles are more informative than their sparse descriptions.
_BOOK_CATEGORY_OVERRIDES = {
    "book_1224": ["Charms"],                    # A Clean Home is a Happy Home
    "book_4026": ["Charms"],                    # Mending Broken Objects
    "book_26945": ["Defense"],                  # Marine Defensive Rituals
    "book_28750": ["Charms"],                   # Chant Locks
    "book_1313": ["Potions"],                   # Asiatic Anti-Venoms
    "book_1097": ["Potions"],                   # Classical Poisons
    "book_1250": ["Defense"],                   # Magical Ailments
    "book_1256": ["Defense"],                   # Defensive Magical Theory
    "book_1218": ["Artificing"],                # Elementary Wandcraft
    "book_1221": ["Herbology"],                 # Gnomes and Gardens
    "book_1222": ["Herbology"],                 # Grand Gardening
    "book_1287": ["Artificing"],                # Broom Care
    "book_6732": ["Herbology"],                 # Herbological Extraction
    "book_1223": ["Potions"],                   # Homemade Potion Ingredients
    "book_1354": ["Potions"],                   # Ingredient Encyclopedia
    "book_1318": ["Charms"],                    # Madcap Magic
    "book_1241": ["Astronomy"],                 # Planetary Movements
    "book_4060": ["Charms"],                    # Pranks and Trick Spells
    "book_1220": ["Artificing"],                # Rare Wand Cores
    "book_1219": ["Artificing"],                # Rare Wand Woods
    "book_28397": ["Herbology"],                # Ryugu Lotus Cultures
    "book_1243": ["Astronomy"],                 # Transneptunian Objects
    "book_1337": ["Artificing"],                # Wandlore
    "book_1312": ["Artificing"],                # Where There's a Wand
}


def canonical_tag_id(name: str) -> str:
    return "catalog-tag-" + str(uuid5(NAMESPACE_URL, f"charms-check:tag:{name.casefold()}"))


def _record_text(record: dict[str, Any]) -> str:
    fields = (
        "name", "description", "raw_effect", "raw_effects", "effect_in_potions",
        "effect_in_other_potions", "additional_instructions", "history", "subtype",
        "skill", "tradition", "type",
    )
    return " ".join(str(record.get(field, "") or "") for field in fields).casefold()


def infer_tags(record: dict[str, Any], collection: str) -> list[str]:
    text = _record_text(record)
    tags = {
        tag for tag, terms in _TAG_TERMS.items() if any(term in text for term in terms)
    }
    if collection == "potions":
        tags.add("Brewing")
    elif collection == "preparations":
        tags.add("Ingredient Processing")
    elif collection == "foods_and_drinks":
        tags.add("Cooking")
    elif collection == "proficiencies" and "creature awareness" in {
        str(value).strip().casefold() for value in record.get("tags", []) or []
    }:
        tags.update(("Creature Awareness", "Identification", "Creature Care"))
    elif collection == "spells" and not tags:
        tags.add("Utility")
    elif not tags:
        tags.add("Research" if collection == "proficiencies" else "Utility")
    existing = {str(value).strip() for value in record.get("tags", []) or [] if str(value).strip()}
    tags.update(existing)
    return sorted(tags, key=str.casefold)


def infer_book_categories(book: dict[str, Any], indexes: dict[str, dict[str, dict[str, Any]]]) -> list[str]:
    existing = [str(value).strip() for value in book.get("categories", []) or []]
    existing = [value for value in existing if value in BOOK_CATEGORIES]
    # Existing categories were entered by the project author and are therefore
    # the reviewed source of truth.  Automated enrichment only fills books
    # which do not have a category; it never broadens curated classifications
    # because a descriptive paragraph happens to mention another subject.
    if existing:
        return list(dict.fromkeys(existing))
    reviewed = _BOOK_CATEGORY_OVERRIDES.get(str(book.get("record_id", "") or ""))
    if reviewed:
        return list(reviewed)
    linked: Counter[str] = Counter()
    for collection in ("spells", "proficiencies", "potions"):
        for link in book.get(collection, []) or []:
            record_id = str(link.get("record_id", "") if isinstance(link, dict) else link)
            record = indexes.get(collection, {}).get(record_id, {})
            skill = str(record.get("skill", "") or "").strip().casefold()
            category = _SKILL_CATEGORY.get(skill)
            if category:
                linked[category] += 4
            elif collection == "potions":
                linked["Potions"] += 4
    title = str(book.get("name", "") or "").casefold()
    description = " ".join(
        str(book.get(field, "") or "")
        for field in ("description", "history", "additional_instructions")
    ).casefold()
    title_evidence = Counter({
        category: sum(title.count(term) for term in terms) * 3
        for category, terms in _CATEGORY_TERMS.items()
    })
    description_evidence = Counter({
        category: sum(description.count(term) for term in terms)
        for category, terms in _CATEGORY_TERMS.items()
    })
    candidates = Counter(linked)
    candidates.update({key: value for key, value in title_evidence.items() if value})
    candidates.update({key: value for key, value in description_evidence.items() if value})
    if not candidates:
        # Contentless general works are historical/reference material unless a
        # human supplies a more specific category later.
        candidates["History"] = 1
    ordered = [name for name, _score in candidates.most_common()]
    primary_score = candidates[ordered[0]]
    inferred = [ordered[0]]
    for name in ordered[1:]:
        # A secondary category must be both genuinely competitive with the
        # primary and supported by linked content or explicit title language.
        # This keeps truly cross-disciplinary works while rejecting incidental
        # mentions in blurbs.
        strong_evidence = linked[name] > 0 or title_evidence[name] > 0
        if strong_evidence and candidates[name] >= max(3, primary_score * 0.7):
            inferred.append(name)
        if len(inferred) == 2:
            break
    return inferred


def enrich_catalog(document: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    result = deepcopy(document)
    indexes = {
        name: {str(item.get("record_id", "")): item for item in result.get(name, []) or []}
        for name in ("spells", "proficiencies", "potions")
    }
    category_changes = []
    for book in result.get("books", []) or []:
        before = list(book.get("categories", []) or [])
        after = infer_book_categories(book, indexes)
        book["categories"] = after
        if before != after:
            category_changes.append({"record_id": book["record_id"], "name": book.get("name", ""), "before": before, "after": after})

    tag_changes = []
    for collection in ("spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks"):
        for record in result.get(collection, []) or []:
            before = list(record.get("tags", []) or [])
            after = infer_tags(record, collection)
            record["tags"] = after
            record["tag_ids"] = [canonical_tag_id(name) for name in after if name in CANONICAL_TAGS]
            if before != after:
                tag_changes.append({"collection": collection, "record_id": record["record_id"], "name": record.get("name", ""), "before": before, "after": after})
            if collection in {"spells", "proficiencies", "potions", "preparations"}:
                record["target_scope"] = normalize_target_scope(
                    record.get("target_scope")
                )

    result["tag_catalog"] = [
        {"record_id": canonical_tag_id(name), "name": name, "normalized_name": name.casefold()}
        for name in CANONICAL_TAGS
    ]
    item_behavior_changes = []
    for collection, activation_mode, slot_type in (
        ("wands", "equipped", "focus"),
        ("holdable_items", "equipped", "focus"),
        ("accessories", "equipped", "accessory"),
        ("general_items", "passive", ""),
        ("plants", "passive", ""),
    ):
        for record in result.get(collection, []) or []:
            before = {
                "activation_mode": record.get("activation_mode"),
                "equipment_slot_type": record.get("equipment_slot_type"),
            }
            record["activation_mode"] = str(
                record.get("activation_mode", activation_mode) or activation_mode
            ).casefold()
            record["equipment_slot_type"] = str(
                record.get("equipment_slot_type", slot_type) or slot_type
            ).casefold()
            if (
                collection == "general_items"
                and str(record.get("type", "") or "") in {"Broom", "Flyable"}
            ):
                record["activation_mode"] = "equipped"
                record["equipment_slot_type"] = "flyable"
                try:
                    record["flight_threshold"] = max(
                        1, min(100, int(record.get("flight_threshold", 7) or 7))
                    )
                except (TypeError, ValueError):
                    record["flight_threshold"] = 7
                source = record.get("in_flight_effects")
                if source is None:
                    source = record.get("bonuses", []) or []
                record["in_flight_effects"] = [
                    effect
                    for effect in normalize_in_flight_effects(source)
                    if isinstance(effect, dict)
                    and effect.get("target") in IN_FLIGHT_EFFECT_TARGETS
                ]
                record["bonuses"] = []
                record["actions"] = []
            actions = []
            for index, action in enumerate(record.get("actions", []) or []):
                if not isinstance(action, dict) or not action.get("action_type"):
                    continue
                normalized_action = deepcopy(action)
                normalized_action["record_id"] = str(
                    normalized_action.get("record_id")
                    or uuid5(
                        NAMESPACE_URL,
                        f"charms-check:item-action:{record.get('record_id')}:{index}:{normalized_action.get('name', '')}",
                    )
                )
                actions.append(normalized_action)
            record["actions"] = actions
            if "bonuses" in record:
                record["bonuses"] = normalize_bonuses(record.get("bonuses"))
            after = {
                "activation_mode": record["activation_mode"],
                "equipment_slot_type": record["equipment_slot_type"],
            }
            if before != after:
                item_behavior_changes.append({
                    "collection": collection, "record_id": record.get("record_id", ""),
                    "name": record.get("name", ""), "before": before, "after": after,
                })
    thresholds = {"X": 7, "XX": 12, "XXX": 18, "XXXX": 25, "XXXXX": 35}
    for creature in result.get("creatures", []) or []:
        threshold = thresholds.get(str(creature.get("classification", "") or "").strip(), 12)
        awareness_id = str(creature.get("awareness_proficiency_id", "") or "")
        prior = creature.get("interaction_rules", {}) or {}
        rules = {}
        for action, flag in (
            ("capture", True),
            ("lure", str(creature.get("can_be_lured", "No")).casefold() == "yes"),
            ("tame", str(creature.get("can_be_tamed", "No")).casefold() == "yes"),
            ("bond", str(creature.get("can_bond", "No")).casefold() == "yes"),
        ):
            existing_rule = prior.get(action, {}) if isinstance(prior, dict) else {}
            rules[action] = {
                "enabled": bool(existing_rule.get("enabled", flag)),
                "skill": str(existing_rule.get("skill", "Creatures") or "Creatures"),
                "threshold": int(existing_rule.get("threshold", threshold) or threshold),
                "required_proficiency_id": str(
                    existing_rule.get("required_proficiency_id", "" if action == "capture" else awareness_id)
                    or ""
                ),
                "notes": str(existing_rule.get("notes", creature.get("additional_social_rules", "")) or "")[:4000],
            }
        creature["interaction_rules"] = rules
    audit = {
        "book_count": len(result.get("books", []) or []),
        "book_category_changes": category_changes,
        "tagged_counts": {
            collection: len(result.get(collection, []) or [])
            for collection in ("spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks")
        },
        "tag_changes": tag_changes,
        "item_behavior_changes": item_behavior_changes,
        "coverage": {
            "uncategorized_books": sum(
                1 for item in result.get("books", []) or [] if not item.get("categories")
            ),
            "untagged_records": {
                collection: sum(
                    1 for item in result.get(collection, []) or [] if not item.get("tags")
                )
                for collection in ("spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks")
            },
        },
        "category_totals": dict(sorted(Counter(
            category
            for item in result.get("books", []) or []
            for category in item.get("categories", []) or []
        ).items())),
        "ambiguous_books": [
            {"record_id": item["record_id"], "name": item.get("name", ""), "categories": item.get("categories", [])}
            for item in result.get("books", []) or [] if len(item.get("categories", []) or []) > 1
        ],
    }
    return result, audit


def validate_catalog(document: dict[str, Any]) -> None:
    database_metadata = document.get("_database", {})
    try:
        schema_version = int(database_metadata.get("schema_version", 0) or 0)
    except (TypeError, ValueError):
        schema_version = 0
    strict_in_flight_effects = schema_version >= 9
    valid_categories = set(BOOK_CATEGORIES)
    catalog = document.get("tag_catalog", []) or []
    tag_ids = {str(item.get("record_id", "")) for item in catalog if isinstance(item, dict)}
    if len(tag_ids) != len(catalog) or not tag_ids:
        raise ValueError("Canonical catalog tags require unique stable IDs")
    for book in document.get("books", []) or []:
        categories = book.get("categories", []) or []
        if not categories or any(value not in valid_categories for value in categories):
            raise ValueError(f"Book {book.get('record_id')} has invalid categories")
    for collection in ("spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks"):
        for record in document.get(collection, []) or []:
            tags = record.get("tags", [])
            if tags is not None and not isinstance(tags, list):
                raise ValueError(f"{collection} {record.get('record_id')} tags must be a list")
            if any(tag_id not in tag_ids for tag_id in record.get("tag_ids", []) or []):
                raise ValueError(f"{collection} {record.get('record_id')} references an unknown tag")
            if (
                collection in {"spells", "proficiencies", "potions", "preparations"}
                and record.get("target_scope", "none") not in TARGET_SCOPES
            ):
                raise ValueError(
                    f"{collection} {record.get('record_id')} has an invalid target"
                )
    for collection in ("wands", "holdable_items", "accessories", "general_items", "plants"):
        for record in document.get(collection, []) or []:
            if record.get("activation_mode") not in {"passive", "equipped", "click"}:
                raise ValueError(f"{collection} {record.get('record_id')} has an invalid activation mode")
            slot = str(record.get("equipment_slot_type", "") or "")
            if slot not in {"", "focus", "accessory", "flyable"}:
                raise ValueError(f"{collection} {record.get('record_id')} has an invalid equipment slot")
            if slot == "flyable":
                try:
                    threshold = int(record.get("flight_threshold"))
                except (TypeError, ValueError) as error:
                    raise ValueError(
                        f"{collection} {record.get('record_id')} needs a Flying threshold"
                    ) from error
                if threshold < 1 or threshold > 100:
                    raise ValueError(
                        f"{collection} {record.get('record_id')} has an invalid Flying threshold"
                    )
                validate_in_flight_effects(
                    record.get("in_flight_effects", [])
                )
                if strict_in_flight_effects and (
                    record.get("bonuses") or record.get("actions")
                ):
                    raise ValueError(
                        f"{collection} {record.get('record_id')} must use only "
                        "in-flight effects"
                    )
            action_ids = [
                str(action.get("record_id", ""))
                for action in record.get("actions", []) or [] if isinstance(action, dict)
            ]
            if any(not value for value in action_ids) or len(action_ids) != len(set(action_ids)):
                raise ValueError(f"{collection} {record.get('record_id')} has invalid item actions")
            complete_bonuses = [
                bonus for bonus in normalize_bonuses(record.get("bonuses", []))
                if isinstance(bonus, dict)
                and bonus.get("type")
                and bonus.get("target")
                and bonus.get("amount") is not None
            ]
            if complete_bonuses:
                validate_bonuses(complete_bonuses)
