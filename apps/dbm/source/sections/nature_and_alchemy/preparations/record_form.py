import tkinter as tk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from sections.nature_and_alchemy.potions.recipe_editor import (
    RecipeEditor,
)
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


class PreparationForm(tk.Frame):
    def __init__(self, parent, record_label, change_command, database):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.record_label = record_label
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

        self.effects_button = SoftButton(
            self.navigation,
            text="Effects",
            command=self.show_effects,
            width=88,
            height=36,
        )
        self.effects_button.pack(side="left", padx=3)
        self.navigation_buttons["effects"] = self.effects_button

        self.recipe_button = SoftButton(
            self.navigation,
            text="Recipe",
            command=self.show_recipe,
            width=88,
            height=36,
        )
        self.recipe_button.pack(side="left", padx=3)
        self.navigation_buttons["recipe"] = self.recipe_button

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
        self.build_effects_view()
        self.build_recipe_view()
        self.activate_view("overview")

    def build_overview_view(self):
        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")

        for column_index in range(4):
            self.overview_view.grid_columnconfigure(column_index, weight=1)

        self.overview_view.grid_rowconfigure(1, weight=1, minsize=300)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Preparation",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=(0, 8),
            pady=(0, 12),
        )

        self.skill_field = LabeledEntry(
            self.overview_view,
            "Skill",
            self.handle_field_change,
        )
        self.skill_field.grid(
            row=0,
            column=2,
            columnspan=2,
            sticky="ew",
            padx=(8, 0),
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Description",
            self.handle_text_change,
            height=11,
        )
        self.description_field.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=(0, 8),
        )

        self.dbnotes_field = MultilineField(
            self.overview_view,
            "DB Notes",
            self.handle_text_change,
            height=11,
        )
        self.dbnotes_field.grid(
            row=1,
            column=2,
            columnspan=2,
            sticky="nsew",
            padx=(8, 0),
        )

    def build_effects_view(self):
        self.effects_view = tk.Frame(self.view_container, bg=SURFACE)
        self.effects_view.grid(row=0, column=0, sticky="nsew")
        self.effects_view.grid_columnconfigure(0, weight=1)
        self.effects_view.grid_rowconfigure(0, weight=1, minsize=210)
        self.effects_view.grid_rowconfigure(1, weight=1, minsize=210)
        bind_theme(self.effects_view, background="SURFACE")
        self.views["effects"] = self.effects_view

        self.raw_effect_field = MultilineField(
            self.effects_view,
            "Raw Effects",
            self.handle_text_change,
            height=10,
        )
        self.raw_effect_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, 8),
        )

        self.effect_in_potions_field = MultilineField(
            self.effects_view,
            "Effect in Potions",
            self.handle_text_change,
            height=10,
        )
        self.effect_in_potions_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(8, 0),
        )

    def build_recipe_view(self):
        self.recipe_view = tk.Frame(self.view_container, bg=SURFACE)
        self.recipe_view.grid(row=0, column=0, sticky="nsew")
        self.recipe_view.grid_columnconfigure(0, weight=1)
        self.recipe_view.grid_rowconfigure(0, weight=1)
        bind_theme(self.recipe_view, background="SURFACE")
        self.views["recipe"] = self.recipe_view

        self.recipe_editor = RecipeEditor(
            self.recipe_view,
            self.database,
            self.handle_field_change,
        )
        self.recipe_editor.grid(row=0, column=0, sticky="nsew")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name", ""))
        self.skill_field.set_value(record.get("skill", ""))
        self.description_field.set_value(record.get("description", ""))
        self.raw_effect_field.set_value(record.get("raw_effect", ""))
        self.effect_in_potions_field.set_value(
            record.get("effect_in_potions", "")
        )
        self.recipe_editor.set_record(record)
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
        values = {
            "name": self.name_field.get_value(),
            "skill": self.skill_field.get_value(),
            "description": self.description_field.get_value(),
            "raw_effect": self.raw_effect_field.get_value(),
            "effect_in_potions": self.effect_in_potions_field.get_value(),
            "dbnotes": self.dbnotes_field.get_value(),
        }
        values.update(self.recipe_editor.get_values())

        return values

    def show_overview(self):
        self.activate_view("overview")

    def show_effects(self):
        self.activate_view("effects")

    def show_recipe(self):
        self.activate_view("recipe")

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
