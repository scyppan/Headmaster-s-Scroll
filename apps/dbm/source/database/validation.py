def validate_database(database_data):
    if not isinstance(database_data, dict):
        raise TypeError("The database root must be a JSON object")

    database_metadata = database_data.get("_database")

    if not isinstance(database_metadata, dict):
        raise TypeError("The database must contain a _database metadata object")

    schema_version = database_metadata.get("schema_version")

    if not isinstance(schema_version, int):
        raise TypeError("The database schema version must be an integer")


def validate_collection(collection_name, collection):
    if not isinstance(collection, list):
        raise TypeError(f"{collection_name} must be a JSON array")

    for record in collection:
        if not isinstance(record, dict):
            raise TypeError(
                f"Every record in {collection_name} must be a JSON object"
            )


def validate_record(record):
    if not isinstance(record, dict):
        raise TypeError("A database record must be a dictionary")
