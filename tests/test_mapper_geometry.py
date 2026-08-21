import importlib.util
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch

from apps.mapper.address_dialogs import (
    address_event_type_label,
    compose_address_event_date,
    format_address_event_date,
    normalize_address_event_time,
    parse_address_event_date,
    split_address_event_date,
    inherited_address_inventory,
)


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

    def test_address_event_labels_and_historical_date_display(self):
        self.assertEqual(
            address_event_type_label("address_owner_changed"),
            "New owner",
        )
        self.assertEqual(
            address_event_type_label("address_unknown"),
            "Address event",
        )
        self.assertEqual(parse_address_event_date("27 Aug 2000"), "2000-08-27")
        self.assertEqual(
            parse_address_event_date("04 Mar 3100 BCE"), "-3100-03-04"
        )
        self.assertEqual(
            format_address_event_date("-3100-03-04"), "04 Mar 3100 BCE"
        )
        self.assertEqual(
            split_address_event_date("-3100-03-04"), ("-3100", "3", "4")
        )
        self.assertEqual(
            compose_address_event_date("-3100", "3", "4"), "-3100-03-04"
        )
        self.assertEqual(normalize_address_event_time("0830"), "08:30")
        self.assertEqual(normalize_address_event_time("20:15"), "20:15")
        with self.assertRaises(ValueError):
            parse_address_event_date("August someday")
        with self.assertRaises(ValueError):
            normalize_address_event_time("25:00")

    def test_new_inventory_copies_the_last_snapshot_without_mutating_it(self):
        original = [{
            "record_id": "line-1",
            "collection": "general_items",
            "catalog_record_id": "item-1",
            "name": "Brass key",
            "quantity": 2,
        }]
        world = {"events": [{
            "record_id": "inventory-1",
            "event_type": "address_contents_changed",
            "date": "2000-01-01",
            "address_ids": ["address-1"],
            "inventory": original,
        }]}
        inherited = inherited_address_inventory(
            world, "address-1", before_date="2001-01-01"
        )
        inherited[0]["quantity"] = 9
        self.assertEqual(original[0]["quantity"], 2)

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

    def test_map_switch_clears_every_artifact_owned_by_the_previous_map(self):
        class Canvas:
            def __init__(self):
                self.deleted = []

            def delete(self, tag):
                self.deleted.append(tag)

        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.regions = [{"record_id": "old-region"}]
        window.warp_points = [{"record_id": "old-warp"}]
        window.map_image = object()
        window.tk_map_image = object()
        window.tk_map_image_size = (1, 2)
        window.canvas = Canvas()
        window._reset_editor = lambda: None
        rendered = []
        window.render_region_list = lambda: rendered.append("regions")
        window.render_canvas = lambda: rendered.append("canvas")

        window._clear_map_specific_state()

        self.assertEqual(window.regions, [])
        self.assertEqual(window.warp_points, [])
        self.assertIsNone(window.map_image)
        self.assertIsNone(window.tk_map_image)
        self.assertIsNone(window.tk_map_image_size)
        self.assertEqual(window.canvas.deleted, ["all"])
        self.assertEqual(rendered, ["regions", "canvas"])

    def test_location_default_map_can_also_serve_one_named_floor(self):
        location = {
            "record_id": "hogwarts",
            "default_map_id": "ground-map",
            "floors": [
                {"record_id": "dungeons", "name": "Dungeons", "primary_map_id": ""},
                {"record_id": "ground", "name": "Ground Floor", "primary_map_id": ""},
            ],
        }
        maps = [{"record_id": "ground-map", "location_id": "hogwarts", "floor_id": ""}]

        mapper.assign_location_map_to_floor(location, maps, "ground")

        self.assertEqual(location["default_map_id"], "ground-map")
        self.assertEqual(location["floors"][1]["primary_map_id"], "ground-map")
        self.assertEqual(maps[0]["floor_id"], "ground")

    def test_reassigning_location_map_clears_previous_floor_role(self):
        location = {
            "record_id": "castle",
            "default_map_id": "map-1",
            "floors": [
                {"record_id": "ground", "name": "Ground", "primary_map_id": "map-1"},
                {"record_id": "first", "name": "First", "primary_map_id": ""},
            ],
        }
        maps = [{"record_id": "map-1", "location_id": "castle", "floor_id": "ground"}]

        mapper.assign_location_map_to_floor(location, maps, "first")

        self.assertEqual(location["floors"][0]["primary_map_id"], "")
        self.assertEqual(location["floors"][1]["primary_map_id"], "map-1")
        self.assertEqual(maps[0]["floor_id"], "first")

    def test_location_default_map_may_remain_separate_from_all_floors(self):
        location = {
            "record_id": "castle",
            "default_map_id": "map-1",
            "floors": [
                {"record_id": "ground", "name": "Ground", "primary_map_id": "map-1"},
                {"record_id": "first", "name": "First", "primary_map_id": "map-2"},
            ],
        }
        maps = [
            {"record_id": "map-1", "location_id": "castle", "floor_id": "ground"},
            {"record_id": "map-2", "location_id": "castle", "floor_id": "first"},
        ]

        mapper.keep_location_map_separate_from_floors(location, maps)

        self.assertEqual(location["floors"][0]["primary_map_id"], "")
        self.assertEqual(location["floors"][1]["primary_map_id"], "map-2")
        self.assertEqual(maps[0]["floor_id"], "")
        self.assertEqual(maps[1]["floor_id"], "first")

    def test_recent_maps_are_unique_and_most_recent_first(self):
        recent = mapper.updated_recent_map_ids(
            ["map-2", "map-1", "map-2"], "map-1", limit=3
        )
        self.assertEqual(recent, ["map-1", "map-2"])

    def test_warp_choices_prioritize_nearby_floors_and_fuzzy_search(self):
        locations = [{
            "record_id": "hogwarts",
            "name": "Campus of Hogwarts",
            "floors": [
                {"record_id": "ground", "name": "Ground Floor"},
                {"record_id": "first", "name": "First Floor"},
            ],
        }, {
            "record_id": "hogsmeade",
            "name": "Hogsmeade Village",
            "floors": [],
        }]
        maps = [{
            "record_id": "ground-map",
            "name": "Hogwarts Ground",
            "location_id": "hogwarts",
            "floor_id": "ground",
            "warp_points": [{"record_id": "great-hall", "name": "Great Hall"}],
        }, {
            "record_id": "first-map",
            "name": "Hogwarts First",
            "location_id": "hogwarts",
            "floor_id": "first",
            "warp_points": [{"record_id": "clock-stairs", "name": "Clocktower Stairs"}],
        }, {
            "record_id": "village-map",
            "name": "Village",
            "location_id": "hogsmeade",
            "floor_id": "",
            "warp_points": [{"record_id": "station", "name": "Railway Station"}],
        }]

        choices = mapper.warp_destination_choices(
            maps,
            locations,
            current_location_id="hogwarts",
            current_map_id="ground-map",
            recent_map_ids=["village-map"],
        )

        self.assertEqual([item["category"] for item in choices], [
            "nearby", "nearby", "recent"
        ])
        fuzzy = mapper.filter_warp_destination_choices(choices, "clok stair")
        self.assertEqual([item["record_id"] for item in fuzzy], ["clock-stairs"])

    def test_map_display_name_tracks_renamed_floor(self):
        location = {
            "name": "Hogwarts",
            "floors": [{"record_id": "ground", "name": "Ground Floor"}],
        }

        self.assertEqual(
            mapper.map_name_for_floor(location, "ground"),
            "Hogwarts — Ground Floor",
        )
        self.assertEqual(mapper.map_name_for_floor(location, ""), "Hogwarts")

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

    def test_region_label_drag_uses_normalized_offset_and_saves(self):
        class Event:
            x = 140
            y = 90

        region = {
            "record_id": "region-1",
            "name": "Great Hall",
            "points": deepcopy(self.square),
            "label_offset": {"x": 0.0, "y": 0.0},
        }
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.regions = [region]
        window.drag_state = {
            "kind": "region-label",
            "record_id": "region-1",
            "start_x": 100,
            "start_y": 50,
            "offset": {"x": 0.0, "y": 0.0},
            "changed": False,
        }
        window.map_width = 400
        window.map_height = 200
        window.scale = 1.0
        window.editor_dirty = False
        window.render_canvas = lambda: None
        window.undo_stack = []
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        window.canvas_drag(Event())
        window.canvas_release(Event())

        self.assertEqual(region["label_offset"], {"x": 0.1, "y": 0.2})
        self.assertEqual(saves, ["Moved area label"])

    def test_region_label_offset_is_part_of_canonical_map_metadata(self):
        region = mapper.normalize_region({
            "record_id": "region-1",
            "name": "Great Hall",
            "behavior_type": "area",
            "points": deepcopy(self.square),
            "label_offset": {"x": -0.125, "y": 0.25},
        })
        self.assertEqual(region["label_offset"], {"x": -0.125, "y": 0.25})

    def test_metadata_pause_flushes_to_automatic_save(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.metadata_save_after_id = None
        window.metadata_history_pending = True
        window.regions = [{"record_id": "region-1", "name": "Gringotts"}]
        window.selected_region_id = ""
        window.render_region_list = lambda: None
        window.render_canvas = lambda: None
        window.region_tree = type("RegionTree", (), {
            "exists": lambda _self, _value: False,
        })()
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

            def set(self, value):
                self.value = value

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
        window.metadata_form_dirty = False
        window.metadata_history_pending = False
        window.metadata_save_after_id = None
        window.regions = [region]
        window.selected_region_id = "region-1"
        window.region_name = Value("Library")
        window.region_behavior = Value("Area")
        window.hover_text = HoverText("A quiet reading room ")
        window.status_value = type("Status", (), {"set": lambda *_args: None})()
        window.target_location_id = ""
        window.selected_region = lambda: region
        window.record_history = lambda: None
        window.schedule_metadata_save = lambda: self.fail("Hover text must not schedule a timed save")
        window.render_region_list = lambda: None
        window.render_canvas = lambda: None
        window.region_tree = type("RegionTree", (), {
            "exists": lambda _self, _value: False,
        })()
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True

        window.hover_text_changed()
        self.assertEqual(saves, [])
        self.assertEqual(region["hover_text"], "")
        self.assertTrue(window.metadata_form_dirty)

        window.hover_text_focus_out()
        self.assertEqual(saves, ["Region details"])
        self.assertEqual(region["hover_text"], "A quiet reading room")
        self.assertFalse(window.metadata_form_dirty)

    def test_reselecting_secret_passage_does_not_erase_hover_text_draft(self):
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.selected_region_id = "secret-1"
        window.metadata_form_dirty = True
        window.render_target_controls = lambda: None
        window.render_canvas = lambda: None
        window.region_name = type("Value", (), {"set": lambda *_args: None})()
        window.hover_text = type("HoverText", (), {
            "delete": lambda *_args: self.fail("Draft hover text was replaced"),
            "insert": lambda *_args: self.fail("Draft hover text was replaced"),
        })()

        window.select_region("secret-1")

        self.assertTrue(window.metadata_form_dirty)

    def test_address_polygon_links_one_canonical_location_address(self):
        class Value:
            def __init__(self, value):
                self.value = value

            def get(self):
                return self.value

            def set(self, value):
                self.value = value

        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        address = {
            "record_id": "address-1",
            "location_id": "castle",
            "name": "93 High Street",
        }
        region = {"record_id": "region-1", "address_id": "", "name": "Area 1"}
        session = type("Session", (), {"data": {"addresses": [address]}})()
        window.region_address = Value("No address linked")
        window.region_name = Value("Area 1")
        window.selected_location_id = "castle"
        window.selected_region = lambda: region
        window.edit_session = lambda: session
        window.addresses = []
        window.metadata_history_pending = False
        window.editor_dirty = False
        window.record_history = lambda: None
        window.region_metadata_changed = lambda: None
        window.flush_metadata_save = lambda: True
        window.render_region_list = lambda: None
        window.render_canvas = lambda: None

        self.assertTrue(window.link_region_address(address))
        self.assertEqual(region["address_id"], "address-1")
        self.assertEqual(region["name"], "93 High Street")
        self.assertEqual(window.region_name.get(), "93 High Street")
        self.assertEqual(window.region_address.get(), "Linked: 93 High Street")

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

    def test_failed_region_delete_restores_the_region_in_the_editor(self):
        class Status:
            value = ""

            def set(self, value):
                self.value = value

        region = {
            "record_id": "region-1",
            "name": "Hogsmeade",
            "points": deepcopy(self.square),
        }
        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.regions = [region]
        window.selected_region_id = "region-1"
        window.editor_dirty = False
        window.status_value = Status()
        window.selected_region = lambda: next(
            (item for item in window.regions if item["record_id"] == window.selected_region_id),
            None,
        )
        window.record_history = lambda: None
        window.render_region_list = lambda: None
        window.select_region = lambda region_id: setattr(window, "selected_region_id", region_id)
        window.autosave_map = lambda _reason: False

        with patch.object(mapper.messagebox, "askyesno", return_value=True):
            window.delete_region()

        self.assertEqual(window.regions, [region])
        self.assertEqual(window.selected_region_id, "region-1")
        self.assertIn("restored", window.status_value.value)

    def test_placed_warp_is_selectable_and_draggable_in_select_mode(self):
        class Canvas:
            def focus_set(self):
                pass

        class Event:
            x = 20
            y = 30

        window = mapper.MapperWindow.__new__(mapper.MapperWindow)
        window.canvas = Canvas()
        window.pan_state = None
        window.map_image = object()
        window.mode = "select"
        window.warp_points = [{"record_id": "warp-1", "name": "Stair", "x": 0.2, "y": 0.3}]
        window.selected_warp_point_id = ""
        window.drag_state = None
        window.canvas_to_normal = lambda *_args, **_kwargs: {"x": 0.2, "y": 0.3}
        window.warp_point_at = lambda *_args: window.warp_points[0]
        window.render_canvas = lambda: None

        window.canvas_press(Event())
        self.assertEqual(window.selected_warp_point_id, "warp-1")
        self.assertEqual(window.drag_state["kind"], "warp")

        window.canvas_to_normal = lambda *_args, **_kwargs: {"x": 0.44, "y": 0.55}
        window.editor_dirty = False
        window.canvas_drag(Event())
        self.assertEqual((window.warp_points[0]["x"], window.warp_points[0]["y"]), (0.44, 0.55))
        saves = []
        window.autosave_map = lambda reason: saves.append(reason) or True
        window.canvas_release(Event())
        self.assertEqual(saves, ["Moved warp point"])


if __name__ == "__main__":
    unittest.main()
