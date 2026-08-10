CURRENT_SCHEMA_VERSION = 1


def migrate_database(database_data):
    database_metadata = database_data.get("_database", {})
    schema_version = database_metadata.get("schema_version", 1)

    if schema_version > CURRENT_SCHEMA_VERSION:
        raise ValueError(
            "This database was created by a newer version of the application"
        )

    database_data["_database"] = {
        **database_metadata,
        "schema_version": CURRENT_SCHEMA_VERSION,
    }

    return database_data
