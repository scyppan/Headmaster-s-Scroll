THEME_COLOR_FIELDS = (
    ("Application", "APP_BACKGROUND", "Application background", "#E9E2D0"),
    ("Application", "SURFACE", "Cards and surfaces", "#F3EFE0"),
    ("Application", "SURFACE_MUTED", "Muted surfaces", "#F3EDDD"),
    ("Editable Fields", "FIELD_BACKGROUND", "Editable field", "#F2EEE3"),
    ("Editable Fields", "FIELD_HOVER", "Editable field hover", "#ECE7D7"),
    ("Editable Fields", "FIELD_FOCUS", "Editable field focus border", "#8F8469"),
    ("Editable Fields", "FIELD_DISABLED", "Disabled editable field", "#D8CFB6"),
    ("Primary Tan", "PRIMARY", "Primary tan", "#D4C6A1"),
    ("Primary Tan", "PRIMARY_LIGHT", "Light primary tan", "#E8DDBF"),
    ("Primary Tan", "PRIMARY_DARK", "Dark primary tan", "#A99D7E"),
    ("Primary Tan", "PRIMARY_HOVER", "Primary hover", "#C7B88F"),
    ("Buttons", "BUTTON_SOFT", "Soft button", "#DDD2B4"),
    ("Buttons", "BUTTON_SOFT_HOVER", "Soft button hover", "#CFC09A"),
    ("Buttons", "BUTTON_DISABLED", "Disabled button", "#E6DECA"),
    ("Buttons", "DELETE_SOFT", "Delete button", "#D4BDB1"),
    ("Buttons", "DELETE_HOVER", "Delete button hover", "#C6A397"),
    ("Sidebar", "SIDEBAR_BACKGROUND", "Sidebar background", "#625E50"),
    ("Sidebar", "SIDEBAR_TILE", "Sidebar tile", "#817A67"),
    ("Sidebar", "SIDEBAR_TILE_HOVER", "Sidebar tile hover", "#958C75"),
    ("Sidebar", "SIDEBAR_TILE_SELECTED", "Selected sidebar tile", "#D4C6A1"),
    ("Text", "TEXT_DARK", "Dark text", "#302D26"),
    ("Text", "TEXT_MUTED", "Muted text", "#686255"),
    ("Text", "TEXT_LIGHT", "Light text", "#FFFDF6"),
    ("Text", "TEXT_DISABLED", "Disabled text", "#8C8576"),
    ("Borders and Lists", "BORDER", "Border", "#C8B993"),
    ("Borders and Lists", "BORDER_SOFT", "Soft border", "#D8CCAD"),
    ("Borders and Lists", "LIST_HOVER", "List item hover", "#DED2B4"),
)


DEFAULT_THEME = {
    field_key: default_value
    for category, field_key, label, default_value in THEME_COLOR_FIELDS
}


DEFAULT_PREFERENCES = {
    "settings_version": 1,
    "window": {
        "start_maximized": True,
        "sidebar_width": 250,
    },
    "layouts": {},
    "theme": DEFAULT_THEME,
}
