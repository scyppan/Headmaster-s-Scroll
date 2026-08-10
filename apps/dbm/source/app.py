import tkinter as tk
import ctypes
import sys
from pathlib import Path

from core.section_loader import load_sections
from database import JsonDatabase
from database.paths import DATABASE_PATH
from preferences import PREFERENCES_PATH, UserPreferences
from runtime_theme import bind_theme
from theme import APP_BACKGROUND, configure_tk_fonts
from window.content_host import ContentHost
from window.lifecycle import ApplicationLifecycle
from window.sidebar import Sidebar


class App(tk.Tk):
    def __init__(self):
        if sys.platform == "win32":
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "CharmsCheck.DatabaseManager"
                )
            except (AttributeError, OSError):
                pass

        super().__init__()
        configure_tk_fonts(self)

        asset_directory = Path(__file__).parent / "assets"
        icon_path = asset_directory / "House Icon.png"
        windows_icon_path = asset_directory / "Charms Check Large.ico"

        self.title("Charms Check DB Manager")

        if sys.platform == "win32" and windows_icon_path.exists():
            try:
                self.iconbitmap(str(windows_icon_path))
            except tk.TclError:
                pass

        elif icon_path.exists():
            self.app_icon = tk.PhotoImage(file=icon_path)
            self.iconphoto(True, self.app_icon)

        self.sections = load_sections()
        self.database = JsonDatabase(DATABASE_PATH)
        self.database.load()
        self.preferences = UserPreferences(PREFERENCES_PATH)
        self.preferences.load()

        for section in self.sections:
            if section.storage_type is None:
                continue

            self.database.ensure_container(
                section.database_key,
                section.storage_type,
            )

        window_preferences = self.preferences.get_window_preferences()
        start_maximized = window_preferences.get("start_maximized", True)
        sidebar_width = window_preferences.get("sidebar_width", 250)

        if not isinstance(sidebar_width, int):
            sidebar_width = 250

        if start_maximized:
            self.state("zoomed")
        else:
            self.geometry("1100x700")

        self.minsize(800, 500)
        self.configure(bg=APP_BACKGROUND)
        bind_theme(self, background="APP_BACKGROUND")

        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.content_host = ContentHost(
            self,
            self.sections,
            self.database,
        )
        self.content_host.grid(row=0, column=1, sticky="nsew")

        self.sidebar = Sidebar(
            self,
            sections=self.sections,
            section_command=self.content_host.show_section,
            sidebar_width=sidebar_width,
        )
        self.sidebar.grid(row=0, column=0, sticky="nsew")

        self.lifecycle = ApplicationLifecycle(
            self,
            self.content_host,
            self.database,
        )
        self.protocol(
            "WM_DELETE_WINDOW",
            self.lifecycle.close_application,
        )
