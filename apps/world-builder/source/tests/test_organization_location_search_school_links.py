import inspect
import unittest
from copy import deepcopy
from types import SimpleNamespace

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.organization_dialogs import (
    OrganizationLocationSelectionDialog,
    QuickOrganizationDialog,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.dialog import EventPersonPickerDialog
from mage_maker.sections.locations.controller import LocationController
from mage_maker.sections.locations.location_hierarchy import (
    location_ids_for_search,
)
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    normalize_organization_record,
)
from mage_maker.sections.organizations.page import OrganizationPage


class FakeDatabase:
    def __init__(self, organizations=None, people=None):
        self.collections = {
            "organizations": deepcopy(organizations or []),
            "locations": [],
            "events": [],
        }
        self.people = deepcopy(people or [])
        self.data = {
            "_application_settings": {
                "mage_groups": [
                    {
                        "group_id": "unassigned",
                        "name": "Unassigned",
                        "color": "#8A738F",
                    },
                    {
                        "group_id": "students",
                        "name": "Students",
                        "color": "#2F6F8F",
                    },
                ]
            }
        }
        self.save_count = 0

    def list_records(self, collection_name):
        return deepcopy(self.collections.get(collection_name, []))

    def read_record(self, collection_name, record_id):
        return next(
            (
                deepcopy(record)
                for record in self.collections.get(collection_name, [])
                if record.get("record_id") == record_id
            ),
            None,
        )

    def create_record(self, collection_name, values):
        created = deepcopy(values)
        created.setdefault(
            "record_id",
            f"{collection_name}-{len(self.collections[collection_name]) + 1}",
        )
        self.collections[collection_name].append(created)
        return deepcopy(created)

    def update_record(self, collection_name, record_id, values):
        for index, record in enumerate(self.collections[collection_name]):
            if record.get("record_id") != record_id:
                continue

            updated = deepcopy(values)
            updated["record_id"] = record_id
            self.collections[collection_name][index] = updated
            return deepcopy(updated)

        raise KeyError(record_id)

    def delete_record(self, collection_name, record_id):
        for index, record in enumerate(self.collections[collection_name]):
            if record.get("record_id") == record_id:
                return self.collections[collection_name].pop(index)

        raise KeyError(record_id)

    def list_people(self):
        return deepcopy(self.people)

    def save(self):
        self.save_count += 1


class FakePersonCreator:
    def __init__(self):
        self.created_values = []

    def __call__(self, values):
        self.created_values.append(deepcopy(values))
        return {
            "record_id": "new-person",
            **values,
        }


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def location_records():
    return [
        {
            "record_id": "britain",
            "name": "Britain",
            "parent_location_id": "",
            "demographics": "Island nation",
            "notes": "",
            "extinct": False,
            "extinction_year": "",
            "timeline_events": [],
        },
        {
            "record_id": "london",
            "name": "London",
            "parent_location_id": "britain",
            "demographics": "Dense magical population",
            "notes": "Government centre",
            "extinct": False,
            "extinction_year": "",
            "timeline_events": [
                {
                    "title": "Battle of London",
                    "date": "1998",
                    "description": "City-wide conflict",
                }
            ],
        },
        {
            "record_id": "ruins",
            "name": "Old Ruins",
            "parent_location_id": "britain",
            "demographics": "",
            "notes": "Abandoned settlement",
            "extinct": True,
            "extinction_year": 1800,
            "timeline_events": [],
        },
    ]


def school_records():
    return [
        {
            "record_id": "school-hogwarts",
            "name": "Hogwarts",
            "location": "Scotland",
            "description": "A school of magic",
            "curriculum": ["Charms", "Defense"],
        }
    ]


def founding_event(year):
    return [
        {
            "record_id": "organization-founding",
            "event_type": "founding",
            "title": "Founding",
            "year": year,
            "description": "",
            "person_ids": [],
        }
    ]


class OrganizationSchoolLinkTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeDatabase()
        self.controller = OrganizationController(
            self.database,
            location_records,
            school_records,
        )

    def test_normalization_adds_canonical_school_field(self):
        normalized = normalize_organization_record(
            {
                "name": "Independent shop",
                "organization_type": "Shop",
                "events": founding_event(1900),
            }
        )

        self.assertEqual("", normalized["school_id"])

    def test_schema_twenty_five_adds_school_links(self):
        database_data = {
            "_database": {
                "schema_version": 24,
                "database_version": "0.24.0",
            },
            "organizations": [
                {
                    "record_id": "school-organization",
                    "name": "Independent School",
                    "organization_type": "School",
                    "location_id": "",
                    "parent_organization_id": "",
                    "overview": "",
                    "notes": "",
                    "events": founding_event(1900),
                    "jobs": [],
                }
            ],
            "people": [],
        }
        database = JsonDatabase("unused.json")

        self.assertTrue(database.migrate_database(database_data))
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        self.assertEqual(
            "",
            database_data["organizations"][0]["school_id"],
        )

    def test_linked_school_controls_name_and_type(self):
        created = self.controller.create_organization(
            {
                "name": "Editable duplicate",
                "organization_type": "Shop",
                "school_id": "school-hogwarts",
                "location_id": "london",
                "parent_organization_id": "",
                "overview": "Ancient education policy",
                "notes": "",
                "events": founding_event(990),
                "jobs": [],
            }
        )

        self.assertEqual("Hogwarts", created["name"])
        self.assertEqual("School", created["organization_type"])
        self.assertEqual("school-hogwarts", created["school_id"])
        self.assertEqual(1, self.database.save_count)

    def test_school_cannot_be_linked_to_two_organizations(self):
        values = {
            "name": "Hogwarts",
            "organization_type": "School",
            "school_id": "school-hogwarts",
            "location_id": "london",
            "parent_organization_id": "",
            "overview": "",
            "notes": "",
            "events": founding_event(990),
            "jobs": [],
        }
        self.controller.create_organization(values)

        with self.assertRaisesRegex(ValueError, "already linked"):
            self.controller.create_organization(values)

    def test_search_combines_text_type_time_place_and_school_link(self):
        self.controller.create_organization(
            {
                "name": "Ignored",
                "organization_type": "Shop",
                "school_id": "school-hogwarts",
                "location_id": "london",
                "parent_organization_id": "",
                "overview": "Ancient education policy",
                "notes": "",
                "events": founding_event(990),
                "jobs": [],
            }
        )
        matches = self.controller.search_organizations(
            "education 990",
            "School",
            1200,
            "britain",
            "linked",
        )

        self.assertEqual(["Hogwarts"], [record["name"] for record in matches])


class LocationSearchTests(unittest.TestCase):
    def test_search_uses_details_and_events_with_all_terms(self):
        visible_ids = location_ids_for_search(
            location_records(),
            "government battle",
        )

        self.assertIn("london", visible_ids)
        self.assertIn("britain", visible_ids)
        self.assertNotIn("ruins", visible_ids)

    def test_filters_find_extinct_end_locations(self):
        visible_ids = location_ids_for_search(
            location_records(),
            "",
            "",
            "Extinct",
            "End locations",
        )

        self.assertIn("ruins", visible_ids)
        self.assertIn("britain", visible_ids)
        self.assertNotIn("london", visible_ids)

    def test_location_controller_lists_only_assigned_organizations(self):
        database = FakeDatabase(
            organizations=[
                {
                    "record_id": "ministry",
                    "name": "Ministry",
                    "organization_type": "Governmental",
                    "location_id": "london",
                },
                {
                    "record_id": "shop",
                    "name": "Village Shop",
                    "organization_type": "Shop",
                    "location_id": "ruins",
                },
            ]
        )
        controller = LocationController(database, lambda: [])

        self.assertEqual(
            ["ministry"],
            [
                organization["record_id"]
                for organization in controller.organizations_for_location(
                    "london"
                )
            ],
        )


class EventPersonSearchTests(unittest.TestCase):
    def test_event_people_carry_group_and_full_person_search_data(self):
        people = [
            {
                "record_id": "person-1",
                "displayed_name": "Hermione Granger",
                "birth_year": 1979,
                "mage_group_id": "students",
            }
        ]
        database = FakeDatabase(people=people)
        controller = EventController(
            database,
            lambda: people,
            location_records,
            lambda: [],
        )
        option = controller.people_options()[0]

        self.assertEqual("Students", option["group_name"])
        self.assertEqual(1979, option["person"]["birth_year"])

    def test_event_controller_can_quick_create_person(self):
        person_creator = FakePersonCreator()
        controller = EventController(
            FakeDatabase(),
            lambda: [],
            location_records,
            lambda: [],
            people_creator=person_creator,
        )
        created = controller.create_event_person(
            {
                "displayed_name": "New Person",
                "birth_year": 1980,
            }
        )

        self.assertEqual("new-person", created["record_id"])
        self.assertEqual(
            "New Person",
            person_creator.created_values[0]["displayed_name"],
        )

    def test_person_picker_searches_history_school_group_and_dates(self):
        picker = SimpleNamespace()
        picker.option_person = EventPersonPickerDialog.option_person.__get__(
            picker
        )
        option = {
            "value": "person-1",
            "label": "Hermione Granger",
            "group_name": "Students",
            "person": {
                "displayed_name": "Hermione Granger",
                "birth_year": 1979,
                "death_year": None,
                "school": "Hogwarts",
                "name_details": {
                    "entries": [
                        {
                            "name_type": "Alias",
                            "name_entry": "Minister Granger",
                            "date": "2019",
                            "note": "Public office",
                        }
                    ]
                },
            },
        }
        search_text = EventPersonPickerDialog.person_search_text(
            picker,
            option,
        )

        for expected in (
            "hermione",
            "minister",
            "hogwarts",
            "students",
            "1979",
            "2019",
        ):
            self.assertIn(expected, search_text)

    def test_person_picker_birth_sort_keeps_unknown_dates_first(self):
        picker = SimpleNamespace(
            sort_value=FakeVariable("Birth year"),
        )
        picker.option_person = EventPersonPickerDialog.option_person.__get__(
            picker
        )
        picker.integer_value = EventPersonPickerDialog.integer_value.__get__(
            picker
        )
        picker.person_age = EventPersonPickerDialog.person_age.__get__(
            picker
        )
        picker.person_sort_key = (
            EventPersonPickerDialog.person_sort_key.__get__(picker)
        )
        options = [
            {
                "value": "newer",
                "label": "Newer",
                "person": {"birth_year": 1980},
            },
            {
                "value": "unknown",
                "label": "Unknown",
                "person": {"birth_year": None},
            },
            {
                "value": "older",
                "label": "Older",
                "person": {"birth_year": 1970},
            },
        ]

        sorted_options = sorted(
            options,
            key=picker.person_sort_key,
        )

        self.assertEqual(
            ["unknown", "older", "newer"],
            [option["value"] for option in sorted_options],
        )


class InterfaceRegressionTests(unittest.TestCase):
    def test_organization_page_has_inline_search_and_school_link(self):
        workspace_source = inspect.getsource(
            OrganizationPage.build_workspace
        )
        details_source = inspect.getsource(
            OrganizationPage.build_details_editor
        )
        school_source = inspect.getsource(
            OrganizationPage.refresh_school_link
        )

        self.assertIn("self.search_control = RoundedEntry", workspace_source)
        self.assertIn('text="Filters ▾"', workspace_source)
        self.assertIn('text="Link school"', details_source)
        self.assertIn("self.name_field.control.set_enabled", school_source)

    def test_every_organization_location_choice_uses_hierarchy(self):
        selection_source = inspect.getsource(
            OrganizationLocationSelectionDialog.build_dialog
        )
        quick_source = inspect.getsource(
            QuickOrganizationDialog.build_dialog
        )

        self.assertIn("LocationHierarchyTree(", selection_source)
        self.assertIn('text="Choose location…"', quick_source)
        self.assertNotIn("self.location_list = tk.Listbox", quick_source)

    def test_event_person_picker_has_filters_and_quick_create(self):
        source = inspect.getsource(EventPersonPickerDialog.build_dialog)

        self.assertIn('text="Filters ▾"', source)
        self.assertIn('text="Show all"', source)
        self.assertIn('text="New person"', source)

    def test_long_development_heading_is_not_forced_into_22_characters(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn("development_page_heading", source)
        self.assertNotIn("width=22", source)


if __name__ == "__main__":
    unittest.main()
