import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, ttk

from mage_maker.sections.items.dialogs import (
    ItemCategoryDialog,
    ItemEditorDialog,
    ItemGroupDialog,
    ItemPassageDialog,
)
from mage_maker.sections.items.models import (
    UNGROUPED_ITEM_GROUP_LABEL,
    item_current_holder,
    item_is_linked_to_person,
    item_passage_rows,
    item_possession_periods,
)
from mage_maker.sections.items.timeline import ItemTimelineView
from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
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
    RoundedEntry,
    RoundedSelect,
    SectionPanel,
    SoftButton,
)


ALL_ITEM_CATEGORIES = "All categories"
ALL_ITEM_GROUPS = "All groups"


class ItemsView(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        people_provider,
        status_command=None,
        event_controller=None,
        events_changed_command=None,
        global_mode=False,
    ):
        super().__init__(parent, bg=SURFACE)
        self.controller = controller
        self.people_provider = people_provider
        self.status_command = status_command
        self.event_controller = event_controller
        self.events_changed_command = events_changed_command
        self.global_mode = bool(global_mode)
        self.current_person = {}
        self.items = []
        self.visible_items = []
        self.selected_item_id = None
        self.active_item_view = "timeline"
        self.search_value = tk.StringVar()
        self.category_value = tk.StringVar(
            value=ALL_ITEM_CATEGORIES
        )
        self.group_value = tk.StringVar(value=ALL_ITEM_GROUPS)
        self.show_all_value = tk.BooleanVar(value=self.global_mode)
        self.heading_value = tk.StringVar(value="Items")
        self.count_value = tk.StringVar(value="0 items")
        self.ownership_heading_value = tk.StringVar(
            value="Select an item"
        )
        self.ownership_holder_value = tk.StringVar(value="")
        self.empty_value = tk.StringVar(
            value=(
                "No items have been recorded."
                if self.global_mode
                else "No items are linked to this person."
            )
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.build_workspace()
        self.add_item_button.set_enabled(self.global_mode)

        if self.global_mode:
            self.show_all_check.grid_remove()
        self.search_value.trace_add("write", self.filter_changed)
        self.category_value.trace_add("write", self.filter_changed)
        self.group_value.trace_add("write", self.filter_changed)
        self.show_all_value.trace_add("write", self.filter_changed)
        self.refresh_items()

    def build_header(self):
        header = tk.Frame(self, bg=SURFACE)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            textvariable=self.heading_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(16, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        count_label = tk.Label(
            header,
            textvariable=self.count_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="e",
        )
        count_label.grid(row=0, column=1, sticky="e", padx=(8, 12))
        category_button = SoftButton(
            header,
            text="Add category",
            command=self.open_add_category_dialog,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=34,
            font=app_font(9, "bold"),
        )
        category_button.grid(row=0, column=2, padx=(0, 6))
        group_button = SoftButton(
            header,
            text="Add group",
            command=self.open_add_group_dialog,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=96,
            height=34,
            font=app_font(9, "bold"),
        )
        group_button.grid(row=0, column=3, padx=(0, 6))
        self.add_item_button = SoftButton(
            header,
            text="Add item" if self.global_mode else "Craft item",
            command=self.open_add_item_dialog,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=92,
            height=34,
            font=app_font(9, "bold"),
        )
        self.add_item_button.grid(row=0, column=4, padx=(0, 6))
        self.edit_item_button = SoftButton(
            header,
            text="Edit",
            command=self.open_edit_item_dialog,
            background=SURFACE,
            width=68,
            height=34,
            font=app_font(9, "bold"),
        )
        self.edit_item_button.grid(row=0, column=5, padx=(0, 6))
        self.delete_item_button = SoftButton(
            header,
            text="Delete",
            command=self.delete_selected_item,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=76,
            height=34,
            font=app_font(9, "bold"),
        )
        self.delete_item_button.grid(row=0, column=6)

    def build_filters(self, parent):
        filters = tk.Frame(parent, bg=SURFACE_MUTED)
        filters.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        filters.grid_columnconfigure((0, 1), weight=1, uniform="filters")
        self.search_entry = RoundedEntry(
            filters,
            textvariable=self.search_value,
            background=SURFACE_MUTED,
            height=36,
            font=app_font(10),
        )
        self.search_entry.grid(
            row=0,
            column=0,
            sticky="ew",
            columnspan=2,
            pady=(0, 8),
        )
        self.category_select = RoundedSelect(
            filters,
            self.category_value,
            [ALL_ITEM_CATEGORIES],
            background=SURFACE_MUTED,
            width=148,
            height=34,
            font=app_font(9),
        )
        self.category_select.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.group_select = RoundedSelect(
            filters,
            self.group_value,
            [ALL_ITEM_GROUPS],
            background=SURFACE_MUTED,
            width=148,
            height=34,
            font=app_font(9),
        )
        self.group_select.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )
        self.show_all_check = tk.Checkbutton(
            filters,
            text="Show all items",
            variable=self.show_all_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            activebackground=SURFACE_MUTED,
            activeforeground=TEXT_DARK,
            selectcolor=FIELD_BACKGROUND,
            font=app_font(9, "bold"),
            borderwidth=0,
            highlightthickness=0,
        )
        self.show_all_check.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(7, 0),
        )

    def build_workspace(self):
        workspace = tk.Frame(self, bg=SURFACE)
        workspace.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=(0, 18),
        )
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(
            0,
            weight=0,
            minsize=340 if self.global_mode else 440,
        )
        workspace.grid_columnconfigure(1, weight=1, minsize=680)
        item_panel = SectionPanel(
            workspace,
            "Tracked items",
            "Items remain here as they pass between people.",
        )
        item_panel.grid_rowconfigure(2, weight=1)
        item_panel.grid_columnconfigure(0, weight=1)
        item_panel.content.grid_rowconfigure(1, weight=1)
        item_panel.content.grid_columnconfigure(0, weight=1)
        self.build_filters(item_panel.content)
        self.build_item_table(item_panel.content)
        item_panel.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=(0, 7),
        )
        detail_frame = tk.Frame(workspace, bg=SURFACE)
        detail_frame.grid_rowconfigure(1, weight=1)
        detail_frame.grid_columnconfigure(0, weight=1)
        detail_frame.grid(
            row=0,
            column=1,
            sticky="nsew",
            padx=(7, 0),
        )
        self.build_item_navigation(detail_frame)
        self.item_timeline_page = tk.Frame(detail_frame, bg=SURFACE)
        self.item_timeline_page.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.item_timeline_page.grid_rowconfigure(0, weight=1)
        self.item_timeline_page.grid_columnconfigure(0, weight=1)
        self.item_timeline = ItemTimelineView(
            self.item_timeline_page,
            self.event_controller,
            self.status_command,
            self.events_changed_command,
        )
        self.item_timeline.grid(row=0, column=0, sticky="nsew")
        self.item_ownership_page = tk.Frame(
            detail_frame,
            bg=SURFACE,
        )
        self.item_ownership_page.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        self.item_ownership_page.grid_rowconfigure(0, weight=1)
        self.item_ownership_page.grid_columnconfigure(0, weight=1)
        self.build_passage_history(self.item_ownership_page)
        self.show_item_view("timeline")

    def build_item_navigation(self, parent):
        navigation = tk.Frame(parent, bg=SURFACE)
        navigation.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.timeline_button = SoftButton(
            navigation,
            text="Timeline & Events",
            command=self.show_timeline_view,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=142,
            height=34,
            font=app_font(9, "bold"),
        )
        self.timeline_button.pack(side="left", padx=(0, 6))
        self.ownership_button = SoftButton(
            navigation,
            text="Ownership History",
            command=self.show_ownership_view,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=146,
            height=34,
            font=app_font(9, "bold"),
        )
        self.ownership_button.pack(side="left")

    def show_item_view(self, view_name):
        normalized_view = (
            "ownership" if view_name == "ownership" else "timeline"
        )
        self.active_item_view = normalized_view

        if normalized_view == "timeline":
            self.item_ownership_page.grid_remove()
            self.item_timeline_page.grid()
            self.item_timeline_page.tkraise()
            self.ownership_button.set_colors(
                BUTTON_SOFT,
                BUTTON_SOFT_HOVER,
                TEXT_DARK,
            )
            self.timeline_button.set_colors(
                PRIMARY,
                PRIMARY_HOVER,
                TEXT_DARK,
            )
            self.item_timeline.refresh_events(
                reload_editor=(
                    not self.item_timeline.event_editor.has_unsaved_changes()
                )
            )
            return True

        self.item_timeline_page.grid_remove()
        self.item_ownership_page.grid()
        self.item_ownership_page.tkraise()
        self.timeline_button.set_colors(
            BUTTON_SOFT,
            BUTTON_SOFT_HOVER,
            TEXT_DARK,
        )
        self.ownership_button.set_colors(
            PRIMARY,
            PRIMARY_HOVER,
            TEXT_DARK,
        )
        return True

    def show_timeline_view(self):
        return self.show_item_view("timeline")

    def show_ownership_view(self):
        return self.show_item_view("ownership")

    def build_item_table(self, parent):
        style = ttk.Style(self)
        self.item_table_style = (
            "Items.Treeview"
            if self.global_mode
            else "MageItems.Treeview"
        )
        style.configure(
            self.item_table_style,
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            rowheight=46,
            borderwidth=0,
            indent=0,
            font=app_font(9),
        )
        style.map(
            self.item_table_style,
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        table_frame = tk.Frame(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.item_table = ttk.Treeview(
            table_frame,
            show="tree",
            selectmode="browse",
            style=self.item_table_style,
        )
        self.item_table.column(
            "#0",
            width=300,
            minwidth=220,
            stretch=True,
            anchor="w",
        )
        self.item_table.tag_configure(
            "alternate",
            background=LIST_ALTERNATE,
        )
        self.item_table.tag_configure(
            "group",
            background=SURFACE_MUTED,
            foreground=TEXT_DARK,
            font=app_font(10, "bold"),
        )
        self.item_table.grid(row=0, column=0, sticky="nsew")
        self.item_table.bind(
            "<<TreeviewSelect>>",
            self.item_selection_changed,
        )
        self.item_table.bind(
            "<Double-Button-1>",
            self.open_edit_item_dialog,
        )
        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.item_table.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.item_table.configure(yscrollcommand=scrollbar.set)
        self.empty_label = tk.Label(
            parent,
            textvariable=self.empty_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            padx=14,
            pady=14,
        )
        self.empty_label.grid(row=1, column=0, sticky="nsew")

    def build_passage_history(self, parent):
        panel = SectionPanel(
            parent,
            "Ownership timeline",
            "Ownership changes are created and edited through linked events.",
        )
        panel.grid(row=0, column=0, sticky="nsew")
        panel.content.grid_rowconfigure(1, weight=1)
        panel.content.grid_columnconfigure(0, weight=1)
        summary = tk.Frame(panel.content, bg=SURFACE_MUTED)
        summary.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        summary.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            summary,
            textvariable=self.ownership_heading_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(12, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        holder = tk.Label(
            summary,
            textvariable=self.ownership_holder_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        holder.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        style = ttk.Style(self)
        style.configure(
            "OwnershipHistory.Treeview",
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            rowheight=48,
            borderwidth=0,
            indent=0,
            font=app_font(9),
        )
        style.map(
            "OwnershipHistory.Treeview",
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        table_frame = tk.Frame(
            panel.content,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        table_frame.grid(row=1, column=0, sticky="nsew")
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.passage_table = ttk.Treeview(
            table_frame,
            show="tree",
            selectmode="browse",
            style="OwnershipHistory.Treeview",
        )
        self.passage_table.column(
            "#0",
            width=620,
            minwidth=420,
            stretch=True,
            anchor="w",
        )
        self.passage_table.tag_configure(
            "alternate",
            background=LIST_ALTERNATE,
        )
        self.passage_table.grid(row=0, column=0, sticky="nsew")
        self.passage_table.bind(
            "<<TreeviewSelect>>",
            self.passage_selection_changed,
        )
        self.passage_table.bind(
            "<Double-Button-1>",
            self.open_edit_passage_dialog,
        )
        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.passage_table.yview,
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.passage_table.configure(yscrollcommand=scrollbar.set)
        controls = tk.Frame(panel.content, bg=SURFACE_MUTED)
        controls.grid(row=2, column=0, sticky="e", pady=(10, 0))
        self.edit_passage_button = SoftButton(
            controls,
            text="Edit change",
            command=self.open_edit_passage_dialog,
            background=SURFACE_MUTED,
            width=102,
            height=34,
            font=app_font(9, "bold"),
        )
        self.edit_passage_button.pack(side="left", padx=(0, 6))
        self.delete_passage_button = SoftButton(
            controls,
            text="Delete change",
            command=self.delete_selected_passage,
            background=SURFACE_MUTED,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=34,
            font=app_font(9, "bold"),
        )
        self.delete_passage_button.pack(side="left")

    def set_person(self, person):
        if self.global_mode:
            self.refresh_items()
            return

        self.current_person = (
            deepcopy(person) if isinstance(person, dict) else {}
        )
        person_name = str(
            self.current_person.get("displayed_name", "")
            or "Unnamed person"
        ).strip()
        self.heading_value.set(f"Items · {person_name}")
        self.add_item_button.set_enabled(
            bool(self.current_person.get("record_id"))
        )
        self.refresh_items()

    def refresh_items(self, selected_item_id=None):
        self.items = (
            self.controller.list_items()
            if self.controller is not None
            else []
        )
        categories = (
            self.controller.list_categories()
            if self.controller is not None
            else []
        )
        groups = (
            self.controller.list_groups()
            if self.controller is not None
            else []
        )
        category_options = [ALL_ITEM_CATEGORIES, *categories]
        group_options = [
            ALL_ITEM_GROUPS,
            *groups,
            UNGROUPED_ITEM_GROUP_LABEL,
        ]
        self.category_select.set_values(category_options)
        self.group_select.set_values(group_options)

        if self.category_value.get() not in category_options:
            self.category_value.set(ALL_ITEM_CATEGORIES)

        if self.group_value.get() not in group_options:
            self.group_value.set(ALL_ITEM_GROUPS)

        if selected_item_id is not None:
            self.selected_item_id = selected_item_id

        self.refresh_visible_items()

    def filter_changed(self, *arguments):
        self.refresh_visible_items()

    def refresh_visible_items(self):
        search_text = self.search_value.get().strip().casefold()
        selected_category = self.category_value.get()
        selected_group = self.group_value.get()
        person_id = str(
            self.current_person.get("record_id", "") or ""
        ).strip()
        self.visible_items = []

        for item in self.items:
            holder = item_current_holder(item)
            possession_periods = item_possession_periods(
                item,
                person_id,
            )
            possession_search_text = " ".join(
                " ".join(
                    (
                        period["years"],
                        period["acquired_by"],
                        period["lost_by"],
                    )
                )
                for period in possession_periods
            )
            searchable_text = " ".join(
                (
                    item["name"],
                    item["category"],
                    item.get("group", ""),
                    item["description"],
                    item["notes"],
                    str(holder.get("person_name", "") or ""),
                    possession_search_text,
                )
            ).casefold()

            if search_text and search_text not in searchable_text:
                continue

            if (
                selected_category != ALL_ITEM_CATEGORIES
                and item["category"] != selected_category
            ):
                continue

            if (
                selected_group != ALL_ITEM_GROUPS
                and (
                    item.get("group", "")
                    if item.get("group", "")
                    else UNGROUPED_ITEM_GROUP_LABEL
                )
                != selected_group
            ):
                continue

            if (
                not self.show_all_value.get()
                and not item_is_linked_to_person(item, person_id)
            ):
                continue

            self.visible_items.append(item)

        self.render_item_table()

    def render_item_table(self):
        for item_id in self.item_table.get_children():
            self.item_table.delete(item_id)

        self.item_ids_by_row_id = {}
        person_id = str(
            self.current_person.get("record_id", "") or ""
        ).strip()
        grouped_items = {}

        for item in self.visible_items:
            group_name = str(item.get("group", "") or "").strip()
            grouped_items.setdefault(group_name, []).append(item)

        configured_groups = (
            self.controller.list_groups()
            if self.controller is not None
            else []
        )
        group_order = [
            group_name
            for group_name in configured_groups
            if group_name in grouped_items
        ]
        group_order.extend(
            sorted(
                (
                    group_name
                    for group_name in grouped_items
                    if group_name
                    and group_name not in configured_groups
                ),
                key=str.casefold,
            )
        )

        if "" in grouped_items:
            group_order.append("")

        visible_row_index = 0

        for group_index, group_name in enumerate(group_order):
            group_items = grouped_items[group_name]
            group_label = group_name or UNGROUPED_ITEM_GROUP_LABEL
            group_row_id = f"__item_group__:{group_index}"
            self.item_table.insert(
                "",
                "end",
                iid=group_row_id,
                text=(
                    f"{group_label}  ·  {len(group_items)} "
                    + ("item" if len(group_items) == 1 else "items")
                ),
                tags=("group",),
                open=True,
            )

            for item in group_items:
                holder = item_current_holder(item)
                self.item_ids_by_row_id[item["record_id"]] = item[
                    "record_id"
                ]
                self.item_table.insert(
                    group_row_id,
                    "end",
                    iid=item["record_id"],
                    text=(
                        f"{item['name']}\n"
                        + (
                            f"{item['category']} · "
                            f"{holder.get('person_name', 'Unpossessed')}"
                            if self.global_mode
                            else item["category"]
                        )
                    ),
                    tags=(
                        ("alternate",)
                        if visible_row_index % 2
                        else ()
                    ),
                    open=True,
                )
                visible_row_index += 1

                if self.global_mode:
                    continue

                for period in item_possession_periods(item, person_id):
                    row_id = (
                        f"{item['record_id']}:possession:"
                        f"{period['passage_id']}"
                    )
                    self.item_ids_by_row_id[row_id] = item[
                        "record_id"
                    ]
                    self.item_table.insert(
                        item["record_id"],
                        "end",
                        iid=row_id,
                        text=(
                            f"{period['years']}\n"
                            f"Acquired: {period['acquired_by']} · "
                            f"Lost: {period['lost_by']}"
                        ),
                        tags=(
                            ("alternate",)
                            if visible_row_index % 2
                            else ()
                        ),
                    )
                    visible_row_index += 1

        item_count = len(self.visible_items)
        self.count_value.set(
            f"{item_count} item" if item_count == 1 else f"{item_count} items"
        )

        if not self.visible_items:
            self.item_table.grid_remove()
            self.empty_label.grid()
            self.selected_item_id = None
            self.show_item_details(None)
            return

        self.empty_label.grid_remove()
        self.item_table.grid()
        visible_ids = {
            item["record_id"] for item in self.visible_items
        }

        if self.selected_item_id not in visible_ids:
            self.selected_item_id = self.visible_items[0]["record_id"]

        self.item_table.selection_set(self.selected_item_id)
        self.item_table.focus(self.selected_item_id)
        self.show_item_details(self.selected_item())

    def item_selection_changed(self, event=None):
        selection = self.item_table.selection()

        if not selection:
            return

        requested_item_id = self.item_ids_by_row_id.get(selection[0])

        if not requested_item_id:
            if self.selected_item_id:
                self.item_table.selection_set(self.selected_item_id)
                self.item_table.focus(self.selected_item_id)
            return

        if requested_item_id == self.selected_item_id:
            return

        requested_item = next(
            (
                item
                for item in self.items
                if item["record_id"] == requested_item_id
            ),
            None,
        )

        if (
            requested_item_id != self.selected_item_id
            and not self.item_timeline.set_item(requested_item)
        ):
            self.item_table.selection_set(self.selected_item_id)
            self.item_table.focus(self.selected_item_id)
            return

        self.selected_item_id = requested_item_id
        self.show_item_details(
            requested_item,
            timeline_is_current=True,
        )

    def selected_item(self):
        return next(
            (
                item
                for item in self.items
                if item["record_id"] == self.selected_item_id
            ),
            None,
        )

    def show_item_details(self, item, timeline_is_current=False):
        has_item = item is not None
        self.edit_item_button.set_enabled(has_item)
        self.delete_item_button.set_enabled(has_item)
        self.timeline_button.set_enabled(
            has_item and self.event_controller is not None
        )
        self.ownership_button.set_enabled(has_item)

        if not has_item:
            self.ownership_heading_value.set("Select an item")
            self.ownership_holder_value.set("")
            self.render_passage_history(None)
            if not timeline_is_current:
                self.item_timeline.set_item(None)
            return

        holder = item_current_holder(item)
        self.ownership_heading_value.set(item["name"])
        self.ownership_holder_value.set(
            f"Current holder: "
            f"{holder.get('person_name', 'Unpossessed')}"
        )
        self.render_passage_history(item)

        if not timeline_is_current:
            self.item_timeline.set_item(item)

    def events_for_item(self, item_id):
        if self.event_controller is None:
            return []

        return self.event_controller.events_for_item(item_id)

    def render_passage_history(self, item):
        for passage_id in self.passage_table.get_children():
            self.passage_table.delete(passage_id)

        rows = item_passage_rows(item) if item is not None else []

        for index, row in enumerate(rows):
            ownership_text = (
                f"{row['date']} · {row['method']} · "
                f"{row['from']} → {row['to']}"
            )

            if row["note"]:
                ownership_text += f"\n{row['note']}"

            self.passage_table.insert(
                "",
                "end",
                iid=row["record_id"],
                text=ownership_text,
                tags=("alternate",) if index % 2 else (),
            )

        self.edit_passage_button.set_enabled(False)
        self.delete_passage_button.set_enabled(False)

    def passage_selection_changed(self, event=None):
        passage = self.selected_passage()
        editable = bool(
            passage
            and not str(
                passage.get("source_event_id", "") or ""
            ).strip()
        )
        self.edit_passage_button.set_enabled(editable)
        self.delete_passage_button.set_enabled(editable)

    def selected_passage(self):
        item = self.selected_item()
        selection = self.passage_table.selection()

        if item is None or not selection:
            return None

        passage_id = selection[0]
        return next(
            (
                passage
                for passage in item["passage_history"]
                if passage["record_id"] == passage_id
            ),
            None,
        )

    def open_add_category_dialog(self):
        ItemCategoryDialog(self, self.save_category)

    def save_category(self, category_name):
        category = self.controller.add_category(category_name)
        self.refresh_items(self.selected_item_id)
        self.notify(f"Added item category {category}")
        return category

    def open_add_group_dialog(self):
        ItemGroupDialog(self, self.save_group)

    def save_group(self, group_name):
        group = self.controller.add_group(group_name)
        self.refresh_items(self.selected_item_id)
        self.notify(f"Added item group {group}")
        return group

    def open_add_item_dialog(self):
        if (
            not self.global_mode
            and not self.current_person.get("record_id")
        ):
            return

        ItemEditorDialog(
            self,
            self.controller.list_categories(),
            self.save_new_item,
            initial_holder=(
                None
                if self.global_mode
                else self.current_person
            ),
            groups=self.controller.list_groups(),
        )

    def save_new_item(self, values):
        person_id = str(
            self.current_person.get("record_id", "") or ""
        ).strip()
        create_crafted_event = bool(
            not self.global_mode
            and person_id
            and self.event_controller is not None
        )

        if create_crafted_event:
            item_values = deepcopy(values)
            initial_passages = list(
                item_values.get("passage_history", []) or []
            )
            crafting_date = str(
                initial_passages[0].get("date", "")
                if initial_passages
                and isinstance(initial_passages[0], dict)
                else ""
            ).strip()
            item_values["passage_history"] = []
            item = self.controller.create_item(item_values)

            try:
                self.event_controller.create_event(
                    {
                        "event_type": "item_event",
                        "title": f"Crafted {item['name']}",
                        "date": crafting_date,
                        "description": "",
                        "person_ids": [person_id],
                        "witness_person_ids": [],
                        "affected_person_ids": [],
                        "period_names": [],
                        "location_ids": [],
                        "locked_location_ids": [],
                        "item_ids": [item["record_id"]],
                        "item_link_types": {
                            item["record_id"]: "crafted"
                        },
                        "item_new_owners": {},
                    }
                )
            except Exception:
                self.controller.delete_item(item["record_id"])
                raise
        else:
            item = self.controller.create_item(values)

        self.refresh_items(item["record_id"])
        self.notify(
            f"Crafted item {item['name']}"
            if create_crafted_event
            else f"Added item {item['name']}"
        )

        if create_crafted_event and callable(
            self.events_changed_command
        ):
            self.events_changed_command()

        return item

    def open_edit_item_dialog(self, event=None):
        item = self.selected_item()

        if item is None:
            return

        ItemEditorDialog(
            self,
            self.controller.list_categories(),
            self.save_edited_item,
            item=item,
            groups=self.controller.list_groups(),
        )

    def save_edited_item(self, values):
        item_id = values["record_id"]
        item = self.controller.update_item(item_id, values)
        self.refresh_items(item["record_id"])
        self.notify(f"Saved item {item['name']}")
        return item

    def delete_selected_item(self):
        item = self.selected_item()

        if item is None:
            return

        if not self.item_timeline.confirm_unsaved_changes():
            return

        if not messagebox.askyesno(
            "Delete item",
            f"Permanently delete {item['name']} and its passage history?",
            parent=self,
            icon="warning",
            default="no",
        ):
            return

        self.controller.delete_item(item["record_id"])
        self.selected_item_id = None
        self.refresh_items()
        self.notify(f"Deleted item {item['name']}")

        if callable(self.events_changed_command):
            self.events_changed_command()

    def open_event_links(self):
        if self.selected_item() is None:
            return False

        self.show_item_view("timeline")
        return self.item_timeline.open_existing_event_links()

    def save_event_links(self, event_ids):
        return self.item_timeline.save_existing_event_links(event_ids)

    def open_add_passage_dialog(self):
        item = self.selected_item()

        if item is None:
            return

        holder = item_current_holder(item)
        ItemPassageDialog(
            self,
            (
                self.event_controller.people_options()
                if self.event_controller is not None
                else self.people_provider()
            ),
            self.save_new_passage,
            excluded_person_id=holder.get("person_id", ""),
            recent_people_options=(
                self.event_controller.recent_people_options()
                if self.event_controller is not None
                else ()
            ),
            mage_groups=(
                self.event_controller.mage_groups()
                if self.event_controller is not None
                else ()
            ),
        )

    def save_new_passage(self, values):
        item = self.selected_item()

        if item is None:
            raise ValueError("Select an item before adding passage history.")

        updated_item = self.controller.add_passage(
            item["record_id"],
            values,
        )
        self.refresh_items(updated_item["record_id"])
        new_holder_name = values["person_name"] or "Unpossessed"
        self.notify(
            f"Recorded passage of {updated_item['name']} to "
            f"{new_holder_name}"
        )
        return updated_item

    def open_edit_passage_dialog(self, event=None):
        passage = self.selected_passage()

        if passage is None:
            return

        source_event_id = str(
            passage.get("source_event_id", "") or ""
        ).strip()

        if source_event_id:
            self.show_item_view("timeline")
            self.item_timeline.selected_event_id = source_event_id
            self.item_timeline.refresh_events()
            return

        ItemPassageDialog(
            self,
            (
                self.event_controller.people_options()
                if self.event_controller is not None
                else self.people_provider()
            ),
            self.save_edited_passage,
            passage=passage,
            recent_people_options=(
                self.event_controller.recent_people_options()
                if self.event_controller is not None
                else ()
            ),
            mage_groups=(
                self.event_controller.mage_groups()
                if self.event_controller is not None
                else ()
            ),
        )

    def save_edited_passage(self, values):
        item = self.selected_item()
        passage = self.selected_passage()

        if item is None or passage is None:
            raise ValueError("Select a passage entry before editing it.")

        updated_item = self.controller.update_passage(
            item["record_id"],
            passage["record_id"],
            values,
        )
        self.refresh_items(updated_item["record_id"])
        self.notify(f"Updated passage history for {updated_item['name']}")
        return updated_item

    def delete_selected_passage(self):
        item = self.selected_item()
        passage = self.selected_passage()

        if item is None or passage is None:
            return

        if str(passage.get("source_event_id", "") or "").strip():
            return

        if not messagebox.askyesno(
            "Delete passage entry",
            "Delete this holder from the item's passage history?",
            parent=self,
            icon="warning",
            default="no",
        ):
            return

        updated_item = self.controller.delete_passage(
            item["record_id"],
            passage["record_id"],
        )
        self.refresh_items(updated_item["record_id"])
        self.notify(f"Updated passage history for {updated_item['name']}")

    def notify(self, message):
        if callable(self.status_command):
            self.status_command(message)
