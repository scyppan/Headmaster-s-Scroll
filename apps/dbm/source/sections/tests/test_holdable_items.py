import tempfile
import unittest
from inspect import signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.items.holdable_items.controller import HoldableItemController
from sections.items.holdable_items.page import HoldableItemsPage


class HoldableItemTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(HoldableItemsPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_conversion_preserves_source_record_and_bonus(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("holdable_items")

        self.assertEqual(len(records), 1)
        self.assertEqual(
            set(records[0]),
            {
                "record_id",
                "name",
                "description",
                "bonuses",
                "dbnotes",
                "last_updated",
            },
        )
        self.assertEqual(records[0]["record_id"], "holdable_item_28899")
        self.assertEqual(records[0]["name"], "Kakaw Tzolkʼin Disc")
        self.assertEqual(
            records[0]["bonuses"],
            [
                {
                    "type": "Ability",
                    "target": "Power",
                    "amount": 1,
                }
            ],
        )

    def test_controller_crud_saves_to_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"holdable_items": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = HoldableItemController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Item",
                    "description": "A test holdable item.",
                    "bonuses": [
                        {
                            "type": "Skill",
                            "target": "Charms",
                            "amount": 2,
                        }
                    ],
                    "dbnotes": "Created by a test.",
                }
            )

            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {"description": "An updated test item."},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = HoldableItemController(reloaded_database)
            self.assertEqual(
                reloaded_controller.get_record(record_id)["description"],
                "An updated test item.",
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))

    def test_duplicate_names_ignore_case_and_extra_spacing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"holdable_items": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = HoldableItemController(database)
            controller.create_record({"name": "Test Item"})

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record({"name": "  test   item  "})


if __name__ == "__main__":
    unittest.main()
