import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import MultilineField, RoundedEntry, RoundedSelect, RoundedText
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class WandForm(tk.Frame):
    def __init__(self, parent, change_command, preview_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.preview_command = preview_command
        self.loading_record = False
        self.effect_labels = []

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.selection_panel = tk.Frame(self, bg=SURFACE)
        self.selection_panel.grid(row=0, column=0, sticky="ew")
        self.selection_panel.bind(
            "<Configure>",
            self.handle_selection_panel_resize,
        )
        bind_theme(self.selection_panel, background="SURFACE")

        for column_index in range(4):
            self.selection_panel.grid_columnconfigure(column_index, weight=1)

        self.maker_value = tk.StringVar()
        self.quality_value = tk.StringVar()
        self.wood_value = tk.StringVar()
        self.core_value = tk.StringVar()
        self.quality_effect_value = tk.StringVar()
        self.wood_effect_value = tk.StringVar()
        self.core_effect_value = tk.StringVar()

        self.maker_select = self.create_select(
            0,
            "Wand Maker",
            self.maker_value,
        )
        self.quality_select = self.create_select(
            1,
            "Wand Quality",
            self.quality_value,
            self.quality_effect_value,
        )
        self.wood_select = self.create_select(
            2,
            "Wand Wood",
            self.wood_value,
            self.wood_effect_value,
        )
        self.core_select = self.create_select(
            3,
            "Wand Core",
            self.core_value,
            self.core_effect_value,
        )

        self.maker_value.trace_add("write", self.handle_selection_change)
        self.quality_value.trace_add("write", self.handle_selection_change)
        self.wood_value.trace_add("write", self.handle_selection_change)
        self.core_value.trace_add("write", self.handle_selection_change)

        self.name_panel = tk.Frame(self, bg=SURFACE)
        self.name_panel.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        self.name_panel.grid_columnconfigure(0, weight=1)
        bind_theme(self.name_panel, background="SURFACE")

        self.name_label = self.create_label(
            self.name_panel,
            "Generated Name",
        )
        self.name_label.grid(row=0, column=0, sticky="ew")

        self.name_display = RoundedText(
            self.name_panel,
            background=SURFACE,
            height=2,
            font=app_font(11),
        )
        self.name_display.grid(row=1, column=0, sticky="ew")
        self.name_display.scrollbar.grid_remove()
        self.name_display.text.configure(
            state="disabled",
            cursor="arrow",
            takefocus=0,
        )

        self.last_updated_value = tk.StringVar(
            value="Last updated: Not yet saved"
        )
        self.last_updated_label = tk.Label(
            self.name_panel,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.last_updated_label.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(8, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.pricing_panel = tk.Frame(self, bg=SURFACE)
        self.pricing_panel.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(14, 0),
        )
        bind_theme(self.pricing_panel, background="SURFACE")

        for column_index in range(5):
            self.pricing_panel.grid_columnconfigure(column_index, weight=1)

        self.multiplier_value = tk.StringVar()
        self.core_base_value = tk.StringVar()
        self.wood_base_value = tk.StringVar()
        self.quality_base_value = tk.StringVar()
        self.total_value = tk.StringVar()

        self.multiplier_entry = self.create_readonly_entry(
            0,
            "Maker Multiplier",
            self.multiplier_value,
        )
        self.core_base_entry = self.create_readonly_entry(
            1,
            "Core Base Knuts",
            self.core_base_value,
        )
        self.wood_base_entry = self.create_readonly_entry(
            2,
            "Wood Base Knuts",
            self.wood_base_value,
        )
        self.quality_base_entry = self.create_readonly_entry(
            3,
            "Quality Base Knuts",
            self.quality_base_value,
        )
        self.total_entry = self.create_readonly_entry(
            4,
            "Total Knuts",
            self.total_value,
        )

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_field_change,
            height=5,
        )
        self.dbnotes_field.grid(
            row=3,
            column=0,
            sticky="nsew",
            pady=(14, 0),
        )

    def create_select(
        self,
        column_index,
        label_text,
        variable,
        effect_variable=None,
    ):
        label = self.create_label(self.selection_panel, label_text)
        label.grid(
            row=0,
            column=column_index,
            sticky="ew",
            padx=(0 if column_index == 0 else 7, 0 if column_index == 3 else 7),
        )

        select = RoundedSelect(
            self.selection_panel,
            variable=variable,
            values=[],
            background=SURFACE,
            height=42,
            font=app_font(10),
            placeholder=f"Select {label_text.lower()}",
        )
        select.grid(
            row=1,
            column=column_index,
            sticky="ew",
            padx=(0 if column_index == 0 else 7, 0 if column_index == 3 else 7),
        )

        if effect_variable is not None:
            effect_label = tk.Label(
                self.selection_panel,
                textvariable=effect_variable,
                bg=SURFACE,
                fg=TEXT_MUTED,
                font=app_font(9),
                anchor="nw",
                justify="left",
                wraplength=205,
                padx=3,
                pady=0,
            )
            effect_label.grid(
                row=2,
                column=column_index,
                sticky="new",
                padx=(
                    0 if column_index == 0 else 7,
                    0 if column_index == 3 else 7,
                ),
                pady=(7, 0),
            )
            bind_theme(
                effect_label,
                background="SURFACE",
                foreground="TEXT_MUTED",
            )
            self.effect_labels.append(effect_label)

        return select

    def handle_selection_panel_resize(self, event):
        effect_wrap_length = max(110, (event.width // 4) - 22)

        for effect_label in self.effect_labels:
            effect_label.configure(wraplength=effect_wrap_length)

    def create_readonly_entry(self, column_index, label_text, variable):
        label = self.create_label(self.pricing_panel, label_text)
        label.grid(
            row=0,
            column=column_index,
            sticky="ew",
            padx=(0 if column_index == 0 else 6, 0 if column_index == 4 else 6),
        )

        entry = RoundedEntry(
            self.pricing_panel,
            textvariable=variable,
            background=SURFACE,
            height=40,
            justify="center",
            font=app_font(10),
        )
        entry.grid(
            row=1,
            column=column_index,
            sticky="ew",
            padx=(0 if column_index == 0 else 6, 0 if column_index == 4 else 6),
        )
        entry.set_enabled(False)

        return entry

    def create_label(self, parent, text):
        label = tk.Label(
            parent,
            text=text,
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        bind_theme(
            label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        return label

    def set_reference_options(self, reference_names):
        self.maker_select.set_values(reference_names.get("maker_name", []))
        self.core_select.set_values(reference_names.get("core_name", []))
        self.wood_select.set_values(reference_names.get("wood_name", []))
        self.quality_select.set_values(reference_names.get("quality_name", []))

    def set_record(self, record):
        self.loading_record = True
        self.maker_value.set(record.get("maker_name", ""))
        self.core_value.set(record.get("core_name", ""))
        self.wood_value.set(record.get("wood_name", ""))
        self.quality_value.set(record.get("quality_name", ""))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))

        last_updated = record.get("last_updated", "")
        display_date = (
            last_updated.replace("T", " ")
            if last_updated
            else "Unknown"
        )
        self.last_updated_value.set(f"Last updated: {display_date}")
        self.update_preview()
        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")
        self.maker_select.canvas.focus_set()

    def get_values(self):
        return {
            "maker_name": self.maker_value.get().strip(),
            "core_name": self.core_value.get().strip(),
            "wood_name": self.wood_value.get().strip(),
            "quality_name": self.quality_value.get().strip(),
            "dbnotes": self.dbnotes_field.get_value(),
        }

    def refresh_preview(self):
        self.update_preview()

    def update_preview(self):
        try:
            preview = self.preview_command(self.get_values())
        except (TypeError, ValueError):
            preview = {
                "name": "",
                "maker_multiplier": None,
                "core_base_knuts": None,
                "wood_base_knuts": None,
                "quality_base_knuts": None,
                "total_knuts": None,
                "core_effect": "",
                "wood_effect": "",
                "quality_effect": "",
            }

        self.set_name_value(preview.get("name", ""))
        self.multiplier_value.set(
            self.format_number(preview.get("maker_multiplier"))
        )
        self.core_base_value.set(
            self.format_number(preview.get("core_base_knuts"))
        )
        self.wood_base_value.set(
            self.format_number(preview.get("wood_base_knuts"))
        )
        self.quality_base_value.set(
            self.format_number(preview.get("quality_base_knuts"))
        )
        self.total_value.set(
            self.format_number(preview.get("total_knuts"))
        )
        self.core_effect_value.set(preview.get("core_effect", ""))
        self.wood_effect_value.set(preview.get("wood_effect", ""))
        self.quality_effect_value.set(preview.get("quality_effect", ""))

    def set_name_value(self, value):
        self.name_display.text.configure(state="normal")
        self.name_display.text.delete("1.0", "end")
        self.name_display.text.insert("1.0", value or "")
        self.name_display.text.edit_modified(False)
        self.name_display.text.configure(state="disabled")

    def format_number(self, value):
        if value is None:
            return ""

        numeric_value = float(value)

        if numeric_value.is_integer():
            return f"{int(numeric_value):,}"

        return f"{numeric_value:,.4f}".rstrip("0").rstrip(".")

    def handle_selection_change(self, *arguments):
        self.update_preview()

        if not self.loading_record:
            self.change_command()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
