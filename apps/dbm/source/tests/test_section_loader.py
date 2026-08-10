import unittest

from core.section_loader import load_sections


class SectionLoaderTests(unittest.TestCase):
    def test_all_sections_are_discovered_in_sidebar_order(self):
        sections = load_sections()
        section_titles = [section.title for section in sections]

        self.assertEqual(
            section_titles,
            [
                "Schools",
                "Wands",
                "Holdable Items",
                "Accessories",
                "General Items",
                "Creatures",
                "Plants",
                "Potions & Preparations",
                "Foods & Drinks",
                "Books",
                "Bookshelves",
                "Proficiencies",
                "Spells",
                "Settings & Preferences",
            ],
        )

    def test_section_keys_are_unique(self):
        sections = load_sections()
        section_keys = [section.key for section in sections]

        self.assertEqual(len(section_keys), len(set(section_keys)))


if __name__ == "__main__":
    unittest.main()
