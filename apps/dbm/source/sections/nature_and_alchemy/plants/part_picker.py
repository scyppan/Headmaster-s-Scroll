import tkinter as tk

from runtime_theme import bind_theme
from shared.widgets import SearchableRecordList, SoftButton
from theme import APP_BACKGROUND, BORDER, SURFACE, TEXT_DARK, app_font


class PlantPartCatalogPicker(tk.Toplevel):
    def __init__(self, parent, catalog_records, excluded_names):
        super().__init__(parent)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.selected_record = None
        self.records_by_id = {}
        normalized_excluded_names = {
            " ".join(str(name).split()).casefold()
            for name in excluded_names
        }

        for record in catalog_records:
            normalized_name = " ".join(
                str(record.get("name", "")).split()
            ).casefold()

            if normalized_name not in normalized_excluded_names:
                self.records_by_id[record["record_id"]] = record

        self.title("Add Plant Part from Catalog")
        self.geometry("640x560")
        self.minsize(500, 420)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.heading = tk.Label(
            self,
            text="Choose a Plant Part",
            bg=APP_BACKGROUND,
            fg=TEXT_DARK,
            font=app_font(16),
            anchor="w",
        )
        self.heading.grid(
            row=0,
            column=0,
            sticky="ew",
            padx=22,
            pady=(18, 12),
        )
        bind_theme(
            self.heading,
            background="APP_BACKGROUND",
            foreground="TEXT_DARK",
        )

        self.list_card = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.list_card.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=22,
        )
        self.list_card.grid_rowconfigure(0, weight=1)
        self.list_card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.list_card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.record_list = SearchableRecordList(
            self.list_card,
            selection_command=self.select_record,
            heading_text="Plant Part Catalog",
            item_word="parts",
            unnamed_label="Unnamed plant part",
        )
        self.record_list.grid(row=0, column=0, sticky="nsew")
        self.record_list.set_records(
            sorted(
                self.records_by_id.values(),
                key=lambda record: record.get("name", "").casefold(),
            )
        )
        self.record_list.listbox.bind(
            "<Double-Button-1>",
            self.accept,
            add="+",
        )

        self.button_row = tk.Frame(self, bg=APP_BACKGROUND)
        self.button_row.grid(
            row=2,
            column=0,
            sticky="e",
            padx=22,
            pady=18,
        )
        bind_theme(self.button_row, background="APP_BACKGROUND")

        self.cancel_button = SoftButton(
            self.button_row,
            text="Cancel",
            command=self.cancel,
            width=90,
            height=36,
        )
        self.cancel_button.pack(side="left", padx=(0, 6))

        self.add_button = SoftButton(
            self.button_row,
            text="Add Part",
            command=self.accept,
            width=100,
            height=36,
        )
        self.add_button.pack(side="left")
        self.add_button.set_enabled(False)

        self.bind("<Escape>", self.cancel)
        self.bind("<Return>", self.accept)
        self.grab_set()
        self.record_list.search_entry.focus_set()

    def select_record(self, record_id):
        self.record_list.selected_record_id = record_id
        self.add_button.set_enabled(record_id in self.records_by_id)

        return True

    def accept(self, event=None):
        record_id = self.record_list.selected_record_id

        if record_id not in self.records_by_id:
            return "break"

        self.selected_record = self.records_by_id[record_id]
        self.destroy()

        return "break"

    def cancel(self, event=None):
        self.selected_record = None
        self.destroy()

        return "break"
