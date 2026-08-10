import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.dates import (
    historical_year_shift,
    next_historical_date,
)
from mage_maker.core.wizarding_currency import format_monthly_salary
from mage_maker.sections.development.models import (
    development_job_assignments,
    job_date_tuple,
    non_magical_development_plan,
    normalize_job_records,
)
from mage_maker.sections.development.position_assignment_dialog import (
    PositionAssignmentDialog,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SoftButton


class NonMagicalJobsView(tk.Frame):
    def __init__(
        self,
        parent,
        change_command,
        people_provider=None,
        organization_provider=None,
        organization_create_command=None,
        organization_location_provider=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.change_command = change_command
        self.people_provider = people_provider
        self.organization_provider = organization_provider
        self.organization_create_command = organization_create_command
        self.organization_location_provider = organization_location_provider
        self.person = {}
        self.development_plan = non_magical_development_plan(None)
        self.assignments = []
        self.visible_assignments = []
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_heading()
        self.build_assignment_list()
        self.build_controls()

    def build_heading(self):
        heading = tk.Label(
            self,
            text="Wizarding jobs",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            self,
            text=(
                "Non-magical people can hold wizarding-world jobs. They do not "
                "receive Development years, Eminence, wizarding reading, or a Ledger."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))

    def build_assignment_list(self):
        list_frame = tk.Frame(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.assignment_list = tk.Listbox(
            list_frame,
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
        )
        self.assignment_list.grid(row=0, column=0, sticky="nsew")
        self.assignment_list.bind(
            "<<ListboxSelect>>",
            self.selection_changed,
        )
        self.assignment_list.bind(
            "<Double-Button-1>",
            self.edit_selected_job,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.assignment_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.assignment_list.configure(yscrollcommand=scrollbar.set)

    def build_controls(self):
        footer = tk.Frame(self, bg=SURFACE)
        footer.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        self.summary_value = tk.StringVar(value="No jobs recorded")
        summary = tk.Label(
            footer,
            textvariable=self.summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        summary.pack(side="left", fill="x", expand=True)
        self.remove_button = SoftButton(
            footer,
            text="Remove",
            command=self.remove_selected_job,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=36,
        )
        self.remove_button.pack(side="right")
        self.edit_button = SoftButton(
            footer,
            text="Edit",
            command=self.edit_selected_job,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=84,
            height=36,
        )
        self.edit_button.pack(side="right", padx=(0, 6))
        self.add_button = SoftButton(
            footer,
            text="Add job",
            command=self.open_add_job,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=96,
            height=36,
        )
        self.add_button.pack(side="right", padx=(0, 6))
        self.edit_button.set_enabled(False)
        self.remove_button.set_enabled(False)

    def set_person(self, person):
        self.person = deepcopy(person) if isinstance(person, dict) else {}
        self.development_plan = non_magical_development_plan(
            self.person.get("development_plan")
        )
        self.assignments = development_job_assignments(
            self.development_plan
        )
        self.refresh_assignments()

    def get_development_plan(self):
        return non_magical_development_plan(
            self.development_plan,
            self.assignments,
        )

    def refresh_assignments(self, selected_record_id=""):
        retained_id = str(selected_record_id or "").strip()

        if not retained_id:
            selected = self.selected_assignment()
            retained_id = str(
                (selected or {}).get("record_id", "") or ""
            ).strip()

        self.visible_assignments = sorted(
            normalize_job_records(self.assignments),
            key=lambda assignment: (
                assignment["start_year"],
                assignment["start_month"] or 1,
                assignment["start_day"] or 1,
                assignment["organization_name"].casefold(),
                assignment["title"].casefold(),
            ),
        )
        self.assignment_list.delete(0, "end")
        retained_index = None

        for index, assignment in enumerate(self.visible_assignments):
            self.assignment_list.insert(
                "end",
                self.assignment_label(assignment),
            )
            self.assignment_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if assignment["record_id"] == retained_id:
                retained_index = index

        if retained_index is not None:
            self.assignment_list.selection_set(retained_index)
            self.assignment_list.see(retained_index)

        count = len(self.visible_assignments)
        self.summary_value.set(
            "No jobs recorded"
            if count == 0
            else "1 job recorded"
            if count == 1
            else f"{count} jobs recorded"
        )
        self.selection_changed()

    def assignment_label(self, assignment):
        start_date = self.job_date_label(assignment, "start")
        end_date = self.job_date_label(assignment, "end")
        date_range = (
            f"{start_date} to {end_date}"
            if end_date
            else f"{start_date} onward"
        )
        return (
            f"{assignment['organization_name']} — {assignment['title']}  ·  "
            f"{date_range}  ·  {format_monthly_salary(assignment['salary'])}"
        )

    def job_date_label(self, assignment, prefix):
        year = assignment.get(f"{prefix}_year")

        if year in (None, ""):
            return ""

        month = assignment.get(f"{prefix}_month")
        day = assignment.get(f"{prefix}_day")
        date_text = str(year)

        if month is not None:
            date_text += f"-{int(month):02d}"

        if day is not None:
            date_text += f"-{int(day):02d}"

        return date_text

    def selected_assignment(self):
        selected = self.assignment_list.curselection()

        if not selected or selected[0] >= len(self.visible_assignments):
            return None

        return self.visible_assignments[selected[0]]

    def selection_changed(self, event=None):
        has_selection = self.selected_assignment() is not None
        self.edit_button.set_enabled(has_selection)
        self.remove_button.set_enabled(has_selection)

    def available_organizations(self):
        if self.organization_provider is None:
            return []

        organizations = self.organization_provider()
        return list(organizations) if organizations is not None else []

    def all_job_assignments(self):
        current_person_id = str(
            self.person.get("record_id", "") or ""
        ).strip()
        assignments = list(self.assignments)

        for person in (
            self.people_provider()
            if self.people_provider is not None
            else []
        ):
            if not isinstance(person, dict):
                continue

            if str(person.get("record_id", "") or "").strip() == current_person_id:
                continue

            assignments.extend(
                development_job_assignments(
                    person.get("development_plan")
                )
            )

        return normalize_job_records(assignments)

    def suggested_start_date(self):
        latest_end_date = None

        for assignment in normalize_job_records(self.assignments):
            if assignment["end_year"] is None:
                continue

            end_date = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )

            if latest_end_date is None or end_date > latest_end_date:
                latest_end_date = end_date

        if latest_end_date is not None:
            return next_historical_date(*latest_end_date)

        birth_year = self.person.get("birth_year")

        if birth_year in (None, "") or isinstance(birth_year, bool):
            return None

        try:
            return historical_year_shift(int(birth_year), 18), None, None
        except (TypeError, ValueError):
            return None

    def open_add_job(self):
        suggested_date = self.suggested_start_date()
        PositionAssignmentDialog(
            self,
            self.available_organizations(),
            suggested_date[0] if suggested_date is not None else None,
            self.save_job,
            self.organization_create_command,
            self.organization_location_provider,
            self.all_job_assignments(),
            default_start_month=(
                suggested_date[1]
                if suggested_date is not None
                else None
            ),
            default_start_day=(
                suggested_date[2]
                if suggested_date is not None
                else None
            ),
        )

    def edit_selected_job(self, event=None):
        selected = self.selected_assignment()

        if selected is None:
            return

        PositionAssignmentDialog(
            self,
            self.available_organizations(),
            selected["start_year"],
            self.save_job,
            self.organization_create_command,
            self.organization_location_provider,
            self.all_job_assignments(),
            selected,
        )

    def save_job(self, assignment):
        normalized_assignment = normalize_job_records([assignment])[0]
        updated_assignments = []
        replaced = False

        for existing_assignment in normalize_job_records(self.assignments):
            if existing_assignment["record_id"] == normalized_assignment["record_id"]:
                updated_assignments.append(normalized_assignment)
                replaced = True
            else:
                updated_assignments.append(existing_assignment)

        if not replaced:
            updated_assignments.append(normalized_assignment)

        self.assignments = normalize_job_records(updated_assignments)
        self.development_plan = self.get_development_plan()
        self.refresh_assignments(normalized_assignment["record_id"])
        self.change_command()

    def remove_selected_job(self):
        selected = self.selected_assignment()

        if selected is None:
            return

        if not messagebox.askyesno(
            "Remove job",
            (
                f"Remove {selected['title']} at "
                f"{selected['organization_name']}?"
            ),
            parent=self,
        ):
            return

        self.assignments = [
            assignment
            for assignment in normalize_job_records(self.assignments)
            if assignment["record_id"] != selected["record_id"]
        ]
        self.development_plan = self.get_development_plan()
        self.refresh_assignments()
        self.change_command()
