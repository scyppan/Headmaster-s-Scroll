from core.section_definition import SectionDefinition
from .page import SettingsAndPreferencesPage


SECTION = SectionDefinition(
    key="settings_and_preferences",
    title="Settings & Preferences",
    order=220,
    page_class=SettingsAndPreferencesPage,
    storage_type=None,
)
