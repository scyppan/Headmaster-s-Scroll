import tkinter as tk
from functools import partial
from tkinter import messagebox

from mage_maker.core.dates import (
    CALENDAR_ADOPTION_NOTE,
    historical_date_was_skipped,
)
from mage_maker.ui.theme import (
    BORDER,
    BORDER_SOFT,
    BUTTON_DISABLED,
    BUTTON_SOFT,
    BUTTON_SOFT_HOVER,
    CONTROL_RADIUS,
    FIELD_BACKGROUND,
    FIELD_DISABLED,
    FIELD_FOCUS,
    FIELD_HOVER,
    LIST_HOVER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_DISABLED,
    TEXT_MUTED,
    app_font,
)


def rounded_points(width, height, radius):
    radius = max(1, min(radius, width // 2, height // 2))

    return (
        radius, 1, radius, 1,
        width - radius, 1, width - radius, 1,
        width - 1, radius, width - 1, radius,
        width - 1, height - radius, width - 1, height - radius,
        width - radius, height - 1, width - radius, height - 1,
        radius, height - 1, radius, height - 1,
        1, height - radius, 1, height - radius,
        1, radius, 1, radius,
    )


class HoverTooltip:
    def __init__(self, widget, text="", delay=450, wraplength=340):
        self.widget = widget
        self.text = str(text or "")
        self.delay = delay
        self.wraplength = wraplength
        self.after_id = None
        self.window = None
        self.widget.bind("<Enter>", self.handle_enter, add="+")
        self.widget.bind("<Leave>", self.handle_leave, add="+")
        self.widget.bind("<ButtonPress>", self.handle_leave, add="+")

    def set_text(self, text):
        self.text = str(text or "")

        if not self.text:
            self.cancel_pending()
            self.hide()

    def handle_enter(self, event=None):
        self.cancel_pending()

        if self.text:
            self.after_id = self.widget.after(self.delay, self.show)

    def handle_leave(self, event=None):
        self.cancel_pending()
        self.hide()

    def cancel_pending(self):
        if self.after_id is not None:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

    def show(self):
        self.after_id = None

        if not self.text or self.window is not None:
            return

        x_position = self.widget.winfo_rootx() + 12
        y_position = self.widget.winfo_rooty() + self.widget.winfo_height() + 7
        self.window = tk.Toplevel(self.widget)
        self.window.wm_overrideredirect(True)
        self.window.wm_geometry(f"+{x_position}+{y_position}")
        label = tk.Label(
            self.window,
            text=self.text,
            bg=TEXT_DARK,
            fg=SURFACE,
            font=app_font(9),
            justify="left",
            wraplength=self.wraplength,
            padx=10,
            pady=7,
            relief="solid",
            borderwidth=1,
        )
        label.pack()

    def hide(self):
        if self.window is not None:
            self.window.destroy()
            self.window = None


class CalendarAdoptionNotice(tk.Label):
    def __init__(
        self,
        parent,
        background=SURFACE,
        foreground=TEXT_MUTED,
        wraplength=520,
        date_variables=(),
    ):
        super().__init__(
            parent,
            text="ⓘ Historical calendar note",
            bg=background,
            fg=foreground,
            font=app_font(8, "bold"),
            anchor="w",
            cursor="question_arrow",
            takefocus=1,
        )
        self.calendar_tooltip = HoverTooltip(
            self,
            CALENDAR_ADOPTION_NOTE,
            delay=180,
            wraplength=wraplength,
        )
        self.date_variable_groups = self.normalize_date_variables(
            date_variables
        )
        self.date_trace_tokens = []
        self.grid_requested = False

        for variable_group in self.date_variable_groups:
            for variable in variable_group:
                if hasattr(variable, "trace_add"):
                    token = variable.trace_add(
                        "write",
                        self.date_changed,
                    )
                    self.date_trace_tokens.append((variable, token))

        self.bind(
            "<Button-1>",
            self.show_calendar_note,
            add="+",
        )

    def normalize_date_variables(self, date_variables):
        values = tuple(date_variables or ())

        if len(values) == 3 and not any(
            isinstance(value, (list, tuple))
            for value in values
        ):
            values = (values,)

        return tuple(
            tuple(group)
            for group in values
            if isinstance(group, (list, tuple)) and len(group) == 3
        )

    def grid(self, *arguments, **keywords):
        result = super().grid(*arguments, **keywords)
        self.grid_requested = True
        self.update_visibility()
        return result

    def date_changed(self, *arguments):
        self.update_visibility()

    def update_visibility(self):
        if not self.grid_requested:
            return

        if self.should_be_visible():
            super().grid()
        else:
            super().grid_remove()

    def should_be_visible(self):
        for year_value, month_value, day_value in self.date_variable_groups:
            year = self.date_variable_value(year_value)
            month = self.date_month_number(
                self.date_variable_value(month_value)
            )
            day = self.date_variable_value(day_value)

            try:
                if historical_date_was_skipped(year, month, day):
                    return True
            except (TypeError, ValueError):
                continue

        return False

    def date_variable_value(self, value):
        return value.get() if hasattr(value, "get") else value

    def date_month_number(self, value):
        month_text = str(value or "").strip()

        try:
            return int(month_text)
        except ValueError:
            month_names = (
                "jan",
                "feb",
                "mar",
                "apr",
                "may",
                "jun",
                "jul",
                "aug",
                "sep",
                "oct",
                "nov",
                "dec",
            )
            normalized = month_text.casefold()[:3]
            return (
                month_names.index(normalized) + 1
                if normalized in month_names
                else month_text
            )
        self.bind(
            "<Return>",
            self.show_calendar_note,
            add="+",
        )
        self.bind(
            "<space>",
            self.show_calendar_note,
            add="+",
        )

    def show_calendar_note(self, event=None):
        messagebox.showinfo(
            "Historical calendar note",
            CALENDAR_ADOPTION_NOTE,
            parent=self.winfo_toplevel(),
        )
        return "break"


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
    ):
        super().__init__(parent, bg=background, width=width, height=height)
        self.normal_fill = fill
        self.hover_fill = FIELD_HOVER
        self.focus_outline = FIELD_FOCUS
        self.border_outline = BORDER
        self.disabled_fill = FIELD_DISABLED
        self.has_focus = False
        self.is_enabled = True
        self.radius = radius
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
        self.entry = tk.Entry(
            self.canvas,
            textvariable=textvariable,
            bg=fill,
            fg=TEXT_DARK,
            insertbackground=TEXT_DARK,
            disabledbackground=FIELD_DISABLED,
            disabledforeground=TEXT_DISABLED,
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            font=font,
            justify=justify,
        )
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
        self.canvas.itemconfigure(self.shape, fill=fill)
        self.entry.configure(bg=fill)

    def set_enabled(self, enabled):
        self.is_enabled = bool(enabled)
        self.entry.configure(state="normal" if enabled else "disabled")
        self.set_fill(self.normal_fill if enabled else self.disabled_fill)

    def focus_set(self):
        self.entry.focus_set()

    def selection_range(self, start, end):
        self.entry.selection_range(start, end)

    def bind_input(self, sequence, command):
        self.bind(sequence, command)
        self.canvas.bind(sequence, command)
        self.entry.bind(sequence, command)


class RoundedSelect(tk.Frame):
    def __init__(
        self,
        parent,
        textvariable,
        values,
        background=SURFACE,
        fill=FIELD_BACKGROUND,
        width=180,
        height=40,
        radius=CONTROL_RADIUS,
        font=app_font(11),
        multiline=False,
    ):
        super().__init__(
            parent,
            bg=background,
            width=width,
            height=height,
            takefocus=1,
            cursor="hand2",
        )
        self.textvariable = textvariable
        self.values = [str(value) for value in values]
        self.background = background
        self.normal_fill = fill
        self.hover_fill = FIELD_HOVER
        self.focus_outline = FIELD_FOCUS
        self.border_outline = BORDER
        self.disabled_fill = FIELD_DISABLED
        self.font = font
        self.radius = radius
        self.multiline = bool(multiline)
        self.is_enabled = True
        self.has_focus = False
        self.grid_propagate(False)
        self.pack_propagate(False)
        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=0,
            borderwidth=0,
            takefocus=1,
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
        label_options = {
            "text": str(self.textvariable.get() or ""),
            "fill": TEXT_DARK,
            "font": font,
            "anchor": "w",
        }

        if self.multiline:
            label_options["width"] = max(20, width - 42)

        self.label = self.canvas.create_text(
            12,
            height // 2,
            **label_options,
        )
        self.arrow = self.canvas.create_text(
            width - 15,
            height // 2,
            text="▾",
            fill=TEXT_MUTED,
            font=app_font(10, "bold"),
            anchor="center",
        )
        self.menu = tk.Menu(
            self,
            tearoff=False,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            activebackground=LIST_HOVER,
            activeforeground=TEXT_DARK,
            disabledforeground=TEXT_DISABLED,
            relief="solid",
            borderwidth=1,
            font=font,
        )
        self.variable_trace = self.textvariable.trace_add(
            "write",
            self.variable_changed,
        )
        self.rebuild_menu()
        self.bind("<Configure>", self.handle_resize)
        self.bind("<Button-1>", self.show_menu)
        self.bind("<Enter>", self.handle_enter)
        self.bind("<Leave>", self.handle_leave)
        self.bind("<FocusIn>", self.handle_focus_in)
        self.bind("<FocusOut>", self.handle_focus_out)
        self.bind("<Return>", self.show_menu)
        self.bind("<space>", self.show_menu)
        self.bind("<Up>", self.select_previous)
        self.bind("<Down>", self.select_next)
        self.canvas.bind("<Button-1>", self.show_menu)
        self.canvas.bind("<Enter>", self.handle_enter)
        self.canvas.bind("<Leave>", self.handle_leave)
        self.canvas.bind("<FocusIn>", self.handle_focus_in)
        self.canvas.bind("<FocusOut>", self.handle_focus_out)
        self.canvas.bind("<Return>", self.show_menu)
        self.canvas.bind("<space>", self.show_menu)
        self.canvas.bind("<Up>", self.select_previous)
        self.canvas.bind("<Down>", self.select_next)

    def rebuild_menu(self):
        self.menu.delete(0, "end")

        for value in self.values:
            self.menu.add_command(
                label=value,
                command=partial(self.select_value, value),
            )

    def set_values(self, values):
        self.values = [str(value) for value in values]
        self.rebuild_menu()

        if self.values and self.textvariable.get() not in self.values:
            self.textvariable.set(self.values[0])

    def set_enabled(self, enabled):
        self.is_enabled = bool(enabled)
        cursor = "hand2" if self.is_enabled else "arrow"
        self.configure(cursor=cursor)
        self.canvas.configure(cursor=cursor)
        self.set_fill(
            self.normal_fill
            if self.is_enabled
            else self.disabled_fill
        )
        self.canvas.itemconfigure(
            self.label,
            fill=TEXT_DARK if self.is_enabled else TEXT_DISABLED,
        )
        self.canvas.itemconfigure(
            self.arrow,
            fill=TEXT_MUTED if self.is_enabled else TEXT_DISABLED,
        )

    def select_value(self, value):
        if not self.is_enabled:
            return

        self.textvariable.set(str(value))
        self.event_generate("<<RoundedSelectSelected>>")

    def select_previous(self, event=None):
        return self.select_adjacent(-1)

    def select_next(self, event=None):
        return self.select_adjacent(1)

    def select_adjacent(self, direction):
        if not self.is_enabled or not self.values:
            return "break"

        current_value = str(self.textvariable.get() or "")
        current_index = (
            self.values.index(current_value)
            if current_value in self.values
            else 0
        )
        next_index = max(
            0,
            min(
                len(self.values) - 1,
                current_index + int(direction),
            ),
        )

        if next_index != current_index or current_value not in self.values:
            self.select_value(self.values[next_index])

        return "break"

    def show_menu(self, event=None):
        if not self.is_enabled or not self.values:
            return "break"

        self.canvas.focus_set()
        self.update_idletasks()

        try:
            self.menu.tk_popup(
                self.winfo_rootx(),
                self.winfo_rooty() + self.winfo_height(),
            )
        finally:
            self.menu.grab_release()

        return "break"

    def variable_changed(self, *arguments):
        self.canvas.itemconfigure(
            self.label,
            text=str(self.textvariable.get() or ""),
        )

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.canvas.coords(
            self.shape,
            *rounded_points(width, height, self.radius),
        )
        self.canvas.coords(self.label, 12, height // 2)
        self.canvas.coords(self.arrow, width - 15, height // 2)

        if self.multiline:
            self.canvas.itemconfigure(
                self.label,
                width=max(20, width - 42),
            )

    def handle_enter(self, event=None):
        if self.is_enabled and not self.has_focus:
            self.set_fill(self.hover_fill)

    def handle_leave(self, event=None):
        if self.is_enabled and not self.has_focus:
            self.set_fill(self.normal_fill)

    def handle_focus_in(self, event=None):
        self.has_focus = True
        self.set_fill(self.normal_fill)
        self.canvas.itemconfigure(
            self.shape,
            outline=self.focus_outline,
            width=2,
        )

    def handle_focus_out(self, event=None):
        self.has_focus = False
        self.set_fill(
            self.normal_fill
            if self.is_enabled
            else self.disabled_fill
        )
        self.canvas.itemconfigure(
            self.shape,
            outline=self.border_outline,
            width=1,
        )

    def set_fill(self, fill):
        self.canvas.itemconfigure(self.shape, fill=fill)

    def focus_set(self):
        self.canvas.focus_set()


class RoundedText(tk.Frame):
    def __init__(
        self,
        parent,
        background=SURFACE,
        fill=FIELD_BACKGROUND,
        height=6,
        minimum_height=76,
        radius=CONTROL_RADIUS,
        font=app_font(11),
    ):
        super().__init__(parent, bg=background)
        self.normal_fill = fill
        self.hover_fill = FIELD_HOVER
        self.focus_outline = FIELD_FOCUS
        self.border_outline = BORDER
        self.has_focus = False
        self.radius = radius
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        control_height = max(int(minimum_height), height * 22)
        self.canvas = tk.Canvas(
            self,
            bg=background,
            highlightthickness=0,
            borderwidth=0,
            height=control_height,
        )
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.shape = self.canvas.create_polygon(
            rounded_points(240, control_height, radius),
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

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)
        self.canvas.bind("<MouseWheel>", command)
        self.text.bind("<MouseWheel>", command)


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
        font=app_font(10, "bold"),
        anchor="center",
        padx=16,
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
        self.minimum_width = calculated_width
        self.is_enabled = True
        self.is_hovered = False
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

    def handle_resize(self, event):
        width = max(2, event.width)
        height = max(2, event.height)
        self.coords(self.shape, *rounded_points(width, height, self.radius))

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
        self.is_enabled = bool(enabled)
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

        self.set_enabled(self.is_enabled)

    def set_text(self, text):
        self.button_text = text
        self.itemconfigure(self.label, text=text)
        bounds = self.bbox(self.label)

        if bounds is None:
            return

        text_width = max(0, bounds[2] - bounds[0])
        self.configure(
            width=max(self.minimum_width, text_width + self.padx * 2)
        )

    def bind_mousewheel(self, command):
        self.bind("<MouseWheel>", command)


class LabeledEntry(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        variable,
        background=SURFACE,
        font_size=11,
        control_height=40,
    ):
        super().__init__(parent, bg=background)
        self.grid_columnconfigure(0, weight=1)
        self.label = tk.Label(
            self,
            text=label_text,
            bg=background,
            fg=TEXT_MUTED,
            font=app_font(9, "bold"),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.control = RoundedEntry(
            self,
            textvariable=variable,
            background=background,
            height=control_height,
            font=app_font(font_size),
        )
        self.control.grid(row=1, column=0, sticky="ew")


class MultilineField(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        height,
        background=SURFACE,
        hint_text="",
    ):
        super().__init__(parent, bg=background)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self.label = tk.Label(
            self,
            text=label_text,
            bg=background,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew", pady=(0, 3))
        self.hint = tk.Label(
            self,
            text=hint_text,
            bg=background,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        self.hint.grid(row=1, column=0, sticky="ew", pady=(0, 6))
        self.control = RoundedText(
            self,
            background=background,
            height=height,
        )
        self.control.grid(row=2, column=0, sticky="nsew")
        self.text = self.control.text


class SectionPanel(tk.Frame):
    def __init__(self, parent, title, description=""):
        super().__init__(
            parent,
            bg=SURFACE_MUTED,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            padx=16,
            pady=14,
        )
        self.grid_columnconfigure(0, weight=1)
        self.title_label = tk.Label(
            self,
            text=title,
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(11, "bold"),
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, sticky="ew")
        self.description_label = tk.Label(
            self,
            text=description,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            justify="left",
        )
        self.description_label.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(3, 12) if description else (0, 8),
        )
        self.content = tk.Frame(self, bg=SURFACE_MUTED)
        self.content.grid(row=2, column=0, sticky="nsew")
        self.content.grid_columnconfigure(0, weight=1)
