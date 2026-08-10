import tkinter as tk
import weakref

from preferences import PREFERENCES_PATH, UserPreferences


class RuntimeTheme:
    def __init__(self):
        preferences = UserPreferences(PREFERENCES_PATH)
        preferences.load()
        self.values = preferences.get_theme_preferences()
        self.listeners = weakref.WeakSet()

    def get_values(self):
        return dict(self.values)

    def register(self, listener):
        self.listeners.add(listener)
        listener.apply_theme(self.values)

    def update_color(self, color_name, color_value):
        self.values[color_name] = color_value
        self.notify_listeners()

    def update_theme(self, theme_values):
        self.values.update(theme_values)
        self.notify_listeners()

    def notify_listeners(self):
        discarded_listeners = []

        for listener in list(self.listeners):
            try:
                listener.apply_theme(self.values)
            except tk.TclError:
                discarded_listeners.append(listener)

        for listener in discarded_listeners:
            self.listeners.discard(listener)


class ThemeBinding:
    def __init__(self, widget, roles):
        self.widget_reference = weakref.ref(widget)
        self.roles = roles

    def apply_theme(self, theme_values):
        widget = self.widget_reference()

        if widget is None:
            return

        configuration = {
            option_name: theme_values[color_name]
            for option_name, color_name in self.roles.items()
        }
        widget.configure(**configuration)


runtime_theme = RuntimeTheme()


def bind_theme(widget, **roles):
    theme_binding = ThemeBinding(widget, roles)

    if not hasattr(widget, "theme_bindings"):
        widget.theme_bindings = []

    widget.theme_bindings.append(theme_binding)
    runtime_theme.register(theme_binding)

    return widget
