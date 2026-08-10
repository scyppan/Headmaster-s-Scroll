import tempfile
import unittest
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.wands.wand_qualities.controller import WandQualityController


class WandQualityTests(unittest.TestCase):
    def test_wand_quality_conversion_preserves_all_source_values(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("wand_qualities")

        record_ids = [record["record_id"] for record in records]
        names = [record["name"] for record in records]
        required_fields = {
            "record_id",
            "name",
            "base_knuts",
            "effect",
            "casting_effect",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 4)
        self.assertEqual(len(record_ids), len(set(record_ids)))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertEqual(
            set(names),
            {"Superior", "Standard", "Shoddy", "Inferior"},
        )

        inferior = next(
            record for record in records if record["name"] == "Inferior"
        )
        self.assertEqual(inferior["base_knuts"], 100)
        self.assertEqual(inferior["effect"], "-3 to all casting checks")
        self.assertEqual(inferior["casting_effect"], -1)

    def test_wand_quality_controller_crud_saves_to_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "wand_qualities": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = WandQualityController(database)

            created_record = controller.create_record(
                {
                    "name": "Test Quality",
                    "base_knuts": 750,
                    "effect": "A test effect.",
                    "casting_effect": -1,
                    "dbnotes": "Created by a test.",
                }
            )

            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {"casting_effect": 1},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = WandQualityController(reloaded_database)

            self.assertEqual(
                reloaded_controller.get_record(record_id)["casting_effect"],
                1,
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))


if __name__ == "__main__":
    unittest.main()
