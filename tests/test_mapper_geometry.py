import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


MAPPER_PATH = Path(__file__).resolve().parents[1] / "apps" / "mapper" / "main.py"
SPEC = importlib.util.spec_from_file_location("headmasters_scroll_mapper", MAPPER_PATH)
mapper = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(mapper)


class MapperGeometryTests(unittest.TestCase):
    def setUp(self):
        self.square = [
            {"x": 0.2, "y": 0.2},
            {"x": 0.8, "y": 0.2},
            {"x": 0.8, "y": 0.8},
            {"x": 0.2, "y": 0.8},
        ]

    def test_polygon_hit_testing(self):
        self.assertTrue(mapper.point_in_polygon(0.5, 0.5, self.square))
        self.assertFalse(mapper.point_in_polygon(0.05, 0.5, self.square))

    def test_nearest_edge_returns_projected_insertion_point(self):
        index, point, distance = mapper.nearest_edge(self.square, 0.5, 0.18)
        self.assertEqual(index, 0)
        self.assertAlmostEqual(point["x"], 0.5)
        self.assertAlmostEqual(point["y"], 0.2)
        self.assertAlmostEqual(distance, 0.02)

    def test_whole_polygon_translation_stays_inside_map(self):
        moved = mapper.translated_points(self.square, 0.7, -0.7)
        self.assertEqual(max(point["x"] for point in moved), 1.0)
        self.assertEqual(min(point["y"] for point in moved), 0.0)
        self.assertEqual(
            [(round(point["x"], 4), round(point["y"], 4)) for point in moved],
            [(0.4, 0.0), (1.0, 0.0), (1.0, 0.6), (0.4, 0.6)],
        )

    def test_close_snap_uses_the_first_node_after_three_nodes(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.draft_points = deepcopy(self.square[:3])
        window.normal_to_canvas = lambda point: (point["x"] * 100, point["y"] * 100)
        x, y, snapped = window.draft_pointer_position(22, 21)
        self.assertTrue(snapped)
        self.assertEqual((x, y), (20.0, 20.0))

    def test_completing_polygon_triggers_automatic_save(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.mode = "draw"
        window.draft_points = deepcopy(self.square)
        window.regions = []
        window.editor_dirty = False
        window.record_history = lambda: None
        window.set_mode = lambda mode: setattr(window, "mode", mode)
        window.render_region_list = lambda: None
        window.select_region = lambda region_id: setattr(window, "selected_region_id", region_id)
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        window.complete_polygon()

        self.assertEqual(len(window.regions), 1)
        self.assertEqual(saves, ["Completed polygon"])

    def test_metadata_pause_flushes_to_automatic_save(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.metadata_save_after_id = None
        window.metadata_history_pending = True
        window.regions = [{"record_id": "region-1", "name": "Gringotts"}]
        window.selected_region_id = ""
        window.render_region_list = lambda: None
        window.render_canvas = lambda: None
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        self.assertTrue(window.flush_metadata_save())
        self.assertFalse(window.metadata_history_pending)
        self.assertEqual(saves, ["Region details"])

    def test_hover_text_waits_for_focus_out_before_saving(self):
        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

        class HoverText(Value):
            def __init__(self, value):
                super().__init__(value)
                self.modified = True

            def edit_modified(self, value=None):
                if value is None:
                    return self.modified
                self.modified = bool(value)

            def get(self, *_args):
                return self.value

        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        region = {
            "record_id": "region-1",
            "name": "Library",
            "behavior_type": "area",
            "hover_text": "",
            "target_location_id": "",
        }
        window.loading_region_properties = False
        window.metadata_history_pending = False
        window.metadata_save_after_id = None
        window.regions = [region]
        window.selected_region_id = "region-1"
        window.region_name = Value("Library")
        window.region_behavior = Value("Area")
        window.hover_text = HoverText("A quiet reading room ")
        window.target_location_id = ""
        window.selected_region = lambda: region
        window.record_history = lambda: None
        window.schedule_metadata_save = lambda: self.fail("Hover text must not schedule a timed save")
        window.render_region_list = lambda: None
        window.render_canvas = lambda: None
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        window.hover_text_changed()
        self.assertEqual(saves, [])
        self.assertEqual(region["hover_text"], "A quiet reading room")

        window.selected_region_id = ""
        window.hover_text_focus_out()
        self.assertEqual(saves, ["Region details"])

    def test_warp_tool_creates_named_point_and_saves_it(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.warp_points = []
        window.selected_warp_point_id = ""
        window.editor_dirty = False
        window.render_canvas = lambda: None
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        with patch.object(mapper.simpledialog, "askstring", return_value="Upper Stairwell"):
            window.add_warp_point({"x": 0.31, "y": 0.67})

        self.assertEqual(len(window.warp_points), 1)
        self.assertEqual(window.warp_points[0]["name"], "Upper Stairwell")
        self.assertEqual(
            (window.warp_points[0]["x"], window.warp_points[0]["y"]),
            (0.31, 0.67),
        )
        self.assertEqual(saves, ["Added warp point"])


if __name__ == "__main__":
    unittest.main()
