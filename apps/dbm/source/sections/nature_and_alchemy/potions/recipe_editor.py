import tkinter as tk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import (
    BoundedNumberField,
    LabeledEntry,
)
from sections.nature_and_alchemy.potions.ingredients_editor import (
    IngredientsEditor,
)
from shared.widgets import MultilineField, SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class RequiredProficienciesEditor(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_proficiency = False
        self.proficiencies = []
        self.selected_index = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text="Required Proficiencies",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.title.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.status_value = tk.StringVar(value="None required")
        self.status = tk.Label(
            self.header,
            textvariable=self.status_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        self.status.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(2, 0),
        )
        bind_theme(
            self.status,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.add_button = SoftButton(
            self.header,
            text="Add",
            command=self.add_proficiency,
            width=62,
            height=30,
        )
        self.add_button.grid(row=0, column=1, padx=(8, 3))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_proficiency,
            width=78,
            height=30,
        )
        self.remove_button.grid(row=0, column=2, padx=(3, 0))

        self.name_field = LabeledEntry(
            self,
            "Selected Proficiency",
            self.handle_field_change,
        )
        self.name_field.grid(row=1, column=0, sticky="ew", pady=(0, 8))

        self.list_frame = tk.Frame(self, bg=SURFACE)
        self.list_frame.grid(row=2, column=0, sticky="nsew")
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
            font=app_font(9),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
            height=4,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind(
            "<<ListboxSelect>>",
            self.select_proficiency,
        )

        self.scrollbar = tk.Scrollbar(
            self.list_frame,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.listbox.configure(yscrollcommand=self.scrollbar.set)

        self.set_detail_enabled(False)

    def set_proficiencies(self, proficiencies):
        self.loading_proficiency = True
        self.proficiencies = (
            [str(value) for value in proficiencies]
            if isinstance(proficiencies, list)
            else []
        )
        self.selected_index = 0 if self.proficiencies else None
        self.refresh_list()
        self.load_selected_proficiency()
        self.loading_proficiency = False

    def get_proficiencies(self):
        self.save_selected_proficiency()
        converted_proficiencies = []
        normalized_names = set()

        for proficiency in self.proficiencies:
            proficiency_name = str(proficiency).strip()

            if not proficiency_name:
                raise ValueError(
                    "Every required proficiency must have a name"
                )

            normalized_name = " ".join(proficiency_name.split()).casefold()

            if normalized_name in normalized_names:
                raise ValueError(
                    f"Duplicate required proficiency: {proficiency_name}"
                )

            normalized_names.add(normalized_name)
            converted_proficiencies.append(proficiency_name)

        return converted_proficiencies

    def add_proficiency(self):
        self.save_selected_proficiency()
        self.proficiencies.append("New Proficiency")
        self.selected_index = len(self.proficiencies) - 1
        self.refresh_list()
        self.load_selected_proficiency()
        self.change_command()
        self.name_field.focus_set()

    def remove_proficiency(self):
        if self.selected_index is None:
            return

        del self.proficiencies[self.selected_index]

        if self.proficiencies:
            self.selected_index = min(
                self.selected_index,
                len(self.proficiencies) - 1,
            )
        else:
            self.selected_index = None

        self.refresh_list()
        self.load_selected_proficiency()
        self.change_command()

    def select_proficiency(self, event=None):
        if self.loading_proficiency:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]

        if selected_index == self.selected_index:
            return

        self.save_selected_proficiency()
        self.selected_index = selected_index
        self.load_selected_proficiency()

    def refresh_list(self):
        self.loading_proficiency = True
        self.listbox.delete(0, "end")

        for proficiency in self.proficiencies:
            self.listbox.insert("end", proficiency or "Unnamed proficiency")

        if self.selected_index is not None:
            self.listbox.selection_set(self.selected_index)
            self.listbox.activate(self.selected_index)
            self.listbox.see(self.selected_index)

        proficiency_count = len(self.proficiencies)
        self.status_value.set(
            "None required"
            if proficiency_count == 0
            else f"{proficiency_count} required"
        )
        self.remove_button.set_enabled(self.selected_index is not None)
        self.loading_proficiency = False

    def load_selected_proficiency(self):
        self.loading_proficiency = True

        if self.selected_index is None:
            self.name_field.set_value("")
            self.set_detail_enabled(False)
        else:
            self.name_field.set_value(
                self.proficiencies[self.selected_index]
            )
            self.set_detail_enabled(True)

        self.loading_proficiency = False

    def save_selected_proficiency(self):
        if self.selected_index is None:
            return

        self.proficiencies[self.selected_index] = self.name_field.get_value()

    def handle_field_change(self, *arguments):
        if self.loading_proficiency or self.selected_index is None:
            return

        self.save_selected_proficiency()
        self.refresh_list()
        self.change_command()

    def set_detail_enabled(self, enabled):
        self.name_field.entry.set_enabled(enabled)


class RecipeEditor(tk.Frame):
    def __init__(self, parent, database, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_recipe = False

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=3, minsize=460)
        self.grid_columnconfigure(1, weight=2, minsize=330)

        self.ingredients_editor = IngredientsEditor(
            self,
            database,
            self.handle_field_change,
        )
        self.ingredients_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 14),
        )

        self.details = tk.Frame(self, bg=SURFACE)
        self.details.grid(row=0, column=1, sticky="nsew")
        self.details.grid_columnconfigure(0, weight=3)
        self.details.grid_columnconfigure(1, weight=2)
        self.details.grid_rowconfigure(1, weight=2, minsize=170)
        self.details.grid_rowconfigure(2, weight=3, minsize=210)
        bind_theme(self.details, background="SURFACE")

        self.brew_time_field = LabeledEntry(
            self.details,
            "Brew Time",
            self.handle_field_change,
        )
        self.brew_time_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(0, 12),
        )

        self.threshold_field = BoundedNumberField(
            self.details,
            "Threshold",
            self.handle_field_change,
            minimum=1,
            maximum=100,
        )
        self.threshold_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(7, 0),
            pady=(0, 12),
        )

        self.proficiencies_editor = RequiredProficienciesEditor(
            self.details,
            self.handle_field_change,
        )
        self.proficiencies_editor.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(0, 12),
        )

        self.instructions_field = MultilineField(
            self.details,
            "Additional Instructions",
            self.handle_text_change,
            height=10,
        )
        self.instructions_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

    def set_record(self, record):
        self.loading_recipe = True
        self.ingredients_editor.set_ingredients(
            record.get("ingredients", [])
        )
        self.brew_time_field.set_value(record.get("brew_time", ""))
        self.threshold_field.set_value(record.get("threshold"))
        self.proficiencies_editor.set_proficiencies(
            record.get("required_proficiencies", [])
        )
        self.instructions_field.set_value(
            record.get("additional_instructions", "")
        )
        self.loading_recipe = False

    def get_values(self):
        return {
            "ingredients": self.ingredients_editor.get_ingredients(),
            "brew_time": self.brew_time_field.get_value(),
            "threshold": self.threshold_field.get_value(),
            "required_proficiencies": (
                self.proficiencies_editor.get_proficiencies()
            ),
            "additional_instructions": (
                self.instructions_field.get_value()
            ),
        }

    def handle_field_change(self, *arguments):
        if not self.loading_recipe:
            self.change_command()

    def handle_text_change(self):
        self.handle_field_change()
