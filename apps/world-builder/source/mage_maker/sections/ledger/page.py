import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, ttk

from mage_maker.sections.ledger.dialog import LedgerEntryDialog
from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_KIND_EARNED,
    delete_ledger_entry,
    format_signed_ledger_currency,
    ledger_amount_text,
    ledger_balance_sickles,
    ledger_entry_date_text,
    ledger_entries_for_calendar_year,
    ledger_running_balances,
    normalize_ledger_entries,
    replace_ledger_entry,
)
from mage_maker.ui.theme import (
    BORDER,
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    FIELD_BACKGROUND,
    LIST_ALTERNATE,
    LIST_SELECTED,
    LOCKED_RED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import SectionPanel, SoftButton


LEDGER_EARNED_GREEN = "#24713A"


class LedgerView(tk.Frame):
    def __init__(self, parent, change_command=None):
        super().__init__(parent, bg=SURFACE)
        self.change_command = change_command
        self.entries = []
        self.year_pages = []
        self.active_page_index = 0
        self.context_id = None
        self.year_heading_value = tk.StringVar(
            value="No development year selected"
        )
        self.balance_value = tk.StringVar(
            value="$0"
        )
        self.empty_value = tk.StringVar(
            value="Start school to create the first ledger year."
        )
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_header()
        self.build_table()
        self.update_year_controls()

    def build_header(self):
        header = tk.Frame(self, bg=SURFACE)
        header.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 14),
        )
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            text="Ledger",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(16, "bold"),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        balance_block = tk.Frame(header, bg=SURFACE)
        balance_block.grid(
            row=0,
            column=1,
            sticky="e",
            padx=(8, 10),
        )
        balance_label = tk.Label(
            balance_block,
            text="Current balance",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8, "bold"),
            anchor="e",
        )
        balance_label.grid(row=0, column=0, sticky="e")
        balance_value = tk.Label(
            balance_block,
            textvariable=self.balance_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="e",
        )
        balance_value.grid(
            row=1,
            column=0,
            sticky="e",
            pady=(2, 0),
        )
        self.previous_year_button = SoftButton(
            header,
            text="<",
            command=self.select_previous_year,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=38,
            height=34,
            font=app_font(11, "bold"),
            padx=4,
        )
        self.previous_year_button.grid(
            row=0,
            column=2,
            padx=(8, 4),
        )
        year_heading = tk.Label(
            header,
            textvariable=self.year_heading_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="center",
            width=34,
        )
        year_heading.grid(
            row=0,
            column=3,
            padx=4,
        )
        self.next_year_button = SoftButton(
            header,
            text=">",
            command=self.select_next_year,
            background=SURFACE,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=38,
            height=34,
            font=app_font(11, "bold"),
            padx=4,
        )
        self.next_year_button.grid(
            row=0,
            column=4,
            padx=4,
        )
        self.add_entry_button = SoftButton(
            header,
            text="Add line item",
            command=self.open_add_entry_dialog,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=118,
            height=34,
            font=app_font(9, "bold"),
        )
        self.add_entry_button.grid(
            row=0,
            column=5,
            padx=(8, 0),
        )
        self.edit_entry_button = SoftButton(
            header,
            text="Edit",
            command=self.open_edit_entry_dialog,
            background=SURFACE,
            width=68,
            height=34,
            font=app_font(9, "bold"),
        )
        self.edit_entry_button.grid(
            row=0,
            column=6,
            padx=(6, 0),
        )
        self.delete_entry_button = SoftButton(
            header,
            text="Delete",
            command=self.delete_selected_entry,
            background=SURFACE,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            foreground=TEXT_DARK,
            width=76,
            height=34,
            font=app_font(9, "bold"),
        )
        self.delete_entry_button.grid(
            row=0,
            column=7,
            padx=(6, 0),
        )

    def build_table(self):
        panel = SectionPanel(
            self,
            "Year ledger",
            (
                "Ledger years run July through June. The opening allowance "
                "lands in July, and monthly allowance begins in August. "
                "School books appear at $0 when caregivers buy them."
            ),
        )
        panel.grid(
            row=1,
            column=0,
            sticky="nsew",
        )
        panel.content.grid_rowconfigure(0, weight=1)
        panel.content.grid_columnconfigure(0, weight=1)
        style = ttk.Style(self)
        style.configure(
            "Ledger.Treeview",
            background=FIELD_BACKGROUND,
            fieldbackground=FIELD_BACKGROUND,
            foreground=TEXT_DARK,
            rowheight=30,
            borderwidth=0,
            font=app_font(10),
        )
        style.configure(
            "Ledger.Treeview.Heading",
            background=SURFACE_MUTED,
            foreground=TEXT_DARK,
            relief="flat",
            font=app_font(10, "bold"),
        )
        style.map(
            "Ledger.Treeview",
            background=[("selected", LIST_SELECTED)],
            foreground=[("selected", TEXT_DARK)],
        )
        table_frame = tk.Frame(
            panel.content,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        table_frame.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        table_frame.grid_rowconfigure(0, weight=1)
        table_frame.grid_columnconfigure(0, weight=1)
        self.table = ttk.Treeview(
            table_frame,
            columns=(
                "date",
                "item",
                "amount",
                "running_total",
                "note",
            ),
            show="headings",
            selectmode="browse",
            style="Ledger.Treeview",
        )
        self.table.heading("date", text="Date")
        self.table.heading("item", text="Item")
        self.table.heading("amount", text="Amount")
        self.table.heading(
            "running_total",
            text="Running total",
        )
        self.table.heading("note", text="Note")
        self.table.column(
            "date",
            width=112,
            minwidth=104,
            stretch=False,
            anchor="w",
        )
        self.table.column(
            "item",
            width=260,
            minwidth=160,
            stretch=True,
            anchor="w",
        )
        self.table.column(
            "amount",
            width=165,
            minwidth=130,
            stretch=False,
            anchor="e",
        )
        self.table.column(
            "running_total",
            width=165,
            minwidth=130,
            stretch=False,
            anchor="e",
        )
        self.table.column(
            "note",
            width=270,
            minwidth=150,
            stretch=True,
            anchor="w",
        )
        self.table.tag_configure(
            LEDGER_KIND_EARNED,
            foreground=LEDGER_EARNED_GREEN,
        )
        self.table.tag_configure(
            LEDGER_KIND_BOUGHT,
            foreground=LOCKED_RED,
        )
        self.table.tag_configure(
            "alternate",
            background=LIST_ALTERNATE,
        )
        self.table.grid(
            row=0,
            column=0,
            sticky="nsew",
        )
        self.table.bind(
            "<<TreeviewSelect>>",
            self.update_entry_buttons,
        )
        self.table.bind(
            "<Double-Button-1>",
            self.open_edit_entry_dialog,
        )
        scrollbar = ttk.Scrollbar(
            table_frame,
            orient="vertical",
            command=self.table.yview,
        )
        scrollbar.grid(
            row=0,
            column=1,
            sticky="ns",
        )
        self.table.configure(yscrollcommand=scrollbar.set)
        self.empty_label = tk.Label(
            panel.content,
            textvariable=self.empty_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="nw",
            justify="left",
            padx=14,
            pady=14,
        )
        self.empty_label.grid(
            row=0,
            column=0,
            sticky="nsew",
        )

    def set_context(
        self,
        entries,
        year_pages,
        academic_start_year=None,
        context_id=None,
    ):
        self.entries = normalize_ledger_entries(entries)
        previous_page_key = (
            self.year_pages[self.active_page_index]["page_key"]
            if self.year_pages
            and 0 <= self.active_page_index < len(self.year_pages)
            else None
        )

        if isinstance(year_pages, int):
            self.year_pages = [
                {
                    "page_key": f"school:{school_year}",
                    "page_type": "school",
                    "school_year": school_year,
                    "adult_year": None,
                    "calendar_year": (
                        int(academic_start_year) + school_year - 1
                        if academic_start_year not in (None, "")
                        else None
                    ),
                    "calendar_end_year": (
                        int(academic_start_year) + school_year
                        if academic_start_year not in (None, "")
                        else None
                    ),
                    "title": (
                        f"Year {school_year} "
                        f"({int(academic_start_year) + school_year - 1}-"
                        f"{int(academic_start_year) + school_year})"
                        if academic_start_year not in (None, "")
                        else f"Year {school_year}"
                    ),
                }
                for school_year in range(1, year_pages + 1)
            ]
        else:
            self.year_pages = [
                deepcopy(page)
                for page in year_pages or []
                if isinstance(page, dict)
                and str(page.get("page_key", "") or "").strip()
            ]

        context_changed = context_id != self.context_id
        self.context_id = context_id

        if not self.year_pages:
            self.active_page_index = 0
        elif context_changed or previous_page_key is None:
            self.active_page_index = 0
        else:
            self.active_page_index = next(
                (
                    index
                    for index, page in enumerate(self.year_pages)
                    if page["page_key"] == previous_page_key
                ),
                min(
                    self.active_page_index,
                    len(self.year_pages) - 1,
                ),
            )

        self.update_year_controls()

    def update_year_controls(self):
        has_year = bool(self.year_pages)

        if has_year:
            active_page = self.year_pages[
                self.active_page_index
            ]
            calendar_year = active_page.get("calendar_year")
            self.year_heading_value.set(
                str(
                    active_page.get(
                        "title",
                        calendar_year
                        if calendar_year is not None
                        else "Development year",
                    )
                )
            )
        else:
            self.year_heading_value.set("No development years")

        self.balance_value.set(
            format_signed_ledger_currency(
                ledger_balance_sickles(self.entries)
            )
        )

        self.previous_year_button.set_enabled(
            has_year and self.active_page_index > 0
        )
        self.next_year_button.set_enabled(
            has_year
            and self.active_page_index < len(self.year_pages) - 1
        )
        self.add_entry_button.set_enabled(
            has_year
            and self.year_pages[
                self.active_page_index
            ].get("calendar_year")
            is not None
        )
        self.refresh_table()
        self.update_entry_buttons()

    def select_previous_year(self):
        if self.active_page_index <= 0:
            return

        self.active_page_index -= 1
        self.update_year_controls()

    def select_next_year(self):
        if self.active_page_index >= len(self.year_pages) - 1:
            return

        self.active_page_index += 1
        self.update_year_controls()

    def refresh_table(self):
        for item_id in self.table.get_children():
            self.table.delete(item_id)

        if not self.year_pages:
            self.empty_value.set(
                "Start school to create the first ledger year."
            )
            self.table.grid_remove()
            self.empty_label.grid()
            return

        active_page = self.year_pages[self.active_page_index]
        year_entries = ledger_entries_for_calendar_year(
            self.entries,
            active_page.get("calendar_year"),
            active_page.get("school_year"),
            active_page.get("adult_year"),
        )

        if not year_entries:
            self.empty_value.set(
                "No ledger entries have been recorded for this year."
            )
            self.table.grid_remove()
            self.empty_label.grid()
            return

        self.empty_label.grid_remove()
        self.table.grid()
        running_balances = ledger_running_balances(
            self.entries
        )

        for row_index, entry in enumerate(year_entries):
            tags = [entry["kind"]]

            if row_index % 2:
                tags.append("alternate")

            self.table.insert(
                "",
                "end",
                iid=entry["entry_id"],
                values=(
                    ledger_entry_date_text(entry),
                    entry["item"],
                    ledger_amount_text(entry),
                    format_signed_ledger_currency(
                        running_balances.get(
                            entry["entry_id"],
                            0,
                        )
                    ),
                    entry["note"],
                ),
                tags=tuple(tags),
            )

    def open_add_entry_dialog(self):
        if not self.year_pages:
            return

        active_page = self.year_pages[self.active_page_index]
        calendar_year = active_page.get("calendar_year")

        if calendar_year is None:
            return

        LedgerEntryDialog(
            self,
            active_page,
            self.save_manual_entry,
        )

    def save_manual_entry(self, entry):
        entry_id = str(entry.get("entry_id", "") or "")

        if any(
            stored_entry["entry_id"] == entry_id
            for stored_entry in self.entries
        ):
            self.entries = replace_ledger_entry(
                self.entries,
                deepcopy(entry),
            )
        else:
            self.entries = normalize_ledger_entries(
                [*self.entries, deepcopy(entry)]
            )

        self.update_year_controls()

        if self.change_command is not None:
            self.change_command(deepcopy(self.entries))

    def selected_entry(self):
        selected_items = self.table.selection()

        if not selected_items:
            return None

        selected_id = str(selected_items[0] or "")
        return next(
            (
                deepcopy(entry)
                for entry in self.entries
                if entry["entry_id"] == selected_id
                and not entry["suppressed"]
            ),
            None,
        )

    def update_entry_buttons(self, event=None):
        has_selection = self.selected_entry() is not None
        self.edit_entry_button.set_enabled(has_selection)
        self.delete_entry_button.set_enabled(has_selection)

    def open_edit_entry_dialog(self, event=None):
        entry = self.selected_entry()

        if entry is None or not self.year_pages:
            return

        LedgerEntryDialog(
            self,
            self.year_pages[self.active_page_index],
            self.save_manual_entry,
            entry,
        )

    def delete_selected_entry(self):
        entry = self.selected_entry()

        if entry is None:
            return

        if not messagebox.askyesno(
            "Delete ledger entry",
            f"Delete {entry['item']} from the ledger?",
            parent=self,
        ):
            return

        self.entries = delete_ledger_entry(
            self.entries,
            entry["entry_id"],
        )
        self.update_year_controls()

        if self.change_command is not None:
            self.change_command(deepcopy(self.entries))
