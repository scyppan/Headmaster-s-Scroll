import tkinter as tk

from runtime_theme import bind_theme
from sections.books.bookshelves.books_editor import BookshelfBooksEditor
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import MultilineField, SoftButton
from theme import SURFACE, TEXT_MUTED, app_font


class BookshelfForm(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.change_command = change_command
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
            width=92,
            height=36,
        )
        self.overview_button.pack(side="left", padx=(0, 3))
        self.navigation_buttons["overview"] = self.overview_button

        self.books_button = SoftButton(
            self.navigation,
            text="Books",
            command=self.show_books,
            width=82,
            height=36,
        )
        self.books_button.pack(side="left", padx=3)
        self.navigation_buttons["books"] = self.books_button

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
        self.build_books_view()
        self.activate_view("overview")

    def build_overview_view(self):
        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")
        self.overview_view.grid_columnconfigure(0, weight=1)
        self.overview_view.grid_columnconfigure(1, weight=1)
        self.overview_view.grid_rowconfigure(1, weight=1, minsize=330)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Bookshelf Name",
            self.handle_field_change,
            font_size=12,
        )
        self.name_field.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Description",
            self.handle_text_change,
            height=15,
        )
        self.description_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 8),
        )

        self.tags_editor = TagEditor(
            self.overview_view,
            self.handle_field_change,
        )
        self.tags_editor.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(8, 0),
        )

    def build_books_view(self):
        self.books_view = tk.Frame(self.view_container, bg=SURFACE)
        self.books_view.grid(row=0, column=0, sticky="nsew")
        self.books_view.grid_rowconfigure(0, weight=1)
        self.books_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.books_view, background="SURFACE")
        self.views["books"] = self.books_view

        self.books_editor = BookshelfBooksEditor(
            self.books_view,
            database=self.database,
            change_command=self.handle_field_change,
        )
        self.books_editor.grid(row=0, column=0, sticky="nsew")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name", ""))
        self.description_field.set_value(record.get("description", ""))
        self.tags_editor.set_tags(record.get("tags", []))
        self.books_editor.set_references(record.get("books", []))

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
            "description": self.description_field.get_value(),
            "tags": self.tags_editor.get_tags(),
            "books": self.books_editor.get_references(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_books(self):
        self.activate_view("books")

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

    def handle_text_change(self):
        self.handle_field_change()
