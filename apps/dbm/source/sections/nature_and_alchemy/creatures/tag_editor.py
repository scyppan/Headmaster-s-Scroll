import tkinter as tk
from copy import deepcopy

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.form_fields import LabeledEntry
from shared.widgets import SoftButton, StripedListbox
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    app_font,
)


class TagEditor(tk.LabelFrame):
    def __init__(self, parent, change_command):
        super().__init__(
            parent,
            text="Tags",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            padx=8,
            pady=8,
        )
        bind_theme(
            self,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.change_command = change_command
        self.loading_tags = False
        self.tags = []
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.entry_row = tk.Frame(self, bg=SURFACE)
        self.entry_row.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        self.entry_row.grid_columnconfigure(0, weight=1)
        bind_theme(self.entry_row, background="SURFACE")

        self.tag_field = LabeledEntry(
            self.entry_row,
            "Add a tag",
            self.handle_entry_change,
        )
        self.tag_field.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.tag_field.entry.entry.bind("<Return>", self.add_tag)

        self.add_button = SoftButton(
            self.entry_row,
            text="Add",
            command=self.add_tag,
            width=68,
            height=36,
        )
        self.add_button.grid(row=0, column=1, sticky="s", padx=(0, 4))

        self.remove_button = SoftButton(
            self.entry_row,
            text="Remove",
            command=self.remove_tag,
            width=82,
            height=36,
        )
        self.remove_button.grid(row=0, column=2, sticky="s")

        self.listbox = StripedListbox(
            self,
            height=6,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=SIDEBAR_TILE_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            font=app_font(9),
            activestyle="none",
            exportselection=False,
            selectmode="browse",
        )
        self.listbox.grid(row=1, column=0, sticky="nsew")
        self.listbox.bind("<<ListboxSelect>>", self.update_remove_state)
        self.remove_button.set_enabled(False)

    def set_tags(self, tags):
        self.loading_tags = True
        self.tags = deepcopy(tags) if isinstance(tags, list) else []
        self.tag_field.set_value("")
        self.refresh_list()
        self.loading_tags = False

    def get_tags(self):
        normalized_tags = set()
        converted_tags = []

        for tag in self.tags:
            tag_text = str(tag).strip()

            if not tag_text:
                continue

            normalized_tag = " ".join(tag_text.split()).casefold()

            if normalized_tag in normalized_tags:
                raise ValueError(f"Duplicate tag: {tag_text}")

            normalized_tags.add(normalized_tag)
            converted_tags.append(tag_text)

        return converted_tags

    def add_tag(self, event=None):
        tag_text = self.tag_field.get_value()

        if not tag_text:
            return "break"

        normalized_tag = " ".join(tag_text.split()).casefold()

        if normalized_tag in {
            " ".join(str(tag).split()).casefold() for tag in self.tags
        }:
            return "break"

        self.tags.append(tag_text)
        self.tags.sort(key=str.casefold)
        self.tag_field.set_value("")
        self.refresh_list()
        self.change_command()

        return "break"

    def remove_tag(self):
        selected_indices = self.listbox.curselection()

        if not selected_indices:
            return

        del self.tags[selected_indices[0]]
        self.refresh_list()
        self.change_command()

    def refresh_list(self):
        self.listbox.delete(0, "end")
        for tag in self.tags:
            self.listbox.insert("end", tag)

        self.remove_button.set_enabled(False)

    def update_remove_state(self, event=None):
        self.remove_button.set_enabled(bool(self.listbox.curselection()))

    def handle_entry_change(self, *arguments):
        return None
