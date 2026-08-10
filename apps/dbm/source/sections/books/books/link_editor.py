import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.magic.proficiencies.association_editor import AssociationPicker
from shared.widgets import SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)


class BookLinkEditor(tk.Frame):
    def __init__(
        self,
        parent,
        database,
        collection_name,
        title_text,
        picker_title,
        change_command,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.database = database
        self.collection_name = collection_name
        self.picker_title = picker_title
        self.change_command = change_command
        self.references = []

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, sticky="ew", pady=(0, 9))
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title = tk.Label(
            self.header,
            text=title_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(12),
            anchor="w",
        )
        self.title.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.add_button = SoftButton(
            self.header,
            text="Search & Add",
            command=self.add_reference,
            width=116,
            height=34,
            font=app_font(9),
        )
        self.add_button.grid(row=0, column=1, padx=(8, 3))

        self.remove_button = SoftButton(
            self.header,
            text="Remove",
            command=self.remove_reference,
            width=82,
            height=34,
            font=app_font(9),
        )
        self.remove_button.grid(row=0, column=2, padx=3)

        self.up_button = SoftButton(
            self.header,
            text="Move Up",
            command=self.move_reference_up,
            width=92,
            height=34,
            font=app_font(9),
        )
        self.up_button.grid(row=0, column=3, padx=3)

        self.down_button = SoftButton(
            self.header,
            text="Move Down",
            command=self.move_reference_down,
            width=104,
            height=34,
            font=app_font(9),
        )
        self.down_button.grid(row=0, column=4, padx=(3, 0))

        self.list_frame = tk.Frame(self, bg=SURFACE)
        self.list_frame.grid(row=1, column=0, sticky="nsew")
        self.list_frame.grid_rowconfigure(0, weight=1)
        self.list_frame.grid_columnconfigure(0, weight=1)
        bind_theme(self.list_frame, background="SURFACE")

        self.listbox = StripedListbox(
            self.list_frame,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(10),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(row=0, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.update_button_states)

        self.scrollbar = tk.Scrollbar(
            self.list_frame,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        self.listbox.configure(yscrollcommand=self.scrollbar.set)
        self.update_button_states()

    def set_references(self, references):
        self.references = (
            deepcopy(references) if isinstance(references, list) else []
        )
        self.refresh_list()

    def get_references(self):
        return deepcopy(self.references)

    def get_records(self):
        return self.database.get_collection(self.collection_name)

    def get_records_by_id(self):
        return {
            record.get("record_id"): record for record in self.get_records()
        }

    def build_record_label(self, record):
        name = str(record.get("name", "")).strip() or "Unnamed record"

        if self.collection_name == "spells":
            incantation = str(record.get("incantation", "")).strip()
            identity = f"{name} ({incantation})" if incantation else name
            skill = str(record.get("skill", "")).strip()
            threshold = record.get("threshold")
            detail = " ".join(
                value
                for value in (
                    skill,
                    f"Threshold {threshold}"
                    if threshold not in (None, "")
                    else "",
                )
                if value
            )
        elif self.collection_name == "proficiencies":
            identity = name
            skill = str(record.get("skill", "")).strip()
            threshold = record.get("threshold")
            tradition = str(record.get("tradition", "")).strip()
            detail = " ".join(
                value
                for value in (
                    skill,
                    f"Threshold {threshold}"
                    if threshold not in (None, "")
                    else "",
                    f"({tradition})" if tradition else "",
                )
                if value
            )
        else:
            identity = name
            threshold = record.get("threshold")
            detail = (
                f"Threshold {threshold}"
                if threshold not in (None, "")
                else ""
            )

        return f"{identity} — {detail}" if detail else identity

    def get_picker_entries(self):
        entries = []

        for record in self.get_records():
            record_id = str(record.get("record_id", "")).strip()

            if not record_id:
                continue

            entries.append(
                {
                    "label": self.build_record_label(record),
                    "record_id": record_id,
                    "name": str(record.get("name", "")).strip(),
                }
            )

        entries.sort(
            key=lambda entry: (
                entry["label"].casefold(),
                entry["record_id"],
            )
        )

        return entries

    def add_reference(self):
        entries = self.get_picker_entries()
        entries_by_label = {entry["label"]: entry for entry in entries}
        picker = AssociationPicker(
            self,
            self.picker_title,
            [entry["label"] for entry in entries],
            [],
        )
        self.wait_window(picker)

        if picker.selected_name is None:
            return

        selected_entry = entries_by_label[picker.selected_name]
        self.references.append(
            {
                "record_id": selected_entry["record_id"],
                "name": selected_entry["name"],
            }
        )
        self.refresh_list(len(self.references) - 1)
        self.change_command()

    def remove_reference(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]
        del self.references[selected_index]
        next_index = (
            min(selected_index, len(self.references) - 1)
            if self.references
            else None
        )
        self.refresh_list(next_index)
        self.change_command()

    def move_reference_up(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices or selected_indices[0] == 0:
            return

        selected_index = selected_indices[0]
        target_index = selected_index - 1
        self.references[target_index], self.references[selected_index] = (
            self.references[selected_index],
            self.references[target_index],
        )
        self.refresh_list(target_index)
        self.change_command()

    def move_reference_down(self):
        selected_indices = self.listbox.curselection()

        if (
            not selected_indices
            or selected_indices[0] >= len(self.references) - 1
        ):
            return

        selected_index = selected_indices[0]
        target_index = selected_index + 1
        self.references[target_index], self.references[selected_index] = (
            self.references[selected_index],
            self.references[target_index],
        )
        self.refresh_list(target_index)
        self.change_command()

    def refresh_list(self, selected_index=None):
        records_by_id = self.get_records_by_id()
        self.listbox.delete(0, "end")

        for reference in self.references:
            record = records_by_id.get(reference.get("record_id"))
            label = (
                self.build_record_label(record)
                if record is not None
                else f"{reference.get('name', 'Missing record')} (missing)"
            )
            self.listbox.insert("end", f"• {label}")

        if selected_index is not None and self.references:
            self.listbox.selection_set(selected_index)
            self.listbox.activate(selected_index)
            self.listbox.see(selected_index)

        self.update_button_states()

    def update_button_states(self, event=None):
        selected_indices = self.listbox.curselection()
        has_selection = bool(selected_indices)
        selected_index = selected_indices[0] if has_selection else None
        self.remove_button.set_enabled(has_selection)
        self.up_button.set_enabled(
            has_selection and selected_index > 0
        )
        self.down_button.set_enabled(
            has_selection and selected_index < len(self.references) - 1
        )
