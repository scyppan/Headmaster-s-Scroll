import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.nature_and_alchemy.preparations.controller import (
    PreparationController,
)
from sections.nature_and_alchemy.preparations.page import PreparationsPage
from sections.nature_and_alchemy.preparations.record_form import PreparationForm


class PreparationTests(unittest.TestCase):
    def test_recipe_view_uses_the_forms_database(self):
        form = MagicMock()
        form.view_container = MagicMock()
        form.views = {}
        form.database = MagicMock(name="database")

        with patch(
            "sections.nature_and_alchemy.preparations.record_form.tk.Frame"
        ) as frame_class, patch(
            "sections.nature_and_alchemy.preparations.record_form.bind_theme"
        ), patch(
            "sections.nature_and_alchemy.preparations.record_form.RecipeEditor"
        ) as recipe_editor_class:
            recipe_view = frame_class.return_value
            recipe_editor = recipe_editor_class.return_value
            PreparationForm.build_recipe_view(form)

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

    def test_preparation_export_is_fully_imported(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        preparation_records = database.get_collection("preparations")
        preparations_by_name = {
            record["name"]: record for record in preparation_records
        }
        required_fields = {
            "record_id",
            "name",
            "skill",
            "brew_time",
            "threshold",
            "required_proficiencies",
            "additional_instructions",
            "description",
            "raw_effect",
            "effect_in_potions",
            "ingredients",
            "dbnotes",
            "last_updated",
        }
        items = [
            item
            for preparation_record in preparation_records
            for item in preparation_record["ingredients"]
        ]

        self.assertEqual(len(preparation_records), 89)
        self.assertEqual(len(preparations_by_name), 89)
        self.assertEqual(
            len({record["record_id"] for record in preparation_records}),
            89,
        )
        self.assertTrue(
            all(
                set(record) == required_fields
                for record in preparation_records
            )
        )
        self.assertTrue(
            all(
                record["threshold"] is None
                or 1 <= record["threshold"] <= 100
                for record in preparation_records
            )
        )
        self.assertEqual(len(items), 115)
        self.assertEqual(len({item["name"] for item in items}), 103)
        self.assertTrue(
            all(
                set(item) == {"name", "type", "quantity"}
                for item in items
            )
        )
        self.assertTrue(all(item["quantity"] == 1 for item in items))
        self.assertEqual(
            preparations_by_name["Boomberry Juice"][
                "required_proficiencies"
            ],
            ["Preparation and Proper Handling of a Boomberry"],
        )
        self.assertTrue(
            all(
                record["additional_instructions"] == ""
                for record in preparation_records
            )
        )
        self.assertEqual(
            preparations_by_name["Powdered Basalt"]["skill"],
            "Alchemy",
        )
        self.assertEqual(
            preparations_by_name["Powdered Basalt"]["threshold"],
            94,
        )
        self.assertEqual(
            [
                item["name"]
                for item in preparations_by_name["Standard Ingredient"][
                    "ingredients"
                ]
            ],
            [
                "Ground Basil",
                "Oregano Leaves",
                "Ground Cinnamon",
                "Whole Cloves",
                "Powdered Garlic",
                "Cayenne Powder",
                "Parsley Flakes",
            ],
        )

    def test_export_placeholders_and_html_are_cleaned(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        preparations_by_name = {
            record["name"]: record
            for record in database.get_collection("preparations")
        }

        self.assertEqual(
            preparations_by_name["Parsley Flakes"]["description"],
            "",
        )
        self.assertEqual(
            preparations_by_name["Dried Thyme"]["raw_effect"],
            "",
        )
        self.assertNotIn(
            "<p>",
            preparations_by_name["Erumpent Horn Fluid"]["description"],
        )

    def test_preparation_page_uses_its_specific_editor(self):
        self.assertEqual(
            PreparationsPage.__mro__[1].__name__,
            "AlchemyFormulaPage",
        )
        self.assertNotEqual(PreparationForm.__name__, "AlchemyFormulaForm")

    def test_controller_crud_preserves_preparation_fields(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                (
                    '{"_database": {"schema_version": 1}, '
                    '"preparations": []}'
                ),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = PreparationController(
                database,
                "preparations",
                "preparation",
            )
            created_record = controller.create_record(
                {
                    "name": "Test Preparation",
                    "skill": "Alchemy",
                    "brew_time": "20 minutes",
                    "threshold": 12,
                    "required_proficiencies": ["Test Proficiency"],
                    "additional_instructions": "Stir clockwise.",
                    "ingredients": [
                        {
                            "name": "First Item",
                            "type": "General Item",
                            "quantity": 4,
                        },
                        {
                            "name": "First Item",
                            "type": "General Item",
                        },
                    ],
                }
            )

            self.assertEqual(created_record["skill"], "Alchemy")
            self.assertEqual(created_record["brew_time"], "20 minutes")
            self.assertEqual(
                created_record["required_proficiencies"],
                ["Test Proficiency"],
            )
            self.assertEqual(
                created_record["additional_instructions"],
                "Stir clockwise.",
            )
            self.assertEqual(len(created_record["ingredients"]), 2)
            self.assertEqual(
                created_record["ingredients"][0]["type"],
                "General Item",
            )
            self.assertEqual(
                created_record["ingredients"][0]["quantity"],
                4,
            )
            self.assertEqual(
                created_record["ingredients"][1]["quantity"],
                1,
            )

            controller.delete_record(created_record["record_id"])

    def test_invalid_preparation_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                (
                    '{"_database": {"schema_version": 1}, '
                    '"preparations": []}'
                ),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = PreparationController(
                database,
                "preparations",
                "preparation",
            )

            with self.assertRaisesRegex(ValueError, "between 1 and 100"):
                controller.create_record(
                    {"name": "Impossible Preparation", "threshold": 101}
                )

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record(
                    {
                        "name": "Blank Item Preparation",
                        "ingredients": [{"name": "   "}],
                    }
                )

            with self.assertRaisesRegex(ValueError, "at least 1"):
                controller.create_record(
                    {
                        "name": "Invalid Quantity Preparation",
                        "ingredients": [
                            {
                                "name": "Rosewater",
                                "type": "Food/Drink",
                                "quantity": 0,
                            }
                        ],
                    }
                )


if __name__ == "__main__":
    unittest.main()
