import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import RoundedEntry, RoundedSelect
from theme import (
    BORDER,
    FIELD_BACKGROUND,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class HelpIcon(tk.Label):
    def __init__(self, parent, help_text):
        super().__init__(
            parent,
            text="?",
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            width=2,
            cursor="hand2",
            relief="solid",
            borderwidth=1,
        )
        self.help_text = help_text
        self.tooltip = None
        bind_theme(
            self,
            background="FIELD_BACKGROUND",
            foreground="TEXT_DARK",
        )
        self.bind("<Enter>", self.show_help)
        self.bind("<Leave>", self.hide_help)
        self.bind("<Button-1>", self.toggle_help)

    def show_help(self, event=None):
        if self.tooltip is not None:
            return

        self.tooltip = tk.Toplevel(self)
        self.tooltip.overrideredirect(True)
        self.tooltip.attributes("-topmost", True)
        self.tooltip.geometry(
            f"+{self.winfo_rootx() + self.winfo_width() + 6}"
            f"+{self.winfo_rooty()}"
        )
        help_label = tk.Label(
            self.tooltip,
            text=self.help_text,
            bg=FIELD_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(9),
            justify="left",
            wraplength=390,
            padx=10,
            pady=8,
            relief="solid",
            borderwidth=1,
        )
        help_label.pack()
        bind_theme(
            help_label,
            background="FIELD_BACKGROUND",
            foreground="TEXT_DARK",
        )

    def hide_help(self, event=None):
        if self.tooltip is None:
            return

        self.tooltip.destroy()
        self.tooltip = None

    def toggle_help(self, event=None):
        if self.tooltip is None:
            self.show_help()
        else:
            self.hide_help()


class LabeledEntry(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        change_command,
        justify="left",
        font_size=11,
        help_text=None,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.grid_columnconfigure(0, weight=1)
        self.value = tk.StringVar()
        self.value.trace_add("write", change_command)

        self.label_row = tk.Frame(self, bg=SURFACE)
        self.label_row.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.label_row.grid_columnconfigure(0, weight=1)
        bind_theme(self.label_row, background="SURFACE")

        self.label = tk.Label(
            self.label_row,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        if help_text:
            self.help_icon = HelpIcon(self.label_row, help_text)
            self.help_icon.grid(row=0, column=1, padx=(6, 0))
        else:
            self.help_icon = None

        self.entry = RoundedEntry(
            self,
            textvariable=self.value,
            background=SURFACE,
            height=40,
            justify=justify,
            font=app_font(font_size),
        )
        self.entry.grid(row=1, column=0, sticky="ew")

    def set_value(self, value):
        self.value.set("" if value is None else str(value))

    def get_value(self):
        return self.value.get().strip()

    def focus_set(self):
        self.entry.focus_set()


class BoundedNumberField(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        change_command,
        minimum,
        maximum,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.minimum = minimum
        self.maximum = maximum
        self.change_command = change_command
        self.updating_value = False
        self.grid_columnconfigure(0, weight=1)
        self.value = tk.StringVar()
        self.value.trace_add("write", self.handle_change)

        self.label = tk.Label(
            self,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.entry = RoundedEntry(
            self,
            textvariable=self.value,
            background=SURFACE,
            height=40,
            justify="center",
            font=app_font(10),
        )
        self.entry.grid(row=1, column=0, sticky="ew")
        validation_command = (
            self.register(self.validate_proposed_value),
            "%P",
        )
        self.entry.entry.configure(
            validate="key",
            validatecommand=validation_command,
        )
        self.entry.entry.bind("<FocusOut>", self.normalize_value)
        self.entry.entry.bind("<Return>", self.normalize_value)

        self.range_hint = tk.Label(
            self,
            text=f"{minimum}–{maximum}",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="center",
        )
        self.range_hint.grid(row=2, column=0, sticky="ew", pady=(3, 0))
        bind_theme(
            self.range_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

    def validate_proposed_value(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def handle_change(self, *arguments):
        if not self.updating_value:
            self.change_command()

    def normalize_value(self, event=None):
        value_text = self.value.get().strip()

        if not value_text:
            return

        value = max(self.minimum, min(self.maximum, int(value_text)))

        if str(value) != value_text:
            self.updating_value = True
            self.value.set(str(value))
            self.updating_value = False
            self.change_command()

    def set_limits(self, minimum, maximum):
        self.minimum = minimum
        self.maximum = maximum
        self.range_hint.configure(text=f"{minimum}–{maximum}")
        self.normalize_value()

    def set_value(self, value):
        self.updating_value = True
        self.value.set("" if value is None else str(value))
        self.updating_value = False
        self.normalize_value()

    def get_value(self):
        self.normalize_value()
        value_text = self.value.get().strip()

        if not value_text:
            return None

        return int(value_text)


class LabeledSelect(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        values,
        change_command,
        placeholder="{undefined}",
        help_text=None,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.grid_columnconfigure(0, weight=1)
        self.value = tk.StringVar()
        self.value.trace_add("write", change_command)

        self.label_row = tk.Frame(self, bg=SURFACE)
        self.label_row.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self.label_row.grid_columnconfigure(0, weight=1)
        bind_theme(self.label_row, background="SURFACE")

        self.label = tk.Label(
            self.label_row,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        if help_text:
            self.help_icon = HelpIcon(self.label_row, help_text)
            self.help_icon.grid(row=0, column=1, padx=(6, 0))
        else:
            self.help_icon = None

        self.select = RoundedSelect(
            self,
            variable=self.value,
            values=values,
            background=SURFACE,
            height=40,
            font=app_font(10),
            placeholder=placeholder,
        )
        self.select.grid(row=1, column=0, sticky="ew")

    def set_value(self, value):
        self.value.set(value or "{undefined}")

    def set_values(self, values):
        self.select.set_values(values)

    def get_value(self):
        return self.value.get().strip() or "{undefined}"


class RangeField(tk.Frame):
    def __init__(
        self,
        parent,
        label_text,
        change_command,
        minimum=1,
        maximum=50,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.minimum = minimum
        self.maximum = maximum
        self.change_command = change_command
        self.updating_values = False
        self.normalize_job = None
        self.last_changed_side = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.low_value = tk.StringVar()
        self.high_value = tk.StringVar()
        self.low_value.trace_add("write", self.handle_low_change)
        self.high_value.trace_add("write", self.handle_high_change)

        self.label = tk.Label(
            self,
            text=label_text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.label.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 5),
        )
        bind_theme(
            self.label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.low_entry = RoundedEntry(
            self,
            textvariable=self.low_value,
            background=SURFACE,
            height=40,
            justify="center",
            font=app_font(10),
        )
        self.low_entry.grid(row=1, column=0, sticky="ew", padx=(0, 5))

        self.high_entry = RoundedEntry(
            self,
            textvariable=self.high_value,
            background=SURFACE,
            height=40,
            justify="center",
            font=app_font(10),
        )
        self.high_entry.grid(row=1, column=1, sticky="ew", padx=(5, 0))

        validation_command = (
            self.register(self.validate_proposed_value),
            "%P",
        )
        self.low_entry.entry.configure(
            validate="key",
            validatecommand=validation_command,
        )
        self.high_entry.entry.configure(
            validate="key",
            validatecommand=validation_command,
        )
        self.low_entry.entry.bind("<FocusOut>", self.commit_low)
        self.high_entry.entry.bind("<FocusOut>", self.commit_high)
        self.low_entry.entry.bind("<Return>", self.commit_low)
        self.high_entry.entry.bind("<Return>", self.commit_high)

        self.range_hint = tk.Label(
            self,
            text=f"Low {minimum}–{maximum}        High {minimum}–{maximum}",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(8),
            anchor="center",
        )
        self.range_hint.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(3, 0),
        )
        bind_theme(
            self.range_hint,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

    def validate_proposed_value(self, proposed_value):
        return proposed_value == "" or proposed_value.isdigit()

    def handle_low_change(self, *arguments):
        if self.updating_values:
            return

        self.last_changed_side = "low"
        self.schedule_normalization()
        self.change_command()

    def handle_high_change(self, *arguments):
        if self.updating_values:
            return

        self.last_changed_side = "high"
        self.schedule_normalization()
        self.change_command()

    def schedule_normalization(self):
        if self.normalize_job is not None:
            self.after_cancel(self.normalize_job)

        self.normalize_job = self.after(350, self.run_scheduled_normalization)

    def run_scheduled_normalization(self):
        self.normalize_job = None
        self.normalize_ranges()

    def commit_low(self, event=None):
        self.last_changed_side = "low"
        self.normalize_ranges()

    def commit_high(self, event=None):
        self.last_changed_side = "high"
        self.normalize_ranges()

    def normalize_ranges(self):
        if self.normalize_job is not None:
            self.after_cancel(self.normalize_job)
            self.normalize_job = None

        low_text = self.low_value.get().strip()
        high_text = self.high_value.get().strip()
        low_value = None if not low_text else int(low_text)
        high_value = None if not high_text else int(high_text)

        if low_value is not None:
            low_value = max(self.minimum, min(self.maximum, low_value))

        if high_value is not None:
            high_value = max(self.minimum, min(self.maximum, high_value))

        if (
            low_value is not None
            and high_value is not None
            and low_value > high_value
        ):
            if self.last_changed_side == "high":
                low_value = high_value
            else:
                high_value = low_value

        normalized_low = "" if low_value is None else str(low_value)
        normalized_high = "" if high_value is None else str(high_value)
        values_changed = normalized_low != low_text or normalized_high != high_text

        if values_changed:
            self.updating_values = True
            self.low_value.set(normalized_low)
            self.high_value.set(normalized_high)
            self.updating_values = False
            self.change_command()

    def set_value(self, value):
        range_value = value if isinstance(value, dict) else {}
        low_value = range_value.get("low")
        high_value = range_value.get("high")
        self.updating_values = True
        self.low_value.set("" if low_value is None else str(low_value))
        self.high_value.set("" if high_value is None else str(high_value))
        self.updating_values = False
        self.last_changed_side = "low"
        self.normalize_ranges()

    def get_value(self):
        self.normalize_ranges()
        low_text = self.low_value.get().strip()
        high_text = self.high_value.get().strip()

        return {
            "low": None if not low_text else int(low_text),
            "high": None if not high_text else int(high_text),
        }
