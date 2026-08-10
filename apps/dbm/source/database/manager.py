import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from headmasters_scroll.store import SharedJsonStore
from database.backups import create_database_backup
from database.migrations import migrate_database
from database.validation import (
    validate_collection,
    validate_database,
    validate_record,
)


class JsonDatabase:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.data = {}
        self.dirty = False
        shared_directory = os.environ.get("HEADMASTERS_SCROLL_DATA_DIRECTORY")
        self.shared_store = None
        self.shared_session = None
        if shared_directory and self.database_path.resolve() == (Path(shared_directory) / "db.json").resolve():
            self.shared_store = SharedJsonStore()

    def load(self):
        if self.shared_store:
            self.shared_session = self.shared_store.load("db.json")
            loaded_data = deepcopy(self.shared_session.data)
        else:
            with self.database_path.open(
                "r",
                encoding="utf-8",
            ) as database_file:
                loaded_data = json.load(database_file)

        migrated_data = migrate_database(loaded_data)
        validate_database(migrated_data)

        self.data = migrated_data
        self.dirty = False

    def ensure_container(self, container_name, storage_type="collection"):
        if container_name in self.data:
            return

        if storage_type == "collection":
            self.data[container_name] = []
        elif storage_type == "object":
            self.data[container_name] = {}
        else:
            raise ValueError(f"Unknown storage type: {storage_type}")

        self.dirty = True

    def has_container(self, container_name):
        return container_name in self.data

    def get_container(self, container_name):
        if container_name not in self.data:
            raise KeyError(f"Unknown database container: {container_name}")

        return deepcopy(self.data[container_name])

    def get_collection(self, collection_name):
        if collection_name not in self.data:
            raise KeyError(f"Unknown database collection: {collection_name}")

        collection = self.data[collection_name]
        validate_collection(collection_name, collection)

        return deepcopy(collection)

    def create(self, collection_name, record):
        validate_record(record)
        collection = self.data.get(collection_name)
        validate_collection(collection_name, collection)

        new_record = deepcopy(record)
        new_record.setdefault("record_id", str(uuid.uuid4()))

        if self.read(collection_name, new_record["record_id"]) is not None:
            raise ValueError(
                f"Duplicate record ID: {new_record['record_id']}"
            )

        current_time = datetime.now(timezone.utc).isoformat()
        new_record.setdefault("last_updated", current_time)

        collection.append(new_record)
        self.dirty = True

        return deepcopy(new_record)

    def read(self, collection_name, record_id):
        collection = self.data.get(collection_name)
        validate_collection(collection_name, collection)

        for record in collection:
            if record.get("record_id") == record_id:
                return deepcopy(record)

        return None

    def update(self, collection_name, record_id, changes):
        validate_record(changes)
        collection = self.data.get(collection_name)
        validate_collection(collection_name, collection)

        if "record_id" in changes and changes["record_id"] != record_id:
            raise ValueError("A record ID cannot be changed")

        for record in collection:
            if record.get("record_id") != record_id:
                continue

            record.update(deepcopy(changes))
            record["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.dirty = True

            return deepcopy(record)

        raise KeyError(f"Unknown record ID: {record_id}")

    def delete(self, collection_name, record_id):
        collection = self.data.get(collection_name)
        validate_collection(collection_name, collection)

        for record_index, record in enumerate(collection):
            if record.get("record_id") != record_id:
                continue

            deleted_record = collection.pop(record_index)
            self.dirty = True

            return deepcopy(deleted_record)

        raise KeyError(f"Unknown record ID: {record_id}")

    def replace_object(self, object_name, object_value):
        if not isinstance(object_value, dict):
            raise TypeError("A database object must be a dictionary")

        if object_name not in self.data:
            raise KeyError(f"Unknown database object: {object_name}")

        self.data[object_name] = deepcopy(object_value)
        self.dirty = True

    def get_database_metadata(self):
        return deepcopy(self.data["_database"])

    def set_database_version(self, database_version):
        if not isinstance(database_version, str):
            raise TypeError("The database version must be text")

        cleaned_version = database_version.strip()

        if not cleaned_version:
            raise ValueError("The database version cannot be empty")

        self.data["_database"]["database_version"] = cleaned_version
        self.dirty = True

    def save(self, create_backup=False):
        self.data["_database"]["last_saved"] = datetime.now(
            timezone.utc
        ).isoformat()
        validate_database(self.data)
        if self.shared_store and self.shared_session:
            self.shared_session.data = deepcopy(self.data)
            outcome = self.shared_store.save(self.shared_session, "dbm")
            if not outcome.saved:
                raise RuntimeError(
                    "DBM found overlapping changes in the shared database. "
                    "Reload DBM before saving this record."
                )
            self.data = deepcopy(self.shared_session.data)
            self.dirty = False
            return
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        if create_backup:
            create_database_backup(self.database_path)

        temporary_path = self.database_path.with_suffix(".json.tmp")

        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as database_file:
            json.dump(
                self.data,
                database_file,
                ensure_ascii=False,
                indent=2,
            )
            database_file.write("\n")

        os.replace(temporary_path, self.database_path)
        self.dirty = False

    def discard_unsaved_changes(self):
        self.load()
