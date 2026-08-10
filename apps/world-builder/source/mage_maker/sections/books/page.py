import tkinter as tk
from tkinter import messagebox, ttk

from mage_maker.sections.books.dialogs import (
    BookContentPickerDialog,
    BookDialog,
    BookHoldingDialog,
)
from mage_maker.sections.books.models import book_reading_source_text
from mage_maker.ui.theme import (
    ADD_GREEN,
    ADD_GREEN_HOVER,
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


class BooksPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        status_command,
        records_changed_command=None,
        auto_refresh=True,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.records_changed_command = records_changed_command
        self.books = []
        self.selected_book_id = None
        self.search_value = tk.StringVar()
        self.count_value = tk.StringVar(value="0 books")
        self.title_value = tk.StringVar(value="Select a book")
        self.author_value = tk.StringVar(value="")
        self.publication_value = tk.StringVar(value="")
        self.printing_value = tk.StringVar(value="")
        self.location_value = tk.StringVar(value="")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_page()
        self.search_value.trace_add("write", self.refresh_book_tree)

        if auto_refresh:
            self.refresh()

    def build_page(self):
        workspace = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=BORDER,
            borderwidth=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        workspace.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        list_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        list_card.grid_rowconfigure(2, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        list_header = tk.Frame(list_card, bg=PRIMARY_DARK, height=58)
        list_header.grid(row=0, column=0, sticky="ew")
        list_header.grid_propagate(False)
        list_header.grid_columnconfigure(0, weight=1)
        list_title = tk.Label(
            list_header,
            text="Books",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=16,
        )
        list_title.grid(row=0, column=0, sticky="nsew")
        count = tk.Label(
            list_header,
            textvariable=self.count_value,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(9),
            anchor="e",
            padx=14,
        )
        count.grid(row=0, column=1, sticky="nsew")
        search_row = tk.Frame(list_card, bg=SURFACE, padx=12, pady=12)
        search_row.grid(row=1, column=0, sticky="ew")
        search_row.grid_columnconfigure(0, weight=1)
        self.search_entry = RoundedEntry(
            search_row,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
        )
        self.search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        new_button = SoftButton(
            search_row,
            text="New",
            command=self.open_new_book_dialog,
            background=SURFACE,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=74,
            height=38,
        )
        new_button.grid(row=0, column=1)
        tree_frame = tk.Frame(list_card, bg=FIELD_BACKGROUND)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure(
            "BookCatalog.Treeview",
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            rowheight=42,
            borderwidth=0,
            font=app_font(10),
        )
        style.map(
            "BookCatalog.Treeview",
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        self.book_tree = ttk.Treeview(
            tree_frame,
            columns=("author",),
            show="tree headings",
            selectmode="browse",
            style="BookCatalog.Treeview",
        )
        self.book_tree.heading("#0", text="Title")
        self.book_tree.heading("author", text="Author")
        self.book_tree.column("#0", width=190, minwidth=130, stretch=True)
        self.book_tree.column(
            "author",
            width=130,
            minwidth=95,
            stretch=False,
        )
        self.book_tree.tag_configure("alternate", background=LIST_ALTERNATE)
        self.book_tree.grid(row=0, column=0, sticky="nsew")
        self.book_tree.bind("<<TreeviewSelect>>", self.book_selected)
        self.book_tree.bind("<ButtonRelease-1>", self.book_selected)
        scrollbar = ttk.Scrollbar(
            tree_frame,
            orient="vertical",
            command=self.book_tree.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.book_tree.configure(yscrollcommand=scrollbar.set)
        editor_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        editor_card.grid_rowconfigure(2, weight=1)
        editor_card.grid_columnconfigure(0, weight=1)
        self.build_editor_header(editor_card)
        self.build_metadata(editor_card)
        self.build_tabs(editor_card)
        workspace.add(list_card, minsize=310, width=390)
        workspace.add(editor_card, minsize=690)

    def build_editor_header(self, parent):
        header = tk.Frame(parent, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        title = tk.Label(
            header,
            textvariable=self.title_value,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=16,
        )
        title.grid(row=0, column=0, sticky="nsew")
        self.edit_button = SoftButton(
            header,
            text="Edit",
            command=self.open_edit_book_dialog,
            background=PRIMARY_DARK,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=78,
            height=36,
        )
        self.edit_button.grid(row=0, column=1, padx=(0, 6), pady=11)
        self.delete_button = SoftButton(
            header,
            text="Delete",
            command=self.delete_selected_book,
            background=PRIMARY_DARK,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=84,
            height=36,
        )
        self.delete_button.grid(row=0, column=2, padx=(0, 14), pady=11)

    def build_metadata(self, parent):
        metadata = tk.Frame(parent, bg=SURFACE_MUTED, padx=16, pady=12)
        metadata.grid(row=1, column=0, sticky="ew", padx=16, pady=14)
        metadata.grid_columnconfigure(0, weight=1)
        metadata.grid_columnconfigure(1, weight=1)
        author = tk.Label(
            metadata,
            textvariable=self.author_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        author.grid(row=0, column=0, sticky="ew")
        publication = tk.Label(
            metadata,
            textvariable=self.publication_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="e",
        )
        publication.grid(row=0, column=1, sticky="ew")
        printing = tk.Label(
            metadata,
            textvariable=self.printing_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        printing.grid(row=1, column=0, sticky="ew", pady=(5, 0))
        location = tk.Label(
            metadata,
            textvariable=self.location_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        location.grid(row=1, column=1, sticky="ew", pady=(5, 0))

    def build_tabs(self, parent):
        self.notebook = ttk.Notebook(parent)
        self.notebook.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=16,
            pady=(0, 16),
        )
        details_tab = tk.Frame(self.notebook, bg=SURFACE, padx=14, pady=14)
        contents_tab = tk.Frame(self.notebook, bg=SURFACE, padx=14, pady=14)
        holdings_tab = tk.Frame(self.notebook, bg=SURFACE, padx=14, pady=14)
        readings_tab = tk.Frame(self.notebook, bg=SURFACE, padx=14, pady=14)
        self.notebook.add(details_tab, text="Details")
        self.notebook.add(contents_tab, text="Contents")
        self.notebook.add(holdings_tab, text="Possession & availability")
        self.notebook.add(readings_tab, text="Reading history")
        self.build_details_tab(details_tab)
        self.build_contents_tab(contents_tab)
        self.build_holdings_tab(holdings_tab)
        self.build_readings_tab(readings_tab)

    def build_details_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_columnconfigure(1, weight=1)
        description_heading = tk.Label(
            parent,
            text="Description",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        description_heading.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        notes_heading = tk.Label(
            parent,
            text="Notes",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        notes_heading.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.description_text = tk.Text(
            parent,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
            state="disabled",
        )
        self.description_text.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 7),
            pady=(6, 0),
        )
        self.notes_text = tk.Text(
            parent,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            wrap="word",
            relief="flat",
            borderwidth=0,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
            state="disabled",
        )
        self.notes_text.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(7, 0),
            pady=(6, 0),
        )

    def build_contents_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        controls = tk.Frame(parent, bg=SURFACE)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.add_content_button = SoftButton(
            controls,
            text="Add content",
            command=self.open_add_content_dialog,
            background=SURFACE,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=34,
        )
        self.add_content_button.pack(side="left")
        self.remove_content_button = SoftButton(
            controls,
            text="Remove",
            command=self.remove_selected_content,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=34,
        )
        self.remove_content_button.pack(side="left", padx=(7, 0))
        self.content_table = self.build_table(
            parent,
            ("name", "type", "source"),
            ("Name", "Kind", "Definitive source"),
            (360, 130, 170),
        )
        self.content_table.grid(row=1, column=0, sticky="nsew")

    def build_holdings_tab(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        controls = tk.Frame(parent, bg=SURFACE)
        controls.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.add_holding_button = SoftButton(
            controls,
            text="Add holding",
            command=self.open_add_holding_dialog,
            background=SURFACE,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=34,
        )
        self.add_holding_button.pack(side="left")
        self.edit_holding_button = SoftButton(
            controls,
            text="Edit",
            command=self.open_edit_holding_dialog,
            background=SURFACE,
            width=78,
            height=34,
        )
        self.edit_holding_button.pack(side="left", padx=(7, 0))
        self.remove_holding_button = SoftButton(
            controls,
            text="Remove",
            command=self.remove_selected_holding,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=34,
        )
        self.remove_holding_button.pack(side="left", padx=(7, 0))
        self.holding_table = self.build_table(
            parent,
            ("holder", "kind", "dates", "stock"),
            ("Holder / location", "Kind", "Availability", "Stock / price"),
            (260, 125, 200, 150),
        )
        self.holding_table.grid(row=1, column=0, sticky="nsew")
        self.holding_table.bind(
            "<Double-Button-1>",
            self.open_edit_holding_dialog,
        )

    def build_readings_tab(self, parent):
        parent.grid_rowconfigure(0, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        self.reading_table = self.build_table(
            parent,
            ("date", "person", "source"),
            ("Date", "Reader", "How acquired / accessed"),
            (110, 190, 390),
        )
        self.reading_table.grid(row=0, column=0, sticky="nsew")

    def build_table(self, parent, columns, headings, widths):
        table = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode="browse",
        )

        for column, heading, width in zip(columns, headings, widths):
            table.heading(column, text=heading)
            table.column(
                column,
                width=width,
                minwidth=max(70, width // 2),
                stretch=True,
                anchor="w",
            )

        return table

    def refresh(self, selected_book_id=None):
        requested_id = selected_book_id or self.selected_book_id
        self.books = self.controller.list_books()
        available_ids = {book["record_id"] for book in self.books}

        if requested_id not in available_ids:
            requested_id = self.books[0]["record_id"] if self.books else None

        self.selected_book_id = requested_id
        self.refresh_book_tree()
        self.load_selected_book()

    def refresh_book_tree(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().strip().casefold().split()
            if term
        ]
        visible_books = [
            book
            for book in self.books
            if all(
                term
                in " ".join(
                    (
                        book["title"],
                        book["author_name"],
                        book["description"],
                        book["notes"],
                    )
                ).casefold()
                for term in query_terms
            )
        ]

        for item_id in self.book_tree.get_children():
            self.book_tree.delete(item_id)

        for index, book in enumerate(visible_books):
            self.book_tree.insert(
                "",
                "end",
                iid=book["record_id"],
                text=book["title"],
                values=(book["author_name"],),
                tags=("alternate",) if index % 2 else (),
            )

        count = len(visible_books)
        self.count_value.set(
            f"{count} book" if count == 1 else f"{count} books"
        )

        if (
            self.selected_book_id
            and self.book_tree.exists(self.selected_book_id)
        ):
            self.book_tree.selection_set(self.selected_book_id)
            self.book_tree.see(self.selected_book_id)

    def book_selected(self, event=None):
        selection = self.book_tree.selection()

        if not selection:
            return

        selected_id = selection[0]

        if selected_id == self.selected_book_id:
            return

        self.selected_book_id = selected_id
        self.load_selected_book()

    def selected_book(self):
        return next(
            (
                book
                for book in self.books
                if book["record_id"] == self.selected_book_id
            ),
            None,
        )

    def load_selected_book(self):
        book = self.selected_book()
        enabled = book is not None
        self.edit_button.set_enabled(enabled)
        self.delete_button.set_enabled(enabled)
        self.add_content_button.set_enabled(enabled)
        self.remove_content_button.set_enabled(enabled)
        self.add_holding_button.set_enabled(enabled)
        self.edit_holding_button.set_enabled(enabled)
        self.remove_holding_button.set_enabled(enabled)

        if book is None:
            self.title_value.set("Select a book")
            self.author_value.set("")
            self.publication_value.set("")
            self.printing_value.set("")
            self.location_value.set("")
            self.set_read_only_text(self.description_text, "")
            self.set_read_only_text(self.notes_text, "")
            self.clear_table(self.content_table)
            self.clear_table(self.holding_table)
            self.clear_table(self.reading_table)
            return

        self.title_value.set(book["title"])
        self.author_value.set(f"Author: {book['author_name']}")
        self.publication_value.set(
            f"Published: {book['publication_date']}"
        )
        self.printing_value.set(
            "Mass printed"
            if book["mass_printed"]
            else "Tracked edition / possession chain"
        )
        self.location_value.set(
            book["publication_location_name"]
            or "No publication location recorded"
        )
        self.set_read_only_text(self.description_text, book["description"])
        self.set_read_only_text(self.notes_text, book["notes"])
        self.load_contents(book)
        self.load_holdings(book)
        self.load_readings(book)

    def set_read_only_text(self, widget, value):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", str(value or ""))
        widget.configure(state="disabled")

    def clear_table(self, table):
        for item_id in table.get_children():
            table.delete(item_id)

    def load_contents(self, book):
        self.clear_table(self.content_table)

        for entry in book["contents"]:
            self.content_table.insert(
                "",
                "end",
                iid=entry["entry_id"],
                values=(
                    entry["name"],
                    entry["content_type"],
                    entry["collection"].replace("_", " ").title(),
                ),
            )

    def load_holdings(self, book):
        self.clear_table(self.holding_table)

        for holding in book["holdings"]:
            availability = holding["available_from"] or "Beginning unknown"

            if holding["available_until"]:
                availability += f" – {holding['available_until']}"

            if holding["sold_out_date"]:
                availability += f" · sold out {holding['sold_out_date']}"

            stock_parts = []

            if holding["copies"] is not None:
                stock_parts.append(f"{holding['copies']} copies")

            if holding["price_sickles"] is not None:
                stock_parts.append(f"{holding['price_sickles']} sickles")

            self.holding_table.insert(
                "",
                "end",
                iid=holding["entry_id"],
                values=(
                    holding["holder_name"],
                    holding["holder_type"],
                    availability,
                    " · ".join(stock_parts) or "—",
                ),
            )

    def load_readings(self, book):
        self.clear_table(self.reading_table)

        for reading in self.controller.readings_for_book(book["record_id"]):
            self.reading_table.insert(
                "",
                "end",
                iid=reading["record_id"],
                values=(
                    reading["date"],
                    reading["person_name"],
                    book_reading_source_text(reading),
                ),
            )

    def open_new_book_dialog(self):
        BookDialog(self, self.controller, None, self.save_new_book)

    def save_new_book(self, values):
        created = self.controller.create_book(values)
        self.refresh(created["record_id"])
        self.notify_changed()
        self.status_command(f"Created book: {created['title']}")
        return created

    def open_edit_book_dialog(self):
        book = self.selected_book()

        if book is None:
            return

        BookDialog(self, self.controller, book, self.save_edited_book)

    def save_edited_book(self, values):
        updated = self.controller.update_book(
            self.selected_book_id,
            values,
        )
        self.refresh(updated["record_id"])
        self.notify_changed()
        self.status_command(f"Updated book: {updated['title']}")
        return updated

    def delete_selected_book(self):
        book = self.selected_book()

        if book is None:
            return

        if not messagebox.askyesno(
            "Delete book",
            f"Delete {book['title']} from the definitive catalog?",
            parent=self,
        ):
            return

        try:
            self.controller.delete_book(book["record_id"])
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot delete book",
                str(error),
                parent=self,
            )
            return

        self.selected_book_id = None
        self.refresh()
        self.notify_changed()
        self.status_command(f"Deleted book: {book['title']}")

    def open_add_content_dialog(self):
        if self.selected_book() is None:
            return

        BookContentPickerDialog(
            self,
            self.controller,
            self.add_content,
        )

    def add_content(self, values):
        updated = self.controller.add_content(
            self.selected_book_id,
            values,
        )
        self.refresh(updated["record_id"])
        self.notify_changed()
        self.status_command(f"Added {values['name']} to {updated['title']}.")
        return updated

    def remove_selected_content(self):
        selection = self.content_table.selection()

        if not selection:
            return

        try:
            updated = self.controller.remove_content(
                self.selected_book_id,
                selection[0],
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot remove content",
                str(error),
                parent=self,
            )
            return

        self.refresh(updated["record_id"])
        self.notify_changed()

    def open_add_holding_dialog(self):
        if self.selected_book() is None:
            return

        BookHoldingDialog(
            self,
            self.controller,
            None,
            self.add_holding,
        )

    def add_holding(self, values):
        updated = self.controller.add_holding(
            self.selected_book_id,
            values,
        )
        self.refresh(updated["record_id"])
        self.notify_changed()
        self.status_command(f"Added a holding for {updated['title']}.")
        return updated

    def selected_holding(self):
        selection = self.holding_table.selection()
        book = self.selected_book()

        if not selection or book is None:
            return None

        return next(
            (
                holding
                for holding in book["holdings"]
                if holding["entry_id"] == selection[0]
            ),
            None,
        )

    def open_edit_holding_dialog(self, event=None):
        holding = self.selected_holding()

        if holding is None:
            return

        BookHoldingDialog(
            self,
            self.controller,
            holding,
            self.save_edited_holding,
        )

    def save_edited_holding(self, values):
        entry_id = str(values.get("entry_id", "") or "").strip()
        updated = self.controller.update_holding(
            self.selected_book_id,
            entry_id,
            values,
        )
        self.refresh(updated["record_id"])
        self.notify_changed()
        self.status_command(f"Updated a holding for {updated['title']}.")
        return updated

    def remove_selected_holding(self):
        holding = self.selected_holding()

        if holding is None:
            return

        try:
            updated = self.controller.remove_holding(
                self.selected_book_id,
                holding["entry_id"],
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot remove holding",
                str(error),
                parent=self,
            )
            return

        self.refresh(updated["record_id"])
        self.notify_changed()

    def notify_changed(self):
        if callable(self.records_changed_command):
            self.records_changed_command()

    def create_shortcut(self):
        self.open_new_book_dialog()

    def search_shortcut(self):
        self.search_entry.focus_set()
