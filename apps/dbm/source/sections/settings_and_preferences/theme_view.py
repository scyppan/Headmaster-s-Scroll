import re
import tkinter as tk
from functools import partial
from tkinter import colorchooser, messagebox

from preferences.defaults import THEME_COLOR_FIELDS
from runtime_theme import bind_theme, runtime_theme
from shared.widgets.controls import rounded_points
from theme import (
    app_font,
    monospace_font,
    BORDER,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
)


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class ColorSwatch(tk.Canvas):
    def __init__(self, parent, color, command):
        super().__init__(
            parent,
            bg=SURFACE,
            width=130,
            height=42,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
            takefocus=1,
        )

        self.command = command
        self.current_color = color
        self.color_is_valid = True
        self.surface_color = SURFACE
        self.border_color = BORDER
        self.focus_color = TEXT_DARK
        self.shape = self.create_polygon(
            rounded_points(130, 42, 10),
            smooth=True,
            splinesteps=24,
            fill=color,
            outline=BORDER,
            width=1,
        )
        self.bind("<Configure>", self.handle_resize)
        self.bind("<Button-1>", self.handle_click)
        self.bind("<Return>", self.handle_click)
        self.bind("<space>", self.handle_click)
        self.bind("<Enter>", self.handle_enter)
        self.bind("<Leave>", self.handle_leave)
        runtime_theme.register(self)

    def handle_resize(self, event):
        self.coords(
            self.shape,
            *rounded_points(event.width, event.height, 10),
        )

    def handle_click(self, event=None):
        self.command()

    def handle_enter(self, event):
        self.itemconfigure(
            self.shape,
            outline=self.focus_color,
            width=3,
        )

    def handle_leave(self, event):
        self.set_color(self.current_color, self.color_is_valid)

    def set_color(self, color, valid):
        self.current_color = color
        self.color_is_valid = valid

        if valid:
            self.itemconfigure(
                self.shape,
                fill=color,
                outline=self.border_color,
                width=1,
            )
        else:
            self.itemconfigure(
                self.shape,
                fill=self.surface_color,
                outline="#A04C3F",
                width=2,
            )

    def apply_theme(self, theme_values):
        self.surface_color = theme_values["SURFACE"]
        self.border_color = theme_values["BORDER"]
        self.focus_color = theme_values["FIELD_FOCUS"]
        self.configure(bg=self.surface_color)
        self.set_color(self.current_color, self.color_is_valid)


class ThemeSettingsView(tk.Frame):
    def __init__(self, parent, controller, dirty_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.controller = controller
        self.dirty_command = dirty_command
        self.loading_settings = False
        self.form_dirty = False
        self.color_values = {}
        self.color_swatches = {}
        self.color_value_labels = {}

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.introduction = tk.Label(
            self,
            text=(
                "Click any color swatch to open the color picker. Your "
                "selection previews across the app immediately; Save Theme "
                "makes it permanent."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="w",
        )
        self.introduction.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=30,
            pady=(24, 12),
        )
        bind_theme(
            self.introduction,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.scroll_area = tk.Canvas(
            self,
            bg=SURFACE,
            highlightthickness=0,
            borderwidth=0,
        )
        self.scroll_area.grid(row=1, column=0, sticky="nsew")
        self.scroll_area.bind("<Configure>", self.resize_fields_frame)
        self.scroll_area.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(self.scroll_area, background="SURFACE")

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.scroll_area.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=1, column=1, sticky="ns", padx=(0, 10))
        self.scroll_area.configure(yscrollcommand=self.scrollbar.set)

        self.fields_frame = tk.Frame(self.scroll_area, bg=SURFACE)
        bind_theme(self.fields_frame, background="SURFACE")
        self.fields_frame.grid_columnconfigure(0, weight=1)
        self.fields_frame.bind("<Configure>", self.update_scroll_region)
        self.fields_frame.bind("<MouseWheel>", self.scroll_with_mousewheel)
        self.fields_window = self.scroll_area.create_window(
            (0, 0),
            window=self.fields_frame,
            anchor="nw",
        )

        self.build_color_fields()
        self.load_values()

    def build_color_fields(self):
        current_category = None
        row_index = 0

        for category, field_key, label_text, default_value in THEME_COLOR_FIELDS:
            if category != current_category:
                category_label = tk.Label(
                    self.fields_frame,
                    text=category,
                    bg=SURFACE,
                    fg=TEXT_DARK,
                    font=app_font(14),
                    anchor="w",
                )
                category_label.grid(
                    row=row_index,
                    column=0,
                    columnspan=3,
                    sticky="ew",
                    padx=30,
                    pady=(18 if row_index else 6, 8),
                )
                category_label.bind(
                    "<MouseWheel>",
                    self.scroll_with_mousewheel,
                )
                bind_theme(
                    category_label,
                    background="SURFACE",
                    foreground="TEXT_DARK",
                )
                current_category = category
                row_index += 1

            field_label = tk.Label(
                self.fields_frame,
                text=f"{label_text}  ({field_key})",
                bg=SURFACE,
                fg=TEXT_DARK,
                font=app_font(10),
                anchor="w",
            )
            field_label.grid(
                row=row_index,
                column=0,
                sticky="ew",
                padx=(30, 20),
                pady=5,
            )
            field_label.bind(
                "<MouseWheel>",
                self.scroll_with_mousewheel,
            )
            bind_theme(
                field_label,
                background="SURFACE",
                foreground="TEXT_DARK",
            )

            color_value = tk.StringVar(value=default_value)
            color_value.trace_add(
                "write",
                partial(self.handle_color_change, field_key),
            )

            color_swatch = ColorSwatch(
                self.fields_frame,
                default_value,
                command=partial(self.choose_color, field_key),
            )
            color_swatch.grid(
                row=row_index,
                column=1,
                padx=(0, 14),
                pady=5,
            )
            color_swatch.bind(
                "<MouseWheel>",
                self.scroll_with_mousewheel,
            )

            color_value_label = tk.Label(
                self.fields_frame,
                textvariable=color_value,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=monospace_font(10),
                width=9,
                anchor="w",
                cursor="hand2",
            )
            color_value_label.grid(
                row=row_index,
                column=2,
                padx=(0, 30),
                pady=5,
            )
            color_value_label.bind(
                "<Button-1>",
                partial(self.open_picker_from_label, field_key),
            )
            color_value_label.bind(
                "<MouseWheel>",
                self.scroll_with_mousewheel
            )
            bind_theme(
                color_value_label,
                background="SURFACE",
                foreground="TEXT_MUTED",
            )

            self.color_values[field_key] = color_value
            self.color_swatches[field_key] = color_swatch
            self.color_value_labels[field_key] = color_value_label
            row_index += 1

        self.bottom_spacer = tk.Frame(
            self.fields_frame,
            bg=SURFACE,
            height=24,
        )
        self.bottom_spacer.grid(
            row=row_index,
            column=0,
            columnspan=3,
            sticky="ew",
        )
        bind_theme(self.bottom_spacer, background="SURFACE")

    def load_values(self):
        theme_values = self.controller.load_theme_settings()
        self.loading_settings = True

        for field_key, color_value in self.color_values.items():
            saved_value = theme_values.get(field_key, color_value.get())
            color_value.set(saved_value)
            is_valid = HEX_COLOR_PATTERN.fullmatch(saved_value) is not None
            self.color_swatches[field_key].set_color(saved_value, is_valid)

        self.loading_settings = False
        self.form_dirty = False
        runtime_theme.update_theme(theme_values)

        return "Theme colors loaded"

    def save_values(self):
        theme_values = {}
        invalid_fields = []

        for field_key, color_value in self.color_values.items():
            cleaned_value = color_value.get().strip().upper()

            if not HEX_COLOR_PATTERN.fullmatch(cleaned_value):
                invalid_fields.append(field_key)
                continue

            theme_values[field_key] = cleaned_value

        if invalid_fields:
            messagebox.showerror(
                "Invalid theme color",
                (
                    "Every theme color must use the format #RRGGBB.\n\n"
                    f"Check: {', '.join(invalid_fields)}"
                ),
                parent=self,
            )
            return False

        self.controller.save_theme_settings(theme_values)
        self.loading_settings = True

        for field_key, cleaned_value in theme_values.items():
            self.color_values[field_key].set(cleaned_value)

        self.loading_settings = False
        self.form_dirty = False
        runtime_theme.update_theme(theme_values)

        return "Theme saved. The current colors are now permanent."

    def handle_color_change(self, field_key, *arguments):
        color_value = self.color_values[field_key].get().strip()
        is_valid = HEX_COLOR_PATTERN.fullmatch(color_value) is not None
        self.color_swatches[field_key].set_color(color_value, is_valid)

        if self.loading_settings:
            return

        if is_valid:
            runtime_theme.update_color(field_key, color_value.upper())
            self.winfo_toplevel().update_idletasks()

        self.form_dirty = True
        self.dirty_command()

    def choose_color(self, field_key):
        current_color = self.color_values[field_key].get().strip()

        if HEX_COLOR_PATTERN.fullmatch(current_color) is None:
            current_color = "#D4C6A1"

        selected_color = colorchooser.askcolor(
            color=current_color,
            title=f"Choose {field_key}",
            parent=self,
        )[1]

        if selected_color is None:
            return

        self.color_values[field_key].set(selected_color.upper())

    def open_picker_from_label(self, field_key, event=None):
        self.choose_color(field_key)

    def has_unsaved_changes(self):
        return self.form_dirty

    def update_scroll_region(self, event):
        self.scroll_area.configure(
            scrollregion=self.scroll_area.bbox("all")
        )

    def resize_fields_frame(self, event):
        self.scroll_area.itemconfigure(
            self.fields_window,
            width=event.width,
        )

    def scroll_with_mousewheel(self, event):
        if event.delta > 0:
            self.scroll_area.yview_scroll(-3, "units")
        elif event.delta < 0:
            self.scroll_area.yview_scroll(3, "units")

        return "break"
