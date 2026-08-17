"""Compatibility wrapper for the former standalone Gathering & Stock page.

Searching Methods now lives in Settings & Preferences. Keeping this wrapper
preserves older imports without retaining the catalog-wide assignment list.
"""

from sections.settings_and_preferences.controller import SettingsController
from sections.settings_and_preferences.searching_methods_view import (
    SearchingMethodsView,
)


class GatheringMethodsPage(SearchingMethodsView):
    def __init__(self, parent, database):
        super().__init__(
            parent,
            controller=SettingsController(database),
            dirty_command=lambda: None,
        )
