import random
import unittest

from headmasters_scroll.creatures import (
    adjust_range,
    generate_creature_instance,
    migrate_creature_database,
    normalize_campaign_creature,
    roll_creature_action,
    validate_creature_database,
)


class CreatureEncounterTests(unittest.TestCase):
    def species(self):
        return {
            "record_id": "species-bat",
            "name": "Bat",
            "classification": "X",
            "size": {"low": 1, "high": 2},
            "wound_cap": {"low": 1, "high": 2},
            "magical_resistance": {"low": 0, "high": 1},
            "intelligence": {"low": 1, "high": 3},
            "social_skill": {"low": 1, "high": 2},
            "movement": {"flying": {"enabled": "Yes", "low": 3, "high": 5}},
            "attacks": [{"name": "Bite", "roll": {"low": 2, "high": 6}}],
            "abilities": [{"name": "Echolocation", "roll": {"low": 4, "high": 8}}],
            "parts": [{"name": "Wings", "required_proficiency": "No"}],
        }

    def test_migration_links_families_and_stable_nested_records(self):
        document = {
            "creatures": [self.species(), {**self.species(), "record_id": "species-young-bat", "name": "Young Bat"}],
            "proficiencies": [],
        }
        result = migrate_creature_database(document)
        self.assertEqual(result["proficiencies_created"], 1)
        self.assertEqual(
            document["creatures"][0]["awareness_proficiency_id"],
            document["creatures"][1]["awareness_proficiency_id"],
        )
        self.assertEqual(document["proficiencies"][0]["threshold"], 7)
        self.assertEqual(document["creatures"][0]["parts"][0]["yield"], {"low": 2, "high": 2})
        validate_creature_database(document)
        ids_before = [
            item["record_id"]
            for key in ("attacks", "abilities", "parts")
            for item in document["creatures"][0][key]
        ]
        migrate_creature_database(document)
        ids_after = [
            item["record_id"]
            for key in ("attacks", "abilities", "parts")
            for item in document["creatures"][0][key]
        ]
        self.assertEqual(ids_before, ids_after)

    def test_legacy_aptitude_ranges_match_creature_creator(self):
        self.assertEqual(adjust_range(4, 12, "inept"), (1, 6))
        self.assertEqual(adjust_range(4, 12, "unskilled"), (4, 9))
        self.assertEqual(adjust_range(4, 12, "typical"), (4, 12))
        self.assertEqual(adjust_range(4, 12, "skilled"), (5, 12))
        self.assertEqual(adjust_range(4, 12, "exceptional"), (6, 18))

    def test_generated_values_and_actions_persist_without_rerolling(self):
        document = {"creatures": [self.species()], "proficiencies": []}
        migrate_creature_database(document)
        species = document["creatures"][0]
        placement = {
            "location_id": "location-cave", "floor_id": "", "map_id": "map-cave",
            "x": 0.4, "y": 0.6,
        }
        instance = generate_creature_instance(species, 3, placement, random.Random(42))
        restored = normalize_campaign_creature(instance)
        self.assertEqual(instance["generated"], restored["generated"])
        self.assertEqual(instance["actions"], restored["actions"])
        self.assertEqual(instance["internal_label"], "Bat · 3")
        action = roll_creature_action(restored, restored["actions"][0]["record_id"], random.Random(7))
        self.assertGreaterEqual(action["roll"], action["range"]["low"])
        self.assertLessEqual(action["roll"], action["range"]["high"])

    def test_harvest_pool_and_attempt_contract_rejects_invalid_state(self):
        document = {"creatures": [self.species()], "proficiencies": []}
        migrate_creature_database(document)
        instance = generate_creature_instance(
            document["creatures"][0], 1,
            {"location_id": "location-cave", "floor_id": "", "map_id": "map-cave", "x": 0.5, "y": 0.5},
            random.Random(2),
        )
        instance["harvest_pools"][0]["remaining_quantity"] = 11
        with self.assertRaises(ValueError):
            normalize_campaign_creature(instance)


if __name__ == "__main__":
    unittest.main()
