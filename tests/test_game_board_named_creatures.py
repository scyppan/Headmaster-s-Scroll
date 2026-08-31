import json
import random
import tempfile
import unittest
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from headmasters_scroll.campaigns import CampaignRepository
from headmasters_scroll.creatures import (
    generate_creature_instance,
    normalize_campaign_creature,
)
from headmasters_scroll.game_board.server import create_apps
from headmasters_scroll.game_board.service import GameBoardService
from headmasters_scroll.game_board.storage import GameBoardRepository
from headmasters_scroll.store import SharedJsonStore


def campaign_document():
    return {
        "schema_version": 1,
        "_headmasters_scroll": {
            "revision_id": "named-creature-test",
            "last_modified_at": "2026-08-30T00:00:00Z",
            "last_modified_by": "test",
        },
        "campaigns": [{
            "record_id": "campaign-1",
            "name": "Named Creature Campaign",
            "game_world_start_date": "2000-01-01",
            "created_at": "2026-08-30T00:00:00Z",
            "last_updated": "2026-08-30T00:00:00Z",
        }],
    }


class NamedCreatureServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "campaign.json").write_text(
            json.dumps(campaign_document()), encoding="utf-8"
        )
        self.repository = GameBoardRepository(root)
        campaigns = CampaignRepository(SharedJsonStore(root))
        self.service = GameBoardService(self.repository, campaigns)
        player = self.service.add_contact("Player", "player@example.com")
        self.session = self.service.create_session(
            "Named creatures",
            (date.today() + timedelta(days=1)).isoformat(),
            [player["id"]],
            campaign_id="campaign-1",
        )
        self.world = deepcopy(self.service._world_document())
        self.species = deepcopy(
            self.service._database_document().get("creatures", [])[0]
        )
        generated = generate_creature_instance(
            self.species,
            1,
            {
                "location_id": "solidification",
                "floor_id": "",
                "map_id": "solidification",
                "x": 0.5,
                "y": 0.5,
            },
            random.Random(17),
        )
        self.named = {
            "record_id": "named-creature-test",
            "name": "Pip",
            "species_record_id": self.species["record_id"],
            "generated": deepcopy(generated["generated"]),
            "actions": deepcopy(generated["actions"]),
            "statistics_solidified": True,
        }
        self.world.setdefault("named_creatures", []).append(self.named)
        world_patch = patch.object(
            self.service, "_world_document", return_value=self.world
        )
        world_patch.start()
        self.addCleanup(world_patch.stop)

    def tearDown(self):
        self.temporary.cleanup()

    def test_unplaced_campaign_creatures_are_valid_but_partial_places_are_not(self):
        generated = generate_creature_instance(
            self.species,
            1,
            {
                "location_id": "",
                "floor_id": "",
                "map_id": "",
                "x": 0.5,
                "y": 0.5,
            },
            random.Random(8),
        )

        self.assertEqual(generated["placement"]["map_id"], "")
        invalid = deepcopy(generated)
        invalid["placement"]["map_id"] = "map-only"
        with self.assertRaisesRegex(ValueError, "map and location together"):
            normalize_campaign_creature(invalid)

    def test_generic_creature_can_join_campaign_before_a_map_is_open(self):
        created = self.service.place_campaign_creature(
            self.session["id"], self.species["record_id"]
        )

        self.assertEqual(created["placement"]["map_id"], "")
        self.assertEqual(created["placement"]["location_id"], "")
        actor = next(
            item for item in self.service.board_snapshot(self.session["id"])["actors"]
            if item.get("actor_id") == created["record_id"]
        )
        self.assertEqual(actor["actor_type"], "creature")
        self.assertEqual(actor["map_id"], "")

    def test_named_creature_can_be_added_unplaced_once_with_fixed_stats(self):
        result = self.service.place_named_creature(
            self.session["id"], self.named["record_id"]
        )

        self.assertTrue(result["created"])
        self.assertEqual(result["named_creature_id"], self.named["record_id"])
        self.assertEqual(result["display_name"], "Pip")
        self.assertEqual(result["placement"]["map_id"], "")
        self.assertEqual(result["generated"], self.named["generated"])
        self.assertEqual(result["actions"], self.named["actions"])
        state = self.service.campaign_repository.get(
            "campaign-1"
        )["game_state"]
        self.assertEqual(len(state["creatures"]), 1)
        with self.assertRaisesRegex(ValueError, "already part"):
            self.service.place_named_creature(
                self.session["id"], self.named["record_id"]
            )

    def test_unplaced_named_creature_appears_only_on_headmaster_board(self):
        created = self.service.place_named_creature(
            self.session["id"], self.named["record_id"]
        )

        headmaster = self.service.board_snapshot(self.session["id"])
        actor = next(
            item for item in headmaster["actors"]
            if item.get("actor_id") == created["record_id"]
        )
        self.assertEqual(actor["internal_label"], "Pip")
        self.assertEqual(actor["true_name"], self.species["name"])
        self.assertEqual(actor["named_creature_id"], self.named["record_id"])
        self.assertEqual(actor["map_id"], "")
        player = self.service.board_snapshot(
            self.session["id"], for_players=True, contact_id="unknown"
        )
        self.assertNotIn(
            created["record_id"],
            {item.get("actor_id") for item in player["actors"]},
        )

    def test_named_creature_search_reports_species_and_materialization(self):
        before = self.service.named_creature_choices(
            self.session["id"], "pip"
        )
        self.assertEqual(before[0]["species_name"], self.species["name"])
        self.assertFalse(before[0]["materialized"])

        created = self.service.place_named_creature(
            self.session["id"], self.named["record_id"]
        )
        after = self.service.named_creature_choices(
            self.session["id"], "pip"
        )
        self.assertTrue(after[0]["materialized"])
        self.assertEqual(after[0]["campaign_creature_id"], created["record_id"])

    def test_named_creature_identity_survives_death_and_cannot_be_rerolled(self):
        created = self.service.place_named_creature(
            self.session["id"], self.named["record_id"]
        )
        creature_id = created["record_id"]

        with self.assertRaisesRegex(ValueError, "cannot be rerolled"):
            self.service.creature_campaign_action(
                self.session["id"], creature_id, "reroll"
            )

        def remove_harvest_pools(state):
            state["creatures"][creature_id]["harvest_pools"] = []

        self.service.campaign_repository.update_game_state(
            "campaign-1", remove_harvest_pools
        )
        killed = self.service.creature_campaign_action(
            self.session["id"], creature_id, "kill"
        )
        self.assertEqual(killed["life_state"], "dead")
        self.assertEqual(killed["named_creature_id"], self.named["record_id"])
        self.assertEqual(killed["display_name"], "Pip")
        revived = self.service.creature_campaign_action(
            self.session["id"], creature_id, "revive"
        )
        self.assertEqual(revived["life_state"], "alive")

    def test_named_creature_battle_materialization_is_unique_and_atomic(self):
        map_id = self.service.board_snapshot(self.session["id"])["maps"][0][
            "record_id"
        ]
        battle = self.service.create_battle(
            self.session["id"], "Named battle", map_id
        )
        created = self.service.add_named_creature_to_battle(
            self.session["id"], battle["record_id"], self.named["record_id"],
            map_id, 0.5, 0.5,
        )
        state = self.service.campaign_repository.get("campaign-1")["game_state"]
        self.assertEqual(created["named_creature_id"], self.named["record_id"])
        self.assertEqual(len(state["creatures"]), 1)
        self.assertEqual(
            state["battles"][battle["record_id"]]["participants"][0]["actor_id"],
            created["record_id"],
        )
        with self.assertRaisesRegex(ValueError, "already part"):
            self.service.add_named_creature_to_battle(
                self.session["id"], battle["record_id"],
                self.named["record_id"], map_id, 0.5, 0.5,
            )
        with self.assertRaisesRegex(ValueError, "already part"):
            self.service.place_named_creature(
                self.session["id"], self.named["record_id"]
            )
        unchanged = self.service.campaign_repository.get("campaign-1")[
            "game_state"
        ]
        self.assertEqual(len(unchanged["creatures"]), 1)
        self.assertEqual(
            len(unchanged["battles"][battle["record_id"]]["participants"]), 1
        )

        second = deepcopy(self.named)
        second.update(record_id="named-creature-second", name="Moth")
        self.world["named_creatures"].append(second)
        with self.assertRaisesRegex(KeyError, "Unknown battle"):
            self.service.add_named_creature_to_battle(
                self.session["id"], "missing-battle", second["record_id"],
                map_id, 0.5, 0.5,
            )
        after_failure = self.service.campaign_repository.get("campaign-1")[
            "game_state"
        ]
        self.assertFalse(any(
            item.get("named_creature_id") == second["record_id"]
            for item in after_failure["creatures"].values()
        ))


class NamedCreatureApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        (root / "campaign.json").write_text(
            json.dumps(campaign_document()), encoding="utf-8"
        )
        repository = GameBoardRepository(root)
        settings = repository.settings()
        settings.update(
            wordpress_player_url="https://players.example/game/",
            allowed_origin="https://players.example",
            public_api_base="https://board.example",
        )
        repository.save_settings(settings)
        campaigns = CampaignRepository(SharedJsonStore(root))
        admin_app, _player_app, self.runtime = create_apps(repository, campaigns)
        self.client = TestClient(admin_app)
        self.headers = {"X-Admin-Key": settings["admin_key"]}

    def tearDown(self):
        self.client.close()
        self.temporary.cleanup()

    def test_named_creature_browse_and_unplaced_materialization_routes(self):
        listed = [{
            "record_id": "pip", "name": "Pip", "materialized": False,
        }]
        with patch.object(
            self.runtime.service,
            "named_creature_choices",
            return_value=listed,
        ) as search:
            response = self.client.get(
                "/api/admin/board/named-creatures",
                headers=self.headers,
                params={"session_id": "session-a", "q": "pip", "limit": 25},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"named_creatures": listed})
        search.assert_called_once_with("session-a", "pip", 25)

        created = {
            "record_id": "campaign-pip",
            "named_creature_id": "pip",
            "placement": {"map_id": ""},
        }
        with patch.object(
            self.runtime.service,
            "place_named_creature",
            return_value=created,
        ) as place:
            response = self.client.post(
                "/api/admin/board/named-creatures/pip",
                headers=self.headers,
                json={"session_id": "session-a"},
            )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), created)
        place.assert_called_once_with(
            "session-a", "pip", None, 0.5, 0.5
        )

    def test_generic_creature_route_accepts_an_unplaced_addition(self):
        created = {
            "record_id": "campaign-owl",
            "species_id": "owl",
            "placement": {"map_id": "", "location_id": ""},
        }
        with patch.object(
            self.runtime.service,
            "place_campaign_creature",
            return_value=created,
        ) as place:
            response = self.client.post(
                "/api/admin/board/creatures",
                headers=self.headers,
                json={"session_id": "session-a", "species_id": "owl"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), created)
        place.assert_called_once_with("session-a", "owl", None, 0.5, 0.5)


if __name__ == "__main__":
    unittest.main()
