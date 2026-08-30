import inspect
import unittest
from types import SimpleNamespace

from headmasters_scroll.game_board.desktop import (
    GameBoardWindow,
    board_actor_typology_sections,
)


class Value:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class Label:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


class Button:
    def __init__(self):
        self.state = "normal"

    def configure(self, **values):
        self.state = values.get("state", self.state)


class GameBoardDesktopActorTests(unittest.TestCase):
    def snapshot(self):
        return {
            "maps": [
                {"record_id": "map-a", "name": "Great Hall"},
                {"record_id": "map-b", "name": "Forest"},
            ],
            "actors": [
                {
                    "actor_type": "person",
                    "actor_id": "person-a",
                    "name": "Alice",
                    "map_id": "map-a",
                    "group_name": "Prefects",
                    "is_player_character": True,
                },
                {
                    "actor_type": "creature",
                    "actor_id": "creature-a",
                    "name": "Bowtruckle",
                    "true_name": "Bowtruckle",
                    "internal_label": "Bowtruckle · 2",
                    "map_id": "map-b",
                    "location_id": "location-b",
                    "group_name": "Forest denizens",
                    "life_state": "alive",
                },
            ],
        }

    def test_unified_helper_groups_placed_unplaced_and_creature_typologies(self):
        sections = board_actor_typology_sections(
            self.snapshot(),
            [
                {"id": "person-a", "name": "Alice"},
                {"id": "person-b", "name": "Bea"},
            ],
            "Maps",
            selected_map_id="map-b",
        )

        by_type = {name: groups for name, groups in sections}
        characters = [
            actor
            for _section, actors in by_type["Characters"]
            for actor in actors
        ]
        creatures = [
            actor
            for _section, actors in by_type["Creatures"]
            for actor in actors
        ]
        self.assertEqual({actor["actor_id"] for actor in characters}, {
            "person-a", "person-b"
        })
        self.assertEqual(characters[0]["actor_typology"], "Character")
        self.assertTrue(any(actor.get("unplaced") for actor in characters))
        self.assertEqual([actor["actor_id"] for actor in creatures], ["creature-a"])
        self.assertEqual(creatures[0]["actor_typology"], "Creature")
        self.assertEqual(creatures[0]["actor_subtype"], "Bowtruckle")
        self.assertEqual(by_type["Creatures"][0][0], "Forest")

    def test_unified_helper_searches_creature_species_and_keeps_types_separate(self):
        sections = board_actor_typology_sections(
            self.snapshot(),
            [{"id": "person-a", "name": "Alice"}],
            "Groups",
            "bowtruckle",
        )

        by_type = {name: groups for name, groups in sections}
        self.assertEqual(by_type["Characters"], [])
        self.assertEqual(by_type["Creatures"][0][0], "Forest denizens")

    def test_creature_sheet_selection_is_synchronous_and_type_specific(self):
        window = object.__new__(GameBoardWindow)
        creature = self.snapshot()["actors"][1]
        window.board_snapshot = {"actors": [creature]}
        window.selected_board_actor_id = "creature-a"
        window.selected_session_id = "session-a"
        window._board_character_sheet_request_token = ""
        rendered = []
        window._render_board_creature_sheet = rendered.append
        window._background = lambda *_args, **_kwargs: self.fail(
            "creature sheet attempted an unnecessary person-sheet request"
        )

        window._begin_selected_actor_sheet_request()

        self.assertEqual(rendered, [creature])
        self.assertEqual(
            window._board_character_sheet_request_token,
            "session-a:creature-a:creature",
        )

    def test_creature_sheet_exposes_attributes_actions_and_encounter_state(self):
        window = object.__new__(GameBoardWindow)
        creature = {
            **self.snapshot()["actors"][1],
            "visibility": "headmaster",
            "generated": {
                "size": 2,
                "heavy_wound_cap": 3,
                "magical_resistance": 4,
                "intelligence": 5,
                "social_skill": 1,
                "movement": {"climbing": 6},
            },
            "wounds": [{"severity": "heavy", "note": "Broken branch"}],
            "actions": [{"name": "Scratch", "adjusted_range": {"low": 2, "high": 5}}],
        }
        window.board_snapshot = {
            "maps": [{"record_id": "map-b", "name": "Forest"}],
            "actors": [creature],
        }
        window.board_actor_sheet_typology = Value()
        window.board_character_sheet_name = Value()
        window.board_character_sheet_status = Value()
        window.board_character_sheet_portrait = Label()
        window._board_character_sheet_portrait_image = object()
        configured = []
        panels = {}
        window._configure_actor_sheet_tabs = configured.append
        window._set_character_sheet_panel = (
            lambda label, title, sections: panels.setdefault(label, (title, sections))
        )
        window._render_selected_creature_details = lambda: configured.append("actions")

        window._render_board_creature_sheet(creature)

        self.assertEqual(configured, ["creature", "actions"])
        self.assertIn("CREATURE", window.board_actor_sheet_typology.get())
        self.assertIn("Headmaster only", window.board_character_sheet_status.get())
        attribute_text = str(panels["Attributes"])
        self.assertIn("Heavy wound capacity: 3", attribute_text)
        self.assertIn("Climbing: 6", attribute_text)
        self.assertIn("Broken branch", str(panels["Story"]))

    def test_map_double_click_opens_creature_in_shared_sheet_drawer(self):
        window = object.__new__(GameBoardWindow)
        creature = self.snapshot()["actors"][1]
        window.board_canvases = {"map-b": object()}
        window.board_snapshot = {"actors": [creature]}
        window.selected_board_actor_id = ""
        window._actor_at = lambda *_args: ("creature-a", "piece")
        calls = []
        window.open_selected_actor_sheet = lambda: calls.append("sheet")
        window._draw_board_map = calls.append
        window.complete_board_obscuration = lambda *_args: calls.append("obscuration")

        result = window._board_double_click(
            SimpleNamespace(x=10, y=20), "map-b"
        )

        self.assertEqual(result, "break")
        self.assertEqual(window.selected_board_actor_id, "creature-a")
        self.assertEqual(calls, ["sheet", "map-b"])

    def test_creature_selection_keeps_map_and_group_but_disables_faction(self):
        window = object.__new__(GameBoardWindow)
        creature = self.snapshot()["actors"][1]
        window.board_snapshot = {
            "maps": [{"record_id": "map-b", "name": "Forest"}],
            "actors": [creature],
        }
        window.state_data = {"characters": []}
        window.selected_board_actor_id = "creature-a"
        window.board_actor_action_buttons = [Button() for _ in range(4)]
        window.board_actor_action_summary = Value()

        window._update_board_actor_actions()

        self.assertEqual(
            [button.state for button in window.board_actor_action_buttons],
            ["normal", "normal", "normal", "disabled"],
        )
        self.assertIn("Creature", window.board_actor_action_summary.get())

    def test_actor_rail_is_persistent_and_separate_toggle_tools_are_removed(self):
        build = inspect.getsource(GameBoardWindow._build)
        tools = inspect.getsource(GameBoardWindow._build_headmaster_tool_rail)
        drawer = inspect.getsource(GameBoardWindow._build_actor_sheet_drawer)

        self.assertIn("self._create_board_groups_controls(game_board_panel)", build)
        self.assertNotIn('(\"groups\", \"●\", \"Characters\")', tools)
        self.assertNotIn('(\"creatures\", \"◆\", \"Creatures\")', tools)
        self.assertIn("self.board_actor_sheet_width", drawer)
        self.assertIn("self.board_creature_actions", drawer)


if __name__ == "__main__":
    unittest.main()
