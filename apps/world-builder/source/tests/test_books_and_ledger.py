import inspect
import unittest

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.models import (
    normalize_school_year_record,
)
from mage_maker.sections.development.school_years import (
    assigned_school_books_by_year,
    ensure_school_year_records,
)
from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_SOURCE_ALLOWANCE,
    LEDGER_SOURCE_SCHOOL_BOOK,
    ledger_amount_text,
    new_manual_ledger_entry,
    reconcile_school_ledger_entries,
)
from mage_maker.sections.ledger.page import LedgerView
from mage_maker.sections.profile.books import (
    BooksView,
    school_year_reading_entries,
)
from mage_maker.sections.profile.page import PersonForm


class FakeRandomizer:
    def random(self):
        return 0.0

    def choice(self, options):
        return list(options)[0]


class SchoolBookReadingTests(unittest.TestCase):
    def setUp(self):
        self.books = [
            {
                "record_id": "book-one",
                "name": "First-Year Defense",
                "author": "A. Author",
            },
            {
                "record_id": "book-two",
                "name": "Second-Year Charms",
                "author": "B. Author",
            },
            {
                "record_id": "book-three",
                "name": "Independent History",
                "author": "C. Author",
            },
            {
                "record_id": "book-four",
                "name": "Independent Flying",
                "author": "D. Author",
            },
        ]
        self.school = {
            "name": "Hogwarts",
            "course_books": [
                {
                    "year": 1,
                    "course": "Defense",
                    "record_id": "book-one",
                    "name": "First-Year Defense",
                },
                {
                    "year": 1,
                    "course": "History",
                    "record_id": "book-one",
                    "name": "First-Year Defense",
                },
                {
                    "year": 2,
                    "course": "Charms",
                    "record_id": "book-two",
                    "name": "Second-Year Charms",
                },
            ],
        }

    def test_curriculum_assignments_keep_every_unique_book(self):
        assignments = assigned_school_books_by_year(
            "Hogwarts",
            [self.school],
            self.books,
        )

        self.assertEqual(
            ["book-one"],
            [book["record_id"] for book in assignments[1]],
        )
        self.assertEqual(
            "A. Author",
            assignments[1][0]["author"],
        )

    def test_assigned_books_are_not_limited_to_two(self):
        record = normalize_school_year_record(
            {
                "year": 1,
                "school": "Hogwarts",
                "ability": "Power",
                "skills": ["Charms", "Defense"],
                "assigned_books": self.books,
                "books": self.books,
            }
        )

        self.assertEqual(4, len(record["assigned_books"]))
        self.assertEqual(2, len(record["books"]))

    def test_intentional_study_excludes_current_and_earlier_assignments(self):
        assignments = assigned_school_books_by_year(
            "Hogwarts",
            [self.school],
            self.books,
        )
        records = ensure_school_year_records(
            [],
            2,
            {
                "schema": "Scattershot",
                "school_started": True,
                "academic_years_advanced": 1,
            },
            self.books,
            [],
            [],
            FakeRandomizer(),
            school_name="Hogwarts",
            assigned_books_by_year=assignments,
        )

        self.assertEqual(
            ["book-one"],
            [
                book["record_id"]
                for book in records[0]["assigned_books"]
            ],
        )
        self.assertEqual(
            ["book-two", "book-three"],
            [
                book["record_id"]
                for book in records[0]["books"]
            ],
        )
        self.assertEqual(
            ["book-four"],
            [
                book["record_id"]
                for book in records[1]["books"]
            ],
        )

    def test_books_profile_labels_every_source(self):
        entries = school_year_reading_entries(
            [
                {
                    "year": 1,
                    "school": "Hogwarts",
                    "ability": "Power",
                    "skills": ["Charms", "Defense"],
                    "assigned_books": [self.books[0]],
                    "books": [self.books[1], self.books[2]],
                }
            ]
        )

        self.assertEqual(
            [
                "Assigned in Year 1",
                "Intentional study in Year 1",
                "Intentional study in Year 1",
            ],
            [entry["source"] for entry in entries],
        )

    def test_books_page_is_read_only_and_has_no_add_action(self):
        source = inspect.getsource(BooksView)

        self.assertIn("This list is read-only", source)
        self.assertNotIn("Add book", source)
        self.assertNotIn("BookSelectionDialog", source)


class LedgerModelTests(unittest.TestCase):
    def setUp(self):
        self.year_one = {
            "year": 1,
            "school": "Hogwarts",
            "ability": "Power",
            "skills": ["Charms", "Defense"],
            "assigned_books": [
                {
                    "record_id": "book-one",
                    "name": "First-Year Defense",
                    "author": "A. Author",
                },
                {
                    "record_id": "book-two",
                    "name": "First-Year Charms",
                    "author": "B. Author",
                },
            ],
            "books": [],
        }

    def test_first_year_allowances_begin_in_august(self):
        entries = reconcile_school_ledger_entries(
            [],
            [self.year_one],
            36,
            1991,
        )
        allowance_entries = [
            entry
            for entry in entries
            if entry["automatic_source"] == LEDGER_SOURCE_ALLOWANCE
        ]
        school_book_entries = [
            entry
            for entry in entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_SCHOOL_BOOK
        ]

        self.assertEqual(11, len(allowance_entries))
        self.assertEqual(
            [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6],
            [entry["month"] for entry in allowance_entries],
        )
        self.assertTrue(
            all(
                entry["amount_sickles"] == 36
                for entry in allowance_entries
            )
        )
        self.assertEqual(2, len(school_book_entries))
        self.assertTrue(
            all(
                entry["amount_sickles"] == 0
                and entry["note"] == "purchased by caregivers"
                and entry["month"] == 7
                and 20 <= entry["day"] <= 31
                for entry in school_book_entries
            )
        )

    def test_previous_allowances_remain_historical(self):
        original_entries = reconcile_school_ledger_entries(
            [],
            [self.year_one],
            36,
            1991,
        )
        reconciled_entries = reconcile_school_ledger_entries(
            original_entries,
            [self.year_one],
            50,
            1991,
        )

        self.assertEqual(
            {36},
            {
                entry["amount_sickles"]
                for entry in reconciled_entries
                if entry["automatic_source"]
                == LEDGER_SOURCE_ALLOWANCE
            },
        )

    def test_manual_line_items_are_kept_with_their_year(self):
        manual_entry = new_manual_ledger_entry(
            1,
            "October",
            "Second-hand broom",
            21,
            LEDGER_KIND_BOUGHT,
            "Used for Flying practice",
            1991,
        )
        entries = reconcile_school_ledger_entries(
            [manual_entry],
            [self.year_one],
            36,
            1991,
        )

        stored_entry = next(
            entry
            for entry in entries
            if entry["entry_id"] == manual_entry["entry_id"]
        )
        self.assertEqual(10, stored_entry["month"])
        self.assertEqual(
            "Second-hand broom",
            stored_entry["item"],
        )
        self.assertEqual(
            "−1 Galleon and 4 sickles",
            ledger_amount_text(stored_entry),
        )

    def test_removing_a_school_year_removes_its_ledger_rows(self):
        entries = reconcile_school_ledger_entries(
            [],
            [self.year_one],
            36,
            1991,
        )
        entries = reconcile_school_ledger_entries(
            entries,
            [],
            36,
            1991,
        )

        self.assertEqual([], entries)

    def test_invalid_school_year_records_are_ignored_safely(self):
        entries = reconcile_school_ledger_entries(
            [],
            [{"year": "not-a-year"}, None],
            36,
            1991,
        )

        self.assertEqual([], entries)

    def test_ledger_page_uses_year_arrows_and_dialog_addition(self):
        source = inspect.getsource(LedgerView)

        self.assertIn('text="<"', source)
        self.assertIn('text=">"', source)
        self.assertIn('text="Add line item"', source)
        self.assertIn(
            "LedgerEntryDialog",
            source,
        )


class BooksLedgerPersistenceTests(unittest.TestCase):
    def test_version_seventeen_adds_ledger_and_book_sources(self):
        database_data = {
            "_database": {
                "schema_version": 17,
                "database_version": "0.17.0",
            },
            "people": [
                {
                    "development_plan": {
                        "schema": "Scattershot",
                        "school_started": True,
                        "academic_years_advanced": 0,
                        "school_years": [
                            {
                                "year": 1,
                                "ability": "Power",
                                "skills": ["Charms", "Defense"],
                                "books": [],
                            }
                        ],
                    }
                }
            ],
        }
        database = JsonDatabase("unused.json")

        self.assertTrue(database.migrate_database(database_data))
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        plan = database_data["people"][0]["development_plan"]
        self.assertEqual([], plan["ledger_entries"])
        self.assertEqual(
            [],
            plan["school_years"][0]["assigned_books"],
        )
        self.assertEqual(
            "",
            plan["school_years"][0]["school"],
        )

    def test_profile_navigation_includes_books_and_ledger(self):
        source = inspect.getsource(PersonForm)

        self.assertIn('("books", "Books"', source)
        self.assertIn('("ledger", "Ledger"', source)


if __name__ == "__main__":
    unittest.main()
