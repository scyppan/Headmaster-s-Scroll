from __future__ import annotations

from copy import deepcopy
from uuid import uuid4

from headmasters_scroll.effects import (
    BONUS_ACTIVATION_MODES,
    TARGET_SCOPES,
    normalize_target_scope,
)


ITEM_EFFECT_TYPES = ("Spell", "Proficiency", "Potion", "Custom")
ITEM_EFFECT_COLLECTIONS = {
    "Spell": ("spells",),
    "Proficiency": ("proficiencies",),
    "Potion": ("potions", "preparations"),
    "Custom": (),
}


def normalize_item_action(value):
    if not isinstance(value, dict):
        return value
    action = deepcopy(value)
    effect_type = str(action.get("effect_type", "") or "").strip().title()
    if not effect_type:
        roll_type = str(action.get("roll_type", "") or "").casefold()
        if roll_type == "spell":
            effect_type = "Spell"
        elif roll_type == "proficiency":
            effect_type = "Proficiency"
        elif str(action.get("action_type", "") or "").casefold() == "potion":
            effect_type = "Potion"
        else:
            effect_type = "Custom"
    action["effect_type"] = effect_type
    action["record_id"] = str(action.get("record_id") or uuid4())
    action["name"] = " ".join(str(action.get("name", "") or "").split())
    action["description"] = str(
        action.get("description", action.get("message", "")) or ""
    ).strip()
    action["target_id"] = str(action.get("target_id", "") or "").strip()
    action["target_collection"] = str(
        action.get("target_collection", "") or ""
    ).strip()
    mode = str(action.get("activation_mode", "click") or "click").casefold()
    if effect_type != "Custom":
        mode = "click"
    action["activation_mode"] = (
        mode if mode in BONUS_ACTIVATION_MODES else "click"
    )
    action["target_scope"] = normalize_target_scope(
        action.get("target_scope"), default="self"
    )
    action["depletable"] = bool(action.get("depletable", False))
    if action["activation_mode"] != "click":
        action["depletable"] = False
    action["consume_quantity"] = 1 if action["depletable"] else 0
    if effect_type == "Spell":
        action["action_type"] = "roll"
        action["roll_type"] = "spell"
        action["target_collection"] = "spells"
    elif effect_type == "Proficiency":
        action["action_type"] = "roll"
        action["roll_type"] = "proficiency"
        action["target_collection"] = "proficiencies"
    elif effect_type == "Potion":
        action["action_type"] = "potion"
        if action["target_collection"] not in {"potions", "preparations"}:
            action["target_collection"] = "potions"
    else:
        action["action_type"] = "message"
        action["message"] = action["description"]
        action["target_id"] = ""
        action["target_collection"] = ""
    return action


def normalize_item_actions(values):
    if not isinstance(values, list):
        return values
    return [normalize_item_action(value) for value in values]


def validate_item_actions(values, database):
    if not isinstance(values, list):
        raise TypeError("Item effects must be a list.")
    seen = set()
    for raw_action in values:
        action = normalize_item_action(raw_action)
        if not isinstance(action, dict):
            raise TypeError("Every item effect must be structured.")
        effect_type = action.get("effect_type")
        if effect_type not in ITEM_EFFECT_TYPES:
            raise ValueError("Every item effect must use a defined type.")
        action_id = action.get("record_id")
        if not action_id or action_id in seen:
            raise ValueError("Every item effect needs a unique stable ID.")
        seen.add(action_id)
        if action.get("activation_mode") not in BONUS_ACTIVATION_MODES:
            raise ValueError("Every item effect must be Passive or Clickable.")
        if action.get("target_scope") not in TARGET_SCOPES:
            raise ValueError("Every item effect must define who it targets.")
        if effect_type == "Custom":
            if not action.get("name") or not action.get("description"):
                raise ValueError("A custom item effect needs a name and effect text.")
            continue
        collection = action.get("target_collection")
        if collection not in ITEM_EFFECT_COLLECTIONS[effect_type]:
            raise ValueError(f"The {effect_type.lower()} effect has an invalid source.")
        target_id = action.get("target_id")
        matches = database.get_collection(collection)
        if not any(str(record.get("record_id", "")) == target_id for record in matches):
            raise ValueError(f"The selected {effect_type.lower()} no longer exists.")

