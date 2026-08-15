import tkinter as tk
from functools import partial

from headmasters_scroll.effects import (
    BONUS_ACTIVATION_MODES,
    BONUS_CATEGORIES,
    BONUS_TARGETS,
    TARGET_SCOPE_LABELS,
    TARGET_SCOPES,
    normalize_bonus,
)
from runtime_theme import bind_theme
from shared.widgets.controls import RoundedEntry, RoundedSelect, SoftButton
from theme import BORDER, PRIMARY, SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class BonusRow(tk.Frame):
    def __init__(self, parent, change_command, remove_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.change_command = change_command
        self.remove_command = remove_command
        self.loading_bonus = False

        weights = (0, 1, 0, 0, 0, 0, 0)
        for column, weight in enumerate(weights):
            self.grid_columnconfigure(column, weight=weight)

        self.type_value = tk.StringVar()
        self.type_value.trace_add("write", self.handle_category_change)
        self.type_box = RoundedSelect(
            self,
            variable=self.type_value,
            values=("", *BONUS_CATEGORIES),
            background=SURFACE,
            width=92,
            height=30,
            font=app_font(9),
            placeholder="Category",
        )
        self.type_box.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.target_value = tk.StringVar()
        self.target_value.trace_add("write", self.handle_change)
        self.target_box = RoundedSelect(
            self,
            variable=self.target_value,
            values=(),
            background=SURFACE,
            width=140,
            height=30,
            font=app_font(9),
            placeholder="Select value",
        )
        self.target_box.grid(row=0, column=1, sticky="ew", padx=3)

        self.amount_value = tk.StringVar()
        self.amount_value.trace_add("write", self.handle_change)
        self.amount_entry = RoundedEntry(
            self,
            textvariable=self.amount_value,
            background=SURFACE,
            width=42,
            height=30,
            justify="center",
            font=app_font(9),
        )
        self.amount_entry.grid(row=0, column=2, sticky="ew", padx=3)

        self.mode_value = tk.StringVar(value="Passive")
        self.mode_value.trace_add("write", self.handle_mode_change)
        self.mode_box = RoundedSelect(
            self,
            variable=self.mode_value,
            values=("Passive", "Clickable"),
            background=SURFACE,
            width=80,
            height=30,
            font=app_font(9),
            placeholder="Use",
        )
        self.mode_box.grid(row=0, column=3, sticky="ew", padx=3)

        self.scope_value = tk.StringVar(value=TARGET_SCOPE_LABELS["self"])
        self.scope_value.trace_add("write", self.handle_change)
        self.scope_box = RoundedSelect(
            self,
            variable=self.scope_value,
            values=tuple(TARGET_SCOPE_LABELS[value] for value in TARGET_SCOPES),
            background=SURFACE,
            width=76,
            height=30,
            font=app_font(9),
            placeholder="Affects",
        )
        self.scope_box.grid(row=0, column=4, sticky="ew", padx=3)

        self.depletable_value = tk.BooleanVar(value=False)
        self.depletable_button = tk.Checkbutton(
            self,
            variable=self.depletable_value,
            command=self.handle_change,
            text="Deplete",
            bg=SURFACE,
            fg=TEXT_DARK,
            activebackground=SURFACE,
            selectcolor=SURFACE,
            font=app_font(7),
            padx=0,
        )
        self.depletable_button.grid(row=0, column=5, sticky="w", padx=3)
        bind_theme(
            self.depletable_button,
            background="SURFACE",
            foreground="TEXT_DARK",
            activebackground="SURFACE",
            selectcolor="SURFACE",
        )

        self.remove_button = SoftButton(
            self,
            text="×",
            command=partial(self.remove_command, self),
            background=SURFACE,
            width=28,
            height=30,
            padx=0,
        )
        self.remove_button.grid(row=0, column=6, padx=(3, 0))

    def set_bonus(self, bonus):
        value = normalize_bonus(bonus if isinstance(bonus, dict) else {})
        self.loading_bonus = True
        self.type_value.set(value.get("type", ""))
        self.refresh_target_values(clear_invalid=False)
        self.target_value.set(value.get("target", ""))
        amount = value.get("amount")
        self.amount_value.set("" if amount is None else str(amount))
        mode = value.get("activation_mode", "passive")
        self.mode_value.set("Clickable" if mode == "click" else "Passive")
        scope = value.get("target_scope", "self")
        self.scope_value.set(TARGET_SCOPE_LABELS.get(scope, "Self"))
        self.depletable_value.set(bool(value.get("depletable", False)))
        self.refresh_depletable_state()
        self.loading_bonus = False

    def get_bonus(self):
        amount_text = self.amount_value.get().strip()
        try:
            amount = int(amount_text) if amount_text else None
        except ValueError as error:
            raise ValueError("Bonus amount must be a whole number.") from error

        scope_by_label = {
            label: value for value, label in TARGET_SCOPE_LABELS.items()
        }
        return normalize_bonus({
            "type": self.type_value.get().strip(),
            "target": self.target_value.get().strip(),
            "amount": amount,
            "activation_mode": (
                "click" if self.mode_value.get() == "Clickable" else "passive"
            ),
            "target_scope": scope_by_label.get(
                self.scope_value.get(), "self"
            ),
            "depletable": bool(self.depletable_value.get()),
        })

    def is_empty(self):
        return not (
            self.type_value.get().strip()
            or self.target_value.get().strip()
            or self.amount_value.get().strip()
        )

    def refresh_target_values(self, clear_invalid=True):
        values = BONUS_TARGETS.get(self.type_value.get(), ())
        self.target_box.set_values(values)
        if clear_invalid and self.target_value.get() not in values:
            self.target_value.set("")

    def refresh_depletable_state(self):
        clickable = self.mode_value.get() == "Clickable"
        self.depletable_button.configure(state="normal" if clickable else "disabled")
        if not clickable:
            self.depletable_value.set(False)

    def handle_category_change(self, *arguments):
        self.refresh_target_values()
        self.handle_change()

    def handle_mode_change(self, *arguments):
        self.refresh_depletable_state()
        self.handle_change()

    def handle_change(self, *arguments):
        if not self.loading_bonus:
            self.change_command()

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)
        for widget in (
            self.type_box,
            self.target_box,
            self.amount_entry,
            self.mode_box,
            self.scope_box,
            self.depletable_button,
            self.remove_button,
        ):
            if hasattr(widget, "bind_mousewheel"):
                widget.bind_mousewheel(command)
            elif hasattr(widget, "bind_input"):
                widget.bind_input("<MouseWheel>", command)
            else:
                widget.bind("<MouseWheel>", command)


class BonusEditor(tk.Frame):
    HEADERS = ("Category", "Selection", "+/−", "Use", "Affects", "Deplete")
    WEIGHTS = (2, 3, 1, 2, 2, 1)

    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.change_command = change_command
        self.bonus_rows = []
        self.grid_columnconfigure(0, weight=1)

        heading_bar = tk.Frame(self, bg=SURFACE)
        heading_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        heading_bar.grid_columnconfigure(0, weight=1)
        bind_theme(heading_bar, background="SURFACE")
        heading = tk.Label(
            heading_bar, text="Bonuses", bg=SURFACE, fg=TEXT_DARK,
            font=app_font(10), anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        bind_theme(heading, background="SURFACE", foreground="TEXT_DARK")
        add_button = SoftButton(
            heading_bar, text="+", command=self.add_bonus,
            background=SURFACE, fill=PRIMARY, fill_role="PRIMARY",
            hover_fill_role="PRIMARY_DARK", width=36, height=34, padx=0,
        )
        add_button.grid(row=0, column=1)

        headers = tk.Frame(self, bg=SURFACE)
        headers.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        bind_theme(headers, background="SURFACE")
        for column, (text, weight) in enumerate(zip(self.HEADERS, self.WEIGHTS)):
            headers.grid_columnconfigure(column, weight=weight)
            label = tk.Label(
                headers, text=text, bg=SURFACE, fg=TEXT_MUTED,
                font=app_font(8), anchor="w",
            )
            label.grid(row=0, column=column, sticky="ew", padx=3)
            bind_theme(label, background="SURFACE", foreground="TEXT_MUTED")

        self.scroll_area = tk.Canvas(
            self, bg=SURFACE, highlightbackground=BORDER,
            highlightthickness=1, height=104,
        )
        self.scroll_area.grid(row=2, column=0, sticky="new")
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.scroll_area.yview,
        )
        self.scrollbar.grid(row=2, column=1, sticky="ns")
        self.scroll_area.configure(yscrollcommand=self.scrollbar.set)
        bind_theme(
            self.scroll_area, background="SURFACE", highlightbackground="BORDER"
        )
        self.rows_frame = tk.Frame(self.scroll_area, bg=SURFACE)
        bind_theme(self.rows_frame, background="SURFACE")
        self.rows_window = self.scroll_area.create_window(
            (0, 0), window=self.rows_frame, anchor="nw"
        )
        self.scroll_area.bind("<Configure>", self.resize_rows_frame)
        self.scroll_area.bind("<MouseWheel>", self.scroll_with_mousewheel)
        self.rows_frame.bind("<Configure>", self.update_scroll_region)
        self.rows_frame.bind("<MouseWheel>", self.scroll_with_mousewheel)

    def set_bonuses(self, bonuses):
        for row in self.bonus_rows:
            row.destroy()
        self.bonus_rows = []
        for bonus in bonuses or []:
            self.add_bonus_row(bonus, notify_change=False)

    def get_bonuses(self):
        return [row.get_bonus() for row in self.bonus_rows if not row.is_empty()]

    def add_bonus(self):
        self.add_bonus_row({}, notify_change=True)

    def add_bonus_row(self, bonus, notify_change):
        row = BonusRow(
            self.rows_frame, self.change_command, self.remove_bonus_row
        )
        row.set_bonus(bonus)
        row.bind_mousewheel(self.scroll_with_mousewheel)
        self.bonus_rows.append(row)
        self.relayout_rows()
        if notify_change:
            self.change_command()

    def remove_bonus_row(self, row):
        if row in self.bonus_rows:
            self.bonus_rows.remove(row)
            row.destroy()
            self.relayout_rows()
            self.change_command()

    def relayout_rows(self):
        for index, row in enumerate(self.bonus_rows):
            row.grid(row=index, column=0, sticky="ew", padx=3, pady=2)
        self.rows_frame.grid_columnconfigure(0, weight=1)

    def update_scroll_region(self, event=None):
        self.scroll_area.configure(scrollregion=self.scroll_area.bbox("all"))

    def resize_rows_frame(self, event):
        self.scroll_area.itemconfigure(self.rows_window, width=event.width)

    def scroll_with_mousewheel(self, event):
        if event.delta:
            self.scroll_area.yview_scroll(-1 if event.delta > 0 else 1, "units")
        return "break"
