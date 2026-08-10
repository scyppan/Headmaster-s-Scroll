import inspect
import unittest
from copy import deepcopy

from mage_maker.sections.development.models import new_job_record
from mage_maker.sections.events.dialog import PlaceholderLocationDialog
from mage_maker.sections.events.editor import EventEditor
from mage_maker.sections.events.types import (
    canonical_event_type,
    event_type_options,
)
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
)
from mage_maker.sections.locations.models import (
    location_foundation_event_state,
)
from mage_maker.sections.locations.page import LocationPage
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    new_organization_job,
)
from mage_maker.sections.organizations.page import OrganizationPage
from mage_maker.shell.person_list import FILTER_SHOW_ALL, PeopleList


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class NoOpCallable:
    def __call__(self):
        return None


class TimelineDatabase:
    def __init__(self, people, database_year=1993):
        self.people = deepcopy(people)
        self.data = {
            "_application_settings": {
                "database_date": {
                    "year": database_year,
                    "month": 7,
                    "day": 31,
                }
            }
        }

    def list_people(self):
        return deepcopy(self.people)

    def list_records(self, collection_name):
        return []


class MagePeriodFilterTests(unittest.TestCase):
    def setUp(self):
        self.people_list = object.__new__(PeopleList)
        self.people_list.periods_by_name = {
            "Founders era": {
                "name": "Founders era",
                "calculation_start_year": 900,
                "calculation_end_year": 999,
            }
        }

    def test_period_filter_keeps_every_lifespan_that_overlaps(self):
        people = (
            ({"birth_year": 850, "deceased": True, "death_year": 900}, True),
            ({"birth_year": 999}, True),
            ({"birth_year": 950, "deceased": True, "death_year": 980}, True),
            ({"birth_year": 850, "deceased": True, "death_year": 899}, False),
            ({"birth_year": 1000}, False),
            ({"birth_year": None}, False),
        )

        for person, expected in people:
            with self.subTest(person=person):
                self.assertEqual(
                    expected,
                    PeopleList.matches_period_filter(
                        self.people_list,
                        person,
                        "Founders era",
                    ),
                )

    def test_period_filter_is_part_of_the_compact_filter_menu(self):
        source = inspect.getsource(PeopleList.rebuild_filter_menu)

        self.assertIn('label="Period"', source)
        self.assertIn("self.period_filter_value", source)

    def test_show_all_clears_the_selected_period(self):
        people_list = object.__new__(PeopleList)
        people_list.filter_updates_paused = False
        people_list.search_value = FakeVariable("maeve")
        people_list.group_filter_value = FakeVariable("Founders")
        people_list.age_filter_value = FakeVariable("70+")
        people_list.period_filter_value = FakeVariable("Founders era")
        people_list.sort_value = FakeVariable("Name")
        people_list.rebuild_rows = NoOpCallable()

        PeopleList.show_all_people(people_list)

        self.assertEqual(
            FILTER_SHOW_ALL,
            people_list.period_filter_value.get(),
        )


class OrganizationJobTimelineTests(unittest.TestCase):
    def setUp(self):
        self.job = new_organization_job(
            "Chief Auror",
            {"galleons": 20, "sickles": 0, "knuts": 0},
            1980,
        )
        alice_assignment = new_job_record(
            "ministry",
            "Ministry of Magic",
            "Chief Auror",
            self.job["salary"],
            1990,
            1,
            1,
            1991,
            6,
            30,
            organization_job_id=self.job["record_id"],
        )
        bob_assignment = new_job_record(
            "ministry",
            "Ministry of Magic",
            "Chief Auror",
            self.job["salary"],
            1991,
            7,
            1,
            organization_job_id=self.job["record_id"],
        )
        people = [
            {
                "record_id": "alice",
                "displayed_name": "Alice",
                "development_plan": {
                    "adult_years": [
                        {"adult_year": 1, "jobs": [alice_assignment]}
                    ]
                },
            },
            {
                "record_id": "bob",
                "displayed_name": "Bob",
                "development_plan": {
                    "adult_years": [
                        {"adult_year": 1, "jobs": [bob_assignment]}
                    ]
                },
            },
        ]
        self.controller = OrganizationController(
            TimelineDatabase(people),
            lambda: [],
        )

    def test_timeline_is_year_by_year_with_ordered_handover(self):
        timeline = self.controller.organization_job_yearly_timeline(
            self.job
        )

        self.assertEqual(
            [1990, 1991, 1992, 1993],
            [row["year"] for row in timeline],
        )
        self.assertEqual(["Alice"], timeline[0]["holder_names"])
        self.assertEqual(["Alice", "Bob"], timeline[1]["holder_names"])
        self.assertEqual(["Bob"], timeline[2]["holder_names"])
        self.assertEqual("1991  ·  Alice → Bob", timeline[1]["label"])

    def test_timeline_stops_at_database_year_for_ongoing_role(self):
        timeline = self.controller.organization_job_yearly_timeline(
            self.job
        )

        self.assertEqual(1993, timeline[-1]["year"])

    def test_jobs_page_places_timeline_beside_job_list(self):
        source = inspect.getsource(OrganizationPage.build_jobs)

        self.assertIn("self.job_timeline_list", source)
        self.assertIn('"<<ListboxSelect>>"', source)
        self.assertIn('uniform="organization_jobs"', source)


class LocationFoundationTests(unittest.TestCase):
    def test_later_founding_event_is_highlightable_but_not_valid(self):
        state = location_foundation_event_state(
            {
                "record_id": "london",
                "timeline_events": [
                    {
                        "event_id": "politics",
                        "event_type": "political",
                        "title": "Council formed",
                        "date": "900",
                    },
                    {
                        "event_id": "founding",
                        "event_type": "founding",
                        "title": "Founding of London",
                        "date": "901",
                    },
                ],
            }
        )

        self.assertFalse(state["valid"])
        self.assertEqual("politics", state["first_event_id"])
        self.assertEqual("founding", state["foundation_event_id"])

    def test_direct_community_establishment_can_be_the_first_event(self):
        state = location_foundation_event_state(
            {
                "record_id": "london",
                "timeline_events": [
                    {
                        "event_id": "later",
                        "event_type": "political",
                        "title": "Council formed",
                        "date": "901",
                    }
                ],
            },
            [
                {
                    "record_id": "community",
                    "event_type": "wizarding_community_established",
                    "title": "Wizarding community established",
                    "date": "900",
                    "location_ids": ["london"],
                }
            ],
        )

        self.assertTrue(state["valid"])
        self.assertEqual("community", state["first_event_id"])
        self.assertEqual("community", state["foundation_event_id"])

    def test_foundation_wins_a_same_date_tie_in_the_visible_timeline(self):
        state = location_foundation_event_state(
            {
                "record_id": "london",
                "timeline_events": [
                    {
                        "event_id": "other",
                        "event_type": "political",
                        "title": "A council formed",
                        "date": "900",
                    },
                    {
                        "event_id": "founding",
                        "event_type": "founding",
                        "title": "Founding of London",
                        "date": "900",
                    },
                ],
            }
        )

        self.assertTrue(state["valid"])
        self.assertEqual("founding", state["first_event_id"])

    def test_community_establishment_is_a_location_event_type(self):
        location_options = dict(event_type_options("location"))

        self.assertEqual(
            "Wizarding community established",
            location_options["wizarding_community_established"],
        )
        self.assertEqual(
            "wizarding_community_established",
            canonical_event_type(
                "wizarding community established"
            ),
        )

    def test_location_rows_warn_but_foundation_events_use_green_styles(self):
        hierarchy_source = inspect.getsource(
            LocationHierarchyTree.insert_location_record
        )
        timeline_source = inspect.getsource(
            LocationPage.refresh_timeline
        )

        self.assertIn("_foundation_event_valid", hierarchy_source)
        self.assertIn('tags.append("missing_foundation")', hierarchy_source)
        self.assertIn("location_event_is_foundation", timeline_source)
        self.assertIn("background=FAMILY_GREEN", timeline_source)
        self.assertIn("selectbackground=ADD_GREEN", timeline_source)


class CutoffRegressionTests(unittest.TestCase):
    def test_placeholder_location_window_has_room_for_footer(self):
        source = inspect.getsource(PlaceholderLocationDialog.__init__)

        self.assertIn('self.geometry("520x390")', source)
        self.assertIn("self.minsize(480, 370)", source)

    def test_location_event_editor_uses_outer_scrollbar(self):
        source = inspect.getsource(EventEditor.__init__)

        self.assertIn("self.compact_no_scroll = False", source)


if __name__ == "__main__":
    unittest.main()
