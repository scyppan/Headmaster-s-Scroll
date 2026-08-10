import unittest
from unittest.mock import Mock

from mage_maker.sections.profile.page import PersonForm
from mage_maker.shell.person_list import PeopleList


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class ProfileLoadingPerformanceTests(unittest.TestCase):
    def test_mage_list_keeps_only_birth_data_on_the_second_line(self):
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

    def test_death_overview_shows_age_without_repeating_the_date(self):
        form = object.__new__(PersonForm)
        form.variables = {
            "deceased": FakeVariable(True),
            "birth_year": FakeVariable("1980"),
            "birth_month": FakeVariable("7"),
            "birth_day": FakeVariable("31"),
            "death_year": FakeVariable("1998"),
            "death_month": FakeVariable("7"),
            "death_day": FakeVariable("30"),
        }
        form.death_overview_value = FakeVariable()

        PersonForm.update_death_overview(form)

        self.assertEqual(
            "age 17",
            form.death_overview_value.get(),
        )

    def test_selecting_a_person_defers_expensive_panels(self):
        form = object.__new__(PersonForm)
        form.load_generation = 0
        form.loading = False
        form.current_record_id = None
        form.person_snapshot = {}
        form.loaded_section_record_ids = {}
        form.linked_events_snapshot = []
        form.current_name_value = FakeVariable()
        form.variables = {"displayed_name": FakeVariable()}
        form.text_widgets = {}
        form.name_details = {}
        form.imported_count_value = FakeVariable()
        form.famous_connections = Mock()
        form.boolean_widgets = {}
        form.tooltips = {}
        form.active_page_name = "profile"
        form.cancel_deferred_load = Mock()
        form.refresh_mage_groups = Mock()
        form.update_school_summary_from_person = Mock()
        form.update_death_date_visibility = Mock()
        form.update_death_overview = Mock()
        form.show_page = Mock()
        form.update_idletasks = Mock()
        form.schedule_deferred_active_page = Mock()

        PersonForm.set_person(
            form,
            {
                "record_id": "maeve",
                "displayed_name": "Maeve",
                "timeline_events": [{"event_id": "born"}],
                "development_plan": {"adult_years": [{}] * 40},
            },
        )

        self.assertEqual("maeve", form.current_record_id)
        self.assertEqual("Maeve", form.current_name_value.get())
        form.show_page.assert_called_once_with(
            "profile",
            defer_loading=True,
        )
        form.schedule_deferred_active_page.assert_called_once_with()

    def test_loading_variables_does_not_recalculate_development(self):
        form = object.__new__(PersonForm)
        form.loading = True
        form.development = Mock()
        form.change_command = Mock()

        PersonForm.variable_changed(form)

        form.development.set_birth_date.assert_not_called()
        form.change_command.assert_not_called()

    def test_unopened_panels_preserve_the_selected_records_data(self):
        form = object.__new__(PersonForm)
        form.current_record_id = "maeve"
        form.loaded_section_record_ids = {}
        form.person_snapshot = {
            "school": "Hogwarts",
            "blood_status": "Half-blood",
            "developmental_environment": "Magical",
            "parental_values": {"wealth": 9},
            "initial_bonuses": {"traits": ["Frugal"]},
            "characteristics": {"Power": 4},
            "development_plan": {
                "schema": "Scattershot",
                "adult_years": [{"adult_year": 1}],
            },
            "timeline_events": [{"event_id": "maeve-event"}],
            "biological_mother_id": "mother",
            "biological_father_id": "father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
            "mate_ids": ["mate"],
            "spouse_relationships": [{"person_id": "mate"}],
        }

        development_values = PersonForm.current_development_values(form)
        timeline_events = PersonForm.current_timeline_events(form)
        relationship_values = PersonForm.current_relationship_values(form)

        self.assertEqual("Hogwarts", development_values["school"])
        self.assertEqual(
            [{"adult_year": 1}],
            development_values["development_plan"]["adult_years"],
        )
        self.assertEqual([{"event_id": "maeve-event"}], timeline_events)
        self.assertEqual("mother", relationship_values["biological_mother_id"])
        self.assertEqual(["mate"], relationship_values["mate_ids"])


if __name__ == "__main__":
    unittest.main()
