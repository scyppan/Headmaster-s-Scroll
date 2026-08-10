import tkinter as tk

from runtime_theme import bind_theme
from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS
from sections.magic.proficiencies.required_materials import (
    RequiredMaterialsEditor,
)
from sections.magic.traditions import TRADITIONS
from sections.nature_and_alchemy.creatures.form_fields import (
    BoundedNumberField,
    LabeledEntry,
)
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import MultilineField, RoundedSelect, SoftButton
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class OptionalSelectField(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        values,
        change_command,
        placeholder="None",
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.grid_columnconfigure(0, weight=1)
        self.value = tk.StringVar()
        self.value.trace_add("write", change_command)
        self.label = tk.Label(
            self,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )
        self.select = RoundedSelect(
            self,
            variable=self.value,
            values=values,
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder=placeholder,
        )
        self.select.grid(row=1, column=0, sticky="ew")

    def set_value(self, value):
        self.value.set(str(value or "").strip())

    def get_value(self):
        return self.value.get().strip()


class ProficiencyForm(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
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

        self.requirements_button = SoftButton(
            self.navigation,
            text="Requirements",
            command=self.show_requirements,
            width=122,
            height=36,
        )
        self.requirements_button.pack(side="left", padx=3)
        self.navigation_buttons["requirements"] = self.requirements_button

        self.history_button = SoftButton(
            self.navigation,
            text="History & DB Notes",
            command=self.show_history,
            width=156,
            height=36,
        )
        self.history_button.pack(side="left", padx=3)
        self.navigation_buttons["history"] = self.history_button

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

        self.build_overview_view()
        self.build_requirements_view()
        self.build_history_view()
        self.activate_view("overview")

    def build_overview_view(self):
        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")

        for column_index in range(4):
            self.overview_view.grid_columnconfigure(column_index, weight=1)

        self.overview_view.grid_rowconfigure(2, weight=1, minsize=380)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Proficiency",
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

        self.tradition_field = OptionalSelectField(
            self.overview_view,
            "Tradition",
            ("", *TRADITIONS),
            self.handle_field_change,
            placeholder="No tradition",
        )
        self.tradition_field.grid(
            row=0,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 12),
        )

        self.skill_field = OptionalSelectField(
            self.overview_view,
            "Skill",
            PROFICIENCY_SKILLS,
            self.handle_field_change,
            placeholder="Select skill",
        )
        self.skill_field.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 10),
            pady=(0, 12),
        )

        self.threshold_field = BoundedNumberField(
            self.overview_view,
            "Threshold",
            self.handle_field_change,
            minimum=1,
            maximum=100,
        )
        self.threshold_field.grid(
            row=1,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(10, 0),
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
        )

    def build_requirements_view(self):
        self.requirements_view = tk.Frame(
            self.view_container,
            bg=SURFACE,
        )
        self.requirements_view.grid(row=0, column=0, sticky="nsew")
        self.requirements_view.grid_rowconfigure(0, weight=1)
        self.requirements_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.requirements_view, background="SURFACE")
        self.views["requirements"] = self.requirements_view

        self.required_materials_editor = RequiredMaterialsEditor(
            self.requirements_view,
            database=self.database,
            change_command=self.handle_field_change,
        )
        self.required_materials_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

    def build_history_view(self):
        self.history_view = tk.Frame(self.view_container, bg=SURFACE)
        self.history_view.grid(row=0, column=0, sticky="nsew")
        self.history_view.grid_rowconfigure(0, weight=1)
        self.history_view.grid_rowconfigure(1, weight=1)
        self.history_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.history_view, background="SURFACE")
        self.views["history"] = self.history_view

        self.history_field = MultilineField(
            self.history_view,
            "History",
            self.handle_text_change,
            height=16,
        )
        self.history_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, 6),
        )

        self.dbnotes_field = MultilineField(
            self.history_view,
            "DB Notes",
            self.handle_text_change,
            height=16,
        )
        self.dbnotes_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(6, 0),
        )

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name"))
        self.tradition_field.set_value(record.get("tradition", ""))
        self.skill_field.set_value(record.get("skill", ""))
        self.threshold_field.set_value(record.get("threshold"))
        self.description_field.set_value(record.get("description", ""))
        self.tags_editor.set_tags(record.get("tags", []))
        self.required_materials_editor.set_materials(
            record.get("required_materials", [])
        )
        self.history_field.set_value(record.get("history", ""))
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
            "tradition": self.tradition_field.get_value(),
            "skill": self.skill_field.get_value(),
            "threshold": self.threshold_field.get_value(),
            "required_materials": (
                self.required_materials_editor.get_materials()
            ),
            "description": self.description_field.get_value(),
            "history": self.history_field.get_value(),
            "tags": self.tags_editor.get_tags(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_requirements(self):
        self.activate_view("requirements")

    def show_history(self):
        self.activate_view("history")

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
