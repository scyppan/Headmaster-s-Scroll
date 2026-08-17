from __future__ import annotations

from copy import deepcopy
import tkinter as tk
from tkinter import messagebox, ttk
from uuid import uuid4

from runtime_theme import bind_theme
from theme import (
    BORDER,
    SURFACE,
    SURFACE_MUTED,
    TEXT_DARK,
    TEXT_MUTED,
    app_font,
)


class SearchingMethodsView(tk.Frame):
    """Compact canonical editor for item searching methods."""

    def __init__(self, parent, controller, dirty_command):
        super().__init__(parent, bg=SURFACE)
        bind_theme(self, background="SURFACE")

        self.controller = controller
        self.dirty_command = dirty_command
        self.loading_values = False
        self.form_dirty = False
        self.methods = []
        self.selected_method_id = None

        self.name_value = tk.StringVar()
        self.description_value = tk.StringVar()
        self.name_value.trace_add("write", self.handle_field_change)
        self.description_value.trace_add("write", self.handle_field_change)

        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)

        heading = tk.Label(
            self,
            text="Searching Methods",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(18),
            anchor="w",
        )
        heading.grid(row=0, column=0, sticky="ew", padx=30, pady=(30, 12))
        bind_theme(heading, background="SURFACE", foreground="TEXT_DARK")

        workspace = tk.Frame(
            self,
            bg=SURFACE,
            highlightbackground=BORDER,
            highlightthickness=1,
        )
        workspace.grid(row=1, column=0, sticky="nsew", padx=30, pady=(0, 30))
        workspace.grid_rowconfigure(0, weight=1)
        workspace.grid_columnconfigure(1, weight=1)
        bind_theme(
            workspace,
            background="SURFACE",
            highlightbackground="BORDER",
        )

        list_panel = tk.Frame(workspace, bg=SURFACE_MUTED, width=280)
        list_panel.grid(row=0, column=0, sticky="nsw")
        list_panel.grid_propagate(False)
        list_panel.grid_rowconfigure(1, weight=1)
        list_panel.grid_columnconfigure(0, weight=1)
        bind_theme(list_panel, background="SURFACE_MUTED")

        list_header = tk.Frame(list_panel, bg=SURFACE_MUTED)
        list_header.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        bind_theme(list_header, background="SURFACE_MUTED")
        tk.Label(
            list_header,
            text="Methods",
            bg=SURFACE_MUTED,
            fg=TEXT_DARK,
            font=app_font(10, "bold"),
        ).pack(side="left")
        ttk.Button(
            list_header,
            text="+",
            width=3,
            command=self.add_method,
        ).pack(side="right")
        ttk.Button(
            list_header,
            text="−",
            width=3,
            command=self.delete_method,
        ).pack(side="right", padx=(0, 4))

        self.method_tree = ttk.Treeview(
            list_panel,
            show="tree",
            selectmode="browse",
        )
        self.method_tree.grid(
            row=1,
            column=0,
            sticky="nsew",
            padx=8,
            pady=(0, 8),
        )
        self.method_tree.bind("<<TreeviewSelect>>", self.select_method)

        editor = tk.Frame(workspace, bg=SURFACE)
        editor.grid(row=0, column=1, sticky="nsew", padx=24, pady=20)
        editor.grid_columnconfigure(0, weight=1)
        bind_theme(editor, background="SURFACE")

        self.editor_title = tk.Label(
            editor,
            text="Select a method",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(15),
            anchor="w",
        )
        self.editor_title.grid(row=0, column=0, sticky="ew", pady=(0, 18))
        bind_theme(
            self.editor_title,
            background="SURFACE",
            foreground="TEXT_DARK",
        )

        tk.Label(
            editor,
            text="Name",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew")
        self.name_entry = ttk.Entry(editor, textvariable=self.name_value)
        self.name_entry.grid(row=2, column=0, sticky="ew", pady=(4, 14))

        tk.Label(
            editor,
            text="Description",
            bg=SURFACE,
            fg=TEXT_DARK,
            font=app_font(10),
            anchor="w",
        ).grid(row=3, column=0, sticky="ew")
        self.description_entry = ttk.Entry(
            editor,
            textvariable=self.description_value,
        )
        self.description_entry.grid(row=4, column=0, sticky="ew", pady=(4, 14))

        note = tk.Label(
            editor,
            text=(
                "Assign a Searching Method from the applicable item record. "
                "This page only manages the reusable method names."
            ),
            bg=SURFACE,
            fg=TEXT_MUTED,
            font=app_font(10),
            justify="left",
            anchor="nw",
            wraplength=620,
        )
        note.grid(row=5, column=0, sticky="ew", pady=(12, 0))
        bind_theme(note, background="SURFACE", foreground="TEXT_MUTED")

        self.set_editor_enabled(False)
        self.load_values()

    def load_values(self):
        self.loading_values = True
        self.methods = self.controller.load_searching_methods()
        self.selected_method_id = None
        self.name_value.set("")
        self.description_value.set("")
        self.refresh_tree()
        self.editor_title.configure(text="Select a method")
        self.set_editor_enabled(False)
        self.loading_values = False
        self.form_dirty = False
        return "Searching methods loaded"

    def save_values(self):
        self.commit_editor_values()
        names = [str(method.get("name", "")).strip() for method in self.methods]
        if any(not name for name in names):
            messagebox.showerror(
                "Name required",
                "Every searching method needs a name.",
                parent=self,
            )
            return False
        if len({name.casefold() for name in names}) != len(names):
            messagebox.showerror(
                "Duplicate name",
                "Every searching method needs a unique name.",
                parent=self,
            )
            return False

        self.methods = self.controller.save_searching_methods(self.methods)
        self.form_dirty = False
        self.refresh_tree()
        return "Searching methods saved"

    def has_unsaved_changes(self):
        return self.form_dirty

    def mark_dirty(self):
        if self.loading_values:
            return
        if not self.form_dirty:
            self.form_dirty = True
            self.dirty_command()

    def handle_field_change(self, *_args):
        if self.loading_values or self.selected_method_id is None:
            return
        self.commit_editor_values()
        self.mark_dirty()
        self.refresh_tree(keep_selection=True)

    def commit_editor_values(self):
        method = self.selected_method()
        if method is None:
            return
        method["name"] = self.name_value.get().strip()
        method["description"] = self.description_value.get().strip()

    def selected_method(self):
        return next(
            (
                method
                for method in self.methods
                if str(method.get("record_id")) == self.selected_method_id
            ),
            None,
        )

    def refresh_tree(self, keep_selection=False):
        selected_id = self.selected_method_id if keep_selection else None
        self.method_tree.delete(*self.method_tree.get_children())
        for method in self.methods:
            method_id = str(method.get("record_id"))
            self.method_tree.insert(
                "",
                "end",
                iid=method_id,
                text=str(method.get("name") or "Unnamed method"),
            )
        if selected_id and self.method_tree.exists(selected_id):
            self.method_tree.selection_set(selected_id)

    def add_method(self):
        self.commit_editor_values()
        method = {
            "record_id": str(uuid4()),
            "name": "New searching method",
            "description": "",
        }
        self.methods.append(method)
        self.selected_method_id = str(method["record_id"])
        self.refresh_tree(keep_selection=True)
        self.show_selected_method()
        self.mark_dirty()
        self.name_entry.focus_set()
        self.name_entry.selection_range(0, "end")

    def delete_method(self):
        method = self.selected_method()
        if method is None:
            return
        method_id = str(method.get("record_id"))
        if self.method_is_used(method_id):
            messagebox.showerror(
                "Method in use",
                "Choose another Searching Method on the linked items before deleting this one.",
                parent=self,
            )
            return
        self.methods = [
            item
            for item in self.methods
            if str(item.get("record_id")) != method_id
        ]
        self.selected_method_id = None
        self.refresh_tree()
        self.loading_values = True
        self.name_value.set("")
        self.description_value.set("")
        self.loading_values = False
        self.editor_title.configure(text="Select a method")
        self.set_editor_enabled(False)
        self.mark_dirty()

    def method_is_used(self, method_id):
        def contains(value):
            if isinstance(value, dict):
                if str(value.get("extraction_method_id", "")) == method_id:
                    return True
                if method_id in {
                    str(item)
                    for item in value.get("gathering_method_ids", []) or []
                }:
                    return True
                return any(contains(item) for item in value.values())
            if isinstance(value, list):
                return any(contains(item) for item in value)
            return False

        return contains(self.controller.database.data)

    def select_method(self, *_args):
        selected = self.method_tree.selection()
        if not selected:
            return
        self.commit_editor_values()
        self.selected_method_id = selected[0]
        self.show_selected_method()

    def show_selected_method(self):
        method = self.selected_method()
        if method is None:
            return
        self.loading_values = True
        self.name_value.set(str(method.get("name", "")))
        self.description_value.set(str(method.get("description", "")))
        self.loading_values = False
        self.editor_title.configure(text="Method details")
        self.set_editor_enabled(True)

    def set_editor_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        self.name_entry.configure(state=state)
        self.description_entry.configure(state=state)
