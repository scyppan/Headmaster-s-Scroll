import json
import tempfile
import unittest
from pathlib import Path

from headmasters_scroll.campaigns import (
    CampaignRepository,
    compact_campaign_document_for_storage,
    compact_campaign_person_overlays,
    default_campaign_person_state,
    hydrate_campaign_person_board,
    normalize_campaign,
    normalize_board_camera,
    normalize_game_world_date,
)
from headmasters_scroll.store import SharedJsonStore


class CampaignTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "campaign.json"
        self.path.write_text(json.dumps({
            "schema_version": 1,
            "_headmasters_scroll": {
                "revision_id": "campaign-revision",
                "last_modified_at": "2026-08-11T00:00:00Z",
                "last_modified_by": "test",
            },
            "campaigns": [],
        }), encoding="utf-8")
        self.repository = CampaignRepository(SharedJsonStore(self.directory))

    def tearDown(self):
        self.temporary.cleanup()

    def test_campaign_create_update_and_delete_use_shared_storage(self):
        created = self.repository.save_campaign("First Campaign", "-3100-01-09")
        self.assertEqual(created["history_policy"], "keep")
        self.assertEqual(created["events"], [])
        self.assertEqual(created["requests"], [])
        self.assertEqual(created["game_world_start_date"], "-3100-01-09")
        updated = self.repository.save_campaign(
            "Renamed Campaign", "1943-09-01", created["record_id"]
        )
        self.assertEqual(updated["name"], "Renamed Campaign")
        self.assertEqual(self.repository.list()[0]["game_world_start_date"], "1943-09-01")
        self.repository.delete(created["record_id"])
        self.assertEqual(self.repository.list(), [])
        backups = list((self.directory / "backups" / "campaign").glob("*.json"))
        self.assertGreaterEqual(len(backups), 3)

    def test_campaign_dates_validate_real_dates_and_bce(self):
        self.assertEqual(normalize_game_world_date("-3100-01-09"), "-3100-01-09")
        with self.assertRaises(ValueError):
            normalize_game_world_date("1943-02-30")

    def test_new_campaign_has_a_backward_compatible_board_state(self):
        created = self.repository.save_campaign("Board Campaign", "1943-09-01")
        state = created["game_state"]
        self.assertFalse(state["initialized"])
        self.assertEqual(state["current_game_datetime"], "1943-09-01T08:00")
        self.assertEqual(state["loaded_map_ids"], [])
        self.assertEqual(state["player_active_map_ids"], {})
        self.assertEqual(state["maps"], {})
        self.assertEqual(state["people"], {})
        self.assertEqual(state["groups"], [])
        self.assertEqual(state["battles"], {})

    def test_fresh_game_state_does_not_copy_world_board_runtime_state(self):
        campaign = self.repository.save_campaign("Isolated", "1943-09-01")
        world = {
            "maps": [{
                "record_id": "map-1",
                "name": "Legacy map",
                "location_id": "location-1",
                "floor_id": "",
                "players_published": True,
                "obscurations": [{
                    "record_id": "fog-1",
                    "points": [
                        {"x": 0.1, "y": 0.1},
                        {"x": 0.4, "y": 0.1},
                        {"x": 0.2, "y": 0.4},
                    ],
                }],
                "headmaster_camera": {
                    "zoom": 8,
                    "center_x": 0.2,
                    "center_y": 0.7,
                },
            }],
            "people": [{
                "record_id": "person-1",
                "board": {
                    "placement": {
                        "location_id": "location-1",
                        "floor_id": "",
                        "map_id": "map-1",
                        "x": 0.25,
                        "y": 0.75,
                    },
                    "visibility": "headmaster",
                    "name_revealed": True,
                },
            }],
            "board_groups": [{
                "record_id": "legacy-group",
                "name": "Old party",
                "location_id": "location-1",
                "members": [],
            }],
        }
        original_world = json.loads(json.dumps(world))

        initialized = self.repository.ensure_game_state(
            campaign["record_id"], world, "1943-09-02T19:45"
        )

        state = initialized["game_state"]
        self.assertTrue(state["initialized"])
        self.assertEqual(state["current_game_datetime"], "1943-09-02T19:45")
        self.assertEqual(state["loaded_map_ids"], [])
        self.assertEqual(state["active_map_id"], "")
        self.assertEqual(state["player_active_map_ids"], {})
        self.assertEqual(state["maps"], {})
        self.assertEqual(state["people"], {})
        self.assertEqual(state["creatures"], {})
        self.assertEqual(state["groups"], [])
        self.assertEqual(state["battles"], {})
        self.assertEqual(world, original_world)

    def test_campaign_board_hydration_keeps_only_authored_portrait(self):
        portrait = {
            "asset_id": "portrait:person-1",
            "sha256": "a" * 64,
            "width": 512,
            "height": 512,
            "mime_type": "image/webp",
        }
        authored = {
            "portrait": portrait,
            "placement": {
                "location_id": "legacy-location",
                "floor_id": "",
                "map_id": "legacy-map",
                "x": 0.2,
                "y": 0.8,
            },
            "visibility": "headmaster",
            "display_mode": "token",
            "name_revealed": True,
            "faction_revealed": True,
            "faction_organization_id": "legacy-faction",
            "label_offset": {"x": 0.5, "y": -0.4},
            "nameplate_scale": 2.0,
        }

        hydrated = hydrate_campaign_person_board(authored)

        self.assertEqual(hydrated["portrait"], portrait)
        self.assertIsNone(hydrated["placement"])
        self.assertEqual(hydrated["visibility"], "players")
        self.assertEqual(hydrated["display_mode"], "dot")
        self.assertFalse(hydrated["name_revealed"])
        self.assertFalse(hydrated["faction_revealed"])
        self.assertEqual(hydrated["faction_organization_id"], "")
        self.assertEqual(hydrated["label_offset"], {"x": 0.0, "y": 0.0})
        self.assertEqual(hydrated["nameplate_scale"], 1.0)

    def test_cleared_campaign_placement_stays_clear_during_hydration(self):
        authored = {
            "placement": {
                "location_id": "legacy-location",
                "floor_id": "",
                "map_id": "legacy-map",
                "x": 0.2,
                "y": 0.8,
            },
            "visibility": "headmaster",
        }
        campaign_state = {
            **default_campaign_person_state(),
            "current_state": "Watching",
        }
        compacted = compact_campaign_person_overlays({"person-1": campaign_state})
        self.assertEqual(compacted, {"person-1": {"current_state": "Watching"}})
        normalized = normalize_campaign({
            "record_id": "campaign-1",
            "name": "Cleared",
            "game_world_start_date": "1943-09-01",
            "game_state": {"people": compacted},
        })["game_state"]["people"]["person-1"]

        hydrated = hydrate_campaign_person_board(authored, normalized)

        self.assertIsNone(hydrated["placement"])
        self.assertEqual(hydrated["visibility"], "players")

    def test_reset_game_state_targets_one_campaign_and_preserves_clock(self):
        target = self.repository.save_campaign("Test camp", "1943-09-01")
        untouched = self.repository.save_campaign("Charms Check", "1991-09-01")

        def dirty(state):
            state.update({
                "initialized": True,
                "current_game_datetime": "1943-10-31T22:15",
                "loaded_map_ids": ["map-1"],
                "active_map_id": "map-1",
                "people": {
                    "person-1": {
                        **default_campaign_person_state(),
                        "current_state": "Hidden",
                    }
                },
            })

        self.repository.update_game_state(target["record_id"], dirty)
        untouched_before = self.repository.get(untouched["record_id"])
        untouched_raw_before = next(
            item for item in json.loads(self.path.read_text(encoding="utf-8"))["campaigns"]
            if item["record_id"] == untouched["record_id"]
        )

        reset = self.repository.reset_game_state(target["record_id"])

        state = reset["game_state"]
        self.assertFalse(state["initialized"])
        self.assertEqual(state["current_game_datetime"], "1943-10-31T22:15")
        self.assertEqual(state["loaded_map_ids"], [])
        self.assertEqual(state["maps"], {})
        self.assertEqual(state["people"], {})
        self.assertEqual(state["groups"], [])
        self.assertEqual(state["battles"], {})
        self.assertEqual(
            self.repository.get(untouched["record_id"]), untouched_before
        )
        untouched_raw_after = next(
            item for item in json.loads(self.path.read_text(encoding="utf-8"))["campaigns"]
            if item["record_id"] == untouched["record_id"]
        )
        self.assertEqual(untouched_raw_after, untouched_raw_before)

    def test_default_person_state_is_implicit_and_round_trips(self):
        default = default_campaign_person_state()
        self.assertEqual(compact_campaign_person_overlays({"person-1": default}), {})

        campaign = self.repository.save_campaign("Sparse", "2000-01-01")
        for field, changed_value in {
            "visibility": "headmaster",
            "display_mode": "token",
            "current_state": "Unconscious",
            "airborne": True,
            "currency_knuts": 7,
        }.items():
            state = default_campaign_person_state()
            state[field] = changed_value
            compacted = compact_campaign_person_overlays({"person-1": state})
            campaign["game_state"]["people"] = compacted
            hydrated = normalize_campaign(campaign)["game_state"]["people"]["person-1"]
            self.assertEqual(hydrated[field], changed_value)
            self.assertEqual(hydrated["label_offset"], {"x": 0.0, "y": 0.0})

    def test_compaction_preserves_battle_actor_markers_without_mutating_source(self):
        campaign = self.repository.save_campaign("Battle", "2000-01-01")
        campaign["game_state"]["people"] = {
            "person-1": default_campaign_person_state()
        }
        campaign["game_state"]["battles"] = {
            "battle-1": {
                "record_id": "battle-1",
                "name": "Test battle",
                "map_id": "map-1",
                "participants": [{
                    "record_id": "participant-1",
                    "actor_type": "person",
                    "actor_id": "person-1",
                }],
            }
        }
        source = {
            "campaigns": [campaign],
            "_headmasters_scroll": {"revision_id": "unchanged"},
        }
        compacted = compact_campaign_document_for_storage(source)
        self.assertEqual(compacted["campaigns"][0]["game_state"]["people"], {
            "person-1": {}
        })
        self.assertIn("placement", source["campaigns"][0]["game_state"]["people"]["person-1"])
        hydrated = normalize_campaign(compacted["campaigns"][0])
        self.assertIsNone(hydrated["game_state"]["people"]["person-1"]["placement"])

    def test_repository_saves_only_non_default_person_overlays(self):
        campaign = self.repository.save_campaign("Sparse saves", "2000-01-01")

        def update(state):
            state["people"] = {
                "default-person": default_campaign_person_state(),
                "changed-person": {
                    **default_campaign_person_state(),
                    "current_state": "Hidden",
                },
            }

        self.repository.update_game_state(campaign["record_id"], update)
        raw = json.loads(self.path.read_text(encoding="utf-8"))["campaigns"][0]
        self.assertNotIn("default-person", raw["game_state"]["people"])
        self.assertEqual(raw["game_state"]["people"]["changed-person"], {
            "current_state": "Hidden"
        })
        hydrated = self.repository.get(campaign["record_id"])
        self.assertEqual(
            hydrated["game_state"]["people"]["changed-person"]["visibility"],
            "players",
        )

    def test_board_cameras_are_resolution_independent_and_validated(self):
        self.assertEqual(
            normalize_board_camera({"zoom": 12, "center_x": 0.2, "center_y": 0.8}),
            {"zoom": 12.0, "center_x": 0.2, "center_y": 0.8},
        )
        with self.assertRaises(ValueError):
            normalize_board_camera({"zoom": 33, "center_x": 0.5, "center_y": 0.5})
        with self.assertRaises(ValueError):
            normalize_board_camera({"zoom": 2, "center_x": -0.1, "center_y": 0.5})

    def test_campaign_events_are_appended_without_copying_world_history(self):
        campaign = self.repository.save_campaign(
            "Branch Campaign", "2000-01-01", history_policy="discard"
        )
        event = self.repository.add_event(
            campaign["record_id"],
            "add_wound",
            "2000-02-03",
            event_time="14:15",
            details={"person_ids": ["person-1"], "severity": "light"},
        )
        stored = self.repository.get(campaign["record_id"])
        self.assertEqual(stored["history_policy"], "discard")
        self.assertEqual(stored["events"], [event])
        self.assertEqual(event["person_ids"], ["person-1"])
        self.assertNotIn("world_events", stored)

    def test_request_approval_and_event_append_are_one_save(self):
        campaign = self.repository.save_campaign("Requests", "2000-01-01")
        request = self.repository.add_request(
            campaign["record_id"], "teaching",
            {"pupil_person_id": "pupil", "knowledge_record_id": "spell"},
        )
        resolved = self.repository.resolve_request(
            campaign["record_id"], request["record_id"], "approved",
            event_type="taught_spell", event_date="2000-01-02",
            event_details={"person_ids": ["pupil"], "knowledge_record_id": "spell"},
        )
        stored = self.repository.get(campaign["record_id"])
        self.assertEqual(resolved["status"], "approved")
        self.assertEqual(stored["requests"][0]["event_id"], stored["events"][0]["record_id"])

    def test_shared_tags_equipment_and_state_resolution_persist(self):
        campaign = self.repository.save_campaign("Connected State", "2000-01-01")

        def add_shared_state(value):
            value["shared_tags"] = [{
                "record_id": "tag-1", "name": "Door Magic",
                "created_by_player_id": "contact-1", "created_at": "2000-01-01T00:00:00Z",
            }]
            value["tag_assignments"] = [{
                "record_id": "assignment-1", "collection": "spells",
                "target_record_id": "spell-1", "tag_id": "tag-1",
                "created_by_player_id": "contact-1", "created_at": "2000-01-01T00:00:00Z",
            }]

        self.repository.update_campaign(campaign["record_id"], add_shared_state)
        request = self.repository.add_request(campaign["record_id"], "equipment_change", {})

        def equip(state):
            state.setdefault("people", {}).setdefault("person-1", {}).setdefault("equipment", {})["focus"] = "wand-instance"

        self.repository.resolve_request(
            campaign["record_id"], request["record_id"], "approved",
            event_type="equipment_changed", event_date="2000-01-01", state_updater=equip,
        )
        stored = self.repository.get(campaign["record_id"])
        self.assertEqual(stored["shared_tags"][0]["created_by_player_id"], "contact-1")
        self.assertEqual(stored["tag_assignments"][0]["target_record_id"], "spell-1")
        self.assertEqual(stored["game_state"]["people"]["person-1"]["equipment"]["focus"], "wand-instance")

    def test_flyable_equipment_and_airborne_state_persist(self):
        campaign = self.repository.save_campaign("Flying", "2000-01-01")

        def mount(state):
            person = state.setdefault("people", {}).setdefault("person-1", {})
            person["equipment"] = {"flyable": "broom-instance"}
            person["airborne"] = True

        self.repository.update_game_state(campaign["record_id"], mount)
        person = self.repository.get(campaign["record_id"])["game_state"]["people"]["person-1"]
        self.assertEqual(person["equipment"]["flyable"], "broom-instance")
        self.assertTrue(person["airborne"])
        self.assertEqual(
            set(person["equipment"]),
            {"focus", "accessory_1", "accessory_2", "flyable"},
        )

    def test_battle_condition_and_typed_wound_persist(self):
        campaign = self.repository.save_campaign("Battle state", "2000-01-01")

        def injure(state):
            person = state.setdefault("people", {}).setdefault("person-1", {})
            person["current_state"] = "Unconscious"
            person["wounds"] = [{
                "record_id": "wound-1", "severity": "heavy",
                "injury_type": "Blunt force/Crushing",
                "note": "Struck by falling masonry",
                "created_at": "2000-01-01T12:00:00Z",
            }]

        self.repository.update_game_state(campaign["record_id"], injure)
        person = self.repository.get(campaign["record_id"])["game_state"]["people"]["person-1"]
        self.assertEqual(person["current_state"], "Unconscious")
        self.assertEqual(person["wounds"][0]["injury_type"], "Blunt force/Crushing")


if __name__ == "__main__":
    unittest.main()
