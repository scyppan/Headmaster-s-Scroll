import tkinter as tk
from collections import Counter

from runtime_theme import bind_theme
from shared.widgets.controls import RoundedEntry
from shared.widgets.striped_listbox import StripedListbox
from theme import (
    app_font,
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_HOVER,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
)


class SearchableRecordList(tk.Frame):
    def __init__(
        self,
        parent,
        selection_command,
        heading_text,
        item_word,
        unnamed_label,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.selection_command = selection_command
        self.heading_text = heading_text
        self.item_word = item_word
        self.unnamed_label = unnamed_label
        self.records = []
        self.visible_record_ids = []
        self.labels_by_id = {}
        self.selected_record_id = None
        self.suppress_selection_event = False
        self.hovered_index = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text=heading_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15),
            anchor="w",
        )
        self.heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(16, 10),
        )
        bind_theme(
            self.heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_records)
        self.search_entry = RoundedEntry(
            self,
            textvariable=self.search_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )

        self.listbox = StripedListbox(
            self,
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
        self.listbox.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(16, 0),
        )
        self.listbox.bind("<<ListboxSelect>>", self.handle_selection)
        self.listbox.bind("<Motion>", self.handle_hover)
        self.listbox.bind("<Leave>", self.clear_hover)
        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.listbox.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(
            row=2,
            column=1,
            sticky="ns",
            padx=(0, 16),
        )
        self.listbox.configure(yscrollcommand=self.scrollbar.set)

        self.count_label = tk.Label(
            self,
            text=f"0 {item_word}",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.count_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(8, 14),
        )
        bind_theme(
            self.count_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

    def set_records(self, records, selected_record_id=None):
        self.records = records
        self.labels_by_id = {}

        name_counts = Counter(record.get("name", "") for record in records)

        for record in records:
            record_id = record["record_id"]
            record_name = record.get("name", "") or self.unnamed_label

            if name_counts[record.get("name", "")] > 1:
                record_date = record.get("last_updated", "")[:10]
                record_label = f"{record_name} — {record_date}"
            else:
                record_label = record_name

            self.labels_by_id[record_id] = record_label

        self.selected_record_id = selected_record_id
        self.rebuild_visible_list()

    def set_selected_record(self, record_id):
        self.selected_record_id = record_id

        if record_id not in self.visible_record_ids:
            self.search_value.set("")

        self.select_visible_record()

    def clear_selection(self):
        self.selected_record_id = None
        self.suppress_selection_event = True
        self.listbox.selection_clear(0, "end")
        self.suppress_selection_event = False

    def filter_records(self, *arguments):
        self.rebuild_visible_list()

    def rebuild_visible_list(self):
        search_text = self.search_value.get().casefold().strip()

        if search_text:
            visible_records = [
                record
                for record in self.records
                if search_text
                in self.labels_by_id[record["record_id"]].casefold()
            ]
        else:
            visible_records = self.records

        self.visible_record_ids = [
            record["record_id"] for record in visible_records
        ]

        self.suppress_selection_event = True
        self.listbox.delete(0, "end")

        for record_id in self.visible_record_ids:
            self.listbox.insert("end", self.labels_by_id[record_id])

        self.suppress_selection_event = False
        self.hovered_index = None
        self.select_visible_record()

        visible_count = len(self.visible_record_ids)
        total_count = len(self.records)

        if visible_count == total_count:
            self.count_label.config(text=f"{total_count} {self.item_word}")
        else:
            self.count_label.config(
                text=(
                    f"{visible_count} of {total_count} "
                    f"{self.item_word}"
                )
            )

    def select_visible_record(self):
        self.suppress_selection_event = True
        self.listbox.selection_clear(0, "end")

        if self.selected_record_id in self.visible_record_ids:
            selected_index = self.visible_record_ids.index(
                self.selected_record_id
            )
            self.listbox.selection_set(selected_index)
            self.listbox.activate(selected_index)
            self.listbox.see(selected_index)

        self.suppress_selection_event = False

    def handle_selection(self, event):
        if self.suppress_selection_event:
            return

        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        selected_index = selected_indices[0]
        selected_record_id = self.visible_record_ids[selected_index]
        selection_accepted = self.selection_command(selected_record_id)

        if selection_accepted is False:
            self.select_visible_record()

    def handle_hover(self, event):
        if not self.visible_record_ids:
            return

        hovered_index = self.listbox.nearest(event.y)

        if hovered_index == self.hovered_index:
            return

        self.clear_hover()
        self.hovered_index = hovered_index
        self.listbox.set_hovered_index(hovered_index)

    def clear_hover(self, event=None):
        self.hovered_index = None
        self.listbox.clear_hovered_index()
