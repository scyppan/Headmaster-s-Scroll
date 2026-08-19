import tkinter as tk
from copy import deepcopy
from functools import partial

from runtime_theme import bind_theme
from sections.books.bookshelves.book_picker import BookPicker
from sections.schools.constants import (
    SCHOOL_COURSE_DISPLAY_NAMES,
    SCHOOL_COURSES,
)
from shared.widgets import SoftButton
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    PRIMARY_DARK,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class SchoolBookPicker(BookPicker):
    def __init__(
        self,
        parent,
        database,
        excluded_record_ids=(),
        recent_record_ids=(),
    ):
        super().__init__(
            parent,
            database=database,
            excluded_record_ids=excluded_record_ids,
            recent_record_ids=recent_record_ids,
        )
        self.title("Choose Course Book")
        self.heading.configure(text="Choose Course Book")
        self.listbox.configure(selectmode="browse")
        self.add_button.set_text("Choose Book")
        self.cancel_button.pack_forget()
        self.add_button.pack_forget()
        self.add_button.pack(side="left", padx=(0, 6))
        self.cancel_button.pack(side="left")


class CourseBooksEditor(tk.Frame):
    def __init__(
        self,
        parent,
        database,
        change_command,
        book_navigation_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
        self.book_navigation_command = book_navigation_command
        self.curriculum = self.empty_curriculum()
        self.course_books = []
        self.active_year = 1
        self.year_buttons = {}
        self.book_values = []

        self.grid_rowconfigure(5, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.title = tk.Label(
            self,
            text="Course Books",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12),
            anchor="w",
        )
        self.title.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        bind_theme(
            self.title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.hint = tk.Label(
            self,
            text=(
                "Every checked curriculum course appears here. "
                "None means that no book is assigned; use + to add another."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.hint.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        bind_theme(
            self.hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.active_year_value = tk.StringVar(value="Viewing Year 1")
        self.active_year_label = tk.Label(
            self,
            textvariable=self.active_year_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="center",
            pady=4,
        )
        self.active_year_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(
            self.active_year_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.year_row = tk.Frame(self, bg=SURFACE)
        self.year_row.grid(row=3, column=0, sticky="ew", pady=(0, 12))
        bind_theme(self.year_row, background="SURFACE")

        for year_number in range(1, 8):
            self.year_row.grid_columnconfigure(
                year_number - 1,
                weight=1,
                uniform="course_book_years",
            )
            year_button = SoftButton(
                self.year_row,
                text=f"Year {year_number}",
                command=partial(self.select_year, year_number),
                width=86,
                height=34,
                font=app_font(9),
            )
            year_button.grid(
                row=0,
                column=year_number - 1,
                sticky="ew",
                padx=(0, 4) if year_number < 7 else 0,
            )
            self.year_buttons[year_number] = year_button

        self.column_headers = tk.Frame(self, bg=SURFACE)
        self.column_headers.grid(row=4, column=0, sticky="ew", pady=(0, 6))
        self.column_headers.grid_columnconfigure(0, weight=2)
        self.column_headers.grid_columnconfigure(1, weight=5)
        bind_theme(self.column_headers, background="SURFACE")

        self.course_header = tk.Label(
            self.column_headers,
            text="Course",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.course_header.grid(row=0, column=0, sticky="ew", padx=(10, 12))
        bind_theme(
            self.course_header,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.book_header = tk.Label(
            self.column_headers,
            text="Book",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.book_header.grid(row=0, column=1, sticky="ew", padx=(0, 12))
        bind_theme(
            self.book_header,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.scroll_area = tk.Canvas(
            self,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
        )
        self.scroll_area.grid(row=5, column=0, sticky="nsew", padx=(0, 14))
        self.scroll_area.bind("<Configure>", self.resize_rows_frame)
        self.scroll_area.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(
            self.scroll_area,
            background="SURFACE",
            highlightbackground="BORDER_SOFT",
            highlightcolor="BORDER_SOFT",
        )

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.scroll_area.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=5, column=0, sticky="nse")
        self.scroll_area.configure(yscrollcommand=self.scrollbar.set)

        self.rows_frame = tk.Frame(self.scroll_area, bg=SURFACE)
        self.rows_frame.grid_columnconfigure(0, weight=2)
        self.rows_frame.grid_columnconfigure(1, weight=5)
        self.rows_frame.bind("<Configure>", self.update_scroll_region)
        self.rows_frame.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(self.rows_frame, background="SURFACE")
        self.rows_window = self.scroll_area.create_window(
            0,
            0,
            window=self.rows_frame,
            anchor="nw",
        )

        self.update_year_buttons()
        self.refresh_rows()

    def set_state(self, curriculum, course_books):
        self.curriculum = (
            deepcopy(curriculum)
            if isinstance(curriculum, list)
            else self.empty_curriculum()
        )
        self.course_books = (
            deepcopy(course_books) if isinstance(course_books, list) else []
        )
        self.prune_unchecked_course_books()
        self.refresh_rows()

    def set_curriculum(self, curriculum):
        self.curriculum = (
            deepcopy(curriculum)
            if isinstance(curriculum, list)
            else self.empty_curriculum()
        )
        self.prune_unchecked_course_books()
        self.refresh_rows()

    def set_course_books(self, course_books):
        self.course_books = (
            deepcopy(course_books) if isinstance(course_books, list) else []
        )
        self.prune_unchecked_course_books()
        self.refresh_rows()

    def get_course_books(self):
        return deepcopy(self.course_books)

    def select_year(self, year_number):
        if year_number == self.active_year:
            return

        self.active_year = year_number
        self.update_year_buttons()
        self.refresh_rows()

    def update_year_buttons(self):
        self.active_year_value.set(f"Viewing Year {self.active_year}")

        for year_number, year_button in self.year_buttons.items():
            if year_number == self.active_year:
                year_button.set_theme_roles(
                    "SIDEBAR_BACKGROUND",
                    "SIDEBAR_TILE_HOVER",
                    "TEXT_LIGHT",
                )
                year_button.set_text(f"● Year {year_number}")
            else:
                year_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )
                year_button.set_text(f"Year {year_number}")

    def get_selected_courses(self, year_number):
        if year_number < 1 or year_number > len(self.curriculum):
            return []

        year_record = self.curriculum[year_number - 1]
        core_courses = set(year_record.get("core", []))
        elective_courses = set(year_record.get("electives", []))

        return [
            course_name
            for course_name in SCHOOL_COURSES
            if course_name in core_courses
        ] + [
            course_name
            for course_name in SCHOOL_COURSES
            if course_name in elective_courses
            and course_name not in core_courses
        ]

    def get_assignments(self, year_number, course_name):
        return [
            (course_book_index, course_book)
            for course_book_index, course_book in enumerate(self.course_books)
            if course_book.get("year") == year_number
            and course_book.get("course") == course_name
        ]

    def get_books_by_id(self):
        return {
            book.get("record_id"): book
            for book in self.database.get_collection("books")
        }

    def choose_book(self, course_name, course_book_index=None, event=None):
        excluded_record_ids = [
            course_book.get("record_id")
            for existing_index, course_book in enumerate(self.course_books)
            if existing_index != course_book_index
            and course_book.get("year") == self.active_year
            and course_book.get("course") == course_name
        ]
        picker = SchoolBookPicker(
            self,
            self.database,
            excluded_record_ids=excluded_record_ids,
            recent_record_ids=getattr(
                self.database,
                "recent_book_record_ids",
                (),
            ),
        )
        self.wait_window(picker)

        if not picker.selected_references:
            return "break"

        selected_reference = picker.selected_references[0]
        assignment = {
            "year": self.active_year,
            "course": course_name,
            "record_id": selected_reference["record_id"],
        }

        if course_book_index is None:
            self.course_books.append(assignment)
        else:
            self.course_books[course_book_index] = assignment

        self.refresh_rows()
        self.change_command()

        return "break"

    def remove_book(self, course_book_index):
        if course_book_index < 0 or course_book_index >= len(self.course_books):
            return

        del self.course_books[course_book_index]
        self.refresh_rows()
        self.change_command()

    def prune_unchecked_course_books(self):
        selected_courses_by_year = {
            year_number: set(self.get_selected_courses(year_number))
            for year_number in range(1, 8)
        }
        self.course_books = [
            course_book
            for course_book in self.course_books
            if course_book.get("year") in selected_courses_by_year
            and course_book.get("course")
            in selected_courses_by_year[course_book.get("year")]
        ]

    def refresh_rows(self):
        for row_widget in self.rows_frame.winfo_children():
            row_widget.destroy()

        self.book_values = []
        selected_courses = self.get_selected_courses(self.active_year)

        if not selected_courses:
            empty_label = tk.Label(
                self.rows_frame,
                text=(
                    f"No courses are checked for Year {self.active_year}. "
                    "Select them on the Curriculum page."
                ),
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(10),
                anchor="center",
                justify="center",
                pady=30,
            )
            empty_label.grid(
                row=0,
                column=0,
                columnspan=3,
                sticky="ew",
                padx=12,
            )
            bind_theme(
                empty_label,
                background="SURFACE",
                foreground="TEXT_MUTED",
            )
            self.bind_scroll(empty_label)
            self.update_scroll_region()
            return

        books_by_id = self.get_books_by_id()
        row_index = 0

        for course_name in selected_courses:
            assignments = self.get_assignments(
                self.active_year,
                course_name,
            )

            if not assignments:
                self.build_assignment_row(
                    row_index,
                    course_name,
                    None,
                    None,
                    "None",
                    None,
                )
                row_index += 1
                continue

            for assignment_index, (
                course_book_index,
                course_book,
            ) in enumerate(assignments):
                linked_book = books_by_id.get(course_book.get("record_id"))
                book_name = (
                    str(linked_book.get("name", "")).strip()
                    if linked_book is not None
                    else f"{course_book.get('name', 'Missing book')} (missing)"
                )
                self.build_assignment_row(
                    row_index,
                    course_name if assignment_index == 0 else "",
                    course_name,
                    course_book_index,
                    book_name,
                    course_book.get("record_id"),
                )
                row_index += 1

        self.update_scroll_region()

    def build_assignment_row(
        self,
        row_index,
        displayed_course_name,
        assignment_course_name,
        course_book_index,
        book_name,
        book_record_id,
    ):
        actual_course_name = assignment_course_name or displayed_course_name
        course_label = tk.Label(
            self.rows_frame,
            text=SCHOOL_COURSE_DISPLAY_NAMES.get(
                displayed_course_name,
                displayed_course_name,
            ),
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
        )
        course_label.grid(
            row=row_index,
            column=0,
            sticky="nsew",
            pady=5,
        )
        bind_theme(
            course_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        book_value = tk.StringVar(value=book_name or "None")
        self.book_values.append(book_value)
        book_title = tk.Label(
            self.rows_frame,
            textvariable=book_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK if book_record_id else PRIMARY_DARK,
            relief="flat",
            borderwidth=0,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            font=app_font(9),
            cursor="hand2" if book_record_id else "arrow",
            anchor="w",
            padx=9,
        )
        book_title.grid(
            row=row_index,
            column=1,
            sticky="ew",
            padx=(0, 8),
            pady=5,
            ipady=8,
        )

        if book_record_id:
            book_title.bind(
                "<Button-1>",
                partial(self.open_book, book_record_id),
            )

        bind_theme(
            book_title,
            background="FIELD_BACKGROUND",
            foreground=(
                "TEXT_DARK" if book_record_id else "PRIMARY_DARK"
            ),
            highlightbackground="BORDER_SOFT",
            highlightcolor="BORDER_SOFT",
        )

        controls = tk.Frame(self.rows_frame, bg=SURFACE)
        controls.grid(row=row_index, column=2, sticky="e", pady=5, padx=(0, 8))
        bind_theme(controls, background="SURFACE")

        choose_button = SoftButton(
            controls,
            text="Assign" if course_book_index is None else "Change",
            command=partial(
                self.choose_book,
                actual_course_name,
                course_book_index,
            ),
            width=68,
            height=32,
            font=app_font(8),
        )
        choose_button.pack(side="left", padx=(0, 4))

        if course_book_index is not None:
            remove_button = SoftButton(
                controls,
                text="−",
                command=partial(self.remove_book, course_book_index),
                width=32,
                height=32,
                font=app_font(11),
            )
            remove_button.pack(side="left", padx=(0, 4))
            self.bind_scroll(remove_button)

        if displayed_course_name:
            add_button = SoftButton(
                controls,
                text="+",
                command=partial(self.choose_book, actual_course_name, None),
                width=32,
                height=32,
                font=app_font(11),
            )
            add_button.pack(side="left")
            self.bind_scroll(add_button)

        self.bind_scroll(course_label)
        self.bind_scroll(book_title)
        self.bind_scroll(controls)
        self.bind_scroll(choose_button)

    def open_book(self, record_id, event=None):
        if self.book_navigation_command is not None:
            self.book_navigation_command(record_id)

        return "break"

    def bind_scroll(self, widget):
        widget.bind("<MouseWheel>", self.scroll_with_mousewheel)

    def update_scroll_region(self, event=None):
        self.scroll_area.configure(scrollregion=self.scroll_area.bbox("all"))

    def resize_rows_frame(self, event):
        self.scroll_area.itemconfigure(self.rows_window, width=event.width)

    def scroll_with_mousewheel(self, event):
        if event.delta > 0:
            self.scroll_area.yview_scroll(-3, "units")
        elif event.delta < 0:
            self.scroll_area.yview_scroll(3, "units")

        return "break"

    @staticmethod
    def empty_curriculum():
        return [
            {
                "year": year_number,
                "core": [],
                "electives": [],
                "elective_limit": 0,
            }
            for year_number in range(1, 8)
        ]
