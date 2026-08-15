import tkinter as tk

from headmasters_scroll.effects import (
    TARGET_SCOPE_LABELS,
    TARGET_SCOPES,
    normalize_target_scope,
)
from runtime_theme import bind_theme
from shared.widgets.controls import RoundedSelect
from theme import SURFACE, TEXT_DARK, app_font


class TargetScopeField(tk.Frame):
    def __init__(self, parent, change_command, label_text="Target"):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")
        self.grid_columnconfigure(0, weight=1)

        self.value = tk.StringVar(value=TARGET_SCOPE_LABELS["none"])
        self.value.trace_add("write", change_command)

        label = tk.Label(
            self,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        bind_theme(label, background="SURFACE", foreground="TEXT_DARK")

        self.select = RoundedSelect(
            self,
            variable=self.value,
            values=tuple(TARGET_SCOPE_LABELS[value] for value in TARGET_SCOPES),
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder="Select target",
        )
        self.select.grid(row=1, column=0, sticky="ew")

    def set_value(self, value):
        scope = normalize_target_scope(value)
        self.value.set(TARGET_SCOPE_LABELS[scope])

    def get_value(self):
        return normalize_target_scope(self.value.get())
