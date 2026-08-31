import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    character_sheet_knowledge_confidence,
    character_sheet_recipe_requirement_summary,
    search_character_sheet_knowledge,
)


class FakeButton:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


class FakeLayoutWidget:
    def __init__(self, *, x=0, y=0, width=1, height=1, managed=False):
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.managed = managed

    def update_idletasks(self):
        pass

    def winfo_x(self):
        return self.x

    def winfo_y(self):
        return self.y

    def winfo_width(self):
        return self.width

    def winfo_height(self):
        return self.height

    def winfo_manager(self):
        return "pack" if self.managed else ""


class GameBoardDesktopSheetTests(unittest.TestCase):
    def attributes(self):
        return {
            "attributes": [{"name": "Panache", "value": 3, "total": 8}],
            "skills": [{"name": "Potions", "value": 2, "total": 7}],
        }

    def test_confidence_matches_the_web_required_roll_bands(self):
        easy = character_sheet_knowledge_confidence(
            {"threshold": 8, "skill": "Potions"},
            "recipes",
            self.attributes(),
        )
        impossible = character_sheet_knowledge_confidence(
            {"threshold": 17, "skill": "Potions"},
            "recipes",
            self.attributes(),
        )

        self.assertEqual(easy["required_roll"], 3)
        self.assertEqual(easy["label"], "Easy to prepare")
        self.assertEqual(impossible["label"], "Can't prepare")

    def test_sheet_uses_full_reading_width_when_the_page_has_room(self):
        window = object.__new__(GameBoardWindow)
        window.game_board_page = FakeLayoutWidget(width=912, height=800)
        window.board_actor_sidebar = FakeLayoutWidget(width=264)
        window.headmaster_tool_rail = FakeLayoutWidget()
        window.board_top_controls = FakeLayoutWidget()
        window.board_actor_sheet_width = 640

        self.assertEqual(window._actor_drawer_bounds(), (268, 0, 640, 800))

    def test_search_uses_web_fields_filters_and_relevance(self):
        records = [
            {
                "record_id": "shield",
                "name": "Aegis Charm",
                "skill": "Charms",
                "source": "Defensive Magic",
                "subtype": "Charm",
                "threshold": 8,
                "tags": ["Protection"],
                "description": "Raises a silver shield.",
            },
            {
                "record_id": "light",
                "name": "Wand Light",
                "skill": "Charms",
                "source": "First-Year Charms",
                "subtype": "Charm",
                "threshold": 2,
                "tags": ["Utility"],
                "description": "Makes light.",
            },
        ]

        matches = search_character_sheet_knowledge(
            records,
            "spells",
            query="silver protection",
            skill="Charms",
            source="Defensive Magic",
            subtype="Charm",
        )

        self.assertEqual([item["record_id"] for item in matches], ["shield"])

    def test_recipe_search_filters_readiness_and_sorts_difficulty(self):
        records = [
            {
                "record_id": "hard",
                "name": "Hard Potion",
                "threshold": 9,
                "requirements": {"ready": True},
            },
            {
                "record_id": "easy",
                "name": "Easy Potion",
                "threshold": 3,
                "requirements": {"ready": True},
            },
            {
                "record_id": "missing",
                "name": "Missing Potion",
                "threshold": 1,
                "requirements": {"ready": False},
            },
        ]

        matches = search_character_sheet_knowledge(
            records,
            "recipes",
            readiness="ready",
            sort_by="difficulty",
        )

        self.assertEqual(
            [item["record_id"] for item in matches], ["easy", "hard"]
        )

    def test_recipe_confirmation_summary_separates_consumables_and_vessels(self):
        summary = character_sheet_recipe_requirement_summary({
            "ingredients": [{
                "selected": "Tea leaves",
                "alternatives": [{
                    "name": "Tea leaves", "required": 2, "available": 3,
                }],
            }],
            "vessels": [{"selected": "Copper Cauldron"}],
            "missing": [],
        })

        self.assertEqual(summary["consumables"], ["2 × Tea leaves (3 available)"])
        self.assertEqual(summary["vessels"], ["Copper Cauldron"])
        self.assertEqual(summary["missing"], [])

    def action_window(self, collection, record):
        window = object.__new__(GameBoardWindow)
        window.selected_session_id = "session-a"
        window._active_board_character_sheet_scope = (
            "session-a", "person-a"
        )
        window.board_character_sheet_knowledge_tabs = {
            collection: {"action": FakeButton()}
        }
        window._selected_character_sheet_knowledge_record = (
            lambda selected: record if selected == collection else None
        )
        window._selected_board_actor = lambda: {
            "actor_type": "person", "actor_id": "person-a",
        }
        calls = []
        window.client = SimpleNamespace(
            request=lambda method, path, payload, timeout=0: (
                calls.append((method, path, payload, timeout))
                or {"text": "Authoritative result"}
            )
        )
        window.set_notice = lambda value: calls.append(("notice", value))
        window.refresh = lambda **kwargs: calls.append(("refresh", kwargs))
        window._load_selected_actor_sheet = (
            lambda **kwargs: calls.append(("sheet", kwargs))
        )
        window._background = (
            lambda work, completed, **_kwargs: completed(work())
        )
        return window, calls

    def test_sheet_action_rejects_a_stale_actor_selection(self):
        record = {"record_id": "spell-a", "name": "Aegis Charm"}
        window, calls = self.action_window("spells", record)
        window._selected_board_actor = lambda: {
            "actor_type": "person", "actor_id": "person-b",
        }

        result = window.perform_selected_character_sheet_knowledge("spells")

        self.assertEqual(result, "break")
        self.assertEqual(calls, [])

    def test_spell_action_uses_authoritative_person_roll_endpoint(self):
        record = {"record_id": "spell-a", "name": "Aegis Charm"}
        window, calls = self.action_window("spells", record)

        result = window.perform_selected_character_sheet_knowledge("spells")

        self.assertEqual(result, "break")
        self.assertEqual(calls[0], (
            "POST",
            "/api/admin/board/people/person-a/roll",
            {
                "session_id": "session-a",
                "roll_type": "spell",
                "target_id": "spell-a",
            },
            60,
        ))

    def test_recipe_action_confirms_and_uses_consuming_endpoint(self):
        record = {
            "record_id": "recipe-a",
            "name": "Tea",
            "requirements": {
                "ready": True,
                "ingredients": [{
                    "name": "Tea leaves", "required": 2, "available": 2,
                }],
                "vessel": {"name": "Cauldron"},
            },
        }
        window, calls = self.action_window("recipes", record)

        with patch(
            "headmasters_scroll.game_board.desktop.messagebox.askyesno",
            return_value=True,
        ) as confirm:
            result = window.perform_selected_character_sheet_knowledge("recipes")

        self.assertEqual(result, "break")
        self.assertIn("whether the attempt succeeds or fails", confirm.call_args.args[1])
        self.assertIn("Required vessel (not consumed): Cauldron", confirm.call_args.args[1])
        self.assertEqual(calls[0], (
            "POST",
            "/api/admin/board/people/person-a/recipe-attempt",
            {"session_id": "session-a", "target_id": "recipe-a"},
            60,
        ))

    def test_sheet_builds_dedicated_searchable_knowledge_views(self):
        build_source = inspect.getsource(GameBoardWindow._build_actor_sheet_drawer)
        action_source = inspect.getsource(
            GameBoardWindow.perform_selected_character_sheet_knowledge
        )

        for label in ("Spells", "Proficiencies", "Recipes"):
            self.assertIn(f'"{label}"', build_source)
        self.assertIn("recipe-attempt", action_source)
        self.assertIn('"roll_type": config["singular"]', action_source)


if __name__ == "__main__":
    unittest.main()
