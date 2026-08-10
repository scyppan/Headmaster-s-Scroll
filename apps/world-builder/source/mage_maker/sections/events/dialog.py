import tkinter as tk
from copy import deepcopy
from datetime import date
from functools import partial
from tkinter import messagebox

from mage_maker.core.dates import historical_year_distance
from mage_maker.sections.events.models import (
    WORLD_EVENT_LABEL_TYPES,
    WORLD_EVENT_TYPES,
    WORLD_EVENT_TYPE_LABELS,
    normalize_world_event_date,
    split_world_event_date,
)
from mage_maker.sections.locations.location_hierarchy import (
    LocationHierarchyTree,
)
from mage_maker.sections.locations.models import (
    recent_location_label,
)
from mage_maker.shell.person_list import (
    AGE_FILTER_BOUNDS,
    AGE_FILTER_OPTIONS,
    FILTER_SHOW_ALL,
    SORT_AGE,
    SORT_BIRTH_YEAR,
    SORT_BIRTH_YEAR_NEWEST,
    SORT_GROUP,
    SORT_NAME,
    SORT_OPTIONS,
)
from mage_maker.ui.theme import (
    ADD_GREEN,
    ADD_GREEN_HOVER,
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_HOVER,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    CalendarAdoptionNotice,
    LabeledEntry,
    RoundedEntry,
    RoundedSelect,
    RoundedText,
    SoftButton,
)


class WorldEventDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        controller,
        event=None,
        saved_command=None,
        default_person_ids=(),
        default_location_ids=(),
        locked_location_ids=(),
    ):
        super().__init__(parent)
        self.controller = controller
        self.saved_command = saved_command
        self.event = deepcopy(event) if isinstance(event, dict) else {}
        self.people_options = self.controller.people_options()
        self.location_options = self.controller.location_options()
        self.location_records = self.controller.location_records()
        self.recent_people_options = (
            self.controller.recent_people_options()
        )
        self.recent_location_options = (
            self.controller.recent_location_options()
        )
        self.title_value = tk.StringVar(
            value=str(self.event.get("title", "") or "")
        )
        event_type = str(self.event.get("event_type", "other") or "other")
        self.event_type_value = tk.StringVar(
            value=WORLD_EVENT_TYPE_LABELS.get(event_type, "Other")
        )
        year, month, day = split_world_event_date(
            self.event.get("date", "")
        )
        self.year_value = tk.StringVar(value=year)
        self.month_value = tk.StringVar(value=month)
        self.day_value = tk.StringVar(value=day)
        self.time_value = tk.StringVar(
            value=str(self.event.get("time", "") or "").strip()
        )
        self.initial_person_ids = set(
            self.event.get("person_ids", default_person_ids)
        )
        self.selected_person_ids = [
            option["value"]
            for option in self.people_options
            if option["value"] in self.initial_person_ids
        ]
        self.locked_location_ids = {
            str(location_id or "").strip()
            for location_id in (
                list(self.event.get("locked_location_ids", []))
                + list(locked_location_ids)
            )
            if str(location_id or "").strip()
        }
        self.initial_location_ids = set(
            self.event.get("location_ids", default_location_ids)
        ).union(self.locked_location_ids)
        self.selected_location_ids = [
            option["value"]
            for option in self.location_options
            if option["value"] in self.initial_location_ids
        ]
        self.title(
            "Edit shared event"
            if self.event.get("record_id")
            else "Add shared event"
        )
        self.geometry("940x720")
        self.minsize(820, 620)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.year_value.trace_add("write", self.update_time_visibility)
        self.month_value.trace_add("write", self.update_time_visibility)
        self.day_value.trace_add("write", self.update_time_visibility)
        self.time_value.trace_add("write", self.update_time_visibility)
        self.update_time_visibility()
        self.bind("<Escape>", self.close_dialog)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=20,
            pady=18,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=20, pady=20)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(5, weight=1)
        heading = tk.Label(
            card,
            text="Shared event",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "The required year places this event in its period automatically. "
                "Link any applicable people and locations so the same event also "
                "appears from those records."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(3, 14))
        main_fields = tk.Frame(card, bg=SURFACE)
        main_fields.grid(row=2, column=0, sticky="ew")
        main_fields.grid_columnconfigure(0, weight=3)
        main_fields.grid_columnconfigure(1, weight=2)
        title_field = LabeledEntry(
            main_fields,
            "Event title",
            self.title_value,
            background=SURFACE,
        )
        title_field.grid(row=0, column=0, sticky="ew", padx=(0, 7))
        type_panel = tk.Frame(main_fields, bg=SURFACE)
        type_panel.grid(row=0, column=1, sticky="ew", padx=(7, 0))
        type_panel.grid_columnconfigure(0, weight=1)
        type_label = tk.Label(
            type_panel,
            text="Event type",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        type_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        type_picker = RoundedSelect(
            type_panel,
            textvariable=self.event_type_value,
            values=[label for event_type, label in WORLD_EVENT_TYPES],
            background=SURFACE,
            height=40,
            font=app_font(10),
        )
        type_picker.grid(row=1, column=0, sticky="ew")
        date_panel = tk.Frame(card, bg=SURFACE)
        self.date_panel = date_panel
        date_panel.grid(row=3, column=0, sticky="ew", pady=(14, 0))
        date_panel.grid_columnconfigure((0, 1, 2, 3), weight=1)
        year_field = LabeledEntry(
            date_panel,
            "Year (required)",
            self.year_value,
            background=SURFACE,
        )
        year_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        month_field = LabeledEntry(
            date_panel,
            "Month",
            self.month_value,
            background=SURFACE,
        )
        month_field.grid(row=0, column=1, sticky="ew", padx=6)
        day_field = LabeledEntry(
            date_panel,
            "Day",
            self.day_value,
            background=SURFACE,
        )
        day_field.grid(row=0, column=2, sticky="ew", padx=(6, 0))
        self.time_field = LabeledEntry(
            date_panel,
            "Time (HHMM, 24-hour)",
            self.time_value,
            background=SURFACE,
        )
        self.time_field.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(12, 0),
        )
        self.time_field.grid_remove()
        calendar_notice = CalendarAdoptionNotice(
            date_panel,
            background=SURFACE,
            wraplength=640,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        )
        calendar_notice.grid(
            row=1,
            column=0,
            columnspan=4,
            sticky="w",
            pady=(5, 0),
        )
        description_panel = tk.Frame(card, bg=SURFACE)
        description_panel.grid(row=4, column=0, sticky="ew", pady=(14, 0))
        description_panel.grid_columnconfigure(0, weight=1)
        description_label = tk.Label(
            description_panel,
            text="Description",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        description_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.description_control = RoundedText(
            description_panel,
            background=SURFACE,
            height=4,
        )
        self.description_control.grid(row=1, column=0, sticky="ew")
        self.description_control.text.insert(
            "1.0",
            str(self.event.get("description", "") or ""),
        )
        associations = tk.Frame(card, bg=SURFACE)
        associations.grid(row=5, column=0, sticky="nsew", pady=(16, 0))
        associations.grid_rowconfigure(0, weight=1)
        associations.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="event_associations",
        )
        self.people_list = self.build_people_selection(
            associations,
            0,
        )
        self.locations_list = self.build_location_selection(
            associations,
            1,
        )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=6, column=0, sticky="e", pady=(16, 0))
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
            width=112,
            height=36,
        )
        save_button.pack(side="left")
        self.after_idle(title_field.control.focus_set)

    def build_people_selection(self, parent, column):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        panel.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(0, 6),
        )
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        self.people_heading_value = tk.StringVar()
        heading = tk.Label(
            panel,
            textvariable=self.people_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        hint = tk.Label(
            panel,
            text="Add only the people linked to this event.",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(2, 7))
        list_frame = tk.Frame(panel, bg=SURFACE_MUTED)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        listbox = tk.Listbox(
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
            selectmode="extended",
            exportselection=False,
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)
        self.build_recent_suggestions(
            panel,
            3,
            self.recent_people_options,
            self.person_chosen,
        )
        buttons = tk.Frame(panel, bg=SURFACE_MUTED)
        buttons.grid(row=4, column=0, sticky="e", pady=(8, 0))
        add_button = SoftButton(
            buttons,
            text="Select people",
            command=self.open_person_picker,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=106,
            height=34,
        )
        add_button.pack(side="left", padx=(0, 6))
        remove_button = SoftButton(
            buttons,
            text="Remove",
            command=self.remove_selected_people,
            background=SURFACE_MUTED,
            width=88,
            height=34,
        )
        remove_button.pack(side="left")
        self.render_selected_people(listbox)
        return listbox

    def build_recent_suggestions(
        self,
        parent,
        row,
        options,
        selection_command,
    ):
        recent_panel = tk.Frame(parent, bg=SURFACE_MUTED)
        recent_panel.grid(row=row, column=0, sticky="ew")
        recent_panel.grid_columnconfigure(0, weight=1)
        recent_label = tk.Label(
            recent_panel,
            text="Recently used",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        recent_label.grid(row=0, column=0, sticky="ew", pady=(0, 3))

        if not options:
            empty_label = tk.Label(
                recent_panel,
                text="Suggestions appear here after you save events.",
                bg=SURFACE_MUTED,
                fg=TEXT_MUTED,
                font=app_font(8),
                anchor="w",
            )
            empty_label.grid(row=1, column=0, sticky="ew")
            return recent_panel

        for index, option in enumerate(options[:3]):
            suggestion = SoftButton(
                recent_panel,
                text=self.short_suggestion_label(option.get("label", "")),
                command=partial(
                    selection_command,
                    option.get("value", ""),
                ),
                background=SURFACE_MUTED,
                fill=FIELD_BACKGROUND,
                hover_fill=LIST_SELECTED,
                foreground=TEXT_DARK,
                width=320,
                height=28,
                anchor="w",
                padx=9,
                font=app_font(8),
            )
            suggestion.grid(
                row=index + 1,
                column=0,
                sticky="ew",
                pady=(0, 3),
            )

        return recent_panel

    def short_suggestion_label(self, label):
        normalized = " ".join(str(label or "").strip().split())

        if len(normalized) <= 34:
            return normalized

        return f"{normalized[:31]}..."

    def render_selected_people(self, listbox=None):
        target_listbox = listbox or self.people_list
        people_labels = {
            option["value"]: option["label"]
            for option in self.people_options
        }
        target_listbox.delete(0, "end")

        for person_id in self.selected_person_ids:
            target_listbox.insert(
                "end",
                people_labels.get(person_id, "Missing person"),
            )

        if hasattr(self, "people_heading_value"):
            selected_count = len(self.selected_person_ids)
            self.people_heading_value.set(
                (
                    "People · 1 selected"
                    if selected_count == 1
                    else f"People · {selected_count} selected"
                )
            )

    def open_person_picker(self):
        selected_id = (
            self.selected_person_ids[-1]
            if self.selected_person_ids
            else ""
        )
        suggestion_provider = getattr(
            self.controller,
            "event_people_suggestion_options",
            None,
        )
        suggested_people_options = (
            suggestion_provider(self.selected_person_ids)
            if callable(suggestion_provider)
            else self.recent_people_options
        )
        EventPersonPickerDialog(
            self,
            self.people_options,
            self.recent_people_options,
            selected_id,
            self.people_chosen,
            create_person_command=getattr(
                self.controller,
                "create_event_person",
                None,
            ),
            mage_groups=(
                self.controller.mage_groups()
                if hasattr(self.controller, "mage_groups")
                else []
            ),
            allow_multiple=True,
            selected_person_ids=self.selected_person_ids,
            suggested_people_options=suggested_people_options,
            reference_date=self.current_date_value(),
            action_text="Use selected",
        )

    def people_chosen(self, person_ids):
        self.people_options = self.controller.people_options()
        available_person_ids = {
            str(option.get("value", "") or "").strip()
            for option in self.people_options
            if str(option.get("value", "") or "").strip()
        }
        self.selected_person_ids = []

        for person_id in person_ids or ():
            normalized_id = str(person_id or "").strip()

            if (
                normalized_id in available_person_ids
                and normalized_id not in self.selected_person_ids
            ):
                self.selected_person_ids.append(normalized_id)

        self.render_selected_people()

    def person_chosen(self, person_id):
        normalized_id = str(person_id or "").strip()
        self.people_options = self.controller.people_options()

        if normalized_id and normalized_id not in self.selected_person_ids:
            self.selected_person_ids.append(normalized_id)

        self.render_selected_people()

        if normalized_id in self.selected_person_ids:
            index = self.selected_person_ids.index(normalized_id)
            self.people_list.selection_clear(0, "end")
            self.people_list.selection_set(index)
            self.people_list.see(index)

    def remove_selected_people(self):
        selected_indices = set(self.people_list.curselection())

        if not selected_indices:
            return

        self.selected_person_ids = [
            person_id
            for index, person_id in enumerate(self.selected_person_ids)
            if index not in selected_indices
        ]
        self.render_selected_people()

    def build_location_selection(self, parent, column):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        panel.grid(
            row=0,
            column=column,
            sticky="nsew",
            padx=(6, 0),
        )
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            panel,
            text="Locations",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        hint = tk.Label(
            panel,
            text="Add locations from a searchable hierarchy.",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        hint.grid(row=1, column=0, sticky="ew", pady=(2, 7))
        list_frame = tk.Frame(panel, bg=SURFACE_MUTED)
        list_frame.grid(row=2, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        listbox = tk.Listbox(
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
            selectmode="extended",
            exportselection=False,
        )
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar = tk.Scrollbar(list_frame, command=listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        listbox.configure(yscrollcommand=scrollbar.set)
        self.build_recent_suggestions(
            panel,
            3,
            self.recent_location_options,
            self.location_chosen,
        )
        buttons = tk.Frame(panel, bg=SURFACE_MUTED)
        buttons.grid(row=4, column=0, sticky="e", pady=(8, 0))
        add_button = SoftButton(
            buttons,
            text="Find location",
            command=self.open_location_picker,
            background=SURFACE_MUTED,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=34,
        )
        add_button.pack(side="left", padx=(0, 6))
        remove_button = SoftButton(
            buttons,
            text="Remove",
            command=self.remove_selected_locations,
            background=SURFACE_MUTED,
            width=88,
            height=34,
        )
        remove_button.pack(side="left")
        self.render_selected_locations(listbox)
        return listbox

    def render_selected_locations(self, listbox=None):
        target_listbox = listbox or self.locations_list
        location_labels = {
            option["value"]: option["label"]
            for option in self.location_options
        }
        target_listbox.delete(0, "end")

        for location_id in self.selected_location_ids:
            location_label = location_labels.get(
                location_id,
                "Missing location",
            )

            if location_id in self.locked_location_ids:
                location_label = f"{location_label}  ·  source locked"

            target_listbox.insert(
                "end",
                location_label,
            )

    def open_location_picker(self):
        selected_id = (
            self.selected_location_ids[-1]
            if self.selected_location_ids
            else ""
        )
        EventLocationPickerDialog(
            self,
            self.location_records,
            selected_id,
            self.location_chosen,
            create_location_command=getattr(
                self.controller,
                "create_placeholder_location",
                None,
            ),
            recent_location_options=self.recent_location_options,
            selection_history_command=getattr(
                self.controller,
                "remember_location_selection",
                None,
            ),
        )

    def location_chosen(self, location_id):
        normalized_id = str(location_id or "").strip()
        self.location_options = self.controller.location_options()
        self.location_records = self.controller.location_records()

        if (
            normalized_id
            and normalized_id not in self.selected_location_ids
        ):
            self.selected_location_ids.append(normalized_id)

        self.render_selected_locations()

        if normalized_id in self.selected_location_ids:
            index = self.selected_location_ids.index(normalized_id)
            self.locations_list.selection_clear(0, "end")
            self.locations_list.selection_set(index)
            self.locations_list.see(index)

    def remove_selected_locations(self):
        selected_indices = set(self.locations_list.curselection())

        if not selected_indices:
            return

        self.selected_location_ids = [
            location_id
            for index, location_id in enumerate(self.selected_location_ids)
            if (
                index not in selected_indices
                or location_id in self.locked_location_ids
            )
        ]
        self.render_selected_locations()

    def save_event(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()
        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            date_value += f"-{day}"

        if not year:
            messagebox.showerror(
                "Cannot save event",
                "Enter the year when this event happened.",
                parent=self,
            )
            return False

        values = {
            "event_type": WORLD_EVENT_LABEL_TYPES.get(
                self.event_type_value.get(),
                "other",
            ),
            "title": self.title_value.get(),
            "date": date_value,
            "time": self.time_value.get().strip(),
            "description": self.description_control.text.get(
                "1.0",
                "end-1c",
            ),
            "person_ids": list(self.selected_person_ids),
            "period_names": [],
            "location_ids": list(
                dict.fromkeys(
                    self.selected_location_ids
                    + list(self.locked_location_ids)
                )
            ),
            "locked_location_ids": list(self.locked_location_ids),
        }

        try:
            if self.event.get("record_id"):
                saved = self.controller.update_event(
                    self.event["record_id"],
                    values,
                )
            else:
                saved = self.controller.create_event(values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save event",
                str(error),
                parent=self,
            )
            return False

        if self.saved_command is not None:
            self.saved_command(saved)

        self.destroy()
        return True

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
            self.date_panel.grid_columnconfigure(3, weight=1)
            self.time_field.grid()
            return True

        try:
            selected_date = normalize_world_event_date(
                self.current_date_value()
            )
        except ValueError:
            self.time_field.grid_remove()
            self.date_panel.grid_columnconfigure(3, weight=0)
            return False

        current_record_id = str(
            self.event.get("record_id", "") or ""
        ).strip()

        for event in self.controller.list_events():
            if (
                current_record_id
                and str(event.get("record_id", "") or "").strip()
                == current_record_id
            ):
                continue

            if str(event.get("date", "") or "").strip() == selected_date:
                self.date_panel.grid_columnconfigure(3, weight=1)
                self.time_field.grid()
                return True

        self.time_field.grid_remove()
        self.date_panel.grid_columnconfigure(3, weight=0)
        return False

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class EventPersonPickerDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        people_options,
        recent_people_options,
        selected_person_id,
        save_command,
        create_person_command=None,
        mage_groups=None,
        dialog_title="Add event person",
        heading_text="Choose a person",
        explanation_text=(
            "Likely participants appear first. Type any part of a name "
            "to search everyone."
        ),
        selection_prompt="Select a person to add.",
        action_text="Add person",
        allow_multiple=False,
        selected_person_ids=None,
        locked_person_ids=None,
        suggested_people_options=None,
        reference_date=None,
    ):
        super().__init__(parent)
        self.allow_multiple = bool(allow_multiple)
        self.people_options = [
            deepcopy(option)
            for option in people_options
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
        ]
        self.recent_people_options = [
            deepcopy(option)
            for option in recent_people_options
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
        ]
        known_person_ids = {
            str(option.get("value", "") or "").strip()
            for option in self.people_options
            if str(option.get("value", "") or "").strip()
        }
        requested_suggestions = (
            suggested_people_options
            if suggested_people_options is not None
            else self.recent_people_options
        )
        self.suggested_people_options = []
        used_suggestion_ids = set()

        for option in requested_suggestions or ():
            if not isinstance(option, dict):
                continue

            person_id = str(option.get("value", "") or "").strip()

            if (
                person_id not in known_person_ids
                or person_id in used_suggestion_ids
            ):
                continue

            self.suggested_people_options.append(deepcopy(option))
            used_suggestion_ids.add(person_id)
        self.visible_options = []
        self.selected_person_id = str(
            selected_person_id or ""
        ).strip()
        self.selected_person_ids = []
        self.locked_person_order = []

        for person_id in locked_person_ids or ():
            normalized_person_id = str(person_id or "").strip()

            if (
                normalized_person_id
                and normalized_person_id not in self.locked_person_order
            ):
                self.locked_person_order.append(normalized_person_id)

        self.locked_person_ids = set(self.locked_person_order)

        for person_id in selected_person_ids or ():
            normalized_person_id = str(person_id or "").strip()

            if (
                normalized_person_id
                and normalized_person_id not in self.selected_person_ids
            ):
                self.selected_person_ids.append(normalized_person_id)

        if (
            self.allow_multiple
            and self.selected_person_id
            and self.selected_person_id not in self.selected_person_ids
        ):
            self.selected_person_ids.append(self.selected_person_id)

        for person_id in self.locked_person_order:
            if person_id not in self.selected_person_ids:
                self.selected_person_ids.append(person_id)

        if not self.allow_multiple:
            self.selected_person_ids = (
                [self.selected_person_id]
                if self.selected_person_id
                else []
            )
        self.save_command = save_command
        self.create_person_command = create_person_command
        self.dialog_title = str(
            dialog_title or "Choose a person"
        ).strip()
        self.heading_text = str(
            heading_text or "Choose a person"
        ).strip()
        self.explanation_text = str(explanation_text or "").strip()
        self.selection_prompt = str(
            selection_prompt or "Select a person."
        ).strip()
        self.action_text = str(action_text or "Choose person").strip()
        self.reference_date = reference_date
        self.mage_groups = [
            deepcopy(group)
            for group in mage_groups or []
            if isinstance(group, dict)
        ]
        self.search_value = tk.StringVar()
        self.group_filter_value = tk.StringVar(
            value=FILTER_SHOW_ALL
        )
        self.age_filter_value = tk.StringVar(
            value=FILTER_SHOW_ALL
        )
        self.sort_value = tk.StringVar(value=SORT_BIRTH_YEAR)
        self.filter_summary_value = tk.StringVar(
            value="All people · Birth year"
        )
        self.filter_updates_paused = False
        self.show_all_requested = False
        self.result_heading_value = tk.StringVar(value="Suggestions")
        self.selection_value = tk.StringVar(
            value=(
                "0 people selected"
                if self.allow_multiple
                else self.selection_prompt
            )
        )
        self.title(self.dialog_title)
        self.geometry(
            "620x680" if self.allow_multiple else "560x620"
        )
        self.minsize(
            500 if self.allow_multiple else 460,
            540 if self.allow_multiple else 500,
        )
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_results)
        self.group_filter_value.trace_add(
            "write",
            self.refresh_results,
        )
        self.age_filter_value.trace_add(
            "write",
            self.refresh_results,
        )
        self.sort_value.trace_add("write", self.refresh_results)
        self.refresh_results()
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
        card.grid_rowconfigure(5, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text=self.heading_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=self.explanation_text,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=470,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.search_control = RoundedEntry(
            card,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_control.grid(row=2, column=0, sticky="ew")
        self.search_control.bind_input("<Escape>", self.clear_search)
        self.search_control.bind_input("<Return>", self.choose_first_result)
        filter_row = tk.Frame(card, bg=SURFACE)
        filter_row.grid(row=3, column=0, sticky="ew", pady=(9, 0))
        filter_row.grid_columnconfigure(1, weight=1)
        self.filter_button = SoftButton(
            filter_row,
            text="Filters ▾",
            command=self.show_filter_menu,
            background=SURFACE,
            width=82,
            height=30,
            font=app_font(9, "bold"),
        )
        self.filter_button.grid(row=0, column=0, sticky="w")
        filter_summary = tk.Label(
            filter_row,
            textvariable=self.filter_summary_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        )
        filter_summary.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=8,
        )
        show_all_button = SoftButton(
            filter_row,
            text="Show all",
            command=self.show_all_people,
            background=SURFACE,
            width=68,
            height=30,
            font=app_font(8, "bold"),
        )
        show_all_button.grid(row=0, column=2, sticky="e")
        self.build_filter_menu()
        results_heading = tk.Label(
            card,
            textvariable=self.result_heading_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        results_heading.grid(row=4, column=0, sticky="ew", pady=(11, 5))
        results_frame = tk.Frame(
            card,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        results_frame.grid(row=5, column=0, sticky="nsew")
        results_frame.grid_rowconfigure(0, weight=1)
        results_frame.grid_columnconfigure(0, weight=1)
        self.results_list = tk.Listbox(
            results_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
        )
        self.results_list.grid(row=0, column=0, sticky="nsew")
        self.results_list.bind("<<ListboxSelect>>", self.person_selected)

        if self.allow_multiple:
            self.results_list.bind(
                "<ButtonRelease-1>",
                self.toggle_person_selection,
            )
            self.results_list.bind(
                "<space>",
                self.toggle_person_selection,
            )
        else:
            self.results_list.bind(
                "<Double-Button-1>",
                self.choose_person,
            )
        scrollbar = tk.Scrollbar(
            results_frame,
            command=self.results_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.results_list.configure(yscrollcommand=scrollbar.set)
        selected_label = tk.Label(
            card,
            textvariable=self.selection_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        selected_label.grid(row=6, column=0, sticky="ew", pady=(10, 0))
        self.bulk_actions = tk.Frame(card, bg=SURFACE)
        self.bulk_actions.grid(
            row=7,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        self.bulk_actions.grid_columnconfigure(3, weight=1)
        select_visible_button = SoftButton(
            self.bulk_actions,
            text="Select visible",
            command=self.select_visible_people,
            background=SURFACE,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=104,
            height=30,
            font=app_font(8, "bold"),
        )
        select_visible_button.grid(row=0, column=0, sticky="w")
        clear_visible_button = SoftButton(
            self.bulk_actions,
            text="Clear visible",
            command=self.clear_visible_people,
            background=SURFACE,
            width=98,
            height=30,
            font=app_font(8, "bold"),
        )
        clear_visible_button.grid(
            row=0,
            column=1,
            sticky="w",
            padx=(6, 0),
        )
        clear_all_button = SoftButton(
            self.bulk_actions,
            text="Clear all",
            command=self.clear_all_people,
            background=SURFACE,
            width=80,
            height=30,
            font=app_font(8, "bold"),
        )
        clear_all_button.grid(
            row=0,
            column=2,
            sticky="w",
            padx=(6, 0),
        )

        if not self.allow_multiple:
            self.bulk_actions.grid_remove()

        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=8 if self.allow_multiple else 7,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        footer.grid_columnconfigure(1, weight=1)

        if self.create_person_command is not None:
            new_person_button = SoftButton(
                footer,
                text="New person",
                command=self.open_quick_person,
                background=SURFACE,
                fill=ADD_GREEN,
                hover_fill=ADD_GREEN_HOVER,
                foreground=TEXT_DARK,
                width=104,
                height=36,
            )
            new_person_button.grid(row=0, column=0, sticky="w")

        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        )
        cancel_button.grid(row=0, column=2, padx=(0, 6))
        self.add_button = SoftButton(
            footer,
            text=self.action_text,
            command=self.choose_person,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=36,
        )
        self.add_button.grid(row=0, column=3)
        self.add_button.set_enabled(self.allow_multiple)
        self.after_idle(self.search_control.focus_set)

    def build_filter_menu(self):
        self.filter_menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )
        group_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )
        group_names = {
            str(option.get("group_name", "") or "").strip()
            for option in self.people_options
            if str(option.get("group_name", "") or "").strip()
        }

        for group in self.mage_groups:
            group_name = str(group.get("name", "") or "").strip()

            if group_name:
                group_names.add(group_name)

        for group_name in [
            FILTER_SHOW_ALL,
            *sorted(group_names, key=str.casefold),
        ]:
            group_menu.add_radiobutton(
                label=group_name,
                variable=self.group_filter_value,
                value=group_name,
            )

        age_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for age_option in AGE_FILTER_OPTIONS:
            age_menu.add_radiobutton(
                label=age_option,
                variable=self.age_filter_value,
                value=age_option,
            )

        sort_menu = tk.Menu(
            self.filter_menu,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            relief="solid",
            borderwidth=1,
            font=app_font(10),
        )

        for sort_option in SORT_OPTIONS:
            sort_menu.add_radiobutton(
                label=sort_option,
                variable=self.sort_value,
                value=sort_option,
            )

        self.filter_menu.add_cascade(label="Group", menu=group_menu)
        self.filter_menu.add_cascade(label="Age", menu=age_menu)
        self.filter_menu.add_cascade(
            label="Sort by",
            menu=sort_menu,
        )
        self.filter_menu.add_separator()
        self.filter_menu.add_command(
            label=FILTER_SHOW_ALL,
            command=self.show_all_people,
        )

    def show_filter_menu(self):
        self.filter_button.update_idletasks()

        try:
            self.filter_menu.tk_popup(
                self.filter_button.winfo_rootx(),
                (
                    self.filter_button.winfo_rooty()
                    + self.filter_button.winfo_height()
                ),
            )
        finally:
            self.filter_menu.grab_release()

    def show_all_people(self):
        self.filter_updates_paused = True
        self.search_value.set("")
        self.group_filter_value.set(FILTER_SHOW_ALL)
        self.age_filter_value.set(FILTER_SHOW_ALL)
        self.filter_updates_paused = False
        self.show_all_requested = True
        self.refresh_results()

    def update_filter_summary(self):
        parts = []

        if self.group_filter_value.get() != FILTER_SHOW_ALL:
            parts.append(self.group_filter_value.get())

        if self.age_filter_value.get() != FILTER_SHOW_ALL:
            parts.append(self.age_filter_value.get())

        if not parts:
            parts.append("All people")

        parts.append(self.sort_value.get())
        self.filter_summary_value.set(" · ".join(parts))

    def option_person(self, option):
        person = option.get("person")

        if isinstance(person, dict):
            return person

        return {
            "record_id": option.get("value"),
            "displayed_name": option.get("label"),
            "mage_group_id": "",
        }

    def integer_value(self, value):
        if isinstance(value, bool):
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def person_age(self, person):
        birth_year = self.integer_value(person.get("birth_year"))

        if birth_year is None:
            return None

        birth_month = self.integer_value(person.get("birth_month"))
        birth_day = self.integer_value(person.get("birth_day"))
        reference_date = getattr(self, "reference_date", None)

        if reference_date is not None:
            try:
                end_year_text, end_month_text, end_day_text = (
                    split_world_event_date(reference_date)
                )
            except (TypeError, ValueError):
                return None

            end_year = self.integer_value(end_year_text)
            end_month = self.integer_value(end_month_text)
            end_day = self.integer_value(end_day_text)
        else:
            death_year = self.integer_value(person.get("death_year"))
            has_death_date = (
                bool(person.get("deceased"))
                or death_year is not None
            )

            if has_death_date:
                end_year = death_year
                end_month = self.integer_value(
                    person.get("death_month")
                )
                end_day = self.integer_value(person.get("death_day"))
            else:
                today = date.today()
                end_year = today.year
                end_month = today.month
                end_day = today.day

        if end_year is None:
            return None

        try:
            age = historical_year_distance(birth_year, end_year)
        except (TypeError, ValueError):
            return None

        if (
            birth_month is not None
            and birth_day is not None
            and end_month is not None
            and end_day is not None
            and (end_month, end_day) < (birth_month, birth_day)
        ):
            age -= 1

        return age if age >= 0 else None

    def matches_age_filter(self, person):
        selected_filter = self.age_filter_value.get()

        if selected_filter == FILTER_SHOW_ALL:
            return True

        age = self.person_age(person)

        if selected_filter == "Unknown age":
            return age is None

        bounds = AGE_FILTER_BOUNDS.get(selected_filter)

        if bounds is None or age is None:
            return bounds is None

        minimum_age, maximum_age = bounds
        return (
            age >= minimum_age
            and (
                maximum_age is None
                or age <= maximum_age
            )
        )

    def person_search_text(self, option):
        person = self.option_person(option)
        name_details = person.get("name_details", {})
        entries = (
            name_details.get("entries", [])
            if isinstance(name_details, dict)
            else []
        )
        previous_names = " ".join(
            " ".join(
                str(entry.get(field_name, "") or "")
                for field_name in (
                    "name_type",
                    "name_entry",
                    "date",
                    "note",
                )
            )
            for entry in entries
            if isinstance(entry, dict)
        )
        return " ".join(
            str(value or "")
            for value in (
                option.get("label"),
                previous_names,
                person.get("school"),
                option.get("group_name"),
                person.get("birth_year"),
                person.get("death_year"),
            )
        ).casefold()

    def person_sort_key(self, option):
        person = self.option_person(option)
        selected_sort = self.sort_value.get()
        name = str(option.get("label", "") or "").casefold()
        group_name = str(
            option.get("group_name", "") or ""
        ).casefold()
        birth_year = self.integer_value(person.get("birth_year"))
        birth_month = self.integer_value(person.get("birth_month"))
        birth_day = self.integer_value(person.get("birth_day"))
        birth_is_dated = birth_year is not None
        oldest_birth_key = (
            birth_is_dated,
            birth_year if birth_year is not None else 0,
            birth_month if birth_month is not None else 13,
            birth_day if birth_day is not None else 32,
            name,
        )

        if selected_sort == SORT_BIRTH_YEAR_NEWEST:
            return (
                birth_is_dated,
                -birth_year if birth_year is not None else 0,
                -birth_month if birth_month is not None else 0,
                -birth_day if birth_day is not None else 0,
                name,
            )

        if selected_sort == SORT_NAME:
            return name, *oldest_birth_key

        if selected_sort == SORT_GROUP:
            return group_name, *oldest_birth_key

        if selected_sort == SORT_AGE:
            age = self.person_age(person)
            return (
                age is None,
                -age if age is not None else 0,
                *oldest_birth_key,
            )

        return oldest_birth_key

    def person_display_text(self, option):
        person = self.option_person(option)
        birth_year = self.integer_value(person.get("birth_year"))
        birth_text = (
            f"Born {birth_year}"
            if birth_year is not None
            else "Birth date unknown"
        )
        reference_date = getattr(self, "reference_date", None)

        if reference_date is not None:
            event_age = self.person_age(person)
            birth_text = (
                f"Age {event_age} at event · {birth_text}"
                if event_age is not None
                else f"Age at event unknown · {birth_text}"
            )
        group_name = str(option.get("group_name", "") or "").strip()
        details = (
            f"{birth_text} · {group_name}"
            if group_name
            else birth_text
        )
        suggestion_reason = str(
            option.get("suggestion_reason", "") or ""
        ).strip()

        if suggestion_reason:
            details = f"{details} · {suggestion_reason}"

        return (
            f"{option.get('label', 'Unnamed person')}"
            f"  ·  {details}"
        )

    def refresh_results(self, *arguments):
        if self.filter_updates_paused:
            return

        self.update_filter_summary()
        query_terms = [
            term
            for term in self.search_value.get().casefold().split()
            if term
        ]
        selected_group = self.group_filter_value.get()
        filters_are_active = bool(
            query_terms
            or selected_group != FILTER_SHOW_ALL
            or self.age_filter_value.get() != FILTER_SHOW_ALL
            or self.sort_value.get() != SORT_BIRTH_YEAR
            or self.show_all_requested
        )

        if filters_are_active:
            self.visible_options = sorted(
                [
                    option
                    for option in self.people_options
                    if (
                        selected_group == FILTER_SHOW_ALL
                        or option.get("group_name") == selected_group
                    )
                    and self.matches_age_filter(
                        self.option_person(option)
                    )
                    and all(
                        term in self.person_search_text(option)
                        for term in query_terms
                    )
                ],
                key=self.person_sort_key,
            )
            self.result_heading_value.set(
                f"People ({len(self.visible_options)})"
            )
        else:
            suggestion_options = list(
                getattr(
                    self,
                    "suggested_people_options",
                    self.recent_people_options,
                )
            )

            if self.allow_multiple and self.selected_person_ids:
                options_by_person_id = {
                    str(option.get("value", "") or "").strip(): option
                    for option in self.people_options
                    if str(option.get("value", "") or "").strip()
                }
                self.visible_options = [
                    options_by_person_id[person_id]
                    for person_id in self.selected_person_ids
                    if person_id in options_by_person_id
                ]

                for option in suggestion_options:
                    person_id = str(
                        option.get("value", "") or ""
                    ).strip()

                    if (
                        person_id
                        and all(
                            str(
                                visible_option.get("value", "") or ""
                            ).strip()
                            != person_id
                            for visible_option in self.visible_options
                        )
                    ):
                        self.visible_options.append(option)

                self.result_heading_value.set(
                    "Selected people and suggestions"
                )
            else:
                self.visible_options = suggestion_options
                self.result_heading_value.set(
                    (
                        "Suggestions"
                        if self.visible_options
                        else "Start typing to search"
                    )
                )

        self.results_list.delete(0, "end")

        for index, option in enumerate(self.visible_options):
            person_id = str(option.get("value", "") or "").strip()
            display_text = self.person_display_text(option)

            if self.allow_multiple:
                if person_id in self.locked_person_ids:
                    display_text = f"✓ {display_text} · fixed"
                elif person_id in self.selected_person_ids:
                    display_text = f"✓ {display_text}"
                else:
                    display_text = f"  {display_text}"

            self.results_list.insert(
                "end",
                display_text,
            )

            if person_id == self.selected_person_id:
                self.results_list.selection_set(index)
                self.results_list.see(index)

        if not any(
            option.get("value") == self.selected_person_id
            for option in self.visible_options
        ):
            self.selected_person_id = ""

        self.update_selection_display()

    def person_selected(self, event=None):
        selection = self.results_list.curselection()

        if not selection:
            return

        self.selected_person_id = str(
            self.visible_options[selection[0]].get("value", "") or ""
        ).strip()
        self.update_selection_display()

    def update_selection_display(self):
        if self.allow_multiple:
            selected_count = len(self.selected_person_ids)
            self.selection_value.set(
                (
                    "1 person selected"
                    if selected_count == 1
                    else f"{selected_count} people selected"
                )
            )
            self.add_button.set_enabled(True)
            return

        selected_label = ""

        for option in self.people_options:
            if option.get("value") == self.selected_person_id:
                selected_label = str(option.get("label", "") or "")
                break

        self.selection_value.set(
            selected_label or self.selection_prompt
        )
        self.add_button.set_enabled(bool(self.selected_person_id))

    def choose_first_result(self, event=None):
        if self.visible_options and not self.selected_person_id:
            self.selected_person_id = str(
                self.visible_options[0].get("value", "") or ""
            ).strip()
            self.results_list.selection_clear(0, "end")
            self.results_list.selection_set(0)

        if self.allow_multiple:
            self.toggle_person_selection()
            return "break"

        self.choose_person()
        return "break"

    def choose_person(self, event=None):
        if self.allow_multiple:
            self.save_command(list(self.selected_person_ids))
            self.destroy()
            return

        if not self.selected_person_id:
            return

        self.save_command(self.selected_person_id)
        self.destroy()

    def toggle_person_selection(self, event=None):
        if not self.allow_multiple:
            return

        selection = self.results_list.curselection()

        if selection:
            self.selected_person_id = str(
                self.visible_options[selection[0]].get("value", "") or ""
            ).strip()

        if not self.selected_person_id:
            return "break"

        if self.selected_person_id in self.locked_person_ids:
            return "break"

        if self.selected_person_id in self.selected_person_ids:
            self.selected_person_ids = [
                person_id
                for person_id in self.selected_person_ids
                if person_id != self.selected_person_id
            ]
        else:
            self.selected_person_ids.append(self.selected_person_id)

        first_visible_fraction = self.results_list.yview()[0]
        self.refresh_results()
        self.results_list.yview_moveto(first_visible_fraction)
        return "break"

    def select_visible_people(self):
        for option in self.visible_options:
            person_id = str(option.get("value", "") or "").strip()

            if person_id and person_id not in self.selected_person_ids:
                self.selected_person_ids.append(person_id)

        self.refresh_results()

    def clear_visible_people(self):
        visible_person_ids = {
            str(option.get("value", "") or "").strip()
            for option in self.visible_options
            if str(option.get("value", "") or "").strip()
        }
        self.selected_person_ids = [
            person_id
            for person_id in self.selected_person_ids
            if (
                person_id not in visible_person_ids
                or person_id in self.locked_person_ids
            )
        ]
        self.refresh_results()

    def clear_all_people(self):
        self.selected_person_ids = [
            person_id
            for person_id in self.selected_person_ids
            if person_id in self.locked_person_ids
        ]
        self.refresh_results()

    def open_quick_person(self):
        if self.create_person_command is None:
            return

        QuickEventPersonDialog(
            self,
            self.mage_groups,
            self.create_person_command,
            self.quick_person_created,
        )

    def quick_person_created(self, person):
        if not isinstance(person, dict):
            return

        person_id = str(person.get("record_id", "") or "").strip()

        if not person_id:
            return

        group_name = next(
            (
                str(group.get("name", "") or "")
                for group in self.mage_groups
                if str(group.get("group_id", "") or "")
                == str(person.get("mage_group_id", "") or "")
            ),
            "Unassigned",
        )
        option = {
            "value": person_id,
            "label": str(
                person.get("displayed_name", "")
                or "Unnamed magician"
            ).strip(),
            "person": deepcopy(person),
            "group_name": group_name,
        }
        self.people_options = [
            existing_option
            for existing_option in self.people_options
            if str(existing_option.get("value", "") or "").strip()
            != person_id
        ]
        self.people_options.append(option)

        if self.allow_multiple:
            self.recent_people_options = [
                option,
                *(
                    recent_option
                    for recent_option in self.recent_people_options
                    if str(
                        recent_option.get("value", "") or ""
                    ).strip()
                    != person_id
                ),
            ]
            self.suggested_people_options = [
                option,
                *(
                    suggested_option
                    for suggested_option in getattr(
                        self,
                        "suggested_people_options",
                        (),
                    )
                    if str(
                        suggested_option.get("value", "") or ""
                    ).strip()
                    != person_id
                ),
            ]
            self.selected_person_id = person_id

            if person_id not in self.selected_person_ids:
                self.selected_person_ids.append(person_id)

            self.refresh_results()
            return

        self.save_command(person_id)
        self.after_idle(self.destroy)

    def clear_search(self, event=None):
        if self.search_value.get():
            self.search_value.set("")
            return "break"

        self.destroy()
        return "break"

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class QuickEventPersonDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        mage_groups,
        create_command,
        saved_command,
    ):
        super().__init__(parent)
        self.mage_groups = [
            deepcopy(group)
            for group in mage_groups or []
            if isinstance(group, dict)
        ]
        self.create_command = create_command
        self.saved_command = saved_command
        self.name_value = tk.StringVar()
        self.birth_year_value = tk.StringVar()
        self.birth_month_value = tk.StringVar()
        self.birth_day_value = tk.StringVar()
        self.can_give_birth_value = tk.BooleanVar(value=False)
        self.non_magical_value = tk.BooleanVar(value=False)
        group_names = [
            str(group.get("name", "") or "").strip()
            for group in self.mage_groups
            if str(group.get("name", "") or "").strip()
        ]
        self.group_names = group_names or ["Unassigned"]
        self.group_value = tk.StringVar(value=self.group_names[0])
        self.title("New person")
        self.geometry("560x500")
        self.minsize(500, 460)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.grab_set()
        self.after_idle(self.name_entry.focus_set)

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY, height=58)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text="New person",
            bg=PRIMARY,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=20, pady=18)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_columnconfigure((0, 1, 2), weight=1)
        name_label = tk.Label(
            body,
            text="Displayed name",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        name_label.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        self.name_entry = RoundedEntry(
            body,
            textvariable=self.name_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.name_entry.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(5, 14),
        )
        birth_label = tk.Label(
            body,
            text="Birth date",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        birth_label.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="ew",
        )

        for column, label_text, variable in (
            (0, "Year", self.birth_year_value),
            (1, "Month", self.birth_month_value),
            (2, "Day", self.birth_day_value),
        ):
            part_label = tk.Label(
                body,
                text=label_text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8),
                anchor="w",
            )
            part_label.grid(
                row=3,
                column=column,
                sticky="ew",
                padx=(
                    (0, 6)
                    if column == 0
                    else ((6, 0) if column == 2 else 6)
                ),
                pady=(5, 3),
            )
            entry = RoundedEntry(
                body,
                textvariable=variable,
                background=SURFACE,
                height=38,
                font=app_font(10),
                justify="center",
            )
            entry.grid(
                row=4,
                column=column,
                sticky="ew",
                padx=(
                    (0, 6)
                    if column == 0
                    else ((6, 0) if column == 2 else 6)
                ),
                pady=(0, 14),
            )

        calendar_notice = CalendarAdoptionNotice(
            body,
            background=SURFACE,
            wraplength=500,
            date_variables=(
                self.birth_year_value,
                self.birth_month_value,
                self.birth_day_value,
            ),
        )
        calendar_notice.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(0, 10),
        )

        group_label = tk.Label(
            body,
            text="Group",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        group_label.grid(
            row=6,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        group_select = RoundedSelect(
            body,
            self.group_value,
            self.group_names,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        group_select.grid(
            row=7,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(5, 14),
        )
        flags = tk.Frame(body, bg=SURFACE)
        flags.grid(
            row=8,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        can_give_birth = tk.Checkbutton(
            flags,
            text="Can give birth",
            variable=self.can_give_birth_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9),
        )
        can_give_birth.pack(side="left")
        non_magical = tk.Checkbutton(
            flags,
            text="Non-magical",
            variable=self.non_magical_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9),
        )
        non_magical.pack(side="left", padx=(20, 0))
        footer = tk.Frame(self, bg=APP_BACKGROUND)
        footer.grid(
            row=2,
            column=0,
            sticky="e",
            padx=18,
            pady=(0, 16),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=APP_BACKGROUND,
            width=88,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        create_button = SoftButton(
            footer,
            text="Create and add",
            command=self.create_person,
            background=APP_BACKGROUND,
            fill=ADD_GREEN,
            hover_fill=ADD_GREEN_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=36,
        )
        create_button.pack(side="left")

    def optional_integer(
        self,
        value,
        label,
        minimum=None,
        maximum=None,
    ):
        text = str(value or "").strip()

        if not text:
            return None

        try:
            number = int(text)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{label} must be a whole number.") from error

        if minimum is not None and number < minimum:
            raise ValueError(f"{label} cannot be less than {minimum}.")

        if maximum is not None and number > maximum:
            raise ValueError(f"{label} cannot exceed {maximum}.")

        return number

    def selected_group_id(self):
        return next(
            (
                str(group.get("group_id", "") or "")
                for group in self.mage_groups
                if str(group.get("name", "") or "")
                == self.group_value.get()
            ),
            "unassigned",
        )

    def create_person(self):
        try:
            person = self.create_command(
                {
                    "displayed_name": self.name_value.get(),
                    "birth_year": self.optional_integer(
                        self.birth_year_value.get(),
                        "Birth year",
                        -99999,
                        99999,
                    ),
                    "birth_month": self.optional_integer(
                        self.birth_month_value.get(),
                        "Birth month",
                        1,
                        12,
                    ),
                    "birth_day": self.optional_integer(
                        self.birth_day_value.get(),
                        "Birth day",
                        1,
                        31,
                    ),
                    "mage_group_id": self.selected_group_id(),
                    "can_give_birth": self.can_give_birth_value.get(),
                    "non_magical": self.non_magical_value.get(),
                }
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot create person",
                str(error),
                parent=self,
            )
            return

        self.saved_command(person)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class EventLocationPickerDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        selected_location_id,
        save_command,
        dialog_title="Add event location",
        action_text="Add location",
        create_location_command=None,
        recent_location_options=(),
        selection_history_command=None,
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
        self.dialog_title = str(
            dialog_title or "Add event location"
        )
        self.action_text = str(action_text or "Add location")
        self.create_location_command = create_location_command
        self.selection_history_command = selection_history_command
        available_location_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in self.locations
            if str(location.get("record_id", "") or "").strip()
        }
        self.recent_location_options = []
        used_recent_ids = set()

        for option in recent_location_options or ():
            if not isinstance(option, dict):
                continue

            location_id = str(option.get("value", "") or "").strip()

            if (
                not location_id
                or location_id not in available_location_ids
                or location_id in used_recent_ids
            ):
                continue

            used_recent_ids.add(location_id)
            self.recent_location_options.append(
                {
                    "value": location_id,
                    "label": str(
                        option.get("label", "")
                        or recent_location_label(
                            location_id,
                            self.locations,
                        )
                    ).strip(),
                }
            )

            if len(self.recent_location_options) >= 5:
                break

        self.recent_location_ids = [
            option["value"]
            for option in self.recent_location_options
        ]
        self.selection_value = tk.StringVar(
            value="Select a location from the hierarchy."
        )
        self.title(self.dialog_title)
        self.geometry("620x760")
        self.minsize(500, 620)
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
        self.location_selected(
            self.location_tree.selected_location_id
        )
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
        card.grid_rowconfigure(3, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="Choose a location",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Search by any part of a location or its path, then expand "
                "the matching branch and choose the exact place."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        recent_panel = tk.Frame(
            card,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=10,
            pady=8,
        )
        recent_panel.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 12),
        )
        recent_panel.grid_columnconfigure(0, weight=1)
        recent_heading = tk.Label(
            recent_panel,
            text="Recently viewed or selected locations",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        recent_heading.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.recent_listbox = tk.Listbox(
            recent_panel,
            height=min(
                5,
                max(1, len(self.recent_location_options)),
            ),
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
        self.recent_listbox.grid(row=1, column=0, sticky="ew")
        self.recent_listbox.bind(
            "<<ListboxSelect>>",
            self.recent_location_selected,
        )
        self.recent_listbox.bind(
            "<Double-Button-1>",
            self.choose_recent_location,
        )

        if self.recent_location_options:
            for index, option in enumerate(
                self.recent_location_options
            ):
                self.recent_listbox.insert("end", option["label"])
                self.recent_listbox.itemconfigure(
                    index,
                    background=(
                        FIELD_BACKGROUND
                        if index % 2 == 0
                        else LIST_ALTERNATE
                    ),
                )
        else:
            self.recent_listbox.insert(
                "end",
                "No recently viewed locations",
            )
            self.recent_listbox.configure(
                state="disabled",
                fg=TEXT_MUTED,
            )

        self.location_tree = LocationHierarchyTree(
            card,
            self.location_selected,
            background=SURFACE,
            show_scope_controls=True,
        )
        self.location_tree.grid(row=3, column=0, sticky="nsew")
        selected_label = tk.Label(
            card,
            textvariable=self.selection_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        selected_label.grid(row=4, column=0, sticky="ew", pady=(10, 0))
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=5, column=0, sticky="e", pady=(14, 0))

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
        self.add_button = SoftButton(
            footer,
            text=self.action_text,
            command=self.choose_location,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=118,
            height=36,
        )
        self.add_button.pack(side="left")

    def location_selected(self, location_id):
        requested_id = str(location_id or "").strip()
        self.selected_location_id = requested_id
        self.recent_listbox.selection_clear(0, "end")

        if requested_id in self.recent_location_ids:
            recent_index = self.recent_location_ids.index(requested_id)
            self.recent_listbox.selection_set(recent_index)
            self.recent_listbox.see(recent_index)

        if not requested_id:
            self.selection_value.set(
                "Select a location from the hierarchy."
            )
            self.add_button.set_enabled(False)
            return

        self.selection_value.set(
            recent_location_label(requested_id, self.locations)
        )
        self.add_button.set_enabled(True)

    def recent_location_selected(self, event=None):
        selected = self.recent_listbox.curselection()

        if not selected or selected[0] >= len(self.recent_location_ids):
            return

        location_id = self.recent_location_ids[selected[0]]
        self.location_tree.select_location(location_id, notify=True)

    def choose_recent_location(self, event=None):
        self.recent_location_selected()
        self.choose_location()
        return "break"

    def open_placeholder_location(self):
        if self.create_location_command is None:
            return False

        PlaceholderLocationDialog(
            self,
            self.locations,
            self.selected_location_id,
            self.create_location_command,
            self.placeholder_location_created,
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
        self.location_tree.select_location(
            self.selected_location_id,
        )
        self.location_selected(self.selected_location_id)
        return True

    def choose_location(self):
        if not self.selected_location_id:
            return

        if callable(self.selection_history_command):
            self.selection_history_command(self.selected_location_id)

        self.save_command(self.selected_location_id)
        self.destroy()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"


class PlaceholderLocationDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        locations,
        selected_parent_location_id,
        create_command,
        saved_command,
        allow_world_parent=True,
    ):
        super().__init__(parent)
        self.locations = [
            deepcopy(location)
            for location in locations
            if isinstance(location, dict)
        ]
        self.create_command = create_command
        self.saved_command = saved_command
        self.allow_world_parent = bool(allow_world_parent)
        self.place_value = tk.StringVar()
        selected_parent_id = str(
            selected_parent_location_id or ""
        ).strip()
        available_ids = [
            str(location.get("record_id", "") or "").strip()
            for location in self.locations
            if str(location.get("record_id", "") or "").strip()
        ]

        if selected_parent_id not in available_ids:
            selected_parent_id = (
                (available_ids[0] if available_ids else "")
                if not self.allow_world_parent
                else ""
            )

        selected_parent_label = (
            recent_location_label(
                selected_parent_id,
                self.locations,
            )
            if selected_parent_id
            else "The World"
        )
        self.parent_value = tk.StringVar(
            value=selected_parent_label
        )
        self.selected_parent_id = selected_parent_id
        self.title("New location")
        self.geometry("520x390")
        self.minsize(480, 370)
        self.resizable(False, False)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.bind("<Escape>", self.close_dialog)
        self.bind("<Return>", self.save_location)
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
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="New location placeholder",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Enter the place and its parent. Additional details can be "
                "added later from Locations."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        explanation.grid(row=1, column=0, sticky="ew", pady=(4, 12))
        self.place_field = LabeledEntry(
            card,
            "Place",
            self.place_value,
            background=SURFACE,
        )
        self.place_field.grid(row=2, column=0, sticky="ew")
        parent_panel = tk.Frame(card, bg=SURFACE)
        parent_panel.grid(row=3, column=0, sticky="ew", pady=(12, 0))
        parent_panel.grid_columnconfigure(0, weight=1)
        parent_label = tk.Label(
            parent_panel,
            text="Parent",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        parent_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        parent_display = tk.Label(
            parent_panel,
            textvariable=self.parent_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
            pady=9,
        )
        parent_display.grid(row=1, column=0, sticky="ew")
        choose_parent_button = SoftButton(
            parent_panel,
            text="Choose…",
            command=self.choose_parent_location,
            background=SURFACE,
            width=82,
            height=38,
            font=app_font(9, "bold"),
        )
        choose_parent_button.grid(
            row=1,
            column=1,
            padx=(6, 0),
        )

        if self.allow_world_parent:
            world_button = SoftButton(
                parent_panel,
                text="The World",
                command=self.use_world_parent,
                background=SURFACE,
                width=88,
                height=38,
                font=app_font(9, "bold"),
            )
            world_button.grid(
                row=1,
                column=2,
                padx=(6, 0),
            )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=4, column=0, sticky="e", pady=(16, 0))
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
            text="Create location",
            command=self.save_location,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=132,
            height=36,
        )
        save_button.pack(side="left")
        self.after_idle(self.place_field.control.focus_set)

    def selected_parent_location_id(self):
        return self.selected_parent_id

    def choose_parent_location(self):
        EventLocationPickerDialog(
            self,
            self.locations,
            self.selected_parent_id,
            self.parent_location_selected,
            dialog_title="Choose parent location",
            action_text="Use parent",
        )

    def parent_location_selected(self, location_id):
        self.selected_parent_id = str(location_id or "").strip()
        self.parent_value.set(
            recent_location_label(
                self.selected_parent_id,
                self.locations,
            )
            if self.selected_parent_id
            else "The World"
        )

    def use_world_parent(self):
        self.selected_parent_id = ""
        self.parent_value.set("The World")

    def save_location(self, event=None):
        try:
            created = self.create_command(
                self.place_value.get(),
                self.selected_parent_location_id(),
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot create location",
                str(error),
                parent=self,
            )
            return "break"

        if not isinstance(created, dict):
            messagebox.showerror(
                "Cannot create location",
                "The location could not be created.",
                parent=self,
            )
            return "break"

        self.saved_command(created)
        self.destroy()
        return "break"

    def close_dialog(self, event=None):
        self.destroy()
        return "break"
