import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, ttk

from mage_maker.sections.development.models import (
    adult_year_calendar_year_range,
    development_year_page_title,
    normalize_adult_year_records,
    normalize_school_year_records,
    school_year_calendar_year_range,
)
from mage_maker.ui.theme import (
    ADD_GREEN,
    ADD_GREEN_HOVER,
    BORDER_SOFT,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SectionPanel, SoftButton


def school_year_reading_entries(
    school_year_records,
    academic_start_year=None,
):
    entries = []

    for record in normalize_school_year_records(
        school_year_records
    ):
        year_number = record["year"]
        calendar_range = school_year_calendar_year_range(
            academic_start_year,
            year_number,
        )
        calendar_text = (
            f"{calendar_range[0]} – {calendar_range[1]}"
            if calendar_range is not None
            else f"School Year {year_number}"
        )

        for book in record.get("assigned_books", []):
            entries.append(
                {
                    "year": year_number,
                    "date": calendar_text,
                    "name": book["name"],
                    "author": book["author"],
                    "source": f"Assigned in Year {year_number}",
                    "source_kind": "assigned",
                    "page_type": "school",
                    "page_number": year_number,
                }
            )

        for book in record.get("books", []):
            entries.append(
                {
                    "year": year_number,
                    "date": calendar_text,
                    "name": book["name"],
                    "author": book["author"],
                    "source": (
                        f"Intentional study in Year {year_number}"
                    ),
                    "source_kind": "intentional",
                    "page_type": "school",
                    "page_number": year_number,
                }
            )

    return entries


def adult_year_reading_entries(
    adult_year_records,
    academic_start_year=None,
    school_attended=True,
):
    entries = []

    for record in normalize_adult_year_records(
        adult_year_records
    ):
        adult_year = record["adult_year"]
        calendar_range = adult_year_calendar_year_range(
            academic_start_year,
            adult_year,
        )
        calendar_year = (
            calendar_range[0]
            if calendar_range is not None
            else None
        )
        calendar_end_year = (
            calendar_range[1]
            if calendar_range is not None
            else None
        )
        source_year = (
            development_year_page_title(
                {
                    "page_type": "adult",
                    "adult_year": adult_year,
                    "calendar_year": calendar_year,
                    "calendar_end_year": calendar_end_year,
                    "school_attended": bool(school_attended),
                }
            )
            if calendar_year is not None
            else f"Adult Year {adult_year}"
        )

        for book in record.get("books", []):
            entries.append(
                {
                    "year": calendar_year,
                    "date": (
                        str(calendar_year)
                        if calendar_end_year in (None, calendar_year)
                        else f"{calendar_year} – {calendar_end_year}"
                    ),
                    "name": book["name"],
                    "author": book["author"],
                    "source": (
                        f"Intentional study in {source_year}"
                    ),
                    "source_kind": "intentional",
                    "page_type": "adult",
                    "page_number": adult_year,
                }
            )

    return entries


class BooksView(tk.Frame):
    def __init__(
        self,
        parent,
        book_controller=None,
        status_command=None,
        records_changed_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.book_controller = book_controller
        self.status_command = status_command
        self.records_changed_command = records_changed_command
        self.person_id = None
        self.legacy_entries = []
        self.catalog_entries = []
        self.entries = []
        self.entries_by_item_id = {}
        self.count_value = tk.StringVar(value="0 books")
        self.empty_value = tk.StringVar(
            value="No reading has been recorded."
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.build_list()
        self.refresh_entries()

    def build_header(self):
        header = tk.Frame(self, bg=SURFACE)
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            text="Books",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(16, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        count_label = tk.Label(
            header,
            textvariable=self.count_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        count_label.grid(row=0, column=1, sticky="e")
        self.record_button = SoftButton(
            header,
            text="Record reading",
            command=self.open_reading_dialog,
            background=SURFACE,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=34,
        )
        self.record_button.grid(row=0, column=2, sticky="e", padx=(12, 0))
        self.remove_button = SoftButton(
            header,
            text="Remove",
            command=self.remove_selected_reading,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=84,
            height=34,
        )
        self.remove_button.grid(row=0, column=3, sticky="e", padx=(7, 0))

    def build_list(self):
        panel = SectionPanel(
            self,
            "Reading history",
            (
                "All assigned and independently read books appear here."
            ),
        )
        panel.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        panel.content.grid_rowconfigure(0, weight=1)
        panel.content.grid_columnconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure(
            "Books.Treeview",
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            rowheight=32,
            borderwidth=0,
            font=app_font(10),
        )
        style.configure(
            "Books.Treeview.Heading",
            background=SURFACE_MUTED,
            foreground=TEXT_DARK,
            relief="flat",
            font=app_font(10, "bold"),
        )
        style.map(
            "Books.Treeview",
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        list_frame = tk.Frame(
            panel.content,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.table = ttk.Treeview(
            list_frame,
            columns=("date", "book", "author", "source"),
            show="headings",
            selectmode="browse",
            style="Books.Treeview",
        )
        self.table.heading("date", text="Date")
        self.table.heading("book", text="Book")
        self.table.heading("author", text="Author")
        self.table.heading("source", text="Source")
        self.table.column(
            "date",
            width=120,
            minwidth=90,
            stretch=False,
            anchor="w",
        )
        self.table.column(
            "book",
            width=390,
            minwidth=220,
            stretch=True,
            anchor="w",
        )
        self.table.column(
            "author",
            width=230,
            minwidth=140,
            stretch=True,
            anchor="w",
        )
        self.table.column(
            "source",
            width=230,
            minwidth=190,
            stretch=False,
            anchor="w",
        )
        self.table.tag_configure(
            "alternate",
            background=LIST_ALTERNATE,
        )
        self.table.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        scrollbar = ttk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.table.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.empty_label = tk.Label(
            panel.content,
            textvariable=self.empty_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            padx=14,
            pady=14,
        )
        self.empty_label.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

    def set_school_year_records(self, school_year_records):
        self.set_development_records(
            school_year_records,
            [],
            None,
        )

    def set_development_records(
        self,
        school_year_records,
        adult_year_records,
        academic_start_year,
        school_attended=True,
    ):
        self.legacy_entries = [
            *school_year_reading_entries(
                deepcopy(school_year_records),
                academic_start_year,
            ),
            *adult_year_reading_entries(
                deepcopy(adult_year_records),
                academic_start_year,
                school_attended=school_attended,
            ),
        ]
        self.combine_entries()
        self.refresh_entries()

    def set_person(self, person_id):
        self.person_id = str(person_id or "").strip()
        self.refresh_catalog_entries()

    def refresh_catalog_entries(self):
        if self.book_controller is None or not self.person_id:
            self.catalog_entries = []
        else:
            self.catalog_entries = (
                self.book_controller.reading_history_entries_for_person(
                    self.person_id
                )
            )

        self.combine_entries()
        self.refresh_entries()

    def combine_entries(self):
        self.entries = [
            *deepcopy(self.legacy_entries),
            *deepcopy(self.catalog_entries),
        ]
        self.entries.sort(key=self.entry_sort_key)

    def entry_sort_key(self, entry):
        date_text = str(entry.get("date", "") or entry.get("year", ""))
        first_year_text = date_text.split("–", 1)[0].strip()

        try:
            first_year = int(first_year_text)
        except (TypeError, ValueError):
            first_year = 100000

        return (
            first_year,
            str(entry.get("name", "") or "").casefold(),
            str(entry.get("record_id", "") or ""),
        )

    def refresh_entries(self):
        for item_id in self.table.get_children():
            self.table.delete(item_id)

        self.entries_by_item_id = {}
        can_record = self.book_controller is not None and bool(self.person_id)
        self.record_button.set_enabled(can_record)
        self.remove_button.set_enabled(can_record)

        entry_count = len(self.entries)
        self.count_value.set(
            f"{entry_count} book"
            if entry_count == 1
            else f"{entry_count} books"
        )

        if not self.entries:
            self.table.grid_remove()
            self.empty_label.grid()
            return

        self.empty_label.grid_remove()
        self.table.grid()

        for index, entry in enumerate(self.entries):
            item_id = (
                f"catalog:{entry['record_id']}"
                if entry.get("record_id")
                else f"legacy:{index}"
            )
            self.entries_by_item_id[item_id] = entry
            self.table.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    entry.get("date") or entry.get("year") or "Unknown",
                    entry["name"],
                    entry["author"] or "Unknown",
                    entry["source"],
                ),
                tags=("alternate",) if index % 2 else (),
            )

    def open_reading_dialog(self):
        if self.book_controller is None or not self.person_id:
            return

        from mage_maker.sections.books.dialogs import BookReadingDialog

        BookReadingDialog(
            self,
            self.book_controller,
            self.person_id,
            self.reading_recorded,
        )

    def reading_recorded(self, reading):
        self.refresh_catalog_entries()

        if callable(self.records_changed_command):
            self.records_changed_command()

        if callable(self.status_command):
            self.status_command(
                f"Recorded reading: {reading['book_title']}"
            )

    def remove_selected_reading(self):
        selection = self.table.selection()

        if not selection:
            return

        entry = self.entries_by_item_id.get(selection[0])

        if entry is None or not entry.get("record_id"):
            messagebox.showinfo(
                "Legacy reading",
                "This reading belongs to the legacy Development plan and "
                "must be changed on its Development year page.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Remove reading",
            f"Remove the reading of {entry['name']} from this history?",
            parent=self,
        ):
            return

        try:
            self.book_controller.delete_reading(
                entry["record_id"],
                self.person_id,
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot remove reading",
                str(error),
                parent=self,
            )
            return

        self.refresh_catalog_entries()

        if callable(self.records_changed_command):
            self.records_changed_command()
