ITEM_EVENT_LINK_TYPES = (
    {
        "value": "passed_down",
        "label": "Passed down",
        "why": "The event records the item being handed from one holder to another.",
        "consequence": "The item continues to exist and its possession changes.",
    },
    {
        "value": "gifted",
        "label": "Gifted",
        "why": "The event records the item being deliberately given to a new owner.",
        "consequence": "The recipient becomes the item's owner and the item continues to exist.",
    },
    {
        "value": "crafted",
        "label": "Crafted",
        "why": "The event records the creation of the item.",
        "consequence": "The item begins to exist at this event.",
    },
    {
        "value": "destroyed",
        "label": "Destroyed",
        "why": "The event records the destruction of the item.",
        "consequence": "The item ceases to exist at this event.",
    },
    {
        "value": "lost",
        "label": "Lost",
        "why": "The event records the holder losing the item.",
        "consequence": "The item becomes unpossessed until it is recovered.",
    },
    {
        "value": "taken",
        "label": "Taken",
        "why": "The event records the item being taken from its holder.",
        "consequence": "Possession changes as a result of the event.",
    },
    {
        "value": "retained",
        "label": "Retained",
        "why": "The event records the item remaining with the same holder.",
        "consequence": "The item stays in its current possession and continues to exist.",
    },
    {
        "value": "history",
        "label": "History",
        "why": "The event records something that happened to or involved the item.",
        "consequence": "The event becomes part of the item's history without changing its possession or lifecycle.",
    },
    {
        "value": "lore",
        "label": "Lore",
        "why": "The event records a story, belief, or piece of lore associated with the item.",
        "consequence": "The lore becomes associated with the item without changing its possession or lifecycle.",
    },
    {
        "value": "found",
        "label": "Found",
        "why": "The event records the item being discovered or recovered.",
        "consequence": "The item is known or possessed again as a result of the event.",
    },
)
DEFAULT_ITEM_EVENT_LINK_TYPE = "passed_down"
ITEM_EVENT_OWNERSHIP_METHODS = {
    "passed_down": "Passed down",
    "gifted": "Gifted",
    "crafted": "Crafted",
    "destroyed": "Destroyed",
    "lost": "Lost",
    "taken": "Taken",
    "found": "Found",
}
ITEM_EVENT_NEW_OWNER_LINK_TYPES = frozenset(
    ("passed_down", "gifted", "taken")
)


def item_event_link_type_options():
    return [dict(option) for option in ITEM_EVENT_LINK_TYPES]


def item_event_ownership_method(value):
    normalized_value = normalize_item_event_link_type(value)
    return ITEM_EVENT_OWNERSHIP_METHODS.get(normalized_value, "")


def normalize_item_event_link_type(value, event_type=""):
    requested_value = str(value or "").strip().casefold().replace(" ", "_")

    for option in ITEM_EVENT_LINK_TYPES:
        if requested_value in (
            option["value"].casefold(),
            option["label"].casefold().replace(" ", "_"),
        ):
            return option["value"]

    if str(event_type or "").strip().casefold() == "crafted":
        return "crafted"

    if str(event_type or "").strip().casefold() == "gifted":
        return "gifted"

    if str(event_type or "").strip().casefold() == "destroyed":
        return "destroyed"

    return DEFAULT_ITEM_EVENT_LINK_TYPE


def normalize_item_event_link_types(value, item_ids, event_type=""):
    candidate_values = value if isinstance(value, dict) else {}
    normalized_values = {}

    for item_id in item_ids or ():
        normalized_item_id = str(item_id or "").strip()

        if not normalized_item_id or normalized_item_id in normalized_values:
            continue

        normalized_values[normalized_item_id] = normalize_item_event_link_type(
            candidate_values.get(normalized_item_id),
            event_type,
        )

    return normalized_values


def normalize_item_event_new_owner(value):
    if isinstance(value, dict):
        person_id = str(value.get("person_id", "") or "").strip()
        person_name = " ".join(
            str(value.get("person_name", "") or "").strip().split()
        )
    else:
        person_id = str(value or "").strip()
        person_name = ""

    return {
        "person_id": person_id,
        "person_name": person_name,
    }


def normalize_item_event_new_owners(value, item_ids, item_link_types):
    candidate_values = value if isinstance(value, dict) else {}
    normalized_link_types = (
        item_link_types if isinstance(item_link_types, dict) else {}
    )
    normalized_values = {}

    for item_id in item_ids or ():
        normalized_item_id = str(item_id or "").strip()

        if (
            not normalized_item_id
            or normalized_link_types.get(normalized_item_id)
            not in ITEM_EVENT_NEW_OWNER_LINK_TYPES
        ):
            continue

        owner = normalize_item_event_new_owner(
            candidate_values.get(normalized_item_id)
        )

        if owner["person_id"] or owner["person_name"]:
            normalized_values[normalized_item_id] = owner

    return normalized_values


def item_event_link_type(event, item_id):
    event_values = event if isinstance(event, dict) else {}
    normalized_item_id = str(item_id or "").strip()

    if not normalized_item_id:
        return normalize_item_event_link_type(
            "",
            event_values.get("event_type", ""),
        )

    return normalize_item_event_link_type(
        (
            event_values.get("item_link_types", {})
            if isinstance(event_values.get("item_link_types", {}), dict)
            else {}
        ).get(normalized_item_id),
        event_values.get("event_type", ""),
    )


def item_event_new_owner(event, item_id):
    event_values = event if isinstance(event, dict) else {}
    normalized_item_id = str(item_id or "").strip()

    if not normalized_item_id:
        return normalize_item_event_new_owner(None)

    owner_values = event_values.get("item_new_owners", {})
    return normalize_item_event_new_owner(
        (
            owner_values
            if isinstance(owner_values, dict)
            else {}
        ).get(normalized_item_id)
    )


def item_event_link_type_label(value, new_owner=None):
    normalized_value = normalize_item_event_link_type(value)

    for option in ITEM_EVENT_LINK_TYPES:
        if option["value"] == normalized_value:
            label = option["label"]

            if normalized_value in ITEM_EVENT_NEW_OWNER_LINK_TYPES:
                owner = normalize_item_event_new_owner(new_owner)

                if owner["person_name"]:
                    relationship_word = (
                        "by" if normalized_value == "taken" else "to"
                    )
                    return (
                        f"{label} {relationship_word} "
                        f"{owner['person_name']}"
                    )

            return label

    return "Passed down"
