from copy import deepcopy
from uuid import NAMESPACE_URL, uuid4, uuid5

from mage_maker.core.dates import normalize_partial_date


NAME_ENTRY_FIELDS = (
    "name_type",
    "name_entry",
    "date",
    "note",
)

NAME_TYPES = (
    "nickname",
    "sobriquet",
    "alias",
    "maiden name",
    "married name",
    "birth name",
    "name change",
)


def empty_name_details():
    return {"entries": []}


def new_name_entry():
    return {
        "entry_id": str(uuid4()),
        "name_type": "",
        "name_entry": "",
        "date": "",
        "note": "",
    }


def normalize_name_entry(entry):
    if not isinstance(entry, dict):
        raise TypeError("Every name history entry must be a collection of fields.")

    normalized = {
        field_name: str(entry.get(field_name, "") or "").strip()
        for field_name in NAME_ENTRY_FIELDS
    }
    normalized["date"] = normalize_partial_date(
        normalized["date"],
        "Name date",
    )
    normalized["entry_id"] = str(entry.get("entry_id", "") or "").strip()

    if not normalized["entry_id"]:
        normalized["entry_id"] = str(uuid4())

    if not normalized["name_type"]:
        raise ValueError("Name type is required.")

    if not normalized["name_entry"]:
        raise ValueError("Name entry is required.")

    return normalized


def normalize_name_details(name_details):
    if not isinstance(name_details, dict):
        raise TypeError("Name details must be a collection of name history entries.")

    entries = name_details.get("entries", [])

    if not isinstance(entries, list):
        raise TypeError("Name history entries must be a list.")

    normalized_entries = [normalize_name_entry(entry) for entry in entries]
    seen_entry_ids = set()
    birth_name_count = 0

    for entry in normalized_entries:
        entry_id = entry["entry_id"]
        normalized_name_type = " ".join(
            str(entry.get("name_type", "") or "")
            .strip()
            .casefold()
            .split()
        )

        if normalized_name_type in ("birth name", "birthname"):
            birth_name_count += 1

        if entry_id in seen_entry_ids:
            entry["entry_id"] = str(uuid4())

        seen_entry_ids.add(entry["entry_id"])

    if birth_name_count > 1:
        raise ValueError("Only one Birth name is allowed.")

    return {"entries": normalized_entries}


def birth_name_entry(name_details):
    entries = (
        name_details.get("entries", [])
        if isinstance(name_details, dict)
        else []
    )

    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict):
            continue

        name_type = " ".join(
            str(entry.get("name_type", "") or "").strip().casefold().split()
        )

        if name_type in ("birth name", "birthname"):
            return deepcopy(entry)

    return None


def synchronize_birth_name_date(name_details, birth_date):
    synchronized_details = normalize_name_details(name_details)
    normalized_birth_date = normalize_partial_date(
        str(birth_date or "").strip(),
        "Birth date",
    )

    for entry in synchronized_details["entries"]:
        name_type = " ".join(
            str(entry.get("name_type", "") or "")
            .strip()
            .casefold()
            .split()
        )

        if name_type in ("birth name", "birthname"):
            entry["date"] = normalized_birth_date

    return synchronized_details


def legacy_entry_id(record_id, ordinal, name_type, name_entry):
    identity = f"mage-maker:{record_id}:{ordinal}:{name_type}:{name_entry}"
    return str(uuid5(NAMESPACE_URL, identity))


def legacy_lines(value):
    return [line.strip() for line in str(value or "").splitlines() if line.strip()]


def append_legacy_entry(entries, record_id, name_type, name_entry, note=""):
    ordinal = len(entries)
    entries.append(
        {
            "entry_id": legacy_entry_id(
                record_id,
                ordinal,
                name_type,
                name_entry,
            ),
            "name_type": name_type,
            "name_entry": name_entry,
            "date": "",
            "note": note,
        }
    )


def migrate_legacy_name_details(name_details, displayed_name="", record_id=""):
    if not isinstance(name_details, dict):
        return empty_name_details()

    if isinstance(name_details.get("entries"), list):
        return normalize_name_details(deepcopy(name_details))

    entries = []

    for alias in legacy_lines(name_details.get("aliases")):
        append_legacy_entry(entries, record_id, "Alias", alias)

    for sobriquet in legacy_lines(name_details.get("sobriquets")):
        append_legacy_entry(entries, record_id, "Sobriquet", sobriquet)

    for historical_name in legacy_lines(name_details.get("name_history")):
        append_legacy_entry(
            entries,
            record_id,
            "Historical name",
            historical_name,
        )

    for name_change in legacy_lines(name_details.get("name_changes")):
        prefix, separator, remaining_text = name_change.partition(":")

        if separator and prefix.strip().casefold() == "maiden name":
            append_legacy_entry(
                entries,
                record_id,
                "Maiden name",
                remaining_text.strip(),
            )
        else:
            append_legacy_entry(
                entries,
                record_id,
                "Name change",
                name_change,
            )

    legacy_note = str(name_details.get("notes", "") or "").strip()

    if legacy_note:
        append_legacy_entry(
            entries,
            record_id,
            "Name note",
            str(displayed_name or "Unspecified name").strip(),
            legacy_note,
        )

    return {"entries": entries}
