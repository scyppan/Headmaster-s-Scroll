import tkinter as tk
from copy import deepcopy

from mage_maker.sections.profile.school_dialog import (
    SchoolSelectionDialog,
)
from mage_maker.ui.theme import (
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SoftButton


SCHOOL_NONE = "{none}"
SCHOOL_SPECIALTY = "{specialty}"


class SchoolField(tk.Frame):
    def __init__(
        self,
        parent,
        schools=None,
        change_command=None,
        background=SURFACE,
    ):
        super().__init__(parent, bg=background)
        self.background = background
        self.change_command = change_command
        self.loading = False
        self.schools = [
            deepcopy(school)
            for school in schools or []
            if isinstance(school, dict)
            and str(school.get("name", "") or "").strip()
        ]
        self.school_names = [
            str(school.get("name", "") or "").strip()
            for school in self.schools
        ]
        self.choice_value = tk.StringVar(value=SCHOOL_NONE)
        self.specialty_value = tk.StringVar()
        self.display_value = tk.StringVar(value="none")
        self.grid_columnconfigure(0, weight=1)

        label = tk.Label(
            self,
            text="School",
            bg=background,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        value_frame = tk.Frame(
            self,
            bg=background,
            height=36,
            cursor="hand2",
        )
        value_frame.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )
        value_frame.grid_propagate(False)
        value_frame.grid_columnconfigure(0, weight=1)
        value_label = tk.Label(
            value_frame,
            textvariable=self.display_value,
            bg=background,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
            padx=0,
            cursor="hand2",
        )
        value_label.grid(row=0, column=0, sticky="nsew")
        value_frame.bind("<Button-1>", self.open_selector)
        value_label.bind("<Button-1>", self.open_selector)
        self.picker = SoftButton(
            self,
            text="Select school",
            command=self.open_selector,
            background=background,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=36,
            font=app_font(9, "bold"),
        )
        self.picker.grid(
            row=1,
            column=1,
            sticky="e",
        )

    def set_value(self, school_name):
        self.loading = True
        normalized_name = str(school_name or "").strip()

        if normalized_name in ("", SCHOOL_NONE):
            self.choice_value.set(SCHOOL_NONE)
            self.specialty_value.set("")
            self.display_value.set("none")
        elif normalized_name == SCHOOL_SPECIALTY:
            self.choice_value.set(SCHOOL_SPECIALTY)
            self.specialty_value.set("")
            self.display_value.set("Specialty school")
        elif normalized_name in self.school_names:
            self.choice_value.set(normalized_name)
            self.specialty_value.set("")
            self.display_value.set(normalized_name)
        else:
            self.choice_value.set(SCHOOL_SPECIALTY)
            self.specialty_value.set(normalized_name)
            self.display_value.set(normalized_name)

        if hasattr(self, "picker"):
            self.picker.set_text(
                "Select school"
                if self.choice_value.get() == SCHOOL_NONE
                else "Change school"
            )

        self.loading = False

    def get_value(self):
        choice = self.choice_value.get().strip()

        if choice == SCHOOL_NONE:
            return ""

        if choice == SCHOOL_SPECIALTY:
            return self.specialty_value.get().strip()

        return choice

    def specialty_is_blank(self):
        return (
            self.choice_value.get().strip() == SCHOOL_SPECIALTY
            and not self.specialty_value.get().strip()
        )

    def open_selector(self, event=None):
        SchoolSelectionDialog(
            self,
            self.schools,
            self.get_value(),
            self.school_selected,
        )

    def school_selected(self, school_name):
        self.set_value(school_name)
        self.notify_change()

    def notify_change(self):
        if not self.loading and self.change_command is not None:
            self.change_command()
