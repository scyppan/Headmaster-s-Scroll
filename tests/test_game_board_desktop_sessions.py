import inspect
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    board_from_admin_state,
    format_expiration_countdown,
    format_stored_local_datetime,
    parse_local_session_end,
)


class FakeTree:
    def __init__(self, selected: str):
        self.selected = selected
        self.selection_set_calls = []

    def selection(self):
        return (self.selected,)

    def exists(self, _item_id):
        return True

    def selection_set(self, item_id):
        self.selection_set_calls.append(item_id)
        self.selected = item_id

    def identify_row(self, _y):
        return self.selected


class FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = values.get("text", self.text)


class FakeManagedWidget:
    def __init__(self):
        self.manager = ""
        self.state = "normal"

    def winfo_manager(self):
        return self.manager

    def pack(self, **_values):
        self.manager = "pack"

    def pack_forget(self):
        self.manager = ""

    def configure(self, **values):
        self.state = values.get("state", self.state)


class FakeStringValue:
    def __init__(self):
        self.value = ""

    def set(self, value):
        self.value = value


class FakeEntry:
    def __init__(self, value="draft"):
        self.value = value

    def delete(self, _start, _end):
        self.value = ""


class FakePopup:
    def __init__(self):
        self.destroyed = False
        self.unposted = False

    def winfo_exists(self):
        return True

    def unpost(self):
        self.unposted = True

    def destroy(self):
        self.destroyed = True


class GameBoardDesktopSessionTests(unittest.TestCase):
    def test_deadline_is_displayed_as_exact_configured_local_time(self):
        self.assertEqual(
            format_stored_local_datetime(
                "2026-08-30T04:59:00Z", "America/Chicago"
            ),
            "29 Aug 2026  23:59 CDT",
        )

    def test_expiration_countdown_does_not_round_up(self):
        self.assertEqual(format_expiration_countdown(600), "10:00")
        self.assertEqual(format_expiration_countdown(599.9), "09:59")
        self.assertEqual(format_expiration_countdown(-1), "00:00")

    def test_custom_session_end_rejects_dst_gaps_and_ambiguity(self):
        central = ZoneInfo("America/Chicago")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            parse_local_session_end("2026-03-08 02:30", central)
        with self.assertRaisesRegex(ValueError, "occurs twice"):
            parse_local_session_end("2026-11-01 01:30", central)

        valid = parse_local_session_end("2026-03-08 03:30", central)
        self.assertEqual(
            valid.astimezone(timezone.utc),
            datetime(2026, 3, 8, 8, 30, tzinfo=timezone.utc),
        )

    def test_only_the_designated_live_session_board_is_returned(self):
        state = {
            "board_session_id": "session-b",
            "sessions": [
                {"id": "session-a"},
                {"id": "session-b"},
            ],
            "archived_sessions": [{"id": "session-old", "archived": True}],
            "boards": {
                "session-a": {"campaign_id": "campaign-a", "maps": ["a"]},
                "session-b": {"campaign_id": "campaign-b", "maps": ["b"]},
                "session-old": {"campaign_id": "campaign-old", "maps": ["old"]},
            },
            "location_maps": ["legacy-global-map"],
        }

        session_id, board = board_from_admin_state(state)

        self.assertEqual(session_id, "session-b")
        self.assertEqual(board["maps"], ["b"])
        board["maps"].append("local-change")
        self.assertEqual(state["boards"]["session-b"]["maps"], ["b"])

    def test_missing_or_archived_designation_never_falls_back(self):
        common = {
            "sessions": [{"id": "session-live"}],
            "archived_sessions": [{"id": "session-old", "archived": True}],
            "boards": {
                "session-live": {"maps": ["live"]},
                "session-old": {"maps": ["old"]},
            },
            "location_maps": ["legacy-global-map"],
        }
        self.assertEqual(board_from_admin_state(common), (None, {}))
        self.assertEqual(
            board_from_admin_state({**common, "board_session_id": "session-old"}),
            (None, {}),
        )

    def test_managed_archived_row_is_separate_from_active_board_session(self):
        window = object.__new__(GameBoardWindow)
        window.selected_session_id = "session-live"
        window.managed_session_id = "session-old"
        window.state_data = {
            "sessions": [{"id": "session-live", "archived": False}],
            "archived_sessions": [{"id": "session-old", "archived": True}],
        }

        self.assertEqual(window._selected_session()["id"], "session-old")
        self.assertEqual(window._board_session()["id"], "session-live")

    def test_selecting_live_session_calls_designation_endpoint(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_tree = FakeTree("session-b")
        window._rendering_session_selection = False
        window._board_session_select_pending_id = None
        window.selected_session_id = "session-a"
        window.managed_session_id = "session-a"
        window._invite_selection_session_id = "session-a"
        window.state_data = {
            "sessions": [{"id": "session-a"}, {"id": "session-b"}],
            "archived_sessions": [],
        }
        window.preferences = {}
        window.preferences_store = SimpleNamespace(save=lambda _value: None)
        calls = []
        window.client = SimpleNamespace(
            request=lambda method, path: calls.append((method, path)) or {}
        )
        window.render = lambda _state: None
        window._reset_board_context = lambda: None
        window._set_board_context_available = lambda _available: None
        window._render_board = lambda _board: None
        window._show_board_loading = lambda _text: None
        window.set_notice = lambda _text, error=False: None
        window.refresh = lambda: None

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window._session_selected()

        self.assertEqual(window.managed_session_id, "session-b")
        self.assertIsNone(window.selected_session_id)
        self.assertEqual(
            calls,
            [("PUT", "/api/admin/sessions/session-b/select")],
        )

    def test_unchanged_queued_session_selection_is_a_no_op(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_tree = FakeTree("session-a")
        window._rendering_session_selection = False
        window.managed_session_id = "session-a"
        window.render = lambda _state: self.fail(
            "an unchanged queued selection rendered again"
        )

        window._session_selected()

        self.assertEqual(window.managed_session_id, "session-a")

    def test_clicking_managed_live_session_explicitly_activates_board(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_tree = FakeTree("session-b")
        window._rendering_session_selection = False
        window._board_session_select_pending_id = None
        window.selected_session_id = "session-a"
        window.managed_session_id = "session-b"
        window._invite_selection_session_id = "session-b"
        window.state_data = {
            "sessions": [{"id": "session-a"}, {"id": "session-b"}],
            "archived_sessions": [],
        }
        window.preferences = {}
        window.preferences_store = SimpleNamespace(save=lambda _value: None)
        calls = []
        window.client = SimpleNamespace(
            request=lambda method, path: calls.append((method, path)) or {}
        )
        window._reset_board_context = lambda: None
        window._set_board_context_available = lambda _available: None
        window._render_board = lambda _board: None
        window._show_board_loading = lambda _text: None
        window.set_notice = lambda _text, error=False: None
        window.refresh = lambda: None

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window._session_clicked(SimpleNamespace(y=0))

        self.assertIsNone(window.selected_session_id)
        self.assertEqual(
            calls,
            [("PUT", "/api/admin/sessions/session-b/select")],
        )

    def test_session_tree_sync_skips_an_already_selected_row(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_tree = FakeTree("session-a")
        window._rendering_session_selection = False

        window._sync_session_tree_selection("session-a")
        window._sync_session_tree_selection("session-b")

        self.assertEqual(window.sessions_tree.selection_set_calls, ["session-b"])
        self.assertFalse(window._rendering_session_selection)

    def test_control_room_configure_handler_never_processes_idle_tasks_inline(self):
        source = inspect.getsource(GameBoardWindow._scrollable_page)

        self.assertNotIn("update_idletasks", source)
        self.assertIn("after_idle", source)

    def test_selecting_archived_session_does_not_designate_it(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_tree = FakeTree("session-old")
        window._rendering_session_selection = False
        window._board_session_select_pending_id = None
        window.selected_session_id = "session-live"
        window.managed_session_id = "session-live"
        window._invite_selection_session_id = "session-live"
        window.state_data = {
            "sessions": [{"id": "session-live"}],
            "archived_sessions": [{"id": "session-old", "archived": True}],
        }
        window.preferences = {}
        window.preferences_store = SimpleNamespace(save=lambda _value: None)
        window.client = SimpleNamespace(
            request=lambda *_args, **_kwargs: self.fail(
                "archived session was sent to the designation endpoint"
            )
        )
        window.render = lambda _state: None

        window._session_selected()

        self.assertEqual(window.managed_session_id, "session-old")
        self.assertEqual(window.selected_session_id, "session-live")

    def test_no_designated_session_clears_board_and_uses_required_message(self):
        window = object.__new__(GameBoardWindow)
        window.selected_session_id = "session-old"
        window.board_snapshot = {"campaign_id": "old-campaign"}
        window.board_empty = FakeLabel()
        events = []

        def reset():
            events.append("reset")
            window.board_snapshot = {}

        window._reset_board_context = reset
        window._set_board_context_available = (
            lambda available: events.append(("available", available))
        )
        window._render_board = lambda board: events.append(("board", board))
        window._render_board_battles = lambda: events.append("battles")

        window._render_designated_board(
            {
                "board_session_id": None,
                "sessions": [{"id": "some-other-live-session"}],
                "boards": {"session-old": {"maps": ["old-map"]}},
                "location_maps": ["global-map"],
            }
        )

        self.assertIsNone(window.selected_session_id)
        self.assertEqual(
            window.board_empty.text,
            "Please start a session to activate the gameboard.",
        )
        self.assertIn(("available", False), events)
        self.assertIn(("board", {}), events)

    def test_expiration_update_uses_optimistic_deadline(self):
        session = {"expires_at": "2099-01-01T12:00:00Z"}
        new_deadline = datetime(2099, 1, 1, 12, 30, tzinfo=timezone.utc)

        payload = GameBoardWindow._session_expiration_payload(
            session, new_deadline
        )

        self.assertEqual(
            payload,
            {
                "expires_at": "2099-01-01T12:30:00Z",
                "expected_expires_at": "2099-01-01T12:00:00Z",
            },
        )
        with self.assertRaisesRegex(ValueError, "different"):
            GameBoardWindow._session_expiration_payload(
                session,
                datetime(2099, 1, 1, 12, tzinfo=timezone.utc),
            )
        with self.assertRaisesRegex(ValueError, "timezone"):
            GameBoardWindow._session_expiration_payload(
                session,
                datetime(2099, 1, 1, 13),
            )

    def test_ten_minute_warning_is_persistent_and_bells_once_per_deadline(self):
        window = object.__new__(GameBoardWindow)
        deadline = datetime(2099, 1, 1, 12, tzinfo=timezone.utc)
        window.selected_session_id = "session-live"
        window.state_data = {
            "settings": {"timezone": "America/Chicago"},
            "sessions": [
                {
                    "id": "session-live",
                    "expires_at": "2099-01-01T12:00:00Z",
                }
            ],
        }
        window.settings = {}
        window.closing = False
        window._expiration_warning_after_id = None
        window._expiration_warning_belled_deadlines = set()
        window._expiration_update_pending = False
        window.session_expiration_alert = FakeManagedWidget()
        window.session_expiration_alert_text = FakeStringValue()
        window.expiration_extension_buttons = [FakeManagedWidget() for _ in range(3)]
        window.workspace = object()
        bells = []
        window.bell = lambda: bells.append("bell")
        window.after = lambda _delay, _callback: "warning-timer"
        window.after_cancel = lambda _after_id: None

        window._update_expiration_warning(deadline - timedelta(minutes=10))
        window._update_expiration_warning(deadline - timedelta(minutes=9, seconds=59))

        self.assertEqual(window.session_expiration_alert.manager, "pack")
        self.assertIn("Session ends in 09:59", window.session_expiration_alert_text.value)
        self.assertEqual(bells, ["bell"])
        self.assertTrue(
            all(button.state == "normal" for button in window.expiration_extension_buttons)
        )

    def test_expiration_control_calls_session_endpoint_with_expected_deadline(self):
        window = object.__new__(GameBoardWindow)
        session = {
            "id": "session-live",
            "expires_at": "2099-01-01T12:00:00Z",
        }
        window._expiration_update_pending = False
        window._board_session = lambda: session
        window._update_expiration_warning = lambda: None
        window.set_notice = lambda _text, error=False: None
        window.refresh = lambda: None
        calls = []
        window.client = SimpleNamespace(
            request=lambda method, path, payload: calls.append(
                (method, path, payload)
            ) or {}
        )

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window._set_board_session_expiration(
            datetime(2099, 1, 1, 13, tzinfo=timezone.utc)
        )

        self.assertEqual(
            calls,
            [
                (
                    "PUT",
                    "/api/admin/sessions/session-live/expiration",
                    {
                        "expires_at": "2099-01-01T13:00:00Z",
                        "expected_expires_at": "2099-01-01T12:00:00Z",
                    },
                )
            ],
        )

    def test_context_reset_clears_drafts_gestures_and_open_piece_menu(self):
        window = object.__new__(GameBoardWindow)
        piece_popup = FakePopup()
        window._board_camera_save_after_ids = {}
        window._piece_popup = piece_popup
        window.chat_entry = FakeEntry("unsent chat")
        window.announcement = FakeEntry("unsent announcement")
        window.board_reveal_value = FakeStringValue()
        window.board_reveal_value.value = True
        window.board_confirmation_message_until = 99.0
        window._board_pan_state = ("map", 1, 2, 3, 4)
        window._drag_label_only = True
        window._drag_label_origin = {"x": 0.4, "y": 0.6}

        window._reset_board_context()

        self.assertEqual(window.chat_entry.value, "")
        self.assertEqual(window.announcement.value, "")
        self.assertFalse(window.board_reveal_value.value)
        self.assertEqual(window.board_confirmation_message_until, 0.0)
        self.assertIsNone(window._board_pan_state)
        self.assertFalse(window._drag_label_only)
        self.assertEqual(window._drag_label_origin, {"x": 0.0, "y": 0.0})
        self.assertTrue(piece_popup.unposted)
        self.assertTrue(piece_popup.destroyed)
        self.assertIsNone(window._piece_popup)


if __name__ == "__main__":
    unittest.main()
