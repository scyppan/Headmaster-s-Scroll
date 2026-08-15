from database.name_links import ensure_unique_record_name
from shared.item_assets import normalize_item_image_reference
from shared.bonus_records import (
    normalize_bonus_record_values,
    validate_bonus_record_values,
)


class AccessoryController:
    collection_name = "accessories"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        record_values = self.normalize_record_values(record_values)
        validate_bonus_record_values(record_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            record_values.get("name", ""),
            record_label="accessory",
        )
        created_record = self.database.create(
            self.collection_name,
            record_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        record_values = self.normalize_record_values(record_values)
        validate_bonus_record_values(record_values)
        if "name" in record_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                record_values["name"],
                record_id=record_id,
                record_label="accessory",
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

    def normalize_record_values(self, record_values):
        normalized_values = normalize_bonus_record_values(record_values)
        if "image_asset" in normalized_values:
            normalized_values["image_asset"] = normalize_item_image_reference(
                normalized_values.get("image_asset")
            )
        return normalized_values

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
