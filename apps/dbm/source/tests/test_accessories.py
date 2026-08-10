import tempfile
import unittest
from inspect import signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.items.accessories.controller import AccessoryController
from sections.items.accessories.page import AccessoriesPage


class AccessoryTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(AccessoriesPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_conversion_preserves_all_source_records_and_bonuses(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("accessories")
        records_by_name = {
            record["name"]: record
            for record in records
        }
        required_fields = {
            "record_id",
            "name",
            "description",
            "bonuses",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 19)
        self.assertEqual(len(records_by_name), 19)
        self.assertTrue(
            all(set(record) == required_fields for record in records)
        )
        self.assertEqual(
            records_by_name["Leather Gloves"]["record_id"],
            "accessory_16851",
        )
        self.assertEqual(
            records_by_name["Gilded Wristwatch"]["bonuses"],
            [
                {
                    "type": "Skill",
                    "target": "Social Skills",
                    "amount": 1,
                },
                {
                    "type": "Characteristic",
                    "target": "Charisma",
                    "amount": 2,
                },
            ],
        )

    def test_controller_crud_saves_to_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"accessories": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = AccessoryController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Accessory",
                    "description": "A test accessory.",
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
                {"description": "An updated test accessory."},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = AccessoryController(reloaded_database)
            self.assertEqual(
                reloaded_controller.get_record(record_id)["description"],
                "An updated test accessory.",
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))

    def test_duplicate_names_ignore_case_and_extra_spacing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"accessories": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = AccessoryController(database)
            controller.create_record({"name": "Test Accessory"})

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record({"name": "  test   accessory  "})


if __name__ == "__main__":
    unittest.main()
