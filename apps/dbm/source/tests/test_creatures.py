import tempfile
import unittest
from inspect import signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.nature_and_alchemy.creatures import constants as creature_constants
from sections.nature_and_alchemy.creatures.controller import (
    CreatureController,
)
from sections.nature_and_alchemy.creatures.page import CreaturesPage
from shared.wounds import (
    WOUND_AMOUNT_LIMITS,
    WOUND_SEVERITIES,
    WOUND_TYPES,
)


class CreatureTests(unittest.TestCase):
    def test_page_accepts_database_from_content_host(self):
        constructor_parameters = tuple(
            signature(CreaturesPage.__init__).parameters
        )

        self.assertEqual(
            constructor_parameters,
            ("self", "parent", "database"),
        )

    def test_fixed_wound_taxonomy_has_thirteen_types_and_three_severities(self):
        self.assertFalse(hasattr(creature_constants, "WOUND_TYPES"))
        self.assertFalse(hasattr(creature_constants, "WOUND_SEVERITIES"))
        self.assertEqual(
            WOUND_TYPES,
            (
                "Cuts/Scratches",
                "Abrasions/Scrapes",
                "Slashes/Gashes",
                "Punctures/Piercing",
                "Gouges",
                "Burns",
                "Disease/Toxic",
                "Blunt force/Crushing",
                "Despairing/Depressing",
                "Terror/Anxiety-inducing",
                "Sanity-shaking",
                "Eruption/Explosion",
                "Vital",
            ),
        )
        self.assertEqual(
            WOUND_SEVERITIES,
            ("Light", "Medium", "Heavy"),
        )
        self.assertEqual(
            WOUND_AMOUNT_LIMITS,
            {"Light": 2, "Medium": 1, "Heavy": 50},
        )

    def test_in_situ_instinct_choices_are_fixed(self):
        self.assertEqual(
            creature_constants.INSTINCT_STANCES,
            (
                "Wary",
                "Hostile",
                "Docile",
                "Cheerful",
                "Curious",
                "Bold",
                "Skittish",
                "Aloof",
                "Uninterested",
                "Territorial",
            ),
        )

    def test_creature_binary_fields_use_no_as_the_default(self):
        self.assertEqual(
            creature_constants.YES_NO_ONLY,
            ("No", "Yes"),
        )
        self.assertEqual(
            creature_constants.INSTINCT_INTENTIONS,
            (
                "Hide",
                "Attack",
                "Investigate",
                "Flee",
                "Threaten",
                "Rally",
                "Freeze",
                "Defend",
            ),
        )

    def test_all_creature_parts_are_children_of_their_creatures(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("creatures")
        records_by_name = {
            record["name"]: record
            for record in records
        }
        required_fields = {
            "record_id",
            "name",
            "creature_type",
            "classification",
            "wound_cap",
            "size",
            "magical",
            "magical_resistance",
            "sentient",
            "intelligence",
            "has_human_social_skills",
            "social_skill",
            "can_be_lured",
            "can_be_tamed",
            "can_bond",
            "additional_social_rules",
            "movement",
            "in_situ_instinct",
            "attacks",
            "abilities",
            "parts",
            "tags",
            "description",
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
        creature_parts = [
            part
            for record in records
            for part in record["parts"]
        ]

        self.assertFalse(database.has_container("creature_parts"))
        self.assertEqual(len(records), 245)
        self.assertEqual(len(records_by_name), 245)
        self.assertEqual(
            len({record["record_id"] for record in records}),
            245,
        )
        self.assertTrue(
            all(set(record) == required_fields for record in records)
        )
        self.assertTrue(
            all(
                record["in_situ_instinct"]
                == {"stance": [], "intention": []}
                for record in records
            )
        )
        self.assertTrue(
            all(
                record[field_name] in creature_constants.YES_NO_ONLY
                for record in records
                for field_name in (
                    "sentient",
                    "has_human_social_skills",
                    "can_be_lured",
                    "can_be_tamed",
                    "can_bond",
                )
            )
        )
        self.assertTrue(
            all(
                movement_value["enabled"]
                in creature_constants.YES_NO_ONLY
                for record in records
                for movement_value in record["movement"].values()
            )
        )
        self.assertTrue(
            all(
                movement_value["enabled"] == "Yes"
                or (
                    movement_value["low"] is None
                    and movement_value["high"] is None
                )
                for record in records
                for movement_value in record["movement"].values()
            )
        )
        self.assertEqual(
            sum(len(record["attacks"]) for record in records),
            44,
        )
        self.assertEqual(
            sum(len(record["abilities"]) for record in records),
            29,
        )
        self.assertEqual(
            sum(len(record["parts"]) for record in records),
            578,
        )
        self.assertEqual(
            len({part["name"].casefold() for part in creature_parts}),
            440,
        )
        self.assertTrue(
            all(
                set(part) == required_part_fields
                for part in creature_parts
            )
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
                for record in records
            )
        )
        self.assertEqual(
            sum(
                len(attack["immediate_damage"])
                for record in records
                for attack in record["attacks"]
            ),
            27,
        )
        self.assertEqual(
            sum(
                len(attack["damage_over_time"])
                for record in records
                for attack in record["attacks"]
            ),
            7,
        )

        clutter_leader = records_by_name["Clutter Leader"]
        self.assertEqual(clutter_leader["record_id"], "creature_1399")
        self.assertEqual(
            clutter_leader["attacks"][0]["immediate_damage"],
            [
                {
                    "type": "Gouges",
                    "severity": "Heavy",
                    "amount": 2,
                }
            ],
        )
        self.assertEqual(
            clutter_leader["attacks"][0]["damage_over_time"],
            [
                {
                    "type": "Disease/Toxic",
                    "severity": "Medium",
                    "amount": 1,
                }
            ],
        )
        self.assertEqual(
            [
                ability["name"]
                for ability in records_by_name["Niffler"]["abilities"]
            ],
            ["Treasure Hunter", "Skilled Thief", "Deep Pockets", "Squeeze"],
        )
        self.assertEqual(records_by_name["Raven"]["attacks"], [])
        self.assertTrue(
            all(
                part["required_proficiency"] == "No"
                for record in records
                for part in record["parts"]
            )
        )
        self.assertEqual(
            records_by_name["Very Small Acromantula"]["parts"][0],
            {
                "name": "Acromantula Venom",
                "required_proficiency": "No",
                "description": (
                    "A powerful venom that can cause significant damage "
                    "even to very large creatures."
                ),
                "raw_effects": "",
                "effect_in_potions": "",
            },
        )
        self.assertEqual(
            [part["name"] for part in records_by_name["Krup"]["parts"]],
            ["Cropped Krup Tail"],
        )
        self.assertEqual(
            [part["name"] for part in records_by_name["Demon"]["parts"]],
            ["Demonic Milk"],
        )
        self.assertEqual(
            [part["name"] for part in records_by_name["Skeleton"]["parts"]],
            ["Bonemeal"],
        )
        self.assertIn(
            "Foul Feathers",
            [part["name"] for part in records_by_name["Pheasant"]["parts"]],
        )
        self.assertTrue(
            all(
                "<" not in record["description"]
                and ">" not in record["description"]
                for record in records
            )
        )
        self.assertTrue(
            all(
                "<" not in part[field_name]
                and ">" not in part[field_name]
                for part in creature_parts
                for field_name in (
                    "description",
                    "raw_effects",
                    "effect_in_potions",
                )
            )
        )

    def test_controller_crud_saves_nested_records(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"creatures": [], "proficiencies": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = CreatureController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Creature",
                    "creature_type": "Beast",
                    "classification": "XXX",
                    "magical": "{undefined}",
                    "sentient": "No",
                    "has_human_social_skills": "No",
                    "can_be_lured": "No",
                    "can_be_tamed": "No",
                    "can_bond": "No",
                    "wound_cap": {"low": 1, "high": 4},
                    "size": {"low": 1, "high": 2},
                    "intelligence": {"low": 2, "high": 4},
                    "social_skill": {"low": None, "high": None},
                    "in_situ_instinct": {
                        "stance": ["Wary", "Territorial"],
                        "intention": ["Investigate", "Defend"],
                    },
                    "movement": {
                        "land": {"enabled": "Yes", "low": 2, "high": 4},
                        "water": {
                            "enabled": "No",
                            "low": None,
                            "high": None,
                        },
                        "air": {
                            "enabled": "No",
                            "low": None,
                            "high": None,
                        },
                    },
                    "attacks": [
                        {
                            "name": "Test Bite",
                            "roll": {"low": 1, "high": 3},
                            "description": "A testing bite.",
                            "immediate_damage": [
                                {
                                    "type": "Punctures/Piercing",
                                    "amount": 1,
                                    "severity": "Light",
                                }
                            ],
                            "damage_over_time": [],
                        }
                    ],
                    "abilities": [
                        {
                            "name": "Test Ability",
                            "roll": {"low": None, "high": None},
                            "description": "A testing ability.",
                            "immediate_damage": [],
                            "damage_over_time": [],
                        }
                    ],
                    "parts": [
                        {
                            "name": "Test Scale",
                            "required_proficiency": "No",
                            "description": "A durable testing scale.",
                            "raw_effects": "Adds testing resilience.",
                            "effect_in_potions": "Stabilizes test mixtures.",
                        }
                    ],
                    "tags": ["Volcanic", "Winged-Horse"],
                }
            )
            record_id = created_record["record_id"]
            controller.update_record(
                record_id,
                {**created_record, "classification": "XXXX"},
            )

            reloaded_database = JsonDatabase(database_path)
            reloaded_database.load()
            reloaded_controller = CreatureController(reloaded_database)
            self.assertEqual(
                reloaded_controller.get_record(record_id)["classification"],
                "XXXX",
            )
            self.assertEqual(
                reloaded_controller.get_record(record_id)["attacks"][0]["name"],
                "Test Bite",
            )
            self.assertEqual(
                reloaded_controller.get_record(record_id)["tags"],
                ["Volcanic", "Winged-Horse"],
            )
            self.assertEqual(
                reloaded_controller.get_record(record_id)[
                    "in_situ_instinct"
                ],
                {
                    "stance": ["Wary", "Territorial"],
                    "intention": ["Investigate", "Defend"],
                },
            )
            self.assertEqual(
                reloaded_controller.get_record(record_id)["parts"][0][
                    "effect_in_potions"
                ],
                "Stabilizes test mixtures.",
            )

            reloaded_controller.delete_record(record_id)
            self.assertIsNone(reloaded_controller.get_record(record_id))

    def test_limits_duplicates_and_invalid_wounds_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"creatures": [], "proficiencies": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = CreatureController(database)
            controller.create_record({"name": "Test Creature"})

            with self.assertRaisesRegex(ValueError, "already exists"):
                controller.create_record({"name": "  test   creature  "})

            with self.assertRaisesRegex(ValueError, "Wound Cap High"):
                controller.create_record(
                    {
                        "name": "Oversized Cap",
                        "wound_cap": {"low": 1, "high": 31},
                    }
                )

            with self.assertRaisesRegex(ValueError, "Low cannot"):
                controller.create_record(
                    {
                        "name": "Backwards Range",
                        "size": {"low": 4, "high": 2},
                    }
                )

            with self.assertRaisesRegex(ValueError, "amount must be"):
                controller.create_record(
                    {
                        "name": "Too Much Medium Damage",
                        "attacks": [
                            {
                                "name": "Invalid Attack",
                                "roll": {"low": 1, "high": 2},
                                "immediate_damage": [
                                    {
                                        "type": "Gouges",
                                        "severity": "Medium",
                                        "amount": 2,
                                    }
                                ],
                                "damage_over_time": [],
                            }
                        ],
                    }
                )

            with self.assertRaisesRegex(ValueError, "Unknown wound type"):
                controller.create_record(
                    {
                        "name": "Another Creature",
                        "attacks": [
                            {
                                "name": "Invalid Attack",
                                "roll": {"low": 1, "high": 2},
                                "immediate_damage": [
                                    {
                                        "type": "Changing Wound",
                                        "severity": "Light",
                                        "amount": 1,
                                    }
                                ],
                                "damage_over_time": [],
                            }
                        ],
                    }
                )

            with self.assertRaisesRegex(
                ValueError,
                "Unknown instinct stance",
            ):
                controller.create_record(
                    {
                        "name": "Unknown Instinct Creature",
                        "in_situ_instinct": {
                            "stance": ["Confused"],
                            "intention": [],
                        },
                    }
                )


if __name__ == "__main__":
    unittest.main()
