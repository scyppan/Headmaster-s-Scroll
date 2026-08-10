import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.sections.development.advancement_dialogs import (
    EminenceManagerDialog,
    JobDialog,
)
from mage_maker.sections.development.initial_bonuses import (
    SCHEMA_SKILLS,
    SOCIAL_SKILLS,
)
from mage_maker.sections.development.models import (
    DEVELOPMENT_SKILL_OPTIONS,
    eminence_skill_counts,
    new_eminence_record,
    normalize_adult_year_record,
    normalize_development_skill,
    total_eminence_points,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
    QuickOrganizationDialog,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.school_years import (
    ensure_school_year_records,
    random_adult_year_record,
)
from mage_maker.sections.ledger.models import (
    LEDGER_SOURCE_SCHOOL_BOOK,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.profile.books import (
    adult_year_reading_entries,
)
from mage_maker.sections.profile.page import PersonForm


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeRecordList:
    def __init__(self):
        self.items = []
        self.selected_rows = ()
        self.seen_row = None

    def delete(self, first, last=None):
        self.items = []
        self.selected_rows = ()

    def insert(self, index, value):
        self.items.append(value)

    def curselection(self):
        return self.selected_rows

    def selection_set(self, index):
        self.selected_rows = (int(index),)

    def selection_clear(self, first, last=None):
        self.selected_rows = ()

    def see(self, index):
        self.seen_row = int(index)

    def itemconfigure(self, index, **options):
        return None


class FakeButton:
    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class FixedRandomizer:
    def __init__(self, rolls):
        self.rolls = list(rolls)

    def randint(self, minimum, maximum):
        return self.rolls.pop(0)

    def random(self):
        return 0.5

    def choice(self, values):
        return values[0]


def characteristic_values(intellect, willpower):
    values = {
        "creativity": 1,
        "equanimity": 1,
        "charisma": 1,
        "attractiveness": 1,
        "strength": 1,
        "agility": 1,
        "intellect": intellect,
        "willpower": willpower,
        "fortitude": 1,
    }
    remaining_points = (
        8
        - (intellect - 1)
        - (willpower - 1)
    )
    creativity_points = min(4, remaining_points)
    values["creativity"] += creativity_points
    values["equanimity"] += (
        remaining_points - creativity_points
    )
    return values


def book_records(count):
    return [
        {
            "record_id": f"book-{index}",
            "name": f"Book {index}",
            "author": f"Author {index}",
        }
        for index in range(1, count + 1)
    ]


class EminenceUpdateTests(unittest.TestCase):
    def test_summary_counts_every_skill_in_first_seen_order(self):
        records = [
            new_eminence_record("First", "", "Charms"),
            new_eminence_record("Second", "", "Runes"),
            new_eminence_record("Third", "", "Charms"),
            new_eminence_record("Fourth", "", "Social"),
        ]

        self.assertEqual(
            {
                "Charms": 2,
                "Runes": 1,
                "Social": 1,
            },
            eminence_skill_counts(records),
        )

    def test_total_includes_initial_school_and_adult_eminence(self):
        initial = new_eminence_record("Initial", "", "Charms")
        school_one = new_eminence_record("School 1", "", "Runes")
        school_two = new_eminence_record("School 2", "", "Social")
        adult = new_eminence_record("Adult", "", "Creatures")
        plan = {
            "schema": "Scattershot",
            "school_started": True,
            "academic_years_advanced": 7,
            "initial_eminence": [initial],
            "school_years": [
                {
                    "year": 1,
                    "school": "Hogwarts",
                    "skipped": False,
                    "ability": "Power",
                    "skills": ["Charms", "Charms"],
                    "characteristic": "intellect",
                    "assigned_books": [],
                    "books": [],
                    "eminence": [school_one, school_two],
                }
            ],
            "adult_years": [
                {
                    "adult_year": 1,
                    "reading_characteristic": "intellect",
                    "reading_rolls": [10, 10, 1],
                    "books": [],
                    "eminence": [adult],
                    "jobs": [],
                }
            ],
        }

        self.assertEqual(4, total_eminence_points(plan))

    def test_breakout_uses_separate_title_and_description_rows(self):
        manager = object.__new__(EminenceManagerDialog)
        manager.records = [
            new_eminence_record(
                "Tournament winner",
                "Won the regional cup.\nUndefeated in finals.",
                "Flying",
            ),
            new_eminence_record(
                "Published",
                "Released a new study.",
                "Runes",
            ),
        ]
        manager.record_list = FakeRecordList()
        manager.count_value = FakeVariable()

        EminenceManagerDialog.refresh_records(manager)

        self.assertEqual(
            [
                "Tournament winner (Flying)",
                "    Won the regional cup.",
                "    Undefeated in finals.",
                "Published (Runes)",
                "    Released a new study.",
            ],
            manager.record_list.items,
        )
        self.assertEqual(
            [0, 0, 0, 1, 1],
            manager.record_index_by_list_row,
        )

    def test_description_row_can_move_its_whole_record_down(self):
        first = new_eminence_record(
            "First",
            "First description",
            "Charms",
        )
        second = new_eminence_record(
            "Second",
            "Second description",
            "Runes",
        )
        manager = object.__new__(EminenceManagerDialog)
        manager.records = [first, second]
        manager.record_list = FakeRecordList()
        manager.count_value = FakeVariable()
        EminenceManagerDialog.refresh_records(manager)
        manager.record_list.selected_rows = (1,)

        EminenceManagerDialog.move_selected_record_down(manager)

        self.assertEqual(
            [second["record_id"], first["record_id"]],
            [record["record_id"] for record in manager.records],
        )
        self.assertEqual(2, manager.record_list.seen_row)

    def test_editing_can_change_skill_without_recreating_record(self):
        original = new_eminence_record(
            "Original",
            "Old description",
            "Charms",
        )
        replacement = {
            **original,
            "title": "Revised",
            "description": "New description",
            "skill": "Runes",
        }
        manager = object.__new__(EminenceManagerDialog)
        manager.records = [original]
        manager.record_list = FakeRecordList()
        manager.count_value = FakeVariable()

        EminenceManagerDialog.replace_record(
            manager,
            0,
            replacement,
        )

        self.assertEqual(
            original["record_id"],
            manager.records[0]["record_id"],
        )
        self.assertEqual("Runes", manager.records[0]["skill"])
        self.assertEqual("Revised", manager.records[0]["title"])

    def test_page_preview_lists_all_eminence_skill_types(self):
        view = object.__new__(DevelopmentView)
        view.active_year_tab = 1
        view.eminence_summary_value = FakeVariable()
        view.adult_eminence_summary_value = FakeVariable()
        records = [
            new_eminence_record("One", "", "Charms"),
            new_eminence_record("Two", "", "Runes"),
            new_eminence_record("Three", "", "Charms"),
            new_eminence_record("Four", "", "Social"),
        ]

        DevelopmentView.refresh_eminence_lists(view, records)

        self.assertEqual(
            (
                "Eminence: 4\n"
                "Charms (2), Runes (1), Social (1)"
            ),
            view.eminence_summary_value.get(),
        )


class TerminologyTests(unittest.TestCase):
    def test_legacy_skill_names_normalize_to_short_labels(self):
        self.assertEqual(
            "Creatures",
            normalize_development_skill("Magical Creatures"),
        )
        self.assertEqual(
            "Runes",
            normalize_development_skill("Ancient Runes"),
        )
        self.assertEqual(
            "Social",
            normalize_development_skill("Social Skills"),
        )

    def test_visible_skill_options_use_only_short_labels(self):
        self.assertIn("Creatures", DEVELOPMENT_SKILL_OPTIONS)
        self.assertIn("Runes", DEVELOPMENT_SKILL_OPTIONS)
        self.assertIn("Social", DEVELOPMENT_SKILL_OPTIONS)
        self.assertNotIn(
            "Magical Creatures",
            DEVELOPMENT_SKILL_OPTIONS,
        )
        self.assertNotIn("Ancient Runes", DEVELOPMENT_SKILL_OPTIONS)
        self.assertNotIn("Social Skills", DEVELOPMENT_SKILL_OPTIONS)
        self.assertIn("Creatures", SCHEMA_SKILLS["Ingredient Crafting"])
        self.assertIn("Runes", SCHEMA_SKILLS["Spell-crafting"])
        self.assertIn("Social", SOCIAL_SKILLS)


class SkippedSchoolYearTests(unittest.TestCase):
    def test_skip_keeps_non_school_development_and_study(self):
        books = book_records(4)
        records = ensure_school_year_records(
            [
                {
                    "year": 1,
                    "school": "Hogwarts",
                    "skipped": True,
                    "ability": "Power",
                    "skills": ["Charms", "Runes"],
                    "characteristic": "intellect",
                    "assigned_books": [books[0]],
                    "books": [books[1], books[2]],
                    "eminence": [
                        new_eminence_record(
                            "Prefect",
                            "Helped classmates.",
                            "Social",
                        )
                    ],
                }
            ],
            1,
            {
                "schema": "Two skill",
                "focused_skills": ["Charms", "Runes"],
                "school_started": True,
                "academic_years_advanced": 0,
            },
            books,
            school_name="Hogwarts",
            assigned_books_by_year={1: [books[0]]},
            initial_characteristics=characteristic_values(2, 2),
        )

        self.assertTrue(records[0]["skipped"])
        self.assertEqual([], records[0]["assigned_books"])
        self.assertEqual("Power", records[0]["ability"])
        self.assertEqual(["Charms", "Runes"], records[0]["skills"])
        self.assertEqual("intellect", records[0]["characteristic"])
        self.assertEqual(
            ["book-2", "book-3"],
            [book["record_id"] for book in records[0]["books"]],
        )
        self.assertEqual(1, len(records[0]["eminence"]))

    def test_skip_removes_school_book_purchase_but_keeps_allowance(self):
        record = {
            "year": 1,
            "school": "Hogwarts",
            "skipped": True,
            "ability": "Power",
            "skills": ["Charms", "Runes"],
            "characteristic": "intellect",
            "assigned_books": [],
            "books": book_records(2),
            "eminence": [],
        }

        entries = reconcile_development_ledger_entries(
            [],
            [record],
            [],
            monthly_allowance_sickles=2,
            starting_allowance_sickles=34,
            academic_start_year=1991,
        )

        self.assertTrue(entries)
        self.assertFalse(
            any(
                entry["automatic_source"]
                == LEDGER_SOURCE_SCHOOL_BOOK
                for entry in entries
            )
        )

    def test_skip_confirmation_explains_what_is_and_is_not_skipped(self):
        source = inspect.getsource(
            DevelopmentView.year_skip_changed
        )

        self.assertIn("messagebox.askyesno(", source)
        self.assertIn(
            "assigned school books will not be",
            source,
        )
        self.assertIn(
            "They can still choose ability, skill, and",
            source,
        )
        self.assertIn(
            "read intentional-study",
            source,
        )


class AdultReadingTests(unittest.TestCase):
    def test_intellect_four_roll_of_twenty_four_allows_three_books(self):
        books = book_records(4)
        record = random_adult_year_record(
            1,
            {"schema": "Scattershot"},
            FixedRandomizer([10, 5, 4, 5]),
            characteristic_values(4, 2),
            [],
            books,
            [],
            [],
        )

        self.assertEqual("intellect", record["reading_characteristic"])
        self.assertEqual([10, 5, 4, 5], record["reading_rolls"])
        self.assertEqual(24, record["reading_total"])
        self.assertEqual(3, record["book_limit"])
        self.assertEqual(3, len(record["books"]))

    def test_higher_willpower_is_used_and_twenty_one_allows_one_book(self):
        record = random_adult_year_record(
            1,
            {"schema": "Scattershot"},
            FixedRandomizer([7, 7, 7]),
            characteristic_values(2, 3),
            [],
            book_records(2),
            [],
            [],
        )

        self.assertEqual("willpower", record["reading_characteristic"])
        self.assertEqual(21, record["reading_total"])
        self.assertEqual(1, record["book_limit"])
        self.assertEqual(1, len(record["books"]))

    def test_adult_records_drop_school_advancements(self):
        record = normalize_adult_year_record(
            {
                "adult_year": 2,
                "ability": "Power",
                "skills": ["Charms", "Runes"],
                "skipped": True,
                "reading_characteristic": "intellect",
                "reading_rolls": [10, 10, 2],
                "books": [],
                "eminence": [],
                "jobs": [],
            }
        )

        self.assertNotIn("ability", record)
        self.assertNotIn("skills", record)
        self.assertNotIn("skipped", record)
        self.assertEqual(2, record["book_limit"])

    def test_adult_reading_rejects_other_characteristics(self):
        with self.assertRaisesRegex(
            ValueError,
            "Intellect or Willpower",
        ):
            normalize_adult_year_record(
                {
                    "adult_year": 1,
                    "reading_characteristic": "creativity",
                    "reading_rolls": [10],
                    "books": [],
                    "eminence": [],
                    "jobs": [],
                }
            )

    def test_adult_books_have_a_calendar_year_source(self):
        entries = adult_year_reading_entries(
            [
                {
                    "adult_year": 1,
                    "reading_characteristic": "intellect",
                    "reading_rolls": [10, 10, 1],
                    "books": [book_records(1)[0]],
                    "eminence": [],
                    "jobs": [],
                }
            ],
            academic_start_year=1991,
        )

        self.assertEqual(
            (
                "Intentional study in First year out of school "
                "(1998 - 1999)"
            ),
            entries[0]["source"],
        )

    def test_adult_page_has_reading_but_no_school_advancement_controls(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn("self.adult_reading_summary_value", source)
        self.assertIn("self.adult_books_button", source)
        self.assertNotIn("self.adult_ability", source)
        self.assertNotIn("self.adult_skill", source)
        self.assertNotIn('text="No annual development"', source)

    def test_adult_page_displays_only_the_book_limit_not_the_roll(self):
        source = inspect.getsource(
            DevelopmentView.render_adult_year_record
        )

        self.assertIn('f"Book limit: {book_limit}"', source)
        self.assertNotIn(
            "reading_characteristic.title()",
            source,
        )
        self.assertNotIn("dice_text", source)


class OrganizationJobTests(unittest.TestCase):
    def test_job_starts_without_silently_selecting_first_organization(self):
        source = inspect.getsource(JobDialog.__init__)

        self.assertIn("self.selected_organization = None", source)

    def test_organization_search_includes_location_and_events(self):
        dialog = SimpleNamespace(
            location_labels_by_id={"place-1": "London / Diagon Alley"}
        )
        text = OrganizationSelectionDialog.organization_search_text(
            dialog,
            {
                "name": "Flourish and Blotts",
                "organization_type": "Shop",
                "location_id": "place-1",
                "overview": "Bookseller",
                "notes": "Public",
                "events": [
                    {
                        "title": "Founding",
                        "year": 1881,
                        "description": "Opened in summer",
                    }
                ],
            },
        )

        for expected in (
            "flourish",
            "shop",
            "diagon alley",
            "bookseller",
            "founding",
            "1881",
            "summer",
        ):
            self.assertIn(expected, text)

    def test_organization_filter_requires_every_search_term_and_type(self):
        dialog = SimpleNamespace(
            organizations=[
                {
                    "record_id": "org-1",
                    "name": "Flourish and Blotts",
                    "organization_type": "Shop",
                    "location_id": "place-1",
                    "events": [
                        {
                            "title": "Founding",
                            "year": 1881,
                        }
                    ],
                },
                {
                    "record_id": "org-2",
                    "name": "Daily Prophet",
                    "organization_type": "Media",
                    "location_id": "place-1",
                    "events": [
                        {
                            "title": "Founding",
                            "year": 1881,
                        }
                    ],
                },
            ],
            location_labels_by_id={
                "place-1": "London / Diagon Alley"
            },
            search_value=FakeVariable("london 1881"),
            type_value=FakeVariable("Shop"),
            organization_list=FakeRecordList(),
            results_value=FakeVariable(),
            use_button=FakeButton(),
        )
        dialog.organization_search_text = (
            OrganizationSelectionDialog.organization_search_text.__get__(
                dialog
            )
        )
        dialog.organization_sort_key = (
            OrganizationSelectionDialog.organization_sort_key.__get__(
                dialog
            )
        )
        dialog.organization_display_text = (
            OrganizationSelectionDialog.organization_display_text.__get__(
                dialog
            )
        )

        OrganizationSelectionDialog.refresh_results(dialog)

        self.assertEqual(1, len(dialog.visible_organizations))
        self.assertEqual(
            "Flourish and Blotts",
            dialog.visible_organizations[0]["name"],
        )
        self.assertTrue(dialog.use_button.enabled)

    def test_quick_create_sends_required_location_and_founding_year(self):
        create_command = Mock(
            return_value={
                "record_id": "org-1",
                "name": "New Organization",
            }
        )
        save_command = Mock()
        dialog = SimpleNamespace(
            location_list=FakeRecordList(),
            visible_locations=[
                {
                    "record_id": "place-1",
                    "label": "London",
                }
            ],
            founding_year_value=FakeVariable("1975"),
            job_title_value=FakeVariable("Researcher"),
            job_salary_galleons_value=FakeVariable("12"),
            job_salary_sickles_value=FakeVariable("4"),
            job_salary_knuts_value=FakeVariable("7"),
            job_opened_year_value=FakeVariable("1980"),
            name_value=FakeVariable("New Organization"),
            type_value=FakeVariable("Shop"),
            create_command=create_command,
            save_command=save_command,
            destroy=Mock(),
        )
        dialog.location_list.selected_rows = (0,)

        QuickOrganizationDialog.create_organization(dialog)

        values = create_command.call_args.args[0]
        self.assertEqual("place-1", values["location_id"])
        self.assertEqual(1975, values["events"][0]["year"])
        self.assertEqual("founding", values["events"][0]["event_type"])
        self.assertEqual("Researcher", values["jobs"][0]["title"])
        self.assertEqual(
            {
                "galleons": 12,
                "sickles": 4,
                "knuts": 7,
                "period": "month",
            },
            values["jobs"][0]["salary"],
        )
        self.assertEqual(1980, values["jobs"][0]["opened_year"])
        save_command.assert_called_once_with(
            create_command.return_value
        )
        dialog.destroy.assert_called_once_with()

    def test_quick_created_organization_is_selected_for_the_job(self):
        save_command = Mock()
        dialog = SimpleNamespace(
            organizations=[],
            save_command=save_command,
            destroy=Mock(),
        )
        organization = {
            "record_id": "org-1",
            "name": "New Organization",
        }

        OrganizationSelectionDialog.organization_created(
            dialog,
            organization,
        )

        self.assertEqual([organization], dialog.organizations)
        save_command.assert_called_once_with(organization)
        dialog.destroy.assert_called_once_with()


class ProfileOverviewTests(unittest.TestCase):
    def test_profile_shows_total_eminence_instead_of_allowance(self):
        source = inspect.getsource(PersonForm.build_profile_page)

        self.assertIn('text="Total eminence points"', source)
        self.assertNotIn('text="Monthly allowance"', source)


if __name__ == "__main__":
    unittest.main()
