import tempfile
import unittest
from collections import Counter
from inspect import getsource, signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.magic.spells.constants import (
    SPELL_SKILLS,
    SPELL_SUBTYPE_DESCRIPTIONS,
    SPELL_SUBTYPES,
)
from sections.magic.spells.controller import SpellController
from sections.magic.spells.filter_dialog import SpellFilterDialog
from sections.magic.spells.page import SpellsPage
from sections.magic.spells.record_form import SpellForm
from sections.magic.spells.record_list import SpellList
from sections.magic.traditions import TRADITIONS, TRADITIONS_PATH


class SpellTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(SpellsPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_spell_export_is_fully_imported(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        spell_records = database.get_collection("spells")
        required_fields = {
            "record_id",
            "name",
            "incantation",
            "tradition",
            "skill",
            "subtype",
            "threshold",
            "description",
            "history",
            "rationale",
            "tags",
            "dbnotes",
            "last_updated",
        }
        records_by_id = {
            record["record_id"]: record for record in spell_records
        }
        name_counts = Counter(
            record["name"].casefold() for record in spell_records
        )

        self.assertEqual(len(spell_records), 491)
        self.assertEqual(len(records_by_id), 491)
        self.assertEqual(len(name_counts), 489)
        self.assertEqual(name_counts["enhanced trace placement"], 2)
        self.assertEqual(name_counts["magical jinx"], 2)
        self.assertTrue(
            all(set(record) == required_fields for record in spell_records)
        )
        self.assertTrue(
            all(1 <= record["threshold"] <= 100 for record in spell_records)
        )
        self.assertTrue(
            all(record["subtype"] in SPELL_SUBTYPES for record in spell_records)
        )
        self.assertTrue(all(record["tags"] == [] for record in spell_records))
        self.assertNotIn("spell_subtypes", database.data)
        self.assertNotIn("traditions", database.data)
        self.assertEqual(
            Counter(record["skill"] for record in spell_records),
            Counter(
                {
                    "Charms": 185,
                    "Transfiguration": 166,
                    "Defense": 79,
                    "Dark Arts": 61,
                }
            ),
        )
        self.assertEqual(
            records_by_id["spell_18798"]["description"],
            (
                "Adheres one object to another as if they had been glued. "
                "Wears off after approximately one hour. Headmaster may add "
                "penalties for adhering multiple larger objects."
            ),
        )
        self.assertEqual(
            records_by_id["spell_19129"]["incantation"],
            "Vestigient",
        )
        self.assertEqual(records_by_id["spell_19129"]["threshold"], 37)
        self.assertEqual(records_by_id["spell_28696"]["skill"], "Defense")
        self.assertEqual(records_by_id["spell_28700"]["skill"], "Dark Arts")
        self.assertNotIn(
            "<p>",
            records_by_id["spell_19250"]["description"],
        )
        self.assertNotIn(
            "<em>",
            records_by_id["spell_19053"]["rationale"],
        )

    def test_controller_crud_allows_distinct_same_name_spells(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "spells": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = SpellController(database)
            first_spell = controller.create_record(
                {
                    "name": "Shared Name",
                    "incantation": "Prima",
                    "skill": "Charms",
                    "subtype": "Utility",
                    "threshold": 7,
                    "tags": ["Household", "Utility"],
                }
            )
            second_spell = controller.create_record(
                {
                    "name": "Shared Name",
                    "incantation": "Secunda",
                    "skill": "Defense",
                    "subtype": "Shielding",
                    "threshold": 12,
                }
            )

            self.assertNotEqual(
                first_spell["record_id"],
                second_spell["record_id"],
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record(
                    {
                        "name": " shared  name ",
                        "incantation": "PRIMA",
                        "skill": "charms",
                        "subtype": "utility",
                        "threshold": 9,
                    }
                )

            controller.update_record(
                second_spell["record_id"],
                {"description": "Updated rules."},
            )
            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = SpellController(reloaded_database)

            self.assertEqual(
                reloaded_controller.get_record(second_spell["record_id"])[
                    "description"
                ],
                "Updated rules.",
            )
            self.assertEqual(first_spell["tags"], ["Household", "Utility"])

            reloaded_controller.delete_record(first_spell["record_id"])
            self.assertIsNone(
                reloaded_controller.get_record(first_spell["record_id"])
            )

    def test_invalid_spell_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, "spells": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = SpellController(database)

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record(
                    {
                        "skill": "Charms",
                        "subtype": "Utility",
                        "threshold": 7,
                    }
                )

            with self.assertRaisesRegex(ValueError, "must have a skill"):
                controller.create_record(
                    {
                        "name": "Nameless Skill Spell",
                        "subtype": "Utility",
                        "threshold": 7,
                    }
                )

            with self.assertRaisesRegex(ValueError, "between 1 and 100"):
                controller.create_record(
                    {
                        "name": "Impossible Spell",
                        "skill": "Charms",
                        "subtype": "Utility",
                        "threshold": 101,
                    }
                )

            with self.assertRaisesRegex(ValueError, "defined subtype"):
                controller.create_record(
                    {
                        "name": "Undefined Classification Spell",
                        "skill": "Charms",
                        "subtype": "Uncatalogued",
                        "threshold": 7,
                    }
                )

            with self.assertRaisesRegex(ValueError, "defined skill"):
                controller.create_record(
                    {
                        "name": "Unclassified Skill Spell",
                        "skill": "Potions",
                        "subtype": "Utility",
                        "threshold": 7,
                    }
                )

            with self.assertRaisesRegex(ValueError, "Duplicate spell tag"):
                controller.create_record(
                    {
                        "name": "Repeated Tag Spell",
                        "skill": "Charms",
                        "subtype": "Utility",
                        "threshold": 7,
                        "tags": ["Movement", " movement "],
                    }
                )

    def test_spell_filters_combine_skill_tradition_threshold_and_tags(self):
        matching_spell = {
            "name": "Shielded Step",
            "skill": "Defense",
            "subtype": "Shielding",
            "tradition": "British",
            "threshold": 18,
            "tags": ["Movement", "Shield"],
        }
        filters = {
            "skills": ("Defense", "Charms"),
            "subtypes": ("Shielding", "Repelling"),
            "traditions": ("British", "Greek"),
            "minimum_threshold": 15,
            "maximum_threshold": 20,
            "tags": ("Movement",),
        }

        self.assertTrue(
            SpellList.record_matches_filters(matching_spell, filters)
        )
        self.assertFalse(
            SpellList.record_matches_filters(
                {**matching_spell, "skill": "Dark Arts"},
                filters,
            )
        )
        self.assertFalse(
            SpellList.record_matches_filters(
                {**matching_spell, "threshold": 21},
                filters,
            )
        )
        self.assertFalse(
            SpellList.record_matches_filters(
                {**matching_spell, "subtype": "Hex"},
                filters,
            )
        )
        self.assertFalse(
            SpellList.record_matches_filters(
                {**matching_spell, "tradition": "Mayan"},
                filters,
            )
        )
        self.assertFalse(
            SpellList.record_matches_filters(
                {**matching_spell, "tags": ["Attack"]},
                filters,
            )
        )

    def test_spell_search_text_includes_classification_and_tags(self):
        search_text = SpellList.build_search_text(
            {
                "name": "Quiet Passage",
                "incantation": "Tacitus",
                "tradition": "European",
                "skill": "Charms",
                "subtype": "Utility",
                "threshold": 14,
                "tags": ["Stealth", "Movement"],
            }
        )

        self.assertIn("charms", search_text)
        self.assertIn("14", search_text)
        self.assertIn("stealth", search_text)

    def test_spell_list_uses_requested_two_line_display(self):
        display_text = SpellList.build_display_text(
            {
                "name": "Quiet Passage",
                "incantation": "Tacitus",
                "skill": "Charms",
                "threshold": 14,
                "subtype": "Concealing",
            }
        )

        self.assertEqual(
            display_text,
            "Quiet Passage (Tacitus)\nCharms 14 (Concealing)",
        )

    def test_spell_subtype_definitions_are_fixed_in_spells_code(self):
        self.assertEqual(
            SPELL_SUBTYPES,
            (
                "Hex",
                "Curse",
                "Blood Magic",
                "Controlling",
                "Banishing",
                "Mental",
                "Concealing",
                "Utility",
                "Enchanting",
                "Alteration",
                "Healing",
                "Enhancing",
                "Environmental",
                "Jinx",
                "Shielding",
                "Repelling",
                "Counterspell",
            ),
        )
        self.assertEqual(
            SPELL_SUBTYPE_DESCRIPTIONS["Banishing"],
            "These spells cast spirits or beings away from an area.",
        )
        self.assertEqual(
            set(SPELL_SUBTYPE_DESCRIPTIONS),
            set(SPELL_SUBTYPES),
        )

    def test_spell_skills_are_fixed_in_spells_code(self):
        self.assertEqual(
            SPELL_SKILLS,
            (
                "Charms",
                "Transfiguration",
                "Defense",
                "Dark Arts",
            ),
        )

        form_source = getsource(SpellForm.__init__)
        self.assertIn("values=SPELL_SKILLS", form_source)
        self.assertNotIn("self.skill_field = LabeledEntry", form_source)

    def test_traditions_live_in_the_data_text_file(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        spell_traditions = {
            record["tradition"]
            for record in database.get_collection("spells")
            if record["tradition"]
        }

        self.assertEqual(
            TRADITIONS,
            (
                "British",
                "Chinese",
                "Egyptian",
                "Greek",
                "Mayan",
                "Mesopotamian",
                "Roman",
                "Spanish",
            ),
        )
        self.assertEqual(
            TRADITIONS_PATH.read_text(encoding="utf-8").splitlines(),
            list(TRADITIONS),
        )
        self.assertTrue(spell_traditions.issubset(set(TRADITIONS)))
        self.assertNotIn("traditions", database.data)

        form_source = getsource(SpellForm.__init__)
        self.assertIn("values=(\"\", *TRADITIONS)", form_source)
        self.assertNotIn("self.tradition_field = LabeledEntry", form_source)

    def test_spell_filter_includes_traditions(self):
        dialog_source = getsource(SpellFilterDialog)

        self.assertIn("self.tradition_values = list(TRADITIONS)", dialog_source)
        self.assertIn("self.tradition_listbox", dialog_source)
        self.assertIn('"traditions": self.get_selected_values', dialog_source)

    def test_subtype_filter_uses_two_column_checkboxes(self):
        dialog_source = getsource(SpellFilterDialog.__init__)

        self.assertIn("self.subtype_variables = {}", dialog_source)
        self.assertIn("subtype_checkbox = tk.Checkbutton", dialog_source)
        self.assertIn("column=subtype_column", dialog_source)
        self.assertIn('uniform="subtype_columns"', dialog_source)
        self.assertNotIn("self.subtype_listbox", dialog_source)


if __name__ == "__main__":
    unittest.main()
