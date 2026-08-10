import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.models import (
    ACADEMIC_YEARS_TO_ADULTHOOD,
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_ASSIGNMENT_PROMPT,
    DEVELOPMENT_ASSIGNMENT_RANDOM,
    DEVELOPMENT_ASSIGNMENT_SCATTERSHOT,
    DEVELOPMENT_ASSIGNMENT_SETTING_KEY,
    DEVELOPMENT_SCHEMA_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    calculate_school_start_year,
    new_development_plan,
    normalize_development_plan,
    school_progress_text,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.mages.page import MagesPage
from mage_maker.sections.settings.controller import (
    ApplicationSettingsController,
)


class FakeVariable:
    def __init__(self, value=""):
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


class FakeSelect:
    def __init__(self, variable):
        self.variable = variable
        self.values = []

    def set_values(self, values):
        self.values = list(values)

        if self.values and self.variable.get() not in self.values:
            self.variable.set(self.values[0])


class FakePromptController:
    def development_assignment_policy(self):
        return DEVELOPMENT_ASSIGNMENT_PROMPT


class FakeCallRecorder:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


class FakePromptPage:
    def __init__(self):
        self.controller = FakePromptController()

    def current_grab_widget(self):
        return None

    def development_prompt_parent(self):
        return self

    def wait_window(self, dialog):
        return None

    def restore_prompt_parent_grab(self, prompt_parent):
        return None


class FakeStrategyDialog:
    def __init__(self, parent, person_name=""):
        self.parent = parent
        self.person_name = person_name
        self.result = "Social"


class DevelopmentModelTests(unittest.TestCase):
    def test_strategy_categories_match_the_required_schema(self):
        self.assertEqual(
            (
                "One skill",
                "Two skill",
                "Three skills",
                "Ability-focus",
                "Material Crafting",
                "Ingredient Crafting",
                "Spell-crafting",
                "Social",
                "Scattershot",
            ),
            DEVELOPMENT_SCHEMA_OPTIONS,
        )

    def test_focus_options_match_the_required_skills_and_abilities(self):
        self.assertEqual(18, len(DEVELOPMENT_SKILL_OPTIONS))
        self.assertIn("Flying", DEVELOPMENT_SKILL_OPTIONS)
        self.assertIn("Perception", DEVELOPMENT_SKILL_OPTIONS)
        self.assertIn("Social", DEVELOPMENT_SKILL_OPTIONS)
        self.assertEqual(
            (
                "Power",
                "Erudition",
                "Panache",
                "Naturalism",
            ),
            DEVELOPMENT_ABILITY_OPTIONS,
        )

    def test_september_first_is_the_school_cutoff(self):
        self.assertEqual(
            2011,
            calculate_school_start_year(2000, 8, 31),
        )
        self.assertEqual(
            2011,
            calculate_school_start_year(2000, 9, 1),
        )
        self.assertEqual(
            2012,
            calculate_school_start_year(2000, 9, 2),
        )
        self.assertEqual(
            2012,
            calculate_school_start_year(2000, 10, 1),
        )
        self.assertEqual(
            2011,
            calculate_school_start_year(2000),
        )
        self.assertIsNone(calculate_school_start_year(None))

    def test_plan_normalization_preserves_individual_overrides(self):
        normalized = normalize_development_plan(
            {
                "schema": "ability focus",
                "age": "14",
                "preferred_ability": "Power",
            }
        )
        self.assertEqual("Ability-focus", normalized["schema"])
        self.assertEqual(0, normalized["academic_years_advanced"])
        self.assertFalse(normalized["school_started"])
        self.assertEqual("Power", normalized["focused_ability"])
        self.assertNotIn("age", normalized)
        self.assertNotIn("preferred_ability", normalized)

    def test_start_school_enters_year_one_without_completing_it(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = False
        view.academic_years_advanced = 0
        view.update_school_progress_controls = lambda **values: None
        change_recorder = FakeCallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.advance_one_year(view)

        self.assertTrue(view.school_started)
        self.assertEqual(0, view.academic_years_advanced)
        self.assertEqual(1, change_recorder.calls)

    def test_advance_one_year_updates_stable_academic_progress(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = True
        view.academic_years_advanced = 3
        view.update_school_progress_controls = lambda **values: None
        change_recorder = FakeCallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.advance_one_year(view)

        self.assertEqual(4, view.academic_years_advanced)
        self.assertEqual(1, change_recorder.calls)

    def test_advance_to_adulthood_completes_seven_academic_years(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = True
        view.academic_years_advanced = 3
        view.update_school_progress_controls = lambda **values: None
        change_recorder = FakeCallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.advance_to_adulthood(view)

        self.assertEqual(
            ACADEMIC_YEARS_TO_ADULTHOOD,
            view.academic_years_advanced,
        )
        self.assertTrue(view.school_started)
        self.assertEqual(1, change_recorder.calls)

    def test_banner_keeps_only_modern_day_progression(self):
        header_source = inspect.getsource(
            DevelopmentView.build_header
        )
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn(
            'text="Advance to modern day"',
            header_source,
        )
        self.assertNotIn("Advance one year", header_source)
        self.assertNotIn("Start school", header_source)
        self.assertIn('text="Random strategy"', panel_source)
        self.assertNotIn("actions_menu", header_source)

    def test_school_progress_labels_cover_all_school_states(self):
        self.assertEqual(
            "Not yet started school",
            school_progress_text(False, 0),
        )
        self.assertEqual(
            "Year 1",
            school_progress_text(True, 0),
        )
        self.assertEqual(
            "Year 7",
            school_progress_text(True, 6),
        )
        self.assertEqual(
            "Graduated",
            school_progress_text(True, 7),
        )

    def test_legacy_crafting_becomes_material_crafting(self):
        normalized = normalize_development_plan(
            {"schema": "Crafting"}
        )
        self.assertEqual(
            "Material Crafting",
            normalized["schema"],
        )

    def test_no_school_displays_the_birth_year_as_the_start_year(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("")
        view.start_year_value = FakeVariable()
        view.birth_year = 2000
        view.birth_month = 9
        view.birth_day = 2

        DevelopmentView.update_start_year(view)

        self.assertEqual(
            "2000",
            view.start_year_value.get(),
        )

    def test_each_skill_dropdown_excludes_every_other_selection(self):
        view = object.__new__(DevelopmentView)
        view.skill_values = [
            FakeVariable("Charms"),
            FakeVariable("Flying"),
            FakeVariable("Alchemy"),
        ]
        view.strategy_value = FakeVariable("Three skills")
        view.skill_selects = [
            FakeSelect(view.skill_values[index])
            for index in range(3)
        ]

        DevelopmentView.update_skill_options(view)

        self.assertIn("Charms", view.skill_selects[0].values)
        self.assertNotIn("Flying", view.skill_selects[0].values)
        self.assertNotIn("Alchemy", view.skill_selects[0].values)
        self.assertNotIn("Charms", view.skill_selects[1].values)
        self.assertIn("Flying", view.skill_selects[1].values)
        self.assertNotIn("Alchemy", view.skill_selects[1].values)
        self.assertNotIn("Charms", view.skill_selects[2].values)
        self.assertNotIn("Flying", view.skill_selects[2].values)
        self.assertIn("Alchemy", view.skill_selects[2].values)
        self.assertEqual(
            ["Charms", "Flying", "Alchemy"],
            [value.get() for value in view.skill_values],
        )

    def test_selected_strategy_receives_random_focus_values(self):
        with patch(
            "mage_maker.sections.development.models.random.sample",
            return_value=["Flying", "Charms", "Perception"],
        ):
            plan = new_development_plan(
                DEVELOPMENT_ASSIGNMENT_PROMPT,
                "Three skills",
            )

        self.assertEqual("Three skills", plan["schema"])
        self.assertEqual(
            ["Flying", "Charms", "Perception"],
            plan["focused_skills"],
        )

        with patch(
            "mage_maker.sections.development.models.random.choice",
            return_value="Panache",
        ):
            ability_plan = new_development_plan(
                DEVELOPMENT_ASSIGNMENT_PROMPT,
                "Ability-focus",
            )

        self.assertEqual("Ability-focus", ability_plan["schema"])
        self.assertEqual("Panache", ability_plan["focused_ability"])

    def test_random_assignment_includes_random_ability_selection(self):
        with patch(
            "mage_maker.sections.development.models.random.choice",
            side_effect=["Ability-focus", "Naturalism"],
        ):
            plan = new_development_plan(
                DEVELOPMENT_ASSIGNMENT_RANDOM
            )

        self.assertEqual("Ability-focus", plan["schema"])
        self.assertEqual(
            "Naturalism",
            plan["focused_ability"],
        )

    def test_skill_plan_requires_distinct_focus_values(self):
        normalized = normalize_development_plan(
            {
                "schema": "Three skills",
                "focused_skills": [
                    "Charms",
                    "Charms",
                    "Flying",
                ],
            }
        )
        self.assertEqual(
            ["Charms", "Flying", "Alchemy"],
            normalized["focused_skills"],
        )


class DevelopmentPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "mage_maker.json"
        )
        self.database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 9,
                        "database_version": "0.9.0",
                        "last_saved": None,
                    },
                    "people": [
                        {
                            "record_id": "existing",
                            "displayed_name": "Existing Magician",
                            "biological_mother_id": "",
                            "biological_father_id": "",
                            "biological_mother_status": "unknown",
                            "biological_father_status": "unknown",
                            "mate_ids": [],
                            "spouse_relationships": [],
                            "timeline_events": [],
                        }
                    ],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                    "_application_settings": {
                        "region_lock_id": "world",
                    },
                }
            ),
            encoding="utf-8",
        )
        self.database = JsonDatabase(self.database_path)
        self.database.load()
        self.controller = PeopleController(self.database)
        self.settings_controller = ApplicationSettingsController(
            self.database
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_migration_registers_a_plan_for_every_existing_person(self):
        existing = self.database.read_person("existing")
        self.assertIn(
            existing["development_plan"]["schema"],
            DEVELOPMENT_SCHEMA_OPTIONS,
        )
        self.assertEqual(
            0,
            existing["development_plan"]["academic_years_advanced"],
        )
        self.assertNotIn("age", existing["development_plan"])
        self.assertEqual(
            29,
            self.database.data["_database"]["schema_version"],
        )
        self.assertEqual(
            DEVELOPMENT_ASSIGNMENT_RANDOM,
            self.database.data["_application_settings"][
                DEVELOPMENT_ASSIGNMENT_SETTING_KEY
            ],
        )
        self.assertEqual(
            "world",
            self.database.data["_application_settings"][
            "region_lock_id"
            ],
        )

    def test_version_ten_age_is_replaced_with_usable_focus_data(self):
        version_ten_path = (
            Path(self.temporary_directory.name)
            / "version_ten.json"
        )
        version_ten_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 10,
                        "database_version": "0.10.0",
                        "last_saved": None,
                    },
                    "people": [
                        {
                            "record_id": "legacy-focus",
                            "displayed_name": "Legacy Focus",
                            "biological_mother_id": "",
                            "biological_father_id": "",
                            "biological_mother_status": "unknown",
                            "biological_father_status": "unknown",
                            "mate_ids": [],
                            "spouse_relationships": [],
                            "timeline_events": [],
                            "development_plan": {
                                "schema": "Two skill",
                                "age": 14,
                            },
                        }
                    ],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                    "_application_settings": {
                        DEVELOPMENT_ASSIGNMENT_SETTING_KEY: (
                            DEVELOPMENT_ASSIGNMENT_RANDOM
                        ),
                    },
                }
            ),
            encoding="utf-8",
        )
        version_ten_database = JsonDatabase(version_ten_path)
        version_ten_database.load()
        plan = version_ten_database.read_person(
            "legacy-focus"
        )["development_plan"]

        self.assertEqual(29, version_ten_database.data["_database"][
            "schema_version"
        ])
        self.assertNotIn("age", plan)
        self.assertEqual(2, len(plan["focused_skills"]))
        self.assertEqual(2, len(set(plan["focused_skills"])))

    def test_scattershot_policy_assigns_scattershot(self):
        self.settings_controller.set_development_assignment_policy(
            DEVELOPMENT_ASSIGNMENT_SCATTERSHOT
        )
        created = self.controller.create_person(
            {"displayed_name": "Scattershot Magician"}
        )
        self.assertEqual(
            "Scattershot",
            created["development_plan"]["schema"],
        )

    def test_random_policy_registers_the_random_selection(self):
        self.settings_controller.set_development_assignment_policy(
            DEVELOPMENT_ASSIGNMENT_RANDOM
        )

        with patch(
            "mage_maker.sections.development.models.random.choice",
            return_value="Material Crafting",
        ):
            created = self.controller.create_person(
                {"displayed_name": "Material Crafter"}
            )

        self.assertEqual(
            "Material Crafting",
            created["development_plan"]["schema"],
        )

    def test_prompt_policy_requires_an_explicit_strategy(self):
        self.settings_controller.set_development_assignment_policy(
            DEVELOPMENT_ASSIGNMENT_PROMPT
        )

        with self.assertRaisesRegex(
            ValueError,
            "Choose a development strategy",
        ):
            self.controller.create_person(
                {"displayed_name": "Unassigned Magician"}
            )

        created = self.controller.create_person(
            {
                "displayed_name": "Assigned Magician",
                "development_plan": {
                    "schema": "Three skills",
                    "focused_skills": [
                        "Charms",
                        "Flying",
                        "Perception",
                    ],
                },
            }
        )
        self.assertEqual(
            "Three skills",
            created["development_plan"]["schema"],
        )

    def test_focus_and_academic_progress_survive_save_and_reload(self):
        updated = self.controller.update_person(
            "existing",
            {
                "development_plan": {
                    "schema": "One skill",
                    "focused_skills": ["Flying"],
                    "academic_years_advanced": 3,
                }
            },
        )
        self.assertEqual(
            {
                "schema": "One skill",
                "blood_status_initialized": False,
                "focused_skills": ["Flying"],
                "academic_years_advanced": 3,
                "school_started": True,
                "school_years": [],
                "ledger_entries": [],
                "initial_eminence": [],
                "mortality_checked_through_age": None,
                "adult_years": [],
            },
            updated["development_plan"],
        )
        reloaded_database = JsonDatabase(self.database_path)
        reloaded_database.load()
        self.assertEqual(
            {
                "schema": "One skill",
                "blood_status_initialized": False,
                "focused_skills": ["Flying"],
                "academic_years_advanced": 3,
                "school_started": True,
                "school_years": [],
                "ledger_entries": [],
                "initial_eminence": [],
                "mortality_checked_through_age": None,
                "adult_years": [],
            },
            reloaded_database.read_person("existing")[
                "development_plan"
            ],
        )


class DevelopmentPromptWorkflowTests(unittest.TestCase):
    def test_prompt_policy_adds_the_selected_plan_before_creation(self):
        page = FakePromptPage()

        with patch(
            "mage_maker.sections.mages.page.DevelopmentStrategyDialog",
            FakeStrategyDialog,
        ):
            prepared = MagesPage.prepare_creation_values(
                page,
                {"displayed_name": "Prompted Magician"},
            )

        self.assertEqual(
            {
                "schema": "Social",
                "blood_status_initialized": False,
                "academic_years_advanced": 0,
                "school_started": False,
                "school_years": [],
                "ledger_entries": [],
                "initial_eminence": [],
                "mortality_checked_through_age": None,
                "adult_years": [],
            },
            prepared["development_plan"],
        )


if __name__ == "__main__":
    unittest.main()
