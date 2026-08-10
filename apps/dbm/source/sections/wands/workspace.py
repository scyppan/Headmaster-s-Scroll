import tkinter as tk
from functools import partial

from runtime_theme import bind_theme
from sections.wands.wand_cores.page import WandCoresPage
from sections.wands.wand_makers.page import WandMakersPage
from sections.wands.wand_qualities.page import WandQualitiesPage
from sections.wands.wand_woods.page import WandWoodsPage
from sections.wands.wands.page import WandsPage
from shared.widgets import SoftButton
from theme import APP_BACKGROUND, PRIMARY_LIGHT


WAND_VIEW_DEFINITIONS = (
    ("wands", "Wands", "wands", WandsPage),
    ("woods", "Woods", "wand_woods", WandWoodsPage),
    ("cores", "Cores", "wand_cores", WandCoresPage),
    ("qualities", "Qualities", "wand_qualities", WandQualitiesPage),
    ("makers", "Makers", "wand_makers", WandMakersPage),
)


class WandWorkspacePage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.active_view_key = None
        self.pages = {}
        self.navigation_buttons = {}

        for view_key, view_title, storage_key, page_class in WAND_VIEW_DEFINITIONS:
            self.database.ensure_container(storage_key, "collection")

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.navigation = tk.Frame(
            self,
            bg=PRIMARY_LIGHT,
        )
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
            page_class,
        ) in enumerate(WAND_VIEW_DEFINITIONS):
            view_button = SoftButton(
                self.navigation,
                text=view_title,
                command=partial(self.show_view, view_key),
                background=PRIMARY_LIGHT,
                width=94,
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

        self.show_view("wands")

    def show_view(self, view_key):
        if view_key == self.active_view_key:
            return True

        if not self.can_leave_active_view():
            return False

        if view_key not in self.pages:
            page_class = self.get_page_class(view_key)
            page = page_class(self.page_container, self.database)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[view_key] = page

        page = self.pages[view_key]
        on_show = getattr(page, "on_show", None)

        if on_show is not None:
            on_show()

        page.tkraise()
        self.active_view_key = view_key
        self.update_navigation()

        return True

    def get_page_class(self, view_key):
        for candidate_key, view_title, storage_key, page_class in WAND_VIEW_DEFINITIONS:
            if candidate_key == view_key:
                return page_class

        raise KeyError(f"Unknown wand view: {view_key}")

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

        active_page = self.pages[self.active_view_key]
        can_leave = getattr(active_page, "can_leave", None)

        if can_leave is None:
            return True

        return can_leave()

    def on_show(self):
        if self.active_view_key is None:
            return

        active_page = self.pages[self.active_view_key]
        on_show = getattr(active_page, "on_show", None)

        if on_show is not None:
            on_show()

    def can_leave(self):
        return self.can_leave_active_view()
