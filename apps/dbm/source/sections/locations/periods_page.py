import tkinter as tk
from tkinter import messagebox, ttk

from mage_maker.sections.locations.models import location_path
from mage_maker.sections.locations.period_definitions import (
    PeriodDefinitionError,
    load_period_definitions,
    period_year_text,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_SELECTED,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


ALL_LOCATIONS_LABEL = "All locations"
CATEGORY_DEFINITIONS = (
    ("born", "Born in this period"),
    ("died", "Died during this period"),
    ("reproductively_active", "Reproductively active"),
    ("living", "Living during this period"),
)


class PeriodsPage(tk.Frame):
    def __init__(self, parent, controller, status_command, navigate_person_command):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.location_records = []
        self.location_ids = []
        self.selected_location_id = ""
        self.period_error = ""

        try:
            self.period_definitions = load_period_definitions()
        except PeriodDefinitionError as error:
            self.period_definitions = []
            self.period_error = str(error)

        self.periods_by_name = {
            period["name"]: period
            for period in self.period_definitions
        }
        initial_period_name = (
            self.period_definitions[0]["name"]
            if self.period_definitions
            else ""
        )
        self.period_value = tk.StringVar(value=initial_period_name)
        self.period_context_value = tk.StringVar()
        self.period_descriptor_value = tk.StringVar()
        self.has_no_children_value = tk.BooleanVar(value=False)
        self.summary_value = tk.StringVar(value="Select a period.")
        self.category_panels = {}
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_workspace()
        self.update_period_details()
        self.refresh()

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
            row=0,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(10, 18),
        )
        self.build_location_sidebar(workspace)
        self.build_results_area(workspace)

    def build_location_sidebar(self, workspace):
        sidebar = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        sidebar.grid_rowconfigure(2, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            sidebar,
            text="Location",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            sidebar,
            text="A location includes every place nested inside it.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=250,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(3, 9))
        self.location_list = tk.Listbox(
            sidebar,
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
        )
        self.location_list.grid(row=2, column=0, sticky="nsew")
        self.location_list.bind("<<ListboxSelect>>", self.location_selected)
        scrollbar = tk.Scrollbar(sidebar, command=self.location_list.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.location_list.configure(yscrollcommand=scrollbar.set)
        workspace.add(sidebar, minsize=270, width=300)

    def build_results_area(self, workspace):
        results_area = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        results_area.grid_rowconfigure(2, weight=1)
        results_area.grid_columnconfigure(0, weight=1)
        self.build_period_controls(results_area)
        self.build_category_grid(results_area)
        workspace.add(results_area, minsize=700)

    def build_period_controls(self, parent):
        controls = tk.Frame(parent, bg=SURFACE_MUTED, padx=14, pady=12)
        controls.grid(row=0, column=0, sticky="ew")
        controls.grid_columnconfigure(0, weight=1)
        title = tk.Label(
            controls,
            text="Period",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, sticky="ew")
        self.period_picker = ttk.Combobox(
            controls,
            textvariable=self.period_value,
            values=[period["name"] for period in self.period_definitions],
            state="readonly" if self.period_definitions else "disabled",
            font=app_font(10),
        )
        self.period_picker.grid(row=1, column=0, sticky="ew", pady=(6, 0), ipady=6)
        self.period_picker.bind("<<ComboboxSelected>>", self.period_selected)
        context = tk.Label(
            controls,
            textvariable=self.period_context_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        context.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        descriptor = tk.Label(
            controls,
            textvariable=self.period_descriptor_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=780,
        )
        descriptor.grid(row=3, column=0, sticky="ew", pady=(3, 0))
        summary = tk.Label(
            parent,
            textvariable=self.summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(9, 7))

    def build_category_grid(self, parent):
        category_grid = tk.Frame(parent, bg=SURFACE)
        category_grid.grid(row=2, column=0, sticky="nsew")
        category_grid.grid_rowconfigure(0, weight=1)
        category_grid.grid_columnconfigure(
            (0, 1, 2, 3),
            weight=1,
            uniform="period_columns",
        )

        for index, (category_key, title) in enumerate(CATEGORY_DEFINITIONS):
            filter_variable = (
                self.has_no_children_value
                if category_key == "reproductively_active"
                else None
            )
            panel = PeriodCategoryPanel(
                category_grid,
                title,
                self.navigate_person_command,
                filter_variable,
                self.calculate,
            )
            panel.grid(
                row=0,
                column=index,
                sticky="nsew",
                padx=(
                    (0, 5)
                    if index == 0
                    else (5, 0)
                    if index == len(CATEGORY_DEFINITIONS) - 1
                    else 5
                ),
            )
            self.category_panels[category_key] = panel

    def refresh(self):
        retained_location_id = self.selected_location_id
        self.location_records = self.controller.list_locations()
        self.location_ids = [""]
        self.location_list.delete(0, "end")
        self.location_list.insert("end", ALL_LOCATIONS_LABEL)
        selected_index = 0

        for location in self.location_records:
            record_id = str(location.get("record_id", "") or "")
            depth = max(
                0,
                location_path(record_id, self.location_records).count(" › "),
            )
            self.location_ids.append(record_id)
            self.location_list.insert(
                "end",
                f"{'   ' * depth}{location.get('name', 'Unnamed')}",
            )

            if record_id == retained_location_id:
                selected_index = len(self.location_ids) - 1

        self.selected_location_id = self.location_ids[selected_index]
        self.location_list.selection_set(selected_index)
        self.location_list.see(selected_index)
        self.update_period_details()
        self.calculate(silent=True)

    def location_selected(self, event=None):
        selected = self.location_list.curselection()

        if not selected:
            return

        self.selected_location_id = self.location_ids[selected[0]]
        self.calculate(silent=True)

    def period_selected(self, event=None):
        self.update_period_details()
        self.calculate()

    def selected_period_definition(self):
        return self.periods_by_name.get(self.period_value.get().strip())

    def update_period_details(self):
        period = self.selected_period_definition()

        if period is None:
            self.period_context_value.set("")
            self.period_descriptor_value.set(
                self.period_error or "Select a period."
            )
            return

        context_parts = []
        group_name = str(period.get("group_name", "") or "").strip()
        years = period_year_text(period)

        if group_name:
            context_parts.append(group_name)

        if years:
            context_parts.append(years)

        descriptors = []
        group_descriptor = str(
            period.get("group_descriptor", "") or ""
        ).strip()
        descriptor = str(period.get("descriptor", "") or "").strip()

        if group_descriptor:
            descriptors.append(group_descriptor)

        if descriptor:
            descriptors.append(descriptor)

        self.period_context_value.set("  ·  ".join(context_parts))
        self.period_descriptor_value.set("  ·  ".join(descriptors))

    def calculate(self, silent=False):
        period = self.selected_period_definition()

        if period is None:
            self.clear_results(self.period_error or "Select a period.")
            return False

        start_year = period["calculation_start_year"]
        end_year = period["calculation_end_year"]

        try:
            results = self.controller.people_for_period(
                start_year,
                end_year,
                self.selected_location_id,
                reproductive_without_children=self.has_no_children_value.get(),
            )
        except ValueError as error:
            self.clear_results(str(error))

            if not silent:
                messagebox.showerror("Cannot calculate period", str(error), parent=self)

            return False

        total_matches = 0

        for category_key, panel in self.category_panels.items():
            category_people = results.get(category_key, [])
            panel.set_people(category_people)
            total_matches += len(category_people)

        location_name = self.selected_location_name()
        years = period_year_text(period)
        self.summary_value.set(
            f"{period['name']}  ·  {years}  ·  {location_name}  ·  "
            f"{total_matches} category entries"
        )
        self.status_command(
            f"Calculated {period['name']} for {location_name}"
        )
        return True

    def selected_location_name(self):
        if not self.selected_location_id:
            return ALL_LOCATIONS_LABEL

        for location in self.location_records:
            if str(location.get("record_id", "") or "") == self.selected_location_id:
                return str(location.get("name", "") or "Unnamed")

        return ALL_LOCATIONS_LABEL

    def clear_results(self, message):
        for panel in self.category_panels.values():
            panel.set_people([])

        self.summary_value.set(str(message or ""))


class PeriodCategoryPanel(tk.Frame):
    def __init__(
        self,
        parent,
        title,
        navigate_person_command,
        filter_variable=None,
        filter_command=None,
    ):
        super().__init__(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        self.title = title
        self.navigate_person_command = navigate_person_command
        self.category_people = []
        self.title_value = tk.StringVar(value=f"{title} (0)")
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            self,
            textvariable=self.title_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 7))
        filter_row = tk.Frame(self, bg=SURFACE_MUTED, height=25)
        filter_row.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        filter_row.grid_propagate(False)

        if filter_variable is not None:
            filter_checkbox = tk.Checkbutton(
                filter_row,
                text="Has no children",
                variable=filter_variable,
                command=filter_command,
                bg=SURFACE_MUTED,
                fg=TEXT_DARK,
                activebackground=SURFACE_MUTED,
                activeforeground=TEXT_DARK,
                selectcolor=FIELD_BACKGROUND,
                font=app_font(9),
                anchor="w",
                padx=0,
                pady=0,
            )
            filter_checkbox.pack(side="left")

        self.people_list = tk.Listbox(
            self,
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
        self.people_list.grid(row=2, column=0, sticky="nsew")
        self.people_list.bind("<Double-Button-1>", self.open_selected_person)
        scrollbar = tk.Scrollbar(self, command=self.people_list.yview)
        scrollbar.grid(row=2, column=1, sticky="ns")
        self.people_list.configure(yscrollcommand=scrollbar.set)

    def set_people(self, people):
        self.category_people = list(people)
        self.people_list.delete(0, "end")
        self.title_value.set(f"{self.title} ({len(self.category_people)})")

        for person in self.category_people:
            name = str(
                person.get("displayed_name", "") or "Unnamed magician"
            ).strip()
            detail = str(person.get("period_date_text", "") or "").strip()
            location = str(person.get("period_location", "") or "").strip()
            row_parts = [name]

            if detail:
                row_parts.append(detail)

            if location:
                row_parts.append(location)

            self.people_list.insert("end", "  ·  ".join(row_parts))

    def open_selected_person(self, event=None):
        selected = self.people_list.curselection()

        if not selected:
            return

        person_id = str(
            self.category_people[selected[0]].get("record_id", "") or ""
        )

        if person_id:
            self.navigate_person_command(person_id)
