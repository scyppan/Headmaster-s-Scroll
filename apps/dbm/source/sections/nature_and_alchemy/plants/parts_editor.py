import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.constants import (
    PROFICIENCY_DEFAULTS,
)
from sections.nature_and_alchemy.creatures.form_fields import (
    LabeledEntry,
    LabeledSelect,
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


class PlantPartsEditor(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.database = database
        self.loading_part = False
        self.parts = []
        self.selected_index = None

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text="Plant Parts",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12),
            anchor="w",
        )
        self.title.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.add_button = SoftButton(
            self.header,
            text="Add",
            command=self.add_part,
            width=72,
            height=34,
        )
        self.add_button.grid(row=0, column=1, padx=(8, 4))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_part,
            width=88,
            height=34,
        )
        self.remove_button.grid(row=0, column=2, padx=(4, 0))

        self.body = tk.Frame(self, bg=SURFACE)
        self.body.grid(row=1, column=0, sticky="nsew")
        self.body.grid_rowconfigure(0, weight=1)
        self.body.grid_columnconfigure(1, weight=1)
        bind_theme(self.body, background="SURFACE")

        self.listbox = StripedListbox(
            self.body,
            width=27,
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
        self.listbox.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.listbox.bind("<<ListboxSelect>>", self.select_part)

        self.detail = tk.Frame(self.body, bg=SURFACE)
        self.detail.grid(row=0, column=1, sticky="nsew")
        self.detail.grid_columnconfigure(0, weight=1)
        self.detail.grid_columnconfigure(1, weight=1)
        self.detail.grid_rowconfigure(1, weight=1, minsize=180)
        self.detail.grid_rowconfigure(2, weight=1, minsize=180)
        bind_theme(self.detail, background="SURFACE")

        self.name_field = LabeledEntry(
            self.detail,
            "Part Name",
            self.handle_field_change,
        )
        self.name_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )

        self.proficiency_field = LabeledSelect(
            self.detail,
            "Requires Proficiency",
            self.get_proficiency_options(),
            self.handle_field_change,
        )
        self.proficiency_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 0),
        )

        self.description_field = MultilineField(
            self.detail,
            "Description",
            self.handle_field_change,
            height=7,
        )
        self.description_field.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(12, 0),
        )

        self.raw_effects_field = MultilineField(
            self.detail,
            "Raw Effects",
            self.handle_field_change,
            height=7,
        )
        self.raw_effects_field.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 8),
            pady=(12, 0),
        )

        self.potion_effects_field = MultilineField(
            self.detail,
            "Effect in Potions",
            self.handle_field_change,
            height=7,
        )
        self.potion_effects_field.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(8, 0),
            pady=(12, 0),
        )

        self.set_detail_enabled(False)

    def set_parts(self, parts):
        self.loading_part = True
        self.parts = deepcopy(parts) if isinstance(parts, list) else []
        self.selected_index = 0 if self.parts else None
        self.refresh_list()
        self.load_selected_part()
        self.loading_part = False

    def get_parts(self):
        self.save_selected_part()
        converted_parts = []
        normalized_names = set()

        for part in self.parts:
            part_name = str(part.get("name", "")).strip()

            if not part_name:
                raise ValueError("Every plant part must have a name")

            normalized_name = " ".join(part_name.split()).casefold()

            if normalized_name in normalized_names:
                raise ValueError(f"Duplicate plant part: {part_name}")

            normalized_names.add(normalized_name)
            required_proficiency = str(
                part.get("required_proficiency", "No")
            ).strip() or "No"
            converted_parts.append(
                {
                    "name": part_name,
                    "required_proficiency": required_proficiency,
                    "description": str(
                        part.get("description", "")
                    ).strip(),
                    "raw_effects": str(
                        part.get("raw_effects", "")
                    ).strip(),
                    "effect_in_potions": str(
                        part.get("effect_in_potions", "")
                    ).strip(),
                }
            )

        return converted_parts

    def add_part(self):
        if self.selected_index is not None:
            self.save_selected_part()

        self.parts.append(
            {
                "name": "New Plant Part",
                "required_proficiency": "No",
                "description": "",
                "raw_effects": "",
                "effect_in_potions": "",
            }
        )
        self.selected_index = len(self.parts) - 1
        self.refresh_list()
        self.load_selected_part()
        self.change_command()
        self.name_field.focus_set()

    def remove_part(self):
        if self.selected_index is None:
            return

        del self.parts[self.selected_index]

        if self.parts:
            self.selected_index = min(
                self.selected_index,
                len(self.parts) - 1,
            )
        else:
            self.selected_index = None

        self.refresh_list()
        self.load_selected_part()
        self.change_command()

    def select_part(self, event=None):
        if self.loading_part:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        self.save_selected_part()
        self.selected_index = selected_indices[0]
        self.load_selected_part()

    def refresh_list(self):
        self.listbox.delete(0, "end")

        for part in self.parts:
            self.listbox.insert("end", part.get("name", "") or "Unnamed")

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        self.remove_button.set_enabled(self.selected_index is not None)

    def load_selected_part(self):
        self.loading_part = True

        if self.selected_index is None:
            part = {}
            detail_enabled = False
        else:
            part = self.parts[self.selected_index]
            detail_enabled = True

        self.name_field.set_value(part.get("name"))
        self.proficiency_field.set_values(self.get_proficiency_options())
        self.proficiency_field.set_value(
            part.get("required_proficiency", "No") or "No"
        )
        self.description_field.set_value(part.get("description", ""))
        self.raw_effects_field.set_value(part.get("raw_effects", ""))
        self.potion_effects_field.set_value(
            part.get("effect_in_potions", "")
        )
        self.set_detail_enabled(detail_enabled)
        self.loading_part = False

    def save_selected_part(self):
        if self.loading_part or self.selected_index is None:
            return

        part = self.parts[self.selected_index]
        part["name"] = self.name_field.get_value()
        part["required_proficiency"] = self.proficiency_field.get_value()
        part["description"] = self.description_field.get_value()
        part["raw_effects"] = self.raw_effects_field.get_value()
        part["effect_in_potions"] = self.potion_effects_field.get_value()

    def handle_field_change(self, *arguments):
        if self.loading_part or self.selected_index is None:
            return

        self.save_selected_part()
        self.refresh_list()
        self.change_command()

    def set_detail_enabled(self, enabled):
        self.name_field.entry.set_enabled(enabled)
        self.proficiency_field.select.canvas.configure(
            state="normal" if enabled else "disabled",
            cursor="hand2" if enabled else "arrow",
        )
        text_state = "normal" if enabled else "disabled"
        self.description_field.text.configure(state=text_state)
        self.raw_effects_field.text.configure(state=text_state)
        self.potion_effects_field.text.configure(state=text_state)

    def get_proficiency_options(self):
        proficiency_names = sorted(
            {
                str(record.get("name", "")).strip()
                for record in self.database.get_collection("proficiencies")
                if str(record.get("name", "")).strip()
            },
            key=str.casefold,
        )

        return (*PROFICIENCY_DEFAULTS, *proficiency_names)
