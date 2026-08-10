import tkinter as tk
from functools import partial

from runtime_theme import bind_theme
from shared.widgets import RoundedEntry, RoundedSelect, SoftButton
from theme import (
    app_font,
    BORDER,
    PRIMARY,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
)


class BonusRow(tk.Frame):
    bonus_types = (
        "",
        "Ability",
        "Skill",
        "Subtype",
        "Characteristic",
    )

    def __init__(self, parent, change_command, remove_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.remove_command = remove_command
        self.loading_bonus = False

        self.grid_columnconfigure(0, weight=2)
        self.grid_columnconfigure(1, weight=4)
        self.grid_columnconfigure(2, weight=1)

        self.type_value = tk.StringVar()
        self.type_value.trace_add("write", self.handle_change)
        self.type_box = RoundedSelect(
            self,
            variable=self.type_value,
            values=self.bonus_types,
            background=SURFACE,
            width=150,
            height=38,
            font=app_font(10),
        )
        self.type_box.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=(0, 6),
        )

        self.target_value = tk.StringVar()
        self.target_value.trace_add("write", self.handle_change)
        self.target_entry = RoundedEntry(
            self,
            textvariable=self.target_value,
            background=SURFACE,
            width=260,
            height=38,
            font=app_font(10),
        )
        self.target_entry.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=6,
        )

        self.amount_value = tk.StringVar()
        self.amount_value.trace_add("write", self.handle_change)
        self.amount_entry = RoundedEntry(
            self,
            textvariable=self.amount_value,
            background=SURFACE,
            width=90,
            height=38,
            justify="center",
            font=app_font(10),
        )
        self.amount_entry.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=6,
        )

        self.remove_button = SoftButton(
            self,
            text="Remove",
            command=partial(self.remove_command, self),
            background=SURFACE,
            width=82,
            height=36,
        )
        self.remove_button.grid(row=0, column=3, padx=(6, 0))

    def set_bonus(self, bonus):
        self.loading_bonus = True
        self.type_value.set(bonus.get("type", ""))
        self.target_value.set(bonus.get("target", ""))

        amount = bonus.get("amount")
        self.amount_value.set("" if amount is None else str(amount))
        self.loading_bonus = False

    def get_bonus(self):
        amount_text = self.amount_value.get().strip()
        amount = int(amount_text) if amount_text else None

        return {
            "type": self.type_value.get().strip(),
            "target": self.target_value.get().strip(),
            "amount": amount,
        }

    def is_empty(self):
        return not (
            self.type_value.get().strip()
            or self.target_value.get().strip()
            or self.amount_value.get().strip()
        )

    def handle_change(self, *arguments):
        if not self.loading_bonus:
            self.change_command()

    def bind_mousewheel(self, mousewheel_command):
        self.bind("<MouseWheel>", mousewheel_command)
        self.type_box.bind_mousewheel(mousewheel_command)
        self.target_entry.bind_input("<MouseWheel>", mousewheel_command)
        self.amount_entry.bind_input("<MouseWheel>", mousewheel_command)
        self.remove_button.bind_mousewheel(mousewheel_command)


class BonusEditor(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.bonus_rows = []

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading_bar = tk.Frame(self, bg=SURFACE)
        bind_theme(self.heading_bar, background="SURFACE")
        self.heading_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.heading_bar.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self.heading_bar,
            text="Bonuses",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.heading.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.add_button = SoftButton(
            self.heading_bar,
            text="Add Bonus",
            command=self.add_bonus,
            background=SURFACE,
            fill=PRIMARY,
            fill_role="PRIMARY",
            hover_fill_role="PRIMARY_DARK",
            width=106,
            height=36,
        )
        self.add_button.grid(row=0, column=1)

        self.column_headers = tk.Frame(self, bg=SURFACE)
        bind_theme(self.column_headers, background="SURFACE")
        self.column_headers.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(6, 4),
        )
        self.column_headers.grid_columnconfigure(0, weight=2)
        self.column_headers.grid_columnconfigure(1, weight=4)
        self.column_headers.grid_columnconfigure(2, weight=1)

        self.type_header = tk.Label(
            self.column_headers,
            text="Type",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.type_header.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.type_header,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.target_header = tk.Label(
            self.column_headers,
            text="Target",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.target_header.grid(row=0, column=1, sticky="ew", padx=12)
        bind_theme(
            self.target_header,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.amount_header = tk.Label(
            self.column_headers,
            text="Amount",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="center",
        )
        self.amount_header.grid(row=0, column=2, sticky="ew")
        bind_theme(
            self.amount_header,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.scroll_area = tk.Canvas(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            height=150,
        )
        self.scroll_area.grid(row=2, column=0, sticky="nsew")
        self.scroll_area.bind("<Configure>", self.resize_rows_frame)
        self.scroll_area.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(
            self.scroll_area,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.scroll_area.yview,
        )
        self.scrollbar.grid(row=2, column=1, sticky="ns")
        self.scroll_area.configure(yscrollcommand=self.scrollbar.set)

        self.rows_frame = tk.Frame(self.scroll_area, bg=SURFACE)
        bind_theme(self.rows_frame, background="SURFACE")
        self.rows_frame.bind("<Configure>", self.update_scroll_region)
        self.rows_frame.bind("<MouseWheel>", self.scroll_with_mousewheel)
        self.rows_window = self.scroll_area.create_window(
            (0, 0),
            window=self.rows_frame,
            anchor="nw",
        )

    def set_bonuses(self, bonuses):
        for bonus_row in self.bonus_rows:
            bonus_row.destroy()

        self.bonus_rows = []

        for bonus in bonuses:
            self.add_bonus_row(bonus, notify_change=False)

    def get_bonuses(self):
        bonuses = []

        for bonus_row in self.bonus_rows:
            if not bonus_row.is_empty():
                bonuses.append(bonus_row.get_bonus())

        return bonuses

    def add_bonus(self):
        self.add_bonus_row({}, notify_change=True)

    def add_bonus_row(self, bonus, notify_change):
        bonus_row = BonusRow(
            self.rows_frame,
            change_command=self.change_command,
            remove_command=self.remove_bonus_row,
        )
        bonus_row.set_bonus(bonus)
        bonus_row.bind_mousewheel(self.scroll_with_mousewheel)
        self.bonus_rows.append(bonus_row)
        self.relayout_rows()

        if notify_change:
            self.change_command()

    def remove_bonus_row(self, bonus_row):
        if bonus_row not in self.bonus_rows:
            return

        self.bonus_rows.remove(bonus_row)
        bonus_row.destroy()
        self.relayout_rows()
        self.change_command()

    def relayout_rows(self):
        for row_index, bonus_row in enumerate(self.bonus_rows):
            bonus_row.grid(
                row=row_index,
                column=0,
                sticky="ew",
                padx=8,
                pady=5,
            )

        self.rows_frame.grid_columnconfigure(0, weight=1)

    def update_scroll_region(self, event):
        self.scroll_area.configure(
            scrollregion=self.scroll_area.bbox("all")
        )

    def resize_rows_frame(self, event):
        self.scroll_area.itemconfigure(
            self.rows_window,
            width=event.width,
        )

    def scroll_with_mousewheel(self, event):
        if event.delta > 0:
            self.scroll_area.yview_scroll(-3, "units")
        elif event.delta < 0:
            self.scroll_area.yview_scroll(3, "units")

        return "break"
