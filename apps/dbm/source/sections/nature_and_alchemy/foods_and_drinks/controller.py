class FoodAndDrinkController:
    collection_name = "foods_and_drinks"

    def __init__(self, database):
        self.database = database

    def list_records(self):
        records = self.database.get_collection(self.collection_name)
        records.sort(key=self.record_sort_key)

        return records

    def get_record(self, record_id):
        return self.database.read(self.collection_name, record_id)

    def create_record(self, record_values):
        created_record = self.database.create(
            self.collection_name,
            record_values,
        )
        self.database.save()

        return created_record

    def update_record(self, record_id, record_values):
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

    def record_sort_key(self, record):
        return (
            record.get("name", "").casefold(),
            record.get("last_updated", ""),
            record.get("record_id", ""),
        )
