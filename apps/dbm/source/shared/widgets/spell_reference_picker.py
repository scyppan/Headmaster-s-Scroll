from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from runtime_theme import bind_theme
from sections.magic.spells.filter_dialog import (
    EMPTY_SPELL_FILTERS,
    SpellFilterDialog,
)
from sections.magic.spells.record_list import SpellList
from shared.widgets.controls import RoundedEntry, SoftButton
from theme import APP_BACKGROUND, FIELD_BACKGROUND, SURFACE, TEXT_DARK, app_font


class SpellReferencePicker(tk.Toplevel):
    """Reusable, search-and-filter-first chooser for a canonical spell record."""

    def __init__(self, parent, records, title="Choose spell"):
        super().__init__(parent)
        self.records = [record for record in records if record.get("record_id")]
        self.visible_records = []
        self.filters = dict(EMPTY_SPELL_FILTERS)
        self.result = None
        self.title(title)
        self.geometry("780x560")
        self.minsize(620, 420)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        search_row = tk.Frame(self, bg=APP_BACKGROUND)
        search_row.grid(row=0, column=0, sticky="ew", padx=14, pady=14)
        search_row.grid_columnconfigure(0, weight=1)
        self.query = tk.StringVar()
        self.query.trace_add("write", self.refresh)
        search = RoundedEntry(
            search_row, textvariable=self.query, background=APP_BACKGROUND,
            height=40, font=app_font(10),
        )
        search.grid(row=0, column=0, sticky="ew")
        SoftButton(
            search_row, text="Advanced filters…", command=self.open_filters,
            background=APP_BACKGROUND, width=150, height=40,
        ).grid(row=0, column=1, padx=(8, 0))

        self.results = ttk.Treeview(
            self, columns=("skill", "subtype", "threshold"),
            show="tree headings", selectmode="browse",
        )
        self.results.heading("#0", text="Spell")
        self.results.heading("skill", text="Skill")
        self.results.heading("subtype", text="Subtype")
        self.results.heading("threshold", text="Threshold")
        self.results.column("#0", width=320)
        self.results.column("skill", width=120)
        self.results.column("subtype", width=140)
        self.results.column("threshold", width=80, anchor="center")
        self.results.grid(row=1, column=0, sticky="nsew", padx=14)
        self.results.bind("<Double-1>", lambda _event: self.choose())
        self.results.bind("<Return>", lambda _event: self.choose())

        actions = tk.Frame(self, bg=APP_BACKGROUND)
        actions.grid(row=2, column=0, sticky="e", padx=14, pady=14)
        SoftButton(
            actions, text="Cancel", command=self.destroy,
            background=APP_BACKGROUND, width=100, height=36,
        ).pack(side="left", padx=4)
        SoftButton(
            actions, text="Choose", command=self.choose,
            background=APP_BACKGROUND, width=100, height=36,
        ).pack(side="left", padx=4)
        self.refresh()
        search.focus_set()

    def refresh(self, *_args):
        query = " ".join(self.query.get().casefold().split())
        terms = query.split()
        self.visible_records = []
        for record in self.records:
            if not SpellList.record_matches_filters(record, self.filters):
                continue
            searchable = " ".join((
                str(record.get("name", "")),
                str(record.get("incantation", "")),
                str(record.get("description", "")),
                str(record.get("skill", "")),
                str(record.get("subtype", "")),
                str(record.get("tradition", "")),
                " ".join(str(tag) for tag in record.get("tags", []) or []),
            )).casefold()
            if terms and not all(term in searchable for term in terms):
                continue
            self.visible_records.append(record)
        self.visible_records.sort(
            key=lambda record: (
                str(record.get("name", "")).casefold(),
                str(record.get("record_id", "")),
            )
        )
        self.results.delete(*self.results.get_children())
        for index, record in enumerate(self.visible_records):
            self.results.insert(
                "", "end", iid=str(index), text=str(record.get("name", "")),
                values=(
                    record.get("skill", ""), record.get("subtype", ""),
                    record.get("threshold", ""),
                ),
            )

    def open_filters(self):
        dialog = SpellFilterDialog(self, self.records, self.filters)
        self.wait_window(dialog)
        if dialog.result is not None:
            self.filters = dialog.result
            self.refresh()

    def choose(self):
        selected = self.results.selection()
        if not selected:
            return
        self.result = self.visible_records[int(selected[0])]
        self.destroy()
