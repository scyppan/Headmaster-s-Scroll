from __future__ import annotations

import re
import unittest
from pathlib import Path


class GameBoardPublicLoaderTests(unittest.TestCase):
    def test_wordpress_loader_exposes_one_machine_readable_public_config(self):
        root = Path(__file__).resolve().parents[1]
        loader = (
            root / "apps" / "charms-check-game-board-weblink" / "wordpress.html"
        ).read_text(encoding="utf-8")

        self.assertEqual(loader.count("ccgb-public-config-v1"), 1)
        self.assertEqual(loader.count("const PUBLIC_CONFIG"), 1)
        self.assertIn("const API_BASE = PUBLIC_CONFIG.apiBase", loader)
        self.assertNotRegex(
            loader,
            re.compile(r"const\s+API_BASE\s*=\s*['\"]"),
        )
        self.assertRegex(
            loader,
            re.compile(
                r"schema\s*:\s*['\"]ccgb-public-config-v1['\"]"
                r"[\s\S]{0,256}?"
                r"apiBase\s*:\s*['\"]https://beast\.tail102829\.ts\.net['\"]"
            ),
        )


if __name__ == "__main__":
    unittest.main()
