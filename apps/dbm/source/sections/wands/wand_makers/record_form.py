import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import MultilineField, NameChecklist, RoundedEntry
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class WandMakerForm(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=2)
        self.grid_rowconfigure(1, weight=4)
        self.grid_rowconfigure(2, weight=2)

        self.identity_panel = tk.Frame(self, bg=SURFACE)
        self.identity_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10),
            pady=(0, 10),
        )
        self.identity_panel.grid_columnconfigure(0, weight=2)
        self.identity_panel.grid_columnconfigure(1, weight=1)
        self.identity_panel.grid_rowconfigure(3, weight=1)
        bind_theme(self.identity_panel, background="SURFACE")

        self.name_label = self.create_label("Maker")
        self.name_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.multiplier_label = self.create_label("Multiplier")
        self.multiplier_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 0),
        )

        self.name_value = tk.StringVar()
        self.name_value.trace_add("write", self.handle_identity_change)
        self.name_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.name_value,
            background=SURFACE,
            height=42,
            font=app_font(12),
        )
        self.name_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.multiplier_value = tk.StringVar()
        self.multiplier_value.trace_add(
            "write",
            self.handle_identity_change,
        )
        self.multiplier_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.multiplier_value,
            background=SURFACE,
            height=42,
            justify="center",
            font=app_font(12),
        )
        self.multiplier_entry.grid(
            row=1,
            column=1,
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
            columnspan=2,
            sticky="ew",
            pady=(9, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.selection_help = tk.Label(
            self.identity_panel,
            text=(
                "Checked items are the qualities, woods, and cores "
                "this maker can use."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            wraplength=420,
        )
        self.selection_help.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="new",
            pady=(14, 0),
        )
        bind_theme(
            self.selection_help,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.quality_checklist = NameChecklist(
            self,
            title="Allowed Wand Qualities",
            change_command=self.handle_field_change,
            height=145,
            columns=2,
        )
        self.quality_checklist.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(0, 10),
        )

        self.wood_checklist = NameChecklist(
            self,
            title="Allowed Wand Woods",
            change_command=self.handle_field_change,
            height=210,
            columns=3,
        )
        self.wood_checklist.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 10),
            pady=10,
        )

        self.core_checklist = NameChecklist(
            self,
            title="Allowed Wand Cores",
            change_command=self.handle_field_change,
            height=210,
            columns=2,
        )
        self.core_checklist.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=10,
        )

        self.notes_field = MultilineField(
            self,
            "Notes",
            self.handle_field_change,
            height=6,
        )
        self.notes_field.grid(
            row=2,
            column=0,
            columnspan=2,
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

    def set_reference_options(self, reference_names):
        self.quality_checklist.set_options(
            reference_names.get("allowed_quality_names", [])
        )
        self.wood_checklist.set_options(
            reference_names.get("allowed_wood_names", [])
        )
        self.core_checklist.set_options(
            reference_names.get("allowed_core_names", [])
        )

    def set_record(self, record):
        self.loading_record = True

        self.name_value.set(record.get("name", ""))
        multiplier = record.get("multiplier")
        self.multiplier_value.set(
            "" if multiplier is None else str(multiplier)
        )
        self.quality_checklist.set_selected(
            record.get("allowed_quality_names", [])
        )
        self.wood_checklist.set_selected(
            record.get("allowed_wood_names", [])
        )
        self.core_checklist.set_selected(
            record.get("allowed_core_names", [])
        )
        self.notes_field.set_value(record.get("notes", ""))

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
        multiplier_text = self.multiplier_value.get().strip()

        if not multiplier_text:
            raise ValueError("Multiplier is required")

        try:
            multiplier = float(multiplier_text)
        except ValueError:
            raise ValueError("Multiplier must be a number") from None

        if multiplier < 0:
            raise ValueError("Multiplier cannot be negative")

        return {
            "name": self.name_value.get().strip(),
            "multiplier": multiplier,
            "allowed_quality_names": self.quality_checklist.get_selected(),
            "allowed_wood_names": self.wood_checklist.get_selected(),
            "allowed_core_names": self.core_checklist.get_selected(),
            "notes": self.notes_field.get_value(),
        }

    def handle_identity_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
