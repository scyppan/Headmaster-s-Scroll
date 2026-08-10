from database.name_links import ensure_unique_record_name
from sections.nature_and_alchemy.creatures.constants import (
    PROFICIENCY_DEFAULTS,
)


class PlantController:
    collection_name = "plants"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        complete_values = {
            "name": "",
            "description": "",
            "parts": [],
            "tags": [],
            "dbnotes": "",
            **record_values,
        }
        self.validate_record_values(complete_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            complete_values.get("name", ""),
            record_label="plant",
        )
        created_record = self.database.create(
            self.collection_name,
            complete_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        self.validate_record_values(record_values)

        if "name" in record_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                record_values["name"],
                record_id=record_id,
                record_label="plant",
            )

        updated_record = self.database.update(
            self.collection_name,
            record_id,
            record_values,
        )
        self.database.save()

        return updated_record

    def delete_record(self, record_id):
        deleted_record = self.database.delete(
            self.collection_name,
            record_id,
        )
        self.database.save()

        return deleted_record

    def validate_record_values(self, record_values):
        if not isinstance(record_values, dict):
            raise TypeError("Plant values must be structured")

        if "name" in record_values and not isinstance(
            record_values["name"],
            str,
        ):
            raise TypeError("Plant name must be text")

        for field_name, field_label in (
            ("description", "Description"),
            ("dbnotes", "DB Notes"),
        ):
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"{field_label} must be text")

        if "parts" in record_values:
            self.validate_parts(record_values["parts"])

        if "tags" in record_values:
            self.validate_tags(record_values["tags"])

    def validate_parts(self, parts):
        if not isinstance(parts, list):
            raise TypeError("Plant parts must be a list")

        proficiency_names = {
            str(record.get("name", "")).strip()
            for record in self.database.get_collection("proficiencies")
            if str(record.get("name", "")).strip()
        }
        allowed_proficiencies = {
            *PROFICIENCY_DEFAULTS,
            *proficiency_names,
        }
        normalized_part_names = set()

        for part in parts:
            if not isinstance(part, dict):
                raise TypeError("Every plant part must be structured")

            part_name = str(part.get("name", "")).strip()

            if not part_name:
                raise ValueError("Every plant part must have a name")

            normalized_name = " ".join(part_name.split()).casefold()

            if normalized_name in normalized_part_names:
                raise ValueError(f"Duplicate plant part: {part_name}")

            normalized_part_names.add(normalized_name)
            required_proficiency = part.get("required_proficiency", "No")

            if required_proficiency not in allowed_proficiencies:
                raise ValueError(
                    f"Unknown proficiency for {part_name}: "
                    f"{required_proficiency}"
                )

            for field_name, field_label in (
                ("description", "Description"),
                ("raw_effects", "Raw Effects"),
                ("effect_in_potions", "Effect in Potions"),
            ):
                field_value = part.get(field_name, "")

                if not isinstance(field_value, str):
                    raise TypeError(
                        f"{part_name} {field_label} must be text"
                    )

    def validate_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Tags must be a list")

        normalized_tags = set()

        for tag in tags:
            tag_text = str(tag).strip()

            if not tag_text:
                raise ValueError("Tags cannot be blank")

            normalized_tag = " ".join(tag_text.split()).casefold()

            if normalized_tag in normalized_tags:
                raise ValueError(f"Duplicate tag: {tag_text}")

            normalized_tags.add(normalized_tag)

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
