import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.books.bookshelves.book_picker import BookPicker
from shared.widgets import SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)


class BookshelfBooksEditor(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
        self.references = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text="Books on This Shelf",
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
            text="Search & Add Books",
            command=self.add_books,
            width=154,
            height=34,
            font=app_font(9),
        )
        self.add_button.grid(row=0, column=1, padx=(8, 3))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_book,
            width=82,
            height=34,
            font=app_font(9),
        )
        self.remove_button.grid(row=0, column=2, padx=3)

        self.up_button = SoftButton(
            self.header,
            text="Move Up",
            command=self.move_book_up,
            width=92,
            height=34,
            font=app_font(9),
        )
        self.up_button.grid(row=0, column=3, padx=3)

        self.down_button = SoftButton(
            self.header,
            text="Move Down",
            command=self.move_book_down,
            width=104,
            height=34,
            font=app_font(9),
        )
        self.down_button.grid(row=0, column=4, padx=(3, 0))

        self.list_frame = tk.Frame(self, bg=SURFACE)
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        bind_theme(self.list_frame, background="SURFACE")

        self.listbox = StripedListbox(
            self.list_frame,
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
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.update_button_states)

        self.scrollbar = tk.Scrollbar(
            self.list_frame,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.listbox.configure(yscrollcommand=self.scrollbar.set)
        self.update_button_states()

    def set_references(self, references):
        self.references = (
            deepcopy(references) if isinstance(references, list) else []
        )
        self.refresh_list()

    def get_references(self):
        return deepcopy(self.references)

    def get_books_by_id(self):
        return {
            book.get("record_id"): book
            for book in self.database.get_collection("books")
        }

    @staticmethod
    def build_book_label(book):
        name = str(book.get("name", "")).strip() or "Unnamed book"
        author = str(book.get("author", "")).strip()
        categories = [
            str(category).strip()
            for category in book.get("categories", [])
            if str(category).strip()
        ]
        details = []

        if author:
            details.append(author)

        if categories:
            details.append(", ".join(categories))

        if not details:
            return name

        return f"{name} — {' • '.join(details)}"

    def add_books(self):
        excluded_record_ids = {
            reference.get("record_id") for reference in self.references
        }
        picker = BookPicker(
            self,
            database=self.database,
            excluded_record_ids=excluded_record_ids,
        )
        self.wait_window(picker)

        if not picker.selected_references:
            return

        first_new_index = len(self.references)
        self.references.extend(picker.selected_references)
        self.refresh_list(first_new_index)
        self.change_command()

    def remove_book(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]
        del self.references[selected_index]
        next_index = (
            min(selected_index, len(self.references) - 1)
            if self.references
            else None
        )
        self.refresh_list(next_index)
        self.change_command()

    def move_book_up(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices or selected_indices[0] == 0:
            return

        selected_index = selected_indices[0]
        target_index = selected_index - 1
        self.references[target_index], self.references[selected_index] = (
            self.references[selected_index],
            self.references[target_index],
        )
        self.refresh_list(target_index)
        self.change_command()

    def move_book_down(self):
        selected_indices = self.listbox.curselection()

        if (
            not selected_indices
            or selected_indices[0] >= len(self.references) - 1
        ):
            return

        selected_index = selected_indices[0]
        target_index = selected_index + 1
        self.references[target_index], self.references[selected_index] = (
            self.references[selected_index],
            self.references[target_index],
        )
        self.refresh_list(target_index)
        self.change_command()

    def refresh_list(self, selected_index=None):
        books_by_id = self.get_books_by_id()
        self.listbox.delete(0, "end")
        labels = []

        for reference in self.references:
            book = books_by_id.get(reference.get("record_id"))
            label = (
                self.build_book_label(book)
                if book is not None
                else f"{reference.get('name', 'Missing book')} (missing)"
            )
            labels.append(f"• {label}")

        if labels:
            self.listbox.insert("end", *labels)

        if selected_index is not None and self.references:
            self.listbox.selection_set(selected_index)
            self.listbox.activate(selected_index)
            self.listbox.see(selected_index)

        self.update_button_states()

    def update_button_states(self, event=None):
        selected_indices = self.listbox.curselection()
        has_selection = bool(selected_indices)
        selected_index = selected_indices[0] if has_selection else None
        self.remove_button.set_enabled(has_selection)
        self.up_button.set_enabled(
            has_selection and selected_index > 0
        )
        self.down_button.set_enabled(
            has_selection and selected_index < len(self.references) - 1
        )
