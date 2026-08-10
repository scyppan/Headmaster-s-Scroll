import tkinter as tk
from tkinter import messagebox

from mage_maker.sections.ledger.models import (
    LEDGER_KIND_BOUGHT,
    LEDGER_KIND_EARNED,
    LEDGER_YEAR_MONTHS,
    MONTH_NAMES,
    new_manual_calendar_ledger_entry,
    normalize_ledger_entry,
    updated_ledger_entry,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    FIELD_BACKGROUND,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import (
    CalendarAdoptionNotice,
    RoundedEntry,
    RoundedSelect,
    SoftButton,
)


LEDGER_DIALOG_KIND_LABELS = (
    "Bought",
    "Sold or earned",
)
LEDGER_DIALOG_MONTH_NAMES = tuple(
    MONTH_NAMES[month_number - 1]
    for month_number in LEDGER_YEAR_MONTHS
)


class LedgerEntryDialog(tk.Toplevel):
    def __init__(
        self,
        parent,
        page,
        save_command,
        entry=None,
    ):
        super().__init__(parent)
        self.page = dict(page)
        self.calendar_year = int(self.page["calendar_year"])
        self.calendar_end_year = int(
            self.page.get(
                "calendar_end_year",
                self.calendar_year,
            )
        )
        self.school_year = (
            int(self.page["school_year"])
            if self.page.get("school_year") not in (None, "")
            else None
        )
        self.adult_year = (
            int(self.page["adult_year"])
            if self.page.get("adult_year") not in (None, "")
            else None
        )
        self.entry = (
            normalize_ledger_entry(entry)
            if isinstance(entry, dict)
            else None
        )
        self.save_command = save_command
        self.month_value = tk.StringVar(
            value=(
                MONTH_NAMES[self.entry["month"] - 1]
                if self.entry is not None
                else LEDGER_DIALOG_MONTH_NAMES[0]
            )
        )
        self.year_value = tk.StringVar(
            value=str(
                self.entry["calendar_year"]
                if self.entry is not None
                else self.calendar_year
            )
        )
        self.day_value = tk.StringVar(
            value=str(
                self.entry["day"]
                if self.entry is not None
                else 1
            )
        )
        self.item_value = tk.StringVar(
            value=(
                self.entry["item"]
                if self.entry is not None
                else ""
            )
        )
        self.kind_value = tk.StringVar(
            value=(
                "Bought"
                if self.entry is not None
                and self.entry["kind"] == LEDGER_KIND_BOUGHT
                else "Sold or earned"
                if self.entry is not None
                else LEDGER_DIALOG_KIND_LABELS[0]
            )
        )
        self.amount_value = tk.StringVar(
            value=(
                str(self.entry["amount_sickles"])
                if self.entry is not None
                else ""
            )
        )
        self.title(
            (
                "Edit ledger entry"
                if self.entry is not None
                else "Add ledger entry"
            )
        )
        self.geometry("590x500")
        self.minsize(540, 460)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent.winfo_toplevel())
        self.grab_set()
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.build_dialog()
        self.bind("<Escape>", self.close_dialog)
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.after_idle(self.focus_item)

    def build_dialog(self):
        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            padx=20,
            pady=18,
        )
        card.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_columnconfigure((0, 1), weight=1)
        card.grid_rowconfigure(8, weight=1)
        heading = tk.Label(
            card,
            text=(
                (
                    "Edit line item"
                    if self.entry is not None
                    else "Add line item"
                )
                + " · "
                + str(
                    self.page.get(
                        "title",
                        self.calendar_year,
                    )
                )
            ),
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15, "bold"),
            anchor="w",
        )
        heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 14),
        )
        month_label = tk.Label(
            card,
            text="Date",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        month_label.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=(0, 7),
            pady=(0, 5),
        )
        kind_label = tk.Label(
            card,
            text="Type",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        kind_label.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(7, 0),
            pady=(0, 5),
        )
        date_controls = tk.Frame(card, bg=SURFACE)
        date_controls.grid(
            row=2,
            column=0,
            sticky="ew",
            padx=(0, 7),
        )
        date_controls.grid_columnconfigure(1, weight=1)
        self.year_entry = RoundedEntry(
            date_controls,
            textvariable=self.year_value,
            background=SURFACE,
            width=72,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.year_entry.grid(
            row=0,
            column=0,
        )
        self.month_select = RoundedSelect(
            date_controls,
            self.month_value,
            LEDGER_DIALOG_MONTH_NAMES,
            background=SURFACE,
            width=116,
            height=38,
            font=app_font(10),
        )
        self.month_select.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(7, 0),
        )
        self.day_entry = RoundedEntry(
            date_controls,
            textvariable=self.day_value,
            background=SURFACE,
            width=54,
            height=38,
            font=app_font(10),
            justify="center",
        )
        self.day_entry.grid(
            row=0,
            column=2,
            padx=(7, 0),
        )
        calendar_notice = CalendarAdoptionNotice(
            date_controls,
            background=SURFACE,
            wraplength=440,
            date_variables=(
                self.year_value,
                self.month_value,
                self.day_value,
            ),
        )
        calendar_notice.grid(
            row=1,
            column=0,
            columnspan=3,
            sticky="w",
            pady=(5, 0),
        )
        self.kind_select = RoundedSelect(
            card,
            self.kind_value,
            LEDGER_DIALOG_KIND_LABELS,
            background=SURFACE,
            width=240,
            height=38,
            font=app_font(10),
        )
        self.kind_select.grid(
            row=2,
            column=1,
            sticky="ew",
            padx=(7, 0),
        )
        item_label = tk.Label(
            card,
            text="Item",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        item_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 5),
        )
        self.item_entry = RoundedEntry(
            card,
            textvariable=self.item_value,
            background=SURFACE,
            width=500,
            height=38,
            font=app_font(10),
        )
        self.item_entry.grid(
            row=4,
            column=0,
            columnspan=2,
            sticky="ew",
        )
        amount_label = tk.Label(
            card,
            text="Amount in sickles",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        amount_label.grid(
            row=5,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(12, 5),
        )
        self.amount_entry = RoundedEntry(
            card,
            textvariable=self.amount_value,
            background=SURFACE,
            width=220,
            height=38,
            font=app_font(10),
        )
        self.amount_entry.grid(
            row=6,
            column=0,
            sticky="w",
        )
        note_label = tk.Label(
            card,
            text="Note",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        note_label.grid(
            row=7,
            column=0,
            columnspan=2,
            sticky="new",
            pady=(12, 5),
        )
        self.note_text = tk.Text(
            card,
            height=5,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            insertbackground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            highlightthickness=1,
            font=app_font(10),
            wrap="word",
            padx=10,
            pady=8,
        )
        self.note_text.grid(
            row=8,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

        if self.entry is not None:
            self.note_text.insert(
                "1.0",
                self.entry["note"],
            )
        footer = tk.Frame(card, bg=SURFACE)
        footer.grid(
            row=9,
            column=0,
            columnspan=2,
            sticky="e",
            pady=(16, 0),
        )
        cancel_button = SoftButton(
            footer,
            text="Cancel",
            command=self.destroy,
            background=SURFACE,
            width=88,
            height=38,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        save_button = SoftButton(
            footer,
            text=(
                "Save changes"
                if self.entry is not None
                else "Add line item"
            ),
            command=self.save_entry,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=124,
            height=38,
        )
        save_button.pack(side="left")

    def focus_item(self):
        self.item_entry.focus_set()

    def close_dialog(self, event=None):
        self.destroy()
        return "break"

    def save_entry(self):
        item = self.item_value.get().strip()

        if not item:
            messagebox.showerror(
                "Item required",
                "Enter the item that was bought, sold, or earned.",
                parent=self,
            )
            return

        try:
            amount_sickles = int(self.amount_value.get().strip())
        except (TypeError, ValueError):
            messagebox.showerror(
                "Amount required",
                "Enter a non-negative whole number of sickles.",
                parent=self,
            )
            return

        if amount_sickles < 0:
            messagebox.showerror(
                "Invalid amount",
                "Enter a non-negative whole number of sickles.",
                parent=self,
            )
            return

        kind = (
            LEDGER_KIND_BOUGHT
            if self.kind_value.get() == "Bought"
            else LEDGER_KIND_EARNED
        )

        try:
            calendar_year = int(self.year_value.get().strip())
        except (TypeError, ValueError):
            messagebox.showerror(
                "Invalid date",
                "Enter a whole calendar year.",
                parent=self,
            )
            return

        month = MONTH_NAMES.index(
            self.month_value.get()
        ) + 1

        if not self.date_belongs_to_page(
            calendar_year,
            month,
        ):
            messagebox.showerror(
                "Date outside this development year",
                (
                    "Choose a date that belongs to "
                    f"{self.page.get('title', 'this development year')}."
                ),
                parent=self,
            )
            return

        try:
            entry = (
                updated_ledger_entry(
                    self.entry,
                    calendar_year,
                    self.month_value.get(),
                    self.day_value.get(),
                    item,
                    amount_sickles,
                    kind,
                    self.note_text.get("1.0", "end-1c"),
                )
                if self.entry is not None
                else new_manual_calendar_ledger_entry(
                    calendar_year,
                    self.month_value.get(),
                    item,
                    amount_sickles,
                    kind,
                    self.note_text.get("1.0", "end-1c"),
                    self.school_year,
                    self.adult_year,
                    self.day_value.get(),
                )
            )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Invalid date",
                str(error),
                parent=self,
            )
            return

        self.save_command(entry)
        self.destroy()

    def date_belongs_to_page(self, calendar_year, month):
        normalized_year = int(calendar_year)
        normalized_month = int(month)

        if self.school_year is not None:
            return (
                normalized_year == self.calendar_year
                and normalized_month >= 7
            ) or (
                normalized_year == self.calendar_end_year
                and normalized_month <= 6
            )

        if self.adult_year == 1:
            return (
                normalized_year == self.calendar_year
                and normalized_month >= 7
            ) or (
                normalized_year == self.calendar_end_year
            )

        return normalized_year == self.calendar_year
