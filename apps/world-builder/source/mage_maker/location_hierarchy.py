import tkinter as tk
from tkinter import messagebox

from mage_maker.core.dates import (
    format_historical_display_date,
    format_line_item_date,
    split_partial_date,
)
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
    WORLD_LOCATION_LABEL,
    location_id_is_in_scope,
    location_ids_in_scope,
)
from mage_maker.sections.locations.models import descendant_ids
from mage_maker.sections.locations.periods_page import PeriodsPage
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
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
    LabeledEntry,
    RoundedEntry,
    RoundedText,
    SoftButton,
)


LOCAL_EVENT_COLORS = ("#FFFFFF", "#F1F1F1")
PROPAGATED_EVENT_COLORS = (
    "#E6D8F0",
    "#D9E7F3",
    "#DCEBDD",
    "#F1E7CF",
    "#E6DFD8",
)


class LocationPage(tk.Frame):
    def __init__(self, parent, controller, status_command, navigate_person_command):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.locations = []
        self.visible_events = []
        self.current_location_id = None
        self.active_section_name = "locations"
        self.creating_location = False
        self.region_lock_id = ""
        self.selected_parent_location_id = ""
        self.section_pages = {}
        self.section_buttons = {}
        self.toolbar_title_value = tk.StringVar(value="Locations")
        self.editor_heading_value = tk.StringVar(value="Location details")
        self.parent_path_value = tk.StringVar(value=WORLD_LOCATION_LABEL)
        self.name_value = tk.StringVar()
        self.extinct_value = tk.BooleanVar(value=False)
        self.extinction_year_value = tk.StringVar()
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_navigation()
        self.build_content()
        self.refresh()
        self.show_section("locations")

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=PRIMARY_DARK, height=64)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        self.toolbar_title = tk.Label(
            toolbar,
            textvariable=self.toolbar_title_value,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=20,
        )
        self.toolbar_title.grid(row=0, column=0, sticky="nsew")
        self.new_location_button = SoftButton(
            toolbar,
            text="New location",
            command=self.create_location,
            background=PRIMARY_DARK,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=38,
        )
        self.new_location_button.grid(row=0, column=1, padx=4, pady=13)
        self.delete_location_button = SoftButton(
            toolbar,
            text="Delete",
            command=self.delete_location,
            background=PRIMARY_DARK,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=88,
            height=38,
        )
        self.delete_location_button.grid(
            row=0,
            column=2,
            padx=(4, 16),
            pady=13,
        )

    def build_navigation(self):
        navigation = tk.Frame(self, bg=APP_BACKGROUND)
        navigation.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=18,
            pady=(10, 0),
        )

        for section_name, label, width in (
            ("locations", "Locations", 104),
            ("periods", "Periods", 96),
        ):
            button = SoftButton(
                navigation,
                text=label,
                command=LocationSectionCommand(self, section_name),
                background=APP_BACKGROUND,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=width,
                height=36,
            )
            button.pack(side="left", padx=(0, 6))
            self.section_buttons[section_name] = button

    def build_content(self):
        content = tk.Frame(self, bg=APP_BACKGROUND)
        content.grid(row=2, column=0, sticky="nsew")
        content.grid_rowconfigure(0, weight=1)
        content.grid_columnconfigure(0, weight=1)
        self.build_workspace(content)
        self.periods_page = PeriodsPage(
            content,
            self.controller,
            self.status_command,
            self.navigate_person_command,
            self.region_lock_changed,
            self.open_location_from_periods,
        )
        self.periods_page.grid(row=0, column=0, sticky="nsew")
        self.section_pages["periods"] = self.periods_page

    def build_workspace(self, parent):
        workspace = tk.PanedWindow(
            parent,
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
        self.section_pages["locations"] = workspace

        list_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=14,
            pady=14,
        )
        list_card.grid_rowconfigure(1, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        list_title = tk.Label(
            list_card,
            text="Location hierarchy",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        list_title.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        self.location_tree = LocationHierarchyTree(
            list_card,
            self.location_selected,
            background=SURFACE,
            scope_change_command=self.region_lock_changed,
        )
        self.location_tree.grid(row=1, column=0, sticky="nsew")

        editor_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        editor_card.grid_rowconfigure(3, weight=1)
        editor_card.grid_columnconfigure(0, weight=1)
        self.build_location_fields(editor_card)
        self.build_timeline(editor_card)

        workspace.add(list_card, minsize=290, width=330)
        workspace.add(editor_card, minsize=680)

    def show_section(self, section_name):
        if section_name not in self.section_pages:
            return False

        self.active_section_name = section_name

        if section_name == "periods":
            self.toolbar_title_value.set("Periods")
            self.new_location_button.grid_remove()
            self.delete_location_button.grid_remove()
            self.periods_page.refresh()
            self.periods_page.set_region_lock(self.region_lock_id)
        else:
            self.toolbar_title_value.set("Locations")
            self.new_location_button.grid()
            self.delete_location_button.grid()

        self.section_pages[section_name].tkraise()

        for name, button in self.section_buttons.items():
            if name == section_name:
                button.set_colors(PRIMARY, PRIMARY_HOVER, TEXT_DARK)
            else:
                button.set_colors(BUTTON_SOFT, BUTTON_SOFT_HOVER, TEXT_DARK)

        return True

    def save_shortcut(self):
        if self.active_section_name == "periods":
            return self.periods_page.save_period_details()

        return self.save_location()

    def create_shortcut(self):
        if self.active_section_name != "locations":
            return False

        self.create_location()
        return True

    def build_location_fields(self, parent):
        identity = tk.Frame(parent, bg=SURFACE_MUTED, padx=14, pady=12)
        identity.grid(row=0, column=0, sticky="ew")
        identity.grid_columnconfigure(0, weight=3)
        identity.grid_columnconfigure(1, weight=2)
        editor_heading = tk.Label(
            identity,
            textvariable=self.editor_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        editor_heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 10),
        )
        self.name_field = LabeledEntry(
            identity,
            "Location name",
            self.name_value,
            background=SURFACE_MUTED,
        )
        self.name_field.grid(row=1, column=0, sticky="ew", padx=(0, 7))
        parent_frame = tk.Frame(identity, bg=SURFACE_MUTED)
        parent_frame.grid(row=1, column=1, sticky="ew", padx=(7, 0))
        parent_frame.grid_columnconfigure(0, weight=1)
        parent_label = tk.Label(
            parent_frame,
            text="Within region",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        parent_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        parent_display = tk.Frame(
            parent_frame,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER,
            highlightthickness=1,
            height=40,
        )
        parent_display.grid(row=1, column=0, sticky="ew")
        parent_display.grid_propagate(False)
        parent_display.grid_columnconfigure(0, weight=1)
        parent_path = tk.Label(
            parent_display,
            textvariable=self.parent_path_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=10,
        )
        parent_path.grid(row=0, column=0, sticky="nsew")
        self.change_parent_button = SoftButton(
            parent_display,
            text="Change",
            command=self.choose_parent_location,
            background=FIELD_BACKGROUND,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=78,
            height=32,
            font=app_font(9, "bold"),
        )
        self.change_parent_button.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(4, 4),
            pady=4,
        )
        extinction_options = tk.Frame(identity, bg=SURFACE_MUTED)
        extinction_options.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(11, 0),
        )
        extinction_checkbox = tk.Checkbutton(
            extinction_options,
            text="This location is extinct",
            variable=self.extinct_value,
            command=self.toggle_extinction_fields,
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
        extinction_checkbox.pack(side="left")
        self.extinction_year_label = tk.Label(
            extinction_options,
            text="Year extinct",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.extinction_year_control = RoundedEntry(
            extinction_options,
            textvariable=self.extinction_year_value,
            background=SURFACE_MUTED,
            width=170,
            height=36,
            font=app_font(10),
        )
        self.toggle_extinction_fields()

        narrative = tk.Frame(parent, bg=SURFACE)
        narrative.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        narrative.grid_columnconfigure(0, weight=1)
        narrative.grid_columnconfigure(1, weight=1)
        demographics_frame = tk.Frame(narrative, bg=SURFACE)
        demographics_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        demographics_label = tk.Label(
            demographics_frame,
            text="Broad demographics",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        demographics_label.pack(fill="x", pady=(0, 5))
        self.demographics_control = RoundedText(
            demographics_frame,
            background=SURFACE,
            height=4,
        )
        self.demographics_control.pack(fill="both", expand=True)
        notes_frame = tk.Frame(narrative, bg=SURFACE)
        notes_frame.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        notes_label = tk.Label(
            notes_frame,
            text="Location notes",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        notes_label.pack(fill="x", pady=(0, 5))
        self.notes_control = RoundedText(
            notes_frame,
            background=SURFACE,
            height=4,
        )
        self.notes_control.pack(fill="both", expand=True)
        self.save_location_button = SoftButton(
            parent,
            text="Save location",
            command=self.save_location,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=38,
        )
        self.save_location_button.grid(
            row=2,
            column=0,
            sticky="e",
            pady=(10, 0),
        )

    def toggle_extinction_fields(self):
        if self.extinct_value.get():
            self.extinction_year_label.pack(
                side="left",
                padx=(22, 8),
            )
            self.extinction_year_control.pack(side="left")
        else:
            self.extinction_year_label.pack_forget()
            self.extinction_year_control.pack_forget()

    def set_parent_location(self, location_id=""):
        requested_id = str(location_id or "").strip()
        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.locations
        }

        if requested_id not in available_ids:
            requested_id = ""

        if (
            self.region_lock_id
            and not location_id_is_in_scope(
                requested_id,
                self.locations,
                self.region_lock_id,
            )
            and not (
                self.current_location_id == self.region_lock_id
                and not self.creating_location
            )
        ):
            requested_id = self.region_lock_id

        self.selected_parent_location_id = requested_id
        self.refresh_parent_display()

    def refresh_parent_display(self):
        parent = self.controller.get_location(
            self.selected_parent_location_id
        )
        parent_name = (
            str(parent.get("name", "") or "Unnamed region").strip()
            if parent is not None
            else WORLD_LOCATION_LABEL
        )
        self.parent_path_value.set(parent_name)
        change_allowed = not (
            self.region_lock_id
            and self.current_location_id == self.region_lock_id
            and not self.creating_location
        )
        self.change_parent_button.set_enabled(change_allowed)

    def choose_parent_location(self):
        if (
            self.region_lock_id
            and self.current_location_id == self.region_lock_id
            and not self.creating_location
        ):
            messagebox.showinfo(
                "Region is locked",
                "Unlock this region before moving the region itself.",
                parent=self,
            )
            return

        unavailable_ids = descendant_ids(
            self.current_location_id,
            self.locations,
        )
        unavailable_ids.add(str(self.current_location_id or ""))
        scoped_ids = location_ids_in_scope(
            self.locations,
            self.region_lock_id,
        )
        available_locations = [
            location
            for location in self.locations
            if (
                str(location.get("record_id", "") or "") not in unavailable_ids
                and (
                    not self.region_lock_id
                    or str(location.get("record_id", "") or "") in scoped_ids
                )
            )
        ]
        LocationParentDialog(
            self,
            available_locations,
            self.selected_parent_location_id,
            self.parent_location_chosen,
            self.region_lock_id,
        )

    def parent_location_chosen(self, location_id):
        self.set_parent_location(location_id)
        parent_name = self.parent_path_value.get()
        self.status_command(f"Location will be placed within {parent_name}")

    def build_timeline(self, parent):
        timeline_panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        timeline_panel.grid(row=3, column=0, sticky="nsew", pady=(14, 0))
        timeline_panel.grid_rowconfigure(2, weight=1)
        timeline_panel.grid_columnconfigure(0, weight=1)
        timeline_heading = tk.Label(
            timeline_panel,
            text="Location timeline",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        timeline_heading.grid(row=0, column=0, sticky="ew")
        legend = tk.Label(
            timeline_panel,
            text=(
                "White/gray: this location  ·  Colored: inherited from an "
                "ancestor level  ·  Mage births and marriages are included automatically"
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        legend.grid(row=1, column=0, sticky="ew", pady=(3, 8))
        list_frame = tk.Frame(timeline_panel, bg=SURFACE_MUTED)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.timeline_list = tk.Listbox(
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
        self.timeline_list.grid(row=0, column=0, sticky="nsew")
        self.timeline_list.bind("<Double-Button-1>", self.open_timeline_selection)
        timeline_scrollbar = tk.Scrollbar(list_frame, command=self.timeline_list.yview)
        timeline_scrollbar.grid(row=0, column=1, sticky="ns")
        self.timeline_list.configure(yscrollcommand=timeline_scrollbar.set)
        event_buttons = tk.Frame(timeline_panel, bg=SURFACE_MUTED)
        event_buttons.grid(row=3, column=0, sticky="e", pady=(9, 0))
        add_button = SoftButton(
            event_buttons,
            text="Add event",
            command=self.add_event,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        add_button.pack(side="left", padx=(0, 6))
        edit_button = SoftButton(
            event_buttons,
            text="Edit",
            command=self.edit_event,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=36,
        )
        edit_button.pack(side="left", padx=(0, 6))
        remove_button = SoftButton(
            event_buttons,
            text="Remove",
            command=self.remove_event,
            background=SURFACE_MUTED,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=36,
        )
        remove_button.pack(side="left")

    def refresh(self, selected_location_id=None):
        selected_id = selected_location_id or self.current_location_id
        self.locations = self.controller.list_locations()
        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.locations
        }

        if self.region_lock_id not in available_ids:
            self.region_lock_id = ""

        self.location_tree.set_locations(self.locations, selected_id or "")
        self.location_tree.set_scope(self.region_lock_id)
        scoped_ids = location_ids_in_scope(
            self.locations,
            self.region_lock_id,
        )

        if (
            selected_id
            and selected_id in scoped_ids
            and self.controller.get_location(selected_id)
        ):
            self.location_tree.select_location(selected_id)
            self.load_location(selected_id)
        elif (
            self.region_lock_id
            and self.region_lock_id in scoped_ids
            and self.controller.get_location(self.region_lock_id)
        ):
            self.location_tree.select_location(self.region_lock_id)
            self.load_location(self.region_lock_id)
        elif self.locations:
            scoped_locations = [
                location
                for location in self.locations
                if str(location.get("record_id", "") or "") in scoped_ids
            ]
            first_location_id = (
                str(scoped_locations[0].get("record_id", "") or "")
                if scoped_locations
                else ""
            )
            self.location_tree.select_location(first_location_id)

            if first_location_id:
                self.load_location(first_location_id)
            else:
                self.clear_form()
        else:
            self.location_tree.select_location("")
            self.clear_form()

        self.periods_page.set_region_lock(self.region_lock_id)

        if self.active_section_name == "periods":
            self.periods_page.refresh()

    def refresh_person_data(self):
        self.refresh(self.current_location_id)

    def location_selected(self, location_id):
        requested_id = str(location_id or "").strip()

        if not requested_id and self.region_lock_id:
            requested_id = self.region_lock_id
            self.location_tree.select_location(requested_id)

        if requested_id:
            self.load_location(requested_id)
        else:
            self.clear_form()
            self.status_command(f"Selected {WORLD_LOCATION_LABEL}")

    def load_location(self, record_id):
        location = self.controller.get_location(record_id)

        if location is None:
            return

        self.current_location_id = record_id
        self.creating_location = False
        self.editor_heading_value.set("Location details")
        self.name_value.set(str(location.get("name", "") or ""))
        self.set_parent_location(location.get("parent_location_id", ""))
        self.extinct_value.set(bool(location.get("extinct")))
        self.extinction_year_value.set(
            str(location.get("extinction_year", "") or "")
        )
        self.toggle_extinction_fields()
        self.demographics_control.text.delete("1.0", "end")
        self.demographics_control.text.insert(
            "1.0",
            str(location.get("demographics", "") or ""),
        )
        self.notes_control.text.delete("1.0", "end")
        self.notes_control.text.insert(
            "1.0",
            str(location.get("notes", "") or ""),
        )
        self.save_location_button.set_enabled(True)
        self.refresh_timeline()
        self.status_command(f"Loaded location {location.get('name', 'Unnamed')}")

    def region_lock_changed(self, location_id):
        requested_id = str(location_id or "").strip()
        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.locations
        }

        if requested_id not in available_ids:
            requested_id = ""

        self.region_lock_id = requested_id
        self.location_tree.set_scope(requested_id)
        self.periods_page.set_region_lock(requested_id)

        if (
            self.current_location_id
            and not location_id_is_in_scope(
                self.current_location_id,
                self.locations,
                self.region_lock_id,
            )
        ):
            self.current_location_id = None

        if (
            self.selected_parent_location_id
            and not location_id_is_in_scope(
                self.selected_parent_location_id,
                self.locations,
                self.region_lock_id,
            )
            and self.current_location_id != self.region_lock_id
        ):
            self.set_parent_location(self.region_lock_id)

        if self.creating_location:
            self.set_parent_location(
                self.selected_parent_location_id or self.region_lock_id
            )
            self.location_tree.select_location(
                self.selected_parent_location_id
            )
        elif self.current_location_id:
            self.location_tree.select_location(self.current_location_id)
            self.load_location(self.current_location_id)
        elif self.region_lock_id:
            self.location_tree.select_location(self.region_lock_id)
            self.load_location(self.region_lock_id)
        else:
            self.location_tree.select_location("")
            self.clear_form()

        if self.region_lock_id:
            location = self.controller.get_location(self.region_lock_id)
            location_name = str(
                (location or {}).get("name", "") or "selected region"
            )
            self.status_command(f"Locked location work to {location_name}")
        else:
            self.status_command("Showing all location regions")

    def open_location_from_periods(self, location_id):
        requested_id = str(location_id or "").strip()

        if not location_id_is_in_scope(
            requested_id,
            self.locations,
            self.region_lock_id,
        ):
            self.status_command(
                "Unlock the current region to open that source location"
            )
            return False

        self.show_section("locations")
        self.location_tree.select_location(requested_id)
        self.load_location(requested_id)
        return True

    def refresh_timeline(self):
        self.timeline_list.delete(0, "end")

        if not self.current_location_id:
            self.visible_events = []
            return

        self.visible_events = self.controller.timeline_for(self.current_location_id)

        for index, event in enumerate(self.visible_events):
            date_text = format_line_item_date(
                event.get("date")
            )
            source_text = ""

            if event.get("propagation_distance", 0):
                source_text = (
                    f"  ·  from {event.get('origin_location_name', 'ancestor')} "
                    f"(level {event.get('source_level', 0)})"
                )

            kind_text = "  ·  mage" if event.get("event_kind") == "mage" else ""
            self.timeline_list.insert(
                "end",
                f"{date_text}  ·  {event.get('title', 'Event')}{source_text}{kind_text}",
            )

            if event.get("propagation_distance", 0):
                level = int(event.get("source_level", 0) or 0)
                color = PROPAGATED_EVENT_COLORS[
                    min(level, len(PROPAGATED_EVENT_COLORS) - 1)
                ]
            else:
                color = LOCAL_EVENT_COLORS[index % 2]

            self.timeline_list.itemconfigure(index, background=color)

    def clear_form(self, parent_location_id="", creating=False):
        self.current_location_id = None
        self.creating_location = bool(creating)
        self.editor_heading_value.set(
            "New location"
            if self.creating_location
            else "Select a location"
        )
        self.name_value.set("")
        self.set_parent_location(parent_location_id)
        self.extinct_value.set(False)
        self.extinction_year_value.set("")
        self.toggle_extinction_fields()
        self.demographics_control.text.delete("1.0", "end")
        self.notes_control.text.delete("1.0", "end")
        self.timeline_list.delete(0, "end")
        self.visible_events = []
        self.save_location_button.set_enabled(self.creating_location)

    def create_location(self):
        self.show_section("locations")
        parent_id = (
            self.current_location_id
            if location_id_is_in_scope(
                self.current_location_id,
                self.locations,
                self.region_lock_id,
            )
            else self.region_lock_id
        )
        self.clear_form(parent_id, creating=True)
        self.location_tree.select_location(parent_id)
        self.name_field.control.focus_set()
        parent_name = self.parent_path_value.get()
        self.status_command(
            f"Creating a new location within {parent_name}"
        )

    def save_location(self):
        values = {
            "name": self.name_value.get(),
            "parent_location_id": self.selected_parent_location_id,
            "demographics": self.demographics_control.text.get("1.0", "end-1c"),
            "notes": self.notes_control.text.get("1.0", "end-1c"),
            "extinct": self.extinct_value.get(),
            "extinction_year": self.extinction_year_value.get(),
        }

        try:
            if self.current_location_id:
                saved_location = self.controller.update_location(
                    self.current_location_id,
                    values,
                )
                action = "Saved"
            else:
                saved_location = self.controller.create_location(values)
                action = "Created"
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot save location", str(error), parent=self)
            return False

        self.creating_location = False
        self.refresh(saved_location["record_id"])
        self.status_command(
            f"{action} location {saved_location['name']}"
        )
        return True

    def delete_location(self):
        location = self.controller.get_location(self.current_location_id)

        if location is None:
            return

        if not messagebox.askyesno(
            "Delete location",
            f"Permanently delete {location.get('name', 'this location')}?",
            parent=self,
        ):
            return

        try:
            self.controller.delete_location(self.current_location_id)
        except (KeyError, ValueError) as error:
            messagebox.showerror("Cannot delete location", str(error), parent=self)
            return

        self.current_location_id = None
        self.refresh()
        self.status_command(f"Deleted location {location.get('name', 'Unnamed')}")

    def add_event(self):
        if not self.current_location_id:
            messagebox.showinfo(
                "Select a location",
                "Select or create a location before adding an event.",
                parent=self,
            )
            return

        LocationEventDialog(self, {}, self.save_new_event)

    def save_new_event(self, values):
        try:
            self.controller.add_event(self.current_location_id, values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot add event", str(error), parent=self)
            return False

        self.refresh_timeline()
        self.status_command("Added location event")
        return True

    def selected_timeline_event(self):
        selected = self.timeline_list.curselection()

        if not selected:
            return None

        return self.visible_events[selected[0]]

    def edit_event(self):
        event = self.selected_timeline_event()

        if event is None:
            return

        if event.get("event_kind") != "location" or event.get(
            "propagation_distance",
            0,
        ):
            messagebox.showinfo(
                "Inherited event",
                "Open the source location or mage to edit this event.",
                parent=self,
            )
            return

        LocationEventDialog(self, event, self.save_edited_event)

    def save_edited_event(self, values):
        event_id = str(values.get("event_id", "") or "")

        try:
            self.controller.update_event(
                self.current_location_id,
                event_id,
                values,
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror("Cannot edit event", str(error), parent=self)
            return False

        self.refresh_timeline()
        self.status_command("Updated location event")
        return True

    def remove_event(self):
        event = self.selected_timeline_event()

        if event is None:
            return

        if event.get("event_kind") != "location" or event.get(
            "propagation_distance",
            0,
        ):
            messagebox.showinfo(
                "Inherited event",
                "Open the source location or mage to remove this event.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Remove event",
            f"Remove {event.get('title', 'this event')}?",
            parent=self,
        ):
            return

        try:
            self.controller.delete_event(
                self.current_location_id,
                event.get("event_id", ""),
            )
        except (KeyError, ValueError) as error:
            messagebox.showerror("Cannot remove event", str(error), parent=self)
            return

        self.refresh_timeline()
        self.status_command("Removed location event")

    def open_timeline_selection(self, event=None):
        selected_event = self.selected_timeline_event()

        if selected_event is None:
            return

        person_id = str(selected_event.get("related_person_id", "") or "")

        if person_id:
            self.navigate_person_command(person_id)
        else:
            self.edit_event()


class LocationParentDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        selected_location_id,
        save_command,
        region_lock_id="",
    ):
        super().__init__(parent)
        self.locations = list(locations)
        self.selected_location_id = str(selected_location_id or "").strip()
        self.save_command = save_command
        self.region_lock_id = str(region_lock_id or "").strip()
        self.title("Choose containing region")
        self.geometry("560x640")
        self.minsize(460, 500)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.location_tree.set_locations(
            self.locations,
            self.selected_location_id,
        )
        self.location_tree.set_scope(self.region_lock_id)
        self.selected_location_id = self.location_tree.selected_location_id
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
            text="Place this location within",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Choose a region from the hierarchy. Search keeps matching "
                "branches together, and The World makes the location top level."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=470,
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
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=3, column=0, sticky="e", pady=(14, 0))
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
            text="Use this region",
            command=self.choose_location,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=134,
            height=36,
        )
        choose_button.pack(side="left")

    def location_selected(self, location_id):
        self.selected_location_id = str(location_id or "").strip()

    def choose_location(self):
        self.save_command(self.selected_location_id)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class LocationEventDialog(tk.Toplevel):
    def __init__(self, parent, event, save_command):
        super().__init__(parent)
        self.event = dict(event or {})
        self.save_command = save_command
        self.title_value = tk.StringVar(value=str(self.event.get("title", "") or ""))
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        year, month, day = split_partial_date(self.event.get("date", ""))
        self.year_value.set(year)
        self.month_value.set(month)
        self.day_value.set(day)
        self.title("Edit location event" if event else "Add location event")
        self.geometry("590x520")
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.bind("<Escape>", self.close_dialog)

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
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="Location event",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        title_field = LabeledEntry(
            card,
            "Event title",
            self.title_value,
            background=SURFACE,
        )
        title_field.grid(row=1, column=0, sticky="ew", pady=(14, 0))
        date_frame = tk.Frame(card, bg=SURFACE)
        date_frame.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        date_frame.grid_columnconfigure((0, 1, 2), weight=1)
        year_field = LabeledEntry(
            date_frame,
            "Year",
            self.year_value,
            background=SURFACE,
        )
        year_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        month_field = LabeledEntry(
            date_frame,
            "Month",
            self.month_value,
            background=SURFACE,
        )
        month_field.grid(row=0, column=1, sticky="ew", padx=6)
        day_field = LabeledEntry(
            date_frame,
            "Day",
            self.day_value,
            background=SURFACE,
        )
        day_field.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        notes_label = tk.Label(
            card,
            text="Event notes",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        notes_label.grid(row=3, column=0, sticky="ew", pady=(14, 5))
        self.notes_control = RoundedText(card, background=SURFACE, height=7)
        self.notes_control.grid(row=4, column=0, sticky="nsew")
        self.notes_control.text.insert(
            "1.0",
            str(self.event.get("note", "") or ""),
        )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=5, column=0, sticky="e", pady=(14, 0))
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        save_button = SoftButton(
            footer,
            text="Save event",
            command=self.save_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=110,
            height=36,
        )
        save_button.pack(side="left")

    def save_event(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()
        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            date_value += f"-{day}"

        values = {
            "event_id": self.event.get("event_id", ""),
            "title": self.title_value.get(),
            "date": date_value,
            "note": self.notes_control.text.get("1.0", "end-1c"),
        }

        if self.save_command(values):
            self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class LocationSectionCommand:
    def __init__(self, page, section_name):
        self.page = page
        self.section_name = section_name

    def __call__(self):
        self.page.show_section(self.section_name)
