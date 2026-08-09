import asyncio
import base64
import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from headmasters_scroll.game_board.gmail import GmailSender
from headmasters_scroll.game_board.server import create_apps
from headmasters_scroll.game_board.storage import GameBoardRepository


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
        self.admin_app, self.player_app, self.runtime = create_apps(self.repository)
        self.admin = TestClient(self.admin_app)
        self.player = TestClient(self.player_app)
        self.admin_headers = {"X-Admin-Key": settings["admin_key"]}
        self.origin_headers = {"Origin": ORIGIN}
        self.contact = self.runtime.service.add_contact("Alice", "alice@example.com")
        self.runtime.service.create_session(
            "API Test", (date.today() + timedelta(days=1)).isoformat(), [self.contact["id"]]
        )
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

    def test_origin_is_required(self):
        response = self.player.post("/v1/admissions", json={"invite_token": self.invite})
        self.assertEqual(response.status_code, 403)

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

        class SendCall:
            def execute(self):
                return {"id": "gmail-message-id"}

        class Messages:
            def send(self, **kwargs):
                captured.update(kwargs)
                return SendCall()

        class Users:
            def messages(self):
                return Messages()

        class Gmail:
            def users(self):
                return Users()

        def build(*_args, **_kwargs):
            return Gmail()

        libraries = (Keyring, object, CredentialsType, object, build)
        with patch("headmasters_scroll.game_board.gmail._libraries", return_value=libraries):
            sender = GmailSender("credentials.json", "headmaster@example.com")
            result = sender.send("alice@example.com", "Invitation", "Private link")
        self.assertEqual(result, "gmail-message-id")
        decoded = base64.urlsafe_b64decode(captured["body"]["raw"]).decode("utf-8")
        self.assertIn("To: alice@example.com", decoded)
        self.assertIn("Subject: Invitation", decoded)
        self.assertIn("Private link", decoded)


class GameBoardAssetTests(unittest.TestCase):
    def test_separate_weblink_loads_versioned_assets_and_waits_for_approval(self):
        root = Path(__file__).resolve().parents[1]
        app = root / "apps" / "charms-check-game-board-weblink"
        loader = (app / "wordpress.html").read_text(encoding="utf-8")
        client = (app / "js" / "game-board.js").read_text(encoding="utf-8")
        index = (app / "index.html").read_text(encoding="utf-8")
        self.assertIn("scyppan/Headmaster-s-Scroll", loader)
        self.assertIn("apps/charms-check-game-board-weblink/", loader)
        self.assertIn("https://beast.tail102829.ts.net", loader)
        self.assertIn("a26.8.9.003", loader)
        self.assertNotIn("https://game.example.com", loader)
        self.assertIn("getElementById('gameboard')", loader)
        self.assertNotIn("<script>", loader)
        self.assertNotIn('<div id="gameboard"', loader)
        self.assertIn('<div id="gameboard"', index)
        self.assertIn("rootId: 'gameboard'", loader)
        self.assertNotIn('id="charms-check-game-board"', loader + index)
        self.assertIn("this.root.innerHTML", client)
        self.assertIn("Waiting for the Headmaster", client)
        self.assertIn("heartbeat_ack", client)
        self.assertIn("acknowledgement", client)
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
        self.assertIn('"Send Selected"', desktop)
        self.assertIn("/api/admin/admissions/", desktop)
        self.assertFalse((root / "apps" / "game-board" / "web" / "admin.html").exists())


if __name__ == "__main__":
    unittest.main()
