from __future__ import annotations

import random
from copy import deepcopy
from typing import Any, Iterable
from uuid import uuid4


BATTLE_STATUSES = {"draft", "active"}
ACTOR_TYPES = {"person", "creature"}


def normalize_battle_participant(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Battle participants must be objects")
    record_id = str(value.get("record_id", "") or uuid4()).strip()
    actor_type = str(value.get("actor_type", "") or "person").strip().casefold()
    actor_id = str(value.get("actor_id", "") or "").strip()
    if not record_id or not actor_id or actor_type not in ACTOR_TYPES:
        raise ValueError("Battle participants require stable actor references")
    return {
        "record_id": record_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "calculated_rank": max(0, int(value.get("calculated_rank", 0) or 0)),
        "random_key": float(value.get("random_key", 0.0) or 0.0),
        "eligible_round": max(1, int(value.get("eligible_round", 1) or 1)),
        "acted_round": max(0, int(value.get("acted_round", 0) or 0)),
        "skipped_round": max(0, int(value.get("skipped_round", 0) or 0)),
        "action_summary": str(value.get("action_summary", "") or "")[:1000],
        "joined_at": str(value.get("joined_at", "") or ""),
    }


def normalize_battle(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Campaign battles must be objects")
    record_id = str(value.get("record_id", "") or uuid4()).strip()
    name = str(value.get("name", "") or "Battle").strip()[:200]
    map_id = str(value.get("map_id", "") or "").strip()
    status = str(value.get("status", "draft") or "draft").strip().casefold()
    if not record_id or not name or not map_id or status not in BATTLE_STATUSES:
        raise ValueError("Every battle requires an ID, name, map, and valid status")
    participants = [
        normalize_battle_participant(item)
        for item in (value.get("participants", []) or [])
    ]
    participant_ids = [item["record_id"] for item in participants]
    actor_keys = [(item["actor_type"], item["actor_id"]) for item in participants]
    if len(participant_ids) != len(set(participant_ids)) or len(actor_keys) != len(set(actor_keys)):
        raise ValueError("Battle participants must be unique")
    order = [str(item or "") for item in (value.get("order", []) or [])]
    order = [item for item in order if item in set(participant_ids)]
    order.extend(item for item in participant_ids if item not in order)
    calculated = [str(item or "") for item in (value.get("calculated_order", []) or [])]
    calculated = [item for item in calculated if item in set(participant_ids)]
    calculated.extend(item for item in participant_ids if item not in calculated)
    current_id = str(value.get("current_participant_id", "") or "")
    if current_id not in set(participant_ids):
        current_id = order[0] if order else ""
    return {
        "record_id": record_id,
        "name": name,
        "map_id": map_id,
        "status": status,
        "round": max(1, int(value.get("round", 1) or 1)),
        "current_participant_id": current_id,
        "participants": participants,
        "order": order,
        "calculated_order": calculated,
        "manual_order": bool(value.get("manual_order", False)),
        "created_at": str(value.get("created_at", "") or ""),
        "started_at": str(value.get("started_at", "") or ""),
        "updated_at": str(value.get("updated_at", "") or ""),
    }


def normalize_battles(value: Any) -> dict[str, dict[str, Any]]:
    raw = value if isinstance(value, dict) else {}
    battles: dict[str, dict[str, Any]] = {}
    occupied: set[tuple[str, str]] = set()
    for raw_id, item in raw.items():
        battle = normalize_battle(item)
        battle_id = str(raw_id or battle["record_id"])
        if battle_id != battle["record_id"] or battle_id in battles:
            raise ValueError("Campaign battle keys must match unique battle IDs")
        for participant in battle["participants"]:
            key = (participant["actor_type"], participant["actor_id"])
            if key in occupied:
                raise ValueError("A board actor may participate in only one active battle")
            occupied.add(key)
        battles[battle_id] = battle
    return battles


def calculated_order(
    people: Iterable[dict[str, Any]], creatures: Iterable[dict[str, Any]],
) -> list[str]:
    """Return stable legacy-style order using persisted participant metadata.

    People are already assigned a rank derived from date-effective Eminence and
    age. Creatures are inserted at their persisted random slots.
    """

    people_sorted = sorted(
        people,
        key=lambda item: (
            int(item.get("calculated_rank", 0)),
            float(item.get("random_key", 0.0)),
            str(item.get("record_id", "")),
        ),
    )
    result = [str(item["record_id"]) for item in people_sorted]
    for creature in sorted(
        creatures,
        key=lambda item: (float(item.get("random_key", 0.0)), str(item.get("record_id", ""))),
    ):
        key = max(0.0, min(0.999999999, float(creature.get("random_key", 0.0))))
        position = int(key * (len(result) + 1))
        result.insert(position, str(creature["record_id"]))
    return result


def participant(
    actor_type: str, actor_id: str, *, rank: int = 0, now: str = "",
    eligible_round: int = 1, rng: random.Random | random.SystemRandom | None = None,
) -> dict[str, Any]:
    source = rng or random.SystemRandom()
    return normalize_battle_participant({
        "record_id": str(uuid4()),
        "actor_type": actor_type,
        "actor_id": actor_id,
        "calculated_rank": rank,
        "random_key": source.random(),
        "eligible_round": eligible_round,
        "joined_at": now,
    })


def public_battle(
    battle: dict[str, Any], actors: dict[tuple[str, str], dict[str, Any]],
    *, viewer_character_id: str = "",
) -> dict[str, Any] | None:
    if battle.get("status") != "active":
        return None
    membership = next((
        item for item in battle["participants"]
        if item["actor_type"] == "person" and item["actor_id"] == viewer_character_id
    ), None)
    if membership is None:
        return None
    by_id = {item["record_id"]: item for item in battle["participants"]}
    current = by_id.get(battle["current_participant_id"])
    visible_order: list[dict[str, Any]] = []
    for participant_id in battle["order"]:
        item = by_id.get(participant_id)
        if not item:
            continue
        actor = actors.get((item["actor_type"], item["actor_id"]), {})
        if actor.get("visibility") != "players" and not (
            item["actor_type"] == "person"
            and item["actor_id"] == viewer_character_id
        ):
            continue
        visible_order.append({
            "participant_id": participant_id,
            "actor_type": item["actor_type"],
            "actor_id": item["actor_id"],
            "name": str(actor.get("name") or actor.get("true_name") or "Unknown"),
            "current": participant_id == battle["current_participant_id"],
            "acted": item["acted_round"] == battle["round"],
            "skipped": item["skipped_round"] == battle["round"],
            "mine": item["actor_type"] == "person" and item["actor_id"] == viewer_character_id,
        })
    current_hidden = False
    if current:
        actor = actors.get((current["actor_type"], current["actor_id"]), {})
        current_hidden = actor.get("visibility") != "players" and not (
            current["actor_type"] == "person"
            and current["actor_id"] == viewer_character_id
        )
    current_actor = actors.get(
        (current["actor_type"], current["actor_id"]), {}
    ) if current else {}
    return {
        "record_id": battle["record_id"],
        "name": battle["name"],
        "round": battle["round"],
        "current_participant_id": battle["current_participant_id"],
        "current_name": "Headmaster turn" if current_hidden else str(
            current_actor.get("name") or current_actor.get("true_name") or "No active turn"
        ),
        "current_hidden": current_hidden,
        "my_turn": bool(current and current["actor_type"] == "person" and current["actor_id"] == viewer_character_id),
        "order": visible_order,
    }
