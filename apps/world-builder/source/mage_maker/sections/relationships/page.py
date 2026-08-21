import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.core.dates import format_date_parts, split_partial_date
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    world_event_sort_key,
)
from mage_maker.sections.events.types import (
    canonical_event_type,
    event_type_label,
)
from mage_maker.sections.family_tree.relationship_picker import (
    RelationshipPickerDialog,
)
from mage_maker.sections.family_tree.spouse_relationships import (
    normalize_spouse_relationships,
)
from mage_maker.sections.timeline.page import (
    EVENT_COLORS,
    format_timeline_date,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    SURFACE,
    SURFACE_MUTED,
    PRIMARY,
    PRIMARY_HOVER,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    LabeledEntry,
    RoundedSelect,
    RoundedText,
    SoftButton,
)


RELATIONSHIP_EVENT_TYPES = (
    "began_friendship",
    "romance",
    "got_married",
    "breakup",
    "foster_child",
)


def foster_relationship_text(current_name, other_names, current_is_parent):
    """Describe the parent and child roles explicitly."""
    current_name = str(current_name or "Unnamed person").strip()
    other_names = [
        str(name or "Missing person").strip()
        for name in other_names
    ]

    if current_is_parent:
        return f"{current_name} is foster parent of {', '.join(other_names)}"

    return f"{', '.join(other_names)} is foster parent of {current_name}"


class RelationshipsView(tk.Frame):
    def __init__(
        self,
        parent,
        people_provider=None,
        event_controller=None,
        navigate_command=None,
        event_saved_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.people_provider = people_provider
        self.event_controller = event_controller
        self.navigate_command = navigate_command
        self.event_saved_command = event_saved_command
        self.person = {}
        self.visible_relationships = []
        self.summary_value = tk.StringVar(value="No person selected")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_view()

    def build_view(self):
        header = tk.Frame(self, bg=SURFACE)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            text="Relationships",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        self.add_event_button = SoftButton(
            header,
            text="Add relationship event",
            command=self.open_add_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=164,
            height=34,
        )
        self.add_event_button.grid(row=0, column=1, padx=(8, 0))
        panel = tk.Frame(
            self,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=14,
            pady=12,
        )
        panel.grid(row=1, column=0, sticky="nsew")
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        summary = tk.Label(
            panel,
            textvariable=self.summary_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        list_frame = tk.Frame(
            panel,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.relationship_list = tk.Listbox(
            list_frame,
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
        self.relationship_list.grid(row=0, column=0, sticky="nsew")
        self.relationship_list.bind(
            "<Double-Button-1>",
            self.open_selected_person,
        )
        self.relationship_list.bind(
            "<Return>",
            self.open_selected_person,
        )
        self.relationship_list.bind(
            "<<ListboxSelect>>",
            self.relationship_selection_changed,
        )
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.relationship_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.relationship_list.configure(yscrollcommand=scrollbar.set)
        actions = tk.Frame(panel, bg=SURFACE_MUTED)
        actions.grid(row=2, column=0, sticky="e", pady=(8, 0))
        self.edit_event_button = SoftButton(
            actions,
            text="Edit event",
            command=self.open_edit_event,
            background=SURFACE_MUTED,
            width=96,
            height=32,
        )
        self.edit_event_button.pack(side="left", padx=(0, 6))
        self.delete_event_button = SoftButton(
            actions,
            text="Delete event",
            command=self.delete_selected_event,
            background=SURFACE_MUTED,
            width=106,
            height=32,
        )
        self.delete_event_button.pack(side="left")
        self.relationship_selection_changed()

    def set_person(self, person):
        self.person = deepcopy(person) if isinstance(person, dict) else {}
        self.refresh()

    def refresh(self):
        self.visible_relationships = self.relationship_rows()
        self.relationship_list.delete(0, "end")

        for index, relationship in enumerate(self.visible_relationships):
            self.relationship_list.insert("end", relationship["label"])
            self.relationship_list.itemconfigure(
                index,
                background=(
                    relationship.get("background")
                    or (
                        FIELD_BACKGROUND
                        if index % 2 == 0
                        else LIST_ALTERNATE
                    )
                ),
            )

        count = len(self.visible_relationships)
        self.summary_value.set(
            f"{count} relationship{'s' if count != 1 else ''}"
            if self.person
            else "No person selected"
        )

        if not self.visible_relationships and self.person:
            self.relationship_list.insert(
                "end",
                "No marriages, romances, breakups, or recorded friendships.",
            )

        self.relationship_selection_changed()

    def relationship_rows(self):
        person_id = str(
            self.person.get("record_id", "") or ""
        ).strip()

        if not person_id:
            return []

        people = (
            list(self.people_provider())
            if callable(self.people_provider)
            else []
        )
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in people
            if isinstance(person, dict)
        }
        rows = []
        used_relationships = set()

        for relationship in normalize_spouse_relationships(
            self.person.get("spouse_relationships", [])
        ):
            if not relationship["married"]:
                continue

            mate_id = relationship["person_id"]
            mate = people_by_id.get(mate_id, {})
            mate_name = str(
                mate.get("displayed_name", "") or "Missing person"
            ).strip()
            date_value = format_date_parts(
                relationship.get("marriage_year"),
                relationship.get("marriage_month"),
                relationship.get("marriage_day"),
                unknown="nd.",
            )
            date_text = format_timeline_date(date_value)
            rows.append(
                {
                    "kind": "marriage",
                    "date": date_value,
                    "person_ids": [mate_id],
                    "label": f"{date_text} · Marriage to {mate_name}",
                }
            )
            used_relationships.add(("marriage", mate_id))

        events = (
            self.event_controller.events_for_person(person_id)
            if self.event_controller is not None
            else []
        )

        for event in events:
            event_type = canonical_event_type(event.get("event_type"))

            if event_type not in (
                "began_friendship",
                "got_married",
                "romance",
                "breakup",
                "foster_child",
            ):
                continue

            if person_id not in event.get("person_ids", []):
                continue

            if event_type == "foster_child":
                foster_parent_ids = list(
                    event.get("foster_parent_person_ids", []) or []
                )
                foster_child_ids = list(
                    event.get("foster_child_person_ids", []) or []
                )
                current_is_parent = person_id in foster_parent_ids
                other_ids = (
                    foster_child_ids if current_is_parent else foster_parent_ids
                )
            else:
                current_is_parent = False
                other_ids = [
                    linked_id
                    for linked_id in event.get("person_ids", [])
                    if linked_id != person_id
                ]

            if not other_ids:
                continue

            if event_type == "got_married" and all(
                ("marriage", other_id) in used_relationships
                for other_id in other_ids
            ):
                continue

            other_names = [
                str(
                    people_by_id.get(other_id, {}).get(
                        "displayed_name",
                        "Missing person",
                    )
                    or "Missing person"
                ).strip()
                for other_id in other_ids
            ]
            date_text = format_timeline_date(event.get("date"))
            event_time = str(event.get("time", "") or "").strip()

            if event_time:
                date_text = f"{date_text} {event_time}"

            relationship_text = {
                "got_married": "Marriage to ",
                "began_friendship": "Began friendship with ",
                "romance": "Romance with ",
                "breakup": "Breakup with ",
                "foster_child": "",
            }[event_type]
            if event_type == "foster_child":
                current_name = str(
                    self.person.get("displayed_name", "")
                    or "Unnamed person"
                ).strip()
                relationship_text = foster_relationship_text(
                    current_name,
                    other_names,
                    current_is_parent,
                )
                other_names = []
            rows.append(
                {
                    "kind": event_type,
                    "date": str(event.get("date", "") or ""),
                    "time": event_time,
                    "record_id": str(
                        event.get("record_id", "") or ""
                    ),
                    "person_ids": other_ids,
                    "event": deepcopy(event),
                    "background": EVENT_COLORS.get(event_type),
                    "label": (
                        f"{date_text} · {relationship_text}"
                        + ", ".join(other_names)
                    ),
                }
            )

        rows.sort(key=self.relationship_sort_key)
        return rows

    def relationship_sort_key(self, relationship):
        return world_event_sort_key(
            {
                "date": relationship.get("date", ""),
                "time": relationship.get("time", ""),
                "title": relationship.get("label", ""),
                "record_id": relationship.get("record_id", ""),
            }
        )

    def open_selected_person(self, event=None):
        if self.navigate_command is None:
            return "break"

        selected = self.relationship_list.curselection()

        if not selected or selected[0] >= len(self.visible_relationships):
            return "break"

        person_ids = self.visible_relationships[selected[0]].get(
            "person_ids",
            [],
        )

        if person_ids:
            self.navigate_command(person_ids[0])

        return "break"

    def selected_relationship(self):
        selected = self.relationship_list.curselection()

        if not selected or selected[0] >= len(self.visible_relationships):
            return None

        return self.visible_relationships[selected[0]]

    def relationship_selection_changed(self, event=None):
        relationship = self.selected_relationship()
        editable = bool(
            relationship
            and str(relationship.get("record_id", "") or "").strip()
        )
        self.edit_event_button.set_enabled(editable)
        self.delete_event_button.set_enabled(editable)

    def open_edit_event(self):
        relationship = self.selected_relationship()

        if not relationship or not relationship.get("record_id"):
            return

        RelationshipEventDialog(
            self,
            self.person,
            self.people_provider() if callable(self.people_provider) else [],
            self.event_controller,
            self.relationship_event_saved,
            event=relationship.get("event"),
        )

    def delete_selected_event(self):
        relationship = self.selected_relationship()

        if not relationship or not relationship.get("record_id"):
            return

        if not messagebox.askyesno(
            "Delete relationship event",
            f"Delete this relationship event?\n\n{relationship['label']}",
            parent=self,
        ):
            return

        try:
            deleted = self.event_controller.delete_event(
                relationship["record_id"]
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot delete relationship event",
                str(error),
                parent=self,
            )
            return

        self.relationship_event_saved(deleted)

    def open_add_event(self):
        if not self.person.get("record_id") or self.event_controller is None:
            messagebox.showinfo(
                "Save person first",
                "Save this person before adding a relationship event.",
                parent=self,
            )
            return

        RelationshipEventDialog(
            self,
            self.person,
            self.people_provider() if callable(self.people_provider) else [],
            self.event_controller,
            self.relationship_event_saved,
        )

    def relationship_event_saved(self, event):
        if self.event_saved_command is not None:
            self.event_saved_command(event)

        self.refresh()


class RelationshipEventDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        current_person,
        people,
        event_controller,
        saved_command,
        event=None,
    ):
        super().__init__(parent)
        self.current_person = dict(current_person)
        self.people = [dict(person) for person in people if isinstance(person, dict)]
        self.event_controller = event_controller
        self.saved_command = saved_command
        self.event = deepcopy(event) if isinstance(event, dict) else None
        self.selected_person_id = ""
        self.kind_value = tk.StringVar(
            value=event_type_label("began_friendship")
        )
        self.direction_value = tk.StringVar(
            value="Current person is foster parent"
        )
        self.selected_person_value = tk.StringVar(value="No person selected")
        self.relationship_preview_value = tk.StringVar()
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        self.kind_value.trace_add("write", self.relationship_kind_changed)
        self.direction_value.trace_add("write", self.update_relationship_preview)

        self.title(
            "Edit relationship event"
            if self.event
            else "Add relationship event"
        )
        self.geometry("620x520")
        self.minsize(560, 470)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.build_dialog()
        self.load_event()
        self.relationship_kind_changed()

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        card.grid_columnconfigure(0, weight=1)
        card.grid_rowconfigure(6, weight=1)
        tk.Label(
            card,
            text=(
                "Edit relationship event"
                if self.event
                else "Add relationship event"
            ),
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.kind_picker = RoundedSelect(
            card,
            self.kind_value,
            [event_type_label(event_type) for event_type in RELATIONSHIP_EVENT_TYPES],
            background=SURFACE,
            height=36,
            font=app_font(9),
        )
        self.kind_picker.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        self.direction_picker = RoundedSelect(
            card,
            self.direction_value,
            (
                "Current person is foster parent",
                "Current person is foster child",
            ),
            background=SURFACE,
            height=34,
            font=app_font(9),
        )
        self.direction_picker.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self.relationship_preview = tk.Label(
            card,
            textvariable=self.relationship_preview_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.relationship_preview.grid(
            row=3,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        person_row = tk.Frame(card, bg=SURFACE)
        person_row.grid(row=4, column=0, sticky="ew")
        person_row.grid_columnconfigure(0, weight=1)
        tk.Label(
            person_row,
            textvariable=self.selected_person_value,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
            padx=10,
            pady=8,
        ).grid(row=0, column=0, sticky="ew")
        SoftButton(
            person_row,
            text="Choose person…",
            command=self.choose_person,
            background=SURFACE,
            width=118,
            height=34,
        ).grid(row=0, column=1, padx=(7, 0))
        date_row = tk.Frame(card, bg=SURFACE)
        date_row.grid(row=5, column=0, sticky="ew", pady=(10, 8))
        date_row.grid_columnconfigure((0, 1, 2), weight=1)

        for column, label, variable in (
            (0, "Year", self.year_value),
            (1, "Month", self.month_value),
            (2, "Day", self.day_value),
        ):
            field = LabeledEntry(
                date_row,
                label,
                variable,
                background=SURFACE,
            )
            field.grid(
                row=0,
                column=column,
                sticky="ew",
                padx=(0, 5) if column == 0 else ((5, 0) if column == 2 else 5),
            )

        self.details = RoundedText(
            card,
            background=SURFACE,
            height=4,
            minimum_height=92,
            font=app_font(9),
        )
        self.details.grid(row=6, column=0, sticky="nsew")
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(row=7, column=0, sticky="e", pady=(14, 0))
        SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=36,
        ).pack(side="left", padx=(0, 6))
        SoftButton(
            footer,
            text="Save event",
            command=self.save_event,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=36,
        ).pack(side="left")

    def relationship_kind_changed(self, *arguments):
        is_foster = self.selected_event_type() == "foster_child"

        if is_foster:
            self.direction_picker.grid()
            self.relationship_preview.grid()
        else:
            self.direction_picker.grid_remove()
            self.relationship_preview.grid_remove()

        self.update_relationship_preview()

    def load_event(self):
        if not self.event:
            return

        event_type = canonical_event_type(self.event.get("event_type"))
        self.kind_value.set(event_type_label(event_type))
        current_id = str(
            self.current_person.get("record_id", "") or ""
        ).strip()
        person_ids = [
            str(person_id or "").strip()
            for person_id in self.event.get("person_ids", []) or []
            if str(person_id or "").strip() != current_id
        ]

        if event_type == "foster_child":
            foster_parent_ids = self.event.get(
                "foster_parent_person_ids", []
            ) or []
            current_is_parent = current_id in foster_parent_ids
            self.direction_value.set(
                "Current person is foster parent"
                if current_is_parent
                else "Current person is foster child"
            )
            role_ids = (
                self.event.get("foster_child_person_ids", [])
                if current_is_parent
                else foster_parent_ids
            ) or []
            person_ids = [
                str(person_id or "").strip()
                for person_id in role_ids
                if str(person_id or "").strip() != current_id
            ]

        if person_ids:
            self.person_selected(person_ids[0])

        year, month, day = split_partial_date(
            self.event.get("date", "")
        )
        self.year_value.set(year)
        self.month_value.set(month)
        self.day_value.set(day)
        description = str(self.event.get("description", "") or "")
        self.details.text.delete("1.0", "end")
        self.details.text.insert("1.0", description)

    def update_relationship_preview(self, *arguments):
        if self.selected_event_type() != "foster_child":
            self.relationship_preview_value.set("")
            return

        current_name = str(
            self.current_person.get("displayed_name", "")
            or "Current person"
        ).strip()
        other_name = self.selected_person_value.get()

        if not self.selected_person_id:
            other_name = (
                "the selected child"
                if self.direction_value.get()
                == "Current person is foster parent"
                else "the selected foster parent"
            )

        if (
            self.direction_value.get()
            == "Current person is foster parent"
        ):
            preview = f"{current_name} is foster parent of {other_name}."
        else:
            preview = f"{other_name} is foster parent of {current_name}."

        self.relationship_preview_value.set(preview)

    def selected_event_type(self):
        label = self.kind_value.get()

        for event_type in RELATIONSHIP_EVENT_TYPES:
            if event_type_label(event_type) == label:
                return event_type

        return "began_friendship"

    def choose_person(self):
        current_id = str(self.current_person.get("record_id", "") or "")
        candidates = [
            person
            for person in self.people
            if str(person.get("record_id", "") or "") != current_id
        ]
        is_foster = self.selected_event_type() == "foster_child"
        current_is_parent = (
            self.direction_value.get() == "Current person is foster parent"
        )
        role = (
            "foster child"
            if is_foster and current_is_parent
            else "foster parent"
            if is_foster
            else "related person"
        )
        RelationshipPickerDialog(
            self,
            title=f"Choose {role}",
            heading=f"Choose {role}",
            explanation=f"Search by name and choose the {role}.",
            primary_people=candidates,
            alternate_people=(),
            alternate_label="",
            alternate_note="",
            select_label="Use person",
            select_command=self.person_selected,
            create_command=None,
            new_profile_label="",
            new_profile_explanation="",
        )

    def person_selected(self, person_id, is_alternate=False):
        self.selected_person_id = str(person_id or "").strip()
        selected = next(
            (
                person
                for person in self.people
                if str(person.get("record_id", "") or "")
                == self.selected_person_id
            ),
            {},
        )
        self.selected_person_value.set(
            str(selected.get("displayed_name", "") or "Unnamed person")
        )
        self.update_relationship_preview()

    def save_event(self):
        current_id = str(self.current_person.get("record_id", "") or "").strip()

        if not self.selected_person_id:
            messagebox.showerror(
                "Person required",
                "Choose the other person in this relationship event.",
                parent=self,
            )
            return

        date_text = "-".join(
            part
            for part in (
                self.year_value.get().strip(),
                self.month_value.get().strip(),
                self.day_value.get().strip(),
            )
            if part
        )

        try:
            event_date = normalize_world_event_date(date_text)
        except ValueError as error:
            messagebox.showerror("Invalid date", str(error), parent=self)
            return

        event_type = self.selected_event_type()
        other_name = self.selected_person_value.get()
        current_name = str(
            self.current_person.get("displayed_name", "") or "Unnamed person"
        )
        values = {
            "event_type": event_type,
            "title": f"{event_type_label(event_type)}: {current_name} and {other_name}",
            "date": event_date,
            "description": self.details.text.get("1.0", "end").strip(),
            "person_ids": [current_id, self.selected_person_id],
        }

        if event_type == "foster_child":
            current_is_parent = (
                self.direction_value.get() == "Current person is foster parent"
            )
            values["foster_parent_person_ids"] = [
                current_id if current_is_parent else self.selected_person_id
            ]
            values["foster_child_person_ids"] = [
                self.selected_person_id if current_is_parent else current_id
            ]

        try:
            if self.event:
                saved = self.event_controller.update_event(
                    self.event["record_id"],
                    values,
                )
            else:
                saved = self.event_controller.create_event(values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save relationship event",
                str(error),
                parent=self,
            )
            return

        self.saved_command(saved)
        self.destroy()
