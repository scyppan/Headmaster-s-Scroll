import tkinter as tk
from tkinter import messagebox

from runtime_theme import bind_theme
from sections.wands.wands.controller import WandController
from sections.wands.wands.record_form import WandForm
from sections.wands.wands.record_list import WandList
from shared.widgets import RecordToolbar
from theme import (
    APP_BACKGROUND,
    BORDER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_MUTED,
    app_font,
)


class WandsPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.controller = WandController(database)
        self.records = []
        self.current_record_id = None
        self.form_dirty = False

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.toolbar = RecordToolbar(
            self,
            title="Wands",
            new_command=self.new_record,
            delete_command=self.delete_record,
            revert_command=self.revert_record,
            save_command=self.save_record,
        )
        self.toolbar.grid(row=0, column=0, sticky="ew")

        self.content_panes = tk.PanedWindow(
            self,
            orient="horizontal",
            bg=BORDER,
            borderwidth=0,
            sashwidth=6,
            sashrelief="flat",
            showhandle=False,
        )
        self.content_panes.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=25,
            pady=25,
        )
        bind_theme(self.content_panes, background="BORDER")

        self.list_card = tk.Frame(
            self.content_panes,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.list_card.grid_rowconfigure(0, weight=1)
        self.list_card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.list_card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.record_list = WandList(
            self.list_card,
            selection_command=self.select_record,
        )
        self.record_list.grid(row=0, column=0, sticky="nsew")

        self.form_card = tk.Frame(
            self.content_panes,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        self.form_card.grid_rowconfigure(0, weight=1)
        self.form_card.grid_columnconfigure(0, weight=1)
        bind_theme(
            self.form_card,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        self.record_form = WandForm(
            self.form_card,
            change_command=self.mark_form_dirty,
            preview_command=self.controller.preview_values,
        )
        self.record_form.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=22,
            pady=20,
        )

        self.content_panes.add(
            self.list_card,
            minsize=260,
            width=360,
        )
        self.content_panes.add(
            self.form_card,
            minsize=720,
        )

        self.status_value = tk.StringVar(value="Ready")
        self.status_bar = tk.Label(
            self,
            textvariable=self.status_value,
            bg=SURFACE_MUTED,
            fg=TEXT_MUTED,
            font=app_font(9),
            anchor="w",
            padx=12,
            pady=7,
        )
        self.status_bar.grid(row=2, column=0, sticky="ew")
        bind_theme(
            self.status_bar,
            background="SURFACE_MUTED",
            foreground="TEXT_MUTED",
        )

        self.refresh_reference_options()
        self.refresh_records()

        if self.records:
            self.load_record(self.records[0]["record_id"])
        else:
            self.new_record()

    def refresh_records(self, selected_record_id=None):
        self.records = self.controller.list_records()
        self.record_list.set_records(
            self.records,
            selected_record_id,
        )

    def refresh_reference_options(self):
        try:
            reference_names = self.controller.get_reference_names()
            self.record_form.set_reference_options(reference_names)
            self.record_form.refresh_preview()
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot load linked names",
                str(error),
                parent=self,
            )
            return False

        return True

    def on_show(self):
        self.refresh_reference_options()

    def load_record(self, record_id):
        record = self.controller.get_record(record_id)

        if record is None:
            return False

        self.current_record_id = record_id
        self.record_form.set_record(record)
        self.record_list.set_selected_record(record_id)
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=True)
        self.status_value.set(f"Loaded {record.get('name', 'wand')}")

        return True

    def select_record(self, record_id):
        if record_id == self.current_record_id:
            return True

        if not self.confirm_unsaved_changes():
            self.record_list.set_selected_record(self.current_record_id)
            return False

        return self.load_record(record_id)

    def new_record(self):
        if not self.confirm_unsaved_changes():
            return False

        self.current_record_id = None
        self.record_form.clear()
        self.record_list.clear_selection()
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=False)
        self.status_value.set("Creating a new wand")

        return True

    def save_record(self):
        record_values = self.record_form.get_values()

        try:
            if self.current_record_id is None:
                saved_record = self.controller.create_record(record_values)
            else:
                saved_record = self.controller.update_record(
                    self.current_record_id,
                    record_values,
                )
        except (TypeError, ValueError) as error:
            messagebox.showerror(
                "Cannot save wand",
                str(error),
                parent=self,
            )
            return False

        self.current_record_id = saved_record["record_id"]
        self.refresh_records(self.current_record_id)
        self.load_record(self.current_record_id)
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=True)
        self.status_value.set(f"Saved {saved_record['name']}")

        return True

    def delete_record(self):
        if self.current_record_id is None:
            self.record_form.clear()
            self.form_dirty = False
            self.toolbar.set_record_state(dirty=False, has_record=False)
            self.status_value.set("New wand cleared")
            return

        record = self.controller.get_record(self.current_record_id)
        record_name = record.get("name", "this wand")
        delete_confirmed = messagebox.askyesno(
            "Delete wand",
            f"Permanently delete {record_name}?",
            parent=self,
        )

        if not delete_confirmed:
            return

        self.controller.delete_record(self.current_record_id)
        self.current_record_id = None
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=False)
        self.refresh_records()

        if self.records:
            self.load_record(self.records[0]["record_id"])
        else:
            self.new_record()

        self.status_value.set(f"Deleted {record_name}")

    def revert_record(self):
        if self.current_record_id is None:
            self.record_form.clear()
            self.form_dirty = False
            self.toolbar.set_record_state(dirty=False, has_record=False)
            self.status_value.set("New wand cleared")
            return

        self.load_record(self.current_record_id)
        self.status_value.set("Changes reverted")

    def mark_form_dirty(self):
        self.form_dirty = True
        self.toolbar.set_record_state(
            dirty=True,
            has_record=self.current_record_id is not None,
        )
        self.status_value.set("Unsaved changes")

    def confirm_unsaved_changes(self):
        if not self.form_dirty:
            return True

        save_choice = messagebox.askyesnocancel(
            "Unsaved wand changes",
            "Save changes to this wand before continuing?",
            parent=self,
        )

        if save_choice is None:
            return False

        if save_choice:
            return self.save_record()

        self.form_dirty = False

        return True

    def can_leave(self):
        return self.confirm_unsaved_changes()
