import tkinter as tk
from math import ceil

from runtime_theme import bind_theme
from shared.widgets.controls import SoftButton
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    FIELD_HOVER,
    PRIMARY_LIGHT,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class NameChecklist(tk.Frame):
    def __init__(
        self,
        parent,
        title,
        change_command,
        height=170,
        columns=1,
    ):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.title = title
        self.change_command = change_command
        self.column_count = max(1, int(columns))
        self.options = []
        self.variables = {}
        self.loading_values = False

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.header = tk.Frame(self, bg=SURFACE)
        self.header.grid(row=0, column=0, columnspan=2, sticky="ew")
        self.header.grid_columnconfigure(0, weight=1)
        bind_theme(self.header, background="SURFACE")

        self.title_value = tk.StringVar(value=title)
        self.title_label = tk.Label(
            self.header,
            textvariable=self.title_value,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.title_label.grid(row=0, column=0, sticky="ew")
        bind_theme(
            self.title_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.all_button = SoftButton(
            self.header,
            text="All",
            command=self.select_all,
            background=SURFACE,
            width=54,
            height=30,
        )
        self.all_button.grid(row=0, column=1, padx=(6, 4))

        self.none_button = SoftButton(
            self.header,
            text="None",
            command=self.clear_all,
            background=SURFACE,
            width=60,
            height=30,
        )
        self.none_button.grid(row=0, column=2)

        self.canvas = tk.Canvas(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
            height=height,
        )
        self.canvas.grid(
            row=1,
            column=0,
            sticky="nsew",
            pady=(5, 0),
        )
        self.canvas.bind("<Configure>", self.resize_rows_frame)
        self.canvas.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(
            self.canvas,
            background="FIELD_BACKGROUND",
            highlightbackground="BORDER_SOFT",
        )

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
        )
        self.scrollbar.grid(
            row=1,
            column=1,
            sticky="ns",
            pady=(5, 0),
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.rows_frame = tk.Frame(self.canvas, bg=FIELD_BACKGROUND)
        self.rows_frame.bind("<Configure>", self.update_scroll_region)
        self.rows_frame.bind("<MouseWheel>", self.scroll_with_mousewheel)
        bind_theme(self.rows_frame, background="FIELD_BACKGROUND")
        self.rows_window = self.canvas.create_window(
            (0, 0),
            window=self.rows_frame,
            anchor="nw",
        )

    def set_options(self, options):
        option_keys = set()
        cleaned_options = []

        for option in options:
            option_key = option.casefold()

            if option_key in option_keys:
                raise ValueError(f'Duplicate checklist option: "{option}"')

            option_keys.add(option_key)
            cleaned_options.append(option)

        previous_selected = set(self.get_selected())
        self.options = sorted(cleaned_options, key=str.casefold)

        for child in self.rows_frame.winfo_children():
            child.destroy()

        self.variables = {}
        self.loading_values = True

        rows_per_column = max(
            1,
            ceil(len(self.options) / self.column_count),
        )

        for option_index, option in enumerate(self.options):
            column_index = option_index // rows_per_column
            row_index = option_index % rows_per_column
            variable = tk.BooleanVar(value=option in previous_selected)
            self.variables[option] = variable
            checkbox = tk.Checkbutton(
                self.rows_frame,
                text=option,
                variable=variable,
                command=self.handle_change,
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                activebackground=FIELD_HOVER,
                activeforeground=TEXT_DARK,
                selectcolor=PRIMARY_LIGHT,
                font=app_font(10),
                anchor="w",
                justify="left",
                relief="flat",
                borderwidth=0,
                highlightthickness=0,
                padx=8,
                pady=4,
            )
            checkbox.grid(
                row=row_index,
                column=column_index,
                sticky="ew",
            )
            checkbox.bind("<MouseWheel>", self.scroll_with_mousewheel)
            bind_theme(
                checkbox,
                background="FIELD_BACKGROUND",
                foreground="TEXT_DARK",
                activebackground="FIELD_HOVER",
                activeforeground="TEXT_DARK",
                selectcolor="PRIMARY_LIGHT",
            )

        for column_index in range(self.column_count):
            self.rows_frame.grid_columnconfigure(
                column_index,
                weight=1,
                uniform="checklist_columns",
            )
        self.loading_values = False
        self.update_count()

    def set_selected(self, selected_names):
        selected_keys = {name.casefold() for name in selected_names}
        self.loading_values = True

        for option, variable in self.variables.items():
            variable.set(option.casefold() in selected_keys)

        self.loading_values = False
        self.update_count()

    def get_selected(self):
        return [
            option
            for option in self.options
            if self.variables.get(option) is not None
            and self.variables[option].get()
        ]

    def select_all(self):
        self.set_every_option(True)

    def clear_all(self):
        self.set_every_option(False)

    def set_every_option(self, selected):
        self.loading_values = True

        for variable in self.variables.values():
            variable.set(selected)

        self.loading_values = False
        self.update_count()
        self.change_command()

    def handle_change(self):
        self.update_count()

        if not self.loading_values:
            self.change_command()

    def update_count(self):
        selected_count = len(self.get_selected())
        self.title_value.set(
            f"{self.title} — {selected_count}/{len(self.options)} selected"
        )

    def update_scroll_region(self, event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def resize_rows_frame(self, event):
        self.canvas.itemconfigure(self.rows_window, width=event.width)

    def scroll_with_mousewheel(self, event):
        if event.delta > 0:
            self.canvas.yview_scroll(-3, "units")
        elif event.delta < 0:
            self.canvas.yview_scroll(3, "units")

        return "break"
