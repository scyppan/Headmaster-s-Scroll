import tkinter as tk
from tkinter import messagebox

from runtime_theme import bind_theme
from sections.magic.proficiencies.constants import PROFICIENCY_SKILLS
from sections.magic.traditions import TRADITIONS
from shared.widgets import RoundedEntry, SoftButton, StripedListbox
from theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


EMPTY_PROFICIENCY_FILTERS = {
    "skills": (),
    "traditions": (),
    "minimum_threshold": None,
    "maximum_threshold": None,
    "tags": (),
}


class ProficiencyFilterDialog(tk.Toplevel):
    def __init__(self, parent, records, current_filters):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.result = None
        self.skill_values = list(PROFICIENCY_SKILLS)
        self.tradition_values = list(TRADITIONS)
        self.tag_values = sorted(
            {
                str(tag).strip()
                for record in records
                for tag in record.get("tags", [])
                if str(tag).strip()
            },
            key=str.casefold,
        )

        self.title("Filter Proficiencies")
        self.geometry("720x760")
        self.minsize(640, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="Filter Proficiencies",
            bg=APP_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(16),
            anchor="w",
        )
        self.heading.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=24,
            pady=(20, 12),
        )
        bind_theme(
            self.heading,
            background="APP_BACKGROUND",
            foreground="TEXT_DARK",
        )

        self.card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.card.grid(row=1, column=0, sticky="nsew", padx=24)
        self.card.grid_rowconfigure(0, weight=2)
        self.card.grid_rowconfigure(6, weight=1)
        self.card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.classification_row = tk.Frame(self.card, bg=SURFACE)
        self.classification_row.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(16, 0),
        )
        self.classification_row.grid_rowconfigure(2, weight=1)
        self.classification_row.grid_columnconfigure(0, weight=1)
        self.classification_row.grid_columnconfigure(1, weight=1)
        bind_theme(self.classification_row, background="SURFACE")

        self.skill_label = tk.Label(
            self.classification_row,
            text="Skills",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.skill_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 9),
            pady=(0, 2),
        )
        bind_theme(
            self.skill_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.tradition_label = tk.Label(
            self.classification_row,
            text="Traditions",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.tradition_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(9, 0),
            pady=(0, 2),
        )
        bind_theme(
            self.tradition_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.skill_hint = tk.Label(
            self.classification_row,
            text="No selection includes every skill.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        self.skill_hint.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 9),
            pady=(0, 6),
        )
        bind_theme(
            self.skill_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.tradition_hint = tk.Label(
            self.classification_row,
            text="No selection includes every tradition.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        self.tradition_hint.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(9, 0),
            pady=(0, 6),
        )
        bind_theme(
            self.tradition_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.skill_listbox = StripedListbox(
            self.classification_row,
            height=10,
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
            selectmode="extended",
        )
        self.skill_listbox.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(0, 9),
        )
        self.skill_listbox.insert("end", *self.skill_values)

        self.tradition_listbox = StripedListbox(
            self.classification_row,
            height=10,
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
            selectmode="extended",
        )
        self.tradition_listbox.grid(
            row=2,
            column=1,
            sticky="nsew",
            padx=(9, 0),
        )

        if self.tradition_values:
            self.tradition_listbox.insert("end", *self.tradition_values)

        self.threshold_label = tk.Label(
            self.card,
            text="Threshold Range",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.threshold_label.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(14, 6),
        )
        bind_theme(
            self.threshold_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.threshold_row = tk.Frame(self.card, bg=SURFACE)
        self.threshold_row.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
        )
        self.threshold_row.grid_columnconfigure(1, weight=1)
        self.threshold_row.grid_columnconfigure(3, weight=1)
        bind_theme(self.threshold_row, background="SURFACE")

        self.minimum_label = tk.Label(
            self.threshold_row,
            text="Minimum",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
        )
        self.minimum_label.grid(row=0, column=0, padx=(0, 8))
        bind_theme(
            self.minimum_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.minimum_value = tk.StringVar()
        self.minimum_entry = RoundedEntry(
            self.threshold_row,
            textvariable=self.minimum_value,
            background=SURFACE,
            width=110,
            height=38,
            justify="center",
            font=app_font(10),
        )
        self.minimum_entry.grid(row=0, column=1, sticky="w")

        self.maximum_label = tk.Label(
            self.threshold_row,
            text="Maximum",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
        )
        self.maximum_label.grid(row=0, column=2, padx=(24, 8))
        bind_theme(
            self.maximum_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.maximum_value = tk.StringVar()
        self.maximum_entry = RoundedEntry(
            self.threshold_row,
            textvariable=self.maximum_value,
            background=SURFACE,
            width=110,
            height=38,
            justify="center",
            font=app_font(10),
        )
        self.maximum_entry.grid(row=0, column=3, sticky="w")

        threshold_validation = (
            self.register(self.validate_threshold_input),
            "%P",
        )
        self.minimum_entry.entry.configure(
            validate="key",
            validatecommand=threshold_validation,
        )
        self.maximum_entry.entry.configure(
            validate="key",
            validatecommand=threshold_validation,
        )

        self.threshold_hint = tk.Label(
            self.card,
            text="Leave either limit blank when that side is unrestricted.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        self.threshold_hint.grid(
            row=3,
            column=0,
            sticky="ew",
            padx=18,
            pady=(5, 0),
        )
        bind_theme(
            self.threshold_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.tag_label = tk.Label(
            self.card,
            text="Tags",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11),
            anchor="w",
        )
        self.tag_label.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=18,
            pady=(14, 2),
        )
        bind_theme(
            self.tag_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.tag_hint = tk.Label(
            self.card,
            text=(
                "Select one or more. A proficiency may match any selected tag."
                if self.tag_values
                else "No proficiency tags have been added yet."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        self.tag_hint.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 6),
        )
        bind_theme(
            self.tag_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.tag_listbox = StripedListbox(
            self.card,
            height=5,
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
            selectmode="extended",
        )
        self.tag_listbox.grid(
            row=6,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 16),
        )

        if self.tag_values:
            self.tag_listbox.insert("end", *self.tag_values)

        self.button_row = tk.Frame(self, bg=APP_BACKGROUND)
        self.button_row.grid(
            row=2,
            column=0,
            sticky="e",
            padx=24,
            pady=20,
        )
        bind_theme(self.button_row, background="APP_BACKGROUND")

        self.clear_button = SoftButton(
            self.button_row,
            text="Clear All",
            command=self.clear,
            background=APP_BACKGROUND,
            width=94,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.clear_button.pack(side="left", padx=(0, 6))

        self.cancel_button = SoftButton(
            self.button_row,
            text="Cancel",
            command=self.cancel,
            background=APP_BACKGROUND,
            width=86,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.cancel_button.pack(side="left", padx=(0, 6))

        self.apply_button = SoftButton(
            self.button_row,
            text="Apply Filters",
            command=self.apply,
            background=APP_BACKGROUND,
            width=126,
            height=36,
            background_role="APP_BACKGROUND",
        )
        self.apply_button.pack(side="left")

        self.load_filters(current_filters)
        self.bind("<Escape>", self.cancel)
        self.bind("<Return>", self.apply)
        self.grab_set()
        self.skill_listbox.focus_set()

    def load_filters(self, filters):
        selected_skills = set(filters.get("skills", ()))
        selected_traditions = set(filters.get("traditions", ()))
        selected_tags = set(filters.get("tags", ()))

        for skill_index, skill_name in enumerate(self.skill_values):
            if skill_name in selected_skills:
                self.skill_listbox.selection_set(skill_index)

        for tradition_index, tradition_name in enumerate(
            self.tradition_values
        ):
            if tradition_name in selected_traditions:
                self.tradition_listbox.selection_set(tradition_index)

        for tag_index, tag_name in enumerate(self.tag_values):
            if tag_name in selected_tags:
                self.tag_listbox.selection_set(tag_index)

        minimum_threshold = filters.get("minimum_threshold")
        maximum_threshold = filters.get("maximum_threshold")
        self.minimum_value.set(
            "" if minimum_threshold is None else str(minimum_threshold)
        )
        self.maximum_value.set(
            "" if maximum_threshold is None else str(maximum_threshold)
        )

    def validate_threshold_input(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def get_selected_values(self, listbox, values):
        return tuple(values[index] for index in listbox.curselection())

    def get_threshold_value(self, value):
        threshold_text = value.get().strip()

        if not threshold_text:
            return None

        threshold = int(threshold_text)

        if not 1 <= threshold <= 100:
            raise ValueError("Threshold limits must be between 1 and 100.")

        return threshold

    def apply(self, event=None):
        try:
            minimum_threshold = self.get_threshold_value(self.minimum_value)
            maximum_threshold = self.get_threshold_value(self.maximum_value)
        except ValueError as error:
            messagebox.showerror(
                "Invalid threshold filter",
                str(error),
                parent=self,
            )
            return "break"

        if (
            minimum_threshold is not None
            and maximum_threshold is not None
            and minimum_threshold > maximum_threshold
        ):
            messagebox.showerror(
                "Invalid threshold filter",
                "Minimum threshold cannot be greater than maximum threshold.",
                parent=self,
            )
            return "break"

        self.result = {
            "skills": self.get_selected_values(
                self.skill_listbox,
                self.skill_values,
            ),
            "traditions": self.get_selected_values(
                self.tradition_listbox,
                self.tradition_values,
            ),
            "minimum_threshold": minimum_threshold,
            "maximum_threshold": maximum_threshold,
            "tags": self.get_selected_values(
                self.tag_listbox,
                self.tag_values,
            ),
        }
        self.destroy()

        return "break"

    def clear(self):
        self.result = dict(EMPTY_PROFICIENCY_FILTERS)
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()

        return "break"
