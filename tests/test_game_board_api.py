import asyncio
import base64
import json
import tempfile
import threading
import time
import unittest
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from fastapi.testclient import TestClient
from fastapi import HTTPException
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
from headmasters_scroll.game_board.server import (
    GameBoardRuntime,
    PlayerConnection,
    SendBody,
    create_apps,
)
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

    def test_slow_gmail_delivery_does_not_block_admin_health(self):
        class SlowGmail:
            def status(self):
                return {"connected": True}

            def send(self, _recipient, _subject, _body):
                time.sleep(0.8)
                return "slow-message"

        self.runtime.gmail = lambda: SlowGmail()

        async def scenario():
            send_endpoint = next(
                route.endpoint for route in self.admin_app.routes
                if route.path == "/api/admin/invitations/send"
            )
            health_endpoint = next(
                route.endpoint for route in self.admin_app.routes
                if route.path == "/api/admin/health"
            )
            started = time.monotonic()
            send = asyncio.create_task(send_endpoint(SendBody(
                session_id=self.session_id,
                contact_ids=[self.contact["id"]],
            )))
            await asyncio.sleep(0.05)
            health = await health_endpoint()
            health_elapsed = time.monotonic() - started
            sent = await send
            return health, health_elapsed, sent

        health, health_elapsed, sent = asyncio.run(scenario())
        self.assertEqual(health, {"service": "game-board", "ready": True})
        self.assertLess(health_elapsed, 0.45)
        self.assertTrue(sent["results"][0]["success"])

    def test_omitted_session_batch_stays_bound_across_board_switch_and_end(self):
        delivery_started = threading.Event()
        release_delivery = threading.Event()
        recipients = []
        second_contact = self.runtime.service.add_contact("Bob", "bob@example.com")
        batch_session = self.runtime.service.create_session(
            "Lifecycle batch",
            (date.today() + timedelta(days=1)).isoformat(),
            [self.contact["id"], second_contact["id"]],
            campaign_id="campaign-1",
        )
        batch_session_id = batch_session["id"]

        class CoordinatedGmail:
            def status(self):
                return {"connected": True}

            def send(self, recipient, _subject, _body):
                recipients.append(recipient)
                delivery_started.set()
                if not release_delivery.wait(2):
                    raise TimeoutError("test delivery was not released")
                return "coordinated-message"

        self.runtime.gmail = lambda: CoordinatedGmail()

        async def scenario():
            send_endpoint = next(
                route.endpoint for route in self.admin_app.routes
                if route.path == "/api/admin/invitations/send"
            )
            end_endpoint = next(
                route.endpoint for route in self.admin_app.routes
                if route.path == "/api/admin/sessions/{session_id}/end"
            )
            select_endpoint = next(
                route.endpoint for route in self.admin_app.routes
                if route.path == "/api/admin/sessions/{session_id}/select"
            )
            send = asyncio.create_task(send_endpoint(SendBody(
                contact_ids=[self.contact["id"], second_contact["id"]],
            )))
            self.assertTrue(await asyncio.to_thread(delivery_started.wait, 1))
            await select_endpoint(self.session_id)
            ending = asyncio.create_task(end_endpoint(batch_session_id))
            await asyncio.sleep(0.05)
            self.assertFalse(ending.done())
            release_delivery.set()
            return await send, await ending

        try:
            sent, ended = asyncio.run(scenario())
        finally:
            release_delivery.set()

        self.assertTrue(sent["results"][0]["success"])
        self.assertEqual(sent["results"][0]["message_id"], "coordinated-message")
        self.assertFalse(sent["results"][1]["success"])
        self.assertIn("session ended", sent["results"][1]["error"].lower())
        self.assertEqual(recipients, ["alice@example.com"])
        self.assertEqual(ended["reason"], "ended")
        with self.assertRaises(KeyError):
            self.runtime.service.session_view(batch_session_id)

    def test_headmaster_can_load_full_sheet_for_any_campaign_character(self):
        state = self.admin.get(
            "/api/admin/state", headers=self.admin_headers
        ).json()
        character = state["characters"][0]

        response = self.admin.get(
            f"/api/admin/board/people/{character['id']}/sheet",
            headers=self.admin_headers,
            params={"session_id": self.session_id},
        )

        self.assertEqual(response.status_code, 200, response.text)
        sheet = response.json()
        self.assertEqual(sheet["character_id"], character["id"])
        self.assertEqual(sheet["overview"]["name"], character["name"])
        for key in (
            "attributes", "spells", "proficiencies", "recipes", "pets",
            "inventory", "relationships", "wounds", "character_notes",
        ):
            self.assertIn(key, sheet)
        self.assertEqual(
            self.admin.get(
                f"/api/admin/board/people/{character['id']}/sheet",
                params={"session_id": self.session_id},
            ).status_code,
            403,
        )

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

    def test_restart_session_reactivates_the_same_invitation_link(self):
        ended = self.admin.post(
            f"/api/admin/sessions/{self.session_id}/end",
            headers=self.admin_headers,
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        self.assertTrue(ended.json()["restartable"])
        archived_state = self.admin.get(
            "/api/admin/state", headers=self.admin_headers
        ).json()
        archived = next(
            item for item in archived_state["archived_sessions"]
            if item["id"] == self.session_id
        )
        self.assertTrue(archived["restartable"])
        self.assertNotIn("alice@example.com", json.dumps(archived))
        self.assertEqual(
            self.admin.post(
                f"/api/admin/sessions/{self.session_id}/restart"
            ).status_code,
            403,
        )

        restarted = self.admin.post(
            f"/api/admin/sessions/{self.session_id}/restart",
            headers=self.admin_headers,
        )

        self.assertEqual(restarted.status_code, 200, restarted.text)
        self.assertEqual(restarted.json()["id"], self.session_id)
        state = self.admin.get(
            "/api/admin/state", headers=self.admin_headers
        ).json()
        self.assertEqual(state["board_session_id"], self.session_id)
        self.assertEqual(state["session"]["id"], self.session_id)
        self.assertNotIn(
            self.session_id,
            [item["id"] for item in state["archived_sessions"]],
        )
        admission = self.player.post(
            "/v1/admissions",
            json={"invite_token": self.invite},
            headers=self.origin_headers,
        )
        self.assertEqual(admission.status_code, 200, admission.text)
        self.assertEqual(admission.json()["status"], "pending")
        self.assertEqual(
            self.admin.post(
                f"/api/admin/sessions/{self.session_id}/restart",
                headers=self.admin_headers,
            ).status_code,
            409,
        )

    def test_restart_fails_fast_while_an_invitation_batch_is_running(self):
        self.runtime.service.end_session("ended", self.session_id)
        restart_endpoint = next(
            route.endpoint for route in self.admin_app.routes
            if route.path == "/api/admin/sessions/{session_id}/restart"
        )

        async def scenario():
            async with self.runtime.invitation_batch_lock:
                started = time.monotonic()
                with self.assertRaises(HTTPException) as raised:
                    await restart_endpoint(self.session_id)
                return raised.exception, time.monotonic() - started

        error, elapsed = asyncio.run(scenario())

        self.assertEqual(error.status_code, 409)
        self.assertLess(elapsed, 0.1)
        self.assertEqual(self.runtime.service.sessions_view(), [])
        self.assertTrue(
            self.runtime.service.archived_sessions_view()[0]["restartable"]
        )

    def test_disconnect_deactivates_connection_even_when_notice_send_fails(self):
        class BrokenNoticeSocket:
            def __init__(self):
                self.closed = False

            async def send_json(self, _message):
                raise ConnectionError("socket write failed")

            async def close(self, **_kwargs):
                self.closed = True

        socket = BrokenNoticeSocket()
        connection = PlayerConnection(
            websocket=socket,
            request_id="request-old",
            contact_id=self.contact["id"],
            name="Alice",
            session_id=self.session_id,
            asset_credential_hash="asset-old",
        )
        key = f"{self.session_id}:{self.contact['id']}"
        self.runtime.connections[key] = connection
        self.runtime.asset_credentials["asset-old"] = key

        with patch.object(
            self.runtime.service, "mark_disconnected"
        ) as mark_disconnected:
            asyncio.run(self.runtime.disconnect(
                self.contact["id"],
                "session_expired",
                "The game session ended.",
                self.session_id,
            ))

        self.assertFalse(connection.active)
        self.assertTrue(connection.persisted)
        self.assertTrue(socket.closed)
        self.assertNotIn(key, self.runtime.connections)
        self.assertNotIn("asset-old", self.runtime.asset_credentials)
        mark_disconnected.assert_called_once()

    def test_disconnect_waits_for_an_admitted_player_save(self):
        save_started = threading.Event()
        release_save = threading.Event()

        class ClosingSocket(FakeSocket):
            def __init__(self):
                super().__init__()
                self.closed = False

            async def close(self, **_kwargs):
                self.closed = True

        def slow_save():
            save_started.set()
            if not release_save.wait(2):
                raise TimeoutError("test save was not released")
            return "saved"

        socket = ClosingSocket()
        connection = PlayerConnection(
            websocket=socket,
            request_id="request-saving",
            contact_id=self.contact["id"],
            name="Alice",
            session_id=self.session_id,
        )
        key = f"{self.session_id}:{self.contact['id']}"
        self.runtime.connections[key] = connection

        async def scenario():
            saving = asyncio.create_task(
                self.runtime.run_connection_operation(connection, slow_save)
            )
            self.assertTrue(await asyncio.to_thread(save_started.wait, 1))
            disconnecting = asyncio.create_task(self.runtime.disconnect(
                self.contact["id"],
                "session_expired",
                "The game session ended.",
                self.session_id,
            ))
            await asyncio.sleep(0.05)
            self.assertFalse(connection.active)
            self.assertFalse(disconnecting.done())
            with self.assertRaises(PermissionError):
                await self.runtime.run_connection_operation(connection, lambda: None)
            release_save.set()
            self.assertEqual(await saving, "saved")
            await disconnecting

        try:
            with patch.object(
                self.runtime.service, "mark_disconnected"
            ) as mark_disconnected:
                asyncio.run(scenario())
        finally:
            release_save.set()

        self.assertTrue(socket.closed)
        self.assertNotIn(key, self.runtime.connections)
        mark_disconnected.assert_called_once()

    def test_cancelling_a_waiter_does_not_release_its_worker_save(self):
        save_started = threading.Event()
        release_save = threading.Event()

        def slow_save():
            save_started.set()
            if not release_save.wait(2):
                raise TimeoutError("test save was not released")

        connection = PlayerConnection(
            websocket=FakeSocket(),
            request_id="request-cancelled",
            contact_id=self.contact["id"],
            name="Alice",
            session_id=self.session_id,
        )
        key = f"{self.session_id}:{self.contact['id']}"
        self.runtime.connections[key] = connection

        async def scenario():
            waiting = asyncio.create_task(
                self.runtime.run_connection_operation(connection, slow_save)
            )
            self.assertTrue(await asyncio.to_thread(save_started.wait, 1))
            waiting.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await waiting
            self.assertFalse(connection.operations_idle.is_set())

            disconnecting = asyncio.create_task(self.runtime.disconnect(
                self.contact["id"],
                "session_expired",
                "The game session ended.",
                self.session_id,
            ))
            await asyncio.sleep(0.05)
            self.assertFalse(disconnecting.done())
            release_save.set()
            await disconnecting

        try:
            with patch.object(self.runtime.service, "mark_disconnected"):
                asyncio.run(scenario())
        finally:
            release_save.set()

        self.assertTrue(connection.operations_idle.is_set())
        self.assertNotIn(key, self.runtime.connections)

    def test_admin_state_contains_only_the_selected_live_session_board(self):
        created = self.admin.post(
            "/api/admin/sessions",
            headers=self.admin_headers,
            json={
                "title": "Second board",
                "campaign_id": "campaign-1",
                "game_day": (date.today() + timedelta(days=2)).isoformat(),
                "expiration_time": "23:59",
                "contact_ids": [self.contact["id"]],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        second_id = created.json()["id"]
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertEqual(state["board_session_id"], second_id)
        self.assertEqual(state["session"]["id"], second_id)
        self.assertEqual(set(state["boards"]), {second_id})
        self.assertLessEqual(set(state["battles"]), {second_id})

        selected = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/select",
            headers=self.admin_headers,
        )
        self.assertEqual(selected.status_code, 200, selected.text)
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertEqual(state["board_session_id"], self.session_id)
        self.assertEqual(set(state["boards"]), {self.session_id})

        ended = self.admin.post(
            f"/api/admin/sessions/{self.session_id}/end",
            headers=self.admin_headers,
        )
        self.assertEqual(ended.status_code, 200, ended.text)
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertEqual([item["id"] for item in state["sessions"]], [second_id])
        self.assertIsNone(state["board_session_id"])
        self.assertIsNone(state["session"])
        self.assertEqual(state["boards"], {})
        self.assertEqual(state["battles"], {})
        self.assertEqual(state["location_maps"], [])
        archived_selection = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/select",
            headers=self.admin_headers,
        )
        self.assertEqual(archived_selection.status_code, 403)

    def test_stale_admin_board_chat_and_announcement_writes_are_rejected(self):
        created = self.admin.post(
            "/api/admin/sessions",
            headers=self.admin_headers,
            json={
                "title": "Selected board",
                "campaign_id": "campaign-1",
                "game_day": (date.today() + timedelta(days=2)).isoformat(),
                "expiration_time": "23:59",
                "contact_ids": [self.contact["id"]],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        selected_id = created.json()["id"]
        state = self.admin.get(
            "/api/admin/state", headers=self.admin_headers
        ).json()
        map_id = state["boards"][selected_id]["maps"][0]["record_id"]
        person_id = state["characters"][0]["id"]

        move = self.admin.post(
            "/api/admin/board/move",
            headers=self.admin_headers,
            json={
                "session_id": self.session_id,
                "person_id": person_id,
                "map_id": map_id,
                "x": 0.25,
                "y": 0.75,
            },
        )
        chat = self.admin.post(
            "/api/admin/chat",
            headers=self.admin_headers,
            json={"session_id": self.session_id, "message": "stale chat"},
        )
        announcement = self.admin.post(
            "/api/admin/announcements",
            headers=self.admin_headers,
            json={"session_id": self.session_id, "message": "stale notice"},
        )

        self.assertEqual(move.status_code, 409, move.text)
        self.assertEqual(chat.status_code, 409, chat.text)
        self.assertEqual(announcement.status_code, 409, announcement.text)
        old_session = self.runtime.service.session_view(self.session_id)
        self.assertEqual(old_session["chat"], [])
        self.assertEqual(old_session["announcement_count"], 0)
        campaign = self.runtime.service.campaign_repository.get("campaign-1")
        self.assertIsNone(
            campaign["game_state"]["people"].get(person_id, {}).get("placement")
        )

    def test_legacy_end_action_disconnects_only_the_board_session(self):
        created = self.admin.post(
            "/api/admin/sessions",
            headers=self.admin_headers,
            json={
                "title": "Selected board",
                "campaign_id": "campaign-1",
                "game_day": (date.today() + timedelta(days=2)).isoformat(),
                "expiration_time": "23:59",
                "contact_ids": [self.contact["id"]],
            },
        )
        self.assertEqual(created.status_code, 200, created.text)
        selected_id = created.json()["id"]
        with patch.object(
            self.runtime, "disconnect_session", new=AsyncMock()
        ) as disconnect_session, patch.object(
            self.runtime, "disconnect_all", new=AsyncMock()
        ) as disconnect_all:
            ended = self.admin.post(
                "/api/admin/session/end", headers=self.admin_headers
            )

        self.assertEqual(ended.status_code, 200, ended.text)
        disconnect_session.assert_awaited_once_with(
            selected_id,
            "session_expired",
            "The game session has ended.",
        )
        disconnect_all.assert_not_awaited()
        remaining = self.runtime.service.sessions_view()
        self.assertEqual([item["id"] for item in remaining], [self.session_id])
        self.assertIsNone(self.runtime.service.board_session_id())

    def test_expiration_endpoint_requires_a_fresh_later_aware_deadline(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        current = state["session"]["expires_at"]
        current_datetime = datetime.fromisoformat(current.replace("Z", "+00:00"))
        later = current_datetime + timedelta(hours=1)
        response = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/expiration",
            headers=self.admin_headers,
            json={
                "expires_at": later.astimezone(
                    timezone(timedelta(hours=2))
                ).isoformat(),
                "expected_expires_at": current,
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["expires_at"], later.isoformat().replace("+00:00", "Z"))

        stale = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/expiration",
            headers=self.admin_headers,
            json={
                "expires_at": (later + timedelta(hours=1)).isoformat(),
                "expected_expires_at": current,
            },
        )
        self.assertEqual(stale.status_code, 409)
        shorter = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/expiration",
            headers=self.admin_headers,
            json={
                "expires_at": current,
                "expected_expires_at": response.json()["expires_at"],
            },
        )
        self.assertEqual(shorter.status_code, 400)
        naive = self.admin.put(
            f"/api/admin/sessions/{self.session_id}/expiration",
            headers=self.admin_headers,
            json={
                "expires_at": "2030-01-01T12:00:00",
                "expected_expires_at": response.json()["expires_at"],
            },
        )
        self.assertEqual(naive.status_code, 400)

    def test_expiration_worker_continues_after_one_session_failure(self):
        service = Mock()
        service.world_fingerprint.return_value = (1, 1)
        due = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
        service.sessions_view.return_value = [
            {"id": "broken", "expires_at": due},
            {"id": "healthy", "expires_at": due},
        ]
        service.begin_session_expiration.side_effect = [ValueError("broken"), True]
        service.finish_session_expiration.return_value = {"id": "healthy"}
        runtime = GameBoardRuntime(service)
        runtime.disconnect_session = AsyncMock()
        runtime.notify_admins = AsyncMock()

        count = asyncio.run(runtime.expire_due_sessions())

        self.assertEqual(count, 1)
        runtime.disconnect_session.assert_awaited_once()
        self.assertEqual(
            runtime.disconnect_session.await_args.args[0], "healthy"
        )

    def test_delete_route_removes_archived_session(self):
        state = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        session_id = state["sessions"][0]["id"]
        ended = self.admin.post(
            f"/api/admin/sessions/{session_id}/end", headers=self.admin_headers
        )
        self.assertEqual(ended.status_code, 200, ended.text)

        deleted = self.admin.delete(
            f"/api/admin/sessions/{session_id}", headers=self.admin_headers
        )

        self.assertEqual(deleted.status_code, 200, deleted.text)
        refreshed = self.admin.get("/api/admin/state", headers=self.admin_headers).json()
        self.assertNotIn(
            session_id,
            [item["id"] for item in refreshed.get("archived_sessions", [])],
        )

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
            self.assertIn("character_attributes", accepted)
            sheet = websocket.receive_json()
            self.assertEqual(sheet["type"], "character_sheet_snapshot")
            self.assertIn("character_sheet", sheet)
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
            "Connection",
            (),
            {
                "websocket": socket,
                "session_id": self.session_id,
                "public": lambda _self, _service: {"contact_id": "fake"},
            },
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
    def test_only_read_book_covers_are_authorized(self):
        service = object.__new__(GameBoardService)
        service.board_snapshot = lambda _session_id, for_players=False: {
            "maps": [],
            "actors": [],
            "character_sheet": {
                "books": [{"cover_asset_id": "book-cover:charms"}],
            },
        }
        service.world_board = SimpleNamespace(
            load=lambda: SimpleNamespace(data={"maps": [], "people": []})
        )
        path, media_type = service.resolve_player_asset(
            "session-1", "book-cover:charms"
        )
        self.assertEqual(path.name, "Charms.png")
        self.assertEqual(media_type, "image/png")
        with self.assertRaises(PermissionError):
            service.resolve_player_asset("session-1", "book-cover:potions")

    def test_book_cover_authorization_uses_the_connected_players_sheet(self):
        service = object.__new__(GameBoardService)
        captured = {}

        def snapshot(_session_id, *, for_players=False, contact_id=None):
            captured.update(for_players=for_players, contact_id=contact_id)
            return {
                "maps": [],
                "actors": [],
                "character_sheet": {
                    "books": [{"cover_asset_id": "book-cover:charms"}],
                },
            }

        service.board_snapshot = snapshot
        service.world_board = SimpleNamespace(
            load=lambda: SimpleNamespace(data={"maps": [], "people": []})
        )

        path, _media_type = service.resolve_player_asset(
            "session-1", "book-cover:charms", "contact-1"
        )

        self.assertEqual(path.name, "Charms.png")
        self.assertEqual(captured, {"for_players": True, "contact_id": "contact-1"})

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

    def test_desktop_can_select_an_archived_session_for_deletion(self):
        window = object.__new__(GameBoardWindow)
        window.selected_session_id = "expired-session"
        window.state_data = {
            "sessions": [],
            "archived_sessions": [
                {"id": "expired-session", "title": "Expired game", "archived": True}
            ],
        }

        self.assertEqual(window._selected_session()["id"], "expired-session")

    def test_separate_weblink_loads_versioned_assets_and_waits_for_approval(self):
        root = Path(__file__).resolve().parents[1]
        app = root / "apps" / "charms-check-game-board-weblink"
        loader = (app / "wordpress.html").read_text(encoding="utf-8")
        client = (app / "js" / "game-board.js").read_text(encoding="utf-8")
        stylesheet = (app / "css" / "game-board.css").read_text(encoding="utf-8")
        index = (app / "index.html").read_text(encoding="utf-8")
        desktop = (root / "headmasters_scroll" / "game_board" / "desktop.py").read_text(encoding="utf-8")
        self.assertIn("scyppan/Headmaster-s-Scroll", loader)
        self.assertIn("apps/charms-check-game-board-weblink/", loader)
        self.assertIn("https://beast.tail102829.ts.net", loader)
        self.assertIn("a26.8.11.010", loader)
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
        self.assertIn("chat-smaller", client)
        self.assertIn("chat-larger", client)
        self.assertIn("syncViewportHeight", client)
        self.assertNotIn('data-ccgb="avatar"', client)
        self.assertIn("board_snapshot", client)
        self.assertIn("renderAttributesPanel", client)
        self.assertIn("renderOverviewPanel", client)
        self.assertIn("renderKnowledgePanel", client)
        self.assertIn("renderBookLibrary", client)
        self.assertIn("renderBookContents", client)
        self.assertIn("Search books, authors, spells, proficiencies, recipes", client)
        self.assertIn("data-library-filter", client)
        self.assertIn("data-remove-filter", client)
        self.assertIn("spellLibraryStorageKey", client)
        self.assertIn("knownPrimaryIds", client)
        self.assertIn("some(recordId => knownPrimaryIds.has(recordId))", client)
        self.assertIn("this.renderBookLibrary(content, collection)", client)
        self.assertIn("proficiency-library", client)
        self.assertIn("recipe-library", client)
        self.assertIn("saveKnowledgeLibraryState", client)
        self.assertIn("← Books", client)
        self.assertIn('<div class="ccgb-book-reader-header"', client)
        self.assertNotIn('<header class="ccgb-book-reader-header"', client)
        self.assertNotIn("Character profile</p>", client)
        self.assertIn("data-book-content-count", client)
        self.assertIn("loadPrivateImage", client)
        self.assertIn("releaseAssets(false)", client)
        self.assertIn("ccgb-book-grid", stylesheet)
        self.assertIn("book-cover:", (root / "headmasters_scroll" / "character_sheet.py").read_text(encoding="utf-8"))
        self.assertIn("character_roll_request", client)
        self.assertIn("roll_result_preview", client)
        self.assertIn("Rolling ${String(label", client)
        self.assertIn("client_request_id", client)
        self.assertIn("ccgb-roll-components", client)
        self.assertIn("component.sources || []", client)
        self.assertIn("is-roll-critical-failure", stylesheet)
        self.assertIn("is-roll-failure", stylesheet)
        self.assertIn("is-roll-success", stylesheet)
        self.assertIn("is-roll-critical-success", stylesheet)
        self.assertIn("edgePointToward", client)
        self.assertIn("skillTitle", client)
        for hover_label in (
            "Buys", "Corecourses", "Electives", "Traits", "Wand parts", "Wand",
            "Quality", "Accessories", "Passive", "Eminence", "Temp",
        ):
            self.assertIn(f"['{hover_label}',", client)
        self.assertIn("Number(breakdown[key] ?? 0)", client)
        self.assertNotIn("sources.map(source", client)
        self.assertNotIn("window.crypto?.getRandomValues", client)
        self.assertNotIn("rolled ${targetId}", client)
        self.assertIn("Click to inspect the dice and every modifier", client)
        self.assertIn("is-name-revealed", client)
        self.assertIn("Share name with players", desktop)
        self.assertIn("character_sheet_updated", client)
        self.assertIn("Ability and Skill Rolls", client)
        self.assertIn("Characteristics Rolls", client)
        self.assertIn("Parental Rolls", client)
        self.assertIn("board_move_commit", client)
        self.assertIn("board_move_committed", client)
        self.assertIn("request_id:", client)
        self.assertIn("/v1/assets/", client)
        self.assertIn("ccgb-chat-rail", client)
        self.assertIn("is-own", client)
        self.assertIn("chat-collapsed { --ccgb-chat-width: 48px; }", stylesheet)
        self.assertIn(".ccgb-chat-message.is-own", stylesheet)
        self.assertIn(".ccgb-chat-message.is-pending", stylesheet)
        self.assertIn("transform: none;", stylesheet)
        self.assertIn("margin: 7px;", stylesheet)
        self.assertIn("max-width: none;", stylesheet)
        self.assertIn("--ccgb-board-height", stylesheet)
        self.assertIn("aspect-ratio: 3840 / 2960", stylesheet)
        self.assertIn(".ccgb-attributes-panel", stylesheet)
        self.assertIn("MAP_NATIVE_WIDTH = 3840", client)
        self.assertIn("MAP_NATIVE_HEIGHT = 2960", client)
        self.assertIn("MAP_ZOOM_STEP = 1.15", client)
        self.assertIn("event.altKey", client)
        self.assertIn("event.button !== 1", client)
        self.assertIn("event.ctrlKey || event.metaKey", client)
        self.assertIn("--map-token-size", client)
        self.assertIn("tokenSize * 0.9", client)
        self.assertIn("TOKEN_SCREEN_SIZES", client)
        self.assertIn("OVERVIEW_DOT_SCREEN_SIZES", client)
        self.assertIn("LABEL_SCREEN_SIZES", client)
        self.assertIn("LABEL_SCREEN_WIDTHS", client)
        self.assertIn("Math.floor(clicks / 3)", client)
        self.assertIn("tier < 6", client)
        self.assertIn("positionOverviewLabels", client)
        self.assertIn("is-overview-marker", client)
        self.assertIn("is-player-character", client)
        self.assertIn("z-index: 12", stylesheet)
        self.assertIn("--map-actor-camera-scale", client)
        self.assertIn("-player-view", client)
        self.assertIn("saveViewState", client)
        self.assertIn("restoreViewState", client)
        self.assertIn("stage.style.width = `${MAP_NATIVE_WIDTH}px`", client)
        self.assertIn("image-rendering: auto", stylesheet)
        self.assertIn("board_camera_focus", client)
        self.assertIn("Don't allow Headmaster to control my camera", client)
        self.assertIn("document.createElement('div')", client)
        self.assertNotIn("ccgb-actor-indicators", client)
        self.assertIn('data-ccgb="zoom-level"', client)
        self.assertIn("Zoom ${Math.round", client)
        self.assertIn("positionOffscreenPlayerLocator", client)
        self.assertIn("is-offscreen-locator", stylesheet)
        self.assertIn("queueSharpMapRepaint", client)
        self.assertIn("is-camera-moving", stylesheet)
        self.assertIn("is-repainting", stylesheet)
        self.assertIn("background: #d6ad52", stylesheet)
        for section in ("Overview", "Attributes", "Spells", "Proficiencies", "Recipes", "Pets", "Inventory", "Relationships", "Wounds", "Settings"):
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
        self.assertIn('text="Send ✓"', desktop)
        self.assertIn('text="Send all"', desktop)
        self.assertIn('"Remove checked players from this session"', desktop)
        self.assertIn('text="Admit All"', desktop)
        self.assertIn("def toggle_chat", desktop)
        self.assertIn('(\"requests\", \"Requests\")', desktop)
        self.assertIn('(\"control-panel\", \"Control Room\")', desktop)
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
        self.assertIn('text="Send"', desktop)
        self.assertIn('text="Explore…"', desktop)
        self.assertIn('self.board_obscure_button = ttk.Button(header, text="✎"', desktop)
        self.assertIn('"<Double-Button-1>", self.rename_board_obscuration', desktop)
        self.assertNotIn('text="Fit map"', desktop)
        self.assertIn("board_search_results_panel", desktop)
        self.assertIn("No close matches", desktop)
        self.assertIn("self.board_map_controls_dock", desktop)
        self.assertIn('("obfuscation-tools", "▧", "Obfuscation")', desktop)
        self.assertIn('("token-tools", "◉", "Tokens & Zoom")', desktop)
        self.assertNotIn('("board-settings", "⚙", "Game Board Settings")', desktop)
        self.assertIn("board_obscuration_list", desktop)
        self.assertIn('text="Sent ✓"', desktop)
        self.assertIn("def open_board_map_controls", desktop)
        self.assertIn("def adjust_current_map_token_scale", desktop)
        self.assertNotIn('text="Set player start point"', desktop)
        self.assertIn("def open_board_zoom_controls", desktop)
        self.assertIn("def add_board_zoom_override", desktop)
        self.assertIn("def save_board_zoom_profile", desktop)
        self.assertNotIn('text="Save map defaults"', desktop)
        self.assertNotIn('text="Move selected to map centre"', desktop)
        self.assertIn("def _apply_responsive_chat_layout", desktop)
        self.assertIn("self._create_board_map_controls(self.board_tools_content)", desktop)
        self.assertIn("self._create_board_groups_controls(self.board_tools_content)", desktop)
        self.assertIn('("groups", "●", "Characters")', desktop)
        self.assertIn("def _build_headmaster_tools_drawer", desktop)
        self.assertIn("def collapse_headmaster_tools", desktop)
        self.assertIn('"groups": 320', desktop)
        self.assertIn("self.section_bar", desktop)
        self.assertNotIn('text="SECTIONS"', desktop)
        self.assertIn("board_character_sections", desktop)
        self.assertIn('label="Open character sheet"', desktop)
        self.assertIn("def _board_double_click", desktop)
        self.assertIn("/api/admin/board/people/{person_id}/sheet", (root / "headmasters_scroll" / "game_board" / "server.py").read_text(encoding="utf-8"))
        self.assertIn('"creatures": 350', desktop)
        self.assertNotIn("self.board_tools_host = tk.Frame(self.chat_expanded", desktop)
        self.assertIn("self.headmaster_tools_drawer.place(", desktop)
        self.assertNotIn('drawer.pack(side="left"', desktop)
        self.assertNotIn('window.title("Map Tools")', desktop)
        self.assertNotIn('dialog.title("Game Board Occupants")', desktop)
        self.assertNotIn('("groups", "●", "Groups")', desktop)
        self.assertIn('self.show_board_tools_panel("groups")', desktop)
        self.assertIn("BOARD_TOKEN_SCREEN_SIZES", desktop)
        self.assertIn("BOARD_OVERVIEW_DOT_SIZES", desktop)
        self.assertIn("zoom_tier < 6", desktop)
        self.assertNotIn('("Heavy wounds", "#c62828"', desktop)
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
        self.assertIn(
            'if key == "game-board" and self._board_context_available:',
            desktop,
        )
        self.assertIn("self.headmaster_tool_rail.pack_forget()", desktop)
        self.assertLess(
            desktop.index("self.section_bar = tk.Frame("),
            desktop.index("self._build_headmaster_tool_rail(game_board_page)"),
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
