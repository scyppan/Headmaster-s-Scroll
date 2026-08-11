import importlib.util
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from PIL import Image
from fastapi.testclient import TestClient

from headmasters_scroll.assets import AssetStore, MAP_CANVAS_SIZE
from headmasters_scroll.campaigns import CampaignRepository
from headmasters_scroll.board import (
    OFF_LIMITS_MESSAGE,
    WorldBoardRepository,
    active_faction_ids,
    normalize_map,
    validate_world_board,
)
from headmasters_scroll.store import SharedJsonStore
from headmasters_scroll.game_board.server import create_apps
from headmasters_scroll.game_board.service import GameBoardService
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
        self.assertEqual((two["width"], two["height"]), MAP_CANVAS_SIZE)
        self.assertEqual(two["file_extension"], ".png")
        self.assertEqual((two["source_width"], two["source_height"]), (500, 1000))
        with Image.open(self.assets.resolve(two["asset_id"], two)) as stored:
            self.assertEqual(stored.size, MAP_CANVAS_SIZE)
        moved = self.repository.move_person("pc-1", "map-1", 0.42, 0.61)
        self.assertEqual((moved["x"], moved["y"]), (0.42, 0.61))

    def test_factions_are_date_aware_and_expired_selection_is_unknown(self):
        document = world_document()
        self.assertEqual(active_faction_ids(document, "pc-1", "2000-06-01T12:00"), ["house-red"])
        self.assertEqual(active_faction_ids(document, "pc-1", "2002-06-01T12:00"), [])
        snapshot = self.repository.snapshot("2002-06-01T12:00", player_character_ids=["pc-1"])
        actor = next(item for item in snapshot["actors"] if item["actor_id"] == "pc-1")
        self.assertEqual(actor["faction_name"], "Unknown")

    def test_player_snapshot_requires_explicit_reveal_and_hides_npc_identity(self):
        concealed = self.repository.snapshot(
            "2000-06-01T12:00",
            player_character_ids=["pc-1"],
            for_players=True,
        )
        self.assertEqual(concealed["maps"], [])
        self.assertEqual(concealed["actors"], [])
        self.repository.set_map_published("map-1", True)
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

    def test_regions_validate_persist_and_enter_player_snapshot_safely(self):
        region = {
            "record_id": "region-gringotts",
            "name": "Gringotts",
            "type_label": "Bank",
            "behavior_type": "shop",
            "hover_text": "The most famous wizarding bank in the world.",
            "points": [
                {"x": 0.1, "y": 0.2},
                {"x": 0.8, "y": 0.2},
                {"x": 0.7, "y": 0.7},
            ],
            "target_location_id": "",
            "created_at": "2026-08-10T00:00:00Z",
            "last_updated": "2026-08-10T00:00:00Z",
        }
        session = self.repository.load()
        session.data["maps"][0]["regions"] = [region]
        session.data["maps"][0]["players_published"] = True
        self.repository.save(session, "mapper")
        reloaded = self.repository.load().data["maps"][0]["regions"]
        self.assertEqual(reloaded, [region])
        admin = self.repository.snapshot("2000-06-01T12:00")
        player = self.repository.snapshot("2000-06-01T12:00", player_character_ids=["pc-1"], for_players=True)
        self.assertEqual(admin["maps"][0]["regions"][0]["name"], "Gringotts")
        public_region = player["maps"][0]["regions"][0]
        self.assertEqual(public_region["name"], "Gringotts")
        self.assertEqual(public_region["hover_text"], region["hover_text"])
        self.assertNotIn("type_label", public_region)

    def test_confirmed_obscurations_are_public_opaque_geometry_but_preview_settings_are_private(self):
        shape = {
            "record_id": "obscuration-1",
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.4, "y": 0.1},
                {"x": 0.3, "y": 0.4},
            ],
            "created_at": "2026-08-10T00:00:00Z",
            "last_updated": "2026-08-10T00:00:00Z",
        }
        saved = self.repository.set_map_presentation(
            "map-1",
            published=True,
            obscurations=[shape],
            preview_opacity=0.35,
            preview_color="#ff0000",
        )
        self.assertEqual(saved["obscuration_preview_opacity"], 0.35)
        player = self.repository.snapshot(
            "2000-06-01T12:00", player_character_ids=["pc-1"], for_players=True
        )
        public_map = player["maps"][0]
        self.assertEqual(public_map["obscurations"], [{"record_id": "obscuration-1", "points": shape["points"]}])
        self.assertNotIn("obscuration_preview_opacity", public_map)
        self.assertNotIn("obscuration_preview_color", public_map)

    def test_travel_requires_revealed_destination_and_rejects_obscured_clicks(self):
        session = self.repository.load()
        session.data["locations"].append({
            "record_id": "village",
            "name": "Village",
            "is_building": False,
            "floors": [],
            "default_map_id": "map-2",
        })
        session.data["maps"].append({
            "record_id": "map-2",
            "name": "Village",
            "location_id": "village",
            "floor_id": "",
            "players_published": False,
            "asset": None,
        })
        session.data["maps"][0]["regions"] = [{
            "record_id": "road-out",
            "name": "Village road",
            "type_label": "Travel",
            "behavior_type": "travel",
            "hover_text": "Follow the road.",
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.5, "y": 0.1}, {"x": 0.3, "y": 0.5}],
            "target_location_id": "village",
        }]
        self.repository.save(session, "mapper")
        obscuration = {
            "record_id": "fog-road",
            "points": [{"x": 0.2, "y": 0.15}, {"x": 0.4, "y": 0.15}, {"x": 0.3, "y": 0.3}],
        }
        self.repository.set_map_presentation(
            "map-1", published=True, obscurations=[obscuration]
        )
        with self.assertRaisesRegex(PermissionError, "obscured"):
            self.repository.travel_person("pc-1", "map-1", "road-out", 0.3, 0.2)
        self.repository.set_map_presentation(
            "map-1", published=True, obscurations=[]
        )
        concealed_snapshot = self.repository.snapshot(
            "2000-06-01T12:00", player_character_ids=["pc-1"], for_players=True
        )
        travel_region = concealed_snapshot["maps"][0]["regions"][0]
        self.assertFalse(travel_region["target_available"])
        self.assertEqual(travel_region["target_map_id"], "")
        with self.assertRaisesRegex(PermissionError, OFF_LIMITS_MESSAGE):
            self.repository.travel_person("pc-1", "map-1", "road-out", 0.3, 0.2)
        self.repository.set_map_published("map-2", True)
        moved = self.repository.travel_person("pc-1", "map-1", "road-out", 0.3, 0.2)
        self.assertEqual(moved["map_id"], "map-2")
        self.assertEqual((moved["x"], moved["y"]), (0.5, 0.5))

    def test_map_start_point_spawns_unplaced_players_without_stacking(self):
        session = self.repository.load()
        session.data["maps"][0]["players_published"] = True
        session.data["maps"][0]["start_point"] = {"x": 0.42, "y": 0.61}
        session.data["maps"][0]["token_scale"] = 0.06
        session.data["people"][0]["board"]["placement"] = None
        session.data["people"].append({
            "record_id": "pc-2",
            "displayed_name": "Player Two",
            "player_character": True,
            "board": {
                "portrait": None,
                "placement": None,
                "visibility": "players",
                "display_mode": "dot",
                "name_revealed": False,
                "faction_revealed": False,
                "faction_organization_id": "",
            },
        })
        self.repository.save(session, "game-board")

        first = self.repository.ensure_person_placement("pc-1")
        second = self.repository.ensure_person_placement("pc-2")

        self.assertEqual((first["x"], first["y"]), (0.42, 0.61))
        self.assertEqual(first["map_id"], "map-1")
        self.assertEqual(second["map_id"], "map-1")
        self.assertNotEqual((second["x"], second["y"]), (first["x"], first["y"]))

    def test_travel_region_arrives_at_its_linked_warp_point(self):
        session = self.repository.load()
        session.data["locations"].append({
            "record_id": "tower",
            "name": "Tower",
            "is_building": True,
            "has_floors": True,
            "floors": [{
                "record_id": "tower-upper",
                "name": "Upper Floor",
                "sort_order": 0,
                "primary_map_id": "map-2",
            }],
            "default_map_id": "map-2",
        })
        session.data["maps"].append({
            "record_id": "map-2",
            "name": "Upper Floor",
            "location_id": "tower",
            "floor_id": "tower-upper",
            "players_published": True,
            "asset": None,
            "warp_points": [{
                "record_id": "warp-upper-stair",
                "name": "Upper stair landing",
                "x": 0.18,
                "y": 0.74,
            }],
        })
        session.data["maps"][0]["players_published"] = True
        session.data["maps"][0]["regions"] = [{
            "record_id": "stairs-up",
            "name": "Stairs up",
            "behavior_type": "travel",
            "hover_text": "Climb the stairs.",
            "points": [
                {"x": 0.1, "y": 0.1},
                {"x": 0.5, "y": 0.1},
                {"x": 0.3, "y": 0.5},
            ],
            "target_location_id": "tower",
            "target_warp_point_id": "warp-upper-stair",
        }]
        self.repository.save(session, "mapper")

        public = self.repository.snapshot(
            "2000-06-01T12:00", player_character_ids=["pc-1"], for_players=True
        )
        public_region = public["maps"][0]["regions"][0]
        self.assertTrue(public_region["target_available"])
        self.assertEqual(public_region["target_map_id"], "map-2")
        self.assertNotIn("target_warp_point_id", public_region)

        moved = self.repository.travel_person("pc-1", "map-1", "stairs-up", 0.3, 0.2)
        self.assertEqual(moved["map_id"], "map-2")
        self.assertEqual((moved["x"], moved["y"]), (0.18, 0.74))

    def test_region_validation_rejects_bad_geometry_and_destinations(self):
        base = {
            "record_id": "region-1",
            "name": "Door",
            "type_label": "Exit",
            "behavior_type": "travel",
            "hover_text": "Leave",
            "points": [{"x": 0.1, "y": 0.1}, {"x": 0.8, "y": 0.1}, {"x": 0.5, "y": 0.8}],
            "target_location_id": "castle",
        }
        document = world_document()
        document["maps"][0]["regions"] = [base]
        validate_world_board(document)
        broken = world_document()
        broken_region = dict(base, behavior_type="shop")
        broken["maps"][0]["regions"] = [broken_region]
        with self.assertRaises(ValueError):
            validate_world_board(broken)
        repeated = world_document()
        repeated_region = dict(base, points=[base["points"][0], base["points"][1], base["points"][0]])
        repeated["maps"][0]["regions"] = [repeated_region]
        with self.assertRaises(ValueError):
            validate_world_board(repeated)

    def test_legacy_map_normalizes_to_empty_regions(self):
        self.assertEqual(normalize_map(world_document()["maps"][0])["regions"], [])

    def test_only_location_assigned_maps_are_available_without_a_game_session(self):
        session = self.repository.load()
        session.data["maps"].append({
            "record_id": "orphan-map",
            "name": "Defunct catalog entry",
            "location_id": "castle",
            "floor_id": "",
            "players_published": False,
            "asset": None,
        })
        self.repository.save(session, "test")
        location_maps = self.repository.location_maps()
        self.assertEqual([item["record_id"] for item in location_maps], ["map-1"])
        self.assertEqual(location_maps[0]["location_name"], "Castle")
        self.assertEqual(
            location_maps[0]["location_ancestry"],
            [{"record_id": "castle", "name": "Castle"}],
        )
        self.assertEqual(location_maps[0]["floor_name"], "First Floor")
        self.assertTrue(location_maps[0]["is_location_default"])
        self.assertTrue(location_maps[0]["is_floor_primary"])

    def test_orphan_maps_and_their_occupants_do_not_enter_board_snapshots(self):
        session = self.repository.load()
        session.data["maps"].append({
            "record_id": "orphan-map",
            "name": "Defunct catalog entry",
            "location_id": "castle",
            "floor_id": "",
            "players_published": True,
            "asset": None,
        })
        session.data["people"][0]["board"]["placement"].update({
            "map_id": "orphan-map",
            "floor_id": "",
        })
        self.repository.save(session, "test")
        snapshot = self.repository.snapshot(
            "2000-06-01T08:00", player_character_ids=["pc-1"]
        )
        self.assertEqual([item["record_id"] for item in snapshot["maps"]], ["map-1"])
        self.assertNotIn("pc-1", [item["actor_id"] for item in snapshot["actors"]])

    def test_location_records_are_unique_for_single_default_map_ownership(self):
        document = world_document()
        document["locations"].append(dict(document["locations"][0]))
        with self.assertRaises(ValueError):
            validate_world_board(document)

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

    def test_map_import_rejects_unsafe_svg_before_replacing_asset(self):
        original = self.directory / "original.png"
        Image.new("RGB", (200, 100), "green").save(original)
        metadata = self.assets.import_map("map-1", original)
        output = self.assets.resolve(metadata["asset_id"], metadata)
        old_bytes = output.read_bytes()
        unsafe = self.directory / "unsafe.svg"
        unsafe.write_text(
            '<svg width="200" height="100" xmlns="http://www.w3.org/2000/svg">'
            '<image href="https://example.com/private.png"/></svg>',
            encoding="utf-8",
        )
        with self.assertRaises(ValueError):
            self.assets.import_map("map-1", unsafe)
        self.assertEqual(output.read_bytes(), old_bytes)

    @unittest.skipUnless(importlib.util.find_spec("resvg_py"), "resvg_py is installed with project dependencies")
    def test_svg_import_renders_png_and_keeps_source(self):
        source = self.directory / "base.svg"
        source.write_text(
            '<svg width="320" height="180" xmlns="http://www.w3.org/2000/svg">'
            '<rect width="320" height="180" fill="#663399"/></svg>',
            encoding="utf-8",
        )
        original = source.read_bytes()
        metadata = self.assets.import_map("map-svg", source)
        self.assertEqual(metadata["file_extension"], ".png")
        self.assertEqual((metadata["width"], metadata["height"]), MAP_CANVAS_SIZE)
        self.assertEqual((metadata["source_width"], metadata["source_height"]), (320, 180))
        with Image.open(self.assets.resolve(metadata["asset_id"], metadata)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertEqual(image.size, MAP_CANVAS_SIZE)
        self.assertEqual(source.read_bytes(), original)


class ProtectedAssetApiTests(unittest.TestCase):
    ORIGIN = "https://players.example.com"

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        world = world_document()
        world["maps"][0]["players_published"] = True
        source = self.directory / "map.png"
        Image.new("RGB", (320, 180), "purple").save(source)
        assets = AssetStore(self.directory / "assets")
        self.assets = assets
        world["maps"][0]["asset"] = assets.import_map("map-1", source)
        (self.directory / "world.json").write_text(json.dumps(world), encoding="utf-8")
        campaign_data = {
            "schema_version": 1,
            "_headmasters_scroll": {
                "revision_id": "campaign-board-revision",
                "last_modified_at": "2026-08-11T00:00:00Z",
                "last_modified_by": "test",
            },
            "campaigns": [{
                "record_id": "campaign-1",
                "name": "Board Campaign",
                "game_world_start_date": "2000-06-01",
                "created_at": "2026-08-11T00:00:00Z",
                "last_updated": "2026-08-11T00:00:00Z",
            }],
        }
        (self.directory / "campaign.json").write_text(
            json.dumps(campaign_data), encoding="utf-8"
        )
        private = GameBoardRepository(self.directory / "private")
        self.private = private
        settings = private.settings()
        settings.update(
            wordpress_player_url=f"{self.ORIGIN}/game-board/",
            allowed_origin=self.ORIGIN,
            public_api_base="https://board.example.com",
        )
        private.save_settings(settings)
        shared = SharedJsonStore(self.directory)
        self.shared = shared
        self.campaigns = CampaignRepository(shared)
        admin_app, player_app, self.runtime = create_apps(
            private, self.campaigns
        )
        self.runtime.service.shared_store = shared
        self.runtime.service.world_board = WorldBoardRepository(shared, assets)
        self.admin = TestClient(admin_app)
        self.player = TestClient(player_app)
        self.admin_headers = {"X-Admin-Key": settings["admin_key"]}
        self.origin_headers = {"Origin": self.ORIGIN}
        contact = self.runtime.service.add_contact("Alice", "alice@example.com")
        self.runtime.service.assign_character(contact["id"], "pc-1")
        session = self.runtime.service.create_session(
            "Board",
            (date.today() + timedelta(days=1)).isoformat(),
            [contact["id"]],
            campaign_id="campaign-1",
        )
        self.session_id = session["id"]
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

    def test_campaign_restores_workspace_clock_maps_groups_positions_and_sizes(self):
        world_before = (self.directory / "world.json").read_bytes()
        requests = (
            self.admin.put(
                "/api/admin/board/workspace",
                headers=self.admin_headers,
                json={
                    "session_id": self.session_id,
                    "loaded_map_ids": ["map-1"],
                    "active_map_id": "map-1",
                },
            ),
            self.admin.put(
                "/api/admin/board/maps/map-1/settings",
                headers=self.admin_headers,
                json={
                    "session_id": self.session_id,
                    "token_scale": 0.007,
                    "start_point": {"x": 0.35, "y": 0.45},
                    "update_start_point": True,
                },
            ),
            self.admin.put(
                "/api/admin/board/maps/map-1/presentation",
                headers=self.admin_headers,
                json={
                    "session_id": self.session_id,
                    "published": True,
                    "obscurations": [],
                    "preview_opacity": 0.35,
                    "preview_color": "#ff0000",
                },
            ),
            self.admin.post(
                "/api/admin/board/move",
                headers=self.admin_headers,
                json={
                    "session_id": self.session_id,
                    "person_id": "pc-1",
                    "map_id": "map-1",
                    "x": 0.41,
                    "y": 0.62,
                },
            ),
            self.admin.post(
                "/api/admin/board/groups",
                headers=self.admin_headers,
                json={
                    "session_id": self.session_id,
                    "name": "Party",
                    "location_id": "castle",
                    "person_ids": ["pc-1", "npc-1"],
                },
            ),
            self.admin.put(
                f"/api/admin/sessions/{self.session_id}/game-datetime",
                headers=self.admin_headers,
                json={"game_datetime": "2000-06-02T14:35"},
            ),
        )
        for response in requests:
            self.assertEqual(response.status_code, 200, response.text)

        state = self.campaigns.get("campaign-1")["game_state"]
        self.assertEqual(state["current_game_datetime"], "2000-06-02T14:35")
        self.assertEqual(state["loaded_map_ids"], ["map-1"])
        self.assertEqual(state["active_map_id"], "map-1")
        self.assertTrue(state["maps"]["map-1"]["players_published"])
        self.assertEqual(state["maps"]["map-1"]["token_scale"], 0.007)
        self.assertEqual(state["maps"]["map-1"]["start_point"], {"x": 0.35, "y": 0.45})
        placement = state["people"]["pc-1"]["placement"]
        self.assertEqual((placement["x"], placement["y"]), (0.41, 0.62))
        self.assertEqual(state["groups"][0]["name"], "Party")
        self.assertEqual((self.directory / "world.json").read_bytes(), world_before)

        resumed = GameBoardService(self.private, self.campaigns)
        resumed.shared_store = self.shared
        resumed.world_board = WorldBoardRepository(self.shared, self.assets)
        snapshot = resumed.board_snapshot(self.session_id)
        actor = next(item for item in snapshot["actors"] if item["actor_id"] == "pc-1")
        map_record = next(item for item in snapshot["maps"] if item["record_id"] == "map-1")
        self.assertEqual(snapshot["game_datetime"], "2000-06-02T14:35")
        self.assertEqual(snapshot["loaded_map_ids"], ["map-1"])
        self.assertEqual((actor["x"], actor["y"]), (0.41, 0.62))
        self.assertEqual(map_record["token_scale"], 0.007)
        self.assertEqual(snapshot["groups"][0]["name"], "Party")


if __name__ == "__main__":
    unittest.main()
