import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.dates import format_line_item_date
from mage_maker.sections.events.controller import (
    DeathEventReplacementRequired,
)
from mage_maker.sections.events.editor import (
    NEW_EVENT_DRAFT_ID,
    EventEditor,
)
from mage_maker.sections.events.types import event_type_label
from mage_maker.sections.items.link_dialog import RecordLinkDialog
from mage_maker.sections.items.links import (
    item_event_new_owner,
    item_event_link_type,
    item_event_link_type_label,
    item_event_link_type_options,
    normalize_item_event_link_types,
    normalize_item_event_new_owners,
)
from mage_maker.sections.timeline.page import (
    EVENT_COLORS,
    timeline_event_background,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
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
from mage_maker.ui.widgets import RoundedEntry, SoftButton


ITEM_EVENT_EDITOR_WIDTH = 500


class ItemTimelineView(tk.Frame):
    def __init__(
        self,
        parent,
        event_controller,
        status_command=None,
        events_changed_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.event_controller = event_controller
        self.status_command = status_command
        self.events_changed_command = events_changed_command
        self.current_item = {}
        self.events = []
        self.visible_events = []
        self.selected_event_id = ""
        self.draft_event_active = False
        self.remove_armed_event_id = ""
        self.search_value = tk.StringVar()
        self.heading_value = tk.StringVar(value="Item timeline")
        self.empty_value = tk.StringVar(
            value="Select an item to view its timeline."
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()
        self.build_workspace()
        self.search_value.trace_add("write", self.search_changed)
        self.refresh_events()

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=SURFACE, height=46)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            toolbar,
            textvariable=self.heading_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="w", padx=(2, 10))
        self.add_button = SoftButton(
            toolbar,
            text="Add event",
            command=self.start_add_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=96,
            height=34,
            font=app_font(9, "bold"),
        )
        self.add_button.grid(row=0, column=1, padx=(7, 0), pady=5)
        self.link_button = SoftButton(
            toolbar,
            text="Link existing",
            command=self.open_existing_event_links,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=34,
            font=app_font(9, "bold"),
        )
        self.link_button.grid(row=0, column=2, padx=(6, 0), pady=5)
        self.remove_button = SoftButton(
            toolbar,
            text="Remove event",
            command=self.remove_event,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=34,
            font=app_font(9, "bold"),
        )
        self.remove_button.grid(row=0, column=3, padx=(6, 0), pady=5)

    def build_workspace(self):
        workspace = tk.Frame(self, bg=SURFACE)
        workspace.grid(row=1, column=0, sticky="nsew")
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(0, weight=1, minsize=430)
        workspace.grid_columnconfigure(
            1,
            weight=0,
            minsize=ITEM_EVENT_EDITOR_WIDTH,
        )
        list_panel = tk.Frame(
            workspace,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        list_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        list_panel.grid_rowconfigure(2, weight=1)
        list_panel.grid_columnconfigure(0, weight=1)
        list_heading = tk.Label(
            list_panel,
            text="Events in date order",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        list_heading.grid(row=0, column=0, sticky="ew")
        self.search_entry = RoundedEntry(
            list_panel,
            textvariable=self.search_value,
            background=SURFACE_MUTED,
            height=34,
            font=app_font(9),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(8, 9),
        )
        list_frame = tk.Frame(
            list_panel,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.event_list = tk.Listbox(
            list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            font=app_font(9),
        )
        self.event_list.grid(row=0, column=0, sticky="nsew")
        self.event_list.bind("<<ListboxSelect>>", self.event_selected)
        self.event_list.bind(
            "<ButtonRelease-1>",
            self.event_selected,
            add="+",
        )
        scrollbar = tk.Scrollbar(list_frame, command=self.event_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.event_list.configure(yscrollcommand=scrollbar.set)
        self.empty_label = tk.Label(
            list_frame,
            textvariable=self.empty_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            padx=14,
            pady=14,
            wraplength=300,
        )
        self.empty_label.grid(row=0, column=0, sticky="nsew")
        editor_panel = tk.Frame(
            workspace,
            bg=SURFACE_MUTED,
            width=ITEM_EVENT_EDITOR_WIDTH,
        )
        editor_panel.grid(
            row=0,
            column=1,
            sticky="ns",
            padx=(7, 0),
        )
        editor_panel.grid_propagate(False)
        editor_panel.grid_rowconfigure(0, weight=1)
        editor_panel.grid_columnconfigure(0, weight=1)
        self.event_editor = EventEditor(
            editor_panel,
            self.event_controller,
            self.save_event,
            self.cancel_editor,
            context="item",
            background=SURFACE_MUTED,
        )
        self.event_editor.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

    def current_item_id(self):
        return str(
            self.current_item.get("record_id", "") or ""
        ).strip()

    def set_item(self, item):
        requested_item = deepcopy(item) if isinstance(item, dict) else {}
        requested_item_id = str(
            requested_item.get("record_id", "") or ""
        ).strip()
        current_item_id = self.current_item_id()

        if (
            requested_item_id != current_item_id
            and not self.confirm_unsaved_changes()
        ):
            return False

        self.current_item = requested_item

        if requested_item_id != current_item_id:
            self.selected_event_id = ""
            self.draft_event_active = False
            self.reset_remove_confirmation()

        item_name = str(
            self.current_item.get("name", "") or "Item"
        ).strip()
        self.heading_value.set(
            f"Timeline · {item_name}"
            if requested_item_id
            else "Item timeline"
        )
        self.refresh_events(
            reload_editor=(requested_item_id != current_item_id)
        )
        return True

    def confirm_unsaved_changes(self):
        if not hasattr(self, "event_editor"):
            return True

        if not self.event_editor.has_unsaved_changes():
            return True

        choice = messagebox.askyesnocancel(
            "Unsaved event changes",
            "Save this event before continuing?",
            parent=self,
            icon="warning",
            default="yes",
        )

        if choice is None:
            return False

        if choice:
            return bool(self.event_editor.save())

        self.cancel_editor()
        return True

    def search_changed(self, *arguments):
        self.refresh_event_list(reload_editor=False)

    def refresh_events(self, reload_editor=True):
        item_id = self.current_item_id()
        self.events = (
            self.event_controller.events_for_item(item_id)
            if self.event_controller is not None and item_id
            else []
        )
        available_event_ids = {
            str(event.get("record_id", "") or "").strip()
            for event in self.events
        }

        if self.draft_event_active:
            available_event_ids.add(NEW_EVENT_DRAFT_ID)

        if self.selected_event_id not in available_event_ids:
            self.selected_event_id = ""

        self.refresh_event_list(reload_editor=reload_editor)

    def refresh_event_list(self, reload_editor=True):
        query = self.search_value.get().strip().casefold()
        self.visible_events = []

        if self.draft_event_active:
            self.visible_events.append(
                {
                    "record_id": NEW_EVENT_DRAFT_ID,
                    "title": "New event",
                    "event_type": "item_event",
                    "date": "",
                    "_draft_event": True,
                }
            )

        for event in self.events:
            summary_text = " ".join(
                (
                    format_line_item_date(
                        event.get("date", ""),
                        unknown="Date unknown",
                    ),
                    str(event.get("time", "") or ""),
                    event_type_label(event),
                    str(event.get("title", "") or ""),
                    str(event.get("description", "") or ""),
                )
            ).casefold()

            if query and query not in summary_text:
                continue

            self.visible_events.append(event)

        self.event_list.delete(0, "end")

        for index, event in enumerate(self.visible_events):
            if event.get("_draft_event"):
                row_text = "New event (unsaved)"
                row_background = PRIMARY_SOFT
            else:
                date_text = format_line_item_date(
                    event.get("date", ""),
                    unknown="Date unknown",
                )
                time_text = str(event.get("time", "") or "").strip()

                if time_text:
                    date_text = f"{date_text} {time_text}"

                link_type = item_event_link_type(
                    event,
                    self.current_item_id(),
                )
                link_type_text = item_event_link_type_label(
                    link_type,
                    item_event_new_owner(
                        event,
                        self.current_item_id(),
                    ),
                )
                title_text = str(
                    event.get("title", "") or "Event"
                ).strip()
                row_text = (
                    f"  {date_text}  ·  {link_type_text}  ·  {title_text}"
                )
                row_background = (
                    EVENT_COLORS["born"]
                    if link_type == "crafted"
                    else (
                        EVENT_COLORS["died"]
                        if link_type == "destroyed"
                        else timeline_event_background(event)
                    )
                )

                if row_background == FIELD_BACKGROUND and index % 2:
                    row_background = LIST_ALTERNATE

            self.event_list.insert("end", row_text)
            self.event_list.itemconfigure(index, background=row_background)

            if event.get("record_id") == self.selected_event_id:
                self.event_list.selection_set(index)
                self.event_list.see(index)

        has_item = bool(self.current_item_id())
        has_events = bool(self.visible_events)
        self.add_button.set_enabled(
            has_item and self.event_controller is not None
        )
        self.link_button.set_enabled(
            has_item and self.event_controller is not None
        )
        self.remove_button.set_enabled(bool(self.selected_event_id))

        if has_events:
            self.empty_label.grid_remove()
            self.event_list.grid()
        else:
            self.event_list.grid_remove()
            self.empty_value.set(
                "No events match this search."
                if has_item and query
                else (
                    "No events are linked to this item. Click Add event to create one."
                    if has_item
                    else "Select an item to view its timeline."
                )
            )
            self.empty_label.grid()

        if not reload_editor or self.event_editor.saving:
            return

        self.load_selected_event()

    def event_selected(self, event=None):
        selection = self.event_list.curselection()

        if not selection or selection[0] >= len(self.visible_events):
            return

        requested_event_id = str(
            self.visible_events[selection[0]].get("record_id", "") or ""
        ).strip()

        if requested_event_id == self.selected_event_id:
            return

        if not self.confirm_unsaved_changes():
            self.restore_selected_event()
            return

        self.selected_event_id = requested_event_id
        self.reset_remove_confirmation()
        self.load_selected_event()

    def restore_selected_event(self):
        self.event_list.selection_clear(0, "end")

        for index, event in enumerate(self.visible_events):
            if event.get("record_id") != self.selected_event_id:
                continue

            self.event_list.selection_set(index)
            self.event_list.see(index)
            break

    def selected_event(self):
        if self.selected_event_id == NEW_EVENT_DRAFT_ID:
            return {
                "record_id": NEW_EVENT_DRAFT_ID,
                "_draft_event": True,
            }

        return next(
            (
                deepcopy(event)
                for event in self.events
                if str(event.get("record_id", "") or "").strip()
                == self.selected_event_id
            ),
            None,
        )

    def load_selected_event(self):
        comparison_command = getattr(
            self.event_editor,
            "set_comparison_events",
            None,
        )

        if callable(comparison_command):
            comparison_command(self.events)

        item_id = self.current_item_id()
        selected_event = self.selected_event()

        if not item_id or selected_event is None:
            self.event_editor.clear(
                "Select an event to view it, or click Add event."
            )
            self.remove_button.set_enabled(False)
            return

        if selected_event.get("_draft_event"):
            self.event_editor.start_new(
                context="item",
                default_item_ids=(item_id,),
                locked_item_ids=(item_id,),
                default_item_link_types={item_id: "crafted"},
            )
            self.remove_button.set_enabled(True)
            return

        stored_event = selected_event

        if stored_event is None:
            self.event_editor.clear("This event no longer exists.")
            self.remove_button.set_enabled(False)
            return

        self.event_editor.load_event(
            stored_event,
            storage_kind="shared",
            context="item",
            item_ids=(item_id,),
            locked_item_ids=(item_id,),
            read_only=False,
            explanation=(
                "This is one shared event. Changes appear on every linked timeline."
            ),
        )
        self.remove_button.set_enabled(True)

    def start_add_event(self):
        item_id = self.current_item_id()

        if self.event_controller is None or not item_id:
            self.event_editor.show_error(
                "Select and save an item before adding an event."
            )
            return False

        if not self.confirm_unsaved_changes():
            return False

        self.draft_event_active = True
        self.selected_event_id = NEW_EVENT_DRAFT_ID
        self.reset_remove_confirmation()
        self.refresh_event_list(reload_editor=False)
        self.restore_selected_event()
        self.event_editor.start_new(
            context="item",
            default_item_ids=(item_id,),
            locked_item_ids=(item_id,),
            default_item_link_types={item_id: "crafted"},
        )
        return True

    def save_event(self, values, storage_kind, original_event):
        item_id = self.current_item_id()

        if self.event_controller is None or not item_id:
            raise ValueError("Select an item before saving its event.")

        prepared_values = deepcopy(values)
        prepared_values["item_ids"] = list(
            dict.fromkeys(
                [
                    *prepared_values.get("item_ids", []),
                    item_id,
                ]
            )
        )
        retained_item_link_types = dict(
            original_event.get("item_link_types", {}) or {}
        )
        retained_item_link_types.update(
            dict(prepared_values.get("item_link_types", {}) or {})
        )
        prepared_values["item_link_types"] = (
            normalize_item_event_link_types(
                retained_item_link_types,
                prepared_values["item_ids"],
                prepared_values.get("event_type", ""),
            )
        )
        retained_item_new_owners = dict(
            original_event.get("item_new_owners", {}) or {}
        )
        retained_item_new_owners.update(
            dict(prepared_values.get("item_new_owners", {}) or {})
        )
        prepared_values["item_new_owners"] = (
            normalize_item_event_new_owners(
                retained_item_new_owners,
                prepared_values["item_ids"],
                prepared_values["item_link_types"],
            )
        )
        record_id = str(
            original_event.get("record_id", "") or ""
        ).strip()

        if record_id == NEW_EVENT_DRAFT_ID:
            record_id = ""

        try:
            saved_event = (
                self.event_controller.update_event(
                    record_id,
                    prepared_values,
                )
                if record_id
                else self.event_controller.create_event(prepared_values)
            )
        except DeathEventReplacementRequired as error:
            replace_existing = messagebox.askyesno(
                "Replace existing Death event?",
                (
                    f"{error}\n\nSaving this event will replace the existing "
                    "Death event. Continue?"
                ),
                parent=self,
                icon="warning",
                default="no",
            )

            if not replace_existing:
                return False

            saved_event = (
                self.event_controller.update_event(
                    record_id,
                    prepared_values,
                    replace_existing_death=True,
                )
                if record_id
                else self.event_controller.create_event(
                    prepared_values,
                    replace_existing_death=True,
                )
            )

        self.draft_event_active = False
        self.selected_event_id = saved_event["record_id"]
        self.reset_remove_confirmation()
        self.refresh_events(reload_editor=False)
        self.load_selected_event()
        self.notify(f"Saved event for {self.current_item.get('name', 'item')}")

        if callable(self.events_changed_command):
            self.events_changed_command()

        return saved_event

    def cancel_editor(self):
        if self.draft_event_active:
            self.draft_event_active = False
            self.selected_event_id = ""
            self.refresh_events(reload_editor=False)
            self.event_editor.clear(
                "Select an event to view it, or click Add event."
            )
            return True

        self.load_selected_event()
        return True

    def remove_event(self):
        selected_event = self.selected_event()

        if selected_event is None:
            return False

        if selected_event.get("_draft_event"):
            self.cancel_editor()
            return True

        event_id = str(selected_event.get("record_id", "") or "").strip()

        if self.remove_armed_event_id != event_id:
            self.remove_armed_event_id = event_id
            self.remove_button.set_text("Confirm remove")
            self.event_editor.show_error(
                "Click Confirm remove again to delete this shared event everywhere."
            )
            return False

        try:
            deleted_event = self.event_controller.delete_event(event_id)
        except (KeyError, TypeError, ValueError) as error:
            self.event_editor.show_error(str(error))
            self.reset_remove_confirmation()
            return False

        self.selected_event_id = ""
        self.reset_remove_confirmation()
        self.refresh_events()
        self.notify(
            f"Deleted event {deleted_event.get('title', 'Event')}"
        )

        if callable(self.events_changed_command):
            self.events_changed_command()

        return True

    def reset_remove_confirmation(self):
        self.remove_armed_event_id = ""

        if hasattr(self, "remove_button"):
            self.remove_button.set_text("Remove event")

    def open_existing_event_links(self):
        item_id = self.current_item_id()

        if self.event_controller is None or not item_id:
            return False

        if not self.confirm_unsaved_changes():
            return False

        RecordLinkDialog(
            self,
            "Link Existing Events to Item",
            f"Link existing events to {self.current_item.get('name', 'item')}",
            (
                "The first 50 recent events are shown. Search or choose an event "
                "type to narrow the results; linked events remain selected."
            ),
            self.event_controller.linkable_event_options(),
            [event["record_id"] for event in self.events],
            self.save_existing_event_links,
            "Save event links",
            group_label="Event type",
            search_label="Search title, date, person, or location",
            initial_limit=50,
            result_limit=200,
            link_type_options=item_event_link_type_options(),
            selected_link_types={
                event["record_id"]: item_event_link_type(event, item_id)
                for event in self.events
            },
            link_type_default="passed_down",
            new_owner_options=self.event_controller.people_options(),
            recent_new_owner_options=(
                self.event_controller.recent_people_options()
                if hasattr(
                    self.event_controller,
                    "recent_people_options",
                )
                else ()
            ),
            selected_new_owners={
                event["record_id"]: item_event_new_owner(event, item_id)
                for event in self.events
            },
            mage_groups=(
                self.event_controller.mage_groups()
                if hasattr(self.event_controller, "mage_groups")
                else ()
            ),
        )
        return True

    def save_existing_event_links(
        self,
        event_ids,
        event_link_types=None,
        event_new_owners=None,
    ):
        item_id = self.current_item_id()

        if self.event_controller is None or not item_id:
            raise ValueError("Select an item before linking events.")

        linked_events = self.event_controller.set_item_event_links(
            item_id,
            event_ids,
            event_link_types,
            event_new_owners,
        )

        if self.selected_event_id not in {
            event["record_id"] for event in linked_events
        }:
            self.selected_event_id = ""

        self.refresh_events()
        self.notify(
            f"Linked {len(linked_events)} event"
            + ("" if len(linked_events) == 1 else "s")
            + f" to {self.current_item.get('name', 'item')}"
        )

        if callable(self.events_changed_command):
            self.events_changed_command()

        return linked_events

    def notify(self, message):
        if callable(self.status_command):
            self.status_command(message)
