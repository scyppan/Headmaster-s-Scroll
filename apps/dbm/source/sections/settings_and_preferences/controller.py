from copy import deepcopy

from preferences import PREFERENCES_PATH, UserPreferences


class SettingsController:
    def __init__(self, database):
        self.database = database
        self.preferences = UserPreferences(PREFERENCES_PATH)
        self.preferences.load()

    def load_general_settings(self):
        return {
            "metadata": self.database.get_database_metadata(),
            "window": self.preferences.get_window_preferences(),
        }

    def save_general_settings(
        self,
        database_version,
        start_maximized,
        sidebar_width,
    ):
        self.database.set_database_version(database_version)
        self.database.save()
        self.preferences.update_window_preferences(
            start_maximized,
            sidebar_width,
        )
        self.preferences.save()

        return self.load_general_settings()

    def load_theme_settings(self):
        self.preferences.load()

        return self.preferences.get_theme_preferences()

    def save_theme_settings(self, theme_values):
        self.preferences.update_theme_preferences(theme_values)
        self.preferences.save()

        return self.preferences.get_theme_preferences()

    def load_searching_methods(self):
        return deepcopy(
            self.database.data.get("gathering_methods", []) or []
        )

    def save_searching_methods(self, methods):
        self.database.data["gathering_methods"] = deepcopy(methods)
        self.database.dirty = True
        self.database.save()

        return self.load_searching_methods()
