import asyncio
import base64
import json
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from headmasters_scroll.campaigns import CampaignRepository
from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    HistoricalDateTime,
    directional_minute_snap,
    format_date_display,
    format_game_datetime,
    format_stored_date,
    parse_game_datetime,
    shift_game_calendar,
)
from headmasters_scroll.game_board.gmail import GmailSender, GmailUnavailable
from headmasters_scroll.game_board.server import create_apps
from headmasters_scroll.game_board.service import (
    GameBoardService,
    format_game_datetime_for_people,
    normalize_game_datetime,
)
from headmasters_scroll.game_board.storage import GameBoardRepository
from headmasters_scroll.store import SharedJsonStore


ORIGIN = "https://players.example.com"


class FakeSocket:
    def __init__(self):
        self.messages = []

    async def send_json(self, value):
        self.messages.append(value)


class GameBoardApiTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = GameBoardRepository(Path(self.temporary.name))
        settings = self.repository.settings()
        settings.update(
            wordpress_player_url=f"{ORIGIN}/game/",
            allowed_origin=ORIGIN,
            public_api_base="https://game.example.com",
        )
        self.repository.save_settings(settings)
        campaign_data = {
            "schema_version": 1,
            "_headmasters_scroll": {
                "revision_id": "campaign-api-revision",
                "last_modified_at": "2026-08-11T00:00:00Z",
                "last_modified_by": "test",
            },
            "campaigns": [{
                "record_id": "campaign-1",
                "name": "API Campaign",
                "game_world_start_date": "1943-09-01",
                "created_at": "2026-08-11T00:00:00Z",
                "last_updated": "2026-08-11T00:00:00Z",
            }],
        }
        (Path(self.temporary.name) / "campaign.json").write_text(
            json.dumps(campaign_data), encoding="utf-8"
        )
        campaigns = CampaignRepository(SharedJsonStore(Path(self.temporary.name)))
        self.admin_app, self.player_app, self.runtime = create_apps(
            self.repository, campaigns
        )
        self.admin = TestClient(self.admin_app)
        self.player = TestClient(self.player_app)
        self.admin_headers = {"X-Admin-Key": settings["admin_key"]}
        self.origin_headers = {"Origin": ORIGIN}
        self.contact = self.runtime.service.add_contact("Alice", "alice@example.com")
        session = self.runtime.service.create_session(
            "API Test",
            (date.today() + timedelta(days=1)).isoformat(),
            [self.contact["id"]],
            campaign_id="campaign-1",
        )
        self.session_id = session["id"]
        self.invite, _link, _entry = self.runtime.service.prepare_invite(self.contact["id"])

    def tearDown(self):
        self.admin.close()
        self.player.close()
        self.temporary.cleanup()

    def admission(self):
        response = self.player.post(
            "/v1/admissions", json={"invite_token": self.invite}, headers=self.origin_headers
        )
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_public_service_does_not_expose_admin_or_data(self):
        self.assertEqual(self.player.get("/api/admin/state").status_code, 404)
        self.assertEqual(self.player.get("/data/world.json").status_code, 404)
        health = self.player.get("/health").json()
        self.assertEqual(set(health), {"service", "available", "paused"})
        self.assertEqual(self.admin.get("/api/admin/state").status_code, 403)
        self.assertEqual(self.admin.get("/api/admin/state", headers=self.admin_headers).status_code, 200)
        self.assertEqual(self.admin.get("/").status_code, 404)

    def test_admin_can_link_a_player_to_a_shared_character(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        character = state["characters"][0]
        response = self.admin.put(
            f"/api/admin/contacts/{self.contact['id']}/character",
            headers=self.admin_headers,
            json={"character_id": character["id"]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["display_name"], character["name"])
        updated = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertEqual(updated["session"]["roster"][0]["name"], character["name"])

    def test_admin_can_set_the_event_date(self):
        response = self.admin.put(
            "/api/admin/session/event-date",
            headers=self.admin_headers,
            json={"event_date": "1943-09-01"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["event_date"], "1943-09-01")
        invalid = self.admin.put(
            "/api/admin/session/event-date",
            headers=self.admin_headers,
            json={"event_date": "September 1"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_admin_can_set_the_in_world_game_datetime(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        session_id = state["sessions"][0]["id"]
        response = self.admin.put(
            f"/api/admin/sessions/{session_id}/game-datetime",
            headers=self.admin_headers,
            json={"game_datetime": "1943-09-01T19:15"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["game_datetime"], "1943-09-01T19:15")
        invalid = self.admin.put(
            f"/api/admin/sessions/{session_id}/game-datetime",
            headers=self.admin_headers,
            json={"game_datetime": "not-a-date"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_invitation_email_includes_the_in_world_game_datetime(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        session_id = state["sessions"][0]["id"]
        self.runtime.service.set_game_datetime(session_id, "1943-09-01T08:15")
        captured = {}

        class FakeGmail:
            def status(self):
                return {"connected": True}

            def send(self, recipient, subject, body):
                captured.update(recipient=recipient, subject=subject, body=body)
                return "sent-message"

        self.runtime.gmail = lambda: FakeGmail()
        response = self.admin.post(
            "/api/admin/invitations/send",
            headers=self.admin_headers,
            json={"session_id": session_id, "contact_ids": [self.contact["id"]]},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(response.json()["results"][0]["success"])
        self.assertIn("Game World Date: 01 Sep 1943 at 08:15.", captured["body"])

    def test_session_management_routes_are_session_specific(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        session_id = state["sessions"][0]["id"]
        duplicated = self.admin.post(
            f"/api/admin/sessions/{session_id}/duplicate", headers=self.admin_headers
        )
        self.assertEqual(duplicated.status_code, 200, duplicated.text)
        duplicate_id = duplicated.json()["id"]
        removed = self.admin.delete(
            f"/api/admin/sessions/{duplicate_id}/players/{self.contact['id']}",
            headers=self.admin_headers,
        )
        self.assertEqual(removed.status_code, 200, removed.text)
        deleted = self.admin.delete(
            f"/api/admin/sessions/{duplicate_id}", headers=self.admin_headers
        )
        self.assertEqual(deleted.status_code, 200, deleted.text)
        remaining = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertEqual([item["id"] for item in remaining["sessions"]], [session_id])

    def test_origin_is_required(self):
        response = self.player.post("/v1/admissions", json={"invite_token": self.invite})
        self.assertEqual(response.status_code, 403)

    def test_wordpress_origin_is_derived_for_browser_preflight(self):
        with tempfile.TemporaryDirectory() as temporary:
            repository = GameBoardRepository(Path(temporary))
            settings = repository.settings()
            settings["wordpress_player_url"] = f"{ORIGIN}/game/"
            settings["allowed_origin"] = ""
            repository.save_settings(settings)
            _admin_app, player_app, _runtime = create_apps(repository)
            with TestClient(player_app) as player:
                response = player.options(
                    "/v1/admissions",
                    headers={
                        "Origin": ORIGIN,
                        "Access-Control-Request-Method": "POST",
                        "Access-Control-Request-Headers": "content-type",
                    },
                )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["access-control-allow-origin"], ORIGIN)

    def test_gmail_setup_errors_are_returned_to_the_native_app(self):
        with patch.object(GmailSender, "authorize", side_effect=GmailUnavailable("Select a credentials file")):
            response = self.admin.post(
                "/api/admin/gmail/authorize",
                headers=self.admin_headers,
                json={"credentials_path": "C:/Private/credentials.json", "sender": ""},
            )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["detail"], "Select a credentials file")
        self.assertEqual(
            self.repository.settings()["gmail_credentials_path"],
            "C:/Private/credentials.json",
        )

    def test_end_to_end_approval_and_ticket_replay(self):
        admission = self.admission()
        poll_headers = {**self.origin_headers, "Authorization": f"Bearer {admission['poll_token']}"}
        pending = self.player.get(f"/v1/admissions/{admission['request_id']}", headers=poll_headers)
        self.assertEqual(pending.json()["status"], "pending")
        approved = self.admin.post(
            f"/api/admin/admissions/{admission['request_id']}/approve", headers=self.admin_headers
        )
        self.assertEqual(approved.status_code, 200)
        ticket = self.player.get(
            f"/v1/admissions/{admission['request_id']}", headers=poll_headers
        ).json()["ticket"]
        with self.player.websocket_connect(
            f"/v1/session?ticket={ticket}", headers=self.origin_headers
        ) as websocket:
            accepted = websocket.receive_json()
            self.assertEqual(accepted["type"], "connection_accepted")
            self.assertEqual(accepted["player_id"], self.contact["id"])
            history = websocket.receive_json()
            self.assertEqual(history, {"v": 1, "type": "chat_history", "messages": []})
            arrival = websocket.receive_json()
            self.assertEqual(arrival["type"], "chat_message")
            self.assertEqual(arrival["message"]["sender_role"], "system")
            self.assertEqual(arrival["message"]["text"], "Alice is here!")
            board = websocket.receive_json()
            self.assertEqual(board["type"], "board_snapshot")
            websocket.send_json({"v": 1, "type": "chat_message", "message": "Hello room"})
            chat = websocket.receive_json()
            self.assertEqual(chat["type"], "chat_message")
            self.assertEqual(chat["message"]["sender_name"], "Alice")
            self.assertEqual(chat["message"]["text"], "Hello room")
            websocket.send_json({"v": 1, "type": "not_allowed"})
            self.assertEqual(websocket.receive_json()["type"], "server_error")
        with self.assertRaises(WebSocketDisconnect):
            with self.player.websocket_connect(
                f"/v1/session?ticket={ticket}", headers=self.origin_headers
            ):
                pass

    def test_rate_limit_rejects_sixth_attempt(self):
        for _ in range(5):
            response = self.player.post(
                "/v1/admissions", json={"invite_token": "x" * 32}, headers=self.origin_headers
            )
            self.assertEqual(response.status_code, 403)
        response = self.player.post(
            "/v1/admissions", json={"invite_token": "x" * 32}, headers=self.origin_headers
        )
        self.assertEqual(response.status_code, 429)

    def test_announcement_broadcast_envelope(self):
        socket = FakeSocket()
        self.runtime.connections["fake"] = type("Connection", (), {"websocket": socket})()
        announcement_id = asyncio.run(self.runtime.announce("Welcome"))
        self.assertEqual(socket.messages[0], {
            "v": 1, "type": "announcement", "id": announcement_id, "message": "Welcome"
        })

    def test_headmaster_chat_is_stored_and_broadcast(self):
        socket = FakeSocket()
        self.runtime.connections["fake"] = type(
            "Connection", (), {"websocket": socket, "public": lambda _self, _service: {"contact_id": "fake"}}
        )()
        response = self.admin.post(
            "/api/admin/chat", headers=self.admin_headers, json={"message": "Gather in the hall"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sender_role"], "headmaster")
        self.assertEqual(socket.messages[0]["type"], "chat_message")
        self.assertEqual(socket.messages[0]["message"]["text"], "Gather in the hall")
        self.assertEqual(self.runtime.service.session_view()["chat"][0]["sender_name"], "Headmaster")


class GmailAdapterTests(unittest.TestCase):
    def test_message_is_encoded_and_sent_with_gmail_api(self):
        class Credentials:
            valid = True
            expired = False
            refresh_token = "refresh"
            scopes = []

            def to_json(self):
                return "{}"

        class Keyring:
            @staticmethod
            def get_password(_service, _account):
                return "{}"

            @staticmethod
            def set_password(_service, _account, _value):
                return None

        class CredentialsType:
            @staticmethod
            def from_authorized_user_info(_value, _scopes):
                return Credentials()

        captured = {}

        class Response:
            status_code = 200

            @staticmethod
            def json():
                return {"id": "gmail-message-id"}

        class AuthorizedSession:
            def __init__(self, credentials):
                captured["credentials"] = credentials

            def post(self, url, **kwargs):
                captured["url"] = url
                captured.update(kwargs)
                return Response()

        libraries = (Keyring, object, CredentialsType, object, AuthorizedSession)
        with (
            patch("headmasters_scroll.game_board.gmail._libraries", return_value=libraries),
            patch("headmasters_scroll.game_board.gmail.shutil.which", return_value=None),
        ):
            sender = GmailSender("credentials.json", "headmaster@example.com")
            result = sender.send("alice@example.com", "Invitation", "Private link")
        self.assertEqual(result, "gmail-message-id")
        self.assertEqual(
            captured["url"],
            "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
        )
        decoded = base64.urlsafe_b64decode(captured["json"]["raw"]).decode("utf-8")
        self.assertIn("To: alice@example.com", decoded)
        self.assertIn("Subject: Invitation", decoded)
        self.assertIn("Private link", decoded)

    def test_windows_curl_transport_keeps_token_off_command_line(self):
        class Credentials:
            valid = True
            expired = False
            refresh_token = "refresh"
            scopes = []
            token = "private-access-token"

        class Keyring:
            @staticmethod
            def get_password(_service, _account):
                return "{}"

        class CredentialsType:
            @staticmethod
            def from_authorized_user_info(_value, _scopes):
                return Credentials()

        captured = {}

        def run(args, **kwargs):
            captured["args"] = args
            captured["config"] = kwargs["input"]
            return type(
                "Completed",
                (),
                {"returncode": 0, "stdout": '{"id":"curl-message-id"}\n200', "stderr": ""},
            )()

        libraries = (Keyring, object, CredentialsType, object, object)
        with (
            patch("headmasters_scroll.game_board.gmail._libraries", return_value=libraries),
            patch("headmasters_scroll.game_board.gmail.shutil.which", return_value="curl.exe"),
            patch("headmasters_scroll.game_board.gmail.subprocess.run", side_effect=run),
        ):
            result = GmailSender("credentials.json").send(
                "alice@example.com", "Invitation", "Private link"
            )
        self.assertEqual(result, "curl-message-id")
        self.assertNotIn("private-access-token", " ".join(captured["args"]))
        self.assertIn("Authorization: Bearer private-access-token", captured["config"])


class GameBoardAssetTests(unittest.TestCase):
    def test_map_search_returns_typo_tolerant_near_matches(self):
        window = object.__new__(GameBoardWindow)
        window.board_snapshot = {
            "maps": [
                {
                    "record_id": "map-hogshire",
                    "name": "Hogshire",
                    "location_name": "Hogshire",
                    "floor_name": "",
                },
                {
                    "record_id": "map-diagon",
                    "name": "Diagon Alley",
                    "location_name": "London",
                    "floor_name": "",
                },
            ]
        }
        self.assertEqual(
            [item["record_id"] for item in window.fuzzy_board_maps("Hogshre")],
            ["map-hogshire"],
        )

    def test_separate_weblink_loads_versioned_assets_and_waits_for_approval(self):
        root = Path(__file__).resolve().parents[1]
        app = root / "apps" / "charms-check-game-board-weblink"
        loader = (app / "wordpress.html").read_text(encoding="utf-8")
        client = (app / "js" / "game-board.js").read_text(encoding="utf-8")
        stylesheet = (app / "css" / "game-board.css").read_text(encoding="utf-8")
        index = (app / "index.html").read_text(encoding="utf-8")
        self.assertIn("scyppan/Headmaster-s-Scroll", loader)
        self.assertIn("apps/charms-check-game-board-weblink/", loader)
        self.assertIn("https://beast.tail102829.ts.net", loader)
        self.assertIn("a26.8.11.003", loader)
        self.assertNotIn("https://game.example.com", loader)
        self.assertIn("getElementById('gameboard')", loader)
        self.assertNotIn("<script>", loader)
        self.assertNotIn('<div id="gameboard"', loader)
        self.assertIn('<div id="gameboard"', index)
        self.assertIn("rootId: 'gameboard'", loader)
        self.assertNotIn('id="charms-check-game-board"', loader + index)
        self.assertIn("this.root.innerHTML", client)
        self.assertIn("document.getElementById('gameboard')", client)
        self.assertNotIn("document.getElementById(options.rootId)", client)
        self.assertIn("Waiting for the Headmaster", client)
        self.assertIn("heartbeat_ack", client)
        self.assertIn("acknowledgement", client)
        self.assertIn("chat_message", client)
        self.assertIn("identity_updated", client)
        self.assertIn("board_snapshot", client)
        self.assertIn("board_move_commit", client)
        self.assertIn("/v1/assets/", client)
        self.assertIn("ccgb-chat-rail", client)
        self.assertIn("is-own", client)
        self.assertIn("chat-collapsed { --ccgb-chat-width: 48px; }", stylesheet)
        self.assertIn(".ccgb-chat-message.is-own", stylesheet)
        self.assertIn("transform: none;", stylesheet)
        self.assertIn("margin: 7px;", stylesheet)
        self.assertIn("max-width: none;", stylesheet)
        self.assertIn("aspect-ratio: 3840 / 2960", stylesheet)
        self.assertIn("MAP_NATIVE_WIDTH = 3840", client)
        self.assertIn("MAP_NATIVE_HEIGHT = 2960", client)
        self.assertIn("MAP_ZOOM_STEP = 1.15", client)
        self.assertIn("event.altKey", client)
        self.assertIn("event.button !== 1", client)
        self.assertIn("event.ctrlKey || event.metaKey", client)
        self.assertIn("--map-token-size", client)
        self.assertIn("ccgb-actor-indicators", client)
        self.assertIn("background: #d6ad52", stylesheet)
        for section in ("Overview", "Attributes", "Spells", "Proficiencies", "Potions", "Pets", "Inventory", "Relationships", "Wounds", "Settings"):
            self.assertIn(section, client)
        self.assertNotIn("world.json", loader + client)
        self.assertFalse((app / "app.json").exists())

    def test_game_board_tile_opens_native_python_controls(self):
        root = Path(__file__).resolve().parents[1]
        entrypoint = (root / "apps" / "game-board" / "main.py").read_text(encoding="utf-8")
        desktop = (root / "headmasters_scroll" / "game_board" / "desktop.py").read_text(encoding="utf-8")
        self.assertIn("headmasters_scroll.game_board.desktop", entrypoint)
        self.assertNotIn("webbrowser", entrypoint)
        self.assertIn("class GameBoardWindow(tk.Tk)", desktop)
        self.assertIn('"Currently Logged In"', desktop)
        self.assertIn('text="Send to Selected"', desktop)
        self.assertIn('text="Send to All"', desktop)
        self.assertIn('text="Remove from Session"', desktop)
        self.assertIn('text="Admit All"', desktop)
        self.assertIn("def toggle_chat", desktop)
        self.assertIn('(("game-board", "Game Board"), ("control-panel", "Control Panel"))', desktop)
        self.assertIn('self.chat_shell.pack(side="right"', desktop)
        self.assertIn("Players & Characters", desktop)
        self.assertIn("_notify_join_request", desktop)
        self.assertIn("/character", desktop)
        self.assertIn('"/api/admin/chat"', desktop)
        self.assertIn("GAME_BOARD_ICON", desktop)
        self.assertIn("maximize_window", desktop)
        self.assertIn("def _scrollable_page", desktop)
        self.assertIn('self.control_panel_button = self.sidebar_buttons["control-panel"]', desktop)
        self.assertIn("self.sidebar_buttons", desktop)
        self.assertIn("ttk.Notebook", desktop)
        self.assertIn("/api/admin/board/move", desktop)
        self.assertNotIn("Game Board Workspace", desktop)
        self.assertNotIn("Publish map", desktop)
        self.assertIn('text="Confirm to players"', desktop)
        self.assertIn('text="Explore…"', desktop)
        self.assertIn('text="Draw obfuscation  [O]"', desktop)
        self.assertIn("board_search_results_panel", desktop)
        self.assertIn("No close matches", desktop)
        self.assertIn('window.title("Map Tools")', desktop)
        self.assertIn('("map-tools", "▦", "Map Tools")', desktop)
        self.assertIn('("board-settings", "⚙", "Game Board Settings")', desktop)
        self.assertIn("board_obscuration_list", desktop)
        self.assertIn("Changes sent to players ✓", desktop)
        self.assertIn("def open_board_map_controls", desktop)
        self.assertIn("def adjust_current_map_token_scale", desktop)
        self.assertIn("def start_setting_board_start_point", desktop)
        self.assertIn("def _apply_responsive_chat_layout", desktop)
        self.assertIn("window.deiconify()", desktop)
        self.assertNotIn('map_controls.pack(side="left"', desktop)
        self.assertIn("def route_board_wheel", desktop)
        self.assertNotIn('unbind_all("<MouseWheel>")', desktop)
        self.assertIn("def open_board_explorer", desktop)
        self.assertIn("/api/admin/board/maps/{map_id}/presentation", (root / "headmasters_scroll" / "game_board" / "server.py").read_text(encoding="utf-8"))
        self.assertIn("/api/admin/admissions/", desktop)
        self.assertIn("def _grid_card", desktop)
        self.assertIn("self.settings_dirty", desktop)
        self.assertIn("def choose_character", desktop)
        self.assertIn("Search by character name", desktop)
        self.assertIn('text="Choose and Link"', desktop)
        self.assertNotIn('text="Link Character"', desktop)
        self.assertNotIn("def link_character", desktop)
        self.assertNotIn("self.character_combo", desktop)
        self.assertIn("class CalendarDateField", desktop)
        self.assertIn('DATE_DISPLAY_FORMAT = "%d %b %Y"', desktop)
        self.assertIn("event_date_field = CalendarDateField(body, date.today())", desktop)
        self.assertNotIn("Invitation day", desktop)
        self.assertNotIn("game_day_field", desktop)
        self.assertIn('"game_day": event_date_field.get_iso()', desktop)
        self.assertIn('text="Campaign"', desktop)
        self.assertIn('text="Choose Campaign…"', desktop)
        self.assertNotIn("game_date_field =", desktop)
        self.assertNotIn('text="Game time (24-hour)"', desktop)
        self.assertIn("def _build_game_clock", desktop)
        self.assertIn('add_button("<<<"', desktop)
        self.assertIn('add_button(">>>"', desktop)
        self.assertIn('add_button("hh")', desktop)
        self.assertIn('add_button("mm")', desktop)
        self.assertIn("(1, 3, 6, 8, 12, 16)", desktop)
        self.assertIn("(1, 3, 5, 10, 15, 30, 45)", desktop)
        self.assertIn('("Morning", 8)', desktop)
        self.assertIn('("Afternoon", 12)', desktop)
        self.assertIn('("Evening", 17)', desktop)
        self.assertIn('("Night", 19)', desktop)
        self.assertIn('"Last hour" if direction < 0 else "Next hour"', desktop)
        self.assertIn("def _build_headmaster_tool_rail", desktop)
        self.assertIn("def select_headmaster_tool", desktop)
        self.assertIn('if key == "game-board":', desktop)
        self.assertIn("self.headmaster_tool_rail.pack_forget()", desktop)
        self.assertLess(
            desktop.index('sidebar.pack(side="left"'),
            desktop.index("self._build_headmaster_tool_rail(self.workspace)"),
        )
        self.assertNotIn('ttk.Label(header, text="Game Board"', desktop)
        self.assertNotIn("padx=28", desktop)
        self.assertIn('("sessions", "Sessions")', desktop)
        self.assertIn('f"{\'✓\' if contact[\'id\'] in checked else \' \'}', desktop)
        self.assertNotIn("event_date_entry", desktop)
        self.assertNotIn("Messages are shared with every connected player.", desktop)
        self.assertFalse((root / "apps" / "game-board" / "web" / "admin.html").exists())

    def test_headmaster_dates_use_readable_display_format(self):
        self.assertEqual(format_date_display(date(2026, 1, 9)), "09 Jan 2026")
        self.assertEqual(format_stored_date("2026-08-09"), "09 Aug 2026")
        self.assertEqual(format_stored_date("2026-08-09T23:59:00Z"), "09 Aug 2026")
        self.assertEqual(format_stored_date(None), "Not set")
        self.assertEqual(
            shift_game_calendar(datetime(2024, 2, 29, 8, 0), years=1),
            datetime(2025, 2, 28, 8, 0),
        )
        self.assertEqual(
            shift_game_calendar(datetime(2026, 1, 31, 8, 0), months=1),
            datetime(2026, 2, 28, 8, 0),
        )
        current = datetime(1943, 9, 1, 10, 20)
        self.assertEqual(
            directional_minute_snap(current, 30, -1),
            datetime(1943, 9, 1, 9, 30),
        )
        self.assertEqual(
            directional_minute_snap(current, 15, 1),
            datetime(1943, 9, 1, 11, 15),
        )

    def test_game_world_dates_support_bce_years(self):
        ancient = parse_game_datetime("-3100-01-09T08:15")
        self.assertEqual(ancient, HistoricalDateTime(-3100, 1, 9, 8, 15))
        self.assertEqual(format_game_datetime(ancient), "09 Jan 3100 BCE  08:15")
        self.assertEqual(
            shift_game_calendar(ancient, years=1),
            HistoricalDateTime(-3099, 1, 9, 8, 15),
        )
        self.assertEqual(
            shift_game_calendar(HistoricalDateTime(-1, 12, 31, 8, 0), days=1),
            datetime(1, 1, 1, 8, 0),
        )
        self.assertEqual(
            normalize_game_datetime("-3100-01-09T08:15", "2026-01-01"),
            "-3100-01-09T08:15",
        )
        self.assertEqual(
            format_game_datetime_for_people("-3100-01-09T08:15"),
            "09 Jan 3100 BCE at 08:15",
        )


if __name__ == "__main__":
    unittest.main()
