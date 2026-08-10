import tkinter as tk

from runtime_theme import bind_theme
from sections.books.books.link_editor import BookLinkEditor
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import MultilineField, SoftButton
from theme import SURFACE, TEXT_MUTED, app_font


class BookForm(tk.Frame):
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

        self.spells_button = SoftButton(
            self.navigation,
            text="Spells",
            command=self.show_spells,
            width=82,
            height=36,
        )
        self.spells_button.pack(side="left", padx=3)
        self.navigation_buttons["spells"] = self.spells_button

        self.proficiencies_button = SoftButton(
            self.navigation,
            text="Proficiencies",
            command=self.show_proficiencies,
            width=122,
            height=36,
        )
        self.proficiencies_button.pack(side="left", padx=3)
        self.navigation_buttons["proficiencies"] = self.proficiencies_button

        self.potions_button = SoftButton(
            self.navigation,
            text="Potions",
            command=self.show_potions,
            width=84,
            height=36,
        )
        self.potions_button.pack(side="left", padx=3)
        self.navigation_buttons["potions"] = self.potions_button

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
        self.build_link_views()
        self.activate_view("overview")

    def build_overview_view(self):
        self.overview_view = tk.Frame(self.view_container, bg=SURFACE)
        self.overview_view.grid(row=0, column=0, sticky="nsew")
        self.overview_view.grid_columnconfigure(0, weight=1)
        self.overview_view.grid_columnconfigure(1, weight=1)
        self.overview_view.grid_rowconfigure(1, weight=3, minsize=260)
        self.overview_view.grid_rowconfigure(2, weight=2, minsize=170)
        bind_theme(self.overview_view, background="SURFACE")
        self.views["overview"] = self.overview_view

        self.name_field = LabeledEntry(
            self.overview_view,
            "Book Name",
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

        self.author_field = LabeledEntry(
            self.overview_view,
            "Author",
            self.handle_field_change,
            font_size=12,
        )
        self.author_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 0),
            pady=(0, 12),
        )

        self.description_field = MultilineField(
            self.overview_view,
            "Description",
            self.handle_text_change,
            height=12,
        )
        self.description_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 8),
            pady=(0, 8),
        )

        self.categories_editor = TagEditor(
            self.overview_view,
            self.handle_field_change,
        )
        self.categories_editor.configure(text="Categories")
        self.categories_editor.tag_field.label.configure(
            text="Add a category"
        )
        self.categories_editor.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(8, 0),
            pady=(0, 8),
        )

        self.dbnotes_field = MultilineField(
            self.overview_view,
            "DB Notes",
            self.handle_text_change,
            height=8,
        )
        self.dbnotes_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(8, 0),
        )

    def build_link_views(self):
        self.spells_view = tk.Frame(self.view_container, bg=SURFACE)
        self.spells_view.grid(row=0, column=0, sticky="nsew")
        self.spells_view.grid_rowconfigure(0, weight=1)
        self.spells_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.spells_view, background="SURFACE")
        self.views["spells"] = self.spells_view
        self.spells_editor = BookLinkEditor(
            self.spells_view,
            database=self.database,
            collection_name="spells",
            title_text="Spells Taught or Referenced",
            picker_title="Add a Spell to This Book",
            change_command=self.handle_field_change,
        )
        self.spells_editor.grid(row=0, column=0, sticky="nsew")

        self.proficiencies_view = tk.Frame(
            self.view_container,
            bg=SURFACE,
        )
        self.proficiencies_view.grid(row=0, column=0, sticky="nsew")
        self.proficiencies_view.grid_rowconfigure(0, weight=1)
        self.proficiencies_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.proficiencies_view, background="SURFACE")
        self.views["proficiencies"] = self.proficiencies_view
        self.proficiencies_editor = BookLinkEditor(
            self.proficiencies_view,
            database=self.database,
            collection_name="proficiencies",
            title_text="Proficiencies Taught or Referenced",
            picker_title="Add a Proficiency to This Book",
            change_command=self.handle_field_change,
        )
        self.proficiencies_editor.grid(row=0, column=0, sticky="nsew")

        self.potions_view = tk.Frame(self.view_container, bg=SURFACE)
        self.potions_view.grid(row=0, column=0, sticky="nsew")
        self.potions_view.grid_rowconfigure(0, weight=1)
        self.potions_view.grid_columnconfigure(0, weight=1)
        bind_theme(self.potions_view, background="SURFACE")
        self.views["potions"] = self.potions_view
        self.potions_editor = BookLinkEditor(
            self.potions_view,
            database=self.database,
            collection_name="potions",
            title_text="Potions Taught or Referenced",
            picker_title="Add a Potion to This Book",
            change_command=self.handle_field_change,
        )
        self.potions_editor.grid(row=0, column=0, sticky="nsew")

    def set_record(self, record):
        retained_view_name = self.active_view_name or "overview"
        self.loading_record = True
        self.name_field.set_value(record.get("name", ""))
        self.author_field.set_value(record.get("author", ""))
        self.description_field.set_value(record.get("description", ""))
        self.categories_editor.set_tags(record.get("categories", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))
        self.spells_editor.set_references(record.get("spells", []))
        self.proficiencies_editor.set_references(
            record.get("proficiencies", [])
        )
        self.potions_editor.set_references(record.get("potions", []))

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
            "author": self.author_field.get_value(),
            "categories": self.categories_editor.get_tags(),
            "description": self.description_field.get_value(),
            "spells": self.spells_editor.get_references(),
            "proficiencies": self.proficiencies_editor.get_references(),
            "potions": self.potions_editor.get_references(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def show_overview(self):
        self.activate_view("overview")

    def show_spells(self):
        self.activate_view("spells")

    def show_proficiencies(self):
        self.activate_view("proficiencies")

    def show_potions(self):
        self.activate_view("potions")

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
