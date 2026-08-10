import tkinter as tk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.ability_editor import AbilityEditor
from sections.nature_and_alchemy.creatures.attack_editor import AttackEditor
from sections.nature_and_alchemy.creatures.constants import (
    BOND_HELP,
    CLASSIFICATIONS,
    CREATURE_TYPES,
    INSTINCT_INTENTIONS,
    INSTINCT_STANCES,
    LURE_HELP,
    TAME_HELP,
    UNDEFINED,
    YES_NO_ONLY,
    YES_NO_VALUES,
)
from sections.nature_and_alchemy.creatures.form_fields import (
    LabeledEntry,
    LabeledSelect,
    RangeField,
)
from sections.nature_and_alchemy.creatures.parts_editor import PartsEditor
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import MultilineField, SoftButton
from theme import (
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    PRIMARY,
    PRIMARY_DARK,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class MovementField(tk.LabelFrame):
    def __init__(
        self,
        parent,
        title,
        unavailable_text,
        change_command,
    ):
        super().__init__(
            parent,
            text=title,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=8,
            pady=6,
        )
        bind_theme(
            self,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.change_command = change_command
        self.unavailable_text = unavailable_text
        self.grid_columnconfigure(0, weight=1)

        self.enabled_field = LabeledSelect(
            self,
            "Movement Available",
            YES_NO_ONLY,
            self.handle_enabled_change,
            placeholder="No",
        )
        self.enabled_field.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        self.speed_field = RangeField(
            self,
            "Speed Range",
            change_command,
            minimum=1,
            maximum=50,
        )
        self.speed_field.grid(row=1, column=0, sticky="ew")

        self.unavailable_label = tk.Label(
            self,
            text=unavailable_text,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            padx=2,
            pady=12,
        )
        self.unavailable_label.grid(row=1, column=0, sticky="ew")
        bind_theme(
            self.unavailable_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )
        self.update_movement_display()

    def set_value(self, value):
        movement_value = value if isinstance(value, dict) else {}
        enabled_value = movement_value.get("enabled", "No")

        if enabled_value not in YES_NO_ONLY:
            enabled_value = (
                "Yes"
                if any(
                    movement_value.get(field_name) is not None
                    for field_name in ("low", "high")
                )
                else "No"
            )

        self.enabled_field.set_value(enabled_value)
        self.speed_field.set_value(
            {
                "low": movement_value.get("low"),
                "high": movement_value.get("high"),
            }
        )
        self.update_movement_display()

    def get_value(self):
        enabled_value = self.enabled_field.get_value()

        if enabled_value == "No":
            return {
                "enabled": "No",
                "low": None,
                "high": None,
            }

        speed_range = self.speed_field.get_value()

        return {
            "enabled": enabled_value,
            "low": speed_range["low"],
            "high": speed_range["high"],
        }

    def handle_enabled_change(self, *arguments):
        self.update_movement_display()
        self.change_command()

    def update_movement_display(self):
        if self.enabled_field.get_value() == "Yes":
            self.unavailable_label.grid_remove()
            self.speed_field.grid()
        else:
            self.speed_field.grid_remove()
            self.unavailable_label.grid()


class InstinctCheckboxGroup(tk.LabelFrame):
    def __init__(self, parent, title, choices, change_command, columns=3):
        super().__init__(
            parent,
            text=title,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=8,
            pady=6,
        )
        bind_theme(
            self,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.choices = tuple(choices)
        self.variables = {}

        for column_index in range(columns):
            self.grid_columnconfigure(column_index, weight=1)

        for choice_index, choice in enumerate(self.choices):
            choice_variable = tk.BooleanVar(value=False)
            self.variables[choice] = choice_variable
            choice_button = tk.Checkbutton(
                self,
                text=choice,
                variable=choice_variable,
                command=change_command,
                bg=SURFACE,
                fg=TEXT_DARK,
                activebackground=SURFACE,
                activeforeground=TEXT_DARK,
                selectcolor=FIELD_BACKGROUND,
                font=app_font(9),
                anchor="w",
                highlightthickness=0,
                borderwidth=0,
                padx=2,
                pady=2,
            )
            choice_button.grid(
                row=choice_index // columns,
                column=choice_index % columns,
                sticky="w",
                padx=(0, 6),
            )
            bind_theme(
                choice_button,
                background="SURFACE",
                foreground="TEXT_DARK",
                activebackground="SURFACE",
                activeforeground="TEXT_DARK",
                selectcolor="FIELD_BACKGROUND",
            )

    def set_choices(self, selected_choices):
        selected_choice_set = set(
            selected_choices if isinstance(selected_choices, list) else []
        )

        for choice, choice_variable in self.variables.items():
            choice_variable.set(choice in selected_choice_set)

    def get_choices(self):
        return [
            choice
            for choice in self.choices
            if self.variables[choice].get()
        ]


class CreatureForm(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
        self.loading_record = False
        self.active_view_name = None
        self.active_action_editor_name = "attacks"
        self.views = {}
        self.navigation_buttons = {}
        self.action_editor_buttons = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.navigation = tk.Frame(self, bg=SURFACE)
        self.navigation.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        bind_theme(self.navigation, background="SURFACE")

        self.overview_button = SoftButton(
            self.navigation,
            text="Overview",
            command=self.show_overview,
            width=88,
            height=36,
        )
        self.overview_button.pack(side="left", padx=(0, 3))
        self.navigation_buttons["overview"] = self.overview_button

        self.intelligence_behavior_button = SoftButton(
            self.navigation,
            text="Intelligence and Behavior",
            command=self.show_intelligence_behavior,
            width=198,
            height=36,
        )
        self.intelligence_behavior_button.pack(side="left", padx=3)
        self.navigation_buttons["intelligence_behavior"] = (
            self.intelligence_behavior_button
        )

        self.actions_button = SoftButton(
            self.navigation,
            text="Attacks & Abilities",
            command=self.show_actions,
            width=150,
            height=36,
        )
        self.actions_button.pack(side="left", padx=3)
        self.navigation_buttons["actions"] = self.actions_button

        self.parts_button = SoftButton(
            self.navigation,
            text="Parts",
            command=self.show_parts,
            width=88,
            height=36,
        )
        self.parts_button.pack(side="left", padx=3)
        self.navigation_buttons["parts"] = self.parts_button

        self.last_updated_value = tk.StringVar(
            value="Last updated: Not yet saved"
        )
        self.last_updated_label = tk.Label(
            self.navigation,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        self.last_updated_label.pack(side="right", fill="x", expand=True)
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.view_container = tk.Frame(self, bg=SURFACE)
        self.view_container.grid(row=1, column=0, sticky="nsew")
        self.view_container.grid_rowconfigure(0, weight=1)
        self.view_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.view_container, background="SURFACE")

        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")
        self.overview_view.grid_columnconfigure(0, weight=1)
        self.overview_view.grid_columnconfigure(1, weight=1)
        self.overview_view.grid_columnconfigure(2, weight=1)
        self.overview_view.grid_columnconfigure(3, weight=1)
        self.overview_view.grid_rowconfigure(2, weight=1, minsize=170)
        self.overview_view.grid_rowconfigure(3, weight=1, minsize=170)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Creature",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 10),
        )

        self.creature_type_field = LabeledSelect(
            self.overview_view,
            "Creature Type",
            CREATURE_TYPES,
            self.handle_field_change,
        )
        self.creature_type_field.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 10),
        )

        self.classification_field = LabeledSelect(
            self.overview_view,
            "Classification",
            CLASSIFICATIONS,
            self.handle_field_change,
        )
        self.classification_field.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(8, 0),
            pady=(0, 10),
        )

        self.wound_cap_field = RangeField(
            self.overview_view,
            "Wound Cap",
            self.handle_field_change,
            minimum=1,
            maximum=30,
        )
        self.wound_cap_field.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 10),
        )

        self.size_field = RangeField(
            self.overview_view,
            "Size",
            self.handle_field_change,
            minimum=1,
            maximum=5,
        )
        self.size_field.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 10),
        )

        self.magical_field = LabeledSelect(
            self.overview_view,
            "Magical",
            YES_NO_VALUES,
            self.handle_field_change,
        )
        self.magical_field.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 10),
        )

        self.magical_resistance_field = RangeField(
            self.overview_view,
            "Magical Resistance",
            self.handle_field_change,
            minimum=1,
            maximum=50,
        )
        self.magical_resistance_field.grid(
            row=1,
            column=3,
            columnspan=1,
            sticky="ew",
            padx=(8, 0),
            pady=(0, 10),
        )

        self.tags_editor = TagEditor(
            self.overview_view,
            self.handle_field_change,
        )
        self.tags_editor.grid(
            row=2,
            column=2,
            columnspan=2,
            sticky="nsew",
            padx=(8, 0),
            pady=(0, 6),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Creature Description",
            self.handle_text_change,
            height=6,
        )
        self.description_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 6),
        )

        self.dbnotes_field = MultilineField(
            self.overview_view,
            "DB Notes",
            self.handle_text_change,
            height=5,
        )
        self.dbnotes_field.grid(
            row=3,
            column=0,
            columnspan=4,
            sticky="nsew",
            pady=(6, 0),
        )

        self.intelligence_behavior_view = tk.Frame(
            self.view_container,
            bg=SURFACE,
        )
        self.intelligence_behavior_view.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.intelligence_behavior_view.grid_columnconfigure(0, weight=1)
        self.intelligence_behavior_view.grid_rowconfigure(2, weight=1)
        bind_theme(
            self.intelligence_behavior_view,
            background="SURFACE",
        )
        self.views["intelligence_behavior"] = (
            self.intelligence_behavior_view
        )

        self.intelligence_social_domestication_section = tk.Frame(
            self.intelligence_behavior_view,
            bg=SURFACE,
        )
        self.intelligence_social_domestication_section.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            0,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            1,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            2,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            3,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            4,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_columnconfigure(
            5,
            weight=1,
        )
        self.intelligence_social_domestication_section.grid_rowconfigure(
            4,
            weight=1,
        )
        bind_theme(
            self.intelligence_social_domestication_section,
            background="SURFACE",
        )

        self.intelligence_heading = tk.Label(
            self.intelligence_social_domestication_section,
            text="Intelligence",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.intelligence_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 6),
        )
        bind_theme(
            self.intelligence_heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.sentient_field = LabeledSelect(
            self.intelligence_social_domestication_section,
            "Sentient",
            YES_NO_ONLY,
            self.handle_sentient_change,
            placeholder="No",
        )
        self.sentient_field.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 5),
        )

        self.intelligence_field = RangeField(
            self.intelligence_social_domestication_section,
            "Intelligence",
            self.handle_field_change,
            minimum=1,
            maximum=50,
        )
        self.intelligence_field.grid(
            row=1,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=(5, 8),
        )

        self.sentient_note_value = tk.StringVar()
        self.sentient_note = tk.Label(
            self.intelligence_social_domestication_section,
            textvariable=self.sentient_note_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            justify="left",
            anchor="nw",
            wraplength=560,
        )
        self.sentient_note.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="new",
            padx=(0, 8),
            pady=(8, 0),
        )
        bind_theme(
            self.sentient_note,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.social_heading = tk.Label(
            self.intelligence_social_domestication_section,
            text="Human Social Skills",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.social_heading.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            padx=(0, 8),
            pady=(12, 6),
        )
        bind_theme(
            self.social_heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.human_social_field = LabeledSelect(
            self.intelligence_social_domestication_section,
            "Has Human Social Skills",
            YES_NO_ONLY,
            self.handle_human_social_change,
            placeholder="No",
        )
        self.human_social_field.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=(0, 5),
        )

        self.social_skill_field = RangeField(
            self.intelligence_social_domestication_section,
            "Human Social Skill",
            self.handle_field_change,
            minimum=1,
            maximum=50,
        )
        self.social_skill_field.grid(
            row=4,
            column=1,
            columnspan=2,
            sticky="ew",
            padx=(5, 8),
        )

        self.additional_social_rules_field = MultilineField(
            self.intelligence_social_domestication_section,
            "Additional Social Rules",
            self.handle_text_change,
            height=7,
        )
        self.additional_social_rules_field.grid(
            row=0,
            column=3,
            rowspan=5,
            columnspan=3,
            sticky="nsew",
            padx=(8, 0),
        )

        self.domestication_heading = tk.Label(
            self.intelligence_social_domestication_section,
            text="Domestication",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.domestication_heading.grid(
            row=5,
            column=0,
            columnspan=6,
            sticky="ew",
            pady=(14, 6),
        )
        bind_theme(
            self.domestication_heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.can_lure_field = LabeledSelect(
            self.intelligence_social_domestication_section,
            "Can Be Lured",
            YES_NO_ONLY,
            self.handle_field_change,
            placeholder="No",
            help_text=LURE_HELP,
        )
        self.can_lure_field.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 5),
        )

        self.can_tame_field = LabeledSelect(
            self.intelligence_social_domestication_section,
            "Can Be Tamed",
            YES_NO_ONLY,
            self.handle_field_change,
            placeholder="No",
            help_text=TAME_HELP,
        )
        self.can_tame_field.grid(
            row=6,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=5,
        )

        self.can_bond_field = LabeledSelect(
            self.intelligence_social_domestication_section,
            "Can Bond",
            YES_NO_ONLY,
            self.handle_field_change,
            placeholder="No",
            help_text=BOND_HELP,
        )
        self.can_bond_field.grid(
            row=6,
            column=4,
            columnspan=2,
            sticky="ew",
            padx=(5, 0),
        )

        self.instinct_box = tk.LabelFrame(
            self.intelligence_behavior_view,
            text="In-situ Instinct",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            padx=8,
            pady=6,
        )
        self.instinct_box.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        self.instinct_box.grid_columnconfigure(0, weight=1)
        self.instinct_box.grid_columnconfigure(1, weight=1)
        bind_theme(
            self.instinct_box,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.stance_field = InstinctCheckboxGroup(
            self.instinct_box,
            "Stance",
            INSTINCT_STANCES,
            self.handle_field_change,
            columns=5,
        )
        self.stance_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 4),
        )

        self.intention_field = InstinctCheckboxGroup(
            self.instinct_box,
            "Intention",
            INSTINCT_INTENTIONS,
            self.handle_field_change,
            columns=4,
        )
        self.intention_field.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(4, 0),
        )

        self.movement_box = tk.LabelFrame(
            self.intelligence_behavior_view,
            text="Movement",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            padx=8,
            pady=6,
        )
        self.movement_box.grid(
            row=2,
            column=0,
            sticky="nsew",
        )
        self.movement_box.grid_rowconfigure(0, weight=1)
        self.movement_box.grid_columnconfigure(0, weight=1)
        self.movement_box.grid_columnconfigure(1, weight=1)
        self.movement_box.grid_columnconfigure(2, weight=1)
        bind_theme(
            self.movement_box,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.land_movement_field = MovementField(
            self.movement_box,
            "Land",
            "is stuck",
            self.handle_field_change,
        )
        self.land_movement_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 5),
        )

        self.water_movement_field = MovementField(
            self.movement_box,
            "Water",
            "will drown",
            self.handle_field_change,
        )
        self.water_movement_field.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=5,
        )

        self.air_movement_field = MovementField(
            self.movement_box,
            "Air",
            "will fall",
            self.handle_field_change,
        )
        self.air_movement_field.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(5, 0),
        )

        self.actions_view = tk.Frame(self.view_container, bg=SURFACE)
        self.actions_view.grid(row=0, column=0, sticky="nsew")
        self.actions_view.grid_columnconfigure(0, weight=1)
        self.actions_view.grid_rowconfigure(1, weight=1)
        bind_theme(self.actions_view, background="SURFACE")
        self.views["actions"] = self.actions_view

        self.action_navigation = tk.Frame(self.actions_view, bg=SURFACE)
        self.action_navigation.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        bind_theme(self.action_navigation, background="SURFACE")

        self.attacks_view_button = SoftButton(
            self.action_navigation,
            text="Attacks",
            command=self.show_attack_editor,
            width=100,
            height=32,
        )
        self.attacks_view_button.pack(side="left", padx=(0, 4))
        self.action_editor_buttons["attacks"] = self.attacks_view_button

        self.abilities_view_button = SoftButton(
            self.action_navigation,
            text="Abilities",
            command=self.show_ability_editor,
            width=100,
            height=32,
        )
        self.abilities_view_button.pack(side="left", padx=4)
        self.action_editor_buttons["abilities"] = self.abilities_view_button

        self.action_editor_container = tk.Frame(
            self.actions_view,
            bg=SURFACE,
        )
        self.action_editor_container.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.action_editor_container.grid_rowconfigure(0, weight=1)
        self.action_editor_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.action_editor_container, background="SURFACE")

        self.attack_editor = AttackEditor(
            self.action_editor_container,
            self.handle_field_change,
        )
        self.attack_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.ability_editor = AbilityEditor(
            self.action_editor_container,
            self.handle_field_change,
        )
        self.ability_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.activate_action_editor("attacks")

        self.parts_view = tk.Frame(self.view_container, bg=SURFACE)
        self.parts_view.grid(row=0, column=0, sticky="nsew")
        self.parts_view.grid_columnconfigure(0, weight=1)
        self.parts_view.grid_rowconfigure(0, weight=1)
        bind_theme(self.parts_view, background="SURFACE")
        self.views["parts"] = self.parts_view

        self.parts_editor = PartsEditor(
            self.parts_view,
            self.database,
            self.handle_field_change,
        )
        self.parts_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

        self.activate_view("overview")
        self.update_sentient_note()
        self.update_social_skill_visibility()

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name"))
        self.creature_type_field.set_value(
            record.get("creature_type", UNDEFINED)
        )
        self.classification_field.set_value(
            record.get("classification", UNDEFINED)
        )
        self.wound_cap_field.set_value(record.get("wound_cap", {}))
        self.size_field.set_value(record.get("size", {}))
        self.magical_field.set_value(record.get("magical", UNDEFINED))
        self.magical_resistance_field.set_value(
            record.get("magical_resistance", {})
        )
        sentient_value = record.get("sentient", "No")
        self.sentient_field.set_value(
            sentient_value if sentient_value in YES_NO_ONLY else "No"
        )

        intelligence = record.get("intelligence")

        if not isinstance(intelligence, dict):
            if record.get("sentient") == "Yes":
                intelligence = record.get("human_intelligence", {})
            else:
                intelligence = record.get("bestial_intelligence", {})

        self.intelligence_field.set_value(intelligence)
        human_social_value = record.get(
            "has_human_social_skills",
            record.get("uses_human_social_skills", "No"),
        )
        self.human_social_field.set_value(
            human_social_value
            if human_social_value in YES_NO_ONLY
            else "No"
        )
        self.social_skill_field.set_value(record.get("social_skill", {}))
        self.additional_social_rules_field.set_value(
            record.get(
                "additional_social_rules",
                record.get("additional_rules", ""),
            )
        )
        self.description_field.set_value(record.get("description", ""))
        self.tags_editor.set_tags(record.get("tags", []))
        can_lure_value = record.get("can_be_lured", "No")
        self.can_lure_field.set_value(
            can_lure_value if can_lure_value in YES_NO_ONLY else "No"
        )
        can_tame_value = record.get("can_be_tamed", "No")
        self.can_tame_field.set_value(
            can_tame_value if can_tame_value in YES_NO_ONLY else "No"
        )
        can_bond_value = record.get("can_bond", "No")
        self.can_bond_field.set_value(
            can_bond_value if can_bond_value in YES_NO_ONLY else "No"
        )
        movement = record.get("movement", {})
        self.land_movement_field.set_value(movement.get("land", {}))
        self.water_movement_field.set_value(movement.get("water", {}))
        self.air_movement_field.set_value(movement.get("air", {}))
        instinct = record.get("in_situ_instinct", {})
        self.stance_field.set_choices(instinct.get("stance", []))
        self.intention_field.set_choices(instinct.get("intention", []))
        self.attack_editor.set_attacks(record.get("attacks", []))
        self.ability_editor.set_abilities(record.get("abilities", []))
        self.parts_editor.set_parts(record.get("parts", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))

        last_updated = record.get("last_updated", "")
        display_date = last_updated.replace("T", " ") if last_updated else "Unknown"
        self.last_updated_value.set(f"Last updated: {display_date}")
        self.update_sentient_note()
        self.update_social_skill_visibility()
        self.activate_view(retained_view_name)
        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")

        if self.active_view_name == "overview":
            self.name_field.focus_set()

    def get_values(self):
        social_skill = self.social_skill_field.get_value()

        if self.human_social_field.get_value() == "No":
            social_skill = {"low": None, "high": None}

        return {
            "name": self.name_field.get_value(),
            "creature_type": self.creature_type_field.get_value(),
            "classification": self.classification_field.get_value(),
            "wound_cap": self.wound_cap_field.get_value(),
            "size": self.size_field.get_value(),
            "magical": self.magical_field.get_value(),
            "magical_resistance": self.magical_resistance_field.get_value(),
            "sentient": self.sentient_field.get_value(),
            "intelligence": self.intelligence_field.get_value(),
            "has_human_social_skills": self.human_social_field.get_value(),
            "social_skill": social_skill,
            "can_be_lured": self.can_lure_field.get_value(),
            "can_be_tamed": self.can_tame_field.get_value(),
            "can_bond": self.can_bond_field.get_value(),
            "additional_social_rules": (
                self.additional_social_rules_field.get_value()
            ),
            "movement": {
                "land": self.land_movement_field.get_value(),
                "water": self.water_movement_field.get_value(),
                "air": self.air_movement_field.get_value(),
            },
            "in_situ_instinct": {
                "stance": self.stance_field.get_choices(),
                "intention": self.intention_field.get_choices(),
            },
            "attacks": self.attack_editor.get_attacks(),
            "abilities": self.ability_editor.get_abilities(),
            "parts": self.parts_editor.get_parts(),
            "tags": self.tags_editor.get_tags(),
            "description": self.description_field.get_value(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_intelligence_behavior(self):
        self.activate_view("intelligence_behavior")

    def show_actions(self):
        self.activate_view("actions")

    def show_attack_editor(self):
        self.activate_action_editor("attacks")

    def show_ability_editor(self):
        self.activate_action_editor("abilities")

    def show_parts(self):
        self.activate_view("parts")

    def activate_view(self, view_name):
        self.active_view_name = view_name
        self.views[view_name].tkraise()

        for navigation_name, navigation_button in self.navigation_buttons.items():
            if navigation_name == view_name:
                navigation_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                navigation_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def activate_action_editor(self, editor_name):
        self.active_action_editor_name = editor_name

        if editor_name == "attacks":
            self.attack_editor.tkraise()
        else:
            self.ability_editor.tkraise()

        for button_name, editor_button in self.action_editor_buttons.items():
            if button_name == editor_name:
                editor_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                editor_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def handle_sentient_change(self, *arguments):
        self.update_sentient_note()
        self.handle_field_change()

    def update_sentient_note(self):
        sentient_value = self.sentient_field.get_value()

        if sentient_value == "Yes":
            note_text = (
                'To roll intelligence checks against sentient creatures, '
                'use "Intellect".'
            )
        elif sentient_value == "No":
            note_text = (
                'To roll intelligence checks against non-sentient creatures, '
                'roll "Creatures".'
            )
        else:
            note_text = ""

        self.sentient_note_value.set(note_text)

    def handle_human_social_change(self, *arguments):
        self.update_social_skill_visibility()
        self.handle_field_change()

    def update_social_skill_visibility(self):
        if self.human_social_field.get_value() == "No":
            self.social_skill_field.grid_remove()
        else:
            self.social_skill_field.grid()

    def handle_field_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_text_change(self):
        self.handle_field_change()
