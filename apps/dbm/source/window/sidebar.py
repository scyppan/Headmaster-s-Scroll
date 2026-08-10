import tkinter as tk
from functools import partial

from runtime_theme import bind_theme
from shared.widgets import SoftButton
from theme import (
    app_font,
    PRIMARY_LIGHT,
    SIDEBAR_BACKGROUND,
    SIDEBAR_TILE,
    SIDEBAR_TILE_HOVER,
    SIDEBAR_TILE_SELECTED,
    TEXT_DARK,
    TEXT_LIGHT,
)


class Sidebar(tk.Frame):
    def __init__(
        self,
        parent,
        sections,
        section_command,
        sidebar_width=250,
    ):
        super().__init__(
            parent,
            width=sidebar_width,
            bg=SIDEBAR_BACKGROUND,
        )
        bind_theme(self, background="SIDEBAR_BACKGROUND")

        self.sections = sections
        self.section_command = section_command
        self.tile_buttons = {}

        self.grid_propagate(False)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.title_label = tk.Label(
            self,
            text="CHARMS CHECK",
            bg=SIDEBAR_BACKGROUND,
            fg=TEXT_LIGHT,
            font=app_font(18),
            pady=20,
        )
        self.title_label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title_label,
            background="SIDEBAR_BACKGROUND",
            foreground="TEXT_LIGHT",
        )
        self.title_label.bind("<MouseWheel>", self.scroll_with_mousewheel)

        self.scroll_area = tk.Canvas(
            self,
            bg=SIDEBAR_BACKGROUND,
            highlightthickness=0,
        )
        self.scroll_area.grid(row=1, column=0, sticky="nsew")
        bind_theme(self.scroll_area, background="SIDEBAR_BACKGROUND")
        self.scroll_area.bind("<MouseWheel>", self.scroll_with_mousewheel)

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.scroll_area.yview,
        )
        self.scrollbar.grid(row=1, column=1, sticky="ns")

        self.scroll_area.configure(
            yscrollcommand=self.scrollbar.set,
        )

        self.tile_container = tk.Frame(
            self.scroll_area,
            bg=SIDEBAR_BACKGROUND,
        )
        self.tile_container.bind(
            "<MouseWheel>",
            self.scroll_with_mousewheel,
        )
        bind_theme(self.tile_container, background="SIDEBAR_BACKGROUND")

        self.tile_window = self.scroll_area.create_window(
            (0, 0),
            window=self.tile_container,
            anchor="nw",
        )

        self.tile_container.bind(
            "<Configure>",
            self.update_scroll_region,
        )
        self.scroll_area.bind(
            "<Configure>",
            self.resize_tile_container,
        )

        for section in self.sections:
            tile = SoftButton(
                self.tile_container,
                text=section.title,
                command=partial(self.select_section, section.key),
                background=SIDEBAR_BACKGROUND,
                fill=SIDEBAR_TILE,
                hover_fill=SIDEBAR_TILE_HOVER,
                foreground=TEXT_LIGHT,
                background_role="SIDEBAR_BACKGROUND",
                fill_role="SIDEBAR_TILE",
                hover_fill_role="SIDEBAR_TILE_HOVER",
                foreground_role="TEXT_LIGHT",
                height=46,
                radius=10,
                anchor="w",
                font=app_font(11),
                padx=18,
            )
            tile.pack(fill="x", padx=12, pady=5)
            tile.bind_mousewheel(self.scroll_with_mousewheel)
            self.tile_buttons[section.key] = tile

        self.select_section(self.sections[0].key)

    def select_section(self, section_key):
        if self.section_command(section_key) is False:
            return False

        for tile_key, tile_button in self.tile_buttons.items():
            if tile_key == section_key:
                tile_button.set_theme_roles(
                    "SIDEBAR_TILE_SELECTED",
                    "PRIMARY_LIGHT",
                    "TEXT_DARK",
                )
            else:
                tile_button.set_theme_roles(
                    "SIDEBAR_TILE",
                    "SIDEBAR_TILE_HOVER",
                    "TEXT_LIGHT",
                )

        return True

    def update_scroll_region(self, event):
        self.scroll_area.configure(
            scrollregion=self.scroll_area.bbox("all")
        )

    def resize_tile_container(self, event):
        self.scroll_area.itemconfigure(
            self.tile_window,
            width=event.width,
        )

    def scroll_with_mousewheel(self, event):
        if event.delta > 0:
            self.scroll_area.yview_scroll(-3, "units")
        elif event.delta < 0:
            self.scroll_area.yview_scroll(3, "units")

        return "break"
