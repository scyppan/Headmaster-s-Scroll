import tkinter as tk
import weakref
from copy import deepcopy
from functools import partial

from runtime_theme import bind_theme, runtime_theme
from sections.schools.constants import (
    SCHOOL_COURSE_DISPLAY_NAMES,
    SCHOOL_COURSES,
)
from shared.widgets import RoundedEntry, SoftButton
from theme import (
    FIELD_BACKGROUND,
    PRIMARY_LIGHT,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


CHECKED_COURSE_BACKGROUND = "#E2F1DF"


class CourseCheckboxThemeBinding:
    def __init__(self, checkbox, variable):
        self.checkbox_reference = weakref.ref(checkbox)
        self.variable = variable

    def apply_theme(self, theme_values):
        checkbox = self.checkbox_reference()

        if checkbox is None:
            return

        checked = self.variable.get()
        background = (
            CHECKED_COURSE_BACKGROUND
            if checked
            else theme_values["SURFACE"]
        )
        checkbox.configure(
            background=background,
            foreground=theme_values["TEXT_DARK"],
            activebackground=background,
            activeforeground=theme_values["TEXT_DARK"],
            selectcolor=(
                CHECKED_COURSE_BACKGROUND
                if checked
                else theme_values["PRIMARY_LIGHT"]
            ),
        )


class CurriculumEditor(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_curriculum = False
        self.active_year = 1
        self.curriculum = self.empty_curriculum()
        self.year_buttons = {}
        self.core_variables = {}
        self.elective_variables = {}
        self.core_checkbox_bindings = {}
        self.elective_checkbox_bindings = {}

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(4, weight=1)

        self.title = tk.Label(
            self,
            text="Seven-Year Curriculum",
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
                "Choose a year, then check its core and elective courses."
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
                uniform="curriculum_years",
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

        self.course_panels = tk.Frame(self, bg=SURFACE)
        self.course_panels.grid(row=4, column=0, sticky="nsew")
        self.course_panels.grid_columnconfigure(
            0,
            weight=1,
            uniform="course_panels",
        )
        self.course_panels.grid_columnconfigure(
            1,
            weight=1,
            uniform="course_panels",
        )
        bind_theme(self.course_panels, background="SURFACE")

        self.core_panel = tk.LabelFrame(
            self.course_panels,
            text="Core Courses",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=10,
            pady=8,
        )
        self.core_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )
        bind_theme(
            self.core_panel,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.elective_panel = tk.LabelFrame(
            self.course_panels,
            text="Elective Courses",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=10,
            pady=8,
        )
        self.elective_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(8, 0),
        )
        bind_theme(
            self.elective_panel,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.build_course_checkboxes(
            self.core_panel,
            "core",
            self.core_variables,
        )
        self.build_course_checkboxes(
            self.elective_panel,
            "electives",
            self.elective_variables,
        )

        self.limit_row = tk.Frame(self, bg=SURFACE)
        self.limit_row.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        self.limit_row.grid_columnconfigure(1, weight=1)
        bind_theme(self.limit_row, background="SURFACE")

        self.limit_label = tk.Label(
            self.limit_row,
            text="Elective Course Limit",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.limit_label.grid(row=0, column=0, padx=(0, 10))
        bind_theme(
            self.limit_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.limit_value = tk.StringVar(value="0")
        self.limit_value.trace_add("write", self.handle_limit_change)
        self.limit_entry = RoundedEntry(
            self.limit_row,
            textvariable=self.limit_value,
            background=SURFACE,
            width=88,
            height=36,
            font=app_font(9),
            justify="center",
        )
        self.limit_entry.grid(row=0, column=1, sticky="w")
        self.limit_entry.entry.configure(
            validate="key",
            validatecommand=(self.register(self.validate_limit_value), "%P"),
        )

        self.update_year_display()

    def build_course_checkboxes(self, parent, course_type, variables):
        checkbox_bindings = (
            self.core_checkbox_bindings
            if course_type == "core"
            else self.elective_checkbox_bindings
        )

        for column_index in range(3):
            parent.grid_columnconfigure(
                column_index,
                weight=1,
                uniform=f"{course_type}_course_columns",
            )

        for course_index, course_name in enumerate(SCHOOL_COURSES):
            course_variable = tk.BooleanVar(value=False)
            variables[course_name] = course_variable
            course_checkbox = tk.Checkbutton(
                parent,
                text=SCHOOL_COURSE_DISPLAY_NAMES.get(
                    course_name,
                    course_name,
                ),
                variable=course_variable,
                command=partial(
                    self.handle_course_toggle,
                    course_type,
                    course_name,
                ),
                bg=SURFACE,
                fg=TEXT_DARK,
                activebackground=SURFACE,
                activeforeground=TEXT_DARK,
                selectcolor=PRIMARY_LIGHT,
                font=app_font(9),
                anchor="w",
                justify="left",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=3,
                pady=4,
            )
            checkbox_binding = CourseCheckboxThemeBinding(
                course_checkbox,
                course_variable,
            )
            course_checkbox.course_theme_binding = checkbox_binding
            checkbox_bindings[course_name] = checkbox_binding
            runtime_theme.register(checkbox_binding)
            course_checkbox.grid(
                row=course_index // 3,
                column=course_index % 3,
                sticky="ew",
                padx=(0, 4),
            )

    def select_year(self, year_number):
        if year_number == self.active_year:
            return

        self.active_year = year_number
        self.update_year_display()

    def update_year_display(self):
        self.loading_curriculum = True
        year_record = self.curriculum[self.active_year - 1]
        core_courses = set(year_record.get("core", []))
        elective_courses = set(year_record.get("electives", []))

        for course_name in SCHOOL_COURSES:
            self.core_variables[course_name].set(course_name in core_courses)
            self.elective_variables[course_name].set(
                course_name in elective_courses
            )
            self.core_checkbox_bindings[course_name].apply_theme(
                runtime_theme.get_values()
            )
            self.elective_checkbox_bindings[course_name].apply_theme(
                runtime_theme.get_values()
            )

        self.limit_value.set(
            str(year_record.get("elective_limit", 0) or 0)
        )
        self.loading_curriculum = False
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

    def handle_course_toggle(self, course_type, course_name):
        if self.loading_curriculum:
            return

        year_record = self.curriculum[self.active_year - 1]
        target_courses = year_record[course_type]
        target_variables = (
            self.core_variables
            if course_type == "core"
            else self.elective_variables
        )

        if target_variables[course_name].get():
            if course_name not in target_courses:
                target_courses.append(course_name)
                target_courses.sort(key=SCHOOL_COURSES.index)
        elif course_name in target_courses:
            target_courses.remove(course_name)

        checkbox_bindings = (
            self.core_checkbox_bindings
            if course_type == "core"
            else self.elective_checkbox_bindings
        )
        checkbox_bindings[course_name].apply_theme(
            runtime_theme.get_values()
        )

        elective_count = len(year_record["electives"])

        if year_record["elective_limit"] > elective_count:
            year_record["elective_limit"] = elective_count
            self.loading_curriculum = True
            self.limit_value.set(str(elective_count))
            self.loading_curriculum = False

        self.change_command()

    def handle_limit_change(self, *arguments):
        if self.loading_curriculum:
            return

        limit_text = self.limit_value.get().strip()
        limit_value = int(limit_text) if limit_text else 0
        elective_count = len(
            self.curriculum[self.active_year - 1]["electives"]
        )

        if limit_value > elective_count:
            limit_value = elective_count
            self.loading_curriculum = True
            self.limit_value.set(str(limit_value))
            self.loading_curriculum = False

        self.curriculum[self.active_year - 1][
            "elective_limit"
        ] = limit_value
        self.change_command()

    def set_curriculum(self, curriculum):
        source_curriculum = (
            deepcopy(curriculum) if isinstance(curriculum, list) else []
        )
        normalized_curriculum = self.empty_curriculum()

        for year_index in range(7):
            if year_index >= len(source_curriculum):
                continue

            source_year = source_curriculum[year_index]

            if not isinstance(source_year, dict):
                continue

            normalized_curriculum[year_index] = {
                "year": year_index + 1,
                "core": list(source_year.get("core", [])),
                "electives": list(source_year.get("electives", [])),
                "elective_limit": int(
                    source_year.get("elective_limit", 0) or 0
                ),
            }

        self.curriculum = normalized_curriculum
        self.update_year_display()

    def get_curriculum(self):
        return deepcopy(self.curriculum)

    @staticmethod
    def validate_limit_value(proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

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
