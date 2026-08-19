"""Retire the duplicate Hogwarts location branch without losing event history."""

from __future__ import annotations

from headmasters_scroll.store import SharedJsonStore


HOGWARTS_ID = "e9cdd1f9-3e84-4408-b2c2-98ed4b3dabef"
CHAMBER_ID = "4da1c615-4a85-409e-8b09-fc51ac1f85d1"
CAMPUS_ID = "073329c7-a04f-4e4a-b2a9-f291b3ef4e04"
RETIRED_IDS = {HOGWARTS_ID, CHAMBER_ID}


def migrate_document(document: dict) -> dict[str, int]:
    document.setdefault("addresses", [])
    locations = document.get("locations", []) or []
    by_id = {
        str(item.get("record_id", "") or ""): item
        for item in locations
        if isinstance(item, dict)
    }
    if CAMPUS_ID not in by_id:
        raise RuntimeError("Campus of Hogwarts is missing; no changes were made")
    unexpected_children = [
        item for item in locations
        if isinstance(item, dict)
        and str(item.get("parent_location_id", "") or "") in RETIRED_IDS
        and str(item.get("record_id", "") or "") not in RETIRED_IDS
    ]
    if unexpected_children:
        names = ", ".join(str(item.get("name", "Unnamed")) for item in unexpected_children)
        raise RuntimeError(f"Unexpected locations still depend on the retired branch: {names}")

    document["locations"] = [
        item for item in locations
        if not isinstance(item, dict)
        or str(item.get("record_id", "") or "") not in RETIRED_IDS
    ]
    replacements = 0

    def replace(value, field_name: str = ""):
        nonlocal replacements
        if isinstance(value, dict):
            return {key: replace(child, key) for key, child in value.items()}
        if isinstance(value, list):
            normalized = [replace(child, field_name) for child in value]
            if field_name.endswith("_ids"):
                normalized = list(dict.fromkeys(normalized))
            return normalized
        if isinstance(value, str) and value in RETIRED_IDS:
            replacements += 1
            return CAMPUS_ID
        return value

    migrated = replace(document)
    document.clear()
    document.update(migrated)
    return {
        "removed_locations": len(RETIRED_IDS & set(by_id)),
        "redirected_references": replacements,
    }


def main() -> None:
    store = SharedJsonStore()
    session = store.load("world.json")
    report = migrate_document(session.data)
    outcome = store.save(session, "mapper")
    if not outcome.saved:
        raise RuntimeError("world.json changed concurrently; no migration was committed")
    print(
        f"Removed {report['removed_locations']} duplicate locations and redirected "
        f"{report['redirected_references']} references to Campus of Hogwarts."
    )


if __name__ == "__main__":
    main()
