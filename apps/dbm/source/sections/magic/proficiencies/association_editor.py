import tkinter as tk
from copy import deepcopy
from difflib import SequenceMatcher

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


class AssociationPicker(tk.Toplevel):
    def __init__(self, parent, title_text, available_names, excluded_names):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        excluded_normalized_names = {
            str(name).casefold() for name in excluded_names
        }
        self.available_names = [
            name
            for name in available_names
            if name.casefold() not in excluded_normalized_names
        ]
        self.visible_names = []
        self.selected_name = None
        self.refresh_job = None

        self.title(title_text)
        self.geometry("560x520")
        self.minsize(480, 420)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text=title_text,
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
        self.card.grid_rowconfigure(3, weight=1)
        self.card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.search_label = tk.Label(
            self.card,
            text="Search",
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
            pady=(0, 8),
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
            row=2,
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
            row=3,
            column=0,
            sticky="nsew",
            padx=(18, 0),
            pady=(0, 16),
        )
        self.listbox.bind("<Double-Button-1>", self.accept)

        self.scrollbar = tk.Scrollbar(
            self.card,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(
            row=3,
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
            text="Add",
            command=self.accept,
            background=APP_BACKGROUND,
            width=90,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.add_button.pack(side="left")

        self.bind("<Escape>", self.cancel)
        self.bind("<Return>", self.accept)
        self.refresh_results()
        self.grab_set()
        self.search_entry.focus_set()

    def schedule_refresh(self, *arguments):
        if self.refresh_job is not None:
            self.after_cancel(self.refresh_job)

        self.refresh_job = self.after(80, self.refresh_results)

    def refresh_results(self):
        self.refresh_job = None
        query = " ".join(self.search_value.get().casefold().split())

        if not query:
            self.visible_names = list(self.available_names)
        else:
            ranked_names = []

            for name in self.available_names:
                normalized_name = name.casefold()

                if normalized_name == query:
                    score = 0
                elif normalized_name.startswith(query):
                    score = 1
                elif query in normalized_name:
                    score = 2 + normalized_name.index(query) / 1000
                else:
                    similarity = SequenceMatcher(
                        None,
                        query,
                        normalized_name,
                    ).ratio()

                    if similarity < 0.42:
                        continue

                    score = 4 + (1 - similarity)

                ranked_names.append((score, normalized_name, name))

            ranked_names.sort()
            self.visible_names = [name for _, _, name in ranked_names]

        self.listbox.delete(0, "end")

        if self.visible_names:
            self.listbox.insert("end", *self.visible_names)
            self.listbox.selection_set(0)
            self.listbox.activate(0)

        self.count_value.set(
            f"{len(self.visible_names)} of {len(self.available_names)} available"
        )
        self.add_button.set_enabled(bool(self.visible_names))

    def flush_scheduled_refresh(self):
        if self.refresh_job is None:
            return

        self.after_cancel(self.refresh_job)
        self.refresh_results()

    def accept(self, event=None):
        self.flush_scheduled_refresh()
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return "break"

        self.selected_name = self.visible_names[selected_indices[0]]
        self.destroy()

        return "break"

    def cancel(self, event=None):
        self.selected_name = None
        self.destroy()

        return "break"


class AssociationEditor(tk.Frame):
    def __init__(
        self,
        parent,
        database,
        collection_name,
        title_text,
        picker_title,
        change_command,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.collection_name = collection_name
        self.picker_title = picker_title
        self.change_command = change_command
        self.values = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text=title_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
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
            command=self.add_value,
            width=112,
            height=32,
            font=app_font(9),
        )
        self.add_button.grid(row=0, column=1, padx=(8, 4))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_value,
            width=82,
            height=32,
            font=app_font(9),
        )
        self.remove_button.grid(row=0, column=2)

        self.listbox = StripedListbox(
            self,
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
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(row=1, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.update_remove_state)
        self.remove_button.set_enabled(False)

    def set_values(self, values):
        self.values = deepcopy(values) if isinstance(values, list) else []
        self.refresh_list()

    def get_values(self):
        return list(self.values)

    def get_available_names(self):
        return sorted(
            {
                " ".join(str(record.get("name", "")).split())
                for record in self.database.get_collection(
                    self.collection_name
                )
                if " ".join(str(record.get("name", "")).split())
            },
            key=str.casefold,
        )

    def add_value(self):
        picker = AssociationPicker(
            self,
            self.picker_title,
            self.get_available_names(),
            self.values,
        )
        self.wait_window(picker)

        if picker.selected_name is None:
            return

        self.values.append(picker.selected_name)
        self.values.sort(key=str.casefold)
        self.refresh_list()
        self.change_command()

    def remove_value(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        del self.values[selected_indices[0]]
        self.refresh_list()
        self.change_command()

    def refresh_list(self):
        self.listbox.delete(0, "end")

        if self.values:
            self.listbox.insert(
                "end",
                *(f"• {value}" for value in self.values),
            )

        self.remove_button.set_enabled(False)

    def update_remove_state(self, event=None):
        self.remove_button.set_enabled(bool(self.listbox.curselection()))
