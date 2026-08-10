import json
import tempfile
import unittest
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from database.name_links import canonical_name_choices
from sections.wands.wand_makers.controller import WandMakerController


class WandMakerTests(unittest.TestCase):
    def test_wand_maker_conversion_preserves_source_records(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("wand_makers")

        record_ids = [record["record_id"] for record in records]
        names = [record["name"] for record in records]
        required_fields = {
            "record_id",
            "name",
            "multiplier",
            "allowed_quality_names",
            "allowed_wood_names",
            "allowed_core_names",
            "notes",
            "last_updated",
        }

        self.assertEqual(len(records), 5)
        self.assertEqual(len(record_ids), len(set(record_ids)))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertTrue(
            all(not record["allowed_quality_names"] for record in records)
        )
        self.assertTrue(all(not record["allowed_wood_names"] for record in records))
        self.assertTrue(all(not record["allowed_core_names"] for record in records))

        multipliers = {
            record["name"]: record["multiplier"] for record in records
        }
        self.assertEqual(multipliers["Garrick Ollivander"], 0.6)
        self.assertEqual(multipliers["Arturo Cephalopos"], 0.1)

    def test_reference_options_come_from_canonical_collection_names(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        controller = WandMakerController(database)
        reference_names = controller.get_reference_names()

        self.assertEqual(len(reference_names["allowed_quality_names"]), 4)
        self.assertEqual(len(reference_names["allowed_wood_names"]), 26)
        self.assertEqual(len(reference_names["allowed_core_names"]), 22)
        self.assertIn("Superior", reference_names["allowed_quality_names"])
        self.assertIn("Holly", reference_names["allowed_wood_names"])
        self.assertIn("Unicorn Horn", reference_names["allowed_core_names"])

    def test_name_links_are_canonical_and_duplicates_are_blocked(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                json.dumps(
                    {
                        "_database": {"schema_version": 1},
                        "wand_makers": [],
                        "wand_qualities": [
                            {"record_id": "quality_1", "name": "Superior"}
                        ],
                        "wand_woods": [
                            {"record_id": "wood_1", "name": "Holly"}
                        ],
                        "wand_cores": [
                            {
                                "record_id": "core_1",
                                "name": "Unicorn Horn",
                            }
                        ],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = WandMakerController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Maker",
                    "multiplier": 1.0,
                    "allowed_quality_names": [" superior "],
                    "allowed_wood_names": ["HOLLY"],
                    "allowed_core_names": ["unicorn   horn"],
                    "notes": "A test maker.",
                }
            )

            self.assertEqual(
                created_record["allowed_quality_names"],
                ["Superior"],
            )
            self.assertEqual(created_record["allowed_wood_names"], ["Holly"])
            self.assertEqual(
                created_record["allowed_core_names"],
                ["Unicorn Horn"],
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record(
                    {
                        "name": " test   maker ",
                        "multiplier": 1.1,
                        "allowed_quality_names": [],
                        "allowed_wood_names": [],
                        "allowed_core_names": [],
                        "notes": "Duplicate name.",
                    }
                )

            with self.assertRaisesRegex(ValueError, "Duplicate selected"):
                controller.update_record(
                    created_record["record_id"],
                    {"allowed_wood_names": ["Holly", " holly "]},
                )

            controller.delete_record(created_record["record_id"])
            self.assertIsNone(
                controller.get_record(created_record["record_id"])
            )

    def test_duplicate_reference_names_are_rejected(self):
        records = [
            {"record_id": "wood_1", "name": "Holly"},
            {"record_id": "wood_2", "name": " holly "},
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate wand wood name"):
            canonical_name_choices(records, "wand wood")


if __name__ == "__main__":
    unittest.main()
