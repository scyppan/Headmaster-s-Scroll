import inspect
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    board_character_sections,
    board_from_admin_state,
    format_expiration_countdown,
    format_stored_local_datetime,
    parse_local_session_end,
    session_can_activate,
    session_can_restart,
)


class FakeTree:
    def __init__(self, selected: str):
        self.selected = selected
        self.selection_set_calls = []

    def selection(self):
        return (self.selected,)

    def winfo_exists(self):
        return True

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

    def get(self):
        return self.value


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
    def test_sessions_page_can_restart_live_or_restorable_unexpired_rooms(self):
        now = datetime(2098, 12, 31, 12, tzinfo=timezone.utc)
        live = {
            "id": "session-live",
            "expires_at": "2099-01-01T12:00:00Z",
        }
        ended = {
            "id": "session-ended",
            "archived": True,
            "status": "ended",
            "restartable": True,
            "expires_at": "2099-01-01T12:00:00Z",
        }

        self.assertTrue(session_can_activate(live, now))
        self.assertTrue(session_can_activate(ended, now))
        self.assertFalse(session_can_activate(
            {**live, "expires_at": "2098-01-01T12:00:00Z"}, now
        ))
        self.assertFalse(session_can_activate(
            {**live, "status": "expiring"}, now
        ))
        self.assertFalse(session_can_activate(
            {**ended, "restartable": False}, now
        ))

    def test_sessions_restart_button_tracks_selected_room_eligibility(self):
        window = object.__new__(GameBoardWindow)
        window.sessions_restart_button = FakeManagedWidget()
        window._restart_session_pending_id = None
        window._board_session_select_pending_id = None
        window.managed_session_id = "session-live"
        window.state_data = {
            "sessions": [{
                "id": "session-live",
                "expires_at": "2099-01-01T12:00:00Z",
            }],
            "archived_sessions": [],
        }

        window._update_sessions_restart_button()
        self.assertEqual(window.sessions_restart_button.state, "normal")

        window._restart_session_pending_id = "session-live"
        window._update_sessions_restart_button()
        self.assertEqual(window.sessions_restart_button.state, "disabled")

        window._restart_session_pending_id = None
        window.state_data["sessions"][0]["expires_at"] = (
            "2000-01-01T00:00:00Z"
        )
        window._update_sessions_restart_button()
        self.assertEqual(window.sessions_restart_button.state, "disabled")

    def test_sessions_restart_activates_selected_live_room(self):
        window = object.__new__(GameBoardWindow)
        session = {
            "id": "session-live",
            "status": "active",
            "expires_at": "2099-01-01T12:00:00Z",
        }
        window.state_data = {
            "sessions": [session], "archived_sessions": []
        }
        window.managed_session_id = "session-live"
        window.selected_session_id = "session-live"
        window._restart_session_pending_id = None
        window._board_session_select_pending_id = None
        window.sessions_restart_button = FakeManagedWidget()
        window._confirm_live_session_restart = lambda _session: True
        calls = []
        notices = []
        window.server = SimpleNamespace(
            start=lambda: calls.append(("server", "start"))
        )
        window.client = SimpleNamespace(
            request=lambda method, path: calls.append((method, path))
            or {"id": "session-live"}
        )
        window.set_notice = lambda text, error=False: notices.append(
            (text, error)
        )
        window._cancel_board_delayed_actions = lambda: calls.append(
            ("cancel", "board")
        )
        window._reset_board_context = lambda: calls.append(("reset", "board"))
        window._set_board_context_available = (
            lambda available: calls.append(("available", available))
        )
        window._render_board = lambda board: calls.append(("render", board))
        window._show_board_loading = lambda text="": calls.append(
            ("loading", text)
        )
        window.refresh = lambda silent=False: calls.append(("refresh", silent))

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window.restart_selected_session()

        self.assertIn(
            ("POST", "/api/admin/sessions/session-live/restart"), calls
        )
        self.assertLess(
            calls.index(("server", "start")),
            calls.index(("POST", "/api/admin/sessions/session-live/restart")),
        )
        self.assertIsNone(window.selected_session_id)
        self.assertEqual(
            window._board_session_select_pending_id, "session-live"
        )
        self.assertIn(("reset", "board"), calls)
        self.assertIn("existing player links are active", notices[-1][0])

    def test_sessions_restart_respects_live_room_confirmation(self):
        window = object.__new__(GameBoardWindow)
        window.state_data = {
            "sessions": [{
                "id": "session-live",
                "status": "active",
                "expires_at": "2099-01-01T12:00:00Z",
            }],
            "archived_sessions": [],
        }
        window.managed_session_id = "session-live"
        window._restart_session_pending_id = None
        window._confirm_live_session_restart = lambda _session: False
        window._background = lambda *_args, **_kwargs: self.fail(
            "a declined live restart was queued"
        )

        window.restart_selected_session()

    def test_sessions_restart_routes_restorable_ending_to_restart_endpoint(self):
        window = object.__new__(GameBoardWindow)
        ended = {
            "id": "session-ended",
            "archived": True,
            "status": "ended",
            "restartable": True,
            "expires_at": "2099-01-01T12:00:00Z",
        }
        window.state_data = {
            "sessions": [], "archived_sessions": [ended]
        }
        window.managed_session_id = "session-ended"
        window._restart_session_pending_id = None
        restarted = []
        window.restart_ended_session = (
            lambda session_id=None: restarted.append(session_id)
        )

        window.restart_selected_session()

        self.assertEqual(restarted, ["session-ended"])

    def test_only_private_future_manual_endings_can_restart(self):
        now = datetime(2098, 12, 31, 12, tzinfo=timezone.utc)
        restartable = {
            "id": "session-ended",
            "archived": True,
            "status": "ended",
            "restartable": True,
            "expires_at": "2099-01-01T12:00:00Z",
        }

        self.assertTrue(session_can_restart(restartable, now))
        self.assertFalse(session_can_restart(
            {**restartable, "restartable": False}, now
        ))
        self.assertFalse(session_can_restart(
            {**restartable, "status": "expired"}, now
        ))
        self.assertFalse(session_can_restart(
            {**restartable, "expires_at": "2098-01-01T12:00:00Z"}, now
        ))

    def test_live_room_restart_calls_endpoint_and_resets_board_context(self):
        window = object.__new__(GameBoardWindow)
        session = {
            "id": "session-ended",
            "title": "Saturday Game",
            "archived": True,
            "status": "ended",
            "restartable": True,
            "expires_at": "2099-01-01T12:00:00Z",
        }
        window.state_data = {"archived_sessions": [session]}
        window.restart_sessions_tree = FakeTree("session-ended")
        window.restart_session_button = FakeManagedWidget()
        window.selected_invite_ids = {"contact-a"}
        window.managed_session_id = None
        window._board_session_select_pending_id = None
        window._restart_session_pending_id = None
        window.selected_session_id = "other-session"
        calls = []
        notices = []
        window.server = SimpleNamespace(
            start=lambda: calls.append(("server", "start"))
        )
        window.client = SimpleNamespace(
            request=lambda method, path: calls.append((method, path))
            or {"id": "session-ended"}
        )
        window.set_notice = lambda text, error=False: notices.append(
            (text, error)
        )
        window._cancel_board_delayed_actions = lambda: calls.append(
            ("cancel", "board")
        )
        window._reset_board_context = lambda: calls.append(("reset", "board"))
        window._set_board_context_available = (
            lambda available: calls.append(("available", available))
        )
        window._render_board = lambda board: calls.append(("render", board))
        window._show_board_loading = lambda text="": calls.append(
            ("loading", text)
        )
        window.refresh = lambda silent=False: calls.append(("refresh", silent))

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window.restart_ended_session()

        self.assertIn(
            ("POST", "/api/admin/sessions/session-ended/restart"), calls
        )
        self.assertLess(
            calls.index(("server", "start")),
            calls.index(("POST", "/api/admin/sessions/session-ended/restart")),
        )
        self.assertEqual(window.managed_session_id, "session-ended")
        self.assertEqual(
            window._board_session_select_pending_id, "session-ended"
        )
        self.assertIsNone(window.selected_session_id)
        self.assertEqual(window.selected_invite_ids, set())
        self.assertIn(("reset", "board"), calls)
        self.assertIn(("render", {}), calls)
        self.assertIn("existing player links are active", notices[-1][0])

    def test_live_room_ignores_duplicate_restart_activation(self):
        window = object.__new__(GameBoardWindow)
        window.state_data = {"archived_sessions": [{
            "id": "session-ended",
            "archived": True,
            "status": "ended",
            "restartable": True,
            "expires_at": "2099-01-01T12:00:00Z",
        }]}
        window.restart_sessions_tree = FakeTree("session-ended")
        window.restart_session_button = FakeManagedWidget()
        window._restart_session_pending_id = None
        window.set_notice = lambda *_args, **_kwargs: None
        queued = []
        window._background = lambda work, success=None, **kwargs: queued.append(
            (work, success, kwargs)
        )

        window.restart_ended_session()
        window.restart_ended_session()

        self.assertEqual(len(queued), 1)
        self.assertEqual(
            window._restart_session_pending_id, "session-ended"
        )

    def test_character_navigator_groups_placed_and_unplaced_people(self):
        snapshot = {
            "maps": [
                {"record_id": "map-a", "name": "Great Hall"},
                {"record_id": "map-b", "name": "Library"},
            ],
            "actors": [
                {
                    "actor_type": "person", "actor_id": "person-a",
                    "name": "Alice", "map_id": "map-a",
                    "group_name": "Explorers", "faction_name": "School",
                },
                {
                    "actor_type": "person", "actor_id": "person-b",
                    "name": "Bob", "map_id": "map-b",
                    "group_name": "", "faction_name": "",
                },
            ],
        }
        characters = [
            {"id": "person-a", "name": "Alice"},
            {"id": "person-b", "name": "Bob"},
            {
                "id": "person-c", "name": "Celia",
                "faction_id": "faction-c",
                "faction_name": "Raven Circle",
                "faction_color": "#223344",
            },
        ]

        by_map = board_character_sections(
            snapshot, characters, "Maps", selected_map_id="map-b"
        )
        self.assertEqual([label for label, _records in by_map], [
            "Library", "Great Hall", "Unplaced"
        ])
        self.assertTrue(by_map[-1][1][0]["unplaced"])
        by_group = board_character_sections(snapshot, characters, "Groups")
        self.assertEqual(
            {label: [item["name"] for item in records] for label, records in by_group},
            {"Explorers": ["Alice"], "No group": ["Bob", "Celia"]},
        )
        by_faction = board_character_sections(snapshot, characters, "Factions")
        self.assertEqual(
            {label: [item["name"] for item in records] for label, records in by_faction},
            {
                "Raven Circle": ["Celia"],
                "School": ["Alice"],
                "No faction": ["Bob"],
            },
        )
        searched = board_character_sections(snapshot, characters, "Maps", "school")
        self.assertEqual(
            [item["name"] for _label, records in searched for item in records],
            ["Alice"],
        )

    def test_selecting_a_navigator_heading_clears_hidden_character_actions(self):
        window = object.__new__(GameBoardWindow)
        window._rendering_actor_selection = False
        window.board_actor_tree = FakeTree("section:0")
        window.selected_board_actor_id = "person-a"
        window.selected_board_map_id = ""
        window._board_character_sheet_request_token = "old-sheet-request"
        window._board_character_sheet_after_id = None
        window._board_character_sheet_portrait_image = object()
        window.board_snapshot = {
            "actors": [{
                "actor_type": "person", "actor_id": "person-a",
                "name": "Alice", "map_id": "map-a",
            }],
            "maps": [{"record_id": "map-a", "name": "Great Hall"}],
        }
        window.state_data = {"characters": []}
        window.board_actor_action_buttons = [FakeManagedWidget() for _ in range(4)]
        window.board_actor_action_summary = FakeStringValue()
        window.board_character_sheet_name = FakeStringValue()
        window.board_character_sheet_status = FakeStringValue()
        window.board_character_sheet_portrait = FakeLabel()
        window.board_character_sheet_texts = {}

        window._board_actor_selected()

        self.assertEqual(window.selected_board_actor_id, "")
        self.assertEqual(window._board_character_sheet_request_token, "")
        self.assertTrue(all(
            button.state == "disabled"
            for button in window.board_actor_action_buttons
        ))
        self.assertEqual(
            window.board_actor_action_summary.value,
            "Select a character to see their sheet and placement controls.",
        )

    def test_character_sheet_selection_is_debounced(self):
        window = object.__new__(GameBoardWindow)
        window._board_character_sheet_after_id = None
        scheduled = {}
        cancelled = []
        begun = []

        def after(delay, callback):
            after_id = f"after-{len(scheduled) + 1}"
            scheduled[after_id] = (delay, callback)
            return after_id

        window.after = after
        window.after_cancel = cancelled.append
        window._begin_selected_actor_sheet_request = lambda: begun.append(True)

        window._load_selected_actor_sheet()
        first_id = window._board_character_sheet_after_id
        window._load_selected_actor_sheet()
        second_id = window._board_character_sheet_after_id

        self.assertNotEqual(first_id, second_id)
        self.assertEqual(cancelled, [first_id])
        self.assertEqual(scheduled[second_id][0], 180)
        self.assertEqual(begun, [])
        scheduled[second_id][1]()
        self.assertEqual(begun, [True])
        self.assertIsNone(window._board_character_sheet_after_id)

    def test_map_selected_character_clears_an_excluding_navigator_search(self):
        window = object.__new__(GameBoardWindow)
        person = {
            "actor_type": "person", "actor_id": "person-a",
            "name": "Alice", "map_id": "map-a",
        }
        window.board_snapshot = {"actors": [person]}
        window.state_data = {"characters": []}
        window.selected_board_actor_id = "person-a"
        window.board_actor_search_var = FakeStringValue()
        window.board_actor_search_var.set("someone else")
        opened = []
        rendered = []
        loaded = []
        window.show_board_tools_panel = opened.append
        window._render_board_actor_list = lambda: rendered.append(True)
        window._load_selected_actor_sheet = (
            lambda *, force=False: loaded.append(force)
        )

        window.open_selected_actor_sheet()

        self.assertEqual(window.board_actor_search_var.get(), "")
        self.assertEqual(window.selected_board_actor_id, "person-a")
        self.assertEqual(opened, ["groups"])
        self.assertEqual(rendered, [True])
        self.assertEqual(loaded, [True])

    def test_map_piece_menu_reveals_person_before_opening_controls(self):
        window = object.__new__(GameBoardWindow)
        canvas = object()
        window.board_canvases = {"map-a": canvas}
        window.selected_board_actor_id = ""
        window.board_obscure_mode = False
        window._actor_at = lambda *_args: ("person-a", "piece")
        calls = []
        window._reveal_selected_person_in_navigator = (
            lambda: calls.append(("reveal", window.selected_board_actor_id))
        )
        window._draw_board_map = lambda map_id: calls.append(("draw", map_id))
        window._render_board_actor_list = lambda: calls.append(("render", None))
        window._load_selected_actor_sheet = lambda: calls.append(("sheet", None))
        window._open_piece_controls = (
            lambda anchor, x, y: calls.append(("controls", anchor, x, y))
        )
        event = SimpleNamespace(x=4, y=7, x_root=40, y_root=70)

        result = window._board_piece_menu(event, "map-a")

        self.assertEqual(result, "break")
        self.assertEqual(window.selected_board_actor_id, "person-a")
        self.assertEqual(calls[0], ("reveal", "person-a"))
        self.assertEqual(calls[-1], ("controls", canvas, 40, 70))

    def test_map_single_click_reveals_person_before_loading_sheet(self):
        window = object.__new__(GameBoardWindow)
        canvas = object()
        window.board_canvases = {"map-a": canvas}
        window.board_snapshot = {"actors": [{
            "actor_type": "person", "actor_id": "person-a",
            "name": "Alice", "map_id": "map-a",
        }]}
        window._actor_at = lambda *_args: ("person-a", "piece")
        calls = []
        window._reveal_selected_person_in_navigator = (
            lambda: calls.append(("reveal", window.selected_board_actor_id))
        )
        window._render_board_actor_list = lambda: calls.append(("render", None))
        window._draw_board_map = lambda map_id: calls.append(("draw", map_id))
        window._load_selected_actor_sheet = lambda: calls.append(("sheet", None))
        event = SimpleNamespace(x=4, y=7, state=0)

        window._board_drag_start(event, "map-a")

        self.assertEqual(window.selected_board_actor_id, "person-a")
        self.assertEqual(calls[0], ("reveal", "person-a"))
        self.assertEqual(calls[-1], ("sheet", None))

    def test_character_navigator_caps_large_unplaced_searches(self):
        characters = [
            {"id": f"person-{index}", "name": f"Person {index:04d}"}
            for index in range(6_244)
        ]

        collapsed = board_character_sections(
            {"maps": [], "actors": []},
            characters,
            "Maps",
            include_unplaced=False,
        )
        matches = board_character_sections(
            {"maps": [], "actors": []},
            characters,
            "Maps",
            "person",
            max_records=200,
        )

        self.assertEqual(collapsed, [])
        self.assertEqual(
            sum(len(records) for _label, records in matches),
            200,
        )

    def test_creature_selection_remains_available_to_piece_controls(self):
        window = object.__new__(GameBoardWindow)
        creature = {
            "actor_type": "creature",
            "actor_id": "creature-1",
            "name": "Bowtruckle",
            "map_id": "map-a",
        }
        window.board_snapshot = {"actors": [creature]}
        window.state_data = {"characters": []}
        window.selected_board_actor_id = "creature-1"

        self.assertIs(window._selected_board_actor(), creature)
        self.assertIs(window._selected_creature(), creature)

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

    def test_quiet_background_timeout_does_not_replace_active_notice(self):
        window = object.__new__(GameBoardWindow)
        window.refreshing = True
        window.server_status = FakeLabel()
        window._hide_board_loading = lambda: None
        notices = []
        window.set_notice = lambda text, error=False: notices.append((text, error))

        window._failed(TimeoutError("timed out"), quiet=True)

        self.assertFalse(window.refreshing)
        self.assertEqual(notices, [])

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
