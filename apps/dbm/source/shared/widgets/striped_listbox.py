import tkinter as tk

from runtime_theme import runtime_theme


STRIPE_BLEND = 0.055


def blend_widget_colors(widget, base_color, blend_color, blend_amount):
    base_red, base_green, base_blue = widget.winfo_rgb(base_color)
    blend_red, blend_green, blend_blue = widget.winfo_rgb(blend_color)
    red = round(
        (base_red + ((blend_red - base_red) * blend_amount)) / 257
    )
    green = round(
        (base_green + ((blend_green - base_green) * blend_amount)) / 257
    )
    blue = round(
        (base_blue + ((blend_blue - base_blue) * blend_amount)) / 257
    )

    return f"#{red:02x}{green:02x}{blue:02x}"


def alternating_row_background(widget, theme_values, row_index):
    if row_index % 2 == 0:
        return theme_values["FIELD_BACKGROUND"]

    return blend_widget_colors(
        widget,
        theme_values["FIELD_BACKGROUND"],
        theme_values["TEXT_DARK"],
        STRIPE_BLEND,
    )


class StripedListbox(tk.Listbox):
    def __init__(self, parent, **options):
        super().__init__(parent, **options)
        self.hovered_index = None
        runtime_theme.register(self)

    def insert(self, index, *elements):
        result = super().insert(index, *elements)
        self.refresh_stripes()

        return result

    def delete(self, first, last=None):
        if last is None:
            result = super().delete(first)
        else:
            result = super().delete(first, last)

        if self.hovered_index is not None and self.hovered_index >= self.size():
            self.hovered_index = None

        self.refresh_stripes()

        return result

    def set_hovered_index(self, row_index):
        if row_index is None or not 0 <= row_index < self.size():
            self.hovered_index = None
        else:
            self.hovered_index = row_index

        self.refresh_stripes()

    def clear_hovered_index(self):
        self.hovered_index = None
        self.refresh_stripes()

    def row_background(self, row_index, theme_values=None):
        active_theme = theme_values or runtime_theme.get_values()

        return alternating_row_background(
            self,
            active_theme,
            row_index,
        )

    def refresh_stripes(self, theme_values=None):
        active_theme = theme_values or runtime_theme.get_values()

        for row_index in range(self.size()):
            if row_index == self.hovered_index:
                background = active_theme["LIST_HOVER"]
            else:
                background = self.row_background(
                    row_index,
                    active_theme,
                )

            self.itemconfigure(
                row_index,
                background=background,
                foreground=active_theme["TEXT_DARK"],
                selectbackground=active_theme["SIDEBAR_TILE_SELECTED"],
                selectforeground=active_theme["TEXT_DARK"],
            )

    def apply_theme(self, theme_values):
        self.configure(
            bg=theme_values["FIELD_BACKGROUND"],
            fg=theme_values["TEXT_DARK"],
            selectbackground=theme_values["SIDEBAR_TILE_SELECTED"],
            selectforeground=theme_values["TEXT_DARK"],
            highlightbackground=theme_values["BORDER_SOFT"],
            highlightcolor=theme_values["BORDER_SOFT"],
        )
        self.refresh_stripes(theme_values)
