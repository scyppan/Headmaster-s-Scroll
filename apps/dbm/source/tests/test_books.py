import tempfile
import unittest
from collections import Counter
from inspect import getsource, signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.books.books.controller import BookController
from sections.books.books.link_editor import BookLinkEditor
from sections.books.books.page import BooksPage
from sections.books.books.record_form import BookForm
from sections.books.books.record_list import BookList
from sections.books.bookshelves.book_picker import (
    BOOK_SEARCH_SCOPES,
    BookPicker,
)
from sections.books.bookshelves.books_editor import BookshelfBooksEditor
from sections.books.bookshelves.controller import BookshelfController
from sections.books.bookshelves.page import BookshelvesPage
from sections.books.bookshelves.record_form import BookshelfForm
from sections.books.bookshelves.record_list import BookshelfList


class BookTests(unittest.TestCase):
    def test_page_and_form_accept_database_from_content_host(self):
        self.assertEqual(
            tuple(signature(BooksPage.__init__).parameters),
            ("self", "parent", "database"),
        )
        self.assertEqual(
            tuple(signature(BookForm.__init__).parameters),
            ("self", "parent", "database", "change_command"),
        )

    def test_book_export_is_fully_preserved_in_linked_schema(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("books")
        required_fields = {
            "record_id",
            "name",
            "author",
            "categories",
            "description",
            "spells",
            "proficiencies",
            "potions",
            "dbnotes",
            "last_updated",
        }
        records_by_id = {record["record_id"]: record for record in records}
        imported_records = [
            record
            for record in records
            if record["record_id"].startswith("book_")
        ]
        imported_records_by_id = {
            record["record_id"]: record for record in imported_records
        }

        self.assertEqual(len(imported_records), 608)
        self.assertEqual(len(imported_records_by_id), 608)
        self.assertEqual(len(records), len(records_by_id))
        self.assertTrue(all(set(record) == required_fields for record in records))
        self.assertEqual(
            sum(len(record["spells"]) for record in imported_records),
            288,
        )
        self.assertEqual(
            sum(
                len(record["proficiencies"])
                for record in imported_records
            ),
            122,
        )
        self.assertEqual(
            sum(len(record["potions"]) for record in imported_records),
            109,
        )
        self.assertEqual(
            Counter(
                category
                for record in imported_records
                for category in record["categories"]
            ),
            Counter(
                {
                    "Charms": 74,
                    "Defense": 59,
                    "Potions": 48,
                    "Transfiguration": 45,
                    "History": 40,
                    "Dark Arts": 33,
                    "Creatures": 27,
                    "Runes": 26,
                    "Divination": 26,
                    "Arithmancy": 24,
                    "Herbology": 23,
                    "Artificing": 16,
                    "Astronomy": 15,
                    "Alchemy": 14,
                    "Muggles": 13,
                    "Nganga": 1,
                    "Mbudye": 1,
                    "Ubunganga": 1,
                }
            ),
        )
        self.assertEqual(
            records_by_id["book_1098"]["name"],
            "Not Playing with a Full Deck",
        )
        self.assertEqual(
            records_by_id["book_1098"]["spells"][:3],
            [
                {
                    "record_id": "spell_19078",
                    "name": "Obliviate",
                },
                {
                    "record_id": "spell_19080",
                    "name": "Spell of Deception",
                },
                {
                    "record_id": "spell_19079",
                    "name": "False Memory",
                },
            ],
        )
        self.assertTrue(all(record["dbnotes"] == "" for record in records))
        self.assertTrue(
            all("<" not in record["description"] for record in records)
        )

    def test_every_book_link_resolves_by_record_id(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        records = database.get_collection("books")
        record_ids_by_link_field = {
            "spells": {
                record["record_id"]
                for record in database.get_collection("spells")
            },
            "proficiencies": {
                record["record_id"]
                for record in database.get_collection("proficiencies")
            },
            "potions": {
                record["record_id"]
                for record in database.get_collection("potions")
            },
        }

        for record in records:
            for link_field, valid_record_ids in record_ids_by_link_field.items():
                self.assertTrue(
                    all(
                        reference["record_id"] in valid_record_ids
                        for reference in record[link_field]
                    )
                )

        astronomy_book = next(
            record
            for record in records
            if record["name"] == "A Guide to Celestial Phenomena"
        )
        welsh_bardic_reference = next(
            reference
            for reference in astronomy_book["proficiencies"]
            if reference["name"] == "Welsh Bardic Charms"
        )
        self.assertEqual(
            welsh_bardic_reference["record_id"],
            "proficiency_22640",
        )

    def test_controller_crud_supports_categories_and_ordered_links(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "books": [],
  "spells": [{"record_id": "spell_1", "name": "Test Spell"}],
  "proficiencies": [{"record_id": "proficiency_1", "name": "Test Proficiency"}],
  "potions": [{"record_id": "potion_1", "name": "Test Potion"}]
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = BookController(database)
            created_record = controller.create_record(
                {
                    "name": "Test Book",
                    "author": "Test Author",
                    "categories": ["Charms", "History"],
                    "spells": [
                        {"record_id": "spell_1", "name": "Old Name"}
                    ],
                    "proficiencies": [
                        {
                            "record_id": "proficiency_1",
                            "name": "Test Proficiency",
                        },
                        {
                            "record_id": "proficiency_1",
                            "name": "Test Proficiency",
                        },
                    ],
                    "potions": [
                        {"record_id": "potion_1", "name": "Test Potion"}
                    ],
                }
            )

            self.assertEqual(created_record["spells"][0]["name"], "Test Spell")
            self.assertEqual(len(created_record["proficiencies"]), 2)
            controller.update_record(
                created_record["record_id"],
                {"description": "Updated description"},
            )
            self.assertEqual(
                controller.get_record(created_record["record_id"])[
                    "description"
                ],
                "Updated description",
            )
            controller.delete_record(created_record["record_id"])
            self.assertIsNone(controller.get_record(created_record["record_id"]))

    def test_invalid_book_values_and_links_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "books": [],
  "spells": [],
  "proficiencies": [],
  "potions": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = BookController(database)

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record({})

            with self.assertRaisesRegex(ValueError, "Duplicate book category"):
                controller.create_record(
                    {
                        "name": "Duplicate Category",
                        "categories": ["Charms", "charms"],
                    }
                )

            with self.assertRaisesRegex(ValueError, "Unknown linked"):
                controller.create_record(
                    {
                        "name": "Missing Spell",
                        "spells": [
                            {
                                "record_id": "spell_missing",
                                "name": "Missing Spell",
                            }
                        ],
                    }
                )

    def test_book_list_is_multiline_and_searches_linked_content(self):
        record = {
            "name": "A Test Book",
            "author": "A. Writer",
            "categories": ["Charms", "History"],
            "description": "A useful description",
            "spells": [{"name": "Hidden Spell"}],
            "proficiencies": [{"name": "Hidden Proficiency"}],
            "potions": [{"name": "Hidden Potion"}],
        }

        self.assertEqual(
            BookList.build_display_text(record),
            "A Test Book\nA. Writer • Charms, History",
        )
        search_text = BookList.build_search_text(record)
        self.assertIn("hidden spell", search_text)
        self.assertIn("hidden proficiency", search_text)
        self.assertIn("hidden potion", search_text)

    def test_form_has_fixed_linked_record_views_and_categories(self):
        form_source = getsource(BookForm)
        editor_source = getsource(BookLinkEditor)

        self.assertIn('collection_name="spells"', form_source)
        self.assertIn('collection_name="proficiencies"', form_source)
        self.assertIn('collection_name="potions"', form_source)
        self.assertIn('text="Categories"', form_source)
        self.assertIn("AssociationPicker", editor_source)
        self.assertIn("Move Up", editor_source)

    def test_bookshelf_page_and_form_accept_database_from_content_host(self):
        self.assertEqual(
            tuple(signature(BookshelvesPage.__init__).parameters),
            ("self", "parent", "database"),
        )
        self.assertEqual(
            tuple(signature(BookshelfForm.__init__).parameters),
            ("self", "parent", "database", "change_command"),
        )

    def test_bookshelves_start_empty_without_changing_the_book_catalog(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()

        imported_records = [
            record
            for record in database.get_collection("books")
            if record["record_id"].startswith("book_")
        ]

        self.assertEqual(len(imported_records), 608)
        self.assertEqual(database.get_collection("bookshelves"), [])
        self.assertFalse(database.has_container("people"))
        self.assertTrue(database.has_container("schools"))

    def test_bookshelf_controller_crud_preserves_ordered_book_links(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "books": [
    {"record_id": "book_1", "name": "First Book"},
    {"record_id": "book_2", "name": "Second Book"}
  ],
  "bookshelves": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = BookshelfController(database)
            created_record = controller.create_record(
                {
                    "name": "Restricted Shelf",
                    "description": "Books requiring supervision.",
                    "tags": ["Restricted", "Advanced"],
                    "books": [
                        {"record_id": "book_2", "name": "Old Name"},
                        {"record_id": "book_1", "name": "First Book"},
                    ],
                }
            )

            self.assertEqual(
                created_record["books"],
                [
                    {"record_id": "book_2", "name": "Second Book"},
                    {"record_id": "book_1", "name": "First Book"},
                ],
            )
            controller.update_record(
                created_record["record_id"],
                {"description": "Updated description"},
            )
            self.assertEqual(
                controller.get_record(created_record["record_id"])[
                    "description"
                ],
                "Updated description",
            )
            controller.delete_record(created_record["record_id"])
            self.assertIsNone(
                controller.get_record(created_record["record_id"])
            )

    def test_bookshelf_controller_rejects_duplicate_and_unknown_books(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "books": [{"record_id": "book_1", "name": "First Book"}],
  "bookshelves": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = BookshelfController(database)

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record({})

            with self.assertRaisesRegex(ValueError, "Duplicate bookshelf tag"):
                controller.create_record(
                    {
                        "name": "Duplicate Tags",
                        "tags": ["Study", "study"],
                    }
                )

            with self.assertRaisesRegex(ValueError, "Duplicate bookshelf book"):
                controller.create_record(
                    {
                        "name": "Duplicate Books",
                        "books": [
                            {"record_id": "book_1", "name": "First Book"},
                            {"record_id": "book_1", "name": "First Book"},
                        ],
                    }
                )

            with self.assertRaisesRegex(ValueError, "Unknown book"):
                controller.create_record(
                    {
                        "name": "Missing Book",
                        "books": [
                            {"record_id": "book_missing", "name": "Missing"}
                        ],
                    }
                )

    def test_bookshelf_display_and_search_include_shelf_contents(self):
        record = {
            "name": "Charms Shelf",
            "description": "Core reading",
            "tags": ["Beginner", "Classroom"],
            "books": [
                {"record_id": "book_1", "name": "Standard Book of Spells"}
            ],
        }

        self.assertEqual(
            BookshelfList.build_display_text(record),
            "Charms Shelf\n1 book • Beginner, Classroom",
        )
        search_text = BookshelfList.build_search_text(record)
        self.assertIn("core reading", search_text)
        self.assertIn("standard book of spells", search_text)

    def test_book_picker_supports_every_requested_search_scope(self):
        entry = BookPicker.build_entry(
            {
                "record_id": "book_1",
                "name": "Advanced Potion-Making",
                "author": "Libatius Borage",
                "categories": ["Potions"],
                "description": "An advanced textbook.",
                "spells": [{"name": "Stirring Charm"}],
                "proficiencies": [{"name": "Careful Heating"}],
                "potions": [{"name": "Felix Felicis"}],
            }
        )

        self.assertIsNotNone(
            BookPicker.rank_entry(entry, "advanced potion", "title")
        )
        self.assertIsNotNone(
            BookPicker.rank_entry(entry, "potions", "categories")
        )
        self.assertIsNotNone(
            BookPicker.rank_entry(entry, "stirring charm", "spells")
        )
        self.assertIsNotNone(
            BookPicker.rank_entry(
                entry,
                "careful heating",
                "proficiencies",
            )
        )
        self.assertIsNotNone(
            BookPicker.rank_entry(entry, "felix felicis", "potions")
        )
        self.assertIsNone(
            BookPicker.rank_entry(entry, "felix felicis", "spells")
        )

    def test_bookshelf_form_uses_tags_and_searchable_book_editor(self):
        form_source = getsource(BookshelfForm)
        editor_source = getsource(BookshelfBooksEditor)
        picker_source = getsource(BookPicker)

        self.assertIn('"Bookshelf Name"', form_source)
        self.assertIn("TagEditor", form_source)
        self.assertIn("BookshelfBooksEditor", form_source)
        self.assertIn('text="Search & Add Books"', editor_source)
        self.assertIn('selectmode="extended"', picker_source)
        self.assertIn(
            ("Proficiencies", "proficiencies", 116),
            BOOK_SEARCH_SCOPES,
        )


if __name__ == "__main__":
    unittest.main()
