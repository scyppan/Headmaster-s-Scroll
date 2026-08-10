import unittest

from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.models import normalize_world_event_date
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
)
from mage_maker.sections.locations.models import normalize_extinction_year
from mage_maker.sections.locations.period_definitions import (
    load_period_definitions,
)
from mage_maker.shell.application import (
    APPLICATION_SETTINGS_KEY,
    REGION_LOCK_SETTING_KEY,
    MageMakerApp,
)
from mage_maker.shell.person_list import PeopleList
from mage_maker.ui.theme import (
    BORDER_SOFT,
    LOCKED_BORDER,
    LOCKED_RED,
    LOCKED_RED_HOVER,
    TEXT_LIGHT,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeButton:
    def __init__(self):
        self.text = ""
        self.colors = ()
        self.enabled = False

    def set_text(self, text):
        self.text = str(text)

    def set_colors(self, fill, hover_fill, foreground=None):
        self.colors = (fill, hover_fill, foreground)

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class FakeFrame:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


class FakeDatabase:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.dirty = False


class FakeLocationController:
    def __init__(self, valid_ids=()):
        self.valid_ids = set(valid_ids)

    def get_location(self, location_id):
        if location_id in self.valid_ids:
            return {
                "record_id": location_id,
                "name": location_id.title(),
            }

        return None


class FakeLocationCreator:
    def __init__(self):
        self.created_values = []

    def __call__(self, values):
        self.created_values.append(dict(values))
        return {
            "record_id": "mungret",
            **values,
        }


class RequestedUpdateTests(unittest.TestCase):
    def test_people_list_displays_only_the_birth_date(self):
        people_list = object.__new__(PeopleList)

        self.assertEqual(
            "Born 923",
            PeopleList.format_birth_date(
                people_list,
                {
                    "birth_year": 923,
                    "deceased": True,
                    "death_year": 998,
                },
            ),
        )

    def test_locked_location_tree_uses_red_unlock_cues(self):
        hierarchy = object.__new__(LocationHierarchyTree)
        hierarchy.show_scope_controls = True
        hierarchy.scope_location_id = "ireland"
        hierarchy.selected_location_id = "ireland"
        hierarchy.records_by_id = {
            "ireland": {
                "record_id": "ireland",
                "name": "Ireland",
            }
        }
        hierarchy.scope_status_value = FakeVariable()
        hierarchy.scope_button = FakeButton()
        hierarchy.tree_frame = FakeFrame()

        LocationHierarchyTree.update_scope_controls(hierarchy)

        self.assertEqual("Unlock", hierarchy.scope_button.text)
        self.assertEqual(
            (LOCKED_RED, LOCKED_RED_HOVER, TEXT_LIGHT),
            hierarchy.scope_button.colors,
        )
        self.assertEqual(
            LOCKED_BORDER,
            hierarchy.tree_frame.values["highlightbackground"],
        )
        self.assertEqual(
            2,
            hierarchy.tree_frame.values["highlightthickness"],
        )

        hierarchy.scope_location_id = ""
        LocationHierarchyTree.update_scope_controls(hierarchy)

        self.assertEqual("Lock here", hierarchy.scope_button.text)
        self.assertEqual(
            BORDER_SOFT,
            hierarchy.tree_frame.values["highlightbackground"],
        )
        self.assertEqual(
            1,
            hierarchy.tree_frame.values["highlightthickness"],
        )

    def test_region_lock_is_loaded_and_remembered_in_settings(self):
        app = object.__new__(MageMakerApp)
        app.database = FakeDatabase(
            {
                APPLICATION_SETTINGS_KEY: {
                    REGION_LOCK_SETTING_KEY: "ireland",
                }
            }
        )
        app.location_controller = FakeLocationController(
            ("ireland", "limerick")
        )

        self.assertEqual(
            "ireland",
            MageMakerApp.saved_region_lock_id(app),
        )
        self.assertTrue(
            MageMakerApp.remember_region_lock(app, "limerick")
        )
        self.assertEqual(
            "limerick",
            app.database.data[APPLICATION_SETTINGS_KEY][
                REGION_LOCK_SETTING_KEY
            ],
        )
        self.assertTrue(app.database.dirty)

    def test_placeholder_location_uses_place_and_parent_only(self):
        create_location = FakeLocationCreator()

        controller = EventController(
            FakeDatabase(),
            lambda: [],
            lambda: [],
            lambda: [],
            create_location,
        )
        created = controller.create_placeholder_location(
            "Mungret",
            "ireland",
        )

        self.assertEqual("mungret", created["record_id"])
        self.assertEqual(
            {
                "name": "Mungret",
                "parent_location_id": "ireland",
                "demographics": "",
                "notes": "",
                "extinct": False,
                "extinction_year": "",
                "timeline_events": [],
            },
            create_location.created_values[0],
        )

    def test_absolute_world_year_bounds_are_99999(self):
        self.assertEqual(
            "-99999",
            normalize_world_event_date("-99999"),
        )
        self.assertEqual(
            "99999",
            normalize_world_event_date("99999"),
        )
        self.assertEqual(
            -99999,
            normalize_extinction_year("-99999", True),
        )
        self.assertEqual(
            99999,
            normalize_extinction_year("99999", True),
        )

        with self.assertRaisesRegex(ValueError, "-99999 and 99999"):
            normalize_world_event_date("-100000")

        with self.assertRaisesRegex(ValueError, "-99999 and 99999"):
            normalize_extinction_year("100000", True)

    def test_prehistory_and_future_use_absolute_bounds(self):
        periods = load_period_definitions()

        self.assertEqual(
            -99999,
            periods[0]["calculation_start_year"],
        )
        self.assertEqual(
            99999,
            periods[-1]["calculation_end_year"],
        )


if __name__ == "__main__":
    unittest.main()
