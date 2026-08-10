import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.damage_editor import DamageEditor
from sections.nature_and_alchemy.creatures.form_fields import (
    LabeledEntry,
    RangeField,
)
from shared.widgets import MultilineField, SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)


class AttackEditor(tk.LabelFrame):
    def __init__(self, parent, change_command, list_height=12):
        super().__init__(
            parent,
            text="Attacks",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            padx=8,
            pady=8,
        )
        bind_theme(
            self,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.change_command = change_command
        self.loading_attack = False
        self.attacks = []
        self.selected_index = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.count_label = tk.Label(
            self.header,
            text="0 attacks",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        )
        self.count_label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.count_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.add_button = SoftButton(
            self.header,
            text="Add Attack",
            command=self.add_attack,
            width=100,
            height=30,
        )
        self.add_button.grid(row=0, column=1, padx=(8, 4))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_attack,
            width=80,
            height=30,
        )
        self.remove_button.grid(row=0, column=2, padx=(4, 0))

        self.body = tk.Frame(self, bg=SURFACE)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_columnconfigure(1, weight=1)
        self.body.grid_rowconfigure(0, weight=1)
        bind_theme(self.body, background="SURFACE")

        self.listbox = StripedListbox(
            self.body,
            width=16,
            height=list_height,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.listbox.bind("<<ListboxSelect>>", self.select_attack)
        self.detail = tk.Frame(self.body, bg=SURFACE)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.grid_columnconfigure(0, weight=1)
        self.detail.grid_columnconfigure(1, weight=1)
        self.detail.grid_rowconfigure(2, weight=1)
        bind_theme(self.detail, background="SURFACE")

        self.name_field = LabeledEntry(
            self.detail,
            "Attack Name",
            self.handle_field_change,
        )
        self.name_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
            pady=(0, 6),
        )

        self.roll_field = RangeField(
            self.detail,
            "Attack Roll",
            self.handle_field_change,
            minimum=1,
            maximum=50,
        )
        self.roll_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(6, 0),
            pady=(0, 6),
        )

        self.description_field = MultilineField(
            self.detail,
            "Attack Description",
            self.handle_text_change,
            height=1,
        )
        self.description_field.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 6),
        )

        self.immediate_damage_editor = DamageEditor(
            self.detail,
            "Immediate Damage",
            self.handle_field_change,
        )
        self.immediate_damage_editor.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 4),
        )

        self.ongoing_damage_editor = DamageEditor(
            self.detail,
            "Damage over Time",
            self.handle_field_change,
        )
        self.ongoing_damage_editor.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(4, 0),
        )

        self.set_detail_enabled(False)

    def set_attacks(self, attacks):
        self.loading_attack = True
        self.attacks = deepcopy(attacks) if isinstance(attacks, list) else []

        for attack in self.attacks:
            if "immediate_damage" not in attack:
                immediate_wound = attack.get("immediate_wound", {})
                attack["immediate_damage"] = (
                    [deepcopy(immediate_wound)]
                    if any(
                        immediate_wound.get(field_name)
                        for field_name in ("type", "severity", "amount")
                    )
                    else []
                )

            if "damage_over_time" not in attack:
                ongoing_wound = attack.get("damage_over_time_wound", {})
                attack["damage_over_time"] = (
                    [deepcopy(ongoing_wound)]
                    if any(
                        ongoing_wound.get(field_name)
                        for field_name in ("type", "severity", "amount")
                    )
                    else []
                )

            attack.pop("immediate_wound", None)
            attack.pop("damage_over_time_wound", None)

        self.selected_index = 0 if self.attacks else None
        self.refresh_list()
        self.load_selected_attack()
        self.loading_attack = False

    def get_attacks(self):
        self.save_selected_attack()
        converted_attacks = []
        normalized_names = set()

        for attack in self.attacks:
            attack_name = str(attack.get("name", "")).strip()

            if not attack_name:
                raise ValueError("Every attack must have a name")

            normalized_name = " ".join(attack_name.split()).casefold()

            if normalized_name in normalized_names:
                raise ValueError(f"Duplicate attack: {attack_name}")

            normalized_names.add(normalized_name)
            roll = attack.get("roll", {})
            roll_low = (
                None
                if str(roll.get("low", "")).strip() == ""
                else int(roll.get("low"))
            )
            roll_high = (
                None
                if str(roll.get("high", "")).strip() == ""
                else int(roll.get("high"))
            )
            immediate_damage = []

            for damage_entry in attack.get("immediate_damage", []):
                amount_text = str(damage_entry.get("amount", "")).strip()

                if not amount_text:
                    raise ValueError(
                        f"Every immediate damage entry for {attack_name} "
                        "must have an amount"
                    )

                immediate_damage.append(
                    {
                        "type": str(damage_entry.get("type", "")).strip(),
                        "severity": str(
                            damage_entry.get("severity", "")
                        ).strip(),
                        "amount": int(amount_text),
                    }
                )

            damage_over_time = []

            for damage_entry in attack.get("damage_over_time", []):
                amount_text = str(damage_entry.get("amount", "")).strip()

                if not amount_text:
                    raise ValueError(
                        f"Every damage-over-time entry for {attack_name} "
                        "must have an amount"
                    )

                damage_over_time.append(
                    {
                        "type": str(damage_entry.get("type", "")).strip(),
                        "severity": str(
                            damage_entry.get("severity", "")
                        ).strip(),
                        "amount": int(amount_text),
                    }
                )

            converted_attacks.append(
                {
                    "name": attack_name,
                    "roll": {
                        "low": roll_low,
                        "high": roll_high,
                    },
                    "description": str(
                        attack.get("description", "")
                    ).strip(),
                    "immediate_damage": immediate_damage,
                    "damage_over_time": damage_over_time,
                }
            )

        return converted_attacks

    def add_attack(self):
        if self.selected_index is not None:
            self.save_selected_attack()

        self.attacks.append(
            {
                "name": "New Attack",
                "roll": {"low": None, "high": None},
                "description": "",
                "immediate_damage": [],
                "damage_over_time": [],
            }
        )
        self.selected_index = len(self.attacks) - 1
        self.refresh_list()
        self.load_selected_attack()
        self.change_command()
        self.name_field.focus_set()

    def remove_attack(self):
        if self.selected_index is None:
            return

        del self.attacks[self.selected_index]

        if self.attacks:
            self.selected_index = min(
                self.selected_index,
                len(self.attacks) - 1,
            )
        else:
            self.selected_index = None

        self.refresh_list()
        self.load_selected_attack()
        self.change_command()

    def select_attack(self, event=None):
        if self.loading_attack:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        self.save_selected_attack()
        self.selected_index = selected_indices[0]
        self.load_selected_attack()

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for attack in self.attacks:
            self.listbox.insert("end", attack.get("name", "") or "Unnamed")

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        self.count_label.configure(text=f"{len(self.attacks)} attacks")
        self.remove_button.set_enabled(self.selected_index is not None)

    def load_selected_attack(self):
        self.loading_attack = True

        if self.selected_index is None:
            attack = {}
            detail_enabled = False
        else:
            attack = self.attacks[self.selected_index]
            detail_enabled = True

        self.name_field.set_value(attack.get("name"))
        self.roll_field.set_value(attack.get("roll", {}))
        self.description_field.set_value(attack.get("description", ""))
        self.immediate_damage_editor.set_damage_entries(
            attack.get("immediate_damage", [])
        )
        self.ongoing_damage_editor.set_damage_entries(
            attack.get("damage_over_time", [])
        )
        self.set_detail_enabled(detail_enabled)
        self.loading_attack = False

    def save_selected_attack(self):
        if self.loading_attack or self.selected_index is None:
            return

        self.immediate_damage_editor.save_selected_damage()
        self.ongoing_damage_editor.save_selected_damage()
        attack = self.attacks[self.selected_index]
        attack["name"] = self.name_field.get_value()
        attack["roll"] = {
            "low": self.roll_field.low_value.get().strip(),
            "high": self.roll_field.high_value.get().strip(),
        }
        attack["description"] = self.description_field.get_value()
        attack["immediate_damage"] = deepcopy(
            self.immediate_damage_editor.damage_entries
        )
        attack["damage_over_time"] = deepcopy(
            self.ongoing_damage_editor.damage_entries
        )

    def handle_field_change(self, *arguments):
        if self.loading_attack or self.selected_index is None:
            return

        self.save_selected_attack()
        selected_index = self.selected_index
        self.refresh_list()
        self.selected_index = selected_index
        self.change_command()

    def handle_text_change(self):
        self.handle_field_change()

    def set_detail_enabled(self, enabled):
        self.name_field.entry.set_enabled(enabled)
        self.roll_field.low_entry.set_enabled(enabled)
        self.roll_field.high_entry.set_enabled(enabled)
        self.description_field.text.configure(
            state="normal" if enabled else "disabled"
        )
        self.immediate_damage_editor.set_detail_enabled(
            enabled and self.immediate_damage_editor.selected_index is not None
        )
        self.ongoing_damage_editor.set_detail_enabled(
            enabled and self.ongoing_damage_editor.selected_index is not None
        )
