import inspect
import json
import tempfile
import unittest
from pathlib import Path

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.mages.page import MagesPage
from mage_maker.sections.profile.page import PersonForm
from mage_maker.sections.settings.controller import (
    ApplicationSettingsController,
)
from mage_maker.sections.settings.mage_groups import (
    DEFAULT_MAGE_GROUP_COLOR,
    DEFAULT_MAGE_GROUP_ID,
    MAGE_GROUPS_SETTING_KEY,
    normalize_mage_group_color,
)
from mage_maker.shell.person_list import PeopleList


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeFrame:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


class FakeSelect:
    def __init__(self, variable):
        self.variable = variable
        self.values = []

    def set_values(self, values):
        self.values = list(values)

        if self.values and self.variable.get() not in self.values:
            self.variable.set(self.values[0])


class FakeNoOp:
    def __call__(self):
        return None


class FakeGroupController:
    def __init__(self, groups):
        self.groups = list(groups)

    def mage_group(self, group_id):
        for group in self.groups:
            if group["group_id"] == group_id:
                return dict(group)

        return dict(self.groups[0])


class MageGroupPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "mage_maker.json"
        )
        self.database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 11,
                        "database_version": "0.11.0",
                        "last_saved": None,
                    },
                    "_application_settings": {
                        "development_strategy_assignment": "scattershot",
                    },
                    "people": [
                        {
                            "record_id": "existing",
                            "displayed_name": "Existing Mage",
                            "biological_mother_id": "",
                            "biological_father_id": "",
                            "biological_mother_status": "unknown",
                            "biological_father_status": "unknown",
                            "mate_ids": [],
                            "spouse_relationships": [],
                            "timeline_events": [],
                            "development_plan": {
                                "schema": "Scattershot",
                                "academic_years_advanced": 0,
                            },
                        }
                    ],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        self.database = JsonDatabase(self.database_path)
        self.database.load()
        self.people_controller = PeopleController(self.database)
        self.settings_controller = ApplicationSettingsController(
            self.database
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_migration_assigns_every_person_to_a_colored_group(self):
        groups = self.settings_controller.mage_groups()
        person = self.database.read_person("existing")

        self.assertEqual(29, self.database.data["_database"]["schema_version"])
        self.assertEqual(
            groups,
            self.database.data["_application_settings"][
                MAGE_GROUPS_SETTING_KEY
            ],
        )
        self.assertEqual(DEFAULT_MAGE_GROUP_ID, person["mage_group_id"])
        self.assertEqual(DEFAULT_MAGE_GROUP_COLOR, groups[0]["color"])

    def test_group_assignment_survives_save_and_reload(self):
        created_group = self.settings_controller.create_mage_group(
            "Founders",
            "#315D8A",
        )
        updated = self.people_controller.update_person(
            "existing",
            {"mage_group_id": created_group["group_id"]},
        )
        reloaded_database = JsonDatabase(self.database_path)
        reloaded_database.load()

        self.assertEqual(
            created_group["group_id"],
            updated["mage_group_id"],
        )
        self.assertEqual(
            created_group["group_id"],
            reloaded_database.read_person("existing")["mage_group_id"],
        )

    def test_new_people_receive_the_default_group(self):
        created = self.people_controller.create_person(
            {"displayed_name": "New Mage"}
        )

        self.assertEqual(
            DEFAULT_MAGE_GROUP_ID,
            created["mage_group_id"],
        )

    def test_renaming_and_recoloring_preserve_group_membership(self):
        created_group = self.settings_controller.create_mage_group(
            "Founders",
            "#315D8A",
        )
        self.people_controller.update_person(
            "existing",
            {"mage_group_id": created_group["group_id"]},
        )
        updated_group = self.settings_controller.update_mage_group(
            created_group["group_id"],
            "First Generation",
            "#3F7D58",
        )

        self.assertEqual(
            created_group["group_id"],
            updated_group["group_id"],
        )
        self.assertEqual("First Generation", updated_group["name"])
        self.assertEqual("#3F7D58", updated_group["color"])
        self.assertEqual(
            created_group["group_id"],
            self.database.read_person("existing")["mage_group_id"],
        )

    def test_unknown_group_assignment_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "existing mage group"):
            self.people_controller.update_person(
                "existing",
                {"mage_group_id": "missing-group"},
            )

    def test_removing_a_group_reassigns_its_people(self):
        created_group = self.settings_controller.create_mage_group(
            "Temporary",
            "#A05A2C",
        )
        self.people_controller.update_person(
            "existing",
            {"mage_group_id": created_group["group_id"]},
        )
        reassigned_count = self.settings_controller.delete_mage_group(
            created_group["group_id"]
        )

        self.assertEqual(1, reassigned_count)
        self.assertEqual(
            DEFAULT_MAGE_GROUP_ID,
            self.database.read_person("existing")["mage_group_id"],
        )

    def test_default_group_cannot_be_removed(self):
        with self.assertRaisesRegex(ValueError, "default mage group"):
            self.settings_controller.delete_mage_group(
                DEFAULT_MAGE_GROUP_ID
            )

    def test_group_names_are_unique_and_colors_are_validated(self):
        self.settings_controller.create_mage_group(
            "Founders",
            "#315D8A",
        )

        with self.assertRaisesRegex(ValueError, "Duplicate mage group name"):
            self.settings_controller.create_mage_group(
                " founders ",
                "#A05A2C",
            )

        with self.assertRaisesRegex(ValueError, "#RRGGBB"):
            normalize_mage_group_color("purple")


class MageGroupPresentationTests(unittest.TestCase):
    def setUp(self):
        self.groups = [
            {
                "group_id": DEFAULT_MAGE_GROUP_ID,
                "name": "Unassigned",
                "color": DEFAULT_MAGE_GROUP_COLOR,
            },
            {
                "group_id": "founders",
                "name": "Founders",
                "color": "#315D8A",
            },
        ]

    def test_people_list_resolves_the_five_pixel_group_bar_color(self):
        people_list = object.__new__(PeopleList)
        people_list.rebuild_rows = FakeNoOp()
        PeopleList.set_people(
            people_list,
            [
                {
                    "record_id": "mage",
                    "displayed_name": "Maeve",
                    "mage_group_id": "founders",
                }
            ],
            "mage",
            self.groups,
        )
        rebuild_source = inspect.getsource(PeopleList.rebuild_rows)

        self.assertEqual(
            "#315D8A",
            people_list.group_colors_by_id["mage"],
        )
        self.assertIn("founders", people_list.search_text_by_id["mage"])
        self.assertIn("width=5", rebuild_source)

    def test_profile_header_uses_display_name_and_group_color(self):
        page = object.__new__(MagesPage)
        page.controller = FakeGroupController(self.groups)
        page.editor_title_value = FakeVariable()
        page.editor_group_bar = FakeFrame()

        MagesPage.update_editor_identity(
            page,
            {
                "displayed_name": "Maeve",
                "mage_group_id": "founders",
            },
        )

        self.assertEqual("Maeve", page.editor_title_value.get())
        self.assertEqual(
            "#315D8A",
            page.editor_group_bar.values["bg"],
        )

    def test_classification_group_selector_maps_name_to_stable_id(self):
        form = object.__new__(PersonForm)
        form.loading = False
        form.mage_group_provider = lambda: self.groups
        form.mage_groups = self.groups
        form.mage_group_value = FakeVariable("Unassigned")
        form.mage_group_select = FakeSelect(form.mage_group_value)

        PersonForm.refresh_mage_groups(form, "founders")

        self.assertEqual(
            ["Unassigned", "Founders"],
            form.mage_group_select.values,
        )
        self.assertEqual("Founders", form.mage_group_value.get())
        self.assertEqual(
            "founders",
            PersonForm.selected_mage_group_id(form),
        )

    def test_group_selector_uses_the_first_full_classification_row(self):
        profile_source = inspect.getsource(
            PersonForm.build_profile_page
        )
        group_start = profile_source.index(
            "group_block = tk.Frame"
        )
        boolean_start = profile_source.index(
            "self.add_boolean_fields(",
            group_start,
        )
        group_layout = profile_source[
            group_start:boolean_start
        ]
        boolean_layout = profile_source[
            boolean_start:
        ]

        self.assertIn("row=0", group_layout)
        self.assertIn("column=0", group_layout)
        self.assertIn("columnspan=2", group_layout)
        self.assertIn("sticky=\"ew\"", group_layout)
        self.assertIn("start_row=1", boolean_layout)

    def test_development_panels_and_skill_controls_follow_current_layout(self):
        initializer_source = inspect.getsource(DevelopmentView.__init__)
        panel_source = inspect.getsource(DevelopmentView.build_plan_panel)

        self.assertIn("self.build_plan_panel()", initializer_source)
        self.assertNotIn("build_school_panel", initializer_source)
        self.assertNotIn("build_strategy_panel", initializer_source)
        self.assertIn('"Development overview"', panel_source)
        self.assertIn('"Initial Values"', initializer_source)
        self.assertIn('"Development years"', panel_source)
        self.assertIn('"Developmental strategy"', panel_source)
        self.assertIn("column=index", panel_source)
        self.assertIn("row=0", panel_source)
        self.assertNotIn(
            "One skill, Two skill, and Three skills concentrate",
            panel_source,
        )


if __name__ == "__main__":
    unittest.main()
