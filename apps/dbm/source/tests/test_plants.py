import tempfile
import unittest
from inspect import signature
from pathlib import Path

from core.section_loader import load_sections
from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.nature_and_alchemy.plants.controller import PlantController
from sections.nature_and_alchemy.plants.page import PlantsPage


class PlantTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(PlantsPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_plants_are_visible_and_standalone_parts_are_hidden(self):
        sections = load_sections()
        section_keys = [section.key for section in sections]

        self.assertIn("plants", section_keys)
        self.assertNotIn("plant_parts", section_keys)

    def test_all_plant_parts_are_children_of_their_plants(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        plant_records = database.get_collection("plants")
        plants_by_name = {
            record["name"]: record
            for record in plant_records
        }
        required_plant_fields = {
            "record_id",
            "name",
            "description",
            "parts",
            "tags",
            "dbnotes",
            "last_updated",
        }
        required_part_fields = {
            "name",
            "required_proficiency",
            "description",
            "raw_effects",
            "effect_in_potions",
        }
        plant_parts = [
            part
            for record in plant_records
            for part in record["parts"]
        ]

        self.assertFalse(database.has_container("plant_parts"))
        self.assertEqual(len(plant_records), 168)
        self.assertEqual(len(plants_by_name), 168)
        self.assertEqual(
            len({record["record_id"] for record in plant_records}),
            168,
        )
        self.assertTrue(
            all(
                set(record) == required_plant_fields
                for record in plant_records
            )
        )
        self.assertEqual(len(plant_parts), 215)
        self.assertEqual(
            len({part["name"].casefold() for part in plant_parts}),
            213,
        )
        self.assertTrue(
            all(set(part) == required_part_fields for part in plant_parts)
        )
        self.assertTrue(
            all(
                len(record["parts"])
                == len(
                    {
                        part["name"].casefold()
                        for part in record["parts"]
                    }
                )
                for record in plant_records
            )
        )
        self.assertTrue(all("level" not in record for record in plant_records))
        self.assertTrue(
            all(
                part["required_proficiency"] == "No"
                for part in plant_parts
            )
        )
        self.assertEqual(
            plants_by_name["Henbane"]["record_id"],
            "plant_20217",
        )
        self.assertEqual(
            plants_by_name["Henbane"]["description"],
            (
                "Henbane is a historic magical plant. Its seeds, stems and "
                "leaves all produce psychotropic effects."
            ),
        )
        self.assertEqual(
            [part["name"] for part in plants_by_name["Moonseed"]["parts"]],
            ["Moonseeds", "Moonseed Leaves", "Moonseed Vines"],
        )
        self.assertEqual(
            [part["name"] for part in plants_by_name["Neem"]["parts"]],
            ["Neem Bark", "Neem Leaves", "Neem Seeds"],
        )
        self.assertEqual(
            [part["name"] for part in plants_by_name["Soy"]["parts"]],
            ["Beans", "Soy Plant Leaves"],
        )
        self.assertEqual(
            [
                part["name"]
                for part in plants_by_name["Caster Plant"]["parts"]
            ],
            ["Caster Oil", "Beans"],
        )
        self.assertEqual(
            [part["name"] for part in plants_by_name["Henbane"]["parts"]],
            ["Horseradish Roots", "Henbane Seeds"],
        )
        self.assertTrue(
            all(
                "<" not in part[field_name]
                and ">" not in part[field_name]
                for part in plant_parts
                for field_name in (
                    "description",
                    "raw_effects",
                    "effect_in_potions",
                )
            )
        )

    def test_controller_crud_saves_child_parts(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                (
                    '{"_database": {"schema_version": 1}, '
                    '"plants": [], "proficiencies": []}'
                ),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = PlantController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Plant",
                    "description": "A test plant.",
                    "parts": [
                        {
                            "name": "Test Leaves",
                            "required_proficiency": "No",
                            "description": "Leaves from the test plant.",
                            "raw_effects": "None",
                            "effect_in_potions": "Unknown",
                        }
                    ],
                    "tags": ["Greenhouse"],
                    "dbnotes": "Created by a test.",
                }
            )
            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {"description": "An updated test plant."},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = PlantController(reloaded_database)
            reloaded_record = reloaded_controller.get_record(record_id)

            self.assertEqual(
                reloaded_record["description"],
                "An updated test plant.",
            )
            self.assertEqual(
                reloaded_record["parts"][0]["name"],
                "Test Leaves",
            )
            self.assertNotIn(
                "catalog_record_id",
                reloaded_record["parts"][0],
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))

    def test_duplicate_names_and_invalid_proficiencies_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                (
                    '{"_database": {"schema_version": 1}, '
                    '"plants": [], "proficiencies": []}'
                ),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = PlantController(database)
            controller.create_record({"name": "Test Plant"})

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record({"name": "  test   PLANT  "})

            with self.assertRaisesRegex(ValueError, "Unknown proficiency"):
                controller.create_record(
                    {
                        "name": "Invalid Proficiency Plant",
                        "parts": [
                            {
                                "name": "Difficult Leaves",
                                "required_proficiency": "Not a proficiency",
                            }
                        ],
                    }
                )


if __name__ == "__main__":
    unittest.main()
