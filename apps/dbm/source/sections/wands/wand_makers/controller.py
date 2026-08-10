from database.name_links import (
    canonical_name_choices,
    canonicalize_name_links,
    ensure_unique_record_name,
)


class WandMakerController:
    collection_name = "wand_makers"
    link_fields = (
        (
            "allowed_quality_names",
            "wand_qualities",
            "wand quality",
        ),
        (
            "allowed_wood_names",
            "wand_woods",
            "wand wood",
        ),
        (
            "allowed_core_names",
            "wand_cores",
            "wand core",
        ),
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

        for field_name, collection_name, collection_label in self.link_fields:
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
            prepared_values.get("name", ""),
            record_label="wand maker",
        )
        created_record = self.database.create(
            self.collection_name,
            prepared_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        prepared_values = self.prepare_values(record_values)

        if "name" in prepared_values:
            ensure_unique_record_name(
                self.database.get_collection(self.collection_name),
                prepared_values["name"],
                record_id=record_id,
                record_label="wand maker",
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
        prepared_values = dict(record_values)

        for field_name, collection_name, collection_label in self.link_fields:
            if field_name not in prepared_values:
                continue

            records = self.database.get_collection(collection_name)
            prepared_values[field_name] = canonicalize_name_links(
                prepared_values[field_name],
                records,
                collection_label,
            )

        return prepared_values

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
