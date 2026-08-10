import tkinter as tk

from mage_maker.sections.development.models import (
    DEVELOPMENT_SCHEMA_OPTIONS,
    normalize_development_schema,
)
from mage_maker.ui.theme import (
    APP_BACKGROUND,
    BORDER,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_LIGHT,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedSelect, SoftButton


class DevelopmentStrategyDialog(tk.Toplevel):
    def __init__(self, parent, person_name=""):
        super().__init__(parent)
        self.result = None
        self.strategy_value = tk.StringVar(
            value=DEVELOPMENT_SCHEMA_OPTIONS[0]
        )
        self.title("Choose Development Strategy")
        self.geometry("520x300")
        self.minsize(480, 280)
        self.configure(bg=APP_BACKGROUND)
        self.transient(parent)
        self.grab_set()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = tk.Frame(self, bg=PRIMARY_DARK, height=62)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)
        header.grid_columnconfigure(0, weight=1)
        heading = tk.Label(
            header,
            text="Choose Development Strategy",
            bg=PRIMARY_DARK,
            fg=TEXT_LIGHT,
            font=app_font(16, "bold"),
            anchor="w",
            padx=20,
        )
        heading.grid(row=0, column=0, sticky="nsew")

        card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        card.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=20,
            pady=20,
        )
        card.grid_columnconfigure(0, weight=1)

        prompt_name = str(person_name or "this magician").strip()
        prompt = tk.Label(
            card,
            text=f"Select the strategy to register for {prompt_name}.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            anchor="w",
            justify="left",
            wraplength=430,
        )
        prompt.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=16,
            pady=(16, 10),
        )
        self.strategy_select = RoundedSelect(
            card,
            self.strategy_value,
            DEVELOPMENT_SCHEMA_OPTIONS,
            background=SURFACE,
            width=420,
            height=42,
            font=app_font(11),
        )
        self.strategy_select.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=16,
        )

        buttons = tk.Frame(card, bg=SURFACE)
        buttons.grid(
            row=2,
            column=0,
            sticky="e",
            padx=16,
            pady=16,
        )
        cancel_button = SoftButton(
            buttons,
            text="Cancel",
            command=self.cancel,
            background=SURFACE,
            width=92,
            height=38,
        )
        cancel_button.pack(side="left", padx=(0, 6))
        select_button = SoftButton(
            buttons,
            text="Use strategy",
            command=self.select_strategy,
            background=SURFACE,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=126,
            height=38,
        )
        select_button.pack(side="left")

        self.bind("<Escape>", self.cancel)
        self.bind("<Return>", self.select_strategy)
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.after(50, self.strategy_select.focus_set)

    def select_strategy(self, event=None):
        self.result = normalize_development_schema(
            self.strategy_value.get()
        )
        self.destroy()

    def cancel(self, event=None):
        self.result = None
        self.destroy()
