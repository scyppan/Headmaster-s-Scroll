import json
import os
import re
from copy import deepcopy
from pathlib import Path

from preferences.defaults import DEFAULT_PREFERENCES, DEFAULT_THEME


HEX_COLOR_PATTERN = re.compile(r"^#[0-9A-Fa-f]{6}$")


class UserPreferences:
    def __init__(self, preferences_path):
        self.preferences_path = Path(preferences_path)
        self.data = deepcopy(DEFAULT_PREFERENCES)

    def load(self):
        self.data = deepcopy(DEFAULT_PREFERENCES)

        if not self.preferences_path.exists():
            return deepcopy(self.data)

        try:
            with self.preferences_path.open(
                "r",
                encoding="utf-8",
            ) as preferences_file:
                loaded_data = json.load(preferences_file)
        except (json.JSONDecodeError, OSError):
            return deepcopy(self.data)

        if not isinstance(loaded_data, dict):
            return deepcopy(self.data)

        self.merge_preferences(loaded_data)

        return deepcopy(self.data)

    def merge_preferences(self, loaded_data):
        settings_version = loaded_data.get("settings_version")

        if isinstance(settings_version, int):
            self.data["settings_version"] = settings_version

        loaded_window = loaded_data.get("window", {})

        if isinstance(loaded_window, dict):
            self.data["window"].update(loaded_window)

        loaded_layouts = loaded_data.get("layouts", {})

        if isinstance(loaded_layouts, dict):
            self.data["layouts"] = deepcopy(loaded_layouts)

        loaded_theme = loaded_data.get("theme", {})

        if isinstance(loaded_theme, dict):
            for color_name in DEFAULT_THEME:
                color_value = loaded_theme.get(color_name)

                if (
                    isinstance(color_value, str)
                    and HEX_COLOR_PATTERN.fullmatch(color_value)
                ):
                    self.data["theme"][color_name] = color_value

    def get_window_preferences(self):
        return deepcopy(self.data["window"])

    def get_theme_preferences(self):
        return deepcopy(self.data["theme"])

    def update_window_preferences(self, start_maximized, sidebar_width):
        self.data["window"] = {
            "start_maximized": bool(start_maximized),
            "sidebar_width": int(sidebar_width),
        }

    def update_theme_preferences(self, theme_values):
        updated_theme = deepcopy(DEFAULT_THEME)

        for color_name in DEFAULT_THEME:
            color_value = theme_values.get(color_name)

            if isinstance(color_value, str):
                updated_theme[color_name] = color_value.upper()

        self.data["theme"] = updated_theme

    def save(self):
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.preferences_path.with_suffix(".json.tmp")

        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as preferences_file:
            json.dump(
                self.data,
                preferences_file,
                ensure_ascii=False,
                indent=2,
            )
            preferences_file.write("\n")

        os.replace(temporary_path, self.preferences_path)
