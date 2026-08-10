import tkinter as tk
from tkinter import messagebox

from sections.settings_and_preferences.controller import SettingsController
from sections.settings_and_preferences.general_view import GeneralSettingsView
from sections.settings_and_preferences.theme_view import ThemeSettingsView
from runtime_theme import bind_theme
from shared.widgets import SoftButton
from theme import (
    app_font,
    APP_BACKGROUND,
    BORDER,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_LIGHT,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
)


class SettingsAndPreferencesPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.controller = SettingsController(database)
        self.active_view_name = None
        self.views = {}
        self.navigation_buttons = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.toolbar = tk.Frame(
            self,
            bg=PRIMARY_LIGHT,
            height=62,
        )
        self.toolbar.grid(row=0, column=0, sticky="ew")
        bind_theme(self.toolbar, background="PRIMARY_LIGHT")
        self.toolbar.grid_propagate(False)

        self.section_title = tk.Label(
            self.toolbar,
            text="Settings & Preferences",
            bg=PRIMARY_LIGHT,
            fg=TEXT_DARK,
            font=app_font(17),
            padx=20,
        )
        self.section_title.pack(side="left", fill="y")
        bind_theme(
            self.section_title,
            background="PRIMARY_LIGHT",
            foreground="TEXT_DARK",
        )

        self.general_button = SoftButton(
            self.toolbar,
            text="General",
            command=self.show_general_view,
            background=PRIMARY_LIGHT,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            background_role="PRIMARY_LIGHT",
            width=92,
            height=38,
        )
        self.general_button.pack(side="left", padx=(4, 4), pady=12)
        self.navigation_buttons["general"] = self.general_button

        self.theme_button = SoftButton(
            self.toolbar,
            text="Theme",
            command=self.show_theme_view,
            background=PRIMARY_LIGHT,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            background_role="PRIMARY_LIGHT",
            width=86,
            height=38,
        )
        self.theme_button.pack(side="left", padx=4, pady=12)
        self.navigation_buttons["theme"] = self.theme_button

        self.save_button = SoftButton(
            self.toolbar,
            text="Save Settings",
            command=self.save_active_view,
            background=PRIMARY_LIGHT,
            fill=PRIMARY,
            hover_fill=PRIMARY_DARK,
            background_role="PRIMARY_LIGHT",
            fill_role="PRIMARY",
            hover_fill_role="PRIMARY_DARK",
            width=132,
            height=38,
        )
        self.save_button.pack(side="right", padx=(4, 16), pady=12)

        self.revert_button = SoftButton(
            self.toolbar,
            text="Revert",
            command=self.revert_active_view,
            background=PRIMARY_LIGHT,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            background_role="PRIMARY_LIGHT",
            width=92,
            height=38,
        )
        self.revert_button.pack(side="right", padx=4, pady=12)

        self.settings_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.settings_card.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=25,
            pady=25,
        )
        self.settings_card.grid_rowconfigure(0, weight=1)
        self.settings_card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.settings_card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.views["general"] = GeneralSettingsView(
            self.settings_card,
            controller=self.controller,
            dirty_command=self.handle_view_dirty,
        )
        self.views["general"].grid(row=0, column=0, sticky="nsew")

        self.views["theme"] = ThemeSettingsView(
            self.settings_card,
            controller=self.controller,
            dirty_command=self.handle_view_dirty,
        )
        self.views["theme"].grid(row=0, column=0, sticky="nsew")

        self.status_value = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(
            self,
            textvariable=self.status_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            padx=12,
            pady=7,
        )
        self.status_bar.grid(row=2, column=0, sticky="ew")
        bind_theme(
            self.status_bar,
            background="SURFACE_MUTED",
            foreground="TEXT_MUTED",
        )

        self.activate_view("general")

    def show_general_view(self):
        self.change_view("general")

    def show_theme_view(self):
        self.change_view("theme")

    def change_view(self, view_name):
        if view_name == self.active_view_name:
            return True

        if not self.confirm_unsaved_changes():
            return False

        self.activate_view(view_name)

        return True

    def activate_view(self, view_name):
        self.active_view_name = view_name
        active_view = self.views[view_name]
        active_view.tkraise()

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

        if view_name == "theme":
            self.save_button.set_text("Save Theme")
            self.status_value.set("Theme colors")
        else:
            self.save_button.set_text("Save Settings")
            self.status_value.set("General settings")

        self.update_action_buttons()

    def get_active_view(self):
        if self.active_view_name is None:
            return None

        return self.views[self.active_view_name]

    def save_active_view(self):
        active_view = self.get_active_view()

        if active_view is None:
            return False

        save_message = active_view.save_values()

        if save_message is False:
            return False

        self.status_value.set(save_message)
        self.update_action_buttons()

        return True

    def revert_active_view(self):
        active_view = self.get_active_view()

        if active_view is None:
            return False

        load_message = active_view.load_values()
        self.status_value.set(load_message)
        self.update_action_buttons()

        return True

    def handle_view_dirty(self):
        self.status_value.set("Unsaved changes")
        self.update_action_buttons()

    def update_action_buttons(self):
        active_view = self.get_active_view()
        has_changes = (
            active_view is not None
            and active_view.has_unsaved_changes()
        )
        self.save_button.set_enabled(has_changes)
        self.revert_button.set_enabled(has_changes)

    def confirm_unsaved_changes(self):
        active_view = self.get_active_view()

        if active_view is None or not active_view.has_unsaved_changes():
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved settings",
            "Save these changes before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return self.save_active_view()

        active_view.load_values()
        self.update_action_buttons()

        return True

    def can_leave(self):
        return self.confirm_unsaved_changes()
