from __future__ import annotations

import calendar
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

if TYPE_CHECKING:
    from .store import SharedJsonStore


GAME_WORLD_DATE = re.compile(
    r"^(?P<year>-?[1-9]\d*)-(?P<month>\d{2})-(?P<day>\d{2})$"
)
GAME_WORLD_DATETIME = re.compile(r"^-?[1-9]\d*-\d{2}-\d{2}T\d{2}:\d{2}$")
HISTORY_KEEP = "keep"
HISTORY_DISCARD = "discard"
HISTORY_POLICIES = {HISTORY_KEEP, HISTORY_DISCARD}
REQUEST_STATUSES = {"pending", "approved", "rejected"}
EQUIPMENT_SLOTS = ("focus", "accessory_1", "accessory_2", "flyable")

LEGACY_GENERATED_ZOOM_TIERS = {
    "0": {"token_size": 0, "nameplate_size": 11},
    "3": {"token_size": 0, "nameplate_size": 11},
    "6": {"token_size": 0, "nameplate_size": 10},
    "9": {"token_size": 0, "nameplate_size": 10},
    "12": {"token_size": 0, "nameplate_size": 9},
    "15": {"token_size": 0, "nameplate_size": 9},
    "18": {"token_size": 68, "nameplate_size": 9},
    "21": {"token_size": 64, "nameplate_size": 8},
}


def default_campaign_person_state() -> dict[str, Any]:
    """Return implicit campaign state for a person without a stored overlay."""

    return {
        "placement": None,
        "visibility": "players",
        "display_mode": "dot",
        "name_revealed": False,
        "faction_revealed": False,
        "faction_organization_id": "",
        "label_offset": {"x": 0.0, "y": 0.0},
        "nameplate_scale": 1.0,
        "wounds": [],
        "current_state": "",
        "battle": None,
        "character_notes": [],
        "consumed_inventory": {},
        "campaign_inventory": [],
        "equipment": {slot: "" for slot in EQUIPMENT_SLOTS},
        "airborne": False,
        "currency_knuts": 0,
    }


def compact_campaign_person_overlays(
    value: Any,
    *,
    required_person_ids: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Return only person-state values that differ from implicit defaults."""

    source = value if isinstance(value, dict) else {}
    defaults = default_campaign_person_state()
    required = required_person_ids or set()
    compacted: dict[str, dict[str, Any]] = {}
    for raw_person_id, raw_state in source.items():
        person_id = str(raw_person_id or "").strip()
        if not person_id or not isinstance(raw_state, dict):
            continue
        overlay = {
            key: deepcopy(field_value)
            for key, field_value in raw_state.items()
            if key not in defaults or field_value != defaults[key]
        }
        if overlay or person_id in required:
            compacted[person_id] = overlay
    return compacted


def compact_campaign_document_for_storage(document: dict[str, Any]) -> dict[str, Any]:
    """Compact campaign person overlays in a detached document."""

    compacted = deepcopy(document)
    if not isinstance(compacted, dict):
        return compacted
    for campaign in compacted.get("campaigns", []) or []:
        if not isinstance(campaign, dict):
            continue
        game_state = campaign.get("game_state")
        if isinstance(game_state, dict):
            required_person_ids = {
                str(participant.get("actor_id", "") or "").strip()
                for battle in (game_state.get("battles", {}) or {}).values()
                if isinstance(battle, dict)
                for participant in (battle.get("participants", []) or [])
                if isinstance(participant, dict)
                and str(participant.get("actor_type", "person") or "person")
                == "person"
                and str(participant.get("actor_id", "") or "").strip()
            }
            game_state["people"] = compact_campaign_person_overlays(
                game_state.get("people"),
                required_person_ids=required_person_ids,
            )
    return compacted


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize_game_world_date(value: Any) -> str:
    raw = str(value or "").strip()
    match = GAME_WORLD_DATE.fullmatch(raw)
    if match is None:
        raise ValueError("Game World Start Date must use YYYY-MM-DD")
    try:
        year, month, day = (
            int(match.group(field)) for field in ("year", "month", "day")
        )
        if year == 0 or not 1 <= month <= 12:
            raise ValueError
        if not 1 <= day <= calendar.monthrange(year, month)[1]:
            raise ValueError
    except ValueError as error:
        raise ValueError("Game World Start Date is not a valid historical date") from error
    shown_year = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    return f"{shown_year}-{month:02d}-{day:02d}"


def format_game_world_date(value: Any) -> str:
    normalized = normalize_game_world_date(value)
    match = GAME_WORLD_DATE.fullmatch(normalized)
    if match is None:
        return normalized
    year, month, day = (
        int(match.group(field)) for field in ("year", "month", "day")
    )
    shown_year = f"{abs(year)} BCE" if year < 0 else str(year)
    return f"{day:02d} {calendar.month_abbr[month]} {shown_year}"


def normalize_board_camera(value: Any) -> dict[str, float]:
    raw = value if isinstance(value, dict) else {}
    zoom = float(raw.get("zoom", 1.0))
    center_x = float(raw.get("center_x", 0.5))
    center_y = float(raw.get("center_y", 0.5))
    if not 1.0 <= zoom <= 32.0:
        raise ValueError("Campaign map camera zoom must be between 1 and 32")
    if not 0.0 <= center_x <= 1.0 or not 0.0 <= center_y <= 1.0:
        raise ValueError("Campaign map camera center must be on the map")
    return {
        "zoom": zoom,
        "center_x": center_x,
        "center_y": center_y,
    }


def normalize_zoom_profile(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    default_zoom = float(raw.get("default_zoom", 1.0))
    if not 1.0 <= default_zoom <= 32.0:
        raise ValueError("Default map zoom must be between 1 and 32")
    default_center_x = float(raw.get("default_center_x", 0.5))
    default_center_y = float(raw.get("default_center_y", 0.5))
    if not 0.0 <= default_center_x <= 1.0 or not 0.0 <= default_center_y <= 1.0:
        raise ValueError("Default map position must be on the map")
    default_nameplate_size = int(raw.get("default_nameplate_size", 10))
    if not 6 <= default_nameplate_size <= 32:
        raise ValueError("Default map nameplate size must be between 6 and 32 pixels")
    raw_tiers = raw.get("tiers", {}) or {}
    if not isinstance(raw_tiers, dict):
        raise ValueError("Map zoom tiers must be keyed by click level")
    tiers: dict[str, dict[str, int]] = {}
    for raw_clicks, item in raw_tiers.items():
        try:
            clicks = int(raw_clicks)
        except (TypeError, ValueError) as error:
            raise ValueError("Map zoom click levels must be whole numbers") from error
        if not 0 <= clicks <= 250:
            raise ValueError("Map zoom click levels must be between 0 and 250")
        if not isinstance(item, dict):
            raise ValueError("Every map zoom-tier override must be an object")
        token_size = int(item.get("token_size", 0))
        nameplate_size = int(item.get("nameplate_size", 10))
        if not 0 <= token_size <= 240:
            raise ValueError("Zoom-tier token size must be between 0 and 240 pixels")
        if not 6 <= nameplate_size <= 32:
            raise ValueError("Zoom-tier nameplate size must be between 6 and 32 pixels")
        tiers[str(clicks)] = {
            "token_size": token_size,
            "nameplate_size": nameplate_size,
        }
    # Older builds generated this exact preset for every map. These were not
    # user-created overrides, so discard only that known automatic set.
    if tiers == LEGACY_GENERATED_ZOOM_TIERS:
        tiers = {}
    return {
        "default_zoom": default_zoom,
        "default_center_x": default_center_x,
        "default_center_y": default_center_y,
        "default_nameplate_size": default_nameplate_size,
        "tiers": dict(sorted(tiers.items(), key=lambda item: int(item[0]))),
    }


def normalize_campaign_game_state(
    value: Any,
    game_world_start_date: str,
) -> dict[str, Any]:
    from .board import (
        DEFAULT_MAP_TOKEN_SCALE,
        MIN_MAP_TOKEN_SCALE,
        normalize_group,
        normalize_obscuration,
        normalize_person_board,
        normalize_map_point,
    )
    from .creatures import normalize_campaign_creature
    from .battles import normalize_battles

    raw = deepcopy(value) if isinstance(value, dict) else {}
    current = str(
        raw.get("current_game_datetime")
        or f"{game_world_start_date}T08:00"
    ).strip()
    if not GAME_WORLD_DATETIME.fullmatch(current):
        raise ValueError("Campaign Game World Date and time must use YYYY-MM-DDTHH:MM")

    loaded_map_ids: list[str] = []
    for map_id in raw.get("loaded_map_ids", []) or []:
        map_id = str(map_id or "").strip()
        if map_id and map_id not in loaded_map_ids:
            loaded_map_ids.append(map_id)
    active_map_id = str(raw.get("active_map_id", "") or "").strip()
    if active_map_id and active_map_id not in loaded_map_ids:
        loaded_map_ids.append(active_map_id)
    raw_player_active_maps = raw.get("player_active_map_ids", {}) or {}
    if not isinstance(raw_player_active_maps, dict):
        raise ValueError("Campaign player active maps must be keyed by player ID")
    player_active_map_ids = {
        str(player_id).strip(): str(map_id).strip()
        for player_id, map_id in raw_player_active_maps.items()
        if str(player_id).strip() and str(map_id).strip()
    }

    map_states: dict[str, dict[str, Any]] = {}
    maps = raw.get("maps", {}) or {}
    if not isinstance(maps, dict):
        raise ValueError("Campaign map state must be an object keyed by map ID")
    for raw_map_id, raw_state in maps.items():
        map_id = str(raw_map_id or "").strip()
        if not map_id or not isinstance(raw_state, dict):
            raise ValueError("Every campaign map state requires a stable map ID")
        token_scale = float(raw_state.get("token_scale", DEFAULT_MAP_TOKEN_SCALE))
        if not MIN_MAP_TOKEN_SCALE <= token_scale <= 0.03:
            raise ValueError("Campaign token size is outside the supported range")
        obscurations = [
            normalize_obscuration(item)
            for item in (raw_state.get("obscurations", []) or [])
        ]
        if len({item["record_id"] for item in obscurations}) != len(obscurations):
            raise ValueError("Campaign obscuration IDs must be unique within a map")
        opacity = float(raw_state.get("obscuration_preview_opacity", 0.35))
        if not 0.05 <= opacity <= 1.0:
            raise ValueError("Campaign obscuration preview opacity is invalid")
        color = str(raw_state.get("obscuration_preview_color", "#ff0000") or "#ff0000").lower()
        if not re.fullmatch(r"#[0-9a-f]{6}", color):
            raise ValueError("Campaign obscuration preview color is invalid")
        raw_player_cameras = raw_state.get("player_cameras", {}) or {}
        if not isinstance(raw_player_cameras, dict):
            raise ValueError("Campaign player cameras must be keyed by player ID")
        player_cameras: dict[str, dict[str, float]] = {}
        for raw_player_id, raw_camera in raw_player_cameras.items():
            player_id = str(raw_player_id or "").strip()
            if not player_id:
                raise ValueError("Every saved player camera requires a player ID")
            player_cameras[player_id] = normalize_board_camera(raw_camera)
        map_states[map_id] = {
            "players_published": bool(raw_state.get("players_published", False)),
            "obscurations": obscurations,
            "obscuration_preview_opacity": opacity,
            "obscuration_preview_color": color,
            "token_scale": token_scale,
            "start_point": normalize_map_point(
                raw_state.get("start_point"), "Campaign map start point", optional=True
            ),
            "headmaster_camera": normalize_board_camera(
                raw_state.get("headmaster_camera")
            ),
            "player_cameras": player_cameras,
            "zoom_profile": normalize_zoom_profile(raw_state.get("zoom_profile")),
        }

    people: dict[str, dict[str, Any]] = {}
    raw_people = raw.get("people", {}) or {}
    if not isinstance(raw_people, dict):
        raise ValueError("Campaign person state must be an object keyed by person ID")
    for raw_person_id, raw_state in raw_people.items():
        person_id = str(raw_person_id or "").strip()
        if not person_id or not isinstance(raw_state, dict):
            raise ValueError("Every campaign person state requires a stable person ID")
        board = normalize_person_board({**raw_state, "portrait": None})
        wounds = []
        for wound in raw_state.get("wounds", []) or []:
            if not isinstance(wound, dict):
                raise ValueError("Campaign wounds must be objects")
            severity = str(wound.get("severity", "") or "").strip().lower()
            if severity not in {"light", "medium", "heavy"}:
                raise ValueError("Campaign wounds must be light, medium, or heavy")
            wounds.append({
                "record_id": str(wound.get("record_id", "") or uuid4()),
                "severity": severity,
                "injury_type": str(wound.get("injury_type", "") or "").strip()[:120],
                "note": str(wound.get("note", "") or "").strip()[:1000],
                "created_at": str(wound.get("created_at", "") or utc_now()),
            })
        notes = []
        for note in raw_state.get("character_notes", []) or []:
            if not isinstance(note, dict):
                raise ValueError("Campaign character notes must be objects")
            text = str(note.get("text", "") or "").strip()
            if text:
                notes.append({
                    "record_id": str(note.get("record_id", "") or uuid4()),
                    "text": text[:4000],
                    "created_at": str(note.get("created_at", "") or utc_now()),
                })
        battle = raw_state.get("battle")
        if battle is not None and not isinstance(battle, dict):
            raise ValueError("Campaign battle state must be an object")
        normalized_battle = None
        if isinstance(battle, dict) and bool(battle.get("active", True)):
            normalized_battle = {
                "active": True,
                "name": str(battle.get("name", "Battle") or "Battle").strip()[:200],
                "entered_at": str(battle.get("entered_at", "") or utc_now()),
            }
        raw_consumed = raw_state.get("consumed_inventory", {}) or {}
        if not isinstance(raw_consumed, dict):
            raise ValueError("Campaign consumed inventory must be keyed by item ID")
        consumed_inventory: dict[str, float | int] = {}
        for raw_item_id, raw_quantity in raw_consumed.items():
            item_id = str(raw_item_id or "").strip()
            try:
                quantity = float(raw_quantity)
            except (TypeError, ValueError) as error:
                raise ValueError("Consumed inventory quantities must be numbers") from error
            if not item_id or quantity < 0:
                raise ValueError("Consumed inventory requires item IDs and non-negative quantities")
            if quantity:
                consumed_inventory[item_id] = int(quantity) if quantity.is_integer() else quantity
        people[person_id] = {
            "placement": deepcopy(board["placement"]),
            "visibility": board["visibility"],
            "display_mode": board["display_mode"],
            "name_revealed": board["name_revealed"],
            "faction_revealed": board["faction_revealed"],
            "faction_organization_id": board["faction_organization_id"],
            "label_offset": deepcopy(board["label_offset"]),
            "nameplate_scale": board["nameplate_scale"],
            "wounds": wounds,
            "current_state": str(raw_state.get("current_state", "") or "").strip()[:240],
            "battle": normalized_battle,
            "character_notes": notes,
            "consumed_inventory": consumed_inventory,
            "campaign_inventory": _normalize_campaign_inventory(
                raw_state.get("campaign_inventory")
            ),
            "equipment": _normalize_equipment(raw_state.get("equipment")),
            "airborne": bool(raw_state.get("airborne", False)),
            "currency_knuts": max(0, int(raw_state.get("currency_knuts", 0) or 0)),
        }

    creatures: dict[str, dict[str, Any]] = {}
    raw_creatures = raw.get("creatures", {}) or {}
    if isinstance(raw_creatures, list):
        raw_creatures = {
            str(item.get("record_id", "") or ""): item
            for item in raw_creatures if isinstance(item, dict)
        }
    if not isinstance(raw_creatures, dict):
        raise ValueError("Campaign creatures must be keyed by instance ID")
    for raw_instance_id, raw_creature in raw_creatures.items():
        instance = normalize_campaign_creature(raw_creature)
        instance_id = str(raw_instance_id or instance["record_id"]).strip()
        if not instance_id or instance_id != instance["record_id"] or instance_id in creatures:
            raise ValueError("Campaign creature keys must match unique instance IDs")
        creatures[instance_id] = instance

    raw_counters = raw.get("creature_counters", {}) or {}
    if not isinstance(raw_counters, dict):
        raise ValueError("Campaign creature counters must be keyed by species ID")
    creature_counters: dict[str, int] = {}
    for raw_species_id, raw_counter in raw_counters.items():
        species_id = str(raw_species_id or "").strip()
        counter = int(raw_counter)
        if not species_id or counter < 0:
            raise ValueError("Campaign creature counters require species IDs and non-negative values")
        creature_counters[species_id] = counter

    groups = []
    for item in (raw.get("groups", []) or []):
        members = item.get("members", []) if isinstance(item, dict) else []
        if len(members) >= 2:
            groups.append(normalize_group(item))
        elif isinstance(item, dict) and len(members) == 1:
            groups.append(deepcopy(item))
    if len({item["record_id"] for item in groups}) != len(groups):
        raise ValueError("Campaign board group IDs must be unique")
    grouped_actors: set[tuple[str, str]] = set()
    for group in groups:
        group_location = str(group.get("location_id", "") or "")
        for member in group.get("members", []) or []:
            actor_type = str(member.get("actor_type", "person") or "person")
            actor_id = str(member.get("actor_id", "") or "")
            key = (actor_type, actor_id)
            if key in grouped_actors:
                raise ValueError("A board actor may belong to only one group")
            grouped_actors.add(key)
            if actor_type == "person":
                actor = people.get(actor_id)
            elif actor_type == "creature":
                actor = creatures.get(actor_id)
            else:
                raise ValueError("Campaign groups support people and creatures")
            if actor is None:
                raise ValueError("Campaign groups may only contain existing actors")
            placement = actor.get("placement") or {}
            if str(placement.get("location_id", "") or "") != group_location:
                raise ValueError("Every group member must occupy the group's location")
    region_interactions = _normalize_region_interaction_state(
        raw.get("region_interactions")
    )
    battles = normalize_battles(raw.get("battles"))
    actor_battles = {
        (participant["actor_type"], participant["actor_id"])
        for battle in battles.values()
        for participant in battle["participants"]
    }
    for actor_type, actor_id in actor_battles:
        if actor_type == "person" and actor_id not in people:
            raise ValueError("Battles may only contain existing people")
        if actor_type == "creature" and actor_id not in creatures:
            raise ValueError("Battles may only contain existing campaign creatures")
    return {
        "initialized": bool(raw.get("initialized", False)),
        "current_game_datetime": current,
        "loaded_map_ids": loaded_map_ids,
        "active_map_id": active_map_id,
        "player_active_map_ids": player_active_map_ids,
        "maps": map_states,
        "people": people,
        "creatures": creatures,
        "creature_counters": creature_counters,
        "groups": groups,
        "region_interactions": region_interactions,
        "battles": battles,
    }


def _normalize_campaign_inventory(value: Any) -> list[dict[str, Any]]:
    raw_stacks = value if isinstance(value, list) else []
    stacks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in raw_stacks:
        if not isinstance(raw, dict):
            raise ValueError("Campaign inventory stacks must be objects")
        stack_id = str(raw.get("record_id", "") or "").strip()
        item_id = str(raw.get("item_id", "") or raw.get("part_id", "") or "").strip()
        quantity = int(raw.get("quantity", 0))
        if not stack_id or stack_id in seen or not item_id or quantity <= 0:
            raise ValueError("Campaign inventory stacks require unique IDs, item IDs, and positive quantities")
        seen.add(stack_id)
        stacks.append({
            "record_id": stack_id,
            "item_id": item_id,
            "part_id": str(raw.get("part_id", "") or item_id),
            "name": str(raw.get("name", "") or "Creature part")[:200],
            "category": str(raw.get("category", "Creature Part") or "Creature Part")[:100],
            "quantity": quantity,
            "source_creature_id": str(raw.get("source_creature_id", "") or ""),
            "source_species_id": str(raw.get("source_species_id", "") or ""),
            "acquired_at": str(raw.get("acquired_at", "") or utc_now()),
            "definition_collection": str(raw.get("definition_collection", "") or "")[:100],
            "definition_record_id": str(raw.get("definition_record_id", "") or item_id),
            "description": str(raw.get("description", "") or "")[:4000],
        })
    return stacks


def _normalize_equipment(value: Any) -> dict[str, str]:
    raw = value if isinstance(value, dict) else {}
    return {
        slot: str(raw.get(slot, "") or "").strip()
        for slot in EQUIPMENT_SLOTS
    }


def _normalize_region_interaction_state(value: Any) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}

    def records(name: str, *, maximum: int = 100000) -> list[dict[str, Any]]:
        source = raw.get(name, []) or []
        if not isinstance(source, list) or len(source) > maximum:
            raise ValueError(f"Campaign region {name} must be a bounded list")
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in source:
            if not isinstance(item, dict):
                raise ValueError(f"Campaign region {name} entries must be objects")
            record_id = str(item.get("record_id", "") or "").strip()
            if not record_id or record_id in seen:
                raise ValueError(f"Campaign region {name} entries require unique IDs")
            seen.add(record_id)
            result.append(deepcopy(item))
        return result

    def counters(name: str) -> dict[str, int]:
        source = raw.get(name, {}) or {}
        if not isinstance(source, dict):
            raise ValueError(f"Campaign region {name} must be keyed by source ID")
        result: dict[str, int] = {}
        for raw_key, raw_value in source.items():
            key = str(raw_key or "").strip()
            amount = int(raw_value)
            if not key or amount < 0:
                raise ValueError(f"Campaign region {name} requires non-negative counters")
            result[key] = amount
        return result

    return {
        "attempts": records("attempts"),
        "secret_unlocks": records("secret_unlocks"),
        "revealed_secrets": records("revealed_secrets"),
        "source_depletion": counters("source_depletion"),
        "shop_window_sales": counters("shop_window_sales"),
        "purchases": records("purchases"),
        "natural_one_losses": records("natural_one_losses"),
    }


def _normalize_shared_tags(value: Any) -> list[dict[str, Any]]:
    raw_tags = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_names: set[str] = set()
    for raw in raw_tags:
        if not isinstance(raw, dict):
            raise ValueError("Campaign shared tags must be objects")
        record_id = str(raw.get("record_id", "") or "").strip()
        name = str(raw.get("name", "") or "").strip()[:100]
        normalized_name = re.sub(r"\s+", " ", name.casefold()).strip()
        if not record_id or not name or record_id in seen_ids or normalized_name in seen_names:
            raise ValueError("Campaign shared tags require unique IDs and names")
        seen_ids.add(record_id)
        seen_names.add(normalized_name)
        result.append({
            "record_id": record_id,
            "name": name,
            "normalized_name": normalized_name,
            "created_by_player_id": str(raw.get("created_by_player_id", "") or ""),
            "created_at": str(raw.get("created_at", "") or utc_now()),
        })
    return result


def _normalize_tag_assignments(value: Any, tag_ids: set[str]) -> list[dict[str, Any]]:
    raw_items = value if isinstance(value, list) else []
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in raw_items:
        if not isinstance(raw, dict):
            raise ValueError("Campaign tag assignments must be objects")
        collection = str(raw.get("collection", "") or "").strip()
        target_id = str(raw.get("target_record_id", "") or "").strip()
        tag_id = str(raw.get("tag_id", "") or "").strip()
        key = (collection, target_id, tag_id)
        if collection not in {"spells", "proficiencies", "recipes", "potions", "preparations", "foods_and_drinks"}:
            raise ValueError("Campaign tags may only target knowledge or recipes")
        if not target_id or tag_id not in tag_ids or key in seen:
            raise ValueError("Campaign tag assignments require unique valid targets and tags")
        seen.add(key)
        result.append({
            "record_id": str(raw.get("record_id", "") or uuid4()),
            "collection": collection,
            "target_record_id": target_id,
            "tag_id": tag_id,
            "created_by_player_id": str(raw.get("created_by_player_id", "") or ""),
            "created_at": str(raw.get("created_at", "") or utc_now()),
        })
    return result


def normalize_campaign(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Every campaign must be an object")
    record_id = str(value.get("record_id", "") or "").strip()
    name = str(value.get("name", "") or "").strip()
    if not record_id:
        raise ValueError("Every campaign requires a stable record ID")
    if not name:
        raise ValueError("Every campaign requires a name")
    result = deepcopy(value)
    result.update({
        "record_id": record_id,
        "name": name,
        "game_world_start_date": normalize_game_world_date(
            value.get("game_world_start_date")
        ),
        "created_at": str(value.get("created_at", "") or "").strip(),
        "last_updated": str(value.get("last_updated", "") or "").strip(),
        "history_policy": str(value.get("history_policy", HISTORY_KEEP) or HISTORY_KEEP)
        .strip()
        .casefold(),
    })
    if result["history_policy"] not in HISTORY_POLICIES:
        raise ValueError("Campaign history policy must keep or discard later world history")
    raw_events = value.get("events", []) or []
    if not isinstance(raw_events, list):
        raise ValueError("Campaign events must be a list")
    events: list[dict[str, Any]] = []
    event_ids: set[str] = set()
    for raw_event in raw_events:
        if not isinstance(raw_event, dict):
            raise ValueError("Every campaign event must be an object")
        event = deepcopy(raw_event)
        record_id = str(event.get("record_id", "") or "").strip()
        event_type = str(event.get("event_type", "") or "").strip()
        event_date = str(event.get("date", "") or "").strip()
        if not record_id or record_id in event_ids:
            raise ValueError("Campaign event IDs must be present and unique")
        if not event_type:
            raise ValueError("Every campaign event requires a type")
        # Campaign events use the same historical date representation as the
        # campaign clock. A time is optional but, when supplied, must be valid.
        normalize_game_world_date(event_date)
        event_time = str(event.get("time", "") or "").strip()
        if event_time and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", event_time):
            raise ValueError("Campaign event time must use a 24-hour HH:MM value")
        event.update({
            "record_id": record_id,
            "event_type": event_type,
            "date": event_date,
            "time": event_time,
        })
        event_ids.add(record_id)
        events.append(event)
    result["events"] = events
    raw_requests = value.get("requests", []) or []
    if not isinstance(raw_requests, list):
        raise ValueError("Campaign requests must be a list")
    requests: list[dict[str, Any]] = []
    request_ids: set[str] = set()
    for raw_request in raw_requests:
        if not isinstance(raw_request, dict):
            raise ValueError("Every campaign request must be an object")
        request = deepcopy(raw_request)
        request_id = str(request.get("record_id", "") or "").strip()
        request_type = str(request.get("request_type", "") or "").strip()
        status = str(request.get("status", "pending") or "pending").strip().casefold()
        if not request_id or request_id in request_ids:
            raise ValueError("Campaign request IDs must be present and unique")
        if not request_type:
            raise ValueError("Every campaign request requires a type")
        if status not in REQUEST_STATUSES:
            raise ValueError("Campaign request status is invalid")
        request.update({
            "record_id": request_id,
            "request_type": request_type,
            "status": status,
            "submitted_at": str(request.get("submitted_at", "") or "").strip(),
        })
        request_ids.add(request_id)
        requests.append(request)
    result["requests"] = requests
    result["shared_tags"] = _normalize_shared_tags(value.get("shared_tags"))
    result["tag_assignments"] = _normalize_tag_assignments(
        value.get("tag_assignments"),
        {item["record_id"] for item in result["shared_tags"]},
    )
    result["game_state"] = normalize_campaign_game_state(
        value.get("game_state"), result["game_world_start_date"]
    )
    return result


def validate_campaigns(document: dict[str, Any]) -> None:
    campaigns = document.get("campaigns")
    if not isinstance(campaigns, list):
        raise ValueError("campaign.json requires a campaigns list")
    normalized = [normalize_campaign(item) for item in campaigns]
    ids = [item["record_id"] for item in normalized]
    if len(ids) != len(set(ids)):
        raise ValueError("Campaign IDs must be unique")


class CampaignRepository:
    def __init__(self, store: SharedJsonStore | None = None):
        if store is None:
            from .store import SharedJsonStore

            store = SharedJsonStore()
        self.store = store

    def _save(self, session: Any, app_id: str):
        """Persist the normalized campaign document using sparse actor overlays.

        Campaign readers hydrate every stored overlay through ``normalize_campaign``.
        Default-only actors are implicit; battle participants retain an empty marker
        so relationship validation can still prove that their actor exists.
        """

        session.data = compact_campaign_document_for_storage(session.data)
        return self.store.save(session, app_id)

    def list(self) -> list[dict[str, Any]]:
        session = self.store.load("campaign.json")
        return sorted(
            (normalize_campaign(item) for item in session.data["campaigns"]),
            key=lambda item: (item["name"].casefold(), item["record_id"]),
        )

    def get(self, campaign_id: str) -> dict[str, Any]:
        campaign = next(
            (item for item in self.list() if item["record_id"] == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        return campaign

    @staticmethod
    def _person_state(
        board: dict[str, Any],
        existing: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        from .board import normalize_person_board

        normalized = normalize_person_board(board)
        prior = existing if isinstance(existing, dict) else {}
        return {
            "placement": deepcopy(normalized["placement"]),
            "visibility": normalized["visibility"],
            "display_mode": normalized["display_mode"],
            "name_revealed": normalized["name_revealed"],
            "faction_revealed": normalized["faction_revealed"],
            "faction_organization_id": normalized["faction_organization_id"],
            "label_offset": deepcopy(normalized["label_offset"]),
            "nameplate_scale": normalized["nameplate_scale"],
            "wounds": deepcopy(prior.get("wounds", []) or []),
            "current_state": str(prior.get("current_state", "") or "").strip()[:240],
            "battle": deepcopy(prior.get("battle")),
            "character_notes": deepcopy(prior.get("character_notes", []) or []),
            "consumed_inventory": deepcopy(prior.get("consumed_inventory", {}) or {}),
            "campaign_inventory": _normalize_campaign_inventory(
                prior.get("campaign_inventory")
            ),
            "equipment": _normalize_equipment(prior.get("equipment")),
            "airborne": bool(prior.get("airborne", False)),
            "currency_knuts": max(0, int(prior.get("currency_knuts", 0) or 0)),
        }

    def ensure_game_state(
        self,
        campaign_id: str,
        world_document: dict[str, Any],
        current_game_datetime: str | None = None,
    ) -> dict[str, Any]:
        from .board import DEFAULT_MAP_TOKEN_SCALE, WorldBoardRepository, normalize_person_board

        session = self.store.load("campaign.json")
        campaign = next(
            (item for item in session.data["campaigns"] if item.get("record_id") == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        normalized = normalize_campaign(campaign)
        if normalized["game_state"]["initialized"]:
            return normalized

        maps = WorldBoardRepository._location_maps(world_document)
        assigned_ids = {item["record_id"] for item in maps}
        map_states = {
            item["record_id"]: {
                "players_published": bool(item.get("players_published", False)),
                "obscurations": deepcopy(item.get("obscurations", []) or []),
                "obscuration_preview_opacity": float(item.get("obscuration_preview_opacity", 0.35)),
                "obscuration_preview_color": str(item.get("obscuration_preview_color", "#ff0000") or "#ff0000"),
                "token_scale": DEFAULT_MAP_TOKEN_SCALE,
                "start_point": deepcopy(item.get("start_point")),
                "headmaster_camera": normalize_board_camera(None),
                "player_cameras": {},
                "zoom_profile": normalize_zoom_profile(None),
            }
            for item in maps
        }
        people = {}
        occupied_map_ids: list[str] = []
        for person in world_document.get("people", []):
            if not isinstance(person, dict) or not person.get("record_id"):
                continue
            board = normalize_person_board(person.get("board"))
            person_id = str(person["record_id"])
            candidate = self._person_state(board)
            people.update(compact_campaign_person_overlays({person_id: candidate}))
            placement = board.get("placement")
            if placement and placement["map_id"] in assigned_ids:
                occupied_map_ids.append(placement["map_id"])
        loaded = [item["record_id"] for item in maps if item.get("players_published")]
        for map_id in occupied_map_ids:
            if map_id not in loaded:
                loaded.append(map_id)
        state = {
            "initialized": True,
            "current_game_datetime": (
                current_game_datetime
                or normalized["game_state"]["current_game_datetime"]
            ),
            "loaded_map_ids": loaded,
            "active_map_id": loaded[0] if loaded else "",
            "player_active_map_ids": {},
            "maps": map_states,
            "people": people,
            "creatures": deepcopy(normalized["game_state"].get("creatures", {})),
            "creature_counters": deepcopy(
                normalized["game_state"].get("creature_counters", {})
            ),
            "groups": deepcopy(world_document.get("board_groups", []) or []),
            "region_interactions": deepcopy(
                normalized["game_state"].get("region_interactions", {})
            ),
            "battles": deepcopy(normalized["game_state"].get("battles", {})),
        }
        campaign["game_state"] = normalize_campaign_game_state(
            state, normalized["game_world_start_date"]
        )
        campaign["last_updated"] = utc_now()
        outcome = self._save(session, "game-board")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return normalize_campaign(campaign)

    def update_game_state(
        self,
        campaign_id: str,
        updater: Callable[[dict[str, Any]], None],
    ) -> dict[str, Any]:
        session = self.store.load("campaign.json")
        campaign = next(
            (item for item in session.data["campaigns"] if item.get("record_id") == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        normalized = normalize_campaign(campaign)
        state = deepcopy(normalized["game_state"])
        updater(state)
        campaign["game_state"] = normalize_campaign_game_state(
            state, normalized["game_world_start_date"]
        )
        campaign["last_updated"] = utc_now()
        outcome = self._save(session, "game-board")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return normalize_campaign(campaign)

    def update_campaign(
        self,
        campaign_id: str,
        updater: Callable[[dict[str, Any]], None],
        *,
        app_id: str = "game-board",
    ) -> dict[str, Any]:
        """Atomically update campaign-level metadata such as shared tags."""

        session = self.store.load("campaign.json")
        campaign = next(
            (item for item in session.data["campaigns"] if item.get("record_id") == campaign_id),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        normalized = normalize_campaign(campaign)
        updater(normalized)
        normalized["last_updated"] = utc_now()
        campaign.clear()
        campaign.update(normalize_campaign(normalized))
        outcome = self._save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return normalize_campaign(campaign)

    def add_event(
        self,
        campaign_id: str,
        event_type: str,
        event_date: str,
        *,
        event_time: str = "",
        details: dict[str, Any] | None = None,
        app_id: str = "game-board",
    ) -> dict[str, Any]:
        """Append one campaign-only dated event without changing world.json."""

        session = self.store.load("campaign.json")
        campaign = next(
            (
                item for item in session.data["campaigns"]
                if item.get("record_id") == campaign_id
            ),
            None,
        )
        if campaign is None:
            raise KeyError("Unknown campaign")
        event = deepcopy(details) if isinstance(details, dict) else {}
        event.update({
            "record_id": str(uuid4()),
            "event_type": str(event_type or "").strip(),
            "date": normalize_game_world_date(event_date),
            "time": str(event_time or "").strip(),
        })
        campaign.setdefault("events", []).append(event)
        campaign["last_updated"] = utc_now()
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self._save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(event)

    def add_request(
        self,
        campaign_id: str,
        request_type: str,
        details: dict[str, Any],
        *,
        app_id: str = "game-board",
    ) -> dict[str, Any]:
        session = self.store.load("campaign.json")
        campaign = next((item for item in session.data["campaigns"] if item.get("record_id") == campaign_id), None)
        if campaign is None:
            raise KeyError("Unknown campaign")
        request = deepcopy(details)
        request.update({
            "record_id": str(uuid4()),
            "request_type": str(request_type or "").strip(),
            "status": "pending",
            "submitted_at": utc_now(),
        })
        campaign.setdefault("requests", []).append(request)
        campaign["last_updated"] = utc_now()
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self._save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(request)

    def resolve_request(
        self,
        campaign_id: str,
        request_id: str,
        decision: str,
        *,
        event_type: str = "",
        event_date: str = "",
        event_time: str = "",
        event_details: dict[str, Any] | None = None,
        state_updater: Callable[[dict[str, Any]], None] | None = None,
        app_id: str = "game-board",
    ) -> dict[str, Any]:
        """Resolve a request and append its approved event in one atomic save."""

        normalized_decision = str(decision or "").strip().casefold()
        if normalized_decision not in {"approved", "rejected"}:
            raise ValueError("A request must be approved or rejected")
        session = self.store.load("campaign.json")
        campaign = next((item for item in session.data["campaigns"] if item.get("record_id") == campaign_id), None)
        if campaign is None:
            raise KeyError("Unknown campaign")
        request = next((item for item in campaign.get("requests", []) or [] if item.get("record_id") == request_id), None)
        if request is None:
            raise KeyError("Unknown campaign request")
        if str(request.get("status", "pending")) != "pending":
            raise ValueError("Only pending requests can be resolved")
        request["status"] = normalized_decision
        request["resolved_at"] = utc_now()
        if normalized_decision == "approved":
            if not event_type:
                raise ValueError("An approved request requires an event type")
            event = deepcopy(event_details) if isinstance(event_details, dict) else {}
            event.update({
                "record_id": str(uuid4()),
                "event_type": str(event_type).strip(),
                "date": normalize_game_world_date(event_date),
                "time": str(event_time or "").strip(),
            })
            request["event_id"] = event["record_id"]
            campaign.setdefault("events", []).append(event)
            if state_updater is not None:
                state = deepcopy(normalize_campaign(campaign)["game_state"])
                state_updater(state)
                campaign["game_state"] = state
        campaign["last_updated"] = utc_now()
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self._save(session, app_id)
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(request)

    def save_campaign(
        self,
        name: str,
        game_world_start_date: str,
        campaign_id: str | None = None,
        history_policy: str | None = None,
    ) -> dict[str, Any]:
        session = self.store.load("campaign.json")
        now = utc_now()
        if campaign_id:
            campaign = next(
                (
                    item
                    for item in session.data["campaigns"]
                    if item.get("record_id") == campaign_id
                ),
                None,
            )
            if campaign is None:
                raise KeyError("Unknown campaign")
        else:
            campaign = {
                "record_id": str(uuid4()),
                "created_at": now,
            }
            session.data["campaigns"].append(campaign)
        campaign.update({
            "name": str(name or "").strip(),
            "game_world_start_date": game_world_start_date,
            "history_policy": str(
                history_policy
                if history_policy is not None
                else campaign.get("history_policy", HISTORY_KEEP)
            ).strip().casefold(),
            "events": deepcopy(campaign.get("events", []) or []),
            "requests": deepcopy(campaign.get("requests", []) or []),
            "last_updated": now,
        })
        normalized = normalize_campaign(campaign)
        campaign.clear()
        campaign.update(normalized)
        outcome = self._save(session, "campaigner")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before saving")
        return deepcopy(campaign)

    def delete(self, campaign_id: str) -> None:
        session = self.store.load("campaign.json")
        before = len(session.data["campaigns"])
        session.data["campaigns"] = [
            item
            for item in session.data["campaigns"]
            if item.get("record_id") != campaign_id
        ]
        if len(session.data["campaigns"]) == before:
            raise KeyError("Unknown campaign")
        outcome = self._save(session, "campaigner")
        if not outcome.saved:
            raise RuntimeError("The campaign changed elsewhere; reload before deleting")
