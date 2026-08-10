import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import MultilineField, RoundedEntry
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class FoodAndDrinkForm(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=3)
        self.grid_rowconfigure(0, weight=2)
        self.grid_rowconfigure(1, weight=3)

        self.left_column = tk.Frame(self, bg=SURFACE)
        self.left_column.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 10),
        )
        self.left_column.grid_rowconfigure(1, weight=1)
        self.left_column.grid_columnconfigure(0, weight=1)
        bind_theme(self.left_column, background="SURFACE")

        self.right_column = tk.Frame(self, bg=SURFACE)
        self.right_column.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(8, 0),
            pady=(0, 10),
        )
        self.right_column.grid_rowconfigure(0, weight=1)
        self.right_column.grid_rowconfigure(1, weight=1)
        self.right_column.grid_columnconfigure(0, weight=1)
        bind_theme(self.right_column, background="SURFACE")

        self.name_panel = tk.Frame(self.left_column, bg=SURFACE)
        self.name_panel.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        self.name_panel.grid_columnconfigure(0, weight=1)
        bind_theme(self.name_panel, background="SURFACE")

        self.name_label = tk.Label(
            self.name_panel,
            text="Name",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.name_label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.name_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.name_value = tk.StringVar()
        self.name_value.trace_add("write", self.handle_name_change)
        self.name_entry = RoundedEntry(
            self.name_panel,
            textvariable=self.name_value,
            background=SURFACE,
            height=42,
            font=app_font(12),
        )
        self.name_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 0),
        )

        self.last_updated_value = tk.StringVar(value="Not yet saved")
        self.last_updated_label = tk.Label(
            self.name_panel,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        self.last_updated_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.description_field = MultilineField(
            self.left_column,
            "Description",
            self.handle_text_change,
            height=10,
        )
        self.description_field.grid(
            row=1,
            column=0,
            sticky="nsew",
        )

        self.raw_effects_field = MultilineField(
            self.right_column,
            "Raw Effects",
            self.handle_text_change,
            height=6,
        )
        self.raw_effects_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            pady=(0, 8),
        )

        self.potion_effects_field = MultilineField(
            self.right_column,
            "Effects in Potions",
            self.handle_text_change,
            height=6,
        )
        self.potion_effects_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(8, 0),
        )

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_text_change,
            height=8,
        )
        self.dbnotes_field.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

    def set_record(self, record):
        self.loading_record = True

        self.name_value.set(record.get("name", ""))
        self.description_field.set_value(record.get("description", ""))
        self.raw_effects_field.set_value(record.get("raw_effects", ""))
        self.potion_effects_field.set_value(
            record.get("effects_in_potions", "")
        )
        self.dbnotes_field.set_value(record.get("dbnotes", ""))

        last_updated = record.get("last_updated", "")
        display_date = last_updated.replace("T", " ") if last_updated else "Unknown"
        self.last_updated_value.set(f"Last updated\n{display_date}")

        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated\nNot yet saved")
        self.name_entry.focus_set()

    def get_values(self):
        return {
            "name": self.name_value.get().strip(),
            "description": self.description_field.get_value(),
            "raw_effects": self.raw_effects_field.get_value(),
            "effects_in_potions": self.potion_effects_field.get_value(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def handle_name_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_text_change(self):
        if not self.loading_record:
            self.change_command()
