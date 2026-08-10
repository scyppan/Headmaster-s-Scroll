import inspect
import unittest
from copy import deepcopy
from unittest.mock import patch

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.book_dialog import (
    BookSelectionDialog,
    book_search_text,
)
from mage_maker.sections.development.models import (
    normalize_development_plan,
    normalize_school_year_book,
    normalize_school_year_record,
    normalize_school_year_records,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.school_years import (
    book_linked_skill_sets,
    ensure_school_year_records,
    preferred_development_abilities,
    random_school_year_record,
    select_school_year_books,
    strategy_weighted_choice,
)


class FakeRandomizer:
    def __init__(self, random_values=None):
        self.random_values = list(random_values or [])

    def random(self):
        if self.random_values:
            return self.random_values.pop(0)

        return 0.0

    def choice(self, options):
        return list(options)[0]


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeSchoolField:
    def __init__(self, value="Hogwarts"):
        self.value = value

    def get_value(self):
        return self.value


class FakeGameDatabase:
    def __init__(self):
        self.loaded = True
        self.collections = {
            "books": [
                {
                    "record_id": "book-charms-1",
                    "name": "Charms One",
                    "author": "A. Author",
                    "categories": ["Charms"],
                    "spells": [{"record_id": "spell-charms"}],
                    "proficiencies": [],
                },
                {
                    "record_id": "book-charms-2",
                    "name": "Charms Two",
                    "author": "B. Author",
                    "categories": ["Charms"],
                    "spells": [],
                    "proficiencies": [],
                },
                {
                    "record_id": "book-history",
                    "name": "History One",
                    "author": "C. Author",
                    "categories": ["History"],
                    "spells": [],
                    "proficiencies": [],
                },
            ],
            "spells": [
                {
                    "record_id": "spell-charms",
                    "name": "A Test Charm",
                    "skill": "Charms",
                }
            ],
            "proficiencies": [],
        }

    def collection(self, collection_name):
        return deepcopy(
            self.collections.get(collection_name, [])
        )


class CallRecorder:
    def __init__(self):
        self.calls = 0
        self.arguments = []

    def __call__(self, *arguments, **keyword_arguments):
        self.calls += 1
        self.arguments.append(
            (arguments, keyword_arguments)
        )


def build_development_view():
    view = object.__new__(DevelopmentView)
    view.loading = False
    view.school_field = FakeSchoolField()
    view.school_started = False
    view.academic_years_advanced = 0
    view.school_year_records = []
    view.development_plan = {
        "schema": "One skill",
        "focused_skills": ["Charms"],
        "academic_years_advanced": 0,
        "school_started": False,
        "school_years": [],
    }
    view.strategy_value = FakeVariable("One skill")
    view.skill_values = [
        FakeVariable("Charms"),
        FakeVariable("Flying"),
        FakeVariable("History"),
    ]
    view.ability_value = FakeVariable("Power")
    view.game_database = FakeGameDatabase()
    view.update_school_progress_controls = CallRecorder()
    view.notify_change = CallRecorder()
    return view


def first_choice(options):
    return list(options)[0]


class SchoolYearModelTests(unittest.TestCase):
    def test_school_year_record_allows_duplicate_skill_improvements(self):
        record = normalize_school_year_record(
            {
                "year": 1,
                "ability": "Power",
                "skills": ["Charms", "Charms"],
                "books": [
                    {
                        "record_id": "book-1",
                        "name": "First Book",
                    },
                    {
                        "record_id": "book-2",
                        "name": "Second Book",
                    },
                ],
            }
        )

        self.assertEqual(["Charms", "Charms"], record["skills"])
        self.assertEqual(2, len(record["books"]))

    def test_school_year_books_remove_duplicate_references(self):
        record = normalize_school_year_record(
            {
                "year": 1,
                "ability": "Power",
                "skills": ["Charms", "Defense"],
                "books": [
                    {
                        "record_id": "book-1",
                        "name": "First Book",
                    },
                    {
                        "record_id": "book-1",
                        "name": "First Book",
                    },
                ],
            }
        )

        self.assertEqual(1, len(record["books"]))

    def test_strategy_choice_uses_the_ninety_ten_split(self):
        preferred = strategy_weighted_choice(
            ["Power", "Erudition"],
            ["Power"],
            FakeRandomizer([0.89]),
        )
        deviation = strategy_weighted_choice(
            ["Power", "Erudition"],
            ["Power"],
            FakeRandomizer([0.90]),
        )

        self.assertEqual("Power", preferred)
        self.assertEqual("Erudition", deviation)

    def test_preferred_ability_follows_the_strategy_skills(self):
        self.assertEqual(
            ["Erudition"],
            preferred_development_abilities(
                {
                    "schema": "One skill",
                    "focused_skills": ["Runes"],
                }
            ),
        )
        self.assertEqual(
            ["Naturalism"],
            preferred_development_abilities(
                {
                    "schema": "Ability-focus",
                    "focused_ability": "Naturalism",
                }
            ),
        )

    def test_random_year_can_spend_both_skill_points_on_one_skill(self):
        record = random_school_year_record(
            1,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 0,
            },
            randomizer=FakeRandomizer([0.0, 0.0, 0.0]),
        )

        self.assertEqual("Power", record["ability"])
        self.assertEqual(["Charms", "Charms"], record["skills"])

    def test_linked_spells_and_proficiencies_supply_book_skills(self):
        explicit_skills, category_skills = book_linked_skill_sets(
            {
                "categories": ["History"],
                "spells": [{"record_id": "spell-1"}],
                "proficiencies": [{"record_id": "prof-1"}],
            },
            [{"record_id": "spell-1", "skill": "Charms"}],
            [{"record_id": "prof-1", "skill": "Flying"}],
        )

        self.assertEqual(
            {"Charms", "Flying"},
            explicit_skills,
        )
        self.assertEqual({"History"}, category_skills)

    def test_automatic_books_prefer_linked_records_then_categories(self):
        books = [
            {
                "record_id": "linked",
                "name": "Linked",
                "spells": [{"record_id": "spell-1"}],
                "proficiencies": [],
                "categories": [],
            },
            {
                "record_id": "category",
                "name": "Category",
                "spells": [],
                "proficiencies": [],
                "categories": ["Charms"],
            },
            {
                "record_id": "random",
                "name": "Random",
                "spells": [],
                "proficiencies": [],
                "categories": ["History"],
            },
        ]
        selected = select_school_year_books(
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
            },
            books,
            [{"record_id": "spell-1", "skill": "Charms"}],
            [],
            FakeRandomizer([0.0, 0.0]),
        )

        self.assertEqual(
            ["linked", "category"],
            [book["record_id"] for book in selected],
        )

    def test_automatic_books_use_nonmatching_book_on_deviation(self):
        selected = select_school_year_books(
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
            },
            [
                {
                    "record_id": "preferred",
                    "name": "Preferred",
                    "categories": ["Charms"],
                },
                {
                    "record_id": "random",
                    "name": "Random",
                    "categories": ["History"],
                },
            ],
            [],
            [],
            FakeRandomizer([0.95, 0.0]),
        )

        self.assertEqual("random", selected[0]["record_id"])
        self.assertEqual(2, len({
            book["record_id"]
            for book in selected
        }))

    def test_missing_years_are_generated_without_replacing_history(self):
        existing_record = {
            "year": 1,
            "school": "",
            "ability": "Erudition",
            "skills": ["History", "History"],
            "assigned_books": [],
            "books": [],
            "eminence": [],
        }
        records = ensure_school_year_records(
            [existing_record],
            3,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 2,
            },
            randomizer=FakeRandomizer(),
        )

        self.assertEqual("Erudition", records[0]["ability"])
        self.assertEqual(
            ["History", "History"],
            records[0]["skills"],
        )
        self.assertFalse(records[0]["skipped"])
        self.assertTrue(records[0]["characteristic"])
        self.assertEqual([1, 2, 3], [
            record["year"]
            for record in records
        ])

    def test_plan_normalization_persists_canonical_school_years(self):
        plan = normalize_development_plan(
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 0,
                "school_years": [
                    {
                        "year": 1,
                        "ability": "Power",
                        "skills": ["Charms", "Charms"],
                        "books": [],
                    }
                ],
            }
        )

        self.assertEqual(1, len(plan["school_years"]))
        self.assertEqual(
            ["Charms", "Charms"],
            plan["school_years"][0]["skills"],
        )

    def test_book_search_covers_linked_content(self):
        search_text = book_search_text(
            {
                "name": "General Text",
                "author": "Test Author",
                "categories": [],
                "spells": [{"name": "Hidden Charm"}],
                "proficiencies": [{"name": "Secret Lore"}],
            }
        )

        self.assertIn("hidden charm", search_text)
        self.assertIn("secret lore", search_text)

    def test_version_sixteen_migration_adds_school_year_storage(self):
        database_data = {
            "_database": {
                "schema_version": 16,
                "database_version": "0.16.0",
            },
            "people": [
                {
                    "development_plan": {
                        "schema": "Scattershot",
                        "school_started": False,
                        "academic_years_advanced": 0,
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
        self.assertEqual(
            [],
            database_data["people"][0]["development_plan"][
                "school_years"
            ],
        )

    def test_year_panel_exposes_ability_skills_and_book_dialog(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )
        dialog_source = inspect.getsource(BookSelectionDialog)

        self.assertIn(
            "self.year_ability_select = RoundedSelect",
            panel_source,
        )
        self.assertIn(
            "self.year_skill_selects = []",
            panel_source,
        )
        self.assertIn(
            'text="Select books"',
            panel_source,
        )
        self.assertIn(
            "self.search_control = RoundedEntry",
            dialog_source,
        )
        self.assertIn(
            "Add exactly two different books.",
            dialog_source,
        )


class SchoolYearViewTests(unittest.TestCase):
    def test_start_school_creates_and_stores_year_one(self):
        view = build_development_view()

        with patch(
            "mage_maker.sections.development.school_years.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.school_years.random.choice",
            side_effect=first_choice,
        ):
            DevelopmentView.advance_one_year(view)

        self.assertTrue(view.school_started)
        self.assertEqual(0, view.academic_years_advanced)
        self.assertEqual(1, len(view.school_year_records))
        year_one = view.school_year_records[0]
        self.assertEqual(1, year_one["year"])
        self.assertEqual("Power", year_one["ability"])
        self.assertEqual(["Charms", "Charms"], year_one["skills"])
        self.assertEqual(2, len(year_one["books"]))
        self.assertEqual(2, len({
            book["record_id"]
            for book in year_one["books"]
        }))

    def test_advance_one_year_preserves_year_one_and_creates_year_two(self):
        view = build_development_view()

        with patch(
            "mage_maker.sections.development.school_years.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.school_years.random.choice",
            side_effect=first_choice,
        ):
            DevelopmentView.advance_one_year(view)
            year_one = deepcopy(view.school_year_records[0])
            DevelopmentView.advance_one_year(view)

        self.assertEqual(1, view.academic_years_advanced)
        self.assertEqual([1, 2], [
            record["year"]
            for record in view.school_year_records
        ])
        self.assertEqual(year_one, view.school_year_records[0])

    def test_advance_to_adulthood_populates_all_seven_years(self):
        view = build_development_view()

        with patch(
            "mage_maker.sections.development.school_years.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.school_years.random.choice",
            side_effect=first_choice,
        ):
            DevelopmentView.advance_to_adulthood(view)

        self.assertEqual(7, view.academic_years_advanced)
        self.assertEqual(list(range(1, 8)), [
            record["year"]
            for record in view.school_year_records
        ])

        selected_book_ids = []

        for record in view.school_year_records:
            self.assertEqual(1, len(record["ability"].splitlines()))
            self.assertEqual(2, len(record["skills"]))
            self.assertLessEqual(len(record["books"]), 2)
            selected_book_ids.extend(
                normalize_school_year_book(book)["record_id"]
                for book in record["books"]
            )

        self.assertEqual(
            len(selected_book_ids),
            len(set(selected_book_ids)),
        )

    def test_manual_year_skills_can_use_the_same_skill_twice(self):
        view = build_development_view()
        view.school_started = True
        view.active_year_tab = 1
        view.school_year_records = [
            {
                "year": 1,
                "ability": "Power",
                "skills": ["Defense", "Flying"],
                "books": [],
            }
        ]
        view.year_ability_value = FakeVariable("Erudition")
        view.year_skill_values = [
            FakeVariable("Charms"),
            FakeVariable("Charms"),
        ]
        view.render_school_year_record = CallRecorder()

        DevelopmentView.school_year_selection_changed(view)

        self.assertEqual(
            ["Charms", "Charms"],
            view.school_year_records[0]["skills"],
        )
        self.assertEqual(
            "Erudition",
            view.school_year_records[0]["ability"],
        )
        self.assertEqual(1, view.notify_change.calls)

    def test_removing_latest_year_removes_its_saved_choices(self):
        view = build_development_view()
        view.school_started = True
        view.academic_years_advanced = 1
        view.school_year_records = [
            {
                "year": 1,
                "ability": "Power",
                "skills": ["Charms", "Charms"],
                "books": [],
            },
            {
                "year": 2,
                "ability": "Erudition",
                "skills": ["History", "History"],
                "books": [],
            },
        ]

        DevelopmentView.remove_latest_school_year(view)

        self.assertEqual(0, view.academic_years_advanced)
        self.assertEqual([1], [
            record["year"]
            for record in view.school_year_records
        ])

    def test_duplicate_manual_books_are_not_saved(self):
        view = build_development_view()
        view.school_started = True
        view.active_year_tab = 1
        view.school_year_records = [
            {
                "year": 1,
                "ability": "Power",
                "skills": ["Charms", "Charms"],
                "books": [],
            }
        ]
        duplicate_book = {
            "record_id": "same-book",
            "name": "Same Book",
        }

        DevelopmentView.save_school_year_books(
            view,
            [duplicate_book, duplicate_book],
        )

        self.assertEqual(
            [],
            view.school_year_records[0]["books"],
        )
        self.assertEqual(0, view.notify_change.calls)


if __name__ == "__main__":
    unittest.main()
