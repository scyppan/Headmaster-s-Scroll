import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, simpledialog
from uuid import uuid4

from mage_maker.core.dates import (
    format_historical_display_date,
    format_line_item_date,
)
from mage_maker.sections.events.editor import (
    NEW_EVENT_DRAFT_ID,
    EventEditor,
)
from mage_maker.sections.events.types import event_type_label
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
    WORLD_LOCATION_LABEL,
    location_id_is_in_scope,
    location_ids_in_scope,
)
from mage_maker.sections.locations.models import descendant_ids
from mage_maker.sections.locations.models import (
    location_event_is_foundation,
)
from mage_maker.ui.theme import (
    ADD_GREEN,
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    FAMILY_GREEN,
    FAMILY_GREEN_DARK,
    LIST_SELECTED,
    LOCKED_BORDER,
    LOCKED_RED,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
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
    RoundedText,
    SoftButton,
)


LOCAL_EVENT_COLORS = ("#FFFFFF", "#F1F1F1")
REGIONAL_EVENT_BACKGROUND = "#E3E3E3"


def location_scope_after_parent_change(
    scope_location_id,
    previous_parent_location_id,
    next_parent_location_id,
):
    previous_parent_id = str(
        previous_parent_location_id or ""
    ).strip()
    next_parent_id = str(next_parent_location_id or "").strip()

    if previous_parent_id != next_parent_id:
        return ""

    return str(scope_location_id or "").strip()


class LocationPage(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        status_command,
        navigate_person_command,
        scope_change_command=None,
        event_controller=None,
        navigate_event_command=None,
        events_changed_command=None,
        navigate_organization_command=None,
    ):
        super().__init__(parent, bg=APP_BACKGROUND)
        self.controller = controller
        self.status_command = status_command
        self.navigate_person_command = navigate_person_command
        self.scope_change_command = scope_change_command
        self.event_controller = event_controller
        self.navigate_event_command = navigate_event_command
        self.events_changed_command = events_changed_command
        self.navigate_organization_command = navigate_organization_command
        self.locations = []
        self.assigned_organizations = []
        self.visible_events = []
        self.draft_event = None
        self.selected_timeline_event_id = ""
        self.event_editor_visible = False
        self.location_timeline_built = False
        self.has_refreshed = False
        self.remove_armed_event_id = ""
        self.current_location_id = None
        self.creating_location = False
        self.region_lock_id = ""
        self.selected_parent_location_id = ""
        self.loaded_parent_location_id = ""
        self.loaded_location_values = None
        self.location_before_create_id = ""
        self.active_view_name = "details"
        self.content = None
        self.editor_heading_value = tk.StringVar(value="Location details")
        self.parent_path_value = tk.StringVar(value=WORLD_LOCATION_LABEL)
        self.notable_facts_value = tk.StringVar(
            value="No notable facts yet."
        )
        self.name_value = tk.StringVar()
        self.has_floors_value = tk.BooleanVar(value=False)
        self.floor_records = []
        self.default_map_id = ""
        self.floor_summary_value = tk.StringVar(value="No named floors")
        self.extinct_value = tk.BooleanVar(value=False)
        self.extinction_date_value = tk.StringVar()
        self.timeline_type_value = tk.StringVar(
            value="No event selected"
        )
        self.timeline_date_value = tk.StringVar(value="Date: nd.")
        self.timeline_people_value = tk.StringVar(value="None")
        self.timeline_periods_value = tk.StringVar(value="None")
        self.timeline_locations_value = tk.StringVar(value="None")
        self.timeline_source_value = tk.StringVar(
            value="Select an event to view its details."
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_content()
        self.refresh()

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=PRIMARY_DARK, height=64)
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        title = tk.Label(
            toolbar,
            text="Locations",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=20,
        )
        title.grid(row=0, column=0, sticky="nsew")
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

    def build_content(self):
        self.content = tk.Frame(self, bg=APP_BACKGROUND)
        self.content.grid(row=1, column=0, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.build_workspace(self.content)

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
        foundation_notice = tk.Label(
            list_card,
            text=(
                "Red: the first event must be Founding or "
                "Wizarding community established."
            ),
            bg=SURFACE,
            fg=LOCKED_RED,
            font=app_font(8, "bold"),
            anchor="w",
            justify="left",
            wraplength=285,
        )
        foundation_notice.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )

        editor_card = tk.Frame(
            workspace,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        editor_card.grid_rowconfigure(1, weight=1)
        editor_card.grid_columnconfigure(0, weight=1)
        self.build_location_view_navigation(editor_card)

        self.location_details_page = tk.Frame(
            editor_card,
            bg=SURFACE,
        )
        self.location_details_page.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.location_details_page.grid_columnconfigure(0, weight=1)
        self.location_details_page.grid_rowconfigure(1, weight=1)
        self.build_location_fields(self.location_details_page)

        self.location_events_page = tk.Frame(
            editor_card,
            bg=SURFACE,
        )
        self.location_events_page.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.location_events_page.grid_rowconfigure(0, weight=1)
        self.location_events_page.grid_columnconfigure(0, weight=1)

        self.location_organizations_page = tk.Frame(
            editor_card,
            bg=SURFACE,
        )
        self.location_organizations_page.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.location_organizations_page.grid_rowconfigure(0, weight=1)
        self.location_organizations_page.grid_columnconfigure(0, weight=1)
        self.build_assigned_organizations(
            self.location_organizations_page
        )
        self.show_location_view("details")

        workspace.add(list_card, minsize=290, width=330)
        workspace.add(editor_card, minsize=680)

    def build_location_view_navigation(self, parent):
        navigation = tk.Frame(parent, bg=SURFACE)
        navigation.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        self.location_details_button = SoftButton(
            navigation,
            text="Details",
            command=self.show_location_details,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=30,
            font=app_font(9, "bold"),
        )
        self.location_details_button.pack(side="left", padx=(0, 6))
        self.location_events_button = SoftButton(
            navigation,
            text="Timeline & Events",
            command=self.show_location_events,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=134,
            height=30,
            font=app_font(9, "bold"),
        )
        self.location_events_button.pack(side="left", padx=(0, 6))
        self.location_organizations_button = SoftButton(
            navigation,
            text="Organizations",
            command=self.show_location_organizations,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=120,
            height=30,
            font=app_font(9, "bold"),
        )
        self.location_organizations_button.pack(side="left")

    def show_location_details(self):
        return self.show_location_view("details")

    def show_location_events(self):
        return self.show_location_view("events")

    def show_location_organizations(self):
        return self.show_location_view("organizations")

    def show_location_view(self, view_name):
        requested_view = str(view_name or "").strip()
        normalized_view = (
            requested_view
            if requested_view in ("details", "events", "organizations")
            else "details"
        )
        current_view = getattr(
            self,
            "active_view_name",
            normalized_view,
        )

        if (
            normalized_view != current_view
            and not self.confirm_unsaved_location_changes()
        ):
            return False

        self.active_view_name = normalized_view
        self.location_details_page.grid_remove()
        self.location_events_page.grid_remove()
        self.location_organizations_page.grid_remove()
        self.location_details_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.location_events_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.location_organizations_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )

        if normalized_view == "events":
            if not self.location_timeline_built:
                self.build_timeline(self.location_events_page, row=0)
                self.location_timeline_built = True

            self.location_events_page.grid()
            self.location_events_page.tkraise()
            self.location_events_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.refresh_timeline()
            return True

        if normalized_view == "organizations":
            self.location_organizations_page.grid()
            self.location_organizations_page.tkraise()
            self.location_organizations_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.refresh_assigned_organizations()
            return True

        self.location_details_page.grid()
        self.location_details_page.tkraise()
        self.location_details_button.set_colors(
            PRIMARY,
            PRIMARY_HOVER,
            TEXT_DARK,
        )
        return True

    def location_form_values(self):
        name_value = getattr(self, "name_value", None)
        notes_control = getattr(self, "notes_control", None)
        notes_widget = getattr(notes_control, "text", None)

        if (
            name_value is None
            or not hasattr(name_value, "get")
            or notes_widget is None
            or not hasattr(notes_widget, "get")
        ):
            return None

        return {
            "name": str(name_value.get() or ""),
            "parent_location_id": str(
                getattr(self, "selected_parent_location_id", "") or ""
            ).strip(),
            "notes": str(notes_widget.get("1.0", "end-1c") or ""),
            "has_floors": bool(self.has_floors_value.get()),
            "floors": deepcopy(self.floor_records),
            "default_map_id": self.default_map_id,
        }

    def remember_loaded_location_values(self):
        self.loaded_location_values = self.location_form_values()
        return self.loaded_location_values

    def has_unsaved_location_changes(self):
        loaded_values = getattr(self, "loaded_location_values", None)
        current_values = self.location_form_values()

        if loaded_values is None or current_values is None:
            return False

        return current_values != loaded_values

    def confirm_unsaved_event_changes(self):
        if not getattr(self, "location_timeline_built", False):
            return True

        event_editor = getattr(self, "event_editor", None)
        association_guard_command = getattr(
            event_editor,
            "association_selection_guard_active",
            None,
        )

        if (
            callable(association_guard_command)
            and association_guard_command()
        ):
            return False

        unsaved_changes_command = getattr(
            event_editor,
            "has_unsaved_changes",
            None,
        )

        if (
            not callable(unsaved_changes_command)
            or not unsaved_changes_command()
        ):
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved event changes",
            "Save this event before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return event_editor.save()

        event_editor.cancel()
        return True

    def discard_location_changes(self):
        current_location_id = str(
            getattr(self, "current_location_id", "") or ""
        ).strip()
        previous_location_id = str(
            getattr(self, "location_before_create_id", "") or ""
        ).strip()
        parent_location_id = str(
            getattr(self, "selected_parent_location_id", "") or ""
        ).strip()

        if (
            current_location_id
            and self.controller.get_location(current_location_id) is not None
        ):
            self.load_location(current_location_id)
            self.location_tree.select_location(current_location_id)
            return True

        if (
            previous_location_id
            and self.controller.get_location(previous_location_id) is not None
        ):
            self.load_location(previous_location_id)
            self.location_tree.select_location(previous_location_id)
            return True

        if (
            parent_location_id
            and self.controller.get_location(parent_location_id) is not None
        ):
            self.load_location(parent_location_id)
            self.location_tree.select_location(parent_location_id)
            return True

        self.clear_form(parent_location_id, creating=True)
        self.location_tree.select_location(parent_location_id)
        return True

    def confirm_unsaved_location_changes(self):
        if not self.confirm_unsaved_event_changes():
            return False

        if not self.has_unsaved_location_changes():
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved location changes",
            "Save changes to this location before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return self.save_location()

        self.discard_location_changes()
        return True

    def restore_location_tree_selection(self):
        selected_location_id = str(
            getattr(self, "current_location_id", "")
            or getattr(self, "location_before_create_id", "")
            or getattr(self, "selected_parent_location_id", "")
            or ""
        ).strip()
        self.location_tree.select_location(selected_location_id)
        return selected_location_id

    def save_shortcut(self):
        return self.save_location()

    def create_shortcut(self):
        self.create_location()
        return True

    def build_location_fields(self, parent):
        parent.grid_rowconfigure(1, weight=1)
        parent.grid_columnconfigure(0, weight=1)
        identity = tk.Frame(parent, bg=SURFACE_MUTED, padx=14, pady=10)
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
            sticky="ew",
            pady=(0, 8),
        )
        self.save_location_button = SoftButton(
            identity,
            text="Save location",
            command=self.save_location,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=34,
        )
        self.save_location_button.grid(
            row=0,
            column=1,
            sticky="e",
            pady=(0, 8),
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
        self.extinction_checkbox = tk.Checkbutton(
            extinction_options,
            text="This location is extinct",
            variable=self.extinct_value,
            command=self.extinction_state_changed,
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
        self.extinction_checkbox.pack(side="left")
        self.has_floors_checkbox = tk.Checkbutton(
            extinction_options,
            text="Has floors",
            variable=self.has_floors_value,
            command=self.floors_state_changed,
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
        self.has_floors_checkbox.pack(side="left", padx=(18, 0))
        self.floors_button = SoftButton(
            extinction_options,
            text="Manage floors",
            command=self.open_floor_editor,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=30,
            font=app_font(9, "bold"),
        )
        self.floors_button.pack(side="left", padx=(10, 0))
        tk.Label(
            extinction_options,
            textvariable=self.floor_summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
        ).pack(side="left", padx=(8, 0))
        self.extinction_date_label = tk.Label(
            extinction_options,
            textvariable=self.extinction_date_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.refresh_extinction_display()
        self.build_location_narrative(parent)

    def build_location_narrative(self, parent):
        narrative = tk.Frame(parent, bg=SURFACE)
        narrative.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        narrative.grid_rowconfigure(0, weight=1)
        narrative.grid_columnconfigure(0, weight=1)
        notes_frame = tk.Frame(narrative, bg=SURFACE)
        notes_frame.grid(row=0, column=0, sticky="nsew")
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
            height=8,
            minimum_height=180,
        )
        self.notes_control.pack(fill="both", expand=True)
        facts_frame = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            padx=14,
            pady=10,
        )
        facts_frame.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(10, 0),
        )
        facts_heading = tk.Label(
            facts_frame,
            text="Notable facts",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        facts_heading.pack(fill="x")
        facts = tk.Label(
            facts_frame,
            textvariable=self.notable_facts_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        facts.pack(fill="x", pady=(4, 0))

    def floors_state_changed(self):
        if not self.has_floors_value.get() and self.floor_records:
            messagebox.showinfo(
                "Named floors",
                "Remove the named floors in Mapper or the floor editor before turning off Has floors.",
                parent=self,
            )
            self.has_floors_value.set(True)
        self.refresh_floor_summary()

    def refresh_floor_summary(self):
        count = len(self.floor_records)
        self.floor_summary_value.set(
            "No named floors" if not count else f"{count} named floor{'s' if count != 1 else ''}"
        )
        if hasattr(self, "floors_button"):
            self.floors_button.set_enabled(bool(self.has_floors_value.get()))

    def open_floor_editor(self):
        if not self.has_floors_value.get():
            messagebox.showinfo("Named floors", "Turn on Has floors first.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Named floors")
        dialog.transient(self)
        dialog.grab_set()
        dialog.configure(bg=SURFACE)
        dialog.geometry("520x420")
        working = deepcopy(self.floor_records)
        tk.Label(dialog, text="Named floors", bg=SURFACE, fg=TEXT_DARK, font=app_font(14, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        tk.Label(dialog, text="Floor names are stable world records. Mapper attaches a primary map to each floor.", bg=SURFACE, fg=TEXT_MUTED, font=app_font(9), wraplength=480, justify="left").pack(anchor="w", padx=16, pady=(0, 10))
        listbox = tk.Listbox(dialog, bg=FIELD_BACKGROUND, fg=TEXT_DARK, selectbackground=PRIMARY, borderwidth=1, relief="solid", font=app_font(10))
        listbox.pack(fill="both", expand=True, padx=16)

        def render(selection=0):
            listbox.delete(0, "end")
            for floor in working:
                suffix = " • map attached" if floor.get("primary_map_id") else ""
                listbox.insert("end", f"{floor['name']}{suffix}")
            if working:
                selection = max(0, min(selection, len(working) - 1))
                listbox.selection_set(selection)
                listbox.activate(selection)

        def selected_index():
            selection = listbox.curselection()
            return selection[0] if selection else None

        def add_floor():
            name = simpledialog.askstring("Add floor", "Floor name", parent=dialog)
            if not name or not name.strip():
                return
            working.append({"record_id": str(uuid4()), "name": name.strip(), "sort_order": len(working), "primary_map_id": ""})
            render(len(working) - 1)

        def rename_floor():
            index = selected_index()
            if index is None:
                return
            name = simpledialog.askstring("Rename floor", "Floor name", initialvalue=working[index]["name"], parent=dialog)
            if name and name.strip():
                working[index]["name"] = name.strip()
                render(index)

        def delete_floor():
            index = selected_index()
            if index is None:
                return
            if working[index].get("primary_map_id"):
                messagebox.showerror("Cannot remove floor", "Remove this floor's maps in Mapper first.", parent=dialog)
                return
            working.pop(index)
            render(index)

        def move(direction):
            index = selected_index()
            if index is None:
                return
            target = index + direction
            if not 0 <= target < len(working):
                return
            working[index], working[target] = working[target], working[index]
            render(target)

        buttons = tk.Frame(dialog, bg=SURFACE)
        buttons.pack(fill="x", padx=16, pady=10)
        for text, command in (("Add", add_floor), ("Rename", rename_floor), ("Remove", delete_floor), ("Move up", lambda: move(-1)), ("Move down", lambda: move(1))):
            tk.Button(buttons, text=text, command=command, bg=BUTTON_SOFT, activebackground=BUTTON_SOFT_HOVER, fg=TEXT_DARK, relief="flat", padx=9, pady=6).pack(side="left", padx=(0, 5))

        def apply():
            for index, floor in enumerate(working):
                floor["sort_order"] = index
            self.floor_records = deepcopy(working)
            self.refresh_floor_summary()
            dialog.destroy()

        footer = tk.Frame(dialog, bg=SURFACE)
        footer.pack(fill="x", padx=16, pady=(0, 14))
        tk.Button(footer, text="Cancel", command=dialog.destroy, bg=BUTTON_SOFT, relief="flat", padx=12, pady=7).pack(side="right")
        tk.Button(footer, text="Use floors", command=apply, bg=PRIMARY, relief="flat", padx=12, pady=7).pack(side="right", padx=(0, 7))
        render()

    def refresh_extinction_display(self):
        state_provider = getattr(
            self.controller,
            "extinction_state_for_location",
            None,
        )
        state = (
            state_provider(
                self.current_location_id
            )
            if self.current_location_id and callable(state_provider)
            else {
                "exists": False,
                "date": "",
            }
        )
        extinct = bool(state.get("exists"))
        self.extinct_value.set(extinct)

        if extinct:
            self.extinction_date_value.set(
                "Extinction date: "
                + format_historical_display_date(state.get("date"))
            )
            self.extinction_date_label.pack(
                side="left",
                padx=(22, 0),
            )
        else:
            self.extinction_date_value.set("")
            self.extinction_date_label.pack_forget()

        return state

    def extinction_state_changed(self):
        state = self.controller.extinction_state_for_location(
            self.current_location_id
        ) if self.current_location_id else {"exists": False}

        if self.extinct_value.get():
            if state.get("exists"):
                self.refresh_extinction_display()
                return

            if not self.current_location_id:
                self.extinct_value.set(False)
                self.status_command(
                    "Save the location before entering its extinction event."
                )
                return

            self.start_extinction_event()
            return

        if state.get("exists"):
            self.extinct_value.set(True)
            messagebox.showinfo(
                "Extinction is a timeline event",
                "Edit or remove the Extinction event in Timeline & Events "
                "to change this location's extinction state.",
                parent=self,
            )
            if not self.show_location_events():
                return

            self.selected_timeline_event_id = str(
                state.get("event_id", "") or ""
            )
            self.refresh_timeline()
            return

        self.refresh_extinction_display()

    def start_extinction_event(self):
        if not self.show_location_events():
            self.extinct_value.set(False)
            return False

        location = self.controller.get_location(
            self.current_location_id
        )
        location_name = str(
            (location or {}).get("name", "") or "this location"
        ).strip()
        self.add_event(
            event_type="extinction",
            title=f"Extinction of {location_name}",
        )
        return True

    def build_assigned_organizations(self, parent):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=8,
        )
        panel.grid(row=0, column=0, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            panel,
            text="Organizations assigned here",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        open_button = SoftButton(
            panel,
            text="Open organization",
            command=self.open_selected_organization,
            background=SURFACE_MUTED,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=30,
            font=app_font(8, "bold"),
        )
        open_button.grid(row=0, column=1, sticky="e")
        list_frame = tk.Frame(
            panel,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(6, 0),
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.organization_list = tk.Listbox(
            list_frame,
            height=3,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.organization_list.grid(row=0, column=0, sticky="nsew")
        self.organization_list.bind(
            "<Double-Button-1>",
            self.open_selected_organization,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.organization_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.organization_list.configure(yscrollcommand=scrollbar.set)

    def refresh_assigned_organizations(self):
        self.assigned_organizations = (
            self.controller.organizations_for_location(
                self.current_location_id
            )
            if self.current_location_id
            else []
        )
        self.organization_list.delete(0, "end")

        for organization in self.assigned_organizations:
            name = str(
                organization.get("name", "") or "Unnamed organization"
            ).strip()
            organization_type = str(
                organization.get("organization_type", "") or ""
            ).strip()
            self.organization_list.insert(
                "end",
                (
                    f"{name} · {organization_type}"
                    if organization_type
                    else name
                ),
            )

    def refresh_location_distinctions(self):
        if not hasattr(self, "notable_facts_value"):
            return

        if (
            not self.current_location_id
            or not hasattr(self.controller, "location_distinctions")
        ):
            self.notable_facts_value.set("No notable facts yet.")
            return

        distinctions = self.controller.location_distinctions(
            self.current_location_id
        )
        self.notable_facts_value.set(
            "\n".join(distinctions)
            if distinctions
            else "No notable facts yet."
        )

    def open_selected_organization(self, event=None):
        if self.navigate_organization_command is None:
            return False

        selected = self.organization_list.curselection()

        if not selected:
            return False

        organization = self.assigned_organizations[int(selected[0])]
        return self.navigate_organization_command(
            organization.get("record_id", "")
        )

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

    def build_timeline(self, parent, row=3):
        timeline_panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=8,
        )
        timeline_panel.grid(
            row=row,
            column=0,
            sticky="nsew",
            pady=(10, 0),
        )
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
        event_buttons = tk.Frame(timeline_panel, bg=SURFACE_MUTED)
        event_buttons.grid(row=0, column=1, sticky="e")
        self.timeline_add_button = SoftButton(
            event_buttons,
            text="Add event",
            command=self.add_event,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=32,
        )
        self.timeline_add_button.pack(side="left", padx=(0, 6))
        self.timeline_edit_button = SoftButton(
            event_buttons,
            text="Edit",
            command=self.edit_event,
            background=SURFACE_MUTED,
            fill=PRIMARY_SOFT,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=82,
            height=32,
        )
        self.timeline_edit_button.pack(side="left", padx=(0, 6))
        self.timeline_remove_button = SoftButton(
            event_buttons,
            text="Remove",
            command=self.remove_event,
            background=SURFACE_MUTED,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=32,
        )
        self.timeline_remove_button.pack(side="left")
        legend = tk.Label(
            timeline_panel,
            text=(
                "Green: founding or wizarding community established  ·  "
                "White/light gray: this location  ·  "
                "Gray and indented: regional"
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=760,
        )
        legend.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(1, 3),
        )
        self.timeline_workspace = tk.Frame(
            timeline_panel,
            bg=SURFACE_MUTED,
        )
        self.timeline_workspace.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        self.timeline_workspace.grid_rowconfigure(0, weight=1)
        self.timeline_workspace.grid_columnconfigure(
            0,
            weight=4,
            uniform="location_events",
        )
        self.timeline_workspace.grid_columnconfigure(
            1,
            weight=5,
            uniform="location_events",
        )
        self.timeline_list_panel = tk.Frame(
            self.timeline_workspace,
            bg=SURFACE_MUTED,
        )
        self.timeline_list_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        self.timeline_list_panel.grid_rowconfigure(0, weight=1)
        self.timeline_list_panel.grid_columnconfigure(0, weight=1)
        list_frame = tk.Frame(
            self.timeline_list_panel,
            bg=SURFACE_MUTED,
        )
        list_frame.grid(row=0, column=0, sticky="nsew")
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
        self.timeline_list.bind(
            "<<ListboxSelect>>",
            self.timeline_event_selected,
        )
        self.timeline_list.bind("<Double-Button-1>", self.edit_event)
        timeline_scrollbar = tk.Scrollbar(list_frame, command=self.timeline_list.yview)
        timeline_scrollbar.grid(row=0, column=1, sticky="ns")
        self.timeline_list.configure(yscrollcommand=timeline_scrollbar.set)
        self.event_editor = EventEditor(
            self.timeline_workspace,
            self.event_controller,
            self.save_event_editor,
            self.cancel_event_editor,
            context="location",
            background=SURFACE_MUTED,
        )
        self.event_editor.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.hide_event_editor()
        self.update_timeline_details()

    def show_event_editor(self):
        if self.event_editor_visible:
            return

        self.timeline_workspace.grid_columnconfigure(
            0,
            weight=4,
            uniform="location_events",
        )
        self.timeline_workspace.grid_columnconfigure(
            1,
            weight=5,
            uniform="location_events",
        )
        self.timeline_list_panel.grid(
            row=0,
            column=0,
            columnspan=1,
            sticky="nsew",
            padx=(0, 7),
        )
        self.event_editor.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.event_editor_visible = True

    def hide_event_editor(self):
        self.event_editor.grid_remove()
        self.timeline_workspace.grid_columnconfigure(
            0,
            weight=1,
            uniform="",
        )
        self.timeline_workspace.grid_columnconfigure(
            1,
            weight=0,
            uniform="",
        )
        self.timeline_list_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=0,
        )
        self.event_editor_visible = False

    def build_timeline_association_detail(
        self,
        parent,
        row,
        title,
        variable,
    ):
        heading = tk.Label(
            parent,
            text=title,
            bg=FIELD_BACKGROUND,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        heading.grid(row=row, column=0, sticky="ew", pady=(9, 2))
        value = tk.Label(
            parent,
            textvariable=variable,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=390,
        )
        value.grid(row=row + 1, column=0, sticky="ew")

    def refresh(self, selected_location_id=None, force=False):
        selected_id = selected_location_id or self.current_location_id
        refreshed_locations = self.controller.list_locations()

        if (
            self.has_refreshed
            and not force
            and selected_location_id is None
            and refreshed_locations == self.locations
        ):
            return

        self.locations = refreshed_locations
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

        self.has_refreshed = True

    def refresh_person_data(self):
        self.controller.invalidate_caches(include_people_sync=True)
        self.refresh(self.current_location_id, force=True)

    def location_selected(self, location_id):
        requested_id = str(location_id or "").strip()

        if not requested_id and self.region_lock_id:
            requested_id = self.region_lock_id
            self.location_tree.select_location(requested_id)

        current_location_id = str(
            getattr(self, "current_location_id", "") or ""
        ).strip()

        if (
            requested_id == current_location_id
            and not getattr(self, "creating_location", False)
        ):
            self.controller.remember_location_interaction(requested_id)
            return True

        if not self.confirm_unsaved_location_changes():
            self.restore_location_tree_selection()
            return False

        self.controller.remember_location_interaction(requested_id)

        if requested_id:
            self.load_location(requested_id)
        else:
            self.clear_form()
            self.status_command(f"Selected {WORLD_LOCATION_LABEL}")

        return True

    def load_location(self, record_id):
        location = self.controller.get_location(record_id)

        if location is None:
            return

        if record_id != self.current_location_id:
            self.draft_event = None
            self.selected_timeline_event_id = ""

        self.current_location_id = record_id
        self.creating_location = False
        self.location_before_create_id = ""
        self.editor_heading_value.set("Location details")
        self.name_value.set(str(location.get("name", "") or ""))
        self.has_floors_value.set(bool(location.get("has_floors", location.get("floors") or location.get("is_building", False))))
        self.floor_records = deepcopy(location.get("floors", []) or [])
        self.default_map_id = str(location.get("default_map_id", "") or "")
        self.refresh_floor_summary()
        self.loaded_parent_location_id = str(
            location.get("parent_location_id", "") or ""
        ).strip()
        self.set_parent_location(location.get("parent_location_id", ""))
        self.refresh_extinction_display()
        self.notes_control.text.delete("1.0", "end")
        self.notes_control.text.insert(
            "1.0",
            str(location.get("notes", "") or ""),
        )
        self.remember_loaded_location_values()
        self.save_location_button.set_enabled(True)
        self.refresh_location_distinctions()

        if self.active_view_name == "organizations":
            self.refresh_assigned_organizations()

        if self.location_timeline_built:
            self.timeline_add_button.set_enabled(True)

            if self.active_view_name == "events":
                self.refresh_timeline()

        self.status_command(f"Loaded location {location.get('name', 'Unnamed')}")

    def set_region_lock(self, location_id="", notify=False):
        requested_id = str(location_id or "").strip()
        available_ids = {
            str(location.get("record_id", "") or "")
            for location in self.locations
        }

        if requested_id not in available_ids:
            requested_id = ""

        self.region_lock_id = requested_id
        self.location_tree.set_scope(requested_id, notify=False)

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

        if notify and self.scope_change_command is not None:
            self.scope_change_command(self.region_lock_id)

        return self.region_lock_id

    def region_lock_changed(self, location_id):
        requested_id = str(location_id or "").strip()

        if (
            requested_id != self.region_lock_id
            and not self.confirm_unsaved_location_changes()
        ):
            self.location_tree.set_scope(
                self.region_lock_id,
                notify=False,
            )
            self.restore_location_tree_selection()
            return False

        return self.set_region_lock(location_id, notify=True)

    def open_location(self, location_id):
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

        self.location_tree.select_location(requested_id)
        return self.location_selected(requested_id)

    def refresh_timeline(self):
        self.refresh_location_distinctions()

        if (
            self.draft_event is None
            and hasattr(self, "extinct_value")
        ):
            self.refresh_extinction_display()

        self.timeline_list.delete(0, "end")

        if not self.current_location_id:
            self.visible_events = []
            self.selected_timeline_event_id = ""
            self.update_timeline_details()
            return

        self.visible_events = self.controller.timeline_for(self.current_location_id)
        if (
            self.draft_event is not None
            and self.draft_event.get("_location_id")
            == self.current_location_id
        ):
            self.visible_events.append(self.draft_event)

        visible_event_ids = {
            str(event.get("event_id", "") or "")
            for event in self.visible_events
        }

        if self.selected_timeline_event_id not in visible_event_ids:
            self.selected_timeline_event_id = ""

        people_labels_by_id = {}

        if (
            getattr(self, "event_controller", None) is not None
            and any(
                event.get("event_kind") == "global"
                and (
                    event.get("person_ids")
                    or event.get("related_person_id")
                )
                for event in self.visible_events
            )
        ):
            people_labels_by_id = {
                str(option.get("value", "") or "").strip(): str(
                    option.get("label", "") or "Missing person"
                ).strip()
                for option in self.event_controller.people_options()
                if str(option.get("value", "") or "").strip()
            }

        for index, event in enumerate(self.visible_events):
            if event.get("_draft_event"):
                self.timeline_list.insert("end", "New event (unsaved)")
                self.timeline_list.itemconfigure(
                    index,
                    background=PRIMARY_SOFT,
                )

                if (
                    str(event.get("event_id", "") or "")
                    == self.selected_timeline_event_id
                ):
                    self.timeline_list.selection_set(index)
                    self.timeline_list.see(index)

                continue

            date_text = format_line_item_date(
                event.get("date")
            )
            time_text = str(event.get("time", "") or "").strip()

            if time_text:
                date_text = f"{date_text} {time_text}"

            source_text = ""

            if event.get("propagation_distance", 0):
                source_text = (
                    f"  ·  from {event.get('origin_location_name', 'ancestor')} "
                    f"(level {event.get('source_level', 0)})"
                )

            event_title = str(
                event.get("title", "") or "Event"
            ).strip()
            event_summary = (
                event_title
                if str(event.get("event_type", "") or "").strip().casefold()
                == "founding"
                else f"{event_type_label(event)}  ·  {event_title}"
            )
            people_text = ""

            if event.get("event_kind") == "global":
                person_ids = [
                    str(person_id or "").strip()
                    for person_id in event.get("person_ids", [])
                    if str(person_id or "").strip()
                ]

                if not person_ids and event.get("related_person_id"):
                    person_ids = [
                        str(event.get("related_person_id") or "").strip()
                    ]

                person_names = [
                    people_labels_by_id.get(
                        person_id,
                        "Missing person",
                    )
                    for person_id in dict.fromkeys(person_ids)
                ]

                if person_names:
                    people_text = "  ·  " + ", ".join(person_names)

            self.timeline_list.insert(
                "end",
                (
                    f"{'    ' if event.get('propagation_distance', 0) else ''}"
                    f"{date_text}  ·  {event_summary}"
                    f"{people_text}{source_text}"
                ),
            )

            if event.get("propagation_distance", 0):
                color = REGIONAL_EVENT_BACKGROUND
            else:
                color = LOCAL_EVENT_COLORS[index % 2]

            self.timeline_list.itemconfigure(index, background=color)

            if event.get("propagation_distance", 0):
                self.timeline_list.itemconfigure(
                    index,
                    foreground=TEXT_MUTED,
                    selectforeground=TEXT_MUTED,
                )

            if (
                location_event_is_foundation(event)
                and not event.get("propagation_distance", 0)
            ):
                self.timeline_list.itemconfigure(
                    index,
                    background=FAMILY_GREEN,
                    foreground=FAMILY_GREEN_DARK,
                    selectbackground=ADD_GREEN,
                    selectforeground=FAMILY_GREEN_DARK,
                )

            if (
                str(event.get("event_id", "") or "")
                == self.selected_timeline_event_id
            ):
                self.timeline_list.selection_set(index)
                self.timeline_list.see(index)

        self.update_timeline_details()

    def timeline_event_selected(self, event=None):
        selected = self.timeline_list.curselection()

        if not selected:
            return

        requested_event_id = str(
            self.visible_events[selected[0]].get("event_id", "") or ""
        )

        if (
            requested_event_id != self.selected_timeline_event_id
            and not self.confirm_unsaved_event_changes()
        ):
            self.restore_selected_timeline_event_row()
            return "break"

        self.selected_timeline_event_id = requested_event_id
        self.reset_event_remove_confirmation()
        self.update_timeline_details()

    def restore_selected_timeline_event_row(self):
        self.timeline_list.selection_clear(0, "end")

        for index, event in enumerate(self.visible_events):
            if str(event.get("event_id", "") or "") != str(
                self.selected_timeline_event_id or ""
            ):
                continue

            self.timeline_list.selection_set(index)
            self.timeline_list.see(index)
            return True

        return False

    def update_timeline_details(self):
        comparison_command = getattr(
            self.event_editor,
            "set_comparison_events",
            None,
        )

        if callable(comparison_command):
            comparison_command(self.visible_events)

        event = self.selected_timeline_event()

        if event is None:
            if self.event_editor.is_new_event():
                self.show_event_editor()
                self.event_editor.ensure_new_event_editable()
                self.timeline_edit_button.set_enabled(False)
                self.timeline_remove_button.set_enabled(False)
                return

            self.event_editor.clear(
                "Select an event to view it, or click Add event."
            )
            self.hide_event_editor()
            self.timeline_edit_button.set_enabled(False)
            self.timeline_remove_button.set_enabled(False)
            return

        if event.get("_draft_event"):
            self.show_event_editor()

            if not self.event_editor.is_new_event():
                self.event_editor.start_new(
                    context="location",
                    default_location_ids=(self.current_location_id,),
                    locked_location_ids=(self.current_location_id,),
                    hide_locations=True,
                )

            self.event_editor.ensure_new_event_editable()
            self.timeline_edit_button.set_enabled(False)
            self.timeline_remove_button.set_enabled(False)
            return

        self.show_event_editor()
        can_edit = bool(
            event.get("event_kind") in ("global", "location")
            and not event.get("propagation_distance", 0)
        )
        self.timeline_edit_button.set_enabled(can_edit)
        self.timeline_remove_button.set_enabled(can_edit)
        location_id = str(
            event.get("origin_location_id", "")
            or self.current_location_id
            or ""
        )

        if event.get("event_kind") == "global":
            stored_event = (
                self.event_controller.get_event(
                    event.get("record_id", "")
                )
                if self.event_controller is not None
                else None
            )

            if stored_event is None:
                self.event_editor.clear("This event no longer exists.")
                return

            inherited = bool(event.get("propagation_distance", 0))
            self.event_editor.load_event(
                stored_event,
                storage_kind="shared",
                context="location",
                location_ids=(location_id,),
                locked_location_ids=(location_id,),
                hide_locations=True,
                read_only=inherited,
                explanation=(
                    "This event is inherited from an enclosing location."
                    if inherited
                    else (
                        "The source location is fixed to this location. "
                        "Saving updates the event everywhere it appears."
                    )
                ),
            )
            return

        if event.get("event_kind") == "location":
            inherited = bool(event.get("propagation_distance", 0))
            self.event_editor.load_event(
                event,
                storage_kind="location",
                context="location",
                location_ids=(location_id,),
                locked_location_ids=(location_id,),
                hide_locations=True,
                read_only=inherited,
                explanation=(
                    "This event is inherited from an enclosing location."
                    if inherited
                    else "This event is stored on this location."
                ),
            )
            return

        person_ids = event.get("person_ids", [])

        if not person_ids and event.get("related_person_id"):
            person_ids = [event.get("related_person_id")]

        self.event_editor.load_event(
            event,
            storage_kind="timeline",
            context="person",
            person_ids=person_ids,
            location_ids=(location_id,),
            locked_location_ids=(location_id,),
            hide_locations=True,
            read_only=True,
            explanation=(
                "This individual event is shown here because it happened "
                "at this location."
            )
        )

    def timeline_event_type_text(self, event):
        return event_type_label(event)

    def timeline_event_association_labels(self, event):
        if (
            event.get("event_kind") == "global"
            and self.event_controller is not None
        ):
            return self.event_controller.association_labels(event)

        people_labels = {}
        location_labels = {}

        if self.event_controller is not None:
            people_labels = {
                option["value"]: option["label"]
                for option in self.event_controller.people_options()
            }
            location_labels = {
                option["value"]: option["label"]
                for option in self.event_controller.location_options()
            }

        person_id = str(event.get("related_person_id", "") or "")
        location_id = str(event.get("origin_location_id", "") or "")
        period_names = (
            self.event_controller.period_names_for_date(
                event.get("date", "")
            )
            if self.event_controller is not None
            else []
        )
        return {
            "people": (
                [people_labels.get(person_id, "Missing person")]
                if person_id
                else []
            ),
            "periods": period_names,
            "locations": (
                [
                    location_labels.get(
                        location_id,
                        event.get("origin_location_name", "Missing location"),
                    )
                ]
                if location_id
                else []
            ),
        }

    def timeline_event_source_text(self, event):
        if event.get("event_kind") == "global":
            return "Linked event · visible from every associated record"

        if event.get("event_kind") == "mage":
            return "Individual event · edit from the linked person"

        origin_name = str(
            event.get("origin_location_name", "") or "this location"
        )

        if event.get("propagation_distance", 0):
            return f"Inherited from {origin_name}"

        return f"Saved directly to {origin_name}"

    def clear_form(self, parent_location_id="", creating=False):
        self.current_location_id = None
        self.draft_event = None
        self.creating_location = True
        self.location_before_create_id = ""
        self.loaded_parent_location_id = ""
        self.editor_heading_value.set("New location")
        self.name_value.set("")
        self.set_parent_location(parent_location_id)
        self.extinct_value.set(False)
        self.has_floors_value.set(False)
        self.floor_records = []
        self.default_map_id = ""
        self.refresh_floor_summary()
        self.extinction_date_value.set("")
        self.extinction_date_label.pack_forget()
        self.notes_control.text.delete("1.0", "end")
        self.notable_facts_value.set("No notable facts yet.")

        if self.active_view_name == "organizations":
            self.refresh_assigned_organizations()

        if self.location_timeline_built:
            self.timeline_list.delete(0, "end")
            self.visible_events = []
            self.selected_timeline_event_id = ""
            self.reset_event_remove_confirmation()
            self.update_timeline_details()
            self.timeline_add_button.set_enabled(False)

        self.save_location_button.set_enabled(True)
        self.remember_loaded_location_values()

    def create_location(self):
        if not self.confirm_unsaved_location_changes():
            return False

        if not self.show_location_details():
            return False

        previous_location_id = str(
            self.current_location_id or ""
        ).strip()
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
        self.location_before_create_id = previous_location_id
        self.location_tree.select_location(parent_id)
        self.name_field.control.focus_set()
        parent_name = self.parent_path_value.get()
        self.status_command(
            f"Creating a new location within {parent_name}"
        )
        return True

    def save_location(self):
        creating_new_location = not bool(self.current_location_id)
        has_floors_value = getattr(self, "has_floors_value", None)
        has_floors = bool(has_floors_value.get()) if has_floors_value is not None else False
        floor_records = deepcopy(getattr(self, "floor_records", []) or [])
        default_map_id = str(getattr(self, "default_map_id", "") or "")
        extinction_state = (
            self.controller.extinction_state_for_location(
                self.current_location_id
            )
            if self.current_location_id
            else {"exists": False, "year": None}
        )
        values = {
            "name": self.name_value.get(),
            "parent_location_id": self.selected_parent_location_id,
            "notes": self.notes_control.text.get("1.0", "end-1c"),
            "has_floors": has_floors,
            "floors": floor_records,
            "default_map_id": default_map_id,
            "extinct": bool(extinction_state.get("exists")),
            "extinction_year": (
                extinction_state.get("year")
                if extinction_state.get("exists")
                else ""
            ),
        }

        if not self.current_location_id:
            values["demographics"] = ""

        parent_changed = bool(
            self.current_location_id
            and self.loaded_parent_location_id
            != str(self.selected_parent_location_id or "").strip()
        )

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
        next_scope_id = (
            self.region_lock_id
            if creating_new_location
            else location_scope_after_parent_change(
                self.region_lock_id,
                self.loaded_parent_location_id,
                saved_location.get("parent_location_id", ""),
            )
        )

        if next_scope_id != self.region_lock_id:
            self.region_lock_id = next_scope_id
            self.location_tree.set_scope(next_scope_id, notify=False)

            if self.scope_change_command is not None:
                self.scope_change_command(next_scope_id)

        self.refresh(saved_location["record_id"])

        if parent_changed:
            parent_name = self.parent_path_value.get()
            self.status_command(
                f"Moved {saved_location['name']} within {parent_name} "
                "and restored the full location hierarchy"
            )
        else:
            self.status_command(
                f"{action} location {saved_location['name']}"
            )

        return True

    def delete_location(self):
        if not self.confirm_unsaved_location_changes():
            return False

        location = self.controller.get_location(self.current_location_id)

        if location is None:
            return False

        if not messagebox.askyesno(
            "Delete location",
            f"Permanently delete {location.get('name', 'this location')}?",
            parent=self,
        ):
            return False

        try:
            self.controller.delete_location(self.current_location_id)
        except (KeyError, ValueError) as error:
            messagebox.showerror("Cannot delete location", str(error), parent=self)
            return False

        self.current_location_id = None
        self.refresh()
        self.status_command(f"Deleted location {location.get('name', 'Unnamed')}")
        return True

    def add_event(self, event_type="other", title="New event"):
        if not self.current_location_id:
            self.status_command(
                "Save the location before adding an event."
            )
            return

        if self.event_controller is None:
            self.status_command("The event collection is unavailable.")
            return

        if not self.confirm_unsaved_event_changes():
            return False

        self.draft_event = {
            "event_id": NEW_EVENT_DRAFT_ID,
            "event_type": str(event_type or "other"),
            "title": str(title or "New event"),
            "date": "",
            "note": "",
            "event_kind": "global",
            "origin_location_id": self.current_location_id,
            "_location_id": self.current_location_id,
            "_draft_event": True,
        }
        self.selected_timeline_event_id = NEW_EVENT_DRAFT_ID
        self.reset_event_remove_confirmation()
        self.refresh_timeline()

        if hasattr(self.event_editor, "event_type_value"):
            self.event_editor.event_type_value.set(
                event_type_label(self.draft_event)
            )

        if hasattr(self.event_editor, "title_value"):
            self.event_editor.title_value.set(
                self.draft_event["title"]
            )

        self.event_editor.ensure_new_event_editable()
        return True

    def shared_event_saved(self, event):
        self.draft_event = None
        self.controller.invalidate_caches()
        self.selected_timeline_event_id = str(
            event.get("record_id", "") or ""
        )
        self.refresh_timeline()
        self.status_command(
            f"Saved event {event.get('title', 'Event')}"
        )

        if self.events_changed_command is not None:
            self.events_changed_command()

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
        for event in self.visible_events:
            if (
                str(event.get("event_id", "") or "")
                == self.selected_timeline_event_id
            ):
                return event

        selected = self.timeline_list.curselection()

        if selected and selected[0] < len(self.visible_events):
            selected_event = self.visible_events[selected[0]]
            self.selected_timeline_event_id = str(
                selected_event.get("event_id", "") or ""
            )
            return selected_event

        return None

    def edit_event(self, event=None):
        event = self.selected_timeline_event()

        if event is None:
            return

        if event.get("_draft_event"):
            self.show_event_editor()
            self.event_editor.ensure_new_event_editable()
            return

        can_edit = bool(
            event.get("event_kind") in ("global", "location")
            and not event.get("propagation_distance", 0)
        )

        if not can_edit:
            return

        self.update_timeline_details()
        self.event_editor.begin_edit()
        self.event_editor.canvas.yview_moveto(0)

    def save_event_editor(self, values, storage_kind, original_event):
        if storage_kind == "shared":
            if self.event_controller is None:
                raise ValueError("The event collection is unavailable.")

            source_location_id = str(
                self.current_location_id or ""
            ).strip()
            location_ids = list(values.get("location_ids", []))
            locked_location_ids = list(
                values.get("locked_location_ids", [])
            )

            if source_location_id not in location_ids:
                location_ids.append(source_location_id)

            if source_location_id not in locked_location_ids:
                locked_location_ids.append(source_location_id)

            values["location_ids"] = location_ids
            values["locked_location_ids"] = locked_location_ids
            record_id = str(
                original_event.get("record_id", "") or ""
            ).strip()

            if record_id:
                saved = self.event_controller.update_event(
                    record_id,
                    values,
                )
            else:
                saved = self.event_controller.create_event(values)

            self.shared_event_saved(saved)
            return saved

        if storage_kind != "location":
            raise ValueError(
                "This event is generated from an individual record."
            )

        event_id = str(
            original_event.get("event_id", "") or ""
        ).strip()
        location_id = str(
            original_event.get("origin_location_id", "")
            or self.current_location_id
            or ""
        ).strip()
        location_values = {
            "event_id": event_id,
            "event_type": values["event_type"],
            "title": values["title"],
            "date": values["date"],
            "time": values.get("time", ""),
            "note": values["description"],
        }
        updated_location, saved_event = self.controller.update_event(
            location_id,
            event_id,
            location_values,
        )
        self.selected_timeline_event_id = event_id
        self.refresh_timeline()
        self.status_command(
            f"Saved event {saved_event.get('title', 'Event')}"
        )

        if self.events_changed_command is not None:
            self.events_changed_command()

        return saved_event

    def cancel_event_editor(self):
        if (
            self.draft_event is not None
            or self.event_editor.is_new_event()
        ):
            self.draft_event = None
            self.selected_timeline_event_id = ""
            self.timeline_list.selection_clear(0, "end")
            self.refresh_timeline()
            return

        self.update_timeline_details()

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

        self.selected_timeline_event_id = event_id
        self.refresh_timeline()
        self.status_command("Updated location event")
        return True

    def remove_event(self):
        event = self.selected_timeline_event()

        if event and event.get("_draft_event"):
            self.cancel_event_editor()
            return

        if event is None:
            return

        removable = bool(
            event.get("event_kind") == "global"
            or (
                event.get("event_kind") == "location"
                and not event.get("propagation_distance", 0)
            )
        )

        if not removable:
            self.event_editor.show_error(
                "This event is generated or inherited from another record."
            )
            return

        event_id = str(event.get("event_id", "") or "")

        if self.remove_armed_event_id != event_id:
            self.remove_armed_event_id = event_id
            self.timeline_remove_button.set_text("Confirm remove")
            self.event_editor.show_error(
                "Click Confirm remove again to delete this event."
            )
            return

        if event.get("event_kind") == "global":
            if self.event_controller is None:
                return

            deleted = self.event_controller.delete_event(
                event.get("record_id", "")
            )
            self.controller.invalidate_caches()
            removed_title = deleted.get("title", "Event")
        else:
            self.controller.delete_event(
                self.current_location_id,
                event.get("event_id", ""),
            )
            removed_title = event.get("title", "Event")

        self.selected_timeline_event_id = ""
        self.event_editor.clear(
            "Select an event to view it, or click Add event."
        )
        self.reset_event_remove_confirmation()

        if (
            event.get("event_kind") == "global"
            and self.events_changed_command is not None
        ):
            self.events_changed_command()

        self.refresh_timeline()
        self.status_command(f"Removed event {removed_title}")

    def reset_event_remove_confirmation(self):
        self.remove_armed_event_id = ""

        if hasattr(self, "timeline_remove_button"):
            self.timeline_remove_button.set_text("Remove")

    def open_timeline_selection(self, event=None):
        self.timeline_event_selected(event)
        return "break"


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
