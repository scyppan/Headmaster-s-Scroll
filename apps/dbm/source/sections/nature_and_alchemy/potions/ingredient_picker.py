import tkinter as tk
from difflib import SequenceMatcher
from functools import partial
from tkinter import messagebox
from weakref import WeakKeyDictionary

from runtime_theme import bind_theme
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


CATALOG_COLLECTIONS = (
    ("Preparation", "preparations"),
    ("Potion", "potions"),
    ("Food/Drink", "foods_and_drinks"),
    ("General Item", "general_items"),
)

CATALOG_TYPE_ORDER = {
    "Plant Part": 0,
    "Creature Part": 1,
    "Preparation": 2,
    "Potion": 3,
    "Food/Drink": 4,
    "General Item": 5,
}

INGREDIENT_FILTERS = (
    ("All Ingredients", None, 112),
    ("Creature Parts", "Creature Part", 112),
    ("Plant Parts", "Plant Part", 94),
    ("Food/Drink", "Food/Drink", 92),
    ("Preparations", "Preparation", 104),
    ("Potions", "Potion", 76),
    ("General Items", "General Item", 104),
)


class IngredientCatalog:
    cached_catalogs = WeakKeyDictionary()

    def __init__(self, database):
        self.database = database
        self.entries_by_key = {}
        self.entries = self.build_entries()
        self.entries_by_type = {
            ingredient_type: [] for ingredient_type in CATALOG_TYPE_ORDER
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

        if (
            cached_entry is not None
            and cached_entry[0] == database_version
        ):
            return cached_entry[1]

        catalog = cls(database)
        cls.cached_catalogs[database] = (database_version, catalog)

        return catalog

    def build_entries(self):
        if self.database.has_container("plants"):
            for plant in self.database.get_collection("plants"):
                parent_name = str(plant.get("name", "")).strip()

                for part in plant.get("parts", []):
                    self.add_entry(
                        part.get("name", ""),
                        "Plant Part",
                        parent_name,
                    )

        if self.database.has_container("creatures"):
            for creature in self.database.get_collection("creatures"):
                parent_name = str(creature.get("name", "")).strip()

                for part in creature.get("parts", []):
                    self.add_entry(
                        part.get("name", ""),
                        "Creature Part",
                        parent_name,
                    )

        for ingredient_type, collection_name in CATALOG_COLLECTIONS:
            if not self.database.has_container(collection_name):
                continue

            for record in self.database.get_collection(collection_name):
                self.add_entry(
                    record.get("name", ""),
                    ingredient_type,
                    ingredient_type,
                )

        for collection_name in ("potions", "preparations"):
            if not self.database.has_container(collection_name):
                continue

            for record in self.database.get_collection(collection_name):
                for ingredient in record.get("ingredients", []):
                    self.add_entry(
                        ingredient.get("name", ""),
                        ingredient.get("type", "General Item"),
                        "Existing Recipe Ingredient",
                    )

        return sorted(
            self.entries_by_key.values(),
            key=self.sort_key,
        )

    def add_entry(self, name, ingredient_type, source_name):
        cleaned_name = " ".join(str(name).split())
        cleaned_type = str(ingredient_type).strip() or "General Item"
        cleaned_source = " ".join(str(source_name).split())

        if not cleaned_name or cleaned_type not in CATALOG_TYPE_ORDER:
            return

        normalized_name = cleaned_name.casefold()
        entry_key = f"{cleaned_type.casefold()}::{normalized_name}"

        if entry_key not in self.entries_by_key:
            self.entries_by_key[entry_key] = {
                "key": entry_key,
                "name": cleaned_name,
                "type": cleaned_type,
                "sources": [],
            }

        entry = self.entries_by_key[entry_key]

        if cleaned_source and cleaned_source not in entry["sources"]:
            entry["sources"].append(cleaned_source)

    def search(self, query, ingredient_type=None):
        normalized_query = " ".join(str(query).casefold().split())
        source_entries = (
            self.entries
            if ingredient_type is None
            else self.entries_by_type.get(ingredient_type, [])
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

        query_tokens = normalized_query.split()
        searchable_words = searchable_text.split()
        token_scores = []

        for query_token in query_tokens:
            token_scores.append(
                max(
                    SequenceMatcher(
                        None,
                        query_token,
                        searchable_word,
                    ).ratio()
                    for searchable_word in searchable_words
                )
            )

        if token_scores and min(token_scores) >= 0.62:
            return 4 + (1 - sum(token_scores) / len(token_scores))

        name_score = SequenceMatcher(
            None,
            normalized_query,
            normalized_name,
        ).ratio()

        if name_score >= 0.42:
            return 6 + (1 - name_score)

        return None

    def sort_key(self, entry):
        return (
            CATALOG_TYPE_ORDER[entry["type"]],
            entry["name"].casefold(),
        )


class IngredientPicker(tk.Toplevel):
    def __init__(self, parent, database):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.catalog = IngredientCatalog.for_database(database)
        self.visible_entries = []
        self.visible_entries_by_key = {}
        self.selected_key = None
        self.selected_ingredient = None
        self.suppress_selection = False
        self.active_filter_type = None
        self.filter_buttons = {}
        self.refresh_job = None

        self.title("Add Recipe Ingredient")
        self.geometry("760x640")
        self.minsize(600, 500)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="Choose an Ingredient",
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
            text="Search the Ingredient Catalog",
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
        self.search_entry.bind_input("<Down>", self.focus_results)

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
            ingredient_type,
            button_width,
        ) in enumerate(INGREDIENT_FILTERS):
            filter_button = SoftButton(
                self.filter_row,
                text=button_text,
                command=partial(self.set_filter, ingredient_type),
                background=SURFACE,
                width=button_width,
                height=32,
                font=app_font(8),
                padx=8,
                background_role="SURFACE",
            )
            filter_button.grid(
                row=button_index // 4,
                column=button_index % 4,
                sticky="ew",
                padx=(0 if button_index % 4 == 0 else 4, 0),
                pady=(0 if button_index < 4 else 4, 0),
            )
            self.filter_row.grid_columnconfigure(
                button_index % 4,
                weight=1,
            )
            self.filter_buttons[ingredient_type] = filter_button

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

        self.selection_value = tk.StringVar(value="Select an ingredient")
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
        self.quantity_row.grid_columnconfigure(1, weight=1)
        bind_theme(self.quantity_row, background="SURFACE")

        self.quantity_label = tk.Label(
            self.quantity_row,
            text="Quantity Required",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.quantity_label.grid(row=0, column=0, sticky="w", padx=(0, 12))
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
        self.quantity_entry.grid(row=0, column=1, sticky="w")
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
            text="Add Ingredient",
            command=self.accept,
            background=APP_BACKGROUND,
            width=132,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.add_button.pack(side="left")
        self.add_button.set_enabled(False)

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

    def set_filter(self, ingredient_type):
        if ingredient_type == self.active_filter_type:
            return

        self.active_filter_type = ingredient_type
        self.update_filter_buttons()
        self.refresh_results()

    def update_filter_buttons(self):
        for ingredient_type, filter_button in self.filter_buttons.items():
            if ingredient_type == self.active_filter_type:
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

    def refresh_results(self, *arguments):
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
            self.listbox.see(selected_index)
            self.selected_key = self.visible_entries[selected_index]["key"]

        self.suppress_selection = False
        visible_count = len(self.visible_entries)
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
            f"{visible_count} of {total_count} catalog items"
            if visible_count != total_count
            else f"{total_count} catalog items"
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

        if not selected_indices:
            self.selected_key = None
        else:
            self.selected_key = self.visible_entries[
                selected_indices[0]
            ]["key"]

        self.update_selected_entry()

    def update_selected_entry(self):
        selected_entry = self.get_selected_entry()

        if selected_entry is None:
            self.selection_value.set("No matching ingredient selected")
            self.add_button.set_enabled(False)
            return

        source_names = selected_entry["sources"]
        source_text = ", ".join(source_names[:3])

        if len(source_names) > 3:
            source_text = f"{source_text}, and {len(source_names) - 3} more"

        self.selection_value.set(
            f"{selected_entry['type']} · {source_text}"
            if source_text
            else selected_entry["type"]
        )
        self.add_button.set_enabled(True)

    def get_selected_entry(self):
        return self.visible_entries_by_key.get(self.selected_key)

    def focus_results(self, event=None):
        self.flush_scheduled_refresh()

        if not self.visible_entries:
            return "break"

        self.listbox.focus_set()
        self.listbox.selection_set(0)
        self.listbox.activate(0)

        return "break"

    def validate_quantity_input(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def accept(self, event=None):
        self.flush_scheduled_refresh()
        selected_entry = self.get_selected_entry()

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

        self.selected_ingredient = {
            "name": selected_entry["name"],
            "type": selected_entry["type"],
            "quantity": int(quantity_text),
        }
        self.destroy()

        return "break"

    def cancel(self, event=None):
        self.selected_ingredient = None
        self.destroy()

        return "break"
