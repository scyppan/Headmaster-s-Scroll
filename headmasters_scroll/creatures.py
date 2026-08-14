from __future__ import annotations

import hashlib
import random
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid4, uuid5


APTITUDES = ("inept", "unskilled", "typical", "skilled", "exceptional")
LIFE_STATES = {"alive", "dead"}
VISIBILITIES = {"headmaster", "players"}
CLASSIFICATION_THRESHOLDS = {
    "X": 7,
    "XX": 12,
    "XXX": 18,
    "XXXX": 25,
    "XXXXX": 35,
    "": 12,
}
_FAMILY_PREFIXES = (
    "very small ", "very large ", "newborn ", "juvenile ", "young ",
    "typical ", "small ", "large ", "adult ", "ancient ", "baby ",
    "oversized ", "undersized ",
)


class RandomSource(Protocol):
    def randint(self, low: int, high: int) -> int: ...


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def stable_child_id(species_id: str, collection: str, index: int, name: str) -> str:
    value = uuid5(
        NAMESPACE_URL,
        f"headmasters-scroll:{species_id}:{collection}:{index}:{name.strip().casefold()}",
    )
    return f"creature-{collection[:-1]}-{value}"


def creature_family_name(name: Any) -> str:
    """Return a persisted migration family; runtime code never fuzzy-matches it."""

    family = " ".join(str(name or "Creature").split()).strip()
    lowered = family.casefold()
    changed = True
    while changed:
        changed = False
        for prefix in _FAMILY_PREFIXES:
            if lowered.startswith(prefix) and len(family) > len(prefix):
                family = family[len(prefix):].strip()
                lowered = family.casefold()
                changed = True
                break
    return family or "Creature"


def _stable_proficiency_id(family: str) -> str:
    digest = hashlib.sha1(family.casefold().encode("utf-8")).hexdigest()[:16]
    return f"proficiency_creature_awareness_{digest}"


def _classification_threshold(value: Any) -> int:
    classification = str(value or "").upper().strip()
    return CLASSIFICATION_THRESHOLDS.get(classification, 12)


def _part_yield(name: Any) -> dict[str, int]:
    """Conservative, deterministic migration values; never inferred at runtime."""

    lowered = str(name or "").strip().casefold()
    if re.search(r"\b(feathers|scales|quills|eggs|teeth)\b", lowered):
        return {"low": 1, "high": 4}
    if re.search(r"\b(hooves|paws)\b", lowered):
        return {"low": 4, "high": 4}
    if re.search(r"\b(eyes|ears|wings|horns|tusks|fangs|claws|pedipalps|kidneys|lungs)\b", lowered):
        return {"low": 2, "high": 2}
    return {"low": 1, "high": 1}


def migrate_creature_database(document: dict[str, Any]) -> dict[str, int]:
    """Idempotently add creature encounter links and stable nested record IDs."""

    creatures = document.get("creatures", []) or []
    proficiencies = document.setdefault("proficiencies", [])
    existing_by_name = {
        str(item.get("name", "")).strip().casefold(): item
        for item in proficiencies
        if isinstance(item, dict) and item.get("record_id")
    }
    created = 0
    changed = 0
    for species in creatures:
        if not isinstance(species, dict) or not species.get("record_id"):
            continue
        species_id = str(species["record_id"])
        family = str(species.get("creature_family") or creature_family_name(species.get("name")))
        proficiency_name = f"{family} Proficiency"
        proficiency = existing_by_name.get(proficiency_name.casefold())
        if proficiency is None:
            proficiency = {
                "record_id": _stable_proficiency_id(family),
                "name": proficiency_name,
                "tradition": "",
                "skill": "Magical Creatures",
                "threshold": _classification_threshold(species.get("classification")),
                "required_materials": [],
                "description": (
                    "Identifies, safely handles, and cares for this creature family, "
                    "and permits harvesting its ordinary parts."
                ),
                "history": "",
                "tags": ["Creature Awareness"],
                "dbnotes": "Added by Headmaster's Scroll creature encounter migration.",
                "last_updated": utc_now(),
            }
            proficiencies.append(proficiency)
            existing_by_name[proficiency_name.casefold()] = proficiency
            created += 1
        proficiency_id = str(proficiency["record_id"])
        if species.get("creature_family") != family:
            species["creature_family"] = family
            changed += 1
        if species.get("awareness_proficiency_id") != proficiency_id:
            species["awareness_proficiency_id"] = proficiency_id
            changed += 1
        for collection in ("attacks", "abilities", "parts"):
            for index, item in enumerate(species.get(collection, []) or []):
                if not isinstance(item, dict):
                    continue
                if not str(item.get("record_id", "")).strip():
                    item["record_id"] = stable_child_id(
                        species_id, collection, index, str(item.get("name", ""))
                    )
                    changed += 1
                if collection != "parts":
                    continue
                if not isinstance(item.get("yield"), dict):
                    item["yield"] = _part_yield(item.get("name"))
                    changed += 1
                raw_required = str(item.get("required_proficiency", "No") or "No").strip()
                if raw_required.casefold() in {"", "no", "none", "n/a"}:
                    required_id = None
                else:
                    required = existing_by_name.get(raw_required.casefold()) or existing_by_name.get(
                        f"{raw_required} proficiency".casefold()
                    )
                    required_id = str(required.get("record_id")) if required else None
                if item.get("required_proficiency_id") != required_id:
                    item["required_proficiency_id"] = required_id
                    changed += 1
    return {"creatures": len(creatures), "proficiencies_created": created, "fields_changed": changed}


def validate_creature_database(document: dict[str, Any]) -> None:
    proficiencies = {
        str(item.get("record_id"))
        for item in document.get("proficiencies", []) or []
        if isinstance(item, dict) and item.get("record_id")
    }
    child_ids: set[str] = set()
    for species in document.get("creatures", []) or []:
        if not isinstance(species, dict):
            raise ValueError("Every creature must be an object")
        awareness_id = str(species.get("awareness_proficiency_id", "") or "")
        if not awareness_id or awareness_id not in proficiencies:
            raise ValueError(f"{species.get('name', 'Creature')} requires a valid awareness proficiency")
        for collection in ("attacks", "abilities", "parts"):
            local_ids: set[str] = set()
            for item in species.get(collection, []) or []:
                if not isinstance(item, dict):
                    raise ValueError(f"Creature {collection} must be objects")
                record_id = str(item.get("record_id", "") or "")
                if not record_id or record_id in local_ids or record_id in child_ids:
                    raise ValueError(f"Creature {collection} require globally unique stable IDs")
                local_ids.add(record_id)
                child_ids.add(record_id)
                if collection == "parts":
                    yield_range = item.get("yield") or {}
                    low = int(yield_range.get("low", 0))
                    high = int(yield_range.get("high", 0))
                    if not 1 <= low <= high <= 10:
                        raise ValueError("Creature part yields must be between one and ten")
                    required_id = item.get("required_proficiency_id")
                    if required_id and str(required_id) not in proficiencies:
                        raise ValueError("Creature parts must link to valid specialized proficiencies")


def random_between(value: Any, rng: RandomSource | None = None, default: int | None = None) -> int | None:
    source = rng or random.SystemRandom()
    raw = value if isinstance(value, dict) else {}
    low, high = raw.get("low"), raw.get("high")
    if low is None and high is None:
        return default
    try:
        low = int(low if low is not None else high)
        high = int(high if high is not None else low)
    except (TypeError, ValueError):
        return default
    if low > high:
        low, high = high, low
    return source.randint(low, high)


def pick_aptitude(rng: RandomSource | None = None) -> str:
    value = (rng or random.SystemRandom()).randint(1, 100)
    if value < 10:
        return "inept"
    if value < 25:
        return "unskilled"
    if value > 90:
        return "exceptional"
    if value > 75:
        return "skilled"
    return "typical"


def adjust_range(low: int, high: int, aptitude: str) -> tuple[int, int]:
    low, high = int(low), int(high)
    if low > high:
        low, high = high, low
    if aptitude == "inept":
        adjusted = (1, max(1, int(high * 0.5)))
    elif aptitude == "unskilled":
        adjusted = (low, max(low, int(high * 0.75)))
    elif aptitude == "skilled":
        adjusted = (min(high, -(-low * 125 // 100)), high)
    elif aptitude == "exceptional":
        adjusted = (-(-low * 3 // 2), -(-high * 3 // 2))
    else:
        adjusted = (low, high)
    return (min(adjusted), max(adjusted))


def _generated_action(species_id: str, kind: str, item: dict[str, Any], index: int, rng: RandomSource) -> dict[str, Any]:
    roll_range = item.get("roll") or {}
    low = random_between({"low": roll_range.get("low"), "high": roll_range.get("low")}, rng, 1) or 1
    high = random_between({"low": roll_range.get("high"), "high": roll_range.get("high")}, rng, low) or low
    aptitude = pick_aptitude(rng)
    adjusted_low, adjusted_high = adjust_range(low, high, aptitude)
    return {
        "record_id": str(item.get("record_id") or stable_child_id(species_id, f"{kind}s", index, str(item.get("name", "")))),
        "action_type": kind,
        "name": str(item.get("name") or kind.title()),
        "description": str(item.get("description") or ""),
        "aptitude": aptitude,
        "base_range": {"low": low, "high": high},
        "adjusted_range": {"low": adjusted_low, "high": adjusted_high},
        "immediate_damage": deepcopy(item.get("immediate_damage", []) or []),
        "damage_over_time": deepcopy(item.get("damage_over_time", []) or []),
    }


def generate_creature_instance(
    species: dict[str, Any], counter: int, placement: dict[str, Any],
    rng: RandomSource | None = None,
) -> dict[str, Any]:
    source = rng or random.SystemRandom()
    species_id = str(species.get("record_id", "") or "")
    if not species_id:
        raise ValueError("Creature species requires a stable record ID")
    name = str(species.get("name") or "Creature")
    generated = {
        "size": random_between(species.get("size"), source, 1),
        "heavy_wound_cap": random_between(species.get("wound_cap"), source, 1),
        "magical_resistance": random_between(species.get("magical_resistance"), source),
        "intelligence": random_between(species.get("intelligence"), source),
        "social_skill": random_between(species.get("social_skill"), source),
        "movement": {},
    }
    for mode, movement in (species.get("movement") or {}).items():
        enabled = str((movement or {}).get("enabled", "No")).casefold() == "yes"
        generated["movement"][str(mode)] = random_between(movement, source) if enabled else None
    actions = []
    for kind in ("attack", "ability"):
        for index, item in enumerate(species.get(f"{kind}s", []) or []):
            if isinstance(item, dict):
                actions.append(_generated_action(species_id, kind, item, index, source))
    harvest_pools = []
    for part in species.get("parts", []) or []:
        if not isinstance(part, dict):
            continue
        quantity = random_between(part.get("yield"), source, 1) or 1
        harvest_pools.append({
            "part_id": str(part.get("record_id") or ""),
            "name": str(part.get("name") or "Creature part"),
            "required_proficiency_id": part.get("required_proficiency_id") or None,
            "initial_quantity": min(10, max(1, quantity)),
            "remaining_quantity": min(10, max(1, quantity)),
            "status": "available",
        })
    now = utc_now()
    return normalize_campaign_creature({
        "record_id": str(uuid4()),
        "species_record_id": species_id,
        "species_name": name,
        "awareness_proficiency_id": str(species.get("awareness_proficiency_id") or ""),
        "internal_label": f"{name} · {int(counter)}",
        "counter": int(counter),
        "generated": generated,
        "actions": actions,
        "placement": placement,
        "label_offset": {"x": 0.0, "y": -0.025},
        "visibility": "headmaster",
        "wounds": [],
        "battle": None,
        "life_state": "alive",
        "death_override": False,
        "died_at": None,
        "harvest_pools": harvest_pools,
        "harvest_attempts": [],
        "created_at": now,
        "last_updated": now,
    })


def normalize_campaign_creature(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every campaign creature must be an object")
    result = deepcopy(value)
    for field in ("record_id", "species_record_id", "species_name", "awareness_proficiency_id", "internal_label"):
        result[field] = str(result.get(field, "") or "").strip()
        if not result[field]:
            raise ValueError(f"Every campaign creature requires {field}")
    result["counter"] = max(1, int(result.get("counter", 1)))
    placement = result.get("placement") or {}
    result["placement"] = {
        "location_id": str(placement.get("location_id", "") or ""),
        "floor_id": str(placement.get("floor_id", "") or ""),
        "map_id": str(placement.get("map_id", "") or ""),
        "x": max(0.0, min(1.0, float(placement.get("x", 0.5)))),
        "y": max(0.0, min(1.0, float(placement.get("y", 0.5)))),
    }
    if not result["placement"]["map_id"] or not result["placement"]["location_id"]:
        raise ValueError("Every campaign creature must occupy a map and location")
    offset = result.get("label_offset") or {}
    result["label_offset"] = {
        "x": max(-1.0, min(1.0, float(offset.get("x", 0.0)))),
        "y": max(-1.0, min(1.0, float(offset.get("y", -0.025)))),
    }
    result["visibility"] = str(result.get("visibility", "headmaster") or "headmaster")
    if result["visibility"] not in VISIBILITIES:
        raise ValueError("Campaign creature visibility is invalid")
    generated = result.get("generated") or {}
    cap = max(1, int(generated.get("heavy_wound_cap", 1)))
    generated["heavy_wound_cap"] = cap
    generated["size"] = max(1, int(generated.get("size", 1)))
    generated.setdefault("magical_resistance", None)
    generated.setdefault("intelligence", None)
    generated.setdefault("social_skill", None)
    generated["movement"] = deepcopy(generated.get("movement", {}) or {})
    result["generated"] = generated
    actions = []
    action_ids: set[str] = set()
    for raw in result.get("actions", []) or []:
        if not isinstance(raw, dict):
            raise ValueError("Creature actions must be objects")
        action = deepcopy(raw)
        action_id = str(action.get("record_id", "") or "")
        aptitude = str(action.get("aptitude", "typical") or "typical")
        if not action_id or action_id in action_ids or aptitude not in APTITUDES:
            raise ValueError("Creature actions require unique IDs and valid aptitudes")
        adjusted = action.get("adjusted_range") or {}
        low, high = int(adjusted.get("low", 0)), int(adjusted.get("high", 0))
        if low > high:
            raise ValueError("Creature action ranges are invalid")
        action["record_id"] = action_id
        action["aptitude"] = aptitude
        action["adjusted_range"] = {"low": low, "high": high}
        action_ids.add(action_id)
        actions.append(action)
    result["actions"] = actions
    wounds = []
    for raw in result.get("wounds", []) or []:
        if not isinstance(raw, dict):
            raise ValueError("Creature wounds must be objects")
        severity = str(raw.get("severity", "") or "").casefold()
        if severity not in {"light", "medium", "heavy"}:
            raise ValueError("Creature wounds must be light, medium, or heavy")
        wounds.append({
            "record_id": str(raw.get("record_id") or uuid4()),
            "severity": severity,
            "note": str(raw.get("note", "") or "")[:1000],
            "created_at": str(raw.get("created_at") or utc_now()),
        })
    result["wounds"] = wounds
    result["battle"] = deepcopy(result.get("battle"))
    result["life_state"] = str(result.get("life_state", "alive") or "alive")
    if result["life_state"] not in LIFE_STATES:
        raise ValueError("Campaign creature life state is invalid")
    result["death_override"] = bool(result.get("death_override", False))
    result["died_at"] = result.get("died_at") or None
    pools = []
    pool_ids: set[str] = set()
    for raw in result.get("harvest_pools", []) or []:
        if not isinstance(raw, dict):
            raise ValueError("Creature harvest pools must be objects")
        part_id = str(raw.get("part_id", "") or "")
        initial = int(raw.get("initial_quantity", 0))
        remaining = int(raw.get("remaining_quantity", 0))
        if not part_id or part_id in pool_ids or not 0 <= remaining <= initial <= 10:
            raise ValueError("Creature harvest pools require unique parts and valid quantities")
        pool = deepcopy(raw)
        pool.update({
            "part_id": part_id,
            "initial_quantity": initial,
            "remaining_quantity": remaining,
            "status": "available" if remaining else str(raw.get("status") or "claimed"),
        })
        pool_ids.add(part_id)
        pools.append(pool)
    result["harvest_pools"] = pools
    attempts = []
    seen_attempts: set[tuple[str, str]] = set()
    for raw in result.get("harvest_attempts", []) or []:
        if not isinstance(raw, dict):
            raise ValueError("Harvest attempts must be objects")
        key = (str(raw.get("character_id", "") or ""), str(raw.get("part_id", "") or ""))
        if not all(key) or key in seen_attempts:
            raise ValueError("A character may attempt each corpse part only once")
        seen_attempts.add(key)
        attempts.append(deepcopy(raw))
    result["harvest_attempts"] = attempts
    result["created_at"] = str(result.get("created_at") or utc_now())
    result["last_updated"] = str(result.get("last_updated") or result["created_at"])
    return result


def roll_creature_action(instance: dict[str, Any], action_id: str, rng: RandomSource | None = None) -> dict[str, Any]:
    creature = normalize_campaign_creature(instance)
    if creature["life_state"] != "alive":
        raise ValueError("A dead creature cannot act")
    action = next((item for item in creature["actions"] if item["record_id"] == action_id), None)
    if action is None:
        raise KeyError("Unknown creature attack or ability")
    low = int(action["adjusted_range"]["low"])
    high = int(action["adjusted_range"]["high"])
    roll = (rng or random.SystemRandom()).randint(low, high)
    return {
        "activity_type": "creature_action",
        "actor_type": "creature",
        "creature_id": creature["record_id"],
        "species_name": creature["species_name"],
        "action_id": action["record_id"],
        "action_type": action.get("action_type", "ability"),
        "name": action.get("name", "Action"),
        "aptitude": action["aptitude"],
        "range": {"low": low, "high": high},
        "roll": roll,
        "immediate_damage": deepcopy(action.get("immediate_damage", []) or []),
        "damage_over_time": deepcopy(action.get("damage_over_time", []) or []),
        "text": f"A {creature['species_name']} uses {action.get('name', 'an action')} and rolls {roll}.",
    }
