from decimal import Decimal

from database.name_links import (
    canonical_name_choices,
    canonicalize_name_link,
    ensure_unique_record_name,
)


class WandController:
    collection_name = "wands"
    reference_fields = (
        ("maker_name", "wand_makers", "wand maker"),
        ("core_name", "wand_cores", "wand core"),
        ("wood_name", "wand_woods", "wand wood"),
        ("quality_name", "wand_qualities", "wand quality"),
    )

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def get_reference_names(self):
        reference_names = {}

        for field_name, collection_name, collection_label in self.reference_fields:
            records = self.database.get_collection(collection_name)
            reference_names[field_name] = canonical_name_choices(
                records,
                collection_label,
            )

        return reference_names

    def create_record(self, record_values):
        prepared_values = self.prepare_values(record_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            prepared_values["name"],
            record_label="wand",
        )
        created_record = self.database.create(
            self.collection_name,
            prepared_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        prepared_values = self.prepare_values(record_values)
        ensure_unique_record_name(
            self.database.get_collection(self.collection_name),
            prepared_values["name"],
            record_id=record_id,
            record_label="wand",
        )
        updated_record = self.database.update(
            self.collection_name,
            record_id,
            prepared_values,
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

    def prepare_values(self, record_values):
        prepared_values = {
            "dbnotes": record_values.get("dbnotes", "").strip(),
        }

        for field_name, collection_name, collection_label in self.reference_fields:
            records = self.database.get_collection(collection_name)
            prepared_values[field_name] = canonicalize_name_link(
                record_values.get(field_name, ""),
                records,
                collection_label,
            )

        prepared_values["name"] = self.build_name(prepared_values)

        return prepared_values

    def preview_values(self, record_values):
        preview = {
            "name": "",
            "maker_multiplier": None,
            "core_base_knuts": None,
            "wood_base_knuts": None,
            "quality_base_knuts": None,
            "total_knuts": None,
            "core_effect": "",
            "wood_effect": "",
            "quality_effect": "",
        }
        resolved_values = {}
        reference_records = {}

        for field_name, collection_name, collection_label in self.reference_fields:
            selected_name = record_values.get(field_name, "").strip()

            if not selected_name:
                continue

            records = self.database.get_collection(collection_name)
            canonical_name = canonicalize_name_link(
                selected_name,
                records,
                collection_label,
            )
            resolved_values[field_name] = canonical_name

            for record in records:
                if record.get("name") == canonical_name:
                    reference_records[field_name] = record
                    break

        maker = reference_records.get("maker_name")
        core = reference_records.get("core_name")
        wood = reference_records.get("wood_name")
        quality = reference_records.get("quality_name")

        if maker is not None:
            preview["maker_multiplier"] = maker.get("multiplier")

        if core is not None:
            preview["core_base_knuts"] = core.get("base_knuts")
            preview["core_effect"] = core.get("description", "")

        if wood is not None:
            preview["wood_base_knuts"] = wood.get("base_knuts")
            preview["wood_effect"] = wood.get("description", "")

        if quality is not None:
            preview["quality_base_knuts"] = quality.get("base_knuts")
            preview["quality_effect"] = quality.get("effect", "")

        if len(resolved_values) == len(self.reference_fields):
            preview["name"] = self.build_name(resolved_values)
            total_base = (
                Decimal(str(preview["core_base_knuts"]))
                + Decimal(str(preview["wood_base_knuts"]))
                + Decimal(str(preview["quality_base_knuts"]))
            )
            total_knuts = total_base * Decimal(
                str(preview["maker_multiplier"])
            )
            preview["total_knuts"] = float(total_knuts)

        return preview

    def build_name(self, record_values):
        return (
            f'{record_values["quality_name"]} '
            f'{record_values["wood_name"]} wand with a '
            f'{record_values["core_name"]} core '
            f'(crafted by {record_values["maker_name"]})'
        )

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
