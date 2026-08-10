import inspect
import unittest

from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.profile.page import PersonForm
from mage_maker.sections.profile.school_dialog import (
    SchoolSelectionDialog,
    school_curriculum_text,
    school_detail_values,
)
from mage_maker.sections.profile.school_field import (
    SCHOOL_NONE,
    SCHOOL_SPECIALTY,
    SchoolField,
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
        self.enabled = None
        self.colors = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_colors(self, fill, hover_fill, foreground=None):
        self.colors = (fill, hover_fill, foreground)


class FakeLabel:
    def __init__(self):
        self.values = {}

    def configure(self, **values):
        self.values.update(values)


class FakeListbox:
    def __init__(self):
        self.items = []
        self.selection = []

    def delete(self, first_index, last_index):
        self.items = []
        self.selection = []

    def insert(self, index, value):
        self.items.append(value)

    def itemconfigure(self, index, **values):
        return None

    def selection_set(self, index):
        self.selection = [index]

    def see(self, index):
        return None


class EmptySchoolField:
    def get_value(self):
        return ""


class FakeTree:
    def __init__(self):
        self.items = []

    def get_children(self):
        return tuple(range(len(self.items)))

    def delete(self, item_id):
        return None

    def insert(self, parent, index, **values):
        self.items.append(values)


class FakeText:
    def __init__(self):
        self.content = ""
        self.state = "disabled"
        self.seen = None

    def configure(self, **values):
        if "state" in values:
            self.state = values["state"]

    def delete(self, first_index, last_index):
        self.content = ""

    def insert(self, index, value, *tags):
        self.content += value

    def see(self, index):
        self.seen = index


class FakePanel:
    def __init__(self):
        self.visible = None

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class FakeDevelopment:
    def __init__(self):
        self.focus_calls = 0

    def focus_school(self):
        self.focus_calls += 1


class SchoolSelectionTests(unittest.TestCase):
    def test_profile_school_summary_is_plain_text_and_uses_lowercase_none(self):
        profile_source = inspect.getsource(
            PersonForm.build_profile_page
        )
        self.assertIn('value="none"', profile_source)
        self.assertNotIn(
            "school_value = RoundedEntry",
            profile_source,
        )
        self.assertIn("school_value_controls", profile_source)
        self.assertIn('school_value.pack(side="left")', profile_source)
        self.assertIn(
            'change_school_button.pack(\n'
            '            side="left",',
            profile_source,
        )
        self.assertNotIn(
            "school_summary.grid_columnconfigure(1, weight=1)",
            profile_source,
        )
        open_source = inspect.getsource(
            PersonForm.open_school_editor
        )
        self.assertNotIn("show_page", open_source)
        form = object.__new__(PersonForm)
        form.development = FakeDevelopment()
        PersonForm.open_school_editor(form)
        self.assertEqual(1, form.development.focus_calls)
        view = object.__new__(DevelopmentView)
        view.school_field = EmptySchoolField()
        self.assertEqual("none", DevelopmentView.school_display_text(view))

    def test_name_details_precedes_school_on_the_display_name_row(self):
        profile_source = inspect.getsource(
            PersonForm.build_profile_page
        )
        self.assertIn(
            "school_summary = tk.Frame(\n"
            "            name_row,",
            profile_source,
        )
        self.assertIn(
            "self.name_details_button.grid(\n"
            "            row=0,\n"
            "            column=1,",
            profile_source,
        )
        self.assertIn(
            "school_summary.grid(\n"
            "            row=0,\n"
            "            column=2,",
            profile_source,
        )
        self.assertNotIn(
            "school_summary = tk.Frame(\n"
            "            identity_panel.content,",
            profile_source,
        )

    def test_school_field_preserves_database_and_specialty_schools(self):
        field = object.__new__(SchoolField)
        field.loading = False
        field.school_names = ["Hogwarts", "Uagadou"]
        field.choice_value = FakeVariable(SCHOOL_NONE)
        field.specialty_value = FakeVariable()
        field.display_value = FakeVariable("none")

        SchoolField.set_value(field, "Hogwarts")
        self.assertEqual("Hogwarts", SchoolField.get_value(field))
        self.assertEqual("Hogwarts", field.display_value.get())

        SchoolField.set_value(field, "Local Academy")
        self.assertEqual(SCHOOL_SPECIALTY, field.choice_value.get())
        self.assertEqual(
            "Local Academy",
            SchoolField.get_value(field),
        )

        SchoolField.set_value(field, "")
        self.assertEqual("", SchoolField.get_value(field))
        self.assertEqual("none", field.display_value.get())

    def test_school_dialog_displays_casting_and_yearly_curriculum(self):
        dialog = object.__new__(SchoolSelectionDialog)
        dialog.selected_school = {
            "name": "Insosojae",
            "location": "Geoje, South Korea",
            "canon": False,
            "wandless": True,
            "description": "A non-wand academy.",
            "curriculum": [
                {
                    "year": 1,
                    "core": ["Charms", "History"],
                    "electives": ["Flying", "Alchemy"],
                    "elective_limit": 1,
                },
                {
                    "year": 2,
                    "core": ["Defense"],
                    "electives": [],
                    "elective_limit": 0,
                },
            ],
        }
        dialog.detail_heading_value = FakeVariable()
        dialog.detail_location_value = FakeVariable()
        dialog.detail_casting_value = FakeVariable()
        dialog.detail_type_value = FakeVariable()
        dialog.detail_overview_value = FakeVariable()
        dialog.curriculum_text = FakeText()
        dialog.choose_button = FakeButton()

        SchoolSelectionDialog.render_school_details(dialog)

        self.assertEqual(
            "Insosojae",
            dialog.detail_heading_value.get(),
        )
        self.assertEqual(
            "Geoje, South Korea",
            dialog.detail_location_value.get(),
        )
        self.assertEqual(
            "Non-wand casting",
            dialog.detail_casting_value.get(),
        )
        self.assertEqual(
            "Original school",
            dialog.detail_type_value.get(),
        )
        self.assertEqual(
            "A non-wand academy.",
            dialog.detail_overview_value.get(),
        )
        self.assertEqual(
            (
                "Year 1\n"
                "Core courses: Charms, History\n"
                "Elective courses: Flying, Alchemy\n"
                "Elective course limit: 1\n\n"
                "Year 2\n"
                "Core courses: Defense\n"
                "Elective courses: None\n"
                "Elective course limit: 0"
            ),
            dialog.curriculum_text.content,
        )
        self.assertEqual("disabled", dialog.curriculum_text.state)
        self.assertEqual("1.0", dialog.curriculum_text.seen)
        self.assertTrue(dialog.choose_button.enabled)

    def test_school_dialog_has_search_list_and_detailed_selection(self):
        source = inspect.getsource(SchoolSelectionDialog)
        self.assertIn("self.search_control = RoundedEntry", source)
        self.assertIn("self.school_list = tk.Listbox", source)
        self.assertIn("self.curriculum_text = tk.Text", source)
        self.assertIn('wrap="word"', source)
        self.assertNotIn("curriculum_horizontal_scrollbar", source)
        self.assertIn('text="Overview"', source)
        self.assertIn("self.overview_tab_button = SoftButton", source)
        self.assertIn(
            "self.curriculum_tab_button = SoftButton",
            source,
        )
        self.assertIn(
            "self.detail_overview = ScrollableSchoolOverview",
            source,
        )
        self.assertIn("width=480", source)
        self.assertIn('f"{name} ({location})"', source)
        self.assertNotIn("self.detail_text = tk.Text", source)
        detail_values = school_detail_values(
            {
                "name": "Test School",
                "location": "Test Place",
                "wandless": False,
                "curriculum": [],
            }
        )
        self.assertEqual(
            "Wand casting",
            detail_values["casting_approach"],
        )

    def test_school_search_includes_courses_and_location(self):
        schools = [
            {
                "name": "Hogwarts",
                "location": "Scottish Highlands",
                "description": "A castle school.",
                "wandless": False,
                "curriculum": [
                    {
                        "year": 1,
                        "core": ["Charms"],
                        "electives": ["Flying"],
                        "elective_limit": 1,
                    }
                ],
            },
            {
                "name": "Uagadou",
                "location": "Mountains of the Moon, Uganda",
                "description": "An African academy.",
                "wandless": True,
                "curriculum": [],
            },
        ]
        dialog = object.__new__(SchoolSelectionDialog)
        dialog.schools = schools
        dialog.current_school = ""
        dialog.visible_schools = []
        dialog.selected_school = None
        dialog.search_value = FakeVariable("Flying")
        dialog.results_heading = FakeLabel()
        dialog.school_list = FakeListbox()
        dialog.detail_heading_value = FakeVariable()
        dialog.detail_location_value = FakeVariable()
        dialog.detail_casting_value = FakeVariable()
        dialog.detail_type_value = FakeVariable()
        dialog.detail_overview_value = FakeVariable()
        dialog.curriculum_text = FakeText()
        dialog.choose_button = FakeButton()

        SchoolSelectionDialog.refresh_results(dialog)

        self.assertEqual(["Hogwarts"], [
            school["name"]
            for school in dialog.visible_schools
        ])
        self.assertEqual(
            "Schools (1)",
            dialog.results_heading.values["text"],
        )
        self.assertEqual(
            "Wand casting",
            dialog.detail_casting_value.get(),
        )
        self.assertEqual(
            ["Hogwarts (Scottish Highlands)"],
            dialog.school_list.items,
        )

        dialog.search_value.set("Uganda")
        SchoolSelectionDialog.refresh_results(dialog)

        self.assertEqual(["Uagadou"], [
            school["name"]
            for school in dialog.visible_schools
        ])
        self.assertEqual(
            "Non-wand casting",
            dialog.detail_casting_value.get(),
        )
        self.assertEqual(
            ["Uagadou (Mountains of the Moon, Uganda)"],
            dialog.school_list.items,
        )

    def test_curriculum_text_uses_readable_year_blocks(self):
        curriculum_text = school_curriculum_text(
            [
                {
                    "year": 4,
                    "core": "Charms, Defense",
                    "electives": "Flying",
                    "elective_limit": 1,
                }
            ]
        )

        self.assertEqual(
            (
                "Year 4\n"
                "Core courses: Charms, Defense\n"
                "Elective courses: Flying\n"
                "Elective course limit: 1"
            ),
            curriculum_text,
        )

    def test_school_overview_and_curriculum_are_separate_tabs(self):
        dialog = object.__new__(SchoolSelectionDialog)
        dialog.active_detail_tab = ""
        dialog.overview_tab = FakePanel()
        dialog.curriculum_tab = FakePanel()
        dialog.overview_tab_button = FakeButton()
        dialog.curriculum_tab_button = FakeButton()

        SchoolSelectionDialog.show_curriculum_tab(dialog)

        self.assertEqual(
            "curriculum",
            dialog.active_detail_tab,
        )
        self.assertFalse(dialog.overview_tab.visible)
        self.assertTrue(dialog.curriculum_tab.visible)

        SchoolSelectionDialog.show_overview_tab(dialog)

        self.assertEqual("overview", dialog.active_detail_tab)
        self.assertTrue(dialog.overview_tab.visible)
        self.assertFalse(dialog.curriculum_tab.visible)


if __name__ == "__main__":
    unittest.main()
