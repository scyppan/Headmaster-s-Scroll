import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.bonus_dialogs import (
    InitialSkillBonusDialog,
    TraitSelectionDialog,
)
from mage_maker.sections.development.initial_bonuses import (
    INITIAL_SELECTION_AUTOMATIC,
    INITIAL_SELECTION_MANUAL,
    STRATEGY_PREFERENCE_PROBABILITY,
    allowance_sickles,
    format_wizard_currency,
    initial_bonus_requirements,
    normalize_initial_bonuses,
    preferred_development_traits,
    randomized_initial_skills,
    randomized_initial_traits,
    reconcile_initial_bonuses,
    summarize_initial_skill_bonuses,
)
from mage_maker.sections.development.models import (
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    DEVELOPMENT_SKILLS_BY_ABILITY,
)
from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_MUGGLEBORN,
    BLOOD_STATUS_PUREBLOOD,
    DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
    DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.profile.page import PersonForm
from mage_maker.sections.development.traits import (
    TRAIT_DEFINITIONS,
    TRAIT_NAMES,
    trait_effect_text,
)
from mage_maker.sections.settings.mage_groups import (
    MAGE_GROUPS_SETTING_KEY,
    default_mage_groups,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeButton:
    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class FakeCheckbutton:
    def __init__(self):
        self.state = None

    def configure(self, **values):
        self.state = values.get("state", self.state)


class FakeFrame:
    def __init__(self):
        self.visible = None

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class InitialBonusModelTests(unittest.TestCase):
    def test_trait_catalog_matches_the_attached_export(self):
        self.assertEqual(23, len(TRAIT_DEFINITIONS))
        self.assertEqual("Star gazer", TRAIT_NAMES[0])
        self.assertEqual("Crafty", TRAIT_NAMES[-1])
        self.assertEqual(
            (
                "+9 sickles per month to your allowance under 17; "
                "+2 Galleons per month to your salary when employed "
                "and 17 or older"
            ),
            trait_effect_text("Frugal"),
        )
        self.assertEqual(
            "+3 Astronomy skill",
            trait_effect_text("Star gazer"),
        )
        self.assertEqual(
            "+3 Shielding subtype",
            trait_effect_text("Protective"),
        )

    def test_blood_status_sets_skill_trait_and_muggles_bonuses(self):
        parental_values = {
            "generosity": 5,
            "permissiveness": 5,
            "wealth": 5,
        }
        self.assertEqual(
            {
                "skill_bonus_count": 3,
                "trait_count": 0,
                "muggles_skill_bonus": 0,
            },
            initial_bonus_requirements(
                BLOOD_STATUS_PUREBLOOD,
                "",
                parental_values,
            ),
        )
        self.assertEqual(
            {
                "skill_bonus_count": 2,
                "trait_count": 1,
                "muggles_skill_bonus": 0,
            },
            initial_bonus_requirements(
                BLOOD_STATUS_HALFBLOOD,
                DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
                parental_values,
            ),
        )
        self.assertEqual(
            {
                "skill_bonus_count": 1,
                "trait_count": 2,
                "muggles_skill_bonus": 11,
            },
            initial_bonus_requirements(
                BLOOD_STATUS_HALFBLOOD,
                DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
                parental_values,
            ),
        )
        self.assertEqual(
            {
                "skill_bonus_count": 0,
                "trait_count": 3,
                "muggles_skill_bonus": 11,
            },
            initial_bonus_requirements(
                BLOOD_STATUS_MUGGLEBORN,
                "",
                parental_values,
            ),
        )

    def test_permissiveness_adjusts_the_default_trait_count(self):
        permissive = {
            "generosity": 5,
            "permissiveness": 7,
            "wealth": 5,
        }
        restrictive = {
            "generosity": 5,
            "permissiveness": 3,
            "wealth": 5,
        }
        self.assertEqual(
            1,
            initial_bonus_requirements(
                BLOOD_STATUS_PUREBLOOD,
                "",
                permissive,
            )["trait_count"],
        )
        self.assertEqual(
            0,
            initial_bonus_requirements(
                BLOOD_STATUS_HALFBLOOD,
                DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
                restrictive,
            )["trait_count"],
        )
        self.assertEqual(
            4,
            initial_bonus_requirements(
                BLOOD_STATUS_MUGGLEBORN,
                "",
                permissive,
            )["trait_count"],
        )

    def test_automatic_skill_selection_usually_follows_strategy(self):
        plan = {
            "schema": "One skill",
            "focused_skills": ["Potions"],
        }

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            selected = randomized_initial_skills(plan, 3)

        self.assertEqual(
            ["Potions", "Potions", "Potions"],
            selected,
        )

    def test_automatic_skill_selection_retains_a_random_exception(self):
        plan = {
            "schema": "Ability-focus",
            "focused_ability": "Power",
        }

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=STRATEGY_PREFERENCE_PROBABILITY,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            selected = randomized_initial_skills(plan, 1)

        self.assertEqual(["Alchemy"], selected)

    def test_automatic_skill_selection_uses_the_exact_ninety_percent_cutoff(self):
        plan = {
            "schema": "Ability-focus",
            "focused_ability": "Power",
        }

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=0.899999,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            selected = randomized_initial_skills(plan, 1)

        self.assertEqual(0.90, STRATEGY_PREFERENCE_PROBABILITY)
        self.assertEqual(["Charms"], selected)

    def test_governing_attribute_skill_groups_are_complete(self):
        self.assertEqual(
            tuple(DEVELOPMENT_ABILITY_OPTIONS),
            tuple(DEVELOPMENT_SKILLS_BY_ABILITY),
        )
        self.assertEqual(
            (
                "Charms",
                "Transfiguration",
                "Defense",
                "Dark Arts",
            ),
            DEVELOPMENT_SKILLS_BY_ABILITY["Power"],
        )
        self.assertEqual(
            (
                "Arithmancy",
                "Runes",
                "History",
                "Muggles",
            ),
            DEVELOPMENT_SKILLS_BY_ABILITY["Erudition"],
        )
        self.assertEqual(
            (
                "Potions",
                "Alchemy",
                "Artificing",
                "Flying",
                "Herbology",
            ),
            DEVELOPMENT_SKILLS_BY_ABILITY["Panache"],
        )
        self.assertEqual(
            (
                "Creatures",
                "Astronomy",
                "Divination",
                "Perception",
                "Social",
            ),
            DEVELOPMENT_SKILLS_BY_ABILITY["Naturalism"],
        )
        self.assertEqual(
            set(DEVELOPMENT_SKILL_OPTIONS),
            {
                skill
                for skills in DEVELOPMENT_SKILLS_BY_ABILITY.values()
                for skill in skills
            },
        )

    def test_automatic_trait_selection_uses_strategy_preferences(self):
        plan = {"schema": "Social"}

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            selected = randomized_initial_traits(plan, 2)

        self.assertEqual(
            ["People person", "Observant"],
            selected,
        )

    def test_automatic_trait_selection_deviates_only_on_random_branch(self):
        plan = {"schema": "Social"}
        preferred_traits = preferred_development_traits(plan)

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=STRATEGY_PREFERENCE_PROBABILITY,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            selected = randomized_initial_traits(plan, 1)

        self.assertNotIn(selected[0], preferred_traits)

    def test_skill_strategy_traits_follow_the_skill_governing_attribute(self):
        preferred_traits = preferred_development_traits(
            {
                "schema": "One skill",
                "focused_skills": ["Potions"],
            }
        )

        self.assertIn("Navigator", preferred_traits)
        self.assertIn("Green thumb", preferred_traits)
        self.assertIn("Inventive", preferred_traits)
        self.assertNotIn("Animal lover", preferred_traits)

    def test_manual_selections_survive_automatic_strategy_refresh(self):
        person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "developmental_environment": "",
            "parental_values": {
                "generosity": 5,
                "permissiveness": 8,
                "wealth": 5,
            },
        }
        stored = {
            "initialized": True,
            "skill_selection_mode": INITIAL_SELECTION_MANUAL,
            "trait_selection_mode": INITIAL_SELECTION_MANUAL,
            "skill_bonuses": [
                "Flying",
                "Charms",
                "Perception",
            ],
            "traits": ["Navigator"],
        }
        reconciled = reconcile_initial_bonuses(
            stored,
            person,
            {
                "schema": "One skill",
                "focused_skills": ["Potions"],
            },
            refresh_automatic=True,
        )
        self.assertEqual(
            ["Flying", "Charms", "Perception"],
            reconciled["skill_bonuses"],
        )
        self.assertEqual(["Navigator"], reconciled["traits"])

    def test_automatic_selections_refresh_for_a_new_strategy(self):
        person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "developmental_environment": "",
            "parental_values": {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            },
        }
        stored = {
            "initialized": True,
            "skill_selection_mode": INITIAL_SELECTION_AUTOMATIC,
            "trait_selection_mode": INITIAL_SELECTION_AUTOMATIC,
            "skill_bonuses": [
                "Flying",
                "Charms",
                "Perception",
            ],
            "traits": [],
        }

        with patch(
            "mage_maker.sections.development.initial_bonuses.random.random",
            return_value=0.0,
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            reconciled = reconcile_initial_bonuses(
                stored,
                person,
                {
                    "schema": "One skill",
                    "focused_skills": ["Potions"],
                },
                refresh_automatic=True,
            )

        self.assertEqual(
            "Potions",
            reconciled["skill_bonuses"][0],
        )
        self.assertEqual(
            1,
            len(set(reconciled["skill_bonuses"])),
        )
        self.assertEqual(
            ["Potions", "Potions", "Potions"],
            reconciled["skill_bonuses"],
        )

    def test_initial_bonus_normalization_preserves_repeated_skill_points(self):
        normalized = normalize_initial_bonuses(
            {
                "skill_bonuses": [
                    "Charms",
                    "Charms",
                    "Flying",
                ],
                "traits": [
                    "Frugal",
                    "Frugal",
                    "Curious",
                ],
            }
        )
        self.assertEqual(
            ["Charms", "Charms", "Flying"],
            normalized["skill_bonuses"],
        )
        self.assertEqual(
            ["Frugal", "Curious"],
            normalized["traits"],
        )
        self.assertEqual(
            "Charms +2, Flying +1",
            summarize_initial_skill_bonuses(
                normalized["skill_bonuses"]
            ),
        )

    def test_allowance_uses_product_and_frugal_bonus(self):
        parental_values = {
            "generosity": 4,
            "permissiveness": 5,
            "wealth": 3,
        }
        self.assertEqual(
            12,
            allowance_sickles(parental_values, []),
        )
        self.assertEqual(
            21,
            allowance_sickles(
                parental_values,
                ["Frugal"],
            ),
        )
        self.assertEqual(
            "1 Galleon and 4 sickles",
            format_wizard_currency(21),
        )
        self.assertEqual(
            "17 sickles",
            format_wizard_currency(17),
        )


class InitialBonusViewTests(unittest.TestCase):
    def test_first_development_visit_assigns_parental_values_and_bonuses(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "record_id": "new-magician",
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "developmental_environment": "",
            "parental_values": None,
            "initial_bonuses": None,
        }
        view.parental_values = None
        view.initial_bonuses = None
        view.loading = False
        view.development_plan = {
            "schema": "Scattershot",
            "academic_years_advanced": 0,
        }
        view.strategy_value = FakeVariable("Scattershot")
        view.blood_status_value = FakeVariable(
            BLOOD_STATUS_PUREBLOOD
        )
        view.developmental_environment_value = FakeVariable("")
        view.academic_years_advanced = 0
        view.available_people = lambda: [view.current_person]
        view.apply_parental_values_to_controls = lambda: None
        view.update_parental_controls = lambda: None
        view.update_initial_bonus_controls = lambda: None

        with patch(
            "mage_maker.sections.development.initial_values.random.randint",
            side_effect=[7, 8, 2],
        ), patch(
            "mage_maker.sections.development.initial_bonuses.random.choice",
            side_effect=lambda choices: choices[0],
        ):
            first_activation = DevelopmentView.activate(view)
            first_bonuses = dict(view.initial_bonuses)
            second_activation = DevelopmentView.activate(view)

        self.assertTrue(first_activation)
        self.assertFalse(second_activation)
        self.assertEqual(3, len(first_bonuses["skill_bonuses"]))
        self.assertEqual(1, len(first_bonuses["traits"]))

    def test_initial_values_panel_contains_selectable_bonus_lines(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )
        update_source = inspect.getsource(
            DevelopmentView.update_initial_bonus_controls
        )
        self.assertIn(
            'text="Developmental bonuses"',
            panel_source,
        )
        self.assertIn(
            "self.skill_bonus_button = SoftButton",
            panel_source,
        )
        self.assertIn(
            "self.trait_button = SoftButton",
            panel_source,
        )
        self.assertIn(
            '"No traits"',
            update_source,
        )
        self.assertNotIn(
            "Monthly allowance",
            panel_source,
        )
        profile_source = inspect.getsource(
            PersonForm.build_profile_page
        )
        self.assertIn(
            'text="Total eminence points"',
            profile_source,
        )


class InitialBonusDialogTests(unittest.TestCase):
    def test_skill_and_trait_choices_use_checkboxes(self):
        skill_source = inspect.getsource(
            InitialSkillBonusDialog.build_dialog
        )
        trait_source = inspect.getsource(
            TraitSelectionDialog.build_dialog
        )
        self.assertIn("tk.Checkbutton", skill_source)
        self.assertIn("tk.Checkbutton", trait_source)
        self.assertNotIn("tk.Listbox", skill_source)
        self.assertNotIn("tk.Listbox", trait_source)
        self.assertIn(
            "DEVELOPMENT_SKILLS_BY_ABILITY[ability]",
            skill_source,
        )
        self.assertIn("text=ability", skill_source)
        self.assertIn('text="−1"', skill_source)
        self.assertIn('text="+1"', skill_source)
        self.assertIn("trait_columns = 3", trait_source)
        self.assertIn(
            "trait_effect_text(definition)",
            trait_source,
        )
        self.assertNotIn("detail_panel", trait_source)

    def test_skill_dialog_restores_repeated_bonus_points(self):
        dialog = object.__new__(InitialSkillBonusDialog)
        dialog.required_count = 3
        dialog.selected_skills = [
            "Flying",
            "Flying",
            "Potions",
        ]
        dialog.skill_values = {
            skill: FakeVariable(False)
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_bonus_amounts = {
            skill: 0
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }

        InitialSkillBonusDialog.restore_selection(dialog)

        self.assertEqual(2, dialog.skill_bonus_amounts["Flying"])
        self.assertEqual(1, dialog.skill_bonus_amounts["Potions"])
        self.assertTrue(dialog.skill_values["Flying"].get())
        self.assertTrue(dialog.skill_values["Potions"].get())

    def test_skill_checkboxes_allow_three_points_on_one_skill(self):
        dialog = object.__new__(InitialSkillBonusDialog)
        dialog.required_count = 3
        dialog.skill_values = {
            skill: FakeVariable(False)
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_bonus_amounts = {
            skill: 0
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_label_values = {
            skill: FakeVariable(skill)
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_checkbuttons = {
            skill: FakeCheckbutton()
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_adjustment_frames = {
            skill: FakeFrame()
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_decrement_buttons = {
            skill: FakeButton()
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.skill_increment_buttons = {
            skill: FakeButton()
            for skill in DEVELOPMENT_SKILL_OPTIONS
        }
        dialog.selection_summary_value = FakeVariable()
        dialog.save_button = FakeButton()
        selected = "Flying"
        rejected = "Creatures"
        dialog.skill_values[selected].set(True)
        InitialSkillBonusDialog.selection_changed(
            dialog,
            selected,
        )
        InitialSkillBonusDialog.adjust_skill_bonus(
            dialog,
            selected,
            1,
        )
        InitialSkillBonusDialog.adjust_skill_bonus(
            dialog,
            selected,
            1,
        )
        dialog.skill_values[rejected].set(True)
        InitialSkillBonusDialog.selection_changed(
            dialog,
            rejected,
        )

        self.assertFalse(dialog.skill_values[rejected].get())
        self.assertEqual(
            "3 of 3 bonus points assigned",
            dialog.selection_summary_value.get(),
        )
        self.assertTrue(dialog.save_button.enabled)
        self.assertEqual(3, dialog.skill_bonus_amounts[selected])
        self.assertEqual(
            "Flying +3",
            dialog.skill_label_values[selected].get(),
        )
        self.assertEqual(
            ["Flying", "Flying", "Flying"],
            InitialSkillBonusDialog.selected_skill_bonuses(
                dialog
            ),
        )
        self.assertTrue(
            dialog.skill_adjustment_frames[selected].visible
        )
        self.assertEqual(
            "disabled",
            dialog.skill_checkbuttons[rejected].state,
        )
        self.assertEqual(
            "normal",
            dialog.skill_checkbuttons[selected].state,
        )

        InitialSkillBonusDialog.adjust_skill_bonus(
            dialog,
            selected,
            -1,
        )

        self.assertEqual(
            "2 of 3 bonus points assigned",
            dialog.selection_summary_value.get(),
        )
        self.assertFalse(dialog.save_button.enabled)
        self.assertEqual(2, dialog.skill_bonus_amounts[selected])
        self.assertTrue(all(
            checkbutton.state == "normal"
            for checkbutton in dialog.skill_checkbuttons.values()
        ))

    def test_trait_checkboxes_enforce_the_required_count(self):
        dialog = object.__new__(TraitSelectionDialog)
        dialog.required_count = 2
        dialog.trait_values = {
            definition["name"]: FakeVariable(False)
            for definition in TRAIT_DEFINITIONS
        }
        dialog.trait_checkbuttons = {
            definition["name"]: FakeCheckbutton()
            for definition in TRAIT_DEFINITIONS
        }
        dialog.selection_summary_value = FakeVariable()
        dialog.save_button = FakeButton()
        selected = [
            TRAIT_DEFINITIONS[0]["name"],
            TRAIT_DEFINITIONS[1]["name"],
        ]

        for trait_name in selected:
            dialog.trait_values[trait_name].set(True)

        rejected_index = 2
        rejected = TRAIT_DEFINITIONS[rejected_index]["name"]
        dialog.trait_values[rejected].set(True)
        TraitSelectionDialog.selection_changed(
            dialog,
            rejected_index,
        )

        self.assertFalse(dialog.trait_values[rejected].get())
        self.assertEqual(
            "2 of 2 selected",
            dialog.selection_summary_value.get(),
        )
        self.assertTrue(dialog.save_button.enabled)
        self.assertEqual(
            "disabled",
            dialog.trait_checkbuttons[rejected].state,
        )


class InitialBonusPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "mage_maker.json"
        )
        self.database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 15,
                        "database_version": "0.15.0",
                        "last_saved": None,
                    },
                    "_application_settings": {
                        "development_strategy_assignment": "random",
                        MAGE_GROUPS_SETTING_KEY: default_mage_groups(),
                    },
                    "people": [],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        self.database = JsonDatabase(self.database_path)
        self.database.load()
        self.controller = PeopleController(self.database)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_character_creation_leaves_initial_bonuses_unassigned(self):
        created = self.controller.create_person(
            {"displayed_name": "New Magician"}
        )
        self.assertIsNone(created["parental_values"])
        self.assertIsNone(created["initial_bonuses"])
        self.assertIsNone(created["characteristics"])

    def test_selected_initial_bonuses_persist(self):
        created = self.controller.create_person(
            {"displayed_name": "New Magician"}
        )
        stored_bonuses = {
            "initialized": True,
            "skill_selection_mode": INITIAL_SELECTION_MANUAL,
            "trait_selection_mode": INITIAL_SELECTION_MANUAL,
            "skill_bonuses": [
                "Charms",
                "Charms",
                "Charms",
            ],
            "traits": [],
        }
        updated = self.controller.update_person(
            created["record_id"],
            {"initial_bonuses": stored_bonuses},
        )
        self.assertEqual(
            normalize_initial_bonuses(stored_bonuses),
            updated["initial_bonuses"],
        )
        self.assertEqual(
            ["Charms", "Charms", "Charms"],
            updated["initial_bonuses"]["skill_bonuses"],
        )

    def test_version_fourteen_migrates_with_unassigned_bonuses(self):
        created = self.controller.create_person(
            {"displayed_name": "Legacy Magician"}
        )
        legacy_data = json.loads(
            self.database_path.read_text(encoding="utf-8")
        )
        legacy_data["_database"]["schema_version"] = 14
        legacy_data["_database"]["database_version"] = "0.14.0"
        legacy_data["people"][0].pop("initial_bonuses", None)
        self.database_path.write_text(
            json.dumps(legacy_data),
            encoding="utf-8",
        )
        migrated_database = JsonDatabase(self.database_path)
        migrated_database.load()
        migrated_person = migrated_database.read_person(
            created["record_id"]
        )
        self.assertEqual(
            29,
            migrated_database.data["_database"]["schema_version"],
        )
        self.assertIsNone(migrated_person["initial_bonuses"])


if __name__ == "__main__":
    unittest.main()
