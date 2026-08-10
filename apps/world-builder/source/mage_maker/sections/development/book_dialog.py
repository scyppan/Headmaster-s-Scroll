import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.sections.development.models import (
    SCHOOL_YEAR_BOOK_COUNT,
    normalize_school_year_book,
    normalize_school_year_books,
    school_year_book_identity,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


def book_search_text(book):
    if not isinstance(book, dict):
        return ""

    searchable_values = [
        book.get("name"),
        book.get("author"),
        book.get("description"),
        *(book.get("categories", []) or []),
    ]

    for field_name in ("spells", "proficiencies", "potions"):
        for reference in book.get(field_name, []) or []:
            if isinstance(reference, dict):
                searchable_values.extend(
                    (
                        reference.get("name"),
                        reference.get("record_id"),
                    )
                )
            else:
                searchable_values.append(reference)

    return " ".join(
        str(value or "").strip()
        for value in searchable_values
        if str(value or "").strip()
    ).casefold()


def book_display_text(book):
    normalized_book = normalize_school_year_book(book)
    author = normalized_book["author"]
    return (
        f"{normalized_book['name']} — {author}"
        if author
        else normalized_book["name"]
    )


def book_sort_key(book):
    return (
        str(book.get("name", "") or "").casefold(),
        str(book.get("author", "") or "").casefold(),
    )


def resolve_selected_books(
    books,
    selected_books,
    maximum_count=SCHOOL_YEAR_BOOK_COUNT,
):
    books_by_id = {}
    books_by_identity = {}

    for book in books or []:
        if not isinstance(book, dict):
            continue

        try:
            normalized_book = normalize_school_year_book(book)
        except (TypeError, ValueError):
            continue

        identity = school_year_book_identity(normalized_book)
        books_by_identity[identity] = normalized_book

        if normalized_book["record_id"]:
            books_by_id[normalized_book["record_id"]] = (
                normalized_book
            )

    resolved_books = []

    for selected_book in normalize_school_year_books(
        selected_books,
        maximum_count,
    ):
        resolved_book = (
            books_by_id.get(selected_book["record_id"])
            if selected_book["record_id"]
            else None
        )
        resolved_book = (
            resolved_book
            or books_by_identity.get(
                school_year_book_identity(selected_book)
            )
            or selected_book
        )
        resolved_books.append(deepcopy(resolved_book))

    return resolved_books


class BookSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        books,
        selected_books,
        save_command,
        excluded_book_identities=None,
        required_book_count=SCHOOL_YEAR_BOOK_COUNT,
        heading_text="Books read during this school year",
        explanation_text=None,
    ):
        super().__init__(parent)
        self.required_book_count = max(
            0,
            int(required_book_count),
        )
        self.heading_text = str(heading_text or "").strip()
        self.explanation_text = (
            str(explanation_text).strip()
            if explanation_text not in (None, "")
            else (
                "Search by title, author, category, spell, or "
                "proficiency. Add exactly two different books. "
                "Books assigned in this or an earlier school year "
                "are excluded."
            )
        )
        self.excluded_book_identities = set(
            excluded_book_identities or ()
        )
        self.books = sorted(
            [
                deepcopy(book)
                for book in books or []
                if isinstance(book, dict)
                and str(book.get("name", "") or "").strip()
                and school_year_book_identity(book)
                not in self.excluded_book_identities
            ],
            key=book_sort_key,
        )
        self.selected_books = [
            book
            for book in resolve_selected_books(
                self.books,
                selected_books,
                self.required_book_count,
            )
            if school_year_book_identity(book)
            not in self.excluded_book_identities
        ]
        self.save_command = save_command
        self.visible_books = []
        self.search_value = tk.StringVar()
        self.results_heading_value = tk.StringVar()
        self.selection_heading_value = tk.StringVar()
        self.title("Select Books Read")
        self.geometry("760x650")
        self.minsize(660, 560)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add(
            "write",
            self.refresh_results,
        )
        self.refresh_results()
        self.refresh_selected_books()
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after_idle(self.focus_search)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_rowconfigure(4, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text=self.heading_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=self.explanation_text,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            justify="left",
        )
        explanation.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(4, 10),
        )
        self.search_control = RoundedEntry(
            card,
            textvariable=self.search_value,
            background=SURFACE,
            width=560,
            height=40,
        )
        self.search_control.grid(
            row=2,
            column=0,
            sticky="ew",
        )
        results_heading = tk.Label(
            card,
            textvariable=self.results_heading_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        results_heading.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(12, 6),
        )
        result_frame = tk.Frame(card, bg=SURFACE)
        result_frame.grid(
            row=4,
            column=0,
            sticky="nsew",
        )
        result_frame.grid_rowconfigure(0, weight=1)
        result_frame.grid_columnconfigure(0, weight=1)
        self.result_list = tk.Listbox(
            result_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.result_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.result_list.bind(
            "<Double-Button-1>",
            self.add_selected_book,
        )
        result_scrollbar = tk.Scrollbar(
            result_frame,
            command=self.result_list.yview,
        )
        result_scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        self.result_list.configure(
            yscrollcommand=result_scrollbar.set
        )
        result_actions = tk.Frame(card, bg=SURFACE)
        result_actions.grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(8, 12),
        )
        self.add_button = SoftButton(
            result_actions,
            text="Add selected book",
            command=self.add_selected_book,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=148,
            height=34,
        )
        self.add_button.pack(side="left")
        selection_heading = tk.Label(
            card,
            textvariable=self.selection_heading_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        selection_heading.grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(0, 6),
        )
        selected_frame = tk.Frame(card, bg=SURFACE)
        selected_frame.grid(
            row=7,
            column=0,
            sticky="ew",
        )
        selected_frame.grid_columnconfigure(0, weight=1)
        self.selected_list = tk.Listbox(
            selected_frame,
            height=max(2, self.required_book_count),
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.selected_list.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        self.remove_button = SoftButton(
            selected_frame,
            text="Remove",
            command=self.remove_selected_book,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=86,
            height=34,
        )
        self.remove_button.grid(
            row=0,
            column=1,
            sticky="n",
            padx=(8, 0),
        )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=8,
            column=0,
            sticky="e",
            pady=(14, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=38,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        self.save_button = SoftButton(
            footer,
            text="Use books",
            command=self.save_books,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=38,
        )
        self.save_button.pack(side="left")

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().strip().casefold().split()
            if term
        ]
        self.visible_books = [
            book
            for book in self.books
            if all(
                term in book_search_text(book)
                for term in query_terms
            )
        ]
        self.result_list.delete(0, "end")

        for index, book in enumerate(self.visible_books):
            self.result_list.insert(
                "end",
                book_display_text(book),
            )
            self.result_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.results_heading_value.set(
            f"Books ({len(self.visible_books)})"
        )

        if self.visible_books:
            self.result_list.selection_set(0)

        self.update_action_states()

    def add_selected_book(self, event=None):
        selection = self.result_list.curselection()

        if not selection:
            return

        selected_book = normalize_school_year_book(
            self.visible_books[selection[0]]
        )
        selected_identity = school_year_book_identity(
            selected_book
        )
        existing_identities = {
            school_year_book_identity(book)
            for book in self.selected_books
        }

        if selected_identity in existing_identities:
            messagebox.showinfo(
                "Book already selected",
                "Choose a different book.",
                parent=self,
            )
            return

        if len(self.selected_books) >= self.required_book_count:
            messagebox.showinfo(
                "Book limit reached",
                "Remove one of the selected books before adding another.",
                parent=self,
            )
            return

        self.selected_books.append(selected_book)
        self.refresh_selected_books()

    def remove_selected_book(self):
        selection = self.selected_list.curselection()

        if not selection:
            return

        self.selected_books.pop(selection[0])
        self.refresh_selected_books()

    def refresh_selected_books(self):
        self.selected_list.delete(0, "end")

        for index, book in enumerate(self.selected_books):
            self.selected_list.insert(
                "end",
                f"{index + 1}. {book_display_text(book)}",
            )

        self.selection_heading_value.set(
            f"Selected books ({len(self.selected_books)} of "
            f"{self.required_book_count})"
        )

        if self.selected_books:
            self.selected_list.selection_set(
                len(self.selected_books) - 1
            )

        self.update_action_states()

    def update_action_states(self):
        selection_count = len(self.selected_books)
        self.add_button.set_enabled(
            bool(self.visible_books)
            and selection_count < self.required_book_count
        )
        self.remove_button.set_enabled(selection_count > 0)
        self.save_button.set_enabled(
            selection_count == self.required_book_count
        )

    def save_books(self):
        selected_books = normalize_school_year_books(
            self.selected_books,
            self.required_book_count,
        )

        if len(selected_books) != self.required_book_count:
            return

        self.save_command(selected_books)
        self.destroy()

    def focus_search(self):
        self.search_control.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
