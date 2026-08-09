import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from headmasters_scroll.errors import ManifestError
from headmasters_scroll.launcher import launch_app
from headmasters_scroll.manifests import load_manifests
from headmasters_scroll.merge import merge_documents
from headmasters_scroll.validation import validate_document


class FoundationTests(unittest.TestCase):
    def test_real_data_files_validate_and_period_ids_are_unique(self):
        root = Path(__file__).resolve().parents[1] / "data"
        for name in ("db.json", "world.json", "periods.json"):
            value = json.loads((root / name).read_text(encoding="utf-8"))
            validate_document(name, value)
        periods = json.loads((root / "periods.json").read_text(encoding="utf-8"))
        group_ids = [group["record_id"] for group in periods["period_groups"]]
        period_ids = [period["record_id"] for group in periods["period_groups"] for period in group["periods"]]
        self.assertEqual(len(group_ids), len(set(group_ids)))
        self.assertEqual(len(period_ids), len(set(period_ids)))

    def test_planned_manifests_load_disabled(self):
        root = Path(__file__).resolve().parents[1] / "apps"
        apps = load_manifests(root)
        self.assertEqual({app.app_id for app in apps}, {"mage-maker", "dbm", "game-board"})
        states = {app.app_id: app.enabled for app in apps}
        self.assertEqual(states, {"mage-maker": False, "dbm": False, "game-board": True})

    def test_duplicate_and_broken_manifests_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for folder in (root / "one", root / "two"):
                folder.mkdir()
                (folder / "app.json").write_text(json.dumps({
                    "id": "same", "name": "Same", "enabled": False, "entry_command": []
                }), encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifests(root)

    def test_enabled_manifest_requires_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "bad"
            folder.mkdir()
            (folder / "app.json").write_text(json.dumps({
                "id": "bad", "name": "Bad", "enabled": True, "entry_command": []
            }), encoding="utf-8")
            with self.assertRaises(ManifestError):
                load_manifests(root)

    def test_launcher_starts_separate_process(self):
        root = Path(__file__).resolve().parents[1] / "apps"
        manifest = next(iter(load_manifests(root)))
        enabled = type(manifest)(manifest.app_id, manifest.name, True, ("tool.exe",), None, manifest.directory)
        with patch("headmasters_scroll.launcher.subprocess.Popen") as popen:
            launch_app(enabled)
            popen.assert_called_once()

    def test_nested_period_records_merge_by_id(self):
        metadata = {"revision_id": "one", "last_modified_at": "2026-08-08T00:00:00Z", "last_modified_by": "test"}
        base = {"_headmasters_scroll": metadata, "schema_version": 1, "period_groups": [{
            "record_id": "group-1", "name": "Ages", "periods": [
                {"record_id": "period-1", "name": "First", "description": "old"}
            ]
        }]}
        app = json.loads(json.dumps(base))
        disk = json.loads(json.dumps(base))
        app["period_groups"][0]["periods"][0]["description"] = "app"
        disk["period_groups"][0]["name"] = "Historical ages"
        result = merge_documents("periods.json", base, app, disk)
        self.assertFalse(result.conflicts)
        self.assertEqual(result.data["period_groups"][0]["name"], "Historical ages")
        self.assertEqual(result.data["period_groups"][0]["periods"][0]["description"], "app")


if __name__ == "__main__":
    unittest.main()
