from __future__ import annotations

import calendar
import hashlib
import random
import re
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Iterable
from uuid import NAMESPACE_URL, uuid4, uuid5


SEARCHABLE_REGION_TYPES = {"secret", "library", "storeroom"}
SHOP_FREQUENCIES = {"always", "frequently", "sometimes", "rarely", "very_rarely"}
SHOP_OWNER_TYPES = {"person", "organization"}
SHOP_SCHEDULE_VERSION = "shop-stock-v1"
GATHERING_METHOD_DEFAULTS = (
    ("forage", "Forage"),
    ("prospect", "Prospect"),
    ("survey", "Survey"),
    ("search", "Search"),
    ("dive", "Dive"),
)
CATALOG_COLLECTIONS = {
    "creatures", "books", "plants", "creature_parts", "plant_parts",
    "potions", "preparations", "general_items", "accessories",
    "holdable_items", "foods_and_drinks", "raw_materials",
}


def _text(value: Any, maximum: int = 200) -> str:
    return str(value or "").strip()[:maximum]


def normalize_gathering_method(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every gathering method must be an object")
    record_id = _text(value.get("record_id"), 100)
    name = _text(value.get("name"), 100)
    if not record_id or not name:
        raise ValueError("Every gathering method requires a stable ID and name")
    return {
        **deepcopy(value),
        "record_id": record_id,
        "name": name,
        "description": _text(value.get("description"), 2000),
    }


def ensure_gathering_catalog(database: dict[str, Any]) -> bool:
    """Install stable gathering foundations without rewriting ordinary records.

    Missing per-record assignments and quantities intentionally keep their runtime
    defaults (no method restriction and quantity one).  DBM writes explicit fields
    only after the Headmaster edits a definition.
    """
    changed = False
    methods = database.setdefault("gathering_methods", [])
    if not isinstance(methods, list):
        raise ValueError("gathering_methods must be a list")
    existing = {
        _text(item.get("record_id"), 100)
        for item in methods if isinstance(item, dict)
    }
    for record_id, name in GATHERING_METHOD_DEFAULTS:
        if record_id not in existing:
            methods.append({"record_id": record_id, "name": name, "description": ""})
            changed = True
    for parent_collection, prefix in (("creatures", "creature_part"), ("plants", "plant_part")):
        for parent in database.get(parent_collection, []) or []:
            if not isinstance(parent, dict):
                continue
            parent_id = _text(parent.get("record_id"), 160)
            for index, part in enumerate(parent.get("parts", []) or []):
                if not isinstance(part, dict) or _text(part.get("record_id"), 160):
                    continue
                identity = "|".join((
                    "charms-check", parent_collection, parent_id, str(index),
                    _text(part.get("name"), 300).casefold(),
                ))
                part["record_id"] = f"{prefix}_{uuid5(NAMESPACE_URL, identity).hex}"
                changed = True
    return changed


def validate_gathering_database(database: dict[str, Any]) -> None:
    """Validate the optional gathering catalog and explicit definition defaults."""

    raw_methods = database.get("gathering_methods", []) or []
    if not isinstance(raw_methods, list):
        raise ValueError("gathering_methods must be a list")
    methods = [normalize_gathering_method(item) for item in raw_methods]
    method_ids = {item["record_id"] for item in methods}
    if len(method_ids) != len(methods):
        raise ValueError("Gathering method IDs must be unique")

    def validate_record(record: dict[str, Any]) -> None:
        assignments = record.get("gathering_method_ids", []) or []
        if not isinstance(assignments, list):
            raise ValueError("Gathering method assignments must be a list")
        normalized = {_text(item, 100) for item in assignments if _text(item, 100)}
        if len(normalized) != len(assignments) or normalized - method_ids:
            raise ValueError("A catalog definition references an unknown gathering method")
        searching_method_id = _text(
            record.get("searching_method_id"), 100
        )
        if searching_method_id and searching_method_id not in method_ids:
            raise ValueError(
                "A raw material references an unknown Searching Method"
            )
        for field in ("default_source_quantity", "default_stock_quantity"):
            if field in record and int(record[field]) < 1:
                raise ValueError("Default source and stock quantities must be at least one")

    for collection in CATALOG_COLLECTIONS - {"creature_parts", "plant_parts"}:
        for record in database.get(collection, []) or []:
            if isinstance(record, dict):
                validate_record(record)
    require_nested_ids = int((database.get("_database") or {}).get("schema_version", 1)) >= 4
    nested_ids: set[str] = set()
    for parent_collection in ("creatures", "plants"):
        for parent in database.get(parent_collection, []) or []:
            if not isinstance(parent, dict):
                continue
            for part in parent.get("parts", []) or []:
                if isinstance(part, dict):
                    part_id = _text(part.get("record_id"), 160)
                    if require_nested_ids and (not part_id or part_id in nested_ids):
                        raise ValueError("Nested creature and plant parts require unique stable IDs")
                    if part_id:
                        nested_ids.add(part_id)
                    validate_record(part)


def normalize_catalog_reference(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("A region content reference must be an object")
    collection = _text(value.get("collection"), 100)
    record_id = _text(value.get("record_id"), 160)
    parent_record_id = _text(value.get("parent_record_id"), 160)
    if collection not in CATALOG_COLLECTIONS or not record_id:
        raise ValueError("Region content requires a supported collection and record ID")
    if collection in {"creature_parts", "plant_parts"} and not parent_record_id:
        raise ValueError("Nested parts require their parent creature or plant ID")
    return {
        "collection": collection,
        "record_id": record_id,
        "parent_record_id": parent_record_id,
    }


def catalog_reference_exists(database: dict[str, Any], value: Any) -> bool:
    """Return whether a typed region reference resolves in the canonical catalog."""

    reference = normalize_catalog_reference(value)
    collection = reference["collection"]
    record_id = reference["record_id"]
    parent_id = reference["parent_record_id"]
    if collection not in {"creature_parts", "plant_parts"}:
        return any(
            isinstance(item, dict) and _text(item.get("record_id"), 160) == record_id
            for item in database.get(collection, []) or []
        )
    parent_collection = "creatures" if collection == "creature_parts" else "plants"
    for parent in database.get(parent_collection, []) or []:
        if not isinstance(parent, dict) or _text(parent.get("record_id"), 160) != parent_id:
            continue
        return any(
            isinstance(part, dict) and _text(part.get("record_id"), 160) == record_id
            for part in parent.get("parts", []) or []
        )
    return False


def normalize_search_mode(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every search mode must be an object")
    record_id = _text(value.get("record_id"), 100)
    name = _text(value.get("name"), 100)
    skill = _text(value.get("skill"), 100)
    method_id = _text(value.get("gathering_method_id"), 100)
    if not record_id or not name or not skill or not method_id:
        raise ValueError("Search modes require an ID, name, raw skill, and gathering method")
    return {
        **deepcopy(value), "record_id": record_id, "name": name,
        "skill": skill, "gathering_method_id": method_id,
    }


def normalize_region_content(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every region content entry must be an object")
    record_id = _text(value.get("record_id"), 100)
    if not record_id:
        raise ValueError("Every region content entry requires a stable ID")
    threshold = int(value.get("threshold", 0))
    if threshold < 0 or threshold > 999:
        raise ValueError("Region content thresholds must be between 0 and 999")
    mode_ids: list[str] = []
    for raw in value.get("search_mode_ids", []) or []:
        mode_id = _text(raw, 100)
        if mode_id and mode_id not in mode_ids:
            mode_ids.append(mode_id)
    if not mode_ids:
        raise ValueError("Every region content entry requires at least one search mode")
    return {
        **deepcopy(value), "record_id": record_id,
        "reference": normalize_catalog_reference(value.get("reference")),
        "search_mode_ids": mode_ids, "threshold": threshold,
        "depletable": bool(value.get("depletable", False)),
    }


def normalize_shop_listing(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every shop listing must be an object")
    record_id = _text(value.get("record_id"), 100)
    frequency = _text(value.get("frequency", "always"), 30).casefold().replace(" ", "_")
    if frequency not in SHOP_FREQUENCIES:
        raise ValueError("Unknown shop stock frequency")
    price = int(value.get("price_knuts", 9_999_999))
    if not record_id or price < 0:
        raise ValueError("Shop listings require an ID and non-negative Knut price")
    return {
        **deepcopy(value), "record_id": record_id,
        "reference": normalize_catalog_reference(value.get("reference")),
        "frequency": frequency, "price_knuts": price,
        "price_confirmed": bool(value.get("price_confirmed", "price_knuts" in value)),
    }


def normalize_shop_owner(value: Any) -> dict[str, str] | None:
    """Normalize the person or organization operating one specific shop."""

    if value in (None, "", {}):
        return None
    if not isinstance(value, dict):
        raise ValueError("A shop owner must be a person or organization reference")
    owner_type = _text(value.get("owner_type"), 30).casefold()
    record_id = _text(value.get("record_id"), 160)
    if owner_type not in SHOP_OWNER_TYPES or not record_id:
        raise ValueError("A shop owner must reference a person or organization")
    return {"owner_type": owner_type, "record_id": record_id}


def normalize_region_interactions(region: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(region)
    behavior = _text(result.get("behavior_type", "area"), 30).casefold()
    modes = [normalize_search_mode(item) for item in result.get("search_modes", []) or []]
    mode_ids = {item["record_id"] for item in modes}
    if len(mode_ids) != len(modes):
        raise ValueError("Search mode IDs must be unique within a region")
    contents = [normalize_region_content(item) for item in result.get("contents", []) or []]
    if len({item["record_id"] for item in contents}) != len(contents):
        raise ValueError("Content entry IDs must be unique within a region")
    if any(set(item["search_mode_ids"]) - mode_ids for item in contents):
        raise ValueError("Region content references an unknown search mode")
    listings = [normalize_shop_listing(item) for item in result.get("shop_listings", []) or []]
    if len({item["record_id"] for item in listings}) != len(listings):
        raise ValueError("Shop listing IDs must be unique within a region")
    if behavior not in SEARCHABLE_REGION_TYPES and (modes or contents):
        raise ValueError("Only Secret, Library, and Storeroom regions may contain searches")
    if behavior != "shop" and listings:
        raise ValueError("Only Shop regions may contain shop listings")
    gate_skill = _text(result.get("secret_skill"), 100)
    gate_threshold = int(result.get("secret_threshold", 0))
    if behavior == "secret" and (not gate_skill or gate_threshold < 0):
        raise ValueError("Secret regions require a raw skill and non-negative threshold")
    result.update({
        "secret_skill": gate_skill if behavior == "secret" else "",
        "secret_threshold": gate_threshold if behavior == "secret" else 0,
        "search_modes": modes if behavior in SEARCHABLE_REGION_TYPES else [],
        "contents": contents if behavior in SEARCHABLE_REGION_TYPES else [],
        "shop_seed": _text(result.get("shop_seed") or result.get("record_id"), 200) if behavior == "shop" else "",
        "shop_listings": listings if behavior == "shop" else [],
        "address_id": _text(result.get("address_id"), 160) if behavior in {"address", "shop"} else "",
        "shop_owner": normalize_shop_owner(result.get("shop_owner")) if behavior == "shop" else None,
        "shop_schedule_version": SHOP_SCHEDULE_VERSION if behavior == "shop" else "",
    })
    return result


def validate_region_catalog_links(region: dict[str, Any], database: dict[str, Any]) -> dict[str, Any]:
    """Normalize a region and reject stale method or catalog references."""

    normalized = normalize_region_interactions(region)
    gathering_ids = {
        item["record_id"]
        for item in (
            normalize_gathering_method(raw)
            for raw in database.get("gathering_methods", []) or []
        )
    }
    for mode in normalized.get("search_modes", []) or []:
        if mode["gathering_method_id"] not in gathering_ids:
            raise ValueError(
                f"Search method {mode['name']!r} references a missing gathering method"
            )
    for entry in normalized.get("contents", []) or []:
        if not catalog_reference_exists(database, entry["reference"]):
            raise ValueError("A searchable content entry references a missing catalog record")
    for listing in normalized.get("shop_listings", []) or []:
        if not catalog_reference_exists(database, listing["reference"]):
            raise ValueError("A shop listing references a missing catalog record")
    return normalized


def loot_cost(threshold: int) -> int:
    threshold = int(threshold)
    if threshold <= 14:
        return 1
    if threshold <= 24:
        return 3
    if threshold <= 34:
        return 5
    if threshold <= 49:
        return 7
    if threshold <= 64:
        return 9
    return 10


@dataclass(frozen=True)
class LootResult:
    natural_roll: int
    skill_value: int
    total: int
    awarded_ids: tuple[str, ...]
    destroyed_id: str
    points_remaining: int


def draw_loot(
    entries: Iterable[dict[str, Any]], skill_value: int,
    *, die_roll: int | None = None,
    available_quantity: Callable[[dict[str, Any]], int | None] | None = None,
    chooser: random.Random | None = None,
) -> LootResult:
    die = int(die_roll if die_roll is not None else random.SystemRandom().randint(1, 10))
    if not 1 <= die <= 10:
        raise ValueError("Search dice must be between 1 and 10")
    total = die + int(skill_value)
    pool = [deepcopy(item) for item in entries if int(item.get("threshold", 0)) <= total]
    rng = chooser or random.SystemRandom()
    if not pool:
        return LootResult(die, int(skill_value), total, (), "", 10)

    drawn_counts: dict[str, int] = {}

    def stocked(item: dict[str, Any]) -> bool:
        quantity = available_quantity(item) if available_quantity else None
        if quantity is None:
            return True
        return int(quantity) > drawn_counts.get(str(item.get("record_id", "")), 0)

    pool = [item for item in pool if stocked(item)]
    if not pool:
        return LootResult(die, int(skill_value), total, (), "", 10)
    if die == 1:
        destroyed = rng.choice(pool)
        return LootResult(die, int(skill_value), total, (), str(destroyed["record_id"]), 10)
    points = 10
    awarded: list[str] = []
    free_first = die == 10
    while True:
        affordable = [item for item in pool if stocked(item) and loot_cost(item["threshold"]) <= points]
        if not affordable:
            break
        selected = rng.choice(affordable)
        selected_id = str(selected["record_id"])
        awarded.append(selected_id)
        drawn_counts[selected_id] = drawn_counts.get(selected_id, 0) + 1
        if free_first:
            free_first = False
        else:
            points -= loot_cost(selected["threshold"])
        if points <= 0:
            break
    return LootResult(die, int(skill_value), total, tuple(awarded), "", points)


def _historical_parts(value: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(-?[1-9]\d*)-(\d{2})-(\d{2})(?:T.*)?", str(value or ""))
    if not match:
        raise ValueError("Game date must use YYYY-MM-DD")
    year, month, day = map(int, match.groups())
    if not 1 <= month <= 12 or not 1 <= day <= calendar.monthrange(year, month)[1]:
        raise ValueError("Game date is invalid")
    return year, month, day


def shop_window(region: dict[str, Any], listing: dict[str, Any], game_datetime: str) -> dict[str, Any]:
    listing = normalize_shop_listing(listing)
    frequency = listing["frequency"]
    if frequency == "always":
        return {"available": True, "window_id": "always", "starts": "", "ends": ""}
    interval, duration = {
        "frequently": (3, 28), "sometimes": (6, 14),
        "rarely": (12, 14), "very_rarely": (24, 14),
    }[frequency]
    year, month, day = _historical_parts(game_datetime)
    month_index = year * 12 + month - 1
    seed = "|".join((
        SHOP_SCHEDULE_VERSION, _text(region.get("shop_seed") or region.get("record_id"), 200),
        _text(region.get("record_id"), 100), listing["record_id"],
    ))
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    phase_month = int.from_bytes(digest[:4], "big") % interval
    start_day = 1 + int.from_bytes(digest[4:8], "big") % 14
    cycle_month = month_index - ((month_index - phase_month) % interval)
    cycle_year, cycle_zero_month = divmod(cycle_month, 12)
    cycle_month_number = cycle_zero_month + 1
    start_day = min(start_day, calendar.monthrange(cycle_year, cycle_month_number)[1])
    current_ordinal = _proleptic_ordinal(year, month, day)
    start_ordinal = _proleptic_ordinal(cycle_year, cycle_month_number, start_day)
    available = start_ordinal <= current_ordinal < start_ordinal + duration
    return {
        "available": available,
        "window_id": f"{SHOP_SCHEDULE_VERSION}:{cycle_year}:{cycle_month_number:02d}:{start_day:02d}",
        "starts": f"{cycle_year:04d}-{cycle_month_number:02d}-{start_day:02d}",
        "ends_ordinal": start_ordinal + duration - 1,
    }


def _proleptic_ordinal(year: int, month: int, day: int) -> int:
    prior_year = year - 1
    leap_days = prior_year // 4 - prior_year // 100 + prior_year // 400
    days = 365 * prior_year + leap_days
    month_days = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30)
    days += sum(month_days[1:month]) + day
    if month > 2 and calendar.isleap(year):
        days += 1
    return days


def new_search_mode(name: str, skill: str, method_id: str) -> dict[str, Any]:
    return normalize_search_mode({
        "record_id": str(uuid4()), "name": name, "skill": skill,
        "gathering_method_id": method_id,
    })
