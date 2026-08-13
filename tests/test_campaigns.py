import json
import tempfile
import unittest
from pathlib import Path

from headmasters_scroll.campaigns import (
    CampaignRepository,
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


if __name__ == "__main__":
    unittest.main()
