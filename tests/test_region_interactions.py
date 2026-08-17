import random
import unittest

from headmasters_scroll.board import normalize_region
from headmasters_scroll.campaigns import normalize_campaign_game_state
from headmasters_scroll.region_interactions import (
    catalog_reference_exists,
    draw_loot,
    ensure_gathering_catalog,
    loot_cost,
    shop_window,
    validate_gathering_database,
    validate_region_catalog_links,
)
from headmasters_scroll.game_board.service import GameBoardService


class RegionInteractionTests(unittest.TestCase):
    def region(self, behavior="secret"):
        return {
            "record_id": "region-1", "name": "Hidden cache", "type_label": "",
            "behavior_type": behavior, "hover_text": "Private clue",
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.4, "y": 0.8}],
            "secret_skill": "Perception", "secret_threshold": 12,
            "search_modes": [{
                "record_id": "mode-1", "name": "Search", "skill": "Perception",
                "gathering_method_id": "search",
            }],
            "contents": [{
                "record_id": "entry-1",
                "reference": {"collection": "books", "record_id": "book-1", "parent_record_id": ""},
                "search_mode_ids": ["mode-1"], "threshold": 7, "depletable": True,
            }],
        }

    def test_new_behaviors_and_secret_contract_validate(self):
        secret = normalize_region(self.region())
        self.assertEqual(secret["behavior_type"], "secret")
        self.assertEqual(secret["secret_skill"], "Perception")
        storeroom = self.region("storeroom")
        storeroom["secret_skill"] = ""
        storeroom["secret_threshold"] = 0
        self.assertEqual(normalize_region(storeroom)["behavior_type"], "storeroom")

    def test_secret_passage_retains_its_travel_destination(self):
        value = self.region()
        value.update({
            "secret_passage": True,
            "target_location_id": "hidden-chamber",
            "target_warp_point_id": "hidden-door",
        })
        passage = normalize_region(value)
        self.assertTrue(passage["secret_passage"])
        self.assertEqual(passage["target_location_id"], "hidden-chamber")
        self.assertEqual(passage["target_warp_point_id"], "hidden-door")

    def test_content_must_reference_existing_mode(self):
        value = self.region()
        value["contents"][0]["search_mode_ids"] = ["missing"]
        with self.assertRaises(ValueError):
            normalize_region(value)

    def test_loot_cost_brackets(self):
        self.assertEqual([loot_cost(value) for value in (0, 14, 15, 24, 25, 34, 35, 49, 50, 64, 65)], [1, 1, 3, 3, 5, 5, 7, 7, 9, 9, 10])

    def test_loot_respects_finite_stock_and_natural_ten(self):
        entries = [{"record_id": "a", "threshold": 5}, {"record_id": "b", "threshold": 15}]
        remaining = {"a": 2, "b": 1}
        result = draw_loot(entries, 10, die_roll=10, available_quantity=lambda item: remaining[item["record_id"]], chooser=random.Random(2))
        counts = {record_id: result.awarded_ids.count(record_id) for record_id in set(result.awarded_ids)}
        self.assertLessEqual(counts.get("a", 0), 2)
        self.assertLessEqual(counts.get("b", 0), 1)
        self.assertGreaterEqual(len(result.awarded_ids), 1)

    def test_natural_one_destroys_one_result(self):
        result = draw_loot([{"record_id": "a", "threshold": 0}], 0, die_roll=1, chooser=random.Random(1))
        self.assertEqual(result.awarded_ids, ())
        self.assertEqual(result.destroyed_id, "a")

    def test_shop_schedule_is_world_deterministic_and_bce_safe(self):
        region = {"record_id": "shop-1", "shop_seed": "diagon-alley"}
        listing = {"record_id": "listing-1", "reference": {"collection": "books", "record_id": "book-1", "parent_record_id": ""}, "frequency": "rarely", "price_knuts": 12}
        first = shop_window(region, listing, "2000-08-27T08:00")
        second = shop_window(region, listing, "2000-08-27T20:00")
        ancient = shop_window(region, listing, "-3100-08-27T08:00")
        self.assertEqual(first, second)
        self.assertTrue(ancient["window_id"].startswith("shop-stock-v1:"))

    def test_gathering_catalog_migration_is_idempotent(self):
        database = {
            "books": [{"record_id": "book-1", "name": "Book"}],
            "creatures": [],
            "plants": [{"record_id": "plant-1", "name": "Plant", "parts": [{"name": "Leaf"}]}],
        }
        self.assertTrue(ensure_gathering_catalog(database))
        self.assertFalse(ensure_gathering_catalog(database))
        self.assertEqual(len(database["gathering_methods"]), 5)
        self.assertTrue(database["plants"][0]["parts"][0]["record_id"].startswith("plant_part_"))
        self.assertNotIn("gathering_method_ids", database["books"][0])

    def test_gathering_validation_rejects_unknown_method(self):
        database = {
            "_database": {"schema_version": 4},
            "gathering_methods": [{"record_id": "search", "name": "Search"}],
            "books": [{
                "record_id": "book-1", "name": "Book",
                "gathering_method_ids": ["missing"],
            }],
            "creatures": [], "plants": [],
        }
        with self.assertRaisesRegex(ValueError, "unknown gathering method"):
            validate_gathering_database(database)

    def test_region_catalog_links_resolve_nested_and_top_level_records(self):
        database = {
            "gathering_methods": [{"record_id": "search", "name": "Search"}],
            "books": [{"record_id": "book-1", "name": "Book"}],
            "creatures": [], "plants": [],
        }
        self.assertTrue(catalog_reference_exists(
            database, {"collection": "books", "record_id": "book-1"}
        ))
        validate_region_catalog_links(self.region(), database)

    def test_region_catalog_links_reject_stale_catalog_records(self):
        database = {
            "gathering_methods": [{"record_id": "search", "name": "Search"}],
            "books": [], "creatures": [], "plants": [],
        }
        with self.assertRaisesRegex(ValueError, "missing catalog record"):
            validate_region_catalog_links(self.region(), database)

    def test_competency_pool_requires_awareness_and_known_recipe_ingredients(self):
        database = {
            "creatures": [{
                "record_id": "bat", "name": "Bat",
                "awareness_proficiency_id": "bat-awareness",
            }],
            "plants": [{
                "record_id": "mint", "name": "Mint",
                "parts": [{"record_id": "mint-leaf", "name": "Mint Leaf"}],
            }],
        }
        region = {"contents": [
            {
                "record_id": "bat-entry", "threshold": 2,
                "search_mode_ids": ["mode"],
                "reference": {"collection": "creatures", "record_id": "bat"},
            },
            {
                "record_id": "mint-entry", "threshold": 2,
                "search_mode_ids": ["mode"],
                "reference": {
                    "collection": "plant_parts", "parent_record_id": "mint",
                    "record_id": "mint-leaf",
                },
            },
        ]}
        mode = {"record_id": "mode", "skill": "Potions", "gathering_method_id": "search"}
        service = GameBoardService.__new__(GameBoardService)
        without_knowledge = service._competency_entries(
            region, mode, {"proficiencies": [], "recipes": []}, database
        )
        self.assertEqual(without_knowledge, [])
        with_knowledge = service._competency_entries(region, mode, {
            "proficiencies": [{"record_id": "bat-awareness"}],
            "recipes": [{
                "record_id": "tea", "ingredients": [{"name": "Mint Leaf"}],
            }],
        }, database)
        self.assertEqual(
            [item["record_id"] for item in with_knowledge], ["mint-entry"]
        )
        creature_mode = {
            "record_id": "mode", "skill": "Creatures",
            "gathering_method_id": "search",
        }
        creature_results = service._competency_entries(region, creature_mode, {
            "proficiencies": [{"record_id": "bat-awareness"}], "recipes": [],
        }, database)
        self.assertEqual(
            [item["record_id"] for item in creature_results],
            ["bat-entry", "mint-entry"],
        )

    def test_raw_material_loot_is_filtered_by_selected_searching_method(self):
        database = {
            "gathering_methods": [
                {"record_id": "prospect", "name": "Prospect"},
                {"record_id": "dive", "name": "Dive"},
            ],
            "general_items": [
                {
                    "record_id": "quartz", "name": "Quartz",
                    "type": "Raw Material",
                    "searching_method_id": "prospect",
                },
                {
                    "record_id": "pearl", "name": "Pearl",
                    "type": "Raw Material",
                    "searching_method_id": "dive",
                },
                {
                    "record_id": "rope", "name": "Rope",
                    "type": "Tool & Supply",
                },
            ],
        }
        region = {"contents": [
            {
                "record_id": "quartz-entry", "threshold": 0,
                "search_mode_ids": ["mode"],
                "reference": {"collection": "general_items", "record_id": "quartz"},
            },
            {
                "record_id": "pearl-entry", "threshold": 0,
                "search_mode_ids": ["mode"],
                "reference": {"collection": "general_items", "record_id": "pearl"},
            },
            {
                "record_id": "rope-entry", "threshold": 0,
                "search_mode_ids": ["mode"],
                "reference": {"collection": "general_items", "record_id": "rope"},
            },
        ]}
        mode = {"record_id": "mode", "skill": "Alchemy", "gathering_method_id": "search"}
        service = GameBoardService.__new__(GameBoardService)

        methods = service._extraction_methods_for_mode(region, mode, database)
        self.assertEqual(
            methods,
            [
                {"record_id": "dive", "name": "Dive"},
                {"record_id": "prospect", "name": "Prospect"},
            ],
        )
        prospect = service._competency_entries(
            region, mode, {"proficiencies": [], "recipes": []}, database,
            "prospect",
        )
        self.assertEqual(
            [item["record_id"] for item in prospect],
            ["quartz-entry", "rope-entry"],
        )
        dive = service._competency_entries(
            region, mode, {"proficiencies": [], "recipes": []}, database,
            "dive",
        )
        self.assertEqual(
            [item["record_id"] for item in dive],
            ["pearl-entry", "rope-entry"],
        )
        without_selection = service._competency_entries(
            region, mode, {"proficiencies": [], "recipes": []}, database
        )
        self.assertEqual(
            [item["record_id"] for item in without_selection],
            ["rope-entry"],
        )

    def test_gathering_validation_rejects_unknown_searching_method(self):
        database = {
            "_database": {"schema_version": 4},
            "gathering_methods": [{"record_id": "search", "name": "Search"}],
            "general_items": [{
                "record_id": "quartz", "name": "Quartz", "type": "Raw Material",
                "searching_method_id": "missing",
            }],
            "creatures": [], "plants": [],
        }
        with self.assertRaisesRegex(ValueError, "unknown Searching Method"):
            validate_gathering_database(database)

    def test_campaign_interaction_ledgers_normalize(self):
        state = normalize_campaign_game_state({
            "region_interactions": {
                "attempts": [{"record_id": "attempt-1", "game_day": "2000-08-27"}],
                "revealed_secrets": [{
                    "record_id": "reveal-1",
                    "map_id": "map-1",
                    "region_id": "region-1",
                }],
                "source_depletion": {"region:entry": 2},
            }
        }, "2000-08-27")
        self.assertEqual(state["region_interactions"]["source_depletion"]["region:entry"], 2)
        self.assertEqual(state["region_interactions"]["attempts"][0]["record_id"], "attempt-1")
        self.assertEqual(
            state["region_interactions"]["revealed_secrets"][0]["region_id"],
            "region-1",
        )

    def test_campaign_reveal_and_daily_discovery_are_both_recognized(self):
        campaign = {
            "game_state": {
                "current_game_datetime": "2000-08-27T08:00",
                "region_interactions": {
                    "revealed_secrets": [{"region_id": "global-secret"}],
                    "secret_unlocks": [{
                        "character_id": "pc-1",
                        "region_id": "daily-secret",
                        "game_day": "2000-08-27",
                    }],
                },
            }
        }
        self.assertTrue(GameBoardService._secret_is_revealed(
            campaign, "global-secret", "pc-2"
        ))
        self.assertTrue(GameBoardService._secret_is_revealed(
            campaign, "daily-secret", "pc-1"
        ))
        self.assertFalse(GameBoardService._secret_is_revealed(
            campaign, "daily-secret", "pc-2"
        ))


if __name__ == "__main__":
    unittest.main()
