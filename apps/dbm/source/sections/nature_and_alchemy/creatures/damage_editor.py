import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.constants import UNDEFINED
from sections.nature_and_alchemy.creatures.form_fields import (
    BoundedNumberField,
    LabeledSelect,
)
from shared.widgets import SoftButton, StripedListbox
from shared.wounds import (
    WOUND_AMOUNT_LIMITS,
    WOUND_TYPE_OPTIONS,
)
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)


WOUND_SEVERITY_DISPLAY = {
    "Light": "L",
    "Medium": "M",
    "Heavy": "H",
}

WOUND_SEVERITY_VALUES = {
    "L": "Light",
    "M": "Medium",
    "H": "Heavy",
}


class DamageEditor(tk.LabelFrame):
    def __init__(self, parent, title, change_command):
        super().__init__(
            parent,
            text=title,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=8,
            pady=8,
        )
        bind_theme(
            self,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.change_command = change_command
        self.loading_damage = False
        self.damage_entries = []
        self.selected_index = None

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(self.header, background="SURFACE")

        self.add_button = SoftButton(
            self.header,
            text="Add Damage",
            command=self.add_damage,
            width=106,
            height=28,
        )
        self.add_button.pack(side="left", padx=(0, 4))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_damage,
            width=80,
            height=28,
        )
        self.remove_button.pack(side="left")

        self.listbox = StripedListbox(
            self,
            width=16,
            height=5,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(8),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        self.listbox.bind("<<ListboxSelect>>", self.select_damage)
        self.fields = tk.Frame(self, bg=SURFACE)
        self.fields.grid(row=1, column=1, sticky="new")
        self.fields.grid_columnconfigure(0, weight=7)
        self.fields.grid_columnconfigure(1, weight=1)
        self.fields.grid_columnconfigure(2, weight=1)
        bind_theme(self.fields, background="SURFACE")

        self.type_field = LabeledSelect(
            self.fields,
            "Wound Type",
            WOUND_TYPE_OPTIONS,
            self.handle_field_change,
        )
        self.type_field.select.configure(width=150)
        self.type_field.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.severity_field = LabeledSelect(
            self.fields,
            "Severity",
            tuple(WOUND_SEVERITY_VALUES),
            self.handle_severity_change,
            placeholder="L",
        )
        self.severity_field.select.configure(width=58)
        self.severity_field.grid(row=0, column=1, sticky="ew", padx=4)

        self.amount_field = BoundedNumberField(
            self.fields,
            "Amount",
            self.handle_field_change,
            minimum=1,
            maximum=50,
        )
        self.amount_field.entry.configure(width=64)
        self.amount_field.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        self.set_detail_enabled(False)

    def set_damage_entries(self, damage_entries):
        self.loading_damage = True
        self.damage_entries = (
            deepcopy(damage_entries) if isinstance(damage_entries, list) else []
        )
        self.selected_index = 0 if self.damage_entries else None
        self.refresh_list()
        self.load_selected_damage()
        self.loading_damage = False

    def get_damage_entries(self):
        self.save_selected_damage()
        converted_entries = []

        for damage_entry in self.damage_entries:
            wound_type = str(damage_entry.get("type", UNDEFINED)).strip()
            severity = str(damage_entry.get("severity", UNDEFINED)).strip()
            amount_text = str(damage_entry.get("amount", "")).strip()

            if not amount_text:
                raise ValueError("Every damage entry must have an amount")

            converted_entries.append(
                {
                    "type": wound_type or UNDEFINED,
                    "severity": severity or UNDEFINED,
                    "amount": int(amount_text),
                }
            )

        return converted_entries

    def add_damage(self):
        if self.selected_index is not None:
            self.save_selected_damage()

        self.damage_entries.append(
            {
                "type": UNDEFINED,
                "severity": "Light",
                "amount": 1,
            }
        )
        self.selected_index = len(self.damage_entries) - 1
        self.refresh_list()
        self.load_selected_damage()
        self.change_command()

    def remove_damage(self):
        if self.selected_index is None:
            return

        del self.damage_entries[self.selected_index]

        if self.damage_entries:
            self.selected_index = min(
                self.selected_index,
                len(self.damage_entries) - 1,
            )
        else:
            self.selected_index = None

        self.refresh_list()
        self.load_selected_damage()
        self.change_command()

    def select_damage(self, event=None):
        if self.loading_damage:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        self.save_selected_damage()
        self.selected_index = selected_indices[0]
        self.load_selected_damage()

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for damage_entry in self.damage_entries:
            severity = damage_entry.get("severity", UNDEFINED)
            severity_display = WOUND_SEVERITY_DISPLAY.get(
                severity,
                severity,
            )
            amount = damage_entry.get("amount", "?")
            wound_type = damage_entry.get("type", UNDEFINED)
            self.listbox.insert(
                "end",
                f"{amount} {severity_display}: {wound_type}",
            )

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        self.remove_button.set_enabled(self.selected_index is not None)

    def load_selected_damage(self):
        self.loading_damage = True

        if self.selected_index is None:
            damage_entry = {}
            detail_enabled = False
        else:
            damage_entry = self.damage_entries[self.selected_index]
            detail_enabled = True

        self.type_field.set_value(damage_entry.get("type", UNDEFINED))
        self.severity_field.set_value(
            WOUND_SEVERITY_DISPLAY.get(
                damage_entry.get("severity", "Light"),
                "L",
            )
        )
        self.update_amount_limit()
        self.amount_field.set_value(damage_entry.get("amount", 1))
        self.set_detail_enabled(detail_enabled)
        self.loading_damage = False

    def save_selected_damage(self):
        if self.loading_damage or self.selected_index is None:
            return

        damage_entry = self.damage_entries[self.selected_index]
        damage_entry["type"] = self.type_field.get_value()
        damage_entry["severity"] = WOUND_SEVERITY_VALUES.get(
            self.severity_field.get_value(),
            "Light",
        )
        damage_entry["amount"] = self.amount_field.value.get().strip()

    def handle_severity_change(self, *arguments):
        self.update_amount_limit()
        self.handle_field_change()

    def update_amount_limit(self):
        severity = WOUND_SEVERITY_VALUES.get(
            self.severity_field.get_value(),
            "Light",
        )
        maximum = WOUND_AMOUNT_LIMITS.get(severity, 50)
        self.amount_field.set_limits(1, maximum)

    def handle_field_change(self, *arguments):
        if self.loading_damage or self.selected_index is None:
            return

        self.save_selected_damage()
        selected_index = self.selected_index
        self.refresh_list()
        self.selected_index = selected_index
        self.change_command()

    def set_detail_enabled(self, enabled):
        self.type_field.select.canvas.configure(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )
        self.severity_field.select.canvas.configure(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )
        self.amount_field.entry.set_enabled(enabled)
