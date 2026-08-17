import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, simpledialog
from uuid import uuid4

from mage_maker.core.dates import (
    format_line_item_date,
    historical_days_in_month,
    historical_year_after,
    historical_year_shift,
)
from mage_maker.core.wizarding_currency import format_monthly_salary
from mage_maker.sections.development.models import (
    ACADEMIC_YEARS_TO_ADULTHOOD,
    calculate_school_start_year,
)
from mage_maker.sections.events.editor import (
    NEW_EVENT_DRAFT_ID,
    EventEditor,
)
from mage_maker.sections.events.controller import (
    DeathEventReplacementRequired,
)
from mage_maker.sections.events.models import (
    death_event_person_ids,
    event_time_sort_key,
    split_world_event_date,
)
from mage_maker.sections.events.types import event_type_label
from mage_maker.sections.timeline.events import (
    EVENT_TYPE_LABELS,
    birth_timeline_summary,
    marriage_timeline_summary,
    murder_people_label,
    murder_timeline_summary,
    normalize_timeline_event,
    normalize_timeline_events,
    sort_timeline_events,
    timeline_event_summary,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    FAMILY_GREEN,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import LabeledEntry, SoftButton


EVENT_COLORS = {
    "starting_location": "#DDD2EA",
    "born": "#EAD7E7",
    "birth_name": "#E2D6ED",
    "gave_birth": "#F7F0C9",
    "had_child": "#F7F0C9",
    "got_married": "#D5EAD9",
    "romance": "#F7E7EE",
    "breakup": "#F7E7EE",
    "died": "#EBCFD6",
    "murder": "#E4C6CF",
    "returns_as_ghost": "#D8D5E8",
    "started_school": "#D9E3F1",
    "opened_business": "#E8D9C4",
    "started_job": "#D8E3EC",
    "received_raise": "#D5EAD9",
    "work_change": "#DDD9EC",
    "relocated": "#D7E9F7",
    "travel": "#EAF4FB",
    "item_event": "#E8DCCB",
    "destroyed": "#EBCFD6",
    "founding": FAMILY_GREEN,
    "name_change": "#DDD2EA",
    "custom": "#E0D2E8",
    "other": "#E0D2E8",
}
LIFE_START_PRIORITIES = {
    "starting_location": 0,
    "born": 1,
    "birth_name": 2,
}
TIMELINE_SECTION_DASHES = "-" * 32


def format_timeline_date(value):
    return format_line_item_date(value)


def timeline_event_background(
    event,
    current_person_id="",
):
    event_values = event if isinstance(event, dict) else {}
    event_type = str(
        event_values.get("event_type", "") or ""
    ).strip().casefold()
    selected_person_id = str(current_person_id or "").strip()

    if event_type in (
        "romance",
        "breakup",
        "relocated",
        "travel",
        "founding",
    ):
        return EVENT_COLORS[event_type]

    if event_type == "born":
        baby_ids = {
            str(person_id or "").strip()
            for person_id in event_values.get("baby_person_ids", [])
            if str(person_id or "").strip()
        }
        parent_ids = {
            str(person_id or "").strip()
            for field_name in (
                "birthing_parent_person_ids",
                "non_birthing_parent_person_ids",
            )
            for person_id in event_values.get(field_name, [])
            if str(person_id or "").strip()
        }

        if selected_person_id in parent_ids:
            return EVENT_COLORS["had_child"]

        if selected_person_id in baby_ids:
            return EVENT_COLORS["born"]

    if event_type in ("gave_birth", "had_child"):
        return EVENT_COLORS["had_child"]

    if (
        event_type == "died"
        or (
            event_type == "murder"
            and selected_person_id
            in event_values.get("victim_person_ids", [])
        )
    ):
        return EVENT_COLORS["died"]

    if event_values.get("_stored_event"):
        return LIST_ALTERNATE

    return EVENT_COLORS.get(event_type, FIELD_BACKGROUND)


class TimelineView(tk.Frame):
    def __init__(
        self,
        parent,
        change_command,
        people_provider=None,
        navigate_command=None,
        name_change_command=None,
        event_controller=None,
        person_id_provider=None,
        linked_events_changed_command=None,
        linked_event_create_command=None,
        linked_event_edit_command=None,
        life_start_save_command=None,
        death_event_save_command=None,
        death_event_delete_command=None,
        name_details_command=None,
        selection_changed_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.change_command = change_command
        self.people_provider = people_provider
        self.navigate_command = navigate_command
        self.name_change_command = name_change_command
        self.event_controller = event_controller
        self.person_id_provider = person_id_provider
        self.linked_events_changed_command = linked_events_changed_command
        self.life_start_save_command = life_start_save_command
        self.death_event_save_command = death_event_save_command
        self.death_event_delete_command = death_event_delete_command
        self.name_details_command = name_details_command
        self.selection_changed_command = selection_changed_command
        self.events = []
        self.linked_events = []
        self.visible_events = []
        self.list_rows = []
        self.draft_event = None
        self.selected_event_id = None
        self.event_editor = None
        self.event_editor_visible = False
        self.loading = False
        self.remove_armed_event_id = ""
        self.render_people = []
        self.render_person_id = ""
        self.render_current_person = {}
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_events)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_workspace()

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=SURFACE, height=44)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            toolbar,
            text="Events",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="nsew")
        self.add_button = SoftButton(
            toolbar,
            text="Add event",
            command=self.start_add_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        self.add_button.grid(row=0, column=1, padx=(6, 0), pady=4)
        self.duplicate_button = SoftButton(
            toolbar,
            text="Duplicate event",
            command=self.duplicate_event,
            background=SURFACE,
            width=126,
            height=36,
        )
        self.duplicate_button.grid(
            row=0,
            column=2,
            padx=(6, 0),
            pady=4,
        )
        self.duplicate_many_button = SoftButton(
            toolbar,
            text="Duplicate many...",
            command=self.duplicate_many_events,
            background=SURFACE,
            width=126,
            height=36,
        )
        self.duplicate_many_button.grid(
            row=0,
            column=3,
            padx=(6, 0),
            pady=4,
        )
        self.remove_button = SoftButton(
            toolbar,
            text="Remove",
            command=self.remove_event,
            background=SURFACE,
            width=118,
            height=36,
        )
        self.remove_button.grid(row=0, column=4, padx=(6, 0), pady=4)

    def build_workspace(self):
        self.workspace = tk.Frame(self, bg=SURFACE)
        self.workspace.grid(row=1, column=0, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=5, uniform="timeline")
        self.workspace.grid_columnconfigure(1, weight=4, uniform="timeline")
        self.list_panel = tk.Frame(
            self.workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        self.list_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        self.list_panel.grid_rowconfigure(2, weight=1)
        self.list_panel.grid_columnconfigure(0, weight=1)
        list_heading = tk.Label(
            self.list_panel,
            text="Events in date order",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        list_heading.grid(row=0, column=0, sticky="ew")
        search_entry = LabeledEntry(
            self.list_panel,
            "Search events",
            self.search_value,
            background=SURFACE_MUTED,
        )
        search_entry.grid(row=1, column=0, sticky="ew", pady=(10, 9))
        list_frame = tk.Frame(self.list_panel, bg=SURFACE_MUTED)
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
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.select_event)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        self.name_details_panel = tk.Frame(
            self.workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=24,
            pady=24,
        )
        self.name_details_panel.grid_columnconfigure(0, weight=1)
        name_heading = tk.Label(
            self.name_details_panel,
            text="Birth name",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        name_heading.grid(row=0, column=0, sticky="ew")
        name_explanation = tk.Label(
            self.name_details_panel,
            text="Birth name is edited in the Name Details panel.",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            justify="left",
            wraplength=420,
        )
        name_explanation.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(12, 18),
        )
        self.name_details_button = SoftButton(
            self.name_details_panel,
            text="Open Name Details",
            command=self.open_name_details,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=154,
            height=36,
        )
        self.name_details_button.grid(row=2, column=0, sticky="w")
        self.name_details_panel.grid_remove()
        self.hide_event_editor()
        self.update_button_state()

    def ensure_event_editor(self):
        """Build the expensive editor only after the user needs it.

        The editor owns several searchable association pickers. Constructing
        those pickers while merely opening Timeline used to enumerate the
        complete People collection, which made a list-only view scale with the
        size of the whole world.
        """
        if self.event_editor is not None:
            return self.event_editor

        self.event_editor = EventEditor(
            self.workspace,
            self.event_controller,
            self.save_editor_event,
            self.cancel_editor,
            context="person",
            background=SURFACE_MUTED,
        )
        self.event_editor.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.event_editor.grid_remove()
        return self.event_editor

    def show_editor_error(self, message):
        event_editor = self.ensure_event_editor()
        self.show_event_editor()
        event_editor.show_error(message)

    def show_event_editor(self):
        event_editor = self.ensure_event_editor()

        if self.event_editor_visible:
            return

        self.name_details_panel.grid_remove()
        self.workspace.grid_columnconfigure(
            0,
            weight=5,
            uniform="timeline",
        )
        self.workspace.grid_columnconfigure(
            1,
            weight=4,
            uniform="timeline",
        )
        self.list_panel.grid(
            row=0,
            column=0,
            columnspan=1,
            sticky="nsew",
            padx=(0, 7),
        )
        event_editor.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.event_editor_visible = True

    def show_name_details_panel(self):
        if self.event_editor is not None:
            self.event_editor.grid_remove()
        self.workspace.grid_columnconfigure(
            0,
            weight=5,
            uniform="timeline",
        )
        self.workspace.grid_columnconfigure(
            1,
            weight=4,
            uniform="timeline",
        )
        self.list_panel.grid(
            row=0,
            column=0,
            columnspan=1,
            sticky="nsew",
            padx=(0, 7),
        )
        self.name_details_panel.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.name_details_button.set_enabled(
            self.name_details_command is not None
        )
        self.event_editor_visible = False

    def hide_event_editor(self):
        if self.event_editor is not None:
            self.event_editor.grid_remove()
        self.name_details_panel.grid_remove()
        self.workspace.grid_columnconfigure(
            0,
            weight=1,
            uniform="",
        )
        self.workspace.grid_columnconfigure(
            1,
            weight=0,
            uniform="",
        )
        self.list_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="nsew",
            padx=0,
        )
        self.event_editor_visible = False

    def open_name_details(self):
        if self.name_details_command is None:
            return

        self.name_details_command()

    def current_person_id(self):
        person_id_provider = getattr(self, "person_id_provider", None)

        if person_id_provider is None:
            return ""

        return str(person_id_provider() or "").strip()

    def current_person(self):
        person_id = self.current_person_id()
        people_provider = getattr(self, "people_provider", None)

        if not person_id or people_provider is None:
            return {}

        if getattr(self, "render_person_id", None) == person_id:
            rendered_person = getattr(self, "render_current_person", None)

            if isinstance(rendered_person, dict):
                return rendered_person

        return next(
            (
                person
                for person in people_provider()
                if isinstance(person, dict)
                and str(person.get("record_id", "") or "").strip()
                == person_id
            ),
            {},
        )

    def default_location_ids_for_current_person(self):
        location_command = getattr(
            getattr(self, "event_controller", None),
            "current_location_id_for_person",
            None,
        )

        if not callable(location_command):
            return ()

        location_id = str(
            location_command(self.current_person_id()) or ""
        ).strip()
        return (location_id,) if location_id else ()

    def timeline_section_boundaries(self):
        person = self.current_person()
        school_name = str(person.get("school", "") or "").strip()
        attends_school = bool(
            school_name and not bool(person.get("non_magical"))
        )
        birth_year = person.get("birth_year")
        birth_month = person.get("birth_month")
        birth_day = person.get("birth_day")

        if attends_school:
            school_start_year = calculate_school_start_year(
                birth_year,
                birth_month,
                birth_day,
            )

            if school_start_year is None:
                return attends_school, None, None

            school_start_key = (school_start_year, 9, 1)
            actual_school_starts = [
                self.event_date_parts(event.get("date"))
                for event in [*self.events, *self.linked_events]
                if str(event.get("event_type", "") or "")
                == "started_school"
                and self.event_date_parts(event.get("date"))[0] < 10000
            ]

            if actual_school_starts:
                school_start_key = min(actual_school_starts)

            try:
                adulthood_year = historical_year_shift(
                    school_start_year,
                    ACADEMIC_YEARS_TO_ADULTHOOD,
                )
            except (TypeError, ValueError):
                adulthood_year = None

            adulthood_key = (
                (adulthood_year, 9, 1)
                if adulthood_year is not None
                else None
            )
            return True, school_start_key, adulthood_key

        try:
            adulthood_year = historical_year_shift(birth_year, 18)
        except (TypeError, ValueError):
            adulthood_year = None

        adulthood_key = (
            (
                adulthood_year,
                int(birth_month or 1),
                int(birth_day or 1),
            )
            if adulthood_year is not None
            else None
        )
        return False, None, adulthood_key

    def timeline_section_name(
        self,
        event,
        attends_school,
        school_start_key,
        adulthood_key,
    ):
        event_key = event.get("_display_date_parts")

        if event_key is None:
            event_key = self.event_date_parts(event.get("date"))

        if event_key[0] >= 10000:
            return "childhood"

        if attends_school:
            if school_start_key is None or event_key < school_start_key:
                return "childhood"

            if adulthood_key is None or event_key < adulthood_key:
                return "school"

            return "adulthood"

        if adulthood_key is not None and event_key >= adulthood_key:
            return "adulthood"

        return "childhood"

    def set_events(self, events, refresh=True):
        self.loading = True

        if (
            self.draft_event is not None
            and self.draft_event.get("_person_id") != self.current_person_id()
        ):
            self.draft_event = None
            self.selected_event_id = None

        self.events = normalize_timeline_events(events)
        available_ids = {
            event["event_id"]
            for event in self.events
        }.union(
            {
                str(event.get("record_id", "") or "")
                for event in self.linked_events
            }
        )

        if self.draft_event is not None:
            available_ids.add(NEW_EVENT_DRAFT_ID)

        if self.selected_event_id not in available_ids:
            self.selected_event_id = None

        if refresh:
            self.filter_events()
        self.loading = False

    def get_events(self):
        return deepcopy(self.events)

    def set_linked_events(self, events, refresh=True):
        self.linked_events = [
            deepcopy(event)
            for event in events
            if isinstance(event, dict)
            and str(event.get("record_id", "") or "").strip()
        ]
        available_ids = {
            event["event_id"]
            for event in self.events
        }.union(
            {
                str(event.get("record_id", "") or "")
                for event in self.linked_events
            }
        )

        if self.draft_event is not None:
            available_ids.add(NEW_EVENT_DRAFT_ID)

        if self.selected_event_id not in available_ids:
            self.selected_event_id = None

        if refresh:
            self.filter_events()

    def reset_for_person_change(self):
        """Clear stale Timeline state without querying the People index."""
        self.loading = True
        self.draft_event = None
        self.selected_event_id = None
        self.events = []
        self.linked_events = []
        self.visible_events = []
        self.list_rows = []
        self.render_people = []
        self.render_current_person = {}
        self.render_person_id = ""
        self.listbox.delete(0, "end")
        self.hide_event_editor()
        self.reset_remove_confirmation()
        self.update_button_state()
        self.loading = False

    def filter_events(self, *arguments):
        unsaved_changes_command = getattr(
            getattr(self, "event_editor", None),
            "has_unsaved_changes",
            None,
        )
        preserve_unsaved_editor = bool(
            callable(unsaved_changes_command)
            and unsaved_changes_command()
            and not bool(
                getattr(
                    getattr(self, "event_editor", None),
                    "saving",
                    False,
                )
            )
        )
        query = self.search_value.get().strip().casefold()
        current_person_id_command = getattr(
            self,
            "current_person_id",
            None,
        )
        current_person_id = (
            str(current_person_id_command() or "").strip()
            if callable(current_person_id_command)
            else TimelineView.current_person_id(self)
        )
        people_provider = getattr(self, "people_provider", None)
        self.render_person_id = current_person_id
        candidate_events = [deepcopy(event) for event in self.events]
        linked_birth_for_current_person = any(
            linked_event.get("event_type") == "born"
            and current_person_id in linked_event.get("baby_person_ids", [])
            for linked_event in self.linked_events
        )

        if linked_birth_for_current_person:
            candidate_events = [
                event
                for event in candidate_events
                if not (
                    event.get("event_type") == "born"
                    and event.get("automatic_source") == "life_start"
                )
            ]

        for linked_event in self.linked_events:
            display_event = deepcopy(linked_event)
            display_event["event_id"] = display_event["record_id"]
            display_event["_stored_event"] = True
            display_event["detail"] = display_event.get("title", "")
            display_event["note"] = display_event.get("description", "")
            candidate_events.append(display_event)

        if self.draft_event is not None:
            candidate_events.append(deepcopy(self.draft_event))

        relevant_person_ids = (
            {current_person_id} if current_person_id else set()
        )
        scalar_person_fields = ("person_id", "related_person_id")
        list_person_fields = (
            "person_ids",
            "baby_person_ids",
            "birthing_parent_person_ids",
            "non_birthing_parent_person_ids",
            "perpetrator_person_ids",
            "victim_person_ids",
            "witness_person_ids",
            "affected_person_ids",
            "eminence_person_ids",
        )

        for event in candidate_events:
            for field_name in scalar_person_fields:
                person_id = str(event.get(field_name, "") or "").strip()

                if person_id:
                    relevant_person_ids.add(person_id)

            for field_name in list_person_fields:
                relevant_person_ids.update(
                    str(person_id or "").strip()
                    for person_id in event.get(field_name, [])
                    if str(person_id or "").strip()
                )

        self.render_people = (
            [
                person
                for person in people_provider()
                if isinstance(person, dict)
                and str(person.get("record_id", "") or "").strip()
                in relevant_person_ids
            ]
            if people_provider is not None
            else []
        )
        self.render_current_person = next(
            (
                person
                for person in self.render_people
                if str(person.get("record_id", "") or "").strip()
                == current_person_id
            ),
            {},
        )

        self.visible_events = []

        for event in candidate_events:
            summary = self.event_summary_text(event)
            event["_display_summary"] = summary
            event["_display_date_parts"] = self.event_date_parts(
                event.get("date")
            )

            if (
                not event.get("_draft_event")
                and query
                and query not in summary.casefold()
                and query not in str(event.get("detail") or "").casefold()
                and query not in str(event.get("note") or "").casefold()
                and query not in str(event.get("date") or "").casefold()
                and query not in str(event.get("time") or "").casefold()
            ):
                continue

            self.visible_events.append(event)

        self.visible_events.sort(key=self.display_event_sort_key)
        self.listbox.delete(0, "end")
        self.list_rows = []
        draft_events = [
            event
            for event in self.visible_events
            if event.get("_draft_event")
        ]
        dated_events = [
            event
            for event in self.visible_events
            if not event.get("_draft_event")
        ]

        for draft_event in draft_events:
            row_index = len(self.list_rows)
            self.list_rows.append(draft_event)
            self.listbox.insert("end", "New event (unsaved)")
            self.listbox.itemconfigure(
                row_index,
                background=PRIMARY_SOFT,
            )

            if draft_event.get("event_id") == self.selected_event_id:
                self.listbox.selection_set(row_index)
                self.listbox.see(row_index)

        if not dated_events:
            if (
                not preserve_unsaved_editor
                and (
                    self.event_editor is not None
                    or self.draft_event is not None
                )
            ):
                self.refresh_editor()
            self.update_button_state()
            return

        attends_school, school_start_key, adulthood_key = (
            self.timeline_section_boundaries()
        )
        section_definitions = [
            ("childhood", "Childhood"),
        ]

        if attends_school:
            section_definitions.append(("school", "School"))

        section_definitions.append(("adulthood", "Adulthood"))
        events_by_section = {
            "childhood": [],
            "school": [],
            "adulthood": [],
        }

        for event in dated_events:
            section_name = self.timeline_section_name(
                event,
                attends_school,
                school_start_key,
                adulthood_key,
            )

            if section_name in events_by_section:
                events_by_section[section_name].append(event)

        for section_name, section_label in section_definitions:
            header_index = len(self.list_rows)
            self.list_rows.append(None)
            self.listbox.insert(
                "end",
                (
                    f"{TIMELINE_SECTION_DASHES} {section_label} "
                    f"{TIMELINE_SECTION_DASHES}"
                ),
            )
            self.listbox.itemconfigure(
                header_index,
                background=PRIMARY_SOFT,
                foreground=TEXT_DARK,
                selectbackground=PRIMARY_SOFT,
                selectforeground=TEXT_DARK,
            )

            for event in events_by_section[section_name]:
                row_index = len(self.list_rows)
                self.list_rows.append(event)
                event_date = format_timeline_date(event.get("date"))
                event_time = str(event.get("time", "") or "").strip()

                if event_time:
                    event_date = f"{event_date} {event_time}"

                self.listbox.insert(
                    "end",
                    f"{event_date}: {event['_display_summary']}",
                )
                self.listbox.itemconfigure(
                    row_index,
                    background=timeline_event_background(
                        event,
                        current_person_id,
                    ),
                )

                if event.get("event_id") == self.selected_event_id:
                    self.listbox.selection_set(row_index)
                    self.listbox.see(row_index)

        if (
            not preserve_unsaved_editor
            and (
                self.event_editor is not None
                or self.draft_event is not None
            )
        ):
            self.refresh_editor()
        self.update_button_state()

    def event_summary_text(self, event):
        if event.get("_draft_event"):
            return "New event (unsaved)"

        current_person_id_command = getattr(
            self,
            "current_person_id",
            None,
        )
        current_person_id = (
            str(current_person_id_command() or "").strip()
            if callable(current_person_id_command)
            else TimelineView.current_person_id(self)
        )
        people_provider = getattr(self, "people_provider", None)
        people = (
            getattr(self, "render_people", [])
            if getattr(self, "render_person_id", None) == current_person_id
            else (
                people_provider()
                if people_provider is not None
                else []
            )
        )

        if event.get("event_type") == "murder":
            return murder_timeline_summary(
                event,
                current_person_id,
                people,
            )

        if event.get("_stored_event"):
            event_title = str(
                event.get("title", "") or event_type_label(event)
            ).strip()

            if current_person_id in event.get(
                "witness_person_ids",
                [],
            ):
                return f"Witnessed: {event_title}"

            if current_person_id in event.get(
                "affected_person_ids",
                [],
            ):
                if event.get("event_type") in ("died", "murder"):
                    return (
                        "Affected by death of "
                        + murder_people_label(
                            death_event_person_ids(event),
                            people,
                        )
                    )

                return f"Affected by: {event_title}"

        if event.get("event_type") == "born" and event.get(
            "_stored_event"
        ):
            return birth_timeline_summary(
                event,
                current_person_id,
                people,
            )

        if (
            event.get("_stored_event")
            and event.get("event_type") == "got_married"
        ):
            return marriage_timeline_summary(
                event,
                current_person_id,
                people,
            )

        if (
            event.get("_stored_event")
            and event.get("event_type") == "returns_as_ghost"
        ):
            return str(
                event.get("title", "") or "Returns as ghost"
            ).strip()

        if event.get("_stored_event"):
            summary = (
                f"{event_type_label(event)} · "
                f"{event.get('title', 'Event')}"
            )

            if (
                event.get("event_type")
                in ("started_job", "received_raise")
                and event.get("salary") is not None
            ):
                summary += (
                    f" · {format_monthly_salary(event['salary'])}"
                )

            return summary

        return timeline_event_summary(event)

    def display_event_sort_key(self, event):
        if event.get("_draft_event"):
            return -1, 0, 0, 0, 0, 0, ""

        event_type = str(event.get("event_type", "") or "")
        current_person_id_command = getattr(
            self,
            "current_person_id",
            None,
        )
        current_person_id = (
            str(current_person_id_command() or "").strip()
            if callable(current_person_id_command)
            else TimelineView.current_person_id(self)
        )

        if (
            not event.get("_stored_event")
            and event_type in LIFE_START_PRIORITIES
        ) or (
            event.get("_stored_event")
            and event_type == "born"
            and current_person_id in event.get("baby_person_ids", [])
        ):
            return (
                0,
                LIFE_START_PRIORITIES[event_type],
                0,
                0,
                0,
                event_time_sort_key(event.get("time")),
                "",
            )

        date_parts = event.get("_display_date_parts")

        if date_parts is None:
            date_parts = self.event_date_parts(event.get("date"))

        year, month, day = date_parts
        terminal_priority = 0

        if event_type == "died":
            terminal_priority = 1
        elif (
            event_type == "murder"
            and current_person_id in event.get("victim_person_ids", [])
        ):
            terminal_priority = 1
        elif event_type == "returns_as_ghost":
            terminal_priority = 2

        return (
            1,
            year,
            month,
            day,
            event_time_sort_key(event.get("time")),
            terminal_priority,
            str(
                event.get("_display_summary")
                or self.event_summary_text(event)
            ).casefold(),
        )

    def event_date_parts(self, value):
        date_text = str(value or "").strip()

        if not date_text:
            return 10000, 13, 32

        negative = date_text.startswith("-")
        body = date_text[1:] if negative else date_text
        parts = body.split("-")

        try:
            year = int(parts[0])
        except (TypeError, ValueError, IndexError):
            return 10000, 13, 32

        if negative:
            year = -year

        try:
            month = int(parts[1]) if len(parts) > 1 else 0
        except (TypeError, ValueError):
            month = 0

        try:
            day = int(parts[2]) if len(parts) > 2 else 0
        except (TypeError, ValueError):
            day = 0

        return year, month, day

    def select_event(self, event=None):
        selected_indexes = self.listbox.curselection()

        if not selected_indexes:
            return

        list_rows = getattr(self, "list_rows", self.visible_events)
        selected_index = selected_indexes[0]
        requested_event = (
            list_rows[selected_index]
            if selected_index < len(list_rows)
            else None
        )
        requested_event_id = (
            str(requested_event.get("event_id", "") or "")
            if isinstance(requested_event, dict)
            else ""
        )

        if (
            requested_event_id != str(self.selected_event_id or "")
            and not self.confirm_unsaved_event_changes()
        ):
            self.restore_selected_event_row()
            return "break"

        if requested_event is None:
            self.selected_event_id = None
            self.listbox.selection_clear(0, "end")
            self.refresh_editor()
            self.update_button_state()
            return

        self.selected_event_id = requested_event_id

        if self.selection_changed_command is not None:
            self.selection_changed_command(requested_event_id)

        self.reset_remove_confirmation()
        self.refresh_editor()
        self.update_button_state()

    def restore_selected_event_row(self):
        self.listbox.selection_clear(0, "end")

        for index, row in enumerate(
            getattr(self, "list_rows", self.visible_events)
        ):
            if not isinstance(row, dict):
                continue

            if str(row.get("event_id", "") or "") != str(
                self.selected_event_id or ""
            ):
                continue

            self.listbox.selection_set(index)
            self.listbox.see(index)
            return True

        return False

    def confirm_unsaved_event_changes(self):
        association_guard_command = getattr(
            getattr(self, "event_editor", None),
            "association_selection_guard_active",
            None,
        )

        if (
            callable(association_guard_command)
            and association_guard_command()
        ):
            return False

        unsaved_changes_command = getattr(
            getattr(self, "event_editor", None),
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
            return self.event_editor.save()

        self.event_editor.cancel()
        return True

    def selected_event(self):
        for event in self.visible_events:
            if event.get("event_id") == self.selected_event_id:
                return event

        selected_indexes = self.listbox.curselection()

        list_rows = getattr(self, "list_rows", self.visible_events)

        if selected_indexes and selected_indexes[0] < len(list_rows):
            selected_event = list_rows[selected_indexes[0]]

            if selected_event is None:
                return None

            self.selected_event_id = selected_event.get("event_id")
            return selected_event

        return None

    def refresh_editor(self):
        selected_event = self.selected_event()

        if selected_event is None and self.event_editor is None:
            self.hide_event_editor()
            return

        if (
            selected_event is not None
            and selected_event.get("automatic_source") == "life_start"
            and selected_event.get("event_type") == "birth_name"
        ):
            self.show_name_details_panel()
            return

        event_editor = self.ensure_event_editor()
        comparison_command = getattr(
            event_editor,
            "set_comparison_events",
            None,
        )

        if callable(comparison_command):
            comparison_command([*self.events, *self.linked_events])

        if selected_event is None:
            if event_editor.is_new_event():
                self.show_event_editor()
                event_editor.ensure_new_event_editable()
                return

            event_editor.clear(
                "Select an event to view it, or click Add event."
            )
            self.hide_event_editor()
            return

        if selected_event.get("_draft_event"):
            self.show_event_editor()

            if not self.event_editor.is_new_event():
                self.event_editor.start_new(
                    context="person",
                    default_person_ids=(self.current_person_id(),),
                    locked_person_ids=(self.current_person_id(),),
                    default_location_ids=(
                        self.default_location_ids_for_current_person()
                    ),
                )

            self.event_editor.ensure_new_event_editable()
            return

        self.show_event_editor()
        person_id = self.current_person_id()

        if selected_event.get("_stored_event"):
            stored_event = (
                self.event_controller.get_event(
                    selected_event.get("record_id", "")
                )
                if self.event_controller is not None
                else None
            )

            if stored_event is None:
                self.event_editor.clear("This event no longer exists.")
                return

            current_person_is_ancillary = bool(
                person_id
                and (
                    person_id
                    in stored_event.get("witness_person_ids", [])
                    or person_id
                    in stored_event.get("affected_person_ids", [])
                )
            )

            self.event_editor.load_event(
                stored_event,
                storage_kind="shared",
                context="person",
                person_ids=(
                    ()
                    if current_person_is_ancillary
                    else (person_id,)
                ),
                locked_person_ids=(
                    ()
                    if current_person_is_ancillary
                    or stored_event.get("event_type")
                    in ("born", "murder")
                    else (person_id,)
                ),
                read_only=False,
            )
            return

        automatic_source = str(
            selected_event.get("automatic_source", "") or ""
        )
        event_type = str(
            selected_event.get("event_type", "") or ""
        )

        if automatic_source == "life_start" and event_type == "birth_name":
            self.show_name_details_panel()
            return

        if (
            automatic_source == "life_start"
            and event_type in ("starting_location", "born")
        ):
            location_ids = [
                str(location_id or "").strip()
                for location_id in selected_event.get("location_ids", [])
                if str(location_id or "").strip()
            ]
            location_name = str(
                selected_event.get("detail", "") or ""
            ).strip()

            if event_type == "born":
                starting_event = next(
                    (
                        event
                        for event in self.events
                        if event.get("event_type") == "starting_location"
                    ),
                    {},
                )

                if not location_ids:
                    location_ids = [
                        str(location_id or "").strip()
                        for location_id in starting_event.get(
                            "location_ids",
                            [],
                        )
                        if str(location_id or "").strip()
                    ]

                if not location_name:
                    location_name = str(
                        starting_event.get("detail", "") or ""
                    ).strip()

            if (
                not location_ids
                and location_name
                and self.event_controller is not None
            ):
                for location in self.event_controller.location_records():
                    if (
                        str(location.get("name", "") or "")
                        .strip()
                        .casefold()
                        != location_name.casefold()
                    ):
                        continue

                    location_id = str(
                        location.get("record_id", "") or ""
                    ).strip()

                    if location_id:
                        location_ids = [location_id]

                    break

            self.event_editor.load_event(
                selected_event,
                storage_kind="timeline",
                context="person",
                person_ids=(person_id,),
                locked_person_ids=(person_id,),
                location_ids=location_ids,
                read_only=False,
                explanation=(
                    "Changing the location updates both Starting location "
                    "and Born."
                    if event_type == "starting_location"
                    else (
                        "Changing the birth date updates the person and all "
                        "three opening events. Changing the location also "
                        "updates Starting location."
                    )
                ),
                lock_title=True,
                lock_date=event_type == "starting_location",
                lock_people=True,
                single_location=True,
                title_from_location=event_type == "starting_location",
                display_title=(
                    location_name
                    if event_type == "starting_location"
                    else "Born"
                ),
            )
            return

        if automatic_source == "death_date":
            self.event_editor.load_event(
                selected_event,
                storage_kind="timeline",
                context="person",
                person_ids=(person_id,),
                locked_person_ids=(person_id,),
                read_only=False,
                explanation=(
                    "Saving this event updates the read-only death date "
                    "shown on Overview."
                ),
                lock_date=False,
                lock_people=True,
                single_location=True,
            )
            return

        read_only = bool(automatic_source)
        explanation = ""

        if automatic_source == "life_start":
            explanation = (
                "This required opening event is synchronized from the "
                "person's profile and Name Details."
            )
        elif automatic_source:
            explanation = (
                "This event is synchronized automatically from its source record."
            )

        self.event_editor.load_event(
            selected_event,
            storage_kind="timeline",
            context="person",
            person_ids=(person_id,),
            locked_person_ids=(person_id,),
            read_only=read_only,
            explanation=explanation,
        )

    def start_add_event(self):
        person_id = self.current_person_id()

        if self.event_controller is None or not person_id:
            self.show_event_editor()
            self.event_editor.show_error(
                "Save this person before adding an event."
            )
            return

        if not self.confirm_unsaved_event_changes():
            return

        self.draft_event = {
            "event_id": NEW_EVENT_DRAFT_ID,
            "event_type": "custom",
            "detail": "New event",
            "date": "",
            "note": "",
            "_person_id": person_id,
            "_draft_event": True,
        }
        self.selected_event_id = NEW_EVENT_DRAFT_ID
        self.reset_remove_confirmation()
        self.filter_events()
        self.event_editor.ensure_new_event_editable()

    def open_add_dialog(self):
        self.start_add_event()

    def edit_selected_event(self, event=None):
        selected_event = self.selected_event()

        if selected_event is None:
            return

        if selected_event.get("_draft_event"):
            self.show_event_editor()
            self.event_editor.ensure_new_event_editable()
            return

        if (
            selected_event.get("automatic_source")
            and selected_event.get("automatic_source") != "death_date"
        ):
            return

        self.refresh_editor()
        self.event_editor.begin_edit()
        self.event_editor.canvas.yview_moveto(0)

    def open_edit_dialog(self, event=None):
        self.edit_selected_event(event)

    def save_editor_event(self, values, storage_kind, original_event):
        if storage_kind == "shared":
            if self.event_controller is None:
                raise ValueError("The event collection is unavailable.")

            record_id = str(
                original_event.get("record_id", "") or ""
            ).strip()

            try:
                if record_id:
                    saved = self.event_controller.update_event(
                        record_id,
                        values,
                    )
                else:
                    saved = self.event_controller.create_event(values)
            except DeathEventReplacementRequired as error:
                replace_existing = messagebox.askyesno(
                    "Replace existing Death event?",
                    (
                        f"{error}\n\nSaving this event will replace the "
                        "existing Death event. Continue?"
                    ),
                    parent=self,
                    icon="warning",
                    default="no",
                )

                if not replace_existing:
                    return False

                if record_id:
                    saved = self.event_controller.update_event(
                        record_id,
                        values,
                        replace_existing_death=True,
                    )
                else:
                    saved = self.event_controller.create_event(
                        values,
                        replace_existing_death=True,
                    )

            self.draft_event = None
            self.selected_event_id = saved["record_id"]
            person_id = self.current_person_id()
            self.linked_events = (
                self.event_controller.events_for_person(person_id)
                if person_id
                else []
            )
            self.filter_events()

            if self.linked_events_changed_command is not None:
                self.linked_events_changed_command(saved)

            return saved

        if (
            storage_kind == "timeline"
            and original_event.get("automatic_source") == "life_start"
            and original_event.get("event_type")
            in ("starting_location", "born")
        ):
            if self.life_start_save_command is None:
                raise ValueError(
                    "This opening event cannot be synchronized."
                )

            synchronized_events = self.life_start_save_command(
                values,
                deepcopy(original_event),
            )
            self.events = normalize_timeline_events(
                synchronized_events
            )
            self.selected_event_id = str(
                original_event.get("event_id", "") or ""
            )
            self.filter_events()

            if not self.loading:
                self.change_command()

            for event in self.events:
                if (
                    event.get("event_id")
                    == self.selected_event_id
                ):
                    return deepcopy(event)

            raise ValueError(
                "The synchronized opening event could not be reloaded."
            )

        if (
            storage_kind == "timeline"
            and original_event.get("automatic_source") == "death_date"
        ):
            if self.death_event_save_command is None:
                raise ValueError(
                    "This Death event cannot be synchronized."
                )

            synchronized_events = self.death_event_save_command(
                values,
                deepcopy(original_event),
            )
            self.events = normalize_timeline_events(
                synchronized_events
            )
            self.selected_event_id = str(
                original_event.get("event_id", "") or ""
            )
            self.filter_events()

            if not self.loading:
                self.change_command()

            for event in self.events:
                if event.get("event_id") == self.selected_event_id:
                    return deepcopy(event)

            raise ValueError(
                "The synchronized Death event could not be reloaded."
            )

        if (
            storage_kind == "timeline"
            and values.get("event_type") in ("died", "murder")
        ):
            raise ValueError(
                "Create Death and Murder as new Timeline events so their "
                "people and death dates stay synchronized."
            )

        timeline_event = deepcopy(original_event)
        timeline_event.update(
            {
                "event_type": values["event_type"],
                "detail": values["title"],
                "date": values["date"],
                "time": values.get("time", ""),
                "note": values["description"],
                "person_ids": values["person_ids"],
                "perpetrator_person_ids": values.get(
                    "perpetrator_person_ids",
                    [],
                ),
                "victim_person_ids": values.get(
                    "victim_person_ids",
                    [],
                ),
                "witness_person_ids": values.get(
                    "witness_person_ids",
                    [],
                ),
                "affected_person_ids": values.get(
                    "affected_person_ids",
                    [],
                ),
                "location_ids": values["location_ids"],
                "locked_location_ids": values["locked_location_ids"],
                "organization_id": values.get("organization_id", ""),
                "organization_name": values.get(
                    "organization_name",
                    "",
                ),
                "organization_job_id": values.get(
                    "organization_job_id",
                    "",
                ),
                "job_title": values.get("job_title", ""),
                "job_assignment_id": values.get(
                    "job_assignment_id",
                    "",
                ),
                "job_end_date": values.get("job_end_date", ""),
                "salary": values.get("salary"),
            }
        )
        return self.save_event(timeline_event)

    def save_event(self, event):
        normalized_event = normalize_timeline_event(event)

        if normalized_event.get("event_type") == "died":
            existing_death_event = next(
                (
                    existing_event
                    for existing_event in self.events
                    if existing_event.get("event_id")
                    != normalized_event["event_id"]
                    and existing_event.get("event_type") == "died"
                ),
                None,
            )

            if existing_death_event is not None:
                raise ValueError(
                    "This person already has a Death event."
                )

        replacement_index = None

        for index, existing_event in enumerate(self.events):
            if existing_event.get("event_id") == normalized_event["event_id"]:
                replacement_index = index
                break

        if replacement_index is None:
            self.events.append(normalized_event)
        else:
            self.events[replacement_index] = normalized_event

        self.events = sort_timeline_events(self.events)
        self.selected_event_id = normalized_event["event_id"]
        self.filter_events()

        if not self.loading:
            self.change_command()

        return normalized_event

    def cancel_editor(self):
        if (
            self.draft_event is not None
            or (
                self.event_editor is not None
                and self.event_editor.is_new_event()
            )
        ):
            self.draft_event = None
            self.selected_event_id = None
            self.listbox.selection_clear(0, "end")
            self.filter_events()
            return

        self.refresh_editor()

    def update_button_state(self):
        selected_event = self.selected_event()
        has_selection = selected_event is not None
        automatic = bool(
            has_selection
            and selected_event.get("automatic_source")
        )
        removable_automatic_death = bool(
            automatic
            and selected_event.get("automatic_source") == "death_date"
            and self.death_event_delete_command is not None
        )
        self.remove_button.set_enabled(
            has_selection
            and (not automatic or removable_automatic_death)
            and not selected_event.get("_draft_event")
        )
        can_duplicate = bool(
            has_selection
            and not automatic
            and not selected_event.get("_draft_event")
            and not selected_event.get("organization_event")
            and selected_event.get("event_type")
            not in ("died", "murder")
        )

        if hasattr(self, "duplicate_button"):
            self.duplicate_button.set_enabled(can_duplicate)

        if hasattr(self, "duplicate_many_button"):
            self.duplicate_many_button.set_enabled(can_duplicate)

    def duplicate_event(self):
        selected_event = self.selected_event()

        if selected_event is None or selected_event.get("_draft_event"):
            return False

        association_guard_command = getattr(
            self.event_editor,
            "association_selection_guard_active",
            None,
        )

        if (
            callable(association_guard_command)
            and association_guard_command()
        ):
            return False

        unsaved_changes_command = getattr(
            self.event_editor,
            "has_unsaved_changes",
            None,
        )

        if (
            callable(unsaved_changes_command)
            and unsaved_changes_command()
        ):
            if not self.event_editor.save():
                return False

            selected_event = self.selected_event()

            if selected_event is None or selected_event.get("_draft_event"):
                return False

        if selected_event.get("automatic_source"):
            self.show_editor_error(
                "Automatic events cannot be duplicated."
            )
            return False

        if selected_event.get("event_type") in ("died", "murder"):
            self.show_editor_error(
                "Death and Murder events cannot be duplicated."
            )
            return False

        if selected_event.get("organization_event"):
            self.show_editor_error(
                "Organization-owned events cannot be duplicated here."
            )
            return False

        if selected_event.get("_stored_event"):
            if self.event_controller is None:
                return False

            try:
                duplicated = self.event_controller.duplicate_event(
                    selected_event.get("record_id", "")
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                self.show_editor_error(str(error))
                return False

            person_id = self.current_person_id()
            self.linked_events = (
                self.event_controller.events_for_person(person_id)
                if person_id
                else []
            )
            self.selected_event_id = duplicated["record_id"]
            self.filter_events()

            if self.linked_events_changed_command is not None:
                self.linked_events_changed_command(duplicated)

            return True

        duplicated = deepcopy(selected_event)
        duplicated["event_id"] = str(uuid4())
        duplicated.pop("record_id", None)
        duplicated.pop("_stored_event", None)
        duplicated.pop("_draft_event", None)
        duplicated.pop("_person_id", None)
        duplicate_year, duplicate_month, duplicate_day = (
            split_world_event_date(duplicated.get("date", ""))
        )

        if duplicate_year:
            next_year = int(duplicate_year)

            if duplicate_month:
                next_month = int(duplicate_month) + 1

                if next_month > 12:
                    next_month = 1
                    next_year = historical_year_after(next_year)

                duplicated["date"] = f"{next_year}-{next_month:02d}"

                if duplicate_day:
                    next_day = min(
                        int(duplicate_day),
                        historical_days_in_month(next_year, next_month),
                    )
                    duplicated["date"] += f"-{next_day:02d}"
            else:
                duplicated["date"] = str(
                    historical_year_after(next_year)
                )

        self.save_event(duplicated)
        return True

    def duplicate_many_events(self):
        selected_event = self.selected_event()

        if selected_event is None or selected_event.get("_draft_event"):
            return False

        association_guard_command = getattr(
            self.event_editor,
            "association_selection_guard_active",
            None,
        )

        if (
            callable(association_guard_command)
            and association_guard_command()
        ):
            return False

        if selected_event.get("automatic_source"):
            self.show_editor_error(
                "Automatic events cannot be duplicated."
            )
            return False

        if selected_event.get("event_type") in ("died", "murder"):
            self.show_editor_error(
                "Death and Murder events cannot be duplicated."
            )
            return False

        if selected_event.get("organization_event"):
            self.show_editor_error(
                "Organization-owned events cannot be duplicated here."
            )
            return False

        copy_count = simpledialog.askinteger(
            "Duplicate event many times",
            "How many copies should be created?",
            parent=self,
            initialvalue=5,
            minvalue=2,
            maxvalue=100,
        )

        if copy_count is None:
            return False

        unsaved_changes_command = getattr(
            self.event_editor,
            "has_unsaved_changes",
            None,
        )

        if (
            callable(unsaved_changes_command)
            and unsaved_changes_command()
        ):
            if not self.event_editor.save():
                return False

            selected_event = self.selected_event()

            if selected_event is None or selected_event.get("_draft_event"):
                return False

        if selected_event.get("_stored_event"):
            if self.event_controller is None:
                return False

            try:
                duplicated_events = self.event_controller.duplicate_events(
                    selected_event.get("record_id", ""),
                    copy_count,
                )
            except (KeyError, OSError, TypeError, ValueError) as error:
                self.show_editor_error(str(error))
                return False

            person_id = self.current_person_id()
            self.linked_events = (
                self.event_controller.events_for_person(person_id)
                if person_id
                else []
            )
            latest_duplicate = duplicated_events[-1]
            self.selected_event_id = latest_duplicate["record_id"]
            self.filter_events()

            if self.linked_events_changed_command is not None:
                self.linked_events_changed_command(latest_duplicate)

            return True

        for _ in range(copy_count):
            if not self.duplicate_event():
                return False

        return True

    def remove_event(self):
        selected_event = self.selected_event()

        if selected_event and selected_event.get("_draft_event"):
            self.cancel_editor()
            return

        if selected_event is None:
            return

        removable_automatic_death = bool(
            selected_event.get("automatic_source") == "death_date"
            and self.death_event_delete_command is not None
        )

        if (
            selected_event.get("automatic_source")
            and not removable_automatic_death
        ):
            return

        event_id = str(selected_event.get("event_id", "") or "")

        if self.remove_armed_event_id != event_id:
            self.remove_armed_event_id = event_id
            self.remove_button.set_text("Confirm remove")
            self.show_editor_error(
                "Click Confirm remove again to delete this event."
            )
            return

        deleted_event = None
        timeline_changed = False

        if removable_automatic_death:
            synchronized_events = self.death_event_delete_command(
                deepcopy(selected_event)
            )
            self.events = normalize_timeline_events(
                synchronized_events
            )
            timeline_changed = True
        elif selected_event.get("_stored_event"):
            if self.event_controller is None:
                return

            deleted_event = self.event_controller.delete_event(
                selected_event.get("record_id", "")
            )
            person_id = self.current_person_id()
            self.linked_events = (
                self.event_controller.events_for_person(person_id)
                if person_id
                else []
            )
        else:
            self.events = [
                event
                for event in self.events
                if event.get("event_id") != event_id
            ]
            timeline_changed = True

        self.selected_event_id = None
        if self.event_editor is not None:
            self.event_editor.clear(
                "Select an event to view it, or click Add event."
            )
        self.reset_remove_confirmation()

        if timeline_changed and not self.loading:
            self.change_command()

        if (
            deleted_event is not None
            and self.linked_events_changed_command is not None
        ):
            self.linked_events_changed_command(deleted_event)

        self.filter_events()

    def reset_remove_confirmation(self):
        self.remove_armed_event_id = ""
        self.remove_button.set_text("Remove")
