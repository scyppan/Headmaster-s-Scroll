"""Audit/apply compact stable references in DBM-owned records."""

from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from headmasters_scroll.store import SharedJsonStore  # noqa: E402


def build(database: dict) -> tuple[dict, dict]:
    migrated = deepcopy(database)
    removed_labels = 0
    unresolved = 0
    assignments = 0
    for school in migrated.get("schools", []) or []:
        for assignment in school.get("course_books", []) or []:
            if not isinstance(assignment, dict):
                continue
            assignments += 1
            record_id = str(assignment.get("record_id", "") or "").strip()
            if record_id:
                if "name" in assignment:
                    assignment.pop("name", None)
                    removed_labels += 1
            else:
                unresolved += 1
    return migrated, {
        "course_book_assignments": assignments,
        "copied_book_labels_removed": removed_labels,
        "unresolved_legacy_assignments_retained": unresolved,
    }


def verify(source: dict, migrated: dict) -> None:
    source_schools = source.get("schools", []) or []
    migrated_schools = migrated.get("schools", []) or []
    if len(source_schools) != len(migrated_schools):
        raise ValueError("School count changed")
    for before, after in zip(source_schools, migrated_schools, strict=False):
        before_assignments = before.get("course_books", []) or []
        after_assignments = after.get("course_books", []) or []
        if len(before_assignments) != len(after_assignments):
            raise ValueError("Course-book assignment count changed")
        for old, new in zip(before_assignments, after_assignments, strict=False):
            for field in ("year", "course", "record_id"):
                if old.get(field) != new.get(field):
                    raise ValueError("A course-book relationship changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    arguments = parser.parse_args()
    store = SharedJsonStore(ROOT / "data", lock_timeout=10.0)
    source = store.read_document("db.json")
    migrated, report = build(source)
    verify(source, migrated)
    print(json.dumps(report, indent=2))
    if not arguments.apply:
        print("Audit only; no files changed.")
        return
    session = store.load("db.json")
    migrated, _ = build(session.data)
    verify(session.base_data, migrated)
    session.data = migrated
    outcome = store.save(session, "database-normalizer")
    if not outcome.saved:
        raise RuntimeError("db.json changed during normalization; rerun the audit")
    print("Applied. The shared store created a recoverable timestamped backup.")


if __name__ == "__main__":
    main()
