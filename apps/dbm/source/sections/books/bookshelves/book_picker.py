import tkinter as tk
from difflib import SequenceMatcher
from functools import partial

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


BOOK_SEARCH_SCOPES = (
    ("All", "all", 68),
    ("Title", "title", 72),
    ("Category", "categories", 92),
    ("Spells", "spells", 78),
    ("Proficiencies", "proficiencies", 116),
    ("Potions", "potions", 82),
)


class BookPicker(tk.Toplevel):
    def __init__(
        self,
        parent,
        database,
        excluded_record_ids,
        recent_record_ids=(),
    ):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.excluded_record_ids = set(excluded_record_ids)
        self.recent_record_ids = tuple(
            dict.fromkeys(
                str(record_id).strip()
                for record_id in recent_record_ids
                if str(record_id).strip()
            )
        )
        self.recent_positions = {
            record_id: position
            for position, record_id in enumerate(self.recent_record_ids)
        }
        self.entries = self.build_entries()
        self.visible_entries = []
        self.selected_references = []
        self.active_scope = "all"
        self.scope_buttons = {}
        self.refresh_job = None

        self.title("Choose Books")
        self.geometry("780x650")
        self.minsize(680, 520)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="Choose Books",
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
        self.card.grid_rowconfigure(6, weight=1)
        self.card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.scope_label = tk.Label(
            self.card,
            text="Search Within",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.scope_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(16, 6),
        )
        bind_theme(
            self.scope_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.scope_row = tk.Frame(self.card, bg=SURFACE)
        self.scope_row.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 12),
        )
        bind_theme(self.scope_row, background="SURFACE")

        for scope_label, scope_name, button_width in BOOK_SEARCH_SCOPES:
            scope_button = SoftButton(
                self.scope_row,
                text=scope_label,
                command=partial(self.set_scope, scope_name),
                background=SURFACE,
                width=button_width,
                height=32,
                font=app_font(9),
            )
            scope_button.pack(side="left", padx=(0, 5))
            self.scope_buttons[scope_name] = scope_button

        self.search_label = tk.Label(
            self.card,
            text="Fuzzy Search",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.search_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 6),
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
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 6),
        )

        self.search_hint = tk.Label(
            self.card,
            text=(
                "All searches titles, authors, descriptions, categories, "
                "spells, proficiencies, and potions."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.search_hint.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=18,
            pady=(0, 4),
        )
        bind_theme(
            self.search_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

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
            row=5,
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
            selectmode="extended",
        )
        self.listbox.grid(
            row=6,
            column=0,
            sticky="nsew",
            padx=(18, 0),
            pady=(0, 16),
        )
        self.listbox.bind("<<ListboxSelect>>", self.update_add_state)
        self.listbox.bind("<Double-Button-1>", self.accept)

        self.scrollbar = tk.Scrollbar(
            self.card,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(
            row=6,
            column=1,
            sticky="ns",
            padx=(0, 18),
            pady=(0, 16),
        )
        self.listbox.configure(yscrollcommand=self.scrollbar.set)

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
            text="Add Selected",
            command=self.accept,
            background=APP_BACKGROUND,
            width=122,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.add_button.pack(side="left")

        self.bind("<Escape>", self.cancel)
        self.refresh_results()
        self.update_scope_buttons()
        self.update_add_state()
        self.grab_set()
        self.search_entry.focus_set()

    def build_entries(self):
        entries = []

        for book in self.database.get_collection("books"):
            record_id = str(book.get("record_id", "")).strip()

            if not record_id or record_id in self.excluded_record_ids:
                continue

            entries.append(self.build_entry(book))

        entries.sort(
            key=lambda entry: (
                entry["name"].casefold(),
                entry["author"].casefold(),
                entry["record_id"],
            )
        )

        return entries

    @staticmethod
    def build_entry(book):
        name = str(book.get("name", "")).strip() or "Unnamed book"
        author = str(book.get("author", "")).strip()
        categories = [
            str(category).strip()
            for category in book.get("categories", [])
            if str(category).strip()
        ]
        spells = [
            str(reference.get("name", "")).strip()
            for reference in book.get("spells", [])
            if str(reference.get("name", "")).strip()
        ]
        proficiencies = [
            str(reference.get("name", "")).strip()
            for reference in book.get("proficiencies", [])
            if str(reference.get("name", "")).strip()
        ]
        potions = [
            str(reference.get("name", "")).strip()
            for reference in book.get("potions", [])
            if str(reference.get("name", "")).strip()
        ]
        detail_values = []

        if author:
            detail_values.append(author)

        if categories:
            detail_values.append(", ".join(categories))

        label = name

        if detail_values:
            label = f"{name} — {' • '.join(detail_values)}"

        title_values = [name]
        all_values = [
            name,
            author,
            str(book.get("description", "")).strip(),
            *categories,
            *spells,
            *proficiencies,
            *potions,
        ]

        return {
            "record_id": str(book.get("record_id", "")).strip(),
            "name": name,
            "author": author,
            "label": label,
            "search_values": {
                "all": BookPicker.normalize_search_values(all_values),
                "title": BookPicker.normalize_search_values(title_values),
                "categories": BookPicker.normalize_search_values(categories),
                "spells": BookPicker.normalize_search_values(spells),
                "proficiencies": BookPicker.normalize_search_values(
                    proficiencies
                ),
                "potions": BookPicker.normalize_search_values(potions),
            },
        }

    @staticmethod
    def normalize_search_values(values):
        return tuple(
            " ".join(str(value).casefold().split())
            for value in values
            if str(value).strip()
        )

    @staticmethod
    def rank_entry(entry, query, scope_name):
        if not query:
            return 0

        search_values = entry["search_values"].get(scope_name, ())
        best_score = None

        for search_value in search_values:
            if search_value == query:
                score = 0
            elif search_value.startswith(query):
                score = 1
            elif query in search_value:
                score = 2 + search_value.index(query) / 1000
            else:
                similarity = SequenceMatcher(
                    None,
                    query,
                    search_value,
                ).ratio()

                if similarity < 0.42:
                    continue

                score = 4 + (1 - similarity)

            if best_score is None or score < best_score:
                best_score = score

        return best_score

    def set_scope(self, scope_name):
        if scope_name == self.active_scope:
            return

        self.active_scope = scope_name
        self.update_scope_buttons()
        self.refresh_results()

    def update_scope_buttons(self):
        for scope_name, scope_button in self.scope_buttons.items():
            if scope_name == self.active_scope:
                scope_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                scope_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def schedule_refresh(self, *arguments):
        if self.refresh_job is not None:
            self.after_cancel(self.refresh_job)

        self.refresh_job = self.after(80, self.refresh_results)

    def refresh_results(self):
        self.refresh_job = None
        query = " ".join(self.search_value.get().casefold().split())
        ranked_entries = []

        for entry in self.entries:
            score = self.rank_entry(entry, query, self.active_scope)

            if score is None:
                continue

            recent_position = self.recent_positions.get(entry["record_id"])

            if query or recent_position is None:
                recent_group = 1
                recent_order = 0
            else:
                recent_group = 0
                recent_order = recent_position

            ranked_entries.append(
                (
                    score,
                    recent_group,
                    recent_order,
                    entry["name"].casefold(),
                    entry["author"].casefold(),
                    entry["record_id"],
                    entry,
                )
            )

        ranked_entries.sort(key=lambda ranked_entry: ranked_entry[:6])
        self.visible_entries = [
            ranked_entry[6] for ranked_entry in ranked_entries
        ]
        self.listbox.delete(0, "end")

        if self.visible_entries:
            visible_labels = [
                (
                    f"Recently viewed • {entry['label']}"
                    if not query
                    and entry["record_id"] in self.recent_positions
                    else entry["label"]
                )
                for entry in self.visible_entries
            ]
            self.listbox.insert(
                "end",
                *visible_labels,
            )

        visible_recent_count = sum(
            1
            for entry in self.visible_entries
            if entry["record_id"] in self.recent_positions
        )

        if not query and visible_recent_count:
            self.count_value.set(
                f"{visible_recent_count} recently viewed first • "
                f"{len(self.visible_entries)} available books"
            )
        else:
            self.count_value.set(
                f"{len(self.visible_entries)} of "
                f"{len(self.entries)} available books"
            )
        self.update_add_state()

    def flush_scheduled_refresh(self):
        if self.refresh_job is None:
            return

        self.after_cancel(self.refresh_job)
        self.refresh_results()

    def update_add_state(self, event=None):
        self.add_button.set_enabled(bool(self.listbox.curselection()))

    def accept(self, event=None):
        self.flush_scheduled_refresh()
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return "break"

        self.selected_references = [
            {
                "record_id": self.visible_entries[index]["record_id"],
                "name": self.visible_entries[index]["name"],
            }
            for index in selected_indices
        ]
        self.destroy()

        return "break"

    def cancel(self, event=None):
        self.selected_references = []
        self.destroy()

        return "break"
