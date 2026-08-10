import unittest
from pathlib import Path
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.initial_bonuses import (
    starting_allowance_sickles,
)
from mage_maker.sections.development.models import (
    development_year_pages,
    ensure_adult_year_records,
    new_eminence_record,
    new_job_record,
    normalize_development_plan,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.school_years import (
    ensure_school_year_records,
)
from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_SOURCE_STARTING_ALLOWANCE,
    ledger_balance_sickles,
    new_manual_calendar_ledger_entry,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.organizations.controller import (
    ORGANIZATION_EVENT_FOUNDING,
    OrganizationController,
    new_organization_event,
    normalize_organization_events,
)


class FirstChoiceRandomizer:
    def random(self):
        return 0.0

    def choice(self, values):
        return list(values)[0]


class EmptyOrganizationDatabase:
    def list_records(self, collection_name):
        return []


def school_year_record(year_number):
    return {
        "year": year_number,
        "school": "Hogwarts",
        "ability": "Power",
        "skills": ["Charms", "Defense"],
        "assigned_books": [],
        "books": [],
        "eminence": [],
    }


class LedgerCalendarTests(unittest.TestCase):
    def test_starting_allowance_uses_wealth_times_generosity_galleons(self):
        amount_sickles = starting_allowance_sickles(
            {
                "mode": "Override",
                "wealth": 2,
                "generosity": 3,
                "permissiveness": 4,
            }
        )

        self.assertEqual(6 * 17, amount_sickles)

    def test_four_school_pages_create_four_calendar_ledger_years(self):
        school_records = [
            school_year_record(year_number)
            for year_number in range(1, 5)
        ]
        entries = reconcile_development_ledger_entries(
            [],
            school_records,
            [],
            monthly_allowance_sickles=6,
            starting_allowance_sickles=102,
            academic_start_year=1992,
        )

        self.assertEqual(48, len(entries))
        self.assertEqual(
            [1992, 1993, 1994, 1995, 1996],
            sorted({entry["calendar_year"] for entry in entries}),
        )
        self.assertEqual(
            LEDGER_SOURCE_STARTING_ALLOWANCE,
            entries[0]["automatic_source"],
        )
        self.assertEqual("starting allowance", entries[0]["item"])
        self.assertEqual(7, entries[0]["month"])
        self.assertEqual(102 + (47 * 6), ledger_balance_sickles(entries))

    def test_current_balance_subtracts_purchases(self):
        entries = reconcile_development_ledger_entries(
            [],
            [school_year_record(1)],
            [],
            monthly_allowance_sickles=2,
            starting_allowance_sickles=34,
            academic_start_year=1992,
        )
        purchase = new_manual_calendar_ledger_entry(
            1992,
            "March",
            "Ink",
            5,
            LEDGER_KIND_BOUGHT,
            school_year=1,
        )

        self.assertEqual(
            34 + 22 - 5,
            ledger_balance_sickles([*entries, purchase]),
        )

    def test_adult_manual_entries_follow_their_development_page(self):
        adult_records = ensure_adult_year_records([], 1)
        manual_entry = new_manual_calendar_ledger_entry(
            1999,
            "April",
            "Salary",
            20,
            "earned",
            adult_year=1,
        )
        entries = reconcile_development_ledger_entries(
            [manual_entry],
            [school_year_record(year) for year in range(1, 8)],
            adult_records,
            monthly_allowance_sickles=0,
            starting_allowance_sickles=0,
            academic_start_year=1993,
        )
        retained_manual = next(
            entry
            for entry in entries
            if not entry["automatic_source"]
        )

        self.assertEqual(1, retained_manual["adult_year"])
        self.assertEqual(2001, retained_manual["calendar_year"])


class DevelopmentYearRecordTests(unittest.TestCase):
    def test_intentional_books_are_unique_across_school_years(self):
        books = [
            {
                "record_id": f"book-{index}",
                "name": f"Book {index}",
                "categories": ["Charms"],
            }
            for index in range(1, 7)
        ]
        records = ensure_school_year_records(
            [],
            2,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 1,
            },
            books,
            [],
            [],
            FirstChoiceRandomizer(),
            school_name="Hogwarts",
            assigned_books_by_year={
                1: [books[0]],
                2: [books[1]],
            },
        )
        year_one_ids = {
            book["record_id"]
            for book in records[0]["books"]
        }
        year_two_ids = {
            book["record_id"]
            for book in records[1]["books"]
        }

        self.assertIn("book-2", year_one_ids)
        self.assertTrue(year_one_ids.isdisjoint(year_two_ids))
        self.assertNotIn("book-1", year_one_ids)
        self.assertNotIn("book-1", year_two_ids)
        self.assertNotIn("book-2", year_two_ids)

    def test_adult_page_uses_calendar_year_and_age_range(self):
        plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "school_started": True,
                "academic_years_advanced": 7,
                "school_years": [
                    school_year_record(year)
                    for year in range(1, 8)
                ],
                "adult_years": ensure_adult_year_records([], 1),
            }
        )
        pages = development_year_pages(
            plan,
            academic_start_year=1992,
            birth_year=1981,
        )

        self.assertEqual(8, len(pages))
        self.assertEqual(1999, pages[-1]["calendar_year"])
        self.assertEqual((17, 18), pages[-1]["age_range"])

    def test_late_birthdays_use_age_at_the_school_year_start(self):
        plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "school_started": True,
                "academic_years_advanced": 7,
                "school_years": [
                    school_year_record(year)
                    for year in range(1, 8)
                ],
                "adult_years": ensure_adult_year_records([], 1),
            }
        )
        pages = development_year_pages(
            plan,
            academic_start_year=1993,
            birth_year=1981,
            birth_month=10,
            birth_day=3,
        )

        self.assertEqual(2000, pages[-1]["calendar_year"])
        self.assertEqual((18, 19), pages[-1]["age_range"])

    def test_each_eminence_record_is_one_point(self):
        record = new_eminence_record(
            "",
            "Completed a difficult expedition.",
            "Creatures",
        )

        self.assertEqual("Eminence earned", record["title"])
        self.assertEqual(1, record["points"])

    def test_job_records_store_organization_salary_and_start_date(self):
        record = new_job_record(
            "org-1",
            "Ministry of Magic",
            "Auror",
            "40 Galleons monthly",
            1999,
            9,
            1,
        )

        self.assertEqual("org-1", record["organization_id"])
        self.assertEqual("Auror", record["title"])
        self.assertEqual(
            {
                "galleons": 40,
                "sickles": 0,
                "knuts": 0,
                "period": "month",
            },
            record["salary"],
        )
        self.assertEqual((1999, 9, 1), (
            record["start_year"],
            record["start_month"],
            record["start_day"],
        ))

    def test_right_arrow_from_initial_values_starts_school(self):
        view = object.__new__(DevelopmentView)
        view.active_development_page_index = 0
        view.school_started = False
        view.academic_years_advanced = 0
        view.development_page_count = Mock(return_value=1)
        view.can_add_next_development_page = Mock(
            return_value=True
        )
        view.advance_one_year = Mock()
        view.add_next_adult_year = Mock()

        DevelopmentView.show_next_development_page(view)

        view.advance_one_year.assert_called_once_with()
        view.add_next_adult_year.assert_not_called()

    def test_right_arrow_after_year_seven_adds_an_adult_page(self):
        view = object.__new__(DevelopmentView)
        view.active_development_page_index = 7
        view.school_started = True
        view.academic_years_advanced = 6
        view.development_page_count = Mock(return_value=8)
        view.can_add_next_development_page = Mock(
            return_value=True
        )
        view.advance_one_year = Mock()
        view.add_next_adult_year = Mock()

        DevelopmentView.show_next_development_page(view)

        self.assertEqual(7, view.academic_years_advanced)
        view.add_next_adult_year.assert_called_once_with()

    def test_advance_after_graduation_creates_sequential_adult_years(self):
        view = object.__new__(DevelopmentView)
        view.academic_years_advanced = 7
        view.adult_year_records = []
        view.development_plan = {}
        view.ensure_school_year_record_count = Mock()
        view.update_school_progress_controls = Mock()
        view.notify_change = Mock()

        DevelopmentView.add_next_adult_year(view)
        DevelopmentView.add_next_adult_year(view)

        self.assertEqual(
            [1, 2],
            [
                record["adult_year"]
                for record in view.adult_year_records
            ],
        )
        self.assertEqual(
            view.adult_year_records,
            view.development_plan["adult_years"],
        )
        self.assertEqual(
            2,
            view.update_school_progress_controls.call_count,
        )


class OrganizationEventTests(unittest.TestCase):
    def test_founding_is_always_the_first_organization_event(self):
        events = normalize_organization_events(
            [
                new_organization_event("Expansion", 2001),
                {
                    "event_type": ORGANIZATION_EVENT_FOUNDING,
                    "title": "Something else",
                    "year": 1980,
                },
            ]
        )

        self.assertEqual(
            ORGANIZATION_EVENT_FOUNDING,
            events[0]["event_type"],
        )
        self.assertEqual("Founding", events[0]["title"])
        self.assertEqual(1980, events[0]["year"])

    def test_organization_validation_requires_a_founding_year(self):
        controller = OrganizationController(
            EmptyOrganizationDatabase(),
            lambda: [],
        )

        with self.assertRaisesRegex(ValueError, "founding year"):
            controller.validate_organization(
                controller.normalize_organization(
                    {
                        "name": "The Order",
                        "organization_type": "Non-profit",
                        "events": [],
                    }
                )
            )

    def test_schema_nineteen_adds_organization_event_lists(self):
        database = JsonDatabase(Path("/tmp/not-used.json"))
        database_data = {
            "_database": {
                "schema_version": 18,
                "database_version": "0.18.0",
            },
            "people": [],
            "organizations": [
                {
                    "record_id": "org-1",
                    "name": "The Order",
                }
            ],
        }

        self.assertTrue(database.migrate_database(database_data))
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        self.assertEqual(
            ORGANIZATION_EVENT_FOUNDING,
            database_data["organizations"][0]["events"][0][
                "event_type"
            ],
        )


if __name__ == "__main__":
    unittest.main()
