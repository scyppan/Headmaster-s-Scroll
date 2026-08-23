import tkinter as tk
from copy import deepcopy

from mage_maker.core.dates import format_line_item_date
from mage_maker.sections.events.models import (
    event_linked_person_ids,
    normalize_association_values,
    normalize_world_event,
)
from mage_maker.sections.events.types import (
    canonical_event_type,
    event_type_label,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


EVENT_ROLE_OPTIONS = {
    "born": (
        ("birthing_parent_person_ids", "Birthing parent"),
        ("non_birthing_parent_person_ids", "Non-birthing parent"),
    ),
    "murder": (
        ("perpetrator_person_ids", "Perpetrator"),
        ("victim_person_ids", "Victim"),
        ("witness_person_ids", "Witness"),
        ("affected_person_ids", "Affected by the murder"),
    ),
    "died": (
        ("witness_person_ids", "Witness"),
        ("affected_person_ids", "Affected by the death"),
    ),
    "foster_child": (
        ("foster_parent_person_ids", "Foster parent"),
        ("foster_child_person_ids", "Foster child"),
    ),
}
DEFAULT_EVENT_ROLE_OPTIONS = (("person_ids", "Participant"),)


def event_role_options(event):
    event_values = event if isinstance(event, dict) else {}
    event_type = canonical_event_type(event_values.get("event_type"))
    return EVENT_ROLE_OPTIONS.get(event_type, DEFAULT_EVENT_ROLE_OPTIONS)


def person_event_role(event, person_id):
    normalized_person_id = str(person_id or "").strip()
    if not normalized_person_id:
        return ""

    for field_name, role_label in event_role_options(event):
        if normalized_person_id in normalize_association_values(
            (event or {}).get(field_name)
        ):
            return role_label

    if normalized_person_id in event_linked_person_ids(event):
        return "Participant"

    return ""


def link_person_to_event(event, person_id, role_field):
    event_values = deepcopy(event) if isinstance(event, dict) else {}
    normalized_person_id = str(person_id or "").strip()
    normalized_role_field = str(role_field or "").strip()
    valid_role_fields = {
        field_name for field_name, role_label in event_role_options(event_values)
    }

    if not normalized_person_id:
        raise ValueError("Choose a person to link.")
    if normalized_role_field not in valid_role_fields:
        raise ValueError("Choose a valid role for this event type.")

    existing_role = person_event_role(event_values, normalized_person_id)
    if existing_role:
        raise ValueError(
            f"This person is already linked as {existing_role}."
        )

    role_person_ids = normalize_association_values(
        event_values.get(normalized_role_field)
    )
    role_person_ids.append(normalized_person_id)
    event_values[normalized_role_field] = role_person_ids
    return normalize_world_event(event_values)


class EventLinkDialog(tk.Toplevel):
    """Choose another person, one of their events, and the active role."""

    def __init__(
        self,
        parent,
        people_options,
        current_person_id,
        current_person_name,
        events_provider,
        save_command,
    ):
        super().__init__(parent)
        self.current_person_id = str(current_person_id or "").strip()
        self.current_person_name = str(
            current_person_name or "Current person"
        ).strip()
        self.events_provider = events_provider
        self.save_command = save_command
        self.people_options = sorted(
            [
                deepcopy(option)
                for option in people_options or ()
                if isinstance(option, dict)
                and str(option.get("record_id", "") or "").strip()
                and str(option.get("record_id", "") or "").strip()
                != self.current_person_id
            ],
            key=lambda option: str(
                option.get("displayed_name", "")
                or option.get("name", "")
                or ""
            ).casefold(),
        )
        self.visible_people = []
        self.visible_events = []
        self.person_events = []
        self.selected_person_id = ""
        self.selected_event = None
        self.role_buttons = []
        self.search_value = tk.StringVar()
        self.event_search_value = tk.StringVar()
        self.role_value = tk.StringVar()
        self.status_value = tk.StringVar(
            value="Choose a person to see their events."
        )

        self.title("Link to another event")
        self.geometry("920x650")
        self.minsize(760, 520)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.refresh_people)
        self.event_search_value.trace_add("write", self.refresh_events)
        self.refresh_people()
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)

    @staticmethod
    def person_name(person):
        return str(
            person.get("displayed_name", "")
            or person.get("name", "")
            or "Unnamed person"
        ).strip()

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=18,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        card.grid_rowconfigure(2, weight=1)
        card.grid_columnconfigure(0, weight=2, uniform="link-event")
        card.grid_columnconfigure(1, weight=3, uniform="link-event")

        heading = tk.Label(
            card,
            text=f"Link {self.current_person_name} to an existing event",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(14, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, columnspan=2, sticky="ew")
        explanation = tk.Label(
            card,
            text=(
                "Find a person, choose one of their events, then choose "
                "the role appropriate to that event type."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        explanation.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(4, 12),
        )

        people_panel = self.build_people_panel(card)
        people_panel.grid(row=2, column=0, sticky="nsew", padx=(0, 7))
        event_panel = self.build_event_panel(card)
        event_panel.grid(row=2, column=1, sticky="nsew", padx=(7, 0))

        status = tk.Label(
            card,
            textvariable=self.status_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        status.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(11, 0),
        )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 0),
        )
        footer.grid_columnconfigure(0, weight=1)
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=92,
            height=34,
        )
        cancel_button.grid(row=0, column=1, padx=(0, 7))
        self.link_button = SoftButton(
            footer,
            text="Link event",
            command=self.save_link,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=34,
        )
        self.link_button.grid(row=0, column=2)
        self.link_button.set_enabled(False)

    def build_people_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        tk.Label(
            panel,
            text="1. Person",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        search = RoundedEntry(
            panel,
            textvariable=self.search_value,
            background=SURFACE_MUTED,
            height=36,
            font=app_font(10),
        )
        search.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        people_frame = tk.Frame(panel, bg=FIELD_BACKGROUND)
        people_frame.grid(row=2, column=0, sticky="nsew")
        people_frame.grid_rowconfigure(0, weight=1)
        people_frame.grid_columnconfigure(0, weight=1)
        self.people_list = tk.Listbox(
            people_frame,
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
        self.people_list.grid(row=0, column=0, sticky="nsew")
        self.people_list.bind("<<ListboxSelect>>", self.person_selected)
        people_scroll = tk.Scrollbar(
            people_frame,
            command=self.people_list.yview,
        )
        people_scroll.grid(row=0, column=1, sticky="ns")
        self.people_list.configure(yscrollcommand=people_scroll.set)
        return panel

    def build_event_panel(self, parent):
        panel = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        panel.grid_rowconfigure(2, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        tk.Label(
            panel,
            text="2. Event and role",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        self.event_search = RoundedEntry(
            panel,
            textvariable=self.event_search_value,
            background=SURFACE_MUTED,
            height=36,
            font=app_font(10),
        )
        self.event_search.grid(row=1, column=0, sticky="ew", pady=(8, 8))
        events_frame = tk.Frame(panel, bg=FIELD_BACKGROUND)
        events_frame.grid(row=2, column=0, sticky="nsew")
        events_frame.grid_rowconfigure(0, weight=1)
        events_frame.grid_columnconfigure(0, weight=1)
        self.events_list = tk.Listbox(
            events_frame,
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
        self.events_list.grid(row=0, column=0, sticky="nsew")
        self.events_list.bind("<<ListboxSelect>>", self.event_selected)
        events_scroll = tk.Scrollbar(
            events_frame,
            command=self.events_list.yview,
        )
        events_scroll.grid(row=0, column=1, sticky="ns")
        self.events_list.configure(yscrollcommand=events_scroll.set)
        self.roles_panel = tk.Frame(panel, bg=SURFACE_MUTED)
        self.roles_panel.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        return panel

    def refresh_people(self, *arguments):
        query_terms = [
            term for term in self.search_value.get().casefold().split() if term
        ]
        self.visible_people = [
            person
            for person in self.people_options
            if all(
                term
                in " ".join(
                    str(value or "")
                    for value in (
                        self.person_name(person),
                        person.get("birth_year"),
                        person.get("school"),
                        person.get("group_name"),
                    )
                ).casefold()
                for term in query_terms
            )
        ]
        self.people_list.delete(0, "end")
        for person in self.visible_people:
            birth_year = person.get("birth_year")
            suffix = f" · Born {birth_year}" if birth_year is not None else ""
            self.people_list.insert(
                "end", f"{self.person_name(person)}{suffix}"
            )

    def person_selected(self, event=None):
        selection = self.people_list.curselection()
        if not selection or selection[0] >= len(self.visible_people):
            return
        person = self.visible_people[selection[0]]
        self.selected_person_id = str(
            person.get("record_id", "") or ""
        ).strip()
        self.selected_event = None
        self.role_value.set("")
        self.person_events = list(
            self.events_provider(self.selected_person_id) or ()
        )
        self.status_value.set(
            f"Choose one of {self.person_name(person)}'s events."
        )
        self.refresh_events()

    def refresh_events(self, *arguments):
        if not self.selected_person_id:
            candidate_events = []
        else:
            candidate_events = self.person_events
        query_terms = [
            term
            for term in self.event_search_value.get().casefold().split()
            if term
        ]
        self.visible_events = []
        for event in candidate_events or ():
            if not isinstance(event, dict):
                continue
            search_text = " ".join(
                str(value or "")
                for value in (
                    event_type_label(event),
                    event.get("title"),
                    event.get("description"),
                    event.get("date"),
                )
            ).casefold()
            if all(term in search_text for term in query_terms):
                self.visible_events.append(deepcopy(event))

        self.events_list.delete(0, "end")
        for event in self.visible_events:
            date_label = format_line_item_date(event.get("date"))
            title = str(event.get("title", "") or event_type_label(event))
            existing_role = person_event_role(
                event, self.current_person_id
            )
            role_suffix = (
                f" · Already linked as {existing_role}"
                if existing_role
                else ""
            )
            self.events_list.insert(
                "end", f"{date_label} · {title}{role_suffix}"
            )
        self.clear_roles()

    def clear_roles(self):
        for child in self.roles_panel.winfo_children():
            child.destroy()
        self.role_buttons = []
        self.selected_event = None
        self.role_value.set("")
        self.link_button.set_enabled(False)

    def event_selected(self, event=None):
        selection = self.events_list.curselection()
        if not selection or selection[0] >= len(self.visible_events):
            self.clear_roles()
            return
        self.selected_event = self.visible_events[selection[0]]
        for child in self.roles_panel.winfo_children():
            child.destroy()
        self.role_buttons = []
        existing_role = person_event_role(
            self.selected_event,
            self.current_person_id,
        )
        if existing_role:
            self.role_value.set("")
            self.status_value.set(
                f"{self.current_person_name} is already linked as "
                f"{existing_role}."
            )
            self.link_button.set_enabled(False)
            return

        roles = event_role_options(self.selected_event)
        self.role_value.set(roles[0][0] if len(roles) == 1 else "")
        tk.Label(
            self.roles_panel,
            text="Role",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="w")
        for index, (field_name, role_label) in enumerate(roles, start=1):
            button = tk.Radiobutton(
                self.roles_panel,
                text=role_label,
                variable=self.role_value,
                value=field_name,
                command=self.role_selected,
                bg=SURFACE_MUTED,
                fg=TEXT_DARK,
                activebackground=SURFACE_MUTED,
                activeforeground=TEXT_DARK,
                selectcolor=FIELD_BACKGROUND,
                font=app_font(9),
                cursor="hand2",
            )
            button.grid(
                row=1 + ((index - 1) // 2),
                column=(index - 1) % 2,
                sticky="w",
                padx=(0, 12),
            )
            self.role_buttons.append(button)
        self.status_value.set(
            "Choose the role for this event."
            if len(roles) > 1
            else f"Role: {roles[0][1]}"
        )
        self.link_button.set_enabled(bool(self.role_value.get()))

    def role_selected(self):
        selected_role = self.role_value.get()
        role_label = next(
            (
                label
                for field_name, label in event_role_options(
                    self.selected_event
                )
                if field_name == selected_role
            ),
            "",
        )
        self.status_value.set(
            f"Link {self.current_person_name} as {role_label}."
        )
        self.link_button.set_enabled(bool(selected_role))

    def save_link(self):
        if self.selected_event is None or not self.role_value.get():
            return False
        saved = self.save_command(
            str(self.selected_event.get("record_id", "") or ""),
            self.role_value.get(),
        )
        if saved is False:
            return False
        self.close_dialog()
        return True

    def close_dialog(self, event=None):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        return "break"
