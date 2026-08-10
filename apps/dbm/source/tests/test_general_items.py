import tempfile
import unittest
from inspect import getsource, signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.items.general_items.constants import GENERAL_ITEM_TYPES
from sections.items.general_items.controller import GeneralItemController
from sections.items.general_items.page import GeneralItemsPage
from sections.items.general_items.record_form import GeneralItemForm


class GeneralItemTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(GeneralItemsPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_conversion_preserves_unique_source_records_and_bonuses(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("general_items")
        records_by_name = {
            record["name"]: record
            for record in records
        }
        required_fields = {
            "record_id",
            "name",
            "type",
            "has_magical_effects",
            "description",
            "bonuses",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(records), 224)
        self.assertEqual(len(records_by_name), 224)
        self.assertTrue(
            all(set(record) == required_fields for record in records)
        )
        self.assertEqual(
            records_by_name["Deeply Treated Ash Clast"]["record_id"],
            "general_item_24895",
        )
        self.assertEqual(
            records_by_name["Yajirushi Archer Broom"]["bonuses"],
            [
                {
                    "type": "Skill",
                    "target": "Perception",
                    "amount": 2,
                }
            ],
        )
        self.assertEqual(
            records_by_name["Varápidos Broom"]["bonuses"],
            [
                {
                    "type": "Characteristic",
                    "target": "Agility",
                    "amount": 3,
                }
            ],
        )
        self.assertEqual(
            records_by_name["Vitriol"]["has_magical_effects"],
            "No",
        )
        self.assertEqual(records_by_name["Vitriol"]["type"], "Alchemical")
        self.assertEqual(records_by_name["Firebolt Broom"]["type"], "Broom")
        self.assertEqual(records_by_name["Lute"]["type"], "Instrument")
        self.assertTrue(
            {record["type"] for record in records}.issubset(
                set(GENERAL_ITEM_TYPES)
            )
        )

    def test_all_requested_alchemical_items_are_classified(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records_by_name = {
            record["name"]: record
            for record in database.get_collection("general_items")
        }
        requested_names = {
            "Kohl", "Gold", "Silver", "Abāru", "Copper", "Molochitis",
            "Firestone", "Blackstone", "Lodestone", "Cassiterite",
            "Cinnabar", "Starstone", "Callais", "Yù", "Chalchihuitl",
            "Jade", "Itztli", "Dragonglass", "Kokuseki", "Bloodstone",
            "Serpentstone", "Quartz", "Amethyst", "Jamunia",
            "Chalcedony", "Realgar", "Brimstone", "Orpiment", "Iztatl",
            "Amole", "Emesallu", "Natron", "Stypticstone", "Shabb",
            "Xiaoshi", "Shora", "Saltpeter", "Nūshādir", "Ammoniac",
            "Būraq", "Tinkal", "Thunderstone", "Zaj", "Vitriol",
            "Shinju", "Pearl", "Durr", "Zhenzhu", "Coral", "Thokcha",
            "Leklai", "Xirang", "Aether", "Phlogiston", "Jet", "Esir",
            "Cintāmaṇi", "Syamantaka", "Parasmani", "Carbuncle",
            "Yada Tasi", "Solarsteinn", "Adderstone", "Alabaster",
            "Artsakhstones", "Jasper",
        }

        self.assertTrue(requested_names.issubset(records_by_name))
        self.assertTrue(
            all(
                records_by_name[item_name]["type"] == "Alchemical"
                for item_name in requested_names
            )
        )

    def test_type_is_a_fixed_dropdown(self):
        form_source = getsource(GeneralItemForm)

        self.assertIn("values=GENERAL_ITEM_TYPES", form_source)
        self.assertIn('text="Type"', form_source)

    def test_controller_crud_saves_to_json(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"general_items": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = GeneralItemController(database)
            created_record = controller.create_record(
                {
                    "name": "Test General Item",
                    "type": "Tool & Supply",
                    "has_magical_effects": "Yes",
                    "description": "A test item.",
                    "bonuses": [
                        {
                            "type": "Skill",
                            "target": "Perception",
                            "amount": 2,
                        }
                    ],
                    "dbnotes": "Created by a test.",
                }
            )

            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {"description": "An updated test item."},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = GeneralItemController(reloaded_database)
            self.assertEqual(
                reloaded_controller.get_record(record_id)["description"],
                "An updated test item.",
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))

    def test_duplicate_names_ignore_case_and_extra_spacing(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"general_items": []}',
                encoding="utf-8",
            )

            database = JsonDatabase(database_path)
            database.load()
            controller = GeneralItemController(database)
            controller.create_record(
                {"name": "Test General Item", "type": "Other"}
            )

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record(
                    {"name": "  test   general ITEM  ", "type": "Other"}
                )

    def test_invalid_item_type_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"general_items": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = GeneralItemController(database)

            with self.assertRaisesRegex(ValueError, "defined type"):
                controller.create_record(
                    {"name": "Invalid Item", "type": "Mystery"}
                )


if __name__ == "__main__":
    unittest.main()
