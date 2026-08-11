from __future__ import annotations

import math
import os
import sys
import tkinter as tk
import traceback
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from headmasters_scroll.board import (
    REGION_BEHAVIOR_TYPES,
    WorldBoardRepository,
    ensure_board_collections,
    normalize_region,
    normalize_warp_point,
)
from headmasters_scroll.assets import MAP_CANVAS_HEIGHT, MAP_CANVAS_WIDTH
from headmasters_scroll.preferences import Preferences
from headmasters_scroll.paths import RUNTIME_DIRECTORY
from headmasters_scroll.windowing import MAPPER_ICON, apply_window_icon, configure_windows_app_id, maximize_window


BEHAVIOR_LABELS = {
    "area": "Area",
    "shop": "Shop",
    "travel": "Travel",
    "library": "Library",
    "other": "Other",
}
BEHAVIOR_COLORS = {
    "area": "#3f729b",
    "shop": "#9a6b20",
    "travel": "#7b3f8c",
    "library": "#3f7853",
    "other": "#765f45",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def point_in_polygon(x: float, y: float, points: list[dict]) -> bool:
    inside = False
    previous = points[-1]
    for current in points:
        if (current["y"] > y) != (previous["y"] > y):
            crossing = (previous["x"] - current["x"]) * (y - current["y"]) / (
                previous["y"] - current["y"]
            ) + current["x"]
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def nearest_edge(points: list[dict], x: float, y: float) -> tuple[int, dict, float]:
    best_index = 0
    best_point = {"x": x, "y": y}
    best_distance = float("inf")
    for index, start in enumerate(points):
        end = points[(index + 1) % len(points)]
        dx, dy = end["x"] - start["x"], end["y"] - start["y"]
        length_squared = dx * dx + dy * dy
        ratio = 0.0 if length_squared == 0 else max(
            0.0, min(1.0, ((x - start["x"]) * dx + (y - start["y"]) * dy) / length_squared)
        )
        projected = {"x": start["x"] + ratio * dx, "y": start["y"] + ratio * dy}
        distance = math.hypot(x - projected["x"], y - projected["y"])
        if distance < best_distance:
            best_index, best_point, best_distance = index, projected, distance
    return best_index, best_point, best_distance


def translated_points(points: list[dict], dx: float, dy: float) -> list[dict]:
    min_x = min(point["x"] for point in points)
    max_x = max(point["x"] for point in points)
    min_y = min(point["y"] for point in points)
    max_y = max(point["y"] for point in points)
    dx = min(max(dx, -min_x), 1.0 - max_x)
    dy = min(max(dy, -min_y), 1.0 - max_y)
    return [{"x": point["x"] + dx, "y": point["y"] + dy} for point in points]


class MapperWindow(tk.Tk):
    PAPER = "#ead7aa"
    LIGHT = "#f8edcf"
    EDGE = "#c9aa71"
    INK = "#382719"
    MUTED = "#765f45"
    ACCENT = "#7b3f2b"
    LINE = "#000000"
    POLYGON_CLOSE_SNAP_RADIUS = 16

    def __init__(self) -> None:
        super().__init__()
        self.repository = WorldBoardRepository()
        self.preferences_store = Preferences("mapper")
        self.preferences = self.preferences_store.load()
        self.world_session = None
        self.maps: list[dict] = []
        self.locations: list[dict] = []
        self.selected_map_id = ""
        self.pending_image: Path | None = None
        self.location_options: dict[str, str] = {}
        self.selected_location_id = ""
        self.selected_floor_id = ""
        self.regions: list[dict] = []
        self.warp_points: list[dict] = []
        self.selected_warp_point_id = ""
        self.selected_region_id = ""
        self.updating_region_selection = False
        self.reporting_callback_exception = False
        self.selected_vertex: int | None = None
        self.draft_points: list[dict] = []
        self.mode = "select"
        self.editor_dirty = False
        self.loading_region_properties = False
        self.metadata_history_pending = False
        self.metadata_save_after_id: str | None = None
        self.undo_stack: list[tuple[list[dict], str]] = []
        self.redo_stack: list[tuple[list[dict], str]] = []
        self.drag_state: dict | None = None
        self.pan_state: tuple[float, float, float, float] | None = None
        self.pan_watchdog_id: str | None = None
        self.map_image = None
        self.tk_map_image = None
        self.tk_map_image_size: tuple | None = None
        self.map_width = MAP_CANVAS_WIDTH
        self.map_height = MAP_CANVAS_HEIGHT
        self.scale = 1.0
        self.fit_scale = 1.0
        self.origin_x = 0.0
        self.origin_y = 0.0
        try:
            self.right_panel_width = max(220, min(420, int(self.preferences.get("right_panel_width", 250))))
        except (TypeError, ValueError):
            self.right_panel_width = 250
        self.title("Mapper")
        self.geometry("1500x900")
        self.minsize(980, 620)
        self.configure(background=self.PAPER)
        self.protocol("WM_DELETE_WINDOW", self.close_window)
        apply_window_icon(self, MAPPER_ICON)
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
        style.configure("MapperTitle.TLabel", background=self.PAPER, foreground=self.INK, font=("Georgia", 18, "bold"))
        style.configure("TButton", background=self.ACCENT, foreground="#fff8e7", padding=(8, 5))
        style.map("TButton", background=[("active", "#63311f")])
        style.configure("Tool.TButton", padding=(6, 4))
        style.configure("Treeview", rowheight=25, background="#fff8e6", fieldbackground="#fff8e6")
        style.configure("Treeview.Heading", background=self.EDGE, foreground=self.INK)

    def _build(self) -> None:
        header = ttk.Frame(self, style="Mapper.TFrame")
        header.pack(fill="x", padx=8, pady=(6, 4))
        ttk.Label(header, text="Mapper", style="MapperTitle.TLabel").pack(side="left")
        self.status_value = tk.StringVar(value="Loading world maps…")
        ttk.Label(header, textvariable=self.status_value, style="Mapper.TLabel").pack(side="right")

        self.workspace = ttk.Panedwindow(self, orient="horizontal")
        self.workspace.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_catalog(self.workspace)
        self._build_canvas(self.workspace)
        self._build_regions(self.workspace)
        self.workspace.bind("<ButtonRelease-1>", lambda _event: self.after_idle(self.remember_right_panel_width))
        self.after(150, self.restore_right_panel_width)

    def _build_catalog(self, workspace: ttk.Panedwindow) -> None:
        catalog = ttk.Frame(workspace, style="MapperCard.TFrame", padding=7, width=290)
        workspace.add(catalog, weight=0)
        ttk.Label(catalog, text="Locations", style="MapperCard.TLabel", font=("Georgia", 14, "bold")).pack(anchor="w")
        row = ttk.Frame(catalog, style="MapperCard.TFrame")
        row.pack(fill="x", pady=5)
        self.search_value = tk.StringVar()
        self.search_value.trace_add("write", lambda *_: self.render_catalog())
        ttk.Entry(row, textvariable=self.search_value).pack(side="left", fill="x", expand=True)
        self.map_tree = ttk.Treeview(catalog, show="tree", selectmode="browse", height=11)
        self.map_tree.heading("#0", text="Location / floor")
        self.map_tree.column("#0", width=250)
        self.map_tree.pack(fill="both", expand=True)
        self.map_tree.bind("<<TreeviewSelect>>", self.select_catalog_item)

        details = ttk.LabelFrame(catalog, text="Base Map", padding=6)
        details.pack(fill="x", pady=(7, 0))
        self.floor_value = tk.StringVar(value="Select a location")
        self.has_floors_value = tk.BooleanVar(value=False)
        self.image_value = tk.StringVar(value="No image")
        ttk.Label(details, textvariable=self.floor_value, style="MapperCard.TLabel", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        ttk.Checkbutton(
            details,
            text="Has floors",
            variable=self.has_floors_value,
            command=self.has_floors_changed,
        ).pack(anchor="w", pady=(4, 0))
        ttk.Label(details, textvariable=self.image_value, wraplength=250).pack(anchor="w", pady=(4, 2))
        buttons = ttk.Frame(details)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Import / Replace Map", command=self.choose_image).pack(side="left")
        self.completeness_value = tk.StringVar()
        ttk.Label(catalog, textvariable=self.completeness_value, style="MapperCard.TLabel", wraplength=260).pack(fill="x", pady=(6, 0))

    def _build_canvas(self, workspace: ttk.Panedwindow) -> None:
        center = ttk.Frame(workspace, style="MapperCard.TFrame", padding=4)
        workspace.add(center, weight=1)
        body = ttk.Frame(center, style="MapperCard.TFrame")
        body.pack(fill="both", expand=True)
        toolbar = ttk.Frame(body, style="MapperCard.TFrame", width=104)
        toolbar.pack(side="left", fill="y", padx=(0, 4))
        toolbar.pack_propagate(False)
        ttk.Label(toolbar, text="TOOLS", style="MapperCard.TLabel", font=("Segoe UI", 8, "bold")).pack(fill="x", pady=(2, 4))
        for label, command in (
            ("Select  [V]", lambda: self.set_mode("select")),
            ("Poly  [P]", lambda: self.set_mode("draw")),
            ("Edit Poly [E]", lambda: self.set_mode("edit")),
            ("Warp  [W]", lambda: self.set_mode("warp")),
            ("Undo", self.undo),
            ("Redo", self.redo),
            ("Fit Map", self.fit_map),
        ):
            ttk.Button(toolbar, text=label, command=command, style="Tool.TButton").pack(fill="x", pady=(0, 3))
        ttk.Separator(toolbar).pack(fill="x", pady=5)
        ttk.Label(toolbar, text="● Base Map", foreground="#765f45", style="MapperCard.TLabel", wraplength=94).pack(fill="x", pady=2)
        ttk.Label(toolbar, text="◆ Shapes", foreground=self.ACCENT, style="MapperCard.TLabel", wraplength=94).pack(fill="x", pady=2)
        self.mode_value = tk.StringVar(value="Select")
        ttk.Label(toolbar, textvariable=self.mode_value, style="MapperCard.TLabel", wraplength=94).pack(side="bottom", fill="x", pady=4)
        self.canvas = tk.Canvas(body, background="#3b3328", highlightthickness=0, cursor="arrow")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _event: self.fit_map())
        self.canvas.bind("<Button-1>", self.canvas_press)
        self.canvas.bind("<B1-Motion>", self.canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self.canvas_release)
        self.canvas.bind("<Double-Button-1>", self.canvas_double_click)
        self.canvas.bind("<Button-3>", self.canvas_right_click)
        self.canvas.bind("<Motion>", self.canvas_motion)
        self.canvas.bind("<Leave>", self.canvas_leave)
        # Listen at the application level. On Windows, using Alt can transfer
        # wheel-event ownership away from the canvas even after Alt is
        # released. Pointer routing below keeps the canvas responsive without
        # stealing scrolling from controls elsewhere in the window.
        self.bind_all("<MouseWheel>", self.route_canvas_wheel)
        self.canvas.bind("<Button-2>", self.pan_press)
        self.bind_all("<B2-Motion>", self.pan_drag)
        self.bind_all("<ButtonRelease-2>", self.pan_release)
        self.bind("<Return>", lambda _event: self.complete_polygon())
        self.bind("<Escape>", lambda _event: self.cancel_drawing())
        self.bind("<Control-z>", lambda _event: self.undo())
        self.bind("<Control-y>", lambda _event: self.redo())
        self.bind("<Control-Key-0>", lambda _event: self.fit_map())
        self.bind("<KeyPress-v>", lambda event: self.tool_shortcut(event, "select"))
        self.bind("<KeyPress-V>", lambda event: self.tool_shortcut(event, "select"))
        self.bind("<KeyPress-p>", lambda event: self.tool_shortcut(event, "draw"))
        self.bind("<KeyPress-P>", lambda event: self.tool_shortcut(event, "draw"))
        self.bind("<KeyPress-e>", lambda event: self.tool_shortcut(event, "edit"))
        self.bind("<KeyPress-E>", lambda event: self.tool_shortcut(event, "edit"))
        self.bind("<KeyPress-w>", lambda event: self.tool_shortcut(event, "warp"))
        self.bind("<KeyPress-W>", lambda event: self.tool_shortcut(event, "warp"))
        self.bind("<Delete>", self.delete_node_shortcut)
        self.bind("<BackSpace>", self.delete_node_shortcut)

    def _build_regions(self, workspace: ttk.Panedwindow) -> None:
        panel = ttk.Frame(workspace, style="MapperCard.TFrame", padding=7, width=self.right_panel_width)
        workspace.add(panel, weight=0)
        self.right_panel = panel
        ttk.Label(panel, text="Interactable Shapes", style="MapperCard.TLabel", font=("Georgia", 14, "bold")).pack(anchor="w")
        self.region_tree = ttk.Treeview(panel, columns=("behavior", "status"), show="tree headings", height=9)
        self.region_tree.heading("#0", text="Name")
        self.region_tree.heading("behavior", text="Behavior")
        self.region_tree.heading("status", text="Status")
        self.region_tree.column("#0", width=92)
        self.region_tree.column("behavior", width=55)
        self.region_tree.column("status", width=78)
        self.region_tree.pack(fill="x", pady=5)
        self.region_tree.bind("<<TreeviewSelect>>", self.select_region_from_list)
        row = ttk.Frame(panel, style="MapperCard.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Duplicate", command=self.duplicate_region).pack(side="left")
        ttk.Button(row, text="Delete", command=self.delete_region).pack(side="left", padx=4)

        props = ttk.LabelFrame(panel, text="Selected Region", padding=7)
        props.pack(fill="both", expand=True, pady=(7, 0))
        self.region_name = tk.StringVar()
        self.region_behavior = tk.StringVar(value="Area")
        self.region_target = tk.StringVar(value="Not applicable")
        ttk.Label(props, text="Name").pack(anchor="w")
        ttk.Entry(props, textvariable=self.region_name).pack(fill="x")
        self.region_name.trace_add("write", self.region_metadata_changed)
        ttk.Label(props, text="Behavior").pack(anchor="w", pady=(5, 0))
        self.behavior_select = ttk.Combobox(props, textvariable=self.region_behavior, state="readonly", values=list(BEHAVIOR_LABELS.values()))
        self.behavior_select.pack(fill="x")
        self.behavior_select.bind("<<ComboboxSelected>>", self.region_behavior_changed)
        ttk.Label(props, text="Hover Text").pack(anchor="w", pady=(5, 0))
        self.hover_text = tk.Text(props, height=5, wrap="word", relief="solid", borderwidth=1)
        self.hover_text.pack(fill="x")
        self.hover_text.bind("<<Modified>>", self.hover_text_changed)
        self.hover_text.bind("<FocusIn>", self.hover_text_focus_in)
        self.hover_text.bind("<FocusOut>", self.hover_text_focus_out)
        self.hover_text.edit_modified(False)
        self.target_frame = ttk.Frame(props)
        self.target_frame.pack(fill="x", pady=(6, 0))
        ttk.Label(self.target_frame, text="Travel Destination", font=("Segoe UI", 9, "bold")).pack(anchor="w")
        self.target_label = ttk.Label(self.target_frame, textvariable=self.region_target, wraplength=220)
        self.target_label.pack(fill="x")
        target_buttons = ttk.Frame(self.target_frame)
        target_buttons.pack(fill="x", pady=(3, 0))
        ttk.Button(target_buttons, text="Choose", command=self.choose_destination).pack(side="left")
        ttk.Button(target_buttons, text="Clear", command=self.clear_destination).pack(side="left", padx=4)
        self.target_location_id = ""
        self.target_warp_point_id = ""
        self.region_help_label = ttk.Label(
            props,
            text="Changes save automatically. Tip: middle-drag pans; mouse wheel zooms at the cursor.",
            wraplength=220,
        )
        self.region_help_label.pack(anchor="w", pady=(12, 0))

    def close_window(self) -> None:
        self.flush_metadata_save()
        if self.confirm_discard():
            self.remember_right_panel_width()
            self.destroy()

    @staticmethod
    def write_crash_log(details: str) -> Path:
        path = RUNTIME_DIRECTORY / "mapper-crash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(details, encoding="utf-8")
        return path

    def report_callback_exception(self, exception_type, exception_value, exception_traceback) -> None:
        details = "".join(traceback.format_exception(exception_type, exception_value, exception_traceback))
        try:
            path = self.write_crash_log(details)
        except OSError:
            path = RUNTIME_DIRECTORY / "mapper-crash.log"
        if self.reporting_callback_exception:
            return
        self.reporting_callback_exception = True
        try:
            messagebox.showerror(
                "Mapper error",
                f"Mapper encountered an error but kept the details at:\n{path}",
                parent=self,
            )
        except tk.TclError:
            pass
        finally:
            self.reporting_callback_exception = False

    def restore_right_panel_width(self) -> None:
        try:
            self.update_idletasks()
            total_width = self.workspace.winfo_width()
            if total_width > self.right_panel_width + 300:
                self.workspace.sashpos(1, total_width - self.right_panel_width)
        except (tk.TclError, IndexError):
            pass

    def remember_right_panel_width(self) -> None:
        try:
            width = self.workspace.winfo_width() - self.workspace.sashpos(1)
        except (tk.TclError, IndexError):
            return
        if width < 100:
            return
        self.right_panel_width = max(220, min(420, int(width)))
        self.preferences["right_panel_width"] = self.right_panel_width
        try:
            self.preferences_store.save(self.preferences)
        except OSError:
            pass

    def confirm_discard(self) -> bool:
        if not self.editor_dirty and not self.draft_points and self.pending_image is None:
            return True
        return messagebox.askyesno("Unsaved Mapper work", "Discard the unsaved map changes?", parent=self)

    def refresh(self) -> None:
        try:
            self.world_session = self.repository.load()
            ensure_board_collections(self.world_session.data)
            self.maps = list(self.world_session.data.get("maps", []))
            self.locations = sorted(self.world_session.data.get("locations", []), key=lambda item: str(item.get("name", "")).casefold())
            self.location_options = {
                f"{item.get('name', 'Unnamed')}  [{item.get('record_id')}]": str(item.get("record_id"))
                for item in self.locations
            }
            self.render_catalog()
            self.render_completeness()
            if self.selected_map_id:
                record = next((item for item in self.maps if str(item.get("record_id")) == self.selected_map_id), None)
                if record:
                    self.load_map(record)
            selected = f"floor:{self.selected_location_id}:{self.selected_floor_id}" if self.selected_floor_id else f"location:{self.selected_location_id}"
            if self.selected_location_id and self.map_tree.exists(selected):
                self.map_tree.selection_set(selected)
                self.map_tree.see(selected)
            self.status_value.set(f"{len(self.locations)} locations • {len(self.maps)} prepared maps")
        except Exception as error:
            messagebox.showerror("Mapper", str(error), parent=self)

    def render_catalog(self) -> None:
        query = self.search_value.get().strip().casefold()
        self.map_tree.delete(*self.map_tree.get_children())
        maps_by_id = {str(item.get("record_id")): item for item in self.maps}
        locations_by_id = {str(item.get("record_id", "")): item for item in self.locations}
        included_ids: set[str] = set(locations_by_id)
        if query:
            included_ids = set()
            for location_id, location in locations_by_id.items():
                floor_names = [str(floor.get("name", "")) for floor in location.get("floors", []) or []]
                haystack = " ".join([str(location.get("name", "")), location_id, *floor_names]).casefold()
                if query not in haystack:
                    continue
                current_id = location_id
                seen_ancestors: set[str] = set()
                while current_id and current_id not in seen_ancestors:
                    seen_ancestors.add(current_id)
                    included_ids.add(current_id)
                    current = locations_by_id.get(current_id, {})
                    current_id = str(current.get("parent_location_id", "") or "")

        children: dict[str, list[dict]] = {}
        for location in self.locations:
            location_id = str(location.get("record_id", ""))
            if location_id not in included_ids:
                continue
            parent_id = str(location.get("parent_location_id", "") or "")
            if parent_id not in included_ids or parent_id == location_id:
                parent_id = ""
            children.setdefault(parent_id, []).append(location)

        inserted: set[str] = set()

        def insert_location(location: dict, parent_tree_id: str = "", ancestry: frozenset[str] = frozenset()) -> None:
            location_id = str(location.get("record_id", ""))
            if not location_id or location_id in inserted or location_id in ancestry:
                return
            location_name = str(location.get("name", "Unnamed"))
            floors = list(location.get("floors", []) or []) if location.get("has_floors") else []
            default_map = maps_by_id.get(str(location.get("default_map_id", "")))
            suffix = "" if default_map and default_map.get("asset") else " — No default map"
            tree_id = f"location:{location_id}"
            self.map_tree.insert(parent_tree_id, "end", iid=tree_id, text=f"{location_name}{suffix}", open=bool(query))
            inserted.add(location_id)
            for floor in floors:
                floor_id = str(floor.get("record_id", ""))
                floor_map = maps_by_id.get(str(floor.get("primary_map_id", "")))
                floor_suffix = "" if floor_map and floor_map.get("asset") else " — No map"
                self.map_tree.insert(
                    tree_id,
                    "end",
                    iid=f"floor:{location_id}:{floor_id}",
                    text=f"{floor.get('name', 'Unnamed')}{floor_suffix}",
                )
            next_ancestry = ancestry | {location_id}
            for child in children.get(location_id, []):
                insert_location(child, tree_id, next_ancestry)

        for location in children.get("", []):
            insert_location(location)
        for location in self.locations:
            if str(location.get("record_id", "")) in included_ids:
                insert_location(location)

    def render_completeness(self) -> None:
        maps_by_id = {str(item.get("record_id")): item for item in self.maps}
        missing_locations = [item for item in self.locations if str(item.get("default_map_id", "")) not in maps_by_id]
        floors = [
            floor
            for item in self.locations
            if item.get("has_floors")
            for floor in item.get("floors", []) or []
        ]
        missing_floors = [floor for floor in floors if str(floor.get("primary_map_id", "")) not in maps_by_id]
        self.completeness_value.set(f"Incomplete: {len(missing_locations)} locations and {len(missing_floors)} floors have no map.")

    def clear_map_editor(self) -> None:
        self.selected_map_id = ""
        self.pending_image = None
        self.image_value.set("No image")
        self.regions = []
        self.warp_points = []
        self._reset_editor()
        self.map_image = None
        self.tk_map_image = None
        self.tk_map_image_size = None
        self.render_canvas()

    def select_catalog_item(self, _event: tk.Event | None = None) -> None:
        selected = self.map_tree.selection()
        if not selected:
            return
        self.flush_metadata_save()
        parts = selected[0].split(":", 2)
        location_id = parts[1] if len(parts) > 1 else ""
        floor_id = parts[2] if len(parts) > 2 and parts[0] == "floor" else ""
        if location_id == self.selected_location_id and floor_id == self.selected_floor_id:
            return
        if not self.confirm_discard():
            previous = f"floor:{self.selected_location_id}:{self.selected_floor_id}" if self.selected_floor_id else f"location:{self.selected_location_id}"
            if self.map_tree.exists(previous):
                self.map_tree.selection_set(previous)
            return
        location = next((item for item in self.locations if str(item.get("record_id")) == location_id), None)
        if location is None:
            return
        self.selected_location_id = location_id
        self.selected_floor_id = floor_id
        self.floor_value.set(next((str(floor.get("name", "Unnamed")) for floor in location.get("floors", []) or [] if str(floor.get("record_id")) == floor_id), "Default location map"))
        self.has_floors_value.set(bool(location.get("has_floors", False)))
        map_id = str(location.get("default_map_id", ""))
        if floor_id:
            floor = next((item for item in location.get("floors", []) or [] if str(item.get("record_id")) == floor_id), {})
            map_id = str(floor.get("primary_map_id", ""))
        record = next((item for item in self.maps if str(item.get("record_id")) == map_id), None)
        if record:
            self.load_map(record)
        else:
            self.clear_map_editor()
            self.status_value.set(f"{self.map_display_name()} has no map yet")

    def load_map(self, record: dict) -> None:
        self.selected_map_id = str(record.get("record_id"))
        self.pending_image = None
        location_id = str(record.get("location_id", ""))
        self.selected_location_id = location_id
        location = next((item for item in self.locations if str(item.get("record_id")) == location_id), None)
        self.selected_floor_id = str(record.get("floor_id", ""))
        self.floor_value.set(next((str(floor.get("name", "Unnamed")) for floor in (location or {}).get("floors", []) or [] if str(floor.get("record_id")) == self.selected_floor_id), "Default location map"))
        self.has_floors_value.set(bool((location or {}).get("has_floors", False)))
        self.regions = deepcopy(record.get("regions", []) or [])
        self.warp_points = deepcopy(record.get("warp_points", []) or [])
        self._reset_editor()
        asset = record.get("asset")
        self.image_value.set("Base image ready" if asset else "No image")
        self.load_canvas_image(record)
        self.render_region_list()
        self.after_idle(self.fit_map)

    def _reset_editor(self) -> None:
        self.selected_region_id = ""
        self.selected_warp_point_id = ""
        self.selected_vertex = None
        self.draft_points = []
        self.editor_dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.clear_property_fields()

    def map_display_name(self) -> str:
        location = next((item for item in self.locations if str(item.get("record_id")) == self.selected_location_id), {})
        location_name = str(location.get("name", "Unnamed"))
        if not self.selected_floor_id:
            return location_name
        floor_name = next((str(floor.get("name", "Unnamed")) for floor in location.get("floors", []) or [] if str(floor.get("record_id")) == self.selected_floor_id), "Unnamed floor")
        return f"{location_name} — {floor_name}"

    def choose_image(self) -> None:
        if not self.selected_location_id:
            messagebox.showinfo("Choose a location", "Select a location or floor before importing its map.", parent=self)
            return
        filename = filedialog.askopenfilename(
            parent=self,
            title="Choose base map",
            filetypes=(("Map images", "*.png *.jpg *.jpeg *.webp *.svg"), ("All files", "*.*")),
        )
        if not filename:
            return
        source = Path(filename)
        try:
            width, height, _ = self.repository.assets.inspect_map_source(source)
            current = next((item for item in self.maps if str(item.get("record_id")) == self.selected_map_id), {})
            asset = current.get("asset") or {}
            if asset and self.regions:
                old_ratio = float(asset.get("source_width", asset["width"])) / float(asset.get("source_height", asset["height"]))
                new_ratio = width / height
                if not math.isclose(old_ratio, new_ratio, rel_tol=0.01) and not messagebox.askyesno(
                    "Changed aspect ratio",
                    "This replacement has a different aspect ratio. Existing polygon coordinates will be preserved, but shapes may no longer align. Continue?",
                    parent=self,
                ):
                    return
            self.pending_image = source
            self.image_value.set(f"Importing {source.name} ({width} × {height})…")
            self.save_map("Base map")
        except Exception as error:
            messagebox.showerror("Cannot import map", str(error), parent=self)

    def has_floors_changed(self) -> None:
        location = next((item for item in self.locations if str(item.get("record_id")) == self.selected_location_id), None)
        if location is None:
            self.has_floors_value.set(False)
            return
        enabled = bool(self.has_floors_value.get())
        if not enabled and location.get("floors"):
            messagebox.showinfo(
                "Named floors",
                "Remove the named floors in World Builder before turning off Has floors.",
                parent=self,
            )
            self.has_floors_value.set(True)
            return
        try:
            session = self.repository.load()
            stored = next(item for item in session.data["locations"] if str(item.get("record_id")) == self.selected_location_id)
            stored["has_floors"] = enabled
            self.repository.save(session, "mapper")
            location["has_floors"] = enabled
            self.render_catalog()
            selected = f"floor:{self.selected_location_id}:{self.selected_floor_id}" if self.selected_floor_id else f"location:{self.selected_location_id}"
            if self.map_tree.exists(selected):
                self.map_tree.selection_set(selected)
                self.map_tree.see(selected)
            self.status_value.set("Floors enabled" if enabled else "Floors disabled")
        except Exception as error:
            self.has_floors_value.set(bool(location.get("has_floors", False)))
            messagebox.showerror("Cannot update location", str(error), parent=self)

    def _choose_location_dialog(self, title: str, selected_id: str, callback) -> None:
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.transient(self)
        dialog.grab_set()
        dialog.geometry("620x620")
        dialog.minsize(440, 420)
        query = tk.StringVar()
        ttk.Label(dialog, text="Search by location name or record ID").pack(anchor="w", padx=10, pady=(10, 2))
        entry = ttk.Entry(dialog, textvariable=query)
        entry.pack(fill="x", padx=10)
        result_count = tk.StringVar()
        ttk.Label(dialog, textvariable=result_count).pack(anchor="w", padx=10, pady=(4, 0))
        tree = ttk.Treeview(dialog, columns=("id",), show="tree headings", selectmode="browse")
        tree.heading("#0", text="Location")
        tree.heading("id", text="Record ID")
        tree.column("#0", width=360)
        tree.column("id", width=190)
        tree.pack(fill="both", expand=True, padx=10, pady=6)

        def fill(*_args) -> None:
            tree.delete(*tree.get_children())
            needle = query.get().strip().casefold()
            matches = []
            for location in self.locations:
                location_id = str(location.get("record_id", ""))
                name = str(location.get("name", "Unnamed"))
                if not needle or needle in name.casefold() or needle in location_id.casefold():
                    matches.append((name, location_id))
            for name, location_id in matches:
                tree.insert("", "end", iid=location_id, text=name, values=(location_id,))
            result_count.set(f"{len(matches):,} matching locations")
            if selected_id and tree.exists(selected_id):
                tree.selection_set(selected_id)
                tree.see(selected_id)

        def choose(*_args) -> None:
            selected = tree.selection()
            if selected:
                callback(selected[0])
                dialog.destroy()

        query.trace_add("write", fill)
        tree.bind("<Double-Button-1>", choose)
        actions = ttk.Frame(dialog)
        actions.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Choose", command=choose).pack(side="right", padx=(0, 5))
        fill()
        entry.focus_set()

    def load_canvas_image(self, record: dict) -> None:
        self.map_image = None
        self.tk_map_image = None
        self.tk_map_image_size = None
        try:
            from PIL import Image

            asset = record.get("asset")
            if asset:
                path = self.repository.assets.resolve(str(asset.get("asset_id")), asset)
                with Image.open(path) as opened:
                    self.map_image = opened.convert("RGB").copy()
                    self.map_width, self.map_height = MAP_CANVAS_WIDTH, MAP_CANVAS_HEIGHT
        except Exception as error:
            self.status_value.set(f"Map image unavailable: {error}")
        self.render_canvas()

    def save_map(self, reason: str = "Map changes") -> bool:
        """Persist committed map state without resetting the editor viewport."""

        location_id = self.selected_location_id
        floor_id = self.selected_floor_id
        name = self.map_display_name()
        if not location_id:
            messagebox.showerror("Cannot save map", "Choose a location or floor.", parent=self)
            return False
        if not self.selected_map_id and self.pending_image is None:
            messagebox.showerror("Cannot save map", "Choose a base map image.", parent=self)
            return False
        try:
            regions = [normalize_region(region) for region in self.regions]
            warp_points = [normalize_warp_point(point) for point in self.warp_points]
            session = self.repository.load()
            record = next((item for item in session.data["maps"] if str(item.get("record_id")) == self.selected_map_id), None)
            now = utc_now()
            created_map = record is None
            if record is None:
                record = {
                    "record_id": str(uuid4()),
                    "created_at": now,
                    "players_published": False,
                    "asset": None,
                    "regions": [],
                    "warp_points": [],
                    "start_point": None,
                    "token_scale": 0.055,
                }
                session.data["maps"].append(record)
            map_id = str(record["record_id"])
            asset = record.get("asset")
            imported_image = self.pending_image is not None
            if self.pending_image is not None:
                asset = self.repository.assets.import_map(map_id, self.pending_image)
            record.update(
                name=name,
                location_id=location_id,
                floor_id=floor_id,
                asset=asset,
                regions=regions,
                warp_points=warp_points,
                last_updated=now,
            )
            location = next(item for item in session.data["locations"] if str(item.get("record_id")) == location_id)
            location["has_floors"] = bool(location.get("has_floors", False) or self.has_floors_value.get())
            if not floor_id:
                location["default_map_id"] = map_id
            for floor in location.get("floors", []) or []:
                if str(floor.get("record_id")) == floor_id:
                    floor["primary_map_id"] = map_id
            saved_document = self.repository.save(session, "mapper")
            if asset:
                self.repository.assets.prune_map_variants(map_id, str(asset.get("file_extension", "")))
            self.world_session = session
            self.maps = list(saved_document.get("maps", []))
            self.locations = sorted(
                saved_document.get("locations", []),
                key=lambda item: str(item.get("name", "")).casefold(),
            )
            self.location_options = {
                f"{item.get('name', 'Unnamed')}  [{item.get('record_id')}]": str(item.get("record_id"))
                for item in self.locations
            }
            self.selected_map_id = map_id
            self.pending_image = None
            self.editor_dirty = False
            self.metadata_history_pending = False
            if self.metadata_save_after_id is not None:
                try:
                    self.after_cancel(self.metadata_save_after_id)
                except tk.TclError:
                    pass
                self.metadata_save_after_id = None
            saved_record = next(
                item for item in self.maps if str(item.get("record_id")) == map_id
            )
            self.regions = deepcopy(saved_record.get("regions", []) or [])
            self.warp_points = deepcopy(saved_record.get("warp_points", []) or [])
            if imported_image:
                self.image_value.set("Base image ready")
                self.load_canvas_image(saved_record)
                self.after_idle(self.fit_map)
            if created_map or imported_image:
                self.render_catalog()
                self.render_completeness()
                selected = (
                    f"floor:{self.selected_location_id}:{self.selected_floor_id}"
                    if self.selected_floor_id
                    else f"location:{self.selected_location_id}"
                )
                if self.map_tree.exists(selected):
                    self.map_tree.selection_set(selected)
                    self.map_tree.see(selected)
            self.status_value.set(
                f"{reason} saved automatically • {len(regions)} interactable shapes"
            )
            return True
        except Exception as error:
            self.editor_dirty = True
            messagebox.showerror("Cannot save map", str(error), parent=self)
            self.status_value.set("Automatic save failed — changes remain open in Mapper")
            return False

    def autosave_map(self, reason: str) -> bool:
        return self.save_map(reason)

    def set_mode(self, mode: str) -> None:
        if mode in {"draw", "warp"} and self.map_image is None:
            messagebox.showinfo("Base map required", "Import and save a base map before drawing shapes.", parent=self)
            return
        if mode != "draw" and self.draft_points:
            self.cancel_drawing()
        self.mode = mode
        self.mode_value.set({
            "select": "Select and move shapes",
            "draw": "Place nodes; click the first node to close",
            "edit": "Line: add • node: drag • right-click: remove",
            "warp": "Click: add/select warp • drag: move • right-click: remove",
        }[mode])
        self.canvas.configure(cursor="crosshair" if mode in {"draw", "edit", "warp"} else "arrow")
        self.render_canvas()

    def tool_shortcut(self, event: tk.Event, mode: str) -> None:
        if event.widget.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return
        self.set_mode(mode)

    def fit_map(self) -> None:
        width = max(100, self.canvas.winfo_width())
        height = max(100, self.canvas.winfo_height())
        self.fit_scale = min((width - 24) / self.map_width, (height - 24) / self.map_height)
        self.scale = self.fit_scale
        self.origin_x = (width - self.map_width * self.scale) / 2
        self.origin_y = (height - self.map_height * self.scale) / 2
        self.render_canvas()

    def clamp_view(self) -> None:
        """Keep the fitted map as the outermost permitted viewport."""

        canvas_width = max(1.0, float(self.canvas.winfo_width()))
        canvas_height = max(1.0, float(self.canvas.winfo_height()))
        self.scale = max(self.fit_scale, self.scale)
        display_width = self.map_width * self.scale
        display_height = self.map_height * self.scale
        if display_width <= canvas_width:
            self.origin_x = (canvas_width - display_width) / 2
        else:
            self.origin_x = min(0.0, max(canvas_width - display_width, self.origin_x))
        if display_height <= canvas_height:
            self.origin_y = (canvas_height - display_height) / 2
        else:
            self.origin_y = min(0.0, max(canvas_height - display_height, self.origin_y))

    def normal_to_canvas(self, point: dict) -> tuple[float, float]:
        return self.origin_x + point["x"] * self.map_width * self.scale, self.origin_y + point["y"] * self.map_height * self.scale

    def canvas_to_normal(self, x: float, y: float, clamp: bool = False) -> dict:
        nx = (x - self.origin_x) / (self.map_width * self.scale)
        ny = (y - self.origin_y) / (self.map_height * self.scale)
        if clamp:
            nx, ny = max(0.0, min(1.0, nx)), max(0.0, min(1.0, ny))
        return {"x": nx, "y": ny}

    def render_canvas(self) -> None:
        self.canvas.delete("all")
        if self.map_image is None:
            right = self.origin_x + self.map_width * self.scale
            bottom = self.origin_y + self.map_height * self.scale
            self.canvas.create_rectangle(self.origin_x, self.origin_y, right, bottom, fill="#241d16", outline="#9d7a4e", width=2)
            self.canvas.create_text((self.origin_x + right) / 2, (self.origin_y + bottom) / 2, text="3840 × 2960 reference canvas\nImport and save a base map to begin", fill="#ead7aa", font=("Georgia", 16), justify="center")
            return
        try:
            from PIL import Image, ImageTk

            display_width = max(1, round(self.map_width * self.scale))
            display_height = max(1, round(self.map_height * self.scale))
            canvas_width = max(1, self.canvas.winfo_width())
            canvas_height = max(1, self.canvas.winfo_height())
            visible_left = max(0.0, self.origin_x)
            visible_top = max(0.0, self.origin_y)
            visible_right = min(float(canvas_width), self.origin_x + display_width)
            visible_bottom = min(float(canvas_height), self.origin_y + display_height)
            self.canvas.create_rectangle(
                self.origin_x,
                self.origin_y,
                self.origin_x + display_width,
                self.origin_y + display_height,
                fill="#241d16",
                outline="#9d7a4e",
            )
            if visible_right > visible_left and visible_bottom > visible_top:
                source_left = max(0, math.floor((visible_left - self.origin_x) / display_width * self.map_image.width))
                source_top = max(0, math.floor((visible_top - self.origin_y) / display_height * self.map_image.height))
                source_right = min(self.map_image.width, math.ceil((visible_right - self.origin_x) / display_width * self.map_image.width))
                source_bottom = min(self.map_image.height, math.ceil((visible_bottom - self.origin_y) / display_height * self.map_image.height))
                target_width = max(1, round(visible_right - visible_left))
                target_height = max(1, round(visible_bottom - visible_top))
                cache_key = (
                    display_width,
                    display_height,
                    round(self.origin_x, 2),
                    round(self.origin_y, 2),
                    source_left,
                    source_top,
                    source_right,
                    source_bottom,
                    target_width,
                    target_height,
                )
                if self.tk_map_image is None or self.tk_map_image_size != cache_key:
                    visible = self.map_image.crop((source_left, source_top, source_right, source_bottom))
                    resized = visible.resize((target_width, target_height), Image.Resampling.BILINEAR)
                    self.tk_map_image = ImageTk.PhotoImage(resized)
                    self.tk_map_image_size = cache_key
                self.canvas.create_image(visible_left, visible_top, image=self.tk_map_image, anchor="nw", tags=("base-map",))
        except Exception:
            return
        for region in self.regions:
            coords = [coordinate for point in region["points"] for coordinate in self.normal_to_canvas(point)]
            selected = region["record_id"] == self.selected_region_id
            color = BEHAVIOR_COLORS.get(region.get("behavior_type"), self.MUTED)
            self.canvas.create_polygon(*coords, fill=color, stipple="gray12" if not selected else "gray25", outline=self.LINE, width=3 if selected else 1, tags=(f"region:{region['record_id']}", "region"))
            if selected:
                center_x = sum(point["x"] for point in region["points"]) / len(region["points"])
                center_y = sum(point["y"] for point in region["points"]) / len(region["points"])
                cx, cy = self.normal_to_canvas({"x": center_x, "y": center_y})
                self.canvas.create_text(cx, cy, text=region["name"], fill="#fff8e7", font=("Segoe UI", 10, "bold"))
                if self.mode == "edit":
                    for index, point in enumerate(region["points"]):
                        x, y = self.normal_to_canvas(point)
                        radius = 6 if index == self.selected_vertex else 4
                        self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#fff8e7", outline=self.LINE, width=2, tags=(f"node:{index}", "node"))
        for warp_point in self.warp_points:
            x, y = self.normal_to_canvas(warp_point)
            selected = str(warp_point.get("record_id")) == self.selected_warp_point_id
            radius = 8 if selected else 6
            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill="#7b3f8c",
                outline="#fff8e7" if selected else self.LINE,
                width=3 if selected else 2,
                tags=(f"warp:{warp_point['record_id']}", "warp-point"),
            )
            self.canvas.create_line(x - 11, y, x + 11, y, fill="#fff8e7", width=2, tags=("warp-point",))
            self.canvas.create_line(x, y - 11, x, y + 11, fill="#fff8e7", width=2, tags=("warp-point",))
            self.canvas.create_text(
                x + 12,
                y - 12,
                text=str(warp_point.get("name") or "Warp"),
                anchor="sw",
                fill="#fff8e7",
                font=("Segoe UI", 9, "bold"),
                tags=("warp-point",),
            )
        if self.draft_points:
            coords = [coordinate for point in self.draft_points for coordinate in self.normal_to_canvas(point)]
            if len(coords) >= 4:
                self.canvas.create_line(*coords, fill=self.LINE, width=2)
                if len(self.draft_points) >= 3:
                    first_x, first_y = self.normal_to_canvas(self.draft_points[0])
                    second_x, second_y = self.normal_to_canvas(self.draft_points[1])
                    self.canvas.create_line(first_x, first_y, second_x, second_y, fill=self.LINE, width=4)
            for index, point in enumerate(self.draft_points):
                x, y = self.normal_to_canvas(point)
                radius = 4
                self.canvas.create_oval(x - radius, y - radius, x + radius, y + radius, fill="#fff8e7", outline=self.LINE, width=2)

    @staticmethod
    def wheel_steps(event: tk.Event) -> float:
        return event.delta / 120 if event.delta else 0.0

    @staticmethod
    def windows_key_down(virtual_key: int) -> bool:
        if sys.platform != "win32":
            return False
        try:
            import ctypes

            return bool(ctypes.windll.user32.GetAsyncKeyState(virtual_key) & 0x8000)
        except (AttributeError, OSError):
            return False

    def route_canvas_wheel(self, event: tk.Event) -> str:
        # A rapid Alt-wheel -> middle-drag transition can make Windows/Tk lose
        # the middle-button release. Recover before routing the next wheel
        # event so a stale temporary pan can never poison later controls.
        if self.pan_state is not None and sys.platform == "win32" and not self.windows_key_down(0x04):
            self.finish_pan(focus_canvas=False)
        if hasattr(event, "x_root") and hasattr(event, "y_root"):
            try:
                target = self.winfo_containing(event.x_root, event.y_root)
            except tk.TclError:
                target = None
            current = target
            while current is not None and current is not self.canvas:
                current = getattr(current, "master", None)
            if current is not self.canvas:
                return ""
        if sys.platform == "win32":
            event_control = bool(event.state & 0x0004)
            event_alt = bool(event.state & (0x0008 | 0x20000))
            control_down = event_control or self.windows_key_down(0x11)
            # Alt is intentionally stricter: both sources must agree. This
            # prevents a just-released Alt key from hijacking the next plain
            # wheel event while Windows finishes updating its async state.
            alt_down = event_alt and self.windows_key_down(0x12)
        else:
            control_down = bool(event.state & 0x0004)
            alt_down = bool(event.state & (0x0008 | 0x20000))
        if control_down:
            return self.canvas_zoom_wheel(event)
        if alt_down:
            return self.canvas_horizontal_wheel(event)
        return self.canvas_vertical_wheel(event)

    def canvas_vertical_wheel(self, event: tk.Event) -> str:
        if self.map_image is None:
            return "break"
        self.origin_y += self.wheel_steps(event) * 24
        self.clamp_view()
        self.render_canvas()
        return "break"

    def canvas_horizontal_wheel(self, event: tk.Event) -> str:
        if self.map_image is None:
            return "break"
        self.origin_x += self.wheel_steps(event) * 24
        self.clamp_view()
        self.render_canvas()
        return "break"

    def canvas_zoom_wheel(self, event: tk.Event) -> str:
        if self.map_image is None:
            return "break"
        steps = self.wheel_steps(event)
        before = self.canvas_to_normal(event.x, event.y)
        self.scale = max(self.fit_scale, min(self.fit_scale * 32.0, self.scale * (1.15 ** steps)))
        self.origin_x = event.x - before["x"] * self.map_width * self.scale
        self.origin_y = event.y - before["y"] * self.map_height * self.scale
        self.clamp_view()
        self.render_canvas()
        return "break"

    def pan_press(self, event: tk.Event) -> None:
        self.finish_pan(focus_canvas=False)
        self.canvas.focus_set()
        self.pan_state = (event.x_root, event.y_root, self.origin_x, self.origin_y)
        self.canvas.configure(cursor="fleur")
        self.pan_watchdog_id = self.after(40, self.watch_middle_button)

    def pan_drag(self, event: tk.Event) -> str:
        if self.pan_state:
            x, y, ox, oy = self.pan_state
            self.origin_x, self.origin_y = ox + event.x_root - x, oy + event.y_root - y
            self.clamp_view()
            self.render_canvas()
            return "break"
        return ""

    def watch_middle_button(self) -> None:
        self.pan_watchdog_id = None
        if self.pan_state is None:
            return
        if sys.platform == "win32" and not self.windows_key_down(0x04):
            self.finish_pan()
            return
        self.pan_watchdog_id = self.after(40, self.watch_middle_button)

    def finish_pan(self, focus_canvas: bool = True) -> bool:
        if self.pan_state is None:
            return False
        self.pan_state = None
        if self.pan_watchdog_id is not None:
            try:
                self.after_cancel(self.pan_watchdog_id)
            except tk.TclError:
                pass
            self.pan_watchdog_id = None
        self.canvas.configure(cursor="crosshair" if self.mode in {"draw", "edit", "warp"} else "arrow")
        if focus_canvas:
            self.canvas.focus_set()
        return True

    def pan_release(self, _event: tk.Event | None = None) -> str:
        return "break" if self.finish_pan() else ""

    def canvas_motion(self, event: tk.Event) -> None:
        if self.mode != "draw" or not self.draft_points:
            return
        # Mouse motion only changes this temporary closing guide. Redrawing
        # the 4K map and every existing node for each pointer event can flood
        # Tk's event queue while tracing detailed coastlines.
        self.canvas.delete("draft-preview")
        x, y, snapped = self.draft_pointer_position(event.x, event.y)
        last_x, last_y = self.normal_to_canvas(self.draft_points[-1])
        first_x, first_y = self.normal_to_canvas(self.draft_points[0])
        self.canvas.delete("draft-close-cursor")
        self.canvas.configure(cursor="none" if snapped else "crosshair")
        coordinates = (last_x, last_y, first_x, first_y) if snapped else (last_x, last_y, x, y, first_x, first_y)
        self.canvas.create_line(*coordinates, fill=self.LINE, dash=(5, 3), width=2, tags=("draft-preview",))
        if snapped:
            self.canvas.create_oval(
                event.x - 10,
                event.y - 10,
                event.x + 10,
                event.y + 10,
                fill="#2f7d32",
                outline="#ffffff",
                width=2,
                tags=("draft-close-cursor",),
            )
            self.canvas.create_text(
                event.x,
                event.y,
                text="✓",
                fill="#ffffff",
                font=("Segoe UI Symbol", 12, "bold"),
                tags=("draft-close-cursor",),
            )

    def canvas_leave(self, _event: tk.Event | None = None) -> None:
        self.canvas.delete("draft-close-cursor")
        self.canvas.configure(cursor="crosshair" if self.mode in {"draw", "edit", "warp"} else "arrow")

    def draft_pointer_position(self, x: float, y: float) -> tuple[float, float, bool]:
        if len(self.draft_points) >= 3:
            first_x, first_y = self.normal_to_canvas(self.draft_points[0])
            if math.hypot(x - first_x, y - first_y) <= self.POLYGON_CLOSE_SNAP_RADIUS:
                return first_x, first_y, True
        point = self.canvas_to_normal(x, y, True)
        canvas_x, canvas_y = self.normal_to_canvas(point)
        return canvas_x, canvas_y, False

    def warp_point_at(self, x: float, y: float) -> dict | None:
        for point in reversed(self.warp_points):
            px, py = self.normal_to_canvas(point)
            if math.hypot(x - px, y - py) <= 12:
                return point
        return None

    def add_warp_point(self, point: dict) -> None:
        name = simpledialog.askstring(
            "Name warp point",
            "Name this arrival point (for example, North Stairwell):",
            parent=self,
        )
        if not name or not name.strip():
            return
        now = utc_now()
        warp_point = normalize_warp_point({
            "record_id": str(uuid4()),
            "name": name.strip(),
            "x": point["x"],
            "y": point["y"],
            "created_at": now,
            "last_updated": now,
        })
        self.warp_points.append(warp_point)
        self.selected_warp_point_id = warp_point["record_id"]
        self.editor_dirty = True
        self.render_canvas()
        self.autosave_map("Added warp point")

    def canvas_press(self, event: tk.Event) -> None:
        self.canvas.focus_set()
        if self.pan_state is not None:
            self.pan_release()
        if self.map_image is None:
            return
        point = self.canvas_to_normal(event.x, event.y)
        if not 0 <= point["x"] <= 1 or not 0 <= point["y"] <= 1:
            return
        existing_warp = self.warp_point_at(event.x, event.y)
        if existing_warp is not None and self.mode in {"select", "edit", "warp"}:
            self.selected_warp_point_id = str(existing_warp["record_id"])
            self.drag_state = {
                "kind": "warp",
                "record_id": self.selected_warp_point_id,
                "changed": False,
            }
            self.render_canvas()
            return
        if self.mode == "warp":
            if existing_warp is None:
                self.add_warp_point(point)
            return
        if self.mode == "draw":
            if len(self.draft_points) >= 3:
                _x, _y, snapped = self.draft_pointer_position(event.x, event.y)
                if snapped:
                    self.complete_polygon()
                    return
            if not self.draft_points or math.hypot(point["x"] - self.draft_points[-1]["x"], point["y"] - self.draft_points[-1]["y"]) > 1e-6:
                self.draft_points.append(point)
                self.render_canvas()
            return
        region = self.selected_region()
        if self.mode == "edit" and region:
            for index, vertex in enumerate(region["points"]):
                vx, vy = self.normal_to_canvas(vertex)
                if math.hypot(event.x - vx, event.y - vy) <= 9:
                    self.selected_vertex = index
                    self.record_history()
                    self.drag_state = {"kind": "vertex", "changed": False}
                    self.render_canvas()
                    return
            edge_index, projected, _distance = nearest_edge(region["points"], point["x"], point["y"])
            projected_x, projected_y = self.normal_to_canvas(projected)
            if math.hypot(event.x - projected_x, event.y - projected_y) <= 12:
                self.record_history()
                region["points"].insert(edge_index + 1, projected)
                region["last_updated"] = utc_now()
                self.selected_vertex = edge_index + 1
                self.editor_dirty = True
                self.render_canvas()
                self.autosave_map("Added node")
                return
        self.selected_warp_point_id = ""
        hit = next((candidate for candidate in reversed(self.regions) if point_in_polygon(point["x"], point["y"], candidate["points"])), None)
        if hit:
            self.select_region(str(hit["record_id"]))
            if self.mode == "select":
                self.record_history()
                self.drag_state = {"kind": "polygon", "start": point, "points": deepcopy(hit["points"]), "changed": False}
        else:
            self.select_region("")

    def canvas_drag(self, event: tk.Event) -> None:
        if not self.drag_state:
            return
        if self.drag_state.get("kind") == "warp":
            point = self.canvas_to_normal(event.x, event.y, True)
            warp_point = next(
                (
                    item for item in self.warp_points
                    if str(item.get("record_id")) == self.drag_state.get("record_id")
                ),
                None,
            )
            if warp_point is not None:
                warp_point.update(x=point["x"], y=point["y"])
                self.drag_state["changed"] = True
                self.editor_dirty = True
                self.render_canvas()
            return
        region = self.selected_region()
        if not region:
            return
        point = self.canvas_to_normal(event.x, event.y, True)
        if self.drag_state["kind"] == "vertex" and self.selected_vertex is not None:
            region["points"][self.selected_vertex] = point
        else:
            start = self.drag_state["start"]
            region["points"] = translated_points(self.drag_state["points"], point["x"] - start["x"], point["y"] - start["y"])
        self.drag_state["changed"] = True
        self.editor_dirty = True
        self.render_canvas()

    def canvas_release(self, _event: tk.Event) -> None:
        if self.drag_state and self.drag_state.get("kind") == "warp":
            changed = bool(self.drag_state.get("changed"))
            warp_point = next(
                (
                    item for item in self.warp_points
                    if str(item.get("record_id")) == self.drag_state.get("record_id")
                ),
                None,
            )
            self.drag_state = None
            if changed and warp_point is not None:
                warp_point["last_updated"] = utc_now()
                self.autosave_map("Moved warp point")
            return
        changed = bool(self.drag_state and self.drag_state.get("changed"))
        if self.drag_state and not changed and self.undo_stack:
            self.undo_stack.pop()
        if changed:
            region = self.selected_region()
            if region:
                region["last_updated"] = utc_now()
        self.drag_state = None
        if changed:
            self.autosave_map("Polygon geometry")

    def canvas_right_click(self, event: tk.Event) -> str:
        warp_point = self.warp_point_at(event.x, event.y)
        if warp_point is not None:
            self.selected_warp_point_id = str(warp_point.get("record_id"))
            self.remove_selected_warp_point()
            return "break"
        if self.mode != "edit":
            return ""
        region = self.selected_region()
        if region is None:
            return "break"
        for index, vertex in enumerate(region["points"]):
            vx, vy = self.normal_to_canvas(vertex)
            if math.hypot(event.x - vx, event.y - vy) <= 10:
                self.selected_vertex = index
                self.delete_node()
                return "break"
        return "break"

    def delete_node_shortcut(self, event: tk.Event) -> str:
        if event.widget.winfo_class() in {"Entry", "TEntry", "Text", "TCombobox", "Spinbox", "TSpinbox"}:
            return ""
        if self.mode == "edit" and self.selected_vertex is not None:
            self.delete_node()
            return "break"
        if self.selected_warp_point_id:
            self.remove_selected_warp_point()
            return "break"
        return ""

    def remove_selected_warp_point(self) -> None:
        warp_point = next(
            (
                item for item in self.warp_points
                if str(item.get("record_id")) == self.selected_warp_point_id
            ),
            None,
        )
        if warp_point is None:
            return
        if not messagebox.askyesno(
            "Remove warp point",
            f"Remove {warp_point.get('name', 'this warp point')}?",
            parent=self,
        ):
            return
        warp_id = str(warp_point.get("record_id"))
        self.warp_points = [
            item for item in self.warp_points
            if str(item.get("record_id")) != warp_id
        ]
        for region in self.regions:
            if str(region.get("target_warp_point_id", "")) == warp_id:
                region["target_warp_point_id"] = ""
                region["last_updated"] = utc_now()
        self.selected_warp_point_id = ""
        self.editor_dirty = True
        self.render_region_list()
        self.render_canvas()
        self.autosave_map("Removed warp point")

    def canvas_double_click(self, _event: tk.Event) -> None:
        if self.mode == "draw":
            if len(self.draft_points) >= 2 and self.draft_points[-1] == self.draft_points[-2]:
                self.draft_points.pop()
            self.complete_polygon()

    def complete_polygon(self) -> None:
        if self.mode != "draw":
            return
        if len(self.draft_points) < 3:
            messagebox.showinfo("Polygon incomplete", "Place at least three nodes before completing the polygon.", parent=self)
            return
        now = utc_now()
        region = {
            "record_id": str(uuid4()),
            "name": f"Area {len(self.regions) + 1}",
            "type_label": "",
            "behavior_type": "area",
            "hover_text": "",
            "points": deepcopy(self.draft_points),
            "target_location_id": "",
            "target_warp_point_id": "",
            "created_at": now,
            "last_updated": now,
        }
        try:
            region = normalize_region(region)
        except ValueError as error:
            messagebox.showerror("Cannot complete polygon", str(error), parent=self)
            return
        self.record_history()
        self.regions.append(region)
        self.draft_points = []
        self.editor_dirty = True
        self.set_mode("select")
        self.render_region_list()
        self.select_region(region["record_id"])
        self.autosave_map("Completed polygon")

    def cancel_drawing(self) -> None:
        self.draft_points = []
        self.mode = "select"
        self.mode_value.set("Select and move shapes")
        self.canvas.configure(cursor="arrow")
        self.canvas.delete("draft-close-cursor")
        self.render_canvas()

    def selected_region(self) -> dict | None:
        return next((region for region in self.regions if region["record_id"] == self.selected_region_id), None)

    def select_region_from_list(self, _event: tk.Event | None = None) -> None:
        if self.updating_region_selection:
            return
        selected = self.region_tree.selection()
        if selected:
            self.select_region(selected[0])

    def select_region(self, region_id: str) -> None:
        self.selected_region_id = region_id
        self.selected_vertex = None
        region = self.selected_region()
        self.loading_region_properties = True
        try:
            if region:
                self.region_name.set(region["name"])
                self.region_behavior.set(BEHAVIOR_LABELS.get(region.get("behavior_type"), "Area"))
                self.hover_text.delete("1.0", "end")
                self.hover_text.insert("1.0", region.get("hover_text", ""))
                self.hover_text.edit_modified(False)
                self.target_location_id = str(region.get("target_location_id", ""))
                self.target_warp_point_id = str(region.get("target_warp_point_id", ""))
                if self.region_tree.exists(region_id):
                    if self.region_tree.selection() != (region_id,):
                        self.updating_region_selection = True
                        try:
                            self.region_tree.selection_set(region_id)
                        finally:
                            self.updating_region_selection = False
                    self.region_tree.see(region_id)
            else:
                self.clear_property_fields()
        finally:
            self.loading_region_properties = False
        self.render_target_controls()
        self.render_canvas()

    def clear_property_fields(self) -> None:
        previous = self.loading_region_properties
        self.loading_region_properties = True
        try:
            self.region_name.set("")
            self.region_behavior.set("Area")
            if hasattr(self, "hover_text"):
                self.hover_text.delete("1.0", "end")
                self.hover_text.edit_modified(False)
            self.target_location_id = ""
            self.target_warp_point_id = ""
            if hasattr(self, "region_target"):
                self.region_target.set("Not applicable")
        finally:
            self.loading_region_properties = previous

    def render_region_list(self) -> None:
        self.region_tree.delete(*self.region_tree.get_children())
        location_names = {str(item.get("record_id")): str(item.get("name", "")) for item in self.locations}
        for region in self.regions:
            behavior = region.get("behavior_type", "area")
            if behavior == "travel":
                target = str(region.get("target_location_id", ""))
                warp_id = str(region.get("target_warp_point_id", ""))
                warp = next(
                    (
                        point for map_record in self.maps
                        for point in map_record.get("warp_points", []) or []
                        if str(point.get("record_id", "")) == warp_id
                    ),
                    None,
                )
                status = (
                    f"Warp: {warp.get('name')}"
                    if warp
                    else (f"Travel to: {location_names.get(target, 'Missing')}" if target else "Needs destination")
                )
            else:
                status = "Ready"
            self.region_tree.insert("", "end", iid=region["record_id"], text=region["name"], values=(BEHAVIOR_LABELS.get(behavior, behavior), status))
        if self.selected_region_id and self.region_tree.exists(self.selected_region_id):
            self.updating_region_selection = True
            try:
                self.region_tree.selection_set(self.selected_region_id)
            finally:
                self.updating_region_selection = False

    def render_target_controls(self) -> None:
        behavior = next((key for key, label in BEHAVIOR_LABELS.items() if label == self.region_behavior.get()), "area")
        if behavior != "travel":
            self.target_frame.pack_forget()
            self.region_target.set("Not applicable")
            return
        self.target_frame.pack(fill="x", pady=(6, 0), before=self.region_help_label)
        target_map = next(
            (
                map_record for map_record in self.maps
                if any(
                    str(point.get("record_id", "")) == self.target_warp_point_id
                    for point in map_record.get("warp_points", []) or []
                )
            ),
            None,
        )
        warp = next(
            (
                point for point in (target_map or {}).get("warp_points", []) or []
                if str(point.get("record_id", "")) == self.target_warp_point_id
            ),
            None,
        )
        location = next((item for item in self.locations if str(item.get("record_id")) == self.target_location_id), None)
        if warp and target_map:
            self.region_target.set(f"Warp to: {target_map.get('name')} — {warp.get('name')}")
        else:
            self.region_target.set(f"Travel to: {location.get('name')}" if location else "Needs destination")

    def choose_destination(self) -> None:
        choices = []
        for map_record in self.maps:
            for point in map_record.get("warp_points", []) or []:
                choices.append({
                    "record_id": str(point.get("record_id", "")),
                    "name": str(point.get("name", "Warp point")),
                    "map_name": str(map_record.get("name", "Map")),
                    "location_id": str(map_record.get("location_id", "")),
                })
        if not choices:
            messagebox.showinfo(
                "No warp points",
                "Use the Warp [W] tool on a destination map to create an arrival point first.",
                parent=self,
            )
            return
        dialog = tk.Toplevel(self)
        dialog.title("Choose destination warp point")
        dialog.transient(self)
        dialog.geometry("560x460")
        dialog.minsize(460, 360)
        shell = ttk.Frame(dialog, padding=12)
        shell.pack(fill="both", expand=True)
        query = tk.StringVar()
        ttk.Label(shell, text="Search warp points", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        entry = ttk.Entry(shell, textvariable=query)
        entry.pack(fill="x", pady=(3, 8))
        tree = ttk.Treeview(shell, columns=("map",), show="tree headings", selectmode="browse")
        tree.heading("#0", text="Warp point")
        tree.heading("map", text="Destination map")
        tree.column("#0", width=190)
        tree.column("map", width=270)
        tree.pack(fill="both", expand=True)

        def refill(*_args) -> None:
            text = query.get().strip().casefold()
            tree.delete(*tree.get_children())
            for choice in choices:
                haystack = f"{choice['name']} {choice['map_name']}".casefold()
                if text and text not in haystack:
                    continue
                tree.insert("", "end", iid=choice["record_id"], text=choice["name"], values=(choice["map_name"],))

        def choose(*_args) -> None:
            selection = tree.selection()
            if not selection:
                return
            choice = next(item for item in choices if item["record_id"] == selection[0])
            self.target_location_id = choice["location_id"]
            self.target_warp_point_id = choice["record_id"]
            self.render_target_controls()
            self.region_metadata_changed()
            self.flush_metadata_save()
            dialog.destroy()

        query.trace_add("write", refill)
        tree.bind("<Double-Button-1>", choose)
        actions = ttk.Frame(shell)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="Cancel", command=dialog.destroy).pack(side="right")
        ttk.Button(actions, text="Choose warp point", command=choose).pack(side="right", padx=(0, 6))
        refill()
        entry.focus_set()

    def _set_destination(self, location_id: str) -> None:
        self.target_location_id = location_id
        self.target_warp_point_id = ""
        self.render_target_controls()
        self.region_metadata_changed()
        self.flush_metadata_save()

    def clear_destination(self) -> None:
        self.target_location_id = ""
        self.target_warp_point_id = ""
        self.render_target_controls()
        self.region_metadata_changed()
        self.flush_metadata_save()

    def hover_text_changed(self, _event: tk.Event | None = None) -> None:
        if not self.hover_text.edit_modified():
            return
        self.hover_text.edit_modified(False)
        self.region_metadata_changed(schedule_save=False)

    def hover_text_focus_in(self, _event: tk.Event | None = None) -> None:
        # Finish any save queued by another property before the user starts
        # typing, so a delayed list refresh cannot interrupt this text field.
        self.flush_metadata_save()

    def hover_text_focus_out(self, _event: tk.Event | None = None) -> None:
        self.region_metadata_changed(schedule_save=False)
        self.flush_metadata_save()

    def region_behavior_changed(self, _event: tk.Event | None = None) -> None:
        self.render_target_controls()
        self.region_metadata_changed()
        self.flush_metadata_save()

    def region_metadata_changed(self, *_args, schedule_save: bool = True) -> None:
        """Update the selected region immediately and debounce its disk write."""

        if self.loading_region_properties:
            return
        region = self.selected_region()
        if not region:
            return
        name = self.region_name.get().strip()
        behavior = next((key for key, label in BEHAVIOR_LABELS.items() if label == self.region_behavior.get()), "area")
        if behavior not in REGION_BEHAVIOR_TYPES:
            return
        changes = {
            "name": name,
            "behavior_type": behavior,
            "hover_text": self.hover_text.get("1.0", "end-1c").strip(),
            "target_location_id": self.target_location_id if behavior == "travel" else "",
            "target_warp_point_id": self.target_warp_point_id if behavior == "travel" else "",
        }
        if all(region.get(key, "") == value for key, value in changes.items()):
            return
        if not self.metadata_history_pending:
            self.record_history()
            self.metadata_history_pending = True
        region.update(
            **changes,
            last_updated=utc_now(),
        )
        self.editor_dirty = True
        if schedule_save:
            self.schedule_metadata_save()

    def schedule_metadata_save(self) -> None:
        if self.metadata_save_after_id is not None:
            try:
                self.after_cancel(self.metadata_save_after_id)
            except tk.TclError:
                pass
        self.metadata_save_after_id = self.after(650, self.flush_metadata_save)

    def flush_metadata_save(self) -> bool:
        if self.metadata_save_after_id is not None:
            try:
                self.after_cancel(self.metadata_save_after_id)
            except tk.TclError:
                pass
            self.metadata_save_after_id = None
        if not self.metadata_history_pending:
            return True
        if any(not str(region.get("name", "")).strip() for region in self.regions):
            self.status_value.set("Enter a region name to finish the automatic save")
            return False
        selected = self.selected_region_id
        if not self.autosave_map("Region details"):
            return False
        self.metadata_history_pending = False
        self.render_region_list()
        self.render_canvas()
        if selected and self.region_tree.exists(selected):
            self.updating_region_selection = True
            try:
                self.region_tree.selection_set(selected)
            finally:
                self.updating_region_selection = False
        return True

    def apply_properties(self) -> None:
        """Compatibility entry point for older callers; properties now autosave."""

        self.region_metadata_changed()
        self.flush_metadata_save()

    def record_history(self) -> None:
        self.undo_stack.append((deepcopy(self.regions), self.selected_region_id))
        if len(self.undo_stack) > 100:
            self.undo_stack.pop(0)
        self.redo_stack.clear()

    def undo(self) -> None:
        if not self.undo_stack:
            return
        self.redo_stack.append((deepcopy(self.regions), self.selected_region_id))
        self.regions, selected = self.undo_stack.pop()
        self.editor_dirty = True
        self.render_region_list()
        self.select_region(selected if any(item["record_id"] == selected for item in self.regions) else "")
        self.autosave_map("Undo")

    def redo(self) -> None:
        if not self.redo_stack:
            return
        self.undo_stack.append((deepcopy(self.regions), self.selected_region_id))
        self.regions, selected = self.redo_stack.pop()
        self.editor_dirty = True
        self.render_region_list()
        self.select_region(selected if any(item["record_id"] == selected for item in self.regions) else "")
        self.autosave_map("Redo")

    def delete_node(self) -> None:
        region = self.selected_region()
        if not region or self.selected_vertex is None:
            messagebox.showinfo("Choose a node", "Select a polygon and click one of its node handles first.", parent=self)
            return
        if len(region["points"]) <= 3:
            messagebox.showinfo("Three nodes required", "A polygon must retain at least three nodes.", parent=self)
            return
        self.record_history()
        region["points"].pop(self.selected_vertex)
        self.selected_vertex = None
        region["last_updated"] = utc_now()
        self.editor_dirty = True
        self.render_canvas()
        self.autosave_map("Removed node")

    def duplicate_region(self) -> None:
        region = self.selected_region()
        if not region:
            return
        self.record_history()
        duplicate = deepcopy(region)
        duplicate["record_id"] = str(uuid4())
        duplicate["name"] = f"{region['name']} Copy"
        duplicate["points"] = translated_points(region["points"], 0.025, 0.025)
        duplicate["created_at"] = duplicate["last_updated"] = utc_now()
        self.regions.append(duplicate)
        self.editor_dirty = True
        self.render_region_list()
        self.select_region(duplicate["record_id"])
        self.autosave_map("Duplicated polygon")

    def delete_region(self) -> None:
        region = self.selected_region()
        if not region or not messagebox.askyesno("Delete region", f"Delete {region['name']}?", parent=self):
            return
        self.record_history()
        self.regions = [item for item in self.regions if item["record_id"] != region["record_id"]]
        self.editor_dirty = True
        self.selected_region_id = ""
        self.render_region_list()
        self.select_region("")
        self.autosave_map("Deleted polygon")


def main() -> None:
    os.environ.setdefault("HEADMASTERS_SCROLL_DATA_DIRECTORY", str(ROOT / "data"))
    configure_windows_app_id("Mapper")
    try:
        MapperWindow().mainloop()
    except Exception:
        details = traceback.format_exc()
        try:
            MapperWindow.write_crash_log(details)
        except OSError:
            pass
        raise


if __name__ == "__main__":
    main()
