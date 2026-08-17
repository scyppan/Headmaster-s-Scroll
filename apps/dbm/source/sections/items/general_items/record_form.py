import tkinter as tk

from runtime_theme import bind_theme
from sections.items.general_items.bonus_editor import BonusEditor
from sections.items.general_items.constants import GENERAL_ITEM_TYPES
from sections.nature_and_alchemy.creatures.tag_editor import TagEditor
from shared.widgets import (
    ItemImageAssetField,
    ItemEffectEditor,
    MultilineField,
    RoundedEntry,
    RoundedSelect,
)
from theme import SURFACE, TEXT_DARK, TEXT_MUTED, app_font


class GeneralItemForm(tk.Frame):
    def __init__(self, parent, change_command, database=None):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.change_command = change_command
        self.loading_record = False
        self.database = database
        searching_methods = (
            database.get_collection("gathering_methods")
            if database is not None else []
        )
        self.searching_method_name_by_id = {
            str(record.get("record_id", "")): str(record.get("name", ""))
            for record in searching_methods
            if isinstance(record, dict)
            and record.get("record_id")
            and record.get("name")
        }
        self.searching_method_id_by_name = {
            name: record_id
            for record_id, name in self.searching_method_name_by_id.items()
        }

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(1, weight=2)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=1)

        self.identity_panel = tk.Frame(self, bg=SURFACE)
        self.identity_panel.grid(
            row=0,
            column=0,
            columnspan=2,
            sticky="ew",
            pady=(0, 12),
        )
        self.identity_panel.grid_configure(columnspan=3)
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

        self.base_knuts_label = tk.Label(
            self.identity_panel,
            text="Base Knuts",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        )
        self.base_knuts_label.grid(
            row=0,
            column=3,
            sticky="ew",
            padx=(10, 0),
        )
        bind_theme(
            self.base_knuts_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )
        self.base_knuts_value = tk.StringVar()
        self.base_knuts_value.trace_add("write", self.handle_base_knuts_change)
        self.base_knuts_entry = RoundedEntry(
            self.identity_panel,
            textvariable=self.base_knuts_value,
            background=SURFACE,
            height=42,
            font=app_font(11),
        )
        self.base_knuts_entry.grid(
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

        self.searching_method_panel = tk.Frame(
            self.identity_panel, bg=SURFACE
        )
        self.searching_method_panel.grid_columnconfigure(1, weight=1)
        bind_theme(self.searching_method_panel, background="SURFACE")
        self.searching_method_label = tk.Label(
            self.searching_method_panel,
            text="Searching Method",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        )
        self.searching_method_label.grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        bind_theme(
            self.searching_method_label,
            background="SURFACE",
            foreground="TEXT_DARK",
        )
        self.searching_method_value = tk.StringVar()
        self.searching_method_value.trace_add(
            "write", self.handle_searching_method_change
        )
        self.searching_method_select = RoundedSelect(
            self.searching_method_panel,
            variable=self.searching_method_value,
            values=tuple(self.searching_method_id_by_name),
            background=SURFACE,
            height=30,
            font=app_font(9),
            placeholder="Choose method",
        )
        self.searching_method_select.grid(row=0, column=1, sticky="ew")

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

        self.dbnotes_field = MultilineField(
            self,
            "DB Notes",
            self.handle_field_change,
            height=9,
        )
        self.dbnotes_field.grid(
            row=1,
            column=1,
            sticky="nsew",
            padx=(10, 0),
            pady=(0, 10),
        )

        self.tags_field = TagEditor(self, self.handle_field_change)
        self.tags_field.grid(
            row=1, column=2, sticky="nsew", padx=(10, 0), pady=(0, 10)
        )

        self.bonus_editor = BonusEditor(
            self,
            change_command=self.handle_field_change,
        )
        self.bonus_editor.grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="nsew",
        )
        self.bonus_editor.grid_configure(columnspan=3)

        self.effect_editor = ItemEffectEditor(
            self,
            database=self.database,
            change_command=self.handle_field_change,
        )
        self.effect_editor.grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="nsew",
            pady=(10, 0),
        )
        self.effect_editor.grid_configure(columnspan=3)

    def set_record(self, record):
        self.loading_record = True

        self.name_value.set(record.get("name", ""))
        self.type_value.set(record.get("type", "Other"))
        self.base_knuts_value.set(str(record.get("base_knuts", 0)))
        self.flight_threshold_value.set(
            str(record.get("flight_threshold", "") or "")
        )
        self.searching_method_value.set(
            self.searching_method_name_by_id.get(
                str(record.get("searching_method_id", "") or ""),
                "",
            )
        )
        self.update_special_fields_visibility()
        self.description_field.set_value(record.get("description", ""))
        self.bonus_editor.set_bonuses(record.get("bonuses", []))
        self.effect_editor.set_actions(record.get("actions", []))
        self.dbnotes_field.set_value(record.get("dbnotes", ""))
        self.tags_field.set_tags(record.get("tags", []))
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
        base_knuts_text = self.base_knuts_value.get().strip()
        if not base_knuts_text:
            raise ValueError("Base Knuts is required.")
        try:
            base_knuts = int(base_knuts_text)
        except ValueError as error:
            raise ValueError("Base Knuts must be a whole number.") from error
        if base_knuts < 0:
            raise ValueError("Base Knuts cannot be negative.")
        values = {
            "name": self.name_value.get().strip(),
            "type": self.type_value.get().strip(),
            "base_knuts": base_knuts,
            "description": self.description_field.get_value(),
            "bonuses": self.bonus_editor.get_bonuses(),
            "actions": self.effect_editor.get_actions(),
            "dbnotes": self.dbnotes_field.get_value(),
            "tags": self.tags_field.get_tags(),
            "image_asset": self.image_asset_field.get_value(),
            "flight_threshold": self.flight_threshold_value.get().strip(),
        }
        if values["type"] == "Raw Material":
            values["searching_method_id"] = (
                self.searching_method_id_by_name.get(
                    self.searching_method_value.get(), ""
                )
            )
        return values

    def handle_name_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_type_change(self, *arguments):
        self.update_special_fields_visibility()
        if not self.loading_record:
            self.change_command()

    def handle_base_knuts_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_flight_threshold_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def handle_searching_method_change(self, *arguments):
        if not self.loading_record:
            self.change_command()

    def update_special_fields_visibility(self):
        if self.type_value.get().strip() in {"Broom", "Flyable"}:
            self.flight_panel.grid(
                row=2,
                column=2,
                sticky="ew",
                padx=(10, 0),
                pady=(4, 0),
            )
        else:
            self.flight_panel.grid_remove()
        if self.type_value.get().strip() == "Raw Material":
            self.searching_method_panel.grid(
                row=2,
                column=2,
                columnspan=2,
                sticky="ew",
                padx=(10, 0),
                pady=(4, 0),
            )
        else:
            self.searching_method_panel.grid_remove()

    def handle_field_change(self):
        if not self.loading_record:
            self.change_command()
