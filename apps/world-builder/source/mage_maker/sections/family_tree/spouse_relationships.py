from copy import deepcopy

from mage_maker.core.dates import normalize_date_parts


SPOUSE_DATE_PREFIXES = ("marriage", "divorce")


def empty_spouse_relationship(person_id=""):
    return {
        "person_id": str(person_id or "").strip(),
        "married": False,
        "marriage_year": None,
        "marriage_month": None,
        "marriage_day": None,
        "divorced": False,
        "divorce_year": None,
        "divorce_month": None,
        "divorce_day": None,
    }


def normalize_spouse_relationships(relationships):
    if relationships in (None, ""):
        return []

    if not isinstance(relationships, list):
        raise TypeError("Spouse relationships must be a list.")

    normalized_relationships = []
    seen_ids = set()

    for relationship in relationships:
        if not isinstance(relationship, dict):
            raise TypeError("Every spouse relationship must be an object.")

        normalized = empty_spouse_relationship(relationship.get("person_id"))
        person_id = normalized["person_id"]

        if not person_id or person_id in seen_ids:
            continue

        normalized["married"] = normalize_relationship_boolean(
            relationship.get("married")
        )
        normalized["divorced"] = normalize_relationship_boolean(
            relationship.get("divorced")
        )

        for prefix in SPOUSE_DATE_PREFIXES:
            year, month, day = normalize_date_parts(
                relationship.get(f"{prefix}_year"),
                relationship.get(f"{prefix}_month"),
                relationship.get(f"{prefix}_day"),
                prefix.title(),
            )
            normalized[f"{prefix}_year"] = year
            normalized[f"{prefix}_month"] = month
            normalized[f"{prefix}_day"] = day

        if not normalized["married"]:
            normalized["marriage_year"] = None
            normalized["marriage_month"] = None
            normalized["marriage_day"] = None

        if not normalized["divorced"]:
            normalized["divorce_year"] = None
            normalized["divorce_month"] = None
            normalized["divorce_day"] = None

        if normalized["divorced"] and not normalized["married"]:
            raise ValueError("A divorced relationship must also be marked married.")

        normalized_relationships.append(normalized)
        seen_ids.add(person_id)

    return normalized_relationships


def normalize_relationship_boolean(value):
    if isinstance(value, bool):
        return value

    return str(value or "").strip().casefold() in ("yes", "true", "1")


def relationship_ids(relationships):
    return [
        relationship["person_id"]
        for relationship in normalize_spouse_relationships(relationships)
    ]


def merge_mate_ids(relationships, mate_ids):
    normalized = normalize_spouse_relationships(relationships)
    records_by_id = {
        relationship["person_id"]: deepcopy(relationship)
        for relationship in normalized
    }
    merged = []

    for mate_id in mate_ids or []:
        person_id = str(mate_id or "").strip()

        if not person_id or person_id in {item["person_id"] for item in merged}:
            continue

        merged.append(records_by_id.get(person_id, empty_spouse_relationship(person_id)))

    return merged


def reciprocal_relationship(relationship, person_id):
    reciprocal = deepcopy(relationship)
    reciprocal["person_id"] = str(person_id or "").strip()
    return reciprocal
