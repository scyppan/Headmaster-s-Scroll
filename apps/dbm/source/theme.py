import tkinter as tk
import tkinter.font as tkfont

from runtime_theme import runtime_theme


FONT_FAMILY = "Segoe UI"
MONOSPACE_FONT_FAMILY = "Consolas"
FONT_WEIGHT = "bold"

_NAMED_FONT_FAMILIES = {
    "TkDefaultFont": FONT_FAMILY,
    "TkTextFont": FONT_FAMILY,
    "TkMenuFont": FONT_FAMILY,
    "TkHeadingFont": FONT_FAMILY,
    "TkCaptionFont": FONT_FAMILY,
    "TkSmallCaptionFont": FONT_FAMILY,
    "TkIconFont": FONT_FAMILY,
    "TkTooltipFont": FONT_FAMILY,
    "TkFixedFont": MONOSPACE_FONT_FAMILY,
}


def app_font(size):
    return (FONT_FAMILY, size, FONT_WEIGHT)


def monospace_font(size):
    return (MONOSPACE_FONT_FAMILY, size, FONT_WEIGHT)


def configure_tk_fonts(root):
    for font_name, font_family in _NAMED_FONT_FAMILIES.items():
        try:
            named_font = tkfont.nametofont(font_name, root=root)
        except tk.TclError:
            continue

        named_font.configure(
            family=font_family,
            weight=FONT_WEIGHT,
        )


_theme = runtime_theme.get_values()

APP_BACKGROUND = _theme["APP_BACKGROUND"]
SURFACE = _theme["SURFACE"]
SURFACE_MUTED = _theme["SURFACE_MUTED"]

FIELD_BACKGROUND = _theme["FIELD_BACKGROUND"]
FIELD_HOVER = _theme["FIELD_HOVER"]
FIELD_FOCUS = _theme["FIELD_FOCUS"]
FIELD_DISABLED = _theme["FIELD_DISABLED"]

PRIMARY = _theme["PRIMARY"]
PRIMARY_LIGHT = _theme["PRIMARY_LIGHT"]
PRIMARY_DARK = _theme["PRIMARY_DARK"]
PRIMARY_HOVER = _theme["PRIMARY_HOVER"]

BUTTON_SOFT = _theme["BUTTON_SOFT"]
BUTTON_SOFT_HOVER = _theme["BUTTON_SOFT_HOVER"]
BUTTON_DISABLED = _theme["BUTTON_DISABLED"]
DELETE_SOFT = _theme["DELETE_SOFT"]
DELETE_HOVER = _theme["DELETE_HOVER"]

SIDEBAR_BACKGROUND = _theme["SIDEBAR_BACKGROUND"]
SIDEBAR_TILE = _theme["SIDEBAR_TILE"]
SIDEBAR_TILE_HOVER = _theme["SIDEBAR_TILE_HOVER"]
SIDEBAR_TILE_SELECTED = _theme["SIDEBAR_TILE_SELECTED"]

TEXT_DARK = _theme["TEXT_DARK"]
TEXT_MUTED = _theme["TEXT_MUTED"]
TEXT_LIGHT = _theme["TEXT_LIGHT"]
TEXT_DISABLED = _theme["TEXT_DISABLED"]

BORDER = _theme["BORDER"]
BORDER_SOFT = _theme["BORDER_SOFT"]
LIST_HOVER = _theme["LIST_HOVER"]

CONTROL_RADIUS = 10
