import tkinter as tk
from collections import Counter
from tkinter import ttk

from theme import (
    PRIMARY,
    PRIMARY_LIGHT,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
)


class RecordSelector(tk.Frame):
    def __init__(
        self,
        parent,
        selection_command,
        previous_command,
        next_command,
    ):
        super().__init__(parent, bg=SURFACE)

        self.selection_command = selection_command
        self.records = []
        self.record_ids = []
        self.labels_by_id = {}
        self.ids_by_label = {}

        self.grid_columnconfigure(1, weight=1)

        self.search_label = tk.Label(
            self,
            text="Find record",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=("Segoe UI", 10, "bold"),
        )
        self.search_label.grid(row=0, column=0, padx=(0, 10), sticky="w")

        self.search_value = tk.StringVar()
        self.search_box = ttk.Combobox(
            self,
            textvariable=self.search_value,
            state="normal",
            font=("Segoe UI", 11),
        )
        self.search_box.grid(row=0, column=1, sticky="ew")
        self.search_box.bind(
            "<<ComboboxSelected>>",
            self.handle_selection,
        )
        self.search_box.bind("<KeyRelease>", self.filter_records)

        self.previous_button = tk.Button(
            self,
            text="Previous",
            command=previous_command,
            bg=PRIMARY_LIGHT,
            fg=TEXT_DARK,
            activebackground=PRIMARY,
            relief="flat",
            padx=14,
            pady=7,
        )
        self.previous_button.grid(row=0, column=2, padx=(12, 5))

        self.next_button = tk.Button(
            self,
            text="Next",
            command=next_command,
            bg=PRIMARY_LIGHT,
            fg=TEXT_DARK,
            activebackground=PRIMARY,
            relief="flat",
            padx=14,
            pady=7,
        )
        self.next_button.grid(row=0, column=3, padx=(5, 0))

        self.position_label = tk.Label(
            self,
            text="No records",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=("Segoe UI", 9),
        )
        self.position_label.grid(row=1, column=1, pady=(5, 0), sticky="w")

    def set_records(self, records, selected_record_id=None):
        self.records = records
        self.record_ids = [record["record_id"] for record in records]
        self.labels_by_id = {}
        self.ids_by_label = {}

        name_counts = Counter(record.get("name", "") for record in records)

        for record in records:
            record_id = record["record_id"]
            record_name = record.get("name", "") or "Unnamed record"

            if name_counts[record.get("name", "")] > 1:
                record_date = record.get("last_updated", "")[:10]
                record_label = f"{record_name} — {record_date} — {record_id}"
            else:
                record_label = record_name

            self.labels_by_id[record_id] = record_label
            self.ids_by_label[record_label] = record_id

        self.search_box["values"] = [
            self.labels_by_id[record_id] for record_id in self.record_ids
        ]

        if selected_record_id is not None:
            self.set_selected_record(selected_record_id)
        elif not records:
            self.clear_selection()

    def set_selected_record(self, record_id):
        record_label = self.labels_by_id.get(record_id, "")
        self.search_value.set(record_label)
        self.update_position(record_id)

    def clear_selection(self):
        self.search_value.set("")
        self.position_label.config(text="New record")

    def handle_selection(self, event):
        selected_label = self.search_value.get()
        selected_id = self.ids_by_label.get(selected_label)

        if selected_id is not None:
            self.selection_command(selected_id)

    def filter_records(self, event):
        search_text = self.search_value.get().casefold().strip()

        if not search_text:
            matching_labels = [
                self.labels_by_id[record_id]
                for record_id in self.record_ids
            ]
        else:
            matching_labels = [
                self.labels_by_id[record_id]
                for record_id in self.record_ids
                if search_text
                in self.labels_by_id[record_id].casefold()
            ]

        self.search_box["values"] = matching_labels

    def get_adjacent_record_id(self, current_record_id, direction):
        if current_record_id not in self.record_ids:
            return None

        current_index = self.record_ids.index(current_record_id)
        target_index = current_index + direction

        if target_index < 0 or target_index >= len(self.record_ids):
            return None

        return self.record_ids[target_index]

    def update_position(self, record_id):
        if record_id not in self.record_ids:
            self.position_label.config(text="No record selected")
            return

        record_index = self.record_ids.index(record_id) + 1
        self.position_label.config(
            text=f"Record {record_index} of {len(self.record_ids)}"
        )
