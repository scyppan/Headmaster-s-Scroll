from copy import deepcopy


BOOK_LINK_COLLECTIONS = {
    "spells": "spells",
    "proficiencies": "proficiencies",
    "potions": "potions",
}


class BookController:
    collection_name = "books"
    text_fields = (
        "name",
        "author",
        "description",
        "dbnotes",
    )

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
            "author": "",
            "categories": [],
            "description": "",
            "spells": [],
            "proficiencies": [],
            "potions": [],
            "dbnotes": "",
        }
        complete_values.update(deepcopy(record_values))
        normalized_values = self.normalize_record_values(complete_values)
        self.validate_record_values(normalized_values)
        created_record = self.database.create(
            self.collection_name,
            normalized_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
        current_record = self.get_record(record_id)

        if current_record is None:
            raise KeyError(f"Unknown book record ID: {record_id}")

        normalized_changes = self.normalize_record_values(record_values)
        prospective_record = deepcopy(current_record)
        prospective_record.update(normalized_changes)
        self.validate_record_values(prospective_record)
        updated_record = self.database.update(
            self.collection_name,
            record_id,
            normalized_changes,
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
        normalized_values = deepcopy(record_values)

        for field_name in self.text_fields:
            if field_name in normalized_values:
                normalized_values[field_name] = str(
                    normalized_values[field_name] or ""
                ).strip()

        if "categories" in normalized_values:
            normalized_values["categories"] = self.normalize_categories(
                normalized_values["categories"]
            )

        for link_field, collection_name in BOOK_LINK_COLLECTIONS.items():
            if link_field in normalized_values:
                normalized_values[link_field] = self.normalize_references(
                    normalized_values[link_field],
                    collection_name,
                )

        return normalized_values

    def normalize_categories(self, categories):
        if not isinstance(categories, list):
            raise TypeError("Book categories must be a list.")

        return [" ".join(str(category).split()) for category in categories]

    def normalize_references(self, references, collection_name):
        if not isinstance(references, list):
            raise TypeError("Book links must be stored as a list.")

        records_by_id = {
            record.get("record_id"): record
            for record in self.database.get_collection(collection_name)
        }
        normalized_references = []

        for reference in references:
            if not isinstance(reference, dict):
                raise TypeError("Every book link must be an object.")

            record_id = str(reference.get("record_id", "")).strip()
            linked_record = records_by_id.get(record_id)
            linked_name = (
                str(linked_record.get("name", "")).strip()
                if linked_record is not None
                else str(reference.get("name", "")).strip()
            )
            normalized_references.append(
                {
                    "record_id": record_id,
                    "name": linked_name,
                }
            )

        return normalized_references

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A book must have a name.")

        for field_name in self.text_fields:
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"Book {field_name} must be text.")

        self.validate_categories(record_values.get("categories", []))

        for link_field, collection_name in BOOK_LINK_COLLECTIONS.items():
            self.validate_references(
                record_values.get(link_field, []),
                collection_name,
                link_field,
            )

    def validate_categories(self, categories):
        if not isinstance(categories, list):
            raise TypeError("Book categories must be a list.")

        normalized_categories = set()

        for category in categories:
            if not isinstance(category, str):
                raise TypeError("Every book category must be text.")

            if not category.strip():
                raise ValueError("Book categories cannot be blank.")

            normalized_category = " ".join(category.split()).casefold()

            if normalized_category in normalized_categories:
                raise ValueError(f"Duplicate book category: {category}")

            normalized_categories.add(normalized_category)

    def validate_references(self, references, collection_name, field_name):
        if not isinstance(references, list):
            raise TypeError(f"Book {field_name} must be a list.")

        record_ids = {
            record.get("record_id")
            for record in self.database.get_collection(collection_name)
        }

        for reference in references:
            if not isinstance(reference, dict):
                raise TypeError(f"Every book {field_name} link must be an object.")

            record_id = reference.get("record_id", "")

            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError(f"Every book {field_name} link needs an ID.")

            if record_id not in record_ids:
                raise ValueError(
                    f"Unknown linked {field_name[:-1]}: "
                    f"{reference.get('name', record_id)}"
                )

            if not isinstance(reference.get("name", ""), str):
                raise TypeError(f"Every book {field_name} name must be text.")

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("author", "").casefold(),
            record.get("record_id", ""),
        )
