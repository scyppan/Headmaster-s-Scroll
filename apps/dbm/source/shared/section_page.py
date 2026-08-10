import tkinter as tk
from functools import partial

from runtime_theme import bind_theme
from shared.widgets import SoftButton
from theme import (
    app_font,
    APP_BACKGROUND,
    BORDER,
    PRIMARY,
    PRIMARY_LIGHT,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
)


class StandardSectionPage(tk.Frame):
    section_title = "Section"
    menu_names = ("Overview",)

    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.top_menu = tk.Frame(
            self,
            bg=PRIMARY_LIGHT,
            height=55,
        )
        self.top_menu.grid(row=0, column=0, sticky="ew")
        bind_theme(self.top_menu, background="PRIMARY_LIGHT")
        self.top_menu.grid_propagate(False)

        for menu_name in self.menu_names:
            menu_button = SoftButton(
                self.top_menu,
                text=menu_name,
                command=partial(self.show_menu, menu_name),
                background=PRIMARY_LIGHT,
                fill=PRIMARY_LIGHT,
                hover_fill=PRIMARY,
                background_role="PRIMARY_LIGHT",
                fill_role="PRIMARY_LIGHT",
                hover_fill_role="PRIMARY",
                font=app_font(10),
                height=38,
            )
            menu_button.pack(side="left", padx=(8, 0), pady=8)

        self.content_area = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.content_area.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=25,
            pady=25,
        )
        bind_theme(
            self.content_area,
            background="SURFACE",
            highlightbackground="BORDER",
        )
        self.content_area.grid_rowconfigure(1, weight=1)
        self.content_area.grid_columnconfigure(0, weight=1)

        self.page_title = tk.Label(
            self.content_area,
            text=self.section_title,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(26),
            anchor="w",
        )
        self.page_title.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=30,
            pady=(30, 10),
        )
        bind_theme(
            self.page_title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.page_content = tk.Label(
            self.content_area,
            text=f"The {self.section_title} section is ready to be built.",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(13),
            justify="left",
            anchor="nw",
        )
        self.page_content.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=30,
            pady=10,
        )
        bind_theme(
            self.page_content,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.status_bar = tk.Label(
            self,
            text="Ready",
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            padx=12,
            pady=7,
        )
        self.status_bar.grid(row=2, column=0, sticky="ew")
        bind_theme(
            self.status_bar,
            background="SURFACE_MUTED",
            foreground="TEXT_MUTED",
        )

    def show_menu(self, menu_name):
        self.page_content.config(
            text=f"The {menu_name} view for {self.section_title} is selected."
        )
        self.status_bar.config(text=f"Selected {menu_name}")
