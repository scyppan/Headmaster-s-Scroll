import tkinter as tk
from copy import deepcopy

from mage_maker.core.dates import format_date_parts
from mage_maker.sections.events.models import world_event_sort_key
from mage_maker.sections.events.types import canonical_event_type
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
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class RelationshipsView(tk.Frame):
    def __init__(
        self,
        parent,
        people_provider=None,
        event_controller=None,
        navigate_command=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.people_provider = people_provider
        self.event_controller = event_controller
        self.navigate_command = navigate_command
        self.person = {}
        self.visible_relationships = []
        self.summary_value = tk.StringVar(value="No person selected")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_view()

    def build_view(self):
        heading = tk.Label(
            self,
            text="Relationships",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 6))
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
        scrollbar = tk.Scrollbar(
            list_frame,
            command=self.relationship_list.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.relationship_list.configure(yscrollcommand=scrollbar.set)

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
            ):
                continue

            if person_id not in event.get("person_ids", []):
                continue

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
            }[event_type]
            rows.append(
                {
                    "kind": event_type,
                    "date": str(event.get("date", "") or ""),
                    "time": event_time,
                    "record_id": str(
                        event.get("record_id", "") or ""
                    ),
                    "person_ids": other_ids,
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
