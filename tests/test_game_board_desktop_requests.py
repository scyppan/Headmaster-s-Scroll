import inspect
import unittest
from types import SimpleNamespace

from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    board_request_rows,
    board_request_sections,
    campaign_request_notification_ids,
)


class SelectionTree:
    def selection(self):
        return ("selected",)


class GameBoardDesktopRequestTests(unittest.TestCase):
    def test_unified_projection_is_scoped_to_designated_session(self):
        state = {
            "admin_requests": [
                {
                    "id": "one",
                    "request_key": "campaign:one",
                    "source": "campaign",
                    "decision_status": "pending",
                    "session_id": "session-one",
                    "request_type": "teaching",
                    "type_label": "Teaching",
                    "summary": "Ada wants to teach Bea a spell",
                    "asker": {"name": "Ada"},
                    "details": {"pupil_person_id": "bea"},
                },
                {
                    "id": "two",
                    "source": "admission",
                    "decision_status": "pending",
                    "session_id": "session-two",
                    "asker_name": "Other player",
                },
                {
                    "id": "past",
                    "source": "campaign",
                    "decision_status": "approved",
                    "session_id": "session-one",
                    "asker_name": "Ada",
                },
            ]
        }

        waiting = board_request_rows(state, session_id="session-one")
        history = board_request_rows(state, session_id="session-one", resolved=True)

        self.assertEqual([item["id"] for item in waiting], ["one"])
        self.assertEqual(waiting[0]["asker_name"], "Ada")
        self.assertEqual(waiting[0]["pupil_person_id"], "bea")
        self.assertEqual([item["id"] for item in history], ["past"])

    def test_legacy_projection_uses_contact_name_and_campaign_scope(self):
        state = {
            "contacts": [{"id": "contact-one", "character_name": "Mira"}],
            "requests": [
                {
                    "record_id": "one",
                    "status": "pending",
                    "campaign_id": "campaign-one",
                    "submitted_by_contact_id": "contact-one",
                    "request_type": "equipment_change",
                },
                {
                    "record_id": "two",
                    "status": "pending",
                    "campaign_id": "campaign-two",
                },
            ],
        }

        rows = board_request_rows(
            state, session_id="session-one", campaign_id="campaign-one"
        )

        self.assertEqual([item["id"] for item in rows], ["one"])
        self.assertEqual(rows[0]["asker_name"], "Mira")

    def test_grouping_keeps_askers_together_and_sorts_by_time_or_type(self):
        rows = [
            {
                "request_key": "campaign:a-old",
                "asker_name": "Ada",
                "type_label": "Teaching",
                "submitted_at": "2099-01-01T10:00:00Z",
            },
            {
                "request_key": "campaign:a-new",
                "asker_name": "Ada",
                "type_label": "Creature",
                "submitted_at": "2099-01-03T10:00:00Z",
            },
            {
                "request_key": "campaign:b",
                "asker_name": "Bea",
                "type_label": "Equipment",
                "submitted_at": "2099-01-02T10:00:00Z",
            },
        ]

        newest = board_request_sections(rows, "Newest")
        by_type = board_request_sections(rows, "Type")

        self.assertEqual([name for name, _items in newest], ["Ada", "Bea"])
        self.assertEqual(
            [item["request_key"] for item in newest[0][1]],
            ["campaign:a-new", "campaign:a-old"],
        )
        self.assertEqual(
            [item["type_label"] for item in by_type[0][1]],
            ["Creature", "Teaching"],
        )

    def test_same_display_name_does_not_merge_distinct_askers(self):
        sections = board_request_sections([
            {
                "request_key": "campaign:one",
                "asker_id": "person-one",
                "asker_name": "Alex",
                "submitted_at": "2099-01-01T10:00:00Z",
            },
            {
                "request_key": "campaign:two",
                "asker_id": "person-two",
                "asker_name": "Alex",
                "submitted_at": "2099-01-02T10:00:00Z",
            },
        ])

        self.assertEqual(len(sections), 2)
        self.assertEqual(sum(len(items) for _name, items in sections), 2)

    def test_quick_decision_uses_unified_source_route(self):
        window = object.__new__(GameBoardWindow)
        window.board_pending_requests_tree = SelectionTree()
        window.board_pending_request_rows = {
            "selected": {
                "id": "request-one",
                "request_key": "admission:request-one",
                "source": "admission",
                "decision_status": "pending",
                "session_id": "session-one",
            }
        }
        window.state_data = {
            "admin_requests": [],
            "board_session_id": "session-one",
        }
        window._sync_board_request_actions = lambda: None
        calls = []
        window.client = SimpleNamespace(
            request=lambda *args: calls.append(args) or {"status": "approved"}
        )
        window.set_notice = lambda text: calls.append(("notice", text))
        window.refresh = lambda silent=False: calls.append(("refresh", silent))
        window._failed = lambda *_args: self.fail("decision failed")

        def background(work, success=None, **_kwargs):
            result = work()
            if success:
                success(result)

        window._background = background

        window.resolve_selected_board_request("approved")

        self.assertIn(
            (
                "POST",
                "/api/admin/requests/admission/request-one/decision",
                {
                    "decision": "approved",
                    "expected_session_id": "session-one",
                },
            ),
            calls,
        )
        self.assertIn(("notice", "Request accepted"), calls)

    def test_quick_decision_refuses_missing_or_stale_session_context(self):
        for request_session_id, board_session_id in (
            ("", "session-one"),
            ("session-one", "session-two"),
            ("session-one", ""),
        ):
            with self.subTest(
                request_session_id=request_session_id,
                board_session_id=board_session_id,
            ):
                window = object.__new__(GameBoardWindow)
                window.board_pending_requests_tree = SelectionTree()
                window.board_pending_request_rows = {
                    "selected": {
                        "id": "request-one",
                        "request_key": "campaign:request-one",
                        "source": "campaign",
                        "session_id": request_session_id,
                    }
                }
                window.state_data = {
                    "admin_requests": [],
                    "board_session_id": board_session_id,
                }
                notices = []
                window.set_notice = lambda text, error=False: notices.append(
                    (text, error)
                )
                window._background = lambda *_args, **_kwargs: self.fail(
                    "a stale request decision reached the client"
                )

                window.resolve_selected_board_request("approved")

                self.assertTrue(notices)
                self.assertTrue(notices[-1][1])

    def test_campaign_bell_excludes_admissions_owned_by_admission_alert(self):
        ids = campaign_request_notification_ids([
            {
                "request_key": "campaign:campaign-one",
                "source": "campaign",
            },
            {
                "request_key": "admission:admission-one",
                "source": "admission",
            },
        ])

        self.assertEqual(ids, {"campaign:campaign-one"})

    def test_requests_are_not_a_top_level_application_page(self):
        source = inspect.getsource(GameBoardWindow._build)

        self.assertNotIn('(\"requests\", \"Requests\")', source)
        self.assertNotIn('self._build_requests_page(', source)


if __name__ == "__main__":
    unittest.main()
