import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.wizarding_currency import (
    currency_component_input_is_valid,
)
from mage_maker.sections.development.models import (
    new_job_record,
    normalize_job_record,
    normalize_job_records,
    require_job_position_available,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
)
from mage_maker.sections.organizations.controller import (
    normalize_organization_jobs,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
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


class PositionAssignmentDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        organizations,
        default_start_year,
        save_command,
        organization_create_command=None,
        organization_location_provider=None,
        assignments=None,
        existing_record=None,
        default_start_month=None,
        default_start_day=None,
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.organization_create_command = organization_create_command
        self.organization_location_provider = (
            organization_location_provider
        )
        self.organizations = [
            deepcopy(organization)
            for organization in organizations or []
            if isinstance(organization, dict)
            and str(organization.get("name", "") or "").strip()
        ]
        self.assignments = normalize_job_records(assignments or [])
        self.existing_record = (
            normalize_job_record(existing_record)
            if isinstance(existing_record, dict)
            else None
        )
        self.selected_organization = None
        self.selected_job = None
        self.visible_jobs = []
        existing_salary = (
            self.existing_record["salary"]
            if self.existing_record is not None
            else {
                "galleons": 0,
                "sickles": 0,
                "knuts": 0,
            }
        )
        self.organization_value = tk.StringVar(
            value="No organization selected"
        )
        self.assignment_status_value = tk.StringVar(
            value="Choose an organization and job."
        )
        self.salary_galleons_value = tk.StringVar(
            value=str(existing_salary["galleons"])
        )
        self.salary_sickles_value = tk.StringVar(
            value=str(existing_salary["sickles"])
        )
        self.salary_knuts_value = tk.StringVar(
            value=str(existing_salary["knuts"])
        )
        self.start_year_value = tk.StringVar(
            value=(
                str(self.existing_record["start_year"])
                if self.existing_record is not None
                else (
                    ""
                    if default_start_year in (None, "")
                    else str(default_start_year)
                )
            )
        )
        self.start_month_value = tk.StringVar(
            value=(
                str(self.existing_record["start_month"])
                if (
                    self.existing_record is not None
                    and self.existing_record["start_month"]
                    is not None
                )
                else (
                    ""
                    if default_start_month in (None, "")
                    else str(default_start_month)
                )
            )
        )
        self.start_day_value = tk.StringVar(
            value=(
                str(self.existing_record["start_day"])
                if (
                    self.existing_record is not None
                    and self.existing_record["start_day"]
                    is not None
                )
                else (
                    ""
                    if default_start_day in (None, "")
                    else str(default_start_day)
                )
            )
        )
        self.end_year_value = tk.StringVar(
            value=(
                str(self.existing_record["end_year"])
                if (
                    self.existing_record is not None
                    and self.existing_record["end_year"]
                    is not None
                )
                else ""
            )
        )
        self.end_month_value = tk.StringVar(
            value=(
                str(self.existing_record["end_month"])
                if (
                    self.existing_record is not None
                    and self.existing_record["end_month"]
                    is not None
                )
                else ""
            )
        )
        self.end_day_value = tk.StringVar(
            value=(
                str(self.existing_record["end_day"])
                if (
                    self.existing_record is not None
                    and self.existing_record["end_day"]
                    is not None
                )
                else ""
            )
        )
        self.title(
            "Edit job assignment"
            if self.existing_record is not None
            else "Add job"
        )
        self.configure(bg=APP_BACKGROUND)
        self.geometry("760x740")
        self.minsize(680, 660)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()

        for date_value in (
            self.start_year_value,
            self.start_month_value,
            self.start_day_value,
            self.end_year_value,
            self.end_month_value,
            self.end_day_value,
        ):
            date_value.trace_add(
                "write",
                self.assignment_date_changed,
            )

        self.load_existing_selection()
        self.grab_set()

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=(
                "Edit job assignment"
                if self.existing_record is not None
                else "Add job"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)

        body = tk.Frame(
            self,
            bg=SURFACE,
            padx=20,
            pady=18,
        )
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(4, weight=1)
        body.grid_columnconfigure(0, weight=1)

        organization_label = tk.Label(
            body,
            text="Organization",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        organization_label.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        organization_row = tk.Frame(body, bg=SURFACE)
        organization_row.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 14),
        )
        organization_row.grid_columnconfigure(0, weight=1)
        organization_value = tk.Label(
            organization_row,
            textvariable=self.organization_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
            padx=10,
            pady=9,
            highlightbackground=PRIMARY,
            highlightthickness=1,
        )
        organization_value.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        choose_organization_button = SoftButton(
            organization_row,
            text="Choose organization",
            command=self.open_organization_selector,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=154,
            height=38,
        )
        choose_organization_button.grid(
            row=0,
            column=1,
            padx=(8, 0),
        )

        jobs_label = tk.Label(
            body,
            text="Organization jobs",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        jobs_label.grid(
            row=2,
            column=0,
            sticky="ew",
        )
        job_list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        job_list_frame.grid(
            row=3,
            column=0,
            sticky="nsew",
            pady=(5, 14),
        )
        job_list_frame.grid_rowconfigure(0, weight=1)
        job_list_frame.grid_columnconfigure(0, weight=1)
        self.job_list = tk.Listbox(
            job_list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            height=6,
        )
        self.job_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.job_list.bind(
            "<<ListboxSelect>>",
            self.job_selected,
        )
        job_scrollbar = tk.Scrollbar(
            job_list_frame,
            orient="vertical",
            command=self.job_list.yview,
        )
        job_scrollbar.grid(row=0, column=1, sticky="ns")
        self.job_list.configure(
            yscrollcommand=job_scrollbar.set
        )

        salary_panel = tk.Frame(body, bg=SURFACE)
        salary_panel.grid(
            row=5,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        salary_panel.grid_columnconfigure((0, 1, 2), weight=1)

        for column, label_text, value, maximum in (
            (0, "Monthly salary · Galleons", self.salary_galleons_value, ""),
            (1, "Sickles", self.salary_sickles_value, "16"),
            (2, "Knuts", self.salary_knuts_value, "28"),
        ):
            salary_block = tk.Frame(salary_panel, bg=SURFACE)
            salary_block.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 8) if column < 2 else 0,
            )
            salary_block.grid_columnconfigure(0, weight=1)
            salary_label = tk.Label(
                salary_block,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            salary_label.grid(row=0, column=0, sticky="ew")
            salary_entry = RoundedEntry(
                salary_block,
                textvariable=value,
                background=SURFACE,
                width=170,
                height=36,
                font=app_font(10),
                justify="center",
            )
            salary_entry.grid(
                row=1,
                column=0,
                sticky="ew",
                pady=(4, 0),
            )
            salary_entry.entry.configure(
                validate="key",
                validatecommand=(
                    self.register(currency_component_input_is_valid),
                    "%P",
                    maximum,
                ),
            )

        dates_frame = tk.Frame(body, bg=SURFACE)
        dates_frame.grid(
            row=6,
            column=0,
            sticky="ew",
        )
        dates_frame.grid_columnconfigure((0, 1), weight=1)
        self.build_date_row(
            dates_frame,
            0,
            "Start date",
            self.start_year_value,
            self.start_month_value,
            self.start_day_value,
        )
        self.build_date_row(
            dates_frame,
            1,
            "End date (leave empty if ongoing)",
            self.end_year_value,
            self.end_month_value,
            self.end_day_value,
        )
        calendar_notice = CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=680,
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
        )
        calendar_notice.grid(
            row=7,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        status_label = tk.Label(
            body,
            textvariable=self.assignment_status_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        status_label.grid(
            row=8,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )

        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 16),
        )
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=92,
            height=36,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        self.save_button = SoftButton(
            footer,
            text=(
                "Save changes"
                if self.existing_record is not None
                else "Add job"
            ),
            command=self.save_record,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=36,
        )
        self.save_button.grid(row=0, column=2)
        self.save_button.set_enabled(False)

    def build_date_row(
        self,
        parent,
        row,
        heading,
        year_value,
        month_value,
        day_value,
    ):
        date_frame = tk.Frame(parent, bg=SURFACE)
        date_frame.grid(
            row=0,
            column=row,
            sticky="ew",
            padx=(0, 8) if row == 0 else (8, 0),
        )
        date_heading = tk.Label(
            date_frame,
            text=heading,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        date_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )

        for column, label_text, value, width in (
            (0, "Year", year_value, 110),
            (1, "Month", month_value, 82),
            (2, "Day", day_value, 82),
        ):
            date_block = tk.Frame(date_frame, bg=SURFACE)
            date_block.grid(
                row=1,
                column=column,
                sticky="w",
                padx=(0, 7),
            )
            label = tk.Label(
                date_block,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            label.grid(row=0, column=0, sticky="ew")
            entry = RoundedEntry(
                date_block,
                textvariable=value,
                background=SURFACE,
                width=width,
                height=36,
                font=app_font(10),
                justify="center",
            )
            entry.grid(
                row=1,
                column=0,
                sticky="w",
                pady=(4, 0),
            )

    def load_existing_selection(self):
        if self.existing_record is None:
            self.refresh_jobs()
            return

        organization_id = self.existing_record[
            "organization_id"
        ]
        self.selected_organization = next(
            (
                deepcopy(organization)
                for organization in self.organizations
                if str(
                    organization.get("record_id", "") or ""
                )
                == organization_id
            ),
            None,
        )

        if self.selected_organization is None:
            self.assignment_status_value.set(
                "The assigned organization no longer exists."
            )
            self.refresh_jobs()
            return

        self.organization_value.set(
            self.selected_organization_text()
        )
        selected_job_id = self.existing_record[
            "organization_job_id"
        ]
        self.selected_job = next(
            (
                deepcopy(organization_job)
                for organization_job in normalize_organization_jobs(
                    self.selected_organization.get("jobs", [])
                )
                if organization_job["record_id"]
                == selected_job_id
            ),
            None,
        )
        self.refresh_jobs()

    def selected_organization_text(self):
        if self.selected_organization is None:
            return "No organization selected"

        organization_name = str(
            self.selected_organization.get("name", "") or ""
        ).strip()
        organization_type = str(
            self.selected_organization.get(
                "organization_type",
                "",
            )
            or ""
        ).strip()
        return (
            f"{organization_name} · {organization_type}"
            if organization_type
            else organization_name
        )

    def open_organization_selector(self):
        OrganizationSelectionDialog(
            self,
            self.organizations,
            self.organization_selected,
            self.organization_create_command,
            self.organization_location_provider,
        )

    def organization_selected(self, organization):
        self.selected_organization = deepcopy(organization)
        selected_id = str(
            organization.get("record_id", "") or ""
        )

        if not any(
            str(stored.get("record_id", "") or "") == selected_id
            for stored in self.organizations
        ):
            self.organizations.append(deepcopy(organization))

        self.organization_value.set(
            self.selected_organization_text()
        )
        self.selected_job = None
        self.refresh_jobs()

        if len(self.visible_jobs) == 1:
            self.job_list.selection_set(0)
            self.job_selected()

    def assignment_date_changed(self, *arguments):
        self.refresh_jobs()

    def refresh_jobs(self):
        selected_job_id = (
            str(self.selected_job.get("record_id", "") or "")
            if self.selected_job is not None
            else ""
        )
        self.visible_jobs = (
            normalize_organization_jobs(
                self.selected_organization.get("jobs", [])
            )
            if self.selected_organization is not None
            else []
        )
        self.job_list.delete(0, "end")
        selected_index = None

        for index, organization_job in enumerate(
            self.visible_jobs
        ):
            available, status = self.position_availability(
                organization_job
            )
            self.job_list.insert(
                "end",
                (
                    f"{organization_job['title']} · "
                    f"opened {organization_job['opened_date']} · "
                    f"{status}"
                ),
            )
            self.job_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if (
                organization_job["record_id"]
                == selected_job_id
            ):
                selected_index = index

        if selected_index is not None:
            self.job_list.selection_set(selected_index)
            self.selected_job = deepcopy(
                self.visible_jobs[selected_index]
            )

        if self.selected_organization is None:
            self.assignment_status_value.set(
                "Choose an organization."
            )
        elif not self.visible_jobs:
            self.assignment_status_value.set(
                "This organization has no jobs to assign."
            )
        elif self.selected_job is None:
            self.assignment_status_value.set(
                "Choose an organization job."
            )
        else:
            available, status = self.position_availability(
                self.selected_job
            )
            self.assignment_status_value.set(status)

        self.update_save_state()

    def job_selected(self, event=None):
        selected = self.job_list.curselection()

        if not selected:
            self.selected_job = None
            self.update_save_state()
            return

        self.selected_job = deepcopy(
            self.visible_jobs[int(selected[0])]
        )
        available, status = self.position_availability(
            self.selected_job
        )
        self.assignment_status_value.set(status)
        self.update_save_state()

    def candidate_record(self, organization_job):
        if self.selected_organization is None:
            raise ValueError("Choose an organization.")

        candidate = new_job_record(
            str(
                self.selected_organization.get(
                    "record_id",
                    "",
                )
                or ""
            ),
            str(
                self.selected_organization.get("name", "")
                or ""
            ),
            organization_job["title"],
            {
                "galleons": self.salary_galleons_value.get(),
                "sickles": self.salary_sickles_value.get(),
                "knuts": self.salary_knuts_value.get(),
            },
            self.start_year_value.get(),
            self.start_month_value.get(),
            self.start_day_value.get(),
            self.end_year_value.get(),
            self.end_month_value.get(),
            self.end_day_value.get(),
            organization_job["record_id"],
        )

        if self.existing_record is not None:
            candidate["record_id"] = self.existing_record[
                "record_id"
            ]
            candidate = normalize_job_record(candidate)

        return candidate

    def position_availability(self, organization_job):
        try:
            candidate = self.candidate_record(
                organization_job
            )
            require_job_position_available(
                organization_job,
                candidate,
                self.assignments,
                (
                    self.existing_record["record_id"]
                    if self.existing_record is not None
                    else ""
                ),
            )
        except (TypeError, ValueError) as error:
            return False, str(error)

        return True, "Open for the selected dates"

    def update_save_state(self):
        if self.selected_job is None:
            self.save_button.set_enabled(False)
            return

        available, status = self.position_availability(
            self.selected_job
        )
        self.save_button.set_enabled(available)

        if not available:
            self.assignment_status_value.set(status)

    def save_record(self):
        if self.selected_job is None:
            return

        try:
            record = self.candidate_record(self.selected_job)
            record = require_job_position_available(
                self.selected_job,
                record,
                self.assignments,
                (
                    self.existing_record["record_id"]
                    if self.existing_record is not None
                    else ""
                ),
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save job assignment",
                str(error),
                parent=self,
            )
            return

        self.save_command(record)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
