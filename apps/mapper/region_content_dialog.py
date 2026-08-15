from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from tkinter import messagebox, simpledialog, ttk
from typing import Any, Callable
from uuid import uuid4

from headmasters_scroll.region_interactions import validate_region_catalog_links


COLLECTION_LABELS = {
    "creatures": "Creatures", "books": "Books", "plants": "Plants",
    "creature_parts": "Creature parts", "plant_parts": "Plant parts",
    "potions": "Potions", "preparations": "Preparations",
    "general_items": "General items", "accessories": "Accessories",
    "holdable_items": "Holdable items", "foods_and_drinks": "Food & drink",
}
SHOP_FREQUENCIES = (
    ("always", "Always"), ("frequently", "Frequently"),
    ("sometimes", "Sometimes"), ("rarely", "Rarely"),
    ("very_rarely", "Very rarely"),
)


def _name(record: dict[str, Any]) -> str:
    return str(record.get("name") or record.get("title") or "Untitled")


def catalog_rows(database: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for collection, label in COLLECTION_LABELS.items():
        if collection in {"creature_parts", "plant_parts"}:
            parents = "creatures" if collection == "creature_parts" else "plants"
            for parent in database.get(parents, []) or []:
                parent_id = str(parent.get("record_id", "") or "")
                for part in parent.get("parts", []) or []:
                    record_id = str(part.get("record_id", "") or "")
                    if record_id:
                        rows.append({
                            "key": f"{collection}:{parent_id}:{record_id}",
                            "name": _name(part), "collection": collection,
                            "type_label": label, "parent_record_id": parent_id,
                            "parent_name": _name(parent), "record": part,
                        })
            continue
        for record in database.get(collection, []) or []:
            record_id = str(record.get("record_id", "") or "")
            if record_id:
                rows.append({
                    "key": f"{collection}::{record_id}", "name": _name(record),
                    "collection": collection, "type_label": label,
                    "parent_record_id": "", "parent_name": "", "record": record,
                })
    return sorted(rows, key=lambda item: (item["name"].casefold(), item["type_label"]))


class CatalogChooser(tk.Toplevel):
    def __init__(self, parent: tk.Misc, database: dict[str, Any], callback: Callable[[dict[str, Any]], None]):
        super().__init__(parent)
        self.title("Choose catalog content")
        self.geometry("840x600")
        self.minsize(650, 420)
        self.transient(parent)
        self.callback = callback
        self.rows = catalog_rows(database)
        self.query = tk.StringVar()
        self.type_filter = tk.StringVar(value="All")
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Search the complete catalog", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(4, 8))
        entry = ttk.Entry(controls, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True)
        type_box = ttk.Combobox(
            controls, textvariable=self.type_filter, state="readonly", width=20,
            values=["All", *COLLECTION_LABELS.values()],
        )
        type_box.pack(side="left", padx=(7, 0))
        self.tree = ttk.Treeview(shell, columns=("type", "parent"), show="tree headings", selectmode="browse")
        self.tree.heading("#0", text="Name")
        self.tree.heading("type", text="Kind")
        self.tree.heading("parent", text="Source")
        self.tree.column("#0", width=390)
        self.tree.column("type", width=150)
        self.tree.column("parent", width=200)
        self.tree.pack(fill="both", expand=True)
        buttons = ttk.Frame(shell)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(buttons, text="Choose", command=self.choose).pack(side="right", padx=(0, 7))
        self.query.trace_add("write", self.refill)
        self.type_filter.trace_add("write", self.refill)
        self.tree.bind("<Double-Button-1>", lambda _event: self.choose())
        self.refill()
        entry.focus_set()
        self.grab_set()

    def refill(self, *_args) -> None:
        query = " ".join(self.query.get().casefold().split())
        selected_type = self.type_filter.get()
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            if selected_type != "All" and row["type_label"] != selected_type:
                continue
            haystack = f"{row['name']} {row['type_label']} {row['parent_name']}".casefold()
            if query and query not in haystack:
                continue
            self.tree.insert("", "end", iid=row["key"], text=row["name"], values=(row["type_label"], row["parent_name"]))

    def choose(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = next(item for item in self.rows if item["key"] == selected[0])
        chosen = {
            "collection": row["collection"],
            "record_id": str(row["record"].get("record_id", "")),
            "parent_record_id": row["parent_record_id"],
            "display_name": row["name"],
        }
        self.grab_release()
        self.destroy()
        self.callback(chosen)


class ModeEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, database: dict[str, Any], value: dict[str, Any] | None, callback: Callable[[dict[str, Any]], None]):
        super().__init__(parent)
        self.title("Search method")
        self.geometry("500x420")
        self.transient(parent)
        self.callback = callback
        value = value or {}
        self.record_id = str(value.get("record_id") or uuid4())
        self.name_value = tk.StringVar(value=str(value.get("name", "Search")))
        self.skill_value = tk.StringVar(value=str(value.get("skill", "Perception")))
        self.method_id = tk.StringVar(value=str(value.get("gathering_method_id", "search")))
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Name").pack(anchor="w")
        ttk.Entry(shell, textvariable=self.name_value).pack(fill="x", pady=(2, 8))
        ttk.Label(shell, text="Raw skill").pack(anchor="w")
        ttk.Entry(shell, textvariable=self.skill_value).pack(fill="x", pady=(2, 8))
        ttk.Label(shell, text="Gathering method", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.method_tree = ttk.Treeview(shell, show="tree", height=8, selectmode="browse")
        self.method_tree.pack(fill="both", expand=True, pady=(3, 8))
        for method in database.get("gathering_methods", []) or []:
            method_id = str(method.get("record_id", "") or "")
            if method_id:
                self.method_tree.insert("", "end", iid=method_id, text=str(method.get("name") or method_id))
        if self.method_tree.exists(self.method_id.get()):
            self.method_tree.selection_set(self.method_id.get())
        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Apply", command=self.apply).pack(side="right", padx=(0, 7))
        self.grab_set()

    def apply(self) -> None:
        selection = self.method_tree.selection()
        if not selection or not self.name_value.get().strip() or not self.skill_value.get().strip():
            messagebox.showerror("Incomplete search", "Enter a name, raw skill, and gathering method.", parent=self)
            return
        self.callback({
            "record_id": self.record_id, "name": self.name_value.get().strip(),
            "skill": self.skill_value.get().strip(), "gathering_method_id": selection[0],
        })
        self.destroy()


class RegionContentDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, database: dict[str, Any], region: dict[str, Any], callback: Callable[[dict[str, Any]], None]):
        super().__init__(parent)
        self.title("Region contents")
        self.geometry("1040x680")
        self.minsize(800, 520)
        self.transient(parent)
        self.database = database
        self.region = deepcopy(region)
        self.callback = callback
        shell = ttk.Frame(self, padding=10)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=str(region.get("name") or "Region"), font=("Georgia", 14, "bold")).pack(anchor="w")
        self.tabs = ttk.Notebook(shell)
        self.tabs.pack(fill="both", expand=True, pady=(7, 8))
        behavior = str(region.get("behavior_type", ""))
        if behavior in {"secret", "library", "storeroom"}:
            self._build_modes()
            self._build_contents()
        if behavior == "shop":
            self._build_shop()
        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Apply changes", command=self.apply).pack(side="right", padx=(0, 7))
        self.grab_set()

    def _toolbar(self, parent: tk.Misc, add: Callable, edit: Callable | None, delete: Callable) -> ttk.Frame:
        bar = ttk.Frame(parent)
        bar.pack(fill="x", pady=(0, 5))
        ttk.Button(bar, text="+", width=4, command=add).pack(side="left")
        if edit:
            ttk.Button(bar, text="Edit", command=edit).pack(side="left", padx=4)
        ttk.Button(bar, text="-", width=4, command=delete).pack(side="left")
        return bar

    def _build_modes(self) -> None:
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="Search methods")
        self._toolbar(tab, self.add_mode, self.edit_mode, self.delete_mode)
        self.mode_tree = ttk.Treeview(tab, columns=("skill", "method"), show="tree headings")
        for column, title, width in (("#0", "Search choice", 300), ("skill", "Raw skill", 220), ("method", "Gathering method", 220)):
            self.mode_tree.heading(column, text=title)
            self.mode_tree.column(column, width=width)
        self.mode_tree.pack(fill="both", expand=True)
        self.refresh_modes()

    def refresh_modes(self) -> None:
        methods = {str(item.get("record_id")): str(item.get("name")) for item in self.database.get("gathering_methods", []) or []}
        self.mode_tree.delete(*self.mode_tree.get_children())
        for mode in self.region.get("search_modes", []) or []:
            self.mode_tree.insert("", "end", iid=str(mode["record_id"]), text=str(mode["name"]), values=(mode["skill"], methods.get(str(mode["gathering_method_id"]), mode["gathering_method_id"])))

    def add_mode(self) -> None:
        ModeEditor(self, self.database, None, lambda value: (self.region.setdefault("search_modes", []).append(value), self.refresh_modes()))

    def edit_mode(self) -> None:
        selected = self.mode_tree.selection()
        if not selected:
            return
        value = next(item for item in self.region.get("search_modes", []) if str(item["record_id"]) == selected[0])
        def accept(updated: dict[str, Any]) -> None:
            value.clear(); value.update(updated); self.refresh_modes()
        ModeEditor(self, self.database, value, accept)

    def delete_mode(self) -> None:
        selected = self.mode_tree.selection()
        if not selected:
            return
        mode_id = selected[0]
        if any(mode_id in entry.get("search_mode_ids", []) for entry in self.region.get("contents", []) or []):
            messagebox.showerror("Search method in use", "Remove this method from its content entries first.", parent=self)
            return
        self.region["search_modes"] = [item for item in self.region.get("search_modes", []) if str(item["record_id"]) != mode_id]
        self.refresh_modes()

    def _build_contents(self) -> None:
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="Searchable contents")
        self._toolbar(tab, self.add_content, self.edit_content, self.delete_content)
        self.content_tree = ttk.Treeview(tab, columns=("kind", "threshold", "stock", "modes"), show="tree headings")
        for column, title, width in (("#0", "Content", 280), ("kind", "Kind", 130), ("threshold", "Threshold", 75), ("stock", "Stock", 90), ("modes", "Search methods", 280)):
            self.content_tree.heading(column, text=title); self.content_tree.column(column, width=width)
        self.content_tree.pack(fill="both", expand=True)
        self.refresh_contents()

    def _reference_name(self, reference: dict[str, Any]) -> str:
        key = f"{reference.get('collection')}:{reference.get('parent_record_id', '')}:{reference.get('record_id')}"
        return next((row["name"] for row in catalog_rows(self.database) if row["key"] == key), "Missing catalog record")

    def refresh_contents(self) -> None:
        modes = {str(item["record_id"]): str(item["name"]) for item in self.region.get("search_modes", []) or []}
        self.content_tree.delete(*self.content_tree.get_children())
        for entry in self.region.get("contents", []) or []:
            reference = entry["reference"]
            self.content_tree.insert("", "end", iid=str(entry["record_id"]), text=self._reference_name(reference), values=(COLLECTION_LABELS.get(reference["collection"], reference["collection"]), entry.get("threshold", 0), "Finite" if entry.get("depletable") else "Reusable", ", ".join(modes.get(str(value), "?") for value in entry.get("search_mode_ids", []))))

    def _edit_content_values(self, entry: dict[str, Any]) -> None:
        if not self.region.get("search_modes"):
            messagebox.showinfo("Add a search method", "Create at least one search method first.", parent=self)
            return
        threshold = simpledialog.askinteger("Discovery threshold", "Minimum raw-skill roll total:", initialvalue=int(entry.get("threshold", 0)), minvalue=0, maxvalue=999, parent=self)
        if threshold is None:
            return
        mode_names = "\n".join(f"{index + 1}. {mode['name']}" for index, mode in enumerate(self.region["search_modes"]))
        chosen = simpledialog.askstring("Search methods", f"Enter method numbers separated by commas:\n\n{mode_names}", initialvalue=",".join(str(index + 1) for index, mode in enumerate(self.region["search_modes"]) if mode["record_id"] in entry.get("search_mode_ids", [])), parent=self)
        if chosen is None:
            return
        indexes = []
        for raw in chosen.split(","):
            try:
                index = int(raw.strip()) - 1
            except ValueError:
                continue
            if 0 <= index < len(self.region["search_modes"]) and index not in indexes:
                indexes.append(index)
        if not indexes:
            messagebox.showerror("Search method required", "Choose at least one search method.", parent=self)
            return
        finite = messagebox.askyesno("Finite source", "Should this content deplete from a shared finite stock?", parent=self)
        entry.update({"threshold": threshold, "search_mode_ids": [self.region["search_modes"][index]["record_id"] for index in indexes], "depletable": finite})
        self.refresh_contents()

    def add_content(self) -> None:
        def selected(reference: dict[str, Any]) -> None:
            entry = {"record_id": str(uuid4()), "reference": {key: reference[key] for key in ("collection", "record_id", "parent_record_id")}, "threshold": 0, "search_mode_ids": [], "depletable": False}
            self._edit_content_values(entry)
            if entry["search_mode_ids"]:
                self.region.setdefault("contents", []).append(entry); self.refresh_contents()
        CatalogChooser(self, self.database, selected)

    def edit_content(self) -> None:
        selected = self.content_tree.selection()
        if selected:
            self._edit_content_values(next(item for item in self.region.get("contents", []) if str(item["record_id"]) == selected[0]))

    def delete_content(self) -> None:
        selected = set(self.content_tree.selection())
        if selected:
            self.region["contents"] = [item for item in self.region.get("contents", []) if str(item["record_id"]) not in selected]; self.refresh_contents()

    def _build_shop(self) -> None:
        tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(tab, text="Shop listings")
        self._toolbar(tab, self.add_listing, self.edit_listing, self.delete_listing)
        self.shop_tree = ttk.Treeview(tab, columns=("frequency", "price", "status"), show="tree headings")
        for column, title, width in (("#0", "Item", 380), ("frequency", "Frequency", 140), ("price", "Price (Knuts)", 120), ("status", "Price", 110)):
            self.shop_tree.heading(column, text=title); self.shop_tree.column(column, width=width)
        self.shop_tree.pack(fill="both", expand=True)
        self.refresh_shop()

    def refresh_shop(self) -> None:
        self.shop_tree.delete(*self.shop_tree.get_children())
        frequency_names = dict(SHOP_FREQUENCIES)
        for listing in self.region.get("shop_listings", []) or []:
            self.shop_tree.insert("", "end", iid=str(listing["record_id"]), text=self._reference_name(listing["reference"]), values=(frequency_names.get(listing.get("frequency"), listing.get("frequency")), listing.get("price_knuts", 9_999_999), "Confirmed" if listing.get("price_confirmed") else "Needs price"))

    def _edit_listing_values(self, listing: dict[str, Any]) -> None:
        choice = simpledialog.askstring("Stock frequency", "Always, Frequently, Sometimes, Rarely, or Very rarely:", initialvalue=dict(SHOP_FREQUENCIES).get(listing.get("frequency", "always"), "Always"), parent=self)
        if choice is None:
            return
        lookup = {label.casefold(): key for key, label in SHOP_FREQUENCIES}
        frequency = lookup.get(choice.strip().casefold())
        if not frequency:
            messagebox.showerror("Unknown frequency", "Use Always, Frequently, Sometimes, Rarely, or Very rarely.", parent=self)
            return
        price = simpledialog.askinteger("Listing price", "Price in Knuts:", initialvalue=int(listing.get("price_knuts", 9_999_999)), minvalue=0, maxvalue=999_999_999, parent=self)
        if price is None:
            return
        listing.update({"frequency": frequency, "price_knuts": price, "price_confirmed": True})
        self.refresh_shop()

    def add_listing(self) -> None:
        def selected(reference: dict[str, Any]) -> None:
            listing = {"record_id": str(uuid4()), "reference": {key: reference[key] for key in ("collection", "record_id", "parent_record_id")}, "frequency": "always", "price_knuts": 9_999_999, "price_confirmed": False}
            self.region.setdefault("shop_listings", []).append(listing)
            self._edit_listing_values(listing); self.refresh_shop()
        CatalogChooser(self, self.database, selected)

    def edit_listing(self) -> None:
        selected = self.shop_tree.selection()
        if selected:
            self._edit_listing_values(next(item for item in self.region.get("shop_listings", []) if str(item["record_id"]) == selected[0]))

    def delete_listing(self) -> None:
        selected = set(self.shop_tree.selection())
        if selected:
            self.region["shop_listings"] = [item for item in self.region.get("shop_listings", []) if str(item["record_id"]) not in selected]; self.refresh_shop()

    def apply(self) -> None:
        try:
            normalized = validate_region_catalog_links(self.region, self.database)
        except (TypeError, ValueError) as exc:
            messagebox.showerror("Cannot save region contents", str(exc), parent=self)
            return
        self.callback(normalized)
        self.destroy()
