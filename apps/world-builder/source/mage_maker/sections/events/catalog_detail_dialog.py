from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from mage_maker.ui.theme import (
    APP_BACKGROUND,
    PRIMARY,
    PRIMARY_DARK,
    PRIMARY_HOVER,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_LIGHT,
    app_font,
)
from mage_maker.ui.widgets import SoftButton


CATALOG_LABELS = {
    "spells": "spell",
    "proficiencies": "proficiency",
    "recipes": "recipe",
}


def dbm_source_directory():
    return Path(__file__).resolve().parents[5] / "dbm" / "source"


def load_catalog_editor_components():
    source_directory = dbm_source_directory()

    if not source_directory.is_dir():
        raise RuntimeError(
            "The DBM catalog editors could not be found at "
            f"{source_directory}."
        )

    source_text = str(source_directory)

    if source_text not in sys.path:
        sys.path.insert(0, source_text)

    from database.manager import JsonDatabase
    from sections.magic.proficiencies.page import ProficienciesPage
    from sections.magic.spells.page import SpellsPage
    from sections.nature_and_alchemy.recipes.page import RecipesPage

    return JsonDatabase, {
        "spells": SpellsPage,
        "proficiencies": ProficienciesPage,
        "recipes": RecipesPage,
    }


class CatalogDetailDialog(tk.Toplevel):
    """Open DBM's complete editor and return the saved stable record ID."""

    def __init__(
        self,
        parent,
        database_path,
        collection_name,
        record_id="",
    ):
        super().__init__(parent)
        self.result = None
        self.collection_name = str(collection_name or "")
        self.record_id = str(record_id or "")
        self.database = None
        self.page = None
        item_label = CATALOG_LABELS.get(self.collection_name, "catalog record")

        self.title(
            f"{'Edit' if self.record_id else 'Create'} {item_label} details"
        )
        self.configure(bg=APP_BACKGROUND)
        self.geometry("1280x820")
        self.minsize(1020, 680)
        self.transient(parent.winfo_toplevel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        try:
            database_class, page_classes = load_catalog_editor_components()
            page_class = page_classes[self.collection_name]
            self.database = database_class(database_path)
            self.database.load()
            self.page = page_class(
                self,
                self.database,
                record_saved_command=self.catalog_record_saved,
            )
        except (ImportError, KeyError, OSError, RuntimeError, ValueError) as error:
            self.after_idle(lambda: self.fail_to_open(item_label, error))
            return

        self.page.grid(row=0, column=0, sticky="nsew")

        if self.record_id:
            if not self.page.load_record(self.record_id):
                self.after_idle(
                    lambda: self.fail_to_open(
                        item_label,
                        ValueError(
                            f"The linked {item_label} no longer exists."
                        ),
                    )
                )
                return
        else:
            self.page.new_record()

        footer = tk.Frame(self, bg=SURFACE_MUTED, padx=12, pady=8)
        footer.grid(row=1, column=0, sticky="ew")
        footer.grid_columnconfigure(0, weight=1)

        tk.Label(
            footer,
            text=(
                "Saving in this editor adds the record to the catalog and "
                "links it to the invention event automatically."
            ),
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(9),
            anchor="w",
        ).grid(row=0, column=0, sticky="ew", padx=(0, 12))

        SoftButton(
            footer,
            text="Cancel",
            command=self.cancel,
            background=SURFACE_MUTED,
            fill=APP_BACKGROUND,
            hover_fill=PRIMARY_HOVER,
            foreground=TEXT_DARK,
            width=90,
            height=30,
            font=app_font(9, "bold"),
        ).grid(row=0, column=1, padx=(0, 6))

        try:
            self.state("zoomed")
        except tk.TclError:
            pass

        self.after_idle(self.activate)

    def activate(self):
        if not self.winfo_exists() or self.page is None:
            return
        self.grab_set()
        self.focus_force()

    def fail_to_open(self, item_label, error):
        if not self.winfo_exists():
            return
        messagebox.showerror(
            f"Cannot open {item_label} details",
            str(error),
            parent=self,
        )
        self.destroy()

    def save_and_link(self):
        if self.page is None or not self.page.save_record():
            return False

        return bool(self.result)

    def catalog_record_saved(self, record):
        """Return a newly committed DBM record directly to the event form."""

        if not isinstance(record, dict):
            return False

        record_id = str(record.get("record_id", "") or "").strip()

        if not record_id:
            messagebox.showerror(
                "Cannot link catalog record",
                "The details were saved, but the catalog did not return a "
                "stable record ID.",
                parent=self,
            )
            return False

        self.result = {
            "record_id": record_id,
            "collection": self.collection_name,
            "name": str(record.get("name", "") or "").strip(),
        }
        self.destroy()
        return True

    def cancel(self):
        if self.page is not None:
            confirm = getattr(self.page, "confirm_unsaved_changes", None)
            if callable(confirm) and not confirm():
                return False
        self.destroy()
        return True
