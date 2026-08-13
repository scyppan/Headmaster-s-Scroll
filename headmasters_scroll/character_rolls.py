from __future__ import annotations

import random
from typing import Any, Callable

from .character_sheet import ability_for_skill


class CharacterRollError(ValueError):
    pass


def _by_name(records: list[dict[str, Any]], name: str) -> dict[str, Any]:
    return next((item for item in records if item.get("name") == name), {"value": 0})


def _by_id(records: list[dict[str, Any]], record_id: str) -> dict[str, Any] | None:
    return next((item for item in records if str(item.get("record_id", "")) == record_id), None)


def _die(roller: Callable[[int, int], int]) -> int:
    return int(roller(1, 10))


def perform_character_roll(
    sheet: dict[str, Any],
    roll_type: str,
    target_id: str,
    *,
    roller: Callable[[int, int], int] = random.randint,
) -> dict[str, Any]:
    """Calculate one authorized roll. No browser-provided numeric value is used."""

    roll_type = str(roll_type or "").strip().casefold()
    target_id = str(target_id or "").strip()
    attributes = sheet.get("attributes", {}) or {}
    abilities = attributes.get("attributes", []) or []
    skills = attributes.get("skills", []) or []
    characteristics = attributes.get("characteristics", []) or []
    parental = attributes.get("parental_values", []) or []
    dice: list[int] = []
    bonus = 0
    threshold: int | None = None
    target_name = target_id

    if roll_type == "ability":
        target = _by_name(abilities, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown ability")
        target_name = target_id
        bonus = int(target.get("value", 0))
        dice = [_die(roller)]
    elif roll_type == "skill":
        target = _by_name(skills, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown skill")
        ability_name = ability_for_skill(target_id)
        bonus = int(target.get("value", 0)) + int(_by_name(abilities, ability_name).get("value", 0))
        target_name = target_id
        dice = [_die(roller)]
    elif roll_type == "characteristic":
        target = _by_name(characteristics, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown characteristic")
        count = max(1, min(5, int(target.get("dice", 1))))
        target_name = target_id
        dice = [_die(roller) for _ in range(count)]
    elif roll_type == "parental":
        target = _by_name(parental, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown parental value")
        bonus = int(target.get("value", 0))
        target_name = target_id
        dice = [_die(roller)]
    elif roll_type in {"spell", "proficiency", "recipe"}:
        collection = {"spell": "spells", "proficiency": "proficiencies", "recipe": "recipes"}[roll_type]
        target = _by_id(sheet.get(collection, []) or [], target_id)
        if target is None:
            raise PermissionError(f"This character does not know that {roll_type}")
        target_name = str(target.get("name") or roll_type.title())
        skill = str(target.get("skill") or ("Potions" if roll_type == "recipe" else ""))
        ability_name = ability_for_skill(skill)
        bonus = int(_by_name(skills, skill).get("value", 0)) + int(_by_name(abilities, ability_name).get("value", 0))
        try:
            threshold = int(target.get("threshold"))
        except (TypeError, ValueError):
            threshold = None
        dice = [_die(roller)]
    else:
        raise CharacterRollError("Unknown character action")

    natural = dice[0] if len(dice) == 1 else None
    total = sum(dice) + bonus
    critical = "failure" if natural == 1 else "success" if natural == 10 else ""
    success = None if threshold is None else bool(natural == 10 or (natural != 1 and total >= threshold))
    if threshold is None:
        sentence = f"{sheet['character_name']} rolled {target_name}: {total}."
    else:
        outcome = "succeeded" if success else "failed"
        sentence = f"{sheet['character_name']} attempted {target_name} and {outcome} with {total} against {threshold}."
    if critical:
        sentence = sentence[:-1] + f" ({'critical success' if critical == 'success' else 'critical failure'})."
    return {
        "action_type": roll_type,
        "target_id": target_id,
        "target_name": target_name,
        "dice": dice,
        "bonus": bonus,
        "total": total,
        "threshold": threshold,
        "success": success,
        "critical": critical,
        "text": sentence,
    }
