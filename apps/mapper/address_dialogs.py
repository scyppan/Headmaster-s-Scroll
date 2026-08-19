from __future__ import annotations

import tkinter as tk
from copy import deepcopy
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from typing import Callable
from uuid import uuid4


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _display_name(record: dict, kind: str = "") -> str:
    if kind == "person":
        return str(record.get("displayed_name") or record.get("name") or "Unnamed person")
    return str(record.get("name") or record.get("displayed_name") or "Unnamed organization")


class WorldReferenceChooser(tk.Toplevel):
    """Search people and organizations without reducing core data to a combobox."""

    def __init__(self, parent: tk.Misc, world: dict, callback: Callable[[dict], None]):
        super().__init__(parent)
        self.title("Choose owner")
        self.geometry("760x560")
        self.minsize(600, 400)
        self.transient(parent)
        self.callback = callback
        self.rows: list[dict] = []
        for kind, collection in (("person", "people"), ("organization", "organizations")):
            for record in world.get(collection, []) or []:
                record_id = str(record.get("record_id", "") or "")
                if not record_id:
                    continue
                name = _display_name(record, kind)
                details = " ".join(
                    str(record.get(field, "") or "")
                    for field in (
                        "organization_type", "school", "birth_year", "description"
                    )
                )
                self.rows.append({
                    "key": f"{kind}:{record_id}",
                    "owner_type": kind,
                    "record_id": record_id,
                    "name": name,
                    "details": details,
                    "search": f"{name} {details}".casefold(),
                })
        self.rows.sort(key=lambda item: (item["name"].casefold(), item["owner_type"]))
        self.query = tk.StringVar()
        self.kind = tk.StringVar(value="All")
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        controls = ttk.Frame(shell)
        controls.pack(fill="x", pady=(0, 8))
        entry = ttk.Entry(controls, textvariable=self.query)
        entry.pack(side="left", fill="x", expand=True)
        ttk.Combobox(
            controls,
            textvariable=self.kind,
            values=("All", "People", "Organizations"),
            state="readonly",
            width=18,
        ).pack(side="left", padx=(7, 0))
        self.tree = ttk.Treeview(shell, columns=("kind", "details"), show="tree headings")
        self.tree.heading("#0", text="Name")
        self.tree.heading("kind", text="Kind")
        self.tree.heading("details", text="Details")
        self.tree.column("#0", width=310)
        self.tree.column("kind", width=120)
        self.tree.column("details", width=260)
        self.tree.pack(fill="both", expand=True)
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Choose", command=self.choose).pack(side="right", padx=(0, 7))
        self.query.trace_add("write", self.refill)
        self.kind.trace_add("write", self.refill)
        self.tree.bind("<Double-Button-1>", lambda _event: self.choose())
        self.tree.bind("<Return>", lambda _event: self.choose())
        self.refill()
        entry.focus_set()
        self.grab_set()

    def refill(self, *_args) -> None:
        query = " ".join(self.query.get().casefold().split())
        words = query.split()
        chosen_kind = self.kind.get()
        self.tree.delete(*self.tree.get_children())
        for row in self.rows:
            if chosen_kind == "People" and row["owner_type"] != "person":
                continue
            if chosen_kind == "Organizations" and row["owner_type"] != "organization":
                continue
            if words and not all(word in row["search"] for word in words):
                continue
            self.tree.insert(
                "", "end", iid=row["key"], text=row["name"],
                values=(row["owner_type"].title(), row["details"]),
            )

    def choose(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = next(item for item in self.rows if item["key"] == selected[0])
        value = {
            "owner_type": row["owner_type"],
            "record_id": row["record_id"],
            "display_name": row["name"],
        }
        self.grab_release()
        self.destroy()
        self.callback(value)


class AddressChooser(tk.Toplevel):
    """Search addresses belonging to the shop's current location."""

    def __init__(self, parent: tk.Misc, world: dict, location_id: str, callback: Callable[[dict], None]):
        super().__init__(parent)
        self.title("Choose shop address")
        self.geometry("620x450")
        self.minsize(480, 340)
        self.transient(parent)
        self.callback = callback
        self.rows = sorted(
            [
                item for item in world.get("addresses", []) or []
                if str(item.get("location_id", "")) == str(location_id)
            ],
            key=lambda item: str(item.get("name", "")).casefold(),
        )
        self.query = tk.StringVar()
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        entry = ttk.Entry(shell, textvariable=self.query)
        entry.pack(fill="x", pady=(0, 8))
        self.tree = ttk.Treeview(shell, columns=("notes",), show="tree headings")
        self.tree.heading("#0", text="Address")
        self.tree.heading("notes", text="Notes")
        self.tree.column("#0", width=280)
        self.tree.column("notes", width=280)
        self.tree.pack(fill="both", expand=True)
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Choose", command=self.choose).pack(side="right", padx=(0, 7))
        self.query.trace_add("write", self.refill)
        self.tree.bind("<Double-Button-1>", lambda _event: self.choose())
        self.tree.bind("<Return>", lambda _event: self.choose())
        self.refill()
        entry.focus_set()
        self.grab_set()

    def refill(self, *_args) -> None:
        words = " ".join(self.query.get().casefold().split()).split()
        self.tree.delete(*self.tree.get_children())
        for address in self.rows:
            text = f"{address.get('name', '')} {address.get('notes', '')}".casefold()
            if words and not all(word in text for word in words):
                continue
            self.tree.insert(
                "", "end", iid=str(address["record_id"]),
                text=str(address.get("name", "Address")),
                values=(str(address.get("notes", "")),),
            )

    def choose(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        address = next(item for item in self.rows if str(item.get("record_id")) == selected[0])
        self.grab_release()
        self.destroy()
        self.callback(deepcopy(address))


class AddressEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, value: dict | None, callback: Callable[[dict], None]):
        super().__init__(parent)
        value = value or {}
        self.title("Address")
        self.geometry("520x300")
        self.transient(parent)
        self.callback = callback
        self.record_id = str(value.get("record_id") or uuid4())
        self.created_at = str(value.get("created_at") or utc_now())
        self.name = tk.StringVar(value=str(value.get("name", "")))
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text="Address", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry = ttk.Entry(shell, textvariable=self.name)
        entry.pack(fill="x", pady=(3, 9))
        ttk.Label(shell, text="Notes").pack(anchor="w")
        self.notes = tk.Text(shell, height=8, wrap="word")
        self.notes.pack(fill="both", expand=True, pady=(3, 8))
        self.notes.insert("1.0", str(value.get("notes", "")))
        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Apply", command=self.apply).pack(side="right", padx=(0, 7))
        entry.focus_set()
        self.grab_set()

    def apply(self) -> None:
        name = self.name.get().strip()
        if not name:
            messagebox.showerror("Address required", "Enter the address.", parent=self)
            return
        self.callback({
            "record_id": self.record_id,
            "name": name,
            "notes": self.notes.get("1.0", "end-1c").strip(),
            "created_at": self.created_at,
            "last_updated": utc_now(),
        })
        self.destroy()


class AddressEventEditor(tk.Toplevel):
    EVENT_TYPES = (
        ("address_owner_changed", "Owner changed"),
        ("address_contents_changed", "Contents changed"),
        ("address_occupancy_changed", "Occupancy changed"),
        ("address_established", "Address established"),
        ("custom", "Other"),
    )

    def __init__(self, parent: tk.Misc, world: dict, address: dict, value: dict | None, callback: Callable[[dict], None]):
        super().__init__(parent)
        value = value or {}
        self.title("Address event")
        self.geometry("620x500")
        self.transient(parent)
        self.world = world
        self.address = address
        self.callback = callback
        self.record_id = str(value.get("record_id") or uuid4())
        self.event_type = tk.StringVar(value=str(value.get("event_type") or "address_owner_changed"))
        self.date = tk.StringVar(value=str(value.get("date", "")))
        self.time = tk.StringVar(value=str(value.get("time", "")))
        self.title_value = tk.StringVar(value=str(value.get("title", "")))
        self.owner = deepcopy(value.get("owner_reference")) if isinstance(value.get("owner_reference"), dict) else None
        self.owner_label = tk.StringVar(value=self.owner_name())
        shell = ttk.Frame(self, padding=12)
        shell.pack(fill="both", expand=True)
        ttk.Label(shell, text=str(address.get("name", "Address")), font=("Georgia", 13, "bold")).pack(anchor="w")
        grid = ttk.Frame(shell)
        grid.pack(fill="x", pady=(8, 7))
        for column in range(3):
            grid.columnconfigure(column, weight=1)
        ttk.Label(grid, text="Event").grid(row=0, column=0, sticky="w")
        ttk.Label(grid, text="World date").grid(row=0, column=1, sticky="w", padx=(7, 0))
        ttk.Label(grid, text="Time").grid(row=0, column=2, sticky="w", padx=(7, 0))
        ttk.Combobox(
            grid, textvariable=self.event_type, state="readonly",
            values=[key for key, _label in self.EVENT_TYPES],
        ).grid(row=1, column=0, sticky="ew")
        ttk.Entry(grid, textvariable=self.date).grid(row=1, column=1, sticky="ew", padx=(7, 0))
        ttk.Entry(grid, textvariable=self.time).grid(row=1, column=2, sticky="ew", padx=(7, 0))
        ttk.Label(shell, text="Title").pack(anchor="w")
        ttk.Entry(shell, textvariable=self.title_value).pack(fill="x", pady=(3, 7))
        owner_row = ttk.Frame(shell)
        owner_row.pack(fill="x", pady=(0, 7))
        ttk.Label(owner_row, textvariable=self.owner_label).pack(side="left", fill="x", expand=True)
        ttk.Button(owner_row, text="Choose owner…", command=self.choose_owner).pack(side="left")
        ttk.Button(owner_row, text="Clear", command=self.clear_owner).pack(side="left", padx=(4, 0))
        ttk.Label(shell, text="Details").pack(anchor="w")
        self.description = tk.Text(shell, height=10, wrap="word")
        self.description.pack(fill="both", expand=True, pady=(3, 8))
        self.description.insert("1.0", str(value.get("description", "")))
        actions = ttk.Frame(shell)
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Apply", command=self.apply).pack(side="right", padx=(0, 7))
        self.grab_set()

    def owner_name(self) -> str:
        if not self.owner:
            return "No owner linked"
        kind = str(self.owner.get("owner_type", ""))
        collection = "people" if kind == "person" else "organizations"
        record = next((
            item for item in self.world.get(collection, []) or []
            if str(item.get("record_id", "")) == str(self.owner.get("record_id", ""))
        ), {})
        return f"Owner: {_display_name(record, kind)}"

    def choose_owner(self) -> None:
        def accept(value: dict) -> None:
            self.owner = {key: value[key] for key in ("owner_type", "record_id")}
            self.owner_label.set(f"Owner: {value['display_name']}")
        WorldReferenceChooser(self, self.world, accept)

    def clear_owner(self) -> None:
        self.owner = None
        self.owner_label.set("No owner linked")

    def apply(self) -> None:
        title = self.title_value.get().strip()
        date = self.date.get().strip()
        if not title or not date:
            messagebox.showerror("Incomplete event", "Enter a title and world date.", parent=self)
            return
        value = {
            "record_id": self.record_id,
            "event_type": self.event_type.get(),
            "title": title,
            "date": date,
            "time": self.time.get().strip(),
            "description": self.description.get("1.0", "end-1c").strip(),
            "address_ids": [str(self.address["record_id"])],
        }
        if self.owner:
            value["owner_reference"] = deepcopy(self.owner)
            key = "person_ids" if self.owner["owner_type"] == "person" else "organization_ids"
            value[key] = [self.owner["record_id"]]
        self.callback(value)
        self.destroy()


class AddressManagerDialog(tk.Toplevel):
    """Edit stable addresses and their canonical world events for one location."""

    def __init__(
        self,
        parent: tk.Misc,
        world: dict,
        location_id: str,
        callback: Callable[[list, list], None],
        *,
        selected_address_id: str = "",
    ):
        super().__init__(parent)
        self.world = world
        self.location_id = str(location_id)
        self.callback = callback
        location = next((item for item in world.get("locations", []) or [] if str(item.get("record_id")) == self.location_id), {})
        self.title(f"Address history — {location.get('name', 'Location')}")
        self.geometry("980x620")
        self.minsize(760, 460)
        self.transient(parent)
        self.addresses = deepcopy(world.get("addresses", []) or [])
        self.events = deepcopy(world.get("events", []) or [])
        shell = ttk.Frame(self, padding=10)
        shell.pack(fill="both", expand=True)
        panes = ttk.Panedwindow(shell, orient="horizontal")
        panes.pack(fill="both", expand=True)
        left = ttk.Frame(panes, padding=5)
        right = ttk.Frame(panes, padding=5)
        panes.add(left, weight=1)
        panes.add(right, weight=2)
        self._header(left, "Addresses", self.add_address, self.edit_address, self.delete_address)
        self.address_tree = ttk.Treeview(left, show="tree", selectmode="browse")
        self.address_tree.pack(fill="both", expand=True)
        self.address_tree.bind("<<TreeviewSelect>>", lambda _event: self.refresh_events())
        self.address_tree.bind("<Double-Button-1>", lambda _event: self.edit_address())
        self._header(right, "Address events", self.add_event, self.edit_event, self.delete_event)
        self.event_tree = ttk.Treeview(right, columns=("date", "type", "owner"), show="tree headings")
        self.event_tree.heading("#0", text="Event")
        self.event_tree.heading("date", text="Date")
        self.event_tree.heading("type", text="Type")
        self.event_tree.heading("owner", text="Owner")
        self.event_tree.column("#0", width=260)
        self.event_tree.column("date", width=105)
        self.event_tree.column("type", width=150)
        self.event_tree.column("owner", width=170)
        self.event_tree.pack(fill="both", expand=True)
        self.event_tree.bind("<Double-Button-1>", lambda _event: self.edit_event())
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Save addresses & events", command=self.apply).pack(side="right", padx=(0, 7))
        self.refresh_addresses(selected_address_id)
        self.grab_set()

    @staticmethod
    def _header(parent, title, add, edit, delete):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 5))
        ttk.Label(row, text=title, font=("Segoe UI", 10, "bold")).pack(side="left")
        ttk.Button(row, text="−", width=3, command=delete).pack(side="right")
        ttk.Button(row, text="✎", width=3, command=edit).pack(side="right", padx=3)
        ttk.Button(row, text="+", width=3, command=add).pack(side="right")

    def location_addresses(self) -> list[dict]:
        return [item for item in self.addresses if str(item.get("location_id", "")) == self.location_id]

    def selected_address(self) -> dict | None:
        selection = self.address_tree.selection()
        return next((item for item in self.addresses if selection and str(item.get("record_id")) == selection[0]), None)

    def refresh_addresses(self, selected_id: str = "") -> None:
        self.address_tree.delete(*self.address_tree.get_children())
        for address in sorted(self.location_addresses(), key=lambda item: str(item.get("name", "")).casefold()):
            self.address_tree.insert("", "end", iid=str(address["record_id"]), text=str(address["name"]))
        chosen = selected_id or next(iter(self.address_tree.get_children()), "")
        if chosen and self.address_tree.exists(chosen):
            self.address_tree.selection_set(chosen)
        self.refresh_events()

    def add_address(self) -> None:
        def accept(value: dict) -> None:
            value["location_id"] = self.location_id
            self.addresses.append(value)
            self.refresh_addresses(str(value["record_id"]))
        AddressEditor(self, None, accept)

    def edit_address(self) -> None:
        address = self.selected_address()
        if address is None:
            return
        def accept(value: dict) -> None:
            value["location_id"] = self.location_id
            address.clear(); address.update(value)
            self.refresh_addresses(str(value["record_id"]))
        AddressEditor(self, address, accept)

    def delete_address(self) -> None:
        address = self.selected_address()
        if address is None:
            return
        address_id = str(address["record_id"])
        if any(address_id in (event.get("address_ids", []) or []) for event in self.events if isinstance(event, dict)):
            messagebox.showerror("Address has events", "Remove this address's events before deleting it.", parent=self)
            return
        if any(
            str(region.get("address_id", "")) == address_id
            for map_record in self.world.get("maps", []) or []
            for region in map_record.get("regions", []) or []
        ):
            messagebox.showerror(
                "Address is mapped",
                "Unlink the map area or shop from this address before deleting it.",
                parent=self,
            )
            return
        self.addresses = [item for item in self.addresses if str(item.get("record_id")) != address_id]
        self.refresh_addresses()

    def address_events(self) -> list[dict]:
        address = self.selected_address()
        if address is None:
            return []
        address_id = str(address["record_id"])
        return [item for item in self.events if address_id in (item.get("address_ids", []) or [])]

    def owner_name(self, event: dict) -> str:
        owner = event.get("owner_reference")
        if not isinstance(owner, dict):
            return ""
        kind = str(owner.get("owner_type", ""))
        collection = "people" if kind == "person" else "organizations"
        record = next((item for item in self.world.get(collection, []) or [] if str(item.get("record_id")) == str(owner.get("record_id"))), {})
        return _display_name(record, kind)

    def refresh_events(self) -> None:
        self.event_tree.delete(*self.event_tree.get_children())
        for event in sorted(self.address_events(), key=lambda item: (str(item.get("date", "")), str(item.get("time", "")))):
            event_id = str(event.get("record_id", "") or "")
            if event_id:
                self.event_tree.insert("", "end", iid=event_id, text=str(event.get("title", "Event")), values=(event.get("date", ""), str(event.get("event_type", "")).replace("address_", "").replace("_", " ").title(), self.owner_name(event)))

    def add_event(self) -> None:
        address = self.selected_address()
        if address is None:
            messagebox.showinfo("Choose address", "Select an address first.", parent=self)
            return
        def accept(value: dict) -> None:
            self.events.append(value); self.refresh_events()
        AddressEventEditor(self, self.world, address, None, accept)

    def edit_event(self) -> None:
        selected = self.event_tree.selection()
        address = self.selected_address()
        event = next((item for item in self.events if selected and str(item.get("record_id")) == selected[0]), None)
        if address is None or event is None:
            return
        def accept(value: dict) -> None:
            event.clear(); event.update(value); self.refresh_events()
        AddressEventEditor(self, self.world, address, event, accept)

    def delete_event(self) -> None:
        selected = set(self.event_tree.selection())
        if selected:
            self.events = [item for item in self.events if str(item.get("record_id")) not in selected]
            self.refresh_events()

    def apply(self) -> None:
        self.callback(self.addresses, self.events)
        self.destroy()
