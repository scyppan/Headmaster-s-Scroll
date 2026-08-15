from __future__ import annotations

import json
from pathlib import Path

from apps.mapper.catalog_cache import MapperCatalogCache


def world_document() -> dict:
    return {
        "_headmasters_scroll": {"revision_id": "revision-one"},
        "locations": [
            {
                "record_id": "location-one",
                "name": "Hogwarts",
                "floors": [],
            }
        ],
        "maps": [
            {
                "record_id": "map-one",
                "name": "Ground Floor",
                "location_id": "location-one",
                "regions": [],
            }
        ],
        "people": [{"record_id": "person-one", "name": "Not cached"}],
        "events": [{"record_id": "event-one", "name": "Not cached"}],
    }


def write_world(path: Path, document: dict) -> None:
    path.write_text(json.dumps(document), encoding="utf-8")


def test_cache_contains_only_mapper_collections_and_is_current(tmp_path: Path):
    source = tmp_path / "world.json"
    cache_path = tmp_path / "runtime" / "catalog-index.json"
    document = world_document()
    write_world(source, document)

    cache = MapperCatalogCache(source, cache_path)
    cache.write(document)
    loaded = cache.load()

    assert loaded is not None
    assert loaded["revision_id"] == "revision-one"
    assert loaded["locations"][0]["record_id"] == "location-one"
    assert loaded["maps"][0]["record_id"] == "map-one"
    stored = json.loads(cache_path.read_text(encoding="utf-8"))
    assert "people" not in stored
    assert "events" not in stored


def test_cache_rejects_external_change_and_corruption(tmp_path: Path):
    source = tmp_path / "world.json"
    cache_path = tmp_path / "runtime" / "catalog-index.json"
    document = world_document()
    write_world(source, document)
    cache = MapperCatalogCache(source, cache_path)
    cache.write(document)
    assert cache.load() is not None

    document["locations"][0]["name"] = "Campus of Hogwarts"
    write_world(source, document)
    assert cache.load() is None

    cache_path.write_text("{broken", encoding="utf-8")
    assert cache.load() is None

