import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, simpledialog, ttk
from uuid import uuid4

from mage_maker.core.autosave import DebouncedAutosave
from mage_maker.core.dates import (
    format_historical_display_date,
    format_line_item_date,
)
from mage_maker.core.wizarding_currency import (
    currency_component_input_is_valid,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationLocationSelectionDialog,
    OrganizationSelectionDialog,
)
from mage_maker.sections.events.models import (
    death_event_person_ids,
    split_world_event_date,
    world_event_sort_key,
)

from mage_maker.sections.organizations.controller import (
    ORGANIZATION_EVENT_FOUNDING,
    ORGANIZATION_TYPES,
    SHOP_STOCK_CATEGORIES,
    normalize_organization_extinction_date,
    normalize_organization_jobs,
    normalize_organization_events,
    normalize_shop_inventory,
    normalize_storeroom_inventory,
    new_organization_job,
    organization_context_label,
    organization_id_is_in_scope,
    organization_ids_in_scope,
)
from mage_maker.sections.organizations.event_dialog import (
    OrganizationEventDialog,
)
from mage_maker.sections.organizations.job_dialog import (
    OrganizationJobDialog,
)
from mage_maker.sections.organizations.appointment_dialog import (
    JobAppointmentDialog,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_HOVER,
    LIST_SELECTED,
    LOCKED_BORDER,
    LOCKED_RED,
    LOCKED_RED_HOVER,
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
    RoundedEntry,
    RoundedText,
    SoftButton,
)
from mage_maker.ui.colored_tags import ColoredTagsEditor


ORGANIZATION_TREE_ROOT_ID = "__mage_maker_organizations__"


class OrganizationSchoolSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        schools,
        selected_school_id,
        save_command,
        cancel_command=None,
    ):
        super().__init__(parent)
        self.schools = [
            deepcopy(school)
            for school in schools or []
            if isinstance(school, dict)
            and str(school.get("record_id", "") or "").strip()
        ]
        self.visible_schools = []
        self.selected_school_id = str(
            selected_school_id or ""
        ).strip()
        self.save_command = save_command
        self.cancel_command = cancel_command
        self.search_value = tk.StringVar()
        self.results_value = tk.StringVar()
        self.title("Link school")
        self.geometry("660x600")
        self.minsize(540, 480)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.grab_set()
        self.after_idle(self.search_control.focus_set)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Link school",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)
        explanation = tk.Label(
            body,
            text=(
                "Search school names, locations, descriptions, and "
                "curriculum. Linking controls the organization name."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=570,
        )
        explanation.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.search_control = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_control.grid(row=1, column=0, sticky="ew")
        results_label = tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        results_label.grid(row=2, column=0, sticky="ew", pady=(10, 5))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.school_list = tk.Listbox(
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
        self.school_list.grid(row=0, column=0, sticky="nsew")
        self.school_list.bind(
            "<Double-Button-1>",
            self.use_selected_school,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.school_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.school_list.configure(yscrollcommand=scrollbar.set)
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(
            row=2,
            column=0,
            sticky="e",
            padx=18,
            pady=(0, 16),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        self.use_button = SoftButton(
            footer,
            text="Link school",
            command=self.use_selected_school,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=36,
        )
        self.use_button.pack(side="left")

    def school_search_text(self, school):
        curriculum = school.get("curriculum", [])
        curriculum_text = " ".join(
            str(value or "")
            for value in (
                curriculum
                if isinstance(curriculum, (list, tuple))
                else [curriculum]
            )
        )
        return " ".join(
            str(value or "").strip()
            for value in (
                school.get("name"),
                school.get("location"),
                school.get("description"),
                curriculum_text,
            )
            if str(value or "").strip()
        ).casefold()

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().casefold().split()
            if term
        ]
        self.visible_schools = sorted(
            [
                school
                for school in self.schools
                if all(
                    term in self.school_search_text(school)
                    for term in query_terms
                )
            ],
            key=self.school_sort_key,
        )
        self.school_list.delete(0, "end")

        for index, school in enumerate(self.visible_schools):
            name = str(
                school.get("name", "") or "Unnamed school"
            ).strip()
            location = str(school.get("location", "") or "").strip()
            self.school_list.insert(
                "end",
                f"{name}  ·  {location}" if location else name,
            )
            self.school_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if school.get("record_id") == self.selected_school_id:
                self.school_list.selection_set(index)
                self.school_list.see(index)

        self.results_value.set(
            f"Schools ({len(self.visible_schools)})"
        )
        self.use_button.set_enabled(bool(self.visible_schools))

    def school_sort_key(self, school):
        return (
            str(school.get("name", "") or "").casefold(),
            str(school.get("location", "") or "").casefold(),
        )

    def use_selected_school(self, event=None):
        selected = self.school_list.curselection()

        if not selected:
            return

        self.save_command(
            deepcopy(self.visible_schools[int(selected[0])])
        )
        self.destroy()

    def close_dialog(self, event=None):
        if self.cancel_command is not None:
            self.cancel_command()

        self.destroy()
        return "break"


class VacantJobFillDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        people,
        organization,
        organization_job,
        vacancy,
        save_command,
    ):
        super().__init__(parent)
        self.people = [
            deepcopy(person)
            for person in people or []
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        ]
        self.organization = deepcopy(organization)
        self.organization_job = deepcopy(organization_job)
        self.vacancy = deepcopy(vacancy)
        self.save_command = save_command
        self.visible_people = []
        self.search_value = tk.StringVar()
        self.results_value = tk.StringVar()
        self.salary_galleons_value = tk.StringVar(value="0")
        self.salary_sickles_value = tk.StringVar(value="0")
        self.salary_knuts_value = tk.StringVar(value="0")
        self.start_year_value = tk.StringVar(
            value=str(vacancy.get("start_year", "") or "")
        )
        self.start_month_value = tk.StringVar(
            value=str(vacancy.get("start_month", "") or "")
        )
        self.start_day_value = tk.StringVar(
            value=str(vacancy.get("start_day", "") or "")
        )
        self.end_year_value = tk.StringVar(
            value=str(vacancy.get("end_year", "") or "")
        )
        self.end_month_value = tk.StringVar(
            value=str(vacancy.get("end_month", "") or "")
        )
        self.end_day_value = tk.StringVar(
            value=str(vacancy.get("end_day", "") or "")
        )
        self.title("Fill vacant position")
        self.geometry("760x700")
        self.minsize(680, 620)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_people)
        self.refresh_people()
        self.grab_set()
        self.after_idle(self.search_entry.entry.focus_set)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Fill vacant position",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)
        organization_name = str(
            self.organization.get("name", "")
            or "Unnamed organization"
        ).strip()
        job_title = str(
            self.organization_job.get("title", "")
            or "Unnamed position"
        ).strip()
        position_label = tk.Label(
            body,
            text=f"{job_title} at {organization_name}",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        position_label.grid(row=0, column=0, sticky="ew")
        self.search_entry = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            height=36,
            font=app_font(10),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )
        results_label = tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        results_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 4),
        )
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.people_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            height=8,
        )
        self.people_list.grid(row=0, column=0, sticky="nsew")
        self.people_list.bind(
            "<<ListboxSelect>>",
            self.person_selected,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.people_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.people_list.configure(yscrollcommand=scrollbar.set)
        salary_frame = tk.Frame(body, bg=SURFACE)
        salary_frame.grid(
            row=4,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )
        salary_frame.grid_columnconfigure((0, 1, 2), weight=1)

        for column, label_text, value, maximum in (
            (0, "Monthly salary · Galleons", self.salary_galleons_value, ""),
            (1, "Sickles", self.salary_sickles_value, "16"),
            (2, "Knuts", self.salary_knuts_value, "28"),
        ):
            salary_block = tk.Frame(salary_frame, bg=SURFACE)
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
                font=app_font(8, "bold"),
                anchor="w",
            )
            salary_label.grid(row=0, column=0, sticky="ew")
            salary_entry = RoundedEntry(
                salary_block,
                textvariable=value,
                background=SURFACE,
                height=34,
                font=app_font(9),
                justify="center",
            )
            salary_entry.grid(
                row=1,
                column=0,
                sticky="ew",
                pady=(3, 0),
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
            row=5,
            column=0,
            sticky="ew",
            pady=(12, 0),
        )
        dates_frame.grid_columnconfigure((0, 1), weight=1)
        self.build_date_fields(
            dates_frame,
            0,
            "Start date",
            self.start_year_value,
            self.start_month_value,
            self.start_day_value,
        )
        self.build_date_fields(
            dates_frame,
            1,
            "End date",
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
            row=6,
            column=0,
            sticky="w",
            pady=(7, 0),
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
            width=88,
            height=36,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        self.fill_button = SoftButton(
            footer,
            text="Fill position",
            command=self.fill_position,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=118,
            height=36,
        )
        self.fill_button.grid(row=0, column=2)
        self.fill_button.set_enabled(False)

    def build_date_fields(
        self,
        parent,
        column,
        heading,
        year_value,
        month_value,
        day_value,
    ):
        date_panel = tk.Frame(parent, bg=SURFACE)
        date_panel.grid(
            row=0,
            column=column,
            sticky="ew",
            padx=(0, 8) if column == 0 else (8, 0),
        )
        date_panel.grid_columnconfigure((0, 1, 2), weight=1)
        date_heading = tk.Label(
            date_panel,
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
        )

        for field_column, label_text, value in (
            (0, "Year", year_value),
            (1, "Month", month_value),
            (2, "Day", day_value),
        ):
            field = tk.Frame(date_panel, bg=SURFACE)
            field.grid(
                row=1,
                column=field_column,
                sticky="ew",
                padx=(0, 5) if field_column < 2 else 0,
                pady=(4, 0),
            )
            field.grid_columnconfigure(0, weight=1)
            label = tk.Label(
                field,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(7, "bold"),
                anchor="w",
            )
            label.grid(row=0, column=0, sticky="ew")
            entry = RoundedEntry(
                field,
                textvariable=value,
                background=SURFACE,
                height=32,
                font=app_font(9),
                justify="center",
            )
            entry.grid(row=1, column=0, sticky="ew", pady=(2, 0))

    def refresh_people(self, *arguments):
        query = self.search_value.get().strip().casefold()
        self.visible_people = sorted(
            [
                person
                for person in self.people
                if query
                in str(
                    person.get("displayed_name", "") or ""
                ).casefold()
            ],
            key=self.person_sort_key,
        )
        self.people_list.delete(0, "end")

        for index, person in enumerate(self.visible_people):
            self.people_list.insert(
                "end",
                str(
                    person.get("displayed_name", "")
                    or "Unnamed magician"
                ),
            )
            self.people_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.results_value.set(
            f"People ({len(self.visible_people)})"
        )
        self.person_selected()

    def person_sort_key(self, person):
        return str(
            person.get("displayed_name", "") or ""
        ).casefold()

    def selected_person(self):
        selected = self.people_list.curselection()

        if not selected or selected[0] >= len(self.visible_people):
            return None

        return self.visible_people[int(selected[0])]

    def person_selected(self, event=None):
        self.fill_button.set_enabled(
            self.selected_person() is not None
        )

    def fill_position(self):
        person = self.selected_person()

        if person is None:
            return

        saved = self.save_command(
            person,
            {
                "galleons": self.salary_galleons_value.get(),
                "sickles": self.salary_sickles_value.get(),
                "knuts": self.salary_knuts_value.get(),
            },
            {
                "year": self.start_year_value.get(),
                "month": self.start_month_value.get(),
                "day": self.start_day_value.get(),
            },
            {
                "year": self.end_year_value.get(),
                "month": self.end_month_value.get(),
                "day": self.end_day_value.get(),
            },
        )

        if saved is not False:
            self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class StoreroomItemSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        items,
        selected_identities,
        save_command,
    ):
        super().__init__(parent)
        self.items = [
            deepcopy(item)
            for item in items or []
            if isinstance(item, dict)
        ]
        self.selected_identities = {
            tuple(identity)
            for identity in selected_identities or ()
        }
        self.save_command = save_command
        self.visible_items = []
        self.search_value = tk.StringVar()
        self.results_value = tk.StringVar()
        self.title("Add storeroom item")
        self.geometry("760x620")
        self.minsize(600, 480)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.grab_set()
        self.after_idle(self.search_control.focus_set)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Add storeroom item",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)
        explanation = tk.Label(
            body,
            text=(
                "Link an existing item to this storeroom. Storeroom items "
                "do not have a price."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=680,
        )
        explanation.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self.search_control = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_control.grid(row=1, column=0, sticky="ew")
        results_label = tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        results_label.grid(row=2, column=0, sticky="ew", pady=(10, 5))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.item_list = tk.Listbox(
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
        self.item_list.grid(row=0, column=0, sticky="nsew")
        self.item_list.bind("<Double-Button-1>", self.use_selected_item)
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.item_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.item_list.configure(yscrollcommand=scrollbar.set)
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(
            row=2,
            column=0,
            sticky="e",
            padx=18,
            pady=(0, 16),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        self.add_button = SoftButton(
            footer,
            text="Add item",
            command=self.use_selected_item,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        self.add_button.pack(side="left")

    def item_search_text(self, item):
        return " ".join(
            str(item.get(field_name, "") or "").strip()
            for field_name in ("name", "category", "collection")
        ).casefold()

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().casefold().split()
            if term
        ]
        self.visible_items = [
            item
            for item in self.items
            if (
                (item.get("collection"), item.get("record_id"))
                not in self.selected_identities
                and all(
                    term in self.item_search_text(item)
                    for term in query_terms
                )
            )
        ]
        self.item_list.delete(0, "end")

        for index, item in enumerate(self.visible_items):
            self.item_list.insert("end", item.get("label", "Unnamed item"))
            self.item_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.results_value.set(f"Available items ({len(self.visible_items)})")
        self.add_button.set_enabled(bool(self.visible_items))

    def use_selected_item(self, event=None):
        selected = self.item_list.curselection()

        if not selected:
            return

        self.save_command(deepcopy(self.visible_items[int(selected[0])]))
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class OrganizationPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        status_command,
        event_controller=None,
        events_changed_command=None,
        scope_change_command=None,
        auto_refresh=True,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.event_controller = event_controller
        self.events_changed_command = events_changed_command
        self.scope_change_command = scope_change_command
        self.all_organizations = []
        self.organizations = []
        self.organization_id_by_line = {}
        self.organizations_by_id = {}
        self.location_labels_by_id = {}
        self.organization_lock_id = ""
        self.suppress_tree_selection = False
        self.hovered_tree_id = ""
        self.form_updates_paused = True
        self.form_dirty = False
        self.current_organization_id = None
        self.loaded_parent_organization_id = ""
        self.selected_location_id = ""
        self.selected_parent_organization_id = ""
        self.selected_school_id = ""
        self.active_editor_page = "details"
        self.hydrated_editor_pages = set()
        self.organization_events = normalize_organization_events([])
        self.organization_jobs = normalize_organization_jobs([])
        self.visible_job_timeline = []
        self.job_timeline_value = tk.StringVar(
            value="Select a job to see its timeline"
        )
        self.name_value = tk.StringVar()
        self.type_value = tk.StringVar(value=ORGANIZATION_TYPES[0])
        self.location_value = tk.StringVar(value="No location selected")
        self.parent_value = tk.StringVar(
            value="No parent organization"
        )
        self.link_school_value = tk.BooleanVar(value=False)
        self.school_value = tk.StringVar(value="Choose a school")
        self.has_shop_value = tk.BooleanVar(value=False)
        self.also_location_value = tk.BooleanVar(value=False)
        self.shop_inventory = normalize_shop_inventory({})
        self.famous_organization_value = tk.BooleanVar(value=False)
        self.is_faction_value = tk.BooleanVar(value=False)
        self.faction_color_value = tk.StringVar(value="#808080")
        self.has_storeroom_value = tk.BooleanVar(value=False)
        self.storeroom_inventory = normalize_storeroom_inventory([])
        self.includes_library_value = tk.BooleanVar(value=False)
        self.library_open_to_outsiders_value = tk.BooleanVar(value=False)
        self.extinct_value = tk.BooleanVar(value=False)
        self.extinction_year_value = tk.StringVar()
        self.extinction_month_value = tk.StringVar()
        self.extinction_day_value = tk.StringVar()
        self.search_value = tk.StringVar()
        self.type_filter_value = tk.StringVar(value="All types")
        self.school_filter_value = tk.StringVar(value="All school links")
        self.filter_updates_paused = False
        self.year_filter_value = None
        self.location_filter_id = ""
        self.location_filter_value = tk.StringVar(value="All places")
        self.filter_summary_value = tk.StringVar(
            value="All organizations"
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_workspace()
        self.autosave = DebouncedAutosave(
            self,
            self.autosave_organization,
            lambda: self.form_dirty,
            delay_ms=700,
        )
        self.name_value.trace_add("write", self.form_value_changed)
        self.type_value.trace_add("write", self.form_value_changed)
        self.faction_color_value.trace_add("write", self.form_value_changed)
        self.also_location_value.trace_add(
            "write",
            self.form_value_changed,
        )
        self.link_school_value.trace_add(
            "write",
            self.form_value_changed,
        )
        for extinction_date_value in (
            self.extinction_year_value,
            self.extinction_month_value,
            self.extinction_day_value,
        ):
            extinction_date_value.trace_add(
                "write",
                self.form_value_changed,
            )
        self.overview_control.text.bind(
            "<<Modified>>",
            self.narrative_changed,
            add="+",
        )
        self.notes_control.text.bind(
            "<<Modified>>",
            self.narrative_changed,
            add="+",
        )
        self.search_value.trace_add("write", self.filter_changed)
        self.type_filter_value.trace_add("write", self.filter_changed)
        self.school_filter_value.trace_add(
            "write",
            self.filter_changed,
        )
        self.form_updates_paused = False

        if auto_refresh:
            self.refresh()

    def form_value_changed(self, *arguments):
        if hasattr(self, "name_field"):
            self.update_organization_required_fields()
        self.mark_form_dirty()

    def narrative_changed(self, event):
        if not event.widget.edit_modified():
            return

        event.widget.edit_modified(False)
        self.mark_form_dirty()

    def mark_form_dirty(self):
        if self.form_updates_paused or not self.current_organization_id:
            return

        self.form_dirty = True
        self.revert_button.set_enabled(True)
        self.update_organization_required_fields()
        self.status_command("Changes will save automatically")
        self.autosave.schedule()

    def build_filter_menu(self):
        self.filter_menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=PRIMARY_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )
        type_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=PRIMARY_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for organization_type in ("All types", *ORGANIZATION_TYPES):
            type_menu.add_radiobutton(
                label=organization_type,
                variable=self.type_filter_value,
                value=organization_type,
            )

        school_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=PRIMARY_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for school_filter in (
            "All school links",
            "Linked schools",
            "Unlinked organizations",
        ):
            school_menu.add_radiobutton(
                label=school_filter,
                variable=self.school_filter_value,
                value=school_filter,
            )

        self.filter_menu.add_cascade(label="Type", menu=type_menu)
        self.filter_menu.add_cascade(
            label="School link",
            menu=school_menu,
        )
        self.filter_menu.add_command(
            label="Existing in year…",
            command=self.choose_year_filter,
        )
        self.filter_menu.add_command(
            label="Place…",
            command=self.choose_location_filter,
        )
        self.filter_menu.add_separator()
        self.filter_menu.add_command(
            label="Show all",
            command=self.show_all_organizations,
        )

    def show_filter_menu(self):
        self.filter_button.update_idletasks()

        try:
            self.filter_menu.tk_popup(
                self.filter_button.winfo_rootx(),
                (
                    self.filter_button.winfo_rooty()
                    + self.filter_button.winfo_height()
                ),
            )
        finally:
            self.filter_menu.grab_release()

    def choose_year_filter(self):
        selected_year = simpledialog.askinteger(
            "Existing in year",
            (
                "Show organizations founded on or before which year?\n"
                "Cancel to keep the current filter."
            ),
            parent=self,
            initialvalue=self.year_filter_value,
            minvalue=-99999,
            maxvalue=99999,
        )

        if selected_year is None:
            return

        self.year_filter_value = selected_year
        self.refresh(self.current_organization_id)

    def choose_location_filter(self):
        OrganizationLocationSelectionDialog(
            self,
            self.controller.location_records(),
            self.location_filter_selected,
            self.location_filter_id,
            dialog_title="Filter organizations by place",
            action_text="Use place",
            allow_clear=True,
        )

    def location_filter_selected(self, location):
        self.location_filter_id = (
            str(location.get("record_id", "") or "").strip()
            if isinstance(location, dict)
            else ""
        )
        self.location_filter_value.set(
            self.controller.location_label(
                self.location_filter_id
            )
            if self.location_filter_id
            else "All places"
        )
        self.refresh(self.current_organization_id)

    def school_filter_key(self):
        selected = self.school_filter_value.get()

        if selected == "Linked schools":
            return "linked"

        if selected == "Unlinked organizations":
            return "unlinked"

        return "all"

    def update_filter_summary(self):
        parts = []

        if self.type_filter_value.get() != "All types":
            parts.append(self.type_filter_value.get())

        if self.school_filter_value.get() != "All school links":
            parts.append(self.school_filter_value.get())

        if self.year_filter_value is not None:
            parts.append(f"By {self.year_filter_value}")

        if self.location_filter_id:
            parts.append(self.location_filter_value.get())

        self.filter_summary_value.set(
            " · ".join(parts) or "All organizations"
        )

    def filter_changed(self, *arguments):
        if self.filter_updates_paused:
            return

        self.refresh(self.current_organization_id)

    def show_all_organizations(self):
        self.filter_updates_paused = True
        self.search_value.set("")
        self.type_filter_value.set("All types")
        self.school_filter_value.set("All school links")
        self.year_filter_value = None
        self.location_filter_id = ""
        self.location_filter_value.set("All places")
        self.filter_updates_paused = False
        self.refresh(self.current_organization_id)

    def search_shortcut(self):
        self.search_control.focus_set()
        return True

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=PRIMARY_DARK, height=64)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        title = tk.Label(
            toolbar,
            text="Organizations",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=20,
        )
        title.grid(row=0, column=0, sticky="nsew")
        self.new_button = SoftButton(
            toolbar,
            text="New",
            command=self.create_organization,
            background=PRIMARY_DARK,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=38,
        )
        self.new_button.grid(row=0, column=1, padx=4, pady=13)
        self.delete_button = SoftButton(
            toolbar,
            text="Delete",
            command=self.delete_organization,
            background=PRIMARY_DARK,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=38,
        )
        self.delete_button.grid(row=0, column=2, padx=4, pady=13)
        self.revert_button = SoftButton(
            toolbar,
            text="Revert",
            command=self.revert_organization,
            background=PRIMARY_DARK,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=38,
        )
        self.revert_button.grid(row=0, column=3, padx=4, pady=13)
        self.save_button = SoftButton(
            toolbar,
            text="Save",
            command=self.save_organization,
            background=PRIMARY_DARK,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=38,
        )
        self.save_button.grid_remove()

    def build_workspace(self):
        workspace = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=BORDER,
            borderwidth=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        workspace.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(10, 18),
        )
        list_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        list_card.grid_rowconfigure(4, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        list_title = tk.Label(
            list_card,
            text="Organizations",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        list_title.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        advanced_button = SoftButton(
            list_card,
            text="Advanced…",
            command=self.open_organization_search,
            background=SURFACE,
            width=92,
            height=32,
            font=app_font(9, "bold"),
        )
        advanced_button.grid(
            row=0,
            column=1,
            sticky="e",
            pady=(0, 9),
        )
        scope_bar = tk.Frame(list_card, bg=SURFACE)
        scope_bar.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 9),
        )
        scope_bar.grid_columnconfigure(0, weight=1)
        self.organization_scope_status_value = tk.StringVar(
            value="All organizations"
        )
        scope_status = tk.Label(
            scope_bar,
            textvariable=self.organization_scope_status_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        scope_status.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 7),
        )
        self.organization_scope_button = SoftButton(
            scope_bar,
            text="Select to lock",
            command=self.toggle_organization_lock,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=30,
            font=app_font(9, "bold"),
        )
        self.organization_scope_button.grid(
            row=0,
            column=1,
            sticky="e",
        )
        self.search_control = RoundedEntry(
            list_card,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_control.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )
        filter_row = tk.Frame(list_card, bg=SURFACE)
        filter_row.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )
        filter_row.grid_columnconfigure(1, weight=1)
        self.filter_button = SoftButton(
            filter_row,
            text="Filters ▾",
            command=self.show_filter_menu,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=30,
            font=app_font(9, "bold"),
        )
        self.filter_button.grid(row=0, column=0, sticky="w")
        filter_summary = tk.Label(
            filter_row,
            textvariable=self.filter_summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        filter_summary.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )
        show_all_button = SoftButton(
            filter_row,
            text="Show all",
            command=self.show_all_organizations,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=68,
            height=30,
            font=app_font(8, "bold"),
        )
        show_all_button.grid(row=0, column=2, sticky="e")
        self.build_filter_menu()
        self.organization_tree_frame = tk.Frame(
            list_card,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
        )
        self.organization_tree_frame.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        self.organization_tree_frame.grid_rowconfigure(0, weight=1)
        self.organization_tree_frame.grid_columnconfigure(0, weight=1)
        organization_tree_style = ttk.Style(self)
        organization_tree_style.configure(
            "OrganizationHierarchy.Treeview",
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            borderwidth=0,
            relief="flat",
            rowheight=46,
            indent=10,
            font=app_font(10),
        )
        organization_tree_style.map(
            "OrganizationHierarchy.Treeview",
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        self.organization_tree = ttk.Treeview(
            self.organization_tree_frame,
            style="OrganizationHierarchy.Treeview",
            show="tree",
            selectmode="browse",
            takefocus=True,
        )
        self.organization_tree.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.organization_tree.tag_configure(
            "context",
            foreground=TEXT_MUTED,
        )
        self.organization_tree.tag_configure(
            "top_level_even",
            background="#E9D9F0",
        )
        self.organization_tree.tag_configure(
            "top_level_odd",
            background="#E2CFEB",
        )
        self.organization_tree.tag_configure(
            "nested_organization",
            background="#FFFFFF",
        )
        self.organization_tree.tag_configure(
            "hover",
            background=LIST_HOVER,
        )
        self.organization_tree.bind(
            "<<TreeviewSelect>>",
            self.organization_selected,
        )
        self.organization_tree.bind(
            "<Motion>",
            self.organization_tree_motion,
        )
        self.organization_tree.bind(
            "<Leave>",
            self.organization_tree_left,
        )
        self.organization_tree.bind(
            "<Return>",
            self.toggle_selected_organization_branch,
        )
        self.organization_tree.bind(
            "<space>",
            self.toggle_selected_organization_branch,
        )
        self.organization_tree.configure(cursor="hand2")
        list_scrollbar = tk.Scrollbar(
            self.organization_tree_frame,
            command=self.organization_tree.yview,
        )
        list_scrollbar.grid(row=0, column=1, sticky="ns")
        self.organization_tree.configure(
            yscrollcommand=list_scrollbar.set
        )

        editor_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=20,
            pady=18,
        )
        editor_card.grid_columnconfigure(0, weight=1)
        editor_card.grid_rowconfigure(2, weight=1)
        self.build_editor(editor_card)
        workspace.add(list_card, minsize=290, width=330)
        workspace.add(editor_card, minsize=680)

    def build_editor(self, parent):
        page_navigation = tk.Frame(parent, bg=SURFACE)
        page_navigation.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 10),
        )
        self.details_page_button = SoftButton(
            page_navigation,
            text="Details",
            command=self.show_details_page,
            background=SURFACE,
            width=92,
            height=34,
            font=app_font(9, "bold"),
        )
        self.details_page_button.pack(
            side="left",
            padx=(0, 6),
        )
        self.children_page_button = SoftButton(
            page_navigation,
            text="Nested organizations",
            command=self.show_children_page,
            background=SURFACE,
            width=156,
            height=34,
            font=app_font(9, "bold"),
        )
        self.children_page_button.pack(side="left")
        self.timeline_page_button = SoftButton(
            page_navigation,
            text="Timeline",
            command=self.show_timeline_page,
            background=SURFACE,
            width=96,
            height=34,
            font=app_font(9, "bold"),
        )
        self.timeline_page_button.pack(
            side="left",
            padx=(6, 0),
        )
        self.jobs_page_button = SoftButton(
            page_navigation,
            text="Jobs",
            command=self.show_jobs_page,
            background=SURFACE,
            width=92,
            height=34,
            font=app_font(9, "bold"),
        )
        self.jobs_page_button.pack(
            side="left",
            padx=(6, 0),
        )
        self.shop_page_button = SoftButton(
            page_navigation,
            text="Shop",
            command=self.show_shop_page,
            background=SURFACE,
            width=92,
            height=34,
            font=app_font(9, "bold"),
        )
        self.storeroom_page_button = SoftButton(
            page_navigation,
            text="Storeroom",
            command=self.show_storeroom_page,
            background=SURFACE,
            width=104,
            height=34,
            font=app_font(9, "bold"),
        )
        page_container = tk.Frame(parent, bg=SURFACE)
        page_container.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        page_container.grid_rowconfigure(0, weight=1)
        page_container.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)
        self.details_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.details_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.details_page.grid_columnconfigure(0, weight=1)
        self.details_page.grid_rowconfigure(2, weight=1)
        self.children_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.children_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.children_page.grid_columnconfigure(0, weight=1)
        self.children_page.grid_rowconfigure(1, weight=1)
        self.timeline_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.timeline_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.timeline_page.grid_columnconfigure(0, weight=1)
        self.timeline_page.grid_rowconfigure(1, weight=1)
        self.jobs_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.jobs_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.jobs_page.grid_columnconfigure(0, weight=1)
        self.jobs_page.grid_rowconfigure(1, weight=1)
        self.shop_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.shop_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.shop_page.grid_columnconfigure(0, weight=1)
        self.shop_page.grid_rowconfigure(1, weight=1)
        self.storeroom_page = tk.Frame(
            page_container,
            bg=SURFACE,
        )
        self.storeroom_page.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.storeroom_page.grid_columnconfigure(0, weight=1)
        self.storeroom_page.grid_rowconfigure(1, weight=1)
        self.build_details_editor(self.details_page)
        self.build_children_editor(self.children_page)
        self.build_timeline_editor(self.timeline_page)
        self.build_jobs(self.jobs_page)
        self.build_shop(self.shop_page)
        self.build_storeroom(self.storeroom_page)
        self.show_editor_page("details")
        self.update_shop_page_visibility()
        self.update_storeroom_page_visibility()

    def build_details_editor(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "Organizations are tied to a location. Types currently include "
                "governmental, non-profit, media, school, and shop."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=14,
            pady=12,
        )
        explanation.grid(row=0, column=0, sticky="ew")
        fields = tk.Frame(parent, bg=SURFACE)
        fields.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        fields.grid_columnconfigure(0, weight=2)
        fields.grid_columnconfigure(1, weight=1)
        fields.grid_columnconfigure(2, weight=2)
        self.name_field = LabeledEntry(
            fields,
            "Organization name",
            self.name_value,
            background=SURFACE,
        )
        self.name_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 7),
        )
        type_frame = tk.Frame(fields, bg=SURFACE)
        type_frame.grid(row=0, column=1, sticky="ew", padx=7)
        type_frame.grid_columnconfigure(0, weight=1)
        type_label = tk.Label(
            type_frame,
            text="Type",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        type_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.type_picker = ttk.Combobox(
            type_frame,
            textvariable=self.type_value,
            values=ORGANIZATION_TYPES,
            state="readonly",
            font=app_font(10),
        )
        self.type_picker.grid(row=1, column=0, sticky="ew", ipady=7)
        self.type_picker.bind(
            "<<ComboboxSelected>>",
            self.organization_type_changed,
        )
        location_frame = tk.Frame(fields, bg=SURFACE)
        location_frame.grid(row=0, column=2, sticky="ew", padx=(7, 0))
        location_frame.grid_columnconfigure(0, weight=1)
        location_label = tk.Label(
            location_frame,
            text="Home location",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        location_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        location_value_label = tk.Label(
            location_frame,
            textvariable=self.location_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
            pady=9,
        )
        location_value_label.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        choose_location_button = SoftButton(
            location_frame,
            text="Choose…",
            command=self.open_location_dialog,
            background=SURFACE,
            width=82,
            height=38,
            font=app_font(9, "bold"),
        )
        choose_location_button.grid(
            row=1,
            column=1,
            padx=(6, 0),
        )
        clear_location_button = SoftButton(
            location_frame,
            text="Clear",
            command=self.clear_location,
            background=SURFACE,
            width=62,
            height=38,
            font=app_font(9, "bold"),
        )
        clear_location_button.grid(
            row=1,
            column=2,
            padx=(6, 0),
        )
        parent_frame = tk.Frame(fields, bg=SURFACE)
        parent_frame.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 0),
        )
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_label = tk.Label(
            parent_frame,
            text="Nested within",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        parent_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        parent_value_label = tk.Label(
            parent_frame,
            textvariable=self.parent_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
            pady=9,
        )
        parent_value_label.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        self.choose_parent_button = SoftButton(
            parent_frame,
            text="Choose…",
            command=self.open_parent_dialog,
            background=SURFACE,
            width=82,
            height=38,
            font=app_font(9, "bold"),
        )
        self.choose_parent_button.grid(
            row=1,
            column=1,
            padx=(6, 0),
        )
        self.clear_parent_button = SoftButton(
            parent_frame,
            text="No parent",
            command=self.clear_parent,
            background=SURFACE,
            width=92,
            height=38,
            font=app_font(9, "bold"),
        )
        self.clear_parent_button.grid(
            row=1,
            column=2,
            padx=(6, 0),
        )
        school_frame = tk.Frame(fields, bg=SURFACE)
        school_frame.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 0),
        )
        school_frame.grid_columnconfigure(1, weight=1)
        self.school_link_checkbox = tk.Checkbutton(
            school_frame,
            text="Link school",
            variable=self.link_school_value,
            command=self.toggle_school_link,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.school_link_checkbox.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 10),
        )
        school_value_label = tk.Label(
            school_frame,
            textvariable=self.school_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=10,
            pady=8,
        )
        school_value_label.grid(
            row=0,
            column=1,
            sticky="ew",
        )
        self.choose_school_button = SoftButton(
            school_frame,
            text="Choose school…",
            command=self.open_school_dialog,
            background=SURFACE,
            width=118,
            height=36,
            font=app_font(9, "bold"),
        )
        self.choose_school_button.grid(
            row=0,
            column=2,
            padx=(6, 0),
        )
        flags_frame = tk.Frame(fields, bg=SURFACE)
        flags_frame.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(12, 0),
        )
        flags_frame.grid_columnconfigure(4, weight=1)
        self.has_shop_checkbox = tk.Checkbutton(
            flags_frame,
            text="Has a shop",
            variable=self.has_shop_value,
            command=self.shop_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.has_shop_checkbox.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 20),
        )
        self.also_location_checkbox = tk.Checkbutton(
            flags_frame,
            text="This organization is also a location",
            variable=self.also_location_value,
            command=self.mark_form_dirty,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.also_location_checkbox.grid(
            row=1,
            column=2,
            columnspan=2,
            sticky="w",
            padx=(0, 20),
            pady=(8, 0),
        )
        self.has_storeroom_checkbox = tk.Checkbutton(
            flags_frame,
            text="Has a storeroom",
            variable=self.has_storeroom_value,
            command=self.storeroom_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.has_storeroom_checkbox.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(0, 20),
        )
        self.includes_library_checkbox = tk.Checkbutton(
            flags_frame,
            text="Includes a library",
            variable=self.includes_library_value,
            command=self.library_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.includes_library_checkbox.grid(
            row=1,
            column=0,
            sticky="w",
            padx=(0, 20),
            pady=(8, 0),
        )
        self.library_open_checkbox = tk.Checkbutton(
            flags_frame,
            text="Library open to outsiders",
            variable=self.library_open_to_outsiders_value,
            command=self.mark_form_dirty,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.library_open_checkbox.grid(
            row=1,
            column=1,
            sticky="w",
            padx=(0, 20),
            pady=(8, 0),
        )
        self.famous_organization_checkbox = tk.Checkbutton(
            flags_frame,
            text="Famous organization",
            variable=self.famous_organization_value,
            command=self.mark_form_dirty,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.famous_organization_checkbox.grid(
            row=0,
            column=2,
            sticky="w",
            padx=(0, 20),
        )
        self.faction_checkbox = tk.Checkbutton(
            flags_frame,
            text="In-world faction",
            variable=self.is_faction_value,
            command=self.mark_form_dirty,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.faction_checkbox.grid(
            row=1,
            column=2,
            sticky="w",
            padx=(0, 20),
            pady=(8, 0),
        )
        self.faction_color_field = LabeledEntry(
            flags_frame,
            "Faction color (#RRGGBB)",
            self.faction_color_value,
            background=SURFACE,
        )
        self.faction_color_field.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(0, 20),
            pady=(8, 0),
        )
        self.extinct_checkbox = tk.Checkbutton(
            flags_frame,
            text="Extinct",
            variable=self.extinct_value,
            command=self.extinction_state_changed,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            anchor="w",
            padx=0,
            pady=0,
        )
        self.extinct_checkbox.grid(
            row=0,
            column=3,
            sticky="w",
            padx=(0, 20),
        )
        self.extinction_date_frame = tk.Frame(
            flags_frame,
            bg=SURFACE,
        )
        self.extinction_date_frame.grid(
            row=2,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(8, 0),
        )
        self.extinction_date_frame.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="organization_extinction_date",
        )
        extinction_date_heading = tk.Label(
            self.extinction_date_frame,
            text="Extinction date",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        extinction_date_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        self.extinction_year_field = LabeledEntry(
            self.extinction_date_frame,
            "Year",
            self.extinction_year_value,
            background=SURFACE,
        )
        self.extinction_year_field.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 5),
        )
        self.extinction_month_field = LabeledEntry(
            self.extinction_date_frame,
            "Month",
            self.extinction_month_value,
            background=SURFACE,
        )
        self.extinction_month_field.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=5,
        )
        self.extinction_day_field = LabeledEntry(
            self.extinction_date_frame,
            "Day",
            self.extinction_day_value,
            background=SURFACE,
        )
        self.extinction_day_field.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(5, 0),
        )
        calendar_notice = CalendarAdoptionNotice(
            self.extinction_date_frame,
            background=SURFACE,
            wraplength=620,
            date_variables=(
                self.extinction_year_value,
                self.extinction_month_value,
                self.extinction_day_value,
            ),
        )
        calendar_notice.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )
        self.update_extinction_date_visibility()
        self.update_library_state()
        narrative = tk.Frame(parent, bg=SURFACE)
        narrative.grid(row=2, column=0, sticky="nsew", pady=(16, 0))
        narrative.grid_rowconfigure(0, weight=1)
        narrative.grid_columnconfigure(0, weight=1)
        narrative.grid_columnconfigure(1, weight=1)
        narrative.grid_columnconfigure(2, weight=1)
        overview_frame = tk.Frame(narrative, bg=SURFACE)
        overview_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        overview_label = tk.Label(
            overview_frame,
            text="Overview",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        overview_label.pack(fill="x", pady=(0, 5))
        self.overview_control = RoundedText(
            overview_frame,
            background=SURFACE,
            height=12,
        )
        self.overview_control.pack(fill="both", expand=True)
        notes_frame = tk.Frame(narrative, bg=SURFACE)
        notes_frame.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        notes_label = tk.Label(
            notes_frame,
            text="Notes",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        notes_label.pack(fill="x", pady=(0, 5))
        self.notes_control = RoundedText(
            notes_frame,
            background=SURFACE,
            height=12,
        )
        self.notes_control.pack(fill="both", expand=True)

        events_frame = tk.Frame(narrative, bg=SURFACE)
        events_frame.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(14, 0),
        )
        events_frame.grid_rowconfigure(1, weight=1)
        events_frame.grid_columnconfigure(0, weight=1)
        events_label = tk.Label(
            events_frame,
            text="Events",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        events_label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.event_list = tk.Listbox(
            events_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            height=10,
        )
        self.event_list.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        self.event_list.bind(
            "<Double-Button-1>",
            self.edit_selected_event,
        )
        event_scrollbar = tk.Scrollbar(
            events_frame,
            command=self.event_list.yview,
        )
        event_scrollbar.grid(row=1, column=2, sticky="ns")
        self.event_list.configure(
            yscrollcommand=event_scrollbar.set
        )
        add_event_button = SoftButton(
            events_frame,
            text="Add event",
            command=self.add_event,
            background=SURFACE,
            width=76,
            height=32,
            font=app_font(9, "bold"),
        )
        add_event_button.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        edit_event_button = SoftButton(
            events_frame,
            text="Edit",
            command=self.edit_selected_event,
            background=SURFACE,
            width=56,
            height=32,
            font=app_font(9, "bold"),
        )
        edit_event_button.grid(
            row=2,
            column=1,
            sticky="w",
            padx=(6, 0),
            pady=(8, 0),
        )
        remove_event_button = SoftButton(
            events_frame,
            text="Remove",
            command=self.remove_selected_event,
            background=SURFACE,
            width=68,
            height=32,
            font=app_font(9, "bold"),
        )
        remove_event_button.grid(
            row=2,
            column=2,
            sticky="e",
            padx=(6, 0),
            pady=(8, 0),
        )
        events_frame.grid_remove()
        self.tags_editor = ColoredTagsEditor(
            narrative,
            title="Tags",
            background=SURFACE,
            change_command=self.mark_form_dirty,
            height=10,
        )
        self.tags_editor.grid(
            row=0,
            column=2,
            sticky="nsew",
            padx=(14, 0),
        )

    def build_timeline_editor(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "This page contains the organization's full event timeline. "
                "Add, edit, and remove organization events here."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=14,
            pady=12,
        )
        explanation.grid(row=0, column=0, sticky="ew")
        timeline_frame = tk.Frame(
            parent,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        timeline_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )
        timeline_frame.grid_rowconfigure(0, weight=1)
        timeline_frame.grid_columnconfigure(0, weight=1)
        self.event_list = tk.Listbox(
            timeline_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            font=app_font(11),
            activestyle="none",
            exportselection=False,
        )
        self.event_list.grid(row=0, column=0, sticky="nsew")
        self.event_list.bind(
            "<Double-Button-1>",
            self.edit_selected_event,
        )
        scrollbar = tk.Scrollbar(
            timeline_frame,
            command=self.event_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.event_list.configure(yscrollcommand=scrollbar.set)
        actions = tk.Frame(parent, bg=SURFACE)
        actions.grid(row=2, column=0, sticky="w", pady=(10, 0))
        SoftButton(
            actions,
            text="Add event",
            command=self.add_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=96,
            height=34,
            font=app_font(9, "bold"),
        ).pack(side="left")
        SoftButton(
            actions,
            text="Edit",
            command=self.edit_selected_event,
            background=SURFACE,
            width=66,
            height=34,
            font=app_font(9, "bold"),
        ).pack(side="left", padx=(6, 0))
        SoftButton(
            actions,
            text="Remove",
            command=self.remove_selected_event,
            background=SURFACE,
            width=76,
            height=34,
            font=app_font(9, "bold"),
        ).pack(side="left", padx=(6, 0))

    def build_children_editor(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "These are the organizations nested directly within the "
                "selected organization."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            padx=14,
            pady=12,
        )
        explanation.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        list_frame = tk.Frame(
            parent,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.children_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(11),
            activestyle="none",
            exportselection=False,
        )
        self.children_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.children_list.bind(
            "<Double-Button-1>",
            self.open_selected_child,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.children_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.children_list.configure(
            yscrollcommand=scrollbar.set
        )
        open_button = SoftButton(
            parent,
            text="Open selected organization",
            command=self.open_selected_child,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=190,
            height=38,
            font=app_font(9, "bold"),
        )
        open_button.grid(
            row=2,
            column=0,
            sticky="e",
            pady=(12, 0),
        )

    def show_editor_page(self, page_name):
        if page_name == "storeroom" and self.has_storeroom_value.get():
            self.active_editor_page = "storeroom"
            self.hydrate_editor_page("storeroom")
            self.storeroom_page.tkraise()
            self.storeroom_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )

            for page_button in (
                self.details_page_button,
                self.children_page_button,
                self.timeline_page_button,
                self.jobs_page_button,
                self.shop_page_button,
            ):
                page_button.set_colors(
                    BUTTON_SOFT,
                    BUTTON_SOFT_HOVER,
                    TEXT_DARK,
                )

            return

        if page_name == "shop" and self.has_shop_value.get():
            self.active_editor_page = "shop"
            self.shop_page.tkraise()
            self.shop_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.details_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.children_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.timeline_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.jobs_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.storeroom_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            return

        if page_name == "timeline":
            self.active_editor_page = "timeline"
            self.hydrate_editor_page("timeline")
            self.timeline_page.tkraise()
            self.timeline_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )

            for page_button in (
                self.details_page_button,
                self.children_page_button,
                self.jobs_page_button,
                self.shop_page_button,
                self.storeroom_page_button,
            ):
                page_button.set_colors(
                    BUTTON_SOFT,
                    BUTTON_SOFT_HOVER,
                    TEXT_DARK,
                )

            return

        if page_name == "jobs":
            self.active_editor_page = "jobs"
            self.hydrate_editor_page("jobs")
            self.jobs_page.tkraise()
            self.jobs_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.details_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.children_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.timeline_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.shop_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.storeroom_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            return

        if page_name == "children":
            self.active_editor_page = "children"
            self.hydrate_editor_page("children")
            self.children_page.tkraise()
            self.children_page_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.details_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.timeline_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.jobs_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.shop_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.storeroom_page_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            return

        self.active_editor_page = "details"
        self.hydrated_editor_pages.add("details")
        self.details_page.tkraise()
        self.details_page_button.set_colors(
            PRIMARY,
            PRIMARY_HOVER,
            TEXT_DARK,
        )
        self.children_page_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.timeline_page_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.jobs_page_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.shop_page_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.storeroom_page_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )

    def hydrate_editor_page(self, page_name):
        normalized_page_name = str(page_name or "").strip().casefold()

        if normalized_page_name in self.hydrated_editor_pages:
            return

        if normalized_page_name == "children":
            self.refresh_children_list()
        elif normalized_page_name == "timeline":
            self.refresh_event_list()
        elif normalized_page_name == "jobs":
            self.refresh_job_list()
        elif normalized_page_name == "storeroom":
            self.refresh_storeroom_list()

        self.hydrated_editor_pages.add(normalized_page_name)

    def show_details_page(self):
        self.show_editor_page("details")

    def show_children_page(self):
        self.show_editor_page("children")

    def show_timeline_page(self):
        self.show_editor_page("timeline")

    def show_jobs_page(self):
        self.show_editor_page("jobs")

    def show_shop_page(self):
        self.show_editor_page("shop")

    def show_storeroom_page(self):
        self.show_editor_page("storeroom")

    def organization_type_changed(self, event=None):
        if self.type_value.get() == "School":
            self.also_location_value.set(True)

        if hasattr(self, "update_also_location_state"):
            self.update_also_location_state()
        self.mark_form_dirty()

    def update_also_location_state(self):
        if not hasattr(self, "also_location_checkbox"):
            return

        is_school = self.type_value.get() == "School"

        if is_school:
            self.also_location_value.set(True)

        self.also_location_checkbox.configure(
            state="disabled" if is_school else "normal"
        )

    def shop_state_changed(self):
        self.update_shop_page_visibility()
        self.mark_form_dirty()

    def update_shop_page_visibility(self):
        if not hasattr(self, "shop_page_button"):
            return

        if self.has_shop_value.get():
            if not self.shop_page_button.winfo_manager():
                self.shop_page_button.pack(
                    side="left",
                    padx=(6, 0),
                )
            return

        if self.active_editor_page == "shop":
            self.show_details_page()

        self.shop_page_button.pack_forget()

    def storeroom_state_changed(self):
        self.update_storeroom_page_visibility()
        self.mark_form_dirty()

    def library_state_changed(self):
        if not self.includes_library_value.get():
            self.library_open_to_outsiders_value.set(False)

        self.update_library_state()
        self.mark_form_dirty()

    def update_library_state(self):
        if not hasattr(self, "library_open_checkbox"):
            return

        self.library_open_checkbox.configure(
            state=(
                "normal"
                if self.includes_library_value.get()
                else "disabled"
            )
        )

    def update_storeroom_page_visibility(self):
        if not hasattr(self, "storeroom_page_button"):
            return

        if self.has_storeroom_value.get():
            if not self.storeroom_page_button.winfo_manager():
                self.storeroom_page_button.pack(
                    side="left",
                    padx=(6, 0),
                )
            return

        if self.active_editor_page == "storeroom":
            self.show_details_page()

        self.storeroom_page_button.pack_forget()

    def extinction_state_changed(self):
        self.update_extinction_date_visibility()
        self.mark_form_dirty()

    def update_extinction_date_visibility(self):
        if not hasattr(self, "extinction_date_frame"):
            return

        if self.extinct_value.get():
            self.extinction_date_frame.grid()
        else:
            self.extinction_date_frame.grid_remove()

    def refresh_children_list(self):
        if not hasattr(self, "children_list"):
            return

        self.child_organizations = (
            self.controller.first_order_children(
                self.current_organization_id
            )
            if self.current_organization_id
            else []
        )
        self.children_list.delete(0, "end")

        for index, organization in enumerate(
            self.child_organizations
        ):
            self.children_list.insert(
                "end",
                organization.get("name", "Unnamed"),
            )
            self.children_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

    def open_selected_child(self, event=None):
        selected = self.children_list.curselection()

        if not selected:
            return

        if not self.confirm_unsaved_organization_changes():
            return

        organization = self.child_organizations[
            int(selected[0])
        ]
        self.refresh(organization["record_id"], force_load=True)
        self.show_details_page()

    def build_jobs(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "Positions belong to this organization. Each position records "
                "when it opened and whether it is currently filled. Select a "
                "timeline range, then use Fill or adjust appointment."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=14,
            pady=12,
        )
        explanation.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        jobs_frame = tk.Frame(
            parent,
            bg=SURFACE,
        )
        jobs_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )
        jobs_frame.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="organization_jobs",
        )
        jobs_frame.grid_rowconfigure(1, weight=1)
        jobs_label = tk.Label(
            jobs_frame,
            text="Jobs",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        jobs_label.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 5),
        )
        timeline_label = tk.Label(
            jobs_frame,
            textvariable=self.job_timeline_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
            justify="left",
            wraplength=320,
        )
        timeline_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(14, 0),
            pady=(0, 5),
        )
        job_list_frame = tk.Frame(
            jobs_frame,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        job_list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
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
            highlightthickness=0,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.job_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        job_scrollbar = tk.Scrollbar(
            job_list_frame,
            command=self.job_list.yview,
        )
        job_scrollbar.grid(row=0, column=1, sticky="ns")
        self.job_list.configure(
            yscrollcommand=job_scrollbar.set
        )
        self.job_list.bind(
            "<<ListboxSelect>>",
            self.job_selected,
        )
        self.job_list.bind(
            "<Double-Button-1>",
            self.edit_selected_job,
        )
        timeline_frame = tk.Frame(
            jobs_frame,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        timeline_frame.grid(
            row=1,
            column=1,
            rowspan=2,
            sticky="nsew",
            padx=(14, 0),
        )
        timeline_frame.grid_rowconfigure(0, weight=1)
        timeline_frame.grid_columnconfigure(0, weight=1)
        self.job_timeline_list = tk.Listbox(
            timeline_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightthickness=0,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.job_timeline_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        timeline_scrollbar = tk.Scrollbar(
            timeline_frame,
            command=self.job_timeline_list.yview,
        )
        timeline_scrollbar.grid(row=0, column=1, sticky="ns")
        self.job_timeline_list.configure(
            yscrollcommand=timeline_scrollbar.set
        )
        self.job_timeline_list.bind(
            "<Double-Button-1>",
            self.job_timeline_clicked,
        )
        self.job_timeline_list.bind(
            "<<ListboxSelect>>",
            self.job_timeline_selection_changed,
        )
        job_actions = tk.Frame(
            jobs_frame,
            bg=SURFACE,
        )
        job_actions.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(8, 0),
        )
        add_job_button = SoftButton(
            job_actions,
            text="Add job",
            command=self.add_job,
            background=SURFACE,
            width=76,
            height=32,
            font=app_font(9, "bold"),
        )
        add_job_button.grid(
            row=0,
            column=0,
            sticky="w",
        )
        edit_job_button = SoftButton(
            job_actions,
            text="Edit",
            command=self.edit_selected_job,
            background=SURFACE,
            width=56,
            height=32,
            font=app_font(9, "bold"),
        )
        edit_job_button.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(6, 0),
        )
        duplicate_job_button = SoftButton(
            job_actions,
            text="Duplicate",
            command=self.duplicate_selected_job,
            background=SURFACE,
            width=82,
            height=32,
            font=app_font(9, "bold"),
        )
        duplicate_job_button.grid(
            row=0,
            column=2,
            sticky="w",
            padx=(6, 0),
        )
        remove_job_button = SoftButton(
            job_actions,
            text="Remove",
            command=self.remove_selected_job,
            background=SURFACE,
            width=68,
            height=32,
            font=app_font(9, "bold"),
        )
        remove_job_button.grid(
            row=0,
            column=3,
            sticky="w",
            padx=(6, 0),
        )
        self.appointment_button = SoftButton(
            jobs_frame,
            text="Fill or adjust appointment",
            command=self.job_timeline_clicked,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=184,
            height=32,
            font=app_font(9, "bold"),
        )
        self.appointment_button.grid(
            row=3,
            column=1,
            sticky="e",
            padx=(14, 0),
            pady=(8, 0),
        )
        self.appointment_button.set_enabled(False)

    def build_shop(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "Products will be linked here when shop inventory is built. "
                "The four stock categories are reserved below."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=14,
            pady=12,
        )
        explanation.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        categories = tk.Frame(parent, bg=SURFACE)
        categories.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )
        categories.grid_rowconfigure((0, 1), weight=1)
        categories.grid_columnconfigure((0, 1), weight=1)

        for index, (category_key, category_label) in enumerate(
            SHOP_STOCK_CATEGORIES
        ):
            category_card = tk.Frame(
                categories,
                bg=FIELD_BACKGROUND,
                highlightbackground=BORDER_SOFT,
                highlightthickness=1,
                padx=14,
                pady=12,
            )
            category_card.grid(
                row=index // 2,
                column=index % 2,
                sticky="nsew",
                padx=(0, 7) if index % 2 == 0 else (7, 0),
                pady=(0, 7) if index < 2 else (7, 0),
            )
            category_heading = tk.Label(
                category_card,
                text=category_label,
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                font=app_font(11, "bold"),
                anchor="w",
            )
            category_heading.pack(fill="x")
            placeholder = tk.Label(
                category_card,
                text="Product linking placeholder",
                bg=FIELD_BACKGROUND,
                fg=TEXT_MUTED,
                font=app_font(9),
                anchor="nw",
                justify="left",
            )
            placeholder.pack(fill="both", expand=True, pady=(8, 0))

    def build_storeroom(self, parent):
        explanation = tk.Label(
            parent,
            text=(
                "Items stored here are linked from the game database and "
                "do not have a price."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
            wraplength=760,
            padx=14,
            pady=12,
        )
        explanation.grid(row=0, column=0, sticky="ew")
        list_frame = tk.Frame(
            parent,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.storeroom_list = tk.Listbox(
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
        self.storeroom_list.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.storeroom_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.storeroom_list.configure(yscrollcommand=scrollbar.set)
        actions = tk.Frame(parent, bg=SURFACE)
        actions.grid(row=2, column=0, sticky="w", pady=(10, 0))
        add_button = SoftButton(
            actions,
            text="Add item",
            command=self.add_storeroom_item,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=34,
            font=app_font(9, "bold"),
        )
        add_button.pack(side="left")
        remove_button = SoftButton(
            actions,
            text="Remove",
            command=self.remove_storeroom_item,
            background=SURFACE,
            width=82,
            height=34,
            font=app_font(9, "bold"),
        )
        remove_button.pack(side="left", padx=(6, 0))

    def refresh_storeroom_list(self):
        if not hasattr(self, "storeroom_list"):
            return

        self.storeroom_inventory = normalize_storeroom_inventory(
            getattr(self, "storeroom_inventory", [])
        )
        self.storeroom_list.delete(0, "end")

        for index, reference in enumerate(self.storeroom_inventory):
            self.storeroom_list.insert(
                "end",
                self.controller.storeroom_item_label(reference),
            )
            self.storeroom_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

    def add_storeroom_item(self):
        selected_identities = {
            (reference["collection"], reference["record_id"])
            for reference in self.storeroom_inventory
        }
        StoreroomItemSelectionDialog(
            self,
            self.controller.storeroom_item_options(),
            selected_identities,
            self.storeroom_item_selected,
        )

    def storeroom_item_selected(self, item):
        reference = {
            "collection": item.get("collection", ""),
            "record_id": item.get("record_id", ""),
        }
        self.storeroom_inventory = normalize_storeroom_inventory(
            [*self.storeroom_inventory, reference]
        )
        self.refresh_storeroom_list()
        self.mark_form_dirty()

    def remove_storeroom_item(self):
        selected = self.storeroom_list.curselection()

        if not selected:
            return

        selected_index = int(selected[0])
        self.storeroom_inventory = [
            reference
            for index, reference in enumerate(self.storeroom_inventory)
            if index != selected_index
        ]
        self.refresh_storeroom_list()
        self.mark_form_dirty()

    def refresh(
        self,
        selected_organization_id=None,
        force_load=False,
    ):
        selected_id = (
            self.current_organization_id
            if selected_organization_id is None
            else str(selected_organization_id or "").strip()
        )
        self.all_organizations = self.controller.list_organizations()
        self.organizations_by_id = {
            str(organization.get("record_id", "") or "").strip(): organization
            for organization in self.all_organizations
            if str(organization.get("record_id", "") or "").strip()
        }
        self.location_labels_by_id = {
            str(option.get("record_id", "") or "").strip(): str(
                option.get("label", "") or "Unknown location"
            ).strip()
            for option in self.controller.location_options()
            if str(option.get("record_id", "") or "").strip()
        }

        if self.organization_lock_id not in self.organizations_by_id:
            self.organization_lock_id = ""

        self.organizations = self.controller.search_organizations(
            self.search_value.get(),
            self.type_filter_value.get(),
            self.year_filter_value,
            self.location_filter_id,
            self.school_filter_key(),
            organizations=self.all_organizations,
        )
        self.update_filter_summary()
        matching_ids = {
            str(organization.get("record_id", "") or "")
            for organization in self.organizations
        }
        scoped_ids = organization_ids_in_scope(
            self.all_organizations,
            self.organization_lock_id,
        )
        matching_ids &= scoped_ids
        visible_ids = self.organization_visible_ids(
            matching_ids,
            scoped_ids,
        )

        if (
            self.form_dirty
            and self.current_organization_id in scoped_ids
        ):
            visible_ids |= self.organization_visible_ids(
                {self.current_organization_id},
                scoped_ids,
            )

        if selected_id not in visible_ids:
            selected_id = (
                self.organization_lock_id
                if self.organization_lock_id in visible_ids
                else next(
                    (
                        str(organization.get("record_id", "") or "")
                        for organization in self.organizations
                        if str(
                            organization.get("record_id", "") or ""
                        )
                        in visible_ids
                    ),
                    "",
                )
            )

        if self.form_dirty and not force_load:
            selected_id = (
                self.current_organization_id
                if self.current_organization_id in visible_ids
                else ""
            )

        self.rebuild_organization_tree(
            visible_ids,
            matching_ids,
            selected_id,
        )
        self.update_organization_lock_controls()

        if self.form_dirty and not force_load:
            return

        if selected_id:
            self.load_organization(selected_id)
        else:
            self.clear_form()

    def organization_visible_ids(self, matching_ids, scoped_ids):
        visible_ids = set(matching_ids)

        for matching_id in matching_ids:
            current_id = matching_id
            visited_ids = set()

            while current_id and current_id not in visited_ids:
                visited_ids.add(current_id)
                organization = self.organizations_by_id.get(current_id)

                if organization is None:
                    break

                parent_id = str(
                    organization.get(
                        "parent_organization_id",
                        "",
                    )
                    or ""
                ).strip()

                if not parent_id or parent_id not in scoped_ids:
                    break

                visible_ids.add(parent_id)
                current_id = parent_id

        return visible_ids

    def expanded_organization_ids(self):
        return {
            organization_id
            for organization_id in self.organizations_by_id
            if self.organization_tree.exists(organization_id)
            and bool(
                self.organization_tree.item(
                    organization_id,
                    "open",
                )
            )
        }

    def rebuild_organization_tree(
        self,
        visible_ids,
        matching_ids,
        selected_id,
    ):
        expanded_ids = self.expanded_organization_ids()
        children_by_parent_id = {}

        for organization_id, organization in self.organizations_by_id.items():
            parent_id = str(
                organization.get("parent_organization_id", "") or ""
            ).strip()

            if parent_id not in self.organizations_by_id:
                parent_id = ""

            children_by_parent_id.setdefault(parent_id, []).append(
                organization_id
            )

        for child_ids in children_by_parent_id.values():
            child_ids.sort(key=self.organization_tree_sort_key)

        self.top_level_organization_bands = {
            organization_id: index % 2
            for index, organization_id in enumerate(
                children_by_parent_id.get("", [])
            )
        }

        self.suppress_tree_selection = True
        root_items = self.organization_tree.get_children("")

        if root_items:
            self.organization_tree.delete(*root_items)

        self.organization_tree.insert(
            "",
            "end",
            iid=ORGANIZATION_TREE_ROOT_ID,
            text="All organizations",
            open=True,
        )
        inserted_ids = set()
        query_is_active = bool(
            self.search_value.get().strip()
            or self.type_filter_value.get() != "All types"
            or self.school_filter_value.get() != "All school links"
            or self.year_filter_value is not None
            or self.location_filter_id
        )

        if (
            self.organization_lock_id
            and self.organization_lock_id in visible_ids
        ):
            self.insert_organization_record(
                ORGANIZATION_TREE_ROOT_ID,
                self.organization_lock_id,
                matching_ids,
                expanded_ids,
                query_is_active,
            )
            inserted_ids.add(self.organization_lock_id)
            self.insert_organization_children(
                self.organization_lock_id,
                self.organization_lock_id,
                children_by_parent_id,
                visible_ids,
                matching_ids,
                expanded_ids,
                query_is_active,
                inserted_ids,
            )
        elif not self.organization_lock_id:
            self.insert_organization_children(
                ORGANIZATION_TREE_ROOT_ID,
                "",
                children_by_parent_id,
                visible_ids,
                matching_ids,
                expanded_ids,
                query_is_active,
                inserted_ids,
            )

        for organization_id in sorted(
            visible_ids - inserted_ids,
            key=self.organization_tree_sort_key,
        ):
            self.insert_organization_record(
                ORGANIZATION_TREE_ROOT_ID,
                organization_id,
                matching_ids,
                expanded_ids,
                query_is_active,
            )

        tree_id = (
            selected_id
            if selected_id and self.organization_tree.exists(selected_id)
            else ORGANIZATION_TREE_ROOT_ID
        )
        self.organization_tree.selection_set(tree_id)
        self.organization_tree.focus(tree_id)
        self.organization_tree.see(tree_id)
        self.suppress_tree_selection = False

    def insert_organization_children(
        self,
        tree_parent_id,
        parent_organization_id,
        children_by_parent_id,
        visible_ids,
        matching_ids,
        expanded_ids,
        query_is_active,
        inserted_ids,
    ):
        for organization_id in children_by_parent_id.get(
            parent_organization_id,
            [],
        ):
            if (
                organization_id not in visible_ids
                or organization_id in inserted_ids
            ):
                continue

            inserted_ids.add(organization_id)
            self.insert_organization_record(
                tree_parent_id,
                organization_id,
                matching_ids,
                expanded_ids,
                query_is_active,
            )
            self.insert_organization_children(
                organization_id,
                organization_id,
                children_by_parent_id,
                visible_ids,
                matching_ids,
                expanded_ids,
                query_is_active,
                inserted_ids,
            )

    def insert_organization_record(
        self,
        tree_parent_id,
        organization_id,
        matching_ids,
        expanded_ids,
        query_is_active,
    ):
        organization = self.organizations_by_id[organization_id]
        name = str(
            organization.get("name", "") or "Unnamed organization"
        ).strip()
        location_label = self.cached_location_label(
            organization.get("location_id", "")
        )
        self.organization_tree.insert(
            tree_parent_id,
            "end",
            iid=organization_id,
            text=f"{name}\n{location_label}",
            open=(
                query_is_active
                or organization_id in expanded_ids
            ),
            tags=tuple(
                [
                    (
                        "nested_organization"
                        if str(
                            organization.get(
                                "parent_organization_id",
                                "",
                            )
                            or ""
                        ).strip()
                        else (
                            "top_level_odd"
                            if self.top_level_organization_bands.get(
                                organization_id,
                                0,
                            )
                            else "top_level_even"
                        )
                    ),
                    *(
                        []
                        if organization_id in matching_ids
                        else ["context"]
                    ),
                ]
            ),
        )

    def organization_tree_sort_key(self, organization_id):
        organization = self.organizations_by_id.get(
            organization_id,
            {},
        )
        return (
            str(organization.get("name", "") or "").casefold(),
            str(organization_id),
        )

    def organization_selected(self, event=None):
        if self.suppress_tree_selection:
            return

        selection = self.organization_tree.selection()

        if not selection:
            return

        tree_id = selection[0]
        organization_id = (
            ""
            if tree_id == ORGANIZATION_TREE_ROOT_ID
            else tree_id
        )

        if not organization_id and self.organization_lock_id:
            organization_id = self.organization_lock_id
            self.select_organization_tree_item(organization_id)

        if organization_id == self.current_organization_id:
            self.update_organization_lock_controls()
            return

        if not self.confirm_unsaved_organization_changes():
            self.select_organization_tree_item(
                self.current_organization_id
            )
            return

        if organization_id:
            self.load_organization(organization_id)
        else:
            self.clear_form()

        self.update_organization_lock_controls()

    def confirm_unsaved_organization_changes(self):
        if not self.form_dirty:
            return True

        self.autosave.flush()
        if not self.form_dirty:
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved organization changes",
            "Save changes before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return self.save_organization()

        self.form_dirty = False
        return True

    def select_organization_tree_item(self, organization_id=""):
        requested_id = str(organization_id or "").strip()
        tree_id = (
            requested_id
            if requested_id
            and self.organization_tree.exists(requested_id)
            else ORGANIZATION_TREE_ROOT_ID
        )
        self.suppress_tree_selection = True
        self.organization_tree.selection_set(tree_id)
        self.organization_tree.focus(tree_id)
        self.organization_tree.see(tree_id)
        self.suppress_tree_selection = False

    def toggle_selected_organization_branch(self, event=None):
        selection = self.organization_tree.selection()

        if not selection:
            return "break"

        tree_id = selection[0]

        if self.organization_tree.get_children(tree_id):
            self.organization_tree.item(
                tree_id,
                open=not bool(
                    self.organization_tree.item(tree_id, "open")
                ),
            )

        return "break"

    def organization_tree_motion(self, event):
        tree_id = self.organization_tree.identify_row(event.y)

        if tree_id == self.hovered_tree_id:
            return

        self.clear_organization_tree_hover()

        if not tree_id:
            return

        tags = list(self.organization_tree.item(tree_id, "tags"))

        if "hover" not in tags:
            tags.append("hover")

        self.organization_tree.item(tree_id, tags=tuple(tags))
        self.hovered_tree_id = tree_id

    def organization_tree_left(self, event=None):
        self.clear_organization_tree_hover()

    def clear_organization_tree_hover(self):
        if (
            not self.hovered_tree_id
            or not self.organization_tree.exists(
                self.hovered_tree_id
            )
        ):
            self.hovered_tree_id = ""
            return

        tags = [
            tag
            for tag in self.organization_tree.item(
                self.hovered_tree_id,
                "tags",
            )
            if tag != "hover"
        ]
        self.organization_tree.item(
            self.hovered_tree_id,
            tags=tuple(tags),
        )
        self.hovered_tree_id = ""

    def toggle_organization_lock(self):
        if self.organization_lock_id:
            return self.set_organization_lock("")

        requested_id = str(
            self.current_organization_id or ""
        ).strip()

        if not requested_id:
            return ""

        return self.set_organization_lock(requested_id)

    def set_organization_lock(
        self,
        organization_id="",
        notify=True,
        refresh_page=True,
    ):
        requested_id = str(organization_id or "").strip()

        if (
            self.organizations_by_id
            and requested_id not in self.organizations_by_id
        ):
            requested_id = ""

        previous_lock_id = self.organization_lock_id
        self.organization_lock_id = requested_id

        if refresh_page:
            self.refresh(self.current_organization_id)

        if requested_id:
            organization = self.organizations_by_id.get(
                requested_id,
                {},
            )
            organization_name = str(
                organization.get("name", "") or "selected organization"
            ).strip()
            self.status_command(
                f"Locked organization work to {organization_name}"
            )
        else:
            self.status_command("Showing all organizations")

        if (
            notify
            and previous_lock_id != self.organization_lock_id
            and self.scope_change_command is not None
        ):
            self.scope_change_command(self.organization_lock_id)

        return self.organization_lock_id

    def update_organization_lock_controls(self):
        if not hasattr(self, "organization_scope_button"):
            return

        current_id = str(
            self.current_organization_id or ""
        ).strip()
        locked_root = self.organizations_by_id.get(
            self.organization_lock_id
        )

        if locked_root is not None:
            organization_name = str(
                locked_root.get("name", "") or "Unnamed organization"
            ).strip()
            self.organization_scope_status_value.set(
                f"Showing only {organization_name}"
            )
            self.organization_scope_button.set_text("Unlock")
            self.organization_scope_button.set_colors(
                LOCKED_RED,
                LOCKED_RED_HOVER,
                TEXT_LIGHT,
            )
            self.organization_scope_button.set_enabled(True)
            self.organization_tree_frame.configure(
                highlightbackground=LOCKED_BORDER,
                highlightcolor=LOCKED_BORDER,
                highlightthickness=2,
            )
        else:
            self.organization_scope_status_value.set("All organizations")
            self.organization_scope_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.organization_scope_button.set_text(
                "Lock here" if current_id else "Select to lock"
            )
            self.organization_scope_button.set_enabled(bool(current_id))
            self.organization_tree_frame.configure(
                highlightbackground=BORDER_SOFT,
                highlightcolor=BORDER_SOFT,
                highlightthickness=1,
            )

        parent_change_allowed = not (
            self.organization_lock_id
            and current_id == self.organization_lock_id
        )

        if hasattr(self, "choose_parent_button"):
            self.choose_parent_button.set_enabled(parent_change_allowed)

        if hasattr(self, "clear_parent_button"):
            self.clear_parent_button.set_enabled(parent_change_allowed)

    def open_organization_search(self):
        OrganizationSelectionDialog(
            self,
            self.controller.list_organizations(),
            self.organization_search_selected,
            location_provider=self.controller.location_records,
        )

    def organization_search_selected(self, organization):
        organization_id = str(
            organization.get("record_id", "") or ""
        ).strip()

        if organization_id:
            if not organization_id_is_in_scope(
                organization_id,
                self.all_organizations,
                self.organization_lock_id,
            ):
                self.status_command(
                    "Unlock the current organization branch to open that organization"
                )
                return

            if not self.confirm_unsaved_organization_changes():
                return

            self.filter_updates_paused = True
            self.search_value.set("")
            self.type_filter_value.set("All types")
            self.school_filter_value.set("All school links")
            self.year_filter_value = None
            self.location_filter_id = ""
            self.location_filter_value.set("All places")
            self.filter_updates_paused = False
            self.refresh(organization_id, force_load=True)

    def refresh_location_picker(self, selected_location_id=""):
        self.selected_location_id = str(
            selected_location_id or ""
        ).strip()
        self.location_value.set(
            self.cached_location_label(self.selected_location_id)
        )

    def cached_location_label(self, location_id):
        selected_id = str(location_id or "").strip()

        if not selected_id:
            return "No location selected"

        return self.location_labels_by_id.get(
            selected_id,
            "Unknown location",
        )

    def refresh_school_link(self, selected_school_id=None):
        if selected_school_id is not None:
            self.selected_school_id = str(
                selected_school_id or ""
            ).strip()

        school = self.controller.school_by_id(
            self.selected_school_id
        )
        is_linked = school is not None

        if not is_linked:
            self.selected_school_id = ""

        self.link_school_value.set(is_linked)
        self.school_value.set(
            self.controller.school_label(
                self.selected_school_id
            )
            if is_linked
            else "Choose a school"
        )
        self.choose_school_button.set_enabled(
            bool(self.link_school_value.get())
        )
        self.name_field.control.set_enabled(not is_linked)
        self.type_picker.configure(
            state="disabled" if is_linked else "readonly"
        )

        if is_linked:
            self.name_value.set(
                str(school.get("name", "") or "")
            )
            self.type_value.set("School")

        if hasattr(self, "update_also_location_state"):
            self.update_also_location_state()

    def toggle_school_link(self):
        if not self.link_school_value.get():
            self.selected_school_id = ""
            self.refresh_school_link("")
            return

        if not self.selected_school_id:
            self.open_school_dialog()

    def available_schools_for_link(self):
        linked_school_ids = {
            str(organization.get("school_id", "") or "").strip()
            for organization in self.controller.list_organizations()
            if str(
                organization.get("record_id", "") or ""
            ).strip()
            != str(self.current_organization_id or "").strip()
            and str(organization.get("school_id", "") or "").strip()
        }
        return [
            school
            for school in self.controller.school_records()
            if str(school.get("record_id", "") or "").strip()
            not in linked_school_ids
        ]

    def open_school_dialog(self):
        if not self.link_school_value.get():
            self.link_school_value.set(True)

        OrganizationSchoolSelectionDialog(
            self,
            self.available_schools_for_link(),
            self.selected_school_id,
            self.school_selected,
            self.school_selection_cancelled,
        )

    def school_selection_cancelled(self):
        if self.selected_school_id:
            return

        self.link_school_value.set(False)
        self.refresh_school_link("")

    def school_selected(self, school):
        if not isinstance(school, dict):
            return

        self.selected_school_id = str(
            school.get("record_id", "") or ""
        ).strip()
        self.link_school_value.set(True)
        self.refresh_school_link()
        self.mark_form_dirty()

    def refresh_parent_picker(self, selected_parent_id=""):
        self.selected_parent_organization_id = str(
            selected_parent_id or ""
        ).strip()
        self.parent_value.set(
            organization_context_label(
                self.selected_parent_organization_id,
                self.controller.list_organizations(),
            )
            if self.selected_parent_organization_id
            else "No parent organization"
        )

    def open_location_dialog(self):
        OrganizationLocationSelectionDialog(
            self,
            self.controller.location_records(),
            self.location_selected,
            self.selected_location_id,
            dialog_title="Select organization location",
            action_text="Use location",
            allow_clear=True,
            create_location_command=(
                self.controller.create_placeholder_location
            ),
        )

    def location_selected(self, location):
        if isinstance(location, dict):
            location_id = str(
                location.get("record_id", "") or ""
            ).strip()

            if location_id:
                self.location_labels_by_id[location_id] = str(
                    location.get("label", "")
                    or location.get("name", "")
                    or "Unknown location"
                ).strip()

        self.refresh_location_picker(
            location.get("record_id", "")
            if isinstance(location, dict)
            else ""
        )
        self.mark_form_dirty()

    def clear_location(self):
        self.refresh_location_picker("")
        self.mark_form_dirty()

    def open_parent_dialog(self):
        if (
            self.organization_lock_id
            and self.current_organization_id
            == self.organization_lock_id
        ):
            messagebox.showinfo(
                "Organization branch is locked",
                "Unlock this organization before moving the branch itself.",
                parent=self,
            )
            return

        allowed_parent_ids = {
            option["record_id"]
            for option in self.controller.parent_options(
                self.current_organization_id or "",
            )
            if option["record_id"]
        }
        parent_candidates = [
            organization
            for organization in self.controller.list_organizations()
            if (
                organization.get("record_id") in allowed_parent_ids
                and organization_id_is_in_scope(
                    organization.get("record_id", ""),
                    self.all_organizations,
                    self.organization_lock_id,
                )
            )
        ]
        OrganizationSelectionDialog(
            self,
            parent_candidates,
            self.parent_selected,
            location_provider=self.controller.location_records,
        )

    def parent_selected(self, organization):
        parent_id = str(
            organization.get("record_id", "") or ""
        ).strip()
        self.refresh_parent_picker(
            parent_id
        )

        if not self.selected_location_id:
            parent = self.controller.get_organization(parent_id)

            if parent is not None:
                self.refresh_location_picker(
                    parent.get("location_id", "")
                )

        self.mark_form_dirty()

    def clear_parent(self):
        if (
            self.organization_lock_id
            and self.current_organization_id
            == self.organization_lock_id
        ):
            messagebox.showinfo(
                "Organization branch is locked",
                "Unlock this organization before moving the branch itself.",
                parent=self,
            )
            return

        self.refresh_parent_picker("")
        self.mark_form_dirty()

    def load_organization(self, record_id):
        organization = self.controller.get_organization(record_id)

        if organization is None:
            return

        self.form_updates_paused = True
        self.current_organization_id = record_id
        self.loaded_parent_organization_id = str(
            organization.get("parent_organization_id", "") or ""
        ).strip()
        self.name_value.set(str(organization.get("name", "") or ""))
        self.type_value.set(
            str(organization.get("organization_type", "") or ORGANIZATION_TYPES[0])
        )
        self.also_location_value.set(
            bool(organization.get("also_location"))
            or self.type_value.get() == "School"
        )
        self.update_also_location_state()
        self.has_shop_value.set(bool(organization.get("has_shop")))
        self.shop_inventory = normalize_shop_inventory(
            organization.get("shop_inventory", {})
        )
        self.famous_organization_value.set(
            bool(organization.get("famous_organization"))
        )
        self.is_faction_value.set(bool(organization.get("is_faction")))
        self.faction_color_value.set(
            str(organization.get("faction_color", "#808080") or "#808080")
        )
        self.has_storeroom_value.set(
            bool(organization.get("has_storeroom"))
        )
        self.storeroom_inventory = normalize_storeroom_inventory(
            organization.get("storeroom_inventory", [])
        )
        self.includes_library_value.set(
            bool(organization.get("includes_library"))
        )
        self.library_open_to_outsiders_value.set(
            bool(organization.get("library_open_to_outsiders"))
        )
        self.extinct_value.set(bool(organization.get("extinct")))
        extinction_year, extinction_month, extinction_day = (
            split_world_event_date(
                organization.get("extinction_date", "")
            )
        )
        self.extinction_year_value.set(extinction_year)
        self.extinction_month_value.set(extinction_month)
        self.extinction_day_value.set(extinction_day)
        self.update_shop_page_visibility()
        self.update_storeroom_page_visibility()
        self.update_library_state()
        self.update_extinction_date_visibility()
        self.link_school_value.set(
            bool(str(organization.get("school_id", "") or "").strip())
        )
        self.refresh_school_link(organization.get("school_id", ""))
        self.refresh_location_picker(organization.get("location_id", ""))
        self.refresh_parent_picker(
            organization.get("parent_organization_id", "")
        )
        self.overview_control.text.delete("1.0", "end")
        self.overview_control.text.insert(
            "1.0",
            str(organization.get("overview", "") or ""),
        )
        self.notes_control.text.delete("1.0", "end")
        self.notes_control.text.insert(
            "1.0",
            str(organization.get("notes", "") or ""),
        )
        self.tags_editor.set_tags(organization.get("tags", []))
        self.organization_events = normalize_organization_events(
            organization.get("events", [])
        )
        self.organization_jobs = normalize_organization_jobs(
            organization.get("jobs", [])
        )
        self.hydrated_editor_pages = {"details"}
        self.overview_control.text.edit_modified(False)
        self.notes_control.text.edit_modified(False)
        self.refresh_event_list()
        self.hydrate_editor_page(self.active_editor_page)
        self.form_updates_paused = False
        self.form_dirty = False
        self.set_editor_state(True, False)
        self.update_organization_lock_controls()
        self.status_command(
            f"Loaded organization {organization.get('name', 'Unnamed')}"
        )

    def clear_form(self):
        self.form_updates_paused = True
        self.current_organization_id = None
        self.loaded_parent_organization_id = ""
        self.name_value.set("")
        self.type_value.set(ORGANIZATION_TYPES[0])
        self.also_location_value.set(False)
        self.update_also_location_state()
        self.has_shop_value.set(False)
        self.shop_inventory = normalize_shop_inventory({})
        self.famous_organization_value.set(False)
        self.is_faction_value.set(False)
        self.faction_color_value.set("#808080")
        self.has_storeroom_value.set(False)
        self.storeroom_inventory = normalize_storeroom_inventory([])
        self.includes_library_value.set(False)
        self.library_open_to_outsiders_value.set(False)
        self.extinct_value.set(False)
        self.extinction_year_value.set("")
        self.extinction_month_value.set("")
        self.extinction_day_value.set("")
        self.update_shop_page_visibility()
        self.update_storeroom_page_visibility()
        self.update_library_state()
        self.update_extinction_date_visibility()
        self.link_school_value.set(False)
        self.refresh_school_link("")
        self.refresh_location_picker()
        self.refresh_parent_picker()
        self.overview_control.text.delete("1.0", "end")
        self.notes_control.text.delete("1.0", "end")
        self.tags_editor.set_tags([])
        self.organization_events = normalize_organization_events([])
        self.organization_jobs = normalize_organization_jobs([])
        self.hydrated_editor_pages = {"details"}
        self.overview_control.text.edit_modified(False)
        self.notes_control.text.edit_modified(False)
        self.refresh_event_list()
        self.hydrate_editor_page(self.active_editor_page)
        self.form_updates_paused = False
        self.form_dirty = False
        self.set_editor_state(False, False)
        self.update_organization_lock_controls()

    def set_editor_state(self, has_organization, has_changes=False):
        enabled = bool(has_organization)
        self.delete_button.set_enabled(enabled)
        self.revert_button.set_enabled(
            enabled and bool(has_changes)
        )
        self.save_button.set_enabled(
            enabled and bool(has_changes)
        )

    def create_organization(self):
        if not self.confirm_unsaved_organization_changes():
            return

        parent_id = (
            self.current_organization_id
            if organization_id_is_in_scope(
                self.current_organization_id,
                self.all_organizations,
                self.organization_lock_id,
            )
            else self.organization_lock_id
        )

        try:
            created = self.controller.create_default_organization(
                parent_organization_id=parent_id,
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot create organization",
                str(error),
                parent=self,
            )
            return

        self.filter_updates_paused = True
        self.search_value.set("")
        self.type_filter_value.set("All types")
        self.school_filter_value.set("All school links")
        self.year_filter_value = None
        self.location_filter_id = ""
        self.location_filter_value.set("All places")
        self.filter_updates_paused = False
        self.organization_created(created)

    def organization_created(self, created):
        self.refresh(created["record_id"], force_load=True)
        self.status_command(f"Created organization {created['name']}")

    def revert_organization(self):
        if not self.current_organization_id:
            return

        self.form_dirty = False
        self.refresh(
            self.current_organization_id,
            force_load=True,
        )
        self.status_command("Organization changes reverted")

    def extinction_date_from_form(self):
        extinct_value = getattr(self, "extinct_value", None)

        if extinct_value is None or not extinct_value.get():
            return ""

        year_value = getattr(self, "extinction_year_value", None)
        month_value = getattr(self, "extinction_month_value", None)
        day_value = getattr(self, "extinction_day_value", None)
        year = year_value.get().strip() if year_value is not None else ""
        month = month_value.get().strip() if month_value is not None else ""
        day = day_value.get().strip() if day_value is not None else ""

        if not year and (month or day):
            raise ValueError(
                "Extinction date month and day require a year."
            )

        if day and not month:
            raise ValueError("Extinction date day requires a month.")

        extinction_date = year

        if month:
            extinction_date += f"-{month}"

        if day:
            extinction_date += f"-{day}"

        return normalize_organization_extinction_date(
            extinction_date,
            True,
        )

    def update_organization_required_fields(self):
        valid = bool(self.name_value.get().strip())
        self.name_field.control.set_invalid(not valid)
        return valid

    def autosave_organization(self):
        return self.save_organization(silent=True, refresh_after=False)

    def save_organization(self, silent=False, refresh_after=True):
        if (
            self.link_school_value.get()
            and not self.selected_school_id
        ):
            self.link_school_value.set(False)
            self.refresh_school_link("")

        has_shop_value = getattr(self, "has_shop_value", None)
        has_storeroom_value = getattr(
            self,
            "has_storeroom_value",
            None,
        )
        famous_organization_value = getattr(
            self,
            "famous_organization_value",
            None,
        )
        is_faction_value = getattr(self, "is_faction_value", None)
        faction_color_value = getattr(self, "faction_color_value", None)
        includes_library_value = getattr(
            self,
            "includes_library_value",
            None,
        )
        library_open_to_outsiders_value = getattr(
            self,
            "library_open_to_outsiders_value",
            None,
        )
        extinct_value = getattr(self, "extinct_value", None)
        also_location_value = getattr(
            self,
            "also_location_value",
            None,
        )

        if not self.update_organization_required_fields():
            self.status_command("Complete the required fields outlined in red")
            return False
        try:
            extinction_date = OrganizationPage.extinction_date_from_form(
                self
            )
        except ValueError as error:
            if silent:
                self.status_command(f"Could not save organization: {error}")
            else:
                messagebox.showerror(
                    "Cannot save organization",
                    str(error),
                    parent=self,
                )
            return False

        values = {
            "name": self.name_value.get(),
            "organization_type": self.type_value.get(),
            "location_id": self.selected_location_id,
            "parent_organization_id": (
                self.selected_parent_organization_id
            ),
            "school_id": self.selected_school_id,
            "also_location": (
                bool(also_location_value.get())
                if also_location_value is not None
                else self.type_value.get() == "School"
            ),
            "has_shop": (
                bool(has_shop_value.get())
                if has_shop_value is not None
                else False
            ),
            "shop_inventory": getattr(
                self,
                "shop_inventory",
                normalize_shop_inventory({}),
            ),
            "famous_organization": (
                bool(famous_organization_value.get())
                if famous_organization_value is not None
                else False
            ),
            "is_faction": (
                bool(is_faction_value.get())
                if is_faction_value is not None
                else False
            ),
            "faction_color": (
                str(faction_color_value.get() or "#808080")
                if faction_color_value is not None
                else "#808080"
            ),
            "has_storeroom": (
                bool(has_storeroom_value.get())
                if has_storeroom_value is not None
                else False
            ),
            "storeroom_inventory": getattr(
                self,
                "storeroom_inventory",
                normalize_storeroom_inventory([]),
            ),
            "includes_library": (
                bool(includes_library_value.get())
                if includes_library_value is not None
                else False
            ),
            "library_open_to_outsiders": (
                bool(library_open_to_outsiders_value.get())
                if library_open_to_outsiders_value is not None
                else False
            ),
            "extinct": (
                bool(extinct_value.get())
                if extinct_value is not None
                else False
            ),
            "extinction_date": extinction_date,
            "overview": self.overview_control.text.get("1.0", "end-1c"),
            "notes": self.notes_control.text.get("1.0", "end-1c"),
            "tags": (
                self.tags_editor.get_tags()
                if hasattr(self, "tags_editor")
                else []
            ),
            "events": self.organization_events,
            "jobs": self.organization_jobs,
        }
        parent_changed = bool(
            self.current_organization_id
            and self.loaded_parent_organization_id
            != str(self.selected_parent_organization_id or "").strip()
        )

        try:
            if self.current_organization_id:
                updated = self.controller.update_organization(
                    self.current_organization_id,
                    values,
                )
            else:
                updated = self.controller.create_organization(
                    values
                )
        except (KeyError, TypeError, ValueError) as error:
            if silent:
                self.status_command(f"Could not save organization: {error}")
            else:
                messagebox.showerror(
                    "Cannot save organization",
                    str(error),
                    parent=self,
                )
            return False

        if hasattr(self, "search_value"):
            visible_ids = {
                str(organization.get("record_id", "") or "").strip()
                for organization in self.controller.search_organizations(
                    self.search_value.get(),
                    self.type_filter_value.get(),
                    self.year_filter_value,
                    self.location_filter_id,
                    self.school_filter_key(),
                )
            }

            if updated["record_id"] not in visible_ids:
                self.filter_updates_paused = True
                self.search_value.set("")
                self.type_filter_value.set("All types")
                self.school_filter_value.set("All school links")
                self.year_filter_value = None
                self.location_filter_id = ""
                self.location_filter_value.set("All places")
                self.filter_updates_paused = False

        if parent_changed and self.organization_lock_id:
            self.organization_lock_id = ""

            if self.scope_change_command is not None:
                self.scope_change_command("")

        self.form_dirty = False
        self.current_organization_id = updated["record_id"]
        self.loaded_parent_organization_id = str(
            updated.get("parent_organization_id", "") or ""
        ).strip()
        self.revert_button.set_enabled(False)
        if refresh_after or parent_changed:
            self.refresh(updated["record_id"], force_load=True)
            events_changed_command = getattr(
                self,
                "events_changed_command",
                None,
            )
            if events_changed_command is not None:
                events_changed_command()
        self.status_command(f"Saved organization {updated['name']}")
        return True

    def delete_organization(self):
        organization = self.controller.get_organization(
            self.current_organization_id
        )

        if organization is None:
            return

        if not messagebox.askyesno(
            "Delete organization",
            f"Permanently delete {organization.get('name', 'this organization')}?",
            parent=self,
        ):
            return

        try:
            self.controller.delete_organization(
                self.current_organization_id
            )
        except (KeyError, ValueError) as error:
            messagebox.showerror(
                "Cannot delete organization",
                str(error),
                parent=self,
            )
            return
        self.current_organization_id = None
        self.form_dirty = False

        if self.organization_lock_id == organization.get("record_id"):
            self.organization_lock_id = ""

            if self.scope_change_command is not None:
                self.scope_change_command("")

        self.refresh()
        self.status_command(
            f"Deleted organization {organization.get('name', 'Unnamed')}"
        )

    def refresh_event_list(self):
        if not hasattr(self, "event_list"):
            return

        self.event_list.delete(0, "end")
        people_labels_by_id = {
            str(option.get("value", "") or "").strip(): str(
                option.get("label", "") or "Unknown person"
            ).strip()
            for option in (
                self.event_controller.people_options()
                if self.event_controller is not None
                else []
            )
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
        }

        for index, event in enumerate(self.organization_events):
            date_text = format_line_item_date(
                event.get("date")
                or (
                    str(event.get("year"))
                    if event.get("year") is not None
                    else ""
                ),
                unknown="Date required",
            )
            event_time = str(event.get("time", "") or "").strip()

            if event_time:
                date_text = f"{date_text} {event_time}"

            person_ids = list(event.get("person_ids", []))
            people_count = len(person_ids)

            if people_count == 1:
                people_text = (
                    " · "
                    + people_labels_by_id.get(
                        str(person_ids[0] or "").strip(),
                        "Unknown person",
                    )
                )
            elif people_count > 1:
                people_text = f" · {people_count} people"
            else:
                people_text = ""
            self.event_list.insert(
                "end",
                f"{date_text} — {event['title']}{people_text}",
            )
            self.event_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        if self.organization_events:
            self.event_list.selection_set(0)

    def selected_event_index(self):
        selected = self.event_list.curselection()

        if not selected:
            return None

        return int(selected[0])

    def add_event(self):
        OrganizationEventDialog(
            self,
            self.save_added_event,
            event_controller=self.event_controller,
        )

    def save_added_event(self, event):
        self.organization_events = normalize_organization_events(
            [*self.organization_events, event]
        )
        self.refresh_event_list()
        self.event_list.selection_clear(0, "end")
        self.event_list.selection_set(
            len(self.organization_events) - 1
        )
        self.persist_organization_event_changes()

    def edit_selected_event(self, event=None):
        selected_index = self.selected_event_index()

        if selected_index is None:
            return

        OrganizationEventDialog(
            self,
            self.save_edited_event,
            self.organization_events[selected_index],
            self.event_controller,
        )

    def save_edited_event(self, event):
        event_id = event["record_id"]
        self.organization_events = normalize_organization_events(
            [
                (
                    event
                    if stored_event["record_id"] == event_id
                    else stored_event
                )
                for stored_event in self.organization_events
            ]
        )
        self.refresh_event_list()

        for index, stored_event in enumerate(
            self.organization_events
        ):
            if stored_event["record_id"] == event_id:
                self.event_list.selection_clear(0, "end")
                self.event_list.selection_set(index)
                break

        self.persist_organization_event_changes()

    def remove_selected_event(self):
        selected_index = self.selected_event_index()

        if selected_index is None:
            return

        selected_event = self.organization_events[selected_index]

        if (
            selected_event["event_type"]
            == ORGANIZATION_EVENT_FOUNDING
        ):
            messagebox.showinfo(
                "Founding cannot be removed",
                "The founding event must remain the first organization event.",
                parent=self,
            )
            return

        self.organization_events = normalize_organization_events(
            [
                event
                for index, event in enumerate(
                    self.organization_events
                )
                if index != selected_index
            ]
        )
        self.refresh_event_list()
        self.persist_organization_event_changes()

    def persist_organization_event_changes(self):
        self.mark_form_dirty()

    def refresh_job_list(self, selected_job_id=""):
        if not hasattr(self, "job_list"):
            return

        retained_job_id = str(selected_job_id or "").strip()

        if not retained_job_id:
            selected_index = self.selected_job_index()

            if (
                selected_index is not None
                and selected_index < len(self.organization_jobs)
            ):
                retained_job_id = self.organization_jobs[
                    selected_index
                ]["record_id"]

        self.job_list.delete(0, "end")
        selected_index = None

        for index, organization_job in enumerate(
            self.organization_jobs
        ):
            status = self.controller.organization_job_status(
                organization_job
            )
            self.job_list.insert(
                "end",
                (
                    f"{organization_job['title']} · "
                    f"opened {organization_job['opened_date']}"
                    + (
                        f" · closed {organization_job['closed_date']}"
                        if organization_job["closed_date"]
                        else ""
                    )
                    + " · "
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

            if organization_job["record_id"] == retained_job_id:
                selected_index = index

        if self.organization_jobs:
            if selected_index is None:
                selected_index = 0

            self.job_list.selection_set(selected_index)
            self.job_list.see(selected_index)

        self.refresh_job_timeline()

    def selected_job_index(self):
        selected = self.job_list.curselection()

        if not selected:
            return None

        return int(selected[0])

    def job_selected(self, event=None):
        self.refresh_job_timeline()

    def refresh_job_timeline(self):
        if not hasattr(self, "job_timeline_list"):
            return

        self.job_timeline_list.delete(0, "end")
        if hasattr(self, "appointment_button"):
            self.appointment_button.set_enabled(False)
        selected_index = self.selected_job_index()

        if (
            selected_index is None
            or not 0 <= selected_index < len(self.organization_jobs)
        ):
            self.visible_job_timeline = []
            self.job_timeline_value.set(
                "Select a job to see its timeline"
            )
            return

        selected_job = self.organization_jobs[selected_index]
        self.visible_job_timeline = (
            self.controller.organization_job_yearly_timeline(
                selected_job
            )
        )
        self.job_timeline_value.set(
            f"{selected_job['title']} · timeline"
        )

        if not self.visible_job_timeline:
            self.job_timeline_list.insert(
                "end",
                "No one has held this role.",
            )
            return

        for index, timeline_entry in enumerate(
            self.visible_job_timeline
        ):
            self.job_timeline_list.insert(
                "end",
                timeline_entry["label"],
            )
            self.job_timeline_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

    def job_timeline_selection_changed(self, event=None):
        selected = self.job_timeline_list.curselection()
        valid_selection = bool(
            selected
            and 0 <= int(selected[0]) < len(self.visible_job_timeline)
        )

        if hasattr(self, "appointment_button"):
            self.appointment_button.set_enabled(valid_selection)

    def job_timeline_clicked(self, event=None):
        if not getattr(self, "visible_job_timeline", []):
            return

        selected = self.job_timeline_list.curselection()
        selected_index = int(selected[0]) if selected else -1

        if selected_index < 0 and event is not None:
            selected_index = int(
                self.job_timeline_list.nearest(event.y)
            )
            self.job_timeline_list.selection_clear(0, "end")
            self.job_timeline_list.selection_set(selected_index)

        if not 0 <= selected_index < len(self.visible_job_timeline):
            return

        timeline_entry = self.visible_job_timeline[selected_index]

        selected_job_index = self.selected_job_index()

        if selected_job_index is None or self.event_controller is None:
            return

        organization = self.organizations_by_id.get(
            str(self.current_organization_id or "")
        )

        if organization is None:
            return

        appointment_window = self.job_appointment_window(selected_index)
        existing_appointment = self.job_appointment_values(
            timeline_entry
        )
        existing_raises = self.job_appointment_raises(
            existing_appointment
        )
        default_salary = (
            existing_appointment.get("salary")
            if existing_appointment
            else self.controller.last_salary_for_organization_job(
                self.organization_jobs[selected_job_index]["record_id"],
                (
                    appointment_window["start_year"],
                    appointment_window["start_month"],
                    appointment_window["start_day"],
                ),
            )
        )
        JobAppointmentDialog(
            self,
            self.event_controller.people_provider(),
            organization,
            self.organization_jobs[selected_job_index],
            appointment_window,
            self.save_job_appointment,
            availability_command=(
                self.event_controller.person_job_availability
            ),
            existing_appointment=existing_appointment,
            default_salary=default_salary,
            existing_raises=existing_raises,
        )

    def job_appointment_window(self, selected_index):
        timeline_entry = self.visible_job_timeline[selected_index]
        window_start = (
            timeline_entry["start_year"],
            timeline_entry["start_month"],
            timeline_entry["start_day"],
        )
        window_end = (
            timeline_entry["end_year"],
            timeline_entry["end_month"],
            timeline_entry["end_day"],
        )
        open_ended = bool(timeline_entry.get("open_ended", False))

        if not timeline_entry.get("vacant"):
            if (
                selected_index > 0
                and self.visible_job_timeline[
                    selected_index - 1
                ].get("vacant")
            ):
                previous_entry = self.visible_job_timeline[
                    selected_index - 1
                ]
                window_start = (
                    previous_entry["start_year"],
                    previous_entry["start_month"],
                    previous_entry["start_day"],
                )

            if (
                selected_index + 1 < len(self.visible_job_timeline)
                and self.visible_job_timeline[
                    selected_index + 1
                ].get("vacant")
            ):
                next_entry = self.visible_job_timeline[
                    selected_index + 1
                ]
                window_end = (
                    next_entry["end_year"],
                    next_entry["end_month"],
                    next_entry["end_day"],
                )
                open_ended = bool(next_entry.get("open_ended", False))

        return {
            "start_year": window_start[0],
            "start_month": window_start[1],
            "start_day": window_start[2],
            "end_year": window_end[0],
            "end_month": window_end[1],
            "end_day": window_end[2],
            "open_ended": open_ended,
        }

    def job_appointment_values(self, timeline_entry):
        if timeline_entry.get("vacant"):
            return {}

        event_ids = list(timeline_entry.get("event_ids", []) or [])
        stored_event = (
            self.event_controller.get_event(event_ids[0])
            if event_ids
            else None
        )

        if stored_event is not None:
            return deepcopy(stored_event)

        start_date = (
            f"{timeline_entry['start_year']}-"
            f"{timeline_entry['start_month']:02d}-"
            f"{timeline_entry['start_day']:02d}"
        )
        end_date = ""

        if not timeline_entry.get("open_ended"):
            end_date = (
                f"{timeline_entry['end_year']}-"
                f"{timeline_entry['end_month']:02d}-"
                f"{timeline_entry['end_day']:02d}"
            )

        return {
            "record_id": "",
            "event_type": "started_job",
            "date": start_date,
            "job_end_date": end_date,
            "person_ids": list(
                timeline_entry.get("person_ids", []) or []
            ),
            "special_appointment_name": str(
                timeline_entry.get("special_appointment_name", "") or ""
            ),
            "salary": deepcopy(timeline_entry.get("salary")),
            "job_assignment_id": str(
                (timeline_entry.get("assignment_ids", []) or [""])[0]
            ),
            "job_concurrent": bool(
                timeline_entry.get("concurrent", False)
            ),
            "died_in_office": bool(
                timeline_entry.get("died_in_office", False)
            ),
            "died_in_office_death_event_id": str(
                timeline_entry.get(
                    "died_in_office_death_event_id",
                    "",
                )
                or ""
            ),
            "died_in_office_created_death_event": bool(
                timeline_entry.get(
                    "died_in_office_created_death_event",
                    False,
                )
            ),
        }

    def job_appointment_raises(self, appointment):
        if not appointment:
            return []

        appointment_event_id = str(
            appointment.get("record_id", "") or ""
        ).strip()
        assignment_id = str(
            appointment.get("job_assignment_id", "") or ""
        ).strip()
        raises = []

        for event in self.event_controller.list_events():
            if event.get("event_type") != "received_raise":
                continue

            if appointment_event_id and str(
                event.get("source_job_event_id", "") or ""
            ).strip() == appointment_event_id:
                raises.append(
                    {
                        "record_id": event["record_id"],
                        "date": event.get("date", ""),
                        "salary": deepcopy(event.get("salary")),
                    }
                )
                continue

            if assignment_id and str(
                event.get("job_assignment_id", "") or ""
            ).strip() == assignment_id:
                raises.append(
                    {
                        "record_id": event["record_id"],
                        "date": event.get("date", ""),
                        "salary": deepcopy(event.get("salary")),
                    }
                )

        return raises

    def person_death_event(self, person_id):
        selected_person_id = str(person_id or "").strip()
        death_events = [
            event
            for event in self.event_controller.list_events()
            if selected_person_id in death_event_person_ids(event)
        ]

        if not death_events:
            return None

        death_events.sort(
            key=world_event_sort_key
        )
        return death_events[-1]

    def person_death_date(self, person):
        if not isinstance(person, dict):
            return ""

        death_event = self.person_death_event(
            person.get("record_id", "")
        )

        if death_event is not None:
            return str(death_event.get("date", "") or "").strip()

        year = str(person.get("death_year", "") or "").strip()
        month = str(person.get("death_month", "") or "").strip()
        day = str(person.get("death_day", "") or "").strip()
        date_text = year

        if month:
            date_text += f"-{month}"

        if day:
            date_text += f"-{day}"

        return date_text

    def resolve_died_in_office_date(self, appointment_values):
        if not appointment_values.get("died_in_office"):
            return appointment_values.get("end_date", "")

        person = appointment_values.get("person")
        end_date = str(
            appointment_values.get("end_date", "") or ""
        ).strip()

        if person is None:
            raise ValueError(
                "Died in office is available only for an individual."
            )

        if not end_date:
            raise ValueError(
                "Died in office requires an appointment end date."
            )

        existing_death_date = self.person_death_date(person)

        if not existing_death_date or existing_death_date == end_date:
            return end_date

        choice = messagebox.askyesnocancel(
            "Death date differs",
            (
                f"{person.get('displayed_name', 'This individual')} already "
                f"has a death date of {existing_death_date}.\n\n"
                f"Choose Yes to change the death date to {end_date}.\n"
                f"Choose No to change the job end date to "
                f"{existing_death_date}.\n"
                "Choose Cancel to return to the appointment."
            ),
            parent=self,
        )

        if choice is None:
            return None

        return end_date if choice else existing_death_date

    def save_job_appointment(self, appointment_values):
        selected_job_index = self.selected_job_index()

        if selected_job_index is None or self.event_controller is None:
            return False

        organization = self.organizations_by_id.get(
            str(self.current_organization_id or "")
        )

        if organization is None:
            return False

        organization_job = self.organization_jobs[selected_job_index]
        existing_appointment = deepcopy(
            appointment_values.get("existing_appointment", {})
        )
        person = appointment_values.get("person")
        person_ids = (
            [person["record_id"]]
            if isinstance(person, dict)
            else []
        )

        try:
            resolved_end_date = self.resolve_died_in_office_date(
                appointment_values
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save appointment",
                str(error),
                parent=self,
            )
            return False

        if resolved_end_date is None:
            return False

        organization_name = str(
            organization.get("name", "") or "Unnamed organization"
        ).strip()
        event_id = str(
            existing_appointment.get("record_id", "") or uuid4()
        ).strip()
        assignment_id = str(
            existing_appointment.get("job_assignment_id", "")
            or self.event_controller.started_job_assignment_id(event_id)
        ).strip()
        title = f"{organization_job['title']} at {organization_name}"
        event_values = {
            "record_id": event_id,
            "event_type": "started_job",
            "title": title,
            "date": appointment_values["start_date"],
            "description": str(
                existing_appointment.get("description", "") or ""
            ),
            "person_ids": person_ids,
            "eminence_person_ids": [],
            "eminence_skills": {},
            "period_names": [],
            "location_ids": [],
            "locked_location_ids": [],
            "organization_id": organization["record_id"],
            "organization_name": organization_name,
            "organization_job_id": organization_job["record_id"],
            "job_title": organization_job["title"],
            "job_assignment_id": assignment_id,
            "job_end_date": resolved_end_date,
            "salary": appointment_values["salary"],
            "special_appointment_name": appointment_values.get(
                "special_appointment_name",
                "",
            ),
            "job_concurrent": bool(
                appointment_values.get("job_concurrent", False)
            ),
            "died_in_office": bool(
                appointment_values.get("died_in_office", False)
            ),
            "died_in_office_death_event_id": str(
                (
                    existing_appointment.get(
                        "died_in_office_death_event_id",
                        "",
                    )
                    if appointment_values.get("died_in_office", False)
                    else ""
                )
                or ""
            ).strip(),
            "died_in_office_created_death_event": bool(
                existing_appointment.get(
                    "died_in_office_created_death_event",
                    False,
                )
                if appointment_values.get("died_in_office", False)
                else False
            ),
        }
        database = self.event_controller.database
        database_data = deepcopy(database.data)
        database_dirty = database.dirty
        database_revision = database.revision

        try:
            stored_appointment = self.event_controller.get_event(event_id)

            if stored_appointment is None:
                saved_event = self.event_controller.create_event(
                    event_values
                )
            else:
                saved_event = self.event_controller.update_event(
                    event_id,
                    event_values,
                )

            death_event_id = ""

            if event_values["died_in_office"]:
                existing_death_event = self.person_death_event(
                    person["record_id"]
                )
                created_death_event = bool(
                    existing_appointment.get(
                        "died_in_office_created_death_event",
                        False,
                    )
                )

                if existing_death_event is None:
                    created_death_event = True
                    saved_death_event = self.event_controller.create_event(
                        {
                            "event_type": "died",
                            "title": "death",
                            "date": resolved_end_date,
                            "description": (
                                f"Died while serving as "
                                f"{organization_job['title']} at "
                                f"{organization_name}."
                            ),
                            "person_ids": person_ids,
                            "eminence_person_ids": [],
                            "eminence_skills": {},
                            "period_names": [],
                            "location_ids": [],
                            "locked_location_ids": [],
                        },
                        replace_existing_death=True,
                    )
                else:
                    saved_death_event = self.event_controller.update_event(
                        existing_death_event["record_id"],
                        {
                            "date": resolved_end_date,
                        },
                        replace_existing_death=True,
                    )

                death_event_id = saved_death_event["record_id"]
                saved_event = self.event_controller.update_event(
                    saved_event["record_id"],
                    {
                        "died_in_office": True,
                        "died_in_office_death_event_id": death_event_id,
                        "died_in_office_created_death_event": (
                            created_death_event
                        ),
                    },
                )
            elif (
                existing_appointment.get("died_in_office")
                and existing_appointment.get(
                    "died_in_office_death_event_id"
                )
                and existing_appointment.get(
                    "died_in_office_created_death_event",
                    False,
                )
            ):
                generated_death_id = str(
                    existing_appointment.get(
                        "died_in_office_death_event_id",
                        "",
                    )
                    or ""
                ).strip()

                if self.event_controller.get_event(generated_death_id):
                    self.event_controller.delete_event(generated_death_id)

            existing_raises = {
                raise_record["record_id"]: raise_record
                for raise_record in self.job_appointment_raises(saved_event)
            }
            requested_raises = {
                str(raise_record.get("record_id", "") or uuid4()): deepcopy(
                    raise_record
                )
                for raise_record in appointment_values.get("raises", [])
            }

            for removed_raise_id in (
                set(existing_raises) - set(requested_raises)
            ):
                if self.event_controller.get_event(removed_raise_id):
                    self.event_controller.delete_event(removed_raise_id)

            for raise_id, raise_record in requested_raises.items():
                raise_values = {
                    "record_id": raise_id,
                    "event_type": "received_raise",
                    "title": f"Received a raise for {title}",
                    "date": raise_record["date"],
                    "description": "",
                    "person_ids": person_ids,
                    "eminence_person_ids": [],
                    "eminence_skills": {},
                    "period_names": [],
                    "location_ids": [],
                    "locked_location_ids": [],
                    "organization_id": organization["record_id"],
                    "organization_name": organization_name,
                    "organization_job_id": organization_job["record_id"],
                    "job_title": organization_job["title"],
                    "job_assignment_id": assignment_id,
                    "source_job_event_id": saved_event["record_id"],
                    "salary": raise_record["salary"],
                }

                if self.event_controller.get_event(raise_id) is None:
                    self.event_controller.create_event(raise_values)
                else:
                    self.event_controller.update_event(
                        raise_id,
                        raise_values,
                    )
        except (KeyError, TypeError, ValueError) as error:
            database.data = database_data
            database.dirty = database_dirty
            database.revision = database_revision
            self.event_controller.invalidate_event_cache()

            try:
                database.save()
            except (OSError, TypeError, ValueError):
                pass

            messagebox.showerror(
                "Cannot save appointment",
                str(error),
                parent=self,
            )
            return False

        self.refresh_job_timeline()
        holder_name = (
            person.get("displayed_name", "Unnamed magician")
            if isinstance(person, dict)
            else appointment_values.get(
                "special_appointment_name",
                "Special appointment",
            )
        )
        self.status_command(
            f"Saved {organization_job['title']} appointment for "
            f"{holder_name}"
        )

        if self.events_changed_command is not None:
            self.events_changed_command()

        return saved_event

    def vacant_job_date_text(self, date_values):
        year = str(date_values.get("year", "") or "").strip()
        month = str(date_values.get("month", "") or "").strip()
        day = str(date_values.get("day", "") or "").strip()
        date_text = year

        if month:
            date_text += f"-{month}"

        if day:
            date_text += f"-{day}"

        return date_text

    def save_vacant_job(
        self,
        person,
        salary,
        start_date,
        end_date,
    ):
        selected_job_index = self.selected_job_index()

        if selected_job_index is None:
            return False

        organization = self.organizations_by_id.get(
            str(self.current_organization_id or "")
        )

        if organization is None:
            return False

        organization_job = self.organization_jobs[
            selected_job_index
        ]
        organization_name = str(
            organization.get("name", "")
            or "Unnamed organization"
        ).strip()
        title = (
            f"{organization_job['title']} at {organization_name}"
        )

        try:
            saved_event = self.event_controller.create_event(
                {
                    "event_type": "started_job",
                    "title": title,
                    "date": self.vacant_job_date_text(start_date),
                    "description": "",
                    "person_ids": [person["record_id"]],
                    "eminence_person_ids": [],
                    "eminence_skills": {},
                    "period_names": [],
                    "location_ids": [],
                    "locked_location_ids": [],
                    "organization_id": organization["record_id"],
                    "organization_name": organization_name,
                    "organization_job_id": organization_job[
                        "record_id"
                    ],
                    "job_title": organization_job["title"],
                    "job_end_date": self.vacant_job_date_text(
                        end_date
                    ),
                    "salary": salary,
                }
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot fill position",
                str(error),
                parent=self,
            )
            return False

        self.refresh_job_timeline()
        self.status_command(
            f"Filled {organization_job['title']} with "
            f"{person.get('displayed_name', 'Unnamed magician')}"
        )

        if self.events_changed_command is not None:
            self.events_changed_command()

        return saved_event

    def add_job(self):
        founding_year, founding_month, founding_day = (
            split_world_event_date(
                self.organization_events[0]["date"]
            )
        )

        try:
            extinction_date = self.extinction_date_from_form()
        except ValueError as error:
            messagebox.showerror(
                "Cannot add organization job",
                str(error),
                parent=self,
            )
            return

        OrganizationJobDialog(
            self,
            self.save_added_job,
            default_opened_year=founding_year,
            default_opened_month=founding_month,
            default_opened_day=founding_day,
            organization_extinct=self.extinct_value.get(),
            organization_extinction_date=extinction_date,
        )

    def save_added_job(self, organization_job):
        self.organization_jobs = normalize_organization_jobs(
            [*self.organization_jobs, organization_job]
        )
        self.refresh_job_list(
            organization_job["record_id"]
        )
        self.mark_form_dirty()
        return self.save_organization()

    def edit_selected_job(self, event=None):
        selected_index = self.selected_job_index()

        if selected_index is None:
            return

        try:
            extinction_date = self.extinction_date_from_form()
        except ValueError as error:
            messagebox.showerror(
                "Cannot edit organization job",
                str(error),
                parent=self,
            )
            return

        OrganizationJobDialog(
            self,
            self.save_edited_job,
            existing_job=self.organization_jobs[selected_index],
            organization_extinct=self.extinct_value.get(),
            organization_extinction_date=extinction_date,
        )

    def save_edited_job(self, organization_job):
        job_id = organization_job["record_id"]
        self.organization_jobs = normalize_organization_jobs(
            [
                (
                    organization_job
                    if stored_job["record_id"] == job_id
                    else stored_job
                )
                for stored_job in self.organization_jobs
            ]
        )
        self.refresh_job_list(job_id)

        self.mark_form_dirty()
        return self.save_organization()

    def duplicate_selected_job(self):
        selected_index = self.selected_job_index()

        if selected_index is None:
            return

        selected_job = self.organization_jobs[selected_index]
        duplicated_job = new_organization_job(
            selected_job["title"],
            selected_job["opened_year"],
            selected_job["opened_month"],
            selected_job["opened_day"],
            selected_job["closed_year"],
            selected_job["closed_month"],
            selected_job["closed_day"],
            level=selected_job["level"],
        )
        if not self.save_added_job(duplicated_job):
            return

        self.status_command(
            f"Duplicated position {selected_job['title']}"
        )

    def remove_selected_job(self):
        selected_index = self.selected_job_index()

        if selected_index is None:
            return

        selected_job = self.organization_jobs[selected_index]

        if self.controller.organization_job_is_referenced(
            selected_job["record_id"]
        ):
            messagebox.showerror(
                "Cannot remove job",
                "This job has character assignments and cannot be removed.",
                parent=self,
            )
            return

        self.organization_jobs = normalize_organization_jobs(
            [
                organization_job
                for index, organization_job in enumerate(
                    self.organization_jobs
                )
                if index != selected_index
            ]
        )
        self.refresh_job_list()
        self.mark_form_dirty()
        self.save_organization()
