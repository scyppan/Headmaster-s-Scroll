import json
from copy import deepcopy
from pathlib import Path


STOREROOM_ITEM_COLLECTIONS = (
    ("wands", "Wands"),
    ("holdable_items", "Holdable items"),
    ("accessories", "Accessories"),
    ("general_items", "General items"),
    ("creatures", "Creatures"),
    ("plants", "Plants"),
    ("potions", "Potions"),
    ("preparations", "Preparations"),
    ("foods_and_drinks", "Food and drink"),
    ("books", "Books"),
)


class GameDatabaseError(ValueError):
    pass


class GameDatabase:
    def __init__(self, database_directory):
        self.database_directory = Path(database_directory)
        self.database_path = None
        self.data = {}
        self.error = ""

    def load(self):
        if self.database_directory.is_file():
            database_files = [self.database_directory]
        else:
            self.database_directory.mkdir(parents=True, exist_ok=True)
            database_files = sorted(
                path
                for path in self.database_directory.iterdir()
                if path.is_file() and not path.name.startswith(".")
            )

        if not database_files:
            raise GameDatabaseError(
                f"No game database was found in {self.database_directory}."
            )

        if len(database_files) > 1:
            file_names = ", ".join(path.name for path in database_files)
            raise GameDatabaseError(
                "The data/dbm folder must contain exactly one game database "
                f"file. Found: {file_names}."
            )

        database_path = database_files[0]

        try:
            with database_path.open("r", encoding="utf-8-sig") as database_file:
                loaded_data = json.load(database_file)
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise GameDatabaseError(
                f"Cannot read the game database {database_path.name}: {error}"
            ) from error

        if not isinstance(loaded_data, dict):
            raise GameDatabaseError("The game database root must be a JSON object.")

        schools = loaded_data.get("schools")

        if not isinstance(schools, list):
            raise GameDatabaseError(
                "The game database must contain a schools collection."
            )

        for school in schools:
            if not isinstance(school, dict):
                raise GameDatabaseError("Every school must be a JSON object.")

            if not str(school.get("name", "") or "").strip():
                raise GameDatabaseError("Every school must have a name.")

        self.database_path = database_path
        self.data = loaded_data
        self.error = ""
        return self

    def mark_unavailable(self, error):
        self.database_path = None
        self.data = {}
        self.error = str(error or "The game database is unavailable.").strip()

    def collection(self, collection_name):
        collection = self.data.get(str(collection_name or ""), [])

        if not isinstance(collection, list):
            return []

        return deepcopy(collection)

    def schools(self):
        schools = self.collection("schools")
        schools.sort(key=self.school_sort_key)
        return schools

    def school_sort_key(self, school):
        return (
            str(school.get("name", "") or "").casefold(),
            str(school.get("location", "") or "").casefold(),
        )

    def school_names(self):
        return [
            str(school.get("name", "") or "").strip()
            for school in self.schools()
            if str(school.get("name", "") or "").strip()
        ]

    def storeroom_items(self):
        items = []

        for collection_name, category_label in (
            STOREROOM_ITEM_COLLECTIONS
        ):
            for record in self.collection(collection_name):
                record_id = str(
                    record.get("record_id", "") or ""
                ).strip()
                name = str(record.get("name", "") or "").strip()

                if not record_id or not name:
                    continue

                items.append(
                    {
                        "collection": collection_name,
                        "record_id": record_id,
                        "name": name,
                        "category": category_label,
                    }
                )

        return items

    def collection_counts(self):
        return {
            collection_name: len(collection)
            for collection_name, collection in self.data.items()
            if isinstance(collection, list)
        }

    @property
    def loaded(self):
        return self.database_path is not None and bool(self.data)
