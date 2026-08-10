import tkinter as tk
from tkinter import messagebox

from runtime_theme import bind_theme
from shared.widgets import RoundedEntry
from theme import SURFACE, SURFACE_MUTED, TEXT_DARK, TEXT_MUTED, app_font


class GeneralSettingsView(tk.Frame):
    def __init__(self, parent, controller, dirty_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.controller = controller
        self.dirty_command = dirty_command
        self.loading_settings = False
        self.form_dirty = False

        self.grid_columnconfigure(1, weight=1)

        self.database_heading = tk.Label(
            self,
            text="Database",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(18),
            anchor="w",
        )
        self.database_heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=30,
            pady=(30, 18),
        )
        bind_theme(
            self.database_heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.database_version_label = tk.Label(
            self,
            text="Database version",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.database_version_label.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(30, 20),
            pady=8,
        )
        bind_theme(
            self.database_version_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.database_version_value = tk.StringVar()
        self.database_version_value.trace_add(
            "write",
            self.handle_setting_change,
        )
        self.database_version_entry = RoundedEntry(
            self,
            textvariable=self.database_version_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.database_version_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 30),
            pady=8,
        )

        self.window_heading = tk.Label(
            self,
            text="Window and Layout",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(18),
            anchor="w",
        )
        self.window_heading.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=30,
            pady=(30, 18),
        )
        bind_theme(
            self.window_heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.start_maximized_value = tk.BooleanVar()
        self.start_maximized_check = tk.Checkbutton(
            self,
            text="Start the application maximized",
            variable=self.start_maximized_value,
            command=self.mark_form_dirty,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=SURFACE_MUTED,
            font=app_font(10),
            anchor="w",
        )
        self.start_maximized_check.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=30,
            pady=8,
        )
        bind_theme(
            self.start_maximized_check,
            background="SURFACE",
            foreground="TEXT_DARK",
            activebackground="SURFACE",
            activeforeground="TEXT_DARK",
            selectcolor="SURFACE_MUTED",
        )

        self.sidebar_width_label = tk.Label(
            self,
            text="Sidebar width",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.sidebar_width_label.grid(
            row=4,
            column=0,
            sticky="w",
            padx=(30, 20),
            pady=8,
        )
        bind_theme(
            self.sidebar_width_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.sidebar_width_value = tk.StringVar()
        self.sidebar_width_value.trace_add(
            "write",
            self.handle_setting_change,
        )
        self.sidebar_width_entry = RoundedEntry(
            self,
            textvariable=self.sidebar_width_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.sidebar_width_entry.grid(
            row=4,
            column=1,
            sticky="ew",
            padx=(0, 30),
            pady=8,
        )

        self.layout_note = tk.Label(
            self,
            text=(
                "Window and layout preferences are stored in the separate "
                "user_preferences.json file. Window changes apply the next "
                "time the application starts."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            wraplength=650,
            anchor="nw",
        )
        self.layout_note.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=30,
            pady=(25, 30),
        )
        bind_theme(
            self.layout_note,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.load_values()

    def load_values(self):
        settings = self.controller.load_general_settings()
        metadata = settings["metadata"]
        window_preferences = settings["window"]

        self.loading_settings = True
        self.database_version_value.set(
            metadata.get("database_version", "1.0")
        )
        self.start_maximized_value.set(
            window_preferences.get("start_maximized", True)
        )
        self.sidebar_width_value.set(
            str(window_preferences.get("sidebar_width", 250))
        )
        self.loading_settings = False
        self.form_dirty = False

        return "General settings loaded"

    def save_values(self):
        database_version = self.database_version_value.get().strip()

        if not database_version:
            messagebox.showerror(
                "Database version required",
                "Enter a database version before saving.",
                parent=self,
            )
            return False

        try:
            sidebar_width = int(self.sidebar_width_value.get())
        except ValueError:
            messagebox.showerror(
                "Invalid sidebar width",
                "Sidebar width must be a whole number.",
                parent=self,
            )
            return False

        if sidebar_width < 180 or sidebar_width > 500:
            messagebox.showerror(
                "Invalid sidebar width",
                "Sidebar width must be between 180 and 500 pixels.",
                parent=self,
            )
            return False

        self.controller.save_general_settings(
            database_version,
            self.start_maximized_value.get(),
            sidebar_width,
        )
        self.form_dirty = False

        return "Settings saved. Window changes apply at the next start."

    def handle_setting_change(self, *arguments):
        self.mark_form_dirty()

    def mark_form_dirty(self):
        if self.loading_settings:
            return

        self.form_dirty = True
        self.dirty_command()

    def has_unsaved_changes(self):
        return self.form_dirty
