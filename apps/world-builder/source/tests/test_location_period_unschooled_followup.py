import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.sections.development.event_eminence import (
    event_eminence_target,
)
from mage_maker.sections.development.models import (
    calculate_development_start_year,
    development_year_pages,
    ensure_adult_year_records,
    normalize_development_plan,
)
from mage_maker.sections.events.editor import EventEditor
from mage_maker.sections.ledger.models import (
    ledger_adult_calendar_year,
    ledger_page_calendar_years,
)
from mage_maker.sections.locations.page import LocationPage
from mage_maker.sections.profile.books import adult_year_reading_entries
from mage_maker.shell.application import MageMakerApp
from mage_maker.shell.person_list import FILTER_SHOW_ALL, PeopleList
from mage_maker.ui.theme import FAMILY_GREEN


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeTimelineList:
    def __init__(self):
        self.rows = []
        self.configurations = {}

    def delete(self, first, last):
        self.rows = []
        self.configurations = {}

    def insert(self, position, value):
        self.rows.append(value)

    def itemconfigure(self, index, **values):
        self.configurations.setdefault(index, {}).update(values)

    def selection_set(self, index):
        return None

    def see(self, index):
        return None


class DeathAndLocationFollowupTests(unittest.TestCase):
    def test_assigned_organizations_are_built_on_their_own_page(self):
        source = inspect.getsource(LocationPage.build_workspace)

        self.assertIn("self.location_organizations_page", source)
        self.assertIn("self.build_assigned_organizations(", source)
        self.assertIn("self.location_details_page", source)
        self.assertNotIn(
            "self.build_assigned_organizations(self.location_details_page)",
            source,
        )

    def test_location_event_editor_uses_the_compact_picker_height(self):
        source = inspect.getsource(EventEditor.__init__)

        self.assertIn('self.context == "location"', source)
        self.assertGreaterEqual(source.count("listbox.configure(height=3)"), 2)

    def test_qualifying_location_events_are_green(self):
        location_page = object.__new__(LocationPage)
        location_page.current_location_id = "london"
        location_page.draft_event = None
        location_page.selected_timeline_event_id = ""
        location_page.timeline_list = FakeTimelineList()
        location_page.controller = SimpleNamespace(
            timeline_for=Mock(
                return_value=[
                    {
                        "event_id": "founding",
                        "event_type": "founding",
                        "title": "Founding of London",
                        "date": "43",
                        "propagation_distance": 0,
                    }
                ]
            )
        )
        location_page.update_timeline_details = Mock()

        LocationPage.refresh_timeline(location_page)

        self.assertEqual(
            FAMILY_GREEN,
            location_page.timeline_list.configurations[0]["background"],
        )


class MageListFollowupTests(unittest.TestCase):
    def test_visible_period_control_uses_the_period_filter_value(self):
        source = inspect.getsource(PeopleList.__init__)

        self.assertIn('text="Alive during period"', source)
        self.assertIn("self.period_filter_select", source)
        self.assertIn("self.period_filter_value", source)

    def test_period_filter_keeps_only_overlapping_lifespans(self):
        people_list = object.__new__(PeopleList)
        people_list.periods_by_name = {
            "Founders": {
                "calculation_start_year": 900,
                "calculation_end_year": 999,
            }
        }
        cases = (
            ({"birth_year": 850, "death_year": 900}, True),
            ({"birth_year": 999}, True),
            ({"birth_year": 850, "death_year": 899}, False),
            ({"birth_year": 1000}, False),
            ({"birth_year": None}, False),
        )

        for person, expected in cases:
            with self.subTest(person=person):
                self.assertEqual(
                    expected,
                    PeopleList.matches_period_filter(
                        people_list,
                        person,
                        "Founders",
                    ),
                )

        self.assertTrue(
            PeopleList.matches_period_filter(
                people_list,
                {},
                FILTER_SHOW_ALL,
            )
        )

    def test_returning_to_mages_refreshes_new_people(self):
        source = inspect.getsource(MageMakerApp.show_page)

        self.assertIn('if page_name == "mages":', source)
        self.assertIn("mages_page.refresh_people(", source)


class UnschooledDevelopmentFollowupTests(unittest.TestCase):
    def setUp(self):
        self.start_year = calculate_development_start_year(
            1767,
            6,
            7,
            school_attended=False,
        )
        self.plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "calendar_year_progression": True,
                "adult_years": ensure_adult_year_records([], 3),
            }
        )

    def test_unschooled_pages_begin_with_birth_year_pair_then_yearly(self):
        pages = development_year_pages(
            self.plan,
            self.start_year,
            1767,
            6,
            7,
            school_attended=False,
        )

        self.assertEqual(1760, self.start_year)
        self.assertEqual(
            ["1767-1768", "1769", "1770"],
            [page["title"] for page in pages],
        )
        self.assertEqual((0, 1), pages[0]["age_range"])

    def test_unschooled_plan_preserves_year_records(self):
        self.assertFalse(self.plan["school_started"])
        self.assertEqual(0, self.plan["academic_years_advanced"])
        self.assertEqual(3, len(self.plan["adult_years"]))
        self.assertTrue(self.plan["calendar_year_progression"])

    def test_unschooled_books_use_the_same_page_titles(self):
        adult_records = ensure_adult_year_records([], 2)
        adult_records[0]["reading_characteristic"] = "intellect"
        adult_records[0]["reading_rolls"] = [10, 10, 1]
        adult_records[0]["books"] = [
            {
                "record_id": "book-1",
                "name": "A Young Mage's Primer",
                "author": "M. Quill",
            }
        ]
        entries = adult_year_reading_entries(
            adult_records,
            self.start_year,
            school_attended=False,
        )

        self.assertEqual(
            "Intentional study in 1767-1768",
            entries[0]["source"],
        )

    def test_unschooled_event_eminence_targets_the_matching_year(self):
        person = {
            "record_id": "flavio",
            "birth_year": 1767,
            "birth_month": 6,
            "birth_day": 7,
            "school": "",
            "development_plan": self.plan,
        }
        target = event_eminence_target(
            person,
            {
                "event_id": "event-1769",
                "event_type": "custom",
                "title": "A notable discovery",
                "date": "1769",
            },
        )

        self.assertEqual("adult", target["page_type"])
        self.assertEqual(2, target["adult_year"])
        self.assertEqual("1769", target["title"])

    def test_unschooled_ledger_skips_the_nonexistent_year_zero(self):
        start_year = calculate_development_start_year(
            1,
            3,
            1,
            school_attended=False,
        )

        self.assertEqual(1, ledger_adult_calendar_year(start_year, 1))
        self.assertEqual(
            {1, 2},
            ledger_page_calendar_years(start_year, adult_year=1),
        )
        self.assertEqual(3, ledger_adult_calendar_year(start_year, 2))


if __name__ == "__main__":
    unittest.main()
