import tempfile
import unittest
from inspect import signature
from pathlib import Path
from unittest.mock import MagicMock, patch

from core.section_loader import load_sections
from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.nature_and_alchemy.potions.controller import (
    AlchemyFormulaController,
)
from sections.nature_and_alchemy.potions.ingredient_picker import (
    IngredientCatalog,
    IngredientPicker,
    INGREDIENT_FILTERS,
)
from sections.nature_and_alchemy.potions.page import PotionsPage
from sections.nature_and_alchemy.potions.record_form import (
    AlchemyFormulaForm,
)


class PotionTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(PotionsPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_recipe_view_uses_the_forms_database(self):
        form = MagicMock()
        form.view_container = MagicMock()
        form.views = {}
        form.database = MagicMock(name="database")

        with patch(
            "sections.nature_and_alchemy.potions.record_form.tk.Frame"
        ) as frame_class, patch(
            "sections.nature_and_alchemy.potions.record_form.bind_theme"
        ), patch(
            "sections.nature_and_alchemy.potions.record_form.RecipeEditor"
        ) as recipe_editor_class:
            recipe_view = frame_class.return_value
            recipe_editor = recipe_editor_class.return_value
            AlchemyFormulaForm.build_recipe_view(form)

        recipe_editor_class.assert_called_once_with(
            recipe_view,
            form.database,
            form.handle_field_change,
        )
        recipe_editor.grid.assert_called_once_with(
            row=0,
            column=0,
            sticky="nsew",
        )

    def test_combined_workspace_hides_standalone_preparations(self):
        sections = load_sections()
        section_keys = [section.key for section in sections]

        self.assertIn("potions", section_keys)
        self.assertNotIn("preparations", section_keys)

    def test_potion_export_is_fully_imported(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        potion_records = database.get_collection("potions")
        preparation_records = database.get_collection("preparations")
        potions_by_name = {
            record["name"]: record for record in potion_records
        }
        required_fields = {
            "record_id",
            "name",
            "inventor",
            "tradition",
            "brew_time",
            "threshold",
            "description",
            "raw_effect",
            "effect_in_other_potions",
            "ingredients",
            "required_proficiencies",
            "additional_instructions",
            "dbnotes",
            "last_updated",
        }
        ingredients = [
            ingredient
            for potion_record in potion_records
            for ingredient in potion_record["ingredients"]
        ]

        self.assertEqual(len(potion_records), 150)
        self.assertEqual(len(potions_by_name), 150)
        self.assertEqual(
            len({record["record_id"] for record in potion_records}),
            150,
        )
        self.assertTrue(
            all(set(record) == required_fields for record in potion_records)
        )
        self.assertTrue(
            all(
                1 <= record["threshold"] <= 100
                for record in potion_records
            )
        )
        self.assertEqual(len(ingredients), 361)
        self.assertEqual(
            len({ingredient["name"] for ingredient in ingredients}),
            170,
        )
        self.assertTrue(
            all(
                set(ingredient) == {"name", "type", "quantity"}
                for ingredient in ingredients
            )
        )
        self.assertTrue(
            all(ingredient["quantity"] == 1 for ingredient in ingredients)
        )
        self.assertTrue(
            all(
                ingredient["type"]
                in {
                    "Plant Part",
                    "Creature Part",
                    "Preparation",
                    "Potion",
                    "Food/Drink",
                    "General Item",
                }
                for ingredient in ingredients
            )
        )
        self.assertTrue(
            all(
                record["required_proficiencies"] == []
                for record in potion_records
            )
        )
        self.assertTrue(
            all(
                record["additional_instructions"] == ""
                for record in potion_records
            )
        )
        self.assertEqual(len(preparation_records), 89)
        self.assertEqual(
            potions_by_name["Penelope's Prolonging Potion"]["inventor"],
            "Penelope Evans",
        )
        self.assertEqual(
            potions_by_name["Penelope's Prolonging Potion"]["threshold"],
            13,
        )
        self.assertEqual(
            [
                ingredient["name"]
                for ingredient in potions_by_name[
                    "Penelope's Prolonging Potion"
                ]["ingredients"]
            ],
            [
                "Welwitschia Leaf Oils",
                "Wiggentree Bark",
                "Sopophorous Bean Powder",
                "Basilisk Venom",
                "Bloodroot Roots",
                "Standard Potioning Water",
            ],
        )
        self.assertEqual(
            [
                ingredient["name"]
                for ingredient in potions_by_name["Crystalized Water"][
                    "ingredients"
                ]
            ],
            [
                "Standard Potioning Water",
                "Bonemeal",
                "Flouridated Muggle Water",
                "Bonemeal",
            ],
        )

    def test_controller_crud_keeps_collections_separate(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                (
                    '{"_database": {"schema_version": 1}, '
                    '"potions": [], "preparations": []}'
                ),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            potion_controller = AlchemyFormulaController(
                database,
                "potions",
                "potion",
            )
            preparation_controller = AlchemyFormulaController(
                database,
                "preparations",
                "preparation",
            )
            potion = potion_controller.create_record(
                {
                    "name": "Test Potion",
                    "brew_time": "3 hours",
                    "threshold": 10,
                    "required_proficiencies": ["Potion Making"],
                    "additional_instructions": "Keep away from sunlight.",
                    "ingredients": [
                        {
                            "name": "Test Ingredient",
                            "type": "Plant Part",
                            "quantity": 3,
                        },
                        {
                            "name": "Test Ingredient",
                            "type": "Plant Part",
                        },
                    ],
                }
            )
            preparation = preparation_controller.create_record(
                {
                    "name": "Test Preparation",
                    "threshold": 12,
                }
            )

            self.assertIsNotNone(
                potion_controller.get_record(potion["record_id"])
            )
            self.assertEqual(
                potion["ingredients"][0]["type"],
                "Plant Part",
            )
            self.assertEqual(potion["ingredients"][0]["quantity"], 3)
            self.assertEqual(potion["ingredients"][1]["quantity"], 1)
            self.assertEqual(potion["brew_time"], "3 hours")
            self.assertEqual(
                potion["required_proficiencies"],
                ["Potion Making"],
            )
            self.assertEqual(
                potion["additional_instructions"],
                "Keep away from sunlight.",
            )
            self.assertIsNone(
                preparation_controller.get_record(potion["record_id"])
            )
            self.assertIsNotNone(
                preparation_controller.get_record(
                    preparation["record_id"]
                )
            )

            potion_controller.delete_record(potion["record_id"])
            preparation_controller.delete_record(preparation["record_id"])

    def test_invalid_thresholds_and_blank_ingredients_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "potions": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = AlchemyFormulaController(
                database,
                "potions",
                "potion",
            )

            with self.assertRaisesRegex(ValueError, "between 1 and 100"):
                controller.create_record(
                    {"name": "Impossible Potion", "threshold": 101}
                )

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record(
                    {
                        "name": "Blank Ingredient Potion",
                        "ingredients": [{"name": "   "}],
                    }
                )

            with self.assertRaisesRegex(ValueError, "Unknown ingredient type"):
                controller.create_record(
                    {
                        "name": "Invalid Ingredient Type Potion",
                        "ingredients": [
                            {
                                "name": "Mystery Ingredient",
                                "type": "Mystery",
                            }
                        ],
                    }
                )

            with self.assertRaisesRegex(ValueError, "at least 1"):
                controller.create_record(
                    {
                        "name": "Invalid Quantity Potion",
                        "ingredients": [
                            {
                                "name": "Rosewater",
                                "type": "Food/Drink",
                                "quantity": 0,
                            }
                        ],
                    }
                )

            with self.assertRaisesRegex(
                ValueError,
                "Duplicate required proficiency",
            ):
                controller.create_record(
                    {
                        "name": "Duplicate Proficiency Potion",
                        "required_proficiencies": [
                            "Potion Making",
                            "potion making",
                        ],
                    }
                )

    def test_ingredient_catalog_combines_sources_and_fuzzy_searches(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        catalog = IngredientCatalog(database)

        self.assertEqual(len(catalog.entries), 1304)
        self.assertEqual(
            catalog.search("unicorn hrn")[0]["name"],
            "Ground Unicorn Horn",
        )
        self.assertEqual(
            catalog.search("boombery juse")[0]["name"],
            "Boomberry Juice",
        )
        self.assertEqual(
            catalog.search("boombery juse")[0]["type"],
            "Preparation",
        )

    def test_ingredient_catalog_filters_each_supported_type(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        catalog = IngredientCatalog(database)
        filter_types = {
            ingredient_type
            for button_text, ingredient_type, button_width
            in INGREDIENT_FILTERS
        }

        self.assertEqual(
            filter_types,
            {
                None,
                "Creature Part",
                "Plant Part",
                "Food/Drink",
                "Preparation",
                "Potion",
                "General Item",
            },
        )

        for ingredient_type in filter_types - {None}:
            filtered_entries = catalog.search("", ingredient_type)
            self.assertTrue(filtered_entries)
            self.assertTrue(
                all(
                    entry["type"] == ingredient_type
                    for entry in filtered_entries
                )
            )

    def test_ingredient_rows_use_bullets_instead_of_numbers(self):
        ingredient_editor_path = (
            Path(__file__).parents[1]
            / "sections"
            / "nature_and_alchemy"
            / "potions"
            / "ingredients_editor.py"
        )
        ingredient_editor_source = ingredient_editor_path.read_text(
            encoding="utf-8"
        )

        self.assertIn('"• "', ingredient_editor_source)
        self.assertNotIn(
            'f"{ingredient_index + 1}. "',
            ingredient_editor_source,
        )

    def test_picker_populates_the_listbox_in_one_bulk_insert(self):
        picker = MagicMock()
        picker.refresh_job = None
        picker.selected_key = None
        picker.active_filter_type = None
        picker.search_value.get.return_value = ""
        picker.catalog.entries = [
            {
                "key": "plant part::a",
                "type": "Plant Part",
                "name": "A",
            },
            {
                "key": "creature part::b",
                "type": "Creature Part",
                "name": "B",
            },
        ]
        picker.catalog.entries_by_type = {}
        picker.catalog.search.return_value = picker.catalog.entries

        IngredientPicker.refresh_results(picker)

        picker.listbox.insert.assert_called_once_with(
            "end",
            "[Plant Part] A",
            "[Creature Part] B",
        )


if __name__ == "__main__":
    unittest.main()
