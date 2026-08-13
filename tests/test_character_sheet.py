import unittest

from headmasters_scroll.character_rolls import perform_character_roll
from headmasters_scroll.character_sheet import build_character_sheet, effective_campaign_events


class CharacterSheetTests(unittest.TestCase):
    def setUp(self):
        self.person = {
            "record_id": "person-1",
            "displayed_name": "Ada",
            "birth_year": 2000,
            "initial_attribute_buys": ["Power", "Power"],
            "initial_bonuses": {"skill_bonuses": ["Charms"], "traits": ["Brave"]},
            "development_plan": {"school_years": [], "adult_years": [], "initial_eminence": []},
            "characteristics": {"fortitude": 2},
            "parental_values": {"generosity": 3},
            "board": {"portrait": None},
        }
        self.world = {
            "people": [self.person, {"record_id": "person-2", "displayed_name": "Bea"}],
            "events": [
                {"record_id": "past", "event_type": "began_friendship", "date": "2001-01-01", "person_ids": ["person-1", "person-2"]},
                {"record_id": "future", "event_type": "taught_spell", "date": "2005-01-01", "person_ids": ["person-1"], "knowledge_record_id": "spell-1"},
                {"record_id": "tame", "event_type": "tamed_creature", "date": "2002-02-01", "person_ids": ["person-1"], "named_creature_id": "named-1"},
                {"record_id": "bond", "event_type": "bonded_creature", "date": "2002-03-01", "person_ids": ["person-1"], "named_creature_id": "named-1"},
                {"record_id": "irk", "event_type": "irked_creature", "date": "2002-04-01", "person_ids": ["person-1"], "named_creature_id": "named-1"},
            ],
            "books": [{"record_id": "book-1", "title": "Primer", "contents": [{"content_type": "Proficiency", "collection": "proficiencies", "record_id": "prof-1"}]}],
            "book_readings": [{"record_id": "read-1", "person_id": "person-1", "book_id": "book-1", "date": "2002-01-01"}],
            "named_creatures": [{"record_id": "named-1", "name": "Pip", "species_record_id": "creature-1"}],
            "items": [],
        }
        self.database = {
            "schools": [],
            "spells": [{"record_id": "spell-1", "name": "Lumos", "skill": "Charms", "threshold": 3}],
            "proficiencies": [{"record_id": "prof-1", "name": "Research", "skill": "History", "threshold": 7}],
            "potions": [], "preparations": [], "foods_and_drinks": [],
            "creatures": [{"record_id": "creature-1", "name": "Kneazle", "classification": "Beast", "size": "Small"}],
            "books": [],
        }

    def campaign(self, current="2003-01-01T08:00", policy="keep"):
        return {
            "record_id": "campaign-1",
            "game_world_start_date": "2000-01-01",
            "history_policy": policy,
            "events": [],
            "game_state": {"current_game_datetime": current, "people": {}},
        }

    def test_keep_and_discard_branch_world_history(self):
        kept = effective_campaign_events(self.world, self.campaign("2006-01-01T08:00", "keep"))
        discarded = effective_campaign_events(self.world, self.campaign("2006-01-01T08:00", "discard"))
        self.assertEqual(
            {item["record_id"] for item in kept},
            {"past", "future", "tame", "bond", "irk"},
        )
        self.assertEqual(discarded, [])

    def test_reading_grants_contents_and_future_teaching_waits(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign())
        self.assertEqual([item["record_id"] for item in sheet["proficiencies"]], ["prof-1"])
        self.assertEqual(sheet["spells"], [])
        later = build_character_sheet(self.person, self.world, self.database, self.campaign("2006-01-01T08:00"))
        self.assertEqual([item["record_id"] for item in later["spells"]], ["spell-1"])

    def test_ownership_or_assignment_without_completed_reading_grants_nothing(self):
        self.world["book_readings"] = []
        self.person["assigned_book_ids"] = ["book-1"]
        self.world["items"] = [{
            "record_id": "owned-book", "name": "Primer", "book_id": "book-1",
            "passage_history": [{"date": "2001-01-01", "person_id": "person-1"}],
        }]
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign())
        self.assertEqual(sheet["proficiencies"], [])

    def test_future_and_duplicate_readings_are_date_effective_and_deduplicated(self):
        self.world["book_readings"].extend([
            {"record_id": "read-2", "person_id": "person-1", "book_id": "book-1", "date": "2002-06-01"},
            {"record_id": "read-3", "person_id": "person-1", "book_id": "book-1", "date": "2009-01-01"},
        ])
        early = build_character_sheet(self.person, self.world, self.database, self.campaign())
        self.assertEqual([item["record_id"] for item in early["proficiencies"]], ["prof-1"])

    def test_tame_bond_and_irk_histories_coexist(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign())
        self.assertEqual(len(sheet["pets"]), 1)
        self.assertEqual(sheet["pets"][0]["relationships"], ["pet", "ally", "irked"])
        self.assertEqual(sheet["pets"][0]["species"]["classification"], "Beast")
        self.assertEqual(sheet["relationships"][0]["type"], "Friendship")

    def test_server_roll_uses_sheet_values_and_critical_rules(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign("2006-01-01T08:00"))
        result = perform_character_roll(sheet, "spell", "spell-1", roller=lambda _a, _b: 10)
        self.assertEqual(result["critical"], "success")
        self.assertTrue(result["success"])
        with self.assertRaises(PermissionError):
            perform_character_roll(sheet, "spell", "hidden-spell", roller=lambda _a, _b: 10)

    def test_all_roll_categories_are_server_calculated(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign("2006-01-01T08:00"))
        sheet["recipes"] = [{"record_id": "recipe-1", "name": "Tea", "skill": "Potions", "threshold": 5}]
        for roll_type, target in (
            ("ability", "Power"), ("skill", "Charms"),
            ("characteristic", "Fortitude"), ("parental", "Generosity"),
            ("spell", "spell-1"), ("proficiency", "prof-1"),
            ("recipe", "recipe-1"),
        ):
            result = perform_character_roll(sheet, roll_type, target, roller=lambda _a, _b: 6)
            self.assertEqual(result["action_type"], roll_type)
            self.assertTrue(result["dice"])
        failure = perform_character_roll(sheet, "ability", "Power", roller=lambda _a, _b: 1)
        self.assertEqual(failure["critical"], "failure")


if __name__ == "__main__":
    unittest.main()
