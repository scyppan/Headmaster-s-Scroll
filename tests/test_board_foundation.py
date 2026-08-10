import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from headmasters_scroll.assets import AssetStore
from headmasters_scroll.board import (
    WorldBoardRepository,
    active_faction_ids,
    validate_world_board,
)
from headmasters_scroll.store import SharedJsonStore
from headmasters_scroll.game_board.server import create_apps
from headmasters_scroll.game_board.storage import GameBoardRepository


def world_document():
    return {
        "_database": {"schema_version": 1},
        "_headmasters_scroll": {
            "revision_id": "world-revision-1",
            "last_modified_at": "2026-08-10T00:00:00Z",
            "last_modified_by": "test",
        },
        "locations": [{
            "record_id": "castle",
            "name": "Castle",
            "is_building": True,
            "floors": [{"record_id": "floor-1", "name": "First Floor", "sort_order": 0, "primary_map_id": "map-1"}],
            "default_map_id": "map-1",
        }],
        "maps": [{
            "record_id": "map-1",
            "name": "First Floor",
            "location_id": "castle",
            "floor_id": "floor-1",
            "players_published": False,
            "asset": None,
        }],
        "organizations": [{
            "record_id": "house-red",
            "name": "House Red",
            "is_faction": True,
            "faction_color": "#aa0000",
        }],
        "events": [
            {"record_id": "join-1", "event_type": "joined_faction", "date": "2000-01-01", "time": "", "person_ids": ["pc-1"], "organization_id": "house-red"},
            {"record_id": "leave-1", "event_type": "left_faction", "date": "2001-01-01", "time": "", "person_ids": ["pc-1"], "organization_id": "house-red"},
        ],
        "people": [
            {
                "record_id": "pc-1",
                "displayed_name": "Player One",
                "player_character": True,
                "board": {
                    "portrait": None,
                    "placement": {"location_id": "castle", "floor_id": "floor-1", "map_id": "map-1", "x": 0.2, "y": 0.3},
                    "visibility": "players",
                    "display_mode": "dot",
                    "name_revealed": False,
                    "faction_revealed": True,
                    "faction_organization_id": "house-red",
                },
            },
            {
                "record_id": "npc-1",
                "displayed_name": "Secret NPC",
                "player_character": False,
                "board": {
                    "portrait": None,
                    "placement": {"location_id": "castle", "floor_id": "floor-1", "map_id": "map-1", "x": 0.7, "y": 0.8},
                    "visibility": "players",
                    "display_mode": "dot",
                    "name_revealed": False,
                    "faction_revealed": False,
                    "faction_organization_id": "",
                },
            },
        ],
        "board_groups": [],
    }


class BoardFoundationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        (self.directory / "world.json").write_text(
            json.dumps(world_document(), indent=2) + "\n",
            encoding="utf-8",
        )
        self.assets = AssetStore(self.directory / "assets")
        self.repository = WorldBoardRepository(
            SharedJsonStore(self.directory),
            self.assets,
        )

    def tearDown(self):
        self.temporary.cleanup()

    def test_portrait_import_forces_square_webp_and_keeps_source(self):
        source = self.directory / "source.png"
        Image.new("RGB", (800, 600), "navy").save(source)
        original = source.read_bytes()
        metadata = self.assets.import_portrait("pc-1", source, (100, 0, 700, 600))
        output = self.assets.resolve(metadata["asset_id"], metadata)
        with Image.open(output) as image:
            self.assertEqual(image.size, (512, 512))
            self.assertEqual(image.format, "WEBP")
        self.assertEqual(source.read_bytes(), original)
        self.assertNotIn(str(output), json.dumps(metadata))

    def test_map_replace_keeps_stable_id_and_normalized_position(self):
        first = self.directory / "first.png"
        second = self.directory / "second.jpg"
        Image.new("RGB", (1000, 500), "green").save(first)
        Image.new("RGB", (500, 1000), "gold").save(second)
        one = self.assets.import_map("map-1", first)
        two = self.assets.import_map("map-1", second)
        self.assertEqual(one["asset_id"], two["asset_id"])
        self.assertEqual((two["width"], two["height"]), (500, 1000))
        moved = self.repository.move_person("pc-1", "map-1", 0.42, 0.61)
        self.assertEqual((moved["x"], moved["y"]), (0.42, 0.61))

    def test_factions_are_date_aware_and_expired_selection_is_unknown(self):
        document = world_document()
        self.assertEqual(active_faction_ids(document, "pc-1", "2000-06-01T12:00"), ["house-red"])
        self.assertEqual(active_faction_ids(document, "pc-1", "2002-06-01T12:00"), [])
        snapshot = self.repository.snapshot("2002-06-01T12:00", player_character_ids=["pc-1"])
        actor = next(item for item in snapshot["actors"] if item["actor_id"] == "pc-1")
        self.assertEqual(actor["faction_name"], "Unknown")

    def test_player_snapshot_opens_occupied_map_and_hides_npc_identity(self):
        snapshot = self.repository.snapshot(
            "2000-06-01T12:00",
            player_character_ids=["pc-1"],
            for_players=True,
        )
        self.assertEqual([item["record_id"] for item in snapshot["maps"]], ["map-1"])
        pc = next(item for item in snapshot["actors"] if item["actor_id"] == "pc-1")
        npc = next(item for item in snapshot["actors"] if item["actor_id"] == "npc-1")
        self.assertEqual(pc["display_mode"], "nameplate")
        self.assertEqual(npc["name"], "Unknown")
        self.assertEqual(npc["faction_color"], "#808080")

    def test_groups_require_one_location_and_dissolve_when_member_leaves(self):
        group = self.repository.create_group("Explorers", "castle", ["pc-1", "npc-1"])
        self.assertEqual(len(group["members"]), 2)
        self.repository.set_group("pc-1", None)
        self.assertEqual(self.repository.load().data["board_groups"], [])
        invalid = world_document()
        invalid["board_groups"] = [{
            "record_id": "bad-group",
            "name": "Bad",
            "location_id": "castle",
            "members": [{"record_id": "member-1", "actor_type": "person", "actor_id": "missing"}],
        }]
        with self.assertRaises(ValueError):
            validate_world_board(invalid)

    def test_same_field_concurrent_move_is_rejected(self):
        first = self.repository.load()
        second = self.repository.load()
        first.data["people"][0]["board"]["placement"]["x"] = 0.4
        self.repository.save(first)
        second.data["people"][0]["board"]["placement"]["x"] = 0.9
        with self.assertRaises(RuntimeError):
            self.repository.save(second)


class ProtectedAssetApiTests(unittest.TestCase):
    ORIGIN = "https://players.example.com"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        world = world_document()
        source = self.directory / "map.png"
        Image.new("RGB", (320, 180), "purple").save(source)
        assets = AssetStore(self.directory / "assets")
        world["maps"][0]["asset"] = assets.import_map("map-1", source)
        (self.directory / "world.json").write_text(json.dumps(world), encoding="utf-8")
        private = GameBoardRepository(self.directory / "private")
        settings = private.settings()
        settings.update(
            wordpress_player_url=f"{self.ORIGIN}/game-board/",
            allowed_origin=self.ORIGIN,
            public_api_base="https://board.example.com",
        )
        private.save_settings(settings)
        admin_app, player_app, self.runtime = create_apps(private)
        shared = SharedJsonStore(self.directory)
        self.runtime.service.shared_store = shared
        self.runtime.service.world_board = WorldBoardRepository(shared, assets)
        self.admin = TestClient(admin_app)
        self.player = TestClient(player_app)
        self.admin_headers = {"X-Admin-Key": settings["admin_key"]}
        self.origin_headers = {"Origin": self.ORIGIN}
        contact = self.runtime.service.add_contact("Alice", "alice@example.com")
        self.runtime.service.assign_character(contact["id"], "pc-1")
        self.runtime.service.create_session(
            "Board",
            (date.today() + timedelta(days=1)).isoformat(),
            [contact["id"]],
            game_datetime="2000-06-01T12:00",
        )
        self.invite, _link, _entry = self.runtime.service.prepare_invite(contact["id"])

    def tearDown(self):
        self.admin.close()
        self.player.close()
        self.temporary.cleanup()

    def test_assets_require_live_connection_credential_and_visibility(self):
        admission = self.player.post(
            "/v1/admissions",
            headers=self.origin_headers,
            json={"invite_token": self.invite},
        ).json()
        self.admin.post(
            f"/api/admin/admissions/{admission['request_id']}/approve",
            headers=self.admin_headers,
        )
        polled = self.player.get(
            f"/v1/admissions/{admission['request_id']}",
            headers={**self.origin_headers, "Authorization": f"Bearer {admission['poll_token']}"},
        ).json()
        self.assertEqual(
            self.player.get("/v1/assets/map%3Amap-1", headers=self.origin_headers).status_code,
            403,
        )
        credential = ""
        with self.player.websocket_connect(
            f"/v1/session?ticket={polled['ticket']}",
            headers=self.origin_headers,
        ) as socket:
            accepted = socket.receive_json()
            credential = accepted["asset_credential"]
            headers = {**self.origin_headers, "Authorization": f"Bearer {credential}"}
            response = self.player.get("/v1/assets/map%3Amap-1", headers=headers)
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.headers["cache-control"], "private, no-store")
            self.assertEqual(self.player.get("/v1/assets/map%3Asecret", headers=headers).status_code, 403)
        headers = {**self.origin_headers, "Authorization": f"Bearer {credential}"}
        self.assertEqual(self.player.get("/v1/assets/map%3Amap-1", headers=headers).status_code, 403)


if __name__ == "__main__":
    unittest.main()
