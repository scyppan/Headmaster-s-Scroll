import unittest

from headmasters_scroll.character_rolls import perform_character_roll
from headmasters_scroll.character_sheet import (
    _book_cover_asset_id, build_character_sheet, effective_campaign_events,
    recipe_requirements,
)


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
            "books": [{"record_id": "book-1", "title": "Primer", "categories": ["Charms"], "contents": [{"content_type": "Proficiency", "collection": "proficiencies", "record_id": "prof-1"}]}],
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

    def test_categoryless_book_uses_explicit_subject_in_title_for_cover(self):
        self.assertEqual(
            _book_cover_asset_id({
                "record_id": "book_1238",
                "name": "Introduction to Astronomy",
                "categories": [],
            }),
            "book-cover:astronomy",
        )

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
        self.assertEqual(sheet["proficiencies"][0]["source"], "Primer")
        self.assertEqual([item["record_id"] for item in sheet["books"]], ["book-1"])
        self.assertEqual(sheet["books"][0]["cover_asset_id"], "book-cover:charms")
        self.assertEqual(sheet["books"][0]["contents"]["proficiencies"], ["prof-1"])
        self.assertEqual(sheet["spells"], [])
        later = build_character_sheet(self.person, self.world, self.database, self.campaign("2006-01-01T08:00"))
        self.assertEqual([item["record_id"] for item in later["spells"]], ["spell-1"])
        self.assertEqual(later["spells"][0]["source"], "Unknown teacher")

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

    def test_school_and_recreational_books_follow_curriculum_and_dates(self):
        self.person.update({"birth_year": 1990, "birth_month": 1, "birth_day": 1, "school": "Hogwarts"})
        self.person["development_plan"] = {"school_years": [{
            "year": 1, "school": "Hogwarts", "skipped": False,
            "electives": ["Runes"],
            "books": [{"record_id": "book-recreation-one"}, {"record_id": "book-recreation-two"}],
        }], "adult_years": [], "initial_eminence": []}
        self.database["schools"] = [{
            "name": "Hogwarts",
            "curriculum": [{"year": 1, "core": ["Charms"], "electives": ["Runes", "Divination"]}],
            "course_books": [
                {"year": 1, "course": "Charms", "record_id": "book-core"},
                {"year": 1, "course": "Runes", "record_id": "book-elective"},
                {"year": 1, "course": "Divination", "record_id": "book-unselected"},
            ],
        }]
        self.database["books"] = [
            {"record_id": "book-core", "spells": [{"record_id": "spell-core"}]},
            {"record_id": "book-elective", "spells": [{"record_id": "spell-elective"}]},
            {"record_id": "book-unselected", "spells": [{"record_id": "spell-unselected"}]},
            {"record_id": "book-recreation-one", "spells": [{"record_id": "spell-recreation-one"}]},
            {"record_id": "book-recreation-two", "spells": [{"record_id": "spell-recreation-two"}]},
        ]
        self.database["spells"].extend([
            {"record_id": "spell-core", "name": "Core"},
            {"record_id": "spell-elective", "name": "Elective"},
            {"record_id": "spell-unselected", "name": "Unselected"},
            {"record_id": "spell-recreation-one", "name": "September"},
            {"record_id": "spell-recreation-two", "name": "January"},
        ])
        early = build_character_sheet(self.person, self.world, self.database, self.campaign("2001-09-01T08:00"))
        self.assertEqual({item["record_id"] for item in early["spells"]}, {"spell-core", "spell-elective", "spell-recreation-one"})
        january = build_character_sheet(self.person, self.world, self.database, self.campaign("2002-01-01T08:00"))
        self.assertIn("spell-recreation-two", {item["record_id"] for item in january["spells"]})

    def test_tame_bond_and_irk_histories_coexist(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign())
        self.assertEqual(len(sheet["pets"]), 1)
        self.assertEqual(sheet["pets"][0]["relationships"], ["pet", "ally", "irked"])
        self.assertEqual(sheet["pets"][0]["species"]["classification"], "Beast")
        self.assertEqual(sheet["relationships"][0]["type"], "Friendship")

    def test_overview_age_is_calculated_at_campaign_date(self):
        sheet = build_character_sheet(
            self.person, self.world, self.database, self.campaign("2026-08-13T08:00")
        )
        self.assertEqual(sheet["overview"]["age"], 26)

    def test_server_roll_uses_sheet_values_and_critical_rules(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign("2006-01-01T08:00"))
        result = perform_character_roll(sheet, "spell", "spell-1", roller=lambda _a, _b: 10)
        self.assertEqual(result["critical"], "success")
        self.assertTrue(result["success"])
        self.assertEqual(result["outcome"], "critical_success")
        self.assertEqual(result["components"][0], {"label": "d10", "value": 10, "kind": "die"})
        self.assertIn("CRITICALLY SUCCEEDS in casting Lumos", result["text"])
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
        self.assertEqual(failure["text"], "Ada CRITICALLY FAILS a straight Power roll.")

    def test_recipe_requires_every_ingredient_before_rolling(self):
        sheet = build_character_sheet(
            self.person, self.world, self.database, self.campaign("2006-01-01T08:00")
        )
        sheet["recipes"] = [{
            "record_id": "recipe-1", "name": "Tea", "skill": "Potions",
            "threshold": 5,
            "ingredients": [{"name": "Tea leaves", "quantity": 2}],
        }]
        sheet["inventory"] = [{"name": "Tea leaves", "quantity": 1}]
        with self.assertRaisesRegex(PermissionError, "Missing recipe ingredients"):
            perform_character_roll(sheet, "recipe", "recipe-1", roller=lambda _a, _b: 6)
        sheet["inventory"][0]["quantity"] = 2
        result = perform_character_roll(
            sheet, "recipe", "recipe-1", roller=lambda _a, _b: 6
        )
        self.assertEqual(result["action_type"], "recipe")

    def test_recipe_requirements_separate_consumables_from_vessel(self):
        requirements = recipe_requirements(
            {
                "ingredients": [{"name": "Tea leaves", "quantity": 2}],
                "required_vessel": "Cauldron",
            },
            [
                {"record_id": "leaves", "name": "Tea leaves", "quantity": 3},
                {"record_id": "vessel", "name": "Copper Cauldron", "quantity": 1},
            ],
        )
        self.assertTrue(requirements["ready"])
        self.assertEqual(requirements["consumption"], {"leaves": 2})
        self.assertEqual(
            requirements["vessel"], {"name": "Cauldron", "available": True}
        )

    def test_recipe_requirements_report_every_shortfall(self):
        requirements = recipe_requirements(
            {
                "ingredients": [
                    {"name": "Tea leaves", "quantity": 2},
                    {"name": "Honey", "quantity": 1},
                ],
                "required_vessel": "Cauldron",
            },
            [{"record_id": "leaves", "name": "Tea leaves", "quantity": 1}],
        )
        self.assertFalse(requirements["ready"])
        self.assertEqual(
            requirements["missing"],
            ["1 Tea leaves", "1 Honey", "vessel: Cauldron"],
        )

    def test_recipe_requirements_support_or_vessels_and_proficiencies(self):
        requirements = recipe_requirements(
            {
                "ingredient_requirements": [
                    {
                        "record_id": "salt-line",
                        "alternatives": [{
                            "collection": "raw_materials",
                            "record_id": "saltpeter",
                            "name": "Saltpeter",
                            "quantity": 1,
                        }],
                    },
                    {
                        "record_id": "vitriol-line",
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
                "proficiency_requirements": [{
                    "record_id": "proficiency-line",
                    "alternatives": [{
                        "collection": "proficiencies",
                        "record_id": "acid-work",
                        "name": "Acid Work",
                    }],
                }],
            },
            [
                {
                    "record_id": "salt-stack",
                    "definition_collection": "raw_materials",
                    "definition_record_id": "saltpeter",
                    "name": "Saltpeter",
                    "quantity": 1,
                },
                {
                    "record_id": "vitriol-stack",
                    "definition_collection": "raw_materials",
                    "definition_record_id": "vitriol",
                    "name": "Vitriol",
                    "quantity": 1,
                },
                {
                    "record_id": "retort-stack",
                    "definition_collection": "general_items",
                    "definition_record_id": "retort",
                    "name": "Glass Retort",
                    "quantity": 1,
                },
            ],
            {"acid-work"},
        )
        self.assertTrue(requirements["ready"])
        self.assertEqual(
            requirements["consumption"],
            {"salt-stack": 1, "vitriol-stack": 1},
        )
        self.assertEqual(requirements["vessels"][0]["selected"], "Retort")
        self.assertEqual(
            requirements["proficiencies"][0]["selected"], "Acid Work"
        )

    def test_recipe_requirement_groups_do_not_reuse_the_same_stack(self):
        requirements = recipe_requirements(
            {
                "ingredient_requirements": [
                    {
                        "record_id": "line-1",
                        "alternatives": [{"name": "Salt", "quantity": 1}],
                    },
                    {
                        "record_id": "line-2",
                        "alternatives": [{"name": "Salt", "quantity": 1}],
                    },
                ],
            },
            [{"record_id": "salt-stack", "name": "Salt", "quantity": 1}],
        )
        self.assertFalse(requirements["ready"])
        self.assertEqual(requirements["consumption"], {"salt-stack": 1})
        self.assertEqual(requirements["missing"], ["1 Salt"])

    def test_owned_passive_and_equipped_items_feed_roll_ledgers(self):
        self.world["items"] = [
            {
                "record_id": "charm-instance", "name": "Lucky Coin",
                "definition_record_id": "coin-definition", "quantity": 1,
                "passage_history": [{"date": "2001-01-01", "person_id": "person-1"}],
            },
            {
                "record_id": "ring-instance", "name": "Charm Ring",
                "definition_record_id": "ring-definition", "quantity": 1,
                "passage_history": [{"date": "2001-01-01", "person_id": "person-1"}],
            },
        ]
        self.database.update({
            "wands": [], "holdable_items": [], "general_items": [{
                "record_id": "coin-definition", "name": "Lucky Coin",
                "activation_mode": "passive",
                "bonuses": [{"type": "Skill", "target": "Charms", "amount": 2}],
            }],
            "accessories": [{
                "record_id": "ring-definition", "name": "Charm Ring",
                "activation_mode": "equipped", "equipment_slot_type": "accessory",
                "bonuses": [{"type": "Skill", "target": "Charms", "amount": 3}],
            }],
            "plants": [],
        })
        campaign = self.campaign()
        campaign["game_state"]["people"] = {
            "person-1": {"equipment": {"focus": "", "accessory_1": "ring-instance", "accessory_2": ""}}
        }
        sheet = build_character_sheet(self.person, self.world, self.database, campaign)
        charms = next(item for item in sheet["attributes"]["skills"] if item["name"] == "Charms")
        self.assertEqual(charms["breakdown"]["passive"], 2)
        self.assertEqual(charms["breakdown"]["accessories"], 3)
        self.assertTrue(next(item for item in sheet["inventory"] if item["record_id"] == "ring-instance")["equipped"])

    def test_harvested_nested_part_keeps_its_item_image_and_passive_bonus(self):
        self.database.update({
            "wands": [], "holdable_items": [], "accessories": [],
            "general_items": [], "plants": [],
            "creatures": [{
                "record_id": "bat", "name": "Bat", "parts": [{
                    "record_id": "bat-wing", "name": "Bat Wing",
                    "image_asset": "assets/items/parts/bat-wing.png",
                    "base_knuts": 7,
                    "activation_mode": "passive",
                    "bonuses": [{
                        "type": "Skill", "target": "Charms", "amount": 2,
                        "activation_mode": "passive",
                    }],
                }],
            }],
        })
        campaign = self.campaign()
        campaign["game_state"]["people"] = {"person-1": {
            "campaign_inventory": [{
                "record_id": "harvest-stack", "item_id": "bat-wing",
                "part_id": "bat-wing", "definition_collection": "creature_parts",
                "name": "Bat Wing", "quantity": 1,
            }],
        }}
        sheet = build_character_sheet(
            self.person, self.world, self.database, campaign
        )
        wing = next(
            item for item in sheet["inventory"]
            if item["record_id"] == "harvest-stack"
        )
        self.assertEqual(wing["definition_collection"], "creature_parts")
        self.assertEqual(wing["image_asset"], "assets/items/parts/bat-wing.png")
        self.assertEqual(wing["base_knuts"], 7)
        charms = next(
            item for item in sheet["attributes"]["skills"]
            if item["name"] == "Charms"
        )
        self.assertEqual(charms["breakdown"]["passive"], 2)

    def test_in_flight_effects_apply_only_while_airborne(self):
        self.world["items"] = [{
            "record_id": "broom-instance", "name": "Training Broom",
            "definition_record_id": "broom-definition", "quantity": 1,
            "passage_history": [{"date": "2001-01-01", "person_id": "person-1"}],
        }]
        self.database.update({
            "wands": [], "holdable_items": [], "accessories": [], "plants": [],
            "general_items": [{
                "record_id": "broom-definition", "name": "Training Broom",
                "type": "Flyable", "activation_mode": "equipped",
                "equipment_slot_type": "flyable", "flight_threshold": 9,
                "bonuses": [{"type": "Skill", "target": "Charms", "amount": 99}],
                "in_flight_effects": [
                    {"type": "Skill", "target": "Flying", "amount": 4}
                ],
            }],
        })
        campaign = self.campaign()
        unmounted = build_character_sheet(self.person, self.world, self.database, campaign)
        flying = next(item for item in unmounted["attributes"]["skills"] if item["name"] == "Flying")
        self.assertEqual(flying["total"], 0)
        item = unmounted["inventory"][0]
        self.assertEqual(item["equipment_slot_type"], "flyable")
        self.assertEqual(item["flight_threshold"], 9)
        self.assertFalse(item["equipped"])

        campaign["game_state"]["people"] = {
            "person-1": {
                "equipment": {"flyable": "broom-instance"},
                "airborne": False,
            }
        }
        grounded = build_character_sheet(
            self.person, self.world, self.database, campaign
        )
        grounded_flying = next(
            item for item in grounded["attributes"]["skills"]
            if item["name"] == "Flying"
        )
        grounded_charms = next(
            item for item in grounded["attributes"]["skills"]
            if item["name"] == "Charms"
        )
        self.assertEqual(grounded_flying["total"], 0)
        self.assertNotEqual(grounded_charms["total"], 99)

        campaign["game_state"]["people"] = {
            "person-1": {
                "equipment": {"flyable": "broom-instance"},
                "airborne": True,
            }
        }
        mounted = build_character_sheet(self.person, self.world, self.database, campaign)
        flying = next(item for item in mounted["attributes"]["skills"] if item["name"] == "Flying")
        self.assertEqual(flying["total"], 4)
        self.assertTrue(mounted["airborne"])
        self.assertEqual(flying["breakdown"]["passive"], 4)

    def test_natural_ten_does_not_bypass_an_unreachable_threshold(self):
        sheet = build_character_sheet(
            self.person, self.world, self.database, self.campaign("2006-01-01T08:00")
        )
        sheet["spells"][0]["threshold"] = 99
        result = perform_character_roll(
            sheet, "spell", "spell-1", roller=lambda _a, _b: 10
        )
        self.assertFalse(result["success"])
        self.assertEqual(result["critical"], "")
        self.assertEqual(result["outcome"], "failure")

    def test_skill_roll_retains_character_controls_wording_and_components(self):
        sheet = build_character_sheet(self.person, self.world, self.database, self.campaign())
        result = perform_character_roll(sheet, "skill", "Charms", roller=lambda _a, _b: 6)
        self.assertIn("attempts to cast a straight Charms spell", result["text"])
        self.assertEqual([item["label"] for item in result["components"]], ["d10", "Power", "Charms"])
        self.assertEqual(result["formula"], "6 + 2 + 1")
        self.assertEqual(
            [item["label"] for item in result["components"][2]["sources"]],
            [
                "Buys", "Corecourses", "Electives", "Traits", "Wand parts",
                "Wand", "Quality", "Accessories", "Passive", "Eminence", "Temp",
            ],
        )
        self.assertTrue(all(
            "value" in item for item in result["components"][2]["sources"]
        ))

    def test_characteristic_roll_details_include_base_and_passive_without_adding_pool(self):
        sheet = build_character_sheet(
            self.person, self.world, self.database, self.campaign()
        )
        result = perform_character_roll(
            sheet, "characteristic", "Fortitude", roller=lambda _a, _b: 4
        )
        pool = result["components"][-1]
        self.assertEqual(pool["kind"], "pool")
        self.assertEqual(
            pool["sources"],
            [{"label": "Base", "value": 2}, {"label": "Passive", "value": 0}],
        )
        self.assertEqual(result["total"], 8)
        self.assertEqual(result["formula"], "4 + 4")


if __name__ == "__main__":
    unittest.main()
