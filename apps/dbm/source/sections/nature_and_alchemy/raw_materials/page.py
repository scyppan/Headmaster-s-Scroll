import tkinter as tk
from tkinter import messagebox, ttk

from runtime_theme import bind_theme
from sections.nature_and_alchemy.raw_materials.controller import RawMaterialController
from shared.widgets import ItemImageAssetField, MultilineField, RecordToolbar, RoundedEntry, RoundedSelect
from theme import APP_BACKGROUND, BORDER, SURFACE, SURFACE_MUTED, TEXT_DARK, TEXT_MUTED, app_font


class RawMaterialsPage(tk.Frame):
    def __init__(self, parent, database):
        super().__init__(parent, bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")
        self.database = database
        self.controller = RawMaterialController(database)
        self.records = []
        self.current_record_id = None
        self.form_dirty = False
        self.loading = False
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.toolbar = RecordToolbar(self, title="Raw Materials", new_command=self.new_record, delete_command=self.delete_record, revert_command=self.revert_record, save_command=self.save_record)
        self.toolbar.grid(row=0, column=0, sticky="ew")
        panes = tk.PanedWindow(self, orient="horizontal", bg=BORDER, borderwidth=0, sashwidth=6)
        panes.grid(row=1, column=0, sticky="nsew", padx=25, pady=25)
        list_card = tk.Frame(panes, bg=SURFACE)
        list_card.grid_rowconfigure(1, weight=1)
        list_card.grid_columnconfigure(0, weight=1)
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", self.refresh_list)
        RoundedEntry(list_card, textvariable=self.search_value, background=SURFACE, height=38, font=app_font(10)).grid(row=0, column=0, sticky="ew", padx=12, pady=12)
        self.record_tree = ttk.Treeview(list_card, show="tree")
        self.record_tree.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.record_tree.bind("<<TreeviewSelect>>", self.select_record)
        form = tk.Frame(panes, bg=SURFACE)
        form.grid_columnconfigure(1, weight=1)
        form.grid_columnconfigure(2, weight=1)
        form.grid_rowconfigure(3, weight=1)
        bind_theme(form, background="SURFACE")
        self.image_field = ItemImageAssetField(form, change_command=self.mark_dirty)
        self.image_field.grid(row=0, column=0, rowspan=3, sticky="nw", padx=18, pady=18)
        self.name_value = tk.StringVar()
        self.category_value = tk.StringVar()
        self.knuts_value = tk.StringVar(value="0")
        self.quantity_value = tk.StringVar(value="1")
        for variable in (self.name_value, self.category_value, self.knuts_value, self.quantity_value):
            variable.trace_add("write", self.mark_dirty)
        self.add_entry(form, "Name", self.name_value, 0, 1)
        self.add_entry(form, "Category", self.category_value, 0, 2)
        self.add_entry(form, "Base Knuts", self.knuts_value, 1, 1)
        self.add_entry(form, "Default Quantity", self.quantity_value, 1, 2)
        methods = self.controller.searching_methods()
        self.method_id_by_name = {str(item.get("name", "")): str(item.get("record_id", "")) for item in methods}
        self.method_name_by_id = {value: key for key, value in self.method_id_by_name.items()}
        self.method_value = tk.StringVar()
        self.method_value.trace_add("write", self.mark_dirty)
        method_box = tk.Frame(form, bg=SURFACE)
        method_box.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(8, 18), pady=(0, 12))
        method_box.grid_columnconfigure(0, weight=1)
        tk.Label(method_box, text="Searching Method", bg=SURFACE, fg=TEXT_DARK, font=app_font(10), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))
        RoundedSelect(method_box, variable=self.method_value, values=tuple(self.method_id_by_name), background=SURFACE, height=38, font=app_font(10), placeholder="Select searching method").grid(row=1, column=0, sticky="ew")
        self.description = MultilineField(form, "Description", self.mark_dirty, height=10)
        self.description.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(18, 8), pady=(0, 18))
        self.notes = MultilineField(form, "DB Notes", self.mark_dirty, height=10)
        self.notes.grid(row=3, column=2, sticky="nsew", padx=(8, 18), pady=(0, 18))
        panes.add(list_card, minsize=220, width=285)
        panes.add(form, minsize=680)
        self.status_value = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self.status_value, bg=SURFACE_MUTED, fg=TEXT_MUTED, font=app_font(9), anchor="w", padx=12, pady=7).grid(row=2, column=0, sticky="ew")
        self.refresh_records()
        self.load_record(self.records[0]["record_id"]) if self.records else self.new_record()

    def add_entry(self, parent, label, variable, row, column):
        box = tk.Frame(parent, bg=SURFACE)
        box.grid(row=row, column=column, sticky="ew", padx=(8, 18), pady=(18 if row == 0 else 0, 12))
        box.grid_columnconfigure(0, weight=1)
        tk.Label(box, text=label, bg=SURFACE, fg=TEXT_DARK, font=app_font(10), anchor="w").grid(row=0, column=0, sticky="ew", pady=(0, 4))
        RoundedEntry(box, textvariable=variable, background=SURFACE, height=38, font=app_font(10)).grid(row=1, column=0, sticky="ew")

    def refresh_records(self, selected_id=None):
        self.records = self.controller.list_records()
        self.refresh_list()
        if selected_id and self.record_tree.exists(selected_id):
            self.record_tree.selection_set(selected_id)

    def refresh_list(self, *_args):
        query = self.search_value.get().strip().casefold()
        self.record_tree.delete(*self.record_tree.get_children())
        for record in self.records:
            searchable = f"{record.get('name', '')} {record.get('category', '')}".casefold()
            if query and query not in searchable:
                continue
            self.record_tree.insert("", "end", iid=str(record["record_id"]), text=str(record.get("name") or "Unnamed material"))

    def select_record(self, *_args):
        selected = self.record_tree.selection()
        if not selected or selected[0] == self.current_record_id:
            return
        if not self.confirm_unsaved_changes():
            if self.current_record_id:
                self.record_tree.selection_set(self.current_record_id)
            return
        self.load_record(selected[0])

    def load_record(self, record_id):
        record = self.controller.get_record(record_id)
        if record is None:
            return False
        self.loading = True
        self.current_record_id = record_id
        self.name_value.set(record.get("name", ""))
        self.category_value.set(record.get("category", ""))
        self.knuts_value.set(str(record.get("base_knuts", 0)))
        self.quantity_value.set(str(record.get("default_source_quantity", 1)))
        method_id = str(record.get("searching_method_id", "") or next(iter(record.get("gathering_method_ids", []) or []), ""))
        self.method_value.set(self.method_name_by_id.get(method_id, ""))
        self.description.set_value(record.get("description", ""))
        self.notes.set_value(record.get("dbnotes", ""))
        self.image_field.set_value(record.get("image_asset", ""))
        self.loading = False
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=True)
        self.record_tree.selection_set(record_id)
        self.status_value.set(f"Loaded {record.get('name', 'raw material')}")
        return True

    def values(self):
        try:
            knuts = int(self.knuts_value.get())
            quantity = int(self.quantity_value.get())
        except ValueError as error:
            raise ValueError("Base Knuts and quantity must be whole numbers.") from error
        return {"name": self.name_value.get(), "category": self.category_value.get(), "base_knuts": knuts, "default_source_quantity": quantity, "searching_method_id": self.method_id_by_name.get(self.method_value.get(), ""), "description": self.description.get_value(), "dbnotes": self.notes.get_value(), "image_asset": self.image_field.get_value()}

    def new_record(self):
        if not self.confirm_unsaved_changes():
            return False
        self.loading = True
        self.current_record_id = None
        self.name_value.set(""); self.category_value.set(""); self.knuts_value.set("0"); self.quantity_value.set("1"); self.method_value.set("")
        self.description.set_value(""); self.notes.set_value(""); self.image_field.set_value("")
        self.loading = False
        self.form_dirty = False
        self.toolbar.set_record_state(dirty=False, has_record=False)
        self.record_tree.selection_remove(self.record_tree.selection())
        self.status_value.set("Creating a raw material")
        return True

    def save_record(self):
        try:
            values = self.values()
            record = self.controller.create_record(values) if self.current_record_id is None else self.controller.update_record(self.current_record_id, values)
        except (TypeError, ValueError, KeyError) as error:
            messagebox.showerror("Cannot save raw material", str(error), parent=self)
            return False
        self.current_record_id = record["record_id"]
        self.refresh_records(self.current_record_id)
        self.load_record(self.current_record_id)
        return True

    def delete_record(self):
        if self.current_record_id is None:
            return self.new_record()
        record = self.controller.get_record(self.current_record_id) or {}
        if not messagebox.askyesno("Delete raw material", f"Permanently delete {record.get('name', 'this raw material')}?", parent=self):
            return
        self.controller.delete_record(self.current_record_id)
        self.current_record_id = None
        self.refresh_records()
        self.load_record(self.records[0]["record_id"]) if self.records else self.new_record()

    def revert_record(self):
        return self.load_record(self.current_record_id) if self.current_record_id else self.new_record()

    def mark_dirty(self, *_args):
        if self.loading:
            return
        self.form_dirty = True
        self.toolbar.set_record_state(dirty=True, has_record=self.current_record_id is not None)
        self.status_value.set("Unsaved changes")

    def confirm_unsaved_changes(self):
        if not self.form_dirty:
            return True
        choice = messagebox.askyesnocancel("Unsaved raw material", "Save changes before continuing?", parent=self)
        if choice is None:
            return False
        if choice:
            return self.save_record()
        self.form_dirty = False
        return True

    def can_leave(self):
        return self.confirm_unsaved_changes()
