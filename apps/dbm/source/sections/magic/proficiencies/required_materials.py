import tkinter as tk
from copy import deepcopy
from difflib import SequenceMatcher
from functools import partial
from tkinter import messagebox
from weakref import WeakKeyDictionary

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from shared.widgets import RoundedEntry, SoftButton, StripedListbox
from theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


REQUIRED_MATERIAL_TYPES = (
    "Creature",
    "Plant",
    "Creature Part",
    "Plant Part",
    "Preparation",
    "Potion",
    "General Item",
    "Food/Drink",
)

MATERIAL_COLLECTIONS = (
    ("Preparation", "preparations"),
    ("Potion", "potions"),
    ("General Item", "general_items"),
    ("Food/Drink", "foods_and_drinks"),
)

MATERIAL_FILTERS = (
    ("All Materials", None, 108),
    ("Creatures", "Creature", 86),
    ("Plants", "Plant", 72),
    ("Creature Parts", "Creature Part", 108),
    ("Plant Parts", "Plant Part", 92),
    ("Preparations", "Preparation", 100),
    ("Potions", "Potion", 72),
    ("General Items", "General Item", 102),
    ("Food/Drink", "Food/Drink", 90),
)


class RequiredMaterialCatalog:
    cached_catalogs = WeakKeyDictionary()

    def __init__(self, database):
        self.database = database
        self.entries_by_key = {}
        self.entries = self.build_entries()
        self.entries_by_type = {
            material_type: [] for material_type in REQUIRED_MATERIAL_TYPES
        }

        for entry in self.entries:
            self.entries_by_type[entry["type"]].append(entry)

    @classmethod
    def for_database(cls, database):
        database_version = database.get_database_metadata().get(
            "last_saved",
            "",
        )
        cached_entry = cls.cached_catalogs.get(database)

        if cached_entry is not None and cached_entry[0] == database_version:
            return cached_entry[1]

        catalog = cls(database)
        cls.cached_catalogs[database] = (database_version, catalog)

        return catalog

    def build_entries(self):
        if self.database.has_container("creatures"):
            for creature in self.database.get_collection("creatures"):
                parent_name = str(creature.get("name", "")).strip()
                self.add_entry(parent_name, "Creature", "Creatures")

                for part in creature.get("parts", []):
                    self.add_entry(
                        part.get("name", ""),
                        "Creature Part",
                        parent_name,
                    )

        if self.database.has_container("plants"):
            for plant in self.database.get_collection("plants"):
                parent_name = str(plant.get("name", "")).strip()
                self.add_entry(parent_name, "Plant", "Plants")

                for part in plant.get("parts", []):
                    self.add_entry(
                        part.get("name", ""),
                        "Plant Part",
                        parent_name,
                    )

        for material_type, collection_name in MATERIAL_COLLECTIONS:
            if not self.database.has_container(collection_name):
                continue

            for record in self.database.get_collection(collection_name):
                self.add_entry(
                    record.get("name", ""),
                    material_type,
                    material_type,
                )

        return sorted(self.entries_by_key.values(), key=self.sort_key)

    def add_entry(self, name, material_type, source_name):
        cleaned_name = " ".join(str(name).split())
        cleaned_source = " ".join(str(source_name).split())

        if not cleaned_name or material_type not in REQUIRED_MATERIAL_TYPES:
            return

        entry_key = f"{material_type.casefold()}::{cleaned_name.casefold()}"

        if entry_key not in self.entries_by_key:
            self.entries_by_key[entry_key] = {
                "key": entry_key,
                "name": cleaned_name,
                "type": material_type,
                "sources": [],
            }

        entry = self.entries_by_key[entry_key]

        if cleaned_source and cleaned_source not in entry["sources"]:
            entry["sources"].append(cleaned_source)

    def search(self, query, material_type=None):
        normalized_query = " ".join(str(query).casefold().split())
        source_entries = (
            self.entries
            if material_type is None
            else self.entries_by_type.get(material_type, [])
        )

        if not normalized_query:
            return list(source_entries)

        ranked_entries = []

        for entry in source_entries:
            score = self.match_score(entry, normalized_query)

            if score is not None:
                ranked_entries.append((score, self.sort_key(entry), entry))

        ranked_entries.sort(key=lambda ranked_entry: ranked_entry[:2])

        return [ranked_entry[2] for ranked_entry in ranked_entries]

    def match_score(self, entry, normalized_query):
        normalized_name = entry["name"].casefold()
        searchable_text = " ".join(
            (
                normalized_name,
                entry["type"].casefold(),
                " ".join(entry["sources"]).casefold(),
            )
        )

        if normalized_query == normalized_name:
            return 0

        if normalized_name.startswith(normalized_query):
            return 1

        if normalized_query in normalized_name:
            return 2 + normalized_name.index(normalized_query) / 1000

        if normalized_query in searchable_text:
            return 3

        similarity = SequenceMatcher(
            None,
            normalized_query,
            normalized_name,
        ).ratio()

        if similarity >= 0.42:
            return 5 + (1 - similarity)

        return None

    def sort_key(self, entry):
        return (
            REQUIRED_MATERIAL_TYPES.index(entry["type"]),
            entry["name"].casefold(),
        )

    def contains(self, material_name, material_type):
        material_key = (
            f"{str(material_type).casefold()}::"
            f"{' '.join(str(material_name).split()).casefold()}"
        )

        return material_key in self.entries_by_key


class RequiredMaterialPicker(tk.Toplevel):
    def __init__(self, parent, database):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.catalog = RequiredMaterialCatalog.for_database(database)
        self.visible_entries = []
        self.visible_entries_by_key = {}
        self.selected_key = None
        self.selected_material = None
        self.suppress_selection = False
        self.active_filter_type = None
        self.filter_buttons = {}
        self.refresh_job = None

        self.title("Add Required Material")
        self.geometry("800x660")
        self.minsize(640, 520)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="Choose a Required Material",
            bg=APP_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(16),
            anchor="w",
        )
        self.heading.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=24,
            pady=(20, 12),
        )
        bind_theme(
            self.heading,
            background="APP_BACKGROUND",
            foreground="TEXT_DARK",
        )

        self.card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.card.grid(row=1, column=0, sticky="nsew", padx=24)
        self.card.grid_rowconfigure(4, weight=1)
        self.card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.search_label = tk.Label(
            self.card,
            text="Search All Available Materials",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.search_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(16, 6),
        )
        bind_theme(
            self.search_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.schedule_refresh)
        self.search_entry = RoundedEntry(
            self.card,
            textvariable=self.search_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 10),
        )

        self.filter_row = tk.Frame(self.card, bg=SURFACE)
        self.filter_row.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 8),
        )
        bind_theme(self.filter_row, background="SURFACE")

        for button_index, (
            button_text,
            material_type,
            button_width,
        ) in enumerate(MATERIAL_FILTERS):
            filter_button = SoftButton(
                self.filter_row,
                text=button_text,
                command=partial(self.set_filter, material_type),
                background=SURFACE,
                width=button_width,
                height=32,
                font=app_font(8),
                padx=8,
                background_role="SURFACE",
            )
            filter_button.grid(
                row=button_index // 5,
                column=button_index % 5,
                sticky="ew",
                padx=(0 if button_index % 5 == 0 else 4, 0),
                pady=(0 if button_index < 5 else 4, 0),
            )
            self.filter_row.grid_columnconfigure(
                button_index % 5,
                weight=1,
            )
            self.filter_buttons[material_type] = filter_button

        self.count_value = tk.StringVar()
        self.count_label = tk.Label(
            self.card,
            textvariable=self.count_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.count_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 7),
        )
        bind_theme(
            self.count_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.listbox = StripedListbox(
            self.card,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(
            row=4,
            column=0,
            sticky="nsew",
            padx=(18, 0),
        )
        self.listbox.bind("<<ListboxSelect>>", self.select_entry)
        self.listbox.bind("<Double-Button-1>", self.accept)

        self.scrollbar = tk.Scrollbar(
            self.card,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(
            row=4,
            column=1,
            sticky="ns",
            padx=(0, 18),
        )
        self.listbox.configure(yscrollcommand=self.scrollbar.set)

        self.selection_value = tk.StringVar(value="Select a material")
        self.selection_label = tk.Label(
            self.card,
            textvariable=self.selection_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.selection_label.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(9, 0),
        )
        bind_theme(
            self.selection_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.quantity_row = tk.Frame(self.card, bg=SURFACE)
        self.quantity_row.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(10, 16),
        )
        bind_theme(self.quantity_row, background="SURFACE")

        self.quantity_label = tk.Label(
            self.quantity_row,
            text="Quantity Required",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.quantity_label.pack(side="left", padx=(0, 12))
        bind_theme(
            self.quantity_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.quantity_value = tk.StringVar(value="1")
        self.quantity_entry = RoundedEntry(
            self.quantity_row,
            textvariable=self.quantity_value,
            background=SURFACE,
            width=110,
            height=38,
            justify="center",
            font=app_font(10),
        )
        self.quantity_entry.pack(side="left")
        quantity_validation = (
            self.register(self.validate_quantity_input),
            "%P",
        )
        self.quantity_entry.entry.configure(
            validate="key",
            validatecommand=quantity_validation,
        )

        self.button_row = tk.Frame(self, bg=APP_BACKGROUND)
        self.button_row.grid(
            row=2,
            column=0,
            sticky="e",
            padx=24,
            pady=20,
        )
        bind_theme(self.button_row, background="APP_BACKGROUND")

        self.cancel_button = SoftButton(
            self.button_row,
            text="Cancel",
            command=self.cancel,
            background=APP_BACKGROUND,
            width=90,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.cancel_button.pack(side="left", padx=(0, 6))

        self.add_button = SoftButton(
            self.button_row,
            text="Add Material",
            command=self.accept,
            background=APP_BACKGROUND,
            width=124,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.add_button.pack(side="left")

        self.bind("<Escape>", self.cancel)
        self.bind("<Return>", self.accept)
        self.update_filter_buttons()
        self.refresh_results()
        self.grab_set()
        self.search_entry.focus_set()

    def schedule_refresh(self, *arguments):
        if self.refresh_job is not None:
            self.after_cancel(self.refresh_job)

        self.refresh_job = self.after(90, self.refresh_results)

    def set_filter(self, material_type):
        if material_type == self.active_filter_type:
            return

        self.active_filter_type = material_type
        self.update_filter_buttons()
        self.refresh_results()

    def update_filter_buttons(self):
        for material_type, filter_button in self.filter_buttons.items():
            if material_type == self.active_filter_type:
                filter_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                filter_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def refresh_results(self):
        self.refresh_job = None
        previous_key = self.selected_key
        self.visible_entries = self.catalog.search(
            self.search_value.get(),
            self.active_filter_type,
        )
        self.visible_entries_by_key = {
            entry["key"]: entry for entry in self.visible_entries
        }
        self.suppress_selection = True
        self.listbox.delete(0, "end")
        display_rows = [
            f"[{entry['type']}] {entry['name']}"
            for entry in self.visible_entries
        ]

        if display_rows:
            self.listbox.insert("end", *display_rows)

        self.selected_key = None

        if self.visible_entries:
            selected_index = 0

            for entry_index, entry in enumerate(self.visible_entries):
                if entry["key"] == previous_key:
                    selected_index = entry_index
                    break

            self.listbox.selection_set(selected_index)
            self.listbox.activate(selected_index)
            self.selected_key = self.visible_entries[selected_index]["key"]

        self.suppress_selection = False
        total_count = (
            len(self.catalog.entries)
            if self.active_filter_type is None
            else len(
                self.catalog.entries_by_type.get(
                    self.active_filter_type,
                    [],
                )
            )
        )
        self.count_value.set(
            f"{len(self.visible_entries)} of {total_count} materials"
        )
        self.update_selected_entry()

    def flush_scheduled_refresh(self):
        if self.refresh_job is None:
            return

        self.after_cancel(self.refresh_job)
        self.refresh_results()

    def select_entry(self, event=None):
        if self.suppress_selection:
            return

        selected_indices = self.listbox.curselection()
        self.selected_key = (
            None
            if not selected_indices
            else self.visible_entries[selected_indices[0]]["key"]
        )
        self.update_selected_entry()

    def update_selected_entry(self):
        selected_entry = self.visible_entries_by_key.get(self.selected_key)

        if selected_entry is None:
            self.selection_value.set("No matching material selected")
            self.add_button.set_enabled(False)
            return

        source_text = ", ".join(selected_entry["sources"][:3])
        self.selection_value.set(
            f"{selected_entry['type']} · {source_text}"
            if source_text
            else selected_entry["type"]
        )
        self.add_button.set_enabled(True)

    def validate_quantity_input(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def accept(self, event=None):
        self.flush_scheduled_refresh()
        selected_entry = self.visible_entries_by_key.get(self.selected_key)

        if selected_entry is None:
            return "break"

        quantity_text = self.quantity_value.get().strip()

        if not quantity_text or int(quantity_text) < 1:
            messagebox.showerror(
                "Quantity required",
                "Quantity must be a whole number of at least 1.",
                parent=self,
            )
            self.quantity_entry.focus_set()
            return "break"

        self.selected_material = {
            "name": selected_entry["name"],
            "type": selected_entry["type"],
            "quantity": int(quantity_text),
        }
        self.destroy()

        return "break"

    def cancel(self, event=None):
        self.selected_material = None
        self.destroy()

        return "break"


class RequiredMaterialsEditor(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
        self.loading_material = False
        self.materials = []
        self.selected_index = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=4)
        self.grid_columnconfigure(1, weight=2)
        self.grid_columnconfigure(2, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 10),
        )
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text="Required Materials",
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
            text="Search & Add",
            command=self.add_material,
            width=112,
            height=34,
        )
        self.add_button.grid(row=0, column=1, padx=(8, 4))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_material,
            width=84,
            height=34,
        )
        self.remove_button.grid(row=0, column=2)

        self.name_field = LabeledEntry(
            self,
            "Selected Material",
            self.handle_field_change,
            font_size=11,
        )
        self.name_field.grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self.type_field = LabeledEntry(
            self,
            "Material Type",
            self.handle_field_change,
        )
        self.type_field.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )

        self.quantity_field = LabeledEntry(
            self,
            "Quantity",
            self.handle_field_change,
            justify="center",
            font_size=10,
        )
        self.quantity_field.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(12, 0),
            pady=(0, 12),
        )
        quantity_validation = (
            self.register(self.validate_quantity_input),
            "%P",
        )
        self.quantity_field.entry.entry.configure(
            validate="key",
            validatecommand=quantity_validation,
        )

        self.listbox = StripedListbox(
            self,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
        )
        self.listbox.bind("<<ListboxSelect>>", self.select_material)

        self.set_detail_enabled(False)

    def set_materials(self, materials):
        self.loading_material = True
        self.materials = (
            deepcopy(materials) if isinstance(materials, list) else []
        )
        self.selected_index = 0 if self.materials else None
        self.refresh_list()
        self.load_selected_material()
        self.loading_material = False

    def get_materials(self):
        self.save_selected_material()

        for material in self.materials:
            quantity = material.get("quantity")
            material_name = str(material.get("name", "")).strip()

            if isinstance(quantity, bool) or not isinstance(quantity, int):
                raise TypeError(
                    f"Quantity for {material_name} must be a whole number."
                )

            if quantity < 1:
                raise ValueError(
                    f"Quantity for {material_name} must be at least 1."
                )

        return deepcopy(self.materials)

    def add_material(self):
        self.save_selected_material()
        picker = RequiredMaterialPicker(self, self.database)
        self.wait_window(picker)

        if picker.selected_material is None:
            return

        material_key = (
            picker.selected_material["type"].casefold(),
            picker.selected_material["name"].casefold(),
        )
        existing_keys = {
            (
                str(material.get("type", "")).casefold(),
                str(material.get("name", "")).casefold(),
            )
            for material in self.materials
        }

        if material_key in existing_keys:
            messagebox.showerror(
                "Material already required",
                "That material is already in the requirements list. "
                "Select it and change its quantity instead.",
                parent=self,
            )
            return

        self.materials.append(picker.selected_material)
        self.selected_index = len(self.materials) - 1
        self.refresh_list()
        self.load_selected_material()
        self.change_command()
        self.quantity_field.focus_set()

    def remove_material(self):
        if self.selected_index is None:
            return

        del self.materials[self.selected_index]
        self.selected_index = (
            min(self.selected_index, len(self.materials) - 1)
            if self.materials
            else None
        )
        self.refresh_list()
        self.load_selected_material()
        self.change_command()

    def select_material(self, event=None):
        if self.loading_material:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]

        if selected_index == self.selected_index:
            return

        self.save_selected_material()
        self.selected_index = selected_index
        self.load_selected_material()

    def refresh_list(self):
        self.loading_material = True
        self.listbox.delete(0, "end")

        if self.materials:
            self.listbox.insert(
                "end",
                *(
                    "• "
                    f"{material.get('quantity', '?')} × "
                    f"[{material.get('type', '')}] "
                    f"{material.get('name', '')}"
                    for material in self.materials
                ),
            )

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        self.loading_material = False
        self.remove_button.set_enabled(self.selected_index is not None)

    def load_selected_material(self):
        self.loading_material = True

        if self.selected_index is None:
            self.name_field.set_value("")
            self.type_field.set_value("")
            self.quantity_field.set_value("")
            self.set_detail_enabled(False)
        else:
            material = self.materials[self.selected_index]
            self.name_field.set_value(material.get("name", ""))
            self.type_field.set_value(material.get("type", ""))
            self.quantity_field.set_value(material.get("quantity", 1))
            self.set_detail_enabled(True)

        self.loading_material = False

    def save_selected_material(self):
        if self.selected_index is None:
            return

        quantity_text = self.quantity_field.get_value()
        updated_material = dict(self.materials[self.selected_index])
        updated_material["quantity"] = (
            int(quantity_text) if quantity_text else None
        )
        self.materials[self.selected_index] = updated_material

    def handle_field_change(self, *arguments):
        if self.loading_material or self.selected_index is None:
            return

        self.save_selected_material()
        self.refresh_list()
        self.change_command()

    def set_detail_enabled(self, enabled):
        self.name_field.entry.set_enabled(False)
        self.type_field.entry.set_enabled(False)
        self.quantity_field.entry.set_enabled(enabled)

    def validate_quantity_input(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()
