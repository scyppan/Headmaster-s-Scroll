import tkinter as tk
from copy import deepcopy
from tkinter import messagebox
from uuid import uuid4

from mage_maker.core.dates import (
    LATEST_HISTORICAL_YEAR,
    next_historical_date,
)
from mage_maker.core.wizarding_currency import (
    currency_component_input_is_valid,
    normalize_monthly_salary,
)
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    split_world_event_date,
)
from mage_maker.sections.development.models import job_date_tuple
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
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
    RoundedEntry,
    SoftButton,
)


class SalaryRaiseDialog(tk.Toplevel):
    def __init__(self, parent, save_command, existing_raise=None):
        super().__init__(parent)
        self.save_command = save_command
        self.existing_raise = deepcopy(existing_raise or {})
        year, month, day = split_world_event_date(
            self.existing_raise.get("date", "")
        )
        salary = normalize_monthly_salary(
            self.existing_raise.get("salary")
        )
        self.year_value = tk.StringVar(value=year)
        self.month_value = tk.StringVar(value=month)
        self.day_value = tk.StringVar(value=day)
        self.galleons_value = tk.StringVar(
            value=str(salary["galleons"])
        )
        self.sickles_value = tk.StringVar(
            value=str(salary["sickles"])
        )
        self.knuts_value = tk.StringVar(value=str(salary["knuts"]))
        self.title(
            "Edit salary raise"
            if self.existing_raise
            else "Add salary raise"
        )
        self.geometry("620x390")
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.bind("<Escape>", self.close_dialog)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.grab_set()

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=56)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text=(
                "Edit salary raise"
                if self.existing_raise
                else "Add salary raise"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(14, "bold"),
            anchor="w",
            padx=18,
        ).pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure((0, 1, 2), weight=1)
        tk.Label(
            body,
            text="Raise date",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew")

        for column, label_text, variable in (
            (0, "Year", self.year_value),
            (1, "Month", self.month_value),
            (2, "Day", self.day_value),
        ):
            panel = tk.Frame(body, bg=SURFACE)
            panel.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0, 6) if column < 2 else 0,
                pady=(5, 0),
            )
            panel.grid_columnconfigure(0, weight=1)
            tk.Label(
                panel,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            RoundedEntry(
                panel,
                textvariable=variable,
                background=SURFACE,
                height=34,
                justify="center",
            ).grid(row=1, column=0, sticky="ew", pady=(3, 0))

        CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=560,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        ).grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(6, 12),
        )
        tk.Label(
            body,
            text="New monthly salary",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        ).grid(row=3, column=0, columnspan=3, sticky="ew")

        for column, label_text, variable, maximum in (
            (0, "Galleons", self.galleons_value, ""),
            (1, "Sickles", self.sickles_value, "16"),
            (2, "Knuts", self.knuts_value, "28"),
        ):
            panel = tk.Frame(body, bg=SURFACE)
            panel.grid(
                row=4,
                column=column,
                sticky="ew",
                padx=(0, 6) if column < 2 else 0,
                pady=(5, 0),
            )
            panel.grid_columnconfigure(0, weight=1)
            tk.Label(
                panel,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            entry = RoundedEntry(
                panel,
                textvariable=variable,
                background=SURFACE,
                height=34,
                justify="center",
            )
            entry.grid(row=1, column=0, sticky="ew", pady=(3, 0))
            entry.entry.configure(
                validate="key",
                validatecommand=(
                    self.register(currency_component_input_is_valid),
                    "%P",
                    maximum,
                ),
            )

        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="e", padx=18, pady=(0, 16))
        SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        ).pack(side="left", padx=(0, 7))
        SoftButton(
            footer,
            text="Save raise",
            command=self.save_raise,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        ).pack(side="left")

    def save_raise(self):
        date_text = self.year_value.get().strip()

        if self.month_value.get().strip():
            date_text += f"-{self.month_value.get().strip()}"

        if self.day_value.get().strip():
            date_text += f"-{self.day_value.get().strip()}"

        try:
            normalized_date = normalize_world_event_date(date_text)
            salary = normalize_monthly_salary(
                {
                    "galleons": self.galleons_value.get(),
                    "sickles": self.sickles_value.get(),
                    "knuts": self.knuts_value.get(),
                }
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save salary raise",
                str(error),
                parent=self,
            )
            return

        self.save_command(
            {
                "record_id": str(
                    self.existing_raise.get("record_id", "")
                    or uuid4()
                ),
                "date": normalized_date,
                "salary": salary,
            }
        )
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class JobAppointmentDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        people,
        organization,
        organization_job,
        vacancy,
        save_command,
        availability_command=None,
        existing_appointment=None,
        default_salary=None,
        existing_raises=None,
    ):
        super().__init__(parent)
        self.people = [
            deepcopy(person)
            for person in people or []
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        ]
        self.organization = deepcopy(organization or {})
        self.organization_job = deepcopy(organization_job or {})
        self.vacancy = deepcopy(vacancy or {})
        self.save_command = save_command
        self.availability_command = availability_command
        self.existing_appointment = deepcopy(existing_appointment or {})
        self.raises = [
            deepcopy(raise_record)
            for raise_record in existing_raises or []
            if isinstance(raise_record, dict)
        ]
        self.person_raises = deepcopy(self.raises)
        self.visible_people = []
        self.availability_valid = True
        self.initializing = True
        self.search_value = tk.StringVar()
        self.results_value = tk.StringVar()
        self.availability_value = tk.StringVar(
            value="Choose an individual to check their availability."
        )
        self.special_value = tk.BooleanVar(
            value=bool(
                self.existing_appointment.get(
                    "special_appointment_name",
                    "",
                )
            )
        )
        self.special_name_value = tk.StringVar(
            value=str(
                self.existing_appointment.get(
                    "special_appointment_name",
                    "",
                )
                or ""
            )
        )
        self.concurrent_value = tk.BooleanVar(
            value=bool(
                self.existing_appointment.get("job_concurrent", False)
                or self.existing_appointment.get("concurrent", False)
            )
        )
        self.current_value = tk.BooleanVar(
            value=bool(
                self.existing_appointment
                and not str(
                    self.existing_appointment.get("job_end_date", "") or ""
                ).strip()
            )
        )
        self.died_in_office_value = tk.BooleanVar(
            value=bool(
                self.existing_appointment.get("died_in_office", False)
            )
        )
        salary = normalize_monthly_salary(
            self.existing_appointment.get("salary", default_salary)
        )
        self.salary_galleons_value = tk.StringVar(
            value=str(salary["galleons"])
        )
        self.salary_sickles_value = tk.StringVar(
            value=str(salary["sickles"])
        )
        self.salary_knuts_value = tk.StringVar(
            value=str(salary["knuts"])
        )
        start_date = str(
            self.existing_appointment.get("date", "") or ""
        ).strip()
        end_date = str(
            self.existing_appointment.get("job_end_date", "") or ""
        ).strip()

        if not start_date:
            start_date = self.date_text_from_range("start")

        if not end_date and not self.current_value.get():
            end_date = self.date_text_from_range("end")

        start_year, start_month, start_day = split_world_event_date(
            start_date
        )
        end_year, end_month, end_day = split_world_event_date(end_date)
        self.start_year_value = tk.StringVar(value=start_year)
        self.start_month_value = tk.StringVar(value=start_month)
        self.start_day_value = tk.StringVar(value=start_day)
        self.end_year_value = tk.StringVar(value=end_year)
        self.end_month_value = tk.StringVar(value=end_month)
        self.end_day_value = tk.StringVar(value=end_day)
        self.saved_end_values = (end_year, end_month, end_day)
        self.title(
            "Edit job appointment"
            if self.existing_appointment
            else "Fill vacant position"
        )
        self.geometry("840x900")
        self.minsize(760, 780)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.bind("<Escape>", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_people)
        self.special_name_value.trace_add("write", self.update_save_state)
        self.refresh_people()
        self.select_existing_person()
        self.special_state_changed()
        self.current_state_changed()
        self.refresh_raise_list()
        self.initializing = False
        self.apply_availability_constraints(update_dates=False)
        self.update_save_state()
        self.grab_set()

    def date_text_from_range(self, prefix):
        year = str(self.vacancy.get(f"{prefix}_year", "") or "").strip()
        month = str(
            self.vacancy.get(f"{prefix}_month", "") or ""
        ).strip()
        day = str(self.vacancy.get(f"{prefix}_day", "") or "").strip()
        date_text = year

        if month:
            date_text += f"-{month}"

        if day:
            date_text += f"-{day}"

        return date_text

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        tk.Label(
            header,
            text=(
                "Edit job appointment"
                if self.existing_appointment
                else "Fill vacant position"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        ).pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=16)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(4, weight=1)
        body.grid_columnconfigure(0, weight=1)
        organization_name = str(
            self.organization.get("name", "") or "Unnamed organization"
        ).strip()
        job_title = str(
            self.organization_job.get("title", "") or "Unnamed position"
        ).strip()
        tk.Label(
            body,
            text=f"{job_title} at {organization_name}",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        option_row = tk.Frame(body, bg=SURFACE)
        option_row.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.special_checkbox = tk.Checkbutton(
            option_row,
            text="Special appointment",
            variable=self.special_value,
            command=self.special_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
        )
        self.special_checkbox.pack(side="left")
        self.concurrent_checkbox = tk.Checkbutton(
            option_row,
            text="Hold concurrently",
            variable=self.concurrent_value,
            command=self.concurrent_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
        )
        self.concurrent_checkbox.pack(side="left", padx=(18, 0))
        self.died_checkbox = tk.Checkbutton(
            option_row,
            text="Died in office",
            variable=self.died_in_office_value,
            command=self.died_in_office_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
        )
        self.died_checkbox.pack(side="left", padx=(18, 0))
        self.special_name_entry = RoundedEntry(
            body,
            textvariable=self.special_name_value,
            background=SURFACE,
            height=36,
            font=app_font(10),
        )
        self.special_name_entry.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        self.search_entry = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            height=36,
            font=app_font(10),
        )
        self.search_entry.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(6, 3))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=4, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.people_list = tk.Listbox(
            list_frame,
            height=6,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.people_list.grid(row=0, column=0, sticky="nsew")
        self.people_list.bind("<<ListboxSelect>>", self.person_selected)
        scrollbar = tk.Scrollbar(list_frame, command=self.people_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.people_list.configure(yscrollcommand=scrollbar.set)
        salary_frame = tk.Frame(body, bg=SURFACE)
        salary_frame.grid(row=5, column=0, sticky="ew", pady=(10, 0))
        salary_frame.grid_columnconfigure((0, 1, 2), weight=1)
        tk.Label(
            salary_frame,
            text="Starting salary",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew")

        for column, label_text, variable, maximum in (
            (0, "Galleons", self.salary_galleons_value, ""),
            (1, "Sickles", self.salary_sickles_value, "16"),
            (2, "Knuts", self.salary_knuts_value, "28"),
        ):
            panel = tk.Frame(salary_frame, bg=SURFACE)
            panel.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0, 7) if column < 2 else 0,
                pady=(3, 0),
            )
            panel.grid_columnconfigure(0, weight=1)
            tk.Label(
                panel,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            salary_entry = RoundedEntry(
                panel,
                textvariable=variable,
                background=SURFACE,
                height=32,
                justify="center",
            )
            salary_entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            salary_entry.entry.configure(
                validate="key",
                validatecommand=(
                    self.register(currency_component_input_is_valid),
                    "%P",
                    maximum,
                ),
            )

        dates_frame = tk.Frame(body, bg=SURFACE)
        dates_frame.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        dates_frame.grid_columnconfigure((0, 1), weight=1)
        self.start_entries = self.build_date_fields(
            dates_frame,
            0,
            "Start date",
            self.start_year_value,
            self.start_month_value,
            self.start_day_value,
        )
        self.end_entries = self.build_date_fields(
            dates_frame,
            1,
            "End date",
            self.end_year_value,
            self.end_month_value,
            self.end_day_value,
        )
        date_options = tk.Frame(body, bg=SURFACE)
        date_options.grid(row=7, column=0, sticky="ew", pady=(6, 0))
        self.current_checkbox = tk.Checkbutton(
            date_options,
            text="Currently in position (no end date)",
            variable=self.current_value,
            command=self.current_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
        )
        self.current_checkbox.pack(side="left")
        CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=740,
            date_variables=(
                (
                    self.start_year_value,
                    self.start_month_value,
                    self.start_day_value,
                ),
                (
                    self.end_year_value,
                    self.end_month_value,
                    self.end_day_value,
                ),
            ),
        ).grid(row=8, column=0, sticky="w", pady=(4, 0))
        tk.Label(
            body,
            textvariable=self.availability_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=740,
            padx=10,
            pady=7,
        ).grid(row=9, column=0, sticky="ew", pady=(6, 0))
        raises_frame = tk.Frame(body, bg=SURFACE)
        raises_frame.grid(row=10, column=0, sticky="ew", pady=(10, 0))
        raises_frame.grid_columnconfigure(0, weight=1)
        tk.Label(
            raises_frame,
            text="Subsequent raises",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.raises_list = tk.Listbox(
            raises_frame,
            height=3,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.raises_list.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        self.raises_list.bind("<Double-Button-1>", self.edit_raise)
        raise_actions = tk.Frame(raises_frame, bg=SURFACE)
        raise_actions.grid(row=1, column=1, sticky="n", padx=(7, 0))
        self.add_raise_button = SoftButton(
            raise_actions,
            text="Add raise",
            command=self.add_raise,
            background=SURFACE,
            width=88,
            height=28,
            font=app_font(8, "bold"),
        )
        self.add_raise_button.pack(fill="x")
        self.edit_raise_button = SoftButton(
            raise_actions,
            text="Edit",
            command=self.edit_raise,
            background=SURFACE,
            width=88,
            height=28,
            font=app_font(8, "bold"),
        )
        self.edit_raise_button.pack(fill="x", pady=(4, 0))
        self.remove_raise_button = SoftButton(
            raise_actions,
            text="Remove",
            command=self.remove_raise,
            background=SURFACE,
            width=88,
            height=28,
            font=app_font(8, "bold"),
        )
        self.remove_raise_button.pack(fill="x", pady=(4, 0))
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 14))
        footer.grid_columnconfigure(0, weight=1)
        SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        ).grid(row=0, column=1, padx=(0, 7))
        self.save_button = SoftButton(
            footer,
            text=(
                "Save appointment"
                if self.existing_appointment
                else "Fill position"
            ),
            command=self.save_appointment,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=138,
            height=36,
        )
        self.save_button.grid(row=0, column=2)

    def build_date_fields(
        self,
        parent,
        column,
        heading,
        year_value,
        month_value,
        day_value,
    ):
        panel = tk.Frame(parent, bg=SURFACE)
        panel.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 7) if column == 0 else (7, 0),
        )
        panel.grid_columnconfigure((0, 1, 2), weight=1)
        tk.Label(
            panel,
            text=heading,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=3, sticky="ew")
        entries = []

        for field_column, label_text, variable in (
            (0, "Year", year_value),
            (1, "Month", month_value),
            (2, "Day", day_value),
        ):
            field = tk.Frame(panel, bg=SURFACE)
            field.grid(
                row=1,
                column=field_column,
                sticky="ew",
                padx=(0, 5) if field_column < 2 else 0,
                pady=(3, 0),
            )
            field.grid_columnconfigure(0, weight=1)
            tk.Label(
                field,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(7, "bold"),
                anchor="w",
            ).grid(row=0, column=0, sticky="ew")
            entry = RoundedEntry(
                field,
                textvariable=variable,
                background=SURFACE,
                height=30,
                justify="center",
            )
            entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))
            entries.append(entry)

        return entries

    def refresh_people(self, *arguments):
        query = self.search_value.get().strip().casefold()
        self.visible_people = sorted(
            [
                person
                for person in self.people
                if query
                in str(person.get("displayed_name", "") or "").casefold()
            ],
            key=lambda person: str(
                person.get("displayed_name", "") or ""
            ).casefold(),
        )
        self.people_list.delete(0, "end")

        for index, person in enumerate(self.visible_people):
            self.people_list.insert(
                "end",
                str(person.get("displayed_name", "") or "Unnamed magician"),
            )
            self.people_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.results_value.set(f"People ({len(self.visible_people)})")
        self.update_save_state()

    def select_existing_person(self):
        person_ids = list(
            self.existing_appointment.get("person_ids", []) or []
        )

        if not person_ids:
            return

        person_id = str(person_ids[0] or "").strip()

        for index, person in enumerate(self.visible_people):
            if str(person.get("record_id", "") or "").strip() != person_id:
                continue

            self.people_list.selection_set(index)
            self.people_list.see(index)
            self.apply_availability_constraints(update_dates=False)
            self.update_save_state()
            return

    def selected_person(self):
        selected = self.people_list.curselection()

        if not selected or selected[0] >= len(self.visible_people):
            return None

        return self.visible_people[int(selected[0])]

    def person_selected(self, event=None):
        self.apply_availability_constraints()
        self.update_save_state()

    def special_state_changed(self):
        special = self.special_value.get()

        if special:
            self.person_raises = deepcopy(self.raises)
            self.raises = []
            self.refresh_raise_list()
            self.search_entry.grid_remove()
            self.people_list.master.grid_remove()
            self.special_name_entry.grid()
            self.results_value.set(
                "Enter a creature, office-holder description, or other name."
            )
            self.concurrent_value.set(False)
            self.died_in_office_value.set(False)
        else:
            if not self.raises and self.person_raises:
                self.raises = deepcopy(self.person_raises)
                self.refresh_raise_list()
            self.special_name_entry.grid_remove()
            self.search_entry.grid()
            self.people_list.master.grid()
            self.refresh_people()

        self.concurrent_checkbox.configure(
            state="disabled" if special else "normal"
        )
        self.died_checkbox.configure(
            state="disabled" if special else "normal"
        )
        self.set_raise_controls_enabled(not special)
        self.apply_availability_constraints()
        self.update_save_state()

    def concurrent_state_changed(self):
        self.apply_availability_constraints()
        self.update_save_state()

    def died_in_office_state_changed(self):
        if self.died_in_office_value.get():
            self.current_value.set(False)

        self.current_checkbox.configure(
            state=(
                "disabled"
                if (
                    self.died_in_office_value.get()
                    or not bool(self.vacancy.get("open_ended", False))
                )
                else "normal"
            )
        )
        self.current_state_changed()

    def current_state_changed(self):
        if self.current_value.get():
            current_end = (
                self.end_year_value.get(),
                self.end_month_value.get(),
                self.end_day_value.get(),
            )

            if any(current_end):
                self.saved_end_values = current_end

            self.end_year_value.set("")
            self.end_month_value.set("")
            self.end_day_value.set("")
        elif not any(
            (
                self.end_year_value.get(),
                self.end_month_value.get(),
                self.end_day_value.get(),
            )
        ):
            restored = self.saved_end_values

            if not any(restored):
                restored = (
                    str(self.vacancy.get("end_year", "") or ""),
                    str(self.vacancy.get("end_month", "") or ""),
                    str(self.vacancy.get("end_day", "") or ""),
                )

            self.end_year_value.set(restored[0])
            self.end_month_value.set(restored[1])
            self.end_day_value.set(restored[2])

        for entry in self.end_entries:
            entry.set_enabled(not self.current_value.get())

        self.died_checkbox.configure(
            state=(
                "disabled"
                if self.current_value.get() or self.special_value.get()
                else "normal"
            )
        )

        if not self.initializing:
            self.apply_availability_constraints()

        self.update_save_state()

    def appointment_window(self):
        return (
            (
                int(self.vacancy["start_year"]),
                int(self.vacancy.get("start_month") or 1),
                int(self.vacancy.get("start_day") or 1),
            ),
            (
                int(self.vacancy["end_year"]),
                int(self.vacancy.get("end_month") or 12),
                int(self.vacancy.get("end_day") or 31),
            ),
        )

    def apply_availability_constraints(self, update_dates=True):
        self.availability_valid = True
        selected_person = self.selected_person()

        if (
            self.current_value.get()
            and not bool(self.vacancy.get("open_ended", False))
        ):
            self.availability_valid = False
            self.availability_value.set(
                "This vacancy has a fixed end date, so the appointment "
                "cannot be marked as current."
            )
            return

        if self.special_value.get():
            self.availability_value.set(
                "Special appointments are constrained only by this "
                "position's vacancy window."
            )
            return

        if selected_person is None:
            self.availability_value.set(
                "Choose an individual to check their other jobs."
            )
            return

        if self.concurrent_value.get():
            self.availability_value.set(
                "Concurrent appointment: only this position's vacancy "
                "window limits the dates."
            )
            return

        if self.availability_command is None:
            return

        window_start, window_end = self.appointment_window()
        availability_end = (
            (LATEST_HISTORICAL_YEAR, 12, 31)
            if self.current_value.get()
            else window_end
        )
        available = self.availability_command(
            selected_person.get("record_id", ""),
            window_start,
            availability_end,
            str(
                self.existing_appointment.get("job_assignment_id", "")
                or ""
            ),
        )

        if available is None:
            self.availability_valid = False
            self.availability_value.set(
                "This individual has no non-overlapping dates in this "
                "vacancy. Select Hold concurrently or choose someone else."
            )
            return

        available_start, available_end = available

        if (
            self.current_value.get()
            and available_end
            != (LATEST_HISTORICAL_YEAR, 12, 31)
        ):
            next_job_start = next_historical_date(*available_end)
            self.availability_valid = False
            self.availability_value.set(
                "This individual has another non-concurrent job beginning "
                f"{next_job_start[0]}-{next_job_start[1]:02d}-"
                f"{next_job_start[2]:02d}. Enter an end date or select "
                "Hold concurrently."
            )
            return

        if update_dates and not (
            self.initializing and self.existing_appointment
        ):
            self.start_year_value.set(str(available_start[0]))
            self.start_month_value.set(str(available_start[1]))
            self.start_day_value.set(str(available_start[2]))

            if not self.current_value.get():
                self.end_year_value.set(str(available_end[0]))
                self.end_month_value.set(str(available_end[1]))
                self.end_day_value.set(str(available_end[2]))

        if self.current_value.get():
            self.availability_value.set(
                "Available without overlapping another job from "
                f"{available_start[0]}-{available_start[1]:02d}-"
                f"{available_start[2]:02d}, with no later job recorded."
            )
            return

        self.availability_value.set(
            "Available without overlapping another job: "
            f"{available_start[0]}-{available_start[1]:02d}-"
            f"{available_start[2]:02d} through "
            f"{available_end[0]}-{available_end[1]:02d}-"
            f"{available_end[2]:02d}."
        )

    def set_raise_controls_enabled(self, enabled):
        self.add_raise_button.set_enabled(enabled)
        self.edit_raise_button.set_enabled(enabled)
        self.remove_raise_button.set_enabled(enabled)

    def refresh_raise_list(self):
        self.raises.sort(key=lambda record: str(record.get("date", "")))
        self.raises_list.delete(0, "end")

        for index, raise_record in enumerate(self.raises):
            salary = normalize_monthly_salary(raise_record.get("salary"))
            self.raises_list.insert(
                "end",
                f"{raise_record.get('date', '')} — "
                f"{salary['galleons']}g {salary['sickles']}s "
                f"{salary['knuts']}k",
            )
            self.raises_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

    def add_raise(self):
        if self.special_value.get():
            return

        SalaryRaiseDialog(self, self.save_raise)

    def edit_raise(self, event=None):
        if self.special_value.get():
            return

        selected = self.raises_list.curselection()

        if not selected:
            return

        SalaryRaiseDialog(
            self,
            self.save_raise,
            self.raises[int(selected[0])],
        )

    def save_raise(self, raise_record):
        record_id = str(raise_record.get("record_id", "") or "")
        self.raises = [
            deepcopy(raise_record)
            if str(stored.get("record_id", "") or "") == record_id
            else stored
            for stored in self.raises
        ]

        if not any(
            str(stored.get("record_id", "") or "") == record_id
            for stored in self.raises
        ):
            self.raises.append(deepcopy(raise_record))

        self.refresh_raise_list()

    def remove_raise(self):
        selected = self.raises_list.curselection()

        if not selected:
            return

        selected_index = int(selected[0])
        self.raises = [
            raise_record
            for index, raise_record in enumerate(self.raises)
            if index != selected_index
        ]
        self.refresh_raise_list()

    def date_value(self, prefix):
        year_value = getattr(self, f"{prefix}_year_value").get().strip()
        month_value = getattr(
            self,
            f"{prefix}_month_value",
        ).get().strip()
        day_value = getattr(self, f"{prefix}_day_value").get().strip()
        date_text = year_value

        if month_value:
            date_text += f"-{month_value}"

        if day_value:
            date_text += f"-{day_value}"

        return date_text

    def update_save_state(self, *arguments):
        has_holder = bool(
            self.special_name_value.get().strip()
            if self.special_value.get()
            else self.selected_person()
        )
        self.save_button.set_enabled(
            has_holder and self.availability_valid
        )

    def save_appointment(self):
        person = None if self.special_value.get() else self.selected_person()
        special_name = (
            self.special_name_value.get().strip()
            if self.special_value.get()
            else ""
        )

        if person is None and not special_name:
            return

        start_date = self.date_value("start")
        end_date = "" if self.current_value.get() else self.date_value("end")

        try:
            start_date = normalize_world_event_date(start_date)
            end_date = (
                normalize_world_event_date(end_date) if end_date else ""
            )
            salary = normalize_monthly_salary(
                {
                    "galleons": self.salary_galleons_value.get(),
                    "sickles": self.salary_sickles_value.get(),
                    "knuts": self.salary_knuts_value.get(),
                }
            )
            start_parts = split_world_event_date(start_date)
            start_boundary = job_date_tuple(*start_parts)
            end_boundary = (
                job_date_tuple(
                    *split_world_event_date(end_date),
                    end_boundary=True,
                )
                if end_date
                else None
            )

            for raise_record in self.raises:
                raise_date = normalize_world_event_date(
                    raise_record.get("date", "")
                )
                raise_boundary = job_date_tuple(
                    *split_world_event_date(raise_date)
                )

                if raise_boundary < start_boundary or (
                    end_boundary is not None
                    and raise_boundary > end_boundary
                ):
                    raise ValueError(
                        "Every raise date must fall within the appointment."
                    )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save appointment",
                str(error),
                parent=self,
            )
            return

        saved = self.save_command(
            {
                "person": deepcopy(person) if person is not None else None,
                "special_appointment_name": special_name,
                "salary": salary,
                "start_date": start_date,
                "end_date": end_date,
                "currently_in_position": self.current_value.get(),
                "job_concurrent": self.concurrent_value.get(),
                "died_in_office": self.died_in_office_value.get(),
                "raises": deepcopy(self.raises),
                "existing_appointment": deepcopy(
                    self.existing_appointment
                ),
            }
        )

        if saved is not False:
            self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
