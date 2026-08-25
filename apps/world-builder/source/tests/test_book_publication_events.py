import unittest

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.books.models import (
    book_publication_event_id,
    publication_event_from_book,
    synchronize_book_publication_events,
)
from mage_maker.sections.events.types import (
    event_type_label,
    event_type_options,
)
from mage_maker.sections.events.models import normalize_world_event


def sample_book():
    return {
        "record_id": "book-one",
        "title": "A History of Useful Tests",
        "author_person_id": "author-one",
        "author_name": "Ada Author",
        "publication_date": "1899-09-01",
        "publication_location_id": "",
        "publication_location_name": "",
        "mass_printed": True,
        "description": "",
        "notes": "",
        "contents": [],
        "holdings": [],
    }


class BookPublicationEventTests(unittest.TestCase):
    def test_published_a_book_is_available_in_person_event_menu(self):
        self.assertIn(
            ("published_book", "Published a book"),
            event_type_options("person"),
        )

    def test_publication_event_links_book_author_and_date(self):
        event = publication_event_from_book(sample_book())

        self.assertEqual("Published a book", event_type_label(event))
        self.assertEqual("published_book", event["event_type"])
        self.assertEqual(["book-one"], event["book_ids"])
        self.assertEqual(["author-one"], event["person_ids"])
        self.assertEqual("1899-09-01", event["date"])

    def test_publication_event_does_not_require_a_book_link(self):
        event = normalize_world_event({
            "record_id": "publication-without-book",
            "event_type": "published_book",
            "title": "Published an unnamed manuscript",
            "date": "1899-09-01",
            "book_ids": [],
        })

        self.assertEqual([], event["book_ids"])

    def test_synchronization_resolves_an_existing_author_by_name(self):
        book = sample_book()
        book["author_person_id"] = ""
        data = {
            "people": [
                {"record_id": "author-one", "displayed_name": "Ada Author"}
            ],
            "books": [book],
            "events": [],
        }

        self.assertTrue(synchronize_book_publication_events(data))
        stored = data["books"][0]
        self.assertEqual("author-one", stored["author_person_id"])
        self.assertEqual(
            book_publication_event_id("book-one"),
            stored["publication_event_id"],
        )
        self.assertEqual(1, len(data["events"]))

    def test_schema_38_migrates_books_to_publication_events(self):
        data = {
            "_database": {
                "schema_version": 38,
                "database_version": "0.38.0",
            },
            "people": [],
            "books": [sample_book()],
            "events": [],
        }
        database = JsonDatabase("unused.json")

        self.assertTrue(database.migrate_database(data))
        self.assertEqual(40, data["_database"]["schema_version"])
        self.assertEqual("0.40.0", data["_database"]["database_version"])
        self.assertEqual(1, len(data["events"]))

    def test_schema_39_removes_only_derived_ledger_rows(self):
        data = {
            "_database": {
                "schema_version": 39,
                "database_version": "0.39.0",
            },
            "people": [{
                "record_id": "person-1",
                "development_plan": {
                    "ledger_entries": [
                        {
                            "entry_id": "derived-1",
                            "school_year": 1,
                            "month": 9,
                            "day": 1,
                            "item": "Allowance",
                            "kind": "earned",
                            "amount_sickles": 10,
                            "automatic_source": "monthly_allowance",
                        },
                        {
                            "entry_id": "purchase-1",
                            "school_year": 1,
                            "month": 9,
                            "day": 2,
                            "item": "Ink",
                            "kind": "bought",
                            "amount_sickles": 2,
                            "automatic_source": "",
                        },
                    ]
                },
            }],
            "books": [],
            "events": [],
        }

        database = JsonDatabase("unused.json")
        self.assertTrue(database.migrate_database(data))
        rows = data["people"][0]["development_plan"]["ledger_entries"]
        self.assertEqual(["purchase-1"], [row["entry_id"] for row in rows])


if __name__ == "__main__":
    unittest.main()
