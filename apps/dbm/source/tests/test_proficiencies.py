import tempfile
import unittest
from collections import Counter
from inspect import getsource, signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS
from sections.magic.proficiencies.controller import ProficiencyController
from sections.magic.proficiencies.page import ProficienciesPage
from sections.magic.proficiencies.record_form import ProficiencyForm
from sections.magic.proficiencies.record_list import ProficiencyList
from sections.magic.proficiencies.required_materials import (
    REQUIRED_MATERIAL_TYPES,
    RequiredMaterialCatalog,
)
from sections.magic.traditions import TRADITIONS, TRADITIONS_PATH


class ProficiencyTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        self.assertEqual(
            tuple(signature(ProficienciesPage.__init__).parameters),
            ("self", "parent", "database"),
        )
        self.assertEqual(
            tuple(signature(ProficiencyForm.__init__).parameters),
            ("self", "parent", "database", "change_command"),
        )

    def test_proficiency_export_is_fully_preserved_in_new_schema(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("proficiencies")
        required_fields = {
            "record_id",
            "name",
            "tradition",
            "skill",
            "threshold",
            "required_materials",
            "description",
            "history",
            "tags",
            "dbnotes",
            "last_updated",
        }
        records_by_id = {record["record_id"]: record for record in records}
        name_counts = Counter(record["name"].casefold() for record in records)

        self.assertEqual(len(records), 666)
        self.assertEqual(len(records_by_id), 666)
        self.assertEqual(len(name_counts), 665)
        self.assertEqual(name_counts["welsh bardic charms"], 2)
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertEqual(
            Counter(record["skill"] for record in records),
            Counter(
                {
                    "Herbology": 236,
                    "Ancient Runes": 120,
                    "Divination": 90,
                    "Artificing": 75,
                    "Astronomy": 40,
                    "History": 39,
                    "Muggles": 30,
                    "Arithmancy": 18,
                    "Magical Creatures": 16,
                    "Potions": 2,
                }
            ),
        )
        self.assertEqual(
            sum(record["threshold"] is None for record in records),
            2,
        )
        self.assertEqual(
            sum(len(record["required_materials"]) for record in records),
            25,
        )
        self.assertTrue(all("prerequisite" not in record for record in records))
        self.assertTrue(all(record["tags"] == [] for record in records))
        self.assertTrue(all(record["dbnotes"] == "" for record in records))
        self.assertTrue(
            all("<p>" not in record["history"] for record in records)
        )
        self.assertEqual(
            records_by_id["proficiency_13828"]["name"],
            "Griffin Profieicny",
        )
        self.assertEqual(
            records_by_id["proficiency_16332"]["threshold"],
            None,
        )
        self.assertEqual(
            {
                records_by_id["proficiency_22640"]["skill"],
                records_by_id["proficiency_23080"]["skill"],
            },
            {"Astronomy", "History"},
        )

    def test_materials_resolve_to_master_catalogs(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("proficiencies")
        catalog = RequiredMaterialCatalog.for_database(database)

        self.assertTrue(
            all(
                catalog.contains(material["name"], material["type"])
                for record in records
                for material in record["required_materials"]
            )
        )
        self.assertTrue(
            all(
                material["quantity"] == 1
                for record in records
                for material in record["required_materials"]
            )
        )
        self.assertEqual(
            Counter(
                material["type"]
                for record in records
                for material in record["required_materials"]
            ),
            Counter(
                {
                    "General Item": 15,
                    "Plant Part": 5,
                    "Preparation": 2,
                    "Creature Part": 2,
                    "Plant": 1,
                }
            ),
        )

    def test_controller_crud_supports_lists_and_material_quantities(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "plants": [{"name": "Bamboo", "parts": []}],
  "creatures": [{"name": "Griffin", "parts": []}],
  "preparations": [],
  "potions": [],
  "general_items": [{"name": "Small pins"}],
  "foods_and_drinks": [],
  "proficiencies": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = ProficiencyController(database)
            first_record = controller.create_record(
                {
                    "name": "Shared Name",
                    "tradition": "British",
                    "skill": "Herbology",
                    "threshold": 10,
                    "required_materials": [
                        {
                            "name": "Small pins",
                            "type": "General Item",
                            "quantity": 3,
                        }
                    ],
                    "tags": ["Plants"],
                }
            )
            second_record = controller.create_record(
                {
                    "name": "Shared Name",
                    "skill": "History",
                    "threshold": 10,
                }
            )

            self.assertNotEqual(
                first_record["record_id"],
                second_record["record_id"],
            )
            self.assertEqual(
                first_record["required_materials"][0]["quantity"],
                3,
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record(
                    {
                        "name": " shared name ",
                        "tradition": "british",
                        "skill": "herbology",
                        "threshold": 10,
                    }
                )

            controller.update_record(
                second_record["record_id"],
                {"description": "Updated rules."},
            )
            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = ProficiencyController(reloaded_database)

            self.assertEqual(
                reloaded_controller.get_record(second_record["record_id"])[
                    "description"
                ],
                "Updated rules.",
            )

            reloaded_controller.delete_record(first_record["record_id"])
            self.assertIsNone(
                reloaded_controller.get_record(first_record["record_id"])
            )

    def test_invalid_proficiency_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "plants": [{"name": "Bamboo", "parts": []}],
  "creatures": [{"name": "Griffin", "parts": []}],
  "preparations": [],
  "potions": [],
  "general_items": [{"name": "Small pins"}],
  "foods_and_drinks": [],
  "proficiencies": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = ProficiencyController(database)

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record({"skill": "History"})

            with self.assertRaisesRegex(ValueError, "defined skill"):
                controller.create_record(
                    {"name": "Unknown Skill", "skill": "Charms"}
                )

            with self.assertRaisesRegex(ValueError, "between 1 and 100"):
                controller.create_record(
                    {
                        "name": "Impossible Threshold",
                        "skill": "History",
                        "threshold": 101,
                    }
                )

            with self.assertRaisesRegex(ValueError, "defined tradition"):
                controller.create_record(
                    {
                        "name": "Unknown Tradition",
                        "skill": "History",
                        "tradition": "Martian",
                    }
                )

            with self.assertRaisesRegex(ValueError, "at least 1"):
                controller.create_record(
                    {
                        "name": "Bad Quantity",
                        "skill": "History",
                        "required_materials": [
                            {
                                "name": "Small pins",
                                "type": "General Item",
                                "quantity": 0,
                            }
                        ],
                    }
                )

    def test_proficiency_filters_combine_skill_tradition_threshold_and_tags(self):
        matching_record = {
            "name": "Herbal Method",
            "skill": "Herbology",
            "tradition": "British",
            "threshold": 18,
            "tags": ["Plants", "Extraction"],
        }
        filters = {
            "skills": ("Herbology", "Potions"),
            "traditions": ("British",),
            "minimum_threshold": 15,
            "maximum_threshold": 20,
            "tags": ("Extraction",),
        }

        self.assertTrue(
            ProficiencyList.record_matches_filters(matching_record, filters)
        )
        self.assertFalse(
            ProficiencyList.record_matches_filters(
                {**matching_record, "skill": "History"},
                filters,
            )
        )
        self.assertFalse(
            ProficiencyList.record_matches_filters(
                {**matching_record, "threshold": None},
                filters,
            )
        )
        self.assertFalse(
            ProficiencyList.record_matches_filters(
                {**matching_record, "tradition": "Greek"},
                filters,
            )
        )

    def test_proficiency_list_uses_two_line_display(self):
        display_text = ProficiencyList.build_display_text(
            {
                "name": "Herbal Method",
                "skill": "Herbology",
                "threshold": 18,
                "tradition": "British",
            }
        )

        self.assertEqual(
            display_text,
            "Herbal Method\nHerbology 18 (British)",
        )

    def test_fixed_skills_traditions_and_material_types_cover_data(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("proficiencies")

        self.assertEqual(
            {record["skill"] for record in records},
            set(PROFICIENCY_SKILLS) - {"Alchemy", "Flying"},
        )
        self.assertIn("Alchemy", PROFICIENCY_SKILLS)
        self.assertIn("Flying", PROFICIENCY_SKILLS)
        self.assertTrue(
            {
                record["tradition"]
                for record in records
                if record["tradition"]
            }.issubset(set(TRADITIONS))
        )
        self.assertEqual(
            REQUIRED_MATERIAL_TYPES,
            (
                "Creature",
                "Plant",
                "Creature Part",
                "Plant Part",
                "Preparation",
                "Potion",
                "General Item",
                "Food/Drink",
            ),
        )
        self.assertEqual(
            TRADITIONS_PATH.read_text(encoding="utf-8").splitlines(),
            list(TRADITIONS),
        )
        self.assertNotIn("traditions", database.data)

    def test_form_has_no_plant_or_creature_association_section(self):
        form_source = getsource(ProficiencyForm)

        self.assertNotIn("AssociationEditor", form_source)
        self.assertNotIn("associated_plants", form_source)
        self.assertNotIn("associated_creatures", form_source)
        self.assertIn("PROFICIENCY_SKILLS", form_source)
        self.assertNotIn("prerequisite", form_source.casefold())
        self.assertNotIn("item_requirements_checkbox", form_source)
        self.assertNotIn("item_yield_field", form_source)

    def test_required_material_catalog_contains_all_eight_types(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        catalog = RequiredMaterialCatalog.for_database(database)

        self.assertEqual(set(catalog.entries_by_type), set(REQUIRED_MATERIAL_TYPES))
        self.assertTrue(catalog.search("griff", "Creature"))
        self.assertTrue(catalog.search("bamb", "Plant"))
        self.assertTrue(catalog.search("boomberry", "Preparation"))

    def test_existing_recipe_proficiency_link_is_preserved(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        boomberry_juice = next(
            record
            for record in database.get_collection("preparations")
            if record["name"] == "Boomberry Juice"
        )

        self.assertEqual(
            boomberry_juice["required_proficiencies"],
            ["Preparation and Proper Handling of a Boomberry"],
        )


if __name__ == "__main__":
    unittest.main()
