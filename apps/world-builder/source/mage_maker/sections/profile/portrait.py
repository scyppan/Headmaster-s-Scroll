from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk


class SquareCropDialog(tk.Toplevel):
    """Modal square crop chooser returning a source-image pixel box."""

    def __init__(self, parent: tk.Misc, path: Path):
        super().__init__(parent)
        try:
            from PIL import Image, ImageOps, ImageTk
        except ImportError as error:
            self.destroy()
            raise RuntimeError("Portrait import requires Pillow") from error
        with Image.open(path) as opened:
            self.source = ImageOps.exif_transpose(opened).convert("RGB")
        if self.source.width < 32 or self.source.height < 32:
            self.destroy()
            raise ValueError("The portrait image is too small")
        self.result: tuple[int, int, int, int] | None = None
        self.title("Crop portrait")
        self.transient(parent)
        self.grab_set()
        self.resizable(False, False)
        self.configure(bg="#ead7aa")
        self.scale = min(620 / self.source.width, 470 / self.source.height, 1.0)
        preview_size = (
            max(1, round(self.source.width * self.scale)),
            max(1, round(self.source.height * self.scale)),
        )
        preview = self.source.resize(preview_size, Image.Resampling.LANCZOS)
        self.preview_width, self.preview_height = preview.size
        self.photo = ImageTk.PhotoImage(preview)
        tk.Label(
            self,
            text="Drag the square over the portrait. Use Size to tighten or widen the crop.",
            bg="#ead7aa",
            fg="#382719",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=14, pady=(12, 8))
        self.canvas = tk.Canvas(
            self,
            width=self.preview_width,
            height=self.preview_height,
            highlightthickness=1,
            highlightbackground="#7b3f2b",
            cursor="fleur",
        )
        self.canvas.pack(padx=14)
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        initial = min(self.preview_width, self.preview_height)
        self.side_value = tk.DoubleVar(value=initial)
        self.center_x = self.preview_width / 2
        self.center_y = self.preview_height / 2
        self.rectangle = self.canvas.create_rectangle(0, 0, initial, initial, outline="#fff7cf", width=3)
        self.shades: list[int] = []
        self.drag_offset = (0.0, 0.0)
        self.canvas.bind("<ButtonPress-1>", self.start_drag)
        self.canvas.bind("<B1-Motion>", self.drag)
        controls = tk.Frame(self, bg="#ead7aa")
        controls.pack(fill="x", padx=14, pady=10)
        tk.Label(controls, text="Size", bg="#ead7aa", fg="#382719").pack(side="left")
        ttk.Scale(
            controls,
            from_=min(48, initial),
            to=initial,
            variable=self.side_value,
            command=lambda _value: self.draw_crop(),
        ).pack(side="left", fill="x", expand=True, padx=10)
        tk.Button(controls, text="Cancel", command=self.cancel, bg="#c9aa71", relief="flat", padx=12, pady=7).pack(side="right")
        tk.Button(controls, text="Use crop", command=self.accept, bg="#7b3f2b", fg="#fff8e7", relief="flat", padx=12, pady=7).pack(side="right", padx=(0, 7))
        self.bind("<Escape>", lambda _event: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.draw_crop()
        self.wait_window(self)

    def bounds(self) -> tuple[float, float, float, float]:
        side = min(float(self.side_value.get()), self.preview_width, self.preview_height)
        half = side / 2
        self.center_x = max(half, min(self.preview_width - half, self.center_x))
        self.center_y = max(half, min(self.preview_height - half, self.center_y))
        return self.center_x - half, self.center_y - half, self.center_x + half, self.center_y + half

    def draw_crop(self) -> None:
        left, top, right, bottom = self.bounds()
        self.canvas.coords(self.rectangle, left, top, right, bottom)
        for shade in self.shades:
            self.canvas.delete(shade)
        fill = "#26170e"
        self.shades = [
            self.canvas.create_rectangle(0, 0, self.preview_width, top, fill=fill, stipple="gray50", outline=""),
            self.canvas.create_rectangle(0, bottom, self.preview_width, self.preview_height, fill=fill, stipple="gray50", outline=""),
            self.canvas.create_rectangle(0, top, left, bottom, fill=fill, stipple="gray50", outline=""),
            self.canvas.create_rectangle(right, top, self.preview_width, bottom, fill=fill, stipple="gray50", outline=""),
        ]
        self.canvas.tag_raise(self.rectangle)

    def start_drag(self, event: tk.Event) -> None:
        self.drag_offset = (event.x - self.center_x, event.y - self.center_y)

    def drag(self, event: tk.Event) -> None:
        self.center_x = event.x - self.drag_offset[0]
        self.center_y = event.y - self.drag_offset[1]
        self.draw_crop()

    def accept(self) -> None:
        left, top, right, _bottom = self.bounds()
        source_left = round(left / self.scale)
        source_top = round(top / self.scale)
        source_side = round((right - left) / self.scale)
        source_side = min(source_side, self.source.width - source_left, self.source.height - source_top)
        self.result = (source_left, source_top, source_left + source_side, source_top + source_side)
        self.destroy()

    def cancel(self) -> None:
        self.result = None
        self.destroy()


def choose_square_crop(parent: tk.Misc, path: Path):
    return SquareCropDialog(parent, path).result
