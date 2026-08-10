import tkinter as tk
from copy import deepcopy
from functools import partial
from tkinter import messagebox

from mage_maker.sections.development.models import (
    DEVELOPMENT_SKILL_OPTIONS,
    EMINENCE_DEFAULT_TITLE,
    new_eminence_record,
    new_job_record,
    normalize_development_skill,
    normalize_eminence_record,
    normalize_eminence_records,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    FIELD_BACKGROUND,
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
    RoundedEntry,
    RoundedSelect,
    RoundedText,
    SoftButton,
)


class EminenceDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        save_command,
        default_skill=None,
        default_title=None,
        existing_record=None,
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.existing_record = (
            normalize_eminence_record(existing_record)
            if isinstance(existing_record, dict)
            else None
        )
        try:
            selected_skill = normalize_development_skill(
                (
                    self.existing_record["skill"]
                    if self.existing_record is not None
                    else default_skill
                )
            )
        except ValueError:
            selected_skill = DEVELOPMENT_SKILL_OPTIONS[0]
        self.title_value = tk.StringVar(
            value=(
                self.existing_record["title"]
                if self.existing_record is not None
                else
                str(default_title or "").strip()
                or (
                    f"{selected_skill} eminence earned"
                    if default_skill not in (None, "")
                    else EMINENCE_DEFAULT_TITLE
                )
            )
        )
        self.skill_value = tk.StringVar(
            value=selected_skill
        )
        self.title(
            "Edit eminence"
            if self.existing_record is not None
            else "Add eminence"
        )
        self.configure(bg=APP_BACKGROUND)
        self.geometry("620x455")
        self.minsize(560, 410)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()

        if self.existing_record is not None:
            self.description_control.text.insert(
                "1.0",
                self.existing_record["description"],
            )

        self.grab_set()
        self.after_idle(self.focus_title)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=(
                "Edit eminence"
                if self.existing_record is not None
                else "Add eminence"
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
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)

        title_label = tk.Label(
            body,
            text="Title",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew")
        self.title_entry = RoundedEntry(
            body,
            textvariable=self.title_value,
            background=SURFACE,
            width=420,
            height=38,
            font=app_font(10),
        )
        self.title_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 12),
        )

        skill_label = tk.Label(
            body,
            text="Skill",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        skill_label.grid(row=0, column=1, sticky="ew", padx=(14, 0))
        self.skill_select = RoundedSelect(
            body,
            self.skill_value,
            DEVELOPMENT_SKILL_OPTIONS,
            background=SURFACE,
            width=180,
            height=38,
            font=app_font(10),
        )
        self.skill_select.grid(
            row=1,
            column=1,
            sticky="e",
            padx=(14, 0),
            pady=(5, 12),
        )

        description_label = tk.Label(
            body,
            text="Description",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        description_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.description_control = RoundedText(
            body,
            background=SURFACE,
            height=9,
        )
        self.description_control.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
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
        save_button = SoftButton(
            footer,
            text=(
                "Save changes"
                if self.existing_record is not None
                else "Add eminence"
            ),
            command=self.save_record,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=36,
        )
        save_button.grid(row=0, column=2)

    def focus_title(self):
        self.title_entry.entry.focus_set()
        self.title_entry.entry.selection_range(0, "end")

    def close_dialog(self, event=None):
        self.destroy()

    def save_record(self):
        try:
            record = new_eminence_record(
                self.title_value.get(),
                self.description_control.text.get(
                    "1.0",
                    "end-1c",
                ),
                self.skill_value.get(),
            )

            if self.existing_record is not None:
                record["record_id"] = self.existing_record[
                    "record_id"
                ]
                record = normalize_eminence_record(record)
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add eminence",
                str(error),
                parent=self,
            )
            return

        self.save_command(record)
        self.destroy()


class EminenceManagerDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        records,
        default_skill,
        save_command,
    ):
        super().__init__(parent)
        self.records = normalize_eminence_records(records)
        self.default_skill = default_skill
        self.save_command = save_command
        self.count_value = tk.StringVar()
        self.title("Manage eminence")
        self.configure(bg=APP_BACKGROUND)
        self.geometry("720x510")
        self.minsize(620, 430)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.refresh_records()
        self.grab_set()

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Eminence records",
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
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        count_label = tk.Label(
            body,
            textvariable=self.count_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        count_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=PRIMARY,
            highlightthickness=1,
        )
        list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.record_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=PRIMARY,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.record_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.record_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.record_list.configure(
            yscrollcommand=scrollbar.set
        )
        self.record_list.bind(
            "<Double-Button-1>",
            self.edit_selected_record,
        )
        action_row = tk.Frame(body, bg=SURFACE)
        action_row.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )
        action_row.grid_columnconfigure(5, weight=1)
        add_button = SoftButton(
            action_row,
            text="Add eminence",
            command=self.add_record,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=34,
        )
        add_button.grid(row=0, column=0)
        edit_button = SoftButton(
            action_row,
            text="Edit",
            command=self.edit_selected_record,
            background=SURFACE,
            width=74,
            height=34,
        )
        edit_button.grid(
            row=0,
            column=1,
            padx=(7, 0),
        )
        move_up_button = SoftButton(
            action_row,
            text="↑ Up",
            command=self.move_selected_record_up,
            background=SURFACE,
            width=64,
            height=34,
        )
        move_up_button.grid(
            row=0,
            column=2,
            padx=(7, 0),
        )
        move_down_button = SoftButton(
            action_row,
            text="↓ Down",
            command=self.move_selected_record_down,
            background=SURFACE,
            width=76,
            height=34,
        )
        move_down_button.grid(
            row=0,
            column=3,
            padx=(7, 0),
        )
        remove_button = SoftButton(
            action_row,
            text="Remove",
            command=self.remove_selected_record,
            background=SURFACE,
            width=82,
            height=34,
        )
        remove_button.grid(
            row=0,
            column=4,
            padx=(7, 0),
        )
        cancel_button = SoftButton(
            action_row,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=88,
            height=34,
        )
        cancel_button.grid(
            row=0,
            column=6,
            padx=(7, 0),
        )
        save_button = SoftButton(
            action_row,
            text="Save",
            command=self.save_records,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=34,
        )
        save_button.grid(
            row=0,
            column=7,
            padx=(7, 0),
        )

    def refresh_records(self, selected_index=None):
        self.record_list.delete(0, "end")
        self.record_index_by_list_row = []

        for record_index, record in enumerate(self.records):
            self.record_list.insert(
                "end",
                f"{record['title']} ({record['skill']})",
            )
            self.record_index_by_list_row.append(record_index)

            for description_line in record["description"].splitlines():
                self.record_list.insert(
                    "end",
                    f"    {description_line}",
                )
                self.record_index_by_list_row.append(record_index)

        point_count = len(self.records)
        self.count_value.set(
            f"{point_count} eminence point"
            if point_count == 1
            else f"{point_count} eminence points"
        )

        if selected_index is not None and self.records:
            selected_record_index = max(
                0,
                min(int(selected_index), len(self.records) - 1),
            )
            selected_row = self.record_index_by_list_row.index(
                selected_record_index
            )
            self.record_list.selection_set(selected_row)
            self.record_list.see(selected_row)

    def selected_record_index(self):
        selected = self.record_list.curselection()

        if not selected:
            return None

        selected_row = int(selected[0])

        if not 0 <= selected_row < len(
            self.record_index_by_list_row
        ):
            return None

        return self.record_index_by_list_row[selected_row]

    def add_record(self):
        EminenceDialog(
            self,
            self.append_record,
            default_skill=self.default_skill,
        )

    def append_record(self, record):
        self.records = normalize_eminence_records(
            [*self.records, record]
        )
        self.refresh_records(len(self.records) - 1)

    def edit_selected_record(self, event=None):
        selected_index = self.selected_record_index()

        if selected_index is None:
            return

        EminenceDialog(
            self,
            partial(self.replace_record, selected_index),
            existing_record=self.records[selected_index],
        )

    def replace_record(self, selected_index, record):
        updated_records = deepcopy(self.records)
        updated_records[int(selected_index)] = record
        self.records = normalize_eminence_records(
            updated_records
        )
        self.refresh_records(selected_index)

    def move_selected_record_up(self):
        selected_index = self.selected_record_index()

        if selected_index is None or selected_index <= 0:
            return

        self.records[selected_index - 1], self.records[
            selected_index
        ] = (
            self.records[selected_index],
            self.records[selected_index - 1],
        )
        self.refresh_records(selected_index - 1)

    def move_selected_record_down(self):
        selected_index = self.selected_record_index()

        if (
            selected_index is None
            or selected_index >= len(self.records) - 1
        ):
            return

        self.records[selected_index + 1], self.records[
            selected_index
        ] = (
            self.records[selected_index],
            self.records[selected_index + 1],
        )
        self.refresh_records(selected_index + 1)

    def remove_selected_record(self):
        selected_index = self.selected_record_index()

        if selected_index is None:
            return

        self.records = [
            record
            for index, record in enumerate(self.records)
            if index != selected_index
        ]
        self.refresh_records(selected_index)

    def save_records(self):
        self.save_command(
            normalize_eminence_records(self.records)
        )
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class JobDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        organizations,
        default_start_year,
        save_command,
        organization_create_command=None,
        organization_location_provider=None,
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.organization_create_command = organization_create_command
        self.organization_location_provider = (
            organization_location_provider
        )
        self.organizations = [
            organization
            for organization in organizations or []
            if isinstance(organization, dict)
            and str(organization.get("name", "") or "").strip()
        ]
        self.selected_organization = None
        self.organization_value = tk.StringVar(
            value=self.selected_organization_text()
        )
        self.title_value = tk.StringVar()
        self.salary_value = tk.StringVar()
        self.start_year_value = tk.StringVar(
            value=(
                ""
                if default_start_year in (None, "")
                else str(default_start_year)
            )
        )
        self.start_month_value = tk.StringVar()
        self.start_day_value = tk.StringVar()
        self.title("Add job")
        self.configure(bg=APP_BACKGROUND)
        self.geometry("690x520")
        self.minsize(620, 470)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.grab_set()
        self.after_idle(self.focus_title)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Add job",
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
        body.grid_columnconfigure((0, 1), weight=1)

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
            columnspan=2,
            sticky="ew",
        )
        organization_row = tk.Frame(
            body,
            bg=SURFACE,
        )
        organization_row.grid(
            row=1,
            column=0,
            columnspan=2,
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

        title_label = tk.Label(
            body,
            text="Title",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        title_label.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        self.title_entry = RoundedEntry(
            body,
            textvariable=self.title_value,
            background=SURFACE,
            width=250,
            height=38,
            font=app_font(10),
        )
        self.title_entry.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(5, 14),
        )

        salary_label = tk.Label(
            body,
            text="Salary",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        salary_label.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        salary_entry = RoundedEntry(
            body,
            textvariable=self.salary_value,
            background=SURFACE,
            width=300,
            height=38,
            font=app_font(10),
        )
        salary_entry.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(5, 14),
        )

        date_label = tk.Label(
            body,
            text="Start date",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        date_label.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        date_row = tk.Frame(body, bg=SURFACE)
        date_row.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(5, 0),
        )

        for column, label_text, value, width in (
            (0, "Year", self.start_year_value, 120),
            (1, "Month", self.start_month_value, 92),
            (2, "Day", self.start_day_value, 92),
        ):
            date_block = tk.Frame(date_row, bg=SURFACE)
            date_block.grid(
                row=0,
                column=column,
                sticky="w",
                padx=(0, 9),
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
            entry.grid(row=1, column=0, sticky="w", pady=(4, 0))

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
            text="Add job",
            command=self.save_record,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        self.save_button.grid(row=0, column=2)
        self.save_button.set_enabled(
            self.selected_organization is not None
        )

        if not self.organizations:
            warning = tk.Label(
                body,
                text=(
                    "No organization is selected. Use Choose organization "
                    "to search or create one."
                ),
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(10),
                anchor="w",
            )
            warning.grid(
                row=8,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(16, 0),
            )

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
        self.save_button.set_enabled(True)

    def focus_title(self):
        self.title_entry.entry.focus_set()

    def close_dialog(self, event=None):
        self.destroy()

    def save_record(self):
        if self.selected_organization is None:
            return

        organization_name = str(
            self.selected_organization.get("name", "") or ""
        ).strip()
        organization_id = str(
            self.selected_organization.get("record_id", "") or ""
        ).strip()

        try:
            record = new_job_record(
                organization_id,
                organization_name,
                self.title_value.get(),
                self.salary_value.get(),
                self.start_year_value.get(),
                self.start_month_value.get(),
                self.start_day_value.get(),
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add job",
                str(error),
                parent=self,
            )
            return

        self.save_command(record)
        self.destroy()


from mage_maker.sections.development.position_assignment_dialog import (
    PositionAssignmentDialog,
)


JobDialog = PositionAssignmentDialog
