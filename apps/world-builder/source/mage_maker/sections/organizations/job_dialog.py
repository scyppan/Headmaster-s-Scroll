import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.events.models import split_world_event_date
from mage_maker.sections.organizations.controller import (
    new_organization_job,
    normalize_organization_job,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
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


class OrganizationJobDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        save_command,
        existing_job=None,
        default_opened_year=None,
        default_opened_month=None,
        default_opened_day=None,
        organization_extinct=False,
        organization_extinction_date="",
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.existing_job = (
            normalize_organization_job(existing_job)
            if isinstance(existing_job, dict)
            else None
        )
        self.organization_extinct = bool(organization_extinct)
        opened_date = (
            self.existing_job["opened_date"]
            if self.existing_job is not None
            else self.default_date_text(
                default_opened_year,
                default_opened_month,
                default_opened_day,
            )
        )
        closed_date = (
            self.existing_job["closed_date"]
            if self.existing_job is not None
            else ""
        )

        if self.organization_extinct and not closed_date:
            closed_date = str(
                organization_extinction_date or ""
            ).strip()

        opened_year, opened_month, opened_day = (
            split_world_event_date(opened_date)
        )
        closed_year, closed_month, closed_day = (
            split_world_event_date(closed_date)
        )
        self.title_value = tk.StringVar(
            value=(
                self.existing_job["title"]
                if self.existing_job is not None
                else ""
            )
        )
        self.level_value = tk.StringVar(
            value=(
                str(self.existing_job["level"])
                if self.existing_job is not None
                else "0"
            )
        )
        self.opened_year_value = tk.StringVar(value=opened_year)
        self.opened_month_value = tk.StringVar(value=opened_month)
        self.opened_day_value = tk.StringVar(value=opened_day)
        self.closed_year_value = tk.StringVar(value=closed_year)
        self.closed_month_value = tk.StringVar(value=closed_month)
        self.closed_day_value = tk.StringVar(value=closed_day)
        self.opened_entries = []
        self.closed_entries = []
        self.title(
            "Edit organization job"
            if self.existing_job is not None
            else "Add organization job"
        )
        self.configure(bg=APP_BACKGROUND)
        self.geometry("760x440")
        self.minsize(680, 420)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.bind("<Escape>", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.update_closed_date_state()
        self.update_idletasks()
        self.position_upper_right()
        self.grab_set()
        self.after_idle(self.focus_title)

    def default_date_text(self, year, month, day):
        if year in (None, ""):
            return ""

        value = str(year).strip()

        if month not in (None, ""):
            value += f"-{month}"

        if day not in (None, ""):
            value += f"-{day}"

        return value

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=(
                "Edit organization job"
                if self.existing_job is not None
                else "Add organization job"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)

        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=4)
        level_label = tk.Label(
            body,
            text="Level",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        level_label.grid(row=0, column=0, sticky="ew")
        self.level_entry = RoundedEntry(
            body,
            textvariable=self.level_value,
            background=SURFACE,
            width=82,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.level_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 10),
            pady=(5, 14),
        )
        title_label = tk.Label(
            body,
            text="Title",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=1, sticky="ew")
        self.title_entry = RoundedEntry(
            body,
            textvariable=self.title_value,
            background=SURFACE,
            width=500,
            height=38,
            font=app_font(10),
        )
        self.title_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            pady=(5, 14),
        )
        dates_row = tk.Frame(body, bg=SURFACE)
        dates_row.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        dates_row.grid_columnconfigure((0, 1), weight=1)
        self.opened_entries = self.build_date_panel(
            dates_row,
            0,
            "Position opened",
            (
                self.opened_year_value,
                self.opened_month_value,
                self.opened_day_value,
            ),
        )
        self.closed_entries = self.build_date_panel(
            dates_row,
            1,
            "Position closed",
            (
                self.closed_year_value,
                self.closed_month_value,
                self.closed_day_value,
            ),
        )
        self.extinction_note = tk.Label(
            body,
            text=(
                "This date is controlled by the organization's "
                "extinction date."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        self.extinction_note.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 4),
        )
        self.calendar_notice = CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=620,
            date_variables=(
                (
                    self.opened_year_value,
                    self.opened_month_value,
                    self.opened_day_value,
                ),
                (
                    self.closed_year_value,
                    self.closed_month_value,
                    self.closed_day_value,
                ),
            ),
        )
        self.calendar_notice.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(4, 0),
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
                if self.existing_job is not None
                else "Add job"
            ),
            command=self.save_job,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=36,
        )
        save_button.grid(row=0, column=2)

    def build_date_panel(self, parent, column, heading_text, variables):
        panel = tk.Frame(parent, bg=SURFACE)
        panel.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 8) if column == 0 else (8, 0),
            pady=(0, 12),
        )
        panel.grid_columnconfigure((0, 1, 2), weight=1)
        heading = tk.Label(
            panel,
            text=heading_text,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        entries = []

        for column, label_text, variable in (
            (0, "Year", variables[0]),
            (1, "Month", variables[1]),
            (2, "Day", variables[2]),
        ):
            field = tk.Frame(panel, bg=SURFACE)
            field.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0, 6) if column < 2 else 0,
            )
            field.grid_columnconfigure(0, weight=1)
            label = tk.Label(
                field,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            label.grid(row=0, column=0, sticky="ew")
            entry = RoundedEntry(
                field,
                textvariable=variable,
                background=SURFACE,
                height=36,
                font=app_font(10),
                justify="center",
            )
            entry.grid(row=1, column=0, sticky="ew", pady=(3, 0))
            entries.append(entry)

        return entries

    def update_closed_date_state(self):
        for entry in self.closed_entries:
            entry.set_enabled(not self.organization_extinct)

        if self.organization_extinct:
            self.extinction_note.grid()
        else:
            self.extinction_note.grid_remove()

    def position_upper_right(self):
        owner = self.master.winfo_toplevel()
        dialog_width = max(680, self.winfo_width())
        dialog_height = max(420, self.winfo_height())
        owner_left = owner.winfo_rootx()
        owner_top = owner.winfo_rooty()
        owner_width = max(owner.winfo_width(), dialog_width + 48)
        x_position = owner_left + owner_width - dialog_width - 24
        y_position = owner_top + 72
        self.geometry(
            f"{dialog_width}x{dialog_height}+{x_position}+{y_position}"
        )
        self.lift()

    def focus_title(self):
        self.title_entry.entry.focus_set()
        self.title_entry.entry.selection_range(0, "end")

    def save_job(self):
        try:
            job = new_organization_job(
                self.title_value.get(),
                self.opened_year_value.get(),
                self.opened_month_value.get(),
                self.opened_day_value.get(),
                self.closed_year_value.get(),
                self.closed_month_value.get(),
                self.closed_day_value.get(),
                level=self.level_value.get(),
            )

            if self.existing_job is not None:
                job["record_id"] = self.existing_job["record_id"]
                job = normalize_organization_job(job)
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save organization job",
                str(error),
                parent=self,
            )
            return

        if self.save_command(job) is not False:
            self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
