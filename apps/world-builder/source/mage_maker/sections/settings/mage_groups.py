import re
from copy import deepcopy


MAGE_GROUPS_SETTING_KEY = "mage_groups"
DEFAULT_MAGE_GROUP_ID = "unassigned"
DEFAULT_MAGE_GROUP_NAME = "Unassigned"
DEFAULT_MAGE_GROUP_COLOR = "#8A738F"
MAGE_GROUP_COLOR_PALETTE = (
    "#8A738F",
    "#2F6F8F",
    "#3F7D58",
    "#A05A2C",
    "#8B4F73",
    "#6C63A8",
    "#A47C1B",
    "#3B7F7A",
)


def default_mage_groups():
    return [
        {
            "group_id": DEFAULT_MAGE_GROUP_ID,
            "name": DEFAULT_MAGE_GROUP_NAME,
            "color": DEFAULT_MAGE_GROUP_COLOR,
        }
    ]


def normalize_mage_group_name(value):
    name = " ".join(str(value or "").strip().split())

    if not name:
        raise ValueError("A mage group needs a name.")

    if len(name) > 80:
        raise ValueError("A mage group name cannot exceed 80 characters.")

    return name


def normalize_mage_group_color(value):
    color = str(value or "").strip().upper()

    if not re.fullmatch(r"#[0-9A-F]{6}", color):
        raise ValueError(
            "A mage group color must use the format #RRGGBB."
        )

    return color


def normalize_mage_groups(value):
    if value in (None, ""):
        return default_mage_groups()

    if not isinstance(value, list):
        raise TypeError("Mage groups must be stored as a list.")

    normalized_groups = []
    seen_ids = set()
    seen_names = set()

    for group in value:
        if not isinstance(group, dict):
            raise TypeError("Every mage group must be an object.")

        group_id = str(group.get("group_id", "") or "").strip()

        if not group_id:
            raise ValueError("Every mage group needs a group_id.")

        if group_id in seen_ids:
            raise ValueError(f"Duplicate mage group_id: {group_id}")

        name = normalize_mage_group_name(group.get("name"))
        normalized_name = name.casefold()

        if normalized_name in seen_names:
            raise ValueError(f'Duplicate mage group name: "{name}"')

        normalized_groups.append(
            {
                "group_id": group_id,
                "name": name,
                "color": normalize_mage_group_color(
                    group.get("color")
                ),
            }
        )
        seen_ids.add(group_id)
        seen_names.add(normalized_name)

    if DEFAULT_MAGE_GROUP_ID not in seen_ids:
        normalized_groups.insert(0, default_mage_groups()[0])

    return normalized_groups


def default_mage_group_id(groups):
    normalized_groups = normalize_mage_groups(groups)

    for group in normalized_groups:
        if group["group_id"] == DEFAULT_MAGE_GROUP_ID:
            return DEFAULT_MAGE_GROUP_ID

    return normalized_groups[0]["group_id"]


def normalize_mage_group_id(value, groups):
    normalized_group_id = str(value or "").strip()
    normalized_groups = normalize_mage_groups(groups)
    available_ids = {
        group["group_id"]
        for group in normalized_groups
    }

    if normalized_group_id in available_ids:
        return normalized_group_id

    return default_mage_group_id(normalized_groups)


def require_mage_group_id(value, groups):
    normalized_group_id = str(value or "").strip()
    normalized_groups = normalize_mage_groups(groups)
    available_ids = {
        group["group_id"]
        for group in normalized_groups
    }

    if normalized_group_id not in available_ids:
        raise ValueError(
            "Every magician must belong to an existing mage group."
        )

    return normalized_group_id


def mage_group_definition(group_id, groups):
    normalized_group_id = normalize_mage_group_id(group_id, groups)

    for group in normalize_mage_groups(groups):
        if group["group_id"] == normalized_group_id:
            return deepcopy(group)

    return deepcopy(default_mage_groups()[0])


def next_mage_group_color(groups):
    normalized_groups = normalize_mage_groups(groups)
    used_colors = {
        group["color"]
        for group in normalized_groups
    }

    for color in MAGE_GROUP_COLOR_PALETTE:
        if color not in used_colors:
            return color

    return MAGE_GROUP_COLOR_PALETTE[
        len(normalized_groups) % len(MAGE_GROUP_COLOR_PALETTE)
    ]


def contrasting_text_color(color):
    normalized_color = normalize_mage_group_color(color)
    red = int(normalized_color[1:3], 16)
    green = int(normalized_color[3:5], 16)
    blue = int(normalized_color[5:7], 16)
    luminance = (
        (red * 299)
        + (green * 587)
        + (blue * 114)
    ) / 1000

    return "#2B1D31" if luminance >= 160 else "#FFFFFF"
