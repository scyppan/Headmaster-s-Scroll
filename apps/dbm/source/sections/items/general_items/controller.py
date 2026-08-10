from database.name_links import ensure_unique_record_name
from sections.items.general_items.constants import (
    GENERAL_ITEM_TYPES,
    GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME,
)


class GeneralItemController:
    collection_name = "general_items"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        normalized_values = self.normalize_record_values(record_values)
        self.validate_record_values(normalized_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            normalized_values.get("name", ""),
            record_label="general item",
        )
        created_record = self.database.create(
            self.collection_name,
            normalized_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        normalized_values = self.normalize_record_values(record_values)
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown general item record ID: {record_id}")

        prospective_record = dict(current_record)
        prospective_record.update(normalized_values)
        self.validate_record_values(prospective_record)

        if "name" in normalized_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                normalized_values["name"],
                record_id=record_id,
                record_label="general item",
            )

        updated_record = self.database.update(
            self.collection_name,
            record_id,
            normalized_values,
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

    def normalize_record_values(self, record_values):
        normalized_values = dict(record_values)

        if "name" in normalized_values:
            normalized_values["name"] = " ".join(
                str(normalized_values["name"] or "").split()
            )

        if "type" in normalized_values:
            normalized_type = " ".join(
                str(normalized_values["type"] or "").split()
            ).casefold()
            normalized_values["type"] = (
                GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME.get(
                    normalized_type,
                    " ".join(str(normalized_values["type"] or "").split()),
                )
            )

        return normalized_values

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A general item must have a name.")

        if record_values.get("type", "") not in GENERAL_ITEM_TYPES:
            raise ValueError("A general item must use a defined type.")

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
