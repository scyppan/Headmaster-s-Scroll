from __future__ import annotations

import ctypes
import sys
import tkinter as tk

from .paths import PROJECT_ROOT


WINDOW_ICON = PROJECT_ROOT / "assets" / "worn-scroll.ico"


def configure_windows_app_id(app_name: str = "HeadmastersScroll") -> None:
    if sys.platform == "win32":
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            f"CharmsCheck.HeadmastersScroll.{app_name}"
        )


def apply_window_icon(window: tk.Tk | tk.Toplevel) -> None:
    if sys.platform == "win32":
        icon_path = str(WINDOW_ICON)
        # Set the current window icon for the taskbar, then make it the
        # default for any dialogs or additional top-level windows.
        window.iconbitmap(icon_path)
        window.iconbitmap(default=icon_path)
