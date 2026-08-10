import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.dates import format_line_item_date
from mage_maker.sections.events.editor import (
    NEW_EVENT_DRAFT_ID,
    EventEditor,
)
from mage_maker.sections.events.models import event_time_sort_key
from mage_maker.sections.events.types import (
    event_type_label,
    event_visible_outside_person,
)
from mage_maker.sections.timeline.events import job_timeline_summary
from mage_maker.ui.theme import (
    BORDER_SOFT,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
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
from mage_maker.ui.widgets import SoftButton


def period_event_date_key(value):
    date_text = str(value or "").strip()

    if not date_text:
        return 100000, 13, 32

    negative = date_text.startswith("-")
    body = date_text[1:] if negative else date_text
    parts = body.split("-")

    try:
        year = int(parts[0])
    except (TypeError, ValueError, IndexError):
        return 100000, 13, 32

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


def period_event_sort_key(event):
    return (
        period_event_date_key(event.get("date")),
        event_time_sort_key(event.get("time")),
        event_type_label(event).casefold(),
        str(event.get("title", "") or "").casefold(),
        str(event.get("event_id", "") or ""),
    )


def period_event_display_text(event):
    date_text = format_line_item_date(event.get("date"))
    time_text = str(event.get("time", "") or "").strip()

    if time_text:
        date_text = f"{date_text} {time_text}"

    title = str(event.get("title", "") or "Event")
    event_type = str(
        event.get("event_type", "") or ""
    ).strip().casefold()

    if event_type in ("started_job", "received_raise"):
        event_summary = job_timeline_summary(event)
    elif event_type == "founding":
        event_summary = title
    else:
        event_summary = f"{event_type_label(event)}  ·  {title}"

    return f"{date_text}  ·  {event_summary}"


class PeriodEventsView(tk.Frame):
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
        self.draft_event = None
        self.selected_event_id = ""
        self.event_editor_visible = False
        self.remove_armed_event_id = ""
        self.title_value = tk.StringVar(value="Events (0)")
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
            fill=PRIMARY_SOFT,
            hover_fill=PRIMARY_HOVER,
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
            width=118,
            height=36,
        )
        self.remove_button.grid(row=0, column=3, padx=(6, 0), pady=5)

    def build_workspace(self):
        self.workspace = tk.Frame(self, bg=SURFACE)
        self.workspace.grid(row=1, column=0, sticky="nsew")
        self.workspace.grid_rowconfigure(0, weight=1)
        self.workspace.grid_columnconfigure(0, weight=5, uniform="events")
        self.workspace.grid_columnconfigure(1, weight=4, uniform="events")
        self.list_panel = tk.Frame(
            self.workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=11,
        )
        self.list_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        self.list_panel.grid_rowconfigure(1, weight=1)
        self.list_panel.grid_columnconfigure(0, weight=1)
        hint = tk.Label(
            self.list_panel,
            text=(
                "Events in this period. Individual events appear only for "
                "people marked as famous."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        hint.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        list_frame = tk.Frame(self.list_panel, bg=SURFACE_MUTED)
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
        self.event_editor = EventEditor(
            self.workspace,
            self.event_controller,
            self.save_event_editor,
            self.cancel_event_editor,
            context="period",
            background=SURFACE_MUTED,
        )
        self.event_editor.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.hide_event_editor()
        self.update_button_state()

    def show_event_editor(self):
        if self.event_editor_visible:
            return

        self.workspace.grid_columnconfigure(
            0,
            weight=5,
            uniform="events",
        )
        self.workspace.grid_columnconfigure(
            1,
            weight=4,
            uniform="events",
        )
        self.list_panel.grid(
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

    def set_period(self, period):
        self.draft_event = None
        self.period = deepcopy(period) if isinstance(period, dict) else None
        self.selected_event_id = ""
        self.reset_remove_confirmation()
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
        stored_events = self.event_controller.events_for_period(
            self.period["name"],
            start_year,
            end_year,
        )
        generated_events = self.location_controller.events_for_period(
            start_year,
            end_year,
            "",
            famous_people_only=True,
        )

        for event in stored_events:
            if not event_visible_outside_person(event.get("event_type")):
                continue

            if (
                self.event_controller.event_is_individual(event)
                and not self.event_controller.event_has_famous_person(event)
            ):
                continue

            row = deepcopy(event)
            row["event_kind"] = "global"
            row["event_id"] = event["record_id"]
            row["association_labels"] = (
                self.event_controller.association_labels(event)
            )
            self.events.append(row)

        for event in generated_events:
            if not event_visible_outside_person(event.get("event_type")):
                continue

            row = deepcopy(event)
            row["event_id"] = str(event.get("event_id", "") or "")
            row["association_labels"] = self.generated_association_labels(row)
            self.events.append(row)

        self.events.sort(key=period_event_sort_key)

        if self.draft_event is not None:
            self.events.append(deepcopy(self.draft_event))

        self.render_events()

    def generated_association_labels(self, event):
        person_ids = [
            str(person_id or "").strip()
            for person_id in event.get("person_ids", [])
            if str(person_id or "").strip()
        ]

        if not person_ids and event.get("related_person_id"):
            person_ids = [str(event.get("related_person_id"))]

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
            "people": [
                people_by_id.get(person_id, "Missing person")
                for person_id in person_ids
            ],
            "periods": [self.period["name"]] if self.period else [],
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
            if event.get("_draft_event"):
                self.listbox.insert("end", "New event (unsaved)")
                self.listbox.itemconfigure(
                    index,
                    background=PRIMARY_SOFT,
                )

                if event.get("event_id") == self.selected_event_id:
                    self.listbox.selection_set(index)
                    self.listbox.see(index)

                continue

            self.listbox.insert(
                "end",
                period_event_display_text(event),
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

        self.update_editor()
        self.update_button_state()

    def event_selected(self, event=None):
        selection = self.listbox.curselection()

        if not selection:
            return

        requested_event_id = self.events[selection[0]]["event_id"]

        if (
            requested_event_id != self.selected_event_id
            and not self.confirm_unsaved_event_changes()
        ):
            self.restore_selected_event_row()
            return "break"

        self.selected_event_id = requested_event_id
        self.reset_remove_confirmation()
        self.update_editor()
        self.update_button_state()

    def restore_selected_event_row(self):
        self.listbox.selection_clear(0, "end")

        for index, event in enumerate(self.events):
            if str(event.get("event_id", "") or "") != str(
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
            icon="warning",
            default="yes",
        )

        if save_choice is None:
            return False

        if save_choice:
            return bool(self.event_editor.save())

        self.event_editor.cancel()
        return True

    def selected_event(self):
        for event in self.events:
            if event.get("event_id") == self.selected_event_id:
                return event

        selection = self.listbox.curselection()

        if selection and selection[0] < len(self.events):
            selected_event = self.events[selection[0]]
            self.selected_event_id = selected_event.get("event_id", "")
            return selected_event

        return None

    def update_editor(self):
        comparison_command = getattr(
            self.event_editor,
            "set_comparison_events",
            None,
        )

        if callable(comparison_command):
            comparison_command(self.events)

        event = self.selected_event()

        if event is None:
            if self.event_editor.is_new_event():
                self.show_event_editor()
                self.event_editor.ensure_new_event_editable()
                return

            self.event_editor.clear(
                "Select an event to view it, or click Add event."
            )
            self.hide_event_editor()
            return

        if event.get("_draft_event"):
            self.show_event_editor()

            if not self.event_editor.is_new_event():
                self.event_editor.start_new(
                    context="period",
                    minimum_year=self.period["calculation_start_year"],
                    maximum_year=self.period["calculation_end_year"],
                )

            self.event_editor.ensure_new_event_editable()
            return

        self.show_event_editor()
        labels = event.get("association_labels", {})

        if event.get("event_kind") == "global":
            stored_event = self.event_controller.get_event(
                event.get("record_id", "")
            )

            if stored_event is None:
                self.event_editor.clear("This event no longer exists.")
                return

            self.event_editor.load_event(
                stored_event,
                storage_kind="shared",
                context="period",
                read_only=False,
                minimum_year=self.period["calculation_start_year"],
                maximum_year=self.period["calculation_end_year"],
            )
            return

        person_ids = list(event.get("person_ids", []))

        if not person_ids and event.get("related_person_id"):
            person_ids = [event.get("related_person_id")]

        location_ids = []
        origin_location_id = str(
            event.get("origin_location_id", "") or ""
        )

        if origin_location_id:
            location_ids.append(origin_location_id)

        self.event_editor.load_event(
            event,
            storage_kind=(
                "timeline"
                if event.get("event_kind") == "mage"
                else "location"
            ),
            context=(
                "person"
                if event.get("event_kind") == "mage"
                else "location"
            ),
            person_ids=person_ids,
            location_ids=location_ids,
            read_only=True,
            explanation=(
                "This individual event is shown because the person is marked famous."
                if event.get("event_kind") == "mage"
                else "This event is stored on its source location."
            ),
            minimum_year=self.period["calculation_start_year"],
            maximum_year=self.period["calculation_end_year"],
        )

    def add_event(self):
        if self.period is None:
            self.status_command("Select a period first.")
            return

        if not self.confirm_unsaved_event_changes():
            return False

        self.draft_event = {
            "event_id": NEW_EVENT_DRAFT_ID,
            "event_type": "other",
            "title": "New event",
            "date": "",
            "description": "",
            "event_kind": "global",
            "_draft_event": True,
        }
        self.selected_event_id = NEW_EVENT_DRAFT_ID
        self.reset_remove_confirmation()
        self.refresh()
        self.event_editor.ensure_new_event_editable()

    def edit_event(self, event=None):
        selected = self.selected_event()

        if selected is None:
            return

        if selected.get("_draft_event"):
            self.show_event_editor()
            self.event_editor.ensure_new_event_editable()
            return

        if selected.get("event_kind") != "global":
            return

        self.update_editor()
        self.event_editor.begin_edit()
        self.event_editor.canvas.yview_moveto(0)

    def save_event_editor(self, values, storage_kind, original_event):
        if storage_kind != "shared":
            raise ValueError(
                "This generated event must be edited at its source record."
            )

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

        self.draft_event = None
        self.selected_event_id = saved["record_id"]
        self.changed_command(saved)
        return saved

    def cancel_event_editor(self):
        if (
            self.draft_event is not None
            or self.event_editor.is_new_event()
        ):
            self.draft_event = None
            self.selected_event_id = ""
            self.listbox.selection_clear(0, "end")
            self.refresh()
            return

        self.update_editor()

    def remove_event(self):
        selected = self.selected_event()

        if selected and selected.get("_draft_event"):
            self.cancel_event_editor()
            return

        if selected is None or selected.get("event_kind") != "global":
            self.event_editor.show_error(
                "This generated event must be removed at its source record."
            )
            return

        event_id = str(selected.get("event_id", "") or "")

        if self.remove_armed_event_id != event_id:
            self.remove_armed_event_id = event_id
            self.remove_button.set_text("Confirm remove")
            self.event_editor.show_error(
                "Click Confirm remove again to delete this event."
            )
            return

        deleted = self.event_controller.delete_event(
            selected["record_id"]
        )
        self.selected_event_id = ""
        self.reset_remove_confirmation()
        self.refresh()
        self.status_command(
            f"Removed event {deleted.get('title', 'Event')}"
        )
        self.changed_command(None)

    def update_button_state(self):
        selected = self.selected_event()
        self.edit_button.set_enabled(
            bool(
                selected
                and selected.get("event_kind") == "global"
                and not selected.get("_draft_event")
            )
        )
        self.remove_button.set_enabled(
            bool(
                selected
                and selected.get("event_kind") == "global"
                and not selected.get("_draft_event")
            )
        )

    def reset_remove_confirmation(self):
        self.remove_armed_event_id = ""
        self.remove_button.set_text("Remove")

    def select_event(self, record_id):
        requested_id = str(record_id or "")

        if (
            requested_id != str(self.selected_event_id or "")
            and not self.confirm_unsaved_event_changes()
        ):
            self.restore_selected_event_row()
            return False

        for index, event in enumerate(self.events):
            if event.get("event_id") != requested_id:
                continue

            self.selected_event_id = requested_id
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(index)
            self.listbox.see(index)
            self.update_editor()
            self.update_button_state()
            return True

        return False
