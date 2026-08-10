import tkinter as tk
from tkinter import messagebox, ttk

from mage_maker.core.dates import (
    format_historical_display_date,
    format_line_item_date,
)
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
    WORLD_LOCATION_LABEL,
    location_id_is_in_scope,
)
from mage_maker.sections.locations.models import location_extinction_state
from mage_maker.sections.locations.period_definitions import (
    PeriodDefinitionError,
    load_period_definitions,
    update_period_definition,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, RoundedText, SoftButton


CATEGORY_DEFINITIONS = (
    ("born", "Born in this period"),
    ("living", "Living during this period"),
    ("reproductively_active", "Reproductively active"),
    ("died", "Died during this period"),
)
EXTINCT_BEFORE_BACKGROUND = "#EBCFD6"
EXTINCT_BEFORE_TEXT = "#6A2E3C"
EXTINCT_DURING_BACKGROUND = "#F1DDB7"
EXTINCT_DURING_TEXT = "#6A4A18"
PERIOD_EVENT_COLORS = ("#FFFFFF", "#F1F1F1")


class PeriodsPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        status_command,
        navigate_person_command,
        scope_change_command=None,
        navigate_location_command=None,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.scope_change_command = scope_change_command
        self.navigate_location_command = navigate_location_command
        self.location_records = []
        self.selected_location_id = ""
        self.region_lock_id = ""
        self.period_events = []
        self.period_error = ""
        self.save_feedback_after_id = None

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
        self.period_start_year_value = tk.StringVar()
        self.period_end_year_value = tk.StringVar()
        self.has_no_children_value = tk.BooleanVar(value=False)
        self.summary_value = tk.StringVar(value="Select a period.")
        self.extinction_notice_value = tk.StringVar()
        self.period_save_feedback_value = tk.StringVar()
        self.events_title_value = tk.StringVar(value="Events in this period (0)")
        self.category_panels = {}
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_workspace()
        self.update_period_details()

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
        self.location_tree = LocationHierarchyTree(
            sidebar,
            self.location_selected,
            background=SURFACE,
            scope_change_command=self.region_scope_changed,
        )
        self.location_tree.grid(row=2, column=0, sticky="nsew")
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
        results_area.grid_rowconfigure(3, weight=3)
        results_area.grid_rowconfigure(4, weight=2)
        results_area.grid_columnconfigure(0, weight=1)
        self.build_period_controls(results_area)
        self.build_category_grid(results_area)
        self.build_events_list(results_area)
        workspace.add(results_area, minsize=700)

    def build_period_controls(self, parent):
        controls = tk.Frame(parent, bg=SURFACE_MUTED, padx=14, pady=12)
        controls.grid(row=0, column=0, sticky="ew")
        controls.grid_columnconfigure(0, weight=2)
        controls.grid_columnconfigure(
            (1, 2),
            weight=1,
            uniform="period_year_fields",
        )
        period_label = tk.Label(
            controls,
            text="Period",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        period_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 14),
            pady=(0, 5),
        )
        start_year_label = tk.Label(
            controls,
            text="From",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        start_year_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(0, 7),
            pady=(0, 5),
        )
        end_year_label = tk.Label(
            controls,
            text="Through",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        end_year_label.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(7, 0),
            pady=(0, 5),
        )
        self.period_picker = ttk.Combobox(
            controls,
            textvariable=self.period_value,
            values=[period["name"] for period in self.period_definitions],
            state="readonly" if self.period_definitions else "disabled",
            font=app_font(10),
        )
        self.period_picker.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 14),
            ipady=6,
        )
        self.period_picker.bind("<<ComboboxSelected>>", self.period_selected)
        self.period_picker.bind("<Up>", self.select_previous_period)
        self.period_picker.bind("<Down>", self.select_next_period)
        self.period_start_year_control = RoundedEntry(
            controls,
            textvariable=self.period_start_year_value,
            background=SURFACE_MUTED,
            height=36,
            font=app_font(10),
        )
        self.period_start_year_control.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 7),
        )
        self.period_start_year_control.bind_input(
            "<Return>",
            self.period_details_submitted,
        )
        self.period_end_year_control = RoundedEntry(
            controls,
            textvariable=self.period_end_year_value,
            background=SURFACE_MUTED,
            height=36,
            font=app_font(10),
        )
        self.period_end_year_control.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=(7, 0),
        )
        self.period_end_year_control.bind_input(
            "<Return>",
            self.period_details_submitted,
        )
        description_panel = tk.Frame(controls, bg=SURFACE_MUTED)
        description_panel.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(12, 0),
        )
        description_panel.grid_columnconfigure(0, weight=1)
        description_panel.grid_rowconfigure(1, weight=1)
        description_label = tk.Label(
            description_panel,
            text="Description",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        description_label.grid(row=0, column=0, sticky="ew")
        self.period_description_control = RoundedText(
            description_panel,
            background=SURFACE_MUTED,
            height=3,
            font=app_font(9),
        )
        self.period_description_control.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(5, 0),
        )
        save_feedback = tk.Label(
            description_panel,
            textvariable=self.period_save_feedback_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        save_feedback.grid(
            row=2,
            column=0,
            sticky="w",
            pady=(7, 0),
        )
        self.save_period_button = SoftButton(
            description_panel,
            text="Save period",
            command=self.save_period_details,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=124,
            height=34,
        )
        self.save_period_button.grid(
            row=2,
            column=0,
            sticky="e",
            pady=(7, 0),
        )
        self.extinction_notice = tk.Label(
            parent,
            textvariable=self.extinction_notice_value,
            bg=EXTINCT_BEFORE_BACKGROUND,
            fg=EXTINCT_BEFORE_TEXT,
            font=app_font(11, "bold"),
            anchor="w",
            justify="left",
            padx=12,
            pady=9,
        )
        self.extinction_notice.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(9, 0),
        )
        self.extinction_notice.grid_remove()
        summary = tk.Label(
            parent,
            textvariable=self.summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        summary.grid(row=2, column=0, sticky="ew", pady=(9, 7))

    def build_category_grid(self, parent):
        category_grid = tk.Frame(parent, bg=SURFACE)
        category_grid.grid(row=3, column=0, sticky="nsew")
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

    def build_events_list(self, parent):
        events_panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        events_panel.grid(
            row=4,
            column=0,
            sticky="nsew",
            pady=(10, 0),
        )
        events_panel.grid_rowconfigure(2, weight=1)
        events_panel.grid_columnconfigure(0, weight=1)
        events_heading = tk.Label(
            events_panel,
            textvariable=self.events_title_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        events_heading.grid(row=0, column=0, sticky="ew")
        events_hint = tk.Label(
            events_panel,
            text=(
                "Events from the selected region, its nested places, and "
                "applicable parent regions. Double-click to open the source."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
        )
        events_hint.grid(row=1, column=0, sticky="ew", pady=(2, 6))
        events_frame = tk.Frame(events_panel, bg=SURFACE_MUTED)
        events_frame.grid(row=2, column=0, sticky="nsew")
        events_frame.grid_rowconfigure(0, weight=1)
        events_frame.grid_columnconfigure(0, weight=1)
        self.events_list = tk.Listbox(
            events_frame,
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
        self.events_list.grid(row=0, column=0, sticky="nsew")
        self.events_list.bind("<Double-Button-1>", self.open_selected_event)
        events_scrollbar = tk.Scrollbar(
            events_frame,
            command=self.events_list.yview,
        )
        events_scrollbar.grid(row=0, column=1, sticky="ns")
        self.events_list.configure(yscrollcommand=events_scrollbar.set)

    def refresh(self):
        retained_location_id = self.selected_location_id
        self.location_records = self.controller.list_locations()
        available_location_ids = {
            str(location.get("record_id", "") or "")
            for location in self.location_records
        }
        self.selected_location_id = (
            retained_location_id
            if (
                retained_location_id in available_location_ids
                and location_id_is_in_scope(
                    retained_location_id,
                    self.location_records,
                    self.region_lock_id,
                )
            )
            else self.region_lock_id
        )
        self.location_tree.set_locations(
            self.location_records,
            self.selected_location_id,
        )
        self.location_tree.set_scope(self.region_lock_id)
        self.selected_location_id = self.location_tree.selected_location_id
        self.update_period_details()
        self.calculate(silent=True)

    def set_region_lock(self, location_id="", notify=False):
        requested_id = str(location_id or "").strip()

        if not self.location_records:
            self.region_lock_id = requested_id

            if notify and self.scope_change_command is not None:
                self.scope_change_command(self.region_lock_id)

            return

        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.location_records
        }

        if requested_id not in available_ids:
            requested_id = ""

        self.region_lock_id = requested_id
        self.location_tree.set_scope(requested_id, notify=False)

        if not location_id_is_in_scope(
            self.selected_location_id,
            self.location_records,
            self.region_lock_id,
        ):
            self.selected_location_id = self.region_lock_id

        self.location_tree.select_location(self.selected_location_id)
        self.calculate(silent=True)

        if notify and self.scope_change_command is not None:
            self.scope_change_command(self.region_lock_id)

    def region_scope_changed(self, location_id):
        self.set_region_lock(location_id, notify=True)

    def location_selected(self, location_id):
        requested_id = str(location_id or "")

        if not location_id_is_in_scope(
            requested_id,
            self.location_records,
            self.region_lock_id,
        ):
            requested_id = self.region_lock_id

        self.selected_location_id = requested_id
        self.calculate(silent=True)

    def period_selected(self, event=None):
        self.clear_save_feedback()
        self.update_period_details()
        self.calculate()

    def select_previous_period(self, event=None):
        return self.step_period(-1)

    def select_next_period(self, event=None):
        return self.step_period(1)

    def step_period(self, direction):
        period_names = [
            period["name"]
            for period in self.period_definitions
        ]

        if not period_names:
            return "break"

        current_name = self.period_value.get().strip()

        try:
            current_index = period_names.index(current_name)
        except ValueError:
            current_index = 0

        next_index = max(
            0,
            min(len(period_names) - 1, current_index + int(direction)),
        )
        self.period_picker.current(next_index)
        self.period_value.set(period_names[next_index])
        self.period_selected()
        return "break"

    def period_details_submitted(self, event=None):
        self.save_period_details()
        return "break"

    def selected_period_definition(self):
        return self.periods_by_name.get(self.period_value.get().strip())

    def update_period_details(self):
        period = self.selected_period_definition()

        if period is None:
            self.period_start_year_value.set("")
            self.period_end_year_value.set("")
            self.period_description_control.text.delete("1.0", "end")
            self.period_description_control.text.insert(
                "1.0",
                self.period_error or "Select a period.",
            )
            return

        descriptor = str(period.get("descriptor", "") or "").strip()
        self.period_start_year_value.set(str(period.get("start_year", "") or ""))
        self.period_end_year_value.set(str(period.get("end_year", "") or ""))
        self.period_description_control.text.delete("1.0", "end")
        self.period_description_control.text.insert("1.0", descriptor)

    def save_period_details(self):
        period = self.selected_period_definition()

        if period is None:
            messagebox.showerror(
                "Cannot save period",
                self.period_error or "Select a period.",
                parent=self,
            )
            return False

        descriptor = self.period_description_control.text.get(
            "1.0",
            "end-1c",
        )

        try:
            updated_definitions = update_period_definition(
                period["name"],
                self.period_start_year_value.get(),
                self.period_end_year_value.get(),
                descriptor,
            )
        except PeriodDefinitionError as error:
            messagebox.showerror(
                "Cannot save period",
                str(error),
                parent=self,
            )
            return False

        selected_period_name = period["name"]
        self.period_definitions = updated_definitions
        self.periods_by_name = {
            definition["name"]: definition
            for definition in self.period_definitions
        }
        self.period_picker.configure(
            values=[
                definition["name"]
                for definition in self.period_definitions
            ]
        )
        self.period_value.set(selected_period_name)
        self.update_period_details()
        self.calculate(silent=True)
        self.status_command(
            f"Saved {selected_period_name} and adjusted the surrounding periods"
        )
        self.show_save_feedback()
        return True

    def show_save_feedback(self):
        self.clear_save_feedback()
        self.period_save_feedback_value.set("✓ Saved")
        self.save_feedback_after_id = self.after(
            1800,
            self.clear_save_feedback,
        )

    def clear_save_feedback(self):
        if self.save_feedback_after_id is not None:
            try:
                self.after_cancel(self.save_feedback_after_id)
            except tk.TclError:
                pass

            self.save_feedback_after_id = None

        self.period_save_feedback_value.set("")

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
            period_events = self.controller.events_for_period(
                start_year,
                end_year,
                self.selected_location_id,
            )
        except (KeyError, TypeError, ValueError) as error:
            self.clear_results(str(error))

            if not silent:
                messagebox.showerror("Cannot calculate period", str(error), parent=self)

            return False

        total_matches = 0

        for category_key, panel in self.category_panels.items():
            category_people = results.get(category_key, [])
            panel.set_people(category_people)
            total_matches += len(category_people)

        self.set_events(period_events)
        location_name = self.selected_location_name()
        self.summary_value.set(
            f"{location_name}  ·  {total_matches} category entries  ·  "
            f"{len(period_events)} events"
        )
        self.update_extinction_notice(period)
        self.status_command(
            f"Calculated {period['name']} for {location_name}"
        )
        return True

    def set_events(self, events):
        self.period_events = list(events)
        self.events_list.delete(0, "end")
        self.events_title_value.set(
            f"Events in this period ({len(self.period_events)})"
        )

        for index, event in enumerate(self.period_events):
            date_text = format_line_item_date(
                event.get("date")
            )
            title = str(event.get("title", "") or "Event").strip()
            location_name = str(
                event.get("origin_location_name", "") or ""
            ).strip()
            kind_text = "mage" if event.get("event_kind") == "mage" else ""
            row_parts = [date_text, title]

            if location_name:
                row_parts.append(location_name)

            if kind_text:
                row_parts.append(kind_text)

            self.events_list.insert("end", "  ·  ".join(row_parts))
            self.events_list.itemconfigure(
                index,
                background=PERIOD_EVENT_COLORS[index % len(PERIOD_EVENT_COLORS)],
            )

    def selected_period_event(self):
        selection = self.events_list.curselection()

        if not selection:
            return None

        return self.period_events[selection[0]]

    def open_selected_event(self, event=None):
        selected_event = self.selected_period_event()

        if selected_event is None:
            return

        person_id = str(
            selected_event.get("related_person_id", "") or ""
        )

        if person_id:
            self.navigate_person_command(person_id)
            return

        location_id = str(
            selected_event.get("origin_location_id", "") or ""
        )

        if location_id and self.navigate_location_command is not None:
            self.navigate_location_command(location_id)

    def selected_location_name(self):
        if not self.selected_location_id:
            return WORLD_LOCATION_LABEL

        for location in self.location_records:
            if str(location.get("record_id", "") or "") == self.selected_location_id:
                return str(location.get("name", "") or "Unnamed")

        return WORLD_LOCATION_LABEL

    def selected_location_record(self):
        for location in self.location_records:
            if (
                str(location.get("record_id", "") or "")
                == self.selected_location_id
            ):
                return location

        return None

    def update_extinction_notice(self, period):
        location = self.selected_location_record()
        state = location_extinction_state(
            location,
            period.get("calculation_start_year"),
            period.get("calculation_end_year"),
        )

        if state not in ("before", "during"):
            self.extinction_notice_value.set("")
            self.extinction_notice.grid_remove()
            return

        location_name = str(location.get("name", "") or "This location")
        extinction_year = str(location.get("extinction_year", "") or "")

        if state == "before":
            self.extinction_notice_value.set(
                f"EXTINCT BEFORE THIS PERIOD  ·  {location_name} became "
                f"extinct in {extinction_year}."
            )
            self.extinction_notice.configure(
                bg=EXTINCT_BEFORE_BACKGROUND,
                fg=EXTINCT_BEFORE_TEXT,
            )
        else:
            self.extinction_notice_value.set(
                f"GOES EXTINCT DURING THIS PERIOD  ·  {location_name} "
                f"becomes extinct in {extinction_year}."
            )
            self.extinction_notice.configure(
                bg=EXTINCT_DURING_BACKGROUND,
                fg=EXTINCT_DURING_TEXT,
            )

        self.extinction_notice.grid()

    def clear_results(self, message):
        for panel in self.category_panels.values():
            panel.set_people([])

        self.set_events([])
        self.extinction_notice_value.set("")
        self.extinction_notice.grid_remove()
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
