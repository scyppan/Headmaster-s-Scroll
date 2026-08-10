import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, simpledialog

from mage_maker.sections.events.models import world_event_year
from mage_maker.sections.organizations.controller import (
    ORGANIZATION_EVENT_FOUNDING,
    ORGANIZATION_TYPES,
    new_organization_job,
    organization_context_label,
    organization_paths_by_id,
)
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
)
from mage_maker.sections.locations.models import (
    location_path,
    location_paths_by_id,
    recent_location_label,
)
from mage_maker.ui.theme import (
    ADD_GREEN,
    ADD_GREEN_HOVER,
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
    RoundedSelect,
    SoftButton,
)


def normalize_dialog_location(location):
    normalized = deepcopy(location)

    if not str(normalized.get("name", "") or "").strip():
        normalized["name"] = str(
            normalized.get("label", "") or "Unnamed location"
        ).strip()

    normalized.setdefault("parent_location_id", "")
    normalized.setdefault("demographics", "")
    normalized.setdefault("notes", "")
    normalized.setdefault("extinct", False)
    normalized.setdefault("extinction_year", "")
    normalized.setdefault("timeline_events", [])
    return normalized


class OrganizationLocationSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        save_command,
        selected_location_id="",
        dialog_title="Select location",
        action_text="Use location",
        allow_clear=True,
        create_location_command=None,
    ):
        super().__init__(parent)
        self.locations = [
            normalize_dialog_location(location)
            for location in locations or []
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        ]
        self.save_command = save_command
        self.selected_location_id = str(
            selected_location_id or ""
        ).strip()
        self.selection_value = tk.StringVar(
            value="Select a location from the hierarchy."
        )
        self.dialog_title = str(dialog_title or "Select location")
        self.action_text = str(action_text or "Use location")
        self.allow_clear = bool(allow_clear)
        self.create_location_command = create_location_command
        self.title(self.dialog_title)
        self.geometry("680x700")
        self.minsize(540, 540)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.location_tree.set_locations(
            self.locations,
            self.selected_location_id,
        )
        self.location_selected(
            self.location_tree.selected_location_id
        )
        self.grab_set()
        self.after_idle(self.focus_search)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=self.dialog_title,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)

        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(1, weight=1)
        body.grid_columnconfigure(0, weight=1)
        explanation = tk.Label(
            body,
            text=(
                "Search names, full paths, notes, demographics, and events. "
                "Use the filters or lock to a branch to narrow large worlds."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=590,
        )
        explanation.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        self.location_tree = LocationHierarchyTree(
            body,
            self.location_selected,
            background=SURFACE,
            show_scope_controls=True,
        )
        self.location_tree.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        selected_label = tk.Label(
            body,
            textvariable=self.selection_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        selected_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(10, 0),
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

        if self.allow_clear:
            clear_button = SoftButton(
                footer,
                text="Clear location",
                command=self.clear_location,
                background=APP_BACKGROUND,
                width=118,
                height=36,
            )
            clear_button.grid(row=0, column=0, sticky="w")

        if self.create_location_command is not None:
            quick_add_button = SoftButton(
                footer,
                text="Quick add location",
                command=self.quick_add_location,
                background=APP_BACKGROUND,
                width=144,
                height=36,
            )
            quick_add_button.grid(
                row=0,
                column=1,
                padx=(7, 0),
            )

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        )
        cancel_button.grid(row=0, column=2, padx=(7, 0))
        self.use_button = SoftButton(
            footer,
            text=self.action_text,
            command=self.use_selected_location,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=36,
        )
        self.use_button.grid(row=0, column=3, padx=(7, 0))
        self.use_button.set_enabled(False)

    def location_selected(self, location_id):
        self.selected_location_id = str(location_id or "").strip()
        selected = next(
            (
                location
                for location in self.locations
                if str(location.get("record_id", "") or "").strip()
                == self.selected_location_id
            ),
            None,
        )

        if selected is None:
            self.selection_value.set(
                "Select a location from the hierarchy."
            )
            self.use_button.set_enabled(False)
            return

        self.selection_value.set(
            recent_location_label(
                self.selected_location_id,
                self.locations,
            )
        )
        self.use_button.set_enabled(True)

    def use_selected_location(self, event=None):
        selected = next(
            (
                location
                for location in self.locations
                if str(location.get("record_id", "") or "").strip()
                == self.selected_location_id
            ),
            None,
        )

        if selected is None:
            return

        selected["label"] = recent_location_label(
            self.selected_location_id,
            self.locations,
        )
        self.save_command(
            deepcopy(selected)
        )
        self.destroy()

    def clear_location(self):
        self.save_command(None)
        self.destroy()

    def quick_add_location(self):
        if self.create_location_command is None:
            return False

        location_name = simpledialog.askstring(
            "Quick add location",
            "Location name:",
            parent=self,
        )

        if location_name is None or not location_name.strip():
            return False

        try:
            created = self.create_location_command(
                location_name.strip(),
                self.selected_location_id,
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add location",
                str(error),
                parent=self,
            )
            return False

        if not isinstance(created, dict):
            return False

        normalized = normalize_dialog_location(created)
        self.locations.append(normalized)
        self.selected_location_id = str(
            normalized.get("record_id", "") or ""
        ).strip()
        self.location_tree.set_locations(
            self.locations,
            self.selected_location_id,
        )
        self.location_selected(self.selected_location_id)
        return True

    def focus_search(self):
        self.location_tree.search_control.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class OrganizationSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        organizations,
        save_command,
        create_command=None,
        location_provider=None,
    ):
        super().__init__(parent)
        self.organizations = [
            deepcopy(organization)
            for organization in organizations or []
            if isinstance(organization, dict)
            and str(organization.get("name", "") or "").strip()
        ]
        self.organization_paths_by_id = organization_paths_by_id(
            self.organizations
        )
        self.save_command = save_command
        self.create_command = create_command
        self.location_provider = location_provider
        available_locations = self.available_locations()
        self.location_labels_by_id = {
            str(option.get("record_id", "") or ""): str(
                option.get("label", "") or ""
            )
            for option in available_locations
        }
        self.location_display_labels_by_id = {
            str(option.get("record_id", "") or ""): recent_location_label(
                option.get("record_id", ""),
                available_locations,
            )
            for option in available_locations
        }
        self.visible_organizations = []
        self.search_value = tk.StringVar()
        self.type_value = tk.StringVar(value="All types")
        self.year_value = tk.StringVar()
        self.location_filter_id = ""
        self.location_filter_value = tk.StringVar(
            value="All locations"
        )
        self.results_value = tk.StringVar()
        self.title("Select organization")
        self.geometry("790x620")
        self.minsize(680, 500)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.type_value.trace_add("write", self.refresh_results)
        self.year_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.grab_set()
        self.after_idle(self.focus_search)

    def available_locations(self):
        if self.location_provider is None:
            return []

        locations = self.location_provider()
        available = [
            deepcopy(location)
            for location in locations or []
            if isinstance(location, dict)
        ]
        paths_by_id = location_paths_by_id(available)

        for location in available:
            record_id = str(
                location.get("record_id", "") or ""
            ).strip()
            location["label"] = str(
                location.get("label", "")
                or paths_by_id.get(record_id, "")
            ).strip()

        return available

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Select organization",
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
                "Search names, types, locations, founding years, "
                "descriptions, notes, and event titles. Multiple words "
                "must all match."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            justify="left",
        )
        explanation.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 9),
        )
        self.search_control = RoundedEntry(
            body,
            textvariable=self.search_value,
            background=SURFACE,
            width=470,
            height=40,
            font=app_font(10),
        )
        self.search_control.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 8),
        )
        self.type_select = RoundedSelect(
            body,
            self.type_value,
            ("All types", *ORGANIZATION_TYPES),
            background=SURFACE,
            width=190,
            height=40,
            font=app_font(10),
        )
        self.type_select.grid(
            row=1,
            column=1,
            sticky="e",
        )
        filter_row = tk.Frame(body, bg=SURFACE)
        filter_row.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(10, 0),
        )
        filter_row.grid_columnconfigure(1, weight=1)
        year_label = tk.Label(
            filter_row,
            text="Existing in year",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        year_label.grid(
            row=0,
            column=0,
            sticky="w",
            padx=(0, 6),
        )
        self.year_control = RoundedEntry(
            filter_row,
            textvariable=self.year_value,
            background=SURFACE,
            width=108,
            height=36,
            font=app_font(9),
            justify="center",
        )
        self.year_control.grid(
            row=0,
            column=1,
            sticky="w",
        )
        location_filter_label = tk.Label(
            filter_row,
            textvariable=self.location_filter_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=10,
            pady=8,
        )
        location_filter_label.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(12, 6),
        )
        choose_location_button = SoftButton(
            filter_row,
            text="Place…",
            command=self.open_location_filter,
            background=SURFACE,
            width=78,
            height=36,
            font=app_font(9, "bold"),
        )
        choose_location_button.grid(
            row=0,
            column=3,
        )
        clear_filters_button = SoftButton(
            filter_row,
            text="Clear filters",
            command=self.clear_filters,
            background=SURFACE,
            width=104,
            height=36,
            font=app_font(9, "bold"),
        )
        clear_filters_button.grid(
            row=0,
            column=4,
            padx=(6, 0),
        )
        results_label = tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        results_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 6),
        )
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.organization_list = tk.Listbox(
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
        self.organization_list.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.organization_list.bind(
            "<Double-Button-1>",
            self.use_selected_organization,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.organization_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.organization_list.configure(
            yscrollcommand=scrollbar.set
        )

        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=18,
            pady=(0, 16),
        )
        footer.grid_columnconfigure(1, weight=1)
        new_button = SoftButton(
            footer,
            text="New organization",
            command=self.open_quick_create,
            background=APP_BACKGROUND,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=146,
            height=36,
        )
        new_button.grid(row=0, column=0, sticky="w")
        new_button.set_enabled(
            self.create_command is not None
            and self.location_provider is not None
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        )
        cancel_button.grid(
            row=0,
            column=2,
            padx=(7, 0),
        )
        self.use_button = SoftButton(
            footer,
            text="Use organization",
            command=self.use_selected_organization,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=142,
            height=36,
        )
        self.use_button.grid(
            row=0,
            column=3,
            padx=(7, 0),
        )

    def organization_hierarchy_label(self, organization):
        organization_id = str(
            organization.get("record_id", "") or ""
        )
        return organization_context_label(
            organization_id,
            getattr(
                self,
                "organizations",
                [organization],
            ),
        )

    def organization_search_text(self, organization):
        organization_id = str(
            organization.get("record_id", "") or ""
        ).strip()
        searchable_values = [
            organization.get("name"),
            organization.get("organization_type"),
            organization.get("overview"),
            organization.get("notes"),
            self.location_labels_by_id.get(
                str(organization.get("location_id", "") or ""),
                "",
            ),
            OrganizationSelectionDialog.organization_hierarchy_label(
                self,
                organization,
            ),
            getattr(
                self,
                "organization_paths_by_id",
                {},
            ).get(organization_id, ""),
            "Has a shop" if organization.get("has_shop") else "",
            (
                "Includes a library"
                if organization.get("includes_library")
                else ""
            ),
            (
                "Library open to outsiders"
                if organization.get("library_open_to_outsiders")
                else ""
            ),
            "Extinct" if organization.get("extinct") else "Active",
            organization.get("extinction_date"),
        ]

        for event in organization.get("events", []) or []:
            if not isinstance(event, dict):
                continue

            searchable_values.extend(
                (
                    event.get("title"),
                    event.get("year"),
                    event.get("description"),
                )
            )

        for organization_job in organization.get("jobs", []) or []:
            if not isinstance(organization_job, dict):
                continue

            searchable_values.extend(
                (
                    organization_job.get("title"),
                    organization_job.get("opened_date"),
                    organization_job.get("closed_date"),
                )
            )

        return " ".join(
            str(value or "").strip()
            for value in searchable_values
            if str(value or "").strip()
        ).casefold()

    def organization_display_text(self, organization):
        return OrganizationSelectionDialog.organization_hierarchy_label(
            self,
            organization,
        )

    def organization_founding_year(self, organization):
        for event in organization.get("events", []) or []:
            if not isinstance(event, dict):
                continue

            if str(event.get("event_type", "") or "").casefold() != (
                ORGANIZATION_EVENT_FOUNDING
            ):
                continue

            try:
                return int(event.get("year"))
            except (TypeError, ValueError):
                return None

        return None

    def organization_matches_year(
        self,
        organization,
        selected_year,
    ):
        if selected_year is None:
            return True

        founding_year = (
            OrganizationSelectionDialog.organization_founding_year(
                self,
                organization,
            )
        )
        extinction_year = (
            world_event_year(organization.get("extinction_date", ""))
            if organization.get("extinct")
            else None
        )
        return (
            founding_year is not None
            and founding_year <= selected_year
            and (
                extinction_year is None
                or extinction_year >= selected_year
            )
        )

    def organization_matches_location(self, organization):
        location_filter_id = getattr(
            self,
            "location_filter_id",
            "",
        )

        if not location_filter_id:
            return True

        organization_location_label = (
            self.location_labels_by_id.get(
                str(organization.get("location_id", "") or ""),
                "",
            )
        )
        selected_location_label = (
            self.location_labels_by_id.get(
                location_filter_id,
                "",
            )
        )

        if not selected_location_label:
            return False

        return (
            organization_location_label == selected_location_label
            or organization_location_label.startswith(
                f"{selected_location_label} › "
            )
        )

    def open_location_filter(self):
        OrganizationLocationSelectionDialog(
            self,
            self.available_locations(),
            self.location_filter_selected,
            self.location_filter_id,
            dialog_title="Filter organizations by place",
            action_text="Use place",
            allow_clear=True,
        )

    def location_filter_selected(self, location):
        if location is None:
            self.location_filter_id = ""
            self.location_filter_value.set("All locations")
        else:
            self.location_filter_id = str(
                location.get("record_id", "") or ""
            ).strip()
            self.location_filter_value.set(
                str(location.get("label", "") or "All locations")
            )

        self.refresh_results()

    def clear_filters(self):
        self.search_value.set("")
        self.type_value.set("All types")
        self.year_value.set("")
        self.location_filter_id = ""
        self.location_filter_value.set("All locations")
        self.refresh_results()

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().strip().casefold().split()
            if term
        ]
        selected_type = self.type_value.get()
        selected_year = None

        year_variable = getattr(self, "year_value", None)
        year_text = (
            year_variable.get().strip()
            if year_variable is not None
            else ""
        )

        if year_text:
            try:
                selected_year = int(year_text)
            except (TypeError, ValueError):
                selected_year = -100000

        self.visible_organizations = sorted(
            [
                organization
                for organization in self.organizations
                if (
                    selected_type == "All types"
                    or organization.get("organization_type")
                    == selected_type
                )
                and OrganizationSelectionDialog.organization_matches_year(
                    self,
                    organization,
                    selected_year,
                )
                and OrganizationSelectionDialog.organization_matches_location(
                    self,
                    organization,
                )
                and all(
                    term in self.organization_search_text(organization)
                    for term in query_terms
                )
            ],
            key=self.organization_sort_key,
        )
        self.organization_list.delete(0, "end")

        for index, organization in enumerate(
            self.visible_organizations
        ):
            self.organization_list.insert(
                "end",
                self.organization_display_text(organization),
            )
            self.organization_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.results_value.set(
            f"Organizations ({len(self.visible_organizations)})"
        )

        if self.visible_organizations:
            self.organization_list.selection_set(0)

        self.use_button.set_enabled(bool(self.visible_organizations))

    def organization_sort_key(self, organization):
        return str(
            organization.get("name", "") or ""
        ).casefold()

    def open_quick_create(self):
        if (
            self.create_command is None
            or self.location_provider is None
        ):
            return

        QuickOrganizationDialog(
            self,
            self.available_locations(),
            self.create_command,
            self.organization_created,
        )

    def organization_created(self, organization):
        self.organizations.append(deepcopy(organization))
        self.save_command(deepcopy(organization))
        self.destroy()

    def use_selected_organization(self, event=None):
        selected = self.organization_list.curselection()

        if not selected:
            return

        self.save_command(
            deepcopy(self.visible_organizations[int(selected[0])])
        )
        self.destroy()

    def focus_search(self):
        self.search_control.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class QuickOrganizationDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        create_command,
        save_command,
    ):
        super().__init__(parent)
        self.locations = [
            normalize_dialog_location(location)
            for location in locations or []
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        ]
        self.visible_locations = []
        self.selected_location_id = ""
        self.create_command = create_command
        self.save_command = save_command
        self.name_value = tk.StringVar()
        self.type_value = tk.StringVar(value=ORGANIZATION_TYPES[0])
        self.founding_year_value = tk.StringVar()
        self.founding_month_value = tk.StringVar()
        self.founding_day_value = tk.StringVar()
        self.job_title_value = tk.StringVar()
        self.job_opened_year_value = tk.StringVar()
        self.job_opened_month_value = tk.StringVar()
        self.job_opened_day_value = tk.StringVar()
        self.location_search_value = tk.StringVar()
        self.location_results_value = tk.StringVar()
        self.location_value = tk.StringVar(
            value="Choose an organization location"
        )
        self.title("New organization")
        self.geometry("760x590")
        self.minsize(680, 550)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.grab_set()
        self.after_idle(self.focus_name)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="New organization",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)

        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure((0, 1), weight=1)

        name_label = tk.Label(
            body,
            text="Name",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        name_label.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        type_label = tk.Label(
            body,
            text="Type",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        type_label.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        self.name_entry = RoundedEntry(
            body,
            textvariable=self.name_value,
            background=SURFACE,
            width=300,
            height=38,
            font=app_font(10),
        )
        self.name_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(5, 13),
        )
        type_select = RoundedSelect(
            body,
            self.type_value,
            ORGANIZATION_TYPES,
            background=SURFACE,
            width=220,
            height=38,
            font=app_font(10),
        )
        type_select.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(7, 0),
            pady=(5, 13),
        )
        founding_date_frame = tk.Frame(body, bg=SURFACE)
        founding_date_frame.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 13),
        )
        founding_date_frame.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
            uniform="quick_organization_founding_date",
        )

        for column, label_text in enumerate(
            ("Founding year", "Month", "Day")
        ):
            founding_date_label = tk.Label(
                founding_date_frame,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            founding_date_label.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 7) if column < 2 else 0,
            )

        founding_year_entry = RoundedEntry(
            founding_date_frame,
            textvariable=self.founding_year_value,
            background=SURFACE,
            width=150,
            height=38,
            font=app_font(10),
            justify="center",
        )
        founding_year_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(5, 0),
        )
        founding_month_entry = RoundedEntry(
            founding_date_frame,
            textvariable=self.founding_month_value,
            background=SURFACE,
            width=100,
            height=38,
            font=app_font(10),
            justify="center",
        )
        founding_month_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 7),
            pady=(5, 0),
        )
        founding_day_entry = RoundedEntry(
            founding_date_frame,
            textvariable=self.founding_day_value,
            background=SURFACE,
            width=100,
            height=38,
            font=app_font(10),
            justify="center",
        )
        founding_day_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            pady=(5, 0),
        )
        job_title_label = tk.Label(
            body,
            text="First job title",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        job_title_label.grid(
            row=4,
            column=0,
            sticky="ew",
            padx=(0, 7),
        )
        job_opened_year_label = tk.Label(
            body,
            text="Position opened",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        job_opened_year_label.grid(
            row=4,
            column=1,
            sticky="ew",
            padx=(7, 0),
        )
        job_title_entry = RoundedEntry(
            body,
            textvariable=self.job_title_value,
            background=SURFACE,
            width=300,
            height=38,
            font=app_font(10),
        )
        job_title_entry.grid(
            row=5,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(5, 13),
        )
        job_opened_panel = tk.Frame(body, bg=SURFACE)
        job_opened_panel.grid(
            row=5,
            column=1,
            sticky="ew",
            padx=(7, 0),
            pady=(5, 13),
        )
        job_opened_panel.grid_columnconfigure((0, 1, 2), weight=1)

        for column, label_text in enumerate(("Year", "Month", "Day")):
            job_opened_part_label = tk.Label(
                job_opened_panel,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            job_opened_part_label.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 4) if column < 2 else 0,
                pady=(0, 3),
            )

        job_opened_year_entry = RoundedEntry(
            job_opened_panel,
            textvariable=self.job_opened_year_value,
            background=SURFACE,
            width=92,
            height=38,
            font=app_font(10),
            justify="center",
        )
        job_opened_year_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        job_opened_month_entry = RoundedEntry(
            job_opened_panel,
            textvariable=self.job_opened_month_value,
            background=SURFACE,
            width=72,
            height=38,
            font=app_font(10),
            justify="center",
        )
        job_opened_month_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=4,
        )
        job_opened_day_entry = RoundedEntry(
            job_opened_panel,
            textvariable=self.job_opened_day_value,
            background=SURFACE,
            width=72,
            height=38,
            font=app_font(10),
            justify="center",
        )
        job_opened_day_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(4, 0),
        )
        calendar_notice = CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=680,
            date_variables=(
                (
                    self.founding_year_value,
                    self.founding_month_value,
                    self.founding_day_value,
                ),
                (
                    self.job_opened_year_value,
                    self.job_opened_month_value,
                    self.job_opened_day_value,
                ),
            ),
        )
        calendar_notice.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 10),
        )
        location_label = tk.Label(
            body,
            text="Location",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        location_label.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        location_display = tk.Label(
            body,
            textvariable=self.location_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
            pady=9,
        )
        location_display.grid(
            row=10,
            column=0,
            sticky="ew",
            pady=(5, 0),
        )
        choose_location_button = SoftButton(
            body,
            text="Choose location…",
            command=self.open_location_dialog,
            background=SURFACE,
            width=138,
            height=38,
            font=app_font(9, "bold"),
        )
        choose_location_button.grid(
            row=10,
            column=1,
            sticky="e",
            padx=(8, 0),
            pady=(5, 0),
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
        save_button = SoftButton(
            footer,
            text="Create organization",
            command=self.create_organization,
            background=APP_BACKGROUND,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=152,
            height=36,
        )
        save_button.grid(row=0, column=2)

    def refresh_locations(self, *arguments):
        query_terms = [
            term
            for term in self.location_search_value.get()
            .strip()
            .casefold()
            .split()
            if term
        ]
        self.visible_locations = [
            location
            for location in self.locations
            if all(
                term
                in str(location.get("label", "") or "").casefold()
                for term in query_terms
            )
        ]
        if not hasattr(self, "location_list"):
            return

        self.location_list.delete(0, "end")

        for index, location in enumerate(self.visible_locations):
            self.location_list.insert(
                "end",
                location["label"],
            )
            self.location_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        self.location_results_value.set(
            f"{len(self.visible_locations)} locations"
        )

        if self.visible_locations:
            self.location_list.selection_set(0)

    def open_location_dialog(self):
        OrganizationLocationSelectionDialog(
            self,
            self.locations,
            self.location_selected,
            self.selected_location_id,
            dialog_title="Select organization location",
            action_text="Use location",
            allow_clear=False,
        )

    def location_selected(self, location):
        if not isinstance(location, dict):
            return

        self.selected_location_id = str(
            location.get("record_id", "") or ""
        ).strip()
        self.location_value.set(
            str(
                location.get("label", "")
                or location_path(
                    self.selected_location_id,
                    self.locations,
                )
                or "Choose an organization location"
            )
        )

    def create_organization(self):
        selected_location_id = str(
            getattr(self, "selected_location_id", "") or ""
        ).strip()

        if (
            not selected_location_id
            and hasattr(self, "location_list")
        ):
            selected = self.location_list.curselection()

            if selected:
                selected_location_id = str(
                    self.visible_locations[
                        int(selected[0])
                    ].get("record_id", "")
                    or ""
                ).strip()

        if not selected_location_id:
            messagebox.showerror(
                "Cannot create organization",
                "Choose a location.",
                parent=self,
            )
            return

        try:
            founding_year = int(self.founding_year_value.get())
        except (TypeError, ValueError):
            messagebox.showerror(
                "Cannot create organization",
                "Founding year must be a whole number.",
                parent=self,
            )
            return

        founding_month_value = getattr(
            self,
            "founding_month_value",
            None,
        )
        founding_day_value = getattr(
            self,
            "founding_day_value",
            None,
        )
        founding_month = (
            founding_month_value.get().strip()
            if founding_month_value is not None
            else ""
        )
        founding_day = (
            founding_day_value.get().strip()
            if founding_day_value is not None
            else ""
        )

        if founding_day and not founding_month:
            messagebox.showerror(
                "Cannot create organization",
                "The founding day requires a month.",
                parent=self,
            )
            return

        try:
            job_title = self.job_title_value.get().strip()
            job_opened_year = (
                self.job_opened_year_value.get().strip()
            )
            job_opened_month_value = getattr(
                self,
                "job_opened_month_value",
                None,
            )
            job_opened_day_value = getattr(
                self,
                "job_opened_day_value",
                None,
            )
            job_opened_month = (
                job_opened_month_value.get().strip()
                if job_opened_month_value is not None
                else ""
            )
            job_opened_day = (
                job_opened_day_value.get().strip()
                if job_opened_day_value is not None
                else ""
            )
            organization_jobs = []

            if (
                job_title
                or job_opened_year
                or job_opened_month
                or job_opened_day
            ):
                organization_jobs.append(
                    new_organization_job(
                        job_title,
                        job_opened_year or founding_year,
                        job_opened_month or founding_month,
                        job_opened_day or founding_day,
                    )
                )

            organization = self.create_command(
                {
                    "name": self.name_value.get(),
                    "organization_type": self.type_value.get(),
                    "location_id": selected_location_id,
                    "parent_organization_id": "",
                    "has_shop": self.type_value.get() == "Shop",
                    "shop_inventory": {},
                    "extinct": False,
                    "extinction_date": "",
                    "overview": "",
                    "notes": "",
                    "jobs": organization_jobs,
                    "events": [
                        {
                            "record_id": "organization-founding",
                            "event_type": ORGANIZATION_EVENT_FOUNDING,
                            "title": "Founding",
                            "year": founding_year,
                            "month": founding_month,
                            "day": founding_day,
                            "description": "",
                        }
                    ],
                }
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot create organization",
                str(error),
                parent=self,
            )
            return

        self.save_command(organization)
        self.destroy()

    def focus_name(self):
        self.name_entry.entry.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
