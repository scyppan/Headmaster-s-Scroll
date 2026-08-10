import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets.controls import SoftButton
from theme import (
    app_font,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    DELETE_HOVER,
    DELETE_SOFT,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_LIGHT,
    TEXT_DARK,
)


class RecordToolbar(tk.Frame):
    def __init__(
        self,
        parent,
        title,
        new_command,
        delete_command,
        revert_command,
        save_command,
    ):
        super().__init__(parent, bg=PRIMARY_LIGHT, height=64)
        bind_theme(self, background="PRIMARY_LIGHT")

        self.grid_propagate(False)
        self.pack_propagate(False)

        self.title_label = tk.Label(
            self,
            text=title,
            bg=PRIMARY_LIGHT,
            fg=TEXT_DARK,
            font=app_font(17),
            padx=20,
        )
        self.title_label.pack(side="left", fill="y")
        bind_theme(
            self.title_label,
            background="PRIMARY_LIGHT",
            foreground="TEXT_DARK",
        )

        self.save_button = SoftButton(
            self,
            text="Save",
            command=save_command,
            background=PRIMARY_LIGHT,
            fill=PRIMARY,
            hover_fill=PRIMARY_DARK,
            background_role="PRIMARY_LIGHT",
            fill_role="PRIMARY",
            hover_fill_role="PRIMARY_DARK",
            width=92,
        )
        self.save_button.pack(side="right", padx=(4, 16), pady=12)

        self.revert_button = SoftButton(
            self,
            text="Revert",
            command=revert_command,
            background=PRIMARY_LIGHT,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            background_role="PRIMARY_LIGHT",
            width=92,
        )
        self.revert_button.pack(side="right", padx=4, pady=12)

        self.delete_button = SoftButton(
            self,
            text="Delete",
            command=delete_command,
            background=PRIMARY_LIGHT,
            fill=DELETE_SOFT,
            hover_fill=DELETE_HOVER,
            background_role="PRIMARY_LIGHT",
            fill_role="DELETE_SOFT",
            hover_fill_role="DELETE_HOVER",
            width=92,
        )
        self.delete_button.pack(side="right", padx=4, pady=12)

        self.new_button = SoftButton(
            self,
            text="New",
            command=new_command,
            background=PRIMARY_LIGHT,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            background_role="PRIMARY_LIGHT",
            width=82,
        )
        self.new_button.pack(side="right", padx=4, pady=12)

        self.set_record_state(dirty=False, has_record=False)

    def set_record_state(self, dirty, has_record):
        self.save_button.set_enabled(dirty)
        self.revert_button.set_enabled(dirty)
        self.delete_button.set_enabled(has_record)
