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
        self.assertEqual(39, data["_database"]["schema_version"])
        self.assertEqual("0.39.0", data["_database"]["database_version"])
        self.assertEqual(1, len(data["events"]))


if __name__ == "__main__":
    unittest.main()
