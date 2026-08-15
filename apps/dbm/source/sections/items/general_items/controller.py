from database.name_links import ensure_unique_record_name
from sections.items.general_items.constants import (
    GENERAL_ITEM_TYPES,
    GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME,
)
from shared.item_assets import normalize_item_image_reference
from shared.bonus_records import (
    normalize_bonus_record_values,
    validate_bonus_record_values,
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

    def extraction_methods(self):
        return [
            {
                "record_id": str(record.get("record_id", "")),
                "name": str(record.get("name", "") or ""),
            }
            for record in self.database.get_collection("gathering_methods")
            if record.get("record_id") and record.get("name")
        ]

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
        normalized_values = normalize_bonus_record_values(record_values)

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

        if "image_asset" in normalized_values:
            normalized_values["image_asset"] = normalize_item_image_reference(
                normalized_values.get("image_asset")
            )

        if "extraction_method_id" in normalized_values:
            method_id = str(
                normalized_values.get("extraction_method_id", "") or ""
            ).strip()
            normalized_values["extraction_method_id"] = method_id
            normalized_values["gathering_method_ids"] = (
                [method_id] if method_id else []
            )

        if "flight_threshold" in normalized_values:
            raw_threshold = normalized_values.get("flight_threshold", "")
            normalized_values["flight_threshold"] = (
                int(raw_threshold) if str(raw_threshold).strip() else None
            )

        if normalized_values.get("type") in {"Broom", "Flyable"}:
            normalized_values["activation_mode"] = "equipped"
            normalized_values["equipment_slot_type"] = "flyable"

        return normalized_values

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A general item must have a name.")

        if record_values.get("type", "") not in GENERAL_ITEM_TYPES:
            raise ValueError("A general item must use a defined type.")

        extraction_method_id = str(
            record_values.get("extraction_method_id", "") or ""
        ).strip()
        if record_values.get("type") == "Alchemical":
            if not extraction_method_id:
                raise ValueError(
                    "An alchemical item must select an extraction method."
                )
            known_method_ids = {
                str(record.get("record_id", ""))
                for record in self.database.get_collection(
                    "gathering_methods"
                )
            }
            if extraction_method_id not in known_method_ids:
                raise ValueError(
                    "The selected extraction method no longer exists."
                )

        if record_values.get("type") in {"Broom", "Flyable"}:
            try:
                threshold = int(record_values.get("flight_threshold"))
            except (TypeError, ValueError) as error:
                raise ValueError(
                    "A flyable item must have a Flying threshold."
                ) from error
            if threshold < 1 or threshold > 100:
                raise ValueError(
                    "A flyable item's Flying threshold must be between 1 and 100."
                )

        validate_bonus_record_values(record_values)

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
