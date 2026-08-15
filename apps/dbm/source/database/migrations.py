CURRENT_SCHEMA_VERSION = 4


def migrate_database(database_data):
    database_metadata = database_data.get("_database", {})
    schema_version = database_metadata.get("schema_version", 1)

    if schema_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This database was created by a newer version of the application"
        )

    if schema_version < 2:
        for book in database_data.get("books", []):
            if isinstance(book, dict) and not str(book.get("publication_date", "") or "").strip():
                book["publication_date"] = "1900-01-01"

    if schema_version < 3:
        from headmasters_scroll.region_interactions import ensure_gathering_catalog

        ensure_gathering_catalog(database_data)

    if schema_version < 4:
        from headmasters_scroll.region_interactions import ensure_gathering_catalog

        ensure_gathering_catalog(database_data)

    database_data["_database"] = {
        **database_metadata,
        "schema_version": CURRENT_SCHEMA_VERSION,
    }

    return database_data
