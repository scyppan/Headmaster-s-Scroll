import tkinter as tk
from copy import deepcopy
from tkinter import messagebox

from mage_maker.sections.events.dialog import EventPersonPickerDialog
from mage_maker.sections.events.models import split_world_event_date
from mage_maker.sections.items.models import (
    DEFAULT_ITEM_CATEGORY,
    ITEM_PASSAGE_METHODS,
    UNGROUPED_ITEM_GROUP_LABEL,
    UNPOSSESSED_ITEM_HOLDER_LABEL,
)
from mage_maker.ui.theme import (
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    CalendarAdoptionNotice,
    LabeledEntry,
    MultilineField,
    RoundedSelect,
    SoftButton,
)


class ItemCategoryDialog(tk.Toplevel):
    def __init__(self, parent, save_command):
        super().__init__(parent)
        self.save_command = save_command
        self.category_value = tk.StringVar()
        self.title("Add Item Category")
        self.geometry("430x185")
        self.minsize(390, 170)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_columnconfigure(0, weight=1)
        self.build_content()
        self.grab_set()
        self.after_idle(self.focus_category)

    def build_content(self):
        heading = tk.Label(
            self,
            text="Add item category",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(14, "bold"),
            anchor="w",
            padx=18,
            pady=12,
        )
        heading.grid(row=0, column=0, sticky="ew")
        content = tk.Frame(self, bg=SURFACE)
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=16,
        )
        content.grid_columnconfigure(0, weight=1)
        self.category_field = LabeledEntry(
            content,
            "Category name",
            self.category_value,
            background=SURFACE,
        )
        self.category_field.grid(row=0, column=0, sticky="ew")
        controls = tk.Frame(content, bg=SURFACE)
        controls.grid(row=1, column=0, sticky="e", pady=(16, 0))
        cancel_button = SoftButton(
            controls,
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
        add_button = SoftButton(
            controls,
            text="Add category",
            command=self.save_category,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=114,
            height=36,
        )
        add_button.pack(side="left")

    def focus_category(self):
        self.category_field.entry.focus_set()

    def save_category(self):
        try:
            self.save_command(self.category_value.get())
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add category",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()


class ItemGroupDialog(tk.Toplevel):
    def __init__(self, parent, save_command):
        super().__init__(parent)
        self.save_command = save_command
        self.group_value = tk.StringVar()
        self.title("Add Item Group")
        self.geometry("430x185")
        self.minsize(390, 170)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_columnconfigure(0, weight=1)
        self.build_content()
        self.grab_set()
        self.after_idle(self.focus_group)

    def build_content(self):
        heading = tk.Label(
            self,
            text="Add item group",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(14, "bold"),
            anchor="w",
            padx=18,
            pady=12,
        )
        heading.grid(row=0, column=0, sticky="ew")
        content = tk.Frame(self, bg=SURFACE)
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=16,
        )
        content.grid_columnconfigure(0, weight=1)
        self.group_field = LabeledEntry(
            content,
            "Group name",
            self.group_value,
            background=SURFACE,
        )
        self.group_field.grid(row=0, column=0, sticky="ew")
        controls = tk.Frame(content, bg=SURFACE)
        controls.grid(row=1, column=0, sticky="e", pady=(16, 0))
        cancel_button = SoftButton(
            controls,
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
        add_button = SoftButton(
            controls,
            text="Add group",
            command=self.save_group,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        add_button.pack(side="left")

    def focus_group(self):
        self.group_field.entry.focus_set()

    def save_group(self):
        try:
            self.save_command(self.group_value.get())
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot add group",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()


class ItemEditorDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        categories,
        save_command,
        item=None,
        initial_holder=None,
        groups=None,
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.item = deepcopy(item) if isinstance(item, dict) else None
        self.initial_holder = (
            deepcopy(initial_holder)
            if isinstance(initial_holder, dict)
            else {}
        )
        self.crafting_mode = bool(
            self.item is None and self.initial_holder.get("record_id")
        )
        self.categories = list(categories or [DEFAULT_ITEM_CATEGORY])
        self.groups = list(groups or [])
        selected_category = (
            str(self.item.get("category", "") or "").strip()
            if self.item is not None
            else DEFAULT_ITEM_CATEGORY
        )
        selected_group = (
            str(self.item.get("group", "") or "").strip()
            if self.item is not None
            else ""
        )
        self.name_value = tk.StringVar(
            value=(
                str(self.item.get("name", "") or "")
                if self.item is not None
                else ""
            )
        )
        self.category_value = tk.StringVar(
            value=(
                selected_category
                if selected_category in self.categories
                else self.categories[0]
            )
        )
        self.group_value = tk.StringVar(
            value=(
                selected_group
                if selected_group in self.groups
                else UNGROUPED_ITEM_GROUP_LABEL
            )
        )
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        self.method_value = tk.StringVar(value="Crafted")
        self.title(
            "Edit Item"
            if self.item is not None
            else "Craft Item" if self.crafting_mode else "Add Item"
        )
        self.geometry("720x690" if self.item is None else "720x565")
        self.minsize(660, 520)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.build_content()
        self.grab_set()
        self.after_idle(self.focus_name)

    def build_header(self):
        heading = tk.Label(
            self,
            text=(
                "Edit item"
                if self.item is not None
                else "Craft item" if self.crafting_mode else "Add item"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(14, "bold"),
            anchor="w",
            padx=18,
            pady=12,
        )
        heading.grid(row=0, column=0, sticky="ew")

    def build_content(self):
        content = tk.Frame(self, bg=SURFACE)
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=16,
        )
        content.grid_columnconfigure(0, weight=2, uniform="item")
        content.grid_columnconfigure((1, 2), weight=1, uniform="item")
        content.grid_rowconfigure(2, weight=1)
        self.name_field = LabeledEntry(
            content,
            "Item name",
            self.name_value,
            background=SURFACE,
        )
        self.name_field.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 7),
        )
        category_block = tk.Frame(content, bg=SURFACE)
        category_block.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=7,
        )
        category_block.grid_columnconfigure(0, weight=1)
        category_label = tk.Label(
            category_block,
            text="Category",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        category_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        category_select = RoundedSelect(
            category_block,
            self.category_value,
            self.categories,
            background=SURFACE,
            height=40,
        )
        category_select.grid(row=1, column=0, sticky="ew")
        group_block = tk.Frame(content, bg=SURFACE)
        group_block.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=(7, 0),
        )
        group_block.grid_columnconfigure(0, weight=1)
        group_label = tk.Label(
            group_block,
            text="Group",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        group_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        group_select = RoundedSelect(
            group_block,
            self.group_value,
            [UNGROUPED_ITEM_GROUP_LABEL, *self.groups],
            background=SURFACE,
            height=40,
        )
        group_select.grid(row=1, column=0, sticky="ew")
        self.description_field = MultilineField(
            content,
            "Description",
            7,
            background=SURFACE,
            hint_text="What the item is, looks like, and does.",
        )
        self.description_field.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(14, 7),
        )
        self.notes_field = MultilineField(
            content,
            "Notes",
            4,
            background=SURFACE,
            hint_text="Private database notes about this item.",
        )
        self.notes_field.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(7, 0),
        )

        if self.item is not None:
            self.description_field.text.insert(
                "1.0",
                str(self.item.get("description", "") or ""),
            )
            self.notes_field.text.insert(
                "1.0",
                str(self.item.get("notes", "") or ""),
            )
        elif self.initial_holder.get("record_id"):
            self.build_initial_holder(content, 3)

        controls = tk.Frame(content, bg=SURFACE)
        controls.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="e",
            pady=(16, 0),
        )
        cancel_button = SoftButton(
            controls,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=84,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        save_button = SoftButton(
            controls,
            text="Craft item" if self.crafting_mode else "Save item",
            command=self.save_item,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=36,
        )
        save_button.pack(side="left")

    def build_initial_holder(self, parent, row):
        panel = tk.Frame(parent, bg=SURFACE_MUTED, padx=12, pady=10)
        panel.grid(
            row=row,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(14, 0),
        )
        panel.grid_columnconfigure((0, 1, 2), weight=1)
        holder_name = str(
            self.initial_holder.get("displayed_name", "")
            or "Unnamed person"
        ).strip()
        holder_label = tk.Label(
            panel,
            text=f"Crafter and first owner: {holder_name}",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        holder_label.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 8),
        )
        year_field = LabeledEntry(
            panel,
            "Year",
            self.year_value,
            background=SURFACE_MUTED,
        )
        year_field.grid(row=1, column=0, sticky="ew", padx=(0, 6))
        month_field = LabeledEntry(
            panel,
            "Month",
            self.month_value,
            background=SURFACE_MUTED,
        )
        month_field.grid(row=1, column=1, sticky="ew", padx=6)
        day_field = LabeledEntry(
            panel,
            "Day",
            self.day_value,
            background=SURFACE_MUTED,
        )
        day_field.grid(row=1, column=2, sticky="ew", padx=(6, 0))
        calendar_notice = CalendarAdoptionNotice(
            panel,
            background=SURFACE_MUTED,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        )
        calendar_notice.grid(
            row=2,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(6, 0),
        )

    def focus_name(self):
        self.name_field.entry.focus_set()

    def passage_date(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()

        if not year:
            if month or day:
                raise ValueError(
                    "Crafting month or day requires a year."
                )

            raise ValueError("Enter the year when this item was crafted.")

        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            if not month:
                raise ValueError("Crafting day requires a month.")

            date_value += f"-{day}"

        return date_value

    def save_item(self):
        values = {
            "name": self.name_value.get(),
            "category": self.category_value.get(),
            "group": (
                ""
                if self.group_value.get()
                == UNGROUPED_ITEM_GROUP_LABEL
                else self.group_value.get()
            ),
            "description": self.description_field.text.get(
                "1.0",
                "end-1c",
            ),
            "notes": self.notes_field.text.get("1.0", "end-1c"),
        }

        if self.item is not None:
            values["record_id"] = self.item["record_id"]
            values["passage_history"] = deepcopy(
                self.item.get("passage_history", [])
            )
        elif self.initial_holder.get("record_id"):
            try:
                passage_date = self.passage_date()
            except ValueError as error:
                messagebox.showerror(
                    "Cannot save item",
                    str(error),
                    parent=self,
                )
                return

            values["passage_history"] = [
                {
                    "person_id": str(
                        self.initial_holder.get("record_id", "") or ""
                    ).strip(),
                    "person_name": str(
                        self.initial_holder.get("displayed_name", "")
                        or "Unnamed person"
                    ).strip(),
                    "date": passage_date,
                    "method": self.method_value.get(),
                    "note": "",
                }
            ]
        else:
            values["passage_history"] = []

        try:
            self.save_command(values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save item",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()


class ItemPassageDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        people,
        save_command,
        passage=None,
        excluded_person_id="",
        recent_people_options=(),
        mage_groups=(),
    ):
        super().__init__(parent)
        self.save_command = save_command
        self.passage = (
            deepcopy(passage) if isinstance(passage, dict) else None
        )
        selected_passage_person_id = str(
            self.passage.get("person_id", "")
            if self.passage is not None
            else ""
        ).strip()
        excluded_id = str(excluded_person_id or "").strip()
        self.people_options = []
        used_person_ids = set()

        for person in people or ():
            if not isinstance(person, dict):
                continue

            person_record = person.get("person")
            normalized_person = (
                deepcopy(person_record)
                if isinstance(person_record, dict)
                else deepcopy(person)
            )
            person_id = str(
                person.get(
                    "value",
                    normalized_person.get("record_id", ""),
                )
                or ""
            ).strip()
            person_name = str(
                person.get(
                    "label",
                    normalized_person.get("displayed_name", ""),
                )
                or "Unnamed person"
            ).strip()

            if (
                not person_id
                or person_id in used_person_ids
                or (
                    excluded_id
                    and person_id == excluded_id
                    and person_id != selected_passage_person_id
                )
            ):
                continue

            used_person_ids.add(person_id)
            normalized_person["record_id"] = person_id
            normalized_person["displayed_name"] = person_name
            self.people_options.append(
                {
                    "value": person_id,
                    "label": person_name,
                    "person": normalized_person,
                    "group_name": str(
                        person.get("group_name", "") or ""
                    ).strip(),
                }
            )

        self.person_labels_by_id = {
            option["value"]: option["label"]
            for option in self.people_options
        }
        self.recent_people_options = [
            deepcopy(option)
            for option in recent_people_options or ()
            if isinstance(option, dict)
            and str(option.get("value", "") or "").strip()
            in self.person_labels_by_id
        ]
        self.mage_groups = [
            deepcopy(group)
            for group in mage_groups or ()
            if isinstance(group, dict)
        ]
        self.selected_person_id = (
            selected_passage_person_id
            if selected_passage_person_id in self.person_labels_by_id
            else ""
        )
        self.selected_person_name = (
            self.person_labels_by_id.get(
                self.selected_person_id,
                str(
                    self.passage.get("person_name", "")
                    if self.passage is not None
                    else ""
                ).strip(),
            )
            if self.selected_person_id
            else ""
        )
        self.person_value = tk.StringVar(
            value=(
                self.selected_person_name
                if self.selected_person_id
                else UNPOSSESSED_ITEM_HOLDER_LABEL
            )
        )
        self.method_value = tk.StringVar(
            value=(
                str(self.passage.get("method", "") or "First recorded")
                if self.passage is not None
                else "Destroyed"
            )
        )
        self.automatic_method_value = (
            "" if self.passage is not None else "Destroyed"
        )
        self.year_value = tk.StringVar()
        self.month_value = tk.StringVar()
        self.day_value = tk.StringVar()
        self.title(
            "Edit Item Passage"
            if self.passage is not None
            else "Pass Item"
        )
        self.geometry("640x500")
        self.minsize(580, 460)
        self.configure(bg=SURFACE)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.close_dialog)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.load_date()
        self.build_content()
        self.grab_set()

    def person_sort_key(self, person):
        return str(
            person.get("displayed_name", "") or ""
        ).casefold()

    def person_label(self, person):
        return str(
            person.get("displayed_name", "") or "Unnamed person"
        ).strip()

    def load_date(self):
        if self.passage is None:
            return

        date_value = str(self.passage.get("date", "") or "").strip()

        if not date_value:
            return

        year, month, day = split_world_event_date(date_value)
        self.year_value.set(year)
        self.month_value.set(month)
        self.day_value.set(day)

    def build_content(self):
        heading = tk.Label(
            self,
            text=(
                "Edit passage"
                if self.passage is not None
                else "Record item passage"
            ),
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(14, "bold"),
            anchor="w",
            padx=18,
            pady=12,
        )
        heading.grid(row=0, column=0, sticky="ew")
        content = tk.Frame(self, bg=SURFACE)
        content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=18,
            pady=16,
        )
        content.grid_columnconfigure((0, 1, 2), weight=1)
        holder_block = tk.Frame(content, bg=SURFACE)
        holder_block.grid(
            row=0,
            column=0,
            columnspan=2,
            rowspan=2,
            sticky="nsew",
            padx=(0, 7),
        )
        holder_block.grid_columnconfigure(0, weight=1)
        holder_label = tk.Label(
            holder_block,
            text="New holder or status",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        holder_label.grid(
            row=0,
            column=0,
            columnspan=3,
            sticky="ew",
            pady=(0, 5),
        )
        self.holder_display = tk.Label(
            holder_block,
            textvariable=self.person_value,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
            padx=10,
            pady=10,
        )
        self.holder_display.grid(
            row=1,
            column=0,
            sticky="ew",
        )
        choose_holder_button = SoftButton(
            holder_block,
            text="Choose person",
            command=self.open_person_picker,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=112,
            height=40,
            font=app_font(9, "bold"),
        )
        choose_holder_button.grid(
            row=1,
            column=1,
            sticky="e",
            padx=(7, 0),
        )
        unpossessed_button = SoftButton(
            holder_block,
            text="Unpossessed",
            command=self.set_unpossessed,
            background=SURFACE,
            width=102,
            height=40,
            font=app_font(9, "bold"),
        )
        unpossessed_button.grid(
            row=1,
            column=2,
            sticky="e",
            padx=(6, 0),
        )
        method_block = tk.Frame(content, bg=SURFACE)
        method_block.grid(
            row=0,
            column=2,
            rowspan=2,
            sticky="nsew",
            padx=(7, 0),
        )
        method_block.grid_columnconfigure(0, weight=1)
        method_label = tk.Label(
            method_block,
            text="How it passed",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        method_label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        method_select = RoundedSelect(
            method_block,
            self.method_value,
            ITEM_PASSAGE_METHODS,
            background=SURFACE,
            height=40,
        )
        method_select.grid(row=1, column=0, sticky="ew")
        year_field = LabeledEntry(
            content,
            "Year",
            self.year_value,
            background=SURFACE,
        )
        year_field.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(14, 0))
        month_field = LabeledEntry(
            content,
            "Month",
            self.month_value,
            background=SURFACE,
        )
        month_field.grid(row=2, column=1, sticky="ew", padx=6, pady=(14, 0))
        day_field = LabeledEntry(
            content,
            "Day",
            self.day_value,
            background=SURFACE,
        )
        day_field.grid(row=2, column=2, sticky="ew", padx=(6, 0), pady=(14, 0))
        calendar_notice = CalendarAdoptionNotice(
            content,
            background=SURFACE,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        )
        calendar_notice.grid(
            row=3,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(6, 0),
        )
        self.note_field = MultilineField(
            content,
            "Passage note",
            6,
            background=SURFACE,
            hint_text="Why or how the item changed hands.",
        )
        self.note_field.grid(
            row=4,
            column=0,
            columnspan=3,
            sticky="nsew",
            pady=(14, 0),
        )

        if self.passage is not None:
            self.note_field.text.insert(
                "1.0",
                str(self.passage.get("note", "") or ""),
            )

        controls = tk.Frame(content, bg=SURFACE)
        controls.grid(
            row=5,
            column=0,
            columnspan=3,
            sticky="e",
            pady=(16, 0),
        )
        cancel_button = SoftButton(
            controls,
            text="Cancel",
            command=self.close_dialog,
            background=SURFACE,
            width=84,
            height=36,
        )
        cancel_button.pack(side="left", padx=(0, 7))
        save_button = SoftButton(
            controls,
            text="Save passage",
            command=self.save_passage,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=116,
            height=36,
        )
        save_button.pack(side="left")

    def passage_date(self):
        year = self.year_value.get().strip()
        month = self.month_value.get().strip()
        day = self.day_value.get().strip()

        if not year:
            if month or day:
                raise ValueError("Passage month or day requires a year.")

            return ""

        date_value = year

        if month:
            date_value += f"-{month}"

        if day:
            if not month:
                raise ValueError("Passage day requires a month.")

            date_value += f"-{day}"

        return date_value

    def open_person_picker(self):
        recent_people_options = list(self.recent_people_options)
        selected_person_option = next(
            (
                option
                for option in self.people_options
                if option["value"] == self.selected_person_id
            ),
            None,
        )

        if selected_person_option is not None:
            recent_people_options = [
                selected_person_option,
                *(
                    option
                    for option in recent_people_options
                    if option["value"] != self.selected_person_id
                ),
            ]

        EventPersonPickerDialog(
            self,
            self.people_options,
            recent_people_options,
            self.selected_person_id,
            self.person_selected,
            mage_groups=self.mage_groups,
            dialog_title="Choose Item Holder",
            heading_text="Choose the item holder",
            explanation_text=(
                "Search all people and choose who holds the item after "
                "this ownership change."
            ),
            selection_prompt="Select the new holder.",
            action_text="Use person",
        )
        return True

    def person_selected(self, person_id):
        normalized_person_id = str(person_id or "").strip()

        if normalized_person_id not in self.person_labels_by_id:
            return False

        self.selected_person_id = normalized_person_id
        self.selected_person_name = self.person_labels_by_id[
            normalized_person_id
        ]
        self.person_value.set(self.selected_person_name)

        if self.method_value.get() == self.automatic_method_value:
            self.method_value.set("Passed down")
            self.automatic_method_value = "Passed down"

        return True

    def set_unpossessed(self):
        self.selected_person_id = ""
        self.selected_person_name = ""
        self.person_value.set(UNPOSSESSED_ITEM_HOLDER_LABEL)

        if self.method_value.get() == self.automatic_method_value:
            self.method_value.set("Destroyed")
            self.automatic_method_value = "Destroyed"

        return True

    def save_passage(self):
        person_id = str(self.selected_person_id or "").strip()

        if person_id and person_id not in self.person_labels_by_id:
            messagebox.showerror(
                "Cannot save passage",
                "Choose a holder or Unpossessed.",
                parent=self,
            )
            return

        try:
            passage_date = self.passage_date()
            values = {
                "person_id": person_id,
                "person_name": (
                    self.person_labels_by_id.get(person_id, "")
                    if person_id
                    else ""
                ),
                "date": passage_date,
                "method": self.method_value.get(),
                "note": self.note_field.text.get("1.0", "end-1c"),
            }
            self.save_command(values)
        except (KeyError, TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save passage",
                str(error),
                parent=self,
            )
            return

        self.close_dialog()

    def close_dialog(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass

        self.destroy()
