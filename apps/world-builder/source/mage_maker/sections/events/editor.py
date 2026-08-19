import tkinter as tk
from copy import deepcopy
from time import monotonic

from mage_maker.core.wizarding_currency import (
    currency_component_input_is_valid,
)
from mage_maker.sections.events.types import (
    EVENT_TYPE_LABELS,
    event_type_from_label,
    event_type_label,
    event_type_options,
)
from mage_maker.sections.events.dialog import (
    EventLocationPickerDialog,
    EventPersonPickerDialog,
)
from mage_maker.sections.events.eminence_picker import (
    EventEminencePicker,
)
from mage_maker.sections.events.models import (
    normalize_world_event_date,
    split_world_event_date,
)
from mage_maker.sections.items.link_dialog import RecordLinkDialog
from mage_maker.sections.items.links import (
    ITEM_EVENT_NEW_OWNER_LINK_TYPES,
    item_event_link_type_label,
    item_event_link_type_options,
    normalize_item_event_link_type,
    normalize_item_event_link_types,
    normalize_item_event_new_owners,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
)
from mage_maker.ui.theme import (
    BORDER_SOFT,
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
    CalendarAdoptionNotice,
    LabeledEntry,
    RoundedEntry,
    RoundedSelect,
    RoundedText,
    SoftButton,
)


NEW_EVENT_DRAFT_ID = "__new-event-draft__"
EVENT_TYPE_DEFAULT_TITLES = {
    "born": "Birth",
    "died": "death",
    "murder": "Murder",
    "returns_as_ghost": "Returns as ghost",
    "romance": "Romance",
    "breakup": "Breakup",
    "travel": "Travel",
    "item_event": "Item event",
    "joined_faction": "Joined a faction",
    "left_faction": "Left a faction",
}


def split_editor_date(value):
    date_text = str(value or "").strip()

    if not date_text:
        return "", "", ""

    negative = date_text.startswith("-")
    date_body = date_text[1:] if negative else date_text
    parts = date_body.split("-")
    year = parts[0] if parts else ""

    if negative and year:
        year = f"-{year}"

    month = parts[1] if len(parts) > 1 else ""
    day = parts[2] if len(parts) > 2 else ""
    return year, month, day


class EventAssociationPicker(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        association_kind,
        background=SURFACE_MUTED,
        heading_text="",
        select_button_text="",
    ):
        super().__init__(
            parent,
            bg=background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=3,
            pady=2,
        )
        self.controller = controller
        self.association_kind = str(association_kind or "")
        self.background = background
        self.heading_text = str(heading_text or "").strip()
        self.select_button_text = str(
            select_button_text or ""
        ).strip()
        self.options = []
        self.options_by_id = {}
        self.options_loaded = False
        self.options_revision = None
        self.options_mode = None
        self.visible_options = []
        self.selected_ids = []
        self.locked_ids = set()
        self.locked_order = []
        self.excluded_ids = set()
        self.is_enabled = True
        self.single_selection = False
        self.foundation_only = False
        self.include_recent = True
        self.change_command = None
        self.instruction_text = ""
        self.result_heading_value = tk.StringVar(value="Recently viewed")
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_controls()

    def build_controls(self):
        heading_row = tk.Frame(self, bg=self.background)
        heading_row.grid(row=0, column=0, sticky="ew", pady=(0, 1))
        heading_row.grid_columnconfigure(0, weight=1)
        heading_labels = {
            "people": "People",
            "locations": "Locations",
            "organizations": "Organizations",
        }
        self.heading_value = tk.StringVar(
            value=heading_labels.get(
                self.association_kind,
                "Records",
            )
        )

        if self.heading_text:
            self.heading_value.set(self.heading_text)

        heading = tk.Label(
            heading_row,
            textvariable=self.heading_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        recent_heading = tk.Label(
            heading_row,
            textvariable=self.result_heading_value,
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        recent_heading.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(8, 0),
        )
        list_frame = tk.Frame(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.listbox = tk.Listbox(
            list_frame,
            height=4,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(8),
            activestyle="none",
            exportselection=False,
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind(
            "<<ListboxSelect>>",
            self.selection_changed,
        )
        self.listbox.bind("<ButtonRelease-1>", self.toggle_selected)
        self.listbox.bind("<space>", self.toggle_selected)
        self.listbox.bind("<Return>", self.toggle_selected)
        scrollbar = tk.Scrollbar(list_frame, command=self.listbox.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.listbox.configure(yscrollcommand=scrollbar.set)
        select_button_labels = {
            "people": "Select another person",
            "locations": "Select another location",
            "organizations": "Select an organization",
        }
        self.select_button = SoftButton(
            self,
            text=select_button_labels.get(
                self.association_kind,
                "Select a record",
            ),
            command=self.open_selector,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            height=22,
            font=app_font(8, "bold"),
        )
        if self.select_button_text:
            self.select_button.set_text(self.select_button_text)
        self.select_button.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(1, 0),
        )

    def set_values(self, selected_ids=(), locked_ids=()):
        self.selected_ids = []

        for association_id in selected_ids:
            normalized_id = str(association_id or "").strip()

            if normalized_id and normalized_id not in self.selected_ids:
                self.selected_ids.append(normalized_id)

        self.locked_order = []

        for association_id in locked_ids:
            locked_id = str(association_id or "").strip()

            if locked_id and locked_id not in self.locked_order:
                self.locked_order.append(locked_id)

        self.locked_ids = set(self.locked_order)

        for locked_id in self.locked_order:
            if locked_id not in self.selected_ids:
                self.selected_ids.append(locked_id)

        if self.single_selection and len(self.selected_ids) > 1:
            if self.locked_order:
                self.selected_ids = self.locked_order[:1]
            else:
                self.selected_ids = self.selected_ids[-1:]

        self.refresh_options()

    def set_instruction(self, instruction=""):
        self.instruction_text = str(instruction or "").strip()
        self.refresh_results()

    def get_values(self):
        return list(self.selected_ids)

    def set_excluded_ids(self, excluded_ids=()):
        self.excluded_ids = {
            str(association_id or "").strip()
            for association_id in excluded_ids
            if str(association_id or "").strip()
        }
        self.selected_ids = [
            association_id
            for association_id in self.selected_ids
            if association_id not in self.excluded_ids
            or association_id in self.locked_ids
        ]
        self.options_loaded = False
        self.refresh_options()

    def refresh_options(self):
        database = getattr(self.controller, "database", None)
        database_revision = getattr(database, "revision", None)
        cacheable = isinstance(database_revision, int)
        options_mode = (
            self.association_kind,
            bool(getattr(self, "foundation_only", False)),
            tuple(sorted(getattr(self, "excluded_ids", set()))),
            tuple(sorted(self.selected_ids))
            if self.association_kind == "locations"
            and getattr(self, "foundation_only", False)
            else (),
        )

        if (
            getattr(self, "options_loaded", False)
            and cacheable
            and getattr(self, "options_revision", None)
            == database_revision
            and getattr(self, "options_mode", None) == options_mode
        ):
            self.refresh_results()
            return

        if self.association_kind == "people":
            recent_options = (
                self.controller.recent_people_options(limit=5)
                if self.include_recent
                else []
            )
            requested_ids = [
                *self.selected_ids,
                *self.locked_order,
                *(
                    str(option.get("value", "") or "").strip()
                    for option in recent_options
                    if isinstance(option, dict)
                ),
            ]
            targeted_provider = getattr(
                self.controller,
                "people_options_for_ids",
                None,
            )
            self.options = (
                targeted_provider(requested_ids)
                if callable(targeted_provider)
                else self.controller.people_options()
            )
        elif self.association_kind == "organizations":
            self.options = self.controller.organization_options()
        else:
            if getattr(self, "foundation_only", False):
                self.options = self.controller.location_options(
                    available_for_founding=True,
                    include_ids=self.selected_ids,
                )
            else:
                self.options = self.controller.location_options()

        excluded_ids = getattr(self, "excluded_ids", set())
        self.options = [
            option
            for option in self.options
            if str(option.get("value", "") or "").strip()
            not in excluded_ids
        ]

        self.options_by_id = {
            str(option.get("value", "") or "").strip(): option
            for option in self.options
            if str(option.get("value", "") or "").strip()
        }
        self.options_loaded = True
        self.options_revision = (
            database_revision if cacheable else None
        )
        self.options_mode = options_mode

        self.refresh_results()

    def recent_options(self, limit=12):
        if self.association_kind == "people":
            return self.controller.recent_people_options(limit=limit)

        if self.association_kind == "organizations":
            return []

        return self.controller.recent_location_options(limit=limit)

    def refresh_results(self, *arguments):
        options_by_id = getattr(self, "options_by_id", {})

        if not options_by_id and self.options:
            options_by_id = {
                str(option.get("value", "") or ""): option
                for option in self.options
                if str(option.get("value", "") or "").strip()
            }
            self.options_by_id = options_by_id
        visible_ids = []

        for association_id in self.locked_order:
            if association_id in options_by_id:
                visible_ids.append(association_id)

        for association_id in self.selected_ids:
            if (
                association_id in options_by_id
                and association_id not in visible_ids
            ):
                visible_ids.append(association_id)

        if self.include_recent:
            recent_count = 0

            for option in self.recent_options():
                association_id = str(
                    option.get("value", "") or ""
                ).strip()

                if (
                    not association_id
                    or association_id in self.locked_ids
                    or association_id
                    in getattr(self, "excluded_ids", set())
                ):
                    continue

                if association_id not in visible_ids:
                    visible_ids.append(association_id)

                recent_count += 1

                if recent_count >= 5:
                    break

        self.visible_options = [
            deepcopy(options_by_id[association_id])
            for association_id in visible_ids
            if association_id in options_by_id
        ]

        instruction_text = str(
            getattr(self, "instruction_text", "") or ""
        ).strip()

        if instruction_text:
            self.result_heading_value.set(instruction_text)
        elif (
            self.association_kind == "people"
            and self.locked_ids
            and not self.include_recent
        ):
            self.result_heading_value.set("Current person")
        elif self.association_kind == "people" and self.locked_ids:
            self.result_heading_value.set(
                "Current person and recently viewed"
            )
        elif self.selected_ids:
            self.result_heading_value.set(
                "Selected and recently viewed"
            )
        else:
            self.result_heading_value.set(
                "Recently viewed"
                if self.visible_options
                else "No recently viewed records"
            )

        self.render_results()

    def render_results(self):
        selected_row_id = self.selected_row_id()
        self.listbox.delete(0, "end")

        for index, option in enumerate(self.visible_options):
            association_id = str(option.get("value", "") or "")
            label = str(option.get("label", "") or "Unnamed")

            if association_id in self.locked_ids:
                display_label = (
                    f"✓ {label}  ·  current person"
                    if self.association_kind == "people"
                    else f"✓ {label}  ·  fixed"
                )
            elif association_id in self.selected_ids:
                display_label = f"✓ {label}"
            else:
                display_label = label

            self.listbox.insert("end", display_label)
            self.listbox.itemconfigure(
                index,
                background=(
                    FIELD_BACKGROUND
                    if index % 2 == 0
                    else LIST_ALTERNATE
                ),
            )

            if association_id == selected_row_id:
                self.listbox.selection_set(index)

        self.selection_changed()

    def selected_row_id(self):
        selected = self.listbox.curselection()

        if not selected or selected[0] >= len(self.visible_options):
            return ""

        return str(
            self.visible_options[selected[0]].get("value", "") or ""
        ).strip()

    def selection_changed(self, event=None):
        return self.selected_row_id()

    def toggle_selected(self, event=None):
        if not self.is_enabled:
            return "break"

        association_id = self.selected_row_id()

        if not association_id or association_id in self.locked_ids:
            return "break"

        if association_id in self.selected_ids:
            self.selected_ids = [
                selected_id
                for selected_id in self.selected_ids
                if selected_id != association_id
            ]
        elif self.single_selection:
            self.selected_ids = [
                locked_id
                for locked_id in self.locked_order
            ]
            self.selected_ids.append(association_id)
        else:
            self.selected_ids.append(association_id)

        if (
            self.association_kind == "locations"
            and association_id in self.selected_ids
        ):
            remember_selection = getattr(
                self.controller,
                "remember_location_selection",
                None,
            )

            if callable(remember_selection):
                remember_selection(association_id)

        self.refresh_results()

        if self.change_command is not None:
            self.change_command()

        return "break"

    def open_selector(self):
        if not self.is_enabled:
            return False

        selected_id = next(
            (
                association_id
                for association_id in reversed(self.selected_ids)
                if association_id not in self.locked_ids
            ),
            "",
        )

        if self.association_kind == "people":
            # Opening the chooser is the deliberate point at which the full
            # searchable People catalogue is needed.  Merely viewing an event
            # keeps the picker scoped to its linked and recent people.
            self.options = self.controller.people_options()
            self.options_by_id = {
                str(option.get("value", "") or "").strip(): option
                for option in self.options
                if str(option.get("value", "") or "").strip()
            }
            recent_options = [
                option
                for option in self.recent_options(limit=12)
                if str(option.get("value", "") or "").strip()
                not in self.locked_ids
                and str(option.get("value", "") or "").strip()
                not in getattr(self, "excluded_ids", set())
            ][:5]
            EventPersonPickerDialog(
                self,
                self.options,
                recent_options,
                selected_id,
                self.selector_chosen,
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
            )
        elif self.association_kind == "locations":
            location_records = (
                self.controller.location_records(
                    available_for_founding=True,
                    include_ids=self.selected_ids,
                )
                if getattr(self, "foundation_only", False)
                else self.controller.location_records()
            )
            EventLocationPickerDialog(
                self,
                location_records,
                selected_id,
                self.selector_chosen,
                create_location_command=getattr(
                    self.controller,
                    "create_placeholder_location",
                    None,
                ),
                recent_location_options=self.recent_options(
                    limit=5
                ),
                selection_history_command=getattr(
                    self.controller,
                    "remember_location_selection",
                    None,
                ),
            )
        else:
            OrganizationSelectionDialog(
                self,
                self.controller.organization_records(),
                self.organization_selector_chosen,
            )

        return True

    def selector_chosen(self, association_id):
        normalized_id = str(association_id or "").strip()

        if not normalized_id:
            return False

        if normalized_id in getattr(self, "excluded_ids", set()):
            return False

        if self.association_kind == "people":
            targeted_provider = getattr(
                self.controller,
                "people_options_for_ids",
                None,
            )
            if callable(targeted_provider):
                option_by_id = {
                    str(option.get("value", "") or "").strip(): option
                    for option in self.options
                    if str(option.get("value", "") or "").strip()
                }
                option_by_id.update(
                    {
                        str(option.get("value", "") or "").strip(): option
                        for option in targeted_provider(
                            (*self.selected_ids, normalized_id)
                        )
                    }
                )
                self.options = list(option_by_id.values())
            else:
                self.options = self.controller.people_options()
        elif self.association_kind == "organizations":
            self.options = self.controller.organization_options()
        else:
            if getattr(self, "foundation_only", False):
                self.options = self.controller.location_options(
                    available_for_founding=True,
                    include_ids=(*self.selected_ids, normalized_id),
                )
            else:
                self.options = self.controller.location_options()

        self.options_by_id = {
            str(option.get("value", "") or "").strip(): option
            for option in self.options
            if str(option.get("value", "") or "").strip()
        }

        if self.single_selection:
            self.selected_ids = [
                locked_id
                for locked_id in self.locked_order
            ]

        if normalized_id not in self.selected_ids:
            self.selected_ids.append(normalized_id)

        self.refresh_results()

        for index, option in enumerate(self.visible_options):
            if str(option.get("value", "") or "") != normalized_id:
                continue

            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(index)
            self.listbox.see(index)
            break

        self.selection_changed()

        if self.change_command is not None:
            self.change_command()

        return True

    def organization_selector_chosen(self, organization):
        if not isinstance(organization, dict):
            return False

        return self.selector_chosen(
            organization.get("record_id", "")
        )

    def set_enabled(self, enabled):
        self.is_enabled = bool(enabled)
        self.listbox.configure(state="normal")
        self.select_button.set_enabled(self.is_enabled)


class MurderAdditionalPeopleDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        controller,
        witness_person_ids=(),
        affected_person_ids=(),
        saved_command=None,
    ):
        super().__init__(parent)
        self.saved_command = saved_command
        self.title("Event witnesses and affected people")
        self.geometry("780x430")
        self.minsize(660, 360)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        content = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=12,
            pady=10,
        )
        content.grid(row=0, column=0, sticky="nsew", padx=14, pady=14)
        content.grid_rowconfigure(1, weight=1)
        content.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="murder_additional_people",
        )

        explanation = tk.Label(
            content,
            text=(
                "Choose any witnesses and people affected by this event. "
                "Save this dialog to return them to the event."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        explanation.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 8),
        )

        self.witnesses_picker = EventAssociationPicker(
            content,
            controller,
            "people",
            background=SURFACE_MUTED,
            heading_text="Witnessed by",
            select_button_text="Select another witness",
        )
        self.witnesses_picker.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 5),
        )
        self.witnesses_picker.set_values(witness_person_ids)

        self.affected_picker = EventAssociationPicker(
            content,
            controller,
            "people",
            background=SURFACE_MUTED,
            heading_text="Affected by",
            select_button_text="Select another affected person",
        )
        self.affected_picker.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(5, 0),
        )
        self.affected_picker.set_values(affected_person_ids)

        footer = tk.Frame(content, bg=SURFACE)
        footer.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="e",
            pady=(10, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=82,
            height=30,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        save_button = SoftButton(
            footer,
            text="Save people",
            command=self.save_people,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=108,
            height=30,
        )
        save_button.pack(side="left")
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.bind("<Escape>", self.close_dialog)

    def save_people(self):
        if callable(self.saved_command):
            saved = self.saved_command(
                self.witnesses_picker.get_values(),
                self.affected_picker.get_values(),
            )

            if saved is False:
                return False

        self.destroy()
        return True

    def close_dialog(self, event=None):
        self.destroy()
        return "break" if event is not None else True


class EventEditor(tk.Frame):
    def __init__(
        self,
        parent,
        controller,
        save_command,
        cancel_command=None,
        context="period",
        background=SURFACE_MUTED,
    ):
        super().__init__(
            parent,
            bg=background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        self.controller = controller
        self.save_command = save_command
        self.cancel_command = cancel_command
        self.context = str(context or "period")
        self.compact_no_scroll = self.context == "location"
        self.background = background
        self.event = {}
        self.storage_kind = "shared"
        self.editor_mode = "empty"
        self.controls_enabled = False
        self.read_only = True
        self.lock_type = False
        self.lock_title = False
        self.lock_date = False
        self.lock_people = False
        self.description_only = False
        self.title_and_description_only = False
        self.title_from_location = False
        self.hide_locations = False
        self.feedback_after_id = None
        self.minimum_year = None
        self.maximum_year = None
        self.founding_title_locked = False
        self.generated_founding_title = ""
        self.generated_extinction_title = ""
        self.generated_job_event_title = ""
        self.generated_event_type_title = ""
        self.previous_event_type = ""
        self.saved_editor_values = None
        self.saving = False
        self.association_selection_guard_until = 0.0
        self.job_event_options = []
        self.job_event_options_by_label = {}
        self.heading_value = tk.StringVar(value="Event details")
        self.explanation_value = tk.StringVar(
            value="Select an event or add a new one."
        )
        self.title_value = tk.StringVar()
        self.event_type_value = tk.StringVar()
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        self.time_value = tk.StringVar()
        self.comparison_events = []
        self.comparison_events_set = False
        self.period_value = tk.StringVar(value="Period: determined by year")
        self.feedback_value = tk.StringVar()
        self.murder_witnesses_summary_value = tk.StringVar(
            value="Witnessed: None"
        )
        self.murder_affected_summary_value = tk.StringVar(
            value="Affected by: None"
        )
        self.selected_item_ids = []
        self.locked_item_ids = []
        self.selected_item_link_types = {}
        self.selected_item_new_owners = {}
        self.items_summary_value = tk.StringVar(value="Items: None")
        self.job_event_value = tk.StringVar()
        self.salary_galleons_value = tk.StringVar(value="0")
        self.salary_sickles_value = tk.StringVar(value="0")
        self.salary_knuts_value = tk.StringVar(value="0")
        self.job_end_year_value = tk.StringVar()
        self.job_end_month_value = tk.StringVar()
        self.job_end_day_value = tk.StringVar()
        self.character_control_link_id = ""
        self.character_control_link_collection = ""
        self.character_control_link_name = tk.StringVar(value="No linked record")
        self.adjusting_year = False
        self.year_value.trace_add("write", self.update_period_display)
        self.month_value.trace_add("write", self.update_period_display)
        self.day_value.trace_add("write", self.update_period_display)
        self.year_value.trace_add("write", self.update_time_visibility)
        self.month_value.trace_add("write", self.update_time_visibility)
        self.day_value.trace_add("write", self.update_time_visibility)
        self.time_value.trace_add("write", self.update_time_visibility)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.scrollbar_visible = True
        self.build_scrollable_form()

        for compact_picker in (
            self.baby_picker,
            self.birthing_parent_picker,
            self.non_birthing_parent_picker,
            self.perpetrators_picker,
            self.victims_picker,
            self.locations_picker,
        ):
            compact_picker.listbox.configure(height=3)

        if self.context == "location":
            self.people_picker.listbox.configure(height=4)
            self.baby_picker.listbox.configure(height=3)
            self.birthing_parent_picker.listbox.configure(height=3)
            self.non_birthing_parent_picker.listbox.configure(height=3)
            self.perpetrators_picker.listbox.configure(height=3)
            self.victims_picker.listbox.configure(height=3)
            self.witnesses_picker.listbox.configure(height=3)
            self.affected_picker.listbox.configure(height=3)
            self.locations_picker.listbox.configure(height=3)
            self.scrollbar.grid_remove()
            self.scrollbar_visible = False

        self.event_type_value.trace_add(
            "write",
            self.event_type_changed,
        )
        self.job_event_value.trace_add(
            "write",
            self.job_event_selection_changed,
        )
        self.clear()

    def build_scrollable_form(self):
        self.canvas = tk.Canvas(
            self,
            bg=self.background,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.form = tk.Frame(
            self.canvas,
            bg=self.background,
            padx=8,
            pady=3,
        )
        self.form_window = self.canvas.create_window(
            0,
            0,
            window=self.form,
            anchor="nw",
        )
        self.form.grid_columnconfigure(0, weight=1)
        self.form.bind("<Configure>", self.form_resized)
        self.canvas.bind("<Configure>", self.canvas_resized)
        self.canvas.bind("<MouseWheel>", self.mousewheel)
        self.form.bind("<MouseWheel>", self.mousewheel)
        self.build_form()

    def build_form(self):
        form_columnspan = 2 if self.compact_no_scroll else 1

        if self.compact_no_scroll:
            self.form.grid_columnconfigure(
                (0, 1),
                weight=1,
                uniform="location_event_compact",
            )

        header = tk.Frame(self.form, bg=self.background)
        header.grid(
            row=0,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
            pady=(0, 2),
        )
        header.grid_columnconfigure(1, weight=1)
        heading = tk.Label(
            header,
            textvariable=self.heading_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="w", padx=(0, 12))
        explanation = tk.Label(
            header,
            textvariable=self.explanation_value,
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="e",
            justify="right",
            wraplength=500,
        )
        explanation.grid(row=0, column=1, sticky="ew")
        main_fields = tk.Frame(self.form, bg=self.background)
        main_fields.grid(
            row=1,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
        )
        main_fields.grid_columnconfigure(0, weight=2)
        main_fields.grid_columnconfigure(1, weight=3)
        type_panel = tk.Frame(main_fields, bg=self.background)
        type_panel.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        type_panel.grid_columnconfigure(0, weight=1)
        type_label = tk.Label(
            type_panel,
            text="Event type",
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="w",
        )
        type_label.grid(row=0, column=0, sticky="ew", pady=(0, 2))
        self.type_picker = RoundedSelect(
            type_panel,
            textvariable=self.event_type_value,
            values=[],
            background=self.background,
            height=24,
            font=app_font(9),
        )
        self.type_picker.grid(row=1, column=0, sticky="ew")
        self.title_field = LabeledEntry(
            main_fields,
            "Event title",
            self.title_value,
            background=self.background,
            control_height=24,
        )
        self.title_field.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(5, 0),
        )
        date_panel = tk.Frame(self.form, bg=self.background)
        self.date_panel = date_panel
        date_panel.grid(
            row=2,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
            pady=(1, 0),
        )
        date_panel.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.year_field = LabeledEntry(
            date_panel,
            "Year",
            self.year_value,
            background=self.background,
            control_height=24,
        )
        self.year_field.grid(row=0, column=0, sticky="ew", padx=(0, 4))
        self.year_field.control.bind_input(
            "<FocusOut>",
            self.clamp_year_to_editor_bounds,
        )
        self.month_field = LabeledEntry(
            date_panel,
            "Month",
            self.month_value,
            background=self.background,
            control_height=24,
        )
        self.month_field.grid(row=0, column=1, sticky="ew", padx=4)
        self.day_field = LabeledEntry(
            date_panel,
            "Day",
            self.day_value,
            background=self.background,
            control_height=24,
        )
        self.day_field.grid(row=0, column=2, sticky="ew", padx=(4, 0))
        self.time_field = LabeledEntry(
            date_panel,
            "Time (HHMM, 24-hour)",
            self.time_value,
            background=self.background,
            control_height=24,
        )
        self.time_field.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(8, 0),
        )
        self.time_field.grid_remove()
        calendar_notice = CalendarAdoptionNotice(
            date_panel,
            background=self.background,
            wraplength=560,
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
            pady=(1, 0),
        )
        self.job_event_panel = tk.Frame(
            self.form,
            bg=self.background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=5,
            pady=3,
        )
        self.job_event_panel.grid(
            row=3,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
            pady=(2, 0),
        )
        self.job_event_panel.grid_columnconfigure(0, weight=2)
        self.job_event_panel.grid_columnconfigure(
            (1, 2, 3),
            weight=1,
        )
        job_label = tk.Label(
            self.job_event_panel,
            text="Organization job",
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8, "bold"),
            anchor="w",
        )
        job_label.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.job_event_picker = RoundedSelect(
            self.job_event_panel,
            textvariable=self.job_event_value,
            values=[],
            background=self.background,
            height=24,
            font=app_font(8),
        )
        self.job_event_picker.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.job_salary_label = tk.Label(
            self.job_event_panel,
            text="Starting monthly salary",
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8, "bold"),
            anchor="w",
        )
        self.job_salary_label.grid(
            row=0,
            column=1,
            columnspan=3,
            sticky="ew",
            padx=(4, 0),
        )
        self.job_salary_entries = []

        for column, label_text, value, maximum in (
            (1, "Galleons", self.salary_galleons_value, ""),
            (2, "Sickles", self.salary_sickles_value, "16"),
            (3, "Knuts", self.salary_knuts_value, "28"),
        ):
            salary_block = tk.Frame(
                self.job_event_panel,
                bg=self.background,
            )
            salary_block.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(4, 0),
            )
            salary_block.grid_columnconfigure(0, weight=1)
            salary_label = tk.Label(
                salary_block,
                text=label_text,
                bg=self.background,
                fg=TEXT_MUTED,
                font=app_font(7, "bold"),
                anchor="w",
            )
            salary_label.grid(row=0, column=0, sticky="ew")
            salary_entry = RoundedEntry(
                salary_block,
                textvariable=value,
                background=self.background,
                width=92,
                height=24,
                font=app_font(8),
                justify="center",
            )
            salary_entry.grid(
                row=1,
                column=0,
                sticky="ew",
                pady=(1, 0),
            )
            salary_entry.entry.configure(
                validate="key",
                validatecommand=(
                    self.register(currency_component_input_is_valid),
                    "%P",
                    maximum,
                ),
            )
            self.job_salary_entries.append(salary_entry)

        self.job_end_date_panel = tk.Frame(
            self.job_event_panel,
            bg=self.background,
        )
        self.job_end_date_panel.grid(
            row=2,
            column=0,
            columnspan=4,
            sticky="ew",
            pady=(4, 0),
        )
        self.job_end_date_panel.grid_columnconfigure(
            (0, 1, 2),
            weight=1,
        )
        job_end_heading = tk.Label(
            self.job_end_date_panel,
            text="End date",
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8, "bold"),
            anchor="w",
        )
        job_end_heading.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        self.job_end_date_entries = []

        for column, label_text, value in (
            (0, "Year", self.job_end_year_value),
            (1, "Month", self.job_end_month_value),
            (2, "Day", self.job_end_day_value),
        ):
            end_date_block = tk.Frame(
                self.job_end_date_panel,
                bg=self.background,
            )
            end_date_block.grid(
                row=1,
                column=column,
                sticky="ew",
                padx=(0, 4) if column < 2 else 0,
            )
            end_date_block.grid_columnconfigure(0, weight=1)
            end_date_label = tk.Label(
                end_date_block,
                text=label_text,
                bg=self.background,
                fg=TEXT_MUTED,
                font=app_font(7, "bold"),
                anchor="w",
            )
            end_date_label.grid(row=0, column=0, sticky="ew")
            end_date_entry = RoundedEntry(
                end_date_block,
                textvariable=value,
                background=self.background,
                height=24,
                font=app_font(8),
                justify="center",
            )
            end_date_entry.grid(
                row=1,
                column=0,
                sticky="ew",
                pady=(1, 0),
            )
            self.job_end_date_entries.append(end_date_entry)

        self.job_end_calendar_notice = CalendarAdoptionNotice(
            self.job_end_date_panel,
            background=self.background,
            wraplength=540,
            date_variables=(
                self.job_end_year_value,
                self.job_end_month_value,
                self.job_end_day_value,
            ),
        )
        self.job_end_calendar_notice.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(2, 0),
        )

        self.job_event_panel.grid_remove()
        description_heading = tk.Frame(
            self.form,
            bg=self.background,
        )
        description_heading.grid(
            row=4,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
            pady=(1, 1),
        )
        description_heading.grid_columnconfigure(0, weight=1)
        description_label = tk.Label(
            description_heading,
            text="Description",
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        )
        description_label.grid(row=0, column=0, sticky="w")
        period_label = tk.Label(
            description_heading,
            textvariable=self.period_value,
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="e",
        )
        period_label.grid(row=0, column=1, sticky="e", padx=(12, 0))
        self.description_control = RoundedText(
            self.form,
            background=self.background,
            height=4 if self.compact_no_scroll else 1,
            minimum_height=96 if self.compact_no_scroll else 43,
            font=app_font(9),
        )
        self.description_control.grid(
            row=5,
            column=0,
            sticky="nsew" if self.compact_no_scroll else "ew",
            padx=(0, 4) if self.compact_no_scroll else 0,
        )
        self.association_panel = tk.Frame(
            self.form,
            bg=self.background,
        )
        if self.compact_no_scroll:
            self.association_panel.grid(
                row=5,
                column=1,
                sticky="nsew",
                padx=(4, 0),
            )
        else:
            self.association_panel.grid(
                row=6,
                column=0,
                sticky="ew",
                pady=(1, 0),
            )
        self.association_panel.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="event_associations",
        )
        self.people_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
        )
        self.people_picker.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 4),
        )
        self.people_picker.change_command = (
            self.people_selection_changed
        )
        self.baby_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Baby",
            select_button_text="Select the baby",
        )
        self.baby_picker.single_selection = True
        self.baby_picker.change_command = (
            self.birth_people_selection_changed
        )
        self.baby_picker.grid_remove()
        self.birthing_parent_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Birthing parent",
            select_button_text="Select the birthing parent",
        )
        self.birthing_parent_picker.single_selection = True
        self.birthing_parent_picker.change_command = (
            self.birth_people_selection_changed
        )
        self.birthing_parent_picker.grid_remove()
        self.non_birthing_parent_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Non-Birthing parent",
            select_button_text="Select the non-birthing parent",
        )
        self.non_birthing_parent_picker.single_selection = True
        self.non_birthing_parent_picker.change_command = (
            self.birth_people_selection_changed
        )
        self.non_birthing_parent_picker.grid_remove()
        self.perpetrators_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Perpetrator",
            select_button_text="Select another perpetrator",
        )
        self.perpetrators_picker.change_command = (
            self.murder_people_selection_changed
        )
        self.perpetrators_picker.grid_remove()
        self.victims_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Victim",
            select_button_text="Select another victim",
        )
        self.victims_picker.change_command = (
            self.murder_people_selection_changed
        )
        self.victims_picker.grid_remove()
        self.witnesses_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Witness",
            select_button_text="Select another witness",
        )
        self.witnesses_picker.change_command = (
            self.murder_people_selection_changed
        )
        self.witnesses_picker.grid_remove()
        self.affected_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "people",
            background=self.background,
            heading_text="Affected by",
            select_button_text="Select another affected person",
        )
        self.affected_picker.change_command = (
            self.murder_people_selection_changed
        )
        self.affected_picker.grid_remove()
        self.murder_additional_people_panel = tk.Frame(
            self.association_panel,
            bg=self.background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=4,
            pady=2,
        )
        self.murder_additional_people_panel.grid_columnconfigure(
            (0, 1),
            weight=1,
            uniform="event_ancillary_people",
        )
        witnesses_summary = tk.Label(
            self.murder_additional_people_panel,
            textvariable=self.murder_witnesses_summary_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=205,
        )
        witnesses_summary.grid(row=0, column=0, sticky="ew")
        affected_summary = tk.Label(
            self.murder_additional_people_panel,
            textvariable=self.murder_affected_summary_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8),
            anchor="w",
            justify="left",
            wraplength=205,
        )
        affected_summary.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(6, 0),
        )
        self.murder_additional_people_button = SoftButton(
            self.murder_additional_people_panel,
            text="Edit witnesses / affected by",
            command=self.open_murder_additional_people_dialog,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=174,
            height=24,
            font=app_font(8, "bold"),
        )
        self.murder_additional_people_button.grid(
            row=0,
            column=2,
            sticky="e",
            padx=(8, 0),
        )
        self.murder_additional_people_panel.grid_remove()
        self.locations_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "locations",
            background=self.background,
        )
        self.locations_picker.change_command = (
            self.location_selection_changed
        )
        self.locations_picker.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(4, 0),
        )
        self.organizations_picker = EventAssociationPicker(
            self.association_panel,
            self.controller,
            "organizations",
            background=self.background,
        )
        self.organizations_picker.single_selection = True
        self.organizations_picker.include_recent = False
        self.organizations_picker.change_command = (
            self.organization_selection_changed
        )
        self.organizations_picker.grid_remove()
        self.eminence_picker = EventEminencePicker(
            self.association_panel,
            self.controller,
            self.background,
        )
        self.eminence_picker.grid_remove()
        self.character_control_link_panel = tk.Frame(
            self.association_panel,
            bg=self.background,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=4,
            pady=3,
        )
        self.character_control_link_panel.grid_columnconfigure(0, weight=1)
        tk.Label(
            self.character_control_link_panel,
            textvariable=self.character_control_link_name,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(9, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew")
        SoftButton(
            self.character_control_link_panel,
            text="Choose...",
            command=self.open_character_control_link,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=84,
            height=24,
            font=app_font(8, "bold"),
        ).grid(row=0, column=1, padx=(6, 0))
        SoftButton(
            self.character_control_link_panel,
            text="Clear",
            command=self.clear_character_control_link,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=62,
            height=24,
            font=app_font(8, "bold"),
        ).grid(row=0, column=2, padx=(4, 0))
        self.character_control_link_panel.grid_remove()
        footer = tk.Frame(self.form, bg=self.background)
        footer.grid(
            row=7,
            column=0,
            columnspan=form_columnspan,
            sticky="ew",
            pady=(1, 0),
        )
        footer.grid_columnconfigure(0, weight=1)
        feedback = tk.Label(
            footer,
            textvariable=self.feedback_value,
            bg=self.background,
            fg=TEXT_DARK,
            font=app_font(8, "bold"),
            anchor="w",
            justify="left",
            wraplength=230,
        )
        feedback.grid(row=0, column=0, sticky="ew")
        items_summary = tk.Label(
            footer,
            textvariable=self.items_summary_value,
            bg=self.background,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="e",
        )
        items_summary.grid(row=0, column=1, padx=(8, 0))
        self.link_items_button = SoftButton(
            footer,
            text="Link items",
            command=self.open_item_links,
            background=self.background,
            fill=FIELD_BACKGROUND,
            hover_fill=LIST_SELECTED,
            foreground=TEXT_DARK,
            width=82,
            height=24,
            font=app_font(8, "bold"),
        )
        self.link_items_button.grid(row=0, column=2, padx=(5, 0))
        self.cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.cancel,
            background=self.background,
            width=76,
            height=24,
            font=app_font(8, "bold"),
        )
        self.cancel_button.grid(row=0, column=3, padx=(5, 0))
        self.save_button = SoftButton(
            footer,
            text="Save event",
            command=self.save,
            background=self.background,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=98,
            height=24,
            font=app_font(8, "bold"),
        )
        self.save_button.grid(row=0, column=4, padx=(5, 0))

    def form_resized(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        self.after_idle(self.update_scrollbar_visibility)

    def canvas_resized(self, event):
        self.canvas.itemconfigure(
            self.form_window,
            width=max(1, event.width),
        )
        self.after_idle(self.update_scrollbar_visibility)

    def update_scrollbar_visibility(self):
        if self.compact_no_scroll:
            if self.scrollbar_visible:
                self.scrollbar.grid_remove()
                self.scrollbar_visible = False

            self.canvas.yview_moveto(0)
            return

        bounds = self.canvas.bbox("all")
        content_height = (
            max(0, bounds[3] - bounds[1])
            if bounds
            else 0
        )
        available_height = max(1, self.canvas.winfo_height())
        needs_scrollbar = content_height > available_height + 2

        if needs_scrollbar and not self.scrollbar_visible:
            self.scrollbar.grid(row=0, column=1, sticky="ns")
            self.scrollbar_visible = True
        elif not needs_scrollbar and self.scrollbar_visible:
            self.scrollbar.grid_remove()
            self.scrollbar_visible = False
            self.canvas.yview_moveto(0)

    def mousewheel(self, event):
        if not self.scrollbar_visible:
            return None

        if event.delta:
            self.canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units",
            )

        return "break"

    def clear(self, message="Select an event or add a new one."):
        self.event = {}
        self.storage_kind = "shared"
        self.editor_mode = "empty"
        self.read_only = True
        self.lock_type = False
        self.lock_title = False
        self.lock_date = False
        self.lock_people = False
        self.description_only = False
        self.title_and_description_only = False
        self.title_from_location = False
        self.founding_title_locked = False
        self.generated_founding_title = ""
        self.generated_extinction_title = ""
        self.generated_job_event_title = ""
        self.generated_event_type_title = ""
        self.previous_event_type = ""
        self.people_picker.include_recent = True
        self.people_picker.single_selection = False
        self.baby_picker.include_recent = True
        self.birthing_parent_picker.include_recent = True
        self.non_birthing_parent_picker.include_recent = True
        self.perpetrators_picker.include_recent = True
        self.victims_picker.include_recent = True
        self.witnesses_picker.include_recent = True
        self.affected_picker.include_recent = True
        self.locations_picker.single_selection = False
        self.locations_picker.foundation_only = False
        if hasattr(self.locations_picker, "set_instruction"):
            self.locations_picker.set_instruction("")
        self.set_year_bounds()
        self.heading_value.set("Event details")
        self.explanation_value.set(message)
        self.title_value.set("")
        self.event_type_value.set("")
        self.year_value.set("")
        self.month_value.set("")
        self.day_value.set("")
        self.time_value.set("")
        if hasattr(self, "job_event_value"):
            self.job_event_value.set("")
            self.salary_galleons_value.set("0")
            self.salary_sickles_value.set("0")
            self.salary_knuts_value.set("0")
            if hasattr(self, "job_end_year_value"):
                self.job_end_year_value.set("")
                self.job_end_month_value.set("")
                self.job_end_day_value.set("")
            self.job_event_panel.grid_remove()
        self.description_control.text.configure(state="normal")
        self.description_control.text.delete("1.0", "end")
        self.people_picker.set_values(())
        self.baby_picker.set_values(())
        self.birthing_parent_picker.set_values(())
        self.non_birthing_parent_picker.set_values(())
        self.perpetrators_picker.set_values(())
        self.victims_picker.set_values(())
        self.witnesses_picker.set_values(())
        self.affected_picker.set_values(())
        self.update_murder_additional_people_summary()
        self.selected_item_ids = []
        self.locked_item_ids = []
        self.selected_item_link_types = {}
        self.selected_item_new_owners = {}
        self.clear_character_control_link()
        self.update_items_summary()

        if hasattr(self, "eminence_picker"):
            self.eminence_picker.set_values((), (), {}, "")

        self.locations_picker.set_values(())
        if hasattr(self, "organizations_picker"):
            self.organizations_picker.set_values(())
        self.show_locations(True)
        self.set_controls_enabled(False)
        self.clear_feedback()
        self.canvas.yview_moveto(0)
        self.saved_editor_values = None
        self.saving = False

    def start_new(
        self,
        context=None,
        default_person_ids=(),
        locked_person_ids=(),
        default_location_ids=(),
        locked_location_ids=(),
        default_item_ids=(),
        locked_item_ids=(),
        default_item_link_types=None,
        default_item_new_owners=None,
        hide_locations=False,
        minimum_year=None,
        maximum_year=None,
    ):
        self.event = {}
        self.storage_kind = "shared"
        self.editor_mode = "new"
        self.context = str(context or self.context or "period")
        self.read_only = False
        self.lock_type = False
        self.lock_title = False
        self.lock_date = False
        self.lock_people = False
        self.description_only = False
        self.title_and_description_only = False
        self.title_from_location = False
        self.founding_title_locked = False
        self.generated_founding_title = ""
        self.generated_extinction_title = ""
        self.generated_job_event_title = ""
        self.generated_event_type_title = ""
        self.previous_event_type = ""
        self.people_picker.include_recent = True
        self.people_picker.single_selection = False
        self.baby_picker.include_recent = True
        self.birthing_parent_picker.include_recent = True
        self.non_birthing_parent_picker.include_recent = True
        self.perpetrators_picker.include_recent = True
        self.victims_picker.include_recent = True
        self.witnesses_picker.include_recent = True
        self.affected_picker.include_recent = True
        self.locations_picker.single_selection = False
        self.locations_picker.foundation_only = False
        if hasattr(self.locations_picker, "set_instruction"):
            self.locations_picker.set_instruction("")
        self.set_year_bounds(minimum_year, maximum_year)
        self.heading_value.set("New event")
        self.explanation_value.set(
            "Choose the event type, enter its date, and link the records it belongs to."
        )
        self.title_value.set("")
        self.year_value.set("")
        self.month_value.set("")
        self.day_value.set("")
        self.time_value.set("")
        if hasattr(self, "job_event_value"):
            self.job_event_value.set("")
            self.salary_galleons_value.set("0")
            self.salary_sickles_value.set("0")
            self.salary_knuts_value.set("0")
            if hasattr(self, "job_end_year_value"):
                self.job_end_year_value.set("")
                self.job_end_month_value.set("")
                self.job_end_day_value.set("")
        self.description_control.text.configure(state="normal")
        self.description_control.text.delete("1.0", "end")
        self.clear_character_control_link()
        self.configure_type_options()
        self.event_type_value.set(self.default_type_label())
        self.people_picker.set_values(
            default_person_ids,
            locked_person_ids,
        )
        self.baby_picker.set_values(())
        self.birthing_parent_picker.set_values(())
        self.non_birthing_parent_picker.set_values(())
        self.perpetrators_picker.set_values(())
        self.victims_picker.set_values(())
        self.witnesses_picker.set_values(())
        self.affected_picker.set_values(())
        self.update_murder_additional_people_summary()
        self.locked_item_ids = list(
            dict.fromkeys(
                str(item_id or "").strip()
                for item_id in locked_item_ids or ()
                if str(item_id or "").strip()
            )
        )
        self.selected_item_ids = list(
            dict.fromkeys(
                [
                    *(
                        str(item_id or "").strip()
                        for item_id in default_item_ids or ()
                        if str(item_id or "").strip()
                    ),
                    *self.locked_item_ids,
                ]
            )
        )
        self.selected_item_link_types = normalize_item_event_link_types(
            default_item_link_types,
            self.selected_item_ids,
            event_type_from_label(
                self.event_type_value.get(),
                "other",
            ),
        )
        self.selected_item_new_owners = normalize_item_event_new_owners(
            default_item_new_owners,
            self.selected_item_ids,
            self.selected_item_link_types,
        )
        self.update_items_summary()
        if hasattr(self, "eminence_picker"):
            self.eminence_picker.set_values(
                self.people_picker.get_values(),
                (),
                {},
                NEW_EVENT_DRAFT_ID,
            )
        self.locations_picker.set_values(
            default_location_ids,
            locked_location_ids,
        )
        if hasattr(self, "organizations_picker"):
            self.organizations_picker.set_values(())
        self.show_locations(not hide_locations)
        self.set_controls_enabled(True)
        self.clear_feedback()
        self.update_period_display()
        self.canvas.yview_moveto(0)
        self.saved_editor_values = None

    def is_new_event(self):
        return self.editor_mode == "new" and not self.read_only

    def ensure_new_event_editable(self):
        if not self.is_new_event():
            return False

        self.set_controls_enabled(True)

        if self.description_only:
            self.description_control.text.focus_set()
        else:
            self.title_field.control.focus_set()

        return True

    def begin_edit(self):
        if (
            not self.event
            or self.read_only
            or self.editor_mode not in ("view", "edit")
        ):
            return False

        self.editor_mode = "edit"
        self.heading_value.set("Edit event")
        self.explanation_value.set(
            "Changes saved here update this event everywhere it appears."
        )
        self.set_controls_enabled(True)
        self.type_picker.set_enabled(
            not self.description_only and not self.lock_type
        )

        if self.description_only:
            self.description_control.text.focus_set()
        else:
            self.title_field.control.focus_set()

        return True

    def ensure_loaded_event_editable(self):
        if not self.event or self.read_only:
            return False

        return self.begin_edit()

    def load_event(
        self,
        event,
        storage_kind="shared",
        context=None,
        person_ids=(),
        locked_person_ids=(),
        location_ids=(),
        locked_location_ids=(),
        item_ids=(),
        locked_item_ids=(),
        hide_locations=False,
        read_only=False,
        explanation="",
        minimum_year=None,
        maximum_year=None,
        lock_title=False,
        lock_date=False,
        lock_people=False,
        single_location=False,
        title_from_location=False,
        display_title=None,
        description_only=False,
        title_and_description_only=False,
    ):
        self.event = deepcopy(event) if isinstance(event, dict) else {}
        self.storage_kind = str(storage_kind or "shared")
        self.context = str(context or self.context or "period")
        self.read_only = bool(read_only)
        self.editor_mode = "view" if self.read_only else "edit"
        self.set_year_bounds(minimum_year, maximum_year)
        self.lock_type = bool(
            self.event.get("automatic_source")
            or self.event.get("organization_event")
        )
        self.lock_title = bool(
            lock_title or self.event.get("organization_event")
        )
        self.lock_date = bool(lock_date)
        self.lock_people = bool(lock_people)
        self.description_only = bool(description_only)
        self.title_and_description_only = bool(
            title_and_description_only
        )
        self.title_from_location = bool(title_from_location)
        self.founding_title_locked = False
        self.generated_founding_title = ""
        self.generated_extinction_title = ""
        self.generated_job_event_title = ""
        self.people_picker.include_recent = not self.lock_people
        self.baby_picker.include_recent = not self.lock_people
        self.birthing_parent_picker.include_recent = not self.lock_people
        self.non_birthing_parent_picker.include_recent = (
            not self.lock_people
        )
        self.perpetrators_picker.include_recent = not self.lock_people
        self.victims_picker.include_recent = not self.lock_people
        self.witnesses_picker.include_recent = not self.lock_people
        self.affected_picker.include_recent = not self.lock_people
        loaded_event_type = str(
            self.event.get("event_type", "") or ""
        ).strip()
        self.previous_event_type = loaded_event_type
        self.locations_picker.single_selection = bool(
            single_location
            or loaded_event_type in (
                "relocated",
                "founding",
                "extinction",
                "born",
                "died",
                "murder",
            )
        )
        self.people_picker.single_selection = loaded_event_type in (
            "died",
            "returns_as_ghost",
        )
        self.locations_picker.foundation_only = (
            self.event.get("event_type") == "founding"
        )
        self.heading_value.set(
            "Event details" if self.read_only else "Edit event"
        )
        self.explanation_value.set(
            explanation
            or (
                "This event is generated from its source record."
                if self.read_only
                else "Changes saved here update this event everywhere it appears."
            )
        )
        loaded_title = (
            self.loaded_title()
            if display_title is None
            else str(display_title or "")
        )
        self.title_value.set(loaded_title)
        loaded_default_title = EVENT_TYPE_DEFAULT_TITLES.get(
            loaded_event_type,
            "",
        )
        self.generated_event_type_title = (
            loaded_default_title
            if loaded_default_title
            and loaded_title.strip() == loaded_default_title
            else ""
        )
        self.configure_type_options()
        self.event_type_value.set(
            event_type_label(self.event.get("event_type"))
        )
        year, month, day = split_editor_date(
            self.event.get("date", "")
        )
        self.year_value.set(year)
        self.month_value.set(month)
        self.day_value.set(day)
        self.time_value.set(
            str(self.event.get("time", "") or "").strip()
        )
        loaded_type = str(self.event.get("event_type", "") or "")
        if loaded_type in ("taught_spell", "taught_proficiency", "taught_recipe"):
            self.character_control_link_id = str(self.event.get("knowledge_record_id", "") or "")
            self.character_control_link_collection = str(self.event.get("knowledge_collection", "") or "")
            self.character_control_link_name.set(str(self.event.get("knowledge_name", "") or "Linked taught record"))
        elif loaded_type in ("tamed_creature", "bonded_creature", "irked_creature"):
            self.character_control_link_id = str(self.event.get("named_creature_id", "") or "")
            self.character_control_link_collection = "named_creatures"
            self.character_control_link_name.set(str(self.event.get("named_creature_name", "") or "Linked named creature"))
        else:
            self.clear_character_control_link()
        self.load_job_event_values()
        self.update_job_event_panel()
        self.description_control.text.configure(state="normal")
        self.description_control.text.delete("1.0", "end")
        self.description_control.text.insert(
            "1.0",
            self.loaded_description(),
        )
        stored_person_ids = self.event.get("person_ids", [])
        stored_location_ids = self.event.get("location_ids", [])
        stored_locked_location_ids = self.event.get(
            "locked_location_ids",
            [],
        )
        self.people_picker.set_values(
            list(stored_person_ids or ()) + list(person_ids or ()),
            locked_person_ids,
        )
        baby_ids = list(
            self.event.get("baby_person_ids", []) or ()
        )
        if (
            loaded_event_type == "born"
            and not baby_ids
            and self.context == "person"
            and self.event.get("automatic_source") == "life_start"
        ):
            current_person_ids = list(
                dict.fromkeys(
                    str(person_id or "").strip()
                    for person_id in (
                        *locked_person_ids,
                        *person_ids,
                    )
                    if str(person_id or "").strip()
                )
            )
            baby_ids = current_person_ids[:1]
        birthing_parent_ids = list(
            self.event.get("birthing_parent_person_ids", []) or ()
        )
        non_birthing_parent_ids = list(
            self.event.get(
                "non_birthing_parent_person_ids",
                [],
            )
            or ()
        )
        self.baby_picker.set_values(
            baby_ids,
            (
                baby_ids
                if loaded_event_type == "born"
                and self.event.get("automatic_source")
                in ("birth_event", "life_start")
                else ()
            ),
        )
        self.birthing_parent_picker.set_values(birthing_parent_ids)
        self.non_birthing_parent_picker.set_values(
            non_birthing_parent_ids
        )
        self.birthing_parent_picker.set_excluded_ids(baby_ids)
        self.non_birthing_parent_picker.set_excluded_ids(baby_ids)
        perpetrator_ids = list(
            self.event.get("perpetrator_person_ids", []) or ()
        )
        victim_ids = list(
            self.event.get("victim_person_ids", []) or ()
        )
        witness_ids = list(
            self.event.get("witness_person_ids", []) or ()
        )
        affected_ids = list(
            self.event.get("affected_person_ids", []) or ()
        )
        locked_role_ids = set()
        self.perpetrators_picker.set_values(
            perpetrator_ids,
            [
                person_id
                for person_id in perpetrator_ids
                if person_id in locked_role_ids
            ],
        )
        self.victims_picker.set_values(
            victim_ids,
            [
                person_id
                for person_id in victim_ids
                if person_id in locked_role_ids
            ],
        )
        self.witnesses_picker.set_values(
            witness_ids,
            [
                person_id
                for person_id in witness_ids
                if person_id in locked_role_ids
            ],
        )
        self.affected_picker.set_values(
            affected_ids,
            [
                person_id
                for person_id in affected_ids
                if person_id in locked_role_ids
            ],
        )
        self.update_murder_additional_people_summary()
        self.locked_item_ids = list(
            dict.fromkeys(
                str(item_id or "").strip()
                for item_id in locked_item_ids or ()
                if str(item_id or "").strip()
            )
        )
        self.selected_item_ids = list(
            dict.fromkeys(
                [
                    *(
                        str(item_id or "").strip()
                        for item_id in self.event.get("item_ids", []) or ()
                        if str(item_id or "").strip()
                    ),
                    *(
                        str(item_id or "").strip()
                        for item_id in item_ids or ()
                        if str(item_id or "").strip()
                    ),
                    *self.locked_item_ids,
                ]
            )
        )
        self.selected_item_link_types = normalize_item_event_link_types(
            self.event.get("item_link_types"),
            self.selected_item_ids,
            loaded_event_type,
        )
        self.selected_item_new_owners = normalize_item_event_new_owners(
            self.event.get("item_new_owners"),
            self.selected_item_ids,
            self.selected_item_link_types,
        )
        self.update_items_summary()
        if hasattr(self, "eminence_picker"):
            eminence_candidate_ids = (
                list(
                    dict.fromkeys(
                        [
                            *perpetrator_ids,
                            *witness_ids,
                            *affected_ids,
                        ]
                    )
                )
                if loaded_event_type == "murder"
                else list(
                    dict.fromkeys(
                        [
                            *self.people_picker.get_values(),
                            *witness_ids,
                            *affected_ids,
                        ]
                    )
                )
            )

            if loaded_event_type in ("born", "died"):
                eminence_candidate_ids = []
            self.eminence_picker.set_values(
                eminence_candidate_ids,
                self.event.get("eminence_person_ids", []),
                self.event.get("eminence_skills", {}),
                self.event.get(
                    "record_id",
                    self.event.get("event_id", ""),
                ),
            )
        loaded_location_ids = (
            list(stored_location_ids or ()) + list(location_ids or ())
        )
        loaded_locked_location_ids = (
            list(stored_locked_location_ids or ())
            + list(locked_location_ids or ())
        )

        if loaded_event_type == "relocated" and loaded_location_ids:
            loaded_location_ids = loaded_location_ids[-1:]
            loaded_locked_location_ids = []

        self.locations_picker.set_values(
            loaded_location_ids,
            loaded_locked_location_ids,
        )
        organization_id = str(
            self.event.get("organization_id", "") or ""
        ).strip()
        if hasattr(self, "organizations_picker"):
            self.organizations_picker.set_values(
                (organization_id,) if organization_id else (),
                (
                    (organization_id,)
                    if organization_id
                    and self.event.get("organization_event")
                    else ()
                ),
            )
            self.organization_selection_changed()
        self.location_selection_changed()
        self.show_locations(not hide_locations)
        self.set_controls_enabled(not self.read_only)
        self.clear_feedback()
        self.update_period_display()
        self.update_time_visibility()
        self.canvas.yview_moveto(0)
        self.saved_editor_values = deepcopy(self.values())

    def loaded_title(self):
        if self.storage_kind == "shared":
            return str(self.event.get("title", "") or "")

        if self.storage_kind == "timeline":
            return str(self.event.get("detail", "") or "")

        return str(self.event.get("title", "") or "")

    def loaded_description(self):
        if self.storage_kind == "shared":
            return str(self.event.get("description", "") or "")

        return str(self.event.get("note", "") or "")

    def refresh_job_event_options(self):
        if not hasattr(self, "job_event_picker"):
            return

        option_provider = getattr(
            self.controller,
            "organization_job_options",
            None,
        )
        self.job_event_options = (
            list(option_provider())
            if callable(option_provider)
            else []
        )
        self.job_event_options_by_label = {
            str(option.get("label", "") or ""): option
            for option in self.job_event_options
            if str(option.get("label", "") or "").strip()
        }
        self.job_event_picker.set_values(
            list(self.job_event_options_by_label)
        )

    def selected_job_event_option(self):
        if not hasattr(self, "job_event_value"):
            return None

        return self.job_event_options_by_label.get(
            self.job_event_value.get(),
        )

    def load_job_event_values(self):
        if not hasattr(self, "job_event_value"):
            return

        if str(
            self.event.get("event_type", "") or ""
        ).strip() not in ("started_job", "received_raise"):
            self.job_event_options = []
            self.job_event_options_by_label = {}
            self.job_event_picker.set_values([])
            self.job_event_value.set("")
            self.salary_galleons_value.set("0")
            self.salary_sickles_value.set("0")
            self.salary_knuts_value.set("0")
            if hasattr(self, "job_end_year_value"):
                self.job_end_year_value.set("")
                self.job_end_month_value.set("")
                self.job_end_day_value.set("")
            return

        self.refresh_job_event_options()
        organization_id = str(
            self.event.get("organization_id", "") or ""
        ).strip()
        organization_job_id = str(
            self.event.get("organization_job_id", "") or ""
        ).strip()
        selected_label = ""

        for option in self.job_event_options:
            if (
                str(option.get("organization_id", "") or "")
                == organization_id
                and str(
                    option.get("organization_job_id", "") or ""
                )
                == organization_job_id
            ):
                selected_label = str(
                    option.get("label", "") or ""
                )
                break

        self.job_event_value.set(selected_label)
        salary = self.event.get("salary")

        if isinstance(salary, dict):
            self.salary_galleons_value.set(
                str(salary.get("galleons", 0) or 0)
            )
            self.salary_sickles_value.set(
                str(salary.get("sickles", 0) or 0)
            )
            self.salary_knuts_value.set(
                str(salary.get("knuts", 0) or 0)
            )
        else:
            self.salary_galleons_value.set("0")
            self.salary_sickles_value.set("0")
            self.salary_knuts_value.set("0")

        if hasattr(self, "job_end_year_value"):
            end_year, end_month, end_day = split_world_event_date(
                self.event.get("job_end_date", "")
            )
            self.job_end_year_value.set(end_year)
            self.job_end_month_value.set(end_month)
            self.job_end_day_value.set(end_day)

    def job_event_selection_changed(self, *arguments):
        option = self.selected_job_event_option()

        if option is None:
            return

        generated_title = str(
            option.get("event_title", option.get("label", ""))
            or ""
        ).strip()
        current_title = self.title_value.get().strip()

        if (
            generated_title
            and (
                not current_title
                or current_title == self.generated_job_event_title
            )
        ):
            self.title_value.set(generated_title)

        self.generated_job_event_title = generated_title

    def update_job_event_panel(self):
        if not hasattr(self, "job_event_panel"):
            return

        event_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )
        is_job_event = event_type in (
            "started_job",
            "received_raise",
        )

        if not is_job_event:
            self.job_event_panel.grid_remove()
            self.form.after_idle(self.form_resized)
            return

        self.refresh_job_event_options()
        self.job_salary_label.configure(
            text=(
                "New monthly salary"
                if event_type == "received_raise"
                else "Starting monthly salary"
            )
        )
        self.job_event_panel.grid()
        self.job_event_picker.set_enabled(self.controls_enabled)

        for salary_entry in self.job_salary_entries:
            salary_entry.set_enabled(self.controls_enabled)

        if (
            event_type == "started_job"
            and hasattr(self, "job_end_date_panel")
        ):
            self.job_end_date_panel.grid()

            for end_date_entry in self.job_end_date_entries:
                end_date_entry.set_enabled(self.controls_enabled)
        elif hasattr(self, "job_end_date_panel"):
            self.job_end_date_panel.grid_remove()

        self.form.after_idle(self.form_resized)

    def configure_type_options(self):
        options = event_type_options(
            self.context,
            include_automatic=bool(
                self.event.get("automatic_source")
            ),
            current_event_type=self.event.get("event_type"),
        )
        self.type_picker.set_values(
            [label for event_type, label in options]
        )

    def default_type_label(self):
        if self.context == "item":
            return EVENT_TYPE_LABELS["item_event"]

        if self.context == "person":
            return EVENT_TYPE_LABELS["custom"]

        return EVENT_TYPE_LABELS["other"]

    def set_year_bounds(self, minimum_year=None, maximum_year=None):
        self.minimum_year = (
            int(minimum_year)
            if minimum_year not in (None, "")
            else None
        )
        self.maximum_year = (
            int(maximum_year)
            if maximum_year not in (None, "")
            else None
        )

        if self.minimum_year is None or self.maximum_year is None:
            self.year_field.label.configure(text="Year")
            return

        self.year_field.label.configure(
            text=(
                f"Year ({self.minimum_year:,} to "
                f"{self.maximum_year:,})"
            )
        )

    def show_locations(self, visible):
        self.hide_locations = not bool(visible)

        self.update_association_layout()
        self.form.after_idle(self.form_resized)

    def update_association_layout(self):
        event_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )
        self.people_picker.grid_remove()
        self.baby_picker.grid_remove()
        self.birthing_parent_picker.grid_remove()
        self.non_birthing_parent_picker.grid_remove()
        self.perpetrators_picker.grid_remove()
        self.victims_picker.grid_remove()
        self.witnesses_picker.grid_remove()
        self.affected_picker.grid_remove()
        self.murder_additional_people_panel.grid_remove()
        self.locations_picker.grid_remove()
        if hasattr(self, "organizations_picker"):
            self.organizations_picker.grid_remove()

        if hasattr(self, "eminence_picker"):
            self.eminence_picker.grid_remove()

        if event_type == "murder":
            self.perpetrators_picker.grid(
                row=0,
                column=0,
                sticky="ew",
                padx=(0, 4),
            )
            self.victims_picker.grid(
                row=0,
                column=1,
                sticky="ew",
                padx=(4, 0),
            )
            self.murder_additional_people_panel.grid(
                row=1,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(3, 0),
            )

            if not self.hide_locations:
                self.locations_picker.grid(
                    row=2,
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    pady=(3, 0),
                )

            if hasattr(self, "eminence_picker"):
                self.eminence_picker.grid(
                    row=(3 if not self.hide_locations else 2),
                    column=0,
                    columnspan=2,
                    sticky="ew",
                    pady=(3, 0),
                )

            return

        if event_type == "born":
            self.birthing_parent_picker.grid(
                row=0,
                column=0,
                sticky="ew",
                padx=(0, 4),
            )
            self.non_birthing_parent_picker.grid(
                row=0,
                column=1,
                sticky="ew",
                padx=(4, 0),
            )
            self.baby_picker.grid(
                row=1,
                column=0,
                sticky="ew",
                padx=(0, 4),
                pady=(4, 0),
            )

            if not self.hide_locations:
                self.locations_picker.grid(
                    row=1,
                    column=1,
                    sticky="ew",
                    padx=(4, 0),
                    pady=(4, 0),
                )

            self.murder_additional_people_panel.grid(
                row=2,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(3, 0),
            )

            return

        self.people_picker.grid(
            row=0,
            column=0,
            columnspan=(
                1
                if event_type in ("organization_founding", "joined_faction", "left_faction")
                or not self.hide_locations
                else 2
            ),
            sticky="ew",
            padx=(0, 4) if not self.hide_locations else 0,
        )

        if (
            event_type in ("organization_founding", "joined_faction", "left_faction")
            and hasattr(self, "organizations_picker")
        ):
            self.organizations_picker.grid(
                row=0,
                column=1,
                sticky="ew",
                padx=(4, 0),
            )
        elif not self.hide_locations:
            self.locations_picker.grid(
                row=0,
                column=1,
                sticky="ew",
                padx=(4, 0),
            )

        self.murder_additional_people_panel.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(3, 0),
        )

        if hasattr(self, "eminence_picker") and event_type != "died":
            self.eminence_picker.grid(
                row=2,
                column=0,
                columnspan=2,
                sticky="ew",
                pady=(3, 0),
            )

    def set_controls_enabled(self, enabled):
        editable = bool(enabled)
        self.controls_enabled = editable
        field_editable = (
            editable
            and not self.description_only
            and not self.title_and_description_only
        )
        title_editable = editable and not self.description_only
        selected_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )
        self.type_picker.set_enabled(field_editable and not self.lock_type)
        self.title_field.control.set_enabled(
            title_editable
            and not self.lock_title
            and not self.founding_title_locked
            and selected_type != "born"
        )
        self.year_field.control.set_enabled(
            field_editable and not self.lock_date
        )
        self.month_field.control.set_enabled(
            field_editable and not self.lock_date
        )
        self.day_field.control.set_enabled(
            field_editable and not self.lock_date
        )
        self.time_field.control.set_enabled(
            field_editable and not self.lock_date
        )
        self.description_control.text.configure(
            state="normal" if editable else "disabled"
        )
        self.people_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.baby_picker.set_enabled(
            field_editable
            and not self.lock_people
            and not (
                selected_type == "born"
                and self.baby_picker.locked_order
            )
            and not (
                selected_type == "born"
                and self.event.get("automatic_source") == "birth_event"
            )
        )
        self.birthing_parent_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.non_birthing_parent_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.perpetrators_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.victims_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.witnesses_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.affected_picker.set_enabled(
            field_editable and not self.lock_people
        )
        self.murder_additional_people_button.set_enabled(
            field_editable and not self.lock_people
        )
        if hasattr(self, "eminence_picker"):
            self.eminence_picker.set_enabled(field_editable)

        self.locations_picker.set_enabled(field_editable)
        if hasattr(self, "organizations_picker"):
            self.organizations_picker.set_enabled(
                field_editable
                and not bool(self.event.get("organization_event"))
            )
        if hasattr(self, "job_event_picker"):
            self.job_event_picker.set_enabled(field_editable)

            for salary_entry in self.job_salary_entries:
                salary_entry.set_enabled(field_editable)

            for end_date_entry in getattr(
                self,
                "job_end_date_entries",
                (),
            ):
                end_date_entry.set_enabled(field_editable)

        if hasattr(self, "link_items_button"):
            self.link_items_button.set_enabled(editable)
        self.save_button.set_enabled(editable)
        self.cancel_button.set_enabled(True)

    def people_selection_changed(self):
        self.murder_people_selection_changed()

    def birth_people_selection_changed(self):
        baby_ids = self.baby_picker.get_values()
        self.birthing_parent_picker.set_excluded_ids(baby_ids)
        self.non_birthing_parent_picker.set_excluded_ids(baby_ids)
        self.murder_people_selection_changed()

    def murder_people_selection_changed(self):
        self.update_murder_additional_people_summary()
        selected_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )

        if hasattr(self, "eminence_picker"):
            if selected_type == "murder":
                eminence_candidate_ids = list(
                    dict.fromkeys(
                        [
                            *self.perpetrators_picker.get_values(),
                            *self.witnesses_picker.get_values(),
                            *self.affected_picker.get_values(),
                        ]
                    )
                )
            elif selected_type in ("born", "died"):
                eminence_candidate_ids = []
            else:
                eminence_candidate_ids = list(
                    dict.fromkeys(
                        [
                            *self.people_picker.get_values(),
                            *self.witnesses_picker.get_values(),
                            *self.affected_picker.get_values(),
                        ]
                    )
                )

            self.eminence_picker.update_people(
                eminence_candidate_ids
            )

        self.form.after_idle(self.form_resized)

    def update_murder_additional_people_summary(self):
        if not hasattr(self, "murder_witnesses_summary_value"):
            return

        people_provider = getattr(
            self.controller,
            "people_options",
            None,
        )
        people_options = (
            list(people_provider())
            if callable(people_provider)
            else []
        )
        labels_by_id = {
            str(option.get("value", "") or "").strip(): str(
                option.get("label", "") or ""
            ).strip()
            for option in people_options
            if str(option.get("value", "") or "").strip()
        }
        witness_names = [
            labels_by_id.get(person_id, person_id)
            for person_id in self.witnesses_picker.get_values()
        ]
        affected_names = [
            labels_by_id.get(person_id, person_id)
            for person_id in self.affected_picker.get_values()
        ]
        witness_text = ", ".join(witness_names) or "None"
        affected_text = ", ".join(affected_names) or "None"

        self.murder_witnesses_summary_value.set(
            f"Witnessed: {witness_text}"
        )
        self.murder_affected_summary_value.set(
            f"Affected by: {affected_text}"
        )

    def open_murder_additional_people_dialog(self):
        if not self.controls_enabled or self.lock_people:
            return False

        MurderAdditionalPeopleDialog(
            self,
            self.controller,
            self.witnesses_picker.get_values(),
            self.affected_picker.get_values(),
            self.murder_additional_people_chosen,
        )
        return True

    def murder_additional_people_chosen(
        self,
        witness_person_ids,
        affected_person_ids,
    ):
        self.witnesses_picker.set_values(witness_person_ids)
        self.affected_picker.set_values(affected_person_ids)
        self.murder_people_selection_changed()
        return True

    def update_items_summary(self):
        if not hasattr(self, "items_summary_value"):
            return

        linked_item_count = len(self.selected_item_ids)

        if linked_item_count == 0:
            self.items_summary_value.set("Items: None")
        elif linked_item_count == 1:
            item_id = self.selected_item_ids[0]
            link_type = getattr(
                self,
                "selected_item_link_types",
                {},
            ).get(item_id, "")
            self.items_summary_value.set(
                "Items: 1 linked · "
                + item_event_link_type_label(
                    link_type,
                    getattr(
                        self,
                        "selected_item_new_owners",
                        {},
                    ).get(item_id),
                )
            )
        else:
            self.items_summary_value.set(
                f"Items: {linked_item_count} linked"
            )

    def item_link_person_ids(self):
        return list(
            dict.fromkeys(
                str(person_id or "").strip()
                for person_id in (
                    *self.people_picker.get_values(),
                    *self.baby_picker.get_values(),
                    *self.birthing_parent_picker.get_values(),
                    *self.non_birthing_parent_picker.get_values(),
                    *self.perpetrators_picker.get_values(),
                    *self.victims_picker.get_values(),
                    *self.witnesses_picker.get_values(),
                    *self.affected_picker.get_values(),
                )
                if str(person_id or "").strip()
            )
        )

    def open_item_links(self):
        if not self.controls_enabled:
            return False

        item_options_command = getattr(
            self.controller,
            "item_options",
            None,
        )
        item_link_explanation = (
            "Choose each item connected to this event, then select why it "
            "is linked and what the event does to it."
        )

        if self.context == "person":
            possessor_person_ids = self.item_link_person_ids()
            event_date = self.date_value()

            if not possessor_person_ids:
                self.show_error(
                    "Select the people, witnesses, or affected people "
                    "before linking items."
                )
                return False

            if not event_date:
                self.show_error(
                    "Enter the event date before linking items from a "
                    "Mage timeline."
                )
                return False

            try:
                item_options = (
                    list(
                        item_options_command(
                            possessor_person_ids=possessor_person_ids,
                            on_date=event_date,
                        )
                    )
                    if callable(item_options_command)
                    else []
                )
            except (KeyError, TypeError, ValueError) as error:
                self.show_error(str(error))
                return False

            item_link_explanation = (
                "Only items possessed during this event by its people, "
                "witnesses, or affected people are available. Select why "
                "each item is linked and what the event does to it."
            )
        else:
            item_options = (
                list(item_options_command())
                if callable(item_options_command)
                else []
            )

        selected_event_type = str(
            getattr(self, "event", {}).get("event_type", "other")
            if isinstance(getattr(self, "event", {}), dict)
            else "other"
        ).strip()

        if hasattr(self, "event_type_value"):
            selected_event_type = event_type_from_label(
                self.event_type_value.get(),
                selected_event_type or "other",
            )

        RecordLinkDialog(
            self,
            "Link Items to Event",
            "Link items to this event",
            item_link_explanation,
            item_options,
            self.selected_item_ids,
            self.item_links_chosen,
            "Save item links",
            locked_ids=self.locked_item_ids,
            link_type_options=item_event_link_type_options(),
            selected_link_types=getattr(
                self,
                "selected_item_link_types",
                {},
            ),
            link_type_default=normalize_item_event_link_type(
                "",
                selected_event_type,
            ),
            new_owner_options=self.controller.people_options(),
            recent_new_owner_options=(
                self.controller.recent_people_options()
                if hasattr(self.controller, "recent_people_options")
                else ()
            ),
            selected_new_owners=getattr(
                self,
                "selected_item_new_owners",
                {},
            ),
            mage_groups=(
                self.controller.mage_groups()
                if hasattr(self.controller, "mage_groups")
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
        self.selected_item_ids = list(
            dict.fromkeys(
                [
                    *(
                        str(item_id or "").strip()
                        for item_id in item_ids or ()
                        if str(item_id or "").strip()
                    ),
                    *self.locked_item_ids,
                ]
            )
        )
        requested_link_types = dict(
            getattr(self, "selected_item_link_types", {}) or {}
        )

        if isinstance(item_link_types, dict):
            requested_link_types.update(item_link_types)
        event_type = (
            event_type_from_label(
                self.event_type_value.get(),
                "other",
            )
            if hasattr(self, "event_type_value")
            else str(
                getattr(self, "event", {}).get("event_type", "other")
                or "other"
            )
        )
        self.selected_item_link_types = normalize_item_event_link_types(
            requested_link_types,
            self.selected_item_ids,
            event_type,
        )
        requested_new_owners = dict(
            getattr(self, "selected_item_new_owners", {}) or {}
        )

        if isinstance(item_new_owners, dict):
            requested_new_owners.update(item_new_owners)

        self.selected_item_new_owners = normalize_item_event_new_owners(
            requested_new_owners,
            self.selected_item_ids,
            self.selected_item_link_types,
        )
        self.update_items_summary()
        return True

    def location_selection_changed(self):
        if getattr(self, "controls_enabled", False):
            self.association_selection_guard_until = monotonic() + 0.35

        selected_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )

        if selected_type == "founding":
            self.apply_founding_title()
            return

        if selected_type == "extinction":
            self.apply_extinction_title()
            return

        if not self.title_from_location:
            return

        selected_location_ids = self.locations_picker.get_values()

        if not selected_location_ids:
            self.title_value.set("")
            return

        selected_location_id = selected_location_ids[-1]

        for location in self.controller.location_records():
            if (
                str(location.get("record_id", "") or "").strip()
                != selected_location_id
            ):
                continue

            self.title_value.set(
                str(location.get("name", "") or "").strip()
            )
            return

    def update_location_selection_for_type_change(
        self,
        selected_type,
        previous_type,
    ):
        if (
            selected_type == "relocated"
            and previous_type
            and previous_type != "relocated"
        ):
            self.locations_picker.set_values(())
            return True

        return False

    def organization_selection_changed(self):
        if (
            event_type_from_label(
                self.event_type_value.get(),
                "other",
            )
            == "organization_founding"
        ):
            self.apply_organization_founding_title()

    def clear_character_control_link(self):
        self.character_control_link_id = ""
        self.character_control_link_collection = ""
        if hasattr(self, "character_control_link_name"):
            self.character_control_link_name.set("No linked record")

    def update_character_control_link_panel(self, selected_type=None):
        if not hasattr(self, "character_control_link_panel"):
            return
        selected_type = selected_type or event_type_from_label(
            self.event_type_value.get(), "other"
        )
        supported = selected_type in {
            "taught_spell", "taught_proficiency", "taught_recipe",
            "tamed_creature", "bonded_creature", "irked_creature",
        }
        if supported:
            self.character_control_link_panel.grid(
                row=1, column=0, columnspan=2, sticky="ew", pady=(4, 0)
            )
        else:
            self.character_control_link_panel.grid_remove()

    def open_character_control_link(self):
        selected_type = event_type_from_label(
            self.event_type_value.get(), "other"
        )
        options_command = getattr(
            self.controller, "character_control_link_options", None
        )
        options = options_command(selected_type) if callable(options_command) else []
        if not options:
            self.show_error(
                "No matching records are available. Create the record first, then return to this event."
            )
            return False
        self._character_control_link_options = {
            option["value"]: option for option in options
        }
        RecordLinkDialog(
            self,
            "Choose Linked Record",
            "Choose the one record linked to this event",
            "Search by name or details. Core data is linked by stable record ID.",
            options,
            [self.character_control_link_id] if self.character_control_link_id else [],
            self.character_control_link_chosen,
            "Choose record",
            group_label="Type",
            result_limit=200,
        )
        return True

    def character_control_link_chosen(self, selected_ids, *_unused):
        selected_id = str((selected_ids or [""])[0] or "")
        option = getattr(self, "_character_control_link_options", {}).get(
            selected_id
        )
        if not option:
            self.clear_character_control_link()
            return
        self.character_control_link_id = selected_id
        self.character_control_link_collection = str(
            option.get("collection", "") or ""
        )
        self.character_control_link_name.set(str(option.get("label", "Linked record")))

    def event_type_changed(self, *arguments):
        self.update_job_event_panel()
        selected_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )
        self.update_character_control_link_panel(selected_type)
        previous_type = str(
            getattr(self, "previous_event_type", "") or ""
        ).strip()
        current_title = self.title_value.get().strip()
        previous_default_title = EVENT_TYPE_DEFAULT_TITLES.get(
            previous_type,
            "",
        )
        generated_titles = {
            str(
                getattr(self, attribute_name, "") or ""
            ).strip()
            for attribute_name in (
                "generated_event_type_title",
                "generated_founding_title",
                "generated_extinction_title",
                "generated_job_event_title",
            )
            if str(
                getattr(self, attribute_name, "") or ""
            ).strip()
        }
        title_uses_previous_default = (
            current_title in ("", "New event")
            or current_title in generated_titles
            or (
                bool(previous_default_title)
                and current_title == previous_default_title
            )
        )
        next_default_title = EVENT_TYPE_DEFAULT_TITLES.get(
            selected_type,
            "",
        )

        if title_uses_previous_default:
            self.title_value.set(next_default_title)
            self.generated_event_type_title = next_default_title
        else:
            self.generated_event_type_title = ""

        self.previous_event_type = selected_type
        self.update_location_selection_for_type_change(
            selected_type,
            previous_type,
        )

        self.people_picker.single_selection = selected_type in (
            "died",
            "returns_as_ghost",
        )
        self.locations_picker.single_selection = (
            selected_type
            in (
                "relocated",
                "founding",
                "extinction",
                "born",
                "died",
                "murder",
            )
        )
        self.locations_picker.foundation_only = (
            selected_type == "founding"
        )
        if hasattr(self.locations_picker, "heading_value"):
            self.locations_picker.heading_value.set(
                "Birth location"
                if selected_type == "born"
                else "Locations"
            )

        if hasattr(self.locations_picker, "select_button"):
            self.locations_picker.select_button.set_text(
                "Select birth location"
                if selected_type == "born"
                else "Select another location"
            )
        if hasattr(self.locations_picker, "set_instruction"):
            self.locations_picker.set_instruction(
                "(only pick the destination location)."
                if selected_type == "relocated"
                else (
                    "(optional; select no more than one location)."
                    if selected_type in ("died", "murder")
                    else (
                        "(editable; select no more than one birth location)."
                        if selected_type == "born"
                        else ""
                    )
                )
            )

        if selected_type == "murder":
            if (
                not self.perpetrators_picker.get_values()
                and not self.victims_picker.get_values()
                and not self.witnesses_picker.get_values()
                and not self.affected_picker.get_values()
            ):
                self.perpetrators_picker.set_values(
                    self.people_picker.get_values(),
                    (),
                )

        elif selected_type in (
            "died",
            "returns_as_ghost",
            "romance",
            "breakup",
            "travel",
            "item_event",
        ):
            pass
        elif (
            self.baby_picker.get_values()
            or self.birthing_parent_picker.get_values()
            or self.non_birthing_parent_picker.get_values()
            or
            self.perpetrators_picker.get_values()
            or self.victims_picker.get_values()
            or self.witnesses_picker.get_values()
            or self.affected_picker.get_values()
        ):
            role_person_ids = list(
                dict.fromkeys(
                    [
                        *self.people_picker.get_values(),
                        *self.baby_picker.get_values(),
                        *self.birthing_parent_picker.get_values(),
                        *self.non_birthing_parent_picker.get_values(),
                        *self.perpetrators_picker.get_values(),
                        *self.victims_picker.get_values(),
                    ]
                )
            )
            role_locked_ids = list(
                dict.fromkeys(
                    [
                        *self.people_picker.locked_order,
                        *self.baby_picker.locked_order,
                        *self.birthing_parent_picker.locked_order,
                        *self.non_birthing_parent_picker.locked_order,
                        *self.perpetrators_picker.locked_order,
                        *self.victims_picker.locked_order,
                    ]
                )
            )
            self.people_picker.set_values(
                role_person_ids,
                role_locked_ids,
            )

        if selected_type in ("born", "died") and hasattr(
            self,
            "eminence_picker",
        ):
            self.eminence_picker.set_values((), (), {}, "")

        self.murder_people_selection_changed()

        if hasattr(self.locations_picker, "refresh_options"):
            self.locations_picker.refresh_options()
        self.update_association_layout()

        if selected_type == "founding":
            self.apply_founding_title()
            return

        if selected_type == "organization_founding":
            self.apply_organization_founding_title()
            return

        if selected_type == "extinction":
            self.apply_extinction_title()
            return

        if (
            self.generated_founding_title
            and self.title_value.get()
            == self.generated_founding_title
        ):
            self.title_value.set("")

        self.generated_founding_title = ""
        self.founding_title_locked = False

        if (
            self.generated_extinction_title
            and self.title_value.get()
            == self.generated_extinction_title
        ):
            self.title_value.set("")

        self.generated_extinction_title = ""

        if hasattr(self, "title_field"):
            self.title_field.control.set_enabled(
                self.controls_enabled
                and not self.lock_title
            )

    def apply_founding_title(self):
        location_ids = list(self.locations_picker.locked_order)

        if not location_ids:
            location_ids = self.locations_picker.get_values()

        selected_location_id = (
            str(location_ids[0] or "").strip()
            if location_ids
            else ""
        )
        selected_location = next(
            (
                location
                for location in self.controller.location_records()
                if str(location.get("record_id", "") or "").strip()
                == selected_location_id
            ),
            None,
        )
        location_name = str(
            (selected_location or {}).get("name", "") or ""
        ).strip()
        generated_title = (
            f"Founding of {location_name}"
            if location_name
            else ""
        )
        previous_generated_title = self.generated_founding_title

        if (
            not generated_title
            and previous_generated_title
            and self.title_value.get() == previous_generated_title
        ):
            self.title_value.set("")

        self.founding_title_locked = bool(generated_title)
        self.generated_founding_title = generated_title

        if generated_title:
            self.title_value.set(generated_title)

        if hasattr(self, "title_field"):
            self.title_field.control.set_enabled(
                self.controls_enabled
                and not self.lock_title
                and not self.founding_title_locked
            )

    def apply_organization_founding_title(self):
        if not hasattr(self, "organizations_picker"):
            return

        organization_ids = (
            self.organizations_picker.get_values()
            if hasattr(self, "organizations_picker")
            else []
        )
        selected_id = organization_ids[0] if organization_ids else ""
        selected_organization = next(
            (
                organization
                for organization in self.controller.organization_records()
                if str(
                    organization.get("record_id", "") or ""
                ).strip()
                == selected_id
            ),
            None,
        )
        organization_name = str(
            (selected_organization or {}).get("name", "") or ""
        ).strip()
        generated_title = (
            f"Founding of {organization_name}"
            if organization_name
            else ""
        )
        previous_generated_title = self.generated_founding_title

        if (
            not generated_title
            and previous_generated_title
            and self.title_value.get() == previous_generated_title
        ):
            self.title_value.set("")

        self.generated_founding_title = generated_title
        self.founding_title_locked = bool(generated_title)

        if generated_title:
            self.title_value.set(generated_title)

        self.title_field.control.set_enabled(
            self.controls_enabled
            and not self.lock_title
            and not self.founding_title_locked
        )

    def apply_extinction_title(self):
        location_ids = list(self.locations_picker.locked_order)

        if not location_ids:
            location_ids = self.locations_picker.get_values()

        selected_location_id = (
            str(location_ids[0] or "").strip()
            if location_ids
            else ""
        )
        selected_location = next(
            (
                location
                for location in self.controller.location_records()
                if str(location.get("record_id", "") or "").strip()
                == selected_location_id
            ),
            None,
        )
        location_name = str(
            (selected_location or {}).get("name", "") or ""
        ).strip()
        generated_title = (
            f"Extinction of {location_name}"
            if location_name
            else ""
        )
        current_title = self.title_value.get().strip()

        if (
            generated_title
            and (
                not current_title
                or current_title == self.generated_extinction_title
                or current_title == "New event"
            )
        ):
            self.title_value.set(generated_title)

        self.generated_extinction_title = generated_title

    def update_period_display(self, *arguments):
        if getattr(self, "adjusting_year", False):
            return

        year = self.year_value.get().strip()

        if not year:
            self.period_value.set("Period: determined by year")
            return

        period_names = self.controller.period_names_for_date(year)

        if not period_names:
            try:
                numeric_year = int(year)
            except ValueError:
                numeric_year = None

            clamp_command = getattr(
                self.controller,
                "clamp_year_to_defined_periods",
                None,
            )

            if numeric_year is not None and callable(clamp_command):
                clamped_year = clamp_command(numeric_year)

                if clamped_year != numeric_year:
                    self.adjusting_year = True
                    self.year_value.set(str(clamped_year))
                    self.adjusting_year = False
                    year = str(clamped_year)
                    period_names = (
                        self.controller.period_names_for_date(year)
                    )

        self.period_value.set(
            "Period: "
            + (
                ", ".join(period_names)
                if period_names
                else "outside the defined periods"
            )
        )

    def set_comparison_events(self, events):
        self.comparison_events = [
            {
                "record_id": str(
                    event.get("record_id", "") or ""
                ).strip(),
                "event_id": str(
                    event.get("event_id", "") or ""
                ).strip(),
                "date": str(event.get("date", "") or "").strip(),
            }
            for event in events or ()
            if isinstance(event, dict)
        ]
        self.comparison_events_set = True

        if hasattr(self, "time_field"):
            self.update_time_visibility()

    def time_is_needed(self):
        time_variable = getattr(self, "time_value", None)
        time_text = (
            str(time_variable.get() or "").strip()
            if time_variable is not None
            else ""
        )

        if time_text:
            return True

        try:
            selected_date = normalize_world_event_date(
                self.date_value()
            )
        except ValueError:
            return False

        comparison_events = list(
            getattr(self, "comparison_events", []) or []
        )

        if not getattr(self, "comparison_events_set", False):
            list_events = getattr(
                getattr(self, "controller", None),
                "list_events",
                None,
            )

            if callable(list_events):
                comparison_events = list_events()

        current_event = getattr(self, "event", {})
        current_ids = {
            str(current_event.get(field_name, "") or "").strip()
            for field_name in ("record_id", "event_id")
            if str(current_event.get(field_name, "") or "").strip()
        }

        for event in comparison_events:
            event_ids = {
                str(event.get(field_name, "") or "").strip()
                for field_name in ("record_id", "event_id")
                if str(event.get(field_name, "") or "").strip()
            }

            if current_ids.intersection(event_ids):
                continue

            if str(event.get("date", "") or "").strip() == selected_date:
                return True

        return False

    def update_time_visibility(self, *arguments):
        time_field = getattr(self, "time_field", None)

        if time_field is None:
            return False

        if self.time_is_needed():
            date_panel = getattr(self, "date_panel", None)

            if date_panel is not None:
                date_panel.grid_columnconfigure(3, weight=1)

            time_field.grid()
            return True

        time_field.grid_remove()
        date_panel = getattr(self, "date_panel", None)

        if date_panel is not None:
            date_panel.grid_columnconfigure(3, weight=0)

        return False

    def clamp_year_to_editor_bounds(self, event=None):
        if (
            self.minimum_year is None
            or self.maximum_year is None
        ):
            return False

        try:
            event_year = int(self.year_value.get().strip())
        except ValueError:
            return False

        clamped_year = min(
            self.maximum_year,
            max(self.minimum_year, event_year),
        )

        if clamped_year == event_year:
            return False

        self.adjusting_year = True
        self.year_value.set(str(clamped_year))
        self.adjusting_year = False
        self.update_period_display()
        return True

    def date_value(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()
        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            date_value += f"-{day}"

        return date_value

    def job_end_date_value(self):
        if not hasattr(self, "job_end_year_value"):
            return str(
                getattr(self, "event", {}).get("job_end_date", "") or ""
            ).strip()

        year = self.job_end_year_value.get().strip()
        month = self.job_end_month_value.get().strip()
        day = self.job_end_day_value.get().strip()
        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            date_value += f"-{day}"

        return date_value

    def values(self):
        selected_locations = self.locations_picker.get_values()
        locked_locations = list(self.locations_picker.locked_order)
        event_type = event_type_from_label(
            self.event_type_value.get(),
            "other",
        )
        baby_person_ids = (
            self.baby_picker.get_values()
            if event_type == "born"
            else []
        )
        birthing_parent_person_ids = (
            self.birthing_parent_picker.get_values()
            if event_type == "born"
            else []
        )
        non_birthing_parent_person_ids = (
            self.non_birthing_parent_picker.get_values()
            if event_type == "born"
            else []
        )
        perpetrator_person_ids = (
            self.perpetrators_picker.get_values()
            if event_type == "murder"
            else []
        )
        victim_person_ids = (
            self.victims_picker.get_values()
            if event_type == "murder"
            else []
        )
        witness_person_ids = self.witnesses_picker.get_values()
        affected_person_ids = self.affected_picker.get_values()
        selected_person_ids = (
            list(
                dict.fromkeys(
                    [
                        *baby_person_ids,
                        *birthing_parent_person_ids,
                        *non_birthing_parent_person_ids,
                    ]
                )
            )
            if event_type == "born"
            else (
                list(
                    dict.fromkeys(
                        [
                        *perpetrator_person_ids,
                        *victim_person_ids,
                        *witness_person_ids,
                        *affected_person_ids,
                        ]
                    )
                )
                if event_type == "murder"
                else self.people_picker.get_values()
            )
        )
        selected_location_ids = list(
            dict.fromkeys(selected_locations + locked_locations)
        )

        no_eminence_event = event_type in ("born", "died")
        job_option = self.selected_job_event_option()
        organization_ids = (
            self.organizations_picker.get_values()
            if hasattr(self, "organizations_picker")
            else []
        )
        selected_organization_id = (
            organization_ids[0] if organization_ids else ""
        )
        organization_records_command = getattr(
            self.controller,
            "organization_records",
            None,
        )
        organization_records = (
            organization_records_command()
            if selected_organization_id
            and callable(organization_records_command)
            else []
        )
        selected_organization = next(
            (
                organization
                for organization in organization_records
                if str(
                    organization.get("record_id", "") or ""
                ).strip()
                == selected_organization_id
            ),
            None,
        )
        return {
            "event_type": event_type,
            "title": self.title_value.get(),
            "date": self.date_value(),
            "time": self.time_value.get().strip(),
            "description": self.description_control.text.get(
                "1.0",
                "end-1c",
            ),
            "person_ids": selected_person_ids,
            "baby_person_ids": baby_person_ids,
            "birthing_parent_person_ids": birthing_parent_person_ids,
            "non_birthing_parent_person_ids": (
                non_birthing_parent_person_ids
            ),
            "perpetrator_person_ids": perpetrator_person_ids,
            "victim_person_ids": victim_person_ids,
            "witness_person_ids": witness_person_ids,
            "affected_person_ids": affected_person_ids,
            "eminence_person_ids": (
                []
                if no_eminence_event
                else (
                    self.eminence_picker.get_values()
                    if hasattr(self, "eminence_picker")
                    else self.event.get("eminence_person_ids", [])
                )
            ),
            "eminence_skills": (
                {}
                if no_eminence_event
                else (
                    self.eminence_picker.get_skill_values()
                    if hasattr(self, "eminence_picker")
                    else self.event.get("eminence_skills", {})
                )
            ),
            "period_names": [],
            "location_ids": (
                []
                if event_type in ("organization_founding", "joined_faction", "left_faction")
                else selected_location_ids
            ),
            "item_ids": list(
                dict.fromkeys(
                    [
                        *getattr(self, "selected_item_ids", []),
                        *getattr(self, "locked_item_ids", []),
                    ]
                )
            ),
            "item_link_types": normalize_item_event_link_types(
                getattr(self, "selected_item_link_types", {}),
                [
                    *getattr(self, "selected_item_ids", []),
                    *getattr(self, "locked_item_ids", []),
                ],
                event_type,
            ),
            "item_new_owners": normalize_item_event_new_owners(
                getattr(self, "selected_item_new_owners", {}),
                [
                    *getattr(self, "selected_item_ids", []),
                    *getattr(self, "locked_item_ids", []),
                ],
                normalize_item_event_link_types(
                    getattr(self, "selected_item_link_types", {}),
                    [
                        *getattr(self, "selected_item_ids", []),
                        *getattr(self, "locked_item_ids", []),
                    ],
                    event_type,
                ),
            ),
            "locked_location_ids": (
                []
                if event_type in ("organization_founding", "joined_faction", "left_faction")
                else locked_locations
            ),
            "organization_id": (
                selected_organization_id
                if event_type in ("organization_founding", "joined_faction", "left_faction")
                else (
                    str(job_option.get("organization_id", "") or "")
                    if job_option is not None
                    else ""
                )
            ),
            "organization_name": (
                str(
                    (selected_organization or {}).get("name", "")
                    or ""
                )
                if event_type in ("organization_founding", "joined_faction", "left_faction")
                else (
                    str(job_option.get("organization_name", "") or "")
                    if job_option is not None
                    else ""
                )
            ),
            "organization_job_id": (
                str(
                    job_option.get("organization_job_id", "")
                    or ""
                )
                if job_option is not None
                else ""
            ),
            "job_title": (
                str(job_option.get("job_title", "") or "")
                if job_option is not None
                else ""
            ),
            "job_assignment_id": str(
                self.event.get("job_assignment_id", "") or ""
            ),
            "job_end_date": str(
                self.job_end_date_value()
                if event_type == "started_job"
                else ""
            ),
            "salary": (
                {
                    "galleons": self.salary_galleons_value.get(),
                    "sickles": self.salary_sickles_value.get(),
                    "knuts": self.salary_knuts_value.get(),
                }
                if event_type in ("started_job", "received_raise")
                else None
            ),
            "knowledge_record_id": (
                self.character_control_link_id
                if event_type in ("taught_spell", "taught_proficiency", "taught_recipe")
                else ""
            ),
            "knowledge_collection": (
                self.character_control_link_collection
                if event_type in ("taught_spell", "taught_proficiency", "taught_recipe")
                else ""
            ),
            "knowledge_name": (
                self.character_control_link_name.get()
                if event_type in ("taught_spell", "taught_proficiency", "taught_recipe")
                and self.character_control_link_id
                else ""
            ),
            "named_creature_id": (
                self.character_control_link_id
                if event_type in ("tamed_creature", "bonded_creature", "irked_creature")
                else ""
            ),
            "named_creature_name": (
                self.character_control_link_name.get()
                if event_type in ("tamed_creature", "bonded_creature", "irked_creature")
                and self.character_control_link_id
                else ""
            ),
        }

    def save(self):
        if self.read_only:
            return False

        self.clamp_year_to_editor_bounds()
        values = self.values()

        if (
            self.storage_kind == "shared"
            and not values["date"]
            and values["event_type"] != "born"
        ):
            self.show_error("Enter the year when this event happened.")
            return False

        missing_item_owner_ids = [
            item_id
            for item_id in values["item_ids"]
            if values["item_link_types"].get(item_id)
            in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            and not values["item_new_owners"].get(
                item_id,
                {},
            ).get("person_id")
        ]

        if missing_item_owner_ids:
            self.show_error(
                "Choose the new owner for every Passed down, Gifted, or "
                "Taken item link."
            )
            return False

        if values["event_type"] in (
            "taught_spell", "taught_proficiency", "taught_recipe",
            "tamed_creature", "bonded_creature", "irked_creature",
        ) and not self.character_control_link_id:
            self.show_error("Choose the record linked to this event.")
            return False

        if self.context == "person" and values["item_ids"]:
            possessor_person_ids = list(
                dict.fromkeys(
                    [
                        *values["person_ids"],
                        *values["witness_person_ids"],
                        *values["affected_person_ids"],
                    ]
                )
            )

            try:
                eligible_item_ids = {
                    option["value"]
                    for option in self.controller.item_options(
                        possessor_person_ids=possessor_person_ids,
                        on_date=values["date"],
                    )
                }
            except (KeyError, TypeError, ValueError) as error:
                self.show_error(str(error))
                return False

            if any(
                item_id not in eligible_item_ids
                for item_id in values["item_ids"]
            ):
                self.show_error(
                    "Every linked item must be possessed during this event "
                    "by one of its people, witnesses, or affected people."
                )
                return False

        if (
            values["event_type"] in ("died", "murder")
            and not values["date"]
        ):
            self.show_error("Enter the year when this death happened.")
            return False

        if values["event_type"] in ("started_job", "received_raise"):
            if not values["organization_job_id"]:
                self.show_error("Choose the organization job.")
                return False

            if len(values["person_ids"]) != 1:
                self.show_error(
                    "A job event must belong to exactly one person."
                )
                return False

        if (
            values["event_type"] == "started_job"
            and hasattr(self, "job_end_year_value")
        ):
            end_year = self.job_end_year_value.get().strip()
            end_month = self.job_end_month_value.get().strip()
            end_day = self.job_end_day_value.get().strip()

            if not end_year and (end_month or end_day):
                self.show_error("Job end month and day require a year.")
                return False

            if end_day and not end_month:
                self.show_error("Job end day requires a month.")
                return False

        if (
            values["event_type"] == "relocated"
            and len(values["location_ids"]) != 1
        ):
            self.show_error(
                "Select exactly one destination location for a relocation."
            )
            return False

        if (
            values["event_type"] == "founding"
            and len(values["location_ids"]) != 1
        ):
            self.show_error(
                "Select exactly one location for a founding event."
            )
            return False

        if (
            values["event_type"] == "extinction"
            and len(values["location_ids"]) != 1
        ):
            self.show_error(
                "Select exactly one location for an extinction event."
            )
            return False

        if (
            values["event_type"] in ("organization_founding", "joined_faction", "left_faction")
            and not values["organization_id"]
        ):
            self.show_error(
                "Select exactly one faction organization."
            )
            return False

        if (
            values["event_type"]
            in ("began_friendship", "romance", "breakup")
            and len(values["person_ids"]) < 2
        ):
            event_label = {
                "began_friendship": "friendship",
                "romance": "romance",
                "breakup": "breakup",
            }[values["event_type"]]
            self.show_error(
                f"A {event_label} event needs at least two people."
            )
            return False

        if values["event_type"] != "murder":
            event_role_ids = [
                *values["person_ids"],
                *values["witness_person_ids"],
                *values["affected_person_ids"],
            ]

            if len(event_role_ids) != len(set(event_role_ids)):
                self.show_error(
                    "Each person can belong to only one event category."
                )
                return False

        if values["event_type"] == "born":
            if len(values["baby_person_ids"]) != 1:
                self.show_error(
                    "A Birth event needs exactly one baby."
                )
                return False

            if len(values["birthing_parent_person_ids"]) > 1:
                self.show_error(
                    "Select no more than one birthing parent."
                )
                return False

            if len(values["non_birthing_parent_person_ids"]) > 1:
                self.show_error(
                    "Select no more than one non-birthing parent."
                )
                return False

            birth_role_ids = [
                *values["baby_person_ids"],
                *values["birthing_parent_person_ids"],
                *values["non_birthing_parent_person_ids"],
            ]

            if len(birth_role_ids) != len(set(birth_role_ids)):
                self.show_error(
                    "The baby and parents must be different people."
                )
                return False

            if len(values["location_ids"]) > 1:
                self.show_error(
                    "A Birth event can use no more than one location."
                )
                return False

        if (
            values["event_type"] == "died"
            and len(values["person_ids"]) != 1
        ):
            self.show_error(
                "A Death event must belong to exactly one person."
            )
            return False

        if (
            values["event_type"] == "returns_as_ghost"
            and len(values["person_ids"]) != 1
        ):
            self.show_error(
                "A Returns as ghost event must belong to exactly one "
                "person."
            )
            return False

        if (
            values["event_type"] in ("died", "murder")
            and len(values["location_ids"]) > 1
        ):
            self.show_error(
                "A Death or Murder event can use no more than one location."
            )
            return False

        if values["event_type"] == "murder":
            if not values["perpetrator_person_ids"]:
                self.show_error(
                    "A Murder event needs at least one perpetrator."
                )
                return False

            if not values["victim_person_ids"]:
                self.show_error(
                    "A Murder event needs at least one victim."
                )
                return False

            if set(values["perpetrator_person_ids"]).intersection(
                values["victim_person_ids"]
            ):
                self.show_error(
                    "The same person cannot be both perpetrator and victim."
                )
                return False

            murder_role_ids = [
                *values["perpetrator_person_ids"],
                *values["victim_person_ids"],
                *values["witness_person_ids"],
                *values["affected_person_ids"],
            ]

            if len(murder_role_ids) != len(set(murder_role_ids)):
                self.show_error(
                    "Each Murder participant can belong to only one category."
                )
                return False

            if set(values["victim_person_ids"]).intersection(
                values["eminence_person_ids"]
            ):
                self.show_error(
                    "Victims cannot earn Eminence from a Murder event."
                )
                return False

        if (
            self.minimum_year is not None
            and self.maximum_year is not None
        ):
            try:
                event_year = int(self.year_value.get().strip())
            except ValueError:
                event_year = None

            if (
                event_year is not None
                and not (
                    self.minimum_year
                    <= event_year
                    <= self.maximum_year
                )
            ):
                self.show_error(
                    f"Enter a year from {self.minimum_year:,} to "
                    f"{self.maximum_year:,} for this period."
                )
                return False

        self.saving = True
        previous_button_text = "Save Event"

        try:
            previous_button_text = str(
                self.save_button.cget("text") or previous_button_text
            )
        except (AttributeError, tk.TclError):
            pass

        self.save_button.set_text("Saving...")
        try:
            self.save_button.configure(state="disabled")
        except (AttributeError, tk.TclError):
            pass
        try:
            self.configure(cursor="wait")
            self.update_idletasks()
        except tk.TclError:
            pass

        try:
            saved = self.save_command(
                values,
                self.storage_kind,
                deepcopy(self.event),
            )
        except (KeyError, TypeError, ValueError) as error:
            self.show_error(str(error))
            return False
        finally:
            self.saving = False
            try:
                self.configure(cursor="")
                self.save_button.configure(state="normal")
                self.save_button.set_text(previous_button_text)
            except (AttributeError, tk.TclError):
                pass

        if saved is False:
            return False

        self.saved_editor_values = deepcopy(self.values())
        self.show_saved()
        return True

    def has_unsaved_changes(self):
        if self.read_only or self.editor_mode == "empty":
            return False

        saved_values = getattr(self, "saved_editor_values", None)

        if saved_values is None:
            return self.is_new_event()

        return self.values() != saved_values

    def association_selection_guard_active(self):
        return monotonic() < float(
            getattr(self, "association_selection_guard_until", 0.0)
            or 0.0
        )

    def cancel(self):
        self.clear_feedback()
        self.editor_mode = "empty"
        self.saved_editor_values = None

        if self.cancel_command is not None:
            self.cancel_command()
        else:
            self.clear()

    def show_error(self, message):
        self.clear_feedback()
        self.feedback_value.set(str(message or "Cannot save this event."))

    def show_saved(self):
        self.clear_feedback()
        self.feedback_value.set("✓ Event saved")
        self.save_button.set_text("✓ Saved")
        self.feedback_after_id = self.after(
            2400,
            self.clear_feedback,
        )

    def clear_feedback(self):
        if self.feedback_after_id is not None:
            try:
                self.after_cancel(self.feedback_after_id)
            except tk.TclError:
                pass

            self.feedback_after_id = None

        self.feedback_value.set("")

        if hasattr(self, "save_button"):
            self.save_button.set_text("Save event")
