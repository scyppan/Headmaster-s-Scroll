from database.name_links import ensure_unique_record_name
from shared.item_assets import normalize_item_image_reference
from shared.item_actions import normalize_item_actions, validate_item_actions
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
        self.validate_record_values(record_values)
        validate_bonus_record_values(record_values)
        validate_item_actions(record_values.get("actions", []), self.database)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            record_values.get("name", ""),
            record_label="accessory",
        )
        created_record = self.database.create(
            self.collection_name,
            record_values,
        )
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise

        return created_record

    def update_record(self, record_id, record_values):
        record_values = self.normalize_record_values(record_values)
        current_record = self.get_record(record_id)
        if current_record is None:
            raise KeyError(f"Unknown accessory record ID: {record_id}")
        prospective_record = dict(current_record)
        prospective_record.update(record_values)
        self.validate_record_values(prospective_record)
        validate_bonus_record_values(prospective_record)
        validate_item_actions(prospective_record.get("actions", []), self.database)
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
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise

        return updated_record

    def delete_record(self, record_id):
        deleted_record = self.database.delete(
            self.collection_name,
            record_id,
        )
        try:
            self.database.save()
        except Exception:
            self.database.discard_unsaved_changes()
            raise

        return deleted_record

    def normalize_record_values(self, record_values):
        normalized_values = normalize_bonus_record_values(record_values)
        normalized_values.setdefault("base_knuts", 0)
        normalized_values.setdefault("actions", [])
        normalized_values.setdefault("activation_mode", "equipped")
        normalized_values.setdefault("equipment_slot_type", "accessory")
        if "base_knuts" in normalized_values:
            try:
                normalized_values["base_knuts"] = int(
                    normalized_values.get("base_knuts", "")
                )
            except (TypeError, ValueError) as error:
                raise ValueError("Base Knuts must be a whole number.") from error
        if "image_asset" in normalized_values:
            normalized_values["image_asset"] = normalize_item_image_reference(
                normalized_values.get("image_asset")
            )
        if "actions" in normalized_values:
            normalized_values["actions"] = normalize_item_actions(
                normalized_values.get("actions")
            )
        return normalized_values

    def validate_record_values(self, record_values):
        base_knuts = record_values.get("base_knuts", 0)
        if not isinstance(base_knuts, int) or isinstance(base_knuts, bool):
            raise ValueError("Base Knuts must be a whole number.")
        if base_knuts < 0:
            raise ValueError("Base Knuts cannot be negative.")

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
