import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.sections.events.dialog import EventPersonPickerDialog
from mage_maker.sections.items.links import (
    ITEM_EVENT_NEW_OWNER_LINK_TYPES,
    normalize_item_event_new_owner,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, RoundedSelect, SoftButton


ALL_LINK_GROUPS = "All event types"
NEW_OWNER_PLACEHOLDER = "Choose new owner"


def filter_record_link_options(
    options,
    search_text="",
    selected_group=ALL_LINK_GROUPS,
    selected_ids=(),
    initial_limit=None,
    result_limit=200,
):
    normalized_search = str(search_text or "").strip().casefold()
    normalized_group = str(selected_group or ALL_LINK_GROUPS).strip()
    selected_id_set = {
        str(record_id or "").strip()
        for record_id in selected_ids or ()
        if str(record_id or "").strip()
    }
    matching_options = [
        deepcopy(option)
        for option in options or ()
        if (
            not normalized_search
            or normalized_search
            in str(option.get("search_text", "") or "").casefold()
        )
        and (
            normalized_group == ALL_LINK_GROUPS
            or option.get("group", "") == normalized_group
        )
    ]
    selected_options = [
        option
        for option in matching_options
        if option.get("value") in selected_id_set
    ]
    unselected_options = [
        option
        for option in matching_options
        if option.get("value") not in selected_id_set
    ]
    requested_limit = (
        initial_limit
        if not normalized_search and normalized_group == ALL_LINK_GROUPS
        else result_limit
    )

    if requested_limit in (None, ""):
        return matching_options, len(matching_options)

    visible_limit = max(1, int(requested_limit))
    remaining_slots = max(0, visible_limit - len(selected_options))
    visible_options = [
        *selected_options,
        *unselected_options[:remaining_slots],
    ]
    return visible_options, len(matching_options)


class RecordLinkDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        title,
        heading,
        explanation,
        options,
        selected_ids,
        save_command,
        save_button_text,
        locked_ids=(),
        group_label="",
        search_label="Search",
        initial_limit=None,
        result_limit=200,
        link_type_options=(),
        selected_link_types=None,
        link_type_default="",
        new_owner_options=(),
        recent_new_owner_options=(),
        selected_new_owners=None,
        mage_groups=(),
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.options = self.normalize_options(options)
        self.visible_options = []
        self.link_type_options = self.normalize_link_type_options(
            link_type_options
        )
        self.link_type_labels_by_value = {
            option["value"]: option["label"]
            for option in self.link_type_options
        }
        self.link_type_values_by_label = {
            option["label"]: option["value"]
            for option in self.link_type_options
        }
        self.uses_link_types = bool(self.link_type_options)
        self.new_owner_options = self.normalize_new_owner_options(
            new_owner_options
        )
        self.new_owner_labels_by_id = {
            option["value"]: option["label"]
            for option in self.new_owner_options
        }
        known_new_owner_ids = set(self.new_owner_labels_by_id)
        self.recent_new_owner_options = [
            option
            for option in self.normalize_new_owner_options(
                recent_new_owner_options
            )
            if option["value"] in known_new_owner_ids
        ]
        self.mage_groups = [
            deepcopy(group)
            for group in mage_groups or ()
            if isinstance(group, dict)
        ]
        requested_default = str(link_type_default or "").strip()
        self.link_type_default = (
            requested_default
            if requested_default in self.link_type_labels_by_value
            else (
                self.link_type_options[0]["value"]
                if self.link_type_options
                else ""
            )
        )
        known_ids = {
            option["value"]
            for option in self.options
        }
        self.locked_ids = {
            str(record_id or "").strip()
            for record_id in locked_ids or ()
            if str(record_id or "").strip() in known_ids
        }
        self.selected_ids = [
            str(record_id or "").strip()
            for record_id in selected_ids or ()
            if str(record_id or "").strip() in known_ids
        ]

        for locked_id in self.locked_ids:
            if locked_id not in self.selected_ids:
                self.selected_ids.append(locked_id)

        requested_link_types = (
            selected_link_types
            if isinstance(selected_link_types, dict)
            else {}
        )
        self.selected_link_types = {}

        for selected_id in self.selected_ids:
            requested_link_type = str(
                requested_link_types.get(selected_id, "") or ""
            ).strip()
            self.selected_link_types[selected_id] = (
                requested_link_type
                if requested_link_type in self.link_type_labels_by_value
                else self.default_link_type_for_record(selected_id)
            )

        requested_new_owners = (
            selected_new_owners
            if isinstance(selected_new_owners, dict)
            else {}
        )
        self.selected_new_owners = {}

        for selected_id in self.selected_ids:
            owner = normalize_item_event_new_owner(
                requested_new_owners.get(selected_id)
            )

            if owner["person_id"] in self.new_owner_labels_by_id:
                owner["person_name"] = self.new_owner_labels_by_id[
                    owner["person_id"]
                ]

            if owner["person_id"] or owner["person_name"]:
                self.selected_new_owners[selected_id] = owner

        self.active_record_id = (
            self.selected_ids[0] if self.selected_ids else ""
        )
        self.link_type_updating = False

        self.dialog_heading = str(heading or "Link records")
        self.explanation = str(explanation or "")
        self.save_button_text = str(save_button_text or "Save links")
        self.group_label = str(group_label or "").strip()
        self.search_label = str(search_label or "Search").strip()
        self.initial_limit = initial_limit
        self.result_limit = result_limit
        self.search_value = tk.StringVar()
        self.group_value = tk.StringVar(value=ALL_LINK_GROUPS)
        self.summary_value = tk.StringVar()
        self.link_type_value = tk.StringVar()
        self.link_type_why_value = tk.StringVar()
        self.link_type_consequence_value = tk.StringVar()
        self.new_owner_value = tk.StringVar(
            value=NEW_OWNER_PLACEHOLDER
        )
        self.title(str(title or self.dialog_heading))
        self.geometry("760x740" if self.uses_link_types else "760x620")
        self.minsize(620, 590 if self.uses_link_types else 480)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.search_value.trace_add("write", self.search_changed)
        self.group_value.trace_add("write", self.search_changed)
        self.link_type_value.trace_add("write", self.link_type_changed)
        self.refresh_options()
        self.grab_set()
        self.after_idle(self.focus_search)

    def normalize_options(self, options):
        normalized_options = []
        used_ids = set()

        for option in options or ():
            if not isinstance(option, dict):
                continue

            record_id = str(option.get("value", "") or "").strip()
            label = str(option.get("label", "") or "").strip()
            detail = str(option.get("detail", "") or "").strip()
            group = str(option.get("group", "") or "").strip()
            additional_search_text = str(
                option.get("search_text", "") or ""
            ).strip()

            if not record_id or not label or record_id in used_ids:
                continue

            used_ids.add(record_id)
            normalized_options.append(
                {
                    "value": record_id,
                    "label": label,
                    "detail": detail,
                    "group": group,
                    "default_link_type": str(
                        option.get("default_link_type", "") or ""
                    ).strip(),
                    "search_text": " ".join(
                        (
                            label,
                            detail,
                            group,
                            additional_search_text,
                        )
                    ).casefold(),
                }
            )

        return normalized_options

    def normalize_link_type_options(self, options):
        normalized_options = []
        used_values = set()

        for option in options or ():
            if not isinstance(option, dict):
                continue

            value = str(option.get("value", "") or "").strip()
            label = str(option.get("label", "") or "").strip()

            if not value or not label or value in used_values:
                continue

            used_values.add(value)
            normalized_options.append(
                {
                    "value": value,
                    "label": label,
                    "why": str(option.get("why", "") or "").strip(),
                    "consequence": str(
                        option.get("consequence", "") or ""
                    ).strip(),
                }
            )

        return normalized_options

    def normalize_new_owner_options(self, options):
        normalized_options = []
        used_values = set()

        for option in options or ():
            if not isinstance(option, dict):
                continue

            value = str(option.get("value", "") or "").strip()
            label = str(option.get("label", "") or "").strip()

            if (
                not value
                or not label
                or value in used_values
            ):
                continue

            used_values.add(value)
            normalized_options.append(
                {
                    "value": value,
                    "label": label,
                    "person": deepcopy(option.get("person", {})),
                    "group_name": str(
                        option.get("group_name", "") or ""
                    ).strip(),
                }
            )

        return normalized_options

    def default_link_type_for_record(self, record_id):
        selected_option = next(
            (
                option
                for option in self.options
                if option["value"] == record_id
            ),
            {},
        )
        requested_default = str(
            selected_option.get("default_link_type", "") or ""
        ).strip()

        if requested_default in self.link_type_labels_by_value:
            return requested_default

        return self.link_type_default

    def build_dialog(self):
        header = tk.Frame(self, bg=PRIMARY_DARK, height=60)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        heading = tk.Label(
            header,
            text=self.dialog_heading,
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(15, "bold"),
            anchor="w",
            padx=18,
        )
        heading.pack(fill="both", expand=True)
        body = tk.Frame(self, bg=SURFACE, padx=18, pady=16)
        body.grid(row=1, column=0, sticky="nsew")
        body.grid_rowconfigure(3, weight=1)
        body.grid_columnconfigure(0, weight=1)
        explanation = tk.Label(
            body,
            text=self.explanation,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
            wraplength=700,
        )
        explanation.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        filters = tk.Frame(body, bg=SURFACE)
        filters.grid(row=1, column=0, sticky="ew")
        filters.grid_columnconfigure(0, weight=1)
        search_block = tk.Frame(filters, bg=SURFACE)
        search_block.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 8) if self.group_label else 0,
        )
        search_block.grid_columnconfigure(0, weight=1)
        search_label = tk.Label(
            search_block,
            text=self.search_label,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        search_label.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.search_entry = RoundedEntry(
            search_block,
            textvariable=self.search_value,
            background=SURFACE,
            height=38,
            font=app_font(10),
        )
        self.search_entry.grid(row=1, column=0, sticky="ew")

        if self.group_label:
            group_block = tk.Frame(filters, bg=SURFACE)
            group_block.grid(row=0, column=1, sticky="ew")
            group_label = tk.Label(
                group_block,
                text=self.group_label,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            group_label.grid(row=0, column=0, sticky="ew", pady=(0, 2))
            group_values = sorted(
                {
                    option["group"]
                    for option in self.options
                    if option.get("group")
                },
                key=str.casefold,
            )
            self.group_select = RoundedSelect(
                group_block,
                self.group_value,
                [ALL_LINK_GROUPS, *group_values],
                background=SURFACE,
                width=190,
                height=38,
                font=app_font(9),
            )
            self.group_select.grid(row=1, column=0, sticky="ew")
        summary = tk.Label(
            body,
            textvariable=self.summary_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        summary.grid(row=2, column=0, sticky="ew", pady=(9, 5))
        list_frame = tk.Frame(
            body,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=3, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
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
            font=app_font(10),
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        if self.uses_link_types:
            self.listbox.bind(
                "<<ListboxSelect>>",
                self.record_selected,
            )
            self.listbox.bind(
                "<Double-Button-1>",
                self.toggle_selected,
            )
        else:
            self.listbox.bind(
                "<ButtonRelease-1>",
                self.toggle_selected,
            )
        self.listbox.bind("<space>", self.toggle_selected)
        self.listbox.bind("<Return>", self.toggle_selected)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)

        footer_row = 4

        if self.uses_link_types:
            link_type_panel = tk.Frame(
                body,
                bg=SURFACE,
                highlightbackground=BORDER_SOFT,
                highlightthickness=1,
                padx=10,
                pady=8,
            )
            link_type_panel.grid(
                row=4,
                column=0,
                sticky="ew",
                pady=(10, 0),
            )
            link_type_panel.grid_columnconfigure(1, weight=1)
            link_type_label = tk.Label(
                link_type_panel,
                text="Link type",
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            link_type_label.grid(
                row=0,
                column=0,
                sticky="w",
                padx=(0, 10),
            )
            self.link_type_select = RoundedSelect(
                link_type_panel,
                self.link_type_value,
                [
                    option["label"]
                    for option in self.link_type_options
                ],
                background=SURFACE,
                width=160,
                height=34,
                font=app_font(9),
            )
            self.link_type_select.grid(
                row=0,
                column=1,
                sticky="w",
            )
            self.toggle_link_button = SoftButton(
                link_type_panel,
                text="Link",
                command=self.toggle_selected,
                background=SURFACE,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=84,
                height=34,
                font=app_font(9, "bold"),
            )
            self.toggle_link_button.grid(
                row=0,
                column=2,
                sticky="e",
                padx=(8, 0),
            )
            self.new_owner_row = tk.Frame(
                link_type_panel,
                bg=SURFACE,
            )
            self.new_owner_row.grid(
                row=1,
                column=0,
                columnspan=3,
                sticky="ew",
                pady=(7, 0),
            )
            self.new_owner_row.grid_columnconfigure(1, weight=1)
            new_owner_label = tk.Label(
                self.new_owner_row,
                text="New owner",
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8, "bold"),
                anchor="w",
            )
            new_owner_label.grid(
                row=0,
                column=0,
                sticky="w",
                padx=(0, 10),
            )
            self.new_owner_display = tk.Label(
                self.new_owner_row,
                textvariable=self.new_owner_value,
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                font=app_font(9),
                anchor="w",
                padx=10,
                pady=8,
                highlightbackground=BORDER_SOFT,
                highlightthickness=1,
            )
            self.new_owner_display.grid(
                row=0,
                column=1,
                sticky="ew",
            )
            self.new_owner_button = SoftButton(
                self.new_owner_row,
                text="Choose person",
                command=self.open_new_owner_picker,
                background=SURFACE,
                fill=BUTTON_SOFT,
                hover_fill=BUTTON_SOFT_HOVER,
                foreground=TEXT_DARK,
                width=112,
                height=34,
                font=app_font(9, "bold"),
            )
            self.new_owner_button.grid(
                row=0,
                column=2,
                sticky="e",
                padx=(8, 0),
            )
            why_label = tk.Label(
                link_type_panel,
                textvariable=self.link_type_why_value,
                bg=SURFACE,
                fg=TEXT_DARK,
                font=app_font(9),
                anchor="w",
                justify="left",
                wraplength=650,
            )
            why_label.grid(
                row=2,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(6, 0),
            )
            consequence_label = tk.Label(
                link_type_panel,
                textvariable=self.link_type_consequence_value,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(9, "bold"),
                anchor="w",
                justify="left",
                wraplength=650,
            )
            consequence_label.grid(
                row=3,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(3, 0),
            )
            self.new_owner_row.grid_remove()
            footer_row = 5

        footer = tk.Frame(body, bg=SURFACE)
        footer.grid(
            row=footer_row,
            column=0,
            sticky="e",
            pady=(14, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=84,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        save_button = SoftButton(
            footer,
            text=self.save_button_text,
            command=self.save_links,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=36,
        )
        save_button.pack(side="left")

    def focus_search(self):
        self.search_entry.entry.focus_set()

    def search_changed(self, *arguments):
        self.refresh_options()

    def refresh_options(self):
        self.visible_options, matching_count = filter_record_link_options(
            self.options,
            self.search_value.get(),
            self.group_value.get(),
            self.selected_ids,
            self.initial_limit,
            self.result_limit,
        )
        self.listbox.delete(0, "end")

        for index, option in enumerate(self.visible_options):
            selected = option["value"] in self.selected_ids
            selected_link_type = self.selected_link_types.get(
                option["value"],
                "",
            )
            selected_owner = normalize_item_event_new_owner(
                self.selected_new_owners.get(option["value"])
            )
            selected_link_label = self.link_type_labels_by_value.get(
                selected_link_type,
                "",
            )

            if (
                selected_link_type in ITEM_EVENT_NEW_OWNER_LINK_TYPES
                and selected_owner["person_name"]
            ):
                relationship_word = (
                    "by" if selected_link_type == "taken" else "to"
                )
                selected_link_label += (
                    f" {relationship_word} {selected_owner['person_name']}"
                )
            link_type_text = (
                "  ·  " + selected_link_label
                if selected and self.uses_link_types
                else ""
            )
            detail = (
                f"  ·  {option['detail']}"
                if option["detail"]
                else ""
            )
            self.listbox.insert(
                "end",
                (
                    f"{'✓' if selected else ' '}  {option['label']}{detail}"
                    + link_type_text
                    + (
                        "  ·  Required"
                        if option["value"] in self.locked_ids
                        else ""
                    )
                ),
            )

            if option["value"] == self.active_record_id:
                self.listbox.selection_set(index)
                self.listbox.see(index)
            self.listbox.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

        selected_count = len(self.selected_ids)
        selected_text = (
            f"{selected_count} linked"
            if selected_count != 1
            else "1 linked"
        )
        visible_count = len(self.visible_options)
        self.summary_value.set(
            f"{selected_text}  ·  Showing {visible_count} of {matching_count}"
        )
        self.update_link_type_panel()

    def selected_option_id(self):
        selection = self.listbox.curselection()

        if not selection or selection[0] >= len(self.visible_options):
            return ""

        return self.visible_options[selection[0]]["value"]

    def record_selected(self, event=None):
        record_id = self.selected_option_id()

        if not record_id:
            return

        self.active_record_id = record_id
        self.update_link_type_panel()

    def toggle_selected(self, event=None):
        record_id = self.selected_option_id()

        if not record_id:
            return "break"

        if record_id in self.locked_ids:
            self.active_record_id = record_id
            self.update_link_type_panel()
            return "break"

        self.active_record_id = record_id

        if record_id in self.selected_ids:
            self.selected_ids = [
                selected_id
                for selected_id in self.selected_ids
                if selected_id != record_id
            ]
            self.selected_link_types.pop(record_id, None)
            self.selected_new_owners.pop(record_id, None)
        else:
            self.selected_ids.append(record_id)
            self.selected_link_types[record_id] = (
                self.default_link_type_for_record(record_id)
            )

        self.refresh_options()
        return "break"

    def link_type_changed(self, *arguments):
        if self.link_type_updating or not self.uses_link_types:
            return

        record_id = self.active_record_id

        if not record_id or record_id not in self.selected_ids:
            return

        requested_label = self.link_type_value.get()
        requested_value = self.link_type_values_by_label.get(
            requested_label,
            "",
        )

        if not requested_value:
            return

        self.selected_link_types[record_id] = requested_value

        if requested_value not in ITEM_EVENT_NEW_OWNER_LINK_TYPES:
            self.selected_new_owners.pop(record_id, None)

        self.refresh_options()

    def open_new_owner_picker(self):
        record_id = self.active_record_id

        if (
            not record_id
            or record_id not in self.selected_ids
            or self.selected_link_types.get(record_id)
            not in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            or not self.new_owner_options
        ):
            return False

        selected_owner = normalize_item_event_new_owner(
            self.selected_new_owners.get(record_id)
        )
        recent_owner_options = list(self.recent_new_owner_options)
        selected_owner_option = next(
            (
                option
                for option in self.new_owner_options
                if option["value"] == selected_owner["person_id"]
            ),
            None,
        )

        if selected_owner_option is not None:
            recent_owner_options = [
                selected_owner_option,
                *(
                    option
                    for option in recent_owner_options
                    if option["value"] != selected_owner["person_id"]
                ),
            ]

        EventPersonPickerDialog(
            self,
            self.new_owner_options,
            recent_owner_options,
            selected_owner["person_id"],
            self.new_owner_selected,
            mage_groups=self.mage_groups,
            dialog_title="Choose New Owner",
            heading_text="Choose the new owner",
            explanation_text=(
                "Search all people and choose who receives or takes "
                "possession of this item."
            ),
            selection_prompt="Select the item's new owner.",
            action_text="Use person",
        )
        return True

    def new_owner_selected(self, person_id):
        record_id = self.active_record_id
        normalized_person_id = str(person_id or "").strip()

        if (
            not record_id
            or record_id not in self.selected_ids
            or self.selected_link_types.get(record_id)
            not in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            or normalized_person_id not in self.new_owner_labels_by_id
        ):
            return False

        self.selected_new_owners[record_id] = {
            "person_id": normalized_person_id,
            "person_name": self.new_owner_labels_by_id[
                normalized_person_id
            ],
        }
        self.refresh_options()
        return True

    def update_link_type_panel(self):
        if not self.uses_link_types or not hasattr(
            self,
            "link_type_select",
        ):
            return

        record_id = self.active_record_id
        selected = record_id in self.selected_ids
        link_type = self.selected_link_types.get(record_id, "")
        link_type_option = next(
            (
                option
                for option in self.link_type_options
                if option["value"] == link_type
            ),
            None,
        )
        self.link_type_updating = True
        self.link_type_value.set(
            link_type_option["label"] if link_type_option else ""
        )
        self.link_type_updating = False
        self.link_type_select.set_enabled(selected)
        owner = normalize_item_event_new_owner(
            self.selected_new_owners.get(record_id)
        )
        owner_label = self.new_owner_labels_by_id.get(
            owner["person_id"],
            owner["person_name"],
        )
        self.new_owner_value.set(
            owner_label or NEW_OWNER_PLACEHOLDER
        )

        if selected and link_type in ITEM_EVENT_NEW_OWNER_LINK_TYPES:
            self.new_owner_row.grid()
            self.new_owner_button.set_enabled(
                bool(self.new_owner_options)
            )
        else:
            self.new_owner_row.grid_remove()

        if hasattr(self, "toggle_link_button"):
            self.toggle_link_button.set_text(
                "Required"
                if record_id in self.locked_ids
                else "Unlink" if selected else "Link"
            )
            self.toggle_link_button.set_enabled(
                bool(record_id) and record_id not in self.locked_ids
            )

        if link_type_option is None:
            self.link_type_why_value.set(
                "Select a linked record to choose why the item is connected."
            )
            self.link_type_consequence_value.set("")
            return

        self.link_type_why_value.set(
            f"Why linked: {link_type_option['why']}"
        )
        consequence = link_type_option["consequence"]

        if (
            link_type in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            and owner["person_name"]
        ):
            if link_type == "passed_down":
                consequence = (
                    f"The item passes to {owner['person_name']} and "
                    "continues to exist."
                )
            elif link_type == "gifted":
                consequence = (
                    f"The item is gifted to {owner['person_name']}; the "
                    "recipient becomes its owner and it continues to exist."
                )
            else:
                consequence = (
                    f"The item is taken by {owner['person_name']}; "
                    "possession changes and the item continues to exist."
                )

        self.link_type_consequence_value.set(
            f"Effect on item: {consequence}"
        )

    def save_links(self):
        for locked_id in self.locked_ids:
            if locked_id not in self.selected_ids:
                self.selected_ids.append(locked_id)

        for record_id in self.selected_ids:
            if (
                self.selected_link_types.get(record_id)
                not in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            ):
                continue

            owner = normalize_item_event_new_owner(
                self.selected_new_owners.get(record_id)
            )

            if owner["person_id"] in self.new_owner_labels_by_id:
                continue

            self.active_record_id = record_id
            self.refresh_options()
            record_label = next(
                (
                    option["label"]
                    for option in self.options
                    if option["value"] == record_id
                ),
                "this item link",
            )
            messagebox.showerror(
                "New owner required",
                f'Choose the new owner for "{record_label}".',
                parent=self,
            )
            return False

        try:
            saved = (
                self.save_command(
                    list(self.selected_ids),
                    {
                        record_id: self.selected_link_types[record_id]
                        for record_id in self.selected_ids
                    },
                    {
                        record_id: normalize_item_event_new_owner(
                            self.selected_new_owners.get(record_id)
                        )
                        for record_id in self.selected_ids
                        if self.selected_link_types.get(record_id)
                        in ITEM_EVENT_NEW_OWNER_LINK_TYPES
                    },
                )
                if self.uses_link_types
                else self.save_command(list(self.selected_ids))
            )
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save links",
                str(error),
                parent=self,
            )
            return False

        if saved is False:
            return False

        self.close_dialog()
        return True

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()
