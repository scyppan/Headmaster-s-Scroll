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


def _component(label: str, value: int, kind: str = "modifier") -> dict[str, Any]:
    return {"label": label, "value": int(value), "kind": kind}


def _roll_value(record: dict[str, Any]) -> int:
    return int(record.get("total", record.get("value", 0)) or 0)


def _roll_text(
    character_name: str,
    roll_type: str,
    target_name: str,
    total: int,
    threshold: int | None,
    critical: str,
    success: bool | None,
) -> str:
    """Preserve Character Controls' established public roll wording."""

    if roll_type == "ability":
        if critical == "success":
            return f"{character_name} CRITICALLY SUCCEEDS a straight {target_name} roll with a total roll value of {total}."
        if critical == "failure":
            return f"{character_name} CRITICALLY FAILS a straight {target_name} roll."
        return f"{character_name} rolls a straight {target_name} roll with a total roll value of {total}."
    if roll_type == "skill":
        if target_name in {"Charms", "Dark Arts", "Defense", "Transfiguration"}:
            if critical == "success":
                return f"{character_name} attempts to cast a straight {target_name} spell and CRITICALLY SUCCEEDS with a total roll value of {total}."
            if critical == "failure":
                return f"{character_name} attempts to cast a straight {target_name} spell and CRITICALLY FAILS."
            return f"{character_name} attempts to cast a straight {target_name} spell with a total roll value of {total}."
        article = "an" if target_name[:1].casefold() in "aeiou" else "a"
        if critical == "success":
            return f"{character_name} attempts {article} {target_name} check and CRITICALLY SUCCEEDS with a total roll value of {total}."
        if critical == "failure":
            return f"{character_name} attempts {article} {target_name} check and CRITICALLY FAILS."
        return f"{character_name} attempts {article} {target_name} check with a total roll value of {total}."
    if roll_type == "characteristic":
        return f"{character_name} rolls a {target_name} roll with a total roll value of {total}."
    if roll_type == "parental":
        if critical == "success":
            return f"{character_name}'s parents roll a {target_name} roll and CRITICALLY SUCCEED. They deny {character_name}'s request."
        if critical == "failure":
            return f"{character_name}'s parents roll a {target_name} roll and CRITICALLY FAIL. They agree to {character_name}'s request."
        return f"{character_name}'s parents roll a {target_name} roll with a total roll value of {total}."
    if roll_type == "spell":
        if critical == "failure":
            return f"{character_name} CRITICALLY FAILS to cast {target_name}."
        if critical == "success" and success:
            return f"{character_name} CRITICALLY SUCCEEDS in casting {target_name} with a total roll value of {total}."
        if success:
            return f"{character_name} successfully casts {target_name} with a total roll value of {total}."
        return f"{character_name} fails to cast {target_name}."
    if roll_type == "proficiency":
        if critical == "failure":
            return f"{character_name} CRITICALLY FAILS to perform the proficiency {target_name}."
        if critical == "success" and success:
            return f"{character_name} CRITICALLY SUCCEEDS in performing the proficiency {target_name} with a total roll value of {total}."
        if success:
            return f"{character_name} successfully performs the proficiency {target_name} with a total roll value of {total}."
        return f"{character_name} fails to perform the {target_name} proficiency."
    if roll_type == "recipe":
        if critical == "failure":
            return f"{character_name} CRITICALLY FAILS to prepare {target_name}. What a mess!"
        if critical == "success" and success:
            return f"{character_name} CRITICALLY SUCCEEDS in preparing {target_name} with a total roll value of {total}."
        if success:
            return f"{character_name} successfully prepares {target_name} with a total roll value of {total}."
        return f"{character_name} fails to prepare {target_name}."
    return f"{character_name} rolled {target_name}: {total}."


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
    components: list[dict[str, Any]] = []
    ability_name = ""
    skill_name = ""

    if roll_type == "ability":
        target = _by_name(abilities, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown ability")
        target_name = target_id
        bonus = _roll_value(target)
        dice = [_die(roller)]
        components = [_component("d10", dice[0], "die"), _component(target_name, bonus)]
    elif roll_type == "skill":
        target = _by_name(skills, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown skill")
        ability_name = ability_for_skill(target_id)
        skill_value = _roll_value(target)
        ability_value = _roll_value(_by_name(abilities, ability_name))
        bonus = skill_value + ability_value
        target_name = target_id
        dice = [_die(roller)]
        skill_name = target_id
        components = [
            _component("d10", dice[0], "die"),
            _component(ability_name or "Ability", ability_value),
            _component(skill_name, skill_value),
        ]
    elif roll_type == "characteristic":
        target = _by_name(characteristics, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown characteristic")
        count = max(1, min(5, int(target.get("dice", 1))))
        target_name = target_id
        dice = [_die(roller) for _ in range(count)]
        components = [
            _component(f"d10 {index + 1}", value, "die")
            for index, value in enumerate(dice)
        ]
    elif roll_type == "parental":
        target = _by_name(parental, target_id)
        if not target or target.get("name") != target_id:
            raise CharacterRollError("Unknown parental value")
        bonus = int(target.get("value", 0))
        target_name = target_id
        dice = [_die(roller)]
        components = [_component("d10", dice[0], "die"), _component(target_name, bonus)]
    elif roll_type in {"spell", "proficiency", "recipe"}:
        collection = {"spell": "spells", "proficiency": "proficiencies", "recipe": "recipes"}[roll_type]
        target = _by_id(sheet.get(collection, []) or [], target_id)
        if target is None:
            raise PermissionError(f"This character does not know that {roll_type}")
        target_name = str(target.get("name") or roll_type.title())
        skill_name = str(target.get("skill") or ("Potions" if roll_type == "recipe" else ""))
        ability_name = ability_for_skill(skill_name)
        skill_value = _roll_value(_by_name(skills, skill_name))
        ability_value = _roll_value(_by_name(abilities, ability_name))
        bonus = skill_value + ability_value
        try:
            threshold = int(target.get("threshold"))
        except (TypeError, ValueError):
            threshold = None
        dice = [_die(roller)]
        components = [
            _component("d10", dice[0], "die"),
            _component(ability_name or "Ability", ability_value),
            _component(skill_name or "Skill", skill_value),
        ]
    else:
        raise CharacterRollError("Unknown character action")

    natural = dice[0] if len(dice) == 1 else None
    total = sum(dice) + bonus
    critical = "failure" if natural == 1 else "success" if natural == 10 else ""
    success = None if threshold is None else bool(natural == 10 or (natural != 1 and total >= threshold))
    sentence = _roll_text(
        str(sheet["character_name"]), roll_type, target_name, total,
        threshold, critical, success,
    )
    formula = " + ".join(str(item["value"]) for item in components) or str(total)
    return {
        "schema_version": 1,
        "action_type": roll_type,
        "target_id": target_id,
        "target_name": target_name,
        "dice": dice,
        "bonus": bonus,
        "total": total,
        "threshold": threshold,
        "success": success,
        "critical": critical,
        "outcome": (
            "critical_success" if critical == "success"
            else "critical_failure" if critical == "failure"
            else "success" if success is True
            else "failure" if success is False
            else "rolled"
        ),
        "formula": formula,
        "components": components,
        "ability_name": ability_name,
        "skill_name": skill_name,
        "text": sentence,
    }
