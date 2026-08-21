from __future__ import annotations

import calendar
import re
import tkinter as tk
from copy import deepcopy
from datetime import datetime, timezone
from tkinter import messagebox, ttk
from typing import Callable
from uuid import uuid4

from headmasters_scroll.campaigns import (
    format_game_world_date,
    normalize_game_world_date,
)


PAPER = "#ead7aa"
LIGHT = "#f8edcf"
FIELD = "#fff8e6"
EDGE = "#c9aa71"
INK = "#382719"
MUTED = "#765f45"

ADDRESS_EVENT_TYPES = (
    ("address_owner_changed", "New owner"),
    ("address_occupancy_changed", "New occupant"),
    ("address_contents_changed", "New inventory"),
)
ADDRESS_EVENT_LABELS = dict(ADDRESS_EVENT_TYPES)
ADDRESS_EVENT_TYPES_BY_LABEL = {
    label: event_type for event_type, label in ADDRESS_EVENT_TYPES
}


def address_event_type_label(event_type: object) -> str:
    """Return the human event label without exposing the storage key."""

    return ADDRESS_EVENT_LABELS.get(
        str(event_type or "").strip(), "Address event"
    )


INVENTORY_COLLECTIONS = (
    "general_items",
    "raw_materials",
    "holdable_items",
    "accessories",
    "wands",
    "potions",
    "preparations",
    "foods_and_drinks",
    "books",
)


def inherited_address_inventory(
    world: dict,
    address_id: str,
    *,
    before_date: str = "",
    before_time: str = "",
    exclude_event_id: str = "",
) -> list[dict]:
    """Copy the last effective inventory; never mutate the prior event."""

    def event_key(date_value: object, time_value: object = "") -> tuple[int, int, int, int, int]:
        normalized = parse_address_event_date(date_value)
        negative = normalized.startswith("-")
        body = normalized[1:] if negative else normalized
        year_text, month_text, day_text = body.split("-")
        year = -int(year_text) if negative else int(year_text)
        clock = normalize_address_event_time(time_value) or "00:00"
        hour_text, minute_text = clock.split(":")
        return year, int(month_text), int(day_text), int(hour_text), int(minute_text)

    cutoff = None
    if before_date:
        cutoff = event_key(before_date, before_time)
    candidates: list[tuple[tuple[int, int, int, int, int], str, dict]] = []
    for event in world.get("events", []) or []:
        if not isinstance(event, dict):
            continue
        if str(event.get("record_id", "")) == str(exclude_event_id or ""):
            continue
        if str(event.get("event_type", "")) != "address_contents_changed":
            continue
        if str(address_id) not in {str(value) for value in event.get("address_ids", []) or []}:
            continue
        try:
            key = event_key(event.get("date", ""), event.get("time", ""))
        except ValueError:
            continue
        if cutoff is not None and key >= cutoff:
            continue
        candidates.append((key, str(event.get("record_id", "")), event))
    if not candidates:
        return []
    inventory = max(candidates, key=lambda item: item[:2])[2].get("inventory", [])
    return deepcopy(inventory) if isinstance(inventory, list) else []


class InventoryReferenceChooser(tk.Toplevel):
    """Search the item catalog instead of forcing a large select box."""

    def __init__(self, parent: tk.Misc, catalog: dict, callback: Callable[[dict], None]):
        super().__init__(parent)
        self.title("Add inventory item")
        self.geometry("720x500")
        self.minsize(560, 380)
        self.transient(parent)
        _apply_dialog_theme(self)
        self.callback = callback
        self.rows: list[dict] = []
        for collection in INVENTORY_COLLECTIONS:
            for record in catalog.get(collection, []) or []:
                if not isinstance(record, dict):
                    continue
                record_id = str(record.get("record_id", "") or "")
                name = str(
                    record.get("name")
                    or record.get("title")
                    or record.get("item_name")
                    or ""
                ).strip()
                if record_id and name:
                    self.rows.append({
                        "collection": collection,
                        "catalog_record_id": record_id,
                        "name": name,
                    })
        shell = ttk.Frame(self, padding=10, style="Address.TFrame")
        shell.pack(fill="both", expand=True)
        self.query = tk.StringVar()
        entry = ttk.Entry(shell, textvariable=self.query, style="Address.TEntry")
        entry.pack(fill="x")
        self.tree = ttk.Treeview(
            shell, columns=("kind",), show="tree headings", selectmode="browse"
        )
        self.tree.heading("#0", text="Item")
        self.tree.heading("kind", text="Catalog")
        self.tree.column("#0", width=430)
        self.tree.column("kind", width=180)
        self.tree.pack(fill="both", expand=True, pady=7)
        actions = ttk.Frame(shell, style="Address.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Add", command=self.accept).pack(side="right", padx=(0, 5))
        self.query.trace_add("write", lambda *_: self.refresh())
        self.tree.bind("<Double-Button-1>", lambda _event: self.accept())
        self.bind("<Escape>", lambda _event: self.destroy())
        self.refresh()
        entry.focus_set()
        self.grab_set()

    def refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        query = self.query.get().strip().casefold()
        for index, row in enumerate(self.rows):
            haystack = f"{row['name']} {row['collection']}".casefold()
            if query and query not in haystack:
                continue
            self.tree.insert(
                "", "end", iid=str(index), text=row["name"],
                values=(row["collection"].replace("_", " ").title(),),
            )

    def accept(self) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        row = deepcopy(self.rows[int(selected[0])])
        row.update(record_id=str(uuid4()), quantity=1)
        self.callback(row)
        self.destroy()


def parse_address_event_date(value: object) -> str:
    """Accept the established display date or canonical ISO storage date."""

    raw = " ".join(str(value or "").strip().split())
    if not raw:
        raise ValueError("Enter a Game World Date.")
    try:
        return normalize_game_world_date(raw)
    except ValueError:
        pass
    shown = re.fullmatch(
        r"(?P<day>\d{1,2})\s+(?P<month>[A-Za-z]{3,9})\s+"
        r"(?P<year>[1-9]\d*)\s*(?P<era>BCE|BC|CE|AD)?",
        raw,
        re.IGNORECASE,
    )
    if shown is None:
        raise ValueError("Use DD Mmm YYYY, for example 27 Aug 2000.")
    month_text = shown.group("month")[:3].title()
    try:
        month = list(calendar.month_abbr).index(month_text)
    except ValueError as error:
        raise ValueError("Enter a valid month name.") from error
    year = int(shown.group("year"))
    if (shown.group("era") or "").upper() in {"BCE", "BC"}:
        year = -year
    shown_year = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    return normalize_game_world_date(
        f"{shown_year}-{month:02d}-{int(shown.group('day')):02d}"
    )


def format_address_event_date(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        return format_game_world_date(raw)
    except ValueError:
        return raw


def split_address_event_date(value: object) -> tuple[str, str, str]:
    """Return the canonical date as the standard Year, Month, Day fields."""

    raw = str(value or "").strip()
    if not raw:
        return "", "", ""
    canonical = parse_address_event_date(raw)
    negative = canonical.startswith("-")
    body = canonical[1:] if negative else canonical
    year_text, month_text, day_text = body.split("-")
    year = int(year_text)
    return (
        f"-{year}" if negative else str(year),
        str(int(month_text)),
        str(int(day_text)),
    )


def compose_address_event_date(
    year_value: object,
    month_value: object,
    day_value: object,
) -> str:
    """Validate standard Year, Month, Day fields and return canonical storage."""

    year_text = str(year_value or "").strip()
    month_text = str(month_value or "").strip()
    day_text = str(day_value or "").strip()
    if not year_text or not month_text or not day_text:
        raise ValueError("Enter the year, month, and day.")
    try:
        year = int(year_text)
        month = int(month_text)
        day = int(day_text)
    except ValueError as error:
        raise ValueError("Year, month, and day must be numbers.") from error
    if year == 0:
        raise ValueError("Year zero is not valid; use -1 for 1 BCE.")
    shown_year = f"-{abs(year):04d}" if year < 0 else f"{year:04d}"
    return normalize_game_world_date(f"{shown_year}-{month:02d}-{day:02d}")


def prompt_game_world_date(
    parent: tk.Misc,
    *,
    title: str = "Game World Date",
    initial: object = "",
) -> str:
    """Show the project's standard three-field historical date editor."""

    year, month, day = split_address_event_date(initial)
    result: list[str] = []
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.transient(parent)
    dialog.resizable(False, False)
    _apply_dialog_theme(dialog)
    shell = ttk.Frame(dialog, padding=14, style="Address.TFrame")
    shell.pack(fill="both", expand=True)
    fields = ttk.Frame(shell, padding=12, style="AddressCard.TFrame")
    fields.pack(fill="x")
    values = (
        ("Year", tk.StringVar(value=year), 12),
        ("Month", tk.StringVar(value=month), 8),
        ("Day", tk.StringVar(value=day), 8),
    )
    for column, (label, variable, width) in enumerate(values):
        fields.columnconfigure(column, weight=1)
        ttk.Label(fields, text=label, style="AddressCard.TLabel").grid(
            row=0, column=column, sticky="w", padx=(0 if column == 0 else 7, 0)
        )
        entry = ttk.Entry(
            fields, textvariable=variable, width=width, style="Address.TEntry"
        )
        entry.grid(
            row=1, column=column, sticky="ew", padx=(0 if column == 0 else 7, 0),
            pady=(3, 0),
        )
        if column == 0:
            entry.focus_set()

    def accept() -> None:
        try:
            result.append(compose_address_event_date(*(row[1].get() for row in values)))
        except ValueError as error:
            messagebox.showerror("Invalid date", str(error), parent=dialog)
            return
        dialog.destroy()

    actions = ttk.Frame(shell, style="Address.TFrame")
    actions.pack(fill="x", pady=(10, 0))
    ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
    ttk.Button(actions, text="Apply", command=accept).pack(
        side="right", padx=(0, 6)
    )
    dialog.bind("<Return>", lambda _event: accept())
    dialog.bind("<Escape>", lambda _event: dialog.destroy())
    dialog.grab_set()
    dialog.wait_window()
    return result[0] if result else ""


def normalize_address_event_time(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    compact = raw.replace(":", "")
    if not re.fullmatch(r"\d{4}", compact):
        raise ValueError("Use a 24-hour time such as 08:30.")
    hour, minute = int(compact[:2]), int(compact[2:])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("Enter a valid 24-hour time.")
    return f"{hour:02d}:{minute:02d}"


def _apply_dialog_theme(window: tk.Toplevel) -> None:
    window.configure(background=PAPER)
    style = ttk.Style(window)
    style.configure("Address.TFrame", background=PAPER)
    style.configure("AddressCard.TFrame", background=LIGHT)
    style.configure("Address.TLabel", background=PAPER, foreground=INK)
    style.configure("AddressCard.TLabel", background=LIGHT, foreground=INK)
    style.configure("AddressMuted.TLabel", background=LIGHT, foreground=MUTED)
    style.configure("Address.TEntry", fieldbackground=FIELD, foreground=INK)
    style.configure("Address.TCombobox", fieldbackground=FIELD, foreground=INK)


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
    """Search or create addresses belonging to the current location."""

    def __init__(self, parent: tk.Misc, world: dict, location_id: str, callback: Callable[[dict], None]):
        super().__init__(parent)
        self.title("Link address")
        self.geometry("620x450")
        self.minsize(480, 340)
        self.transient(parent)
        self.callback = callback
        self.world = world
        self.location_id = str(location_id)
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
        ttk.Button(
            actions,
            text="+ Add address",
            command=self.add_address,
        ).pack(side="left")
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

    def add_address(self) -> None:
        def accept(address: dict) -> None:
            address["location_id"] = self.location_id
            self.world.setdefault("addresses", []).append(address)
            self.rows.append(address)
            self.rows.sort(key=lambda item: str(item.get("name", "")).casefold())
            self.refill()
            address_id = str(address["record_id"])
            if self.tree.exists(address_id):
                self.tree.selection_set(address_id)
                self.tree.focus(address_id)
                self.tree.see(address_id)
                self.after_idle(self.choose)

        AddressEditor(self, None, accept)


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
    EVENT_TYPES = ADDRESS_EVENT_TYPES

    def __init__(self, parent: tk.Misc, world: dict, catalog: dict, address: dict, value: dict | None, callback: Callable[[dict], None]):
        super().__init__(parent)
        value = value or {}
        self.title("Edit address event" if value.get("record_id") else "Add address event")
        self.geometry("700x510")
        self.minsize(620, 470)
        self.transient(parent)
        _apply_dialog_theme(self)
        self.world = world
        self.catalog = catalog
        self.address = address
        self.callback = callback
        self.record_id = str(value.get("record_id") or uuid4())
        event_label = address_event_type_label(
            value.get("event_type") or "address_owner_changed"
        )
        self.event_type_label = tk.StringVar(value=event_label)
        self._last_default_title = event_label
        year, month, day = split_address_event_date(value.get("date", ""))
        self.date_year = tk.StringVar(value=year)
        self.date_month = tk.StringVar(value=month)
        self.date_day = tk.StringVar(value=day)
        self.time = tk.StringVar(
            value=normalize_address_event_time(value.get("time", ""))
        )
        self.title_value = tk.StringVar(
            value=str(value.get("title", "")) or event_label
        )
        self.owner = deepcopy(value.get("owner_reference")) if isinstance(value.get("owner_reference"), dict) else None
        self.owner_label = tk.StringVar(value=self.owner_name())
        self.inventory = deepcopy(value.get("inventory", [])) if isinstance(value.get("inventory"), list) else []
        self._inventory_initialized = bool(value.get("record_id"))
        shell = ttk.Frame(self, padding=14, style="Address.TFrame")
        shell.pack(fill="both", expand=True)
        card = ttk.Frame(shell, padding=16, style="AddressCard.TFrame")
        card.pack(fill="both", expand=True)
        ttk.Label(
            card,
            text="Address event",
            style="AddressCard.TLabel",
            font=("Georgia", 15, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            card,
            text=str(address.get("name", "Address")),
            style="AddressMuted.TLabel",
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(1, 12))

        main_fields = ttk.Frame(card, style="AddressCard.TFrame")
        main_fields.pack(fill="x")
        main_fields.columnconfigure(0, weight=3)
        main_fields.columnconfigure(1, weight=2)
        ttk.Label(
            main_fields, text="Event title", style="AddressCard.TLabel"
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(
            main_fields, text="Event type", style="AddressCard.TLabel"
        ).grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Entry(
            main_fields,
            textvariable=self.title_value,
            style="Address.TEntry",
        ).grid(row=1, column=0, sticky="ew", pady=(3, 0))
        ttk.Combobox(
            main_fields,
            textvariable=self.event_type_label,
            state="readonly",
            values=[label for _key, label in self.EVENT_TYPES],
            style="Address.TCombobox",
        ).grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=(3, 0))

        date_fields = ttk.Frame(card, style="AddressCard.TFrame")
        date_fields.pack(fill="x", pady=(12, 0))
        date_values = (
            ("Year", self.date_year),
            ("Month", self.date_month),
            ("Day", self.date_day),
            ("Time (24-hour)", self.time),
        )
        for column, (label, variable) in enumerate(date_values):
            date_fields.columnconfigure(column, weight=2 if column == 0 else 1)
            ttk.Label(
                date_fields, text=label, style="AddressCard.TLabel"
            ).grid(
                row=0, column=column, sticky="w",
                padx=(0 if column == 0 else 8, 0),
            )
            ttk.Entry(
                date_fields,
                textvariable=variable,
                style="Address.TEntry",
            ).grid(
                row=1, column=column, sticky="ew",
                padx=(0 if column == 0 else 8, 0), pady=(3, 0),
            )

        self.owner_row = ttk.Frame(card, style="AddressCard.TFrame")
        self.owner_row.pack(fill="x", pady=(12, 9))
        ttk.Label(
            self.owner_row, textvariable=self.owner_label, style="AddressCard.TLabel"
        ).pack(side="left", fill="x", expand=True)
        self.choose_owner_button = ttk.Button(self.owner_row, text="Choose…", command=self.choose_owner)
        self.choose_owner_button.pack(side="left")
        ttk.Button(self.owner_row, text="Clear", command=self.clear_owner).pack(side="left", padx=(4, 0))
        self.inventory_frame = ttk.Frame(card, style="AddressCard.TFrame")
        inventory_header = ttk.Frame(self.inventory_frame, style="AddressCard.TFrame")
        inventory_header.pack(fill="x")
        ttk.Label(inventory_header, text="Inventory after this event", style="AddressCard.TLabel").pack(side="left")
        ttk.Button(inventory_header, text="−", width=3, command=self.remove_inventory_item).pack(side="right")
        ttk.Button(inventory_header, text="+", width=3, command=self.add_inventory_item).pack(side="right", padx=(0, 3))
        self.inventory_tree = ttk.Treeview(
            self.inventory_frame, columns=("kind", "quantity"), show="tree headings", height=6
        )
        self.inventory_tree.heading("#0", text="Item")
        self.inventory_tree.heading("kind", text="Kind")
        self.inventory_tree.heading("quantity", text="Qty")
        self.inventory_tree.column("#0", width=310)
        self.inventory_tree.column("kind", width=140)
        self.inventory_tree.column("quantity", width=55, anchor="center")
        self.inventory_tree.pack(fill="x", pady=(3, 8))
        self.inventory_tree.bind("<Double-Button-1>", lambda _event: self.edit_inventory_quantity())
        self.description_label = ttk.Label(
            card, text="Description", style="AddressCard.TLabel"
        )
        self.description_label.pack(anchor="w")
        self.description = tk.Text(
            card,
            height=8,
            wrap="word",
            background=FIELD,
            foreground=INK,
            insertbackground=INK,
            relief="solid",
            borderwidth=1,
            highlightthickness=0,
        )
        self.description.pack(fill="both", expand=True, pady=(3, 8))
        self.description.insert("1.0", str(value.get("description", "")))
        actions = ttk.Frame(card, style="AddressCard.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Cancel", command=self.destroy).pack(side="right")
        ttk.Button(actions, text="Apply", command=self.apply).pack(side="right", padx=(0, 7))
        self.event_type_label.trace_add("write", self._event_type_changed)
        self.bind("<Escape>", lambda _event: self.destroy())
        self._event_type_changed()
        self.grab_set()

    def _event_type_changed(self, *_args) -> None:
        next_default = self.event_type_label.get().strip()
        current_title = self.title_value.get().strip()
        if not current_title or current_title == self._last_default_title:
            self.title_value.set(next_default)
        self._last_default_title = next_default
        event_type = ADDRESS_EVENT_TYPES_BY_LABEL.get(next_default, "address_owner_changed")
        if event_type == "address_contents_changed":
            self.owner_row.pack_forget()
            self.inventory_frame.pack(fill="x", pady=(12, 2), before=self.description_label)
            if not self._inventory_initialized:
                try:
                    before_date = compose_address_event_date(
                        self.date_year.get(),
                        self.date_month.get(),
                        self.date_day.get(),
                    )
                except ValueError:
                    before_date = ""
                self.inventory = inherited_address_inventory(
                    self.world,
                    str(self.address.get("record_id", "")),
                    before_date=before_date,
                    before_time=self.time.get(),
                    exclude_event_id=self.record_id,
                )
                self._inventory_initialized = True
            self.refresh_inventory()
        else:
            self.inventory_frame.pack_forget()
            if not self.owner_row.winfo_manager():
                self.owner_row.pack(fill="x", pady=(12, 9), before=self.description_label)
            noun = "occupant" if event_type == "address_occupancy_changed" else "owner"
            self.choose_owner_button.configure(text=f"Choose {noun}…")
            self.owner_label.set(self.owner_name(noun))

    def refresh_inventory(self) -> None:
        self.inventory_tree.delete(*self.inventory_tree.get_children())
        for item in self.inventory:
            item_id = str(item.get("record_id", "") or uuid4())
            item["record_id"] = item_id
            self.inventory_tree.insert(
                "", "end", iid=item_id, text=str(item.get("name", "Item")),
                values=(str(item.get("collection", "")).replace("_", " ").title(), int(item.get("quantity", 1) or 1)),
            )

    def add_inventory_item(self) -> None:
        def accept(item: dict) -> None:
            self.inventory.append(item)
            self.refresh_inventory()
        InventoryReferenceChooser(self, self.catalog, accept)

    def remove_inventory_item(self) -> None:
        selected = set(self.inventory_tree.selection())
        if selected:
            self.inventory = [item for item in self.inventory if str(item.get("record_id")) not in selected]
            self.refresh_inventory()

    def edit_inventory_quantity(self) -> None:
        selected = self.inventory_tree.selection()
        item = next((row for row in self.inventory if selected and str(row.get("record_id")) == selected[0]), None)
        if item is None:
            return
        from tkinter import simpledialog
        quantity = simpledialog.askinteger(
            "Inventory quantity", "Quantity", initialvalue=int(item.get("quantity", 1) or 1),
            minvalue=1, maxvalue=999999, parent=self,
        )
        if quantity is not None:
            item["quantity"] = quantity
            self.refresh_inventory()

    def owner_name(self, noun: str = "owner") -> str:
        if not self.owner:
            return f"No {noun} linked"
        kind = str(self.owner.get("owner_type", ""))
        collection = "people" if kind == "person" else "organizations"
        record = next((
            item for item in self.world.get(collection, []) or []
            if str(item.get("record_id", "")) == str(self.owner.get("record_id", ""))
        ), {})
        return f"{noun.title()}: {_display_name(record, kind)}"

    def choose_owner(self) -> None:
        def accept(value: dict) -> None:
            self.owner = {key: value[key] for key in ("owner_type", "record_id")}
            noun = "occupant" if ADDRESS_EVENT_TYPES_BY_LABEL.get(self.event_type_label.get()) == "address_occupancy_changed" else "owner"
            self.owner_label.set(f"{noun.title()}: {value['display_name']}")
        WorldReferenceChooser(self, self.world, accept)

    def clear_owner(self) -> None:
        self.owner = None
        self._event_type_changed()

    def apply(self) -> None:
        title = self.title_value.get().strip()
        if not title:
            messagebox.showerror(
                "Incomplete event", "Enter an event title.", parent=self
            )
            return
        try:
            date_value = compose_address_event_date(
                self.date_year.get(),
                self.date_month.get(),
                self.date_day.get(),
            )
            time_value = normalize_address_event_time(self.time.get())
        except ValueError as error:
            messagebox.showerror("Invalid event date", str(error), parent=self)
            return
        event_type = ADDRESS_EVENT_TYPES_BY_LABEL.get(
            self.event_type_label.get(), "address_owner_changed"
        )
        value = {
            "record_id": self.record_id,
            "event_type": event_type,
            "title": title,
            "date": date_value,
            "time": time_value,
            "description": self.description.get("1.0", "end-1c").strip(),
            "address_ids": [str(self.address["record_id"])],
        }
        if event_type == "address_contents_changed":
            value["inventory"] = deepcopy(self.inventory)
        elif self.owner:
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
        catalog: dict,
        location_id: str,
        callback: Callable[[list, list], None],
        *,
        selected_address_id: str = "",
    ):
        super().__init__(parent)
        self.world = world
        self.catalog = catalog
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
                self.event_tree.insert(
                    "",
                    "end",
                    iid=event_id,
                    text=str(event.get("title", "Event")),
                    values=(
                        format_address_event_date(event.get("date", "")),
                        address_event_type_label(event.get("event_type")),
                        self.owner_name(event),
                    ),
                )

    def add_event(self) -> None:
        address = self.selected_address()
        if address is None:
            messagebox.showinfo("Choose address", "Select an address first.", parent=self)
            return
        def accept(value: dict) -> None:
            self.events.append(value); self.refresh_events()
        editor_world = {**self.world, "events": self.events, "addresses": self.addresses}
        AddressEventEditor(self, editor_world, self.catalog, address, None, accept)

    def edit_event(self) -> None:
        selected = self.event_tree.selection()
        address = self.selected_address()
        event = next((item for item in self.events if selected and str(item.get("record_id")) == selected[0]), None)
        if address is None or event is None:
            return
        def accept(value: dict) -> None:
            event.clear(); event.update(value); self.refresh_events()
        editor_world = {**self.world, "events": self.events, "addresses": self.addresses}
        AddressEventEditor(self, editor_world, self.catalog, address, event, accept)

    def delete_event(self) -> None:
        selected = set(self.event_tree.selection())
        if selected:
            self.events = [item for item in self.events if str(item.get("record_id")) not in selected]
            self.refresh_events()

    def apply(self) -> None:
        self.callback(self.addresses, self.events)
        self.destroy()
