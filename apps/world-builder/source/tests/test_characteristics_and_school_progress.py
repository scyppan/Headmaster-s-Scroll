import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.characteristics import (
    CHARACTERISTIC_NAMES,
    CHARACTERISTIC_POINTS_TO_SPEND,
    characteristic_points_remaining,
    characteristics_are_complete,
    initial_values_are_complete,
    normalize_characteristics,
    randomized_characteristics,
)
from mage_maker.sections.development.initial_bonuses import (
    preferred_development_skills,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.settings.mage_groups import (
    default_mage_groups,
)
from mage_maker.sections.development.models import (
    visible_school_year_count,
)
from mage_maker.shell.person_list import PeopleList
from mage_maker.ui.theme import FIELD_BACKGROUND, SURFACE_MUTED


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
        self.visible = False
        self.colors = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)

    def set_text(self, text):
        self.text = text

    def set_colors(self, fill, hover_fill, foreground=None):
        self.colors = (fill, hover_fill, foreground)

    def pack(self, **options):
        self.visible = True

    def pack_forget(self):
        self.visible = False

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class FakeFrame:
    def __init__(self):
        self.visible = False

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class FakeLabel:
    def __init__(self):
        self.options = {}

    def configure(self, **options):
        self.options.update(options)


class CallRecorder:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


class CharacteristicModelTests(unittest.TestCase):
    def test_characteristic_catalog_matches_the_nine_starting_values(self):
        self.assertEqual(
            (
                "creativity",
                "equanimity",
                "charisma",
                "attractiveness",
                "strength",
                "agility",
                "intellect",
                "willpower",
                "fortitude",
            ),
            CHARACTERISTIC_NAMES,
        )
        self.assertEqual(8, CHARACTERISTIC_POINTS_TO_SPEND)

    def test_characteristics_start_at_one_and_require_all_eight_points(self):
        partial = {
            field_name: 1
            for field_name in CHARACTERISTIC_NAMES
        }
        complete = dict(partial)
        complete["creativity"] = 5
        complete["equanimity"] = 5

        self.assertEqual(
            8,
            characteristic_points_remaining(partial),
        )
        self.assertFalse(characteristics_are_complete(partial))
        self.assertEqual(
            0,
            characteristic_points_remaining(complete),
        )
        self.assertTrue(characteristics_are_complete(complete))
        self.assertEqual(
            complete,
            normalize_characteristics(
                complete,
                allow_uninitialized=False,
            ),
        )

    def test_characteristics_reject_values_over_five_or_over_budget(self):
        over_maximum = {
            field_name: 1
            for field_name in CHARACTERISTIC_NAMES
        }
        over_maximum["creativity"] = 6

        with self.assertRaisesRegex(ValueError, "between 1 and 5"):
            normalize_characteristics(over_maximum)

        over_budget = {
            field_name: 2
            for field_name in CHARACTERISTIC_NAMES
        }

        with self.assertRaisesRegex(ValueError, "more than 8"):
            normalize_characteristics(over_budget)

    def test_randomized_characteristics_spend_all_points_once(self):
        with patch(
            "mage_maker.sections.development.characteristics.random.choice",
            side_effect=(
                ["creativity"] * 4
                + ["equanimity"] * 4
            ),
        ):
            characteristics = randomized_characteristics()

        self.assertEqual(5, characteristics["creativity"])
        self.assertEqual(5, characteristics["equanimity"])
        self.assertTrue(
            characteristics_are_complete(characteristics)
        )

    def test_complete_initial_values_require_bonuses_and_characteristics(self):
        characteristics = {
            field_name: 1
            for field_name in CHARACTERISTIC_NAMES
        }
        characteristics["creativity"] = 5
        characteristics["equanimity"] = 5
        person = {
            "blood_status": "Pureblood",
            "developmental_environment": "",
            "parental_values": {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            },
            "initial_bonuses": {
                "initialized": True,
                "skill_selection_mode": "manual",
                "trait_selection_mode": "manual",
                "skill_bonuses": [
                    "Charms",
                    "Flying",
                    "Potions",
                ],
                "traits": [],
            },
            "characteristics": characteristics,
        }

        self.assertTrue(initial_values_are_complete(person))
        person["initial_bonuses"]["skill_bonuses"].pop()
        self.assertFalse(initial_values_are_complete(person))
        person["initial_bonuses"]["skill_bonuses"].append(
            "Potions"
        )
        person["characteristics"] = None
        self.assertFalse(initial_values_are_complete(person))


class CharacteristicViewTests(unittest.TestCase):
    def test_point_control_budget_caps_a_third_characteristic(self):
        view = object.__new__(DevelopmentView)
        view.loading = False
        view.characteristic_variables = {
            field_name: FakeVariable(1)
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_points_value = FakeVariable()
        view.characteristic_submit_button = FakeButton()
        view.characteristic_variables["creativity"].set(5)
        DevelopmentView.characteristic_changed(
            view,
            "creativity",
            5,
        )
        view.characteristic_variables["equanimity"].set(5)
        DevelopmentView.characteristic_changed(
            view,
            "equanimity",
            5,
        )
        view.characteristic_variables["charisma"].set(5)
        DevelopmentView.characteristic_changed(
            view,
            "charisma",
            5,
        )

        self.assertEqual(
            1,
            view.characteristic_variables["charisma"].get(),
        )
        self.assertEqual(
            "All 8 points assigned",
            view.characteristic_points_value.get(),
        )
        self.assertTrue(view.characteristic_submit_button.enabled)

    def test_point_controls_increment_decrement_and_disable_at_limits(self):
        view = object.__new__(DevelopmentView)
        view.loading = False
        view.characteristic_variables = {
            field_name: FakeVariable(1)
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_points_value = FakeVariable()
        view.characteristic_submit_button = FakeButton()
        view.characteristic_decrease_buttons = {
            field_name: FakeButton()
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_increase_buttons = {
            field_name: FakeButton()
            for field_name in CHARACTERISTIC_NAMES
        }

        DevelopmentView.adjust_characteristic(
            view,
            "creativity",
            1,
        )

        self.assertEqual(
            2,
            view.characteristic_variables["creativity"].get(),
        )
        self.assertTrue(
            view.characteristic_decrease_buttons[
                "creativity"
            ].enabled
        )

        DevelopmentView.adjust_characteristic(
            view,
            "creativity",
            -1,
        )

        self.assertEqual(
            1,
            view.characteristic_variables["creativity"].get(),
        )
        self.assertFalse(
            view.characteristic_decrease_buttons[
                "creativity"
            ].enabled
        )

        view.characteristic_variables["creativity"].set(5)
        view.characteristic_variables["equanimity"].set(5)
        DevelopmentView.update_characteristic_points(view)

        self.assertTrue(view.characteristic_submit_button.enabled)
        self.assertTrue(
            all(
                not button.enabled
                for button in
                view.characteristic_increase_buttons.values()
            )
        )

    def test_characteristics_use_compact_point_controls_not_scales(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertNotIn("tk.Scale", source)
        self.assertIn("decrease_button = SoftButton", source)
        self.assertIn("increase_button = SoftButton", source)

    def test_characteristic_labels_and_controls_share_one_row(self):
        source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn(
            "characteristic_stepper.grid(\n"
            "                row=0,\n"
            "                column=1,\n"
            '                sticky="e",',
            source,
        )
        self.assertGreaterEqual(source.count("width=24"), 2)
        self.assertNotIn(
            "characteristic_stepper.grid(\n"
            "                row=1,",
            source,
        )

    def test_submit_stores_a_complete_characteristic_assignment(self):
        view = object.__new__(DevelopmentView)
        view.characteristic_variables = {
            field_name: FakeVariable(1)
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_variables["creativity"].set(5)
        view.characteristic_variables["equanimity"].set(5)
        view.characteristics = None
        view.current_person = {"record_id": "mage-1"}
        view.update_initial_values_completion = lambda: True
        recorder = CallRecorder()
        view.notify_change = recorder

        DevelopmentView.submit_characteristics(view)

        self.assertTrue(
            characteristics_are_complete(view.characteristics)
        )
        self.assertEqual(
            view.characteristics,
            view.current_person["characteristics"],
        )
        self.assertEqual(1, recorder.calls)

    def test_first_activation_bakes_random_characteristics_once(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "record_id": "mage-1",
            "characteristics": None,
        }
        view.parental_values = {
            "generosity": 5,
            "permissiveness": 5,
            "wealth": 5,
        }
        view.characteristics = None
        view.loading = False
        view.update_parental_controls = lambda: None
        view.update_initial_bonus_controls = lambda: None
        view.update_initial_values_completion = lambda: True

        with patch(
            "mage_maker.sections.development.characteristics.random.choice",
            side_effect=(
                ["creativity"] * 4
                + ["equanimity"] * 4
            ),
        ):
            first_activation = DevelopmentView.activate(view)
            first_values = dict(view.characteristics)
            second_activation = DevelopmentView.activate(view)

        self.assertTrue(first_activation)
        self.assertFalse(second_activation)
        self.assertEqual(
            first_values,
            view.current_person["characteristics"],
        )
        self.assertTrue(characteristics_are_complete(first_values))

    def test_activation_reports_loaded_automatic_changes_once(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "record_id": "mage-1",
        }
        view.parental_values = {
            "generosity": 5,
            "permissiveness": 5,
            "wealth": 5,
        }
        view.characteristics = {
            field_name: 1
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristics["creativity"] = 5
        view.characteristics["equanimity"] = 5
        view.pending_automatic_changes = True
        view.loading = False
        view.update_parental_controls = lambda: None
        view.update_initial_bonus_controls = lambda: None
        view.update_initial_values_completion = lambda: True

        first_activation = DevelopmentView.activate(view)
        second_activation = DevelopmentView.activate(view)

        self.assertTrue(first_activation)
        self.assertFalse(second_activation)

    def test_saved_characteristics_are_read_only_until_edit(self):
        view = object.__new__(DevelopmentView)
        view.characteristics_editing = False
        view.update_characteristic_points = CallRecorder()

        DevelopmentView.handle_characteristics_action(view)

        self.assertTrue(view.characteristics_editing)
        self.assertEqual(
            1,
            view.update_characteristic_points.calls,
        )

    def test_baked_characteristics_are_plain_until_edit(self):
        view = object.__new__(DevelopmentView)
        view.characteristic_variables = {
            field_name: FakeVariable(1)
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_variables["creativity"].set(5)
        view.characteristic_variables["equanimity"].set(5)
        view.characteristic_points_value = FakeVariable()
        view.characteristic_submit_button = FakeButton()
        view.characteristic_reset_button = FakeButton()
        view.characteristic_decrease_buttons = {
            field_name: FakeButton()
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_increase_buttons = {
            field_name: FakeButton()
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristic_value_labels = {
            field_name: FakeLabel()
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristics_editing = False

        DevelopmentView.update_characteristic_points(view)

        self.assertTrue(
            all(
                not button.visible
                for button in (
                    list(
                        view.characteristic_decrease_buttons.values()
                    )
                    + list(
                        view.characteristic_increase_buttons.values()
                    )
                )
            )
        )
        self.assertTrue(
            all(
                label.options["bg"] == SURFACE_MUTED
                and label.options["highlightthickness"] == 0
                for label in view.characteristic_value_labels.values()
            )
        )

        view.characteristics_editing = True
        DevelopmentView.update_characteristic_points(view)

        self.assertTrue(
            all(
                button.visible
                for button in (
                    list(
                        view.characteristic_decrease_buttons.values()
                    )
                    + list(
                        view.characteristic_increase_buttons.values()
                    )
                )
            )
        )
        self.assertTrue(
            all(
                label.options["bg"] == FIELD_BACKGROUND
                and label.options["highlightthickness"] == 1
                for label in view.characteristic_value_labels.values()
            )
        )

    def test_initial_panel_and_people_rows_share_red_warning_borders(self):
        development_source = inspect.getsource(
            DevelopmentView.update_initial_values_completion
        )
        list_source = inspect.getsource(
            PeopleList.rebuild_rows
        )
        self.assertIn("LOCKED_BORDER", development_source)
        self.assertIn("initial_values_complete", development_source)
        self.assertIn("LOCKED_BORDER", list_source)
        self.assertIn(
            "initial_values_complete_by_id",
            list_source,
        )


class CraftingStrategyTests(unittest.TestCase):
    def test_each_crafting_strategy_has_only_its_named_skills(self):
        self.assertEqual(
            ["Artificing", "Alchemy"],
            preferred_development_skills(
                {"schema": "Material Crafting"}
            ),
        )
        self.assertEqual(
            ["Herbology", "Creatures", "Potions"],
            preferred_development_skills(
                {"schema": "Ingredient Crafting"}
            ),
        )
        self.assertEqual(
            ["Runes"],
            preferred_development_skills(
                {"schema": "Spell-crafting"}
            ),
        )


class SchoolProgressViewTests(unittest.TestCase):
    def test_current_school_year_is_visible_as_soon_as_it_starts(self):
        self.assertEqual(
            1,
            visible_school_year_count(True, 0),
        )
        header_source = inspect.getsource(
            DevelopmentView.build_header
        )
        self.assertNotIn("advance_year_button", header_source)
        self.assertNotIn("Advance one year", header_source)
        self.assertIn(
            '"Development years"',
            inspect.getsource(DevelopmentView.build_plan_panel),
        )
        self.assertIn(
            'text="Skip this year"',
            inspect.getsource(DevelopmentView.build_plan_panel),
        )

    def test_no_school_enables_calendar_year_adding(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField()
        view.school_started = False
        view.academic_years_advanced = 0
        view.adult_year_records = []
        view.active_development_page_index = 0
        view.current_person = {}
        view.advance_adulthood_button = FakeButton()
        view.year_tabs_container = object()
        view.previous_development_page_button = FakeButton()
        view.next_development_page_button = FakeButton()
        view.remove_latest_year_button = FakeButton()
        view.render_active_development_page = Mock()

        DevelopmentView.update_school_progress_controls(view)

        self.assertTrue(view.next_development_page_button.enabled)
        self.assertFalse(view.advance_adulthood_button.enabled)

    def test_no_school_advances_calendar_years_without_starting_school(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField()
        view.school_started = False
        view.academic_years_advanced = 0
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.advance_one_year(view)
        DevelopmentView.advance_to_adulthood(view)

        self.assertFalse(view.school_started)
        self.assertEqual(0, view.academic_years_advanced)
        self.assertEqual(1, len(view.adult_year_records))
        view.update_school_progress_controls.assert_called_once_with(
            select_latest=True
        )
        self.assertEqual(1, change_recorder.calls)

    def test_remove_control_only_appears_on_latest_year(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.school_started = True
        view.academic_years_advanced = 2
        view.adult_year_records = []
        view.active_development_page_index = 1
        view.current_person = {}
        view.advance_adulthood_button = FakeButton()
        view.year_tabs_container = object()
        view.previous_development_page_button = FakeButton()
        view.next_development_page_button = FakeButton()
        view.remove_latest_year_button = FakeButton()
        view.render_active_development_page = Mock()

        DevelopmentView.update_school_progress_controls(view)

        self.assertFalse(view.remove_latest_year_button.visible)

        view.active_development_page_index = 3
        DevelopmentView.update_school_progress_controls(view)

        self.assertTrue(view.remove_latest_year_button.visible)
        self.assertEqual(
            "Remove Year 3",
            view.remove_latest_year_button.text,
        )

    def test_selecting_school_refreshes_year_action_states(self):
        view = object.__new__(DevelopmentView)
        view.school_field = FakeSchoolField("Hogwarts")
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.school_changed(view)

        view.update_school_progress_controls.assert_called_once_with()
        self.assertEqual(1, change_recorder.calls)

    def test_initial_values_is_the_first_page_right_of_overview(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )
        plan_start = panel_source.index(
            "plan_panel = SectionPanel("
        )
        pages_start = panel_source.index(
            "page_panel = SectionPanel("
        )
        initial_start = panel_source.index(
            "self.initial_values_panel = tk.Frame("
        )
        plan_layout = panel_source[plan_start:pages_start]
        pages_layout = panel_source[pages_start:initial_start]
        initial_layout = panel_source[initial_start:]

        self.assertIn(
            "plan_panel = SectionPanel(\n"
            "            panels,",
            plan_layout,
        )
        self.assertIn(
            "row=0,\n"
            "            column=0,",
            plan_layout,
        )
        self.assertIn(
            "page_panel = SectionPanel(\n"
            "            panels,",
            pages_layout,
        )
        self.assertIn(
            "row=0,\n"
            "            column=1,",
            pages_layout,
        )
        self.assertIn(
            "self.initial_values_panel = tk.Frame(\n"
            "            self.year_tabs_container,",
            initial_layout,
        )
        self.assertIn(
            "row=0,\n"
            "            column=0,",
            initial_layout,
        )
        self.assertNotIn(
            "initial_values_panel = SectionPanel(",
            panel_source,
        )

    def test_initial_values_page_uses_compact_spacing(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )
        initial_start = panel_source.index(
            "self.initial_values_panel = tk.Frame("
        )
        initial_layout = panel_source[initial_start:]

        self.assertIn(
            "self.initial_values_panel = tk.Frame(\n"
            "            self.year_tabs_container,\n"
            "            bg=SURFACE_MUTED,\n"
            "            highlightbackground=BORDER_SOFT,\n"
            "            highlightthickness=2,\n"
            "            padx=12,\n"
            "            pady=8,",
            initial_layout,
        )
        self.assertIn("width=140,", initial_layout)
        self.assertIn("width=160,", initial_layout)
        self.assertIn(
            "initial_eminence_frame = tk.Frame(",
            initial_layout,
        )

    def test_development_years_use_compact_page_arrows(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn(
            "self.previous_development_page_button = SoftButton(",
            panel_source,
        )
        self.assertIn(
            "command=self.show_previous_development_page,",
            panel_source,
        )
        self.assertIn(
            "self.next_development_page_button = SoftButton(",
            panel_source,
        )
        self.assertIn(
            "command=self.show_next_development_page,",
            panel_source,
        )
        self.assertNotIn(
            "year_tab_buttons",
            panel_source,
        )

    def test_selects_are_compact_and_characteristics_have_a_divider(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )
        strategy_start = panel_source.index(
            "self.strategy_select = RoundedSelect("
        )
        focus_start = panel_source.index(
            "self.focus_frame = tk.Frame("
        )
        pages_start = panel_source.index(
            "page_panel = SectionPanel("
        )
        initial_start = panel_source.index(
            "self.initial_values_panel = tk.Frame("
        )
        divider_start = panel_source.index(
            "initial_characteristics_divider = tk.Frame("
        )
        characteristics_start = panel_source.index(
            "characteristics_section = tk.Frame("
        )
        strategy_layout = panel_source[
            strategy_start:focus_start
        ]
        focus_layout = panel_source[
            focus_start:pages_start
        ]
        initial_layout = panel_source[initial_start:]
        divider_layout = panel_source[
            divider_start:characteristics_start
        ]
        characteristics_layout = panel_source[
            characteristics_start:
        ]

        self.assertIn("width=184,", strategy_layout)
        self.assertIn('text="Random strategy"', strategy_layout)
        self.assertIn('sticky="w",', strategy_layout)
        self.assertIn("width=100,", focus_layout)
        self.assertIn("width=180,", focus_layout)
        self.assertIn(
            "row=0,\n"
            "                column=index,",
            focus_layout,
        )
        self.assertIn("width=140,", initial_layout)
        self.assertIn("width=160,", initial_layout)
        self.assertIn(
            "self.initial_values_panel.grid_columnconfigure(\n"
            "            (0, 2),",
            initial_layout,
        )
        self.assertIn("bg=BORDER_SOFT,", divider_layout)
        self.assertIn(
            "row=4,\n"
            "            column=0,\n"
            "            columnspan=3,\n"
            '            sticky="ew",',
            divider_layout,
        )
        self.assertIn(
            "row=5,\n"
            "            column=0,\n"
            "            columnspan=3,",
            characteristics_layout,
        )

    def test_remove_latest_school_year_returns_to_previous_visible_year(self):
        view = object.__new__(DevelopmentView)
        view.school_started = True
        view.academic_years_advanced = 3
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.remove_latest_school_year(view)

        self.assertTrue(view.school_started)
        self.assertEqual(2, view.academic_years_advanced)
        view.update_school_progress_controls.assert_called_once_with(
            select_latest=True
        )
        self.assertEqual(1, change_recorder.calls)

    def test_remove_year_one_returns_to_not_started(self):
        view = object.__new__(DevelopmentView)
        view.school_started = True
        view.academic_years_advanced = 0
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.remove_latest_school_year(view)

        self.assertFalse(view.school_started)
        self.assertEqual(0, view.academic_years_advanced)
        view.update_school_progress_controls.assert_called_once_with(
            select_latest=True
        )
        self.assertEqual(1, change_recorder.calls)

    def test_remove_year_seven_from_graduated_returns_to_year_six(self):
        view = object.__new__(DevelopmentView)
        view.school_started = True
        view.academic_years_advanced = 7
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.remove_latest_school_year(view)

        self.assertTrue(view.school_started)
        self.assertEqual(5, view.academic_years_advanced)
        view.update_school_progress_controls.assert_called_once_with(
            select_latest=True
        )
        self.assertEqual(1, change_recorder.calls)

    def test_remove_school_year_does_nothing_before_school_starts(self):
        view = object.__new__(DevelopmentView)
        view.school_started = False
        view.academic_years_advanced = 0
        view.update_school_progress_controls = Mock()
        change_recorder = CallRecorder()
        view.notify_change = change_recorder

        DevelopmentView.remove_latest_school_year(view)

        self.assertFalse(view.school_started)
        self.assertEqual(0, view.academic_years_advanced)
        view.update_school_progress_controls.assert_not_called()
        self.assertEqual(0, change_recorder.calls)

    def test_visible_school_year_count_includes_the_active_year(self):
        self.assertEqual(
            0,
            visible_school_year_count(False, 0),
        )
        self.assertEqual(
            1,
            visible_school_year_count(True, 0),
        )
        self.assertEqual(
            4,
            visible_school_year_count(True, 3),
        )
        self.assertEqual(
            7,
            visible_school_year_count(True, 7),
        )

    def test_allowance_summary_is_profile_ready_and_frugal_aware(self):
        view = object.__new__(DevelopmentView)
        view.parental_values = {
            "generosity": 4,
            "permissiveness": 5,
            "wealth": 3,
        }
        view.initial_bonuses = {"traits": ["Frugal"]}

        self.assertEqual(
            "1 Galleon and 4 sickles (includes Frugal)",
            DevelopmentView.monthly_allowance_text(view),
        )


class DevelopmentVersionMigrationTests(unittest.TestCase):
    def test_version_fifteen_adds_characteristics_and_school_state(self):
        temporary_directory = tempfile.TemporaryDirectory()
        database_path = (
            Path(temporary_directory.name) / "mage_maker.json"
        )
        groups = default_mage_groups()
        database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 15,
                        "database_version": "0.15.0",
                        "last_saved": None,
                    },
                    "_application_settings": {
                        "development_strategy_assignment": "random",
                        "mage_groups": groups,
                    },
                    "people": [
                        {
                            "record_id": "legacy-crafter",
                            "displayed_name": "Legacy Crafter",
                            "mage_group_id": groups[0]["group_id"],
                            "biological_mother_id": "",
                            "biological_father_id": "",
                            "biological_mother_status": "unknown",
                            "biological_father_status": "unknown",
                            "blood_status": "Pureblood",
                            "developmental_environment": "",
                            "parental_values": None,
                            "initial_bonuses": None,
                            "mate_ids": [],
                            "spouse_relationships": [],
                            "timeline_events": [],
                            "development_plan": {
                                "schema": "Crafting",
                                "academic_years_advanced": 0,
                            },
                        }
                    ],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        database = JsonDatabase(database_path)
        database.load()
        migrated = database.read_person("legacy-crafter")

        self.assertEqual(
            29,
            database.data["_database"]["schema_version"],
        )
        self.assertEqual(
            "Material Crafting",
            migrated["development_plan"]["schema"],
        )
        self.assertFalse(
            migrated["development_plan"]["school_started"]
        )
        self.assertIsNone(migrated["characteristics"])
        temporary_directory.cleanup()


if __name__ == "__main__":
    unittest.main()
