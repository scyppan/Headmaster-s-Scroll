import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import MultilineField, RoundedEntry
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class WandQualityForm(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=3)

        self.identity_panel = tk.Frame(self, bg=SURFACE)
        self.identity_panel.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        self.identity_panel.grid_columnconfigure(0, weight=2)
        self.identity_panel.grid_columnconfigure(1, weight=1)
        self.identity_panel.grid_columnconfigure(2, weight=1)
        bind_theme(self.identity_panel, background="SURFACE")

        self.quality_label = self.create_label("Quality")
        self.quality_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.base_knuts_label = self.create_label("Base Knuts")
        self.base_knuts_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )

        self.casting_effect_label = self.create_label("Casting Effect")
        self.casting_effect_label.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(8, 0),
        )

        self.quality_value = tk.StringVar()
        self.quality_value.trace_add("write", self.handle_identity_change)
        self.quality_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.quality_value,
            background=SURFACE,
            height=42,
            font=app_font(12),
        )
        self.quality_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.base_knuts_value = tk.StringVar()
        self.base_knuts_value.trace_add("write", self.handle_identity_change)
        self.base_knuts_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.base_knuts_value,
            background=SURFACE,
            height=42,
            justify="right",
            font=app_font(12),
        )
        self.base_knuts_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=8,
        )

        self.casting_effect_value = tk.StringVar()
        self.casting_effect_value.trace_add(
            "write",
            self.handle_identity_change,
        )
        self.casting_effect_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.casting_effect_value,
            background=SURFACE,
            height=42,
            justify="center",
            font=app_font(12),
        )
        self.casting_effect_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(8, 0),
        )

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
            columnspan=3,
            sticky="ew",
            pady=(9, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.effect_field = MultilineField(
            self,
            "Effect",
            self.handle_field_change,
            height=7,
        )
        self.effect_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(0, 10),
        )

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_field_change,
            height=8,
        )
        self.dbnotes_field.grid(
            row=2,
            column=0,
            sticky="nsew",
            pady=(10, 0),
        )

    def create_label(self, text):
        label = tk.Label(
            self.identity_panel,
            text=text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        bind_theme(
            label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        return label

    def set_record(self, record):
        self.loading_record = True

        self.quality_value.set(record.get("name", ""))

        base_knuts = record.get("base_knuts")
        self.base_knuts_value.set(
            "" if base_knuts is None else str(base_knuts)
        )

        casting_effect = record.get("casting_effect")
        self.casting_effect_value.set(
            "" if casting_effect is None else str(casting_effect)
        )

        self.effect_field.set_value(record.get("effect", ""))
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
        self.quality_entry.focus_set()

    def get_values(self):
        base_knuts_text = self.base_knuts_value.get().strip()
        casting_effect_text = self.casting_effect_value.get().strip()

        if not base_knuts_text:
            raise ValueError("Base Knuts is required")

        if not casting_effect_text:
            raise ValueError("Casting Effect is required")

        try:
            base_knuts = int(base_knuts_text)
        except ValueError:
            raise ValueError("Base Knuts must be a whole number") from None

        try:
            casting_effect = int(casting_effect_text)
        except ValueError:
            raise ValueError("Casting Effect must be a whole number") from None

        if base_knuts < 0:
            raise ValueError("Base Knuts cannot be negative")

        return {
            "name": self.quality_value.get().strip(),
            "base_knuts": base_knuts,
            "effect": self.effect_field.get_value(),
            "casting_effect": casting_effect,
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def handle_identity_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
