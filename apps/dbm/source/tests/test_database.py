import tempfile
import unittest
from collections import Counter
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH


class JsonDatabaseTests(unittest.TestCase):
    def test_database_contains_domain_collections_and_metadata(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()

        self.assertFalse(database.has_container("people"))
        self.assertTrue(database.has_container("schools"))
        self.assertTrue(database.has_container("books"))
        self.assertTrue(database.has_container("bookshelves"))
        self.assertTrue(database.has_container("foods_and_drinks"))
        self.assertTrue(database.has_container("spells"))
        self.assertTrue(database.has_container("accessories"))

        metadata = database.get_database_metadata()
        self.assertEqual(metadata["schema_version"], 1)
        self.assertEqual(metadata["database_version"], "1.0")

    def test_food_and_drink_conversion_preserves_every_source_record(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()

        records = database.get_collection("foods_and_drinks")
        record_ids = [record["record_id"] for record in records]
        name_counts = Counter(record["name"] for record in records)
        required_fields = {
            "record_id",
            "name",
            "description",
            "raw_effects",
            "effects_in_potions",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 163)
        self.assertEqual(len(record_ids), len(set(record_ids)))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertEqual(
            {
                name
                for name, count in name_counts.items()
                if count > 1
            },
            {
                "Vinegar",
                "Syrup",
                "Alcohol",
                "Hops",
                "Yeast",
                "Ice Pop",
                "Pumpkin Juice",
                "Coffee",
            },
        )

    def test_crud_and_save_use_one_json_file(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "foods_and_drinks": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()

            created_record = database.create(
                "foods_and_drinks",
                {"name": "Pumpkin Juice"},
            )
            record_id = created_record["record_id"]

            self.assertEqual(
                database.read("foods_and_drinks", record_id)["name"],
                "Pumpkin Juice",
            )

            database.update(
                "foods_and_drinks",
                record_id,
                {"name": "Cold Pumpkin Juice"},
            )

            self.assertEqual(
                database.read("foods_and_drinks", record_id)["name"],
                "Cold Pumpkin Juice",
            )

            database.save()

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()

            self.assertEqual(
                reloaded_database.read(
                    "foods_and_drinks",
                    record_id,
                )["name"],
                "Cold Pumpkin Juice",
            )

            reloaded_database.delete("foods_and_drinks", record_id)

            self.assertIsNone(
                reloaded_database.read("foods_and_drinks", record_id)
            )


if __name__ == "__main__":
    unittest.main()
