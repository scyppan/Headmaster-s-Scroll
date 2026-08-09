from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from .errors import ManifestError
from .manifests import AppManifest, load_manifests
from .paths import PROJECT_ROOT
from .windowing import apply_window_icon, configure_windows_app_id, maximize_window


def command_for(manifest: AppManifest) -> list[str]:
    replacements = {"{python}": sys.executable, "{root}": str(PROJECT_ROOT)}
    command: list[str] = []
    for token in manifest.entry_command:
        expanded = token
        for source, destination in replacements.items():
            expanded = expanded.replace(source, destination)
        command.append(expanded)
    return command


def launch_app(manifest: AppManifest) -> subprocess.Popen:
    if not manifest.enabled:
        raise ValueError(f"{manifest.name} is not enabled")
    return subprocess.Popen(command_for(manifest), cwd=PROJECT_ROOT)


class HomeScreen(tk.Tk):
    PARCHMENT = "#ead7aa"
    LIGHT_PARCHMENT = "#f5e8c8"
    DEEP_PARCHMENT = "#cfad70"
    INK = "#3a281b"
    MUTED_INK = "#765f45"
    ACCENT = "#7b3f2b"
    TILE_SIZE = 168
    TILE_GAP = 22

    def __init__(self, manifests: list[AppManifest] | None = None):
        super().__init__()
        self.title("Headmaster's Scroll")
        self.geometry("1100x720")
        self.minsize(720, 520)
        self.configure(background=self.PARCHMENT)
        apply_window_icon(self)
        self.bind("<F11>", self._toggle_maximized)
        self.bind("<Escape>", self._restore_window)
        self.manifests = manifests if manifests is not None else load_manifests()
        self.tiles: list[tk.Frame] = []
        self._build()
        self.after_idle(lambda: maximize_window(self))

    def _build(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure(
            "Parchment.Vertical.TScrollbar",
            background=self.DEEP_PARCHMENT,
            troughcolor=self.PARCHMENT,
            bordercolor=self.PARCHMENT,
            arrowcolor=self.INK,
        )

        header = tk.Frame(self, background=self.PARCHMENT)
        header.pack(fill="x", padx=58, pady=(34, 16))
        tk.Label(
            header,
            text="Headmaster's Scroll",
            font=("Georgia", 31, "bold"),
            foreground=self.INK,
            background=self.PARCHMENT,
        ).pack()
        tk.Label(
            header,
            text="Select an application from the collection",
            font=("Georgia", 12, "italic"),
            foreground=self.MUTED_INK,
            background=self.PARCHMENT,
        ).pack(pady=(6, 0))
        tk.Frame(header, height=2, background=self.ACCENT).pack(fill="x", pady=(20, 0))

        body = tk.Frame(self, background=self.PARCHMENT)
        body.pack(fill="both", expand=True, padx=(46, 30), pady=(4, 18))
        self.canvas = tk.Canvas(
            body,
            background=self.PARCHMENT,
            borderwidth=0,
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(
            body,
            orient="vertical",
            command=self.canvas.yview,
            style="Parchment.Vertical.TScrollbar",
        )
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(12, 0))
        self.cards = tk.Frame(self.canvas, background=self.PARCHMENT)
        self.cards_window = self.canvas.create_window((0, 0), window=self.cards, anchor="nw")
        self.cards.bind("<Configure>", self._update_scroll_region)
        self.canvas.bind("<Configure>", self._resize_grid)
        self.canvas.bind_all("<MouseWheel>", self._scroll_cards)

        for manifest in self.manifests:
            self.tiles.append(self._make_tile(manifest))
        self.after_idle(self._reflow_tiles)

        tk.Label(
            self,
            text="F11 toggles maximized view  •  Esc restores the window",
            font=("Segoe UI", 9),
            foreground=self.MUTED_INK,
            background=self.PARCHMENT,
        ).pack(pady=(0, 12))

    def _make_tile(self, manifest: AppManifest) -> tk.Frame:
        tile = tk.Frame(
            self.cards,
            width=self.TILE_SIZE,
            height=self.TILE_SIZE,
            background=self.LIGHT_PARCHMENT,
            highlightbackground=self.DEEP_PARCHMENT,
            highlightcolor=self.ACCENT,
            highlightthickness=2,
            cursor="hand2" if manifest.enabled else "arrow",
        )
        tile.grid_propagate(False)
        name = tk.Label(
            tile,
            text=manifest.name,
            wraplength=self.TILE_SIZE - 26,
            justify="center",
            font=("Georgia", 15, "bold"),
            foreground=self.INK,
            background=self.LIGHT_PARCHMENT,
        )
        name.place(relx=0.5, rely=0.42, anchor="center")
        status = tk.Label(
            tile,
            text="OPEN" if manifest.enabled else "COMING SOON",
            font=("Segoe UI", 8, "bold"),
            foreground=self.ACCENT if manifest.enabled else self.MUTED_INK,
            background=self.LIGHT_PARCHMENT,
        )
        status.place(relx=0.5, rely=0.78, anchor="center")
        if manifest.enabled:
            for widget in (tile, name, status):
                widget.bind("<Button-1>", lambda _event, app=manifest: self._launch(app))
        return tile

    def _resize_grid(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.cards_window, width=max(event.width, self.TILE_SIZE))
        self._reflow_tiles()

    def _reflow_tiles(self) -> None:
        available = max(self.canvas.winfo_width(), self.TILE_SIZE)
        columns = max(1, available // (self.TILE_SIZE + self.TILE_GAP))
        used_width = columns * self.TILE_SIZE + (columns - 1) * self.TILE_GAP
        side_padding = max(8, (available - used_width) // 2)
        for index, tile in enumerate(self.tiles):
            tile.grid_forget()
            row, column = divmod(index, columns)
            tile.grid(
                row=row,
                column=column,
                padx=(side_padding if column == 0 else self.TILE_GAP // 2, self.TILE_GAP // 2),
                pady=self.TILE_GAP // 2,
            )

    def _update_scroll_region(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _scroll_cards(self, event: tk.Event) -> None:
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def _toggle_maximized(self, _event: tk.Event | None = None) -> str:
        if self.state() == "zoomed":
            self.state("normal")
        else:
            maximize_window(self)
        return "break"

    def _restore_window(self, _event: tk.Event | None = None) -> str:
        self.state("normal")
        return "break"

    def _launch(self, manifest: AppManifest) -> None:
        try:
            launch_app(manifest)
        except OSError as error:
            messagebox.showerror("Could not open app", str(error), parent=self)


def main() -> None:
    configure_windows_app_id()
    try:
        HomeScreen().mainloop()
    except ManifestError as error:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Invalid app configuration", str(error), parent=root)
        root.destroy()


if __name__ == "__main__":
    main()
