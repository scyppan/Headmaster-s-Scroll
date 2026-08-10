import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.organizations.controller import (
    ORGANIZATION_EVENT_FOUNDING,
    new_organization_event,
    normalize_organization_event,
)
from mage_maker.sections.events.dialog import (
    EventPersonPickerDialog,
)
from mage_maker.sections.events.eminence_picker import (
    EventEminencePicker,
)
from mage_maker.sections.events.editor import (
    MurderAdditionalPeopleDialog,
)
from mage_maker.sections.items.link_dialog import RecordLinkDialog
from mage_maker.sections.items.links import (
    ITEM_EVENT_NEW_OWNER_LINK_TYPES,
    item_event_link_type_label,
    item_event_link_type_options,
    normalize_item_event_link_types,
    normalize_item_event_new_owners,
)
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    split_world_event_date,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
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
    RoundedText,
    SoftButton,
)


class OrganizationEventDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        save_command,
        event=None,
        event_controller=None,
    ):
        super().__init__(parent)
        normalized_event = (
            normalize_organization_event(event)
            if isinstance(event, dict)
            else None
        )
        self.save_command = save_command
        self.event_controller = event_controller
        self.event = normalized_event
        self.is_founding = bool(
            normalized_event
            and normalized_event["event_type"]
            == ORGANIZATION_EVENT_FOUNDING
        )
        self.title_value = tk.StringVar(
            value=(
                normalized_event["title"]
                if normalized_event
                else ""
            )
        )
        event_year, event_month, event_day = split_world_event_date(
            normalized_event.get("date", "")
            if normalized_event
            else ""
        )
        self.year_value = tk.StringVar(
            value=event_year
        )
        self.month_value = tk.StringVar(value=event_month)
        self.day_value = tk.StringVar(value=event_day)
        self.time_value = tk.StringVar(
            value=(
                str(normalized_event.get("time", "") or "").strip()
                if normalized_event
                else ""
            )
        )
        self.selected_person_ids = list(
            normalized_event.get("person_ids", [])
            if normalized_event
            else []
        )
        self.selected_witness_person_ids = list(
            normalized_event.get("witness_person_ids", [])
            if normalized_event
            else []
        )
        self.selected_affected_person_ids = list(
            normalized_event.get("affected_person_ids", [])
            if normalized_event
            else []
        )
        self.selected_item_ids = list(
            normalized_event.get("item_ids", [])
            if normalized_event
            else []
        )
        self.selected_item_link_types = normalize_item_event_link_types(
            (
                normalized_event.get("item_link_types")
                if normalized_event
                else None
            ),
            self.selected_item_ids,
            (
                normalized_event.get("event_type", "event")
                if normalized_event
                else "event"
            ),
        )
        self.selected_item_new_owners = normalize_item_event_new_owners(
            (
                normalized_event.get("item_new_owners")
                if normalized_event
                else None
            ),
            self.selected_item_ids,
            self.selected_item_link_types,
        )
        self.items_summary_value = tk.StringVar()
        self.selected_eminence_person_ids = list(
            normalized_event.get("eminence_person_ids", [])
            if normalized_event
            else []
        )
        self.selected_eminence_skills = dict(
            normalized_event.get("eminence_skills", {})
            if normalized_event
            else {}
        )
        self.title(
            "Founding event"
            if self.is_founding
            else "Organization event"
        )
        self.configure(bg=APP_BACKGROUND)
        self.geometry("700x700")
        self.minsize(620, 600)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.year_value.trace_add("write", self.update_time_visibility)
        self.month_value.trace_add("write", self.update_time_visibility)
        self.day_value.trace_add("write", self.update_time_visibility)
        self.time_value.trace_add("write", self.update_time_visibility)
        self.update_time_visibility()
        self.grab_set()
        self.after_idle(self.focus_first_field)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=(
                "Founding event"
                if self.is_founding
                else "Organization event"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)

        body = tk.Frame(
            self,
            bg=SURFACE,
            padx=20,
            pady=18,
        )
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(4, weight=1)
        body.grid_columnconfigure(0, weight=1)

        title_label = tk.Label(
            body,
            text="Title",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        title_label.grid(row=0, column=0, sticky="ew")
        self.title_entry = RoundedEntry(
            body,
            textvariable=self.title_value,
            background=SURFACE,
            width=390,
            height=38,
            font=app_font(10),
        )
        self.title_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(5, 12),
        )
        self.title_entry.entry.configure(
            state="disabled" if self.is_founding else "normal"
        )

        date_frame = tk.Frame(body, bg=SURFACE)
        self.date_frame = date_frame
        date_frame.grid(
            row=0,
            column=1,
            rowspan=2,
            sticky="e",
            padx=(14, 0),
            pady=(0, 12),
        )
        date_frame.grid_columnconfigure((0, 1, 2, 3), weight=1)

        for column, label_text in enumerate(
            ("Year", "Month", "Day", "Time (HHMM)")
        ):
            date_label = tk.Label(
                date_frame,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
            )
            date_label.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 5) if column < 3 else 0,
            )

            if column == 3:
                self.time_label = date_label

        self.year_entry = RoundedEntry(
            date_frame,
            textvariable=self.year_value,
            background=SURFACE,
            width=92,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.year_entry.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 5),
            pady=(5, 0),
        )
        self.month_entry = RoundedEntry(
            date_frame,
            textvariable=self.month_value,
            background=SURFACE,
            width=64,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.month_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(0, 5),
            pady=(5, 0),
        )
        self.day_entry = RoundedEntry(
            date_frame,
            textvariable=self.day_value,
            background=SURFACE,
            width=64,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.day_entry.grid(
            row=1,
            column=2,
            sticky="ew",
            pady=(5, 0),
        )
        self.time_entry = RoundedEntry(
            date_frame,
            textvariable=self.time_value,
            background=SURFACE,
            width=88,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.time_entry.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(5, 0),
            pady=(5, 0),
        )
        self.time_label.grid_remove()
        self.time_entry.grid_remove()
        calendar_notice = CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=620,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        )
        calendar_notice.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(0, 8),
        )

        description_label = tk.Label(
            body,
            text="Description",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        description_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        self.description_control = RoundedText(
            body,
            background=SURFACE,
            height=8,
        )
        self.description_control.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

        if self.event:
            self.description_control.text.insert(
                "1.0",
                self.event["description"],
            )

        people_frame = tk.Frame(body, bg=SURFACE)
        people_frame.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(14, 0),
        )
        people_frame.grid_columnconfigure(0, weight=1)
        self.people_summary_value = tk.StringVar()
        people_label = tk.Label(
            people_frame,
            textvariable=self.people_summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        people_label.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        self.people_list = tk.Listbox(
            people_frame,
            height=3,
            bg=SURFACE,
            fg=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
        )
        self.people_list.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        add_person_button = SoftButton(
            people_frame,
            text="Select people",
            command=self.open_person_picker,
            background=SURFACE,
            width=104,
            height=32,
            font=app_font(9, "bold"),
        )
        add_person_button.grid(
            row=1,
            column=1,
            padx=(8, 0),
        )
        remove_person_button = SoftButton(
            people_frame,
            text="Remove",
            command=self.remove_selected_person,
            background=SURFACE,
            width=82,
            height=32,
            font=app_font(9, "bold"),
        )
        remove_person_button.grid(
            row=1,
            column=2,
            padx=(6, 0),
        )
        self.refresh_people_list()
        ancillary_people_frame = tk.Frame(
            body,
            bg=SURFACE,
            highlightbackground=TEXT_MUTED,
            highlightthickness=1,
            padx=7,
            pady=5,
        )
        ancillary_people_frame.grid(
            row=6,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        ancillary_people_frame.grid_columnconfigure(0, weight=1)
        self.witnesses_summary_value = tk.StringVar()
        self.affected_summary_value = tk.StringVar()
        witnesses_summary = tk.Label(
            ancillary_people_frame,
            textvariable=self.witnesses_summary_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(8),
            anchor="w",
        )
        witnesses_summary.grid(row=0, column=0, sticky="ew")
        affected_summary = tk.Label(
            ancillary_people_frame,
            textvariable=self.affected_summary_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(8),
            anchor="w",
        )
        affected_summary.grid(row=1, column=0, sticky="ew")
        ancillary_people_button = SoftButton(
            ancillary_people_frame,
            text="Edit witnesses / affected by",
            command=self.open_ancillary_people_dialog,
            background=SURFACE,
            width=176,
            height=28,
            font=app_font(8, "bold"),
        )
        ancillary_people_button.grid(
            row=0,
            column=1,
            rowspan=2,
            padx=(8, 0),
        )
        self.refresh_ancillary_people_summary()
        self.eminence_picker = EventEminencePicker(
            body,
            self.event_controller,
            SURFACE,
        )
        self.eminence_picker.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(8, 0),
        )
        self.eminence_picker.set_values(
            self.selected_linked_person_ids(),
            self.selected_eminence_person_ids,
            self.selected_eminence_skills,
            (
                self.event.get("record_id", "")
                if self.event
                else "new-organization-event"
            ),
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
        items_summary = tk.Label(
            footer,
            textvariable=self.items_summary_value,
            bg=APP_BACKGROUND,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="e",
        )
        items_summary.grid(row=0, column=0, sticky="e", padx=(0, 8))
        self.link_items_button = SoftButton(
            footer,
            text="Link items",
            command=self.open_item_links,
            background=APP_BACKGROUND,
            width=96,
            height=36,
        )
        self.link_items_button.grid(row=0, column=1, padx=(0, 7))
        self.link_items_button.set_enabled(self.event_controller is not None)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=92,
            height=36,
        )
        cancel_button.grid(row=0, column=2, padx=(0, 7))
        save_button = SoftButton(
            footer,
            text="Save event",
            command=self.save_event,
            background=APP_BACKGROUND,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=36,
        )
        save_button.grid(row=0, column=3)
        self.refresh_items_summary()

    def focus_first_field(self):
        if self.is_founding:
            self.year_entry.entry.focus_set()
            self.year_entry.entry.selection_range(0, "end")
            return

        self.title_entry.entry.focus_set()
        self.title_entry.entry.selection_range(0, "end")

    def close_dialog(self, event=None):
        self.destroy()

    def people_options(self):
        if self.event_controller is None:
            return []

        return self.event_controller.people_options()

    def refresh_people_list(self):
        if not hasattr(self, "people_list"):
            return

        labels_by_id = {
            option["value"]: option["label"]
            for option in self.people_options()
        }
        self.people_list.delete(0, "end")

        for person_id in self.selected_person_ids:
            self.people_list.insert(
                "end",
                labels_by_id.get(
                    person_id,
                    "Unknown person",
                ),
            )

        selected_count = len(self.selected_person_ids)
        self.people_summary_value.set(
            (
                "People linked to this event · 1 selected"
                if selected_count == 1
                else (
                    "People linked to this event · "
                    f"{selected_count} selected"
                )
            )
        )

    def selected_linked_person_ids(self):
        return list(
            dict.fromkeys(
                [
                    *self.selected_person_ids,
                    *self.selected_witness_person_ids,
                    *self.selected_affected_person_ids,
                ]
            )
        )

    def item_options(self):
        if self.event_controller is None:
            return []

        return self.event_controller.item_options()

    def refresh_items_summary(self):
        linked_item_count = len(self.selected_item_ids)

        if linked_item_count == 0:
            self.items_summary_value.set("Items: None")
        elif linked_item_count == 1:
            item_id = self.selected_item_ids[0]
            self.items_summary_value.set(
                "Items: 1 linked · "
                + item_event_link_type_label(
                    self.selected_item_link_types.get(item_id, ""),
                    self.selected_item_new_owners.get(item_id),
                )
            )
        else:
            self.items_summary_value.set(
                f"Items: {linked_item_count} linked"
            )

    def open_item_links(self):
        if self.event_controller is None:
            return False

        RecordLinkDialog(
            self,
            "Link Items to Event",
            "Link items to this event",
            (
                "Choose each item connected to this event, then select why it "
                "is linked and what the event does to it."
            ),
            self.item_options(),
            self.selected_item_ids,
            self.item_links_chosen,
            "Save item links",
            link_type_options=item_event_link_type_options(),
            selected_link_types=self.selected_item_link_types,
            link_type_default="passed_down",
            new_owner_options=self.people_options(),
            recent_new_owner_options=(
                self.event_controller.recent_people_options()
                if hasattr(
                    self.event_controller,
                    "recent_people_options",
                )
                else ()
            ),
            selected_new_owners=self.selected_item_new_owners,
            mage_groups=(
                self.event_controller.mage_groups()
                if hasattr(self.event_controller, "mage_groups")
                else ()
            ),
        )
        return True

    def item_links_chosen(
        self,
        item_ids,
        item_link_types=None,
        item_new_owners=None,
    ):
        self.selected_item_ids = list(dict.fromkeys(item_ids or ()))
        self.selected_item_link_types = normalize_item_event_link_types(
            (
                item_link_types
                if isinstance(item_link_types, dict)
                else self.selected_item_link_types
            ),
            self.selected_item_ids,
            (
                self.event.get("event_type", "event")
                if self.event
                else "event"
            ),
        )
        requested_new_owners = dict(
            self.selected_item_new_owners or {}
        )

        if isinstance(item_new_owners, dict):
            requested_new_owners.update(item_new_owners)

        self.selected_item_new_owners = normalize_item_event_new_owners(
            requested_new_owners,
            self.selected_item_ids,
            self.selected_item_link_types,
        )
        self.refresh_items_summary()
        return True

    def refresh_ancillary_people_summary(self):
        if not hasattr(self, "witnesses_summary_value"):
            return

        labels_by_id = {
            option["value"]: option["label"]
            for option in self.people_options()
        }
        witness_labels = [
            labels_by_id.get(person_id, "Unknown person")
            for person_id in self.selected_witness_person_ids
        ]
        affected_labels = [
            labels_by_id.get(person_id, "Unknown person")
            for person_id in self.selected_affected_person_ids
        ]
        self.witnesses_summary_value.set(
            "Witnessed: " + (", ".join(witness_labels) or "None")
        )
        self.affected_summary_value.set(
            "Affected by: " + (", ".join(affected_labels) or "None")
        )

    def open_ancillary_people_dialog(self):
        if self.event_controller is None:
            return

        MurderAdditionalPeopleDialog(
            self,
            self.event_controller,
            self.selected_witness_person_ids,
            self.selected_affected_person_ids,
            self.ancillary_people_chosen,
        )

    def ancillary_people_chosen(
        self,
        witness_person_ids,
        affected_person_ids,
    ):
        selected_witness_ids = list(witness_person_ids)
        selected_affected_ids = list(affected_person_ids)
        all_role_ids = [
            *self.selected_person_ids,
            *selected_witness_ids,
            *selected_affected_ids,
        ]

        if len(all_role_ids) != len(set(all_role_ids)):
            messagebox.showerror(
                "Choose different people",
                "Each person can belong to only one event category.",
                parent=self,
            )
            return False

        self.selected_witness_person_ids = selected_witness_ids
        self.selected_affected_person_ids = selected_affected_ids
        self.refresh_ancillary_people_summary()
        self.eminence_picker.update_people(
            self.selected_linked_person_ids()
        )
        return True

    def open_person_picker(self):
        if self.event_controller is None:
            return

        suggestion_provider = getattr(
            self.event_controller,
            "event_people_suggestion_options",
            None,
        )
        suggested_people_options = (
            suggestion_provider(self.selected_person_ids)
            if callable(suggestion_provider)
            else self.event_controller.recent_people_options()
        )
        EventPersonPickerDialog(
            self,
            self.event_controller.people_options(),
            self.event_controller.recent_people_options(),
            (
                self.selected_person_ids[-1]
                if self.selected_person_ids
                else ""
            ),
            self.people_chosen,
            create_person_command=getattr(
                self.event_controller,
                "create_event_person",
                None,
            ),
            mage_groups=(
                self.event_controller.mage_groups()
                if hasattr(self.event_controller, "mage_groups")
                else []
            ),
            allow_multiple=True,
            selected_person_ids=self.selected_person_ids,
            suggested_people_options=suggested_people_options,
            reference_date=self.current_date_value(),
            action_text="Use selected",
        )

    def people_chosen(self, person_ids):
        normalized_person_ids = []

        for person_id in person_ids or ():
            normalized_person_id = str(person_id or "").strip()

            if (
                normalized_person_id
                and normalized_person_id not in normalized_person_ids
            ):
                normalized_person_ids.append(normalized_person_id)

        conflicting_person_ids = set(normalized_person_ids).intersection(
            {
                *self.selected_witness_person_ids,
                *self.selected_affected_person_ids,
            }
        )

        if conflicting_person_ids:
            messagebox.showerror(
                "Choose a different role",
                "A selected person is already witnessed or affected by "
                "the event.",
                parent=self,
            )
            return False

        self.selected_person_ids = normalized_person_ids
        self.refresh_people_list()

        if hasattr(self, "eminence_picker"):
            self.eminence_picker.update_people(
                self.selected_linked_person_ids()
            )

        return True

    def add_selected_person(self, person_id):
        normalized_person_id = str(person_id or "").strip()

        if normalized_person_id in {
            *self.selected_witness_person_ids,
            *self.selected_affected_person_ids,
        }:
            messagebox.showerror(
                "Choose a different role",
                "This person is already witnessed or affected by the "
                "event.",
                parent=self,
            )
            return

        if (
            normalized_person_id
            and normalized_person_id not in self.selected_person_ids
        ):
            self.selected_person_ids.append(
                normalized_person_id
            )

        self.refresh_people_list()

        if hasattr(self, "eminence_picker"):
            self.eminence_picker.update_people(
                self.selected_linked_person_ids()
            )

    def remove_selected_person(self):
        selected = self.people_list.curselection()

        if not selected:
            return

        self.selected_person_ids = [
            person_id
            for index, person_id in enumerate(
                self.selected_person_ids
            )
            if index != int(selected[0])
        ]
        self.refresh_people_list()
        self.eminence_picker.update_people(
            self.selected_linked_person_ids()
        )

    def save_event(self):
        year_text = self.year_value.get().strip()
        month_text = self.month_value.get().strip()
        day_text = self.day_value.get().strip()

        if not year_text:
            messagebox.showerror(
                "Year required",
                "Every organization event requires a year.",
                parent=self,
            )
            return

        try:
            year = int(year_text)
        except ValueError:
            messagebox.showerror(
                "Invalid year",
                "The event year must be a whole number.",
                parent=self,
            )
            return

        if day_text and not month_text:
            messagebox.showerror(
                "Invalid date",
                "The event day requires a month.",
                parent=self,
            )
            return

        description = self.description_control.text.get(
            "1.0",
            "end-1c",
        )
        missing_item_owner_ids = [
            item_id
            for item_id in getattr(self, "selected_item_ids", [])
            if getattr(
                self,
                "selected_item_link_types",
                {},
            ).get(item_id)
            in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            and not getattr(
                self,
                "selected_item_new_owners",
                {},
            ).get(
                item_id,
                {},
            ).get("person_id")
        ]

        if missing_item_owner_ids:
            messagebox.showerror(
                "New owner required",
                "Choose the new owner for every Passed down, Gifted, or "
                "Taken item link.",
                parent=self,
            )
            return

        try:
            if self.is_founding:
                record = normalize_organization_event(
                    {
                        **self.event,
                        "date": "",
                        "year": year,
                        "month": month_text,
                        "day": day_text,
                        "time": self.time_value.get().strip(),
                        "description": description,
                        "person_ids": self.selected_person_ids,
                        "witness_person_ids": (
                            self.selected_witness_person_ids
                        ),
                        "affected_person_ids": (
                            self.selected_affected_person_ids
                        ),
                        "item_ids": getattr(
                            self,
                            "selected_item_ids",
                            [],
                        ),
                        "item_link_types": getattr(
                            self,
                            "selected_item_link_types",
                            {},
                        ),
                        "item_new_owners": getattr(
                            self,
                            "selected_item_new_owners",
                            {},
                        ),
                        "eminence_person_ids": (
                            self.eminence_picker.get_values()
                        ),
                        "eminence_skills": (
                            self.eminence_picker.get_skill_values()
                        ),
                    }
                )
            else:
                record = new_organization_event(
                    self.title_value.get(),
                    year,
                    description,
                    self.selected_person_ids,
                    self.eminence_picker.get_values(),
                    self.eminence_picker.get_skill_values(),
                    month=month_text,
                    day=day_text,
                    witness_person_ids=(
                        self.selected_witness_person_ids
                    ),
                    affected_person_ids=(
                        self.selected_affected_person_ids
                    ),
                    item_ids=getattr(
                        self,
                        "selected_item_ids",
                        [],
                    ),
                    item_link_types=getattr(
                        self,
                        "selected_item_link_types",
                        {},
                    ),
                    item_new_owners=getattr(
                        self,
                        "selected_item_new_owners",
                        {},
                    ),
                    time=self.time_value.get().strip(),
                )

                if self.event is not None:
                    record["record_id"] = self.event["record_id"]
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save event",
                str(error),
                parent=self,
            )
            return

        self.save_command(record)
        self.destroy()

    def current_date_value(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()
        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            date_value += f"-{day}"

        return date_value

    def update_time_visibility(self, *arguments):
        if self.time_value.get().strip():
            self.date_frame.grid_columnconfigure(3, weight=1)
            self.time_label.grid()
            self.time_entry.grid()
            return True

        try:
            selected_date = normalize_world_event_date(
                self.current_date_value()
            )
        except ValueError:
            self.time_label.grid_remove()
            self.time_entry.grid_remove()
            self.date_frame.grid_columnconfigure(3, weight=0)
            return False

        list_events = getattr(self.event_controller, "list_events", None)

        if not callable(list_events):
            self.time_label.grid_remove()
            self.time_entry.grid_remove()
            self.date_frame.grid_columnconfigure(3, weight=0)
            return False

        current_record_id = str(
            (self.event or {}).get("record_id", "") or ""
        ).strip()

        for event in list_events():
            organization_event_id = str(
                event.get("organization_event_id", "") or ""
            ).strip()

            if current_record_id and organization_event_id == current_record_id:
                continue

            if str(event.get("date", "") or "").strip() == selected_date:
                self.date_frame.grid_columnconfigure(3, weight=1)
                self.time_label.grid()
                self.time_entry.grid()
                return True

        self.time_label.grid_remove()
        self.time_entry.grid_remove()
        self.date_frame.grid_columnconfigure(3, weight=0)
        return False
