import inspect
import unittest
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.advancement_dialogs import (
    EminenceDialog,
    EminenceManagerDialog,
)
from mage_maker.sections.development.models import (
    new_eminence_record,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.school_years import (
    ensure_school_year_records,
)
from mage_maker.sections.ledger.models import (
    LEDGER_SOURCE_ALLOWANCE,
    LEDGER_SOURCE_SCHOOL_BOOK,
    LEDGER_SOURCE_STARTING_ALLOWANCE,
    ledger_balance_sickles,
    ledger_entry_date_text,
    ledger_running_balances,
    new_manual_calendar_ledger_entry,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.ledger.page import LedgerView
from mage_maker.sections.profile.school_field import SchoolField
from mage_maker.ui.theme import ADD_GREEN, PRIMARY


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeSchoolField:
    def __init__(self, value=""):
        self.value = value

    def get_value(self):
        return self.value


class FakeButton:
    def __init__(self):
        self.enabled = True
        self.text = ""
        self.colors = None
        self.visible = False

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_text(self, text):
        self.text = text

    def set_colors(self, fill, hover_fill, foreground=None):
        self.colors = (fill, hover_fill, foreground)

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class NavigationLayoutTests(unittest.TestCase):
    def test_page_arrows_share_a_centered_control_group(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn(
            "self.previous_development_page_button = SoftButton(\n"
            "            page_navigation_controls,",
            source,
        )
        self.assertIn(
            "self.next_development_page_button = SoftButton(\n"
            "            page_navigation_controls,",
            source,
        )
        self.assertIn(
            'uniform="development_navigation_sides"',
            source,
        )

    def test_existing_next_page_is_arrow_and_new_page_is_plus(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = True
        view.academic_years_advanced = 0
        view.adult_year_records = []
        view.current_person = {}
        view.active_development_page_index = 0
        view.year_tabs_container = object()
        view.render_active_development_page = Mock()
        view.advance_adulthood_button = FakeButton()
        view.previous_development_page_button = FakeButton()
        view.next_development_page_button = FakeButton()
        view.remove_latest_year_button = FakeButton()

        DevelopmentView.update_school_progress_controls(view)

        self.assertEqual(
            ">",
            view.next_development_page_button.text,
        )
        self.assertEqual(
            PRIMARY,
            view.next_development_page_button.colors[0],
        )

        view.active_development_page_index = 1
        DevelopmentView.update_school_progress_controls(view)

        self.assertEqual(
            "+",
            view.next_development_page_button.text,
        )
        self.assertEqual(
            ADD_GREEN,
            view.next_development_page_button.colors[0],
        )

    def test_middle_year_cannot_be_removed(self):
        view = object.__new__(DevelopmentView)
        view.school_started = True
        view.academic_years_advanced = 3
        view.adult_year_records = []
        view.active_development_page_index = 2

        DevelopmentView.remove_latest_school_year(view)

        self.assertEqual(3, view.academic_years_advanced)

    def test_death_date_blocks_creation_of_a_later_year(self):
        view = object.__new__(DevelopmentView)
        view.birth_year = 1980
        view.birth_month = 5
        view.birth_day = 10
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = True
        view.academic_years_advanced = 0
        view.adult_year_records = []
        view.current_person = {
            "deceased": True,
            "death_year": 1992,
            "death_month": 6,
            "death_day": 30,
        }
        view.active_development_page_index = 1

        self.assertFalse(
            DevelopmentView.can_add_next_development_page(view)
        )
        DevelopmentView.advance_one_year(view)
        self.assertEqual(0, view.academic_years_advanced)

    def test_development_columns_have_fixed_proportions(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertEqual(
            2,
            source.count('uniform="development_panels"'),
        )
        self.assertIn("minsize=330", source)
        self.assertIn("minsize=500", source)


class StrategyAndEminenceTests(unittest.TestCase):
    def test_skill_schema_switch_preserves_existing_slots(self):
        view = object.__new__(DevelopmentView)
        view.loading = False
        view.strategy_value = FakeVariable("One skill")
        view.skill_values = [
            FakeVariable("Charms"),
            FakeVariable("Flying"),
            FakeVariable("Alchemy"),
        ]
        view.ability_value = FakeVariable("Power")
        view.development_plan = {"schema": "Three skills"}
        view.academic_years_advanced = 0
        view.school_started = False
        view.school_year_records = []
        view.adult_year_records = []
        view.ledger_entries = []
        view.initial_eminence_records = []
        view.mortality_checked_through_age = None
        view.update_focus_controls = Mock()
        view.reconcile_initial_bonus_assignments = Mock()
        view.notify_change = Mock()

        DevelopmentView.strategy_changed(view)
        view.strategy_value.set("Three skills")
        DevelopmentView.strategy_changed(view)

        self.assertEqual(
            ["Charms", "Flying", "Alchemy"],
            [value.get() for value in view.skill_values],
        )

    def test_initial_page_keeps_any_number_of_eminence_records(self):
        view = object.__new__(DevelopmentView)
        view.initial_eminence_records = [
            new_eminence_record(
                f"Record {index}",
                "",
                "Charms",
            )
            for index in range(4)
        ]
        view.initial_eminence_summary_value = FakeVariable()
        view.initial_eminence_button = FakeButton()

        DevelopmentView.refresh_initial_eminence(view)

        self.assertEqual(4, len(view.initial_eminence_records))
        self.assertEqual(
            "Eminence: 4\nCharms (4)",
            view.initial_eminence_summary_value.get(),
        )

    def test_eminence_defaults_follow_development_strategy(self):
        view = object.__new__(DevelopmentView)
        view.active_year_tab = 0
        view.active_adult_year = 0
        view.current_development_plan = Mock(
            return_value={
                "schema": "One skill",
                "focused_skills": ["Runes"],
            }
        )

        self.assertEqual(
            "Runes",
            DevelopmentView.eminence_default_skill(view),
        )
        dialog_source = inspect.getsource(
            EminenceDialog.__init__
        )
        self.assertIn(
            'f"{selected_skill} eminence earned"',
            dialog_source,
        )

    def test_eminence_manager_owns_the_unbounded_list(self):
        source = inspect.getsource(EminenceManagerDialog)

        self.assertIn("tk.Listbox(", source)
        self.assertIn("tk.Scrollbar(", source)
        self.assertIn("def add_record(", source)
        self.assertIn("def remove_selected_record(", source)
        self.assertIn("def save_records(", source)


class SkipAndLedgerTests(unittest.TestCase):
    def test_skipped_school_year_has_no_school_reading(self):
        books = [
            {
                "record_id": f"book-{index}",
                "name": f"Book {index}",
            }
            for index in range(1, 4)
        ]
        records = ensure_school_year_records(
            [
                {
                    "year": 1,
                    "school": "Hogwarts",
                    "skipped": True,
                    "ability": "Power",
                    "skills": ["Charms", "Defense"],
                    "assigned_books": [books[0]],
                    "books": [books[1], books[2]],
                    "characteristic": "creativity",
                }
            ],
            1,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 0,
            },
            books,
            [],
            [],
            school_name="Hogwarts",
            assigned_books_by_year={1: [books[0]]},
        )

        self.assertTrue(records[0]["skipped"])
        self.assertEqual([], records[0]["assigned_books"])
        self.assertEqual(2, len(records[0]["books"]))

    def test_skipped_school_year_can_be_unskipped(self):
        books = [
            {
                "record_id": f"book-{index}",
                "name": f"Book {index}",
            }
            for index in range(1, 4)
        ]
        records = ensure_school_year_records(
            [
                {
                    "year": 1,
                    "school": "Hogwarts",
                    "skipped": True,
                    "ability": "Power",
                    "skills": ["Charms", "Defense"],
                    "assigned_books": [],
                    "books": [],
                    "characteristic": "creativity",
                }
            ],
            1,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 0,
            },
            books,
            [],
            [],
            school_name="Hogwarts",
            assigned_books_by_year={1: [books[0]]},
        )
        records[0]["skipped"] = False

        restored_records = ensure_school_year_records(
            records,
            1,
            {
                "schema": "One skill",
                "focused_skills": ["Charms"],
                "school_started": True,
                "academic_years_advanced": 0,
            },
            books,
            [],
            [],
            school_name="Hogwarts",
            assigned_books_by_year={1: [books[0]]},
        )

        self.assertFalse(restored_records[0]["skipped"])
        self.assertEqual(
            ["Book 1"],
            [
                book["name"]
                for book in restored_records[0]["assigned_books"]
            ],
        )
        self.assertEqual(2, len(restored_records[0]["books"]))

    def test_skip_checkbox_can_restore_school_attendance(self):
        view = object.__new__(DevelopmentView)
        view.loading = False
        view.active_adult_year = 0
        view.active_year_tab = 1
        view.school_started = True
        view.academic_years_advanced = 0
        view.school_year_records = [
            {
                "year": 1,
                "school": "Hogwarts",
                "skipped": True,
                "ability": "Power",
                "skills": ["Charms", "Defense"],
                "characteristic": "creativity",
                "assigned_books": [],
                "books": [],
                "eminence": [],
            }
        ]
        view.development_plan = {}
        view.year_skipped_value = FakeVariable(False)
        view.year_ability_value = FakeVariable("Power")
        view.year_skill_values = [
            FakeVariable("Charms"),
            FakeVariable("Defense"),
        ]
        view.year_characteristic_value = FakeVariable("Creativity")
        view.ensure_school_year_record_count = Mock()
        view.render_school_year_record = Mock()
        view.notify_change = Mock()

        DevelopmentView.school_year_selection_changed(view)

        self.assertFalse(view.school_year_records[0]["skipped"])
        view.ensure_school_year_record_count.assert_called_once_with(1)
        view.notify_change.assert_called_once_with()

    def test_skip_note_names_the_person(self):
        source = inspect.getsource(
            DevelopmentView.render_school_year_record
        )

        self.assertIn(
            "skipped attending school this year.",
            source,
        )
        self.assertNotIn(
            "No school books purchased or read.",
            source,
        )

    def test_automatic_ledger_rows_have_exact_dates(self):
        records = [
            {
                "year": 1,
                "school": "Hogwarts",
                "ability": "Power",
                "skills": ["Charms", "Defense"],
                "characteristic": "creativity",
                "assigned_books": [
                    {
                        "record_id": "book-one",
                        "name": "First-Year Charms",
                    }
                ],
                "books": [],
            }
        ]
        entries = reconcile_development_ledger_entries(
            [],
            records,
            [],
            monthly_allowance_sickles=2,
            starting_allowance_sickles=34,
            academic_start_year=1992,
        )
        starting_entry = next(
            entry
            for entry in entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_STARTING_ALLOWANCE
        )
        allowance_entries = [
            entry
            for entry in entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_ALLOWANCE
        ]
        book_entry = next(
            entry
            for entry in entries
            if entry["automatic_source"]
            == LEDGER_SOURCE_SCHOOL_BOOK
        )

        self.assertEqual(
            (1992, 7, 1),
            (
                starting_entry["calendar_year"],
                starting_entry["month"],
                starting_entry["day"],
            ),
        )
        self.assertEqual(8, allowance_entries[0]["month"])
        self.assertTrue(
            all(entry["day"] == 1 for entry in allowance_entries)
        )
        self.assertEqual(7, book_entry["month"])
        self.assertTrue(20 <= book_entry["day"] <= 31)
        self.assertEqual(
            "1992-07-01",
            ledger_entry_date_text(starting_entry),
        )
        running_balances = ledger_running_balances(entries)
        self.assertEqual(
            ledger_balance_sickles(entries),
            running_balances[entries[-1]["entry_id"]],
        )

    def test_manual_ledger_dates_are_preserved(self):
        entry = new_manual_calendar_ledger_entry(
            1992,
            "October",
            "Ink",
            3,
            "bought",
            school_year=1,
            day=17,
        )

        self.assertEqual(17, entry["day"])
        self.assertEqual(
            "1992-10-17",
            ledger_entry_date_text(entry),
        )

    def test_ledger_table_displays_date_and_running_total(self):
        table_source = inspect.getsource(
            LedgerView.build_table
        )
        refresh_source = inspect.getsource(
            LedgerView.refresh_table
        )

        self.assertIn('"date"', table_source)
        self.assertIn('"running_total"', table_source)
        self.assertIn("ledger_entry_date_text", refresh_source)
        self.assertIn("ledger_running_balances", refresh_source)

    def test_schema_twenty_ledger_rows_receive_exact_dates(self):
        database_data = {
            "_database": {
                "schema_version": 20,
                "database_version": "0.20.0",
            },
            "people": [
                {
                    "birth_year": 1980,
                    "birth_month": 5,
                    "birth_day": 10,
                    "parental_values": {
                        "mode": "override",
                        "generosity": 2,
                        "permissiveness": 2,
                        "wealth": 3,
                    },
                    "initial_bonuses": None,
                    "development_plan": {
                        "schema": "Scattershot",
                        "school_started": True,
                        "academic_years_advanced": 0,
                        "school_years": [
                            {
                                "year": 1,
                                "school": "Hogwarts",
                                "skipped": False,
                                "ability": "Power",
                                "skills": [
                                    "Charms",
                                    "Defense",
                                ],
                                "characteristic": "creativity",
                                "assigned_books": [
                                    {
                                        "record_id": "book-one",
                                        "name": "Required Text",
                                    }
                                ],
                                "books": [],
                                "eminence": [],
                            }
                        ],
                        "adult_years": [],
                        "ledger_entries": [],
                        "initial_eminence": [],
                    },
                }
            ],
        }
        database = JsonDatabase("unused-mage-maker.json")

        migrated = database.migrate_database(database_data)

        entries = database_data["people"][0][
            "development_plan"
        ]["ledger_entries"]
        self.assertTrue(migrated)
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        self.assertTrue(
            all("day" in entry for entry in entries)
        )


class SchoolDisplayTests(unittest.TestCase):
    def test_school_summary_is_plain_text_not_a_field(self):
        source = inspect.getsource(SchoolField.__init__)
        value_frame_start = source.index(
            "value_frame = tk.Frame("
        )
        picker_start = source.index("self.picker = SoftButton(")
        value_layout = source[value_frame_start:picker_start]

        self.assertIn("bg=background", value_layout)
        self.assertIn('font=app_font(11, "bold")', value_layout)
        self.assertNotIn("FIELD_BACKGROUND", value_layout)
        self.assertNotIn("highlightthickness", value_layout)


if __name__ == "__main__":
    unittest.main()
