import tkinter as tk

from runtime_theme import bind_theme
from sections.items.general_items.bonus_editor import BonusEditor
from sections.items.general_items.constants import GENERAL_ITEM_TYPES
from shared.widgets import (
    ItemImageAssetField,
    MultilineField,
    RoundedEntry,
    RoundedSelect,
)
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class GeneralItemForm(tk.Frame):
    magical_effect_values = ("", "Yes", "No")

    def __init__(self, parent, change_command, extraction_methods=()):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False
        self.extraction_methods = list(extraction_methods or ())
        self.extraction_method_by_name = {
            str(record.get("name", "")): str(record.get("record_id", ""))
            for record in self.extraction_methods
        }
        self.extraction_method_name_by_id = {
            record_id: name
            for name, record_id in self.extraction_method_by_name.items()
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=3)
        self.grid_rowconfigure(2, weight=2)

        self.identity_panel = tk.Frame(self, bg=SURFACE)
        self.identity_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )
        self.identity_panel.grid_columnconfigure(1, weight=3)
        self.identity_panel.grid_columnconfigure(2, weight=1)
        self.identity_panel.grid_columnconfigure(3, weight=1)
        bind_theme(self.identity_panel, background="SURFACE")

        self.name_label = tk.Label(
            self.identity_panel,
            text="Name",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.name_label.grid(
            row=0,
            column=1,
            sticky="ew",
            padx=(10, 10),
        )
        bind_theme(
            self.name_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.magical_effects_label = tk.Label(
            self.identity_panel,
            text="Has Magical Effects",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.magical_effects_label.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(10, 0),
        )
        bind_theme(
            self.magical_effects_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.name_value = tk.StringVar()
        self.name_value.trace_add("write", self.handle_name_change)
        self.name_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.name_value,
            background=SURFACE,
            height=42,
            font=app_font(12),
        )
        self.name_entry.grid(
            row=1,
            column=1,
            sticky="ew",
            padx=(10, 10),
            pady=(5, 0),
        )

        self.type_label = tk.Label(
            self.identity_panel,
            text="Type",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.type_label.grid(
            row=0,
            column=2,
            sticky="ew",
            padx=10,
        )
        bind_theme(
            self.type_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        self.type_value = tk.StringVar()
        self.type_value.trace_add("write", self.handle_type_change)
        self.type_select = RoundedSelect(
            self.identity_panel,
            variable=self.type_value,
            values=GENERAL_ITEM_TYPES,
            background=SURFACE,
            height=42,
            font=app_font(11),
            placeholder="Select type",
        )
        self.type_select.grid(
            row=1,
            column=2,
            sticky="ew",
            padx=10,
            pady=(5, 0),
        )

        self.magical_effects_value = tk.StringVar()
        self.magical_effects_value.trace_add(
            "write",
            self.handle_magical_effects_change,
        )
        self.magical_effects_select = RoundedSelect(
            self.identity_panel,
            variable=self.magical_effects_value,
            values=self.magical_effect_values,
            background=SURFACE,
            height=42,
            font=app_font(11),
            placeholder="Unspecified",
        )
        self.magical_effects_select.grid(
            row=1,
            column=3,
            sticky="ew",
            padx=(10, 0),
            pady=(5, 0),
        )

        self.last_updated_value = tk.StringVar(
            value="Last updated: Not yet saved"
        )
        self.last_updated_label = tk.Label(
            self.identity_panel,
            textvariable=self.last_updated_value,
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
        )
        self.last_updated_label.grid(
            row=2,
            column=1,
            sticky="ew",
            pady=(9, 0),
        )
        bind_theme(
            self.last_updated_label,
            background="SURFACE",
            foreground="TEXT_MUTED",
        )

        self.extraction_panel = tk.Frame(self.identity_panel, bg=SURFACE)
        self.extraction_panel.grid_columnconfigure(1, weight=1)
        bind_theme(self.extraction_panel, background="SURFACE")
        self.extraction_label = tk.Label(
            self.extraction_panel,
            text="Extraction",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        )
        self.extraction_label.grid(row=0, column=0, sticky="w", padx=(0, 6))
        bind_theme(
            self.extraction_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )
        self.extraction_method_value = tk.StringVar()
        self.extraction_method_value.trace_add(
            "write", self.handle_extraction_method_change
        )
        self.extraction_method_select = RoundedSelect(
            self.extraction_panel,
            variable=self.extraction_method_value,
            values=tuple(self.extraction_method_by_name),
            background=SURFACE,
            height=30,
            font=app_font(9),
            placeholder="Select method",
        )
        self.extraction_method_select.grid(
            row=0, column=1, sticky="ew"
        )

        self.flight_panel = tk.Frame(self.identity_panel, bg=SURFACE)
        self.flight_panel.grid_columnconfigure(1, weight=1)
        bind_theme(self.flight_panel, background="SURFACE")
        self.flight_threshold_label = tk.Label(
            self.flight_panel,
            text="Flying threshold",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        )
        self.flight_threshold_label.grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        bind_theme(
            self.flight_threshold_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )
        self.flight_threshold_value = tk.StringVar()
        self.flight_threshold_value.trace_add(
            "write", self.handle_flight_threshold_change
        )
        self.flight_threshold_entry = RoundedEntry(
            self.flight_panel,
            textvariable=self.flight_threshold_value,
            background=SURFACE,
            height=30,
            font=app_font(9),
        )
        self.flight_threshold_entry.grid(row=0, column=1, sticky="ew")

        self.image_asset_field = ItemImageAssetField(
            self.identity_panel,
            change_command=self.handle_field_change,
        )
        self.image_asset_field.grid(
            row=0,
            column=0,
            rowspan=3,
            sticky="nw",
        )

        self.description_field = MultilineField(
            self,
            "Description",
            self.handle_field_change,
            height=9,
        )
        self.description_field.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=(0, 10),
            pady=(0, 10),
        )

        self.bonus_editor = BonusEditor(
            self,
            change_command=self.handle_field_change,
        )
        self.bonus_editor.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(0, 10),
        )

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_field_change,
            height=7,
        )
        self.dbnotes_field.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )

    def set_record(self, record):
        self.loading_record = True

        self.name_value.set(record.get("name", ""))
        self.type_value.set(record.get("type", "Other"))
        self.magical_effects_value.set(
            record.get("has_magical_effects", "")
        )
        extraction_method_id = str(
            record.get("extraction_method_id", "")
            or next(iter(record.get("gathering_method_ids", []) or []), "")
        )
        self.extraction_method_value.set(
            self.extraction_method_name_by_id.get(
                extraction_method_id, extraction_method_id
            )
        )
        self.flight_threshold_value.set(
            str(record.get("flight_threshold", "") or "")
        )
        self.update_special_fields_visibility()
        self.description_field.set_value(record.get("description", ""))
        self.bonus_editor.set_bonuses(record.get("bonuses", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))
        self.image_asset_field.set_value(record.get("image_asset", ""))

        last_updated = record.get("last_updated", "")
        display_date = (
            last_updated.replace("T", " ")
            if last_updated
            else "Unknown"
        )
        self.last_updated_value.set(f"Last updated: {display_date}")

        self.loading_record = False

    def clear(self):
        self.set_record({})
        self.last_updated_value.set("Last updated: Not yet saved")
        self.name_entry.focus_set()

    def get_values(self):
        return {
            "name": self.name_value.get().strip(),
            "type": self.type_value.get().strip(),
            "has_magical_effects": self.magical_effects_value.get().strip(),
            "description": self.description_field.get_value(),
            "bonuses": self.bonus_editor.get_bonuses(),
            "dbnotes": self.dbnotes_field.get_value(),
            "image_asset": self.image_asset_field.get_value(),
            "extraction_method_id": self.extraction_method_by_name.get(
                self.extraction_method_value.get().strip(),
                self.extraction_method_value.get().strip(),
            ),
            "flight_threshold": self.flight_threshold_value.get().strip(),
        }

    def handle_name_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_magical_effects_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_type_change(self, *arguments):
        self.update_special_fields_visibility()
        if not self.loading_record:
            self.change_command()

    def handle_extraction_method_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_flight_threshold_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def update_special_fields_visibility(self):
        if self.type_value.get().strip() == "Alchemical":
            self.extraction_panel.grid(
                row=2,
                column=2,
                columnspan=2,
                sticky="ew",
                padx=(10, 0),
                pady=(4, 0),
            )
        else:
            self.extraction_panel.grid_remove()
        if self.type_value.get().strip() in {"Broom", "Flyable"}:
            self.flight_panel.grid(
                row=2,
                column=2,
                columnspan=2,
                sticky="ew",
                padx=(10, 0),
                pady=(4, 0),
            )
        else:
            self.flight_panel.grid_remove()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
