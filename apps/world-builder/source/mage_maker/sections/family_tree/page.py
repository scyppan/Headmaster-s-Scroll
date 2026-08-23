import tkinter as tk
from copy import deepcopy
from functools import partial
from tkinter import messagebox

from mage_maker.sections.development.initial_values import (
    PARENT_MAGIC_STATE_NON_MAGICAL,
    allowed_parent_magic_states,
    parent_candidate_explanation,
    person_magic_state,
)
from mage_maker.sections.family_tree.child_dialog import AddChildDialog
from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
    format_person_date,
    maiden_name_for,
    person_birth_sort_key,
    person_can_give_birth,
)
from mage_maker.sections.family_tree.relationship_picker import (
    ParentCouplePickerDialog,
    RelationshipPickerDialog,
)
from mage_maker.sections.family_tree.spouse_candidates import (
    integer_year,
    spouse_candidates,
)
from mage_maker.sections.family_tree.spouse_dialog import SpousePickerDialog
from mage_maker.sections.family_tree.spouse_relationships import (
    empty_spouse_relationship,
    merge_mate_ids,
    normalize_spouse_relationships,
    relationship_ids,
)
from mage_maker.sections.timeline.locations import ParentLocationConflict
from mage_maker.ui.theme import (
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FAMILY_GREEN,
    FAMILY_CHILD_FADED_FILL,
    FAMILY_CHILD_FADED_LINE,
    FAMILY_CHILD_FADED_MUTED,
    FAMILY_CHILD_FADED_OUTLINE,
    FAMILY_CHILD_FADED_TEXT,
    FAMILY_GREEN_DARK,
    FAMILY_GREEN_FADED,
    FAMILY_LINE,
    FAMILY_STEP_ACTIVE,
    FAMILY_STEP_DARK,
    FAMILY_STEP_FADED,
    FAMILY_STEP_FILL,
    FIELD_BACKGROUND,
    PRIMARY,
    PRIMARY_HOVER,
    PRIMARY_SOFT,
    SURFACE,
    SURFACE_MUTED,
    SURFACE_RAISED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SoftButton, rounded_points


class FamilyTreeView(tk.Frame):
    generation_labels = (
        "Grandparents",
        "Parents · pibblings",
        "Selected · siblings · cousins",
        "Children · nibblings",
        "Grandchildren",
    )

    def __init__(
        self,
        parent,
        change_command,
        people_provider,
        create_person_command,
        update_person_command,
        refresh_people_command,
        navigate_command,
        locations_provider=None,
        create_location_command=None,
        event_provider=None,
        school_records_provider=None,
    ):
        super().__init__(parent, bg=SURFACE)
        self.change_command = change_command
        self.people_provider = people_provider
        self.create_person_command = create_person_command
        self.update_person_command = update_person_command
        self.refresh_people_command = refresh_people_command
        self.navigate_command = navigate_command
        self.locations_provider = locations_provider
        self.create_location_command = create_location_command
        self.event_provider = event_provider
        self.school_records_provider = school_records_provider
        self.current_person = {}
        self.people = []
        self.relationship_map = FamilyRelationshipMap([])
        self.mother_id = ""
        self.father_id = ""
        self.mother_status = "unknown"
        self.father_status = "unknown"
        self.mate_ids = []
        self.spouse_relationships = []
        self.active_mate_id = None
        self.active_spouse_owner_id = None
        self.spouse_picker_dialog = None
        self.node_coordinates = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_toolbar()

        self.canvas = tk.Canvas(
            self,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
        )
        self.canvas.grid(row=1, column=0, sticky="nsew")
        self.canvas.bind("<Configure>", self.resize_graph)

    def build_toolbar(self):
        toolbar = tk.Frame(self, bg=SURFACE, height=46)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        toolbar.grid_propagate(False)
        toolbar.grid_columnconfigure(0, weight=1)

        heading = tk.Label(
            toolbar,
            text="Five-generation family graph",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="nsew")

        self.remove_mother_button = SoftButton(
            toolbar,
            text="Unlink birthing",
            command=partial(self.remove_parent, "mother"),
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=36,
        )
        self.remove_mother_button.grid(row=0, column=1, padx=(6, 0), pady=5)

        self.remove_father_button = SoftButton(
            toolbar,
            text="Unlink non-birthing",
            command=partial(self.remove_parent, "father"),
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=150,
            height=36,
        )
        self.remove_father_button.grid(row=0, column=2, padx=(6, 0), pady=5)

        self.add_parent_couple_button = SoftButton(
            toolbar,
            text="Parents…",
            command=self.open_parent_couple_picker,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=86,
            height=36,
        )
        self.add_parent_couple_button.grid(
            row=0, column=3, padx=(6, 0), pady=5
        )

        self.add_mate_button = SoftButton(
            toolbar,
            text="Add spouse",
            command=self.open_mate_picker,
            background=SURFACE,
            fill=FAMILY_GREEN,
            hover_fill=FAMILY_GREEN_FADED,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        self.add_mate_button.grid(row=0, column=4, padx=(6, 0), pady=5)

        self.remove_mate_button = SoftButton(
            toolbar,
            text="Remove spouse",
            command=self.remove_active_mate,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=122,
            height=36,
        )
        self.remove_mate_button.grid(row=0, column=6, padx=(6, 0), pady=5)

        self.add_child_button = SoftButton(
            toolbar,
            text="Add child",
            command=self.open_add_child_dialog,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=102,
            height=36,
        )
        self.add_child_button.grid(row=0, column=7, padx=(6, 0), pady=5)

        self.add_spouse_child_button = SoftButton(
            toolbar,
            text="Child +",
            command=self.open_add_child_with_spouse,
            background=SURFACE,
            fill=FAMILY_GREEN,
            hover_fill=FAMILY_GREEN_FADED,
            foreground=TEXT_DARK,
            width=74,
            height=36,
        )
        self.add_spouse_child_button.grid(
            row=0, column=5, padx=(6, 0), pady=5
        )

    def set_person(self, person, redraw=True):
        previous_record_id = str(
            self.current_person.get("record_id", "") or ""
        )
        next_record_id = str(
            (person or {}).get("record_id", "")
            if isinstance(person, dict)
            else ""
        )

        if previous_record_id != next_record_id:
            self.close_spouse_picker()

        self.current_person = deepcopy(person) if isinstance(person, dict) else {}
        current_record_id = str(
            self.current_person.get("record_id", "") or ""
        )
        self.mother_id = str(
            self.current_person.get("biological_mother_id", "") or ""
        ).strip()
        self.father_id = str(
            self.current_person.get("biological_father_id", "") or ""
        ).strip()
        self.mother_status = self.normalized_parent_status(
            self.mother_id,
            self.current_person.get("biological_mother_status", "unknown"),
        )
        self.father_status = self.normalized_parent_status(
            self.father_id,
            self.current_person.get("biological_father_status", "unknown"),
        )
        self.spouse_relationships = merge_mate_ids(
            self.current_person.get("spouse_relationships", []),
            self.current_person.get("mate_ids", []),
        )
        self.mate_ids = relationship_ids(self.spouse_relationships)

        if previous_record_id != current_record_id:
            self.active_mate_id = None
            self.active_spouse_owner_id = None
        elif self.active_spouse_owner_id == current_record_id and (
            self.active_mate_id not in self.mate_ids
        ):
            self.active_mate_id = None
            self.active_spouse_owner_id = None

        self.reload_people(redraw=redraw)

    def update_current_person(self, values):
        if not isinstance(values, dict):
            return

        self.current_person.update(deepcopy(values))
        self.current_person["biological_mother_id"] = self.mother_id
        self.current_person["biological_father_id"] = self.father_id
        self.current_person["biological_mother_status"] = self.mother_status
        self.current_person["biological_father_status"] = self.father_status
        self.current_person["mate_ids"] = list(self.mate_ids)
        self.current_person["spouse_relationships"] = deepcopy(
            self.spouse_relationships
        )
        self.reload_people()

    def get_relationship_values(self):
        return {
            "biological_mother_id": self.mother_id,
            "biological_father_id": self.father_id,
            "biological_mother_status": self.mother_status,
            "biological_father_status": self.father_status,
            "mate_ids": list(self.mate_ids),
            "spouse_relationships": deepcopy(self.spouse_relationships),
        }

    def reload_people(self, redraw=True, refresh_provider=True):
        # Most relationship edits only change the selected person's links.
        # Re-querying every person summary after each click is expensive on a
        # large world and is unnecessary because the family map already owns
        # the summaries required to redraw the graph.
        if refresh_provider or not self.people:
            self.people = self.people_provider()
        self.current_person["biological_mother_id"] = self.mother_id
        self.current_person["biological_father_id"] = self.father_id
        self.current_person["biological_mother_status"] = self.mother_status
        self.current_person["biological_father_status"] = self.father_status
        self.current_person["mate_ids"] = list(self.mate_ids)
        self.current_person["spouse_relationships"] = deepcopy(
            self.spouse_relationships
        )
        self.relationship_map = FamilyRelationshipMap(
            self.people,
            self.current_person,
            foster_events=(
                self.event_provider(
                    self.current_person.get("record_id", "")
                )
                if callable(self.event_provider)
                and self.current_person.get("record_id")
                else ()
            ),
        )
        self.update_add_child_control()

        if redraw:
            self.redraw_graph()

    def update_add_child_control(self):
        can_add_child = bool(self.current_person.get("record_id")) and not bool(
            self.current_person.get("does_not_have_children")
        )
        self.add_child_button.set_enabled(can_add_child)
        self.add_parent_couple_button.set_enabled(
            bool(self.current_person.get("record_id"))
        )
        self.add_spouse_child_button.set_enabled(
            can_add_child and bool(self.valid_child_spouses())
        )

    def resize_graph(self, event=None):
        self.redraw_graph()

    def redraw_graph(self):
        if not hasattr(self, "canvas"):
            return

        width = max(640, self.canvas.winfo_width())
        height = max(480, self.canvas.winfo_height())
        self.canvas.delete("all")
        self.node_coordinates = {}

        focus_id = str(self.current_person.get("record_id", "") or "")

        if not focus_id:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="Select a magician to view their family graph.",
                fill=TEXT_MUTED,
                font=app_font(11),
            )
            return

        generations = self.relationship_map.build_generations(focus_id)
        generations[1] = self.add_missing_parent_nodes(generations[1])
        lane_height = height / 5
        label_width = 154
        graph_left = label_width + 10
        graph_right = width - 12
        visible_generations = []

        for row_index, label_text in enumerate(self.generation_labels):
            lane_top = row_index * lane_height
            lane_bottom = (row_index + 1) * lane_height
            lane_fill = SURFACE_MUTED if row_index % 2 == 0 else SURFACE_RAISED
            self.canvas.create_rectangle(
                0,
                lane_top,
                width,
                lane_bottom,
                fill=lane_fill,
                outline="",
            )
            self.canvas.create_text(
                14,
                (lane_top + lane_bottom) / 2,
                text=label_text,
                fill=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
                width=label_width - 22,
            )
            visible_nodes = self.select_visible_nodes(
                generations[row_index],
                row_index,
                graph_left,
                graph_right,
                focus_id,
            )
            visible_generations.append(visible_nodes)

            hidden_count = len(generations[row_index]) - len(visible_nodes)

            if hidden_count > 0:
                self.canvas.create_text(
                    graph_right - 4,
                    lane_bottom - 10,
                    text=f"+{hidden_count} more",
                    fill=TEXT_MUTED,
                    font=app_font(8, "bold"),
                    anchor="e",
                )

        for row_index in (1, 0, 2, 3, 4):
            lane_top = row_index * lane_height
            lane_bottom = (row_index + 1) * lane_height
            positions = self.positions_for_row(
                visible_generations[row_index],
                row_index,
                graph_left,
                graph_right,
                (lane_top + lane_bottom) / 2,
                focus_id,
            )

            for (
                node,
                x_position,
                y_position,
                node_width,
                node_height,
            ) in positions:
                record_id = str(node["person"].get("record_id", ""))
                self.node_coordinates[record_id] = (
                    x_position,
                    y_position,
                    node_width,
                    node_height,
                )

        self.draw_relationship_lines(visible_generations)

        for row_index, nodes in enumerate(visible_generations):
            for node in nodes:
                self.draw_person_node(node, row_index, focus_id)

        self.draw_spouse_flags(focus_id)
        self.remove_mother_button.set_enabled(
            bool(self.mother_id) or self.mother_status == "muggle"
        )
        self.remove_father_button.set_enabled(
            bool(self.father_id) or self.father_status == "muggle"
        )
        self.remove_mate_button.set_enabled(
            self.active_mate_id is not None
            and self.active_spouse_owner_id == focus_id
        )

    def add_missing_parent_nodes(self, parent_nodes):
        nodes = list(parent_nodes)
        relation_names = {node.get("relation") for node in nodes}

        if not self.mother_id and "Birthing parent" not in relation_names:
            nodes.append(
                {
                    "person": {
                        "record_id": "__select_mother__",
                        "displayed_name": (
                            "Unknown Muggle"
                            if self.mother_status == "muggle"
                            else "Unknown"
                        ),
                    },
                    "relation": "Birthing parent",
                    "placeholder": True,
                }
            )

        if not self.father_id and "Non-birthing parent" not in relation_names:
            nodes.append(
                {
                    "person": {
                        "record_id": "__select_father__",
                        "displayed_name": (
                            "Unknown Muggle"
                            if self.father_status == "muggle"
                            else "Unknown"
                        ),
                    },
                    "relation": "Non-birthing parent",
                    "placeholder": True,
                }
            )

        return self.order_parent_nodes(nodes)

    def order_parent_nodes(self, nodes):
        relation_order = {
            "Birthing parent's pibbling": 0,
            "Birthing parent": 1,
            "Non-birthing parent": 2,
            "Non-birthing parent's pibbling": 3,
            "Pibbling": 4,
        }
        return sorted(nodes, key=lambda node: relation_order.get(node["relation"], 5))

    def select_visible_nodes(
        self,
        nodes,
        row_index,
        graph_left,
        graph_right,
        focus_id,
    ):
        available_width = max(360, graph_right - graph_left)
        maximum_nodes = (
            max(3, min(9, int(available_width // 132)))
            if row_index == 1
            else max(3, min(7, int(available_width // 142)))
        )

        if len(nodes) <= maximum_nodes:
            return list(nodes)

        if row_index == 1:
            birthing_parent_indexes = [
                index
                for index, node in enumerate(nodes)
                if node.get("relation") == "Birthing parent"
            ]
            non_birthing_parent_indexes = [
                index
                for index, node in enumerate(nodes)
                if node.get("relation") == "Non-birthing parent"
            ]
            birthing_pibbling_indexes = [
                index
                for index, node in enumerate(nodes)
                if node.get("relation") == "Birthing parent's pibbling"
            ]
            non_birthing_pibbling_indexes = [
                index
                for index, node in enumerate(nodes)
                if node.get("relation") == "Non-birthing parent's pibbling"
            ]
            ungrouped_indexes = [
                index
                for index, node in enumerate(nodes)
                if node.get("relation")
                not in (
                    "Birthing parent",
                    "Non-birthing parent",
                    "Birthing parent's pibbling",
                    "Non-birthing parent's pibbling",
                )
            ]
            selected_indexes = set(
                birthing_parent_indexes + non_birthing_parent_indexes
            )
            remaining_slots = max(0, maximum_nodes - len(selected_indexes))
            birthing_cursor = len(birthing_pibbling_indexes) - 1
            non_birthing_cursor = 0

            while remaining_slots > 0 and (
                birthing_cursor >= 0
                or non_birthing_cursor < len(non_birthing_pibbling_indexes)
            ):
                if birthing_cursor >= 0:
                    selected_indexes.add(
                        birthing_pibbling_indexes[birthing_cursor]
                    )
                    birthing_cursor -= 1
                    remaining_slots -= 1

                if (
                    remaining_slots > 0
                    and non_birthing_cursor
                    < len(non_birthing_pibbling_indexes)
                ):
                    selected_indexes.add(
                        non_birthing_pibbling_indexes[
                            non_birthing_cursor
                        ]
                    )
                    non_birthing_cursor += 1
                    remaining_slots -= 1

            for index in ungrouped_indexes:
                if remaining_slots <= 0:
                    break

                selected_indexes.add(index)
                remaining_slots -= 1

            return [
                node
                for index, node in enumerate(nodes)
                if index in selected_indexes
            ]

        relation_priority = {
            "Selected person": 0,
            "Birthing parent": 0,
            "Non-birthing parent": 0,
            "Child": 0,
            "Sibling": 1,
            "1/2 Sibling": 1,
            "Grandparent": 1,
            "Grandchild": 1,
            "Birthing parent's pibbling": 2,
            "Non-birthing parent's pibbling": 2,
            "Nibbling": 3,
            "Birthing parent's cousin": 4,
            "Non-birthing parent's cousin": 4,
            "Cousin": 4,
        }
        ranked_nodes = sorted(
            enumerate(nodes),
            key=lambda item: (
                relation_priority.get(item[1].get("relation"), 5),
                item[0],
            ),
        )[:maximum_nodes]
        selected_indexes = {item[0] for item in ranked_nodes}
        return [node for index, node in enumerate(nodes) if index in selected_indexes]

    def positions_for_row(
        self,
        nodes,
        row_index,
        graph_left,
        graph_right,
        y_position,
        focus_id,
    ):
        if not nodes:
            return []

        center_x = (graph_left + graph_right) / 2

        if row_index == 0:
            anchored_groups = {}
            unanchored_nodes = []

            for node in nodes:
                record_id = str(
                    node["person"].get("record_id", "") or ""
                ).strip()
                visible_child_ids = [
                    child_id
                    for child_id in self.relationship_map.children_of(
                        record_id
                    )
                    if child_id in self.node_coordinates
                ]

                if visible_child_ids:
                    anchor_id = min(
                        visible_child_ids,
                        key=lambda child_id: abs(
                            self.node_coordinates[child_id][0] - center_x
                        ),
                    )
                    anchored_groups.setdefault(anchor_id, []).append(node)
                else:
                    unanchored_nodes.append(node)

            card_gap = 10
            node_width = min(
                132,
                max(
                    70,
                    (
                        graph_right
                        - graph_left
                        - card_gap * max(0, len(nodes) - 1)
                    )
                    / max(1, len(nodes)),
                ),
            )
            desired_positions = []

            for anchor_id, group_nodes in sorted(
                anchored_groups.items(),
                key=lambda item: self.node_coordinates[item[0]][0],
            ):
                anchor_x = self.node_coordinates[anchor_id][0]
                group_width = (
                    node_width * len(group_nodes)
                    + card_gap * max(0, len(group_nodes) - 1)
                )
                group_start = (
                    anchor_x - group_width / 2 + node_width / 2
                )

                for group_index, node in enumerate(group_nodes):
                    desired_positions.append(
                        (
                            node,
                            group_start
                            + group_index * (node_width + card_gap),
                        )
                    )

            unanchored_width = (
                node_width * len(unanchored_nodes)
                + card_gap * max(0, len(unanchored_nodes) - 1)
            )
            unanchored_start = (
                center_x - unanchored_width / 2 + node_width / 2
            )

            for node_index, node in enumerate(unanchored_nodes):
                desired_positions.append(
                    (
                        node,
                        unanchored_start
                        + node_index * (node_width + card_gap),
                    )
                )

            desired_positions.sort(key=lambda item: item[1])
            minimum_x = graph_left + node_width / 2
            maximum_x = graph_right - node_width / 2
            bounded_positions = []

            for node, desired_x in desired_positions:
                x_position = max(minimum_x, desired_x)

                if bounded_positions:
                    x_position = max(
                        x_position,
                        bounded_positions[-1][1]
                        + node_width
                        + card_gap,
                    )

                bounded_positions.append([node, x_position])

            if bounded_positions and bounded_positions[-1][1] > maximum_x:
                overflow = bounded_positions[-1][1] - maximum_x

                for positioned_node in bounded_positions:
                    positioned_node[1] -= overflow

            for index in range(len(bounded_positions) - 2, -1, -1):
                bounded_positions[index][1] = min(
                    bounded_positions[index][1],
                    bounded_positions[index + 1][1]
                    - node_width
                    - card_gap,
                )

            return [
                (node, x_position, y_position, node_width, 64)
                for node, x_position in bounded_positions
            ]

        if row_index == 1:
            birthing_parent_node = None
            non_birthing_parent_node = None
            birthing_pibbling_nodes = []
            non_birthing_pibbling_nodes = []
            ungrouped_nodes = []

            for node in nodes:
                relation = str(node.get("relation", "") or "")

                if relation == "Birthing parent":
                    birthing_parent_node = node
                elif relation == "Non-birthing parent":
                    non_birthing_parent_node = node
                elif relation == "Birthing parent's pibbling":
                    birthing_pibbling_nodes.append(node)
                elif relation == "Non-birthing parent's pibbling":
                    non_birthing_pibbling_nodes.append(node)
                else:
                    ungrouped_nodes.append(node)

            for node in ungrouped_nodes:
                if len(birthing_pibbling_nodes) <= len(
                    non_birthing_pibbling_nodes
                ):
                    birthing_pibbling_nodes.insert(0, node)
                else:
                    non_birthing_pibbling_nodes.append(node)

            if (
                birthing_parent_node is not None
                and non_birthing_parent_node is not None
            ):
                parent_gap = 12
                pibbling_gap = 28
                card_gap = 8
                half_width = (graph_right - graph_left) / 2
                node_width = 132

                if birthing_pibbling_nodes:
                    birthing_width = (
                        half_width
                        - parent_gap / 2
                        - pibbling_gap
                        - card_gap
                        * max(0, len(birthing_pibbling_nodes) - 1)
                    ) / (len(birthing_pibbling_nodes) + 1)
                    node_width = min(node_width, birthing_width)

                if non_birthing_pibbling_nodes:
                    non_birthing_width = (
                        half_width
                        - parent_gap / 2
                        - pibbling_gap
                        - card_gap
                        * max(0, len(non_birthing_pibbling_nodes) - 1)
                    ) / (len(non_birthing_pibbling_nodes) + 1)
                    node_width = min(node_width, non_birthing_width)

                node_width = max(64, min(132, node_width))
                parent_spacing = node_width + parent_gap
                pibbling_spacing = node_width + card_gap
                birthing_parent_x = center_x - parent_spacing / 2
                non_birthing_parent_x = center_x + parent_spacing / 2
                positions = [
                    (
                        birthing_parent_node,
                        birthing_parent_x,
                        y_position,
                        node_width,
                        64,
                    ),
                    (
                        non_birthing_parent_node,
                        non_birthing_parent_x,
                        y_position,
                        node_width,
                        64,
                    ),
                ]
                birthing_x = (
                    birthing_parent_x
                    - node_width
                    - pibbling_gap
                )

                for node in reversed(birthing_pibbling_nodes):
                    positions.append(
                        (node, birthing_x, y_position, node_width, 64)
                    )
                    birthing_x -= pibbling_spacing

                non_birthing_x = (
                    non_birthing_parent_x
                    + node_width
                    + pibbling_gap
                )

                for node in non_birthing_pibbling_nodes:
                    positions.append(
                        (node, non_birthing_x, y_position, node_width, 64)
                    )
                    non_birthing_x += pibbling_spacing

                return positions

        if row_index == 2:
            # Keep the whole sibling/cousin generation in chronological
            # order.  The selected person is a highlight, not an anchor:
            # centering them used to move older siblings from one side to the
            # other whenever the user changed profiles.
            ordered_nodes = sorted(
                nodes,
                key=lambda node: person_birth_sort_key(
                    node.get("person", {})
                ),
            )
            card_gap = 12
            available_width = max(1, graph_right - graph_left)
            node_width = min(
                132,
                max(
                    68,
                    (
                        available_width
                        - card_gap * max(0, len(ordered_nodes) - 1)
                    ) / max(1, len(ordered_nodes)),
                ),
            )
            total_width = (
                node_width * len(ordered_nodes)
                + card_gap * max(0, len(ordered_nodes) - 1)
            )
            start_x = center_x - total_width / 2 + node_width / 2
            return [
                (
                    node,
                    start_x + index * (node_width + card_gap),
                    y_position,
                    node_width,
                    64,
                )
                for index, node in enumerate(ordered_nodes)
            ]

            # Retained below only as historical context for the former
            # selected-person-centred grouping algorithm.
            focus_node = None
            full_sibling_nodes = []
            birthing_half_sibling_nodes = []
            non_birthing_half_sibling_nodes = []
            birthing_relative_nodes = []
            non_birthing_relative_nodes = []
            ungrouped_nodes = []
            focus_person = self.relationship_map.person(focus_id) or {}
            birthing_parent_id = str(
                focus_person.get("biological_mother_id", "") or ""
            ).strip()
            non_birthing_parent_id = str(
                focus_person.get("biological_father_id", "") or ""
            ).strip()

            for node in nodes:
                record_id = str(
                    node["person"].get("record_id", "") or ""
                )
                relation = str(node.get("relation", "") or "")

                if record_id == focus_id:
                    focus_node = node
                elif relation == "Sibling":
                    full_sibling_nodes.append(node)
                elif relation == "1/2 Sibling":
                    parent_ids = set(
                        self.relationship_map.parents_of(record_id)
                    )

                    if birthing_parent_id in parent_ids:
                        birthing_half_sibling_nodes.append(node)
                    elif non_birthing_parent_id in parent_ids:
                        non_birthing_half_sibling_nodes.append(node)
                    else:
                        ungrouped_nodes.append(node)
                elif relation == "Birthing parent's cousin":
                    birthing_relative_nodes.append(node)
                elif relation == "Non-birthing parent's cousin":
                    non_birthing_relative_nodes.append(node)
                else:
                    ungrouped_nodes.append(node)

            if focus_node is None:
                spacing = min(
                    150,
                    (graph_right - graph_left) / max(1, len(nodes)),
                )
                total_width = spacing * (len(nodes) - 1)
                start_x = center_x - total_width / 2
                return [
                    (
                        node,
                        start_x + index * spacing,
                        y_position,
                        132,
                        64,
                    )
                    for index, node in enumerate(nodes)
                ]

            left_full_count = (len(full_sibling_nodes) + 1) // 2
            left_full_nodes = full_sibling_nodes[:left_full_count]
            right_full_nodes = full_sibling_nodes[left_full_count:]

            for node in ungrouped_nodes:
                left_count = (
                    len(left_full_nodes)
                    + len(birthing_half_sibling_nodes)
                    + len(birthing_relative_nodes)
                )
                right_count = (
                    len(right_full_nodes)
                    + len(non_birthing_half_sibling_nodes)
                    + len(non_birthing_relative_nodes)
                )

                if left_count <= right_count:
                    birthing_relative_nodes.append(node)
                else:
                    non_birthing_relative_nodes.append(node)

            sibling_spacing = 144
            group_gap = 24
            positioned_nodes = [(focus_node, 0)]
            left_distance = 0
            right_distance = 0

            for node in reversed(left_full_nodes):
                left_distance += sibling_spacing
                positioned_nodes.append((node, -left_distance))

            if birthing_half_sibling_nodes:
                left_distance += group_gap

                for node in reversed(birthing_half_sibling_nodes):
                    left_distance += sibling_spacing
                    positioned_nodes.append((node, -left_distance))

            if birthing_relative_nodes:
                left_distance += group_gap

                for node in reversed(birthing_relative_nodes):
                    left_distance += sibling_spacing
                    positioned_nodes.append((node, -left_distance))

            for node in right_full_nodes:
                right_distance += sibling_spacing
                positioned_nodes.append((node, right_distance))

            if non_birthing_half_sibling_nodes:
                right_distance += group_gap

                for node in non_birthing_half_sibling_nodes:
                    right_distance += sibling_spacing
                    positioned_nodes.append((node, right_distance))

            if non_birthing_relative_nodes:
                right_distance += group_gap

                for node in non_birthing_relative_nodes:
                    right_distance += sibling_spacing
                    positioned_nodes.append((node, right_distance))

            node_half_width = 66
            left_capacity = max(
                0,
                center_x - graph_left - node_half_width,
            )
            right_capacity = max(
                0,
                graph_right - center_x - node_half_width,
            )
            position_scale = 1.0

            if left_distance > left_capacity and left_distance > 0:
                position_scale = min(
                    position_scale,
                    left_capacity / left_distance,
                )

            if right_distance > right_capacity and right_distance > 0:
                position_scale = min(
                    position_scale,
                    right_capacity / right_distance,
                )

            return [
                (
                    node,
                    center_x + offset * position_scale,
                    y_position,
                    132,
                    64,
                )
                for node, offset in positioned_nodes
            ]

        if row_index == 3:
            anchored_groups = {}
            unanchored_nodes = []
            foster_nodes = []

            for node in nodes:
                if node.get("relation") == "Foster child":
                    foster_nodes.append(node)
                    continue

                record_id = str(
                    node["person"].get("record_id", "") or ""
                ).strip()
                visible_parent_ids = [
                    parent_id
                    for parent_id in self.relationship_map.parents_of(
                        record_id
                    )
                    if parent_id in self.node_coordinates
                ]
                anchor_id = ""

                if (
                    node.get("relation") == "Child"
                    and focus_id in visible_parent_ids
                ):
                    anchor_id = focus_id
                elif visible_parent_ids:
                    anchor_id = visible_parent_ids[0]

                if anchor_id:
                    anchored_groups.setdefault(anchor_id, []).append(node)
                else:
                    unanchored_nodes.append(node)

            node_count = len(nodes)
            card_gap = 8
            graph_width = graph_right - graph_left
            node_width = min(
                132,
                max(
                    64,
                    (
                        graph_width
                        - card_gap * max(0, node_count - 1)
                    )
                    / max(1, node_count),
                ),
            )
            desired_positions = []

            for anchor_id, group_nodes in sorted(
                anchored_groups.items(),
                key=lambda item: self.node_coordinates[item[0]][0],
            ):
                anchor_x = self.node_coordinates[anchor_id][0]
                group_width = (
                    node_width * len(group_nodes)
                    + card_gap * max(0, len(group_nodes) - 1)
                )
                group_start = anchor_x - group_width / 2 + node_width / 2

                for group_index, node in enumerate(group_nodes):
                    desired_positions.append(
                        (
                            node,
                            group_start
                            + group_index * (node_width + card_gap),
                        )
                    )

            unanchored_width = (
                node_width * len(unanchored_nodes)
                + card_gap * max(0, len(unanchored_nodes) - 1)
            )
            unanchored_start = (
                center_x - unanchored_width / 2 + node_width / 2
            )

            for node_index, node in enumerate(unanchored_nodes):
                desired_positions.append(
                    (
                        node,
                        unanchored_start
                        + node_index * (node_width + card_gap),
                    )
                )

            # Foster children share the generation, but they are deliberately
            # not part of the connected biological-child cluster. Keep them
            # together at the far right so they cannot be mistaken for a
            # child connected to the selected person's parent line.
            foster_gap = 22
            foster_start = (
                max(position[1] for position in desired_positions)
                + node_width
                + foster_gap
                if desired_positions
                else center_x
            )

            for node_index, node in enumerate(foster_nodes):
                desired_positions.append(
                    (
                        node,
                        foster_start
                        + node_index * (node_width + card_gap),
                    )
                )

            desired_positions.sort(key=lambda item: item[1])
            bounded_positions = []
            minimum_x = graph_left + node_width / 2
            maximum_x = graph_right - node_width / 2

            for node, desired_x in desired_positions:
                x_position = max(minimum_x, desired_x)

                if bounded_positions:
                    x_position = max(
                        x_position,
                        bounded_positions[-1][1] + node_width + card_gap,
                    )

                bounded_positions.append([node, x_position])

            if bounded_positions and bounded_positions[-1][1] > maximum_x:
                overflow = bounded_positions[-1][1] - maximum_x

                for positioned_node in bounded_positions:
                    positioned_node[1] -= overflow

            for index in range(len(bounded_positions) - 2, -1, -1):
                bounded_positions[index][1] = min(
                    bounded_positions[index][1],
                    bounded_positions[index + 1][1]
                    - node_width
                    - card_gap,
                )

            return [
                (
                    node,
                    x_position,
                    y_position,
                    node_width,
                    64,
                )
                for node, x_position in bounded_positions
            ]

        spacing = min(150, (graph_right - graph_left) / max(1, len(nodes)))
        total_width = spacing * (len(nodes) - 1)
        start_x = center_x - total_width / 2
        return [
            (
                node,
                start_x + index * spacing,
                y_position,
                132,
                64,
            )
            for index, node in enumerate(nodes)
        ]

    def draw_relationship_lines(self, visible_generations):
        visible_ids = []
        visible_nodes = {}

        for row_index, nodes in enumerate(visible_generations):
            visible_ids.extend(
                str(node["person"].get("record_id", ""))
                for node in nodes
                if not node.get("placeholder")
            )

            for node in nodes:
                if node.get("placeholder"):
                    continue

                record_id = str(
                    node["person"].get("record_id", "") or ""
                )
                visible_nodes[record_id] = (row_index, node)

        focus_id = str(
            self.current_person.get("record_id", "") or ""
        )
        focus_parent_ids = set(
            self.relationship_map.parents_of(focus_id)
        )
        birthing_parent_id = str(
            self.current_person.get("biological_mother_id", "") or ""
        ).strip()
        non_birthing_parent_id = str(
            self.current_person.get("biological_father_id", "") or ""
        ).strip()

        for parent_id, child_id in self.relationship_map.visible_parent_child_edges(
            visible_ids
        ):
            parent_coordinates = self.node_coordinates.get(parent_id)
            child_coordinates = self.node_coordinates.get(child_id)

            if parent_coordinates is None or child_coordinates is None:
                continue

            parent_x, parent_y, parent_width, parent_height = parent_coordinates
            child_x, child_y, child_width, child_height = child_coordinates
            line_middle = (parent_y + child_y) / 2
            line_fill = FAMILY_LINE

            if self.child_is_faded(child_id):
                line_fill = FAMILY_CHILD_FADED_LINE

            child_node = visible_nodes.get(child_id)

            if (
                child_node is not None
                and child_node[0] == 2
                and child_node[1].get("relation") == "1/2 Sibling"
                and parent_id in focus_parent_ids
            ):
                if parent_id == birthing_parent_id:
                    parent_side_x = parent_x - parent_width / 2
                elif parent_id == non_birthing_parent_id:
                    parent_side_x = parent_x + parent_width / 2
                elif child_x < parent_x:
                    parent_side_x = parent_x - parent_width / 2
                else:
                    parent_side_x = parent_x + parent_width / 2

                self.canvas.create_line(
                    parent_side_x,
                    parent_y,
                    child_x,
                    parent_y,
                    child_x,
                    child_y - child_height / 2,
                    fill=line_fill,
                    width=2,
                    smooth=False,
                )
                continue

            self.canvas.create_line(
                parent_x,
                parent_y + parent_height / 2,
                parent_x,
                line_middle,
                child_x,
                line_middle,
                child_x,
                child_y - child_height / 2,
                fill=line_fill,
                width=2,
                smooth=False,
            )

        focus_coordinates = self.node_coordinates.get(focus_id)

        if focus_coordinates is None:
            return

        focus_x, focus_y, _focus_width, focus_height = focus_coordinates

        for placeholder_id, parent_status in (
            (
                "__select_mother__",
                getattr(self, "mother_status", "unknown"),
            ),
            (
                "__select_father__",
                getattr(self, "father_status", "unknown"),
            ),
        ):
            if parent_status != "muggle":
                continue

            parent_coordinates = self.node_coordinates.get(
                placeholder_id
            )

            if parent_coordinates is None:
                continue

            parent_x, parent_y, parent_width, parent_height = (
                parent_coordinates
            )
            line_middle = (parent_y + focus_y) / 2
            self.canvas.create_line(
                parent_x,
                parent_y + parent_height / 2,
                parent_x,
                line_middle,
                focus_x,
                line_middle,
                focus_x,
                focus_y - focus_height / 2,
                fill=FAMILY_LINE,
                width=2,
                smooth=False,
            )

    def draw_person_node(self, node, row_index, focus_id):
        person = node["person"]
        record_id = str(person.get("record_id", ""))
        x_position, y_position, node_width, node_height = self.node_coordinates[
            record_id
        ]
        left = x_position - node_width / 2
        top = y_position - node_height / 2
        right = x_position + node_width / 2
        bottom = y_position + node_height / 2
        is_focus = record_id == focus_id
        is_placeholder = bool(node.get("placeholder"))
        fill = PRIMARY_SOFT if is_focus else FIELD_BACKGROUND
        outline = BORDER
        outline_width = 2 if is_focus else 1
        text_fill = TEXT_DARK
        relation_fill = TEXT_MUTED
        plaque_fill = SURFACE_RAISED
        plaque_outline = BORDER_SOFT
        child_is_faded = self.child_is_faded(record_id)

        if self.active_mate_id:
            active_owner_id = str(
                self.active_spouse_owner_id or focus_id
            )
            parent_ids = self.relationship_map.parents_of(record_id)

            if (
                record_id in self.relationship_map.children_of(active_owner_id)
                and self.active_mate_id in parent_ids
            ):
                outline = FAMILY_GREEN_DARK
                outline_width = 3

        if child_is_faded:
            fill = FAMILY_CHILD_FADED_FILL
            outline = FAMILY_CHILD_FADED_OUTLINE
            outline_width = 1
            text_fill = FAMILY_CHILD_FADED_TEXT
            relation_fill = FAMILY_CHILD_FADED_MUTED
            plaque_fill = SURFACE_RAISED
            plaque_outline = FAMILY_CHILD_FADED_OUTLINE

        if is_placeholder:
            fill = BUTTON_SOFT
            outline = PRIMARY
            outline_width = 2

        tag_name = f"person_node:{record_id}"
        shape = self.canvas.create_polygon(
            rounded_points(node_width, node_height, 9),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=outline,
            width=outline_width,
            tags=(tag_name,),
        )
        self.canvas.move(shape, left, top)
        display_name = str(person.get("displayed_name", "") or "Unnamed")
        maiden_name = maiden_name_for(person)
        date_text = format_person_date(person)
        name_character_limit = max(
            8,
            min(23, int(node_width / 6)),
        )
        maiden_character_limit = max(
            6,
            min(18, int(node_width / 7)),
        )
        detail_lines = [
            self.short_text(display_name, name_character_limit)
        ]

        if not is_placeholder:
            maiden_line = (
                f"née {self.short_text(maiden_name, maiden_character_limit)}"
                if maiden_name
                else ""
            )
            detail_lines.extend((maiden_line, date_text))

        text_item = self.canvas.create_text(
            x_position,
            y_position,
            text="\n".join(detail_lines),
            fill=text_fill,
            font=app_font(
                7 if node_width < 96 else 8,
                "bold" if is_focus else "normal",
            ),
            justify="center",
            width=node_width - 12,
            tags=(tag_name,),
        )
        relation_text = str(node.get("relation", "") or "")

        if relation_text in (
            "Birthing parent's pibbling",
            "Non-birthing parent's pibbling",
        ):
            relation_text = "Pibbling"

        relation_item = self.canvas.create_text(
            x_position,
            top - (11 if node_width < 100 else 7),
            text=relation_text,
            fill=relation_fill,
            font=app_font(7, "bold"),
            justify="center",
            width=max(70, node_width + 16),
            tags=(tag_name,),
        )
        relation_bounds = self.canvas.bbox(relation_item)
        relation_plaque = None

        if relation_bounds is not None:
            plaque_left = relation_bounds[0] - 5
            plaque_top = relation_bounds[1] - 2
            plaque_right = relation_bounds[2] + 5
            plaque_bottom = relation_bounds[3] + 2
            relation_plaque = self.canvas.create_rectangle(
                plaque_left,
                plaque_top,
                plaque_right,
                plaque_bottom,
                fill=plaque_fill,
                outline=plaque_outline,
                width=1,
                tags=(tag_name,),
            )
            self.canvas.tag_lower(relation_plaque, relation_item)

        self.canvas.tag_bind(tag_name, "<Enter>", partial(self.enter_canvas_item, tag_name))
        self.canvas.tag_bind(tag_name, "<Leave>", partial(self.leave_canvas_item, tag_name))

        if record_id == "__select_mother__":
            self.canvas.tag_bind(tag_name, "<Button-1>", self.open_mother_picker)
        elif record_id == "__select_father__":
            self.canvas.tag_bind(tag_name, "<Button-1>", self.open_father_picker)
        else:
            self.canvas.tag_bind(
                tag_name,
                "<Double-Button-1>",
                partial(self.navigate_to_person, record_id),
            )

        self.canvas.tag_raise(text_item)

        if relation_plaque is not None:
            self.canvas.tag_raise(relation_plaque)

        self.canvas.tag_raise(relation_item)

    def draw_spouse_flags(self, focus_id):
        step_parent_mates = self.relationship_map.step_parent_mates_of(focus_id)
        visible_ids = set(self.node_coordinates)
        standard_mates_by_owner = {}
        rendered_pairs = set()

        for owner_id in sorted(visible_ids):
            if self.relationship_map.person(owner_id) is None:
                continue

            mate_ids = self.relationship_map.mates_of(owner_id)

            if owner_id == focus_id:
                for mate_id in self.mate_ids:
                    if (
                        mate_id not in mate_ids
                        and self.relationship_map.person(mate_id)
                    ):
                        mate_ids.append(mate_id)

            if owner_id in step_parent_mates:
                mate_ids = [
                    mate_id
                    for mate_id in mate_ids
                    if mate_id not in step_parent_mates[owner_id]
                    and mate_id not in visible_ids
                ]

            if not mate_ids:
                continue

            standard_mates_by_owner[owner_id] = mate_ids
            rendered_pairs.update(
                (owner_id, mate_id) for mate_id in mate_ids
            )

        for parent_id, mate_ids in step_parent_mates.items():
            for mate_id in mate_ids:
                if mate_id not in visible_ids:
                    rendered_pairs.add((parent_id, mate_id))

        active_pair = (self.active_spouse_owner_id, self.active_mate_id)

        if active_pair not in rendered_pairs:
            self.active_spouse_owner_id = None
            self.active_mate_id = None

        for owner_id, mate_ids in standard_mates_by_owner.items():
            self.draw_spouse_flags_for_person(
                owner_id,
                mate_ids,
                is_step_parent=False,
            )

        for parent_id, mate_ids in step_parent_mates.items():
            hidden_mate_ids = [
                mate_id for mate_id in mate_ids if mate_id not in visible_ids
            ]
            self.draw_spouse_flags_for_person(
                parent_id,
                hidden_mate_ids,
                is_step_parent=True,
            )

    def draw_spouse_flags_for_person(
        self,
        owner_id,
        mate_ids,
        is_step_parent=False,
    ):
        owner_coordinates = self.node_coordinates.get(owner_id)

        if owner_coordinates is None or not mate_ids:
            return

        owner_x, owner_y, owner_width, owner_height = owner_coordinates
        flag_width = 16 if is_step_parent else 20
        flag_height = 16 if is_step_parent else 18
        flag_column_gap = 3
        flag_row_step = flag_height
        flag_column_step = flag_width + flag_column_gap
        flag_start_left = owner_x + owner_width / 2 - 3
        flag_start_top = owner_y - owner_height / 2 + 4
        flag_column_count = (len(mate_ids) + 2) // 3

        for index, mate_id in enumerate(mate_ids):
            mate = self.relationship_map.person(mate_id)

            if mate is None:
                continue

            is_active = (
                owner_id == self.active_spouse_owner_id
                and mate_id == self.active_mate_id
            )
            has_active_spouse = self.active_mate_id is not None
            flag_column = index // 3
            flag_row = index % 3
            flag_left = flag_start_left + flag_column * flag_column_step
            flag_top = flag_start_top + flag_row * flag_row_step
            normal_fill = FAMILY_STEP_FILL if is_step_parent else FAMILY_GREEN
            active_fill = FAMILY_STEP_ACTIVE if is_step_parent else FAMILY_GREEN
            faded_fill = FAMILY_STEP_FADED if is_step_parent else FAMILY_GREEN_FADED
            outline_fill = FAMILY_STEP_DARK if is_step_parent else FAMILY_GREEN_DARK
            flag_fill = active_fill if is_active else (
                faded_fill if has_active_spouse else normal_fill
            )
            flag_foreground = (
                outline_fill if is_active or not has_active_spouse else TEXT_MUTED
            )
            tag_name = f"spouse_flag:{owner_id}:{mate_id}"
            flag_shape = self.canvas.create_polygon(
                rounded_points(flag_width, flag_height, 6),
                smooth=True,
                splinesteps=24,
                fill=flag_fill,
                outline=outline_fill,
                width=1,
                tags=(tag_name,),
            )
            self.canvas.move(flag_shape, flag_left, flag_top)
            self.canvas.create_text(
                flag_left + flag_width / 2,
                flag_top + flag_height / 2,
                text="x",
                fill=flag_foreground,
                font=app_font(7, "bold"),
                tags=(tag_name,),
            )
            self.canvas.tag_bind(
                tag_name,
                "<Button-1>",
                partial(self.select_spouse, owner_id, mate_id),
            )
            self.canvas.tag_bind(
                tag_name,
                "<Enter>",
                partial(self.enter_canvas_item, tag_name),
            )
            self.canvas.tag_bind(
                tag_name,
                "<Leave>",
                partial(self.leave_canvas_item, tag_name),
            )

            if is_active:
                self.draw_spouse_detail(
                    owner_id,
                    mate,
                    flag_start_left,
                    flag_top,
                    flag_column_count,
                    flag_column_step,
                    is_step_parent,
                )

    def draw_spouse_detail(
        self,
        owner_id,
        mate,
        flag_start_left,
        flag_top,
        flag_column_count,
        flag_column_step,
        is_step_parent,
    ):
        mate_id = str(mate.get("record_id", "") or "")
        mate_name = self.short_text(mate.get("displayed_name", "Unnamed"), 20)
        detail_text = f"{mate_name}\n{format_person_date(mate)}"
        detail_width = 152
        detail_height = 34
        detail_left = flag_start_left + flag_column_count * flag_column_step + 4
        detail_top = flag_top - 7
        detail_fill = FAMILY_STEP_FILL if is_step_parent else FAMILY_GREEN
        detail_outline = FAMILY_STEP_DARK if is_step_parent else FAMILY_GREEN_DARK
        detail_tag = f"spouse_detail:{owner_id}:{mate_id}"
        detail_shape = self.canvas.create_polygon(
            rounded_points(detail_width, detail_height, 7),
            smooth=True,
            splinesteps=24,
            fill=detail_fill,
            outline=detail_outline,
            width=1,
            tags=(detail_tag,),
        )
        self.canvas.move(detail_shape, detail_left, detail_top)
        self.canvas.create_text(
            detail_left + 8,
            detail_top + detail_height / 2,
            text=detail_text,
            fill=detail_outline,
            font=app_font(7, "bold"),
            anchor="w",
            justify="left",
            tags=(detail_tag,),
        )
        self.canvas.tag_bind(
            detail_tag,
            "<Button-1>",
            partial(self.select_spouse, owner_id, mate_id),
        )
        self.canvas.tag_bind(
            detail_tag,
            "<Enter>",
            partial(self.enter_canvas_item, detail_tag),
        )
        self.canvas.tag_bind(
            detail_tag,
            "<Leave>",
            partial(self.leave_canvas_item, detail_tag),
        )

    def child_is_faded(self, child_id):
        if not self.active_mate_id:
            return False

        focus_id = str(self.current_person.get("record_id", "") or "")
        owner_id = str(
            getattr(self, "active_spouse_owner_id", None) or focus_id
        )
        child_id = str(child_id or "")

        if child_id not in self.relationship_map.children_of(owner_id):
            return False

        parent_ids = self.relationship_map.parents_of(child_id)
        return self.active_mate_id not in parent_ids

    def enter_canvas_item(self, tag_name, event=None):
        self.canvas.configure(cursor="hand2")

    def leave_canvas_item(self, tag_name, event=None):
        self.canvas.configure(cursor="")

    def navigate_to_person(self, record_id, event=None):
        current_id = str(self.current_person.get("record_id", "") or "")

        if record_id != current_id:
            self.navigate_command(record_id)

    def select_spouse(self, owner_id, mate_id, event=None):
        is_active = (
            self.active_spouse_owner_id == owner_id
            and self.active_mate_id == mate_id
        )
        self.active_spouse_owner_id = None if is_active else owner_id
        self.active_mate_id = None if is_active else mate_id
        self.update_add_child_control()
        self.redraw_graph()

    def open_parent_couple_picker(self):
        self.reload_people(redraw=False)
        current_id = str(self.current_person.get("record_id", "") or "")
        couples = self.relationship_map.parent_couple_candidates(current_id)
        if not couples:
            messagebox.showinfo(
                "No parent couples available",
                (
                    "No existing spouse pair meets this person's parent, age, "
                    "and family requirements."
                ),
                parent=self,
            )
            return
        ParentCouplePickerDialog(self, couples, self.set_parent_couple)

    def set_parent_couple(self, mother_id, father_id):
        valid_pairs = {
            (
                str(mother.get("record_id", "") or ""),
                str(father.get("record_id", "") or ""),
            )
            for mother, father in self.relationship_map.parent_couple_candidates(
                self.current_person.get("record_id", "")
            )
        }
        if (mother_id, father_id) not in valid_pairs:
            raise ValueError("That spouse pair is no longer available as parents.")

        replacing = any(
            current_id and current_id != requested_id
            for current_id, requested_id in (
                (self.mother_id, mother_id),
                (self.father_id, father_id),
            )
        )
        if replacing and not messagebox.askyesno(
            "Replace current parents?",
            "Replace the current parent assignment with this couple?",
            parent=self,
            default="no",
        ):
            return False

        self.mother_id = mother_id
        self.mother_status = "person"
        self.father_id = father_id
        self.father_status = "person"
        self.reload_people(refresh_provider=False)
        self.change_command()
        return True

    def open_mother_picker(self, event=None):
        self.open_parent_picker("mother")

    def open_father_picker(self, event=None):
        self.open_parent_picker("father")

    def open_parent_picker(self, parent_role):
        # Parent choices must reflect newly created and newly renamed people.
        # The family graph deliberately caches compact summaries for speed, so
        # refresh that lightweight list at the moment the searchable chooser
        # opens rather than searching a stale snapshot.
        self.reload_people(redraw=False)
        current_id = str(self.current_person.get("record_id", "") or "")
        primary_candidates = self.relationship_map.parent_candidates(
            current_id,
            parent_role,
        )
        alternate_candidates = self.relationship_map.parent_candidates(
            current_id,
            parent_role,
            alternate_role=True,
        )
        role_label = (
            "birthing parent" if parent_role == "mother" else "non-birthing parent"
        )
        alternate_role_label = (
            "non-birthing parent" if parent_role == "mother" else "birthing parent"
        )
        required_setting = "checked" if parent_role == "mother" else "unchecked"
        alternate_label = (
            "See non-birthing parent options"
            if parent_role == "mother"
            else "See birthing parent options"
        )
        alternate_note = (
            f"These people are not assigned as a {alternate_role_label} to anyone. "
            f"Selecting one will set Can give birth to {required_setting}."
        )
        RelationshipPickerDialog(
            self,
            title=f"Select {role_label}",
            heading=f"Select {role_label}",
            explanation=(
                f"Choose an existing {role_label}, or use Enter new for a "
                "name-only character entry.\n"
                + parent_candidate_explanation(
                    self.current_person,
                    self.relationship_map.people_by_id,
                    parent_role,
                )
            ),
            primary_people=primary_candidates,
            alternate_people=alternate_candidates,
            alternate_label=alternate_label,
            alternate_note=alternate_note,
            select_label="Select parent",
            select_command=partial(self.set_parent, parent_role),
            create_command=partial(self.create_parent, parent_role),
            new_profile_label=f"Enter a new {role_label}",
            new_profile_explanation=(
                "Enter the displayed name, birth year, and starting location. "
                "Can give "
                f"birth will be {required_setting}."
            ),
            status_options=(
                ("Unknown", "unknown"),
                ("Unknown Muggle", "muggle"),
            ),
            status_command=partial(
                self.set_parent_status,
                parent_role,
            ),
            locations=(
                self.locations_provider()
                if callable(self.locations_provider)
                else ()
            ),
            create_location_command=self.create_location_command,
            school_records_provider=self.school_records_provider,
        )

    def set_parent(self, parent_role, record_id, change_birth_assignment=False):
        selected_parent = self.relationship_map.person(record_id)

        if selected_parent is None:
            raise ValueError("The selected parent no longer exists.")

        if bool(selected_parent.get("does_not_have_children")):
            raise ValueError(
                "The selected person is marked Does not have children "
                "and cannot be added as a parent."
            )

        allowed_magic_states = allowed_parent_magic_states(
            self.current_person,
            self.relationship_map.people_by_id,
            parent_role,
        )

        if person_magic_state(selected_parent) not in allowed_magic_states:
            raise ValueError(
                "The selected parent's magical status is incompatible "
                "with this individual's blood status."
            )

        if change_birth_assignment:
            updated_parent = self.update_person_command(
                record_id,
                {"can_give_birth": parent_role == "mother"},
            )
            if isinstance(updated_parent, dict):
                selected_parent.update(updated_parent)
                for person in self.people:
                    if str(person.get("record_id", "") or "") == record_id:
                        person.update(updated_parent)
                        break

        if parent_role == "mother":
            self.mother_id = record_id
            self.mother_status = "person"
        else:
            self.father_id = record_id
            self.father_status = "person"

        self.reload_people(refresh_provider=False)
        self.change_command()

    def create_parent(self, parent_role, profile_values):
        values = (
            dict(profile_values)
            if isinstance(profile_values, dict)
            else {"displayed_name": str(profile_values or "")}
        )
        allowed_magic_states = allowed_parent_magic_states(
            self.current_person,
            self.people,
            parent_role,
        )
        values.update(
            {
                "can_give_birth": parent_role == "mother",
                "non_magical": allowed_magic_states == (
                    PARENT_MAGIC_STATE_NON_MAGICAL,
                ),
            }
        )
        created_person = self.create_person_command(values)
        self.reload_people(redraw=False)
        self.set_parent(parent_role, created_person["record_id"])
        return created_person

    def remove_parent(self, parent_role):
        parent_id = self.mother_id if parent_role == "mother" else self.father_id
        parent_status = (
            self.mother_status if parent_role == "mother" else self.father_status
        )

        if not parent_id and parent_status != "muggle":
            return

        parent = self.relationship_map.person(parent_id)
        role_label = (
            "birthing parent" if parent_role == "mother" else "non-birthing parent"
        )
        parent_name = (
            parent.get("displayed_name", f"this {role_label}")
            if parent
            else (
                "the unknown Muggle parent"
                if parent_status == "muggle"
                else f"this {role_label}"
            )
        )

        if not messagebox.askyesno(
            f"Remove {role_label}",
            (
                f"Remove {parent_name} as the {role_label}? "
                "The person's character entry will remain in Mage Maker."
            ),
            parent=self,
        ):
            return

        if parent_role == "mother":
            self.mother_id = ""
            self.mother_status = "unknown"
        else:
            self.father_id = ""
            self.father_status = "unknown"

        self.reload_people()
        self.change_command()

    def set_parent_status(self, parent_role, status):
        normalized_status = (
            "muggle" if str(status or "").casefold() == "muggle" else "unknown"
        )

        if parent_role == "mother":
            self.mother_id = ""
            self.mother_status = normalized_status
        else:
            self.father_id = ""
            self.father_status = normalized_status

        self.reload_people(refresh_provider=False)
        self.change_command()

    def open_mate_picker(self):
        if self.spouse_picker_dialog is not None:
            try:
                if self.spouse_picker_dialog.winfo_exists():
                    self.spouse_picker_dialog.deiconify()
                    self.spouse_picker_dialog.lift()
                    self.spouse_picker_dialog.after_idle(
                        self.spouse_picker_dialog.focus_search
                    )
                    return
            except tk.TclError:
                pass

            self.spouse_picker_dialog = None

        current_id = str(self.current_person.get("record_id", "") or "")

        if integer_year(self.current_person.get("birth_year")) is None:
            messagebox.showinfo(
                "Birth year required",
                "Enter this person's Birth year on the Profile page before adding a spouse.",
                parent=self,
            )
            return

        excluded_ids = set(self.mate_ids)
        excluded_ids.update(self.relationship_map.ancestors_of(current_id))
        excluded_ids.update(self.relationship_map.descendants_of(current_id))
        excluded_ids.update(
            self.relationship_map.relatives_through_third_cousins(current_id)
        )
        candidates = spouse_candidates(
            self.current_person,
            self.people,
            excluded_ids,
        )
        self.spouse_picker_dialog = SpousePickerDialog(
            self,
            self.current_person,
            candidates,
            self.add_spouse_relationship,
            self.create_person_command,
            [
                child
                for child in (
                    self.relationship_map.person(child_id)
                    for child_id in self.relationship_map.children_of(current_id)
                )
                if child is not None
            ],
            self.spouse_picker_closed,
        )

    def close_spouse_picker(self):
        dialog = self.spouse_picker_dialog

        if dialog is None:
            return

        self.spouse_picker_dialog = None

        try:
            if dialog.winfo_exists():
                dialog.close_dialog()
        except tk.TclError:
            return

    def spouse_picker_closed(self):
        self.spouse_picker_dialog = None

    def select_mate(self, record_id, change_birth_assignment=False):
        if change_birth_assignment:
            self.update_person_command(
                record_id,
                {
                    "can_give_birth": not person_can_give_birth(
                        self.current_person
                    )
                },
            )

        self.add_mate(record_id)

    def create_mate(self, displayed_name):
        created_person = self.create_person_command(
            {
                "displayed_name": displayed_name,
                "can_give_birth": not person_can_give_birth(
                    self.current_person
                ),
            }
        )
        self.add_mate(created_person["record_id"])
        return created_person

    def add_mate(self, record_id):
        self.add_spouse_relationship(empty_spouse_relationship(record_id))

    def add_spouse_relationship(self, relationship):
        normalized = normalize_spouse_relationships([relationship])[0]
        record_id = normalized["person_id"]
        self.spouse_relationships = [
            existing
            for existing in self.spouse_relationships
            if existing["person_id"] != record_id
        ]
        self.spouse_relationships.append(normalized)
        self.mate_ids = relationship_ids(self.spouse_relationships)
        self.active_mate_id = record_id
        self.active_spouse_owner_id = str(
            self.current_person.get("record_id", "") or ""
        )
        self.reload_people()
        self.change_command()

    def remove_active_mate(self):
        current_id = str(self.current_person.get("record_id", "") or "")

        if (
            self.active_mate_id is None
            or self.active_spouse_owner_id != current_id
        ):
            return

        mate = self.relationship_map.person(self.active_mate_id)
        mate_name = mate.get("displayed_name", "this spouse") if mate else "this spouse"

        if not messagebox.askyesno(
            "Remove spouse",
            f"Remove {mate_name} as a spouse? Existing parent links on children will remain.",
            parent=self,
        ):
            return

        self.mate_ids = [
            mate_id for mate_id in self.mate_ids if mate_id != self.active_mate_id
        ]
        self.spouse_relationships = [
            relationship
            for relationship in self.spouse_relationships
            if relationship["person_id"] != self.active_mate_id
        ]
        self.active_mate_id = None
        self.active_spouse_owner_id = None
        self.reload_people()
        self.change_command()

    def valid_child_spouses(self):
        current_id = str(self.current_person.get("record_id", "") or "")
        if not current_id:
            return []
        current_can_give_birth = person_can_give_birth(self.current_person)
        return [
            self.relationship_map.person(mate_id)
            for mate_id in self.relationship_map.mates_of(current_id)
            if self.relationship_map.person(mate_id) is not None
            and not bool(
                self.relationship_map.person(mate_id).get(
                    "does_not_have_children"
                )
            )
            and person_can_give_birth(self.relationship_map.person(mate_id))
            != current_can_give_birth
        ]

    def preferred_child_spouse_id(self):
        current_id = str(self.current_person.get("record_id", "") or "")
        valid_ids = [
            str(person.get("record_id", "") or "")
            for person in self.valid_child_spouses()
        ]
        if (
            self.active_spouse_owner_id == current_id
            and self.active_mate_id in valid_ids
        ):
            return self.active_mate_id
        return valid_ids[0] if len(valid_ids) == 1 else ""

    def open_add_child_with_spouse(self):
        spouse_id = self.preferred_child_spouse_id()
        if not spouse_id:
            # Multiple spouses remain an explicit choice in the normal first
            # step; a sole spouse skips that redundant screen.
            return self.open_add_child_dialog()
        return self.open_add_child_dialog(
            preselected_other_parent_id=spouse_id,
            start_on_child=True,
        )

    def open_add_child_dialog(
        self,
        preselected_other_parent_id=None,
        start_on_child=False,
    ):
        current_id = str(self.current_person.get("record_id", "") or "")

        if not current_id:
            return

        if bool(self.current_person.get("does_not_have_children")):
            messagebox.showinfo(
                "Cannot add child",
                (
                    "This person is marked Does not have children. "
                    "Uncheck that classification before adding a child."
                ),
                parent=self,
            )
            return

        self.reload_people(redraw=False)
        current_can_give_birth = person_can_give_birth(
            self.current_person
        )

        ancestors = set(self.relationship_map.ancestors_of(current_id))
        candidates = [
            person
            for person in self.people
            if person.get("record_id") != current_id
            and person.get("record_id") not in ancestors
        ]
        existing_mates = self.valid_child_spouses()
        AddChildDialog(
            self,
            self.current_person,
            candidates,
            self.people_provider,
            self.save_child,
            self.open_child_other_parent_picker,
            existing_mates=existing_mates,
            active_other_parent_id=(
                preselected_other_parent_id
                or (
                    self.active_mate_id
                    if self.active_spouse_owner_id == current_id
                    else None
                )
            ),
            start_on_child=start_on_child,
            locations_provider=self.locations_provider,
            event_provider=self.event_provider,
            create_location_command=self.create_location_command,
            school_records_provider=self.school_records_provider,
        )

    def open_child_other_parent_picker(
        self,
        dialog_parent,
        selection_command,
        child_record_id,
    ):
        current_id = str(self.current_person.get("record_id", "") or "")
        current_can_give_birth = person_can_give_birth(
            self.current_person
        )
        excluded_ids = [child_record_id] if child_record_id else []
        primary_candidates = self.relationship_map.partner_candidates(
            current_id,
            include_existing_mates=True,
            extra_excluded_ids=excluded_ids,
        )
        alternate_candidates = self.relationship_map.partner_candidates(
            current_id,
            alternate_role=True,
            include_existing_mates=True,
            extra_excluded_ids=excluded_ids,
        )
        required_role_label = (
            "non-birthing parent" if current_can_give_birth else "birthing parent"
        )
        alternate_role_label = (
            "birthing parent" if current_can_give_birth else "non-birthing parent"
        )
        required_setting = "unchecked" if current_can_give_birth else "checked"
        alternate_label = (
            "See birthing parent options"
            if current_can_give_birth
            else "See non-birthing parent options"
        )
        return RelationshipPickerDialog(
            dialog_parent,
            title="Choose other parent",
            heading=f"Choose the child's {required_role_label}",
            explanation=(
                f"Choose a {required_role_label}, or use Enter new for a "
                "name-only character entry."
            ),
            primary_people=primary_candidates,
            alternate_people=alternate_candidates,
            alternate_label=alternate_label,
            alternate_note=(
                f"These {alternate_role_label} options have no parent or mate links "
                f"that block changing Can give birth to {required_setting}."
            ),
            select_label="Select parent",
            select_command=selection_command,
            create_command=partial(
                self.create_child_other_parent,
                selection_command,
            ),
            new_profile_label=f"Enter a new {required_role_label}",
            new_profile_explanation=(
                "Enter the displayed name, birth year, and starting location. "
                "Can give "
                f"birth will be {required_setting}."
            ),
            locations=(
                self.locations_provider()
                if callable(self.locations_provider)
                else ()
            ),
            create_location_command=self.create_location_command,
        )

    def create_child_other_parent(self, selection_command, profile_values):
        values = (
            dict(profile_values)
            if isinstance(profile_values, dict)
            else {"displayed_name": str(profile_values or "")}
        )
        values["can_give_birth"] = not person_can_give_birth(
            self.current_person
        )
        created_person = self.create_person_command(values)
        selection_command(created_person["record_id"], False)
        return created_person

    def save_child(
        self,
        child_record_id,
        new_child_name,
        new_child_can_give_birth,
        other_parent_id,
        change_other_parent_assignment=False,
        other_parent_kind="person",
        new_child_profile=None,
    ):
        current_id = str(self.current_person.get("record_id", "") or "")

        if bool(self.current_person.get("does_not_have_children")):
            raise ValueError(
                "This person is marked Does not have children and cannot "
                "be added as a parent."
            )

        current_can_give_birth = person_can_give_birth(
            self.current_person
        )
        current_parent_field = (
            "biological_mother_id"
            if current_can_give_birth
            else "biological_father_id"
        )
        other_parent_field = (
            "biological_father_id"
            if current_can_give_birth
            else "biological_mother_id"
        )
        current_parent_status_field = current_parent_field.replace("_id", "_status")
        other_parent_status_field = other_parent_field.replace("_id", "_status")
        normalized_other_parent_kind = str(other_parent_kind or "unknown").casefold()
        relationship_values = {
            current_parent_field: current_id,
            current_parent_status_field: "person",
        }

        if normalized_other_parent_kind == "person" and other_parent_id:
            if change_other_parent_assignment:
                other_parent = self.update_person_command(
                    other_parent_id,
                    {"can_give_birth": not current_can_give_birth},
                )
            else:
                other_parent = self.relationship_map.person(other_parent_id)

            if (
                other_parent is None
                or person_can_give_birth(other_parent)
                == current_can_give_birth
            ):
                raise ValueError(
                    "The child's other parent must have the opposite Can give birth assignment."
                )

            if bool(other_parent.get("does_not_have_children")):
                raise ValueError(
                    "The child's other parent is marked Does not have "
                    "children and cannot be added as a parent."
                )

            relationship_values[other_parent_field] = other_parent_id
            relationship_values[other_parent_status_field] = "person"
        elif normalized_other_parent_kind == "muggle":
            relationship_values[other_parent_field] = ""
            relationship_values[other_parent_status_field] = "muggle"
        else:
            relationship_values[other_parent_field] = ""
            relationship_values[other_parent_status_field] = "unknown"

        if new_child_name:
            creation_values = deepcopy(
                new_child_profile if isinstance(new_child_profile, dict) else {}
            )
            creation_values.update(
                {
                    "displayed_name": new_child_name,
                    "can_give_birth": bool(new_child_can_give_birth),
                }
            )
            creation_values.update(relationship_values)

            try:
                child = self.create_person_command(creation_values)
            except ParentLocationConflict as error:
                if not self.confirm_long_distance_parent_override(error):
                    return None

                creation_values["long_distance_parent_override"] = True
                child = self.create_person_command(creation_values)
        else:
            child = self.relationship_map.person(child_record_id)

            if child is None:
                raise ValueError("Select an existing child or enter a new child's name.")

            desired_parent_ids = {
                str(relationship_values.get(field_name, "") or "")
                for field_name in (
                    "biological_mother_id",
                    "biological_father_id",
                )
                if str(relationship_values.get(field_name, "") or "")
            }

            for field_name in (current_parent_field, other_parent_field):
                parent_id = str(relationship_values.get(field_name, "") or "")
                existing_parent_id = str(child.get(field_name, "") or "")
                status_field = field_name.replace("_id", "_status")
                existing_status = self.normalized_parent_status(
                    existing_parent_id,
                    child.get(status_field, "unknown"),
                )
                new_status = self.normalized_parent_status(
                    parent_id,
                    relationship_values.get(status_field, "unknown"),
                )

                if (
                    existing_parent_id != parent_id
                    or existing_status != new_status
                ) and (
                    existing_parent_id not in desired_parent_ids
                    or existing_status == "muggle"
                ) and (existing_parent_id or existing_status == "muggle"):
                    existing_parent = self.relationship_map.person(existing_parent_id)
                    existing_name = (
                        existing_parent.get("displayed_name", "another person")
                        if existing_parent
                        else "another person"
                    )
                    replacement_parent = self.relationship_map.person(parent_id)
                    replacement_name = (
                        replacement_parent.get("displayed_name", "another person")
                        if replacement_parent
                        else "Unknown or Muggle"
                    )
                    role_label = (
                        "birthing parent"
                        if field_name == "biological_mother_id"
                        else "non-birthing parent"
                    )

                    if not messagebox.askyesno(
                        "Replace parent",
                        (
                            f"{child.get('displayed_name', 'This person')} already lists "
                            f"{existing_name} as the {role_label}. Replace that link "
                            f"with {replacement_name}?"
                        ),
                        parent=self,
                    ):
                        return None

            try:
                child = self.update_person_command(
                    child_record_id,
                    relationship_values,
                )
            except ParentLocationConflict as error:
                if not self.confirm_long_distance_parent_override(error):
                    return None

                relationship_values["long_distance_parent_override"] = True
                child = self.update_person_command(
                    child_record_id,
                    relationship_values,
                )

        mate_added = (
            normalized_other_parent_kind == "person"
            and other_parent_id
            and other_parent_id not in self.mate_ids
        )

        if mate_added:
            self.mate_ids.append(other_parent_id)
            updated_current_person = self.update_person_command(
                current_id,
                {"mate_ids": list(self.mate_ids)},
            )
            self.current_person["mate_ids"] = list(
                updated_current_person.get("mate_ids", self.mate_ids)
            )
            self.spouse_relationships = normalize_spouse_relationships(
                updated_current_person.get("spouse_relationships", [])
            )
            self.current_person["spouse_relationships"] = deepcopy(
                self.spouse_relationships
            )

        if other_parent_id:
            self.active_mate_id = other_parent_id
            self.active_spouse_owner_id = current_id
        self.refresh_people_command()
        self.reload_people()

        return child

    def confirm_long_distance_parent_override(self, error):
        return messagebox.askyesno(
            "Parents are in different locations",
            (
                f"{error}\n\n"
                "Make the parent locations match before assigning this child, "
                "or choose Yes to use the birthing parent's location, remember "
                "that choice for these parents, and add ‘Father not present at "
                "time of birth.’ to Born.\n\n"
                "Use the birth-location override?"
            ),
            parent=self,
            icon="warning",
            default="no",
        )

    def normalized_parent_status(self, parent_id, status):
        if str(parent_id or "").strip():
            return "person"

        return "muggle" if str(status or "").casefold() == "muggle" else "unknown"

    def normalize_ids(self, record_ids):
        if not isinstance(record_ids, list):
            return []

        normalized_ids = []

        for record_id in record_ids:
            normalized_id = str(record_id or "").strip()

            if normalized_id and normalized_id not in normalized_ids:
                normalized_ids.append(normalized_id)

        return normalized_ids

    def short_text(self, value, maximum_length):
        text = str(value or "").strip()

        if len(text) <= maximum_length:
            return text

        return text[: maximum_length - 1].rstrip() + "…"
