import tkinter as tk

from runtime_theme import bind_theme
from sections.items.accessories.bonus_editor import BonusEditor
from shared.widgets import MultilineField, RoundedEntry
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class AccessoryForm(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=2)

        self.identity_panel = tk.Frame(self, bg=SURFACE)
        self.identity_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )
        self.identity_panel.grid_columnconfigure(0, weight=1)
        bind_theme(self.identity_panel, background="SURFACE")

        self.name_label = tk.Label(
            self.identity_panel,
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
            self.identity_panel,
            textvariable=self.name_value,
            background=SURFACE,
            height=42,
            font=app_font(12),
        )
        self.name_entry.grid(row=1, column=0, sticky="ew", pady=(5, 0))

        self.last_updated_value = tk.StringVar(
            value="Last updated: Not yet saved"
        )
        self.last_updated_label = tk.Label(
            self.identity_panel,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.last_updated_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(9, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.description_field = MultilineField(
            self,
            "Description",
            self.handle_field_change,
            height=5,
        )
        self.description_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 10),
            pady=(0, 10),
        )

        self.bonus_editor = BonusEditor(
            self,
            change_command=self.handle_field_change,
        )
        self.bonus_editor.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(0, 10),
        )

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_field_change,
            height=7,
        )
        self.dbnotes_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

    def set_record(self, record):
        self.loading_record = True

        self.name_value.set(record.get("name", ""))
        self.description_field.set_value(record.get("description", ""))
        self.bonus_editor.set_bonuses(record.get("bonuses", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))

        last_updated = record.get("last_updated", "")
        display_date = (
            last_updated.replace("T", " ")
            if last_updated
            else "Unknown"
        )
        self.last_updated_value.set(f"Last updated: {display_date}")

        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")
        self.name_entry.focus_set()

    def get_values(self):
        return {
            "name": self.name_value.get().strip(),
            "description": self.description_field.get_value(),
            "bonuses": self.bonus_editor.get_bonuses(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def handle_name_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
