import tkinter as tk

from runtime_theme import bind_theme
from sections.magic.spells.constants import SPELL_SKILLS, SPELL_SUBTYPES
from sections.magic.traditions import TRADITIONS
from sections.nature_and_alchemy.creatures.form_fields import (
    BoundedNumberField,
    LabeledEntry,
)
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import (
    MultilineField,
    RoundedSelect,
    SoftButton,
    TargetScopeField,
)
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class SpellForm(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False
        self.active_view_name = None
        self.views = {}
        self.navigation_buttons = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.navigation = tk.Frame(self, bg=SURFACE)
        self.navigation.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        bind_theme(self.navigation, background="SURFACE")

        self.overview_button = SoftButton(
            self.navigation,
            text="Overview",
            command=self.show_overview,
            width=92,
            height=36,
        )
        self.overview_button.pack(side="left", padx=(0, 3))
        self.navigation_buttons["overview"] = self.overview_button

        self.lore_button = SoftButton(
            self.navigation,
            text="History & Rationale",
            command=self.show_lore,
            width=170,
            height=36,
        )
        self.lore_button.pack(side="left", padx=3)
        self.navigation_buttons["lore"] = self.lore_button

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

        for column_index in range(4):
            self.overview_view.grid_columnconfigure(column_index, weight=1)

        self.overview_view.grid_rowconfigure(2, weight=3, minsize=235)
        self.overview_view.grid_rowconfigure(3, weight=2, minsize=165)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Spell Name",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 10),
            pady=(0, 12),
        )

        self.incantation_field = LabeledEntry(
            self.overview_view,
            "Incantation",
            self.handle_field_change,
            font_size=12,
        )
        self.incantation_field.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(10, 8),
            pady=(0, 12),
        )

        self.skill_container = tk.Frame(
            self.overview_view,
            bg=SURFACE,
        )
        self.skill_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.skill_container, background="SURFACE")
        self.skill_container.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 12),
        )

        self.skill_label = tk.Label(
            self.skill_container,
            text="Skill",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.skill_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(
            self.skill_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.skill_value = tk.StringVar()
        self.skill_value.trace_add("write", self.handle_field_change)
        self.skill_select = RoundedSelect(
            self.skill_container,
            variable=self.skill_value,
            values=SPELL_SKILLS,
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder="Select skill",
        )
        self.skill_select.grid(row=1, column=0, sticky="ew")

        self.subtype_container = tk.Frame(
            self.overview_view,
            bg=SURFACE,
        )
        self.subtype_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.subtype_container, background="SURFACE")
        self.subtype_container.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
            pady=(0, 12),
        )

        self.subtype_label = tk.Label(
            self.subtype_container,
            text="Subtype",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.subtype_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(
            self.subtype_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.subtype_value = tk.StringVar()
        self.subtype_value.trace_add("write", self.handle_field_change)
        self.subtype_select = RoundedSelect(
            self.subtype_container,
            variable=self.subtype_value,
            values=SPELL_SUBTYPES,
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder="Select subtype",
        )
        self.subtype_select.grid(row=1, column=0, sticky="ew")

        self.tradition_container = tk.Frame(
            self.overview_view,
            bg=SURFACE,
        )
        self.tradition_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.tradition_container, background="SURFACE")
        self.tradition_container.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(8, 0),
            pady=(0, 12),
        )

        self.tradition_label = tk.Label(
            self.tradition_container,
            text="Tradition",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.tradition_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(
            self.tradition_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.tradition_value = tk.StringVar()
        self.tradition_value.trace_add("write", self.handle_field_change)
        self.tradition_select = RoundedSelect(
            self.tradition_container,
            variable=self.tradition_value,
            values=("", *TRADITIONS),
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder="No tradition",
        )
        self.tradition_select.grid(row=1, column=0, sticky="ew")

        self.threshold_field = BoundedNumberField(
            self.overview_view,
            "Threshold",
            self.handle_field_change,
            minimum=1,
            maximum=100,
        )
        self.threshold_field.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(8, 0),
            pady=(0, 12),
        )

        self.target_scope_field = TargetScopeField(
            self.overview_view,
            self.handle_field_change,
        )
        self.target_scope_field.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=8,
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Description",
            self.handle_text_change,
            height=10,
        )
        self.description_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 6),
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

        self.dbnotes_field = MultilineField(
            self.overview_view,
            "DB Notes",
            self.handle_text_change,
            height=7,
        )
        self.dbnotes_field.grid(
            row=3,
            column=0,
            columnspan=4,
            sticky="nsew",
            pady=(6, 0),
        )

        self.lore_view = tk.Frame(self.view_container, bg=SURFACE)
        self.lore_view.grid(row=0, column=0, sticky="nsew")
        self.lore_view.grid_columnconfigure(0, weight=1)
        self.lore_view.grid_rowconfigure(0, weight=1)
        self.lore_view.grid_rowconfigure(1, weight=1)
        bind_theme(self.lore_view, background="SURFACE")
        self.views["lore"] = self.lore_view

        self.history_field = MultilineField(
            self.lore_view,
            "History",
            self.handle_text_change,
            height=18,
        )
        self.history_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, 6),
        )

        self.rationale_field = MultilineField(
            self.lore_view,
            "Rationale",
            self.handle_text_change,
            height=18,
        )
        self.rationale_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(6, 0),
        )

        self.activate_view("overview")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name"))
        self.incantation_field.set_value(record.get("incantation"))
        self.skill_value.set(record.get("skill", ""))
        self.subtype_value.set(record.get("subtype", ""))
        self.tradition_value.set(record.get("tradition", ""))
        self.threshold_field.set_value(record.get("threshold"))
        self.target_scope_field.set_value(record.get("target_scope", "none"))
        self.description_field.set_value(record.get("description", ""))
        self.history_field.set_value(record.get("history", ""))
        self.rationale_field.set_value(record.get("rationale", ""))
        self.tags_editor.set_tags(record.get("tags", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))

        last_updated = record.get("last_updated", "")
        display_date = last_updated.replace("T", " ") if last_updated else "Unknown"
        self.last_updated_value.set(f"Last updated: {display_date}")
        self.activate_view(retained_view_name)
        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")

        if self.active_view_name == "overview":
            self.name_field.focus_set()

    def get_values(self):
        return {
            "name": self.name_field.get_value(),
            "incantation": self.incantation_field.get_value(),
            "tradition": self.tradition_value.get().strip(),
            "skill": self.skill_value.get().strip(),
            "subtype": self.subtype_value.get().strip(),
            "threshold": self.threshold_field.get_value(),
            "target_scope": self.target_scope_field.get_value(),
            "description": self.description_field.get_value(),
            "history": self.history_field.get_value(),
            "rationale": self.rationale_field.get_value(),
            "tags": self.tags_editor.get_tags(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_lore(self):
        self.activate_view("lore")

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

    def handle_field_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_text_change(self):
        self.handle_field_change()
