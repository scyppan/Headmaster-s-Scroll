import inspect
import random
import unittest

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.characteristics import (
    CHARACTERISTIC_MAXIMUM_VALUE,
    characteristic_values_through_school_year,
    editable_characteristic_buys,
    randomized_characteristics,
)
from mage_maker.sections.development.models import (
    ACADEMIC_YEARS_TO_ADULTHOOD,
    normalize_development_plan,
    new_eminence_record,
)
from mage_maker.sections.development.mortality import (
    simulate_mortality_to_database_date,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.school_years import (
    ensure_school_year_records,
)
from mage_maker.sections.ledger.models import (
    LEDGER_SOURCE_ALLOWANCE,
    LEDGER_SOURCE_STARTING_ALLOWANCE,
    ledger_balance_sickles,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.settings.controller import (
    ApplicationSettingsController,
)
from mage_maker.sections.settings.page import SettingsPage
from mage_maker.sections.settings.simulation import (
    DATABASE_DATE_SETTING_KEY,
    DEFAULT_DATABASE_DATE,
    DEFAULT_MORTALITY_TABLE,
    MORTALITY_TABLE_SETTING_KEY,
    mortality_probability_for_age,
    mortality_table_rows,
)


class SequenceRandom:
    def __init__(self, values):
        self.values = list(values)

    def random(self):
        return self.values.pop(0)


class FakeDatabase:
    def __init__(self):
        self.data = {"_application_settings": {}}
        self.dirty = False


class FakeToggle:
    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class CertainDeathSettings:
    def mortality_table(self):
        table = dict(DEFAULT_MORTALITY_TABLE)
        table["70"] = 1.0
        return table


class MortalityRecorder:
    def __init__(self):
        self.values = None

    def __call__(self, values):
        self.values = values


class FakeModernDayDevelopment:
    def __init__(self):
        self.birth_year = 1980
        self.birth_month = 5
        self.birth_day = 10
        self.school_started = False
        self.academic_years_advanced = 0
        self.school_year_records = []
        self.adult_year_records = []
        self.development_plan = {"schema": "Scattershot"}
        self.characteristics = randomized_characteristics()
        self.current_person = {
            "record_id": "modern-day-mage",
            "birth_year": 1980,
            "birth_month": 5,
            "birth_day": 10,
            "deceased": False,
        }
        self.progress_updated = False
        self.change_count = 0

    def school_is_selected(self):
        return True

    def configured_database_date(self):
        return dict(DEFAULT_DATABASE_DATE)

    def simulate_mortality(self, database_date):
        return {
            "checked_through_age": None,
            "died": False,
            "death_age": None,
            "death_year": None,
        }

    def death_limited_database_date(self, database_date):
        return database_date

    def modern_day_progress_targets(self, database_date):
        return DevelopmentView.modern_day_progress_targets(
            self,
            database_date,
        )

    def school_year_generation_plan(self):
        return {
            "schema": "Scattershot",
            "school_started": self.school_started,
            "academic_years_advanced": self.academic_years_advanced,
            "school_years": self.school_year_records,
            "adult_years": self.adult_year_records,
        }

    def ensure_school_year_record_count(self, target_year_count):
        self.school_year_records = ensure_school_year_records(
            self.school_year_records,
            target_year_count,
            self.school_year_generation_plan(),
            randomizer=random.Random(17),
            school_name="Hogwarts",
            initial_characteristics=self.characteristics,
        )
        self.development_plan["school_years"] = (
            self.school_year_records
        )
        return True

    def update_school_progress_controls(self, select_latest=False):
        self.progress_updated = bool(select_latest)

    def notify_change(self):
        self.change_count += 1


class SimulationSettingsTests(unittest.TestCase):
    def test_database_date_defaults_to_31_july_2000(self):
        controller = ApplicationSettingsController(FakeDatabase())

        self.assertEqual(
            {"year": 2000, "month": 7, "day": 31},
            controller.database_date(),
        )

    def test_database_date_can_be_changed_and_marks_settings_dirty(self):
        database = FakeDatabase()
        controller = ApplicationSettingsController(database)

        changed = controller.set_database_date(2012, 8, 14)

        self.assertTrue(changed)
        self.assertTrue(database.dirty)
        self.assertEqual(
            {"year": 2012, "month": 8, "day": 14},
            database.data["_application_settings"][
                DATABASE_DATE_SETTING_KEY
            ],
        )

    def test_mortality_values_are_stored_to_four_decimals(self):
        database = FakeDatabase()
        controller = ApplicationSettingsController(database)

        controller.set_mortality_probability("70", 0.123456)

        self.assertEqual(0.1235, controller.mortality_table()["70"])

    def test_attached_model_defaults_cover_70_through_150_plus(self):
        rows = mortality_table_rows(DEFAULT_MORTALITY_TABLE)

        self.assertEqual(81, len(rows))
        self.assertEqual(("70", 0.0040), rows[0])
        self.assertEqual(("140", 0.0774), rows[70])
        self.assertEqual(("150+", 0.0790), rows[-1])
        self.assertEqual(
            0.0790,
            mortality_probability_for_age(
                188,
                DEFAULT_MORTALITY_TABLE,
            ),
        )

    def test_settings_page_exposes_date_and_mortality_editors(self):
        page_source = inspect.getsource(SettingsPage.build_page)

        self.assertIn('"Database date"', page_source)
        self.assertIn('"Annual mortality"', page_source)
        self.assertIn("self.mortality_table = ttk.Treeview(", page_source)


class MortalityTests(unittest.TestCase):
    def test_each_attained_age_is_tested_only_once(self):
        table = dict(DEFAULT_MORTALITY_TABLE)
        table["70"] = 0.0
        table["71"] = 1.0
        person = {
            "birth_year": 1930,
            "birth_month": 1,
            "birth_day": 1,
            "deceased": False,
        }
        first_result = simulate_mortality_to_database_date(
            person,
            None,
            table,
            {"year": 2001, "month": 7, "day": 31},
            SequenceRandom([0.5, 0.5]),
        )

        self.assertTrue(first_result["died"])
        self.assertEqual(71, first_result["death_age"])
        self.assertEqual(2001, first_result["death_year"])
        self.assertEqual(71, first_result["checked_through_age"])

        second_result = simulate_mortality_to_database_date(
            person,
            first_result["checked_through_age"],
            table,
            {"year": 2001, "month": 7, "day": 31},
            SequenceRandom([]),
        )
        self.assertFalse(second_result["died"])
        self.assertEqual(71, second_result["checked_through_age"])

    def test_age_seventy_uses_probability_point_zero_zero_four(self):
        self.assertEqual(
            0.0040,
            mortality_probability_for_age(
                70,
                DEFAULT_MORTALITY_TABLE,
            ),
        )

    def test_development_mortality_marks_the_profile_and_checkpoint(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "record_id": "elder",
            "birth_year": 1930,
            "birth_month": 4,
            "birth_day": 12,
            "deceased": False,
        }
        view.birth_year = 1930
        view.birth_month = 4
        view.birth_day = 12
        view.mortality_checked_through_age = None
        view.development_plan = {}
        view.settings_provider = CertainDeathSettings()
        recorder = MortalityRecorder()
        view.mortality_command = recorder

        result = DevelopmentView.simulate_mortality(
            view,
            {"year": 2000, "month": 7, "day": 31},
        )

        self.assertTrue(result["died"])
        self.assertEqual(70, view.mortality_checked_through_age)
        self.assertEqual(
            70,
            view.development_plan[
                "mortality_checked_through_age"
            ],
        )
        self.assertTrue(view.current_person["deceased"])
        self.assertEqual(2000, view.current_person["death_year"])
        self.assertEqual(4, recorder.values["death_month"])
        self.assertEqual(12, recorder.values["death_day"])


class AnnualProgressionTests(unittest.TestCase):
    def test_school_years_each_receive_one_capped_characteristic_buy(self):
        initial_characteristics = {
            "creativity": 5,
            "equanimity": 3,
            "charisma": 1,
            "attractiveness": 1,
            "strength": 1,
            "agility": 1,
            "intellect": 1,
            "willpower": 2,
            "fortitude": 2,
        }
        records = ensure_school_year_records(
            [],
            ACADEMIC_YEARS_TO_ADULTHOOD,
            {"schema": "Scattershot"},
            randomizer=random.Random(7),
            initial_characteristics=initial_characteristics,
        )
        final_values = characteristic_values_through_school_year(
            initial_characteristics,
            records,
        )

        self.assertEqual(7, len(records))
        self.assertTrue(
            all(record["characteristic"] for record in records)
        )
        self.assertTrue(
            all(
                value <= CHARACTERISTIC_MAXIMUM_VALUE
                for value in final_values.values()
            )
        )
        self.assertTrue(
            all(
                record["characteristic"] != "creativity"
                for record in records
            )
        )

    def test_skip_disables_ability_and_skills_but_not_characteristic(self):
        view = object.__new__(DevelopmentView)
        view.year_ability_select = FakeToggle()
        view.year_skill_selects = [FakeToggle(), FakeToggle()]
        view.adult_ability_select = FakeToggle()
        view.adult_skill_selects = [FakeToggle(), FakeToggle()]
        view.year_characteristic_select = FakeToggle()

        DevelopmentView.set_annual_improvement_controls_enabled(
            view,
            False,
        )

        self.assertFalse(view.year_ability_select.enabled)
        self.assertTrue(
            all(
                not control.enabled
                for control in view.year_skill_selects
            )
        )
        self.assertFalse(view.adult_ability_select.enabled)
        self.assertTrue(
            all(
                not control.enabled
                for control in view.adult_skill_selects
            )
        )
        self.assertTrue(view.year_characteristic_select.enabled)

    def test_editing_an_earlier_year_respects_later_buys(self):
        initial_characteristics = {
            "creativity": 3,
            "equanimity": 3,
            "charisma": 1,
            "attractiveness": 1,
            "strength": 1,
            "agility": 1,
            "intellect": 2,
            "willpower": 2,
            "fortitude": 3,
        }
        records = [
            {"year": 1, "characteristic": "charisma"},
            {"year": 2, "characteristic": "creativity"},
            {"year": 3, "characteristic": "creativity"},
        ]

        choices = editable_characteristic_buys(
            initial_characteristics,
            records,
            1,
        )

        self.assertNotIn("creativity", choices)
        self.assertIn("charisma", choices)

    def test_initial_values_store_one_eminence_record(self):
        eminence = new_eminence_record(
            "{eminence earned}",
            "A starting reputation.",
            "Charms",
        )
        plan = normalize_development_plan(
            {
                "schema": "Scattershot",
                "initial_eminence": [eminence],
            }
        )

        self.assertEqual(1, len(plan["initial_eminence"]))
        self.assertEqual(
            "{eminence earned}",
            plan["initial_eminence"][0]["title"],
        )

    def test_development_skills_share_one_horizontal_row(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn(
            "row=0,\n"
            "                column=index,",
            panel_source,
        )
        self.assertGreaterEqual(
            panel_source.count('text="Skip this year"'),
            1,
        )
        self.assertNotIn(
            'text="No annual development"',
            panel_source,
        )
        self.assertIn(
            "remove_latest_year_button",
            panel_source,
        )

    def test_advance_to_modern_day_creates_every_missing_year(self):
        view = FakeModernDayDevelopment()

        DevelopmentView.advance_to_modern_day(view)

        self.assertTrue(view.school_started)
        self.assertEqual(
            ACADEMIC_YEARS_TO_ADULTHOOD,
            view.academic_years_advanced,
        )
        self.assertEqual(7, len(view.school_year_records))
        self.assertEqual(2, len(view.adult_year_records))
        self.assertTrue(
            all(
                len(record["skills"]) == 2
                and record["ability"]
                and record["characteristic"]
                for record in view.school_year_records
            )
        )
        self.assertTrue(
            all(
                record["reading_characteristic"]
                in ("intellect", "willpower")
                and isinstance(record["reading_rolls"], list)
                and "ability" not in record
                and "skills" not in record
                for record in view.adult_year_records
            )
        )
        self.assertTrue(view.progress_updated)
        self.assertEqual(1, view.change_count)


class LedgerStartTests(unittest.TestCase):
    def test_first_ledger_year_opens_in_july_then_pays_from_august(self):
        records = ensure_school_year_records(
            [],
            2,
            {"schema": "Scattershot"},
            randomizer=random.Random(3),
            initial_characteristics=randomized_characteristics(),
        )
        entries = reconcile_development_ledger_entries(
            [],
            records,
            [],
            monthly_allowance_sickles=6,
            starting_allowance_sickles=6 * 17,
            academic_start_year=1991,
        )
        opening = entries[0]
        first_year_allowances = [
            entry
            for entry in entries
            if entry["school_year"] == 1
            and entry["automatic_source"] == LEDGER_SOURCE_ALLOWANCE
        ]
        second_year_allowances = [
            entry
            for entry in entries
            if entry["school_year"] == 2
            and entry["automatic_source"] == LEDGER_SOURCE_ALLOWANCE
        ]

        self.assertEqual(
            LEDGER_SOURCE_STARTING_ALLOWANCE,
            opening["automatic_source"],
        )
        self.assertEqual("starting allowance", opening["item"])
        self.assertEqual(7, opening["month"])
        self.assertEqual(1991, opening["calendar_year"])
        self.assertEqual(6 * 17, opening["amount_sickles"])
        self.assertEqual(
            [8, 9, 10, 11, 12, 1, 2, 3, 4, 5, 6],
            [entry["month"] for entry in first_year_allowances],
        )
        self.assertEqual(12, len(second_year_allowances))
        self.assertEqual(
            (6 * 17) + (23 * 6),
            ledger_balance_sickles(entries),
        )


class SchemaTwentyTests(unittest.TestCase):
    def test_schema_twenty_adds_simulation_and_annual_records(self):
        database_data = {
            "_database": {
                "schema_version": 19,
                "database_version": "0.19.0",
            },
            "_application_settings": {},
            "people": [
                {
                    "record_id": "legacy",
                    "birth_year": 1980,
                    "birth_month": 5,
                    "birth_day": 10,
                    "parental_values": {
                        "initialized": True,
                        "mode": "Override",
                        "generosity": 2,
                        "permissiveness": 4,
                        "wealth": 3,
                    },
                    "characteristics": randomized_characteristics(),
                    "development_plan": {
                        "schema": "Scattershot",
                        "school_started": True,
                        "academic_years_advanced": 0,
                        "school_years": [
                            {
                                "year": 1,
                                "ability": "Power",
                                "skills": ["Charms", "Charms"],
                            }
                        ],
                    },
                }
            ],
            "organizations": [],
        }
        database = object.__new__(JsonDatabase)

        changed = JsonDatabase.migrate_database(
            database,
            database_data,
        )

        self.assertTrue(changed)
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        settings = database_data["_application_settings"]
        self.assertEqual(
            DEFAULT_DATABASE_DATE,
            settings[DATABASE_DATE_SETTING_KEY],
        )
        self.assertEqual(
            DEFAULT_MORTALITY_TABLE,
            settings[MORTALITY_TABLE_SETTING_KEY],
        )
        plan = database_data["people"][0]["development_plan"]
        self.assertTrue(plan["school_years"][0]["characteristic"])
        self.assertFalse(plan["school_years"][0]["skipped"])
        self.assertEqual([], plan["initial_eminence"])
        self.assertIsNone(plan["mortality_checked_through_age"])
        self.assertEqual(12, len(plan["ledger_entries"]))
        self.assertEqual(
            LEDGER_SOURCE_STARTING_ALLOWANCE,
            plan["ledger_entries"][0]["automatic_source"],
        )
        self.assertEqual(7, plan["ledger_entries"][0]["month"])


if __name__ == "__main__":
    unittest.main()
