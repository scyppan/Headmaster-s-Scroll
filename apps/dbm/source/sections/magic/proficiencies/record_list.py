import tkinter as tk
from functools import partial

from runtime_theme import bind_theme, runtime_theme
from sections.magic.proficiencies.filter_dialog import (
    EMPTY_PROFICIENCY_FILTERS,
    ProficiencyFilterDialog,
)
from shared.widgets import (
    RoundedEntry,
    SoftButton,
    alternating_row_background,
)
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


class ProficiencyList(tk.Frame):
    def __init__(self, parent, selection_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.selection_command = selection_command
        self.records = []
        self.visible_record_ids = []
        self.labels_by_id = {}
        self.search_text_by_id = {}
        self.rows_by_id = {}
        self.selected_record_id = None
        self.hovered_record_id = None
        self.active_filters = dict(EMPTY_PROFICIENCY_FILTERS)

        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="All Proficiencies",
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

        self.filter_button = SoftButton(
            self,
            text="Filter",
            command=self.open_filter_dialog,
            background=SURFACE,
            width=88,
            height=32,
            font=app_font(9),
            background_role="SURFACE",
        )
        self.filter_button.place(
            relx=1,
            x=-16,
            y=12,
            anchor="ne",
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
            text="0 proficiencies",
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
        self.update_filter_button()

    @staticmethod
    def build_display_text(record):
        proficiency_name = (
            str(record.get("name", "")).strip() or "Unnamed proficiency"
        )
        skill = str(record.get("skill", "")).strip() or "Unspecified skill"
        threshold = record.get("threshold")
        threshold_text = "—" if threshold in (None, "") else str(threshold)
        tradition = str(record.get("tradition", "")).strip()
        tradition_text = f" ({tradition})" if tradition else ""

        return (
            f"{proficiency_name}\n"
            f"{skill} {threshold_text}{tradition_text}"
        )

    @staticmethod
    def build_search_text(record):
        return " ".join(
            str(value)
            for value in (
                record.get("name", ""),
                record.get("tradition", ""),
                record.get("skill", ""),
                record.get("threshold", ""),
                " ".join(
                    " ".join(
                        (
                            str(material.get("name", "")),
                            str(material.get("type", "")),
                            str(material.get("quantity", "")),
                        )
                    )
                    for material in record.get("required_materials", [])
                    if isinstance(material, dict)
                ),
                record.get("description", ""),
                record.get("history", ""),
                " ".join(str(tag) for tag in record.get("tags", [])),
            )
        ).casefold()

    @staticmethod
    def record_matches_filters(record, filters):
        selected_skills = filters.get("skills", ())

        if selected_skills and record.get("skill", "") not in selected_skills:
            return False

        selected_traditions = filters.get("traditions", ())

        if (
            selected_traditions
            and record.get("tradition", "") not in selected_traditions
        ):
            return False

        threshold = record.get("threshold")
        minimum_threshold = filters.get("minimum_threshold")
        maximum_threshold = filters.get("maximum_threshold")

        if minimum_threshold is not None:
            if not isinstance(threshold, int) or threshold < minimum_threshold:
                return False

        if maximum_threshold is not None:
            if not isinstance(threshold, int) or threshold > maximum_threshold:
                return False

        selected_tags = {
            str(tag).casefold() for tag in filters.get("tags", ())
        }
        record_tags = {
            str(tag).casefold() for tag in record.get("tags", [])
        }

        if selected_tags and not selected_tags.intersection(record_tags):
            return False

        return True

    def set_records(self, records, selected_record_id=None):
        self.records = records
        self.labels_by_id = {
            record["record_id"]: self.build_display_text(record)
            for record in records
        }
        self.search_text_by_id = {
            record["record_id"]: self.build_search_text(record)
            for record in records
        }
        self.selected_record_id = selected_record_id
        self.rebuild_visible_list()

    def set_selected_record(self, record_id):
        self.selected_record_id = record_id

        if record_id not in self.visible_record_ids and self.search_value.get():
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
        visible_records = [
            record
            for record in self.records
            if self.record_matches_filters(record, self.active_filters)
            and (
                not search_text
                or search_text
                in self.search_text_by_id[record["record_id"]]
            )
        ]
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
                pady=7,
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
            self.count_label.configure(text=f"{total_count} proficiencies")
        else:
            self.count_label.configure(
                text=f"{visible_count} of {total_count} proficiencies"
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

    def open_filter_dialog(self):
        dialog = ProficiencyFilterDialog(
            self,
            self.records,
            self.active_filters,
        )
        self.wait_window(dialog)

        if dialog.result is None:
            return

        self.active_filters = dialog.result
        self.update_filter_button()
        self.rebuild_visible_list()

    def update_filter_button(self):
        active_filter_count = sum(
            (
                bool(self.active_filters.get("skills")),
                bool(self.active_filters.get("traditions")),
                self.active_filters.get("minimum_threshold") is not None
                or self.active_filters.get("maximum_threshold") is not None,
                bool(self.active_filters.get("tags")),
            )
        )

        if active_filter_count:
            self.filter_button.set_text(f"Filter ({active_filter_count})")
            self.filter_button.set_theme_roles(
                "PRIMARY",
                "PRIMARY_DARK",
                "TEXT_DARK",
            )
        else:
            self.filter_button.set_text("Filter")
            self.filter_button.set_theme_roles(
                "BUTTON_SOFT",
                "BUTTON_SOFT_HOVER",
                "TEXT_DARK",
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
