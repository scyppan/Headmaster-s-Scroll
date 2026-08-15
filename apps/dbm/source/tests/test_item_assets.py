import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from database import JsonDatabase
from sections.items.general_items.controller import GeneralItemController
from shared import item_assets
from shared.item_assets import (
    list_item_image_assets,
    normalize_item_image_reference,
    resolve_item_image_reference,
)


class ItemAssetTests(unittest.TestCase):
    def temporary_asset_library(self):
        temporary_directory = tempfile.TemporaryDirectory()
        project_root = Path(temporary_directory.name)
        asset_root = project_root / "assets" / "items"
        asset_root.mkdir(parents=True)
        return temporary_directory, project_root, asset_root

    def test_references_are_project_relative_and_reusable(self):
        temporary_directory, project_root, asset_root = (
            self.temporary_asset_library()
        )
        self.addCleanup(temporary_directory.cleanup)
        image_path = asset_root / "wands" / "shared wand.png"
        image_path.parent.mkdir()
        image_path.write_bytes(b"image")

        with (
            patch.object(item_assets, "PROJECT_ROOT", project_root),
            patch.object(item_assets, "ITEM_ASSET_DIRECTORY", asset_root),
        ):
            reference = normalize_item_image_reference(
                image_path,
                require_exists=True,
            )
            self.assertEqual(reference, "assets/items/wands/shared wand.png")
            self.assertEqual(resolve_item_image_reference(reference), image_path)
            self.assertEqual(
                list_item_image_assets("shared wand"),
                [reference],
            )

    def test_reference_outside_item_library_is_rejected(self):
        temporary_directory, project_root, asset_root = (
            self.temporary_asset_library()
        )
        self.addCleanup(temporary_directory.cleanup)
        outside_path = project_root / "outside.png"

        with (
            patch.object(item_assets, "PROJECT_ROOT", project_root),
            patch.object(item_assets, "ITEM_ASSET_DIRECTORY", asset_root),
        ):
            with self.assertRaisesRegex(ValueError, "assets/items"):
                normalize_item_image_reference(outside_path)

    def test_non_image_files_are_not_listed_or_accepted(self):
        temporary_directory, project_root, asset_root = (
            self.temporary_asset_library()
        )
        self.addCleanup(temporary_directory.cleanup)
        (asset_root / "template.psd").write_bytes(b"template")
        (asset_root / "usable.webp").write_bytes(b"image")

        with (
            patch.object(item_assets, "PROJECT_ROOT", project_root),
            patch.object(item_assets, "ITEM_ASSET_DIRECTORY", asset_root),
        ):
            self.assertEqual(
                list_item_image_assets(),
                ["assets/items/usable.webp"],
            )
            with self.assertRaisesRegex(ValueError, "Unsupported"):
                normalize_item_image_reference(asset_root / "template.psd")

    def test_item_record_stores_one_reference_without_copying_image(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = Path(temporary_directory) / "db.json"
            database_path.write_text(
                '{"_database": {"schema_version": 1}, '
                '"general_items": []}',
                encoding="utf-8",
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = GeneralItemController(database)
            reference = "assets/items/wands/ollivander superior.png"
            created = controller.create_record(
                {
                    "name": "Reusable Image Test",
                    "type": "Other",
                    "image_asset": reference,
                }
            )

            self.assertEqual(created["image_asset"], reference)
            reloaded = JsonDatabase(database_path)
            reloaded.load()
            self.assertEqual(
                reloaded.get_collection("general_items")[0]["image_asset"],
                reference,
            )
            self.assertFalse(
                (Path(temporary_directory) / "assets" / "items").exists()
            )


if __name__ == "__main__":
    unittest.main()
