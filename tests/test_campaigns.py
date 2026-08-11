import json
import tempfile
import unittest
from pathlib import Path

from headmasters_scroll.campaigns import CampaignRepository, normalize_game_world_date
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


if __name__ == "__main__":
    unittest.main()
