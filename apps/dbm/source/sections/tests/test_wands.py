import json
import tempfile
import unittest
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.wands.wands.controller import WandController


class WandTests(unittest.TestCase):
    def test_wand_conversion_preserves_all_source_combinations(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("wands")

        record_ids = [record["record_id"] for record in records]
        names = [record["name"] for record in records]
        combinations = [
            (
                record["maker_name"],
                record["core_name"],
                record["wood_name"],
                record["quality_name"],
            )
            for record in records
        ]
        required_fields = {
            "record_id",
            "name",
            "maker_name",
            "core_name",
            "wood_name",
            "quality_name",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 238)
        self.assertEqual(len(record_ids), len(set(record_ids)))
        self.assertEqual(len(names), len(set(names)))
        self.assertEqual(len(combinations), len(set(combinations)))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertTrue(all(not record["dbnotes"] for record in records))

        silver_lime_variants = [
            record
            for record in records
            if record["maker_name"] == "Arturo Cephalopos"
            and record["wood_name"] == "Silver Lime"
        ]
        self.assertEqual(len(silver_lime_variants), 88)
        self.assertEqual(
            {record["quality_name"] for record in silver_lime_variants},
            {"Superior", "Standard", "Shoddy", "Inferior"},
        )
        self.assertEqual(
            len({record["core_name"] for record in silver_lime_variants}),
            22,
        )

    def test_preview_uses_current_linked_values_and_calculates_price(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        controller = WandController(database)
        preview = controller.preview_values(
            {
                "maker_name": "Eldist Rancor",
                "core_name": "Wiggentree Leaf Stem",
                "wood_name": "Black Walnut",
                "quality_name": "Superior",
            }
        )

        self.assertEqual(
            preview["name"],
            "Superior Black Walnut wand with a Wiggentree Leaf Stem "
            "core (crafted by Eldist Rancor)",
        )
        self.assertEqual(preview["maker_multiplier"], 1.1)
        self.assertEqual(preview["core_base_knuts"], 6424)
        self.assertEqual(preview["wood_base_knuts"], 32454)
        self.assertEqual(preview["quality_base_knuts"], 5000)
        self.assertEqual(preview["total_knuts"], 48265.8)

        current_effect_preview = controller.preview_values(
            {
                "maker_name": "Jimmy Kiddell",
                "core_name": "White River Monster Spine",
                "wood_name": "Fir",
                "quality_name": "Inferior",
            }
        )
        self.assertEqual(
            current_effect_preview["core_effect"],
            "Transfiguration +3",
        )
        self.assertEqual(
            current_effect_preview["wood_effect"],
            "Transfiguration +3",
        )

    def test_name_links_are_canonical_and_duplicate_wands_are_blocked(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                json.dumps(
                    {
                        "_database": {"schema_version": 1},
                        "wand_makers": [
                            {
                                "record_id": "maker_1",
                                "name": "Test Maker",
                                "multiplier": 1.25,
                            }
                        ],
                        "wand_cores": [
                            {
                                "record_id": "core_1",
                                "name": "Test Core",
                                "base_knuts": 200,
                                "description": "Core effect",
                            }
                        ],
                        "wand_woods": [
                            {
                                "record_id": "wood_1",
                                "name": "Test Wood",
                                "base_knuts": 300,
                                "description": "Wood effect",
                            }
                        ],
                        "wand_qualities": [
                            {
                                "record_id": "quality_1",
                                "name": "Test Quality",
                                "base_knuts": 500,
                                "effect": "Quality effect",
                            }
                        ],
                        "wands": [],
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = WandController(database)
            created_record = controller.create_record(
                {
                    "maker_name": " test   maker ",
                    "core_name": "TEST CORE",
                    "wood_name": "test wood",
                    "quality_name": "Test Quality",
                    "dbnotes": "Created in a test.",
                }
            )

            self.assertEqual(created_record["maker_name"], "Test Maker")
            self.assertEqual(created_record["core_name"], "Test Core")
            self.assertEqual(created_record["wood_name"], "Test Wood")
            self.assertEqual(created_record["quality_name"], "Test Quality")
            self.assertEqual(
                created_record["name"],
                "Test Quality Test Wood wand with a Test Core core "
                "(crafted by Test Maker)",
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record(
                    {
                        "maker_name": "Test Maker",
                        "core_name": "Test Core",
                        "wood_name": "Test Wood",
                        "quality_name": "Test Quality",
                        "dbnotes": "Duplicate.",
                    }
                )

            controller.delete_record(created_record["record_id"])
            self.assertIsNone(
                controller.get_record(created_record["record_id"])
            )

    def test_unknown_or_missing_linked_names_are_rejected(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        controller = WandController(database)

        with self.assertRaisesRegex(ValueError, "Unknown wand maker"):
            controller.prepare_values(
                {
                    "maker_name": "Unknown Maker",
                    "core_name": "Unicorn Horn",
                    "wood_name": "Holly",
                    "quality_name": "Superior",
                }
            )

        with self.assertRaisesRegex(ValueError, "wand quality must be selected"):
            controller.prepare_values(
                {
                    "maker_name": "Garrick Ollivander",
                    "core_name": "Unicorn Horn",
                    "wood_name": "Holly",
                    "quality_name": "",
                }
            )


if __name__ == "__main__":
    unittest.main()
