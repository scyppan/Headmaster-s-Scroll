import json
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from headmasters_scroll.campaigns import CampaignRepository
from headmasters_scroll.game_board.service import GameBoardService, iso_utc, utc_now
from headmasters_scroll.game_board.storage import GameBoardRepository
from headmasters_scroll.store import SharedJsonStore


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
        campaign_data = {
            "schema_version": 1,
            "_headmasters_scroll": {
                "revision_id": "campaign-test-revision",
                "last_modified_at": "2026-08-11T00:00:00Z",
                "last_modified_by": "test",
            },
            "campaigns": [{
                "record_id": "campaign-1",
                "name": "Test Campaign",
                "game_world_start_date": "1943-09-01",
                "created_at": "2026-08-11T00:00:00Z",
                "last_updated": "2026-08-11T00:00:00Z",
            }],
        }
        (Path(self.temporary.name) / "campaign.json").write_text(
            json.dumps(campaign_data), encoding="utf-8"
        )
        campaigns = CampaignRepository(SharedJsonStore(Path(self.temporary.name)))
        self.service = GameBoardService(self.repository, campaigns)
        self.campaign_id = "campaign-1"
        self.alice = self.service.add_contact("Alice", "Alice@example.com")

    def tearDown(self):
        self.temporary.cleanup()

    def create_session(self, contacts=None):
        contacts = contacts or [self.alice["id"]]
        return self.service.create_session(
            "Saturday Game",
            (date.today() + timedelta(days=1)).isoformat(),
            contacts,
            campaign_id=self.campaign_id,
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

    def test_live_character_catalog_includes_unplaced_faction_and_player_state(self):
        world = {
            "people": [{
                "record_id": "person-1",
                "displayed_name": "Alice Character",
                "board": {"faction_organization_id": "faction-1"},
            }],
            "organizations": [{
                "record_id": "faction-1",
                "name": "Raven Circle",
                "is_faction": True,
                "faction_color": "#223344",
            }],
            "events": [{
                "record_id": "joined-1",
                "event_type": "joined_faction",
                "date": "1943-08-01",
                "time": "1200",
                "person_ids": ["person-1"],
                "organization_id": "faction-1",
            }],
        }
        session = {
            "id": "session-1",
            "game_datetime": "1943-09-01T08:00",
            "roster": [{"character_id": "person-1"}],
        }
        campaign = {
            "game_state": {"current_game_datetime": "1943-09-01T08:00"}
        }

        with patch.object(self.service, "_world_document", return_value=world):
            self.assertEqual(
                self.service.list_characters(),
                [{"id": "person-1", "name": "Alice Character"}],
            )
        with (
            patch.object(self.service, "_board_context", return_value=session),
            patch.object(
                self.service,
                "_campaign_document",
                return_value=(campaign, world),
            ),
        ):
            character = self.service.list_characters("session-1")[0]

        self.assertEqual(character["faction_id"], "faction-1")
        self.assertEqual(character["faction_name"], "Raven Circle")
        self.assertEqual(character["faction_color"], "#223344")
        self.assertTrue(character["is_player_character"])

    def test_teaching_options_include_only_known_subjects_and_same_map_pupils(self):
        self.service.board_snapshot = lambda *_args, **_kwargs: {
            "actors": [
                {"actor_id": "teacher", "name": "Teacher", "map_id": "map-a"},
                {"actor_id": "nearby", "name": "Nearby", "map_id": "map-a"},
                {"actor_id": "elsewhere", "name": "Elsewhere", "map_id": "map-b"},
            ]
        }
        self.service._sheet_for_person = lambda *_args, **_kwargs: {
            "spells": [{"record_id": "known-spell", "name": "Known"}],
            "proficiencies": [],
            "recipes": [],
        }
        options = self.service.teaching_options("session", "teacher")
        self.assertEqual(
            [item["record_id"] for item in options["pupils"]], ["nearby"]
        )
        self.assertEqual(
            [item["record_id"] for item in options["spell"]], ["known-spell"]
        )
        self.assertEqual(options["pupils"][0]["known"]["spell"], ["known-spell"])
        with self.assertRaisesRegex(PermissionError, "already knows"):
            self.service._validate_teaching_action(
                "session", "teacher", "nearby", "spell", "known-spell"
            )
        with self.assertRaises(PermissionError):
            self.service._validate_teaching_action(
                "session", "teacher", "elsewhere", "spell", "known-spell"
            )
        with self.assertRaises(PermissionError):
            self.service._validate_teaching_action(
                "session", "teacher", "nearby", "spell", "unknown-spell"
            )

    def test_confirmed_recipe_consumes_ingredients_but_not_the_vessel(self):
        session = {
            "id": "session",
            "campaign_id": self.campaign_id,
            "roster": [{
                "contact_id": self.alice["id"], "character_id": "person-1"
            }],
        }
        sheet = {
            "character_name": "Alice",
            "attributes": {
                "attributes": [{"name": "Panache", "value": 1}],
                "skills": [{"name": "Potions", "value": 2}],
                "characteristics": [], "parental_values": [],
            },
            "inventory": [
                {"record_id": "leaves", "name": "Tea leaves", "quantity": 2},
                {"record_id": "cauldron", "name": "Copper Cauldron", "quantity": 1},
            ],
            "recipes": [{
                "record_id": "tea", "name": "Tea", "skill": "Potions",
                "threshold": 5,
                "ingredients": [{"name": "Tea leaves", "quantity": 2}],
                "requirements": {
                    "ready": True, "missing": [],
                    "ingredients": [{
                        "name": "Tea leaves", "required": 2,
                        "available": 2, "missing": 0,
                    }],
                    "vessel": {"name": "Cauldron", "available": True},
                    "consumption": {"leaves": 2},
                },
            }],
        }
        self.service.controlled_character_ids = lambda *_args: ["person-1"]
        self.service._active = lambda *_args: ({}, session)
        self.service.character_sheet_for = lambda *_args: sheet
        result = self.service.attempt_character_recipe(
            "session", self.alice["id"], "tea"
        )
        person_state = self.service.campaign_repository.get(
            self.campaign_id
        )["game_state"]["people"]["person-1"]
        self.assertEqual(person_state["consumed_inventory"], {"leaves": 2})
        self.assertNotIn("cauldron", person_state["consumed_inventory"])
        self.assertEqual(result["required_vessel"]["name"], "Cauldron")

    def test_flyable_mount_requires_flying_roll_and_failure_preserves_flight(self):
        session = {
            "id": "session", "campaign_id": self.campaign_id,
            "roster": [{
                "contact_id": self.alice["id"], "character_id": "person-1",
            }],
        }
        sheet = {
            "character_name": "Alice",
            "inventory": [{
                "record_id": "broom", "name": "Training Broom",
                "equipment_slot_type": "flyable", "flight_threshold": 9,
            }],
        }
        self.service._active = lambda *_args: ({}, session)
        self.service.character_sheet_for = lambda *_args: sheet

        with patch(
            "headmasters_scroll.game_board.service.perform_character_roll",
            return_value={"dice": [7], "total": 11, "components": []},
        ):
            result = self.service.update_character_equipment(
                "session", self.alice["id"], "flyable", "broom"
            )
        self.assertEqual(result["status"], "equipped")
        self.assertTrue(result["airborne"])
        person = self.service.campaign_repository.get(
            self.campaign_id
        )["game_state"]["people"]["person-1"]
        self.assertEqual(person["equipment"]["flyable"], "broom")
        self.assertTrue(person["airborne"])

        sheet["inventory"][0].update({
            "record_id": "carpet", "name": "Difficult Carpet",
            "flight_threshold": 30,
        })
        with patch(
            "headmasters_scroll.game_board.service.perform_character_roll",
            return_value={"dice": [4], "total": 8, "components": []},
        ):
            failed = self.service.update_character_equipment(
                "session", self.alice["id"], "flyable", "carpet"
            )
        self.assertEqual(failed["status"], "failed")
        self.assertTrue(failed["airborne"])
        person = self.service.campaign_repository.get(
            self.campaign_id
        )["game_state"]["people"]["person-1"]
        self.assertEqual(person["equipment"]["flyable"], "broom")
        self.assertTrue(person["airborne"])

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
        stored = self.repository.active()["sessions"][0]["roster"][0]
        self.assertNotIn(raw, json.dumps(stored))
        request = self.service.request_admission(raw, "203.0.113.7", "Test Browser")
        self.assertEqual(self.service.poll_admission(request["request_id"], request["poll_token"])["status"], "pending")
        self.service.approve(request["request_id"])
        approved = self.service.poll_admission(request["request_id"], request["poll_token"])
        identity = self.service.consume_ticket(approved["ticket"])
        self.assertEqual(identity["name"], "Alice")
        self.assertTrue(self.service.session_view()["roster"][0]["has_logged_in"])
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

    def test_event_date_is_editable_and_retained_in_summary(self):
        self.create_session()
        updated = self.service.set_event_date("1943-09-01")
        self.assertEqual(updated["event_date"], "1943-09-01")
        with self.assertRaisesRegex(ValueError, "YYYY-MM-DD"):
            self.service.set_event_date("September 1")
        summary = self.service.end_session()
        self.assertEqual(summary["event_date"], "1943-09-01")

    def test_in_world_game_datetime_is_persisted_validated_and_summarized(self):
        game_day = (date.today() + timedelta(days=1)).isoformat()
        created = self.service.create_session(
            "Game Clock", game_day, [self.alice["id"]], campaign_id=self.campaign_id
        )
        self.assertEqual(created["game_datetime"], "1943-09-01T08:00")
        self.assertEqual(created["campaign_id"], self.campaign_id)
        self.assertEqual(created["campaign_name"], "Test Campaign")
        updated = self.service.set_game_datetime(created["id"], "1943-09-01T17:45")
        self.assertEqual(updated["game_datetime"], "1943-09-01T17:45")
        with self.assertRaisesRegex(ValueError, "24-hour"):
            self.service.set_game_datetime(created["id"], "September 1 at supper")
        summary = self.service.end_session("ended", created["id"])
        self.assertEqual(summary["game_datetime"], "1943-09-01T17:45")
        self.assertEqual(summary["campaign_id"], self.campaign_id)

    def test_archived_session_cannot_reopen_or_modify_its_campaign_board(self):
        created = self.create_session()
        snapshot = self.service.board_snapshot(created["id"])
        map_id = snapshot["maps"][0]["record_id"]
        self.service.set_board_workspace(created["id"], [map_id], map_id)
        summary = self.service.end_session("expired", created["id"])

        archived = self.service.archived_sessions_view()
        self.assertEqual(archived[0]["id"], summary["id"])
        self.assertTrue(archived[0]["archived"])
        with self.assertRaisesRegex(PermissionError, "Archived"):
            self.service.board_snapshot(summary["id"])
        with self.assertRaisesRegex(PermissionError, "Archived"):
            self.service.set_map_published(summary["id"], map_id, True)

    def test_new_session_requires_a_campaign(self):
        with self.assertRaisesRegex(ValueError, "Choose a campaign"):
            self.service.create_session(
                "No Campaign",
                (date.today() + timedelta(days=1)).isoformat(),
                [self.alice["id"]],
            )

    def test_expiration_archives_summary_without_credentials_or_email(self):
        self.create_session()
        raw, _link = self.invite()
        self.service.post_chat(self.alice["id"], "Alice", "player", "A private session message")
        request = self.service.request_admission(raw, "203.0.113.9", "Secret Browser")
        wrapper = self.repository.active()
        wrapper["sessions"][0]["expires_at"] = iso_utc(utc_now() - timedelta(seconds=1))
        self.repository.save_active(wrapper)
        with self.assertRaises(ValueError):
            self.service.poll_admission(request["request_id"], request["poll_token"])
        self.assertEqual(len(self.repository.active()["sessions"]), 1)
        due = self.repository.active()["sessions"][0]["expires_at"]
        self.assertTrue(
            self.service.begin_session_expiration(
                self.repository.active()["sessions"][0]["id"], due
            )
        )
        self.service.finish_session_expiration(
            self.repository.active()["sessions"][0]["id"], due
        )
        self.assertEqual(self.repository.active()["sessions"], [])
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

    def test_multiple_sessions_duplicate_remove_end_and_delete_independently(self):
        first = self.create_session()
        bob = self.service.add_contact("Bob", "bob@example.com")
        second = self.service.create_session(
            "Sunday Game", (date.today() + timedelta(days=2)).isoformat(), [bob["id"]],
            event_date="1943-09-02", campaign_id=self.campaign_id,
        )
        self.assertEqual(len(self.service.sessions_view()), 2)
        raw, _link, _player = self.service.prepare_invite(bob["id"], second["id"])
        self.service.record_invite_result(bob["id"], True, second["id"])
        self.assertIsNotNone(self.service.session_view(second["id"])["roster"][0]["sent_at"])
        request = self.service.request_admission(raw, "203.0.113.8", "Browser")
        self.assertEqual(request["session_id"], second["id"])

        duplicate = self.service.duplicate_session(first["id"])
        self.assertEqual(duplicate["title"], "Saturday Game Copy")
        self.assertEqual(duplicate["roster"][0]["invite_status"], "not_sent")
        self.assertEqual(duplicate["game_datetime"], first["game_datetime"])
        self.service.remove_player(duplicate["id"], self.alice["id"])
        self.assertEqual(self.service.session_view(duplicate["id"])["roster"], [])
        self.service.delete_session(duplicate["id"])
        self.assertEqual(len(self.service.sessions_view()), 2)
        summary = self.service.end_session("ended", second["id"])
        self.assertEqual(summary["event_date"], "1943-09-02")
        self.assertEqual([session["id"] for session in self.service.sessions_view()], [first["id"]])

    def test_create_select_end_and_delete_manage_one_authoritative_board_session(self):
        first = self.create_session()
        bob = self.service.add_contact("Bob", "bob@example.com")
        second = self.service.create_session(
            "Sunday Game",
            (date.today() + timedelta(days=2)).isoformat(),
            [bob["id"]],
            campaign_id=self.campaign_id,
        )
        self.assertEqual(self.repository.active()["board_session_id"], second["id"])
        self.assertEqual(self.service.board_session_view()["id"], second["id"])

        selected = self.service.select_board_session(first["id"])
        self.assertEqual(selected["id"], first["id"])
        self.assertEqual(self.service.session_view()["id"], first["id"])
        self.service.end_session("ended", first["id"])
        self.assertIsNone(self.repository.active()["board_session_id"])
        self.assertIsNone(self.service.session_view())
        self.assertEqual([item["id"] for item in self.service.sessions_view()], [second["id"]])

        self.service.select_board_session(second["id"])
        self.service.delete_session(second["id"])
        self.assertIsNone(self.repository.active()["board_session_id"])

    def test_duplicate_session_becomes_the_authoritative_board(self):
        first = self.create_session()
        duplicated = self.service.duplicate_session(first["id"])
        self.assertEqual(
            self.repository.active()["board_session_id"], duplicated["id"]
        )

    def test_expiration_extension_is_timezone_aware_and_race_safe(self):
        session = self.create_session()
        original = session["expires_at"]
        local_zone = ZoneInfo(self.repository.settings()["timezone"])
        original_local = datetime.fromisoformat(
            original.replace("Z", "+00:00")
        ).astimezone(local_zone)
        local_day = original_local.date() + timedelta(days=1)
        extended_local = datetime.combine(local_day, time(0, 15), local_zone)
        extended = extended_local.astimezone(utc_now().tzinfo)
        updated = self.service.update_session_expiration(
            session["id"], extended.isoformat(), original
        )
        self.assertEqual(updated["expires_at"], iso_utc(extended))
        self.assertEqual(updated["game_day"], local_day.isoformat())
        self.assertEqual(updated["expiration_time"], "00:15")
        self.assertFalse(
            self.service.begin_session_expiration(
                session["id"], original, now=extended + timedelta(days=1)
            )
        )
        self.assertEqual(self.service.session_view(session["id"])["id"], session["id"])

        with self.assertRaisesRegex(RuntimeError, "changed"):
            self.service.update_session_expiration(
                session["id"],
                (extended + timedelta(hours=1)).isoformat(),
                original,
            )
        with self.assertRaisesRegex(ValueError, "later"):
            self.service.update_session_expiration(
                session["id"], updated["expires_at"], updated["expires_at"]
            )
        with self.assertRaisesRegex(ValueError, "later"):
            self.service.update_session_expiration(
                session["id"],
                iso_utc(extended - timedelta(minutes=1)),
                updated["expires_at"],
            )
        with self.assertRaisesRegex(ValueError, "timezone"):
            self.service.update_session_expiration(
                session["id"], "2030-01-01T12:00:00", updated["expires_at"]
            )
        with self.assertRaisesRegex(ValueError, "future"):
            self.service.update_session_expiration(
                session["id"],
                iso_utc(utc_now() - timedelta(seconds=1)),
                updated["expires_at"],
            )

    def test_due_and_archived_sessions_reject_expiration_extensions(self):
        session = self.create_session()
        raw, _link = self.invite()
        request = self.service.request_admission(raw, "203.0.113.7", "Browser")
        wrapper = self.repository.active()
        due = iso_utc(utc_now() - timedelta(seconds=1))
        wrapper["sessions"][0]["expires_at"] = due
        self.repository.save_active(wrapper)
        future = iso_utc(utc_now() + timedelta(hours=1))
        with self.assertRaisesRegex(RuntimeError, "already expiring"):
            self.service.update_session_expiration(session["id"], future, due)
        self.assertTrue(self.service.begin_session_expiration(session["id"], due))
        with self.assertRaisesRegex(RuntimeError, "already expiring"):
            self.service.update_session_expiration(session["id"], future, due)
        self.service.mark_disconnected(request["request_id"], 12.5, 400.0, 2)
        summary = self.service.finish_session_expiration(session["id"], due)
        self.assertEqual(summary["reason"], "expired")
        self.assertEqual(summary["players"][0]["disconnects"], 1)
        self.assertEqual(summary["players"][0]["connected_seconds"], 12.5)
        self.assertEqual(summary["players"][0]["average_latency_ms"], 200.0)
        self.assertIsNone(self.repository.active()["board_session_id"])
        with self.assertRaisesRegex(PermissionError, "Archived"):
            self.service.update_session_expiration(session["id"], future, due)

    def test_restart_hides_then_expires_an_overdue_board_session(self):
        session = self.create_session()
        wrapper = self.repository.active()
        due = iso_utc(utc_now() - timedelta(minutes=1))
        wrapper["sessions"][0]["expires_at"] = due
        self.repository.save_active(wrapper)

        restarted = GameBoardService(
            self.repository, self.service.campaign_repository
        )
        self.assertIsNone(restarted.board_session_view())
        self.assertTrue(restarted.begin_session_expiration(session["id"], due))
        summary = restarted.finish_session_expiration(session["id"], due)
        self.assertEqual(summary["id"], session["id"])
        self.assertEqual(restarted.sessions_view(), [])
        self.assertIsNone(self.repository.active()["board_session_id"])

    def test_delete_session_removes_an_expired_archived_session(self):
        session = self.create_session()
        summary = self.service.end_session("expired", session["id"])
        self.assertEqual(
            [item["id"] for item in self.service.archived_sessions_view()],
            [session["id"]],
        )

        deleted = self.service.delete_session(session["id"])

        self.assertEqual(deleted["id"], summary["id"])
        self.assertEqual(self.service.archived_sessions_view(), [])
        self.assertEqual(self.repository.summaries()["sessions"], [])

    def test_legacy_single_session_file_migrates_without_data_loss(self):
        session = self.create_session()
        self.repository.save_active({"schema_version": 1, "session": session})
        migrated = self.repository.active()
        self.assertEqual(migrated["schema_version"], 1)
        self.assertEqual([item["id"] for item in migrated["sessions"]], [session["id"]])
        self.assertIsNone(migrated["board_session_id"])

    def test_legacy_sessions_and_explicit_none_never_fall_back(self):
        older = self.create_session()
        newer = self.service.duplicate_session(older["id"])
        older["created_at"] = "2026-01-01T00:00:00Z"
        newer["created_at"] = "2026-01-02T00:00:00Z"
        self.repository.save_active({
            "schema_version": 1,
            "sessions": [newer, older],
        })
        migrated = self.repository.active()
        self.assertIsNone(migrated["board_session_id"])

        migrated["board_session_id"] = None
        self.repository.save_active(migrated)
        remembered = self.repository.active()
        self.assertIsNone(remembered["board_session_id"])


if __name__ == "__main__":
    unittest.main()
