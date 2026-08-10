import tkinter as tk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import (
    LabeledEntry,
    LabeledSelect,
)
from sections.schools.constants import SCHOOL_BOOLEAN_OPTIONS
from sections.schools.course_books_editor import CourseBooksEditor
from sections.schools.curriculum_editor import CurriculumEditor
from shared.widgets import MultilineField, SoftButton
from theme import SURFACE, TEXT_MUTED, app_font


class SchoolForm(tk.Frame):
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
        self.loading_record = False
        self.active_view_name = None
        self.views = {}
        self.navigation_buttons = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.navigation = tk.Frame(self, bg=SURFACE)
        self.navigation.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        bind_theme(self.navigation, background="SURFACE")

        self.overview_button = SoftButton(
            self.navigation,
            text="Overview",
            command=self.show_overview,
            width=86,
            height=36,
        )
        self.overview_button.pack(side="left", padx=(0, 3))
        self.navigation_buttons["overview"] = self.overview_button

        self.philosophy_button = SoftButton(
            self.navigation,
            text="Philosophy, Practice & Architecture",
            command=self.show_philosophy_and_practice,
            width=232,
            height=36,
        )
        self.philosophy_button.pack(side="left", padx=3)
        self.navigation_buttons[
            "philosophy_and_practice"
        ] = self.philosophy_button

        self.curriculum_button = SoftButton(
            self.navigation,
            text="Curriculum",
            command=self.show_curriculum,
            width=98,
            height=36,
        )
        self.curriculum_button.pack(side="left", padx=3)
        self.navigation_buttons["curriculum"] = self.curriculum_button

        self.course_books_button = SoftButton(
            self.navigation,
            text="Course Books",
            command=self.show_course_books,
            width=112,
            height=36,
        )
        self.course_books_button.pack(side="left", padx=3)
        self.navigation_buttons["course_books"] = self.course_books_button

        self.last_updated_value = tk.StringVar(
            value="Last updated: Not yet saved"
        )
        self.last_updated_label = tk.Label(
            self.navigation,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        self.last_updated_label.pack(side="right", fill="x", expand=True)
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.view_container = tk.Frame(self, bg=SURFACE)
        self.view_container.grid(row=1, column=0, sticky="nsew")
        self.view_container.grid_rowconfigure(0, weight=1)
        self.view_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.view_container, background="SURFACE")

        self.build_overview_view()
        self.build_philosophy_and_practice_view()
        self.build_curriculum_view()
        self.build_course_books_view()
        self.activate_view("overview")

    def build_overview_view(self):
        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")
        self.overview_view.grid_columnconfigure(0, weight=1)
        self.overview_view.grid_columnconfigure(1, weight=1)
        self.overview_view.grid_rowconfigure(2, weight=3, minsize=260)
        self.overview_view.grid_rowconfigure(3, weight=2, minsize=150)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "School Name",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 10),
            pady=(0, 12),
        )

        self.location_field = LabeledEntry(
            self.overview_view,
            "Location",
            self.handle_field_change,
            font_size=12,
        )
        self.location_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 12),
        )

        self.canon_field = LabeledSelect(
            self.overview_view,
            "Canon",
            SCHOOL_BOOLEAN_OPTIONS,
            self.handle_field_change,
            placeholder="No",
        )
        self.canon_field.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 10),
            pady=(0, 12),
        )

        self.wandless_field = LabeledSelect(
            self.overview_view,
            "Wandless",
            SCHOOL_BOOLEAN_OPTIONS,
            self.handle_field_change,
            placeholder="No",
        )
        self.wandless_field.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "School Description",
            self.handle_text_change,
            height=12,
        )
        self.description_field.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 10),
            pady=(0, 8),
        )

        self.areas_served_field = MultilineField(
            self.overview_view,
            "Areas Served",
            self.handle_text_change,
            height=12,
        )
        self.areas_served_field.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(0, 8),
        )

        self.dbnotes_field = MultilineField(
            self.overview_view,
            "DB Notes",
            self.handle_text_change,
            height=7,
        )
        self.dbnotes_field.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(8, 0),
        )

    def build_philosophy_and_practice_view(self):
        self.philosophy_and_practice_view = tk.Frame(
            self.view_container,
            bg=SURFACE,
        )
        self.philosophy_and_practice_view.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.philosophy_and_practice_view.grid_rowconfigure(0, weight=1)
        self.philosophy_and_practice_view.grid_columnconfigure(0, weight=1)
        self.philosophy_and_practice_view.grid_columnconfigure(1, weight=1)
        bind_theme(
            self.philosophy_and_practice_view,
            background="SURFACE",
        )
        self.views[
            "philosophy_and_practice"
        ] = self.philosophy_and_practice_view

        self.philosophy_and_practice_field = MultilineField(
            self.philosophy_and_practice_view,
            "Philosophy & Practice",
            self.handle_text_change,
            height=24,
        )
        self.philosophy_and_practice_field.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 10),
        )

        self.architecture_field = MultilineField(
            self.philosophy_and_practice_view,
            "Architecture",
            self.handle_text_change,
            height=24,
        )
        self.architecture_field.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(10, 0),
        )

    def build_curriculum_view(self):
        self.curriculum_view = tk.Frame(self.view_container, bg=SURFACE)
        self.curriculum_view.grid(row=0, column=0, sticky="nsew")
        self.curriculum_view.grid_rowconfigure(0, weight=1)
        self.curriculum_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.curriculum_view, background="SURFACE")
        self.views["curriculum"] = self.curriculum_view

        self.curriculum_editor = CurriculumEditor(
            self.curriculum_view,
            self.handle_curriculum_change,
        )
        self.curriculum_editor.grid(row=0, column=0, sticky="nsew")

    def build_course_books_view(self):
        self.course_books_view = tk.Frame(self.view_container, bg=SURFACE)
        self.course_books_view.grid(row=0, column=0, sticky="nsew")
        self.course_books_view.grid_rowconfigure(0, weight=1)
        self.course_books_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.course_books_view, background="SURFACE")
        self.views["course_books"] = self.course_books_view

        self.course_books_editor = CourseBooksEditor(
            self.course_books_view,
            database=self.database,
            change_command=self.handle_field_change,
            book_navigation_command=self.book_navigation_command,
        )
        self.course_books_editor.grid(row=0, column=0, sticky="nsew")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name", ""))
        self.location_field.set_value(record.get("location", ""))
        self.canon_field.set_value("Yes" if record.get("canon") else "No")
        self.wandless_field.set_value(
            "Yes" if record.get("wandless") else "No"
        )
        self.description_field.set_value(record.get("description", ""))
        self.areas_served_field.set_value(record.get("areas_served", ""))
        self.philosophy_and_practice_field.set_value(
            record.get("philosophy_and_practice", "")
        )
        self.architecture_field.set_value(record.get("architecture", ""))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))
        self.curriculum_editor.set_curriculum(record.get("curriculum", []))
        self.course_books_editor.set_state(
            self.curriculum_editor.get_curriculum(),
            record.get("course_books", []),
        )

        last_updated = record.get("last_updated", "")
        display_date = last_updated.replace("T", " ") if last_updated else "Unknown"
        self.last_updated_value.set(f"Last updated: {display_date}")
        self.activate_view(retained_view_name)
        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")

        if self.active_view_name == "overview":
            self.name_field.focus_set()

    def get_values(self):
        return {
            "name": self.name_field.get_value(),
            "location": self.location_field.get_value(),
            "canon": self.canon_field.get_value(),
            "wandless": self.wandless_field.get_value(),
            "description": self.description_field.get_value(),
            "areas_served": self.areas_served_field.get_value(),
            "philosophy_and_practice": (
                self.philosophy_and_practice_field.get_value()
            ),
            "architecture": self.architecture_field.get_value(),
            "curriculum": self.curriculum_editor.get_curriculum(),
            "course_books": self.course_books_editor.get_course_books(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_philosophy_and_practice(self):
        self.activate_view("philosophy_and_practice")

    def show_curriculum(self):
        self.activate_view("curriculum")

    def show_course_books(self):
        self.course_books_editor.set_curriculum(
            self.curriculum_editor.get_curriculum()
        )
        self.course_books_editor.select_year(
            self.curriculum_editor.active_year
        )
        self.activate_view("course_books")

    def activate_view(self, view_name):
        self.active_view_name = view_name
        self.views[view_name].tkraise()

        for navigation_name, navigation_button in self.navigation_buttons.items():
            if navigation_name == view_name:
                navigation_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                navigation_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def handle_field_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_curriculum_change(self):
        self.course_books_editor.set_curriculum(
            self.curriculum_editor.get_curriculum()
        )
        self.handle_field_change()

    def handle_text_change(self):
        self.handle_field_change()
