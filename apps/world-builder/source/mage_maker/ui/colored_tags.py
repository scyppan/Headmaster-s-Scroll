import re
import tkinter as tk
from copy import deepcopy
from tkinter import colorchooser, messagebox

from mage_maker.ui.theme import (
    BORDER_SOFT,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    FIELD_BACKGROUND,
    LIST_SELECTED,
    PRIMARY,
    PRIMARY_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)
from mage_maker.ui.widgets import RoundedEntry, SoftButton


TAG_COLOR_PATTERN = re.compile(r"^#[0-9a-fA-F]{6}$")
DEFAULT_TAG_COLOR = "#D8E3EC"


def normalize_colored_tags(value):
    if value in (None, ""):
        candidates = []
    elif isinstance(value, (list, tuple)):
        candidates = list(value)
    else:
        raise TypeError("Tags must be a list.")

    tags = []
    seen_text = set()

    for candidate in candidates:
        if isinstance(candidate, str):
            text = candidate.strip()
            background_color = DEFAULT_TAG_COLOR
        elif isinstance(candidate, dict):
            text = str(
                candidate.get("text", candidate.get("name", "")) or ""
            ).strip()
            background_color = str(
                candidate.get(
                    "background_color",
                    candidate.get("color", DEFAULT_TAG_COLOR),
                )
                or DEFAULT_TAG_COLOR
            ).strip()
        else:
            raise TypeError("Every tag must be text or an object.")

        if not text:
            continue

        if not TAG_COLOR_PATTERN.fullmatch(background_color):
            background_color = DEFAULT_TAG_COLOR

        text_key = text.casefold()

        if text_key in seen_text:
            continue

        seen_text.add(text_key)
        tags.append(
            {
                "text": text,
                "background_color": background_color.upper(),
            }
        )

    return tags


def tag_foreground(background_color):
    color = str(background_color or DEFAULT_TAG_COLOR).lstrip("#")

    try:
        red = int(color[0:2], 16)
        green = int(color[2:4], 16)
        blue = int(color[4:6], 16)
    except (TypeError, ValueError):
        return TEXT_DARK

    luminance = (299 * red + 587 * green + 114 * blue) / 1000
    return "#FFFFFF" if luminance < 128 else TEXT_DARK


class ColoredTagsEditor(tk.Frame):
    def __init__(
        self,
        parent,
        title="Tags",
        background=SURFACE,
        change_command=None,
        height=6,
    ):
        super().__init__(parent, bg=background)
        self.background = background
        self.change_command = change_command
        self.tags = []
        self.selected_color = DEFAULT_TAG_COLOR
        self.text_value = tk.StringVar()
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        tk.Label(
            self,
            text=title,
            bg=background,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", pady=(0, 5))
        list_frame = tk.Frame(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
        )
        list_frame.grid(row=1, column=0, sticky="nsew")
        list_frame.grid_rowconfigure(0, weight=1)
        list_frame.grid_columnconfigure(0, weight=1)
        self.tag_list = tk.Listbox(
            list_frame,
            height=height,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            selectbackground=LIST_SELECTED,
            selectforeground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=app_font(9, "bold"),
            activestyle="none",
            exportselection=False,
        )
        self.tag_list.grid(row=0, column=0, sticky="nsew")
        self.tag_list.bind("<<ListboxSelect>>", self.tag_selected)
        scrollbar = tk.Scrollbar(list_frame, command=self.tag_list.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.tag_list.configure(yscrollcommand=scrollbar.set)
        editor = tk.Frame(self, bg=background)
        editor.grid(row=2, column=0, sticky="ew", pady=(7, 0))
        editor.grid_columnconfigure(0, weight=1)
        self.text_entry = RoundedEntry(
            editor,
            textvariable=self.text_value,
            background=background,
            height=32,
            font=app_font(9),
        )
        self.text_entry.grid(row=0, column=0, sticky="ew")
        self.color_preview = tk.Label(
            editor,
            text="Color",
            bg=self.selected_color,
            fg=tag_foreground(self.selected_color),
            font=app_font(8, "bold"),
            padx=9,
            pady=7,
        )
        self.color_preview.grid(row=0, column=1, padx=(6, 0))
        controls = tk.Frame(self, bg=background)
        controls.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        SoftButton(
            controls,
            text="Pick color",
            command=self.choose_color,
            background=background,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=84,
            height=28,
            font=app_font(8, "bold"),
        ).pack(side="left")
        SoftButton(
            controls,
            text="Add / update",
            command=self.add_or_update_tag,
            background=background,
            fill=PRIMARY,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=104,
            height=28,
            font=app_font(8, "bold"),
        ).pack(side="left", padx=(6, 0))
        SoftButton(
            controls,
            text="Remove",
            command=self.remove_tag,
            background=background,
            fill=BUTTON_SOFT,
            hover_fill=BUTTON_SOFT_HOVER,
            foreground=TEXT_DARK,
            width=70,
            height=28,
            font=app_font(8, "bold"),
        ).pack(side="left", padx=(6, 0))
        tk.Label(
            self,
            text="Each tag stores its own text and background color.",
            bg=background,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="w",
        ).grid(row=4, column=0, sticky="ew", pady=(5, 0))

    def set_tags(self, tags):
        self.tags = normalize_colored_tags(tags)
        self.text_value.set("")
        self.selected_color = DEFAULT_TAG_COLOR
        self.update_color_preview()
        self.refresh_tags()

    def get_tags(self):
        return deepcopy(self.tags)

    def refresh_tags(self, selected_index=None):
        self.tag_list.delete(0, "end")

        for index, tag in enumerate(self.tags):
            self.tag_list.insert("end", tag["text"])
            self.tag_list.itemconfigure(
                index,
                background=tag["background_color"],
                foreground=tag_foreground(tag["background_color"]),
                selectbackground=tag["background_color"],
                selectforeground=tag_foreground(tag["background_color"]),
            )

        if selected_index is not None and 0 <= selected_index < len(self.tags):
            self.tag_list.selection_set(selected_index)
            self.tag_list.see(selected_index)

    def selected_index(self):
        selected = self.tag_list.curselection()
        return int(selected[0]) if selected else None

    def tag_selected(self, event=None):
        selected_index = self.selected_index()

        if selected_index is None:
            return

        selected_tag = self.tags[selected_index]
        self.text_value.set(selected_tag["text"])
        self.selected_color = selected_tag["background_color"]
        self.update_color_preview()

    def choose_color(self):
        selected_color = colorchooser.askcolor(
            color=self.selected_color,
            title="Choose tag background color",
            parent=self,
        )[1]

        if selected_color:
            self.selected_color = selected_color.upper()
            self.update_color_preview()

    def update_color_preview(self):
        self.color_preview.configure(
            bg=self.selected_color,
            fg=tag_foreground(self.selected_color),
        )

    def add_or_update_tag(self):
        tag_text = self.text_value.get().strip()

        if not tag_text:
            messagebox.showerror(
                "Tag text required",
                "Enter text for the tag.",
                parent=self,
            )
            return

        selected_index = self.selected_index()
        tag = {
            "text": tag_text,
            "background_color": self.selected_color,
        }

        if selected_index is None:
            prospective_tags = [*self.tags, tag]
            retained_text = tag_text
        else:
            prospective_tags = [
                tag if index == selected_index else stored_tag
                for index, stored_tag in enumerate(self.tags)
            ]
            retained_text = tag_text

        self.tags = normalize_colored_tags(prospective_tags)
        retained_index = next(
            (
                index
                for index, stored_tag in enumerate(self.tags)
                if stored_tag["text"].casefold() == retained_text.casefold()
            ),
            None,
        )
        self.refresh_tags(retained_index)

        if self.change_command is not None:
            self.change_command()

    def remove_tag(self):
        selected_index = self.selected_index()

        if selected_index is None:
            return

        self.tags = [
            tag
            for index, tag in enumerate(self.tags)
            if index != selected_index
        ]
        self.text_value.set("")
        self.selected_color = DEFAULT_TAG_COLOR
        self.update_color_preview()
        self.refresh_tags()

        if self.change_command is not None:
            self.change_command()
