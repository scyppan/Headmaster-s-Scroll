import tkinter as tk
from functools import partial

from headmasters_scroll.effects import (
    IN_FLIGHT_EFFECT_TARGETS,
    normalize_in_flight_effect,
)
from runtime_theme import bind_theme
from shared.widgets.bonus_editor import BonusEditor, BonusRow
from shared.widgets.controls import RoundedEntry, RoundedSelect, SoftButton
from theme import BORDER, PRIMARY, SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class InFlightEffectRow(tk.Frame):
    def __init__(self, parent, change_command, remove_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.change_command = change_command
        self.remove_command = remove_command
        self.loading_effect = False
        self.grid_columnconfigure(0, weight=1)

        self.target_value = tk.StringVar()
        self.target_value.trace_add("write", self.handle_change)
        self.target_box = RoundedSelect(
            self,
            variable=self.target_value,
            values=tuple(IN_FLIGHT_EFFECT_TARGETS),
            background=SURFACE,
            height=30,
            font=app_font(9),
            placeholder="Effect",
        )
        self.target_box.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        self.amount_value = tk.StringVar()
        self.amount_value.trace_add("write", self.handle_change)
        self.amount_entry = RoundedEntry(
            self,
            textvariable=self.amount_value,
            background=SURFACE,
            width=62,
            height=30,
            justify="center",
            font=app_font(9),
        )
        self.amount_entry.grid(row=0, column=1, sticky="ew", padx=3)

        self.remove_button = SoftButton(
            self,
            text="×",
            command=partial(self.remove_command, self),
            background=SURFACE,
            width=28,
            height=30,
            padx=0,
        )
        self.remove_button.grid(row=0, column=2, padx=(3, 0))

    def set_effect(self, effect):
        value = normalize_in_flight_effect(
            effect if isinstance(effect, dict) else {}
        )
        self.loading_effect = True
        self.target_value.set(value.get("target", ""))
        amount = value.get("amount")
        self.amount_value.set("" if amount is None else str(amount))
        self.loading_effect = False

    def get_effect(self):
        amount_text = self.amount_value.get().strip()
        try:
            amount = int(amount_text) if amount_text else None
        except ValueError as error:
            raise ValueError(
                "In-flight effect amount must be a whole number."
            ) from error
        return normalize_in_flight_effect({
            "target": self.target_value.get().strip(),
            "amount": amount,
        })

    def is_empty(self):
        return not (
            self.target_value.get().strip()
            or self.amount_value.get().strip()
        )

    def handle_change(self, *arguments):
        if not self.loading_effect:
            self.change_command()

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)
        for widget in (self.target_box, self.amount_entry, self.remove_button):
            if hasattr(widget, "bind_mousewheel"):
                widget.bind_mousewheel(command)
            elif hasattr(widget, "bind_input"):
                widget.bind_input("<MouseWheel>", command)
            else:
                widget.bind("<MouseWheel>", command)


class InFlightEffectEditor(tk.Frame):
    def __init__(self, parent, change_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.change_command = change_command
        self.effect_rows = []
        self.grid_columnconfigure(0, weight=1)

        heading_bar = tk.Frame(self, bg=SURFACE)
        heading_bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        heading_bar.grid_columnconfigure(0, weight=1)
        bind_theme(heading_bar, background="SURFACE")
        heading = tk.Label(
            heading_bar,
            text="In-flight effects",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew")
        bind_theme(heading, background="SURFACE", foreground="TEXT_DARK")
        add_button = SoftButton(
            heading_bar,
            text="+",
            command=self.add_effect,
            background=SURFACE,
            fill=PRIMARY,
            fill_role="PRIMARY",
            hover_fill_role="PRIMARY_DARK",
            width=36,
            height=34,
            padx=0,
        )
        add_button.grid(row=0, column=1)

        headers = tk.Frame(self, bg=SURFACE)
        headers.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(4, 2))
        headers.grid_columnconfigure(0, weight=1)
        bind_theme(headers, background="SURFACE")
        for column, text in enumerate(("While flying", "+/−")):
            label = tk.Label(
                headers,
                text=text,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(8),
                anchor="w",
            )
            label.grid(row=0, column=column, sticky="ew", padx=3)
            bind_theme(label, background="SURFACE", foreground="TEXT_MUTED")

        self.scroll_area = tk.Canvas(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
            height=104,
        )
        self.scroll_area.grid(row=2, column=0, sticky="new")
        self.scrollbar = tk.Scrollbar(
            self, orient="vertical", command=self.scroll_area.yview
        )
        self.scrollbar.grid(row=2, column=1, sticky="ns")
        self.scroll_area.configure(yscrollcommand=self.scrollbar.set)
        bind_theme(
            self.scroll_area,
            background="SURFACE",
            highlightbackground="BORDER",
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

    def set_effects(self, effects):
        for row in self.effect_rows:
            row.destroy()
        self.effect_rows = []
        for effect in effects or []:
            normalized = normalize_in_flight_effect(effect)
            if normalized.get("target") in IN_FLIGHT_EFFECT_TARGETS:
                self.add_effect_row(normalized, notify_change=False)

    def get_effects(self):
        return [
            row.get_effect() for row in self.effect_rows if not row.is_empty()
        ]

    def add_effect(self):
        self.add_effect_row({}, notify_change=True)

    def add_effect_row(self, effect, notify_change):
        row = InFlightEffectRow(
            self.rows_frame, self.change_command, self.remove_effect_row
        )
        row.set_effect(effect)
        row.bind_mousewheel(self.scroll_with_mousewheel)
        self.effect_rows.append(row)
        self.relayout_rows()
        if notify_change:
            self.change_command()

    def remove_effect_row(self, row):
        if row in self.effect_rows:
            self.effect_rows.remove(row)
            row.destroy()
            self.relayout_rows()
            self.change_command()

    def relayout_rows(self):
        for index, row in enumerate(self.effect_rows):
            row.grid(row=index, column=0, sticky="ew", padx=3, pady=2)
        self.rows_frame.grid_columnconfigure(0, weight=1)

    def update_scroll_region(self, event=None):
        self.scroll_area.configure(scrollregion=self.scroll_area.bbox("all"))

    def resize_rows_frame(self, event):
        self.scroll_area.itemconfigure(self.rows_window, width=event.width)

    def scroll_with_mousewheel(self, event):
        if event.delta:
            self.scroll_area.yview_scroll(
                -1 if event.delta > 0 else 1, "units"
            )
        return "break"


__all__ = (
    "BonusEditor",
    "BonusRow",
    "InFlightEffectEditor",
    "InFlightEffectRow",
)
