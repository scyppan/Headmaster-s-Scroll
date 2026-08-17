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
        self.assertFalse(database.has_container("bookshelves"))
        self.assertTrue(database.has_container("foods_and_drinks"))
        self.assertTrue(database.has_container("spells"))
        self.assertTrue(database.has_container("accessories"))

        metadata = database.get_database_metadata()
        self.assertEqual(metadata["schema_version"], 9)
        self.assertTrue(database.has_container("raw_materials"))
        self.assertTrue(database.has_container("recipes"))
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

    def test_schema_two_adds_default_publication_date_to_existing_books(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"books": [{"record_id": "book-1", "name": "Old Book"}]}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            self.assertTrue(database.dirty)
            self.assertEqual(database.get_database_metadata()["schema_version"], 9)
            self.assertEqual(
                database.get_collection("books")[0]["publication_date"],
                "1900-01-01",
            )

    def test_schema_five_adds_item_prices_actions_and_natural_types(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 4}, '
                '"general_items": ['
                '{"record_id": "a", "name": "Quartz", "type": "Alchemical"},'
                '{"record_id": "r", "name": "Charm", "type": "Ritual Item"},'
                '{"record_id": "d", "name": "Glass", "type": "Divination"}'
                '], "accessories": [{"record_id": "x", "name": "Ring"}], '
                '"holdable_items": [{"record_id": "h", "name": "Focus"}]}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            items = {
                record["record_id"]: record
                for record in database.get_collection("general_items")
            }
            self.assertEqual(items["a"]["type"], "Alchemical Item")
            self.assertEqual(items["r"]["type"], "General Item")
            self.assertEqual(items["d"]["type"], "Divinatory Item")
            for collection in ("general_items", "accessories", "holdable_items"):
                for record in database.get_collection(collection):
                    self.assertEqual(record["base_knuts"], 0)
                    self.assertEqual(record["actions"], [])

    def test_schema_six_adds_recipe_catalogs_and_moves_searching_off_items(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 5}, '
                '"general_items": [{"record_id": "item", "name": "Cup", '
                '"searching_method_id": "search", '
                '"gathering_method_ids": ["search"]}]}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            item = database.get_collection("general_items")[0]
            self.assertNotIn("searching_method_id", item)
            self.assertNotIn("gathering_method_ids", item)
            self.assertEqual(database.get_collection("raw_materials"), [])
            self.assertEqual(database.get_collection("recipes"), [])
            self.assertEqual(
                database.get_database_metadata()["schema_version"], 9
            )


if __name__ == "__main__":
    unittest.main()
