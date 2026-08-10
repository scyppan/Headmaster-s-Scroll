import tkinter as tk
from copy import deepcopy

from mage_maker.sections.events.types import canonical_event_type
from mage_maker.sections.family_tree.relationships import FamilyRelationshipMap
from mage_maker.sections.family_tree.spouse_relationships import (
    normalize_spouse_relationships,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    FIELD_BACKGROUND,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class FamousConnectionMap:
    def __init__(self, people, current_person=None, events=None):
        self.relationships = FamilyRelationshipMap(people, current_person)
        self.events = [
            deepcopy(event)
            for event in events or []
            if isinstance(event, dict)
        ]

    def labels_for(self, record_id):
        normalized_id = str(record_id or "")
        ranked_labels = []
        famous_people = [
            person
            for person in self.relationships.people_by_id.values()
            if bool(person.get("famous_person"))
            and str(person.get("record_id", "")) != normalized_id
        ]
        famous_people.sort(key=self.person_name_sort_key)

        for famous_person in famous_people:
            famous_id = str(famous_person.get("record_id", ""))
            relationship = self.relationship_to_famous(normalized_id, famous_id)

            if relationship:
                famous_name = str(
                    famous_person.get("displayed_name", "Unnamed") or "Unnamed"
                )
                if relationship in (
                    "Married",
                    "Married and divorced",
                    "Had a child with",
                    "Had a romance with",
                ):
                    label = f"{relationship} {famous_name}"
                else:
                    label = f"{relationship} of {famous_name}"

                priority = {
                    "Married": 0,
                    "Married and divorced": 0,
                    "Had a child with": 1,
                    "Had a romance with": 2,
                }.get(relationship, 3)
                ranked_labels.append(
                    (priority, famous_name.casefold(), label)
                )

        ranked_labels.sort()
        return [label for priority, name, label in ranked_labels]

    def person_name_sort_key(self, person):
        return str(person.get("displayed_name", "")).casefold()

    def relationship_to_famous(self, record_id, famous_id):
        person = self.relationships.person(record_id) or {}
        spouse_relationship = next(
            (
                relationship
                for relationship in normalize_spouse_relationships(
                    person.get("spouse_relationships", [])
                )
                if relationship["person_id"] == famous_id
                and relationship["married"]
            ),
            None,
        )
        marriage_event_exists = any(
            canonical_event_type(event.get("event_type")) == "got_married"
            and record_id in event.get("person_ids", [])
            and famous_id in event.get("person_ids", [])
            for event in self.events
        )

        if spouse_relationship is not None:
            return (
                "Married and divorced"
                if spouse_relationship["divorced"]
                else "Married"
            )

        if marriage_event_exists:
            return "Married"

        shared_children = set(
            self.relationships.children_of(record_id)
        ).intersection(self.relationships.children_of(famous_id))

        if shared_children:
            return "Had a child with"

        romance_exists = any(
            canonical_event_type(event.get("event_type"))
            in ("romance", "breakup")
            and record_id in event.get("person_ids", [])
            and famous_id in event.get("person_ids", [])
            for event in self.events
        )

        if romance_exists:
            return "Had a romance with"

        downward_distance = self.generation_distance(famous_id, record_id)

        if downward_distance == 1:
            return "Child"

        if downward_distance == 2:
            return "Grandchild"

        if downward_distance is not None and downward_distance > 2:
            return "Descendent"

        upward_distance = self.generation_distance(record_id, famous_id)

        if upward_distance == 1:
            return "Parent"

        if upward_distance == 2:
            return "Grandparent"

        if famous_id in self.relationships.siblings_of(record_id):
            return "Sibling"

        if self.is_step_parent(record_id, famous_id):
            return "Step parent"

        if self.is_aunt_or_uncle(record_id, famous_id):
            return "Pibbling"

        if self.is_cousin(record_id, famous_id):
            return "Cousin"

        return ""

    def generation_distance(self, ancestor_id, descendant_id):
        ancestor_id = str(ancestor_id or "")
        descendant_id = str(descendant_id or "")

        if not ancestor_id or not descendant_id or ancestor_id == descendant_id:
            return None

        pending = [(ancestor_id, 0)]
        visited = set()

        while pending:
            current_id, distance = pending.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)

            for child_id in self.relationships.children_of(current_id):
                if child_id == descendant_id:
                    return distance + 1

                pending.append((child_id, distance + 1))

        return None

    def is_step_parent(self, record_id, famous_id):
        step_parent_groups = self.relationships.step_parent_mates_of(famous_id)

        for step_parent_ids in step_parent_groups.values():
            if record_id in step_parent_ids:
                return True

        return False

    def is_aunt_or_uncle(self, record_id, famous_id):
        for parent_id in self.relationships.parents_of(famous_id):
            if record_id in self.relationships.siblings_of(parent_id):
                return True

        return False

    def is_cousin(self, record_id, famous_id):
        for first_parent_id in self.relationships.parents_of(record_id):
            for second_parent_id in self.relationships.parents_of(famous_id):
                if self.relationships.sibling_relation(
                    first_parent_id,
                    second_parent_id,
                ):
                    return True

        return False


class FamousConnectionsView(tk.Frame):
    def __init__(self, parent, background=SURFACE_MUTED, maximum_visible=3):
        super().__init__(parent, bg=background)
        self.background = background
        self.maximum_visible = maximum_visible
        self.connections = []
        self.grid_columnconfigure(0, weight=1)
        self.summary = tk.Label(
            self,
            text="",
            bg=background,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="nw",
            justify="left",
            padx=0,
            pady=1,
        )
        self.summary.grid(row=0, column=0, sticky="ew")
        self.summary.grid_remove()
        self.more_button = tk.Button(
            self,
            text="...",
            command=self.show_full_list,
            bg=background,
            fg=TEXT_DARK,
            activebackground=FIELD_BACKGROUND,
            activeforeground=TEXT_DARK,
            font=app_font(10, "bold"),
            relief="flat",
            borderwidth=0,
            cursor="hand2",
            padx=7,
            pady=2,
        )
        self.more_button.grid(row=1, column=0, sticky="w", pady=(3, 0))
        self.more_button.grid_remove()

    def set_connections(self, connections):
        self.connections = [
            str(connection).strip()
            for connection in connections or []
            if str(connection).strip()
        ]
        visible_connections = self.connections[: self.maximum_visible]

        if visible_connections:
            self.summary.configure(text="\n".join(visible_connections))
            self.summary.grid()
        else:
            self.summary.configure(text="")
            self.summary.grid_remove()

        if len(self.connections) > self.maximum_visible:
            self.more_button.grid()
        else:
            self.more_button.grid_remove()

    def show_full_list(self):
        FamousConnectionsDialog(self, deepcopy(self.connections))


class FamousConnectionsDialog(tk.Toplevel):
    def __init__(self, parent, connections):
        super().__init__(parent)
        self.title("Famous connections")
        self.geometry("460x360")
        self.minsize(380, 260)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=16,
            pady=16,
        )
        card.grid(row=0, column=0, sticky="nsew", padx=18, pady=18)
        card.grid_rowconfigure(1, weight=1)
        card.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            card,
            text="Famous connections",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(13, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        connection_list = tk.Listbox(
            card,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(10),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
        )
        connection_list.grid(row=1, column=0, sticky="nsew")

        for connection in connections:
            connection_list.insert("end", connection)

        scrollbar = tk.Scrollbar(card, command=connection_list.yview)
        scrollbar.grid(row=1, column=1, sticky="ns")
        connection_list.configure(yscrollcommand=scrollbar.set)
        self.bind("<Escape>", self.close_dialog)

    def close_dialog(self, event=None):
        self.destroy()
