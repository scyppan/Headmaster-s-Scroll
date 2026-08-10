import tkinter as tk
from copy import deepcopy
from functools import partial
from tkinter import messagebox

from mage_maker.core.dates import (
    historical_year_distance,
    historical_year_shift,
)
from mage_maker.core.wizarding_currency import format_monthly_salary
from mage_maker.sections.development.bonus_dialogs import (
    InitialSkillBonusDialog,
    TraitSelectionDialog,
)
from mage_maker.sections.development.event_eminence import (
    reconcile_person_event_eminence,
)
from mage_maker.sections.development.advancement_dialogs import (
    EminenceManagerDialog,
    JobDialog,
)
from mage_maker.sections.development.characteristics import (
    CHARACTERISTIC_BASE_VALUE,
    CHARACTERISTIC_MAXIMUM_VALUE,
    CHARACTERISTIC_NAMES,
    CHARACTERISTIC_POINTS_TO_SPEND,
    CHARACTERISTIC_REQUIRED_TOTAL,
    available_characteristic_buys,
    characteristic_value_after_buy,
    characteristic_points_remaining,
    editable_characteristic_buys,
    initial_values_are_complete,
    normalize_characteristic_name,
    normalize_characteristics,
    randomized_characteristics,
)
from mage_maker.sections.development.initial_bonuses import (
    INITIAL_SELECTION_MANUAL,
    allowance_sickles,
    format_wizard_currency,
    initial_bonus_requirements,
    normalize_initial_bonuses,
    preferred_development_skills,
    reconcile_initial_bonuses,
    summarize_initial_skill_bonuses,
    starting_allowance_sickles,
)
from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_OPTIONS,
    DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
    DEVELOPMENTAL_ENVIRONMENT_OPTIONS,
    PARENTAL_MODE_FULLY_RANDOMIZED,
    PARENTAL_MODE_OVERRIDE,
    PARENTAL_MODE_SHARED,
    PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
    PARENTAL_VALUE_NAMES,
    blood_status_options,
    initialize_parental_values,
    normalize_blood_status,
    normalize_developmental_environment,
    normalize_parental_values,
    parental_sibling_reference,
    parental_values_for_mode,
    randomized_blood_status,
    rebase_parental_values,
    resolved_blood_status,
    resolved_developmental_environment,
)
from mage_maker.sections.development.models import (
    ACADEMIC_YEARS_TO_ADULTHOOD,
    DEVELOPMENT_ABILITY_BY_SKILL,
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_SCHEMA_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    adult_year_calendar_year,
    adult_year_calendar_year_range,
    calendar_year_age_range,
    calculate_school_start_year,
    development_year_page_title,
    ensure_adult_year_records,
    development_skill_count,
    eminence_skill_counts,
    normalize_academic_years_advanced,
    normalize_adult_year_records,
    normalize_development_plan,
    normalize_eminence_records,
    normalize_job_records,
    normalize_development_skill,
    job_assignment_overlaps_year_range,
    normalize_school_started,
    normalize_school_year_records,
    randomized_development_plan,
    school_year_calendar_year,
    school_progress_text,
    suggested_job_start_date,
    total_eminence_points,
)
from mage_maker.sections.development.mortality import (
    simulate_mortality_to_database_date,
)
from mage_maker.sections.development.school_years import (
    ensure_adult_year_records_with_improvements,
    ensure_school_year_records,
    random_school_year_skill,
    reconcile_development_plan_characteristics,
    reconcile_school_year_electives,
    reconcile_school_year_characteristic_buys,
    rebuild_school_year_records,
    school_curriculum_year,
)
from mage_maker.sections.ledger.models import (
    normalize_ledger_entries,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.development.traits import trait_effect_text
from mage_maker.sections.profile.school_field import SchoolField
from mage_maker.sections.settings.simulation import (
    DEFAULT_DATABASE_DATE,
    DEFAULT_MORTALITY_TABLE,
    development_cycle_year,
    normalize_database_date,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_HOVER,
    LOCKED_BORDER,
    PRIMARY,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    RoundedEntry,
    RoundedSelect,
    SectionPanel,
    SoftButton,
)


class DevelopmentView(tk.Frame):
    def __init__(
        self,
        parent,
        game_database=None,
        change_command=None,
        people_provider=None,
        organization_provider=None,
        settings_provider=None,
        mortality_command=None,
        organization_create_command=None,
        organization_location_provider=None,
        event_provider=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.game_database = game_database
        self.change_command = change_command
        self.people_provider = people_provider
        self.organization_provider = organization_provider
        self.settings_provider = settings_provider
        self.mortality_command = mortality_command
        self.organization_create_command = (
            organization_create_command
        )
        self.organization_location_provider = (
            organization_location_provider
        )
        self.event_provider = event_provider
        self.loading = False
        self.birth_year = None
        self.birth_month = None
        self.birth_day = None
        self.current_person = {}
        self.development_plan = {
            "schema": "Scattershot",
            "academic_years_advanced": 0,
            "school_started": False,
        }
        self.academic_years_advanced = 0
        self.school_started = False
        self.school_year_records = []
        self.adult_year_records = []
        self.ledger_entries = []
        self.initial_eminence_records = []
        self.mortality_checked_through_age = None
        self.start_year_value = tk.StringVar(value="Unknown")
        self.strategy_value = tk.StringVar(value="Scattershot")
        self.blood_status_value = tk.StringVar(
            value=BLOOD_STATUS_OPTIONS[0]
        )
        self.developmental_environment_value = tk.StringVar(
            value=DEVELOPMENTAL_ENVIRONMENT_MAGICAL
        )
        self.parental_mode_value = tk.StringVar(
            value=PARENTAL_MODE_SHARED
        )
        self.parental_value_variables = {
            field_name: tk.StringVar()
            for field_name in PARENTAL_VALUE_NAMES
        }
        self.parental_values = None
        self.initial_bonuses = None
        self.characteristics = None
        self.pending_automatic_changes = False
        self.characteristics_editing = False
        self.skill_bonus_summary_value = tk.StringVar(
            value="Initial skill bonuses have not been assigned"
        )
        self.trait_summary_value = tk.StringVar(
            value="Traits have not been assigned"
        )
        self.muggles_bonus_summary_value = tk.StringVar()
        self.characteristic_points_value = tk.StringVar(
            value=(
                f"{CHARACTERISTIC_POINTS_TO_SPEND} "
                "points to spend"
            )
        )
        self.characteristic_variables = {
            field_name: tk.IntVar(
                value=CHARACTERISTIC_BASE_VALUE
            )
            for field_name in CHARACTERISTIC_NAMES
        }
        self.characteristic_value_labels = {}
        self.characteristic_decrease_buttons = {}
        self.characteristic_increase_buttons = {}
        self.active_year_tab = 0
        self.active_adult_year = 0
        self.active_development_page_index = 0
        self.development_page_by_person_id = {}
        self.year_placeholder_value = tk.StringVar()
        self.year_detail_heading_value = tk.StringVar()
        self.development_page_heading_value = tk.StringVar(
            value="Initial Values"
        )
        self.development_page_age_value = tk.StringVar()
        self.eminence_summary_value = tk.StringVar(
            value="No eminence earned"
        )
        self.initial_eminence_summary_value = tk.StringVar(
            value="No initial eminence"
        )
        self.adult_eminence_summary_value = tk.StringVar(
            value="No eminence earned"
        )
        self.job_summary_value = tk.StringVar(
            value="No jobs recorded"
        )
        self.year_ability_value = tk.StringVar(
            value=DEVELOPMENT_ABILITY_OPTIONS[0]
        )
        self.year_skipped_value = tk.BooleanVar(value=False)
        self.school_skip_note_value = tk.StringVar()
        self.year_characteristic_value = tk.StringVar(
            value=CHARACTERISTIC_NAMES[0].title()
        )
        self.year_characteristic_summary_value = tk.StringVar()
        self.year_core_courses_value = tk.StringVar(
            value="Core classes: None listed"
        )
        self.year_elective_heading_value = tk.StringVar(
            value="Electives: None available"
        )
        self.year_elective_count_value = tk.StringVar(
            value="0 selected"
        )
        self.year_elective_variables = {}
        self.year_elective_checkbuttons = {}
        self.year_approved_electives = []
        self.year_past_elective_identities = set()
        self.year_elective_limit = 0
        self.year_skill_values = [
            tk.StringVar(value=DEVELOPMENT_SKILL_OPTIONS[0]),
            tk.StringVar(value=DEVELOPMENT_SKILL_OPTIONS[0]),
        ]
        self.skill_values = [
            tk.StringVar(value=DEVELOPMENT_SKILL_OPTIONS[index])
            for index in range(3)
        ]
        self.ability_value = tk.StringVar(
            value=DEVELOPMENT_ABILITY_OPTIONS[0]
        )
        self.strategy_value.trace_add(
            "write",
            self.strategy_changed,
        )
        self.blood_status_value.trace_add(
            "write",
            self.blood_status_changed,
        )
        self.developmental_environment_value.trace_add(
            "write",
            self.developmental_environment_changed,
        )
        self.parental_mode_value.trace_add(
            "write",
            self.parental_mode_changed,
        )

        for skill_value in self.skill_values:
            skill_value.trace_add(
                "write",
                self.focus_selection_changed,
            )

        self.ability_value.trace_add(
            "write",
            self.focus_selection_changed,
        )
        self.year_ability_value.trace_add(
            "write",
            self.school_year_selection_changed,
        )
        self.year_characteristic_value.trace_add(
            "write",
            self.school_year_selection_changed,
        )

        for year_skill_value in self.year_skill_values:
            year_skill_value.trace_add(
                "write",
                self.school_year_selection_changed,
            )

        for parental_value in self.parental_value_variables.values():
            parental_value.trace_add(
                "write",
                self.parental_value_changed,
            )
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.build_header()
        self.build_plan_panel()

    def build_header(self):
        header = tk.Frame(self, bg=SURFACE)
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        header.grid_columnconfigure(0, weight=1)

        heading = tk.Label(
            header,
            text="Development Plan",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(16, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")

        self.advance_adulthood_button = SoftButton(
            header,
            text="Advance to modern day",
            command=self.advance_to_modern_day,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=190,
            height=38,
        )
        self.advance_adulthood_button.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(6, 0),
        )
        self.advance_adulthood_button.grid_remove()

    def build_plan_panel(self):
        panels = tk.Frame(self, bg=SURFACE)
        panels.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        panels.grid_rowconfigure(0, weight=1)
        panels.grid_columnconfigure(
            0,
            weight=2,
            uniform="development_panels",
            minsize=330,
        )
        panels.grid_columnconfigure(
            1,
            weight=3,
            uniform="development_panels",
            minsize=500,
        )

        plan_panel = SectionPanel(
            panels,
            "Development overview",
            "Academic placement and developmental direction.",
        )
        plan_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        plan_panel.content.grid_columnconfigure(0, weight=1)

        academic_row = tk.Frame(
            plan_panel.content,
            bg=SURFACE_MUTED,
        )
        academic_row.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        academic_row.grid_columnconfigure(0, weight=1)

        school_records = (
            self.game_database.schools()
            if self.game_database is not None
            and self.game_database.loaded
            else []
        )
        self.school_records = school_records
        self.school_field = SchoolField(
            academic_row,
            school_records,
            self.school_changed,
            SURFACE_MUTED,
        )
        self.school_field.grid(
            row=0,
            column=0,
            sticky="ew",
        )

        overview_details = tk.Frame(
            academic_row,
            bg=SURFACE_MUTED,
        )
        overview_details.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(16, 0),
        )
        overview_details.grid_columnconfigure((0, 1), weight=1)

        start_year_block = tk.Frame(
            overview_details,
            bg=SURFACE_MUTED,
        )
        start_year_block.grid(
            row=0,
            column=0,
            sticky="nw",
            padx=(0, 8),
        )
        self.start_year_label = tk.Label(
            start_year_block,
            text="Academic start year",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.start_year_label.grid(row=0, column=0, sticky="w")
        start_year_value_label = tk.Label(
            start_year_block,
            textvariable=self.start_year_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        start_year_value_label.grid(
            row=1,
            column=0,
            sticky="w",
            pady=(5, 0),
        )

        strategy_block = tk.Frame(
            overview_details,
            bg=SURFACE_MUTED,
        )
        strategy_block.grid(
            row=0,
            column=1,
            sticky="ne",
            padx=(8, 0),
        )
        strategy_label = tk.Label(
            strategy_block,
            text="Developmental strategy",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        strategy_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.strategy_select = RoundedSelect(
            strategy_block,
            self.strategy_value,
            DEVELOPMENT_SCHEMA_OPTIONS,
            background=SURFACE_MUTED,
            width=184,
            height=40,
            font=app_font(10),
        )
        self.strategy_select.grid(
            row=1,
            column=0,
            sticky="w",
        )
        self.random_strategy_button = SoftButton(
            strategy_block,
            text="Random strategy",
            command=self.randomly_select_strategy,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=40,
            font=app_font(9, "bold"),
        )
        self.random_strategy_button.grid(
            row=1,
            column=1,
            sticky="w",
            padx=(7, 0),
        )
        self.rebuild_development_years_button = SoftButton(
            strategy_block,
            text="Rebuild years",
            command=self.rebuild_development_years,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=34,
            font=app_font(9, "bold"),
        )
        self.rebuild_development_years_button.grid(
            row=2,
            column=1,
            sticky="w",
            padx=(7, 0),
            pady=(7, 0),
        )

        self.focus_frame = tk.Frame(
            plan_panel.content,
            bg=SURFACE_MUTED,
        )
        self.focus_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(20, 0),
        )
        self.focus_frame.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="development_focus_skills",
        )
        self.skill_blocks = []
        self.skill_labels = []
        self.skill_selects = []

        for index in range(3):
            skill_block = tk.Frame(
                self.focus_frame,
                bg=SURFACE_MUTED,
            )
            skill_block.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(
                    (0, 4)
                    if index == 0
                    else (4, 4)
                    if index == 1
                    else (4, 0)
                ),
            )
            skill_block.grid_columnconfigure(0, weight=1)
            skill_label = tk.Label(
                skill_block,
                text=f"Skill {index + 1}",
                bg=SURFACE_MUTED,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            skill_label.grid(
                row=0,
                column=0,
                sticky="ew",
                pady=(0, 4),
            )
            skill_select = RoundedSelect(
                skill_block,
                self.skill_values[index],
                DEVELOPMENT_SKILL_OPTIONS,
                background=SURFACE_MUTED,
                width=100,
                height=38,
                font=app_font(9),
            )
            skill_select.grid(
                row=1,
                column=0,
                sticky="ew",
            )
            self.skill_blocks.append(skill_block)
            self.skill_labels.append(skill_label)
            self.skill_selects.append(skill_select)

        self.ability_block = tk.Frame(
            self.focus_frame,
            bg=SURFACE_MUTED,
        )
        self.ability_block.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        ability_label = tk.Label(
            self.ability_block,
            text="Ability",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
            width=9,
        )
        ability_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 8),
        )
        self.ability_select = RoundedSelect(
            self.ability_block,
            self.ability_value,
            DEVELOPMENT_ABILITY_OPTIONS,
            background=SURFACE_MUTED,
            width=180,
            height=38,
            font=app_font(10),
        )
        self.ability_select.grid(
            row=0,
            column=1,
            sticky="w",
        )

        page_panel = SectionPanel(
            panels,
            "Development years",
            "Initial values and school advancement.",
        )
        self.school_years_panel = page_panel
        page_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        page_panel.content.grid_columnconfigure(0, weight=1)
        page_panel.content.grid_rowconfigure(1, weight=1)

        page_navigation = tk.Frame(
            page_panel.content,
            bg=SURFACE_MUTED,
        )
        page_navigation.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        page_navigation.grid_columnconfigure(
            (0, 2),
            weight=1,
            uniform="development_navigation_sides",
        )
        self.initial_development_page_button = SoftButton(
            page_navigation,
            text="Initial",
            command=self.show_initial_development_page,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=70,
            height=32,
            font=app_font(8, "bold"),
            padx=6,
        )
        self.initial_development_page_button.grid(
            row=0,
            column=0,
            sticky="w",
        )
        page_navigation_controls = tk.Frame(
            page_navigation,
            bg=SURFACE_MUTED,
            width=390,
            height=32,
        )
        page_navigation_controls.grid(
            row=0,
            column=1,
        )
        page_navigation_controls.grid_propagate(False)
        page_navigation_controls.grid_columnconfigure(
            1,
            weight=1,
        )
        self.previous_development_page_button = SoftButton(
            page_navigation_controls,
            text="<",
            command=self.show_previous_development_page,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=36,
            height=32,
            font=app_font(11, "bold"),
            padx=2,
        )
        self.previous_development_page_button.grid(
            row=0,
            column=0,
        )
        development_page_heading_panel = tk.Frame(
            page_navigation_controls,
            bg=SURFACE_MUTED,
        )
        development_page_heading_panel.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )
        development_page_heading_panel.grid_columnconfigure(0, weight=1)
        development_page_heading = tk.Label(
            development_page_heading_panel,
            textvariable=self.development_page_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="center",
        )
        development_page_heading.pack(side="left", expand=True)
        development_page_age = tk.Label(
            development_page_heading_panel,
            textvariable=self.development_page_age_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="center",
        )
        development_page_age.pack(side="left", padx=(5, 0))
        self.next_development_page_button = SoftButton(
            page_navigation_controls,
            text=">",
            command=self.show_next_development_page,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=36,
            height=32,
            font=app_font(11, "bold"),
            padx=2,
        )
        self.next_development_page_button.grid(
            row=0,
            column=2,
        )
        page_navigation_right = tk.Frame(
            page_navigation,
            bg=SURFACE_MUTED,
        )
        page_navigation_right.grid(
            row=0,
            column=2,
            sticky="e",
        )
        self.latest_development_page_button = SoftButton(
            page_navigation_right,
            text="Latest",
            command=self.show_latest_development_page,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=70,
            height=32,
            font=app_font(8, "bold"),
            padx=6,
        )
        self.latest_development_page_button.grid(
            row=0,
            column=0,
            sticky="e",
        )
        self.remove_latest_year_button = SoftButton(
            page_navigation_right,
            text="Remove year",
            command=self.remove_latest_school_year,
            background=SURFACE_MUTED,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=106,
            height=32,
            font=app_font(8, "bold"),
            padx=6,
        )
        self.remove_latest_year_button.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(6, 0),
        )
        self.remove_latest_year_button.grid_remove()
        self.year_tabs_container = tk.Frame(
            page_panel.content,
            bg=SURFACE_MUTED,
        )
        self.year_tabs_container.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.year_tabs_container.grid_rowconfigure(0, weight=1)
        self.year_tabs_container.grid_columnconfigure(0, weight=1)

        self.initial_values_panel = tk.Frame(
            self.year_tabs_container,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=2,
            padx=12,
            pady=8,
        )
        self.initial_values_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.initial_values_panel.grid_columnconfigure(
            (0, 2),
            weight=1,
            uniform="initial_value_status",
        )

        blood_status_block = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        blood_status_block.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )
        blood_status_label = tk.Label(
            blood_status_block,
            text="Blood status",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        blood_status_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        self.blood_status_select = RoundedSelect(
            blood_status_block,
            self.blood_status_value,
            BLOOD_STATUS_OPTIONS,
            background=SURFACE_MUTED,
            width=140,
            height=36,
            font=app_font(10),
        )
        self.blood_status_select.grid(
            row=1,
            column=0,
            sticky="w",
        )
        self.blood_status_text = tk.Label(
            blood_status_block,
            textvariable=self.blood_status_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
            padx=2,
            pady=8,
        )
        self.blood_status_text.grid(
            row=1,
            column=0,
            sticky="ew",
        )

        self.environment_block = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        self.environment_block.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(6, 0),
        )
        environment_label = tk.Label(
            self.environment_block,
            text="Developmental environment",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        environment_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        self.environment_select = RoundedSelect(
            self.environment_block,
            self.developmental_environment_value,
            DEVELOPMENTAL_ENVIRONMENT_OPTIONS,
            background=SURFACE_MUTED,
            width=160,
            height=36,
            font=app_font(10),
        )
        self.environment_select.grid(
            row=1,
            column=0,
            sticky="w",
        )

        parental_header = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        parental_header.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 4),
        )
        parental_header.grid_columnconfigure(0, weight=1)
        parental_heading = tk.Label(
            parental_header,
            text="Parental values",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        parental_heading.grid(row=0, column=0, sticky="ew")
        self.parental_handling_button = SoftButton(
            parental_header,
            text="Handling ▾",
            command=self.show_parental_handling_menu,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=30,
        )
        self.parental_handling_button.grid(
            row=0,
            column=1,
            sticky="e",
        )
        self.parental_handling_menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        parental_values_row = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        parental_values_row.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        parental_values_row.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="parental_values",
        )
        self.parental_value_entries = {}

        for index, field_name in enumerate(PARENTAL_VALUE_NAMES):
            value_block = tk.Frame(
                parental_values_row,
                bg=SURFACE_MUTED,
            )
            value_block.grid(
                row=0,
                column=index,
                sticky="ew",
                padx=(
                    (0, 5)
                    if index == 0
                    else (5, 5)
                    if index == 1
                    else (5, 0)
                ),
            )
            value_label = tk.Label(
                value_block,
                text=field_name.title(),
                bg=SURFACE_MUTED,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            value_label.grid(
                row=0,
                column=0,
                sticky="ew",
                pady=(0, 5),
            )
            value_entry = RoundedEntry(
                value_block,
                textvariable=self.parental_value_variables[
                    field_name
                ],
                background=SURFACE_MUTED,
                width=104,
                height=34,
                font=app_font(10),
                justify="center",
            )
            value_entry.grid(
                row=1,
                column=0,
                sticky="ew",
            )
            self.parental_value_entries[field_name] = value_entry

        initial_assignments = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        initial_assignments.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="new",
            pady=(8, 0),
        )
        initial_assignments.grid_columnconfigure(0, weight=1)
        initial_assignments_heading = tk.Label(
            initial_assignments,
            text="Developmental bonuses",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        initial_assignments_heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 4),
        )
        self.skill_bonus_summary = tk.Label(
            initial_assignments,
            textvariable=self.skill_bonus_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self.skill_bonus_summary.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=1,
        )
        self.skill_bonus_button = SoftButton(
            initial_assignments,
            text="Select",
            command=self.open_initial_skill_bonus_dialog,
            background=SURFACE_MUTED,
            width=72,
            height=30,
            font=app_font(9, "bold"),
        )
        self.skill_bonus_button.grid(
            row=1,
            column=1,
            sticky="e",
            padx=(8, 0),
        )
        self.trait_summary = tk.Label(
            initial_assignments,
            textvariable=self.trait_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            justify="left",
            wraplength=480,
        )
        self.trait_summary.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=1,
        )
        self.trait_button = SoftButton(
            initial_assignments,
            text="Select",
            command=self.open_trait_dialog,
            background=SURFACE_MUTED,
            width=72,
            height=30,
            font=app_font(9, "bold"),
        )
        self.trait_button.grid(
            row=2,
            column=1,
            sticky="e",
            padx=(8, 0),
        )
        self.muggles_bonus_summary = tk.Label(
            initial_assignments,
            textvariable=self.muggles_bonus_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.muggles_bonus_summary.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=1,
        )

        initial_characteristics_divider = tk.Frame(
            self.initial_values_panel,
            bg=BORDER_SOFT,
            height=1,
        )
        initial_characteristics_divider.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(8, 0),
        )

        characteristics_section = tk.Frame(
            self.initial_values_panel,
            bg=SURFACE_MUTED,
        )
        characteristics_section.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="new",
            pady=(6, 0),
        )
        characteristics_section.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="characteristics",
        )
        characteristics_heading = tk.Label(
            characteristics_section,
            text="Characteristics",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        characteristics_heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        characteristic_points = tk.Label(
            characteristics_section,
            textvariable=self.characteristic_points_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="e",
        )
        characteristic_points.grid(
            row=0,
            column=2,
            sticky="e",
        )

        for index, field_name in enumerate(CHARACTERISTIC_NAMES):
            characteristic_block = tk.Frame(
                characteristics_section,
                bg=SURFACE_MUTED,
            )
            characteristic_block.grid(
                row=(index // 3) + 1,
                column=index % 3,
                sticky="ew",
                padx=(
                    (0, 5)
                    if index % 3 == 0
                    else (5, 5)
                    if index % 3 == 1
                    else (5, 0)
                ),
                pady=(2, 0),
            )
            characteristic_block.grid_columnconfigure(0, weight=1)
            characteristic_label = tk.Label(
                characteristic_block,
                text=field_name.title(),
                bg=SURFACE_MUTED,
                fg=TEXT_DARK,
                font=app_font(9),
                anchor="w",
            )
            characteristic_label.grid(
                row=0,
                column=0,
                sticky="ew",
                padx=(0, 4),
            )
            characteristic_stepper = tk.Frame(
                characteristic_block,
                bg=SURFACE_MUTED,
            )
            characteristic_stepper.grid(
                row=0,
                column=1,
                sticky="e",
            )
            decrease_button = SoftButton(
                characteristic_stepper,
                text="−",
                command=partial(
                    self.adjust_characteristic,
                    field_name,
                    -1,
                ),
                background=SURFACE_MUTED,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=24,
                height=24,
                radius=7,
                font=app_font(10, "bold"),
                padx=0,
            )
            decrease_button.grid(
                row=0,
                column=0,
                padx=(0, 2),
            )
            characteristic_value = tk.Label(
                characteristic_stepper,
                textvariable=self.characteristic_variables[
                    field_name
                ],
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                font=app_font(10, "bold"),
                anchor="center",
                highlightbackground=BORDER_SOFT,
                highlightthickness=1,
                width=2,
                padx=3,
                pady=2,
            )
            characteristic_value.grid(row=0, column=1)
            increase_button = SoftButton(
                characteristic_stepper,
                text="+",
                command=partial(
                    self.adjust_characteristic,
                    field_name,
                    1,
                ),
                background=SURFACE_MUTED,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=24,
                height=24,
                radius=7,
                font=app_font(10, "bold"),
                padx=0,
            )
            increase_button.grid(
                row=0,
                column=2,
                padx=(2, 0),
            )
            self.characteristic_value_labels[field_name] = (
                characteristic_value
            )
            self.characteristic_decrease_buttons[field_name] = (
                decrease_button
            )
            self.characteristic_increase_buttons[field_name] = (
                increase_button
            )

        characteristic_buttons = tk.Frame(
            characteristics_section,
            bg=SURFACE_MUTED,
        )
        characteristic_buttons.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(4, 0),
        )
        self.characteristic_submit_button = SoftButton(
            characteristic_buttons,
            text="Edit",
            command=self.handle_characteristics_action,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=78,
            height=28,
            font=app_font(9, "bold"),
        )
        self.characteristic_submit_button.pack(side="left")
        self.characteristic_reset_button = SoftButton(
            characteristic_buttons,
            text="Start Over",
            command=self.reset_characteristics,
            background=SURFACE_MUTED,
            width=92,
            height=28,
            font=app_font(9, "bold"),
        )
        self.characteristic_reset_button.pack(
            side="left",
            padx=(6, 0),
        )
        self.year_detail_panel = tk.Frame(
            self.year_tabs_container,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        self.year_detail_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.year_detail_panel.grid_columnconfigure(1, weight=1)
        self.year_detail_panel.grid_rowconfigure(2, weight=1)
        year_detail_heading = tk.Label(
            self.year_detail_panel,
            textvariable=self.year_detail_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        year_detail_heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        improvement_header = tk.Frame(
            self.year_detail_panel,
            bg=SURFACE_MUTED,
        )
        improvement_header.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        improvement_header.grid_columnconfigure(0, weight=1)
        improvement_heading = tk.Label(
            improvement_header,
            text="Annual improvements",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        improvement_heading.grid(row=0, column=0, sticky="ew")
        self.school_skip_year_checkbutton = tk.Checkbutton(
            improvement_header,
            text="Skip this year",
            variable=self.year_skipped_value,
            command=self.year_skip_changed,
            bg=SURFACE_MUTED,
            activebackground=SURFACE_MUTED,
            fg=TEXT_DARK,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
            padx=0,
            pady=0,
        )
        self.school_skip_year_checkbutton.grid(
            row=0,
            column=1,
            sticky="e",
        )
        self.school_skip_note = tk.Label(
            improvement_header,
            textvariable=self.school_skip_note_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        self.school_skip_note.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(5, 0),
        )
        self.school_skip_note.grid_remove()
        year_improvements = tk.Frame(
            self.year_detail_panel,
            bg=SURFACE_MUTED,
        )
        year_improvements.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        year_improvements.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="school_year_improvements",
        )
        year_ability_block = tk.Frame(
            year_improvements,
            bg=SURFACE_MUTED,
        )
        year_ability_block.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        year_ability_label = tk.Label(
            year_ability_block,
            text="Ability",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        year_ability_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 3),
        )
        self.year_ability_select = RoundedSelect(
            year_ability_block,
            self.year_ability_value,
            DEVELOPMENT_ABILITY_OPTIONS,
            background=SURFACE_MUTED,
            width=154,
            height=32,
            font=app_font(9),
        )
        self.year_ability_select.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        year_characteristic_block = tk.Frame(
            year_improvements,
            bg=SURFACE_MUTED,
        )
        year_characteristic_block.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=4,
        )
        year_characteristic_label = tk.Label(
            year_characteristic_block,
            text="Characteristic buy",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        year_characteristic_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 3),
        )
        self.year_characteristic_select = RoundedSelect(
            year_characteristic_block,
            self.year_characteristic_value,
            [
                field_name.title()
                for field_name in CHARACTERISTIC_NAMES
            ],
            background=SURFACE_MUTED,
            width=154,
            height=32,
            font=app_font(9),
        )
        self.year_characteristic_select.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        year_characteristic_summary = tk.Label(
            year_characteristic_block,
            textvariable=self.year_characteristic_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        year_characteristic_summary.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(2, 0),
        )
        self.year_skill_selects = []

        for skill_index, year_skill_value in enumerate(
            self.year_skill_values
        ):
            skill_block = tk.Frame(
                year_improvements,
                bg=SURFACE_MUTED,
            )
            skill_block.grid(
                row=1,
                column=skill_index,
                sticky="ew",
                padx=(
                    (0, 4)
                    if skill_index == 0
                    else (4, 0)
                ),
                pady=(5, 0),
            )
            skill_label = tk.Label(
                skill_block,
                text=f"Skill {skill_index + 1}",
                bg=SURFACE_MUTED,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            skill_label.grid(
                row=0,
                column=0,
                sticky="ew",
                pady=(0, 3),
            )
            skill_select = RoundedSelect(
                skill_block,
                year_skill_value,
                DEVELOPMENT_SKILL_OPTIONS,
                background=SURFACE_MUTED,
                width=154,
                height=32,
                font=app_font(9),
            )
            skill_select.grid(
                row=1,
                column=0,
                sticky="ew",
            )
            self.year_skill_selects.append(skill_select)

        year_curriculum_divider = tk.Frame(
            self.year_detail_panel,
            bg=BORDER_SOFT,
            height=1,
        )
        year_curriculum_divider.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 9),
        )
        self.year_curriculum_frame = tk.Frame(
            self.year_detail_panel,
            bg=SURFACE_MUTED,
        )
        self.year_curriculum_frame.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        self.year_curriculum_frame.grid_columnconfigure(0, weight=1)
        year_core_courses = tk.Label(
            self.year_curriculum_frame,
            textvariable=self.year_core_courses_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=540,
        )
        year_core_courses.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        year_elective_header = tk.Frame(
            self.year_curriculum_frame,
            bg=SURFACE_MUTED,
        )
        year_elective_header.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 2),
        )
        year_elective_header.grid_columnconfigure(0, weight=1)
        year_elective_heading = tk.Label(
            year_elective_header,
            textvariable=self.year_elective_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        year_elective_heading.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        year_elective_count = tk.Label(
            year_elective_header,
            textvariable=self.year_elective_count_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="e",
        )
        year_elective_count.grid(
            row=0,
            column=1,
            sticky="e",
        )
        self.year_elective_options_frame = tk.Frame(
            self.year_curriculum_frame,
            bg=SURFACE_MUTED,
        )
        self.year_elective_options_frame.grid(
            row=2,
            column=0,
            sticky="ew",
        )
        self.year_elective_options_frame.grid_columnconfigure(
            (0, 1, 2, 3),
            weight=1,
            uniform="school_year_electives",
        )

        self.adult_detail_panel = tk.Frame(
            self.year_tabs_container,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        self.adult_detail_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.adult_detail_panel.grid_columnconfigure(0, weight=1)
        self.adult_detail_panel.grid_rowconfigure(0, weight=1)
        jobs_frame = tk.Frame(
            self.adult_detail_panel,
            bg=SURFACE_MUTED,
        )
        jobs_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        jobs_frame.grid_rowconfigure(1, weight=1)
        jobs_frame.grid_columnconfigure(0, weight=1)
        jobs_heading = tk.Label(
            jobs_frame,
            textvariable=self.job_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        jobs_heading.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 7),
        )
        self.job_list = tk.Listbox(
            jobs_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=PRIMARY,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.job_list.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="nsew",
        )
        add_job_button = SoftButton(
            jobs_frame,
            text="Add job",
            command=self.open_job_dialog,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=30,
            font=app_font(9, "bold"),
        )
        add_job_button.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(7, 0),
        )
        edit_job_button = SoftButton(
            jobs_frame,
            text="Edit selected",
            command=self.edit_selected_job,
            background=SURFACE_MUTED,
            width=102,
            height=30,
            font=app_font(9, "bold"),
        )
        edit_job_button.grid(
            row=2,
            column=1,
            sticky="w",
            padx=(7, 0),
            pady=(7, 0),
        )
        remove_job_button = SoftButton(
            jobs_frame,
            text="Remove selected",
            command=self.remove_selected_job,
            background=SURFACE_MUTED,
            width=112,
            height=30,
            font=app_font(9, "bold"),
        )
        remove_job_button.grid(
            row=2,
            column=2,
            sticky="e",
            pady=(7, 0),
        )

        self.school_year_empty_label = tk.Label(
            self.year_tabs_container,
            textvariable=self.year_placeholder_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            wraplength=540,
            padx=14,
            pady=14,
        )
        self.school_year_empty_label.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.year_detail_panel.grid_remove()
        self.adult_detail_panel.grid_remove()
        self.school_year_empty_label.grid_remove()
        self.update_focus_controls()
        self.update_blood_status_control()
        self.update_parental_controls()
        self.update_initial_bonus_controls()
        self.update_characteristic_points()
        self.update_school_progress_controls()
        self.update_initial_values_completion()

    def set_person(self, person):
        person_values = person if isinstance(person, dict) else {}

        if not hasattr(self, "development_page_by_person_id"):
            self.development_page_by_person_id = {}

        previous_person_id = str(
            getattr(self, "current_person", {}).get("record_id", "")
            or ""
        ).strip()

        if previous_person_id:
            self.development_page_by_person_id[previous_person_id] = int(
                getattr(self, "active_development_page_index", 0)
            )

        selected_person_id = str(
            person_values.get("record_id", "") or ""
        ).strip()
        loaded_development_values = {
            "school": person_values.get("school", ""),
            "blood_status": person_values.get("blood_status"),
            "developmental_environment": person_values.get(
                "developmental_environment"
            ),
            "parental_values": deepcopy(
                person_values.get("parental_values")
            ),
            "initial_bonuses": deepcopy(
                person_values.get("initial_bonuses")
            ),
            "characteristics": deepcopy(
                person_values.get("characteristics")
            ),
            "development_plan": deepcopy(
                person_values.get("development_plan")
            ),
        }
        plan = normalize_development_plan(
            person_values.get("development_plan"),
            default_schema="Scattershot",
        )
        self.loading = True
        self.pending_automatic_changes = False
        self.current_person = deepcopy(person_values)
        self.development_plan = deepcopy(plan)
        self.academic_years_advanced = plan[
            "academic_years_advanced"
        ]
        self.school_started = plan["school_started"]
        self.school_year_records = deepcopy(
            plan.get("school_years", [])
        )
        self.adult_year_records = deepcopy(
            plan.get("adult_years", [])
        )
        self.ledger_entries = deepcopy(
            plan.get("ledger_entries", [])
        )
        self.initial_eminence_records = deepcopy(
            plan.get("initial_eminence", [])
        )
        self.mortality_checked_through_age = plan.get(
            "mortality_checked_through_age"
        )
        self.active_year_tab = 0
        self.active_adult_year = 0
        self.active_development_page_index = (
            self.development_page_by_person_id.get(
                selected_person_id,
                0,
            )
        )
        self.strategy_value.set(plan["schema"])
        self.blood_status_value.set(
            resolved_blood_status(
                person_values,
                self.available_people(),
            )
        )
        self.developmental_environment_value.set(
            resolved_developmental_environment(
                person_values,
                self.available_people(),
            )
            or DEVELOPMENTAL_ENVIRONMENT_MAGICAL
        )
        self.parental_values = normalize_parental_values(
            person_values.get("parental_values")
        )
        self.initial_bonuses = normalize_initial_bonuses(
            person_values.get("initial_bonuses")
        )
        self.characteristics = normalize_characteristics(
            person_values.get("characteristics")
        )

        if self.parental_values is not None:
            self.parental_values = rebase_parental_values(
                self.current_person,
                self.available_people(),
                self.parental_values,
            )
            self.current_person["parental_values"] = deepcopy(
                self.parental_values
            )

        self.apply_parental_values_to_controls()
        focused_skills = plan.get("focused_skills", [])

        for index, skill_value in enumerate(self.skill_values):
            selected_skill = (
                focused_skills[index]
                if index < len(focused_skills)
                else DEVELOPMENT_SKILL_OPTIONS[index]
            )
            skill_value.set(selected_skill)

        self.ability_value.set(
            plan.get(
                "focused_ability",
                DEVELOPMENT_ABILITY_OPTIONS[0],
            )
        )
        self.birth_year = person_values.get("birth_year")
        self.birth_month = person_values.get("birth_month")
        self.birth_day = person_values.get("birth_day")
        self.school_field.set_value(person_values.get("school", ""))
        self.update_start_year()
        self.update_focus_controls()
        self.update_blood_status_control()
        self.update_parental_controls()
        self.update_initial_bonus_controls()
        self.set_characteristic_controls()
        self.refresh_initial_eminence()
        self.update_school_progress_controls()
        self.update_initial_values_completion()
        current_development_values = {
            "school": self.school_field.get_value(),
            "blood_status": self.current_person.get("blood_status"),
            "developmental_environment": self.current_person.get(
                "developmental_environment"
            ),
            "parental_values": deepcopy(self.parental_values),
            "initial_bonuses": deepcopy(self.initial_bonuses),
            "characteristics": deepcopy(self.characteristics),
            "development_plan": deepcopy(plan),
        }
        self.pending_automatic_changes = (
            loaded_development_values != current_development_values
        )
        self.loading = False

    def activate(self):
        if not self.current_person.get("record_id"):
            return False

        previous_loading = self.loading
        self.loading = True
        changed = bool(
            getattr(self, "pending_automatic_changes", False)
        )
        self.pending_automatic_changes = False

        development_plan = getattr(
            self,
            "development_plan",
            None,
        )
        can_initialize_blood_status = (
            isinstance(development_plan, dict)
            and hasattr(self, "blood_status_value")
            and hasattr(self, "available_people")
            and hasattr(self, "update_blood_status_control")
        )

        if can_initialize_blood_status and not bool(
            development_plan.get(
                "blood_status_initialized",
                False,
            )
        ):
            selected_status = randomized_blood_status(
                self.current_person,
                self.available_people(),
            )
            self.blood_status_value.set(selected_status)
            self.current_person["blood_status"] = selected_status
            self.current_person["developmental_environment"] = (
                normalize_developmental_environment(
                    self.current_person.get(
                        "developmental_environment",
                        "",
                    ),
                    selected_status,
                )
            )
            self.development_plan[
                "blood_status_initialized"
            ] = True
            self.update_blood_status_control()
            changed = True

        if self.parental_values is None:
            self.parental_values = initialize_parental_values(
                self.current_person,
                self.available_people(),
            )
            self.current_person["parental_values"] = deepcopy(
                self.parental_values
            )
            self.apply_parental_values_to_controls()
            changed = True

        if hasattr(self, "initial_bonuses"):
            previous_bonuses = deepcopy(self.initial_bonuses)
            self.initial_bonuses = reconcile_initial_bonuses(
                self.initial_bonuses,
                self.initial_bonus_person_values(),
                self.current_development_plan(),
            )
            self.current_person["initial_bonuses"] = deepcopy(
                self.initial_bonuses
            )
            changed = (
                changed
                or previous_bonuses != self.initial_bonuses
            )

        if getattr(self, "characteristics", None) is None:
            self.characteristics = randomized_characteristics()
            self.current_person["characteristics"] = deepcopy(
                self.characteristics
            )

            if hasattr(self, "characteristic_variables"):
                self.set_characteristic_controls()

            changed = True

        visible_years = DevelopmentView.visible_development_school_years(
            self
        )
        changed = (
            self.ensure_school_year_record_count(visible_years)
            or changed
        )
        previous_adult_year_records = deepcopy(
            getattr(self, "adult_year_records", [])
        )
        self.adult_year_records = (
            ensure_adult_year_records_with_improvements(
                previous_adult_year_records,
                len(previous_adult_year_records),
                self.school_year_generation_plan(),
                initial_characteristics=getattr(
                    self,
                    "characteristics",
                    None,
                ),
                school_year_records=getattr(
                    self,
                    "school_year_records",
                    [],
                ),
                manage_reading=False,
            )
        )
        if not isinstance(
            getattr(self, "development_plan", None),
            dict,
        ):
            self.development_plan = {}

        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        changed = (
            changed
            or previous_adult_year_records
            != self.adult_year_records
        )

        event_provider = getattr(self, "event_provider", None)

        if event_provider is not None:
            linked_events = event_provider(
                self.current_person.get("record_id")
            )
            changed = (
                self.reconcile_linked_event_eminence(
                    linked_events,
                    refresh_controls=False,
                )
                or changed
            )

        self.update_parental_controls()
        self.update_initial_bonus_controls()
        self.update_initial_values_completion()
        if (
            hasattr(self, "school_started")
            and hasattr(self, "academic_years_advanced")
        ):
            self.update_school_progress_controls()
        self.loading = previous_loading
        return changed

    def reconcile_linked_event_eminence(
        self,
        events,
        refresh_controls=True,
    ):
        if not self.current_person.get("record_id"):
            return False

        person_values = deepcopy(self.current_person)
        current_plan = self.current_development_plan()
        person_values["development_plan"] = current_plan
        reconciled_plan = reconcile_person_event_eminence(
            person_values,
            events,
        )

        if reconciled_plan == current_plan:
            return False

        self.development_plan = deepcopy(reconciled_plan)
        self.school_year_records = deepcopy(
            reconciled_plan.get("school_years", [])
        )
        self.adult_year_records = deepcopy(
            reconciled_plan.get("adult_years", [])
        )
        self.initial_eminence_records = deepcopy(
            reconciled_plan.get("initial_eminence", [])
        )
        self.current_person["development_plan"] = deepcopy(
            reconciled_plan
        )

        if refresh_controls:
            self.refresh_initial_eminence()
            self.update_school_progress_controls()

        return True

    def set_birth_date(self, birth_year, birth_month, birth_day):
        self.birth_year = birth_year
        self.birth_month = birth_month
        self.birth_day = birth_day
        self.current_person["birth_year"] = birth_year
        self.current_person["birth_month"] = birth_month
        self.current_person["birth_day"] = birth_day
        self.update_start_year()

        if self.parental_values is not None:
            previous_loading = self.loading
            previous_parental_values = deepcopy(
                self.parental_values
            )
            previous_initial_bonuses = deepcopy(
                self.initial_bonuses
            )
            self.loading = True
            self.parental_values = rebase_parental_values(
                self.current_person,
                self.available_people(),
                self.parental_values,
            )
            self.current_person["parental_values"] = deepcopy(
                self.parental_values
            )
            self.apply_parental_values_to_controls()
            self.update_parental_controls()
            self.reconcile_initial_bonus_assignments()
            if (
                previous_parental_values != self.parental_values
                or previous_initial_bonuses != self.initial_bonuses
            ):
                self.pending_automatic_changes = True
            self.loading = previous_loading
        else:
            self.update_parental_handling_menu()

        if hasattr(self, "school_year_records"):
            visible_years = DevelopmentView.visible_development_school_years(
                self
            )
            ledger_changed = self.ensure_school_year_record_count(
                visible_years
            )
            self.pending_automatic_changes = (
                self.pending_automatic_changes or ledger_changed
            )

        if hasattr(self, "year_tabs_container"):
            self.update_school_progress_controls()

    def set_parentage(self, relationship_values):
        if not isinstance(relationship_values, dict):
            return

        previous_loading = self.loading
        self.loading = True

        for field_name in (
            "biological_mother_id",
            "biological_father_id",
            "biological_mother_status",
            "biological_father_status",
        ):
            if field_name in relationship_values:
                self.current_person[field_name] = relationship_values[
                    field_name
                ]

        self.update_blood_status_control()

        if self.parental_values is not None:
            if (
                self.parental_mode_value.get()
                == PARENTAL_MODE_OVERRIDE
            ):
                try:
                    self.parental_values = (
                        self.parental_values_from_controls()
                    )
                except (TypeError, ValueError):
                    pass

            self.parental_values = rebase_parental_values(
                self.current_person,
                self.available_people(),
                self.parental_values,
            )
            self.current_person["parental_values"] = deepcopy(
                self.parental_values
            )
            self.apply_parental_values_to_controls()
            self.update_parental_controls()
            self.reconcile_initial_bonus_assignments()

        self.loading = previous_loading

    def get_values(self):
        plan = self.current_development_plan()
        blood_status = normalize_blood_status(
            self.blood_status_value.get()
        )
        parental_values = self.parental_values_from_controls()
        developmental_environment = normalize_developmental_environment(
            self.developmental_environment_value.get(),
            blood_status,
        )

        if self.initial_bonuses is not None:
            previous_loading = self.loading
            self.loading = True
            self.current_person["blood_status"] = blood_status
            self.current_person["developmental_environment"] = (
                developmental_environment
            )
            self.current_person["parental_values"] = deepcopy(
                parental_values
            )
            self.reconcile_initial_bonus_assignments()
            self.loading = previous_loading

        return {
            "school": self.school_field.get_value(),
            "blood_status": blood_status,
            "developmental_environment": developmental_environment,
            "parental_values": parental_values,
            "initial_bonuses": deepcopy(self.initial_bonuses),
            "characteristics": deepcopy(self.characteristics),
            "development_plan": plan,
        }

    def current_development_plan(self):
        plan = deepcopy(self.development_plan)
        schema = self.strategy_value.get()
        plan["schema"] = schema
        plan["academic_years_advanced"] = (
            self.academic_years_advanced
        )
        plan["school_started"] = bool(
            getattr(self, "school_started", False)
        )
        plan["calendar_year_progression"] = (
            DevelopmentView.uses_calendar_year_progression(self)
        )
        plan["school_years"] = deepcopy(
            getattr(self, "school_year_records", [])
        )
        plan["adult_years"] = deepcopy(
            getattr(self, "adult_year_records", [])
        )
        plan["ledger_entries"] = deepcopy(
            getattr(self, "ledger_entries", [])
        )
        plan["initial_eminence"] = deepcopy(
            getattr(self, "initial_eminence_records", [])
        )
        plan["mortality_checked_through_age"] = getattr(
            self,
            "mortality_checked_through_age",
            None,
        )
        required_skill_count = development_skill_count(schema)

        if required_skill_count:
            plan["focused_skills"] = [
                skill_value.get()
                for skill_value in self.skill_values[
                    :required_skill_count
                ]
            ]
            plan.pop("focused_ability", None)
        elif schema == "Ability-focus":
            plan["focused_ability"] = self.ability_value.get()
            plan.pop("focused_skills", None)
        else:
            plan.pop("focused_skills", None)
            plan.pop("focused_ability", None)

        return normalize_development_plan(plan)

    def parental_values_from_controls(self):
        if self.parental_values is None:
            return None

        stored_parental_values = deepcopy(self.parental_values)
        stored_parental_values["mode"] = (
            self.parental_mode_value.get()
        )

        for field_name in PARENTAL_VALUE_NAMES:
            stored_parental_values[field_name] = (
                self.parental_value_variables[
                    field_name
                ].get()
            )

        return normalize_parental_values(
            stored_parental_values,
            allow_uninitialized=False,
        )

    def school_changed(self):
        stored_plan = getattr(self, "development_plan", {})
        was_calendar_year_progression = bool(
            stored_plan.get("calendar_year_progression", False)
            if isinstance(stored_plan, dict)
            else False
        )

        if self.school_is_selected() and was_calendar_year_progression:
            self.development_plan.pop(
                "calendar_year_progression",
                None,
            )
            self.school_started = True
            self.academic_years_advanced = 0
            self.active_development_page_index = 1

        if not getattr(self, "loading", False):
            self.ensure_school_year_record_count(
                ACADEMIC_YEARS_TO_ADULTHOOD
            )

        if hasattr(self, "start_year_value"):
            self.update_start_year()
        self.update_school_progress_controls()
        self.notify_change()

    def school_is_selected(self):
        school_field = getattr(self, "school_field", None)

        if school_field is None:
            return False

        return bool(
            str(school_field.get_value() or "").strip()
        )

    def uses_calendar_year_progression(self):
        return False

    def development_start_year(self):
        return calculate_school_start_year(
            getattr(self, "birth_year", None),
            getattr(self, "birth_month", None),
            getattr(self, "birth_day", None),
        )

    def visible_development_school_years(self):
        return ACADEMIC_YEARS_TO_ADULTHOOD

    def visible_development_adult_years(self):
        return 0

    def strategy_changed(self, *arguments):
        if self.loading:
            return

        updated_plan = self.current_development_plan()
        required_skill_count = development_skill_count(
            updated_plan["schema"]
        )
        self.loading = True
        self.development_plan = deepcopy(updated_plan)
        focused_skills = updated_plan.get("focused_skills", [])

        for index in range(required_skill_count):
            self.skill_values[index].set(focused_skills[index])

        self.ability_value.set(
            updated_plan.get(
                "focused_ability",
                self.ability_value.get(),
            )
        )
        self.update_focus_controls()
        self.reconcile_initial_bonus_assignments(
            refresh_automatic=True
        )
        self.loading = False
        self.notify_change()

    def blood_status_changed(self, *arguments):
        if self.loading:
            return

        self.current_person["blood_status"] = normalize_blood_status(
            self.blood_status_value.get()
        )
        self.update_blood_status_control()
        self.reconcile_initial_bonus_assignments()
        self.notify_change()

    def developmental_environment_changed(self, *arguments):
        if self.loading:
            return

        self.current_person["developmental_environment"] = (
            normalize_developmental_environment(
                self.developmental_environment_value.get(),
                self.blood_status_value.get(),
            )
        )
        self.reconcile_initial_bonus_assignments()
        self.notify_change()

    def parental_mode_changed(self, *arguments):
        if self.loading or self.parental_values is None:
            return

        self.loading = True
        self.parental_values = parental_values_for_mode(
            self.current_person,
            self.available_people(),
            self.parental_values,
            self.parental_mode_value.get(),
        )
        self.current_person["parental_values"] = deepcopy(
            self.parental_values
        )
        self.apply_parental_values_to_controls()
        self.update_parental_controls()
        self.reconcile_initial_bonus_assignments()
        self.loading = False
        self.notify_change()

    def parental_value_changed(self, *arguments):
        if (
            self.loading
            or self.parental_values is None
            or self.parental_mode_value.get()
            != PARENTAL_MODE_OVERRIDE
        ):
            return

        try:
            self.parental_values = self.parental_values_from_controls()
        except (TypeError, ValueError):
            self.notify_change()
            return

        self.current_person["parental_values"] = deepcopy(
            self.parental_values
        )
        self.reconcile_initial_bonus_assignments()
        self.notify_change()

    def update_start_year(self):
        school_attended = self.school_is_selected()
        start_year = calculate_school_start_year(
            getattr(self, "birth_year", None),
            getattr(self, "birth_month", None),
            getattr(self, "birth_day", None),
        )

        if hasattr(self, "start_year_label"):
            self.start_year_label.configure(
                text=(
                    "Academic start year"
                    if school_attended
                    else "Development start year"
                )
            )

        self.start_year_value.set(
            "Unknown" if start_year in (None, "") else str(start_year)
        )

    def set_characteristic_controls(self):
        stored_values = (
            self.characteristics
            if self.characteristics is not None
            else {
                field_name: CHARACTERISTIC_BASE_VALUE
                for field_name in CHARACTERISTIC_NAMES
            }
        )
        previous_loading = self.loading
        self.loading = True
        self.characteristics_editing = self.characteristics is None

        for field_name in CHARACTERISTIC_NAMES:
            self.characteristic_variables[field_name].set(
                stored_values[field_name]
            )

        self.loading = previous_loading
        self.update_characteristic_points()

    def characteristic_changed(self, field_name, raw_value):
        if self.loading or field_name not in CHARACTERISTIC_NAMES:
            return

        try:
            requested_value = int(round(float(raw_value)))
        except (TypeError, ValueError):
            requested_value = CHARACTERISTIC_BASE_VALUE

        other_total = sum(
            self.characteristic_variables[
                other_field
            ].get()
            for other_field in CHARACTERISTIC_NAMES
            if other_field != field_name
        )
        maximum_available = min(
            CHARACTERISTIC_MAXIMUM_VALUE,
            CHARACTERISTIC_REQUIRED_TOTAL - other_total,
        )
        normalized_value = max(
            CHARACTERISTIC_BASE_VALUE,
            min(requested_value, maximum_available),
        )

        if (
            self.characteristic_variables[field_name].get()
            != normalized_value
        ):
            previous_loading = self.loading
            self.loading = True
            self.characteristic_variables[field_name].set(
                normalized_value
            )
            self.loading = previous_loading

        self.update_characteristic_points()

    def adjust_characteristic(self, field_name, delta):
        if self.loading or field_name not in CHARACTERISTIC_NAMES:
            return

        try:
            current_value = int(
                self.characteristic_variables[field_name].get()
            )
            adjustment = int(delta)
        except (TypeError, ValueError):
            current_value = CHARACTERISTIC_BASE_VALUE
            adjustment = 0

        self.characteristic_changed(
            field_name,
            current_value + adjustment,
        )

    def update_characteristic_points(self):
        if not hasattr(self, "characteristic_submit_button"):
            return

        draft_values = {
            field_name: self.characteristic_variables[
                field_name
            ].get()
            for field_name in CHARACTERISTIC_NAMES
        }
        remaining_points = characteristic_points_remaining(
            draft_values
        )
        editing = bool(
            getattr(self, "characteristics_editing", True)
        )

        if not editing:
            point_text = (
                f"All {CHARACTERISTIC_POINTS_TO_SPEND} "
                "points assigned"
            )
        elif remaining_points == 0:
            point_text = (
                f"All {CHARACTERISTIC_POINTS_TO_SPEND} "
                "points assigned"
            )
        elif remaining_points == 1:
            point_text = "1 point to spend"
        else:
            point_text = f"{remaining_points} points to spend"

        self.characteristic_points_value.set(point_text)
        self.characteristic_submit_button.set_text(
            "Save" if editing else "Edit"
        )
        self.characteristic_submit_button.set_enabled(
            not editing or remaining_points == 0
        )
        reset_button = getattr(
            self,
            "characteristic_reset_button",
            None,
        )

        if reset_button is not None:
            if editing:
                reset_button.pack(
                    side="left",
                    padx=(6, 0),
                )
            else:
                reset_button.pack_forget()

        decrease_buttons = getattr(
            self,
            "characteristic_decrease_buttons",
            {},
        )
        increase_buttons = getattr(
            self,
            "characteristic_increase_buttons",
            {},
        )
        value_labels = getattr(
            self,
            "characteristic_value_labels",
            {},
        )

        for field_name in CHARACTERISTIC_NAMES:
            current_value = draft_values[field_name]
            decrease_button = decrease_buttons.get(field_name)
            increase_button = increase_buttons.get(field_name)
            value_label = value_labels.get(field_name)

            if decrease_button is not None:
                if editing:
                    decrease_button.grid()
                    decrease_button.set_enabled(
                        current_value > CHARACTERISTIC_BASE_VALUE
                    )
                else:
                    decrease_button.grid_remove()

            if increase_button is not None:
                if editing:
                    increase_button.grid()
                    increase_button.set_enabled(
                        current_value
                        < CHARACTERISTIC_MAXIMUM_VALUE
                        and remaining_points > 0
                    )
                else:
                    increase_button.grid_remove()

            if value_label is not None:
                value_label.configure(
                    bg=(
                        FIELD_BACKGROUND
                        if editing
                        else SURFACE_MUTED
                    ),
                    highlightthickness=1 if editing else 0,
                    padx=3 if editing else 0,
                    pady=2 if editing else 0,
                )

    def handle_characteristics_action(self):
        if not self.characteristics_editing:
            self.characteristics_editing = True
            self.update_characteristic_points()
            return

        self.submit_characteristics()

    def submit_characteristics(self):
        draft_values = {
            field_name: self.characteristic_variables[
                field_name
            ].get()
            for field_name in CHARACTERISTIC_NAMES
        }

        try:
            submitted_values = normalize_characteristics(
                draft_values,
                allow_uninitialized=False,
            )
        except (TypeError, ValueError):
            self.update_characteristic_points()
            return

        self.characteristics = submitted_values
        self.current_person["characteristics"] = deepcopy(
            submitted_values
        )
        self.school_year_records = (
            reconcile_school_year_characteristic_buys(
                submitted_values,
                getattr(self, "school_year_records", []),
            )
        )
        current_plan = getattr(self, "development_plan", None)

        if current_plan is not None:
            current_plan["school_years"] = deepcopy(
                self.school_year_records
            )
            self.development_plan = (
                reconcile_development_plan_characteristics(
                    current_plan,
                    submitted_values,
                )
            )
            self.current_person["development_plan"] = deepcopy(
                self.development_plan
            )
        self.characteristics_editing = False
        self.update_characteristic_points()
        self.update_initial_values_completion()
        self.notify_change()

    def reset_characteristics(self):
        previous_loading = self.loading
        self.loading = True

        for field_name in CHARACTERISTIC_NAMES:
            self.characteristic_variables[field_name].set(
                CHARACTERISTIC_BASE_VALUE
            )

        self.characteristics = None
        self.current_person["characteristics"] = None
        self.characteristics_editing = True
        self.loading = previous_loading
        self.update_characteristic_points()
        self.update_initial_values_completion()
        self.notify_change()

    def school_progress_display_text(self):
        return school_progress_text(
            self.school_started,
            self.academic_years_advanced,
        )

    def update_school_progress_controls(
        self,
        select_latest=False,
    ):
        self.academic_years_advanced = (
            normalize_academic_years_advanced(
                self.academic_years_advanced
            )
        )
        self.school_started = normalize_school_started(
            self.school_started,
            self.academic_years_advanced,
        )
        school_selected = self.school_is_selected()
        visible_years = DevelopmentView.visible_development_school_years(
            self
        )

        if hasattr(self, "advance_adulthood_button"):
            self.advance_adulthood_button.set_enabled(
                (
                    school_selected
                    and calculate_school_start_year(
                        getattr(self, "birth_year", None),
                        getattr(self, "birth_month", None),
                        getattr(self, "birth_day", None),
                    )
                    is not None
                )
            )

        if not hasattr(self, "year_tabs_container"):
            return

        page_count = (
            1
            + visible_years
            + DevelopmentView.visible_development_adult_years(self)
        )

        if select_latest:
            self.active_development_page_index = page_count - 1
        else:
            self.active_development_page_index = max(
                0,
                min(
                    getattr(
                        self,
                        "active_development_page_index",
                        0,
                    ),
                    page_count - 1,
                ),
            )

        self.render_active_development_page()

        if hasattr(self, "previous_development_page_button"):
            self.previous_development_page_button.set_enabled(
                self.active_development_page_index > 0
            )

        if hasattr(self, "initial_development_page_button"):
            self.initial_development_page_button.set_enabled(
                self.active_development_page_index > 0
            )

        if hasattr(self, "latest_development_page_button"):
            self.latest_development_page_button.set_enabled(
                self.active_development_page_index < page_count - 1
            )

        if hasattr(self, "next_development_page_button"):
            has_existing_next_page = (
                getattr(
                    self,
                    "active_development_page_index",
                    0,
                )
                < page_count - 1
            )
            self.next_development_page_button.set_text(">")
            self.next_development_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.next_development_page_button.set_enabled(
                has_existing_next_page
            )

        if hasattr(self, "remove_latest_year_button"):
            self.remove_latest_year_button.grid_remove()

    def select_year_tab(self, year_number):
        visible_years = DevelopmentView.visible_development_school_years(
            self
        )

        if not 1 <= int(year_number) <= visible_years:
            return

        self.active_year_tab = int(year_number)
        self.active_adult_year = 0
        self.active_development_page_index = int(year_number)
        self.render_active_development_page()

    def show_development_record(self, page_type, year_number):
        try:
            normalized_year = int(year_number)
        except (TypeError, ValueError):
            return False

        visible_years = DevelopmentView.visible_development_school_years(
            self
        )

        if page_type == "school":
            if not 1 <= normalized_year <= visible_years:
                return False

            target_index = normalized_year
        elif page_type == "adult":
            adult_year_count = (
                DevelopmentView.visible_development_adult_years(self)
            )

            if not 1 <= normalized_year <= adult_year_count:
                return False

            target_index = visible_years + normalized_year
        else:
            return False

        self.active_development_page_index = target_index
        self.update_school_progress_controls()
        return True

    def development_page_count(self):
        return (
            1
            + DevelopmentView.visible_development_school_years(self)
            + DevelopmentView.visible_development_adult_years(self)
        )

    def recorded_death_date(self):
        person = getattr(self, "current_person", {})

        if not bool(person.get("deceased")):
            return None

        try:
            death_year = int(person.get("death_year"))
        except (TypeError, ValueError):
            return None

        death_month_value = person.get("death_month")

        try:
            death_month = int(death_month_value)
        except (TypeError, ValueError):
            death_month = 12

        try:
            death_day = int(person.get("death_day"))
        except (TypeError, ValueError):
            death_day = (
                31
                if death_month_value in (None, "")
                else 1
            )

        try:
            return normalize_database_date(
                {
                    "year": death_year,
                    "month": death_month,
                    "day": death_day,
                }
            )
        except ValueError:
            try:
                return normalize_database_date(
                    {
                        "year": death_year,
                        "month": death_month,
                        "day": 1,
                    }
                )
            except ValueError:
                return None

    def development_targets_at_death(self):
        death_date = self.recorded_death_date()

        if death_date is None:
            return None

        return self.modern_day_progress_targets(death_date)

    def can_add_next_development_page(self):
        page_count = self.development_page_count()
        active_page_index = getattr(
            self,
            "active_development_page_index",
            0,
        )
        return active_page_index < page_count - 1

    def render_active_development_page(self):
        if not hasattr(self, "initial_values_panel"):
            return

        self.initial_values_panel.grid_remove()
        self.year_detail_panel.grid_remove()
        self.adult_detail_panel.grid_remove()
        self.school_year_empty_label.grid_remove()
        visible_years = DevelopmentView.visible_development_school_years(
            self
        )
        page_index = max(
            0,
            min(
                self.active_development_page_index,
                self.development_page_count() - 1,
            ),
        )
        self.active_development_page_index = page_index
        person_id = str(
            getattr(self, "current_person", {}).get("record_id", "")
            or ""
        ).strip()

        if person_id:
            self.development_page_by_person_id[person_id] = page_index

        if page_index == 0:
            self.active_year_tab = 0
            self.active_adult_year = 0
            self.development_page_heading_value.set("Initial Values")
            self.development_page_age_value.set("")
            self.initial_values_panel.grid()
            return

        if page_index <= visible_years:
            self.active_year_tab = page_index
            self.active_adult_year = 0
            calendar_year = school_year_calendar_year(
                calculate_school_start_year(
                    self.birth_year,
                    self.birth_month,
                    self.birth_day,
                ),
                page_index,
            )
            self.development_page_heading_value.set(
                development_year_page_title(
                    {
                        "page_type": "school",
                        "school_year": page_index,
                        "calendar_year": calendar_year,
                        "calendar_end_year": (
                            historical_year_shift(calendar_year, 1)
                            if calendar_year is not None
                            else None
                        ),
                    }
                )
            )
            self.set_development_page_age(
                (page_index + 10, page_index + 11)
            )
            self.render_school_year_record()
            return

        adult_year = page_index - visible_years
        self.active_year_tab = 0
        self.active_adult_year = adult_year
        calendar_range = adult_year_calendar_year_range(
            DevelopmentView.development_start_year(self),
            adult_year,
        )
        calendar_year = (
            calendar_range[0]
            if calendar_range is not None
            else None
        )
        calendar_end_year = (
            calendar_range[1]
            if calendar_range is not None
            else None
        )
        self.development_page_heading_value.set(
            development_year_page_title(
                {
                    "page_type": "adult",
                    "adult_year": adult_year,
                    "calendar_year": calendar_year,
                    "calendar_end_year": calendar_end_year,
                    "school_attended": self.school_is_selected(),
                }
            )
        )
        self.set_development_page_age(
            (
                (0, 1)
                if adult_year == 1
                and not self.school_is_selected()
                and self.birth_year not in (None, "")
                else calendar_year_age_range(
                    calendar_year,
                    self.birth_year,
                    self.birth_month,
                    self.birth_day,
                )
            )
        )
        self.render_adult_year_record()

    def set_development_page_age(self, age_range):
        if not age_range:
            self.development_page_age_value.set("")
            return

        self.development_page_age_value.set(
            f"ages {age_range[0]} to {age_range[1]}"
        )

    def show_previous_development_page(self):
        if self.active_development_page_index <= 0:
            return

        self.active_development_page_index -= 1
        self.update_school_progress_controls()

    def show_initial_development_page(self):
        self.active_development_page_index = 0
        self.update_school_progress_controls()

    def show_latest_development_page(self):
        self.active_development_page_index = max(
            0,
            self.development_page_count() - 1,
        )
        self.update_school_progress_controls()

    def show_next_development_page(self):
        page_count = self.development_page_count()

        if self.active_development_page_index < page_count - 1:
            self.active_development_page_index += 1
            self.update_school_progress_controls()
        return

    def add_next_adult_year(self):
        if (
            not DevelopmentView.uses_calendar_year_progression(self)
            and normalize_academic_years_advanced(
                self.academic_years_advanced
            )
            < ACADEMIC_YEARS_TO_ADULTHOOD
        ):
            return

        previous_records = normalize_adult_year_records(
            getattr(self, "adult_year_records", [])
        )
        target_year_count = len(previous_records) + 1
        death_targets = self.development_targets_at_death()

        if (
            death_targets is not None
            and target_year_count > death_targets[1]
        ):
            return

        self.adult_year_records = (
            ensure_adult_year_records_with_improvements(
                previous_records,
                target_year_count,
                self.school_year_generation_plan(),
                initial_characteristics=getattr(
                    self,
                    "characteristics",
                    None,
                ),
                school_year_records=getattr(
                    self,
                    "school_year_records",
                    [],
                ),
                manage_reading=False,
            )
        )
        if not isinstance(
            getattr(self, "development_plan", None),
            dict,
        ):
            self.development_plan = {"schema": "Scattershot"}

        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        self.development_plan["calendar_year_progression"] = (
            DevelopmentView.uses_calendar_year_progression(self)
        )

        self.ensure_school_year_record_count(
            0
            if DevelopmentView.uses_calendar_year_progression(self)
            else ACADEMIC_YEARS_TO_ADULTHOOD
        )

        self.update_school_progress_controls(select_latest=True)
        self.notify_change()

    def school_year_record(self, year_number=None):
        selected_year = (
            self.active_year_tab
            if year_number is None
            else int(year_number)
        )

        for record in getattr(
            self,
            "school_year_records",
            [],
        ):
            if record.get("year") == selected_year:
                return record

        return None

    def school_curriculum_for_record(self, record):
        if not isinstance(record, dict):
            return None

        schools = getattr(self, "school_records", [])
        school_name = str(
            record.get("school", "") or ""
        ).strip()

        if not school_name:
            school_field = getattr(self, "school_field", None)
            school_name = (
                str(school_field.get_value() or "").strip()
                if school_field is not None
                else ""
            )

        return school_curriculum_year(
            schools,
            school_name,
            record.get("year"),
        )

    def render_school_year_curriculum(self, record):
        if not hasattr(self, "year_elective_options_frame"):
            return

        for child in self.year_elective_options_frame.winfo_children():
            child.destroy()

        self.year_elective_variables = {}
        self.year_elective_checkbuttons = {}
        self.year_approved_electives = []
        self.year_past_elective_identities = set()
        self.year_elective_limit = 0
        self.year_elective_count_value.set("0 selected")

        if bool(record.get("skipped", False)):
            self.year_core_courses_value.set(
                "Core classes: None (school skipped)"
            )
            self.year_elective_heading_value.set(
                "Electives: None (school skipped)"
            )
            return

        curriculum_year = self.school_curriculum_for_record(record)

        if curriculum_year is None:
            self.year_core_courses_value.set(
                "Core classes: None listed"
            )
            self.year_elective_heading_value.set(
                "Electives: None listed"
            )
            return

        core_courses = curriculum_year.get("core", [])
        approved_electives = curriculum_year.get(
            "electives",
            [],
        )
        elective_limit = int(
            curriculum_year.get("elective_limit", 0) or 0
        )
        selected_electives = reconcile_school_year_electives(
            record.get("electives", []),
            approved_electives,
            elective_limit,
        )
        current_year = int(record.get("year", 0) or 0)
        past_elective_identities = set()

        for previous_record in getattr(
            self,
            "school_year_records",
            [],
        ):
            try:
                previous_year = int(
                    previous_record.get("year", 0) or 0
                )
            except (TypeError, ValueError):
                continue

            if (
                previous_year >= current_year
                or bool(previous_record.get("skipped", False))
            ):
                continue

            past_elective_identities.update(
                str(elective or "").strip().casefold()
                for elective in previous_record.get(
                    "electives",
                    [],
                )
                if str(elective or "").strip()
            )

        self.year_core_courses_value.set(
            "Core classes: "
            + (", ".join(core_courses) if core_courses else "None")
        )
        self.year_approved_electives = list(approved_electives)
        self.year_past_elective_identities = (
            past_elective_identities
        )
        self.year_elective_limit = elective_limit

        if not approved_electives or elective_limit == 0:
            self.year_elective_heading_value.set(
                "Electives: None available"
            )
            self.year_elective_count_value.set("0 of 0 selected")
            return

        self.year_elective_heading_value.set(
            f"Electives (choose up to {elective_limit})"
        )
        electives_by_ability = {
            ability: []
            for ability in DEVELOPMENT_ABILITY_OPTIONS
        }

        for elective in approved_electives:
            try:
                elective_skill = normalize_development_skill(
                    elective
                )
            except ValueError:
                elective_skill = ""

            governing_ability = DEVELOPMENT_ABILITY_BY_SKILL.get(
                elective_skill,
                DEVELOPMENT_ABILITY_OPTIONS[-1],
            )
            electives_by_ability[governing_ability].append(elective)

        for column_index, ability in enumerate(
            DEVELOPMENT_ABILITY_OPTIONS
        ):
            ability_frame = tk.Frame(
                self.year_elective_options_frame,
                bg=SURFACE_MUTED,
            )
            ability_frame.grid(
                row=0,
                column=column_index,
                sticky="new",
                padx=(
                    (0, 5)
                    if column_index == 0
                    else (5, 5)
                    if column_index < 3
                    else (5, 0)
                ),
            )
            ability_frame.grid_columnconfigure(0, weight=1)
            ability_heading = tk.Label(
                ability_frame,
                text=ability,
                bg=SURFACE_MUTED,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            ability_heading.grid(
                row=0,
                column=0,
                sticky="ew",
                pady=(0, 2),
            )

            for row_index, elective in enumerate(
                electives_by_ability[ability],
                start=1,
            ):
                was_taken_before = (
                    elective.casefold()
                    in past_elective_identities
                )
                elective_background = (
                    PRIMARY_SOFT
                    if was_taken_before
                    else SURFACE_MUTED
                )
                elective_value = tk.BooleanVar(
                    self,
                    value=elective in selected_electives,
                )
                elective_checkbutton = tk.Checkbutton(
                    ability_frame,
                    text=elective,
                    variable=elective_value,
                    command=partial(
                        self.elective_selection_changed,
                        elective,
                    ),
                    bg=elective_background,
                    activebackground=elective_background,
                    fg=TEXT_DARK,
                    activeforeground=TEXT_DARK,
                    disabledforeground=(
                        TEXT_DARK
                        if was_taken_before
                        else TEXT_MUTED
                    ),
                    selectcolor=FIELD_BACKGROUND,
                    font=app_font(
                        9,
                        "bold" if was_taken_before else "normal",
                    ),
                    anchor="w",
                    justify="left",
                    borderwidth=0,
                    highlightthickness=0,
                    padx=4 if was_taken_before else 0,
                    pady=1,
                )
                elective_checkbutton.grid(
                    row=row_index,
                    column=0,
                    sticky="ew",
                    pady=1,
                )
                self.year_elective_variables[elective] = (
                    elective_value
                )
                self.year_elective_checkbuttons[elective] = (
                    elective_checkbutton
                )

        self.update_elective_checkbutton_states()

    def update_elective_checkbutton_states(self):
        selected_count = sum(
            1
            for elective_value in getattr(
                self,
                "year_elective_variables",
                {},
            ).values()
            if bool(elective_value.get())
        )
        elective_limit = max(
            0,
            int(getattr(self, "year_elective_limit", 0) or 0),
        )

        if hasattr(self, "year_elective_count_value"):
            self.year_elective_count_value.set(
                f"{selected_count} of {elective_limit} selected"
            )

        selection_limit_reached = selected_count >= elective_limit

        for elective, checkbutton in getattr(
            self,
            "year_elective_checkbuttons",
            {},
        ).items():
            elective_value = self.year_elective_variables[elective]
            checkbutton.configure(
                state=(
                    "normal"
                    if bool(elective_value.get())
                    or not selection_limit_reached
                    else "disabled"
                )
            )

    def elective_selection_changed(self, elective):
        if self.loading:
            return

        elective_values = getattr(
            self,
            "year_elective_variables",
            {},
        )
        selected_count = sum(
            1
            for elective_value in elective_values.values()
            if bool(elective_value.get())
        )
        elective_limit = max(
            0,
            int(getattr(self, "year_elective_limit", 0) or 0),
        )

        if selected_count > elective_limit:
            selected_value = elective_values.get(elective)

            if selected_value is not None:
                previous_loading = self.loading
                self.loading = True
                selected_value.set(False)
                self.loading = previous_loading

            self.update_elective_checkbutton_states()
            return

        self.update_elective_checkbutton_states()
        self.school_year_selection_changed()

    def render_school_year_record(self):
        record = self.school_year_record()

        if record is None:
            if hasattr(self, "year_placeholder_value"):
                self.year_placeholder_value.set(
                    f"Year {self.active_year_tab} development details "
                    "will be added here."
                )

            if hasattr(self, "year_detail_panel"):
                self.year_detail_panel.grid_remove()

            if hasattr(self, "school_year_empty_label"):
                self.school_year_empty_label.grid()

            return

        previous_loading = self.loading
        self.loading = True
        school_selected = self.school_is_selected()
        skipped = (
            bool(record.get("skipped", False))
            if school_selected
            else False
        )

        if hasattr(self, "year_detail_heading_value"):
            self.year_detail_heading_value.set(
                f"Year {record['year']}"
            )

        if hasattr(self, "year_ability_value"):
            self.year_ability_value.set(record["ability"])

        if hasattr(self, "year_skipped_value"):
            self.year_skipped_value.set(skipped)

        if hasattr(self, "school_skip_year_checkbutton"):
            if school_selected:
                self.school_skip_year_checkbutton.grid()
            else:
                self.school_skip_year_checkbutton.grid_remove()

        if hasattr(self, "school_skip_note"):
            person_name = str(
                self.current_person.get(
                    "displayed_name",
                    "This person",
                )
                or "This person"
            ).strip()
            self.school_skip_note_value.set(
                f"{person_name} skipped attending school this year."
            )

            if skipped and school_selected:
                self.school_skip_note.grid()
            else:
                self.school_skip_note.grid_remove()

        initial_characteristics = getattr(
            self,
            "characteristics",
            None,
        )
        characteristic_options = (
            editable_characteristic_buys(
                initial_characteristics,
                self.school_year_records,
                record["year"],
            )
            if initial_characteristics is not None
            else CHARACTERISTIC_NAMES
        )
        characteristic = normalize_characteristic_name(
            record.get("characteristic"),
            allow_blank=True,
        )

        if not characteristic and characteristic_options:
            characteristic = characteristic_options[0]

        if hasattr(self, "year_characteristic_select"):
            self.year_characteristic_select.set_values(
                [
                    field_name.title()
                    for field_name in characteristic_options
                ]
            )

        if hasattr(self, "year_characteristic_value"):
            self.year_characteristic_value.set(
                characteristic.title()
            )

        characteristic_after_buy = (
            characteristic_value_after_buy(
                initial_characteristics,
                self.school_year_records,
                record["year"],
            )
            if initial_characteristics is not None
            else None
        )
        self.year_characteristic_summary_value.set(
            (
                f"Becomes {characteristic_after_buy} of 5"
                if characteristic_after_buy is not None
                else "Choose one"
            )
        )

        if hasattr(self, "year_skill_values"):
            for index, skill_value in enumerate(
                self.year_skill_values
            ):
                skill_value.set(record["skills"][index])

        if hasattr(self, "year_core_courses_value"):
            self.render_school_year_curriculum(record)

        self.refresh_eminence_lists(
            record.get("eminence", [])
        )

        if hasattr(self, "year_placeholder_value"):
            self.year_placeholder_value.set(
                f"Ability: {record['ability']}\n"
                f"Skills: {record['skills'][0]}, "
                f"{record['skills'][1]}"
            )

        if hasattr(self, "year_detail_panel"):
            self.year_detail_panel.grid()

        if hasattr(self, "school_year_empty_label"):
            self.school_year_empty_label.grid_remove()

        self.set_annual_improvement_controls_enabled(
            True
        )
        self.loading = previous_loading

    def adult_year_record(self, adult_year=None):
        selected_year = (
            self.active_adult_year
            if adult_year is None
            else int(adult_year)
        )

        for record in getattr(
            self,
            "adult_year_records",
            [],
        ):
            if record.get("adult_year") == selected_year:
                return record

        return None

    def render_adult_year_record(self):
        record = self.adult_year_record()

        if record is None:
            self.year_placeholder_value.set(
                "Adult development details will be added here."
            )
            self.school_year_empty_label.grid()
            return

        previous_loading = self.loading
        self.loading = True
        self.refresh_eminence_lists(
            record.get("eminence", [])
        )
        jobs = self.active_job_assignments_for_adult_year(
            record["adult_year"]
        )
        self.visible_job_assignments = jobs
        self.job_list.delete(0, "end")

        for job in jobs:
            start_date = str(job["start_year"])

            if job["start_month"] is not None:
                start_date += f"-{job['start_month']:02d}"

            if job["start_day"] is not None:
                start_date += f"-{job['start_day']:02d}"

            end_date = "ongoing"

            if job["end_year"] is not None:
                end_date = str(job["end_year"])

                if job["end_month"] is not None:
                    end_date += f"-{job['end_month']:02d}"

                if job["end_day"] is not None:
                    end_date += f"-{job['end_day']:02d}"

            self.job_list.insert(
                "end",
                (
                    f"{job['organization_name']} — {job['title']} · "
                    f"{start_date} to {end_date} · "
                    f"{format_monthly_salary(job['salary'])}"
                ),
            )

        job_count = len(jobs)
        self.job_summary_value.set(
            f"Jobs · {job_count}"
            if job_count != 1
            else "Jobs · 1"
        )
        self.adult_detail_panel.grid()
        self.loading = previous_loading

    def active_job_assignments_for_adult_year(self, adult_year):
        calendar_range = adult_year_calendar_year_range(
            DevelopmentView.development_start_year(self),
            adult_year,
        )

        if calendar_range is None:
            record = self.adult_year_record(adult_year)
            return normalize_job_records(
                (record or {}).get("jobs", [])
            )

        jobs_by_id = {}

        for adult_record in getattr(
            self,
            "adult_year_records",
            [],
        ):
            for job in normalize_job_records(
                adult_record.get("jobs", [])
            ):
                if job_assignment_overlaps_year_range(
                    job,
                    calendar_range[0],
                    calendar_range[1],
                ):
                    jobs_by_id[job["record_id"]] = job

        return sorted(
            jobs_by_id.values(),
            key=lambda job: (
                job["start_year"],
                job["start_month"] or 1,
                job["start_day"] or 1,
                job["organization_name"].casefold(),
                job["title"].casefold(),
            ),
        )

    def refresh_eminence_lists(self, records):
        normalized_records = normalize_eminence_records(records)
        point_count = len(normalized_records)
        summary_text = (
            f"Eminence: {point_count}"
        )

        if normalized_records:
            skill_summary = ", ".join(
                f"{skill} ({count})"
                for skill, count in eminence_skill_counts(
                    normalized_records
                ).items()
            )
            summary_text += f"\n{skill_summary}"

        if self.active_year_tab:
            self.eminence_summary_value.set(summary_text)
        else:
            self.adult_eminence_summary_value.set(summary_text)

    def refresh_initial_eminence(self):
        normalized_records = normalize_eminence_records(
            getattr(self, "initial_eminence_records", [])
        )
        self.initial_eminence_records = normalized_records
        point_count = len(normalized_records)
        summary_text = f"Eminence: {point_count}"

        if normalized_records:
            skill_summary = ", ".join(
                f"{skill} ({count})"
                for skill, count in eminence_skill_counts(
                    normalized_records
                ).items()
            )
            summary_text += f"\n{skill_summary}"

        self.initial_eminence_summary_value.set(
            summary_text
        )

        if hasattr(self, "initial_eminence_button"):
            self.initial_eminence_button.set_text("Manage eminence")

    def open_eminence_dialog(self):
        EminenceManagerDialog(
            self,
            self.eminence_records_for_active_page(),
            self.eminence_default_skill(),
            self.save_eminence_records,
        )

    def eminence_records_for_active_page(self):
        if not self.active_year_tab and not self.active_adult_year:
            return normalize_eminence_records(
                self.initial_eminence_records
            )

        if self.active_year_tab:
            record = self.school_year_record()
        else:
            record = self.adult_year_record()

        if record is None:
            return []

        return normalize_eminence_records(
            record.get("eminence", [])
        )

    def eminence_default_skill(self):
        plan = self.current_development_plan()
        preferred_skills = preferred_development_skills(plan)

        if preferred_skills:
            return preferred_skills[0]

        record = (
            self.school_year_record()
            if self.active_year_tab
            else self.adult_year_record()
            if self.active_adult_year
            else None
        )

        if record is not None and record.get("skills"):
            return record["skills"][0]

        return random_school_year_skill(plan)

    def save_eminence_records(self, eminence_records):
        normalized_records = normalize_eminence_records(
            eminence_records
        )

        if not self.active_year_tab and not self.active_adult_year:
            self.initial_eminence_records = normalized_records
            self.development_plan["initial_eminence"] = deepcopy(
                normalized_records
            )
            self.refresh_initial_eminence()
            self.notify_change()
            return

        if self.active_year_tab:
            record = self.school_year_record()

            if record is None:
                return

            record["eminence"] = normalized_records
            self.school_year_records = normalize_school_year_records(
                self.school_year_records
            )
            self.development_plan["school_years"] = deepcopy(
                self.school_year_records
            )
            self.render_school_year_record()
            self.notify_change()
            return

        record = self.adult_year_record()

        if record is None:
            return

        record["eminence"] = normalized_records
        self.adult_year_records = normalize_adult_year_records(
            self.adult_year_records
        )
        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        self.render_adult_year_record()
        self.notify_change()

    def save_eminence_record(self, eminence_record):
        self.save_eminence_records(
            [
                *self.eminence_records_for_active_page(),
                eminence_record,
            ]
        )

    def remove_initial_eminence(self):
        if not getattr(self, "initial_eminence_records", []):
            return

        self.initial_eminence_records = []
        self.development_plan["initial_eminence"] = []
        self.refresh_initial_eminence()
        self.notify_change()

    def available_organizations(self):
        if self.organization_provider is None:
            return []

        organizations = self.organization_provider()
        return (
            list(organizations)
            if organizations is not None
            else []
        )

    def open_job_dialog(self):
        if not self.active_adult_year:
            return

        calendar_year_range = adult_year_calendar_year_range(
            DevelopmentView.development_start_year(self),
            self.active_adult_year,
        )
        calendar_year = (
            calendar_year_range[0]
            if calendar_year_range is not None
            else None
        )
        current_assignments = []

        for adult_year_record in getattr(
            self,
            "adult_year_records",
            [],
        ):
            current_assignments.extend(
                normalize_job_records(
                    adult_year_record.get("jobs", [])
                )
            )

        suggested_start_date = suggested_job_start_date(
            current_assignments,
            calendar_year,
            (
                calendar_year_range[1]
                if calendar_year_range is not None
                else calendar_year
            ),
        )
        JobDialog(
            self,
            self.available_organizations(),
            (
                suggested_start_date[0]
                if suggested_start_date is not None
                else calendar_year
            ),
            self.save_job_record,
            self.organization_create_command,
            self.organization_location_provider,
            self.all_job_assignments(),
            default_start_month=(
                suggested_start_date[1]
                if suggested_start_date is not None
                else None
            ),
            default_start_day=(
                suggested_start_date[2]
                if suggested_start_date is not None
                else None
            ),
        )

    def save_job_record(self, job_record):
        record = self.adult_year_record()

        if record is None:
            return

        normalized_job_record = normalize_job_records(
            [job_record]
        )[0]
        job_found = False

        for adult_record in self.adult_year_records:
            updated_jobs = []

            for existing_job in normalize_job_records(
                adult_record.get("jobs", [])
            ):
                if (
                    existing_job["record_id"]
                    == normalized_job_record["record_id"]
                ):
                    updated_jobs.append(normalized_job_record)
                    job_found = True
                else:
                    updated_jobs.append(existing_job)

            adult_record["jobs"] = normalize_job_records(updated_jobs)

        if not job_found:
            record["jobs"] = normalize_job_records(
                [
                    *record.get("jobs", []),
                    normalized_job_record,
                ]
            )
        self.adult_year_records = normalize_adult_year_records(
            self.adult_year_records
        )
        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        self.render_adult_year_record()
        self.notify_change()

    def edit_selected_job(self):
        selected = self.job_list.curselection()

        if not selected:
            return

        jobs = normalize_job_records(
            getattr(self, "visible_job_assignments", [])
        )
        selected_index = int(selected[0])

        if not 0 <= selected_index < len(jobs):
            return

        JobDialog(
            self,
            self.available_organizations(),
            jobs[selected_index]["start_year"],
            self.save_job_record,
            self.organization_create_command,
            self.organization_location_provider,
            self.all_job_assignments(),
            jobs[selected_index],
        )

    def all_job_assignments(self):
        assignments = []
        current_person_id = str(
            self.current_person.get("record_id", "") or ""
        )
        people = (
            self.people_provider()
            if self.people_provider is not None
            else []
        )

        for person in people or []:
            if not isinstance(person, dict):
                continue

            if str(person.get("record_id", "") or "") == (
                current_person_id
            ):
                continue

            development_plan = person.get(
                "development_plan",
                {},
            )

            if not isinstance(development_plan, dict):
                continue

            for adult_year_record in development_plan.get(
                "adult_years",
                [],
            ):
                if not isinstance(adult_year_record, dict):
                    continue

                assignments.extend(
                    normalize_job_records(
                        adult_year_record.get("jobs", [])
                    )
                )

        for adult_year_record in getattr(
            self,
            "adult_year_records",
            [],
        ):
            assignments.extend(
                normalize_job_records(
                    adult_year_record.get("jobs", [])
                )
            )

        return normalize_job_records(assignments)

    def remove_selected_job(self):
        selected = self.job_list.curselection()

        if not selected:
            return

        selected_index = int(selected[0])
        visible_jobs = normalize_job_records(
            getattr(self, "visible_job_assignments", [])
        )

        if not 0 <= selected_index < len(visible_jobs):
            return

        selected_job_id = visible_jobs[selected_index]["record_id"]

        for adult_record in self.adult_year_records:
            adult_record["jobs"] = [
                job
                for job in normalize_job_records(
                    adult_record.get("jobs", [])
                )
                if job["record_id"] != selected_job_id
            ]
        self.adult_year_records = normalize_adult_year_records(
            self.adult_year_records
        )
        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        self.render_adult_year_record()
        self.notify_change()

    def set_annual_improvement_controls_enabled(self, enabled):
        if hasattr(self, "year_ability_select"):
            self.year_ability_select.set_enabled(enabled)

        for skill_select in getattr(
            self,
            "year_skill_selects",
            [],
        ):
            skill_select.set_enabled(enabled)

        if hasattr(self, "year_characteristic_select"):
            self.year_characteristic_select.set_enabled(True)

    def year_skip_changed(self, *arguments):
        if self.loading:
            return

        record = self.school_year_record()

        if record is None:
            return

        if not self.school_is_selected():
            self.loading = True
            self.year_skipped_value.set(False)
            self.loading = False
            return

        skip_requested = bool(self.year_skipped_value.get())

        if skip_requested and not bool(record.get("skipped", False)):
            person_name = str(
                self.current_person.get(
                    "displayed_name",
                    "This person",
                )
                or "This person"
            ).strip()
            confirmed = messagebox.askyesno(
                "Skip school this year?",
                (
                    f"{person_name} will skip attending school this "
                    "year. They can still choose ability, skill, and "
                    "characteristic development.\n\n"
                    "Confirm this school year should be skipped."
                ),
                parent=self,
            )

            if not confirmed:
                self.loading = True
                self.year_skipped_value.set(False)
                self.loading = False
                return

        self.school_year_selection_changed()

    def school_year_selection_changed(self, *arguments):
        if self.loading:
            return

        if getattr(self, "active_adult_year", 0):
            return

        record = self.school_year_record()

        if record is None:
            return

        skipped = (
            self.year_skipped_value.get()
            if hasattr(self, "year_skipped_value")
            else bool(record.get("skipped", False))
        )
        elective_variables = getattr(
            self,
            "year_elective_variables",
            {},
        )
        approved_electives = getattr(
            self,
            "year_approved_electives",
            [],
        )
        selected_electives = (
            [
                elective
                for elective in approved_electives
                if elective in elective_variables
                and bool(elective_variables[elective].get())
            ]
            if elective_variables
            else deepcopy(record.get("electives", []))
        )
        electives_initialized = bool(
            record.get("electives_initialized", False)
        )

        if elective_variables:
            electives_initialized = True

        if skipped:
            selected_electives = []
            electives_initialized = False
        elif bool(record.get("skipped", False)):
            selected_electives = []
            electives_initialized = False

        updated_record = normalize_school_year_records(
            [
                {
                    "year": record["year"],
                    "school": record.get("school", ""),
                    "skipped": skipped,
                    "ability": self.year_ability_value.get(),
                    "skills": [
                        skill_value.get()
                        for skill_value in self.year_skill_values
                    ],
                    "characteristic": (
                        self.year_characteristic_value.get()
                        if hasattr(
                            self,
                            "year_characteristic_value",
                        )
                        else record.get("characteristic", "")
                    ),
                    "electives": selected_electives,
                    "electives_initialized": (
                        electives_initialized
                    ),
                    "assigned_books": record.get(
                        "assigned_books",
                        [],
                    ),
                    "books": record.get("books", []),
                    "eminence": record.get("eminence", []),
                }
            ]
        )[0]
        self.school_year_records = [
            (
                updated_record
                if stored_record["year"] == updated_record["year"]
                else stored_record
            )
            for stored_record in self.school_year_records
        ]
        self.development_plan["school_years"] = deepcopy(
            self.school_year_records
        )
        visible_years = DevelopmentView.visible_development_school_years(
            self
        )
        self.ensure_school_year_record_count(visible_years)
        self.render_school_year_record()
        self.notify_change()

    def school_year_generation_plan(self):
        plan = deepcopy(
            getattr(
                self,
                "development_plan",
                {"schema": "Scattershot"},
            )
        )
        plan["academic_years_advanced"] = getattr(
            self,
            "academic_years_advanced",
            0,
        )
        plan["school_started"] = bool(
            getattr(self, "school_started", False)
        )
        plan["school_years"] = deepcopy(
            getattr(self, "school_year_records", [])
        )
        plan["adult_years"] = deepcopy(
            getattr(self, "adult_year_records", [])
        )
        plan["initial_eminence"] = deepcopy(
            getattr(self, "initial_eminence_records", [])
        )
        plan["mortality_checked_through_age"] = getattr(
            self,
            "mortality_checked_through_age",
            None,
        )

        if hasattr(self, "strategy_value"):
            plan["schema"] = self.strategy_value.get()

        plan.setdefault("schema", "Scattershot")

        required_skill_count = development_skill_count(
            plan.get("schema", "Scattershot")
        )

        if required_skill_count and hasattr(self, "skill_values"):
            plan["focused_skills"] = [
                skill_value.get()
                for skill_value in self.skill_values[
                    :required_skill_count
                ]
            ]
        elif (
            plan.get("schema") == "Ability-focus"
            and hasattr(self, "ability_value")
        ):
            plan["focused_ability"] = self.ability_value.get()

        return normalize_development_plan(plan)

    def ensure_school_year_record_count(self, target_year_count):
        previous_records = normalize_school_year_records(
            getattr(self, "school_year_records", [])
        )
        previous_ledger_entries = normalize_ledger_entries(
            getattr(self, "ledger_entries", [])
        )
        school_field = getattr(self, "school_field", None)
        school_name = (
            school_field.get_value()
            if school_field is not None
            else str(
                getattr(self, "current_person", {}).get(
                    "school",
                    "",
                )
                or ""
            ).strip()
        )
        school_records = getattr(self, "school_records", None)
        generated_records = ensure_school_year_records(
            previous_records,
            target_year_count,
            self.school_year_generation_plan(),
            school_name=school_name,
            initial_characteristics=getattr(
                self,
                "characteristics",
                None,
            ),
            manage_books=False,
            schools=school_records,
        )
        self.school_year_records = generated_records
        initial_bonuses = getattr(
            self,
            "initial_bonuses",
            None,
        )
        selected_traits = (
            list(initial_bonuses["traits"])
            if initial_bonuses is not None
            else []
        )
        monthly_allowance = allowance_sickles(
            getattr(self, "parental_values", None),
            selected_traits,
        )
        starting_allowance = starting_allowance_sickles(
            getattr(self, "parental_values", None)
        )
        academic_start_year = DevelopmentView.development_start_year(self)
        self.ledger_entries = reconcile_development_ledger_entries(
            previous_ledger_entries,
            generated_records,
            getattr(self, "adult_year_records", []),
            monthly_allowance,
            starting_allowance,
            academic_start_year,
        )
        changed = (
            previous_records != generated_records
            or previous_ledger_entries != self.ledger_entries
        )

        if hasattr(self, "development_plan"):
            self.development_plan["school_years"] = deepcopy(
                generated_records
            )
            self.development_plan["ledger_entries"] = deepcopy(
                self.ledger_entries
            )

        return changed

    def set_ledger_entries(self, entries):
        normalized_entries = normalize_ledger_entries(entries)

        if normalized_entries == getattr(
            self,
            "ledger_entries",
            [],
        ):
            return

        self.ledger_entries = normalized_entries
        self.development_plan["ledger_entries"] = deepcopy(
            normalized_entries
        )
        self.notify_change()

    def monthly_allowance_text(self):
        selected_traits = (
            list(self.initial_bonuses["traits"])
            if self.initial_bonuses is not None
            else []
        )
        total_sickles = allowance_sickles(
            self.parental_values,
            selected_traits,
        )
        allowance_text = format_wizard_currency(total_sickles)
        frugal_text = (
            " (includes Frugal)"
            if "Frugal" in selected_traits
            else ""
        )
        return f"{allowance_text}{frugal_text}"

    def total_eminence_text(self):
        point_count = total_eminence_points(
            self.current_development_plan()
        )
        return (
            "1 point"
            if point_count == 1
            else f"{point_count} points"
        )

    def initial_values_complete(self):
        person_values = self.initial_bonus_person_values()
        person_values["initial_bonuses"] = deepcopy(
            self.initial_bonuses
        )
        person_values["characteristics"] = deepcopy(
            self.characteristics
        )
        return initial_values_are_complete(person_values)

    def update_initial_values_completion(self):
        if not hasattr(self, "initial_values_panel"):
            return True

        complete = (
            True
            if not self.current_person.get("record_id")
            else self.initial_values_complete()
        )
        self.initial_values_panel.configure(
            highlightbackground=(
                BORDER_SOFT if complete else LOCKED_BORDER
            ),
            highlightthickness=2,
        )
        return complete

    def randomly_select_strategy(self):
        randomized_plan = randomized_development_plan(
            self.strategy_value.get(),
            self.academic_years_advanced,
            school_started=self.school_started,
            school_years=self.school_year_records,
            adult_years=self.adult_year_records,
            ledger_entries=self.ledger_entries,
            initial_eminence=self.initial_eminence_records,
            mortality_checked_through_age=(
                self.mortality_checked_through_age
            ),
            calendar_year_progression=(
                DevelopmentView.uses_calendar_year_progression(self)
            ),
        )
        self.loading = True
        self.development_plan = deepcopy(randomized_plan)
        self.strategy_value.set(randomized_plan["schema"])
        focused_skills = randomized_plan.get("focused_skills", [])

        for index, skill_value in enumerate(self.skill_values):
            selected_skill = (
                focused_skills[index]
                if index < len(focused_skills)
                else DEVELOPMENT_SKILL_OPTIONS[index]
            )
            skill_value.set(selected_skill)

        self.ability_value.set(
            randomized_plan.get(
                "focused_ability",
                DEVELOPMENT_ABILITY_OPTIONS[0],
            )
        )
        self.update_focus_controls()
        self.reconcile_initial_bonus_assignments(
            refresh_automatic=True
        )
        self.loading = False
        self.notify_change()

    def rebuild_development_years(self):
        existing_records = normalize_school_year_records(
            getattr(self, "school_year_records", [])
        )

        if not existing_records:
            return False

        person_name = str(
            getattr(self, "current_person", {}).get(
                "displayed_name",
                "This person",
            )
            or "This person"
        ).strip()
        strategy_name = str(
            self.strategy_value.get() or "Scattershot"
        ).strip()
        confirmed = messagebox.askyesno(
            "Rebuild developmental years?",
            (
                f"Rebuild all developmental years for {person_name} "
                f"using {strategy_name}?\n\n"
                "Ability, skill, characteristic, and elective choices "
                "will be rerolled. School attendance, books, eminence, "
                "jobs, and ledger history will be retained."
            ),
            parent=self,
        )

        if not confirmed:
            return False

        school_records = getattr(self, "school_records", None)

        rebuilt_records = rebuild_school_year_records(
            existing_records,
            self.school_year_generation_plan(),
            initial_characteristics=getattr(
                self,
                "characteristics",
                None,
            ),
            schools=school_records,
        )
        self.school_year_records = rebuilt_records
        self.development_plan["school_years"] = deepcopy(
            rebuilt_records
        )
        self.update_school_progress_controls()
        self.notify_change()
        return True

    def advance_one_year(self):
        page_count = self.development_page_count()

        if self.active_development_page_index >= page_count - 1:
            return False

        self.active_development_page_index += 1
        self.update_school_progress_controls()
        return True

    def configured_database_date(self):
        provider = getattr(self, "settings_provider", None)

        if (
            provider is not None
            and hasattr(provider, "database_date")
        ):
            return provider.database_date()

        return deepcopy(DEFAULT_DATABASE_DATE)

    def configured_mortality_table(self):
        provider = getattr(self, "settings_provider", None)

        if (
            provider is not None
            and hasattr(provider, "mortality_table")
        ):
            return provider.mortality_table()

        return deepcopy(DEFAULT_MORTALITY_TABLE)

    def mortality_simulation_person(self):
        person = deepcopy(getattr(self, "current_person", {}))
        person["birth_year"] = getattr(self, "birth_year", None)
        person["birth_month"] = getattr(self, "birth_month", None)
        person["birth_day"] = getattr(self, "birth_day", None)
        return person

    def death_limited_database_date(self, database_date):
        death_date = self.recorded_death_date()

        if death_date is None:
            return database_date
        database_tuple = (
            database_date["year"],
            database_date["month"],
            database_date["day"],
        )
        death_tuple = (
            death_date["year"],
            death_date["month"],
            death_date["day"],
        )
        return death_date if death_tuple < database_tuple else database_date

    def simulate_mortality(self, database_date):
        result = simulate_mortality_to_database_date(
            self.mortality_simulation_person(),
            getattr(
                self,
                "mortality_checked_through_age",
                None,
            ),
            self.configured_mortality_table(),
            database_date,
        )
        self.mortality_checked_through_age = result[
            "checked_through_age"
        ]
        if hasattr(self, "development_plan"):
            self.development_plan[
                "mortality_checked_through_age"
            ] = self.mortality_checked_through_age

        if not result["died"]:
            return result

        death_month = getattr(self, "birth_month", None)
        death_day = getattr(self, "birth_day", None)
        mortality_values = {
            "deceased": True,
            "death_year": result["death_year"],
            "death_month": death_month or "",
            "death_day": (
                death_day
                if death_month not in (None, "")
                else ""
            ),
        }
        self.current_person.update(mortality_values)

        if self.mortality_command is not None:
            self.mortality_command(deepcopy(mortality_values))

        return result

    def modern_day_progress_targets(self, database_date):
        academic_start_year = DevelopmentView.development_start_year(self)

        if academic_start_year is None:
            return 0, 0

        target_cycle_year = development_cycle_year(database_date)

        if target_cycle_year < academic_start_year:
            return 0, 0

        try:
            elapsed_development_years = historical_year_distance(
                academic_start_year,
                target_cycle_year,
            )
            graduation_year = historical_year_shift(
                academic_start_year,
                ACADEMIC_YEARS_TO_ADULTHOOD,
            )
        except ValueError:
            return 0, 0

        if DevelopmentView.uses_calendar_year_progression(self):
            if target_cycle_year < graduation_year:
                return 0, 0

            return (
                0,
                max(
                    1,
                    historical_year_distance(
                        graduation_year,
                        target_cycle_year,
                    ),
                ),
            )

        school_year_count = min(
            ACADEMIC_YEARS_TO_ADULTHOOD,
            elapsed_development_years + 1,
        )
        adult_year_count = 0

        if target_cycle_year >= graduation_year:
            adult_year_count = max(
                1,
                historical_year_distance(
                    graduation_year,
                    target_cycle_year,
                ),
            )

        return school_year_count, adult_year_count

    def advance_to_modern_day(self):
        database_date = self.configured_database_date()
        self.simulate_mortality(database_date)
        target_date = self.death_limited_database_date(database_date)
        target_school_years, target_adult_years = (
            self.modern_day_progress_targets(target_date)
        )
        existing_school_years = (
            DevelopmentView.visible_development_school_years(self)
        )
        school_year_count = max(
            existing_school_years,
            target_school_years,
        )
        adult_year_count = max(
            len(
                normalize_adult_year_records(
                    getattr(self, "adult_year_records", [])
                )
            ),
            target_adult_years,
        )

        if school_year_count and self.school_is_selected():
            self.school_started = True
            self.academic_years_advanced = (
                ACADEMIC_YEARS_TO_ADULTHOOD
                if adult_year_count
                else school_year_count - 1
            )

        self.ensure_school_year_record_count(school_year_count)
        self.adult_year_records = (
            ensure_adult_year_records_with_improvements(
                getattr(self, "adult_year_records", []),
                adult_year_count,
                self.school_year_generation_plan(),
                initial_characteristics=getattr(
                    self,
                    "characteristics",
                    None,
                ),
                school_year_records=getattr(
                    self,
                    "school_year_records",
                    [],
                ),
                manage_reading=False,
            )
        )
        self.development_plan["adult_years"] = deepcopy(
            self.adult_year_records
        )
        self.development_plan["calendar_year_progression"] = (
            DevelopmentView.uses_calendar_year_progression(self)
        )
        self.ensure_school_year_record_count(school_year_count)
        self.update_school_progress_controls(select_latest=True)
        self.notify_change()

    def advance_to_adulthood(self):
        self.ensure_school_year_record_count(
            ACADEMIC_YEARS_TO_ADULTHOOD
        )
        self.active_development_page_index = (
            ACADEMIC_YEARS_TO_ADULTHOOD
        )
        self.update_school_progress_controls()
        return True

    def remove_latest_school_year(self):
        return False

    def focus_selection_changed(self, *arguments):
        if self.loading:
            return

        self.loading = True

        if development_skill_count(self.strategy_value.get()):
            self.update_skill_options()

        self.reconcile_initial_bonus_assignments(
            refresh_automatic=True
        )
        self.loading = False
        self.notify_change()

    def update_focus_controls(self):
        schema = self.strategy_value.get()
        required_skill_count = development_skill_count(schema)

        if required_skill_count:
            self.focus_frame.grid()
            self.ability_block.grid_remove()

            for index, skill_block in enumerate(self.skill_blocks):
                self.focus_frame.grid_columnconfigure(
                    index,
                    weight=(
                        1
                        if index < required_skill_count
                        else 0
                    ),
                    uniform="development_focus_skills",
                )
                self.skill_labels[index].configure(
                    text=(
                        "Skill"
                        if required_skill_count == 1
                        else f"Skill {index + 1}"
                    )
                )

                if index < required_skill_count:
                    skill_block.grid()
                else:
                    skill_block.grid_remove()

            self.update_skill_options()
            return

        for skill_block in self.skill_blocks:
            skill_block.grid_remove()

        if schema == "Ability-focus":
            self.focus_frame.grid()
            self.ability_block.grid()
        else:
            self.ability_block.grid_remove()
            self.focus_frame.grid_remove()

    def update_skill_options(self):
        active_skill_count = len(self.skill_values)

        if hasattr(self, "strategy_value"):
            try:
                active_skill_count = development_skill_count(
                    self.strategy_value.get()
                )
            except ValueError:
                active_skill_count = len(self.skill_values)

        active_skill_count = max(
            0,
            min(active_skill_count, len(self.skill_values)),
        )
        selected_skills = []

        for skill_value in self.skill_values[:active_skill_count]:
            selected_skill = skill_value.get()

            if (
                selected_skill not in DEVELOPMENT_SKILL_OPTIONS
                or selected_skill in selected_skills
            ):
                selected_skill = next(
                    skill
                    for skill in DEVELOPMENT_SKILL_OPTIONS
                    if skill not in selected_skills
                )
                skill_value.set(selected_skill)

            selected_skills.append(selected_skill)

        for index, skill_select in enumerate(self.skill_selects):
            if index >= active_skill_count:
                skill_select.set_values(DEVELOPMENT_SKILL_OPTIONS)
                continue

            selected_by_other_controls = {
                self.skill_values[other_index].get()
                for other_index in range(active_skill_count)
                if other_index != index
            }
            available_skills = [
                skill
                for skill in DEVELOPMENT_SKILL_OPTIONS
                if skill not in selected_by_other_controls
            ]
            skill_select.set_values(available_skills)

    def apply_parental_values_to_controls(self):
        if not hasattr(self, "parental_value_variables"):
            return

        if self.parental_values is None:
            self.parental_mode_value.set(PARENTAL_MODE_SHARED)

            for parental_value in self.parental_value_variables.values():
                parental_value.set("")

            return

        self.parental_mode_value.set(
            self.parental_values["mode"]
        )

        for field_name in PARENTAL_VALUE_NAMES:
            self.parental_value_variables[field_name].set(
                str(self.parental_values[field_name])
            )

    def update_parental_controls(self):
        if not hasattr(self, "parental_handling_button"):
            return

        self.update_parental_handling_menu()
        initialized = self.parental_values is not None
        self.parental_handling_button.set_enabled(initialized)
        entries_are_editable = (
            initialized
            and self.parental_mode_value.get()
            == PARENTAL_MODE_OVERRIDE
        )

        for entry in self.parental_value_entries.values():
            entry.set_enabled(entries_are_editable)

    def update_parental_handling_menu(self):
        if not hasattr(self, "parental_handling_menu"):
            return

        self.parental_handling_menu.delete(0, "end")
        sibling = parental_sibling_reference(
            self.current_person,
            self.available_people(),
            excluded_record_id=self.current_person.get("record_id"),
        )

        if sibling is not None:
            sibling_name = str(
                sibling.get("displayed_name", "") or ""
            ).strip()
            self.parental_handling_menu.add_radiobutton(
                label=f"Base on {sibling_name}",
                variable=self.parental_mode_value,
                value=PARENTAL_MODE_SHARED,
            )

        for parental_mode in (
            PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            PARENTAL_MODE_FULLY_RANDOMIZED,
            PARENTAL_MODE_OVERRIDE,
        ):
            self.parental_handling_menu.add_radiobutton(
                label=parental_mode,
                variable=self.parental_mode_value,
                value=parental_mode,
            )

    def initial_bonus_person_values(self):
        person_values = deepcopy(self.current_person)
        person_values["blood_status"] = normalize_blood_status(
            self.blood_status_value.get()
        )
        person_values["developmental_environment"] = (
            normalize_developmental_environment(
                self.developmental_environment_value.get(),
                person_values["blood_status"],
            )
        )
        person_values["parental_values"] = deepcopy(
            self.parental_values
        )
        return person_values

    def reconcile_initial_bonus_assignments(
        self,
        refresh_automatic=False,
    ):
        if self.initial_bonuses is None:
            self.update_initial_bonus_controls()
            return False

        previous_bonuses = deepcopy(self.initial_bonuses)
        self.initial_bonuses = reconcile_initial_bonuses(
            self.initial_bonuses,
            self.initial_bonus_person_values(),
            self.current_development_plan(),
            refresh_automatic=refresh_automatic,
        )
        self.current_person["initial_bonuses"] = deepcopy(
            self.initial_bonuses
        )
        self.update_initial_bonus_controls()
        return previous_bonuses != self.initial_bonuses

    def update_initial_bonus_controls(self):
        if not hasattr(self, "skill_bonus_summary_value"):
            return

        requirements = initial_bonus_requirements(
            self.blood_status_value.get(),
            self.developmental_environment_value.get(),
            self.parental_values,
        )
        skill_count = requirements["skill_bonus_count"]
        trait_count = requirements["trait_count"]
        muggles_bonus = requirements["muggles_skill_bonus"]
        selected_skills = (
            list(self.initial_bonuses["skill_bonuses"])
            if self.initial_bonuses is not None
            else []
        )
        selected_traits = (
            list(self.initial_bonuses["traits"])
            if self.initial_bonuses is not None
            else []
        )

        if skill_count == 0:
            self.skill_bonus_summary_value.set(
                "No initial skill bonuses"
            )
            self.skill_bonus_button.grid_remove()
        else:
            skill_label = (
                "initial skill bonus"
                if skill_count == 1
                else "initial skill bonuses"
            )
            selected_skill_text = (
                summarize_initial_skill_bonuses(
                    selected_skills
                )
            )
            selected_text = (
                f": {selected_skill_text}"
                if selected_skill_text
                else ""
            )
            self.skill_bonus_summary_value.set(
                f"+{skill_count} {skill_label}{selected_text}"
            )
            self.skill_bonus_button.grid()
            self.skill_bonus_button.set_enabled(
                self.initial_bonuses is not None
            )

        if trait_count == 0:
            self.trait_summary_value.set("No traits")
            self.trait_button.grid_remove()
        else:
            trait_label = "trait" if trait_count == 1 else "traits"
            selected_text = (
                ": "
                + "; ".join(
                    f"{trait_name}: "
                    f"{trait_effect_text(trait_name)}"
                    for trait_name in selected_traits
                )
                if selected_traits
                else ""
            )
            self.trait_summary_value.set(
                f"{trait_count} {trait_label}{selected_text}"
            )
            self.trait_button.grid()
            self.trait_button.set_enabled(
                self.initial_bonuses is not None
            )

        if muggles_bonus:
            self.muggles_bonus_summary_value.set(
                f"+{muggles_bonus} Muggles skill"
            )
            self.muggles_bonus_summary.grid()
        else:
            self.muggles_bonus_summary_value.set("")
            self.muggles_bonus_summary.grid_remove()

        self.update_initial_values_completion()

    def open_initial_skill_bonus_dialog(self):
        if self.initial_bonuses is None:
            return

        requirements = initial_bonus_requirements(
            self.blood_status_value.get(),
            self.developmental_environment_value.get(),
            self.parental_values,
        )
        required_count = requirements["skill_bonus_count"]

        if required_count <= 0:
            return

        InitialSkillBonusDialog(
            self,
            required_count,
            self.initial_bonuses["skill_bonuses"],
            self.save_initial_skill_bonuses,
        )

    def save_initial_skill_bonuses(self, selected_skills):
        if self.initial_bonuses is None:
            return

        requirements = initial_bonus_requirements(
            self.blood_status_value.get(),
            self.developmental_environment_value.get(),
            self.parental_values,
        )
        required_count = requirements["skill_bonus_count"]
        normalized_bonuses = deepcopy(self.initial_bonuses)
        normalized_bonuses["skill_selection_mode"] = (
            INITIAL_SELECTION_MANUAL
        )
        normalized_bonuses["skill_bonuses"] = list(
            selected_skills
        )
        normalized_bonuses = normalize_initial_bonuses(
            normalized_bonuses,
            allow_uninitialized=False,
        )

        if len(normalized_bonuses["skill_bonuses"]) != required_count:
            raise ValueError(
                f"Select exactly {required_count} initial skills."
            )

        self.initial_bonuses = normalized_bonuses
        self.current_person["initial_bonuses"] = deepcopy(
            self.initial_bonuses
        )
        self.update_initial_bonus_controls()
        self.notify_change()

    def open_trait_dialog(self):
        if self.initial_bonuses is None:
            return

        requirements = initial_bonus_requirements(
            self.blood_status_value.get(),
            self.developmental_environment_value.get(),
            self.parental_values,
        )
        required_count = requirements["trait_count"]

        if required_count <= 0:
            return

        TraitSelectionDialog(
            self,
            required_count,
            self.initial_bonuses["traits"],
            self.save_initial_traits,
        )

    def save_initial_traits(self, selected_traits):
        if self.initial_bonuses is None:
            return

        requirements = initial_bonus_requirements(
            self.blood_status_value.get(),
            self.developmental_environment_value.get(),
            self.parental_values,
        )
        required_count = requirements["trait_count"]
        normalized_bonuses = deepcopy(self.initial_bonuses)
        normalized_bonuses["trait_selection_mode"] = (
            INITIAL_SELECTION_MANUAL
        )
        normalized_bonuses["traits"] = list(selected_traits)
        normalized_bonuses = normalize_initial_bonuses(
            normalized_bonuses,
            allow_uninitialized=False,
        )

        if len(normalized_bonuses["traits"]) != required_count:
            raise ValueError(
                f"Select exactly {required_count} initial traits."
            )

        self.initial_bonuses = normalized_bonuses
        self.current_person["initial_bonuses"] = deepcopy(
            self.initial_bonuses
        )
        self.update_initial_bonus_controls()
        self.notify_change()

    def available_people(self):
        if self.people_provider is None:
            return []

        people = self.people_provider()
        return list(people) if people is not None else []

    def update_blood_status_control(self):
        available_people = self.available_people()
        available_options = blood_status_options(
            self.current_person,
            available_people,
        )
        selected_status = resolved_blood_status(
            {
                **self.current_person,
                "blood_status": self.blood_status_value.get(),
            },
            available_people,
        )
        previous_loading = self.loading
        self.loading = True
        self.blood_status_value.set(selected_status)
        self.current_person["blood_status"] = selected_status
        selected_environment = normalize_developmental_environment(
            (
                self.developmental_environment_value.get()
                or self.current_person.get(
                    "developmental_environment",
                    "",
                )
            ),
            selected_status,
        )
        self.current_person["developmental_environment"] = (
            selected_environment
        )

        if selected_environment:
            self.developmental_environment_value.set(
                selected_environment
            )

        if hasattr(self, "blood_status_select"):
            self.blood_status_select.set_values(available_options)

            if len(available_options) == 1:
                self.blood_status_select.grid_remove()
                self.blood_status_text.grid()
            else:
                self.blood_status_text.grid_remove()
                self.blood_status_select.grid()

        if hasattr(self, "environment_block"):
            if selected_status == BLOOD_STATUS_HALFBLOOD:
                self.environment_block.grid()
            else:
                self.environment_block.grid_remove()

        self.loading = previous_loading

    def show_parental_handling_menu(self):
        self.update_idletasks()

        try:
            self.parental_handling_menu.tk_popup(
                self.parental_handling_button.winfo_rootx(),
                (
                    self.parental_handling_button.winfo_rooty()
                    + self.parental_handling_button.winfo_height()
                ),
            )
        finally:
            self.parental_handling_menu.grab_release()

    def school_display_text(self):
        school_name = self.school_field.get_value()
        return school_name if school_name else "none"

    def focus_school(self):
        self.school_field.open_selector()

    def notify_change(self):
        if not self.loading and self.change_command is not None:
            self.change_command()
