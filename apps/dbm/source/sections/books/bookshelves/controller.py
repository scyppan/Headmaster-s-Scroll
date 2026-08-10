from copy import deepcopy


class BookshelfController:
    collection_name = "bookshelves"
    text_fields = (
        "name",
        "description",
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
            "description": "",
            "tags": [],
            "books": [],
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
            raise KeyError(f"Unknown bookshelf record ID: {record_id}")

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

        if "tags" in normalized_values:
            normalized_values["tags"] = self.normalize_tags(
                normalized_values["tags"]
            )

        if "books" in normalized_values:
            normalized_values["books"] = self.normalize_book_references(
                normalized_values["books"]
            )

        return normalized_values

    def normalize_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Bookshelf tags must be a list.")

        return [" ".join(str(tag).split()) for tag in tags]

    def normalize_book_references(self, references):
        if not isinstance(references, list):
            raise TypeError("Bookshelf books must be stored as a list.")

        books_by_id = {
            record.get("record_id"): record
            for record in self.database.get_collection("books")
        }
        normalized_references = []

        for reference in references:
            if not isinstance(reference, dict):
                raise TypeError("Every bookshelf book must be an object.")

            record_id = str(reference.get("record_id", "")).strip()
            book = books_by_id.get(record_id)
            book_name = (
                str(book.get("name", "")).strip()
                if book is not None
                else str(reference.get("name", "")).strip()
            )
            normalized_references.append(
                {
                    "record_id": record_id,
                    "name": book_name,
                }
            )

        return normalized_references

    def validate_record_values(self, record_values):
        if not record_values.get("name", "").strip():
            raise ValueError("A bookshelf must have a name.")

        for field_name in self.text_fields:
            if field_name in record_values and not isinstance(
                record_values[field_name],
                str,
            ):
                raise TypeError(f"Bookshelf {field_name} must be text.")

        self.validate_tags(record_values.get("tags", []))
        self.validate_book_references(record_values.get("books", []))

    def validate_tags(self, tags):
        if not isinstance(tags, list):
            raise TypeError("Bookshelf tags must be a list.")

        normalized_tags = set()

        for tag in tags:
            if not isinstance(tag, str):
                raise TypeError("Every bookshelf tag must be text.")

            if not tag.strip():
                raise ValueError("Bookshelf tags cannot be blank.")

            normalized_tag = " ".join(tag.split()).casefold()

            if normalized_tag in normalized_tags:
                raise ValueError(f"Duplicate bookshelf tag: {tag}")

            normalized_tags.add(normalized_tag)

    def validate_book_references(self, references):
        if not isinstance(references, list):
            raise TypeError("Bookshelf books must be a list.")

        book_ids = {
            record.get("record_id")
            for record in self.database.get_collection("books")
        }
        selected_book_ids = set()

        for reference in references:
            if not isinstance(reference, dict):
                raise TypeError("Every bookshelf book must be an object.")

            record_id = reference.get("record_id", "")

            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("Every bookshelf book needs an ID.")

            if record_id not in book_ids:
                raise ValueError(
                    f"Unknown book: {reference.get('name', record_id)}"
                )

            if record_id in selected_book_ids:
                raise ValueError(
                    f"Duplicate bookshelf book: "
                    f"{reference.get('name', record_id)}"
                )

            if not isinstance(reference.get("name", ""), str):
                raise TypeError("Every bookshelf book name must be text.")

            selected_book_ids.add(record_id)

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("record_id", ""),
        )
