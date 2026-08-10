import inspect
import shutil
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.models import (
    development_year_pages,
    ensure_adult_year_records,
    normalize_development_plan,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
)
from mage_maker.sections.events.controller import EventController
from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_SOURCE_STARTING_ALLOWANCE,
    delete_ledger_entry,
    new_manual_calendar_ledger_entry,
    reconcile_development_ledger_entries,
    replace_ledger_entry,
    updated_ledger_entry,
    visible_ledger_entries,
)
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    new_organization_event,
    normalize_organization_record,
)
from mage_maker.sections.organizations.page import OrganizationPage
from mage_maker.sections.profile.books import BooksView
from mage_maker.sections.profile.page import PersonForm


def school_year_record(year_number):
    return {
        "year": year_number,
        "school": "Hogwarts",
        "ability": "Power",
        "skills": ["Charms", "Defense"],
        "characteristic": "Intellect",
        "assigned_books": [],
        "books": [],
        "eminence": [],
    }


def founding_event(year):
    return {
        "record_id": "organization-founding",
        "event_type": "founding",
        "title": "Founding",
        "year": year,
        "description": "",
        "person_ids": [],
    }


def organization_record(
    record_id,
    name,
    parent_organization_id="",
    location_id="",
    founding_year=1900,
):
    return normalize_organization_record(
        {
            "record_id": record_id,
            "name": name,
            "organization_type": "Governmental",
            "location_id": location_id,
            "parent_organization_id": parent_organization_id,
            "overview": "",
            "notes": "",
            "events": [founding_event(founding_year)],
            "jobs": [],
        }
    )


class OrganizationListDatabase:
    def __init__(self, organizations):
        self.organizations = deepcopy(organizations)

    def list_records(self, collection_name):
        if collection_name != "organizations":
            return []

        return deepcopy(self.organizations)


class ReadingTableFixture:
    def __init__(self, selected_item):
        self.selected_item = selected_item

    def selection(self):
        return (self.selected_item,)


class AcademicYearPageTests(unittest.TestCase):
    def test_july_thirty_first_birth_uses_requested_page_sequence(self):
        plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "school_started": True,
                "academic_years_advanced": 7,
                "school_years": [
                    school_year_record(year_number)
                    for year_number in range(1, 8)
                ],
                "adult_years": ensure_adult_year_records([], 2),
            }
        )

        pages = development_year_pages(
            plan,
            academic_start_year=1991,
            birth_year=1980,
            birth_month=7,
            birth_day=31,
        )

        self.assertEqual(
            "Year 7 (1997-1998)",
            pages[6]["title"],
        )
        self.assertEqual(
            "First year out of school (1998 - 1999)",
            pages[7]["title"],
        )
        self.assertEqual((17, 18), pages[7]["age_range"])
        self.assertEqual("2000", pages[8]["title"])
        self.assertEqual(
            (1998, 1999),
            (
                pages[7]["calendar_year"],
                pages[7]["calendar_end_year"],
            ),
        )

    def test_every_school_page_has_two_calendar_years(self):
        plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "school_started": True,
                "academic_years_advanced": 6,
                "school_years": [
                    school_year_record(year_number)
                    for year_number in range(1, 8)
                ],
            }
        )

        pages = development_year_pages(
            plan,
            academic_start_year=1991,
        )

        self.assertTrue(
            all(
                page["calendar_end_year"]
                == page["calendar_year"] + 1
                for page in pages
            )
        )


class EditableLedgerTests(unittest.TestCase):
    def setUp(self):
        self.school_years = [school_year_record(1)]
        self.entries = reconcile_development_ledger_entries(
            [],
            self.school_years,
            [],
            monthly_allowance_sickles=17,
            starting_allowance_sickles=51,
            academic_start_year=1991,
        )

    def test_automatic_line_item_edit_survives_reconciliation(self):
        opening = next(
            entry
            for entry in self.entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_STARTING_ALLOWANCE
        )
        edited = updated_ledger_entry(
            opening,
            1991,
            7,
            2,
            "Edited starting allowance",
            85,
            "earned",
            "Adjusted by the player",
        )
        entries = replace_ledger_entry(self.entries, edited)
        reconciled = reconcile_development_ledger_entries(
            entries,
            self.school_years,
            [],
            monthly_allowance_sickles=17,
            starting_allowance_sickles=51,
            academic_start_year=1991,
        )
        stored = next(
            entry
            for entry in reconciled
            if entry["entry_id"] == opening["entry_id"]
        )

        self.assertEqual("Edited starting allowance", stored["item"])
        self.assertEqual(85, stored["amount_sickles"])
        self.assertEqual(2, stored["day"])
        self.assertEqual("Adjusted by the player", stored["note"])

    def test_deleted_automatic_line_item_stays_deleted(self):
        opening = next(
            entry
            for entry in self.entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_STARTING_ALLOWANCE
        )
        entries = delete_ledger_entry(
            self.entries,
            opening["entry_id"],
        )
        reconciled = reconcile_development_ledger_entries(
            entries,
            self.school_years,
            [],
            monthly_allowance_sickles=17,
            starting_allowance_sickles=51,
            academic_start_year=1991,
        )

        self.assertNotIn(
            opening["entry_id"],
            {
                entry["entry_id"]
                for entry in visible_ledger_entries(reconciled)
            },
        )
        suppressed = next(
            entry
            for entry in reconciled
            if entry["entry_id"] == opening["entry_id"]
        )
        self.assertTrue(suppressed["suppressed"])

    def test_manual_line_item_can_be_deleted(self):
        manual = new_manual_calendar_ledger_entry(
            1991,
            "October",
            "Second-hand broom",
            34,
            LEDGER_KIND_BOUGHT,
            "Used",
            school_year=1,
        )
        entries = delete_ledger_entry(
            [*self.entries, manual],
            manual["entry_id"],
        )

        self.assertNotIn(
            manual["entry_id"],
            {entry["entry_id"] for entry in entries},
        )


class IntentionalBookNavigationTests(unittest.TestCase):
    def test_intentional_book_opens_its_exact_development_record(self):
        navigation_command = Mock()
        view = object.__new__(BooksView)
        view.development_navigation_command = navigation_command
        view.entries = [
            {
                "source_kind": "intentional",
                "page_type": "school",
                "page_number": 4,
            }
        ]
        view.table = ReadingTableFixture("reading-0")

        BooksView.open_intentional_study_entry(view)

        navigation_command.assert_called_once_with("school", 4)

    def test_assigned_book_does_not_navigate(self):
        navigation_command = Mock()
        view = object.__new__(BooksView)
        view.development_navigation_command = navigation_command
        view.entries = [
            {
                "source_kind": "assigned",
                "page_type": "school",
                "page_number": 4,
            }
        ]
        view.table = ReadingTableFixture("reading-0")

        BooksView.open_intentional_study_entry(view)

        navigation_command.assert_not_called()

    def test_profile_switches_to_development_before_opening_record(self):
        form = object.__new__(PersonForm)
        form.show_page = Mock()
        form.development = Mock()

        PersonForm.open_intentional_study_development_page(
            form,
            "adult",
            3,
        )

        form.show_page.assert_called_once_with("development")
        form.development.show_development_record.assert_called_once_with(
            "adult",
            3,
        )


class OrganizationSearchAndHierarchyTests(unittest.TestCase):
    def test_time_filter_uses_the_founding_year(self):
        dialog = object.__new__(OrganizationSelectionDialog)
        organization = organization_record(
            "ministry",
            "Ministry for Magic",
            founding_year=1700,
        )

        self.assertTrue(
            OrganizationSelectionDialog.organization_matches_year(
                dialog,
                organization,
                1800,
            )
        )
        self.assertFalse(
            OrganizationSelectionDialog.organization_matches_year(
                dialog,
                organization,
                1600,
            )
        )

    def test_place_filter_includes_nested_locations(self):
        dialog = object.__new__(OrganizationSelectionDialog)
        dialog.location_filter_id = "britain"
        dialog.location_labels_by_id = {
            "britain": "Britain",
            "london": "Britain › London",
        }
        organization = organization_record(
            "ministry",
            "Ministry for Magic",
            location_id="london",
        )

        self.assertTrue(
            OrganizationSelectionDialog.organization_matches_location(
                dialog,
                organization,
            )
        )

    def test_first_order_children_exclude_grandchildren(self):
        organizations = [
            organization_record("ministry", "Ministry for Magic"),
            organization_record(
                "aurors",
                "Auror's Office",
                "ministry",
            ),
            organization_record(
                "training",
                "Auror Training",
                "aurors",
            ),
        ]
        controller = OrganizationController(
            OrganizationListDatabase(organizations),
            lambda: [],
        )

        self.assertEqual(
            ["aurors"],
            [
                child["record_id"]
                for child in controller.first_order_children(
                    "ministry"
                )
            ],
        )

    def test_organization_page_has_dialog_choices_and_standard_toolbar(self):
        source = inspect.getsource(OrganizationPage)
        toolbar_source = inspect.getsource(
            OrganizationPage.build_toolbar
        )

        for button_text in ("New", "Delete", "Revert", "Save"):
            self.assertIn(
                f'text="{button_text}"',
                toolbar_source,
            )

        self.assertNotIn('text="Save organization"', source)
        self.assertIn(
            "OrganizationLocationSelectionDialog(",
            source,
        )
        self.assertIn("OrganizationSelectionDialog(", source)
        self.assertIn('text="Nested organizations"', source)


class OrganizationEventPersistenceTests(unittest.TestCase):
    def test_linked_event_appears_for_person_and_survives_reload(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory) / "mage_maker.json"
            )
            shutil.copy2(
                Path("data") / "mage_maker.json",
                database_path,
            )
            database = JsonDatabase(database_path)
            database.load()
            person = database.list_people()[0]
            person_id = person["record_id"]
            organization_controller = OrganizationController(
                database,
                lambda: database.list_records("locations"),
            )
            linked_event = new_organization_event(
                "Department reorganized",
                1998,
                "The department adopted a new structure.",
                [person_id],
            )
            created = organization_controller.create_organization(
                {
                    "name": "Test Ministry Department",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "parent_organization_id": "",
                    "overview": "",
                    "notes": "",
                    "events": [
                        founding_event(1900),
                        linked_event,
                    ],
                    "jobs": [],
                }
            )
            event_controller = EventController(
                database,
                database.list_people,
                lambda: database.list_records("locations"),
                lambda: [],
            )
            person_events = event_controller.events_for_person(
                person_id
            )
            visible_event = next(
                event
                for event in person_events
                if event.get("organization_id")
                == created["record_id"]
            )

            self.assertEqual(
                "Department reorganized",
                visible_event["title"],
            )
            self.assertEqual(
                created["record_id"],
                visible_event["organization_id"],
            )

            event_controller.update_event(
                visible_event["record_id"],
                {
                    **visible_event,
                    "description": "Edited from the person's event view.",
                },
            )
            reloaded = JsonDatabase(database_path)
            reloaded.load()
            saved_organization = reloaded.read_record(
                "organizations",
                created["record_id"],
            )
            saved_event = next(
                event
                for event in saved_organization["events"]
                if event["record_id"] == linked_event["record_id"]
            )

            self.assertEqual(
                [person_id],
                saved_event["person_ids"],
            )
            self.assertEqual(
                "Edited from the person's event view.",
                saved_event["description"],
            )


if __name__ == "__main__":
    unittest.main()
