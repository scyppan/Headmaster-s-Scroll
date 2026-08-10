import uuid
from copy import deepcopy

from mage_maker.core.dates import format_line_item_date
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    normalize_world_event_time,
    split_world_event_date,
    world_event_sort_key,
)


ITEM_CATEGORIES_SETTING_KEY = "item_categories"
ITEM_GROUPS_SETTING_KEY = "item_groups"
DEFAULT_ITEM_CATEGORY = "Heirlooms"
DEFAULT_ITEM_CATEGORIES = (DEFAULT_ITEM_CATEGORY,)
UNGROUPED_ITEM_GROUP_LABEL = "Ungrouped"
UNPOSSESSED_ITEM_HOLDER_LABEL = "Unpossessed"
ITEM_PASSAGE_METHODS = (
    "First recorded",
    "Crafted",
    "Passed down",
    "Inherited",
    "Gifted",
    "Purchased",
    "Found",
    "Taken",
    "Lost",
    "Destroyed",
    "Other",
)


def normalize_item_category(value):
    category = " ".join(str(value or "").strip().split())

    if not category:
        raise ValueError("An item category needs a name.")

    return category


def normalize_item_categories(value):
    if value in (None, ""):
        candidate_categories = []
    elif isinstance(value, (list, tuple)):
        candidate_categories = list(value)
    else:
        raise TypeError("Item categories must be a list.")

    categories = []
    used_names = set()

    for candidate_category in (
        *DEFAULT_ITEM_CATEGORIES,
        *candidate_categories,
    ):
        category = normalize_item_category(candidate_category)
        category_key = category.casefold()

        if category_key in used_names:
            continue

        used_names.add(category_key)
        categories.append(category)

    return categories


def normalize_item_group(value):
    group = " ".join(str(value or "").strip().split())

    if group.casefold() in (
        "all groups",
        UNGROUPED_ITEM_GROUP_LABEL.casefold(),
    ):
        raise ValueError(
            f'"{group}" is reserved for the item group list.'
        )

    return group


def normalize_item_groups(value):
    if value in (None, ""):
        candidate_groups = []
    elif isinstance(value, (list, tuple)):
        candidate_groups = list(value)
    else:
        raise TypeError("Item groups must be a list.")

    groups = []
    used_names = set()

    for candidate_group in candidate_groups:
        group = normalize_item_group(candidate_group)

        if not group:
            raise ValueError("An item group needs a name.")

        group_key = group.casefold()

        if group_key in used_names:
            raise ValueError(f'Duplicate item group name: "{group}"')

        used_names.add(group_key)
        groups.append(group)

    return groups


def normalize_item_passage_method(value):
    requested_method = " ".join(
        str(value or "First recorded").strip().split()
    )

    for method in ITEM_PASSAGE_METHODS:
        if method.casefold() == requested_method.casefold():
            return method

    raise ValueError(
        "Item passage method must be First recorded, Crafted, Passed down, "
        "Inherited, Gifted, Purchased, Found, Taken, Lost, Destroyed, or "
        "Other."
    )


def normalize_item_passage(value):
    if not isinstance(value, dict):
        raise TypeError("An item passage entry must be an object.")

    normalized = deepcopy(value)
    normalized["record_id"] = str(
        normalized.get("record_id") or uuid.uuid4()
    ).strip()
    normalized["person_id"] = str(
        normalized.get("person_id", "") or ""
    ).strip()
    normalized["person_name"] = " ".join(
        str(normalized.get("person_name", "") or "").strip().split()
    )

    passage_date = str(normalized.get("date", "") or "").strip()
    normalized["date"] = (
        normalize_world_event_date(passage_date)
        if passage_date
        else ""
    )
    normalized["time"] = normalize_world_event_time(
        normalized.get("time")
    )
    normalized["method"] = normalize_item_passage_method(
        normalized.get("method")
    )
    normalized["note"] = str(
        normalized.get("note", "") or ""
    ).strip()
    normalized["source_event_id"] = str(
        normalized.get("source_event_id", "") or ""
    ).strip()
    return normalized


def normalize_item_passages(value):
    if value in (None, ""):
        candidate_passages = []
    elif isinstance(value, (list, tuple)):
        candidate_passages = list(value)
    else:
        raise TypeError("Item passage history must be a list.")

    normalized_passages = []
    used_record_ids = set()

    for candidate_passage in candidate_passages:
        passage = normalize_item_passage(candidate_passage)

        if passage["record_id"] in used_record_ids:
            raise ValueError(
                "Item passage record IDs must be unique within an item."
            )

        used_record_ids.add(passage["record_id"])
        normalized_passages.append(passage)

    return normalized_passages


def normalize_item_record(value):
    if not isinstance(value, dict):
        raise TypeError("An item must be an object.")

    normalized = deepcopy(value)
    normalized["record_id"] = str(
        normalized.get("record_id") or uuid.uuid4()
    ).strip()
    normalized["name"] = " ".join(
        str(normalized.get("name", "") or "").strip().split()
    )

    if not normalized["name"]:
        raise ValueError("An item needs a name.")

    normalized["category"] = normalize_item_category(
        normalized.get("category", DEFAULT_ITEM_CATEGORY)
    )
    normalized["group"] = normalize_item_group(
        normalized.get("group", "")
    )
    normalized["description"] = str(
        normalized.get("description", "") or ""
    ).strip()
    normalized["notes"] = str(
        normalized.get("notes", "") or ""
    ).strip()
    normalized["passage_history"] = normalize_item_passages(
        normalized.get("passage_history", [])
    )
    return normalized


def normalize_item_records(value):
    if value in (None, ""):
        candidate_items = []
    elif isinstance(value, (list, tuple)):
        candidate_items = list(value)
    else:
        raise TypeError("Items must be a list.")

    normalized_items = []
    used_record_ids = set()
    used_names = set()

    for candidate_item in candidate_items:
        item = normalize_item_record(candidate_item)
        item_id = item["record_id"]
        item_name = item["name"].casefold()

        if item_id in used_record_ids:
            raise ValueError(f"Duplicate items record_id: {item_id}")

        if item_name in used_names:
            raise ValueError(f"Duplicate item name: {item['name']}")

        used_record_ids.add(item_id)
        used_names.add(item_name)
        normalized_items.append(item)

    return normalized_items


def item_current_holder(item):
    passage_history = item_passages_in_date_order(item)

    if not passage_history:
        return {
            "person_id": "",
            "person_name": UNPOSSESSED_ITEM_HOLDER_LABEL,
        }

    current_holder = deepcopy(passage_history[-1])

    if not current_holder["person_id"] and not current_holder["person_name"]:
        current_holder["person_name"] = UNPOSSESSED_ITEM_HOLDER_LABEL

    return current_holder


def item_possessor_ids_on_date(item, date_value):
    requested_date = str(date_value or "").strip()

    if not requested_date:
        current_holder = item_current_holder(item)
        current_person_id = str(
            current_holder.get("person_id", "") or ""
        ).strip()
        return [current_person_id] if current_person_id else []

    normalized_date = normalize_world_event_date(requested_date)
    year, month, day = split_world_event_date(normalized_date)
    date_range_start = (
        int(year),
        int(month) if month else 1,
        int(day) if day else 1,
    )
    date_range_end = (
        int(year),
        int(month) if month else 12,
        int(day) if day else 31,
    )
    current_person_id = ""
    possessor_ids = []
    dated_passage_found = False
    passage_in_requested_range = False

    for passage in item_passages_in_date_order(item):
        if not passage["date"]:
            continue

        dated_passage_found = True
        passage_year, passage_month, passage_day = (
            split_world_event_date(passage["date"])
        )
        passage_date_range_start = (
            int(passage_year),
            int(passage_month) if passage_month else 1,
            int(passage_day) if passage_day else 1,
        )
        passage_date_range_end = (
            int(passage_year),
            int(passage_month) if passage_month else 12,
            int(passage_day) if passage_day else 31,
        )

        if passage_date_range_end < date_range_start:
            current_person_id = passage["person_id"]
            continue

        if passage_date_range_start > date_range_end:
            break

        passage_in_requested_range = True

        if (
            current_person_id
            and current_person_id not in possessor_ids
        ):
            possessor_ids.append(current_person_id)

        current_person_id = passage["person_id"]

        if (
            current_person_id
            and current_person_id not in possessor_ids
        ):
            possessor_ids.append(current_person_id)

    if (
        not passage_in_requested_range
        and current_person_id
        and current_person_id not in possessor_ids
    ):
        possessor_ids.append(current_person_id)

    if not dated_passage_found:
        current_holder = item_current_holder(item)
        current_person_id = str(
            current_holder.get("person_id", "") or ""
        ).strip()

        if current_person_id:
            possessor_ids.append(current_person_id)

    return possessor_ids


def item_is_linked_to_person(item, person_id):
    normalized_person_id = str(person_id or "").strip()

    if not normalized_person_id:
        return False

    return any(
        passage["person_id"] == normalized_person_id
        for passage in normalize_item_record(item)["passage_history"]
    )


def item_passage_sort_key(passage):
    return world_event_sort_key(
        {
            "date": passage["date"],
            "time": passage.get("time", ""),
            "title": passage["method"],
            "record_id": passage["record_id"],
        }
    )


def item_passages_in_date_order(item):
    normalized_item = normalize_item_record(item)
    passages = deepcopy(normalized_item["passage_history"])
    passages.sort(key=item_passage_sort_key)
    return passages


def item_possession_periods(item, person_id):
    normalized_person_id = str(person_id or "").strip()

    if not normalized_person_id:
        return []

    passages = item_passages_in_date_order(item)
    periods = []

    for index, passage in enumerate(passages):
        if passage["person_id"] != normalized_person_id:
            continue

        next_passage = (
            passages[index + 1]
            if index + 1 < len(passages)
            else None
        )
        acquired_date = format_line_item_date(
            passage["date"],
            unknown="Date unknown",
        )

        if passage.get("time"):
            acquired_date = f"{acquired_date} {passage['time']}"

        lost_date = (
            format_line_item_date(
                next_passage["date"],
                unknown="Date unknown",
            )
            if next_passage is not None
            else "present"
        )

        if next_passage is not None and next_passage.get("time"):
            lost_date = f"{lost_date} {next_passage['time']}"

        lost_method = (
            next_passage["method"]
            if next_passage is not None
            else "Still possessed"
        )

        if (
            next_passage is not None
            and next_passage["person_name"]
            and next_passage["method"]
            in ("Passed down", "Gifted", "Taken")
        ):
            relationship_word = (
                "by" if next_passage["method"] == "Taken" else "to"
            )
            lost_method = (
                f"{next_passage['method']} {relationship_word} "
                f"{next_passage['person_name']}"
            )
        periods.append(
            {
                "passage_id": passage["record_id"],
                "acquired_date": acquired_date,
                "lost_date": lost_date,
                "years": f"{acquired_date} - {lost_date}",
                "acquired_by": passage["method"],
                "lost_by": lost_method,
            }
        )

    return periods


def item_passage_rows(item):
    rows = []
    previous_holder_name = "—"

    for passage in item_passages_in_date_order(item):
        holder_name = (
            passage["person_name"]
            or UNPOSSESSED_ITEM_HOLDER_LABEL
        )
        passage_date = format_line_item_date(
            passage["date"],
            unknown="Date unknown",
        )

        if passage.get("time"):
            passage_date = f"{passage_date} {passage['time']}"

        rows.append(
            {
                "record_id": passage["record_id"],
                "date": passage_date,
                "from": previous_holder_name,
                "to": holder_name,
                "method": passage["method"],
                "note": passage["note"],
                "source_event_id": passage["source_event_id"],
            }
        )
        previous_holder_name = holder_name

    return rows
