import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.events.dialog import EventLocationPickerDialog
from mage_maker.sections.locations.models import recent_location_label
from mage_maker.sections.profile.school_field import SchoolField
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    FIELD_BACKGROUND,
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
from mage_maker.ui.widgets import (
    CalendarAdoptionNotice,
    LabeledEntry,
    SoftButton,
)


class CreationWizardDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        create_command,
        game_database=None,
        event_controller=None,
    ):
        super().__init__(parent)
        self.create_command = create_command
        self.game_database = game_database
        self.event_controller = event_controller
        self.starting_location_id = ""
        self.title("Create New Magician")
        self.geometry("640x640")
        self.minsize(580, 610)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent)
        self.grab_set()

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=PRIMARY_DARK, height=66)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            text="Create New Magician",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(17, "bold"),
            anchor="w",
            padx=22,
        )
        heading.grid(row=0, column=0, sticky="nsew")

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.grid(row=1, column=0, sticky="nsew", padx=22, pady=22)
        card.grid_columnconfigure(0, weight=1)

        placeholder = tk.Label(
            card,
            text=(
                "This is the first placeholder step in the creation wizard. "
                "Enter the unique displayed name, any known birth date, and the "
                "person's starting location."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=520,
            padx=14,
            pady=12,
        )
        placeholder.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 14))

        self.displayed_name_value = tk.StringVar()
        self.birth_year_value = tk.StringVar()
        self.birth_month_value = tk.StringVar()
        self.birth_day_value = tk.StringVar()
        self.starting_location_value = tk.StringVar(
            value="Select a starting location."
        )
        self.can_give_birth_value = tk.BooleanVar(value=False)

        displayed_name_field = LabeledEntry(
            card,
            "Displayed name",
            self.displayed_name_value,
            background=SURFACE,
            font_size=12,
        )
        displayed_name_field.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=16,
            pady=(0, 14),
        )
        self.displayed_name_entry = displayed_name_field.control

        birth_frame = tk.Frame(card, bg=SURFACE)
        birth_frame.grid(row=2, column=0, sticky="ew", padx=16)
        birth_frame.grid_columnconfigure((0, 1, 2), weight=1)

        birth_year_field = LabeledEntry(
            birth_frame,
            "Birth year",
            self.birth_year_value,
            background=SURFACE,
        )
        birth_year_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))

        birth_month_field = LabeledEntry(
            birth_frame,
            "Month",
            self.birth_month_value,
            background=SURFACE,
        )
        birth_month_field.grid(row=0, column=1, sticky="ew", padx=6)

        birth_day_field = LabeledEntry(
            birth_frame,
            "Day",
            self.birth_day_value,
            background=SURFACE,
        )
        birth_day_field.grid(row=0, column=2, sticky="ew", padx=(6, 0))

        calendar_notice = CalendarAdoptionNotice(
            card,
            background=SURFACE,
            wraplength=520,
            date_variables=(
                self.birth_year_value,
                self.birth_month_value,
                self.birth_day_value,
            ),
        )
        calendar_notice.grid(
            row=3,
            column=0,
            sticky="w",
            padx=16,
            pady=(6, 0),
        )

        starting_location_panel = tk.Frame(card, bg=SURFACE)
        starting_location_panel.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=16,
            pady=(14, 0),
        )
        starting_location_panel.grid_columnconfigure(0, weight=1)
        starting_location_label = tk.Label(
            starting_location_panel,
            text="Starting location",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        starting_location_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        starting_location_display = tk.Frame(
            starting_location_panel,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER,
            highlightthickness=1,
            height=40,
        )
        starting_location_display.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )
        starting_location_display.grid_propagate(False)
        starting_location_display.grid_columnconfigure(0, weight=1)
        starting_location_text = tk.Label(
            starting_location_display,
            textvariable=self.starting_location_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
        )
        starting_location_text.grid(row=0, column=0, sticky="nsew")
        self.starting_location_button = SoftButton(
            starting_location_panel,
            text="Select location",
            command=self.open_starting_location_selector,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=40,
            font=app_font(9, "bold"),
        )
        self.starting_location_button.grid(
            row=1,
            column=1,
            sticky="e",
        )
        self.starting_location_button.set_enabled(
            self.event_controller is not None
        )

        school_records = (
            self.game_database.schools()
            if self.game_database is not None and self.game_database.loaded
            else []
        )
        self.school_field = SchoolField(
            card,
            school_records,
            background=SURFACE,
        )
        self.school_field.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=16,
            pady=(14, 0),
        )

        can_give_birth_check = tk.Checkbutton(
            card,
            text="Can give birth",
            variable=self.can_give_birth_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=SURFACE_MUTED,
            font=app_font(10),
            anchor="w",
            borderwidth=0,
            highlightthickness=0,
        )
        can_give_birth_check.grid(
            row=6,
            column=0,
            sticky="w",
            padx=16,
            pady=(14, 0),
        )

        buttons = tk.Frame(self, bg=APP_BACKGROUND)
        buttons.grid(row=2, column=0, sticky="e", padx=22, pady=(0, 18))

        cancel_button = SoftButton(
            buttons,
            text="Cancel",
            command=self.destroy,
            background=APP_BACKGROUND,
            width=92,
            height=38,
        )
        cancel_button.pack(side="left", padx=(0, 6))

        create_button = SoftButton(
            buttons,
            text="Okay",
            command=self.create_magician,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=38,
        )
        create_button.pack(side="left")

        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.submit_dialog)
        self.after(50, self.focus_name)

    def create_magician(self):
        location_records = (
            self.event_controller.location_records()
            if self.event_controller is not None
            else []
        )
        selected_location = next(
            (
                location
                for location in location_records
                if str(location.get("record_id", "") or "").strip()
                == self.starting_location_id
            ),
            None,
        )

        if selected_location is None:
            messagebox.showerror(
                "Starting location required",
                "Select the magician's starting location.",
                parent=self,
            )
            return

        starting_location = str(
            selected_location.get("name", "") or ""
        ).strip()

        if not starting_location:
            messagebox.showerror(
                "Starting location required",
                "The selected starting location needs a name.",
                parent=self,
            )
            return

        if self.school_field.specialty_is_blank():
            messagebox.showerror(
                "Specialty school required",
                "Enter the specialty school name.",
                parent=self,
            )
            return

        values = {
            "displayed_name": self.displayed_name_value.get(),
            "birth_year": self.birth_year_value.get(),
            "birth_month": self.birth_month_value.get(),
            "birth_day": self.birth_day_value.get(),
            "starting_location": starting_location,
            "starting_location_id": self.starting_location_id,
            "school": self.school_field.get_value(),
            "can_give_birth": self.can_give_birth_value.get(),
        }

        try:
            created_person = self.create_command(values)
        except (TypeError, ValueError) as error:
            messagebox.showerror("Cannot create magician", str(error), parent=self)
            return

        if created_person is not None:
            self.destroy()

    def open_starting_location_selector(self):
        if self.event_controller is None:
            messagebox.showerror(
                "Locations unavailable",
                "The location collection is unavailable.",
                parent=self,
            )
            return False

        EventLocationPickerDialog(
            self,
            self.event_controller.location_records(),
            self.starting_location_id,
            self.starting_location_chosen,
            dialog_title="Choose starting location",
            action_text="Use location",
            create_location_command=getattr(
                self.event_controller,
                "create_placeholder_location",
                None,
            ),
            recent_location_options=(
                self.event_controller.recent_location_options()
            ),
            selection_history_command=getattr(
                self.event_controller,
                "remember_location_selection",
                None,
            ),
        )
        return True

    def starting_location_chosen(self, location_id):
        normalized_location_id = str(location_id or "").strip()
        location_records = (
            self.event_controller.location_records()
            if self.event_controller is not None
            else []
        )
        selected_location = next(
            (
                location
                for location in location_records
                if str(location.get("record_id", "") or "").strip()
                == normalized_location_id
            ),
            None,
        )

        if selected_location is None:
            return False

        self.starting_location_id = normalized_location_id
        self.starting_location_value.set(
            recent_location_label(
                normalized_location_id,
                location_records,
            )
        )
        return True

    def close_dialog(self, event=None):
        self.destroy()

    def submit_dialog(self, event=None):
        self.create_magician()

    def focus_name(self):
        self.displayed_name_entry.focus_set()
