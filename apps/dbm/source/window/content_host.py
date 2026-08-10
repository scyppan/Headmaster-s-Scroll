import tkinter as tk

from runtime_theme import bind_theme
from theme import APP_BACKGROUND


class ContentHost(tk.Frame):
    def __init__(self, parent, sections, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.section_definitions = {
            section.key: section for section in sections
        }
        self.section_pages = {}
        self.active_section_key = None

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def show_section(self, section_key):
        if section_key not in self.section_definitions:
            raise KeyError(f"Unknown section: {section_key}")

        if section_key == self.active_section_key:
            return True

        if not self.can_leave_active_section():
            return False

        if section_key not in self.section_pages:
            section_definition = self.section_definitions[section_key]
            section_page = section_definition.page_class(
                self,
                self.database,
            )
            section_page.grid(row=0, column=0, sticky="nsew")
            self.section_pages[section_key] = section_page

        section_page = self.section_pages[section_key]
        on_show = getattr(section_page, "on_show", None)

        if on_show is not None:
            on_show()

        section_page.tkraise()
        self.active_section_key = section_key

        return True

    def can_leave_active_section(self):
        if self.active_section_key is None:
            return True

        active_page = self.section_pages[self.active_section_key]
        can_leave = getattr(active_page, "can_leave", None)

        if can_leave is None:
            return True

        return can_leave()
