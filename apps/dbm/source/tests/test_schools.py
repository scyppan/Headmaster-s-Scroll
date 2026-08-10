import tempfile
import unittest
from inspect import getsource, signature
from pathlib import Path

from database import JsonDatabase
from database.paths import DATABASE_PATH
from sections.schools.constants import SCHOOL_COURSES
from sections.schools.controller import SchoolController
from sections.schools.course_books_editor import CourseBooksEditor
from sections.schools.curriculum_editor import CurriculumEditor
from sections.schools.page import SchoolsPage
from sections.schools.record_form import SchoolForm
from sections.schools.record_list import SchoolList


class SchoolTests(unittest.TestCase):
    def test_page_and_form_accept_database_from_content_host(self):
        self.assertEqual(
            tuple(signature(SchoolsPage.__init__).parameters),
            ("self", "parent", "database"),
        )
        self.assertEqual(
            tuple(signature(SchoolForm.__init__).parameters),
            (
                "self",
                "parent",
                "database",
                "change_command",
                "book_navigation_command",
            ),
        )

    def test_school_form_retains_the_book_navigation_callback(self):
        initializer_source = getsource(SchoolForm.__init__)
        builder_source = getsource(SchoolForm.build_course_books_view)

        self.assertIn(
            "self.book_navigation_command = book_navigation_command",
            initializer_source,
        )
        self.assertIn(
            "book_navigation_command=self.book_navigation_command",
            builder_source,
        )

    def test_school_export_imports_only_the_25_requested_records(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        schools = database.get_collection("schools")
        school_names = {school["name"] for school in schools}
        excluded_names = {
            "Wizarding Academy for the Dramatic Arts",
            "Charms School",
            "Academy of Broom Flying",
            "Salem Witches Institute",
        }
        required_fields = {
            "record_id",
            "name",
            "location",
            "canon",
            "wandless",
            "description",
            "areas_served",
            "philosophy_and_practice",
            "architecture",
            "curriculum",
            "course_books",
            "dbnotes",
            "last_updated",
        }

        self.assertEqual(len(schools), 25)
        self.assertTrue(excluded_names.isdisjoint(school_names))
        self.assertEqual(len(school_names), 25)
        self.assertTrue(all(set(school) == required_fields for school in schools))
        self.assertTrue(all(len(school["curriculum"]) == 7 for school in schools))
        self.assertEqual(
            sum(len(school["course_books"]) for school in schools),
            1232,
        )
        self.assertTrue(
            all("<" not in school["description"] for school in schools)
        )

    def test_school_curriculum_and_book_links_preserve_source_values(self):
        database = JsonDatabase(DATABASE_PATH)
        database.load()
        schools_by_name = {
            school["name"]: school
            for school in database.get_collection("schools")
        }
        books_by_id = {
            book["record_id"]: book
            for book in database.get_collection("books")
        }
        hogwarts = schools_by_name["Hogwarts"]
        dobastrias = schools_by_name["Dobastrias"]

        self.assertEqual(hogwarts["location"], "Scottish Highlands")
        self.assertTrue(hogwarts["canon"])
        self.assertFalse(hogwarts["wandless"])
        self.assertEqual(
            hogwarts["curriculum"][0],
            {
                "year": 1,
                "core": [
                    "Charms",
                    "Transfiguration",
                    "Defense",
                    "Potions",
                    "Herbology",
                    "Flying",
                    "History",
                    "Astronomy",
                ],
                "electives": [],
                "elective_limit": 0,
            },
        )
        self.assertEqual(
            hogwarts["course_books"][0],
            {
                "year": 1,
                "course": "Potions",
                "record_id": "book_1355",
                "name": "Magical Drafts and Potions",
            },
        )
        self.assertEqual(len(hogwarts["course_books"]), 89)
        self.assertEqual(len(dobastrias["course_books"]), 48)

        for school in schools_by_name.values():
            for course_book in school["course_books"]:
                self.assertIn(course_book["year"], range(1, 8))
                self.assertIn(course_book["course"], SCHOOL_COURSES)
                year_record = school["curriculum"][
                    course_book["year"] - 1
                ]
                selected_courses = set(year_record["core"])
                selected_courses.update(year_record["electives"])
                self.assertIn(course_book["course"], selected_courses)
                linked_book = books_by_id[course_book["record_id"]]
                self.assertEqual(course_book["name"], linked_book["name"])

        self.assertIn(
            "Creatures",
            schools_by_name["Ilvermorny"]["curriculum"][5]["electives"],
        )
        self.assertIn(
            "Creatures",
            schools_by_name["Ilvermorny"]["curriculum"][6]["electives"],
        )

    def test_controller_crud_supports_curriculum_and_repeated_course_books(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "schools": [],
  "books": [{"record_id": "book_1", "name": "Test Book"}]
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = SchoolController(database)
            curriculum = controller.empty_curriculum()
            curriculum[0]["core"] = ["Charms", "History"]
            curriculum[0]["electives"] = ["Alchemy"]
            curriculum[0]["elective_limit"] = 1
            created_record = controller.create_record(
                {
                    "name": "Test School",
                    "location": "Test Location",
                    "canon": "Yes",
                    "wandless": "No",
                    "curriculum": curriculum,
                    "course_books": [
                        {
                            "year": 1,
                            "course": "Charms",
                            "record_id": "book_1",
                            "name": "Old Name",
                        },
                        {
                            "year": 1,
                            "course": "Charms",
                            "record_id": "book_1",
                            "name": "Old Name",
                        },
                    ],
                }
            )

            self.assertTrue(created_record["canon"])
            self.assertFalse(created_record["wandless"])
            self.assertEqual(len(created_record["course_books"]), 2)
            self.assertTrue(
                all(
                    course_book["name"] == "Test Book"
                    for course_book in created_record["course_books"]
                )
            )
            controller.update_record(
                created_record["record_id"],
                {"location": "Updated Location"},
            )
            self.assertEqual(
                controller.get_record(created_record["record_id"])["location"],
                "Updated Location",
            )
            controller.delete_record(created_record["record_id"])
            self.assertIsNone(controller.get_record(created_record["record_id"]))

    def test_invalid_school_values_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "test_database.json"
            database_path.write_text(
                """
{
  "_database": {"schema_version": 1},
  "schools": [],
  "books": []
}
""".strip(),
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = SchoolController(database)

            with self.assertRaisesRegex(ValueError, "must have a name"):
                controller.create_record({})

            bad_curriculum = controller.empty_curriculum()
            bad_curriculum[0]["core"] = ["Unknown Course"]

            with self.assertRaisesRegex(ValueError, "Unknown school course"):
                controller.create_record(
                    {
                        "name": "Bad Curriculum",
                        "curriculum": bad_curriculum,
                    }
                )

            book_curriculum = controller.empty_curriculum()
            book_curriculum[0]["core"] = ["Charms"]

            with self.assertRaisesRegex(ValueError, "Unknown school course book"):
                controller.create_record(
                    {
                        "name": "Bad Book",
                        "curriculum": book_curriculum,
                        "course_books": [
                            {
                                "year": 1,
                                "course": "Charms",
                                "record_id": "missing",
                                "name": "Missing Book",
                            }
                        ],
                    }
                )

            unchecked_curriculum = controller.empty_curriculum()

            with self.assertRaisesRegex(ValueError, "unchecked course"):
                controller.create_record(
                    {
                        "name": "Unchecked Course Book",
                        "curriculum": unchecked_curriculum,
                        "course_books": [
                            {
                                "year": 1,
                                "course": "Charms",
                                "record_id": "missing",
                                "name": "Missing Book",
                            }
                        ],
                    }
                )

    def test_school_form_has_three_focused_views(self):
        form_source = getsource(SchoolForm)
        curriculum_source = getsource(CurriculumEditor)
        course_books_source = getsource(CourseBooksEditor)

        self.assertIn('text="Overview"', form_source)
        self.assertIn('text="Curriculum"', form_source)
        self.assertIn('text="Course Books"', form_source)
        self.assertIn("range(1, 8)", curriculum_source)
        self.assertIn("course_checkbox = tk.Checkbutton", curriculum_source)
        self.assertIn("course_index // 3", curriculum_source)
        self.assertIn("course_index % 3", curriculum_source)
        self.assertNotIn("comma-separated", curriculum_source)
        self.assertIn("BookPicker", course_books_source)
        self.assertIn('text="+"', course_books_source)
        self.assertIn('value=book_name or "None"', course_books_source)
        self.assertIn("book_navigation_command", course_books_source)
        self.assertIn('cursor="hand2" if book_record_id else "arrow"', course_books_source)
        self.assertIn('partial(self.open_book, book_record_id)', course_books_source)
        self.assertIn(
            '"PRIMARY_DARK" if book_record_id else "TEXT_DISABLED"',
            course_books_source,
        )
        self.assertNotIn('"underline"', course_books_source)
        self.assertNotIn("subject_select", course_books_source)
        self.assertEqual(len(SCHOOL_COURSES), 18)

    def test_course_books_follow_checked_courses_for_each_year(self):
        editor = CourseBooksEditor.__new__(CourseBooksEditor)
        editor.curriculum = SchoolController.empty_curriculum()
        editor.curriculum[0]["core"] = ["Charms"]
        editor.curriculum[0]["electives"] = ["Potions"]
        editor.course_books = [
            {
                "year": 1,
                "course": "Charms",
                "record_id": "book_1",
                "name": "Charms Book",
            },
            {
                "year": 1,
                "course": "History",
                "record_id": "book_2",
                "name": "History Book",
            },
            {
                "year": 2,
                "course": "Charms",
                "record_id": "book_3",
                "name": "Second-Year Charms Book",
            },
        ]

        self.assertEqual(
            editor.get_selected_courses(1),
            ["Charms", "Potions"],
        )
        editor.prune_unchecked_course_books()

        self.assertEqual(
            editor.course_books,
            [
                {
                    "year": 1,
                    "course": "Charms",
                    "record_id": "book_1",
                    "name": "Charms Book",
                }
            ],
        )

    def test_school_list_uses_requested_two_line_display(self):
        display_text = SchoolList.build_display_text(
            {
                "record_id": "school_1",
                "name": "Hogwarts",
                "location": "Scottish Highlands",
            }
        )

        self.assertEqual(
            display_text,
            "Hogwarts\nScottish Highlands",
        )

    def test_school_search_text_includes_name_and_location(self):
        search_text = SchoolList.build_search_text(
            {
                "name": "Hogwarts",
                "location": "Scottish Highlands",
            }
        )

        self.assertIn("hogwarts", search_text)
        self.assertIn("scottish highlands", search_text)


if __name__ == "__main__":
    unittest.main()
