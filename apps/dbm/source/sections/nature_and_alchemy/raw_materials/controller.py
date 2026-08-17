from copy import deepcopy

from database.name_links import ensure_unique_record_name
from shared.item_assets import normalize_item_image_reference


class RawMaterialController:
    collection_name = "raw_materials"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        return sorted(
            self.database.get_collection(self.collection_name),
            key=lambda record: (
                str(record.get("name", "")).casefold(),
                str(record.get("record_id", "")),
            ),
        )

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def searching_methods(self):
        return sorted(
            self.database.get_collection("gathering_methods"),
            key=lambda record: str(record.get("name", "")).casefold(),
        )

    def create_record(self, values):
        normalized = self.normalize(values)
        self.validate(normalized)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            normalized["name"],
            record_label="raw material",
        )
        record = self.database.create(self.collection_name, normalized)
        self.database.save()
        return record

    def update_record(self, record_id, values):
        normalized = self.normalize(values)
        current = self.get_record(record_id)
        if current is None:
            raise KeyError(f"Unknown raw material record ID: {record_id}")
        prospective = deepcopy(current)
        prospective.update(normalized)
        self.validate(prospective)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            prospective["name"],
            record_id=record_id,
            record_label="raw material",
        )
        record = self.database.update(
            self.collection_name,
            record_id,
            normalized,
        )
        self.database.save()
        return record

    def delete_record(self, record_id):
        record = self.database.delete(self.collection_name, record_id)
        self.database.save()
        return record

    def normalize(self, values):
        normalized = deepcopy(values)
        normalized["name"] = " ".join(
            str(normalized.get("name", "") or "").split()
        )
        normalized["category"] = " ".join(
            str(normalized.get("category", "") or "").split()
        )
        method_id = str(
            normalized.get("searching_method_id", "") or ""
        ).strip()
        normalized["searching_method_id"] = method_id
        # Established storage name retained for Game Board compatibility.
        normalized["gathering_method_ids"] = [method_id] if method_id else []
        normalized["base_knuts"] = int(normalized.get("base_knuts", 0) or 0)
        normalized["default_source_quantity"] = int(
            normalized.get("default_source_quantity", 1) or 1
        )
        normalized["default_stock_quantity"] = normalized[
            "default_source_quantity"
        ]
        normalized["description"] = str(
            normalized.get("description", "") or ""
        ).strip()
        normalized["dbnotes"] = str(
            normalized.get("dbnotes", "") or ""
        ).strip()
        normalized["image_asset"] = normalize_item_image_reference(
            normalized.get("image_asset")
        )
        return normalized

    def validate(self, values):
        if not values.get("name"):
            raise ValueError("A raw material must have a name.")
        if values.get("base_knuts", 0) < 0:
            raise ValueError("Base Knuts cannot be negative.")
        if values.get("default_source_quantity", 1) < 1:
            raise ValueError("Default quantity must be at least one.")
        method_id = values.get("searching_method_id", "")
        if not method_id:
            raise ValueError("A raw material must select a Searching Method.")
        valid_ids = {
            str(record.get("record_id", ""))
            for record in self.searching_methods()
        }
        if method_id not in valid_ids:
            raise ValueError("The selected Searching Method no longer exists.")
