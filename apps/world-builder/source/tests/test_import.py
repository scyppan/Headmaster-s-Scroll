import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parent.parent / "tools" / "import_formidable_csv.py"
SPEC = importlib.util.spec_from_file_location("import_formidable_csv", SCRIPT_PATH)
IMPORTER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(IMPORTER)


class ImportTests(unittest.TestCase):
    def test_duplicate_headers_are_numbered(self):
        self.assertEqual(
            ["Name", "Skill [1]", "Skill [2]"],
            IMPORTER.indexed_headers(["Name", "Skill", "Skill"]),
        )

    def test_repository_database_has_people_collection(self):
        database_path = Path(__file__).resolve().parent.parent / "data" / "mage_maker.json"
        database = json.loads(database_path.read_text(encoding="utf-8"))
        self.assertIn("people", database)
        self.assertIsInstance(database["people"], list)
        self.assertEqual(28, database["_database"]["schema_version"])
        self.assertEqual("0.28.0", database["_database"]["database_version"])


if __name__ == "__main__":
    unittest.main()
