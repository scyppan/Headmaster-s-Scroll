import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

from headmasters_scroll.game_board.service import GameBoardService, iso_utc, utc_now
from headmasters_scroll.game_board.storage import GameBoardRepository


class GameBoardServiceTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = GameBoardRepository(Path(self.temporary.name))
        settings = self.repository.settings()
        settings.update(
            wordpress_player_url="https://players.example.com/game/",
            allowed_origin="https://players.example.com",
            public_api_base="https://game.example.com",
        )
        self.repository.save_settings(settings)
        self.service = GameBoardService(self.repository)
        self.alice = self.service.add_contact("Alice", "Alice@example.com")

    def tearDown(self):
        self.temporary.cleanup()

    def create_session(self, contacts=None):
        contacts = contacts or [self.alice["id"]]
        return self.service.create_session(
            "Saturday Game", (date.today() + timedelta(days=1)).isoformat(), contacts
        )

    def invite(self, contact_id=None):
        raw, link, _player = self.service.prepare_invite(contact_id or self.alice["id"])
        self.service.record_invite_result(contact_id or self.alice["id"], True)
        return raw, link

    def test_contacts_are_private_and_unique(self):
        self.assertEqual(self.service.list_contacts()[0]["email"], "alice@example.com")
        with self.assertRaises(ValueError):
            self.service.add_contact("Another Alice", "alice@example.com")
        updated = self.service.update_contact(self.alice["id"], "Alice A.", "alice.a@example.com")
        self.assertEqual(updated["name"], "Alice A.")
        self.service.delete_contact(self.alice["id"])
        self.assertEqual(self.service.list_contacts(), [])

    def test_character_link_becomes_the_player_identity_everywhere(self):
        character = self.service.list_characters()[0]
        linked = self.service.assign_character(self.alice["id"], character["id"])
        self.assertEqual(linked["display_name"], character["name"])
        self.create_session()
        raw, _link = self.invite()
        request = self.service.request_admission(raw, "203.0.113.7", "Browser")
        self.assertEqual(
            self.service.poll_admission(request["request_id"], request["poll_token"])["player_name"],
            character["name"],
        )
        chat = self.service.post_chat(self.alice["id"], "Wrong Name", "player", "Hello")
        self.assertEqual(chat["sender_name"], character["name"])
        self.service.assign_character(self.alice["id"], None)
        session = self.service.session_view()
        self.assertEqual(session["roster"][0]["name"], "Alice")
        self.assertEqual(session["pending"][0]["name"], "Alice")
        self.assertEqual(session["chat"][0]["sender_name"], "Alice")

    def test_settings_derive_origins_from_normal_page_urls(self):
        updated = self.service.update_settings({
            "wordpress_player_url": "https://charmscheck.com/game-board/",
            "allowed_origin": "https://charmscheck.com/game-board/",
            "public_api_base": "https://beast.tail102829.ts.net/",
            "gmail_credentials_path": '"C:/Private Files/credentials.json"',
        })
        self.assertEqual(updated["allowed_origin"], "https://charmscheck.com")
        self.assertEqual(updated["public_api_base"], "https://beast.tail102829.ts.net")
        self.assertEqual(updated["gmail_credentials_path"], "C:/Private Files/credentials.json")

    def test_gmail_settings_do_not_require_connection_setup(self):
        settings = self.repository.settings()
        settings["wordpress_player_url"] = "not-finished-yet"
        self.repository.save_settings(settings)
        updated = self.service.update_gmail_settings(
            '"C:/Private Files/credentials.json"', "headmaster@gmail.com"
        )
        self.assertEqual(updated["gmail_credentials_path"], "C:/Private Files/credentials.json")
        self.assertEqual(updated["gmail_sender"], "headmaster@gmail.com")

    def test_approval_ticket_is_single_use_and_reconnect_requires_approval(self):
        self.create_session()
        raw, link = self.invite()
        self.assertTrue(link.startswith("https://players.example.com/game/#invite="))
        stored = self.repository.active()["session"]["roster"][0]
        self.assertNotIn(raw, json.dumps(stored))
        request = self.service.request_admission(raw, "203.0.113.7", "Test Browser")
        self.assertEqual(self.service.poll_admission(request["request_id"], request["poll_token"])["status"], "pending")
        self.service.approve(request["request_id"])
        approved = self.service.poll_admission(request["request_id"], request["poll_token"])
        identity = self.service.consume_ticket(approved["ticket"])
        self.assertEqual(identity["name"], "Alice")
        with self.assertRaises(PermissionError):
            self.service.consume_ticket(approved["ticket"])
        self.service.mark_disconnected(request["request_id"], 12.5, 300.0, 2)
        reconnect = self.service.request_admission(raw, "203.0.113.7", "Test Browser")
        self.assertEqual(reconnect["status"], "pending")

    def test_duplicate_admission_resumes_and_expired_ticket_returns_to_queue(self):
        self.create_session()
        raw, _link = self.invite()
        first = self.service.request_admission(raw, "203.0.113.7", "Browser")
        resumed = self.service.request_admission(raw, "203.0.113.7", "Browser")
        self.assertEqual(resumed["request_id"], first["request_id"])
        self.assertNotEqual(resumed["poll_token"], first["poll_token"])
        self.service.approve(first["request_id"])
        approved = self.service.poll_admission(first["request_id"], resumed["poll_token"])
        ticket_hash = next(iter(self.service._tickets))
        self.service._tickets[ticket_hash]["expires_at"] = utc_now() - timedelta(seconds=1)
        expired = self.service.poll_admission(first["request_id"], resumed["poll_token"])
        self.assertEqual(expired["status"], "disconnected")
        retry = self.service.request_admission(raw, "203.0.113.7", "Browser")
        self.assertEqual(retry["status"], "pending")
        self.assertNotEqual(retry["request_id"], first["request_id"])

    def test_revoke_invalidates_invitation(self):
        self.create_session()
        raw, _link = self.invite()
        self.service.revoke(self.alice["id"])
        with self.assertRaises(PermissionError):
            self.service.request_admission(raw, "203.0.113.8", "Browser")

    def test_pause_blocks_new_admissions(self):
        self.create_session()
        raw, _link = self.invite()
        self.service.set_paused(True)
        with self.assertRaises(PermissionError):
            self.service.request_admission(raw, "203.0.113.8", "Browser")
        self.service.set_paused(False)
        self.assertEqual(self.service.request_admission(raw, "203.0.113.8", "Browser")["status"], "pending")

    def test_expiration_archives_summary_without_credentials_or_email(self):
        self.create_session()
        raw, _link = self.invite()
        self.service.post_chat(self.alice["id"], "Alice", "player", "A private session message")
        request = self.service.request_admission(raw, "203.0.113.9", "Secret Browser")
        wrapper = self.repository.active()
        wrapper["session"]["expires_at"] = iso_utc(utc_now() - timedelta(seconds=1))
        self.repository.save_active(wrapper)
        with self.assertRaises(ValueError):
            self.service.poll_admission(request["request_id"], request["poll_token"])
        self.assertIsNone(self.repository.active()["session"])
        summary_text = json.dumps(self.repository.summaries())
        self.assertIn("Alice", summary_text)
        for secret in (raw, request["poll_token"], "alice@example.com", "203.0.113.9", "Secret Browser", "A private session message"):
            self.assertNotIn(secret, summary_text)

    def test_session_chat_is_bounded_and_validated(self):
        self.create_session()
        message = self.service.post_chat(self.alice["id"], "Wrong Name", "player", "  Hello!  ")
        self.assertEqual(message["sender_name"], "Alice")
        self.assertEqual(message["text"], "Hello!")
        self.assertEqual(self.service.session_view()["chat"][0]["id"], message["id"])
        with self.assertRaises(ValueError):
            self.service.post_chat(self.alice["id"], "Alice", "player", " ")
        with self.assertRaises(ValueError):
            self.service.post_chat(self.alice["id"], "Alice", "player", "x" * 501)

    def test_restart_returns_approved_player_to_pending(self):
        self.create_session()
        raw, _link = self.invite()
        request = self.service.request_admission(raw, "203.0.113.7", "Browser")
        self.service.approve(request["request_id"])
        restarted = GameBoardService(self.repository)
        pending = restarted.session_view()["pending"][0]
        self.assertEqual(pending["status"], "pending")

    def test_nine_player_capacity_and_quality_thresholds(self):
        ids = [self.alice["id"]]
        for index in range(2, 10):
            ids.append(self.service.add_contact(f"Player {index}", f"player{index}@example.com")["id"])
        self.create_session(ids)
        self.assertEqual(len(self.service.session_view()["roster"]), 9)
        tickets = []
        for index, contact_id in enumerate(ids):
            raw, _link = self.invite(contact_id)
            request = self.service.request_admission(raw, f"203.0.113.{index + 1}", "Browser")
            self.service.approve(request["request_id"])
            tickets.append(self.service.poll_admission(request["request_id"], request["poll_token"])["ticket"])
        identities = [self.service.consume_ticket(ticket) for ticket in tickets]
        self.assertEqual(len({item["contact_id"] for item in identities}), 9)
        self.assertEqual(self.service.connection_quality(100, 0), "good")
        self.assertEqual(self.service.connection_quality(250, 0), "fair")
        self.assertEqual(self.service.connection_quality(800, 0), "poor")
        self.assertEqual(self.service.connection_quality(50, 3), "disconnected")

    def test_atomic_files_create_backups(self):
        self.service.add_contact("Bob", "bob@example.com")
        backups = list((Path(self.temporary.name) / "backups" / "contacts").glob("*.json"))
        self.assertTrue(backups)


if __name__ == "__main__":
    unittest.main()
