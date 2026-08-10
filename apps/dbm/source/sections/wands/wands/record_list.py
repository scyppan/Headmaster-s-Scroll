import tkinter as tk
from collections import Counter
from functools import partial

from runtime_theme import bind_theme, runtime_theme
from shared.widgets import RoundedEntry, alternating_row_background
from theme import (
    BORDER_SOFT,
    FIELD_BACKGROUND,
    LIST_HOVER,
    SIDEBAR_TILE_SELECTED,
    SURFACE,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class WandList(tk.Frame):
    def __init__(self, parent, selection_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.selection_command = selection_command
        self.records = []
        self.visible_record_ids = []
        self.labels_by_id = {}
        self.rows_by_id = {}
        self.selected_record_id = None
        self.hovered_record_id = None

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="All Wands",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15),
            anchor="w",
        )
        self.heading.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(16, 10),
        )
        bind_theme(
            self.heading,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.filter_records)
        self.search_entry = RoundedEntry(
            self,
            textvariable=self.search_value,
            background=SURFACE,
            height=40,
            font=app_font(11),
        )
        self.search_entry.grid(
            row=1,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(0, 12),
        )

        self.list_canvas = tk.Canvas(
            self,
            bg=FIELD_BACKGROUND,
            highlightbackground=BORDER_SOFT,
            highlightcolor=BORDER_SOFT,
            highlightthickness=1,
            borderwidth=0,
        )
        self.list_canvas.grid(
            row=2,
            column=0,
            sticky="nsew",
            padx=(16, 0),
        )
        self.list_canvas.bind("<Configure>", self.handle_canvas_resize)
        self.list_canvas.bind("<MouseWheel>", self.handle_mousewheel)

        self.list_frame = tk.Frame(
            self.list_canvas,
            bg=FIELD_BACKGROUND,
        )
        self.list_frame.grid_columnconfigure(0, weight=1)
        self.list_frame.bind("<Configure>", self.update_scroll_region)
        self.list_window = self.list_canvas.create_window(
            0,
            0,
            window=self.list_frame,
            anchor="nw",
        )

        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.list_canvas.yview,
            relief="flat",
            borderwidth=0,
        )
        self.scrollbar.grid(
            row=2,
            column=1,
            sticky="ns",
            padx=(0, 16),
        )
        self.list_canvas.configure(yscrollcommand=self.scrollbar.set)

        self.count_label = tk.Label(
            self,
            text="0 wands",
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.count_label.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="ew",
            padx=16,
            pady=(8, 14),
        )
        bind_theme(
            self.count_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )
        runtime_theme.register(self)

    def set_records(self, records, selected_record_id=None):
        self.records = records
        self.labels_by_id = {}
        name_counts = Counter(record.get("name", "") for record in records)

        for record in records:
            record_id = record["record_id"]
            record_name = record.get("name", "") or "Unnamed wand"

            if name_counts[record.get("name", "")] > 1:
                record_date = record.get("last_updated", "")[:10]
                record_label = f"{record_name} — {record_date}"
            else:
                record_label = record_name

            self.labels_by_id[record_id] = record_label

        self.selected_record_id = selected_record_id
        self.rebuild_visible_list()

    def set_selected_record(self, record_id):
        self.selected_record_id = record_id

        if record_id not in self.visible_record_ids:
            self.search_value.set("")

        self.refresh_row_colors()
        self.scroll_selected_record_into_view()

    def clear_selection(self):
        self.selected_record_id = None
        self.refresh_row_colors()

    def filter_records(self, *arguments):
        self.rebuild_visible_list()

    def rebuild_visible_list(self):
        search_text = self.search_value.get().casefold().strip()

        if search_text:
            visible_records = [
                record
                for record in self.records
                if search_text
                in self.labels_by_id[record["record_id"]].casefold()
            ]
        else:
            visible_records = self.records

        self.visible_record_ids = [
            record["record_id"] for record in visible_records
        ]
        self.hovered_record_id = None

        for row in self.rows_by_id.values():
            row.destroy()

        self.rows_by_id = {}
        wrap_length = max(120, self.list_canvas.winfo_width() - 24)

        for row_index, record_id in enumerate(self.visible_record_ids):
            row = tk.Label(
                self.list_frame,
                text=self.labels_by_id[record_id],
                bg=FIELD_BACKGROUND,
                fg=TEXT_DARK,
                font=app_font(10),
                anchor="nw",
                justify="left",
                wraplength=wrap_length,
                padx=10,
                pady=8,
                cursor="hand2",
            )
            row.grid(row=row_index, column=0, sticky="ew")
            row.bind(
                "<Button-1>",
                partial(self.handle_row_click, record_id),
            )
            row.bind(
                "<Enter>",
                partial(self.handle_row_enter, record_id),
            )
            row.bind(
                "<Leave>",
                partial(self.handle_row_leave, record_id),
            )
            row.bind("<MouseWheel>", self.handle_mousewheel)
            self.rows_by_id[record_id] = row

        visible_count = len(self.visible_record_ids)
        total_count = len(self.records)

        if visible_count == total_count:
            self.count_label.configure(text=f"{total_count} wands")
        else:
            self.count_label.configure(
                text=f"{visible_count} of {total_count} wands"
            )

        self.refresh_row_colors()
        self.update_scroll_region()
        self.scroll_selected_record_into_view()

    def handle_row_click(self, record_id, event=None):
        selection_accepted = self.selection_command(record_id)

        if selection_accepted is not False:
            self.selected_record_id = record_id

        self.refresh_row_colors()

    def handle_row_enter(self, record_id, event=None):
        self.hovered_record_id = record_id
        self.refresh_row_colors()

    def handle_row_leave(self, record_id, event=None):
        if self.hovered_record_id == record_id:
            self.hovered_record_id = None

        self.refresh_row_colors()

    def refresh_row_colors(self):
        theme_values = runtime_theme.get_values()

        for row_index, record_id in enumerate(self.visible_record_ids):
            row = self.rows_by_id[record_id]

            if record_id == self.selected_record_id:
                background = theme_values["SIDEBAR_TILE_SELECTED"]
            elif record_id == self.hovered_record_id:
                background = theme_values["LIST_HOVER"]
            else:
                background = alternating_row_background(
                    self.list_canvas,
                    theme_values,
                    row_index,
                )

            row.configure(
                bg=background,
                fg=theme_values["TEXT_DARK"],
            )

    def handle_canvas_resize(self, event):
        content_width = max(1, event.width - 2)
        self.list_canvas.itemconfigure(
            self.list_window,
            width=content_width,
        )
        wrap_length = max(120, content_width - 20)

        for row in self.rows_by_id.values():
            row.configure(wraplength=wrap_length)

        self.update_scroll_region()

    def update_scroll_region(self, event=None):
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox("all"))

    def handle_mousewheel(self, event):
        if event.delta:
            self.list_canvas.yview_scroll(
                int(-1 * (event.delta / 120)),
                "units",
            )

        return "break"

    def scroll_selected_record_into_view(self):
        row = self.rows_by_id.get(self.selected_record_id)

        if row is None:
            return

        self.update_idletasks()
        content_height = max(1, self.list_frame.winfo_height())
        viewport_top = self.list_canvas.canvasy(0)
        viewport_bottom = viewport_top + self.list_canvas.winfo_height()
        row_top = row.winfo_y()
        row_bottom = row_top + row.winfo_height()

        if row_top < viewport_top:
            self.list_canvas.yview_moveto(row_top / content_height)
        elif row_bottom > viewport_bottom:
            target_top = row_bottom - self.list_canvas.winfo_height()
            self.list_canvas.yview_moveto(target_top / content_height)

    def apply_theme(self, theme_values):
        self.list_canvas.configure(
            bg=theme_values["FIELD_BACKGROUND"],
            highlightbackground=theme_values["BORDER_SOFT"],
            highlightcolor=theme_values["BORDER_SOFT"],
        )
        self.list_frame.configure(bg=theme_values["FIELD_BACKGROUND"])
        self.refresh_row_colors()
