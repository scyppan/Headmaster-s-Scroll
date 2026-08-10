import tkinter as tk
from functools import partial

from runtime_theme import bind_theme
from sections.nature_and_alchemy.potions.editor_page import (
    AlchemyFormulaPage,
)
from sections.nature_and_alchemy.preparations.page import PreparationsPage
from shared.widgets import SoftButton
from theme import APP_BACKGROUND, PRIMARY_LIGHT


ALCHEMY_VIEW_DEFINITIONS = (
    ("potions", "Potions", "potions", "potion"),
    (
        "preparations",
        "Preparations",
        "preparations",
        "preparation",
    ),
)


class PotionsPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.active_view_key = None
        self.pages = {}
        self.navigation_buttons = {}

        for view_key, view_title, storage_key, record_label in (
            ALCHEMY_VIEW_DEFINITIONS
        ):
            self.database.ensure_container(storage_key, "collection")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.navigation = tk.Frame(self, bg=PRIMARY_LIGHT)
        self.navigation.grid(
            row=0,
            column=0,
            sticky="ew",
        )
        bind_theme(self.navigation, background="PRIMARY_LIGHT")

        for index, (
            view_key,
            view_title,
            storage_key,
            record_label,
        ) in enumerate(ALCHEMY_VIEW_DEFINITIONS):
            view_button = SoftButton(
                self.navigation,
                text=view_title,
                command=partial(self.show_view, view_key),
                background=PRIMARY_LIGHT,
                width=116,
                height=34,
                background_role="PRIMARY_LIGHT",
            )
            view_button.pack(
                side="left",
                padx=((25 if index == 0 else 3), 3),
                pady=8,
            )
            self.navigation_buttons[view_key] = view_button

        self.page_container = tk.Frame(self, bg=APP_BACKGROUND)
        self.page_container.grid(row=1, column=0, sticky="nsew")
        self.page_container.grid_rowconfigure(0, weight=1)
        self.page_container.grid_columnconfigure(0, weight=1)
        bind_theme(self.page_container, background="APP_BACKGROUND")

        self.show_view("potions")

    def show_view(self, view_key):
        if view_key == self.active_view_key:
            return True

        if not self.can_leave_active_view():
            return False

        if view_key not in self.pages:
            view_definition = self.get_view_definition(view_key)

            if view_key == "preparations":
                page = PreparationsPage(
                    self.page_container,
                    self.database,
                )
            else:
                page = AlchemyFormulaPage(
                    self.page_container,
                    self.database,
                    view_definition[2],
                    view_definition[1],
                    view_definition[3],
                )
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[view_key] = page

        page = self.pages[view_key]
        page.on_show()
        page.tkraise()
        self.active_view_key = view_key
        self.update_navigation()

        return True

    def get_view_definition(self, view_key):
        for view_definition in ALCHEMY_VIEW_DEFINITIONS:
            if view_definition[0] == view_key:
                return view_definition

        raise KeyError(f"Unknown alchemy view: {view_key}")

    def update_navigation(self):
        for view_key, view_button in self.navigation_buttons.items():
            if view_key == self.active_view_key:
                view_button.set_theme_roles(
                    "PRIMARY",
                    "PRIMARY_DARK",
                    "TEXT_DARK",
                )
            else:
                view_button.set_theme_roles(
                    "BUTTON_SOFT",
                    "BUTTON_SOFT_HOVER",
                    "TEXT_DARK",
                )

    def can_leave_active_view(self):
        if self.active_view_key is None:
            return True

        return self.pages[self.active_view_key].can_leave()

    def on_show(self):
        if self.active_view_key is None:
            return

        self.pages[self.active_view_key].on_show()

    def can_leave(self):
        return self.can_leave_active_view()
