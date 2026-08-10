import tkinter as tk
from tkinter import messagebox

from runtime_theme import bind_theme
from sections.nature_and_alchemy.creatures.controller import (
    CreatureController,
)
from sections.nature_and_alchemy.creatures.record_form import CreatureForm
from sections.nature_and_alchemy.creatures.record_list import CreatureList
from shared.widgets import RecordToolbar
from theme import (
    APP_BACKGROUND,
    BORDER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_MUTED,
    app_font,
)


class CreaturesPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.database = database
        self.controller = CreatureController(database)
        self.records = []
        self.current_record_id = None
        self.form_dirty = False

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self.toolbar = RecordToolbar(
            self,
            title="Creatures",
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

        self.record_list = CreatureList(
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

        self.record_form = CreatureForm(
            self.form_card,
            self.database,
            change_command=self.mark_form_dirty,
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
            minsize=220,
            width=280,
        )
        self.content_panes.add(
            self.form_card,
            minsize=780,
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

    def load_record(self, record_id):
        record = self.controller.get_record(record_id)

        if record is None:
            return False

        self.current_record_id = record_id
        self.record_form.set_record(record)
        self.record_list.set_selected_record(record_id)
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=True)
        self.status_value.set(f"Loaded {record.get('name', 'creature')}")

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
        self.status_value.set("Creating a new creature")

        return True

    def save_record(self):
        try:
            record_values = self.record_form.get_values()
        except ValueError as error:
            messagebox.showerror(
                "Invalid value",
                str(error),
                parent=self,
            )
            return False

        if not record_values["name"]:
            messagebox.showerror(
                "Name required",
                "A creature must have a name.",
                parent=self,
            )
            return False

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
                "Cannot save creature",
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
            self.status_value.set("New creature cleared")
            return

        record = self.controller.get_record(self.current_record_id)
        record_name = record.get("name", "this creature")
        delete_confirmed = messagebox.askyesno(
            "Delete creature",
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
            self.status_value.set("New creature cleared")
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
            "Unsaved creature changes",
            "Save changes to this creature before continuing?",
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
