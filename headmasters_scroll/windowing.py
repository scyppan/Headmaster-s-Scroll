from __future__ import annotations

import ctypes
import sys
import tkinter as tk
from pathlib import Path

from .paths import PROJECT_ROOT


HEADMASTERS_SCROLL_ICON = PROJECT_ROOT / "assets" / "worn-scroll.ico"
GAME_BOARD_ICON = PROJECT_ROOT / "assets" / "enchanted-d10.ico"
MAPPER_ICON = PROJECT_ROOT / "assets" / "north-america-hollow-outline-grey.ico"
WINDOW_ICON = HEADMASTERS_SCROLL_ICON


def configure_windows_app_id(app_name: str = "HeadmastersScroll") -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"CharmsCheck.HeadmastersScroll.{app_name}"
        )


def apply_window_icon(
    window: tk.Tk | tk.Toplevel,
    icon: Path = HEADMASTERS_SCROLL_ICON,
) -> None:
    if sys.platform == "win32":
        icon_path = str(icon)
        # Set the current window icon for the taskbar, then make it the
        # default for any dialogs or additional top-level windows.
        window.iconbitmap(icon_path)
        window.iconbitmap(default=icon_path)
        # Some Windows/Tk combinations keep the Python process icon in the
        # taskbar unless WM_SETICON is also reached through iconphoto. Retain
        # the PhotoImage on the window so Tk cannot garbage-collect it.
        try:
            from PIL import Image, ImageTk

            with Image.open(icon) as source:
                rendered = source.convert("RGBA").resize((64, 64), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(rendered, master=window)
            setattr(window, "_headmasters_scroll_icon_photo", photo)
            window.iconphoto(True, photo)
        except (OSError, tk.TclError, ImportError):
            pass


def maximize_window(window: tk.Tk | tk.Toplevel) -> None:
    """Maximize while preserving the normal title bar and Windows taskbar."""
    try:
        window.state("zoomed")
    except tk.TclError:
        window.attributes("-zoomed", True)
