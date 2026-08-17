from __future__ import annotations

from copy import deepcopy
from typing import Any

from .character_attributes import (
    ABILITY_NAMES,
    CHARACTERISTIC_NAMES,
    SKILL_NAMES,
)


BONUS_CATEGORIES = (
    "Ability",
    "Skill",
    "Subtype",
    "Characteristic",
)

SPELL_SUBTYPE_TARGETS = (
    "Hex",
    "Curse",
    "Blood Magic",
    "Controlling",
    "Banishing",
    "Mental",
    "Concealing",
    "Utility",
    "Enchanting",
    "Alteration",
    "Healing",
    "Enhancing",
    "Environmental",
    "Jinx",
    "Shielding",
    "Repelling",
    "Counterspell",
)

BONUS_TARGETS = {
    "Ability": tuple(ABILITY_NAMES),
    "Skill": tuple(SKILL_NAMES),
    "Subtype": SPELL_SUBTYPE_TARGETS,
    "Characteristic": tuple(
        str(value).replace("_", " ").title()
        for value in CHARACTERISTIC_NAMES
    ),
}

IN_FLIGHT_EFFECT_TARGETS = {
    "Flying": "Skill",
    "Perception": "Skill",
    "Strength": "Characteristic",
    "Agility": "Characteristic",
}

BONUS_ACTIVATION_MODES = ("passive", "click")
TARGET_SCOPES = ("self", "group", "other", "none")
TARGET_SCOPE_LABELS = {
    "self": "Self",
    "group": "Group",
    "other": "Other",
    "none": "No Target",
}
TARGET_SCOPE_BY_LABEL = {
    label.casefold(): value for value, label in TARGET_SCOPE_LABELS.items()
}

_BONUS_CATEGORY_ALIASES = {
    "ability": "Ability",
    "attribute": "Ability",
    "skill": "Skill",
    "subtype": "Subtype",
    "spell subtype": "Subtype",
    "characteristic": "Characteristic",
}

_TARGET_ALIASES = {
    "defense against the dark arts": "Defense",
    "social skills": "Social",
    "ancient runes": "Runes",
    "magical creatures": "Creatures",
}


def normalize_target_scope(value: Any, *, default: str = "none") -> str:
    normalized = " ".join(str(value or "").split()).casefold()
    if normalized in TARGET_SCOPES:
        return normalized
    if normalized in TARGET_SCOPE_BY_LABEL:
        return TARGET_SCOPE_BY_LABEL[normalized]
    return default


def target_scope_label(value: Any) -> str:
    return TARGET_SCOPE_LABELS[normalize_target_scope(value)]


def normalize_bonus(bonus: Any) -> Any:
    if not isinstance(bonus, dict):
        return bonus

    normalized = deepcopy(bonus)
    category_key = " ".join(str(normalized.get("type", "") or "").split())
    category = _BONUS_CATEGORY_ALIASES.get(
        category_key.casefold(), category_key
    )
    normalized["type"] = category

    target = " ".join(str(normalized.get("target", "") or "").split())
    target = _TARGET_ALIASES.get(target.casefold(), target)
    canonical_targets = BONUS_TARGETS.get(category, ())
    target_by_name = {value.casefold(): value for value in canonical_targets}
    normalized["target"] = target_by_name.get(target.casefold(), target)

    mode = " ".join(
        str(normalized.get("activation_mode", "passive") or "passive").split()
    ).casefold()
    normalized["activation_mode"] = (
        mode if mode in BONUS_ACTIVATION_MODES else "passive"
    )
    normalized["target_scope"] = normalize_target_scope(
        normalized.get("target_scope"), default="self"
    )
    raw_depletable = normalized.get("depletable", False)
    if isinstance(raw_depletable, str):
        raw_depletable = raw_depletable.strip().casefold() in {
            "1", "true", "yes", "y", "on",
        }
    normalized["depletable"] = bool(raw_depletable)
    if normalized["activation_mode"] != "click":
        normalized["depletable"] = False
    return normalized


def normalize_bonuses(values: Any) -> Any:
    if not isinstance(values, list):
        return values
    return [normalize_bonus(value) for value in values]


def validate_bonus(bonus: Any) -> None:
    if not isinstance(bonus, dict):
        raise TypeError("Every bonus must be structured.")

    category = bonus.get("type", "")
    if category not in BONUS_CATEGORIES:
        raise ValueError("Every bonus must use a defined category.")

    target = str(bonus.get("target", "") or "").strip()
    if target not in BONUS_TARGETS[category]:
        raise ValueError(
            f"Every {category.lower()} bonus must select a defined value."
        )

    amount = bonus.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int):
        raise TypeError("Every bonus amount must be a whole number.")

    mode = bonus.get("activation_mode")
    if mode not in BONUS_ACTIVATION_MODES:
        raise ValueError("Every bonus must be Passive or Clickable.")

    if bonus.get("target_scope") not in TARGET_SCOPES:
        raise ValueError("Every bonus must define who it targets.")

    if not isinstance(bonus.get("depletable"), bool):
        raise TypeError("Depletable must be true or false.")
    if mode != "click" and bonus.get("depletable"):
        raise ValueError("Only clickable bonuses can be depletable.")


def validate_bonuses(values: Any) -> None:
    if not isinstance(values, list):
        raise TypeError("Bonuses must be a list.")
    for value in values:
        validate_bonus(value)


def normalize_in_flight_effect(effect: Any) -> Any:
    """Normalize a passive modifier that exists only while airborne."""
    if not isinstance(effect, dict):
        return effect
    normalized = normalize_bonus(effect)
    target = " ".join(str(normalized.get("target", "") or "").split())
    canonical = {
        value.casefold(): value for value in IN_FLIGHT_EFFECT_TARGETS
    }.get(target.casefold(), target)
    normalized.update({
        "type": IN_FLIGHT_EFFECT_TARGETS.get(canonical, ""),
        "target": canonical,
        "activation_mode": "passive",
        "target_scope": "self",
        "depletable": False,
    })
    return normalized


def normalize_in_flight_effects(values: Any) -> Any:
    if not isinstance(values, list):
        return values
    return [normalize_in_flight_effect(value) for value in values]


def validate_in_flight_effects(values: Any) -> None:
    if not isinstance(values, list):
        raise TypeError("In-flight effects must be a list.")
    for value in values:
        normalized = normalize_in_flight_effect(value)
        if not isinstance(normalized, dict):
            raise TypeError("Every in-flight effect must be structured.")
        target = normalized.get("target", "")
        if target not in IN_FLIGHT_EFFECT_TARGETS:
            raise ValueError(
                "In-flight effects may affect only Flying, Perception, "
                "Strength, or Agility."
            )
        amount = normalized.get("amount")
        if isinstance(amount, bool) or not isinstance(amount, int):
            raise TypeError("Every in-flight effect must use a whole number.")
        validate_bonus(normalized)
