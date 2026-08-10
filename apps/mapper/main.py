from __future__ import annotations

import os
import sys
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from headmasters_scroll.board import WorldBoardRepository, ensure_board_collections
from headmasters_scroll.windowing import apply_window_icon, configure_windows_app_id, maximize_window


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class MapperWindow(tk.Tk):
    PAPER = "#ead7aa"
    LIGHT = "#f8edcf"
    EDGE = "#c9aa71"
    INK = "#382719"
    MUTED = "#765f45"
    ACCENT = "#7b3f2b"

    def __init__(self) -> None:
        super().__init__()
        self.repository = WorldBoardRepository()
        self.world_session = None
        self.maps: list[dict] = []
        self.locations: list[dict] = []
        self.selected_map_id = ""
        self.pending_image: Path | None = None
        self.location_options: dict[str, str] = {}
        self.floor_options: dict[str, str] = {}
        self.preview_image = None
        self.title("Mapper")
        self.geometry("1180x760")
        self.minsize(820, 560)
        self.configure(background=self.PAPER)
        apply_window_icon(self)
        self._configure_style()
        self._build()
        self.refresh()
        self.after_idle(lambda: maximize_window(self))

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Mapper.TFrame", background=self.PAPER)
        style.configure("MapperCard.TFrame", background=self.LIGHT, relief="solid", borderwidth=1)
        style.configure("Mapper.TLabel", background=self.PAPER, foreground=self.INK)
        style.configure("MapperCard.TLabel", background=self.LIGHT, foreground=self.INK)
        style.configure("MapperTitle.TLabel", background=self.PAPER, foreground=self.INK, font=("Georgia", 22, "bold"))
        style.configure("TButton", background=self.ACCENT, foreground="#fff8e7", padding=(10, 7))
        style.map("TButton", background=[("active", "#63311f")])
        style.configure("Treeview", rowheight=28, background="#fff8e6", fieldbackground="#fff8e6")
        style.configure("Treeview.Heading", background=self.EDGE, foreground=self.INK)

    def _build(self) -> None:
        header = ttk.Frame(self, style="Mapper.TFrame")
        header.pack(fill="x", padx=12, pady=(8, 6))
        ttk.Label(header, text="Mapper", style="MapperTitle.TLabel").pack(side="left")
        self.status_value = tk.StringVar(value="Loading world maps…")
        ttk.Label(header, textvariable=self.status_value, style="Mapper.TLabel").pack(side="right")

        workspace = ttk.Panedwindow(self, orient="horizontal")
        workspace.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        catalog = ttk.Frame(workspace, style="MapperCard.TFrame", padding=10)
        workspace.add(catalog, weight=2)
        ttk.Label(catalog, text="Map Catalog", background=self.LIGHT, foreground=self.INK, font=("Georgia", 16, "bold")).pack(anchor="w", pady=(0, 8))
        search_row = ttk.Frame(catalog, style="MapperCard.TFrame")
        search_row.pack(fill="x", pady=(0, 8))
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", lambda *_: self.render_catalog())
        ttk.Entry(search_row, textvariable=self.search_value).pack(side="left", fill="x", expand=True)
        ttk.Button(search_row, text="New", command=self.new_map).pack(side="left", padx=(6, 0))
        self.map_tree = ttk.Treeview(catalog, columns=("place", "floor", "status"), show="tree headings", selectmode="browse")
        self.map_tree.heading("#0", text="Map")
        self.map_tree.heading("place", text="Location")
        self.map_tree.heading("floor", text="Floor")
        self.map_tree.heading("status", text="Status")
        self.map_tree.column("#0", width=190)
        self.map_tree.column("place", width=190)
        self.map_tree.column("floor", width=120)
        self.map_tree.column("status", width=90)
        self.map_tree.pack(fill="both", expand=True)
        self.map_tree.bind("<<TreeviewSelect>>", self.select_map)
        self.completeness_value = tk.StringVar()
        ttk.Label(catalog, textvariable=self.completeness_value, style="MapperCard.TLabel", wraplength=480).pack(fill="x", pady=(8, 0))

        editor = ttk.Frame(workspace, style="MapperCard.TFrame", padding=16)
        workspace.add(editor, weight=3)
        ttk.Label(editor, text="Map Details", background=self.LIGHT, foreground=self.INK, font=("Georgia", 16, "bold")).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        editor.columnconfigure(1, weight=1)
        editor.rowconfigure(8, weight=1)
        self.name_value = tk.StringVar()
        self.location_value = tk.StringVar()
        self.floor_value = tk.StringVar(value="No floor")
        self.published_value = tk.BooleanVar(value=False)
        self.default_value = tk.BooleanVar(value=False)
        self.primary_value = tk.BooleanVar(value=False)
        self.image_value = tk.StringVar(value="No image selected")

        self._field(editor, 1, "Name", ttk.Entry(editor, textvariable=self.name_value))
        self.location_select = ttk.Combobox(editor, textvariable=self.location_value, state="readonly")
        self._field(editor, 2, "Location", self.location_select)
        self.location_select.bind("<<ComboboxSelected>>", lambda _event: self.refresh_floors())
        self.floor_select = ttk.Combobox(editor, textvariable=self.floor_value, state="readonly")
        self._field(editor, 3, "Floor", self.floor_select)
        self.floor_select.bind("<<ComboboxSelected>>", lambda _event: self.refresh_flags())

        flags = ttk.Frame(editor, style="MapperCard.TFrame")
        flags.grid(row=4, column=0, columnspan=3, sticky="ew", pady=8)
        ttk.Checkbutton(flags, text="Published to players", variable=self.published_value).pack(side="left")
        ttk.Checkbutton(flags, text="Location default", variable=self.default_value).pack(side="left", padx=14)
        ttk.Checkbutton(flags, text="Primary floor map", variable=self.primary_value).pack(side="left")

        image_row = ttk.Frame(editor, style="MapperCard.TFrame")
        image_row.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(4, 8))
        ttk.Button(image_row, text="Choose / Replace Image", command=self.choose_image).pack(side="left")
        ttk.Label(image_row, textvariable=self.image_value, style="MapperCard.TLabel").pack(side="left", padx=10)

        self.preview = tk.Label(editor, text="Map preview", background="#e1c991", foreground=self.MUTED, relief="solid", borderwidth=1)
        self.preview.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(4, 10))
        actions = ttk.Frame(editor, style="MapperCard.TFrame")
        actions.grid(row=9, column=0, columnspan=3, sticky="ew")
        ttk.Button(actions, text="Save Map", command=self.save_map).pack(side="right")
        ttk.Button(actions, text="Reload", command=self.refresh).pack(side="right", padx=(0, 8))

    @staticmethod
    def _field(parent: tk.Misc, row: int, label: str, widget: tk.Widget) -> None:
        ttk.Label(parent, text=label, style="MapperCard.TLabel").grid(row=row, column=0, sticky="w", pady=5, padx=(0, 10))
        widget.grid(row=row, column=1, columnspan=2, sticky="ew", pady=5)

    def refresh(self) -> None:
        try:
            self.world_session = self.repository.load()
            ensure_board_collections(self.world_session.data)
            self.maps = list(self.world_session.data.get("maps", []))
            self.locations = sorted(
                self.world_session.data.get("locations", []),
                key=lambda item: str(item.get("name", "")).casefold(),
            )
            self.location_options = {
                f"{item.get('name', 'Unnamed')}  [{item.get('record_id')} ]": str(item.get("record_id"))
                for item in self.locations
            }
            values = list(self.location_options)
            self.location_select.configure(values=values)
            self.render_catalog()
            self.render_completeness()
            if self.selected_map_id:
                record = next((item for item in self.maps if item.get("record_id") == self.selected_map_id), None)
                if record:
                    self.load_map(record)
            self.status_value.set(f"{len(self.maps)} maps • {len(self.locations)} locations")
        except Exception as error:
            messagebox.showerror("Mapper", str(error), parent=self)

    def render_catalog(self) -> None:
        query = self.search_value.get().strip().casefold()
        location_names = {str(item.get("record_id")): str(item.get("name", "")) for item in self.locations}
        floors = {
            str(floor.get("record_id")): str(floor.get("name", ""))
            for location in self.locations
            for floor in location.get("floors", []) or []
        }
        self.map_tree.delete(*self.map_tree.get_children())
        for record in sorted(self.maps, key=lambda item: str(item.get("name", "")).casefold()):
            haystack = " ".join((str(record.get("name", "")), location_names.get(str(record.get("location_id")), ""), floors.get(str(record.get("floor_id")), ""))).casefold()
            if query and query not in haystack:
                continue
            status = "Ready" if record.get("asset") else "Missing image"
            self.map_tree.insert("", "end", iid=str(record["record_id"]), text=record.get("name", "Unnamed"), values=(location_names.get(str(record.get("location_id")), "Missing"), floors.get(str(record.get("floor_id")), "—"), status))

    def render_completeness(self) -> None:
        mapped_locations = {str(item.get("location_id")) for item in self.maps}
        missing_locations = [item for item in self.locations if str(item.get("record_id")) not in mapped_locations]
        floors = [floor for item in self.locations for floor in item.get("floors", []) or []]
        mapped_floors = {str(item.get("floor_id")) for item in self.maps if item.get("floor_id")}
        missing_floors = [floor for floor in floors if str(floor.get("record_id")) not in mapped_floors]
        self.completeness_value.set(f"Incomplete legacy records: {len(missing_locations)} locations and {len(missing_floors)} named floors have no map yet.")

    def new_map(self) -> None:
        self.selected_map_id = ""
        self.pending_image = None
        self.name_value.set("")
        self.location_value.set("")
        self.floor_value.set("No floor")
        self.published_value.set(False)
        self.default_value.set(False)
        self.primary_value.set(False)
        self.image_value.set("No image selected")
        self.preview.configure(image="", text="Map preview")
        self.preview_image = None

    def select_map(self, _event: tk.Event | None = None) -> None:
        selected = self.map_tree.selection()
        if not selected:
            return
        record = next((item for item in self.maps if str(item.get("record_id")) == selected[0]), None)
        if record:
            self.load_map(record)

    def load_map(self, record: dict) -> None:
        self.selected_map_id = str(record.get("record_id"))
        self.pending_image = None
        self.name_value.set(str(record.get("name", "")))
        location_id = str(record.get("location_id", ""))
        label = next((label for label, value in self.location_options.items() if value == location_id), "")
        self.location_value.set(label)
        self.refresh_floors(str(record.get("floor_id", "")))
        self.published_value.set(bool(record.get("players_published")))
        self.refresh_flags()
        asset = record.get("asset")
        self.image_value.set("Image ready" if asset else "No image selected")
        self.show_preview(record)

    def refresh_floors(self, selected_floor_id: str = "") -> None:
        location_id = self.location_options.get(self.location_value.get(), "")
        location = next((item for item in self.locations if str(item.get("record_id")) == location_id), None)
        self.floor_options = {"No floor": ""}
        for floor in (location or {}).get("floors", []) or []:
            self.floor_options[f"{floor.get('name', 'Unnamed')}  [{floor.get('record_id')}]"] = str(floor.get("record_id"))
        self.floor_select.configure(values=list(self.floor_options))
        selected = next((label for label, value in self.floor_options.items() if value == selected_floor_id), "No floor")
        self.floor_value.set(selected)
        self.refresh_flags()

    def refresh_flags(self) -> None:
        location_id = self.location_options.get(self.location_value.get(), "")
        floor_id = self.floor_options.get(self.floor_value.get(), "")
        location = next((item for item in self.locations if str(item.get("record_id")) == location_id), {})
        self.default_value.set(bool(self.selected_map_id and str(location.get("default_map_id", "")) == self.selected_map_id))
        floor = next((item for item in location.get("floors", []) or [] if str(item.get("record_id")) == floor_id), {})
        self.primary_value.set(bool(self.selected_map_id and str(floor.get("primary_map_id", "")) == self.selected_map_id))

    def choose_image(self) -> None:
        filename = filedialog.askopenfilename(parent=self, title="Choose map image", filetypes=(("Map images", "*.png *.jpg *.jpeg *.webp"), ("All files", "*.*")))
        if not filename:
            return
        self.pending_image = Path(filename)
        self.image_value.set(self.pending_image.name)
        self.show_preview_path(self.pending_image)

    def show_preview(self, record: dict) -> None:
        try:
            asset = record.get("asset")
            if not asset:
                raise FileNotFoundError
            self.show_preview_path(self.repository.assets.resolve(str(asset.get("asset_id")), asset))
        except Exception:
            self.preview.configure(image="", text="Map image unavailable")
            self.preview_image = None

    def show_preview_path(self, path: Path) -> None:
        try:
            from PIL import Image, ImageTk

            with Image.open(path) as image:
                preview = image.copy()
            preview.thumbnail((720, 430))
            self.preview_image = ImageTk.PhotoImage(preview)
            self.preview.configure(image=self.preview_image, text="")
        except Exception as error:
            self.preview.configure(image="", text=f"Cannot preview image: {error}")

    def save_map(self) -> None:
        name = self.name_value.get().strip()
        location_id = self.location_options.get(self.location_value.get(), "")
        floor_id = self.floor_options.get(self.floor_value.get(), "")
        if not name or not location_id:
            messagebox.showerror("Cannot save map", "Enter a map name and choose a location.", parent=self)
            return
        if not self.selected_map_id and self.pending_image is None:
            messagebox.showerror("Cannot save map", "Choose a map image.", parent=self)
            return
        try:
            session = self.repository.load()
            record = next((item for item in session.data["maps"] if str(item.get("record_id")) == self.selected_map_id), None)
            now = utc_now()
            if record is None:
                record = {"record_id": str(uuid4()), "created_at": now, "asset": None}
                session.data["maps"].append(record)
            map_id = str(record["record_id"])
            asset = record.get("asset")
            if self.pending_image is not None:
                asset = self.repository.assets.import_map(map_id, self.pending_image)
            record.update(name=name, location_id=location_id, floor_id=floor_id, players_published=bool(self.published_value.get()), asset=asset, last_updated=now)
            for candidate_location in session.data["locations"]:
                if str(candidate_location.get("default_map_id", "")) == map_id:
                    candidate_location["default_map_id"] = ""
                for candidate_floor in candidate_location.get("floors", []) or []:
                    if str(candidate_floor.get("primary_map_id", "")) == map_id:
                        candidate_floor["primary_map_id"] = ""
            location = next(item for item in session.data["locations"] if str(item.get("record_id")) == location_id)
            if self.default_value.get() or not str(location.get("default_map_id", "")):
                location["default_map_id"] = map_id
            elif str(location.get("default_map_id", "")) == map_id:
                location["default_map_id"] = ""
            for floor in location.get("floors", []) or []:
                if str(floor.get("record_id")) != floor_id:
                    continue
                if self.primary_value.get() or not str(floor.get("primary_map_id", "")):
                    floor["primary_map_id"] = map_id
                elif str(floor.get("primary_map_id", "")) == map_id:
                    floor["primary_map_id"] = ""
            self.repository.save(session, "mapper")
            if asset:
                self.repository.assets.prune_map_variants(
                    map_id,
                    str(asset.get("file_extension", "")),
                )
            self.selected_map_id = map_id
            self.pending_image = None
            self.refresh()
            self.status_value.set(f"Saved {name}")
        except Exception as error:
            messagebox.showerror("Cannot save map", str(error), parent=self)


def main() -> None:
    os.environ.setdefault("HEADMASTERS_SCROLL_DATA_DIRECTORY", str(ROOT / "data"))
    configure_windows_app_id("Mapper")
    MapperWindow().mainloop()


if __name__ == "__main__":
    main()
