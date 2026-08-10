import tkinter as tk

from theme import APP_BACKGROUND


class ContentHost(tk.Frame):
    def __init__(self, parent, sections):
        super().__init__(parent, bg=APP_BACKGROUND)

        self.section_definitions = {
            section.key: section for section in sections
        }
        self.section_pages = {}

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

    def show_section(self, section_key):
        if section_key not in self.section_definitions:
            raise KeyError(f"Unknown section: {section_key}")

        if section_key not in self.section_pages:
            section_definition = self.section_definitions[section_key]
            section_page = section_definition.page_class(self)
            section_page.grid(row=0, column=0, sticky="nsew")
            self.section_pages[section_key] = section_page

        self.section_pages[section_key].tkraise()
