import tkinter as tk
from copy import deepcopy

from mage_maker.sections.development.organization_dialogs import (
    OrganizationLocationSelectionDialog,
)
from mage_maker.sections.locations.models import recent_location_label
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
from mage_maker.ui.widgets import RoundedEntry, SoftButton


class EventJobSelectionDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        job_options,
        locations,
        selected_organization_id,
        selected_job_id,
        save_command,
    ):
        super().__init__(parent)
        self.job_options = [
            deepcopy(option)
            for option in job_options or []
            if isinstance(option, dict)
            and str(option.get("organization_id", "") or "").strip()
            and str(
                option.get("organization_job_id", "") or ""
            ).strip()
        ]
        self.locations = [
            deepcopy(location)
            for location in locations or []
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        ]
        self.selected_organization_id = str(
            selected_organization_id or ""
        ).strip()
        self.selected_job_id = str(selected_job_id or "").strip()
        self.save_command = save_command
        self.visible_options = []
        self.location_filter_id = ""
        self.search_value = tk.StringVar()
        self.location_filter_value = tk.StringVar(value="All regions")
        self.results_value = tk.StringVar(value="Jobs (0)")
        self.title("Select organization job")
        self.geometry("860x720")
        self.minsize(680, 560)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.refresh_results()
        self.grab_set()
        self.after_idle(self.focus_search)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="Select organization job",
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
                "Search job titles, organizations, levels, and locations. "
                "Choose a region to narrow very large job collections."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=790,
        )
        explanation.grid(row=0, column=0, sticky="ew")
        search_row = tk.Frame(body, bg=SURFACE)
        search_row.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )
        search_row.grid_columnconfigure(0, weight=1)
        self.search_entry = RoundedEntry(
            search_row,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_entry.grid(row=0, column=0, sticky="ew")
        location_label = tk.Label(
            search_row,
            textvariable=self.location_filter_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=10,
            pady=9,
        )
        location_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(8, 0),
        )
        region_button = SoftButton(
            search_row,
            text="Region…",
            command=self.open_location_filter,
            background=SURFACE,
            width=82,
            height=38,
            font=app_font(9, "bold"),
        )
        region_button.grid(row=0, column=2, padx=(6, 0))
        clear_region_button = SoftButton(
            search_row,
            text="All regions",
            command=self.clear_location_filter,
            background=SURFACE,
            width=94,
            height=38,
            font=app_font(9, "bold"),
        )
        clear_region_button.grid(row=0, column=3, padx=(6, 0))
        results_label = tk.Label(
            body,
            textvariable=self.results_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        results_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(12, 5),
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
        self.job_list = tk.Listbox(
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
        )
        self.job_list.grid(row=0, column=0, sticky="nsew")
        self.job_list.bind("<<ListboxSelect>>", self.selection_changed)
        self.job_list.bind("<Double-Button-1>", self.use_selected_job)
        scrollbar = tk.Scrollbar(
            list_frame,
            orient="vertical",
            command=self.job_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.job_list.configure(yscrollcommand=scrollbar.set)
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
        self.use_button = SoftButton(
            footer,
            text="Use selected job",
            command=self.use_selected_job,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=146,
            height=36,
        )
        self.use_button.grid(row=0, column=2)
        self.use_button.set_enabled(False)

    def job_search_text(self, option):
        organization = option.get("organization", {})
        return " ".join(
            str(value or "").strip()
            for value in (
                option.get("job_title"),
                option.get("organization_name"),
                option.get("job_level"),
                option.get("location_label"),
                organization.get("organization_type"),
                organization.get("overview"),
                organization.get("notes"),
            )
            if str(value or "").strip()
        ).casefold()

    def job_matches_location(self, option):
        if not self.location_filter_id:
            return True

        return self.location_filter_id in {
            str(location_id or "").strip()
            for location_id in option.get(
                "location_ancestor_ids",
                [],
            )
            if str(location_id or "").strip()
        }

    def job_sort_key(self, option):
        try:
            level = int(option.get("job_level", 0))
        except (TypeError, ValueError):
            level = 0

        return (
            (
                0
                if self.location_filter_id
                and bool(option.get("large_employer_branch"))
                else 1
            ),
            level,
            str(option.get("organization_name", "") or "").casefold(),
            str(option.get("job_title", "") or "").casefold(),
            str(option.get("organization_job_id", "") or ""),
        )

    def refresh_results(self, *arguments):
        query_terms = [
            term
            for term in self.search_value.get().casefold().split()
            if term
        ]
        self.visible_options = sorted(
            [
                option
                for option in self.job_options
                if self.job_matches_location(option)
                and all(
                    term in self.job_search_text(option)
                    for term in query_terms
                )
            ],
            key=self.job_sort_key,
        )
        self.job_list.delete(0, "end")
        selected_index = None

        for index, option in enumerate(self.visible_options):
            self.job_list.insert("end", option.get("label", "Unnamed job"))
            self.job_list.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if (
                str(option.get("organization_id", "") or "").strip()
                == self.selected_organization_id
                and str(
                    option.get("organization_job_id", "") or ""
                ).strip()
                == self.selected_job_id
            ):
                selected_index = index

        if selected_index is not None:
            self.job_list.selection_set(selected_index)
            self.job_list.see(selected_index)

        self.results_value.set(f"Jobs ({len(self.visible_options)})")
        self.selection_changed()

    def selected_job(self):
        selected = self.job_list.curselection()

        if not selected or int(selected[0]) >= len(self.visible_options):
            return None

        return self.visible_options[int(selected[0])]

    def selection_changed(self, event=None):
        self.use_button.set_enabled(self.selected_job() is not None)

    def open_location_filter(self):
        OrganizationLocationSelectionDialog(
            self,
            self.locations,
            self.location_filter_selected,
            self.location_filter_id,
            dialog_title="Filter jobs by region",
            action_text="Use region",
            allow_clear=True,
        )

    def location_filter_selected(self, location):
        self.location_filter_id = (
            str(location.get("record_id", "") or "").strip()
            if isinstance(location, dict)
            else ""
        )
        self.location_filter_value.set(
            recent_location_label(
                self.location_filter_id,
                self.locations,
            )
            if self.location_filter_id
            else "All regions"
        )
        self.refresh_results()

    def clear_location_filter(self):
        self.location_filter_id = ""
        self.location_filter_value.set("All regions")
        self.refresh_results()

    def use_selected_job(self, event=None):
        selected_job = self.selected_job()

        if selected_job is None:
            return "break" if event is not None else False

        saved = self.save_command(deepcopy(selected_job))

        if saved is False:
            return "break" if event is not None else False

        self.destroy()
        return "break" if event is not None else True

    def focus_search(self):
        self.search_entry.entry.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break" if event is not None else True
