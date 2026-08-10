import unittest

from core.section_loader import load_sections
from sections.wands.workspace import WAND_VIEW_DEFINITIONS


class WandWorkspaceTests(unittest.TestCase):
    def test_wand_workspace_has_one_sidebar_section(self):
        sections = load_sections()
        wand_sections = [
            section
            for section in sections
            if section.key.startswith("wand")
        ]

        self.assertEqual(len(wand_sections), 1)
        self.assertEqual(wand_sections[0].key, "wands")
        self.assertEqual(wand_sections[0].title, "Wands")

    def test_wand_views_keep_separate_storage_collections(self):
        view_keys = [definition[0] for definition in WAND_VIEW_DEFINITIONS]
        storage_keys = [definition[2] for definition in WAND_VIEW_DEFINITIONS]

        self.assertEqual(
            view_keys,
            ["wands", "woods", "cores", "qualities", "makers"],
        )
        self.assertEqual(
            storage_keys,
            [
                "wands",
                "wand_woods",
                "wand_cores",
                "wand_qualities",
                "wand_makers",
            ],
        )
        self.assertEqual(len(storage_keys), len(set(storage_keys)))


if __name__ == "__main__":
    unittest.main()
