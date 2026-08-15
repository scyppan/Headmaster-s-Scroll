from __future__ import annotations

import argparse
import json
from pathlib import Path

from headmasters_scroll.catalog import enrich_catalog, validate_catalog
from headmasters_scroll.paths import DATA_DIRECTORY, PROJECT_ROOT
from headmasters_scroll.store import SharedJsonStore


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich books and rules with categories and tags")
    parser.add_argument("--apply", action="store_true", help="Save through the revision-aware store")
    parser.add_argument("--audit", type=Path, default=PROJECT_ROOT / "docs" / "catalog-migration-audit.json")
    args = parser.parse_args()

    store = SharedJsonStore(DATA_DIRECTORY)
    session = store.load("db.json")
    enriched, audit = enrich_catalog(session.data)
    validate_catalog(enriched)
    args.audit.parent.mkdir(parents=True, exist_ok=True)
    args.audit.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in audit.items() if not isinstance(value, list)}, indent=2))
    print(f"Book category changes: {len(audit['book_category_changes'])}")
    print(f"Tag changes: {len(audit['tag_changes'])}")
    if args.apply:
        session.data = enriched
        outcome = store.save(session, "catalog-migration")
        if outcome.status != "saved":
            raise RuntimeError(f"Catalog migration did not save: {outcome.status}")
        print(f"Saved revision {outcome.revision_id}")
    else:
        print("Dry run only; pass --apply to update db.json")


if __name__ == "__main__":
    main()
