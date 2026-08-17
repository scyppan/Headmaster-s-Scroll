from database.name_links import ensure_unique_record_name
from headmasters_scroll.effects import (
    normalize_in_flight_effects,
    validate_in_flight_effects,
)
from sections.items.general_items.constants import (
    GENERAL_ITEM_TYPES,
    GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME,
)
from shared.item_assets import normalize_item_image_reference
from shared.item_actions import normalize_item_actions, validate_item_actions
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
        try:
            self.database.save()
        except Exception:
            # A shared-file conflict, transient Windows lock, or failed atomic
            # replacement must not leave a record that only exists in memory.
            # Reloading also refreshes the shared-data base revision so the
            # unchanged form can be saved again immediately.
            self.database.discard_unsaved_changes()
            raise

        return created_record

    def update_record(self, record_id, record_values):
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown general item record ID: {record_id}")

        prospective_record = dict(current_record)
        prospective_record.update(record_values)
        normalized_values = self.normalize_record_values(prospective_record)
        self.validate_record_values(normalized_values)

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
        normalized_values.pop("extraction_method_id", None)
        normalized_values.setdefault("base_knuts", 0)
        normalized_values.setdefault("actions", [])
        normalized_values.setdefault("activation_mode", "passive")
        normalized_values.setdefault("equipment_slot_type", "")
        normalized_values["tags"] = [
            " ".join(str(tag).split())
            for tag in normalized_values.get("tags", []) or []
            if str(tag).strip()
        ]

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

        if "actions" in normalized_values:
            normalized_values["actions"] = normalize_item_actions(
                normalized_values.get("actions")
            )

        if "flight_threshold" in normalized_values:
            raw_threshold = normalized_values.get("flight_threshold", "")
            normalized_values["flight_threshold"] = (
                int(raw_threshold) if str(raw_threshold).strip() else None
            )

        if "base_knuts" in normalized_values:
            raw_base_knuts = normalized_values.get("base_knuts", "")
            try:
                normalized_values["base_knuts"] = int(raw_base_knuts)
            except (TypeError, ValueError) as error:
                raise ValueError("Base Knuts must be a whole number.") from error

        if normalized_values.get("type") in {"Broom", "Flyable"}:
            normalized_values["activation_mode"] = "equipped"
            normalized_values["equipment_slot_type"] = "flyable"
            legacy_effects = normalized_values.get("bonuses", []) or []
            effects = normalized_values.get("in_flight_effects")
            if effects is None:
                effects = legacy_effects
            normalized_values["in_flight_effects"] = (
                normalize_in_flight_effects(effects)
            )
            # Flyables never use the ordinary item bonus/action channels.
            normalized_values["bonuses"] = []
            normalized_values["actions"] = []
        else:
            normalized_values["in_flight_effects"] = []

        if normalized_values.get("type") == "Raw Material":
            method_id = str(
                normalized_values.get("searching_method_id", "") or ""
            ).strip()
            normalized_values["searching_method_id"] = method_id
            normalized_values["gathering_method_ids"] = (
                [method_id] if method_id else []
            )
        else:
            normalized_values.pop("searching_method_id", None)
            normalized_values.pop("gathering_method_ids", None)

        return normalized_values

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A general item must have a name.")

        if record_values.get("type", "") not in GENERAL_ITEM_TYPES:
            raise ValueError("A general item must use a defined type.")

        base_knuts = record_values.get("base_knuts", 0)
        if not isinstance(base_knuts, int) or isinstance(base_knuts, bool):
            raise ValueError("Base Knuts must be a whole number.")
        if base_knuts < 0:
            raise ValueError("Base Knuts cannot be negative.")

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
            validate_in_flight_effects(
                record_values.get("in_flight_effects", [])
            )
            if record_values.get("bonuses") or record_values.get("actions"):
                raise ValueError(
                    "Flyables use only In-flight effects, not regular bonuses "
                    "or item effects."
                )

        if record_values.get("type") == "Raw Material":
            method_id = str(
                record_values.get("searching_method_id", "") or ""
            ).strip()
            if not method_id:
                raise ValueError("A Raw Material must select a Searching Method.")
            valid_method_ids = {
                str(record.get("record_id", ""))
                for record in self.database.get_collection("gathering_methods")
                if isinstance(record, dict)
            }
            if method_id not in valid_method_ids:
                raise ValueError("The selected Searching Method no longer exists.")

        if record_values.get("type") not in {"Broom", "Flyable"}:
            validate_bonus_record_values(record_values)
            validate_item_actions(record_values.get("actions", []), self.database)
        tags = record_values.get("tags", [])
        if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
            raise ValueError("General item tags must be a list of text values.")

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
