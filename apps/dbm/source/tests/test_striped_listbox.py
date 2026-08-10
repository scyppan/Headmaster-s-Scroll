import unittest

from shared.widgets.striped_listbox import alternating_row_background


class ColorWidget:
    def winfo_rgb(self, color_value):
        red = int(color_value[1:3], 16) * 257
        green = int(color_value[3:5], 16) * 257
        blue = int(color_value[5:7], 16) * 257

        return red, green, blue


class StripedListboxTests(unittest.TestCase):
    def test_adjacent_rows_receive_distinct_theme_derived_colors(self):
        widget = ColorWidget()
        theme_values = {
            "FIELD_BACKGROUND": "#f2eee3",
            "TEXT_DARK": "#302d26",
        }
        even_background = alternating_row_background(
            widget,
            theme_values,
            0,
        )
        odd_background = alternating_row_background(
            widget,
            theme_values,
            1,
        )

        self.assertEqual(even_background, "#f2eee3")
        self.assertEqual(odd_background, "#e7e3d9")
        self.assertNotEqual(even_background, odd_background)


if __name__ == "__main__":
    unittest.main()
