import tempfile
import unittest
from inspect import getsource
from pathlib import Path

from database import JsonDatabase
from sections.items.general_items.controller import GeneralItemController
from sections.nature_and_alchemy.recipes.controller import RecipeController
from sections.nature_and_alchemy.recipes.requirements import RequirementLineDialog


OUTPUT = {
    "collection": "preparations",
    "record_id": "output-item",
    "name": "Prepared output",
}


class RawMaterialAndRecipeTests(unittest.TestCase):
    def database(self, temporary_directory):
        path = Path(temporary_directory) / "db.json"
        path.write_text(
            """{
              "_database": {"schema_version": 6},
              "gathering_methods": [
                {"record_id": "search-prospect", "name": "Prospect"}
              ],
              "raw_materials": [],
              "recipes": []
            }""",
            encoding="utf-8",
        )
        database = JsonDatabase(path)
        database.load()
        return database

    def test_raw_material_requires_searching_method(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = GeneralItemController(
                self.database(temporary_directory)
            )
            with self.assertRaisesRegex(ValueError, "Searching Method"):
                controller.create_record({
                    "name": "Saltpeter",
                    "type": "Raw Material",
                    "base_knuts": 3,
                })
            record = controller.create_record({
                "name": "Saltpeter",
                "type": "Raw Material",
                "base_knuts": 3,
                "searching_method_id": "search-prospect",
                "tags": ["volatile", "mineral"],
            })
            self.assertEqual(record["gathering_method_ids"], ["search-prospect"])
            self.assertEqual(record["tags"], ["volatile", "mineral"])

    def test_recipe_preserves_and_or_requirement_groups(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = RecipeController(self.database(temporary_directory))
            record = controller.create_record({
                "name": "Aqua Fortis",
                "skill": "Potions",
                "threshold": 12,
                "output_item": OUTPUT,
                "output_quantity": 6,
                "ingredient_requirements": [
                    {
                        "record_id": "ingredient-saltpeter",
                        "alternatives": [{
                            "collection": "raw_materials",
                            "record_id": "saltpeter",
                            "name": "Saltpeter",
                            "quantity": 1,
                        }],
                    },
                    {
                        "record_id": "ingredient-vitriol",
                        "alternatives": [{
                            "collection": "raw_materials",
                            "record_id": "vitriol",
                            "name": "Vitriol",
                            "quantity": 1,
                        }],
                    },
                ],
                "vessel_requirements": [{
                    "record_id": "vessel-line",
                    "alternatives": [
                        {
                            "collection": "general_items",
                            "record_id": "alembic",
                            "name": "Alembic",
                        },
                        {
                            "collection": "general_items",
                            "record_id": "retort",
                            "name": "Retort",
                        },
                    ],
                }],
                "proficiency_requirements": [],
            })
            self.assertEqual(len(record["ingredient_requirements"]), 2)
            self.assertEqual(
                [
                    item["name"]
                    for item in record["vessel_requirements"][0]["alternatives"]
                ],
                ["Alembic", "Retort"],
            )

    def test_a_single_required_vessel_needs_no_replacement(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = RecipeController(self.database(temporary_directory))
            record = controller.create_record({
                "name": "Simple Distillate",
                "skill": "Potions",
                "threshold": 7,
                "output_item": OUTPUT,
                "output_quantity": 1,
                "ingredient_requirements": [],
                "vessel_requirements": [{
                    "record_id": "vessel-line",
                    "alternatives": [{
                        "collection": "general_items",
                        "record_id": "alembic",
                        "name": "Alembic",
                    }],
                }],
                "proficiency_requirements": [],
            })
            self.assertEqual(
                record["vessel_requirements"][0]["alternatives"],
                [{
                    "collection": "general_items",
                    "record_id": "alembic",
                    "name": "Alembic",
                }],
            )

    def test_recipe_formulations_can_change_output_for_replacements(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = RecipeController(self.database(temporary_directory))
            record = controller.create_record({
                "name": "Exploding Potion",
                "skill": "Potions",
                "threshold": 12,
                "tags": [],
                "formulations": [{
                    "record_id": "standard-formulation",
                    "name": "Standard",
                    "output_item": {
                        "collection": "potions",
                        "record_id": "exploding-potion",
                        "name": "Exploding Potion",
                    },
                    "output_quantity": 6,
                    "ingredient_requirements": [{
                        "record_id": "volatile-base",
                        "alternatives": [{
                            "collection": "general_items",
                            "record_id": "standard-base",
                            "name": "Standard Base",
                            "quantity": 1,
                        }, {
                            "collection": "general_items",
                            "record_id": "extra-base",
                            "name": "Extra Explody Base",
                            "quantity": 1,
                            "output_item": {
                                "collection": "potions",
                                "record_id": "extra-explody-potion",
                                "name": "Extra Explody Potion",
                            },
                            "output_quantity_modifier": -1,
                        }],
                    }],
                    "vessel_requirements": [],
                    "proficiency_requirements": [],
                }],
            })
            alternative = record["formulations"][0]["ingredient_requirements"][0]["alternatives"][1]
            self.assertEqual(alternative["output_item"]["name"], "Extra Explody Potion")
            self.assertEqual(alternative["output_quantity_modifier"], -1)
            self.assertEqual(record["output_quantity"], 6)

    def test_duplicate_recipe_copies_formulations_with_a_new_identity(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = RecipeController(self.database(temporary_directory))
            original = controller.create_record({
                "name": "Duplicable Recipe", "skill": "Potions", "threshold": 4,
                "output_item": OUTPUT, "output_quantity": 1,
                "ingredient_requirements": [], "vessel_requirements": [],
                "proficiency_requirements": [], "tags": [],
            })
            duplicate = controller.duplicate_record(original["record_id"])
            self.assertNotEqual(duplicate["record_id"], original["record_id"])
            self.assertEqual(duplicate["name"], "Duplicable Recipe (Copy)")
            self.assertNotEqual(
                duplicate["formulations"][0]["record_id"],
                original["formulations"][0]["record_id"],
            )
            self.assertEqual(
                duplicate["formulations"][0]["output_item"],
                original["formulations"][0]["output_item"],
            )

    def test_formulation_can_require_casting_a_known_spell(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            controller = RecipeController(self.database(temporary_directory))
            record = controller.create_record({
                "name": "Fire-Forged Mixture", "skill": "Potions", "threshold": 8,
                "output_item": OUTPUT, "output_quantity": 1,
                "ingredient_requirements": [], "vessel_requirements": [],
                "proficiency_requirements": [],
                "spell_requirements": [{
                    "record_id": "spell-line",
                    "alternatives": [{
                        "collection": "spells", "record_id": "bluebell-flames",
                        "name": "Bluebell Flames",
                    }],
                }],
            })
            self.assertEqual(
                record["formulations"][0]["spell_requirements"][0]["alternatives"][0]["record_id"],
                "bluebell-flames",
            )

    def test_requirement_dialog_calls_replacements_optional(self):
        source = getsource(RequirementLineDialog)
        self.assertIn("Set required", source)
        self.assertIn("Add replacement", source)
        self.assertNotIn("Add alternative", source)


if __name__ == "__main__":
    unittest.main()
