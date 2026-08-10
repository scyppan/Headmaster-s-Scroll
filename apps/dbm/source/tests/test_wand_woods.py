import tempfile
import unittest
from collections import Counter
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.wands.wand_woods.controller import WandWoodController


class WandWoodTests(unittest.TestCase):
    def test_wand_wood_conversion_preserves_records_and_bonus_groups(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("wand_woods")

        record_ids = [record["record_id"] for record in records]
        names = [record["name"] for record in records]
        bonus_counts = Counter(len(record["bonuses"]) for record in records)
        required_fields = {
            "record_id",
            "name",
            "base_knuts",
            "description",
            "bonuses",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 26)
        self.assertEqual(len(record_ids), len(set(record_ids)))
        self.assertEqual(len(names), len(set(names)))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertEqual(bonus_counts, Counter({1: 19, 4: 6, 0: 1}))

        cedarwood = next(
            record for record in records if record["name"] == "Cedarwood"
        )
        self.assertEqual(
            cedarwood["bonuses"],
            [
                {
                    "type": "Skill",
                    "target": "Defense Against the Dark Arts",
                    "amount": 1,
                },
                {
                    "type": "Skill",
                    "target": "Charms",
                    "amount": 1,
                },
                {
                    "type": "Skill",
                    "target": "Transfiguration",
                    "amount": -1,
                },
                {
                    "type": "Skill",
                    "target": "Dark Arts",
                    "amount": -1,
                },
            ],
        )

    def test_wand_wood_controller_crud_saves_to_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "wand_woods": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = WandWoodController(database)

            created_record = controller.create_record(
                {
                    "name": "Test Wood",
                    "base_knuts": 100,
                    "description": "A test wand wood.",
                    "bonuses": [
                        {
                            "type": "Skill",
                            "target": "Charms",
                            "amount": 1,
                        }
                    ],
                    "dbnotes": "Created by a test.",
                }
            )

            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {"base_knuts": 125},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = WandWoodController(reloaded_database)

            self.assertEqual(
                reloaded_controller.get_record(record_id)["base_knuts"],
                125,
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))


if __name__ == "__main__":
    unittest.main()
