from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from uuid import uuid4

from headmasters_scroll.region_interactions import CATALOG_COLLECTIONS


def display_name(record):
    return str(record.get("name") or record.get("title") or "Untitled")


class GatheringMethodsPage(tk.Frame):
    """One searchable workspace for gathering methods and catalog stock defaults."""

    def __init__(self, parent, database):
        super().__init__(parent, bg="#ead9aa")
        self.database = database
        self.query = tk.StringVar()
        self.method_name = tk.StringVar()
        self.method_description = tk.StringVar()
        self.quantity = tk.StringVar(value="1")
        self.selected_record = None
        self.method_variables = {}
        self.grid_rowconfigure(1, weight=1)
        self.grid_columnconfigure(0, weight=1)
        header = tk.Frame(self, bg="#ead9aa")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=9)
        tk.Label(header, text="Gathering & Stock", bg="#ead9aa", font=("Georgia", 17, "bold")).pack(side="left")
        ttk.Button(header, text="Save", command=self.save).pack(side="right")
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.build_methods(panes)
        self.build_assignments(panes)
        self.refresh_methods()
        self.refresh_records()

    def build_methods(self, panes):
        panel = ttk.LabelFrame(panes, text="Gathering methods", padding=8)
        panes.add(panel, weight=1)
        self.method_tree = ttk.Treeview(panel, show="tree", height=12)
        self.method_tree.pack(fill="both", expand=True)
        self.method_tree.bind("<<TreeviewSelect>>", self.select_method)
        row = ttk.Frame(panel); row.pack(fill="x", pady=5)
        ttk.Button(row, text="+", width=4, command=self.add_method).pack(side="left")
        ttk.Button(row, text="-", width=4, command=self.delete_method).pack(side="left", padx=4)
        ttk.Label(panel, text="Name").pack(anchor="w")
        ttk.Entry(panel, textvariable=self.method_name).pack(fill="x")
        ttk.Label(panel, text="Description").pack(anchor="w", pady=(5, 0))
        ttk.Entry(panel, textvariable=self.method_description).pack(fill="x")
        ttk.Button(panel, text="Apply method", command=self.apply_method).pack(anchor="e", pady=(6, 0))

    def build_assignments(self, panes):
        panel = ttk.LabelFrame(panes, text="Catalog defaults", padding=8)
        panes.add(panel, weight=2)
        ttk.Label(panel, text="Search all supported definitions").pack(anchor="w")
        ttk.Entry(panel, textvariable=self.query).pack(fill="x", pady=(2, 6))
        self.record_tree = ttk.Treeview(panel, columns=("kind",), show="tree headings")
        self.record_tree.heading("#0", text="Definition")
        self.record_tree.heading("kind", text="Catalog")
        self.record_tree.column("#0", width=350)
        self.record_tree.column("kind", width=160)
        self.record_tree.pack(fill="both", expand=True)
        self.record_tree.bind("<<TreeviewSelect>>", self.select_record)
        controls = ttk.Frame(panel); controls.pack(fill="x", pady=(7, 0))
        self.method_checks = ttk.Frame(controls)
        self.method_checks.pack(side="left", fill="x", expand=True)
        quantity = ttk.Frame(controls); quantity.pack(side="right")
        ttk.Label(quantity, text="Default source / window quantity").pack(anchor="w")
        ttk.Spinbox(quantity, textvariable=self.quantity, from_=1, to=100000, width=10).pack(side="left")
        ttk.Button(quantity, text="Apply", command=self.apply_assignment).pack(side="left", padx=(5, 0))
        self.query.trace_add("write", lambda *_args: self.refresh_records())

    def methods(self):
        return self.database.data.setdefault("gathering_methods", [])

    def records(self):
        rows = []
        for collection in sorted(CATALOG_COLLECTIONS - {"creature_parts", "plant_parts"}):
            for record in self.database.data.get(collection, []) or []:
                if isinstance(record, dict) and record.get("record_id"):
                    rows.append((collection, record, ""))
        for parents, collection in (("creatures", "creature_parts"), ("plants", "plant_parts")):
            for parent in self.database.data.get(parents, []) or []:
                for record in parent.get("parts", []) or []:
                    if isinstance(record, dict) and record.get("record_id"):
                        rows.append((collection, record, str(parent.get("record_id", ""))))
        return rows

    def refresh_methods(self):
        self.method_tree.delete(*self.method_tree.get_children())
        for method in self.methods():
            self.method_tree.insert("", "end", iid=str(method["record_id"]), text=str(method.get("name") or "Method"))
        self.render_method_checks()

    def add_method(self):
        record = {"record_id": str(uuid4()), "name": "New gathering method", "description": ""}
        self.methods().append(record)
        self.database.dirty = True
        self.refresh_methods()
        self.method_tree.selection_set(record["record_id"])
        self.select_method()

    def select_method(self, *_args):
        selected = self.method_tree.selection()
        if not selected:
            return
        method = next(item for item in self.methods() if str(item["record_id"]) == selected[0])
        self.method_name.set(str(method.get("name", "")))
        self.method_description.set(str(method.get("description", "")))

    def apply_method(self):
        selected = self.method_tree.selection()
        if not selected or not self.method_name.get().strip():
            return
        method = next(item for item in self.methods() if str(item["record_id"]) == selected[0])
        method.update(name=self.method_name.get().strip(), description=self.method_description.get().strip())
        self.database.dirty = True
        self.refresh_methods()

    def delete_method(self):
        selected = self.method_tree.selection()
        if not selected:
            return
        method_id = selected[0]
        if any(method_id in (record.get("gathering_method_ids", []) or []) for _, record, _ in self.records()):
            messagebox.showerror("Method in use", "Remove this method from catalog assignments first.", parent=self)
            return
        self.database.data["gathering_methods"] = [item for item in self.methods() if str(item["record_id"]) != method_id]
        self.database.dirty = True
        self.refresh_methods()

    def refresh_records(self):
        query = self.query.get().strip().casefold()
        self.record_tree.delete(*self.record_tree.get_children())
        for collection, record, parent_id in self.records():
            name = display_name(record)
            if query and query not in f"{name} {collection}".casefold():
                continue
            key = f"{collection}:{parent_id}:{record['record_id']}"
            self.record_tree.insert("", "end", iid=key, text=name, values=(collection.replace("_", " ").title(),))

    def select_record(self, *_args):
        selected = self.record_tree.selection()
        self.selected_record = None
        if not selected:
            return
        collection, parent_id, record_id = selected[0].split(":", 2)
        self.selected_record = next(
            (record for current, record, parent in self.records()
             if current == collection and parent == parent_id and str(record.get("record_id")) == record_id),
            None,
        )
        if self.selected_record is not None:
            self.quantity.set(str(int(self.selected_record.get("default_source_quantity", 1) or 1)))
        self.render_method_checks()

    def render_method_checks(self):
        for child in self.method_checks.winfo_children():
            child.destroy()
        self.method_variables = {}
        assigned = set((self.selected_record or {}).get("gathering_method_ids", []) or [])
        for index, method in enumerate(self.methods()):
            method_id = str(method["record_id"])
            variable = tk.BooleanVar(value=method_id in assigned)
            self.method_variables[method_id] = variable
            ttk.Checkbutton(self.method_checks, text=str(method.get("name") or method_id), variable=variable).grid(row=index // 3, column=index % 3, sticky="w", padx=(0, 8))

    def apply_assignment(self):
        if self.selected_record is None:
            return
        try:
            quantity = max(1, int(self.quantity.get()))
        except ValueError:
            messagebox.showerror("Invalid quantity", "Enter a whole number of at least one.", parent=self)
            return
        self.selected_record["gathering_method_ids"] = [method_id for method_id, variable in self.method_variables.items() if variable.get()]
        self.selected_record["default_source_quantity"] = quantity
        self.selected_record["default_stock_quantity"] = quantity
        self.database.dirty = True

    def save(self):
        self.database.save()
        messagebox.showinfo("Saved", "Gathering methods and catalog defaults were saved.", parent=self)
