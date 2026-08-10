import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets.controls import RoundedText
from theme import SURFACE, TEXT_DARK, app_font


class MultilineField(tk.Frame):
    def __init__(self, parent, label_text, change_command, height):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.label = tk.Label(
            self,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.control = RoundedText(
            self,
            background=SURFACE,
            height=height,
        )
        self.control.grid(row=1, column=0, sticky="nsew")
        self.text = self.control.text
        self.text.bind("<<Modified>>", self.handle_modified)

    def get_value(self):
        return self.text.get("1.0", "end-1c").strip()

    def set_value(self, value):
        self.text.delete("1.0", "end")
        self.text.insert("1.0", value or "")
        self.text.edit_modified(False)

    def handle_modified(self, event):
        if not self.text.edit_modified():
            return

        self.text.edit_modified(False)
        self.change_command()
