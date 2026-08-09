import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from headmasters_scroll.errors import DataLockError, DataValidationError
from headmasters_scroll.store import SharedJsonStore


def sample_document():
    return {
        "_database": {"schema_version": 1},
        "_headmasters_scroll": {
            "revision_id": "revision-1",
            "last_modified_at": "2026-08-08T00:00:00Z",
            "last_modified_by": "test-app",
        },
        "wand_woods": [{"record_id": "wood-1", "name": "Oak", "notes": "old"}],
        "wand_cores": [], "wands": [], "books": [], "spells": [],
    }


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.path = self.directory / "db.json"
        write(self.path, sample_document())
        self.store = SharedJsonStore(self.directory)

    def tearDown(self):
        self.temporary.cleanup()

    def test_normal_save_updates_provenance_and_backup(self):
        session = self.store.load("db.json")
        old_revision = session.loaded_revision
        session.data["wand_woods"][0]["notes"] = "new"
        outcome = self.store.save(session, "mage-maker")
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertTrue(outcome.saved)
        self.assertNotEqual(outcome.revision_id, old_revision)
        self.assertEqual(saved["_headmasters_scroll"]["last_modified_by"], "mage-maker")
        self.assertTrue(list((self.directory / "backups" / "db").glob("*.json")))

    def test_non_overlapping_changes_merge(self):
        first, second = self.store.load("db.json"), self.store.load("db.json")
        first.data["wand_woods"][0]["name"] = "English Oak"
        self.assertTrue(self.store.save(first, "dbm").saved)
        second.data["wand_woods"][0]["notes"] = "second editor"
        self.assertTrue(self.store.save(second, "mage-maker").saved)
        record = json.loads(self.path.read_text(encoding="utf-8"))["wand_woods"][0]
        self.assertEqual((record["name"], record["notes"]), ("English Oak", "second editor"))

    def test_same_field_returns_line_item_and_resolves(self):
        first, second = self.store.load("db.json"), self.store.load("db.json")
        first.data["wand_woods"][0]["notes"] = "disk version"
        self.store.save(first, "dbm")
        second.data["wand_woods"][0]["notes"] = "app version"
        outcome = self.store.save(second, "mage-maker")
        self.assertEqual(outcome.status, "conflicts")
        conflict = outcome.conflicts[0]
        self.assertEqual(
            (conflict.file, conflict.collection, conflict.record_id, conflict.field_path),
            ("db.json", "wand_woods", "wood-1", "notes"),
        )
        resolved = self.store.save_with_resolutions(
            second, {conflict.conflict_id: "disk"}, "mage-maker", outcome.disk_revision
        )
        self.assertTrue(resolved.saved)
        value = json.loads(self.path.read_text(encoding="utf-8"))["wand_woods"][0]["notes"]
        self.assertEqual(value, "disk version")

    def test_third_save_forces_fresh_review(self):
        one, two = self.store.load("db.json"), self.store.load("db.json")
        one.data["wand_woods"][0]["notes"] = "one"
        self.store.save(one, "dbm")
        two.data["wand_woods"][0]["notes"] = "two"
        initial = self.store.save(two, "mage-maker")
        three = self.store.load("db.json")
        three.data["wand_woods"][0]["notes"] = "three"
        self.store.save(three, "other-app")
        refreshed = self.store.save_with_resolutions(
            two, {initial.conflicts[0].conflict_id: "app"}, "mage-maker", initial.disk_revision
        )
        self.assertEqual(refreshed.status, "conflicts")
        self.assertNotEqual(refreshed.disk_revision, initial.disk_revision)

    def test_edit_wins_over_delete(self):
        deleting, editing = self.store.load("db.json"), self.store.load("db.json")
        deleting.data["wand_woods"] = []
        self.store.save(deleting, "dbm")
        editing.data["wand_woods"][0]["notes"] = "restored"
        self.assertTrue(self.store.save(editing, "mage-maker").saved)
        value = json.loads(self.path.read_text(encoding="utf-8"))["wand_woods"][0]["notes"]
        self.assertEqual(value, "restored")

    def test_additions_and_identical_deletions_merge(self):
        first, second = self.store.load("db.json"), self.store.load("db.json")
        first.data["wand_cores"].append({"record_id": "core-1", "name": "Phoenix"})
        second.data["wands"].append({"record_id": "wand-1", "name": "Practice wand"})
        self.assertTrue(self.store.save(first, "dbm").saved)
        self.assertTrue(self.store.save(second, "mage-maker").saved)
        current = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(current["wand_cores"][0]["record_id"], "core-1")
        self.assertEqual(current["wands"][0]["record_id"], "wand-1")
        one, two = self.store.load("db.json"), self.store.load("db.json")
        one.data["wand_woods"] = []
        two.data["wand_woods"] = []
        self.assertTrue(self.store.save(one, "dbm").saved)
        self.assertTrue(self.store.save(two, "mage-maker").saved)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["wand_woods"], [])

    def test_backup_failure_does_not_overwrite(self):
        session = self.store.load("db.json")
        session.data["wand_woods"][0]["name"] = "Changed"
        before = self.path.read_bytes()
        with patch("headmasters_scroll.store.shutil.copy2", side_effect=OSError("backup failed")):
            with self.assertRaises(OSError):
                self.store.save(session, "dbm")
        self.assertEqual(self.path.read_bytes(), before)

    def test_atomic_replace_failure_does_not_overwrite_and_cleans_temp(self):
        session = self.store.load("db.json")
        session.data["wand_woods"][0]["name"] = "Changed"
        before = self.path.read_bytes()
        with patch("headmasters_scroll.store.os.replace", side_effect=OSError("replace failed")):
            with self.assertRaises(OSError):
                self.store.save(session, "dbm")
        self.assertEqual(self.path.read_bytes(), before)
        self.assertFalse(list(self.directory.glob("*.tmp")))

    def test_malformed_json_and_validation_fail_without_overwrite(self):
        self.path.write_text("{broken", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            self.store.load("db.json")
        write(self.path, {"_headmasters_scroll": {}})
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(DataValidationError):
            self.store.load("db.json")
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_unavailable_lock(self):
        self.path.with_suffix(".json.lock").write_text("busy", encoding="utf-8")
        store = SharedJsonStore(self.directory, lock_timeout=0.01)
        session = store.load("db.json")
        with self.assertRaises(DataLockError):
            store.save(session, "dbm")


if __name__ == "__main__":
    unittest.main()
