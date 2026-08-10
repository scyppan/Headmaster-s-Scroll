import tkinter as tk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from sections.nature_and_alchemy.plants.parts_editor import PlantPartsEditor
from shared.widgets import MultilineField, SoftButton
from theme import (
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    PRIMARY,
    PRIMARY_DARK,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class PlantForm(tk.Frame):
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
        self.overview_view.grid_columnconfigure(0, weight=3)
        self.overview_view.grid_columnconfigure(1, weight=1)
        self.overview_view.grid_columnconfigure(2, weight=2)
        self.overview_view.grid_rowconfigure(1, weight=3, minsize=230)
        self.overview_view.grid_rowconfigure(2, weight=2, minsize=170)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Plant",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Plant Description",
            self.handle_text_change,
            height=9,
        )
        self.description_field.grid(
            row=1,
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
            row=1,
            column=2,
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
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(6, 0),
        )

        self.parts_view = tk.Frame(self.view_container, bg=SURFACE)
        self.parts_view.grid(row=0, column=0, sticky="nsew")
        self.parts_view.grid_columnconfigure(0, weight=1)
        self.parts_view.grid_rowconfigure(0, weight=1)
        bind_theme(self.parts_view, background="SURFACE")
        self.views["parts"] = self.parts_view

        self.parts_editor = PlantPartsEditor(
            self.parts_view,
            self.database,
            self.handle_field_change,
        )
        self.parts_editor.grid(row=0, column=0, sticky="nsew")

        self.activate_view("overview")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name"))
        self.description_field.set_value(record.get("description", ""))
        self.tags_editor.set_tags(record.get("tags", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))
        self.parts_editor.set_parts(record.get("parts", []))

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
            "description": self.description_field.get_value(),
            "parts": self.parts_editor.get_parts(),
            "tags": self.tags_editor.get_tags(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

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

    def handle_field_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_text_change(self):
        self.handle_field_change()
