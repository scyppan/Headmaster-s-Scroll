import tkinter as tk
from functools import partial

from runtime_theme import runtime_theme
from theme import (
    app_font,
    BORDER,
    BUTTON_DISABLED,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    CONTROL_RADIUS,
    FIELD_BACKGROUND,
    FIELD_DISABLED,
    FIELD_FOCUS,
    FIELD_HOVER,
    SURFACE,
    TEXT_DARK,
    TEXT_DISABLED,
)


def rounded_points(width, height, radius):
    radius = max(1, min(radius, width // 2, height // 2))

    return (
        radius,
        1,
        radius,
        1,
        width - radius,
        1,
        width - radius,
        1,
        width - 1,
        radius,
        width - 1,
        radius,
        width - 1,
        height - radius,
        width - 1,
        height - radius,
        width - radius,
        height - 1,
        width - radius,
        height - 1,
        radius,
        height - 1,
        radius,
        height - 1,
        1,
        height - radius,
        1,
        height - radius,
        1,
        radius,
        1,
        radius,
    )


class RoundedEntry(tk.Frame):
    def __init__(
        self,
        parent,
        textvariable=None,
        background=SURFACE,
        fill=FIELD_BACKGROUND,
        width=180,
        height=40,
        radius=CONTROL_RADIUS,
        font=app_font(11),
        justify="left",
        show=None,
        background_role="SURFACE",
        fill_role="FIELD_BACKGROUND",
    ):
        super().__init__(
            parent,
            bg=background,
            width=width,
            height=height,
        )

        self.background = background
        self.normal_fill = fill
        self.current_fill = fill
        self.radius = radius
        self.has_focus = False
        self.is_enabled = True
        self.background_role = background_role
        self.fill_role = fill_role
        self.hover_fill = FIELD_HOVER
        self.focus_outline = FIELD_FOCUS
        self.border_outline = BORDER
        self.disabled_fill = FIELD_DISABLED
        self.text_color = TEXT_DARK
        self.disabled_text_color = TEXT_DISABLED

        self.grid_propagate(False)
        self.pack_propagate(False)

        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=0,
            borderwidth=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.shape = self.canvas.create_polygon(
            rounded_points(width, height, radius),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=BORDER,
            width=1,
        )

        entry_options = {
            "textvariable": textvariable,
            "bg": fill,
            "fg": TEXT_DARK,
            "insertbackground": TEXT_DARK,
            "disabledbackground": FIELD_DISABLED,
            "disabledforeground": TEXT_DISABLED,
            "relief": "flat",
            "borderwidth": 0,
            "highlightthickness": 0,
            "font": font,
            "justify": justify,
        }

        if show is not None:
            entry_options["show"] = show

        self.entry = tk.Entry(self.canvas, **entry_options)
        self.entry_window = self.canvas.create_window(
            12,
            height // 2,
            window=self.entry,
            anchor="w",
            width=max(20, width - 24),
            height=max(20, height - 12),
        )

        self.bind("<Configure>", self.handle_resize)
        self.canvas.bind("<Button-1>", self.focus_entry)
        self.canvas.bind("<Enter>", self.handle_enter)
        self.canvas.bind("<Leave>", self.handle_leave)
        self.entry.bind("<FocusIn>", self.handle_focus_in)
        self.entry.bind("<FocusOut>", self.handle_focus_out)
        self.entry.bind("<Enter>", self.handle_enter)
        self.entry.bind("<Leave>", self.handle_leave)
        runtime_theme.register(self)

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.canvas.coords(
            self.shape,
            *rounded_points(width, height, self.radius),
        )
        self.canvas.coords(self.entry_window, 12, height // 2)
        self.canvas.itemconfigure(
            self.entry_window,
            width=max(20, width - 24),
            height=max(20, height - 12),
        )

    def focus_entry(self, event=None):
        if self.is_enabled:
            self.entry.focus_set()

    def handle_focus_in(self, event):
        self.has_focus = True
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=self.focus_outline,
            width=2,
        )

    def handle_focus_out(self, event):
        self.has_focus = False
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=self.border_outline,
            width=1,
        )

    def handle_enter(self, event):
        if self.is_enabled and not self.has_focus:
            self.set_fill(self.hover_fill)

    def handle_leave(self, event):
        if self.is_enabled and not self.has_focus:
            self.set_fill(self.normal_fill)

    def set_fill(self, fill):
        self.current_fill = fill
        self.canvas.itemconfigure(self.shape, fill=fill)
        self.entry.configure(bg=fill)

    def set_enabled(self, enabled):
        self.is_enabled = enabled
        self.entry.configure(state="normal" if enabled else "disabled")
        self.set_fill(self.normal_fill if enabled else self.disabled_fill)

    def apply_theme(self, theme_values):
        self.background = theme_values[self.background_role]
        self.normal_fill = theme_values[self.fill_role]
        self.hover_fill = theme_values["FIELD_HOVER"]
        self.focus_outline = theme_values["FIELD_FOCUS"]
        self.border_outline = theme_values["BORDER"]
        self.disabled_fill = theme_values["FIELD_DISABLED"]
        self.text_color = theme_values["TEXT_DARK"]
        self.disabled_text_color = theme_values["TEXT_DISABLED"]
        self.configure(bg=self.background)
        self.canvas.configure(bg=self.background)
        self.entry.configure(
            fg=self.text_color,
            insertbackground=self.text_color,
            disabledbackground=self.disabled_fill,
            disabledforeground=self.disabled_text_color,
        )

        if not self.is_enabled:
            fill = self.disabled_fill
        elif self.has_focus:
            fill = self.normal_fill
        else:
            fill = self.current_fill

            if fill not in (self.normal_fill, self.hover_fill):
                fill = self.normal_fill

        self.set_fill(fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=(
                self.focus_outline
                if self.has_focus
                else self.border_outline
            ),
        )

    def focus_set(self):
        self.entry.focus_set()

    def get(self):
        return self.entry.get()

    def bind_input(self, sequence, command):
        self.bind(sequence, command)
        self.canvas.bind(sequence, command)
        self.entry.bind(sequence, command)


class RoundedText(tk.Frame):
    def __init__(
        self,
        parent,
        background=SURFACE,
        fill=FIELD_BACKGROUND,
        height=6,
        radius=CONTROL_RADIUS,
        font=app_font(11),
        background_role="SURFACE",
        fill_role="FIELD_BACKGROUND",
    ):
        super().__init__(parent, bg=background)

        self.background = background
        self.normal_fill = fill
        self.radius = radius
        self.has_focus = False
        self.background_role = background_role
        self.fill_role = fill_role
        self.hover_fill = FIELD_HOVER
        self.focus_outline = FIELD_FOCUS
        self.border_outline = BORDER
        self.text_color = TEXT_DARK

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=0,
            borderwidth=0,
            height=max(76, height * 22),
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")

        self.shape = self.canvas.create_polygon(
            rounded_points(240, max(76, height * 22), radius),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=BORDER,
            width=1,
        )

        self.text = tk.Text(
            self.canvas,
            height=height,
            wrap="word",
            bg=fill,
            fg=TEXT_DARK,
            insertbackground=TEXT_DARK,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=font,
            padx=5,
            pady=4,
            undo=True,
        )
        self.text_window = self.canvas.create_window(
            9,
            8,
            window=self.text,
            anchor="nw",
        )

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.text.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(row=0, column=1, sticky="ns", padx=(3, 0))
        self.text.configure(yscrollcommand=self.scrollbar.set)

        self.canvas.bind("<Configure>", self.handle_resize)
        self.canvas.bind("<Button-1>", self.focus_text)
        self.canvas.bind("<Enter>", self.handle_enter)
        self.canvas.bind("<Leave>", self.handle_leave)
        self.text.bind("<FocusIn>", self.handle_focus_in)
        self.text.bind("<FocusOut>", self.handle_focus_out)
        self.text.bind("<Enter>", self.handle_enter)
        self.text.bind("<Leave>", self.handle_leave)
        runtime_theme.register(self)

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.canvas.coords(
            self.shape,
            *rounded_points(width, height, self.radius),
        )
        self.canvas.itemconfigure(
            self.text_window,
            width=max(20, width - 18),
            height=max(20, height - 16),
        )

    def focus_text(self, event=None):
        self.text.focus_set()

    def handle_focus_in(self, event):
        self.has_focus = True
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=self.focus_outline,
            width=2,
        )

    def handle_focus_out(self, event):
        self.has_focus = False
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=self.border_outline,
            width=1,
        )

    def handle_enter(self, event):
        if not self.has_focus:
            self.set_fill(self.hover_fill)

    def handle_leave(self, event):
        if not self.has_focus:
            self.set_fill(self.normal_fill)

    def set_fill(self, fill):
        self.canvas.itemconfigure(self.shape, fill=fill)
        self.text.configure(bg=fill)

    def apply_theme(self, theme_values):
        self.background = theme_values[self.background_role]
        self.normal_fill = theme_values[self.fill_role]
        self.hover_fill = theme_values["FIELD_HOVER"]
        self.focus_outline = theme_values["FIELD_FOCUS"]
        self.border_outline = theme_values["BORDER"]
        self.text_color = theme_values["TEXT_DARK"]
        self.configure(bg=self.background)
        self.canvas.configure(bg=self.background)
        self.text.configure(
            fg=self.text_color,
            insertbackground=self.text_color,
        )
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=(
                self.focus_outline
                if self.has_focus
                else self.border_outline
            ),
        )


class SoftButton(tk.Canvas):
    def __init__(
        self,
        parent,
        text,
        command,
        background=SURFACE,
        fill=BUTTON_SOFT,
        hover_fill=BUTTON_SOFT_HOVER,
        foreground=TEXT_DARK,
        disabled_fill=BUTTON_DISABLED,
        disabled_foreground=TEXT_DISABLED,
        width=None,
        height=38,
        radius=CONTROL_RADIUS,
        font=app_font(10),
        anchor="center",
        padx=16,
        background_role="SURFACE",
        fill_role="BUTTON_SOFT",
        hover_fill_role="BUTTON_SOFT_HOVER",
        foreground_role="TEXT_DARK",
        disabled_fill_role="BUTTON_DISABLED",
        disabled_foreground_role="TEXT_DISABLED",
    ):
        calculated_width = width or max(80, len(text) * 9 + padx * 2)

        super().__init__(
            parent,
            bg=background,
            width=calculated_width,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
            takefocus=1,
        )

        self.button_text = text
        self.command = command
        self.normal_fill = fill
        self.hover_fill = hover_fill
        self.foreground = foreground
        self.disabled_fill = disabled_fill
        self.disabled_foreground = disabled_foreground
        self.radius = radius
        self.anchor = anchor
        self.padx = padx
        self.is_enabled = True
        self.is_hovered = False
        self.background_role = background_role
        self.fill_role = fill_role
        self.hover_fill_role = hover_fill_role
        self.foreground_role = foreground_role
        self.disabled_fill_role = disabled_fill_role
        self.disabled_foreground_role = disabled_foreground_role

        self.shape = self.create_polygon(
            rounded_points(calculated_width, height, radius),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline="",
        )
        self.label = self.create_text(
            calculated_width // 2,
            height // 2,
            text=text,
            fill=foreground,
            font=font,
            anchor="center",
        )

        self.bind("<Configure>", self.handle_resize)
        self.bind("<Enter>", self.handle_enter)
        self.bind("<Leave>", self.handle_leave)
        self.bind("<Button-1>", self.handle_click)
        self.bind("<Return>", self.handle_click)
        self.bind("<space>", self.handle_click)
        runtime_theme.register(self)

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.coords(
            self.shape,
            *rounded_points(width, height, self.radius),
        )

        if self.anchor == "w":
            self.coords(self.label, self.padx, height // 2)
            self.itemconfigure(self.label, anchor="w")
        else:
            self.coords(self.label, width // 2, height // 2)
            self.itemconfigure(self.label, anchor="center")

    def handle_enter(self, event):
        self.is_hovered = True

        if self.is_enabled:
            self.itemconfigure(self.shape, fill=self.hover_fill)

    def handle_leave(self, event):
        self.is_hovered = False

        if self.is_enabled:
            self.itemconfigure(self.shape, fill=self.normal_fill)

    def handle_click(self, event=None):
        if self.is_enabled and self.command is not None:
            self.command()

    def set_enabled(self, enabled):
        self.is_enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")

        if enabled:
            fill = self.hover_fill if self.is_hovered else self.normal_fill
            foreground = self.foreground
        else:
            fill = self.disabled_fill
            foreground = self.disabled_foreground

        self.itemconfigure(self.shape, fill=fill)
        self.itemconfigure(self.label, fill=foreground)

    def set_colors(self, fill, hover_fill, foreground=None):
        self.normal_fill = fill
        self.hover_fill = hover_fill

        if foreground is not None:
            self.foreground = foreground

        if self.is_enabled:
            self.itemconfigure(
                self.shape,
                fill=hover_fill if self.is_hovered else fill,
            )
            self.itemconfigure(self.label, fill=self.foreground)

    def set_theme_roles(
        self,
        fill_role,
        hover_fill_role,
        foreground_role="TEXT_DARK",
    ):
        self.fill_role = fill_role
        self.hover_fill_role = hover_fill_role
        self.foreground_role = foreground_role
        self.apply_theme(runtime_theme.get_values())

    def apply_theme(self, theme_values):
        background = theme_values[self.background_role]
        self.normal_fill = theme_values[self.fill_role]
        self.hover_fill = theme_values[self.hover_fill_role]
        self.foreground = theme_values[self.foreground_role]
        self.disabled_fill = theme_values[self.disabled_fill_role]
        self.disabled_foreground = theme_values[
            self.disabled_foreground_role
        ]
        self.configure(bg=background)
        self.set_enabled(self.is_enabled)

    def set_text(self, text):
        self.button_text = text
        self.itemconfigure(self.label, text=text)

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)


class RoundedSelect(tk.Frame):
    def __init__(
        self,
        parent,
        variable,
        values,
        background=SURFACE,
        fill=FIELD_BACKGROUND,
        width=150,
        height=38,
        radius=CONTROL_RADIUS,
        font=app_font(10),
        placeholder="Select type",
        background_role="SURFACE",
        fill_role="FIELD_BACKGROUND",
    ):
        super().__init__(
            parent,
            bg=background,
            width=width,
            height=height,
        )

        self.variable = variable
        self.values = values
        self.normal_fill = fill
        self.radius = radius
        self.font = font
        self.placeholder = placeholder
        self.background_role = background_role
        self.fill_role = fill_role
        self.hover_fill = FIELD_HOVER
        self.border_outline = BORDER
        self.text_color = TEXT_DARK

        self.grid_propagate(False)
        self.pack_propagate(False)

        self.canvas = tk.Canvas(
            self,
            bg=background,
            height=height,
            highlightthickness=0,
            borderwidth=0,
            cursor="hand2",
        )
        self.canvas.pack(fill="both", expand=True)
        self.shape = self.canvas.create_polygon(
            rounded_points(width, height, radius),
            smooth=True,
            splinesteps=24,
            fill=fill,
            outline=BORDER,
            width=1,
        )
        self.label = self.canvas.create_text(
            12,
            height // 2,
            text=self.display_value(),
            fill=TEXT_DARK,
            font=font,
            anchor="w",
        )
        self.arrow = self.canvas.create_text(
            width - 12,
            height // 2,
            text="▾",
            fill=TEXT_DARK,
            font=app_font(10),
            anchor="e",
        )

        self.menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=FIELD_HOVER,
            activeforeground=TEXT_DARK,
            relief="flat",
            borderwidth=1,
        )

        self.set_values(values)

        self.variable.trace_add("write", self.handle_value_change)
        self.bind("<Configure>", self.handle_resize)
        self.canvas.bind("<Button-1>", self.open_menu)
        self.canvas.bind("<Enter>", self.handle_enter)
        self.canvas.bind("<Leave>", self.handle_leave)
        runtime_theme.register(self)

    def display_value(self):
        return self.variable.get() or self.placeholder

    def set_values(self, values):
        self.values = list(values)
        self.menu.delete(0, "end")

        for value in self.values:
            menu_label = value or "None"
            self.menu.add_command(
                label=menu_label,
                command=partial(self.select_value, value),
            )

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.canvas.coords(
            self.shape,
            *rounded_points(width, height, self.radius),
        )
        self.canvas.coords(self.label, 12, height // 2)
        self.canvas.coords(self.arrow, width - 12, height // 2)

    def open_menu(self, event=None):
        self.menu.tk_popup(
            self.winfo_rootx(),
            self.winfo_rooty() + self.winfo_height(),
        )

    def select_value(self, value):
        self.variable.set(value)

    def handle_value_change(self, *arguments):
        self.canvas.itemconfigure(self.label, text=self.display_value())

    def handle_enter(self, event):
        self.canvas.itemconfigure(self.shape, fill=self.hover_fill)

    def handle_leave(self, event):
        self.canvas.itemconfigure(self.shape, fill=self.normal_fill)

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)
        self.canvas.bind("<MouseWheel>", command)

    def apply_theme(self, theme_values):
        background = theme_values[self.background_role]
        self.normal_fill = theme_values[self.fill_role]
        self.hover_fill = theme_values["FIELD_HOVER"]
        self.border_outline = theme_values["BORDER"]
        self.text_color = theme_values["TEXT_DARK"]
        self.configure(bg=background)
        self.canvas.configure(bg=background)
        self.canvas.itemconfigure(
            self.shape,
            fill=self.normal_fill,
            outline=self.border_outline,
        )
        self.canvas.itemconfigure(self.label, fill=self.text_color)
        self.canvas.itemconfigure(self.arrow, fill=self.text_color)
        self.menu.configure(
            bg=self.normal_fill,
            fg=self.text_color,
            activebackground=self.hover_fill,
            activeforeground=self.text_color,
        )
