import re
import tkinter as tk
from copy import deepcopy
from functools import partial
from tkinter import messagebox

from mage_maker.core.dates import (
    format_historical_display_date,
    format_line_item_date,
)
from mage_maker.sections.events.period_view import (
    PeriodEventsView as UnifiedPeriodEventsView,
)
from mage_maker.sections.events.dialog import PlaceholderLocationDialog
from mage_maker.sections.events.models import event_time_sort_key
from mage_maker.sections.events.types import event_type_label
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
    WORLD_LOCATION_LABEL,
    location_id_is_in_scope,
    location_ids_in_scope,
)
from mage_maker.sections.locations.models import (
    location_extinction_state,
    recent_location_label,
)
from mage_maker.sections.locations.period_definitions import (
    PeriodDefinitionError,
    load_period_definitions,
    update_period_definition,
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
    LabeledEntry,
    RoundedEntry,
    RoundedText,
    SoftButton,
)


CATEGORY_DEFINITIONS = (
    ("born", "Born"),
    ("living", "Living"),
    ("reproductively_active", "Reproductively active"),
    ("died", "Died"),
)
EXTINCT_BEFORE_BACKGROUND = "#EBCFD6"
EXTINCT_BEFORE_TEXT = "#6A2E3C"
EXTINCT_DURING_BACKGROUND = "#F1DDB7"
EXTINCT_DURING_TEXT = "#6A4A18"
EVENT_DATE_PATTERN = re.compile(
    r"^(-?\d{1,5})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$"
)
RECENT_PERIOD_LOCATION_COUNT = 5


class PeriodsPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        event_controller,
        status_command,
        navigate_person_command,
        scope_change_command=None,
        navigate_location_command=None,
        records_changed_command=None,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.event_controller = event_controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.scope_change_command = scope_change_command
        self.navigate_location_command = navigate_location_command
        self.records_changed_command = records_changed_command
        self.period_definitions = []
        self.periods_by_name = {}
        self.selected_period_name = ""
        self.period_error = ""
        self.region_lock_id = ""
        self.pages = {}
        self.navigation_buttons = {}
        self.active_view_name = "overview"
        self.save_feedback_after_id = None
        self.period_heading_value = tk.StringVar(value="Select a period")
        self.period_group_value = tk.StringVar()
        self.period_start_year_value = tk.StringVar()
        self.period_end_year_value = tk.StringVar()
        self.period_save_feedback_value = tk.StringVar()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_workspace()
        self.load_definitions()

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=PRIMARY_DARK, height=64)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        title = tk.Label(
            toolbar,
            text="Periods",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=20,
        )
        title.grid(row=0, column=0, sticky="nsew")

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
        self.period_sidebar = PeriodSidebar(
            workspace,
            self.period_selected,
        )
        workspace.add(self.period_sidebar, minsize=260, width=310)
        content_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        content_card.grid_rowconfigure(1, weight=1)
        content_card.grid_columnconfigure(0, weight=1)
        self.build_view_navigation(content_card)
        self.content = tk.Frame(content_card, bg=SURFACE)
        self.content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18),
        )
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.build_overview_page()
        self.events_view = UnifiedPeriodEventsView(
            self.content,
            self.controller,
            self.event_controller,
            self.status_command,
            self.navigate_person_command,
            self.navigate_location_command,
            self.event_saved,
        )
        self.events_view.grid(row=0, column=0, sticky="nsew")
        self.pages["events"] = self.events_view
        self.people_view = PeriodPeopleView(
            self.content,
            self.controller,
            self.status_command,
            self.navigate_person_command,
            self.people_scope_changed,
        )
        self.people_view.grid(row=0, column=0, sticky="nsew")
        self.pages["people"] = self.people_view
        workspace.add(content_card, minsize=760)
        self.show_view("overview")

    def build_view_navigation(self, parent):
        navigation = tk.Frame(parent, bg=SURFACE, padx=18, pady=14)
        navigation.grid(row=0, column=0, sticky="ew")
        navigation.grid_columnconfigure(3, weight=1)

        for view_name, label, width in (
            ("overview", "Overview", 110),
            ("events", "Events", 96),
            ("people", "People", 96),
        ):
            button = SoftButton(
                navigation,
                text=label,
                command=PeriodViewCommand(self, view_name),
                background=SURFACE,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=width,
                height=36,
            )
            button.grid(
                row=0,
                column=len(self.navigation_buttons),
                padx=(0, 7),
            )
            self.navigation_buttons[view_name] = button

        current_period = tk.Label(
            navigation,
            textvariable=self.period_heading_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        current_period.grid(row=0, column=3, sticky="e")

    def build_overview_page(self):
        page = tk.Frame(self.content, bg=SURFACE)
        page.grid(row=0, column=0, sticky="nsew")
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(2, weight=1)
        self.pages["overview"] = page
        heading_panel = tk.Frame(
            page,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=18,
            pady=15,
        )
        heading_panel.grid(row=0, column=0, sticky="ew")
        heading_panel.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            heading_panel,
            textvariable=self.period_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(17, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        group = tk.Label(
            heading_panel,
            textvariable=self.period_group_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
        )
        group.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        years_panel = tk.Frame(page, bg=SURFACE)
        years_panel.grid(row=1, column=0, sticky="ew", pady=(16, 0))
        years_panel.grid_columnconfigure((0, 1), weight=1)
        start_field = LabeledEntry(
            years_panel,
            "From",
            self.period_start_year_value,
            background=SURFACE,
        )
        start_field.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        start_field.control.bind_input(
            "<Return>",
            self.period_details_submitted,
        )
        end_field = LabeledEntry(
            years_panel,
            "Through",
            self.period_end_year_value,
            background=SURFACE,
        )
        end_field.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        end_field.control.bind_input(
            "<Return>",
            self.period_details_submitted,
        )
        calendar_notice = CalendarAdoptionNotice(
            years_panel,
            background=SURFACE,
            wraplength=640,
        )
        calendar_notice.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(5, 0),
        )
        description_panel = tk.Frame(page, bg=SURFACE)
        description_panel.grid(row=2, column=0, sticky="nsew", pady=(16, 0))
        description_panel.grid_columnconfigure(0, weight=1)
        description_panel.grid_rowconfigure(1, weight=1)
        description_label = tk.Label(
            description_panel,
            text="Description",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        description_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.period_description_control = RoundedText(
            description_panel,
            background=SURFACE,
            height=13,
        )
        self.period_description_control.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        footer = tk.Frame(page, bg=SURFACE)
        footer.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        footer.grid_columnconfigure(0, weight=1)
        feedback = tk.Label(
            footer,
            textvariable=self.period_save_feedback_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        feedback.grid(row=0, column=0, sticky="w")
        self.save_period_button = SoftButton(
            footer,
            text="Save period",
            command=self.save_period_details,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=124,
            height=36,
        )
        self.save_period_button.grid(row=0, column=1, sticky="e")

    def load_definitions(self, retained_period_name=""):
        requested_period_name = (
            retained_period_name
            or self.selected_period_name
        )

        try:
            definitions = load_period_definitions()
        except PeriodDefinitionError as error:
            self.period_definitions = []
            self.periods_by_name = {}
            self.period_error = str(error)
            self.selected_period_name = ""
            self.period_sidebar.set_periods([], "")
            self.update_overview()
            self.events_view.set_period(None)
            self.people_view.set_period(None)
            return False

        self.period_definitions = definitions
        self.periods_by_name = {
            period["name"]: period
            for period in definitions
        }
        self.period_error = ""

        if requested_period_name not in self.periods_by_name:
            requested_period_name = (
                definitions[0]["name"]
                if definitions
                else ""
            )

        self.selected_period_name = requested_period_name
        self.period_sidebar.set_periods(
            definitions,
            requested_period_name,
        )
        self.update_selected_period_views()
        return True

    def refresh(self):
        self.load_definitions(self.selected_period_name)
        self.people_view.set_region_lock(self.region_lock_id)
        return True

    def selected_period_definition(self):
        return self.periods_by_name.get(self.selected_period_name)

    def period_selected(self, period_name):
        requested_name = str(period_name or "").strip()

        if requested_name not in self.periods_by_name:
            return False

        if (
            requested_name != self.selected_period_name
            and not self.confirm_unsaved_event_changes()
        ):
            self.period_sidebar.select_period(
                self.selected_period_name,
                notify=False,
            )
            return False

        self.clear_save_feedback()
        self.selected_period_name = requested_name
        self.update_selected_period_views()
        self.status_command(f"Selected {requested_name}")
        return True

    def update_selected_period_views(self):
        period = self.selected_period_definition()
        self.update_overview()
        self.events_view.set_period(period)
        self.people_view.set_period(period)

    def update_overview(self):
        period = self.selected_period_definition()
        self.period_description_control.text.delete("1.0", "end")

        if period is None:
            self.period_heading_value.set("Select a period")
            self.period_group_value.set("")
            self.period_start_year_value.set("")
            self.period_end_year_value.set("")
            self.period_description_control.text.insert(
                "1.0",
                self.period_error or "Select a period from the left.",
            )
            self.save_period_button.set_enabled(False)
            return

        self.period_heading_value.set(period["name"])
        self.period_group_value.set(
            period.get("group_name")
            or "Independent period"
        )
        self.period_start_year_value.set(
            str(period.get("start_year", "") or "")
        )
        self.period_end_year_value.set(
            str(period.get("end_year", "") or "")
        )
        self.period_description_control.text.insert(
            "1.0",
            str(period.get("descriptor", "") or ""),
        )
        self.save_period_button.set_enabled(True)

    def show_view(self, view_name):
        if view_name not in self.pages:
            return False

        if (
            self.active_view_name == "events"
            and view_name != "events"
            and not self.confirm_unsaved_event_changes()
        ):
            return False

        self.active_view_name = view_name
        self.pages[view_name].tkraise()

        for name, button in self.navigation_buttons.items():
            if name == view_name:
                button.set_colors(PRIMARY, PRIMARY_HOVER, TEXT_DARK)
            else:
                button.set_colors(
                    BUTTON_SOFT,
                    BUTTON_SOFT_HOVER,
                    TEXT_DARK,
                )

        if view_name == "events":
            self.events_view.refresh()
        elif view_name == "people":
            self.people_view.refresh()

        return True

    def confirm_unsaved_event_changes(self):
        confirmation_command = getattr(
            getattr(self, "events_view", None),
            "confirm_unsaved_event_changes",
            None,
        )

        if not callable(confirmation_command):
            return True

        return bool(confirmation_command())

    def period_details_submitted(self, event=None):
        self.save_period_details()
        return "break"

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

        selected_name = period["name"]
        self.period_definitions = updated_definitions
        self.periods_by_name = {
            definition["name"]: definition
            for definition in updated_definitions
        }
        self.selected_period_name = selected_name
        self.period_sidebar.set_periods(
            updated_definitions,
            selected_name,
        )
        self.update_selected_period_views()
        self.status_command(
            f"Saved {selected_name} and adjusted the surrounding periods"
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

    def people_scope_changed(self, location_id):
        self.region_lock_id = str(location_id or "").strip()

        if self.scope_change_command is not None:
            self.scope_change_command(self.region_lock_id)

    def region_scope_changed(self, location_id):
        return self.set_region_lock(location_id, notify=True)

    def set_region_lock(self, location_id="", notify=False):
        self.region_lock_id = str(location_id or "").strip()
        self.people_view.set_region_lock(self.region_lock_id)

        if notify and self.scope_change_command is not None:
            self.scope_change_command(self.region_lock_id)

        return self.region_lock_id

    def event_saved(self, event=None):
        if self.records_changed_command is not None:
            self.records_changed_command()

        if isinstance(event, dict):
            inferred_period_name = self.event_controller.infer_period_name(
                event
            )

            if (
                inferred_period_name
                and inferred_period_name in self.periods_by_name
                and inferred_period_name != self.selected_period_name
            ):
                self.selected_period_name = inferred_period_name
                self.period_sidebar.select_period(
                    inferred_period_name,
                    notify=False,
                )
                self.update_selected_period_views()

            self.events_view.refresh(event.get("record_id", ""))
            self.status_command(
                f"Saved event {event.get('title', 'Event')}"
            )
        else:
            self.events_view.refresh()

    def open_event(self, record_id):
        event = self.event_controller.get_event(record_id)

        if event is None:
            return False

        period_name = self.event_controller.infer_period_name(event)

        if period_name and period_name in self.periods_by_name:
            self.selected_period_name = period_name
            self.period_sidebar.select_period(period_name, notify=False)
            self.update_selected_period_views()

        self.show_view("events")
        return self.events_view.select_event(record_id)

    def create_shortcut(self):
        self.show_view("events")
        self.events_view.add_event()

    def search_shortcut(self):
        self.period_sidebar.focus_search()


class PeriodViewCommand:
    def __init__(self, page, view_name):
        self.page = page
        self.view_name = view_name

    def __call__(self):
        self.page.show_view(self.view_name)


def period_sidebar_date_text(period):
    if not isinstance(period, dict):
        return ""

    start_year = str(period.get("start_year", "") or "")
    end_year = str(period.get("end_year", "") or "")
    return f"{start_year} to {end_year}"


class PeriodSidebar(tk.Frame):
    def __init__(self, parent, selection_command):
        super().__init__(
            parent,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        self.selection_command = selection_command
        self.periods = []
        self.visible_periods = []
        self.selected_period_name = ""
        self.period_name_by_line = {}
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_periods)
        self.grid_rowconfigure(3, weight=1)
        self.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            self,
            text="Periods",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        search_label = tk.Label(
            self,
            text="Search",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        search_label.grid(row=1, column=0, sticky="ew", pady=(12, 5))
        self.search_control = RoundedEntry(
            self,
            textvariable=self.search_value,
            background=SURFACE,
            height=36,
            font=app_font(10),
        )
        self.search_control.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 9),
        )
        self.search_control.bind_input("<Escape>", self.clear_search)
        list_frame = tk.Frame(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.period_list = tk.Text(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            wrap="none",
            cursor="hand2",
            padx=8,
            pady=5,
            spacing1=3,
            spacing3=5,
            takefocus=True,
        )
        self.period_list.grid(row=0, column=0, sticky="nsew")
        self.period_list.bind("<Button-1>", self.period_clicked)
        self.period_list.bind("<Up>", self.select_previous_visible_period)
        self.period_list.bind("<Down>", self.select_next_visible_period)
        self.period_list.bind("<Home>", self.select_first_visible_period)
        self.period_list.bind("<End>", self.select_last_visible_period)
        scrollbar = tk.Scrollbar(list_frame, command=self.period_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.period_list.configure(yscrollcommand=scrollbar.set)
        self.period_list.tag_configure(
            "period_name",
            font=app_font(10),
            foreground=TEXT_DARK,
        )
        self.period_list.tag_configure(
            "period_dates",
            font=app_font(8),
            foreground=TEXT_MUTED,
        )
        self.period_list.tag_configure(
            "alternate",
            background=LIST_ALTERNATE,
        )
        self.period_list.tag_configure(
            "selected",
            background=LIST_SELECTED,
        )
        self.period_list.configure(state="disabled")

    def set_periods(self, periods, selected_period_name=""):
        self.periods = [
            deepcopy(period)
            for period in periods
            if isinstance(period, dict)
        ]
        requested_name = str(selected_period_name or "").strip()

        if requested_name not in {
            period.get("name")
            for period in self.periods
        }:
            requested_name = (
                self.periods[0]["name"]
                if self.periods
                else ""
            )

        self.selected_period_name = requested_name
        self.filter_periods()

    def filter_periods(self, *arguments):
        query = self.search_value.get().strip().casefold()
        self.visible_periods = [
            period
            for period in self.periods
            if not query
            or query in str(period.get("name", "") or "").casefold()
            or query in str(period.get("group_name", "") or "").casefold()
            or query in str(period.get("descriptor", "") or "").casefold()
            or query in period_sidebar_date_text(period).casefold()
        ]
        self.render_periods()

    def render_periods(self):
        self.period_name_by_line = {}
        self.period_list.configure(state="normal")
        self.period_list.delete("1.0", "end")
        selected_index = None

        for index, period in enumerate(self.visible_periods):
            line_number = int(self.period_list.index("end-1c").split(".")[0])
            name_start = self.period_list.index("end-1c")
            self.period_list.insert("end", f"{period['name']}\n")
            name_end = self.period_list.index("end-1c")
            dates_start = name_end
            self.period_list.insert(
                "end",
                f"{period_sidebar_date_text(period)}\n",
            )
            dates_end = self.period_list.index("end-1c")
            self.period_name_by_line[line_number] = period["name"]
            self.period_name_by_line[line_number + 1] = period["name"]
            self.period_list.tag_add("period_name", name_start, name_end)
            self.period_list.tag_add("period_dates", dates_start, dates_end)

            if index % 2:
                self.period_list.tag_add(
                    "alternate",
                    name_start,
                    dates_end,
                )

            if period["name"] == self.selected_period_name:
                self.period_list.tag_add(
                    "selected",
                    name_start,
                    dates_end,
                )
                selected_index = name_start

        self.period_list.configure(state="disabled")

        if selected_index is not None:
            self.period_list.see(selected_index)

    def period_clicked(self, event):
        text_index = self.period_list.index(f"@{event.x},{event.y}")
        line_number = int(text_index.split(".")[0])
        period_name = self.period_name_by_line.get(line_number, "")

        if period_name:
            self.select_period(period_name, notify=True)
            self.period_list.focus_set()

        return "break"

    def select_period(self, period_name, notify=True):
        requested_name = str(period_name or "").strip()

        if requested_name not in {
            period.get("name")
            for period in self.periods
        }:
            return False

        self.selected_period_name = requested_name

        if requested_name not in {
            period.get("name")
            for period in self.visible_periods
        }:
            self.search_value.set("")
        else:
            self.render_periods()

        if notify:
            self.selection_command(requested_name)

        return True

    def select_previous_visible_period(self, event=None):
        return self.select_adjacent_visible_period(-1)

    def select_next_visible_period(self, event=None):
        return self.select_adjacent_visible_period(1)

    def select_first_visible_period(self, event=None):
        if self.visible_periods:
            self.select_period(
                self.visible_periods[0]["name"],
                notify=True,
            )

        return "break"

    def select_last_visible_period(self, event=None):
        if self.visible_periods:
            self.select_period(
                self.visible_periods[-1]["name"],
                notify=True,
            )

        return "break"

    def select_adjacent_visible_period(self, direction):
        if not self.visible_periods:
            return "break"

        period_names = [
            period["name"]
            for period in self.visible_periods
        ]

        if self.selected_period_name in period_names:
            current_index = period_names.index(self.selected_period_name)
        else:
            current_index = 0

        next_index = max(
            0,
            min(
                len(period_names) - 1,
                current_index + int(direction),
            ),
        )
        self.select_period(period_names[next_index], notify=True)
        return "break"

    def clear_search(self, event=None):
        self.search_value.set("")
        self.focus_search()
        return "break"

    def focus_search(self):
        self.search_control.focus_set()
        self.search_control.selection_range(0, "end")


class LegacyPeriodEventsView(tk.Frame):
    def __init__(
        self,
        parent,
        location_controller,
        event_controller,
        status_command,
        navigate_person_command,
        navigate_location_command,
        changed_command,
    ):
        super().__init__(parent, bg=SURFACE)
        self.location_controller = location_controller
        self.event_controller = event_controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.navigate_location_command = navigate_location_command
        self.changed_command = changed_command
        self.period = None
        self.events = []
        self.selected_event_id = ""
        self.title_value = tk.StringVar(value="Events (0)")
        self.type_value = tk.StringVar(value="No event selected")
        self.date_value = tk.StringVar(value="Date: nd.")
        self.people_value = tk.StringVar(value="None")
        self.periods_value = tk.StringVar(value="None")
        self.locations_value = tk.StringVar(value="None")
        self.source_value = tk.StringVar()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_workspace()

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=SURFACE, height=46)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            toolbar,
            textvariable=self.title_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="nsew")
        self.add_button = SoftButton(
            toolbar,
            text="Add event",
            command=self.add_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        self.add_button.grid(row=0, column=1, padx=(6, 0), pady=5)
        self.edit_button = SoftButton(
            toolbar,
            text="Edit",
            command=self.edit_event,
            background=SURFACE,
            width=82,
            height=36,
        )
        self.edit_button.grid(row=0, column=2, padx=(6, 0), pady=5)
        self.remove_button = SoftButton(
            toolbar,
            text="Remove",
            command=self.remove_event,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            width=92,
            height=36,
        )
        self.remove_button.grid(row=0, column=3, padx=(6, 0), pady=5)

    def build_workspace(self):
        workspace = tk.Frame(self, bg=SURFACE)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=5, uniform="events")
        workspace.grid_columnconfigure(1, weight=4, uniform="events")
        list_panel = tk.Frame(
            workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=11,
        )
        list_panel.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        list_panel.grid_rowconfigure(1, weight=1)
        list_panel.grid_columnconfigure(0, weight=1)
        hint = tk.Label(
            list_panel,
            text=(
                "Events associated with this period."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        hint.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        list_frame = tk.Frame(list_panel, bg=SURFACE_MUTED)
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame,
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
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.event_selected)
        self.listbox.bind("<Double-Button-1>", self.edit_event)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        details = tk.Frame(
            workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        details.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        details.grid_columnconfigure(0, weight=1)
        details.grid_rowconfigure(10, weight=1)
        details_heading = tk.Label(
            details,
            text="Selected event",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        details_heading.grid(row=0, column=0, sticky="ew")
        type_label = tk.Label(
            details,
            textvariable=self.type_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        type_label.grid(row=1, column=0, sticky="ew", pady=(13, 2))
        date_label = tk.Label(
            details,
            textvariable=self.date_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        date_label.grid(row=2, column=0, sticky="ew")
        self.build_association_detail(
            details,
            3,
            "People",
            self.people_value,
        )
        self.build_association_detail(
            details,
            5,
            "Periods",
            self.periods_value,
        )
        self.build_association_detail(
            details,
            7,
            "Locations",
            self.locations_value,
        )
        source_heading = tk.Label(
            details,
            text="Source",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        source_heading.grid(row=9, column=0, sticky="ew", pady=(12, 3))
        source_label = tk.Label(
            details,
            textvariable=self.source_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        source_label.grid(row=10, column=0, sticky="new")
        description_heading = tk.Label(
            details,
            text="Description",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        description_heading.grid(row=11, column=0, sticky="ew", pady=(12, 4))
        self.description_text = tk.Text(
            details,
            height=7,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            wrap="word",
            padx=9,
            pady=8,
            state="disabled",
        )
        self.description_text.grid(row=12, column=0, sticky="nsew")
        self.update_details()

    def build_association_detail(self, parent, row, title, variable):
        heading = tk.Label(
            parent,
            text=title,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        heading.grid(row=row, column=0, sticky="ew", pady=(12, 2))
        value = tk.Label(
            parent,
            textvariable=variable,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        value.grid(row=row + 1, column=0, sticky="ew")

    def set_period(self, period):
        self.period = deepcopy(period) if isinstance(period, dict) else None
        self.selected_event_id = ""
        self.refresh()

    def refresh(self, selected_event_id=""):
        if selected_event_id:
            self.selected_event_id = str(selected_event_id)

        self.events = []

        if self.period is None:
            self.render_events()
            return

        start_year = self.period["calculation_start_year"]
        end_year = self.period["calculation_end_year"]
        shared_events = self.event_controller.events_for_period(
            self.period["name"],
            start_year,
            end_year,
        )
        legacy_events = self.location_controller.events_for_period(
            start_year,
            end_year,
            "",
        )

        for event in shared_events:
            row = deepcopy(event)
            row["event_kind"] = "global"
            row["event_id"] = event["record_id"]
            row["association_labels"] = (
                self.event_controller.association_labels(event)
            )
            self.events.append(row)

        for event in legacy_events:
            row = deepcopy(event)
            row["event_id"] = str(event.get("event_id", "") or "")
            row["association_labels"] = self.legacy_association_labels(row)
            self.events.append(row)

        self.events.sort(key=period_event_sort_key)
        self.render_events()

    def legacy_association_labels(self, event):
        person_id = str(event.get("related_person_id", "") or "")
        location_id = str(event.get("origin_location_id", "") or "")
        people_by_id = {
            option["value"]: option["label"]
            for option in self.event_controller.people_options()
        }
        locations_by_id = {
            option["value"]: option["label"]
            for option in self.event_controller.location_options()
        }
        return {
            "people": (
                [people_by_id.get(person_id, "Missing person")]
                if person_id
                else []
            ),
            "periods": (
                [self.period["name"]]
                if self.period is not None
                else []
            ),
            "locations": (
                [locations_by_id.get(location_id, "Missing location")]
                if location_id
                else []
            ),
        }

    def render_events(self):
        self.listbox.delete(0, "end")
        self.title_value.set(f"Events ({len(self.events)})")

        for index, event in enumerate(self.events):
            date_text = format_line_item_date(
                event.get("date")
            )
            time_text = str(event.get("time", "") or "").strip()

            if time_text:
                date_text = f"{date_text} {time_text}"

            event_type = self.event_type_text(event)
            title = str(event.get("title", "") or "Event")
            self.listbox.insert(
                "end",
                f"{date_text}  ·  {event_type}  ·  {title}",
            )
            self.listbox.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if event.get("event_id") == self.selected_event_id:
                self.listbox.selection_set(index)
                self.listbox.see(index)

        if self.selected_event() is None:
            self.selected_event_id = ""

        self.update_details()

    def event_type_text(self, event):
        return event_type_label(event)

    def event_selected(self, event=None):
        selection = self.listbox.curselection()

        if not selection:
            return

        self.selected_event_id = self.events[selection[0]]["event_id"]
        self.update_details()

    def selected_event(self):
        for event in self.events:
            if event.get("event_id") == self.selected_event_id:
                return event

        return None

    def update_details(self):
        event = self.selected_event()
        self.description_text.configure(state="normal")
        self.description_text.delete("1.0", "end")

        if event is None:
            self.type_value.set("No event selected")
            self.date_value.set("Date: nd.")
            self.people_value.set("None")
            self.periods_value.set("None")
            self.locations_value.set("None")
            self.source_value.set("Select an event to view its links.")
            self.edit_button.set_enabled(False)
            self.remove_button.set_enabled(False)
        else:
            labels = event.get("association_labels", {})
            self.type_value.set(
                f"{self.event_type_text(event)} · "
                f"{event.get('title', 'Event')}"
            )
            self.date_value.set(
                "Date: "
                + format_historical_display_date(event.get("date"))
                + (
                    f" {event.get('time')}"
                    if event.get("time")
                    else ""
                )
            )
            self.people_value.set(
                ", ".join(labels.get("people", [])) or "None"
            )
            self.periods_value.set(
                ", ".join(labels.get("periods", [])) or "None"
            )
            self.locations_value.set(
                ", ".join(labels.get("locations", [])) or "None"
            )
            self.source_value.set(self.event_source_text(event))
            self.description_text.insert(
                "1.0",
                str(
                    event.get("description")
                    if event.get("event_kind") == "global"
                    else event.get("note", "")
                    or ""
                ),
            )
            self.edit_button.set_enabled(True)
            self.remove_button.set_enabled(
                event.get("event_kind") == "global"
            )

        self.description_text.configure(state="disabled")

    def event_source_text(self, event):
        if event.get("event_kind") == "global":
            return "Linked event · editable from every associated record"

        if event.get("event_kind") == "mage":
            return "Existing individual event · open the person to edit"

        location_name = str(
            event.get("origin_location_name", "") or "source location"
        )
        return (
            f"Existing location event · open {location_name} to edit"
        )

    def add_event(self):
        if self.period is None:
            return

        WorldEventDialog(
            self,
            self.event_controller,
            saved_command=self.changed_command,
        )

    def edit_event(self, event=None):
        selected = self.selected_event()

        if selected is None:
            return

        if selected.get("event_kind") == "global":
            WorldEventDialog(
                self,
                self.event_controller,
                selected,
                self.changed_command,
            )
            return

        self.open_legacy_source(selected)

    def remove_event(self):
        selected = self.selected_event()

        if selected is None or selected.get("event_kind") != "global":
            return

        if not messagebox.askyesno(
            "Remove shared event",
            f"Remove {selected.get('title', 'this event')} everywhere?",
            parent=self,
        ):
            return

        try:
            deleted = self.event_controller.delete_event(
                selected["record_id"]
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot remove event",
                str(error),
                parent=self,
            )
            return

        self.selected_event_id = ""
        self.refresh()
        self.status_command(
            f"Removed event {deleted.get('title', 'Event')}"
        )
        self.changed_command(None)

    def open_legacy_source(self, event):
        person_id = str(event.get("related_person_id", "") or "")

        if person_id:
            self.navigate_person_command(person_id)
            return

        location_id = str(event.get("origin_location_id", "") or "")

        if location_id and self.navigate_location_command is not None:
            self.navigate_location_command(location_id)

    def select_event(self, record_id):
        requested_id = str(record_id or "")

        for index, event in enumerate(self.events):
            if event.get("event_id") != requested_id:
                continue

            self.selected_event_id = requested_id
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(index)
            self.listbox.see(index)
            self.update_details()
            return True

        return False


class PeriodLocationDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        selected_location_id,
        save_command,
        region_lock_id="",
        create_location_command=None,
    ):
        super().__init__(parent)
        self.locations = [
            deepcopy(location)
            for location in locations
            if isinstance(location, dict)
        ]
        self.selected_location_id = str(
            selected_location_id or ""
        ).strip()
        self.save_command = save_command
        self.region_lock_id = str(region_lock_id or "").strip()
        self.create_location_command = create_location_command
        self.selection_value = tk.StringVar(value=WORLD_LOCATION_LABEL)
        self.title("Select location")
        self.geometry("620x680")
        self.minsize(500, 520)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.location_tree.set_locations(
            self.locations,
            self.selected_location_id,
        )
        self.selected_location_id = (
            self.location_tree.selected_location_id
        )
        self.location_selected(self.selected_location_id)
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="Select another location",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Search by a location name or any part of its path, "
                "then choose the exact place from the hierarchy."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.location_tree = LocationHierarchyTree(
            card,
            self.location_selected,
            background=SURFACE,
            show_scope_controls=False,
            initial_scope_location_id=self.region_lock_id,
        )
        self.location_tree.grid(row=2, column=0, sticky="nsew")
        selected_label = tk.Label(
            card,
            textvariable=self.selection_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        selected_label.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=4, column=0, sticky="e", pady=(14, 0))

        if self.create_location_command is not None:
            new_location_button = SoftButton(
                footer,
                text="New location",
                command=self.open_placeholder_location,
                background=SURFACE,
                width=112,
                height=36,
            )
            new_location_button.pack(side="left", padx=(0, 6))

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        choose_button = SoftButton(
            footer,
            text="Use location",
            command=self.choose_location,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=118,
            height=36,
        )
        choose_button.pack(side="left")

    def location_selected(self, location_id):
        requested_id = str(location_id or "").strip()

        if not requested_id and self.region_lock_id:
            requested_id = self.region_lock_id

        self.selected_location_id = requested_id
        self.selection_value.set(
            recent_location_label(requested_id, self.locations)
        )

    def open_placeholder_location(self):
        if self.create_location_command is None:
            return False

        scoped_ids = location_ids_in_scope(
            self.locations,
            self.region_lock_id,
        )
        available_locations = [
            location
            for location in self.locations
            if (
                not self.region_lock_id
                or str(location.get("record_id", "") or "").strip()
                in scoped_ids
            )
        ]
        PlaceholderLocationDialog(
            self,
            available_locations,
            self.selected_location_id or self.region_lock_id,
            self.create_location_command,
            self.placeholder_location_created,
            allow_world_parent=not bool(self.region_lock_id),
        )
        return True

    def placeholder_location_created(self, location):
        if not isinstance(location, dict):
            return False

        record_id = str(location.get("record_id", "") or "").strip()

        if not record_id:
            return False

        self.locations = [
            existing_location
            for existing_location in self.locations
            if str(existing_location.get("record_id", "") or "").strip()
            != record_id
        ]
        self.locations.append(deepcopy(location))
        self.selected_location_id = record_id
        self.location_tree.set_locations(
            self.locations,
            self.selected_location_id,
        )
        self.location_tree.set_scope(self.region_lock_id)
        self.location_tree.select_location(
            self.selected_location_id,
        )
        self.location_selected(self.selected_location_id)
        return True

    def choose_location(self):
        self.save_command(self.selected_location_id)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class PeriodPeopleView(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        status_command,
        navigate_person_command,
        scope_change_command,
    ):
        super().__init__(parent, bg=SURFACE)
        self.controller = controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.scope_change_command = scope_change_command
        self.period = None
        self.location_records = []
        self.selected_location_id = ""
        self.region_lock_id = ""
        self.recent_location_ids = []
        self.recent_location_buttons = []
        self.current_location_value = tk.StringVar(
            value=WORLD_LOCATION_LABEL
        )
        self.has_no_children_value = tk.BooleanVar(value=False)
        self.summary_value = tk.StringVar(
            value="Select a period and location."
        )
        self.extinction_notice_value = tk.StringVar()
        self.category_panels = {}
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_workspace()

    def build_workspace(self):
        workspace = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=BORDER_SOFT,
            borderwidth=0,
            sashwidth=5,
            sashrelief="flat",
            showhandle=False,
        )
        workspace.grid(row=0, column=0, sticky="nsew")
        location_panel = tk.Frame(
            workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=11,
        )
        location_panel.grid_rowconfigure(5, weight=1)
        location_panel.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            location_panel,
            text="People location",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        hint = tk.Label(
            location_panel,
            text=(
                "Choose one of the five most recently used locations, "
                "or search the full hierarchy."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=250,
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(3, 8))
        current_location = tk.Label(
            location_panel,
            textvariable=self.current_location_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
            justify="left",
            padx=10,
            pady=8,
            wraplength=238,
        )
        current_location.grid(row=2, column=0, sticky="ew")
        recent_heading = tk.Label(
            location_panel,
            text="Recent locations",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        recent_heading.grid(row=3, column=0, sticky="ew", pady=(10, 5))
        recent_panel = tk.Frame(location_panel, bg=SURFACE_MUTED)
        recent_panel.grid(row=4, column=0, sticky="ew")
        recent_panel.grid_columnconfigure(0, weight=1)

        for index in range(RECENT_PERIOD_LOCATION_COUNT):
            button = SoftButton(
                recent_panel,
                text="",
                command=partial(self.select_recent_location, index),
                background=SURFACE_MUTED,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=248,
                height=36,
                font=app_font(9, "bold"),
            )
            button.grid(
                row=index,
                column=0,
                sticky="ew",
                pady=(0, 5),
            )
            button.grid_remove()
            self.recent_location_buttons.append(button)

        select_other_button = SoftButton(
            location_panel,
            text="Select other",
            command=self.open_location_dialog,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=36,
        )
        select_other_button.grid(
            row=6,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )
        workspace.add(location_panel, minsize=260, width=285)
        results = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=11,
        )
        results.grid_rowconfigure(2, weight=1)
        results.grid_columnconfigure(0, weight=1)
        self.extinction_notice = tk.Label(
            results,
            textvariable=self.extinction_notice_value,
            bg=EXTINCT_BEFORE_BACKGROUND,
            fg=EXTINCT_BEFORE_TEXT,
            font=app_font(10, "bold"),
            anchor="w",
            justify="left",
            padx=12,
            pady=8,
        )
        self.extinction_notice.grid(row=0, column=0, sticky="ew")
        self.extinction_notice.grid_remove()
        summary = tk.Label(
            results,
            textvariable=self.summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        summary.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        category_grid = tk.Frame(results, bg=SURFACE)
        category_grid.grid(row=2, column=0, sticky="nsew")
        category_grid.grid_rowconfigure(0, weight=1)
        category_grid.grid_columnconfigure(
            (0, 1, 2, 3),
            weight=1,
            uniform="period_people",
        )

        for index, (category_key, title) in enumerate(
            CATEGORY_DEFINITIONS
        ):
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
                    (0, 4)
                    if index == 0
                    else (4, 0)
                    if index == 3
                    else 4
                ),
            )
            self.category_panels[category_key] = panel

        workspace.add(results, minsize=690)

    def set_period(self, period):
        self.period = deepcopy(period) if isinstance(period, dict) else None
        self.calculate(silent=True)

    def refresh(self):
        retained_location_id = self.selected_location_id
        self.location_records = self.controller.list_locations()
        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.location_records
        }

        if self.region_lock_id not in available_ids:
            self.region_lock_id = ""

        self.selected_location_id = (
            retained_location_id
            if (
                retained_location_id in available_ids
                and location_id_is_in_scope(
                    retained_location_id,
                    self.location_records,
                    self.region_lock_id,
                )
            )
            else self.region_lock_id
        )
        self.refresh_location_choices()
        self.calculate(silent=True)

    def set_region_lock(self, location_id=""):
        requested_id = str(location_id or "").strip()

        if self.location_records:
            available_ids = {
                str(location.get("record_id", "") or "")
                for location in self.location_records
            }

            if requested_id not in available_ids:
                requested_id = ""

        self.region_lock_id = requested_id

        if not location_id_is_in_scope(
            self.selected_location_id,
            self.location_records,
            self.region_lock_id,
        ):
            self.selected_location_id = self.region_lock_id

        self.refresh_location_choices()
        self.calculate(silent=True)

    def region_scope_changed(self, location_id):
        self.region_lock_id = str(location_id or "").strip()
        self.selected_location_id = self.region_lock_id
        self.refresh_location_choices()
        self.calculate(silent=True)

        if self.scope_change_command is not None:
            self.scope_change_command(self.region_lock_id)

    def location_selected(self, location_id):
        requested_id = str(location_id or "")

        if not location_id_is_in_scope(
            requested_id,
            self.location_records,
            self.region_lock_id,
        ):
            requested_id = self.region_lock_id

        self.selected_location_id = requested_id
        self.controller.remember_location_interaction(requested_id)
        self.refresh_location_choices()
        self.calculate(silent=True)

    def recent_locations_for_display(self):
        candidate_ids = [
            self.selected_location_id,
            *self.controller.recent_location_ids(
                RECENT_PERIOD_LOCATION_COUNT * 3
            ),
        ]
        display_ids = []

        for location_id in candidate_ids:
            normalized_id = str(location_id or "").strip()

            if not location_id_is_in_scope(
                normalized_id,
                self.location_records,
                self.region_lock_id,
            ):
                continue

            if normalized_id in display_ids:
                continue

            display_ids.append(normalized_id)

            if len(display_ids) >= RECENT_PERIOD_LOCATION_COUNT:
                break

        return display_ids

    def refresh_location_choices(self):
        self.current_location_value.set(
            "Current: "
            + recent_location_label(
                self.selected_location_id,
                self.location_records,
            )
        )
        self.recent_location_ids = self.recent_locations_for_display()

        for index, button in enumerate(self.recent_location_buttons):
            if index >= len(self.recent_location_ids):
                button.grid_remove()
                continue

            location_id = self.recent_location_ids[index]
            button.set_text(
                recent_location_label(
                    location_id,
                    self.location_records,
                )
            )
            button.set_enabled(True)

            if location_id == self.selected_location_id:
                button.set_colors(
                    PRIMARY,
                    PRIMARY_HOVER,
                    TEXT_DARK,
                )
            else:
                button.set_colors(
                    BUTTON_SOFT,
                    BUTTON_SOFT_HOVER,
                    TEXT_DARK,
                )

            button.grid()

    def select_recent_location(self, index):
        normalized_index = int(index)

        if (
            normalized_index < 0
            or normalized_index >= len(self.recent_location_ids)
        ):
            return False

        self.location_selected(
            self.recent_location_ids[normalized_index]
        )
        return True

    def open_location_dialog(self):
        PeriodLocationDialog(
            self,
            self.location_records,
            self.selected_location_id,
            self.location_dialog_selected,
            self.region_lock_id,
            self.controller.create_placeholder_location,
        )

    def location_dialog_selected(self, location_id):
        self.location_records = self.controller.list_locations()
        self.location_selected(location_id)

    def calculate(self, silent=False):
        if self.period is None:
            self.clear_results("Select a period from the left.")
            return False

        try:
            results = self.controller.people_for_period(
                self.period["calculation_start_year"],
                self.period["calculation_end_year"],
                self.selected_location_id,
                reproductive_without_children=(
                    self.has_no_children_value.get()
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            self.clear_results(str(error))

            if not silent:
                messagebox.showerror(
                    "Cannot calculate people",
                    str(error),
                    parent=self,
                )

            return False

        total_matches = 0

        for category_key, panel in self.category_panels.items():
            people = results.get(category_key, [])
            panel.set_people(people)
            total_matches += len(people)

        location_name = self.selected_location_name()
        self.summary_value.set(
            f"{self.period['name']}  ·  {location_name}  ·  "
            f"{total_matches} category entries"
        )
        self.update_extinction_notice()
        return True

    def selected_location_name(self):
        return recent_location_label(
            self.selected_location_id,
            self.location_records,
        )

    def selected_location_record(self):
        for location in self.location_records:
            if (
                str(location.get("record_id", "") or "")
                == self.selected_location_id
            ):
                return location

        return None

    def update_extinction_notice(self):
        location = self.selected_location_record()

        if self.period is None:
            state = ""
        else:
            state = location_extinction_state(
                location,
                self.period.get("calculation_start_year"),
                self.period.get("calculation_end_year"),
            )

        if state not in ("before", "during"):
            self.extinction_notice_value.set("")
            self.extinction_notice.grid_remove()
            return

        location_name = str(
            location.get("name", "") or "This location"
        )
        extinction_year = str(
            location.get("extinction_year", "") or ""
        )

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
            padx=10,
            pady=10,
        )
        self.title = title
        self.navigate_person_command = navigate_person_command
        self.people = []
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
        heading.grid(row=0, column=0, sticky="ew")

        if filter_variable is not None:
            filter_control = tk.Checkbutton(
                self,
                text="Has no children",
                variable=filter_variable,
                command=filter_command,
                bg=SURFACE_MUTED,
                fg=TEXT_DARK,
                activebackground=SURFACE_MUTED,
                activeforeground=TEXT_DARK,
                selectcolor=FIELD_BACKGROUND,
                font=app_font(8),
                anchor="w",
                borderwidth=0,
                highlightthickness=0,
            )
            filter_control.grid(
                row=1,
                column=0,
                sticky="w",
                pady=(4, 6),
            )
        else:
            spacer = tk.Frame(
                self,
                bg=SURFACE_MUTED,
                height=25,
            )
            spacer.grid(row=1, column=0, sticky="ew", pady=(4, 6))

        list_frame = tk.Frame(self, bg=SURFACE_MUTED)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(8),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind(
            "<Double-Button-1>",
            self.open_selected_person,
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

    def set_people(self, people):
        self.people = list(people)
        self.title_value.set(f"{self.title} ({len(self.people)})")
        self.listbox.delete(0, "end")

        for index, person in enumerate(self.people):
            displayed_name = str(
                person.get("displayed_name", "") or "Unnamed magician"
            )
            detail = str(
                person.get("period_date_text", "") or ""
            ).strip()
            location = str(
                person.get("period_location", "") or ""
            ).strip()
            row_parts = [displayed_name]

            if detail:
                row_parts.append(detail)

            if location:
                row_parts.append(location)

            self.listbox.insert("end", "  ·  ".join(row_parts))
            self.listbox.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

    def open_selected_person(self, event=None):
        selected = self.listbox.curselection()

        if not selected:
            return

        person_id = str(
            self.people[selected[0]].get("record_id", "") or ""
        )

        if person_id:
            self.navigate_person_command(person_id)


def period_event_sort_key(event):
    date_text = str(event.get("date", "") or "")
    match = EVENT_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        date_key = (100000, 13, 32)
    else:
        date_key = (
            int(match.group(1)),
            int(match.group(2) or 0),
            int(match.group(3) or 0),
        )

    return (
        date_key,
        event_time_sort_key(event.get("time")),
        str(event.get("title", "") or "").casefold(),
        str(event.get("event_id", "") or ""),
    )
