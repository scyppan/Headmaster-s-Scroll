import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


APPLICATION_DIRECTORY = Path(__file__).resolve().parent.parent

if str(APPLICATION_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(APPLICATION_DIRECTORY))

from mage_maker.sections.names.history import migrate_legacy_name_details
from mage_maker.sections.family_tree.spouse_relationships import (
    empty_spouse_relationship,
)


TEXT_FIELD_MAP = {
    "Name": "displayed_name",
    "Narrative": "narrative",
    "School": "school",
    "Notes": "notes",
}
BOOLEAN_FIELD_MAP = {
    "Dead or permanently neutralized": "deceased",
    "Canon": "canon",
    "Player Character": "player_character",
}
NUMBER_FIELD_MAP = {
    "Birth Year": "birth_year",
    "Birth Month (value)": "birth_month",
    "Day": "birth_day",
}


def indexed_headers(headers):
    header_counts = Counter(headers)
    seen_counts = defaultdict(int)
    indexed = []

    for header in headers:
        seen_counts[header] += 1

        if header_counts[header] == 1:
            indexed.append(header)
        else:
            indexed.append(f"{header} [{seen_counts[header]}]")

    return indexed


def first_column_indexes(headers):
    indexes = {}

    for index, header in enumerate(headers):
        indexes.setdefault(header, index)

    return indexes


def parse_boolean(value):
    return str(value or "").strip().casefold() in ("yes", "true", "1")


def parse_number(value):
    cleaned = str(value or "").strip()

    if not cleaned:
        return None

    try:
        return int(cleaned)
    except ValueError:
        return None


def build_person(row, unique_headers, column_indexes, row_number):
    imported_fields = {
        unique_headers[index]: value
        for index, value in enumerate(row)
        if str(value).strip() and unique_headers[index] != "Upload character image"
    }
    person = {}

    for source_name, field_name in TEXT_FIELD_MAP.items():
        person[field_name] = str(row[column_indexes[source_name]] or "").strip()

    for source_name, field_name in BOOLEAN_FIELD_MAP.items():
        person[field_name] = parse_boolean(row[column_indexes[source_name]])

    for source_name, field_name in NUMBER_FIELD_MAP.items():
        person[field_name] = parse_number(row[column_indexes[source_name]])

    person["non_magical"] = parse_boolean(row[column_indexes["Muggle"]]) or parse_boolean(
        row[column_indexes["Squib"]]
    )
    person["can_give_birth"] = False
    person["biological_mother_id"] = ""
    person["biological_father_id"] = ""
    person["biological_mother_status"] = "unknown"
    person["biological_father_status"] = "unknown"
    person["mate_ids"] = []
    person["spouse_relationships"] = []
    person["timeline_events"] = []
    person["_biological_mother_name"] = str(
        row[column_indexes["Biological Mother"]] or ""
    ).strip()
    person["_biological_father_name"] = str(
        row[column_indexes["Biological Father"]] or ""
    ).strip()

    source_id = str(row[column_indexes["ID"]] or "").strip()
    source_key = str(row[column_indexes["Key"]] or "").strip()
    person["record_id"] = f"formidable-{source_id or source_key or row_number}"
    maiden_name = str(row[column_indexes["Maiden Name"]] or "").strip()
    nickname_alias = str(row[column_indexes["Nickname/Alias"]] or "").strip()
    person["name_details"] = migrate_legacy_name_details(
        {
            "name_history": "",
            "aliases": nickname_alias,
            "sobriquets": "",
            "name_changes": f"Maiden name: {maiden_name}" if maiden_name else "",
            "notes": "",
        },
        person["displayed_name"],
        person["record_id"],
    )
    person["created_at"] = str(row[column_indexes["Timestamp"]] or "").strip()
    person["last_updated"] = str(row[column_indexes["Last Updated"]] or "").strip()
    person["source_id"] = source_id
    person["source_key"] = source_key
    person["imported_fields"] = imported_fields

    return person


def convert_csv(input_path, output_path):
    input_file_path = Path(input_path)
    output_file_path = Path(output_path)

    with input_file_path.open("r", encoding="utf-8-sig", newline="") as input_file:
        rows = list(csv.reader(input_file))

    if not rows:
        raise ValueError("The CSV file is empty.")

    headers = rows[0]
    unique_headers = indexed_headers(headers)
    column_indexes = first_column_indexes(headers)
    required_headers = set(TEXT_FIELD_MAP)
    required_headers.update(BOOLEAN_FIELD_MAP)
    required_headers.update(NUMBER_FIELD_MAP)
    required_headers.update(
        (
            "ID",
            "Key",
            "Timestamp",
            "Last Updated",
            "Maiden Name",
            "Nickname/Alias",
            "Biological Mother",
            "Biological Father",
            "Muggle",
            "Squib",
        )
    )
    missing_headers = sorted(required_headers.difference(column_indexes))

    if missing_headers:
        raise ValueError("Missing CSV columns: " + ", ".join(missing_headers))

    people = []

    for row_number, row in enumerate(rows[1:], start=2):
        if len(row) != len(headers):
            raise ValueError(
                f"CSV row {row_number} has {len(row)} values; expected {len(headers)}."
            )

        people.append(build_person(row, unique_headers, column_indexes, row_number))

    ids_by_name = {
        person["displayed_name"].casefold(): person["record_id"]
        for person in people
        if person["displayed_name"]
    }
    inferred_mother_ids = set()

    for person in people:
        mother_name = person.pop("_biological_mother_name")
        father_name = person.pop("_biological_father_name")
        mother_id = ids_by_name.get(mother_name.casefold(), "") if mother_name else ""
        father_id = ids_by_name.get(father_name.casefold(), "") if father_name else ""
        person["biological_mother_id"] = mother_id
        person["biological_father_id"] = father_id
        person["biological_mother_status"] = "person" if mother_id else "unknown"
        person["biological_father_status"] = "person" if father_id else "unknown"

        if mother_id:
            inferred_mother_ids.add(mother_id)

    for person in people:
        if person["record_id"] in inferred_mother_ids:
            person["can_give_birth"] = True

        mother_id = person["biological_mother_id"]
        father_id = person["biological_father_id"]

        if not mother_id or not father_id or mother_id == father_id:
            continue

        mother = next(
            candidate
            for candidate in people
            if candidate["record_id"] == mother_id
        )
        father = next(
            candidate
            for candidate in people
            if candidate["record_id"] == father_id
        )

        if father_id not in mother["mate_ids"]:
            mother["mate_ids"].append(father_id)
            mother["spouse_relationships"].append(
                empty_spouse_relationship(father_id)
            )

        if mother_id not in father["mate_ids"]:
            father["mate_ids"].append(mother_id)
            father["spouse_relationships"].append(
                empty_spouse_relationship(mother_id)
            )

    people.sort(
        key=lambda person: (
            person.get("birth_year") if person.get("birth_year") is not None else 10000,
            person.get("birth_month") if person.get("birth_month") is not None else 13,
            person.get("birth_day") if person.get("birth_day") is not None else 32,
            person.get("displayed_name", "").casefold(),
        )
    )
    database = {
        "_database": {
            "schema_version": 8,
            "database_version": "0.8.0",
            "source_file": input_file_path.name,
            "imported_at": datetime.now(timezone.utc).isoformat(),
            "last_saved": None,
        },
        "people": people,
    }
    output_file_path.parent.mkdir(parents=True, exist_ok=True)

    with output_file_path.open("w", encoding="utf-8", newline="\n") as output_file:
        json.dump(database, output_file, ensure_ascii=False, indent=2)
        output_file.write("\n")

    return len(people)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Convert a Formidable character CSV export into Mage Maker JSON."
    )
    parser.add_argument("input_csv")
    parser.add_argument("output_json")
    arguments = parser.parse_args()
    imported_count = convert_csv(arguments.input_csv, arguments.output_json)
    print(f"Imported {imported_count} people into {arguments.output_json}")
