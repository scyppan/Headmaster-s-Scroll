import json
import os
import shutil
import uuid
from collections import OrderedDict
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from headmasters_scroll.store import SharedJsonStore
from headmasters_scroll.board import ensure_board_collections, validate_world_board
from mage_maker.sections.development.models import (
    DEVELOPMENT_ASSIGNMENT_SETTING_KEY,
    calculate_school_start_year,
    migrated_development_plan,
    non_magical_development_plan,
    normalize_development_assignment_policy,
    normalize_development_plan,
    normalize_job_records,
    require_job_position_available,
)
from mage_maker.sections.development.school_years import (
    migrate_annual_progression_choices,
)
from mage_maker.sections.development.initial_bonuses import (
    allowance_sickles,
    normalize_initial_bonuses,
    starting_allowance_sickles,
)
from mage_maker.sections.development.characteristics import (
    normalize_characteristics,
)
from mage_maker.sections.development.initial_values import (
    legacy_developmental_environment,
    normalize_blood_status,
    normalize_developmental_environment,
    normalize_parental_values,
    require_blood_status_compatible,
    resolved_blood_status,
    resolved_developmental_environment,
)
from mage_maker.sections.names.history import migrate_legacy_name_details
from mage_maker.sections.family_tree.spouse_relationships import (
    merge_mate_ids,
    normalize_spouse_relationships,
    relationship_ids,
)
from mage_maker.sections.timeline.events import (
    automatic_child_timeline_event,
    normalize_timeline_events,
    synchronize_profile_timeline_events,
)
from mage_maker.sections.timeline.locations import ensure_life_start_events
from mage_maker.sections.events.models import (
    BIRTH_EVENT_TYPE,
    DEATH_EVENT_TYPES,
    GHOST_EVENT_TYPE,
    birth_event_baby_ids,
    birth_event_person_ids,
    death_event_person_ids,
    event_linked_person_ids,
    normalize_world_event,
    normalize_world_events,
    split_world_event_date,
    synchronize_birth_events_from_people,
    synchronize_people_death_records,
    world_event_date_is_on_or_after,
)
from mage_maker.sections.settings.mage_groups import (
    MAGE_GROUPS_SETTING_KEY,
    normalize_mage_group_id,
    normalize_mage_groups,
    require_mage_group_id,
)
from mage_maker.sections.settings.simulation import (
    DATABASE_DATE_SETTING_KEY,
    MORTALITY_TABLE_SETTING_KEY,
    normalize_database_date,
    normalize_mortality_table,
)
from mage_maker.sections.organizations.controller import (
    normalize_organization_job,
    normalize_organization_jobs,
    normalize_organization_events,
    normalize_organization_record,
    organization_job_date_tuple,
    organization_descendant_ids,
    synchronize_school_campus_locations,
)
from mage_maker.sections.locations.models import (
    normalize_location_record,
    synchronize_location_extinction_records,
)
from mage_maker.sections.ledger.models import (
    normalize_ledger_entries,
    reconcile_development_ledger_entries,
)
from mage_maker.sections.items.models import (
    ITEM_CATEGORIES_SETTING_KEY,
    ITEM_GROUPS_SETTING_KEY,
    normalize_item_categories,
    normalize_item_groups,
    normalize_item_record,
    normalize_item_records,
)
from mage_maker.sections.books.models import (
    normalize_book_reading,
    normalize_book_readings,
    normalize_book_record,
    normalize_book_records,
    synchronize_book_publication_events,
)
from mage_maker.core.world_index import (
    WorldIndexCache,
    people_list_summary,
    record_summary,
    read_indexed_record,
    scan_record_locations,
)
from mage_maker.core.reference_storage import (
    colored_tag_record_id,
    is_derived_timeline_event,
    normalize_event_references,
    timeline_event_to_world,
    world_event_to_timeline,
)


class JsonDatabase:
    DAILY_BACKUP_LIMIT = 10
    ROLLING_BACKUP_LIMIT = 10
    WEEKLY_BACKUP_LIMIT = 10

    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.backup_directory = self.database_path.parent / "backups"
        self.data = {}
        self.dirty = False
        self.revision = 0
        shared_directory = os.environ.get("HEADMASTERS_SCROLL_DATA_DIRECTORY")
        self.shared_store = None
        self.shared_session = None
        self.world_index = WorldIndexCache(self.database_path)
        self.preferences_path = (
            self.world_index.cache_path.parent / "preferences.json"
        )
        self.preferences = self.load_preferences()
        self.record_indexes = {}
        self.person_reference_index = {}
        self.event_person_reference_index = {}
        self.record_cache = OrderedDict()
        self.record_cache_limit = 96
        self.index_dirty = False
        self.fully_loaded = False
        self.change_subscribers = []
        if shared_directory and self.database_path.resolve() == (Path(shared_directory) / "world.json").resolve():
            # Honor the configured directory in the store itself.  Merely
            # using it for the equality check allowed custom/test data paths
            # to fall back to the project's canonical directory on save.
            self.shared_store = SharedJsonStore(Path(shared_directory))

    def load_preferences(self):
        try:
            with self.preferences_path.open("r", encoding="utf-8") as stream:
                values = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError):
            return {}
        return values if isinstance(values, dict) else {}

    def get_preference(self, key, default=None):
        return deepcopy(self.preferences.get(str(key or ""), default))

    def set_preference(self, key, value):
        normalized_key = str(key or "").strip()
        if not normalized_key:
            return False
        if self.preferences.get(normalized_key) == value:
            return False
        self.preferences[normalized_key] = deepcopy(value)
        self.preferences_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.preferences_path.with_name(
            f".{self.preferences_path.name}.{uuid.uuid4().hex}.tmp"
        )
        try:
            with temporary.open(
                "w",
                encoding="utf-8",
                newline="\n",
            ) as stream:
                json.dump(
                    self.preferences,
                    stream,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.preferences_path)
        finally:
            temporary.unlink(missing_ok=True)
        return True

    def load(self, rebuild_index=True):
        cached_index_is_current = self.world_index.load()
        if self.shared_store:
            self.shared_session = self.shared_store.load("world.json")
            # DataSession already owns an isolated working copy. A third
            # whole-world deepcopy here added memory and latency without
            # providing any additional isolation.
            loaded_data = self.shared_session.data
        else:
            with self.database_path.open("r", encoding="utf-8") as database_file:
                loaded_data = json.load(database_file)

        migrated = self.migrate_database(loaded_data)
        collections_added = self.ensure_application_collections(loaded_data)
        self.validate_database(loaded_data)
        self.data = loaded_data
        self.fully_loaded = True
        self.record_cache.clear()
        self.dirty = migrated or collections_added
        self.revision += 1
        self.rebuild_record_indexes()
        if not cached_index_is_current and rebuild_index:
            self.rebuild_world_index()
        elif not cached_index_is_current:
            self.index_dirty = True

    def load_index_only(self):
        """Open the disposable read index without decoding ``world.json``.

        This mode is deliberately read-only.  It lets the shell, People list,
        and one selected basic profile become interactive while a complete
        editable database loads on a worker thread.
        """
        if not self.world_index.load():
            return False
        payload = self.world_index.payload
        self.data = {
            "_database": {
                "schema_version": payload.get("schema_version"),
            },
            "_headmasters_scroll": {
                "revision_id": payload.get("revision_id", ""),
            },
            "_application_settings": deepcopy(
                payload.get("application_settings", {})
            ),
        }
        for collection_name in payload.get("counts", {}):
            self.data.setdefault(collection_name, [])
        self.shared_session = None
        self.record_indexes = {}
        self.record_cache.clear()
        self.dirty = False
        self.index_dirty = False
        self.fully_loaded = False
        self.revision += 1
        return True

    def adopt_loaded_database(self, loaded_database):
        """Adopt a worker-loaded database while retaining subscribers."""
        next_revision = self.revision + 1
        self.data = loaded_database.data
        self.shared_store = loaded_database.shared_store
        self.shared_session = loaded_database.shared_session
        self.world_index = loaded_database.world_index
        self.record_indexes = loaded_database.record_indexes
        self.person_reference_index = (
            loaded_database.person_reference_index
        )
        self.event_person_reference_index = (
            loaded_database.event_person_reference_index
        )
        self.index_dirty = loaded_database.index_dirty
        self.dirty = loaded_database.dirty
        self.fully_loaded = True
        self.record_cache.clear()
        self.revision = next_revision

    def rebuild_record_indexes(self):
        indexes = {}
        person_references = {}
        event_person_references = {}
        for collection_name, records in self.data.items():
            if not isinstance(records, list):
                continue
            collection_index = {}
            for record in records:
                if not isinstance(record, dict):
                    continue
                record_id = str(
                    record.get("record_id")
                    or record.get("event_id")
                    or record.get("reading_id")
                    or ""
                ).strip()
                if record_id:
                    collection_index[record_id] = record
                    if collection_name == "people":
                        referenced_ids = {
                            str(record.get("biological_mother_id", "") or "").strip(),
                            str(record.get("biological_father_id", "") or "").strip(),
                            *(
                                str(value or "").strip()
                                for value in record.get("mate_ids", []) or []
                            ),
                            *(
                                str(relationship.get("person_id", "") or "").strip()
                                for relationship in record.get(
                                    "spouse_relationships", []
                                ) or []
                                if isinstance(relationship, dict)
                            ),
                        }
                        referenced_ids.discard("")
                        for referenced_id in referenced_ids:
                            person_references.setdefault(
                                referenced_id, set()
                            ).add(record_id)
                    elif collection_name == "events":
                        for person_id in event_linked_person_ids(record):
                            event_person_references.setdefault(
                                person_id, set()
                            ).add(record_id)
            indexes[collection_name] = collection_index
        self.record_indexes = indexes
        self.person_reference_index = person_references
        self.event_person_reference_index = event_person_references
        self.record_cache.clear()
        return indexes

    def rebuild_world_index(self):
        try:
            record_ids_by_collection = {
                collection_name: [
                    (
                        str(
                            record.get("record_id")
                            or record.get("event_id")
                            or record.get("reading_id")
                            or ""
                        ).strip()
                        if isinstance(record, dict)
                        else ""
                    )
                    for record in records
                ]
                for collection_name, records in self.data.items()
                if isinstance(records, list)
            }
            locations = scan_record_locations(
                self.database_path,
                record_ids_by_collection,
            )
            self.world_index.build(self.data, locations)
            self.world_index.write()
            self.index_dirty = False
            return True
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            # A disposable cache must never prevent canonical data opening.
            self.world_index.build(self.data)
            self.index_dirty = True
            return False

    def list_people_list_summaries(self):
        if not self.index_dirty and self.world_index.is_current():
            return self.world_index.people_summaries()
        return [
            people_list_summary(person)
            for person in self.data.get("people", [])
            if isinstance(person, dict)
        ]

    def list_summaries(
        self,
        collection_name,
        query="",
        filters=None,
        page=0,
        page_size=100,
    ):
        if not self.index_dirty and self.world_index.is_current():
            summaries = self.world_index.summaries(collection_name)
        else:
            summaries = [
                people_list_summary(record)
                if collection_name == "people"
                else {
                    "record_id": str(
                        record.get("record_id")
                        or record.get("event_id")
                        or record.get("reading_id")
                        or ""
                    ),
                    "name": str(
                        record.get("name")
                        or record.get("title")
                        or record.get("displayed_name")
                        or ""
                    ),
                    "_search_text": " ".join(
                        str(value or "")
                        for value in record.values()
                        if isinstance(value, (str, int, float))
                    ).casefold(),
                }
                for record in self.data.get(collection_name, [])
                if isinstance(record, dict)
            ]
        normalized_query = str(query or "").strip().casefold()
        if normalized_query:
            summaries = [
                summary
                for summary in summaries
                if normalized_query in str(
                    summary.get("_search_text", "")
                ).casefold()
            ]
        for field, expected in (filters or {}).items():
            summaries = [
                summary
                for summary in summaries
                if summary.get(field) == expected
            ]
        start = max(0, int(page or 0)) * max(1, int(page_size or 100))
        return summaries[start : start + max(1, int(page_size or 100))]

    def get_summaries_by_ids(self, collection_name, record_ids):
        """Fetch compact summaries for a small stable-ID set.

        This deliberately avoids ``list_summaries`` because profile event
        rendering normally needs only the people linked to one mage's events,
        not every person in the world.
        """
        normalized_ids = list(
            dict.fromkeys(
                str(record_id or "").strip()
                for record_id in record_ids or ()
                if str(record_id or "").strip()
            )
        )
        if not normalized_ids:
            return []
        if not self.index_dirty and self.world_index.is_current():
            return self.world_index.summaries_by_ids(
                collection_name,
                normalized_ids,
            )
        records_by_id = self.record_indexes.get(collection_name, {})
        summaries = []
        for record_id in normalized_ids:
            record = records_by_id.get(record_id)
            if not isinstance(record, dict):
                continue
            summaries.append(
                people_list_summary(record)
                if collection_name == "people"
                else record_summary(collection_name, record)
            )
        return summaries

    def get_record(self, collection_name, record_id):
        normalized_id = str(record_id or "")
        cache_key = (str(collection_name or ""), normalized_id)
        cached = self.record_cache.get(cache_key)
        if cached is not None:
            self.record_cache.move_to_end(cache_key)
            record = deepcopy(cached)
            return (
                self._hydrate_person_record(record)
                if collection_name == "people"
                else record
            )
        # Once canonical data is loaded, its in-memory record is newer than
        # byte ranges taken from the last saved file (notably after a migration
        # or an unsaved edit).  Indexed byte reads are for index-first mode.
        if self.fully_loaded:
            record = self.record_indexes.get(collection_name, {}).get(
                normalized_id
            )
            if record is None:
                return None
            record = deepcopy(record)
            return (
                self._hydrate_person_record(record)
                if collection_name == "people"
                else record
            )
        if not self.index_dirty and self.world_index.is_current():
            indexed = read_indexed_record(
                self.database_path,
                self.world_index.payload,
                collection_name,
                record_id,
            )
            if indexed is not None:
                self.record_cache[cache_key] = indexed
                self.record_cache.move_to_end(cache_key)
                while len(self.record_cache) > self.record_cache_limit:
                    self.record_cache.popitem(last=False)
                record = deepcopy(indexed)
                return (
                    self._hydrate_person_record(record)
                    if collection_name == "people"
                    else record
                )
        return None

    def _hydrate_person_record(self, person):
        """Resolve selected-person references without bloating stored data."""
        if not isinstance(person, dict):
            return person
        if "tags" not in person:
            tags_by_id = self.record_indexes.get("person_tag_catalog", {})
            person["tags"] = []
            for tag_id in person.get("tag_ids", []) or []:
                tag = tags_by_id.get(tag_id)
                if tag is None and not self.fully_loaded:
                    tag = self.get_record("person_tag_catalog", tag_id)
                if not isinstance(tag, dict):
                    continue
                hydrated_tag = deepcopy(tag)
                hydrated_tag.pop("record_id", None)
                person["tags"].append(hydrated_tag)
        if "imported_fields" not in person:
            import_id = str(person.get("legacy_import_id", "") or "").strip()
            imported = self.record_indexes.get("legacy_person_imports", {}).get(
                import_id
            )
            if imported is None and import_id and not self.fully_loaded:
                imported = self.get_record("legacy_person_imports", import_id)
            person["imported_fields"] = deepcopy(
                imported.get("fields", {}) if isinstance(imported, dict) else {}
            )
        self._hydrate_person_book_references(person)
        if "timeline_events" in person:
            return person
        person_id = str(person.get("record_id", "") or "").strip()
        timeline = synchronize_profile_timeline_events(
            person,
            [],
            organizations=self.data.get("organizations", []),
        )
        overrides_by_id = person.get("event_overrides", {})
        if not isinstance(overrides_by_id, dict):
            overrides_by_id = {}
        for event_id in normalize_event_references(
            person.get("event_refs", [])
        ):
            event = self.record_indexes.get("events", {}).get(event_id)
            if event is None and not self.fully_loaded:
                event = self.get_record("events", event_id)
            hydrated = world_event_to_timeline(
                event,
                person_id,
                overrides_by_id.get(event_id),
            )
            if hydrated is not None:
                timeline.append(hydrated)
        person["timeline_events"] = normalize_timeline_events(timeline)
        return person

    def _hydrate_person_book_references(self, person):
        """Attach book labels to one loaded profile's ID-only references."""
        development_plan = person.get("development_plan")
        if not isinstance(development_plan, dict):
            return

        books_by_id = self.record_indexes.get("books", {})

        def display_reference(value):
            if not isinstance(value, dict):
                return value
            record_id = str(
                value.get("record_id") or value.get("book_id") or ""
            ).strip()
            if not record_id:
                return value
            book = books_by_id.get(record_id)
            if book is None and not self.fully_loaded:
                book = self.get_record("books", record_id)
            if not isinstance(book, dict):
                return value
            return {
                "record_id": record_id,
                "name": str(
                    book.get("title") or book.get("name") or "Missing book"
                ),
                "author": str(
                    book.get("author_name") or book.get("author") or ""
                ),
            }

        for section_name in ("school_years", "adult_years"):
            for record in development_plan.get(section_name, []) or []:
                if not isinstance(record, dict):
                    continue
                for field_name in ("assigned_books", "books"):
                    values = record.get(field_name)
                    if isinstance(values, list):
                        record[field_name] = [
                            display_reference(value) for value in values
                        ]

    def _store_person_timeline(self, person_id, timeline_events, references):
        """Store profile timeline edits in the canonical event collection."""
        normalized_person_id = str(person_id or "").strip()
        existing_refs = normalize_event_references(references)
        events_by_id = self.record_indexes.setdefault("events", {})
        owned_ids = {
            event_id
            for event_id in existing_refs
            if str(
                (events_by_id.get(event_id) or {}).get(
                    "profile_owner_person_id", ""
                )
                or ""
            ).strip()
            == normalized_person_id
        }
        retained_refs = [
            event_id for event_id in existing_refs if event_id not in owned_ids
        ]
        changed_ids = []
        for timeline_event in normalize_timeline_events(timeline_events):
            if is_derived_timeline_event(timeline_event):
                continue
            canonical = timeline_event_to_world(
                normalized_person_id,
                timeline_event,
            )
            event_id = canonical["record_id"]
            current = events_by_id.get(event_id)
            if current is None:
                self.data["events"].append(canonical)
                events_by_id[event_id] = canonical
                changed_ids.append(event_id)
            elif current != canonical:
                current.clear()
                current.update(canonical)
                changed_ids.append(event_id)
            if event_id not in retained_refs:
                retained_refs.append(event_id)

        if changed_ids:
            self.dirty = True
            self.index_dirty = True
            self.notify_changed("events", tuple(changed_ids))
        return retained_refs

    def _store_person_support_references(self, person_id, values):
        """Externalize selected-profile support data before canonical storage."""
        stored = deepcopy(values)
        if "tags" in stored:
            tag_ids = []
            catalog = self.record_indexes.setdefault("person_tag_catalog", {})
            for tag in stored.pop("tags", []) or []:
                if not isinstance(tag, dict):
                    continue
                text = str(tag.get("text", "") or "").strip()
                if not text:
                    continue
                record_id = colored_tag_record_id(tag)
                record = {
                    "record_id": record_id,
                    "text": text,
                    "background_color": str(
                        tag.get("background_color", "") or ""
                    ).strip(),
                }
                if record_id not in catalog:
                    self.data.setdefault("person_tag_catalog", []).append(record)
                    catalog[record_id] = record
                if record_id not in tag_ids:
                    tag_ids.append(record_id)
            stored["tag_ids"] = tag_ids
        if "imported_fields" in stored:
            imported_fields = stored.pop("imported_fields")
            import_id = f"legacy-import:{person_id}"
            imports = self.record_indexes.setdefault("legacy_person_imports", {})
            existing = imports.get(import_id)
            if isinstance(imported_fields, dict) and imported_fields:
                record = {
                    "record_id": import_id,
                    "person_id": person_id,
                    "fields": deepcopy(imported_fields),
                }
                if existing is None:
                    self.data.setdefault("legacy_person_imports", []).append(record)
                    imports[import_id] = record
                else:
                    existing.clear()
                    existing.update(record)
                stored["legacy_import_id"] = import_id
            else:
                if existing is not None:
                    self.data["legacy_person_imports"] = [
                        item
                        for item in self.data.get("legacy_person_imports", [])
                        if item.get("record_id") != import_id
                    ]
                    imports.pop(import_id, None)
                stored["legacy_import_id"] = ""
        return stored

    def get_linked_records(self, collection_name, record_id, relationship):
        if collection_name != "events":
            return []
        return [
            record
            for linked_id in self.linked_event_ids(relationship, record_id)
            if (
                record := self.get_record("events", linked_id)
            ) is not None
        ]

    def begin_edit(self, collection_name, record_id):
        record = self.get_record(collection_name, record_id)
        if record is None:
            raise KeyError(
                f"Unknown {collection_name} record_id: {record_id}"
            )
        return {
            "collection": str(collection_name),
            "record_id": str(record_id),
            "base_revision": self.revision,
            "base_record": record,
            "pending_changes": {},
        }

    def commit(self, edit_session):
        if not isinstance(edit_session, dict):
            raise TypeError("An edit session must be a dictionary.")
        collection_name = str(edit_session.get("collection", ""))
        record_id = str(edit_session.get("record_id", ""))
        base_record = edit_session.get("base_record", {})
        pending = edit_session.get("pending_changes", {})
        if not isinstance(base_record, dict) or not isinstance(pending, dict):
            raise TypeError("An edit session has invalid record changes.")
        current = self.get_record(collection_name, record_id)
        if current is None:
            raise KeyError(
                f"Unknown {collection_name} record_id: {record_id}"
            )
        conflicts = [
            field
            for field, app_value in pending.items()
            if current.get(field) != base_record.get(field)
            and app_value != current.get(field)
        ]
        if conflicts:
            raise RuntimeError(
                "Overlapping edits require review: "
                + ", ".join(sorted(conflicts))
            )
        if collection_name == "people":
            saved = self.update_person(record_id, pending)
        else:
            saved = self.update_record(collection_name, record_id, pending)
        self.save()
        return saved

    def linked_event_ids(self, relationship, record_id):
        if self.fully_loaded and str(relationship or "") == "people":
            return tuple(
                self.event_person_reference_index.get(
                    str(record_id or "").strip(),
                    (),
                )
            )
        return self.world_index.linked_event_ids(relationship, record_id)

    def subscribe(self, callback):
        if callable(callback) and callback not in self.change_subscribers:
            self.change_subscribers.append(callback)

    def notify_changed(self, collection_name, record_ids=()):
        normalized_ids = tuple(
            str(record_id or "").strip()
            for record_id in record_ids
            if str(record_id or "").strip()
        )
        for callback in tuple(self.change_subscribers):
            callback(str(collection_name or ""), normalized_ids, self.revision)

    def ensure_application_collections(self, database_data):
        changed = False

        for collection_name in (
            "locations",
            "organizations",
            "events",
            "items",
            "books",
            "book_readings",
            "maps",
            "board_groups",
            "named_creatures",
            "person_tag_catalog",
            "legacy_person_imports",
        ):
            if collection_name not in database_data:
                database_data[collection_name] = []
                changed = True

        if ensure_board_collections(database_data):
            changed = True

        normalized_items = normalize_item_records(
            database_data.get("items", [])
        )

        if database_data.get("items", []) != normalized_items:
            database_data["items"] = normalized_items
            changed = True

        normalized_books = normalize_book_records(
            database_data.get("books", [])
        )

        if database_data.get("books", []) != normalized_books:
            database_data["books"] = normalized_books
            changed = True

        normalized_book_readings = normalize_book_readings(
            database_data.get("book_readings", [])
        )

        if (
            database_data.get("book_readings", [])
            != normalized_book_readings
        ):
            database_data["book_readings"] = normalized_book_readings
            changed = True

        settings = database_data.get("_application_settings")

        if isinstance(settings, dict):
            normalized_categories = normalize_item_categories(
                settings.get(ITEM_CATEGORIES_SETTING_KEY)
            )

            if (
                settings.get(ITEM_CATEGORIES_SETTING_KEY)
                != normalized_categories
            ):
                settings[ITEM_CATEGORIES_SETTING_KEY] = (
                    normalized_categories
                )
                changed = True

            normalized_groups = normalize_item_groups(
                settings.get(ITEM_GROUPS_SETTING_KEY)
            )

            if (
                settings.get(ITEM_GROUPS_SETTING_KEY)
                != normalized_groups
            ):
                settings[ITEM_GROUPS_SETTING_KEY] = normalized_groups
                changed = True

        return changed

    def normalize_person_access_rules(self, database_data):
        people = [
            person
            for person in database_data.get("people", [])
            if isinstance(person, dict)
        ]
        parent_ids = {
            str(parent_id or "").strip()
            for child in people
            for parent_id in (
                child.get("biological_mother_id"),
                child.get("biological_father_id"),
            )
            if str(parent_id or "").strip()
        }
        non_magical_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in people
            if bool(person.get("non_magical"))
            and str(person.get("record_id", "") or "").strip()
        }
        changed = False

        for person in people:
            person_id = str(
                person.get("record_id", "") or ""
            ).strip()
            childlessness = bool(
                person.get("does_not_have_children", False)
            )

            if person_id in parent_ids:
                childlessness = False

            if person.get("does_not_have_children") is not childlessness:
                person["does_not_have_children"] = childlessness
                changed = True

            if not bool(person.get("non_magical")):
                continue

            cleaned_plan = non_magical_development_plan(
                person.get("development_plan")
            )

            if person.get("development_plan") != cleaned_plan:
                person["development_plan"] = cleaned_plan
                changed = True

            if str(person.get("school", "") or ""):
                person["school"] = ""
                changed = True

        normalized_events = []

        for event in database_data.get("events", []):
            if not isinstance(event, dict):
                continue

            normalized_event = normalize_world_events([event])[0]
            earned_ids = [
                person_id
                for person_id in normalized_event.get(
                    "eminence_person_ids",
                    [],
                )
                if person_id not in non_magical_ids
            ]
            normalized_event["eminence_person_ids"] = earned_ids
            normalized_event["eminence_skills"] = {
                person_id: skill
                for person_id, skill in normalized_event.get(
                    "eminence_skills",
                    {},
                ).items()
                if person_id in earned_ids
            }
            normalized_events.append(normalized_event)

        if database_data.get("events", []) != normalized_events:
            database_data["events"] = normalized_events
            changed = True

        normalized_organizations = []

        for organization in database_data.get("organizations", []):
            if not isinstance(organization, dict):
                continue

            normalized_organization = normalize_organization_record(
                organization
            )

            for event in normalized_organization.get("events", []):
                earned_ids = [
                    person_id
                    for person_id in event.get(
                        "eminence_person_ids",
                        [],
                    )
                    if person_id not in non_magical_ids
                ]
                event["eminence_person_ids"] = earned_ids
                event["eminence_skills"] = {
                    person_id: skill
                    for person_id, skill in event.get(
                        "eminence_skills",
                        {},
                    ).items()
                    if person_id in earned_ids
                }

            normalized_organizations.append(
                normalize_organization_record(
                    normalized_organization
                )
            )

        if (
            database_data.get("organizations", [])
            != normalized_organizations
        ):
            database_data["organizations"] = normalized_organizations
            changed = True

        return changed

    def migrate_database(self, database_data):
        if not isinstance(database_data, dict):
            return False

        metadata = database_data.get("_database", {})

        if not isinstance(metadata, dict):
            return False

        schema_version = metadata.get("schema_version")

        if not isinstance(schema_version, int) or schema_version > 39:
            return False

        if schema_version in (36, 37, 38):
            synchronize_book_publication_events(database_data)
            metadata["schema_version"] = 39
            metadata["database_version"] = "0.39.0"
            database_data["_database"] = metadata
            return True

        # Schema 37 is produced only by the explicit, backed-up reference
        # migration.  Ordinary startup must never delete embedded legacy data.
        if schema_version == 39:
            return False

        if schema_version == 36:
            stored_events = database_data.get("events", [])
            stored_organizations = database_data.get("organizations", [])
            stored_locations = database_data.get("locations", [])
            stored_books = database_data.get("books", [])
            stored_book_readings = database_data.get("book_readings", [])
            normalized_events = normalize_world_events(stored_events)
            repaired_organizations = []

            for organization in stored_organizations:
                repaired = deepcopy(organization)
                founding = normalize_organization_events(
                    repaired.get("events", [])
                )[0]

                if repaired.get("is_faction") and founding["year"] is None:
                    organization_id = str(
                        repaired.get("record_id", "") or ""
                    ).strip()
                    joined_event = next(
                        (
                            event
                            for event in normalized_events
                            if event.get("event_type") == "joined_faction"
                            and str(
                                event.get("organization_id", "") or ""
                            ).strip()
                            == organization_id
                        ),
                        None,
                    )
                    founding_date = str(
                        (joined_event or {}).get("date", "") or "1"
                    ).strip()
                    founding_year = int(
                        split_world_event_date(founding_date)[0]
                    )
                    repaired.setdefault("events", []).insert(
                        0,
                        {
                            "record_id": "organization-founding",
                            "event_type": "founding",
                            "title": "Founding",
                            "date": founding_date,
                            "time": "",
                            "year": founding_year,
                            "description": "",
                            "person_ids": [],
                            "item_ids": [],
                            "item_link_types": {},
                            "item_new_owners": {},
                            "eminence_person_ids": [],
                            "eminence_skills": {},
                        },
                    )

                repaired_organizations.append(repaired)

            normalized_organizations = [
                normalize_organization_record(organization)
                for organization in repaired_organizations
            ]
            normalized_locations = [
                normalize_location_record(location)
                for location in stored_locations
            ]
            normalized_books = normalize_book_records(stored_books)
            normalized_book_readings = normalize_book_readings(
                stored_book_readings
            )
            database_data["events"] = normalized_events
            database_data["organizations"] = normalized_organizations
            database_data["locations"] = normalized_locations
            database_data["books"] = normalized_books
            database_data["book_readings"] = normalized_book_readings
            death_event_changed = self.repair_orphan_death_events(
                database_data
            )
            campus_changed = synchronize_school_campus_locations(
                database_data
            )
            extinction_changed = (
                synchronize_location_extinction_records(
                    database_data,
                    create_legacy_events=False,
                )
            )
            people_changed = False
            people_changed = self.normalize_people_death_timeline_state(
                database_data
            )
            birth_changed = synchronize_birth_events_from_people(
                database_data
            )

            migrated = (
                stored_events != normalized_events
                or stored_organizations != normalized_organizations
                or stored_locations != normalized_locations
                or stored_books != normalized_books
                or stored_book_readings != normalized_book_readings
                or death_event_changed
                or campus_changed
                or extinction_changed
                or people_changed
                or birth_changed
            )

            return (
                self.normalize_person_access_rules(database_data)
                or migrated
            )

        migrated = False

        if schema_version < 2:
            removed_attribute_fields = (
                "generosity",
                "permissiveness",
                "wealth",
                "creativity",
                "equanimity",
                "charisma",
                "attractiveness",
                "strength",
                "agility",
                "intellect",
                "willpower",
                "fortitude",
            )

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                displayed_name = person.pop("name", "")
                maiden_name = person.pop("maiden_name", "")
                nickname_alias = person.pop("nickname_alias", "")
                person["displayed_name"] = displayed_name
                person["name_details"] = {
                    "name_history": "",
                    "aliases": nickname_alias,
                    "sobriquets": "",
                    "name_changes": (
                        f"Maiden name: {maiden_name}" if maiden_name else ""
                    ),
                    "notes": "",
                }
                person.pop("has_other_names", None)
                person.pop("image_url", None)

                for field_name in removed_attribute_fields:
                    person.pop(field_name, None)

                imported_fields = person.get("imported_fields")

                if isinstance(imported_fields, dict):
                    imported_fields.pop("Upload character image", None)

            schema_version = 2
            migrated = True

        if schema_version < 3:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["name_details"] = migrate_legacy_name_details(
                    person.get("name_details", {}),
                    person.get("displayed_name", ""),
                    person.get("record_id", ""),
                )

            migrated = True

        if schema_version < 4:
            people = [
                person
                for person in database_data.get("people", [])
                if isinstance(person, dict)
            ]
            ids_by_name = {
                str(person.get("displayed_name", "")).strip().casefold(): person.get(
                    "record_id", ""
                )
                for person in people
                if str(person.get("displayed_name", "")).strip()
            }
            inferred_mother_ids = set()

            for person in people:
                mother_name = str(person.get("biological_mother", "") or "").strip()
                mother_id = str(
                    person.get("biological_mother_id", "") or ""
                ).strip()

                if not mother_id and mother_name:
                    mother_id = str(ids_by_name.get(mother_name.casefold(), "") or "")

                if mother_id:
                    inferred_mother_ids.add(mother_id)

            for person in people:
                mother_name = str(person.pop("biological_mother", "") or "").strip()
                father_name = str(person.pop("biological_father", "") or "").strip()
                mother_id = str(
                    person.get("biological_mother_id", "") or ""
                ).strip()
                father_id = str(
                    person.get("biological_father_id", "") or ""
                ).strip()

                if not mother_id and mother_name:
                    mother_id = str(ids_by_name.get(mother_name.casefold(), "") or "")

                if not father_id and father_name:
                    father_id = str(ids_by_name.get(father_name.casefold(), "") or "")

                person["biological_mother_id"] = mother_id
                person["biological_father_id"] = father_id
                person["mate_ids"] = [
                    str(mate_id).strip()
                    for mate_id in person.get("mate_ids", [])
                    if str(mate_id).strip()
                ]
                person["non_magical"] = bool(
                    person.get("non_magical")
                    or person.get("muggle")
                    or person.get("squib")
                )
                person["can_give_birth"] = bool(
                    person.get("can_give_birth")
                    or person.get("record_id") in inferred_mother_ids
                )
                person.pop("blood_status", None)
                person.pop("muggle", None)
                person.pop("squib", None)

            migrated = True

        if schema_version < 5:
            people = [
                person
                for person in database_data.get("people", [])
                if isinstance(person, dict)
            ]
            people_by_id = {
                str(person.get("record_id", "")): person
                for person in people
                if str(person.get("record_id", ""))
            }

            for person in people:
                mother_id = str(
                    person.get("biological_mother_id", "") or ""
                ).strip()
                father_id = str(
                    person.get("biological_father_id", "") or ""
                ).strip()
                mother_status = str(
                    person.get("biological_mother_status", "unknown") or "unknown"
                ).strip().casefold()
                father_status = str(
                    person.get("biological_father_status", "unknown") or "unknown"
                ).strip().casefold()
                person["biological_mother_status"] = (
                    "person"
                    if mother_id
                    else "muggle" if mother_status == "muggle" else "unknown"
                )
                person["biological_father_status"] = (
                    "person"
                    if father_id
                    else "muggle" if father_status == "muggle" else "unknown"
                )
                person["timeline_events"] = normalize_timeline_events(
                    person.get("timeline_events", [])
                )
                person["mate_ids"] = [
                    str(mate_id).strip()
                    for mate_id in person.get("mate_ids", [])
                    if str(mate_id).strip()
                ]

                if not mother_id or not father_id or mother_id == father_id:
                    continue

                mother = people_by_id.get(mother_id)
                father = people_by_id.get(father_id)

                if mother is None or father is None:
                    continue

                mother_mates = mother.setdefault("mate_ids", [])
                father_mates = father.setdefault("mate_ids", [])

                if father_id not in mother_mates:
                    mother_mates.append(father_id)

                if mother_id not in father_mates:
                    father_mates.append(mother_id)

            migrated = True

        if schema_version < 6:
            people = [
                person
                for person in database_data.get("people", [])
                if isinstance(person, dict)
            ]
            children_by_parent = {}

            for child in people:
                for parent_id in (
                    child.get("biological_mother_id"),
                    child.get("biological_father_id"),
                ):
                    normalized_parent_id = str(parent_id or "").strip()

                    if normalized_parent_id:
                        children_by_parent.setdefault(
                            normalized_parent_id,
                            [],
                        ).append(child)

            for parent in people:
                parent_id = str(parent.get("record_id", "") or "")
                children = children_by_parent.get(parent_id, [])
                child_ids = {
                    str(child.get("record_id", "") or "")
                    for child in children
                }
                events = [
                    event
                    for event in normalize_timeline_events(
                        parent.get("timeline_events", [])
                    )
                    if not (
                        event.get("automatic_source") == "child_assignment"
                        and event.get("related_person_id") not in child_ids
                    )
                ]

                for child in children:
                    child_id = str(child.get("record_id", "") or "")
                    matching_index = None

                    for index, event in enumerate(events):
                        if (
                            event.get("automatic_source") == "child_assignment"
                            and event.get("related_person_id") == child_id
                        ):
                            matching_index = index
                            break

                    synchronized_event = automatic_child_timeline_event(
                        child,
                        events[matching_index]
                        if matching_index is not None
                        else None,
                    )

                    if matching_index is None:
                        events.append(synchronized_event)
                    else:
                        events[matching_index] = synchronized_event

                parent["timeline_events"] = normalize_timeline_events(events)

            schema_version = 6
            migrated = True

        if schema_version < 7:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                relationships = merge_mate_ids(
                    person.get("spouse_relationships", []),
                    person.get("mate_ids", []),
                )
                person["spouse_relationships"] = relationships
                person["mate_ids"] = relationship_ids(relationships)

            schema_version = 7
            migrated = True

        if schema_version < 8:
            for person in database_data.get("people", []):
                if isinstance(person, dict):
                    person.pop("sex", None)

            schema_version = 8
            migrated = True

        if schema_version < 9:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["timeline_events"] = ensure_life_start_events(person)

            schema_version = 9
            migrated = True

        if schema_version < 10:
            existing_settings = database_data.get(
                "_application_settings",
                {},
            )
            settings = (
                dict(existing_settings)
                if isinstance(existing_settings, dict)
                else {}
            )
            assignment_policy = normalize_development_assignment_policy(
                settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
            )
            settings[DEVELOPMENT_ASSIGNMENT_SETTING_KEY] = (
                assignment_policy
            )
            database_data["_application_settings"] = settings

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = migrated_development_plan(
                    person.get("development_plan"),
                    assignment_policy,
                    person.get("record_id"),
                )

            schema_version = 10
            migrated = True

        if schema_version < 11:
            settings = database_data.get(
                "_application_settings",
                {},
            )
            assignment_policy = normalize_development_assignment_policy(
                settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
                if isinstance(settings, dict)
                else None
            )

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = migrated_development_plan(
                    person.get("development_plan"),
                    assignment_policy,
                    person.get("record_id"),
                )

            schema_version = 11
            migrated = True

        if schema_version < 12:
            existing_settings = database_data.get(
                "_application_settings",
                {},
            )
            settings = (
                dict(existing_settings)
                if isinstance(existing_settings, dict)
                else {}
            )
            mage_groups = normalize_mage_groups(
                settings.get(MAGE_GROUPS_SETTING_KEY)
            )
            settings[MAGE_GROUPS_SETTING_KEY] = mage_groups
            database_data["_application_settings"] = settings

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["mage_group_id"] = normalize_mage_group_id(
                    person.get("mage_group_id"),
                    mage_groups,
                )

            schema_version = 12
            migrated = True

        if schema_version < 13:
            people = [
                person
                for person in database_data.get("people", [])
                if isinstance(person, dict)
            ]

            for person in people:
                legacy_blood_status = person.get("blood_status")
                person["developmental_environment"] = (
                    person.get("developmental_environment")
                    or legacy_developmental_environment(
                        legacy_blood_status
                    )
                )
                person["blood_status"] = resolved_blood_status(
                    person,
                    people,
                )

            schema_version = 13
            migrated = True

        if schema_version < 14:
            people = [
                person
                for person in database_data.get("people", [])
                if isinstance(person, dict)
            ]

            for person in people:
                legacy_blood_status = person.get("blood_status")
                person["blood_status"] = resolved_blood_status(
                    person,
                    people,
                )
                person["developmental_environment"] = (
                    normalize_developmental_environment(
                        (
                            person.get("developmental_environment")
                            or legacy_developmental_environment(
                                legacy_blood_status
                            )
                        ),
                        person["blood_status"],
                    )
                )
                person["parental_values"] = normalize_parental_values(
                    person.get("parental_values")
                )

            schema_version = 14
            migrated = True

        if schema_version < 15:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["initial_bonuses"] = normalize_initial_bonuses(
                    person.get("initial_bonuses")
                )

            schema_version = 15
            migrated = True

        if schema_version < 16:
            settings = database_data.get(
                "_application_settings",
                {},
            )
            assignment_policy = normalize_development_assignment_policy(
                settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
                if isinstance(settings, dict)
                else None
            )

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = migrated_development_plan(
                    person.get("development_plan"),
                    assignment_policy,
                    person.get("record_id"),
                )
                person["characteristics"] = (
                    normalize_characteristics(
                        person.get("characteristics")
                    )
                )

            schema_version = 16
            migrated = True

        if schema_version < 17:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = (
                    normalize_development_plan(
                        person.get("development_plan"),
                        default_schema="Scattershot",
                    )
                )

            schema_version = 17
            migrated = True

        if schema_version < 18:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = (
                    normalize_development_plan(
                        person.get("development_plan"),
                        default_schema="Scattershot",
                    )
                )

            schema_version = 18
            migrated = True

        if schema_version < 19:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = (
                    normalize_development_plan(
                        person.get("development_plan"),
                        default_schema="Scattershot",
                    )
                )

            for organization in database_data.get(
                "organizations",
                [],
            ):
                if not isinstance(organization, dict):
                    continue

                organization["events"] = (
                    normalize_organization_events(
                        organization.get("events", [])
                    )
                )

            schema_version = 19
            migrated = True

        if schema_version < 20:
            settings = database_data.setdefault(
                "_application_settings",
                {},
            )
            settings[DATABASE_DATE_SETTING_KEY] = (
                normalize_database_date(
                    settings.get(DATABASE_DATE_SETTING_KEY)
                )
            )
            settings[MORTALITY_TABLE_SETTING_KEY] = (
                normalize_mortality_table(
                    settings.get(MORTALITY_TABLE_SETTING_KEY)
                )
            )

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                development_plan = (
                    migrate_annual_progression_choices(
                        person.get("development_plan"),
                        person.get("characteristics"),
                        person.get("record_id"),
                    )
                )
                initial_bonuses = normalize_initial_bonuses(
                    person.get("initial_bonuses")
                )
                selected_traits = (
                    initial_bonuses["traits"]
                    if initial_bonuses is not None
                    else []
                )
                development_plan["ledger_entries"] = (
                    reconcile_development_ledger_entries(
                        development_plan.get("ledger_entries", []),
                        development_plan.get("school_years", []),
                        development_plan.get("adult_years", []),
                        allowance_sickles(
                            person.get("parental_values"),
                            selected_traits,
                        ),
                        starting_allowance_sickles(
                            person.get("parental_values")
                        ),
                        calculate_school_start_year(
                            person.get("birth_year"),
                            person.get("birth_month"),
                            person.get("birth_day"),
                        ),
                    )
                )
                person["development_plan"] = (
                    normalize_development_plan(development_plan)
                )

            schema_version = 20
            migrated = True

        if schema_version < 21:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                development_plan = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )
                initial_bonuses = normalize_initial_bonuses(
                    person.get("initial_bonuses")
                )
                selected_traits = (
                    initial_bonuses["traits"]
                    if initial_bonuses is not None
                    else []
                )
                development_plan["ledger_entries"] = (
                    reconcile_development_ledger_entries(
                        development_plan.get("ledger_entries", []),
                        development_plan.get("school_years", []),
                        development_plan.get("adult_years", []),
                        allowance_sickles(
                            person.get("parental_values"),
                            selected_traits,
                        ),
                        starting_allowance_sickles(
                            person.get("parental_values")
                        ),
                        calculate_school_start_year(
                            person.get("birth_year"),
                            person.get("birth_month"),
                            person.get("birth_day"),
                        ),
                    )
                )
                person["development_plan"] = normalize_development_plan(
                    development_plan
                )

            schema_version = 21
            migrated = True

        if schema_version < 22:
            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["initial_bonuses"] = normalize_initial_bonuses(
                    person.get("initial_bonuses")
                )
                person["development_plan"] = (
                    normalize_development_plan(
                        person.get("development_plan"),
                        default_schema="Scattershot",
                    )
                )

            schema_version = 22
            migrated = True

        if schema_version < 23:
            normalized_organizations = []

            for organization in database_data.get(
                "organizations",
                [],
            ):
                if not isinstance(organization, dict):
                    continue

                normalized_organizations.append(
                    normalize_organization_record(organization)
                )

            database_data["organizations"] = (
                normalized_organizations
            )
            organizations_by_id = {
                str(
                    organization.get("record_id", "") or ""
                ): organization
                for organization in normalized_organizations
                if str(
                    organization.get("record_id", "") or ""
                )
            }
            organizations_by_name = {
                str(
                    organization.get("name", "") or ""
                ).strip().casefold(): organization
                for organization in normalized_organizations
                if str(
                    organization.get("name", "") or ""
                ).strip()
            }

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                plan = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )

                for adult_year in plan.get(
                    "adult_years",
                    [],
                ):
                    assignments = normalize_job_records(
                        adult_year.get("jobs", [])
                    )

                    for assignment in assignments:
                        organization = organizations_by_id.get(
                            assignment["organization_id"]
                        )

                        if organization is None:
                            organization = organizations_by_name.get(
                                assignment[
                                    "organization_name"
                                ].casefold()
                            )

                        if organization is None:
                            continue

                        assignment["organization_id"] = str(
                            organization.get("record_id", "")
                            or ""
                        )
                        assignment["organization_name"] = str(
                            organization.get("name", "") or ""
                        )

                        if assignment["organization_job_id"]:
                            continue

                        matching_job = next(
                            (
                                organization_job
                                for organization_job in (
                                    organization.get("jobs", [])
                                )
                                if organization_job["title"].casefold()
                                == assignment["title"].casefold()
                                and organization_job[
                                    "opened_year"
                                ]
                                <= assignment["start_year"]
                            ),
                            None,
                        )

                        if matching_job is None:
                            matching_job = (
                                normalize_organization_job(
                                    {
                                        "organization_id": (
                                            assignment[
                                                "organization_id"
                                            ]
                                        ),
                                        "title": assignment["title"],
                                        "opened_year": assignment[
                                            "start_year"
                                        ],
                                    }
                                )
                            )
                            organization["jobs"] = (
                                normalize_organization_jobs(
                                    [
                                        *organization.get(
                                            "jobs",
                                            [],
                                        ),
                                        matching_job,
                                    ]
                                )
                            )

                        assignment["organization_job_id"] = (
                            matching_job["record_id"]
                        )

                    adult_year["jobs"] = normalize_job_records(
                        assignments
                    )

                person["development_plan"] = (
                    normalize_development_plan(plan)
                )

            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in normalized_organizations
            ]
            schema_version = 23
            migrated = True

        if schema_version < 24:
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                plan = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )
                plan["ledger_entries"] = normalize_ledger_entries(
                    plan.get("ledger_entries", [])
                )
                person["development_plan"] = (
                    normalize_development_plan(plan)
                )

            schema_version = 24
            migrated = True

        if schema_version < 25:
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]
            schema_version = 25
            migrated = True

        if schema_version < 26:
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["development_plan"] = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )

            schema_version = 26
            migrated = True

        if schema_version < 27:
            for person in database_data.get("people", []):
                if isinstance(person, dict):
                    person["unfinished"] = bool(
                        person.get("unfinished", False)
                    )

            schema_version = 27
            migrated = True

        if schema_version < 28:
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]
            schema_version = 28
            migrated = True

        if schema_version < 29:
            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                stored_plan = person.get("development_plan")
                has_stored_initialization_flag = (
                    isinstance(stored_plan, dict)
                    and "blood_status_initialized" in stored_plan
                )
                plan = normalize_development_plan(
                    stored_plan,
                    default_schema="Scattershot",
                )
                initialized = (
                    bool(stored_plan.get("blood_status_initialized"))
                    if has_stored_initialization_flag
                    else any(
                        person.get(field_name) not in (None, "")
                        for field_name in (
                            "parental_values",
                            "initial_bonuses",
                            "characteristics",
                        )
                    )
                    or bool(plan.get("school_started"))
                    or bool(plan.get("academic_years_advanced"))
                    or bool(plan.get("school_years"))
                    or bool(plan.get("adult_years"))
                )
                plan["blood_status_initialized"] = initialized
                person["development_plan"] = (
                    normalize_development_plan(plan)
                )

            schema_version = 29
            migrated = True

        if schema_version < 30:
            self.normalize_person_access_rules(database_data)
            schema_version = 30
            migrated = True

        if schema_version < 31:
            legacy_job_salaries = {}

            for organization in database_data.get(
                "organizations",
                [],
            ):
                if not isinstance(organization, dict):
                    continue

                for organization_job in organization.get("jobs", []):
                    if not isinstance(organization_job, dict):
                        continue

                    organization_job_id = str(
                        organization_job.get("record_id", "") or ""
                    ).strip()
                    salary = organization_job.get("salary")

                    if organization_job_id and salary not in (None, ""):
                        legacy_job_salaries[organization_job_id] = deepcopy(
                            salary
                        )

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                development_plan = person.get("development_plan")

                if not isinstance(development_plan, dict):
                    continue

                for adult_year in development_plan.get(
                    "adult_years",
                    [],
                ):
                    if not isinstance(adult_year, dict):
                        continue

                    for assignment in adult_year.get("jobs", []):
                        if not isinstance(assignment, dict):
                            continue

                        organization_job_id = str(
                            assignment.get(
                                "organization_job_id",
                                "",
                            )
                            or ""
                        ).strip()

                        if (
                            assignment.get("salary") in (None, "")
                            and organization_job_id in legacy_job_salaries
                        ):
                            assignment["salary"] = deepcopy(
                                legacy_job_salaries[organization_job_id]
                            )

            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["timeline_events"] = normalize_timeline_events(
                    person.get("timeline_events", [])
                )
                person["development_plan"] = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )

            schema_version = 31
            migrated = True

        if schema_version < 32:
            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]

            for person in database_data.get("people", []):
                if not isinstance(person, dict):
                    continue

                person["timeline_events"] = normalize_timeline_events(
                    person.get("timeline_events", [])
                )
                person["development_plan"] = normalize_development_plan(
                    person.get("development_plan"),
                    default_schema="Scattershot",
                )

            schema_version = 32
            migrated = True

        if schema_version < 33:
            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]
            database_data["locations"] = [
                normalize_location_record(location)
                for location in database_data.get("locations", [])
                if isinstance(location, dict)
            ]
            synchronize_location_extinction_records(
                database_data,
                create_legacy_events=True,
            )
            synchronize_school_campus_locations(database_data)
            database_data["locations"] = [
                normalize_location_record(location)
                for location in database_data.get("locations", [])
                if isinstance(location, dict)
            ]
            schema_version = 33
            migrated = True

        if schema_version < 34:
            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get(
                    "organizations",
                    [],
                )
                if isinstance(organization, dict)
            ]
            database_data["locations"] = [
                normalize_location_record(location)
                for location in database_data.get("locations", [])
                if isinstance(location, dict)
            ]
            synchronize_school_campus_locations(database_data)
            synchronize_location_extinction_records(
                database_data,
                create_legacy_events=False,
            )
            self.repair_orphan_death_events(database_data)
            self.normalize_people_death_timeline_state(database_data)
            self.normalize_person_access_rules(database_data)
            schema_version = 34
            migrated = True

        if schema_version < 35:
            database_data["events"] = normalize_world_events(
                database_data.get("events", [])
            )
            synchronize_birth_events_from_people(database_data)
            schema_version = 35
            migrated = True

        if schema_version < 36:
            database_data["organizations"] = [
                normalize_organization_record(organization)
                for organization in database_data.get("organizations", [])
                if isinstance(organization, dict)
            ]
            database_data["books"] = normalize_book_records(
                database_data.get("books", [])
            )
            database_data["book_readings"] = normalize_book_readings(
                database_data.get("book_readings", [])
            )
            schema_version = 36
            migrated = True

        synchronize_book_publication_events(database_data)
        metadata["schema_version"] = 39
        metadata["database_version"] = "0.39.0"
        database_data["_database"] = metadata

        return migrated

    def repair_orphan_death_events(self, database_data):
        known_person_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in database_data.get("people", [])
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        stored_events = database_data.get("events", [])
        repaired_events = []

        for stored_event in stored_events:
            event = normalize_world_event(stored_event)

            if event.get("event_type") != "died":
                repaired_events.append(event)
                continue

            valid_person_ids = [
                person_id
                for person_id in event.get("person_ids", [])
                if person_id in known_person_ids
            ]

            if len(valid_person_ids) == 1:
                event["person_ids"] = valid_person_ids
                repaired_events.append(normalize_world_event(event))
                continue

            event["event_type"] = "other"
            event["person_ids"] = valid_person_ids
            event["eminence_person_ids"] = []
            event["eminence_skills"] = {}
            repaired_events.append(normalize_world_event(event))

        normalized_events = normalize_world_events(repaired_events)
        changed = stored_events != normalized_events

        if changed:
            database_data["events"] = normalized_events

        return changed

    def normalize_people_death_timeline_state(self, database_data):
        shared_death_person_ids = {
            person_id
            for event in database_data.get("events", [])
            for person_id in death_event_person_ids(event)
        }
        changed = False

        for person in database_data.get("people", []):
            if not isinstance(person, dict):
                continue

            person_id = str(person.get("record_id", "") or "").strip()
            normalized_timeline = synchronize_profile_timeline_events(
                person,
                normalize_timeline_events(
                    person.get("timeline_events", [])
                ),
                create_death_event=(
                    person_id not in shared_death_person_ids
                ),
                organizations=database_data.get(
                    "organizations",
                    [],
                ),
            )

            if person.get("timeline_events", []) != normalized_timeline:
                person["timeline_events"] = normalized_timeline
                changed = True

        return (
            synchronize_people_death_records(database_data)
            or changed
        )

    def validate_database(self, database_data):
        if not isinstance(database_data, dict):
            raise TypeError("The database root must be a JSON object.")

        validate_world_board(database_data)

        if not isinstance(database_data.get("people"), list):
            raise TypeError("The database must contain a people collection.")

        for collection_name in (
            "locations",
            "organizations",
            "events",
            "items",
            "books",
            "book_readings",
            "named_creatures",
            "person_tag_catalog",
            "legacy_person_imports",
        ):
            if not isinstance(database_data.get(collection_name), list):
                raise TypeError(
                    f"The database must contain a {collection_name} collection."
                )

        metadata = database_data.get("_database")

        if not isinstance(metadata, dict):
            raise TypeError("The database must contain _database metadata.")

        if not isinstance(metadata.get("schema_version"), int):
            raise TypeError("The database schema version must be a number.")

        settings = database_data.get("_application_settings")

        if not isinstance(settings, dict):
            raise TypeError(
                "The database must contain application settings."
            )

        if MAGE_GROUPS_SETTING_KEY not in settings:
            raise ValueError(
                "The application settings must contain mage groups."
            )

        normalized_item_categories = normalize_item_categories(
            settings.get(ITEM_CATEGORIES_SETTING_KEY)
        )

        if (
            settings.get(ITEM_CATEGORIES_SETTING_KEY)
            != normalized_item_categories
        ):
            raise ValueError(
                "Item categories must use canonical stored values."
            )

        normalized_database_date = normalize_database_date(
            settings.get(DATABASE_DATE_SETTING_KEY)
        )

        if (
            settings.get(DATABASE_DATE_SETTING_KEY)
            != normalized_database_date
        ):
            raise ValueError(
                "Database date must use its canonical stored value."
            )

        normalized_mortality_table = normalize_mortality_table(
            settings.get(MORTALITY_TABLE_SETTING_KEY)
        )

        if (
            settings.get(MORTALITY_TABLE_SETTING_KEY)
            != normalized_mortality_table
        ):
            raise ValueError(
                "Mortality table must use canonical stored values."
            )

        mage_groups = normalize_mage_groups(
            settings[MAGE_GROUPS_SETTING_KEY]
        )
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in database_data["people"]
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        parent_ids = {
            str(parent_id or "").strip()
            for person in database_data["people"]
            if isinstance(person, dict)
            for parent_id in (
                person.get("biological_mother_id"),
                person.get("biological_father_id"),
            )
            if str(parent_id or "").strip()
        }
        non_magical_person_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in database_data["people"]
            if isinstance(person, dict)
            and bool(person.get("non_magical"))
            and str(person.get("record_id", "") or "").strip()
        }
        seen_ids = set()
        seen_displayed_names = set()

        for person in database_data["people"]:
            if not isinstance(person, dict):
                raise TypeError("Every person must be a JSON object.")

            record_id = person.get("record_id")

            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError("Every person must have a record_id.")

            if record_id in seen_ids:
                raise ValueError(f"Duplicate person record_id: {record_id}")

            seen_ids.add(record_id)

            displayed_name = str(person.get("displayed_name", "")).strip()

            if not displayed_name:
                raise ValueError("Every person must have a displayed name.")

            normalized_name = displayed_name.casefold()

            if normalized_name in seen_displayed_names:
                raise ValueError(f"Duplicate displayed name: {displayed_name}")

            seen_displayed_names.add(normalized_name)

            if not isinstance(person.get("unfinished"), bool):
                raise TypeError(
                    "Every person's unfinished flag must be true or false."
                )

            if not isinstance(
                person.get("does_not_have_children"),
                bool,
            ):
                raise TypeError(
                    "Every person's Does not have children flag must be "
                    "true or false."
                )

            if (
                person.get("does_not_have_children")
                and record_id in parent_ids
            ):
                raise ValueError(
                    "A person marked Does not have children cannot be "
                    "linked as a parent."
                )

            require_mage_group_id(
                person.get("mage_group_id"),
                mage_groups,
            )
            normalized_blood_status = normalize_blood_status(
                person.get("blood_status")
            )

            if person.get("blood_status") != normalized_blood_status:
                raise ValueError(
                    "Blood status must use its canonical stored value."
                )

            normalized_environment = (
                normalize_developmental_environment(
                    person.get("developmental_environment"),
                    normalized_blood_status,
                )
            )

            if (
                person.get("developmental_environment", "")
                != normalized_environment
            ):
                raise ValueError(
                    "Developmental environment must use its canonical "
                    "stored value."
                )

            normalized_parental_values = normalize_parental_values(
                person.get("parental_values")
            )

            if (
                person.get("parental_values")
                != normalized_parental_values
            ):
                raise ValueError(
                    "Parental values must use their canonical stored "
                    "structure."
                )

            normalized_initial_bonuses = normalize_initial_bonuses(
                person.get("initial_bonuses")
            )

            if (
                person.get("initial_bonuses")
                != normalized_initial_bonuses
            ):
                raise ValueError(
                    "Initial bonuses must use their canonical stored "
                    "structure."
                )

            normalized_characteristics = normalize_characteristics(
                person.get("characteristics")
            )

            if (
                person.get("characteristics")
                != normalized_characteristics
            ):
                raise ValueError(
                    "Characteristics must use their canonical stored "
                    "structure."
                )

            require_blood_status_compatible(
                person,
                people_by_id,
            )

            for field_name in ("biological_mother_id", "biological_father_id"):
                parent_id = person.get(field_name, "")

                if not isinstance(parent_id, str):
                    raise TypeError(f"{field_name} must be a person identifier.")

            for field_name in (
                "biological_mother_status",
                "biological_father_status",
            ):
                if person.get(field_name, "unknown") not in (
                    "unknown",
                    "muggle",
                    "person",
                ):
                    raise ValueError(
                        f"{field_name} must be unknown, muggle, or person."
                    )

            mate_ids = person.get("mate_ids", [])

            if not isinstance(mate_ids, list) or any(
                not isinstance(mate_id, str) for mate_id in mate_ids
            ):
                raise TypeError("mate_ids must be a list of person identifiers.")

            spouse_relationships = normalize_spouse_relationships(
                person.get("spouse_relationships", [])
            )

            if relationship_ids(spouse_relationships) != mate_ids:
                raise ValueError(
                    "mate_ids must match the spouse relationship identifiers."
                )

            normalized_plan = normalize_development_plan(
                person.get("development_plan")
            )

            if person.get("non_magical"):
                if str(person.get("school", "") or ""):
                    raise ValueError(
                        "A non-magical person cannot attend a wizarding "
                        "school."
                    )

                if normalized_plan != non_magical_development_plan(
                    normalized_plan
                ):
                    raise ValueError(
                        "A non-magical person's Development record may "
                        "contain jobs only."
                    )

            normalized_timeline = normalize_timeline_events(
                person.get("timeline_events", [])
            )

            for timeline_event in normalized_timeline:
                if (
                    timeline_event.get("event_type")
                    in DEATH_EVENT_TYPES
                    and not str(
                        timeline_event.get("date", "") or ""
                    ).strip()
                ):
                    raise ValueError(
                        "Every Death or Murder event must have a year."
                    )

        for collection_name in (
            "locations",
            "organizations",
            "events",
            "items",
            "books",
            "book_readings",
        ):
            seen_record_ids = set()

            for record in database_data[collection_name]:
                if not isinstance(record, dict):
                    raise TypeError(
                        f"Every record in {collection_name} must be a JSON object."
                    )

                record_id = str(record.get("record_id", "") or "").strip()

                if not record_id:
                    raise ValueError(
                        f"Every record in {collection_name} must have a record_id."
                    )

                if record_id in seen_record_ids:
                    raise ValueError(
                        f"Duplicate {collection_name} record_id: {record_id}"
                    )

                seen_record_ids.add(record_id)

                if collection_name == "organizations":
                    normalized_organization = (
                        normalize_organization_record(record)
                    )

                    if record != normalized_organization:
                        raise ValueError(
                            "Organizations must use their canonical "
                            "stored structure."
                        )

                if collection_name == "locations":
                    normalized_location = normalize_location_record(record)

                    if record != normalized_location:
                        raise ValueError(
                            "Locations must use their canonical stored "
                            "structure."
                        )

                if collection_name == "items":
                    normalized_item = normalize_item_record(record)

                    if record != normalized_item:
                        raise ValueError(
                            "Items must use their canonical stored structure."
                        )

                    if normalized_item["category"] not in (
                        normalized_item_categories
                    ):
                        raise ValueError(
                            "Every item must use an existing item category."
                        )

                    for passage in normalized_item["passage_history"]:
                        if (
                            passage["person_id"]
                            and passage["person_id"] not in seen_ids
                        ):
                            raise ValueError(
                                "Every item holder must reference an "
                                "existing person."
                            )

                if collection_name == "books":
                    normalized_book = normalize_book_record(record)

                    if record != normalized_book:
                        raise ValueError(
                            "Books must use their canonical stored structure."
                        )

                if collection_name == "book_readings":
                    normalized_reading = normalize_book_reading(record)

                    if record != normalized_reading:
                        raise ValueError(
                            "Book readings must use their canonical stored "
                            "structure."
                        )

        known_book_ids = {
            str(book.get("record_id", "") or "").strip()
            for book in database_data["books"]
            if isinstance(book, dict)
        }
        known_location_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in database_data["locations"]
            if isinstance(location, dict)
        }
        known_organization_ids = {
            str(organization.get("record_id", "") or "").strip()
            for organization in database_data["organizations"]
            if isinstance(organization, dict)
        }
        events_by_id = {
            str(event.get("record_id", "") or "").strip(): event
            for event in database_data["events"]
            if isinstance(event, dict)
        }

        for book in database_data["books"]:
            if (
                book["author_person_id"]
                and book["author_person_id"] not in seen_ids
            ):
                raise ValueError(
                    "Every linked book author must reference an existing "
                    "person."
                )

            if (
                book["publication_location_id"]
                and book["publication_location_id"] not in known_location_ids
            ):
                raise ValueError(
                    "Every book publication location must exist."
                )

            publication_event = events_by_id.get(
                book["publication_event_id"]
            )
            if not isinstance(publication_event, dict):
                raise ValueError(
                    "Every book must have a Published book event."
                )
            if publication_event.get("event_type") != "published_book":
                raise ValueError(
                    "A book publication event must use Published book."
                )
            if publication_event.get("book_ids") != [book["record_id"]]:
                raise ValueError(
                    "A Published book event must reference its book."
                )
            for holding in book["holdings"]:
                if (
                    holding["organization_id"]
                    and holding["organization_id"]
                    not in known_organization_ids
                ):
                    raise ValueError(
                        "Every book library or shop holding must reference "
                        "an existing organization."
                    )

                if (
                    holding["person_id"]
                    and holding["person_id"] not in seen_ids
                ):
                    raise ValueError(
                        "Every private book holding must reference an "
                        "existing person."
                    )

                if (
                    holding["location_id"]
                    and holding["location_id"] not in known_location_ids
                ):
                    raise ValueError(
                        "Every archived book holding must reference an "
                        "existing location."
                    )

        for reading in database_data["book_readings"]:
            if reading["person_id"] not in seen_ids:
                raise ValueError(
                    "Every book reading must reference an existing person."
                )

            if reading["book_id"] not in known_book_ids:
                raise ValueError(
                    "Every book reading must reference an existing book."
                )

        known_item_ids = {
            str(item.get("record_id", "") or "").strip()
            for item in database_data["items"]
            if isinstance(item, dict)
        }

        organizations = database_data["organizations"]
        organization_ids = {
            str(organization.get("record_id", "") or "")
            for organization in organizations
        }
        organization_jobs_by_key = {}
        seen_organization_job_ids = set()

        for organization in organizations:
            organization_id = str(
                organization.get("record_id", "") or ""
            )
            parent_id = str(
                organization.get(
                    "parent_organization_id",
                    "",
                )
                or ""
            )
            campus_location_id = str(
                organization.get("campus_location_id", "") or ""
            ).strip()

            if (
                organization.get("organization_type") == "School"
                and organization.get("location_id")
                and not campus_location_id
            ):
                raise ValueError(
                    "Every school organization must have a campus location."
                )

            if campus_location_id:
                campus = next(
                    (
                        location
                        for location in database_data["locations"]
                        if str(
                            location.get("record_id", "") or ""
                        ).strip()
                        == campus_location_id
                    ),
                    None,
                )

                if campus is None:
                    raise ValueError(
                        "Every school campus location must exist."
                    )

                if str(
                    campus.get("campus_organization_id", "") or ""
                ).strip() != organization_id:
                    raise ValueError(
                        "Every school campus must link back to its organization."
                    )

            if parent_id and parent_id not in organization_ids:
                raise ValueError(
                    "Every parent organization must exist."
                )

            if organization_id in organization_descendant_ids(
                organization_id,
                organizations,
            ):
                raise ValueError(
                    "Organization nesting cannot contain a cycle."
                )

            founding_event = normalize_organization_events(
                organization.get("events", [])
            )[0]
            founding_year = founding_event["year"]

            if founding_year is None:
                raise ValueError(
                    "Every organization must have a founding year."
                )

            for organization_event in normalize_organization_events(
                organization.get("events", [])
            ):
                unknown_person_ids = [
                    person_id
                    for person_id in event_linked_person_ids(
                        organization_event
                    )
                    if person_id not in seen_ids
                ]

                if unknown_person_ids:
                    raise ValueError(
                        "Every person linked to an organization event "
                        "must exist."
                    )

                if any(
                    item_id not in known_item_ids
                    for item_id in organization_event.get(
                        "item_ids",
                        [],
                    )
                ):
                    raise ValueError(
                        "Every item linked to an organization event "
                        "must exist."
                    )

                if any(
                    owner.get("person_id")
                    and owner.get("person_id") not in seen_ids
                    for owner in organization_event.get(
                        "item_new_owners",
                        {},
                    ).values()
                ):
                    raise ValueError(
                        "Every new item owner linked to an organization "
                        "event must exist."
                    )

                organization_event_role_ids = [
                    *organization_event.get("person_ids", []),
                    *organization_event.get(
                        "witness_person_ids",
                        [],
                    ),
                    *organization_event.get(
                        "affected_person_ids",
                        [],
                    ),
                ]

                if len(organization_event_role_ids) != len(
                    set(organization_event_role_ids)
                ):
                    raise ValueError(
                        "Each person can belong to only one event "
                        "category."
                    )

                if non_magical_person_ids.intersection(
                    organization_event.get(
                        "eminence_person_ids",
                        [],
                    )
                ):
                    raise ValueError(
                        "Non-magical people cannot earn Eminence."
                    )

            for organization_job in normalize_organization_jobs(
                organization.get("jobs", [])
            ):
                job_id = organization_job["record_id"]

                if job_id in seen_organization_job_ids:
                    raise ValueError(
                        "Organization job record IDs must be unique."
                    )

                if organization_job_date_tuple(
                    organization_job["opened_date"]
                ) < organization_job_date_tuple(
                    founding_event["date"]
                ):
                    raise ValueError(
                        "An organization job cannot open before its "
                        "organization was founded."
                    )

                organization_jobs_by_key[
                    (organization_id, job_id)
                ] = organization_job
                seen_organization_job_ids.add(job_id)

        all_job_assignments = []

        for person in database_data["people"]:
            plan = normalize_development_plan(
                person.get("development_plan")
            )

            for adult_year in plan.get("adult_years", []):
                all_job_assignments.extend(
                    normalize_job_records(
                        adult_year.get("jobs", [])
                    )
                )

        for assignment in all_job_assignments:
            if not assignment["organization_job_id"]:
                continue

            organization_job = organization_jobs_by_key.get(
                (
                    assignment["organization_id"],
                    assignment["organization_job_id"],
                )
            )

            if organization_job is None:
                raise ValueError(
                    "Every job assignment must reference an existing "
                    "organization job."
                )

            require_job_position_available(
                organization_job,
                assignment,
                all_job_assignments,
                assignment["record_id"],
            )

        world_events = normalize_world_events(database_data["events"])
        location_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in database_data["locations"]
            if isinstance(location, dict)
        }
        seen_birth_baby_ids = set()

        for event in world_events:
            linked_person_ids = event_linked_person_ids(event)

            if any(
                item_id not in known_item_ids
                for item_id in event.get("item_ids", [])
            ):
                raise ValueError(
                    "Every item linked to an event must exist."
                )

            if any(
                owner.get("person_id")
                and owner.get("person_id") not in seen_ids
                for owner in event.get(
                    "item_new_owners",
                    {},
                ).values()
            ):
                raise ValueError(
                    "Every new item owner linked to an event must exist."
                )

            if any(
                person_id not in seen_ids
                for person_id in linked_person_ids
            ):
                raise ValueError(
                    "Every person linked to an event must exist."
                )

            if non_magical_person_ids.intersection(
                event.get("eminence_person_ids", [])
            ):
                raise ValueError(
                    "Non-magical people cannot earn Eminence."
                )

            event_type = event.get("event_type")

            if event_type != "murder":
                event_role_ids = [
                    *event.get("person_ids", []),
                    *event.get("witness_person_ids", []),
                    *event.get("affected_person_ids", []),
                ]

                if len(event_role_ids) != len(set(event_role_ids)):
                    raise ValueError(
                        "Each person can belong to only one event "
                        "category."
                    )

            if event_type == BIRTH_EVENT_TYPE:
                baby_ids = birth_event_baby_ids(event)
                birthing_parent_ids = event.get(
                    "birthing_parent_person_ids",
                    [],
                )
                non_birthing_parent_ids = event.get(
                    "non_birthing_parent_person_ids",
                    [],
                )
                role_ids = birth_event_person_ids(event)

                if len(baby_ids) != 1:
                    raise ValueError(
                        "A Birth event needs exactly one baby."
                    )

                if (
                    len(birthing_parent_ids) > 1
                    or len(non_birthing_parent_ids) > 1
                ):
                    raise ValueError(
                        "A Birth event can have no more than one parent "
                        "in each parent category."
                    )

                if len(role_ids) != (
                    len(baby_ids)
                    + len(birthing_parent_ids)
                    + len(non_birthing_parent_ids)
                ):
                    raise ValueError(
                        "Every Birth event role must belong to a different "
                        "person."
                    )

                if event.get("eminence_person_ids"):
                    raise ValueError(
                        "Birth events cannot earn Eminence."
                    )

                if len(event.get("location_ids", [])) > 1:
                    raise ValueError(
                        "Birth events can have no more than one location."
                    )

                if any(
                    person_id not in seen_ids
                    for person_id in role_ids
                ):
                    raise ValueError(
                        "Every person linked to a Birth event must exist."
                    )

                if any(
                    location_id not in location_ids
                    for location_id in event.get("location_ids", [])
                ):
                    raise ValueError(
                        "Every location linked to a Birth event must exist."
                    )

                baby_id = baby_ids[0]

                if baby_id in seen_birth_baby_ids:
                    raise ValueError(
                        "A baby can have only one Birth event."
                    )

                seen_birth_baby_ids.add(baby_id)
                baby = people_by_id[baby_id]
                event_birth_date = str(
                    event.get("date", "") or ""
                ).strip()
                birth_year, birth_month, birth_day = (
                    split_world_event_date(event_birth_date)
                    if event_birth_date
                    else ("", "", "")
                )

                if (
                    (
                        int(birth_year) if birth_year else None
                    )
                    != baby.get("birth_year")
                    or (
                        int(birth_month) if birth_month else None
                    )
                    != baby.get("birth_month")
                    or (int(birth_day) if birth_day else None)
                    != baby.get("birth_day")
                    or str(
                        baby.get("biological_mother_id", "") or ""
                    ).strip()
                    != (
                        birthing_parent_ids[0]
                        if birthing_parent_ids
                        else ""
                    )
                    or str(
                        baby.get("biological_father_id", "") or ""
                    ).strip()
                    != (
                        non_birthing_parent_ids[0]
                        if non_birthing_parent_ids
                        else ""
                    )
                ):
                    raise ValueError(
                        "A Birth event must match the baby's birth date "
                        "and family links."
                    )

                continue

            if event_type not in DEATH_EVENT_TYPES:
                continue

            if (
                event_type == "died"
                and event.get("eminence_person_ids")
            ):
                raise ValueError(
                    "Death events cannot earn Eminence."
                )

            if len(event.get("location_ids", [])) > 1:
                raise ValueError(
                    "Death and Murder events can have no more than one "
                    "location."
                )

            if any(
                location_id not in location_ids
                for location_id in event.get("location_ids", [])
            ):
                raise ValueError(
                    "Every location linked to a Death or Murder event "
                    "must exist."
                )

            if event_type == "died":
                if len(event.get("person_ids", [])) != 1:
                    raise ValueError(
                        "A Death event needs one person."
                    )

                if any(
                    person_id not in seen_ids
                    for person_id in event.get("person_ids", [])
                ):
                    raise ValueError(
                        "Every person linked to a Death event must exist."
                    )

                continue

            perpetrator_ids = event.get(
                "perpetrator_person_ids",
                [],
            )
            victim_ids = event.get("victim_person_ids", [])
            witness_ids = event.get("witness_person_ids", [])
            affected_ids = event.get("affected_person_ids", [])

            if not perpetrator_ids or not victim_ids:
                raise ValueError(
                    "A Murder event needs perpetrators and victims."
                )

            all_role_ids = [
                *perpetrator_ids,
                *victim_ids,
                *witness_ids,
                *affected_ids,
            ]

            if len(all_role_ids) != len(set(all_role_ids)):
                raise ValueError(
                    "Each Murder participant can belong to only one "
                    "category."
                )

            if set(victim_ids).intersection(
                event.get("eminence_person_ids", [])
            ):
                raise ValueError(
                    "Victims cannot earn Eminence from a Murder event."
                )

            if any(
                person_id not in seen_ids
                for person_id in all_role_ids
            ):
                raise ValueError(
                    "Every person linked to a Murder event must exist."
                )

        for ghost_event in world_events:
            if ghost_event.get("event_type") != GHOST_EVENT_TYPE:
                continue

            ghost_person_ids = ghost_event.get("person_ids", [])

            if len(ghost_person_ids) != 1:
                raise ValueError(
                    "A Returns as ghost event must belong to exactly one "
                    "person."
                )

            ghost_person_id = ghost_person_ids[0]
            death_events = [
                event
                for event in world_events
                if ghost_person_id in death_event_person_ids(event)
            ]
            ghost_person = people_by_id.get(ghost_person_id)

            if ghost_person is not None:
                death_events.extend(
                    timeline_event
                    for timeline_event in normalize_timeline_events(
                        ghost_person.get("timeline_events", [])
                    )
                    if timeline_event.get("event_type") == "died"
                    and str(
                        timeline_event.get("date", "") or ""
                    ).strip()
                )

            if not death_events:
                raise ValueError(
                    "A Returns as ghost event requires a Death or Murder "
                    "event for that person."
                )

            if not any(
                world_event_date_is_on_or_after(
                    ghost_event.get("date"),
                    death_event.get("date"),
                )
                for death_event in death_events
            ):
                raise ValueError(
                    "Returns as ghost cannot occur before that person's "
                    "Death or Murder event."
                )

    def list_people(self):
        if not self.fully_loaded:
            raise RuntimeError(
                "World data is still loading; use indexed People summaries."
            )
        return deepcopy(self.data["people"])

    def read_person(self, record_id):
        return self.get_record("people", record_id)

    def create_person(self, values):
        if not isinstance(values, dict):
            raise TypeError("A person must be a dictionary.")

        person = deepcopy(values)
        person.setdefault("record_id", str(uuid.uuid4()))
        person.setdefault("unfinished", True)
        person.setdefault("does_not_have_children", False)

        if not isinstance(person["unfinished"], bool):
            raise TypeError("A person's unfinished flag must be true or false.")

        if not isinstance(person["does_not_have_children"], bool):
            raise TypeError(
                "A person's Does not have children flag must be true or false."
            )

        settings = self.data.get("_application_settings", {})
        assignment_policy = (
            settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )
        if person.get("non_magical"):
            person["school"] = ""
            person["development_plan"] = (
                non_magical_development_plan(
                    person.get("development_plan")
                )
            )
        else:
            person["development_plan"] = migrated_development_plan(
                person.get("development_plan"),
                assignment_policy,
                person["record_id"],
            )
        mage_groups = normalize_mage_groups(
            settings.get(MAGE_GROUPS_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )
        person["mage_group_id"] = normalize_mage_group_id(
            person.get("mage_group_id"),
            mage_groups,
        )
        requested_blood_status = person.get("blood_status")
        person["blood_status"] = (
            normalize_blood_status(person["blood_status"])
            if person.get("blood_status")
            else resolved_blood_status(
                person,
                self.data["people"],
            )
        )
        person["developmental_environment"] = (
            normalize_developmental_environment(
                (
                    person.get("developmental_environment")
                    or legacy_developmental_environment(
                        requested_blood_status
                    )
                ),
                person["blood_status"],
            )
        )
        person["parental_values"] = normalize_parental_values(
            person.get("parental_values")
        )
        person["initial_bonuses"] = normalize_initial_bonuses(
            person.get("initial_bonuses")
        )
        person["characteristics"] = normalize_characteristics(
            person.get("characteristics")
        )
        require_blood_status_compatible(
            person,
            self.data["people"],
        )

        if self.read_person(person["record_id"]) is not None:
            raise ValueError(f"Duplicate person record_id: {person['record_id']}")

        self.ensure_unique_displayed_name(person.get("displayed_name"))

        person = self._store_person_support_references(
            person["record_id"], person
        )

        timeline_events = person.pop("timeline_events", [])
        person["event_refs"] = self._store_person_timeline(
            person["record_id"],
            timeline_events,
            person.get("event_refs", []),
        )

        current_time = datetime.now(timezone.utc).isoformat()
        person.setdefault("created_at", current_time)
        person["last_updated"] = current_time
        self.data["people"].append(person)
        self.dirty = True
        self.revision += 1
        self.record_indexes.setdefault("people", {})[
            person["record_id"]
        ] = person
        self.index_dirty = True
        self.notify_changed("people", (person["record_id"],))

        return self._hydrate_person_record(deepcopy(person))

    def update_person(self, record_id, values):
        if not isinstance(values, dict):
            raise TypeError("Person changes must be a dictionary.")

        if "record_id" in values and values["record_id"] != record_id:
            raise ValueError("A person record_id cannot be changed.")

        for person in self.data["people"]:
            if person.get("record_id") != record_id:
                continue

            prospective_person = deepcopy(person)
            prospective_person.update(deepcopy(values))
            prospective_person.setdefault(
                "does_not_have_children",
                False,
            )

            if not isinstance(
                prospective_person["does_not_have_children"],
                bool,
            ):
                raise TypeError(
                    "A person's Does not have children flag must be true "
                    "or false."
                )

            if prospective_person.get("non_magical"):
                prospective_person["school"] = ""
                prospective_person["development_plan"] = (
                    non_magical_development_plan(
                        prospective_person.get("development_plan")
                    )
                )
            else:
                prospective_person["development_plan"] = (
                    normalize_development_plan(
                        prospective_person.get("development_plan")
                    )
                )
            settings = self.data.get("_application_settings", {})
            mage_groups = normalize_mage_groups(
                settings.get(MAGE_GROUPS_SETTING_KEY)
                if isinstance(settings, dict)
                else None
            )
            prospective_person["mage_group_id"] = (
                require_mage_group_id(
                    prospective_person.get("mage_group_id"),
                    mage_groups,
                )
            )
            prospective_person["blood_status"] = (
                normalize_blood_status(
                    prospective_person.get("blood_status")
                )
            )
            prospective_person["developmental_environment"] = (
                normalize_developmental_environment(
                    prospective_person.get(
                        "developmental_environment"
                    ),
                    prospective_person["blood_status"],
                )
            )
            prospective_person["parental_values"] = (
                normalize_parental_values(
                    prospective_person.get("parental_values")
                )
            )
            prospective_person["initial_bonuses"] = (
                normalize_initial_bonuses(
                    prospective_person.get("initial_bonuses")
                )
            )
            prospective_person["characteristics"] = (
                normalize_characteristics(
                    prospective_person.get("characteristics")
                )
            )
            require_blood_status_compatible(
                prospective_person,
                self.data["people"],
            )
            self.ensure_unique_displayed_name(
                prospective_person.get("displayed_name"),
                excluded_record_id=record_id,
            )
            stored_values = self._store_person_support_references(
                record_id, values
            )
            if "timeline_events" in stored_values:
                stored_values["event_refs"] = self._store_person_timeline(
                    record_id,
                    stored_values.pop("timeline_events"),
                    person.get("event_refs", []),
                )
            person.update(stored_values)
            person["school"] = prospective_person.get("school", "")
            person["does_not_have_children"] = prospective_person[
                "does_not_have_children"
            ]
            person["development_plan"] = deepcopy(
                prospective_person["development_plan"]
            )
            person["mage_group_id"] = prospective_person[
                "mage_group_id"
            ]
            person["blood_status"] = prospective_person[
                "blood_status"
            ]
            person["developmental_environment"] = (
                prospective_person["developmental_environment"]
            )
            person["parental_values"] = deepcopy(
                prospective_person["parental_values"]
            )
            person["initial_bonuses"] = deepcopy(
                prospective_person["initial_bonuses"]
            )
            person["characteristics"] = deepcopy(
                prospective_person["characteristics"]
            )
            person["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.dirty = True
            self.revision += 1
            self.index_dirty = True
            self.notify_changed("people", (record_id,))

            return self._hydrate_person_record(deepcopy(person))

        raise KeyError(f"Unknown person record_id: {record_id}")

    def ensure_unique_displayed_name(self, displayed_name, excluded_record_id=None):
        normalized_name = str(displayed_name or "").strip().casefold()

        if not normalized_name:
            raise ValueError("A magician must have a displayed name.")

        for person in self.data["people"]:
            if person.get("record_id") == excluded_record_id:
                continue

            existing_name = str(person.get("displayed_name", "")).strip().casefold()

            if existing_name == normalized_name:
                raise ValueError(
                    f'A magician named "{str(displayed_name).strip()}" already exists.'
                )

    def delete_person(self, record_id):
        """Delete one person without reconciling the entire world.

        Large worlds made the original implementation disproportionately
        expensive: it normalized every other person and then performed global
        birth and death synchronizations.  The reverse indexes built at load
        time let deletion repair only records that actually reference this
        person.
        """
        normalized_id = str(record_id or "").strip()
        deleted_person = self.record_indexes.get("people", {}).get(
            normalized_id
        )
        if deleted_person is None:
            raise KeyError(f"Unknown person record_id: {record_id}")

        deleted_person_name = str(
            deleted_person.get("displayed_name", "") or "Unnamed person"
        ).strip()
        related_person_ids = set(
            self.person_reference_index.get(normalized_id, ())
        )
        # Include relationships edited since the most recent complete index
        # rebuild. This is one inexpensive linear pass, not the former
        # people-by-events global reconciliation.
        for candidate in self.data.get("people", []):
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("record_id", "") or "").strip()
            if not candidate_id or candidate_id == normalized_id:
                continue
            candidate_references = {
                str(candidate.get("biological_mother_id", "") or "").strip(),
                str(candidate.get("biological_father_id", "") or "").strip(),
                *(
                    str(value or "").strip()
                    for value in candidate.get("mate_ids", []) or []
                ),
                *(
                    str(relationship.get("person_id", "") or "").strip()
                    for relationship in candidate.get(
                        "spouse_relationships", []
                    )
                    or []
                    if isinstance(relationship, dict)
                ),
            }
            if normalized_id in candidate_references:
                related_person_ids.add(candidate_id)
        related_people = self.record_indexes.get("people", {})
        self.data["people"] = [
            person
            for person in self.data.get("people", [])
            if person.get("record_id") != normalized_id
        ]

        for related_id in related_person_ids:
            related_person = related_people.get(related_id)
            if not isinstance(related_person, dict):
                continue
            if related_person.get("biological_mother_id") == normalized_id:
                related_person["biological_mother_id"] = ""
                related_person["biological_mother_status"] = "unknown"
            if related_person.get("biological_father_id") == normalized_id:
                related_person["biological_father_id"] = ""
                related_person["biological_father_status"] = "unknown"
            related_person["mate_ids"] = [
                mate_id
                for mate_id in related_person.get("mate_ids", [])
                if mate_id != normalized_id
            ]
            related_person["spouse_relationships"] = [
                relationship
                for relationship in normalize_spouse_relationships(
                    related_person.get("spouse_relationships", [])
                )
                if relationship["person_id"] != normalized_id
            ]

        affected_event_ids = set(
            self.event_person_reference_index.get(normalized_id, ())
        )
        for candidate in self.data.get("events", []):
            if (
                isinstance(candidate, dict)
                and normalized_id in event_linked_person_ids(candidate)
            ):
                candidate_id = str(
                    candidate.get("record_id")
                    or candidate.get("event_id")
                    or ""
                ).strip()
                if candidate_id:
                    affected_event_ids.add(candidate_id)
        event_index = self.record_indexes.get("events", {})
        removed_event_ids = set()
        affected_death_people = set()

        for event_id in affected_event_ids:
            event = event_index.get(event_id)
            if not isinstance(event, dict):
                continue
            affected_death_people.update(event_linked_person_ids(event))
            event_type = str(event.get("event_type", "") or "")
            perpetrator_ids = [
                value
                for value in event.get("perpetrator_person_ids", [])
                if value != normalized_id
            ]
            victim_ids = [
                value
                for value in event.get("victim_person_ids", [])
                if value != normalized_id
            ]
            witness_ids = [
                value
                for value in event.get("witness_person_ids", [])
                if value != normalized_id
            ]
            affected_ids = [
                value
                for value in event.get("affected_person_ids", [])
                if value != normalized_id
            ]

            if event_type == BIRTH_EVENT_TYPE:
                baby_ids = [
                    value
                    for value in event.get("baby_person_ids", [])
                    if value != normalized_id
                ]
                if not baby_ids:
                    removed_event_ids.add(event_id)
                    continue
                birthing_parent_ids = [
                    value
                    for value in event.get("birthing_parent_person_ids", [])
                    if value != normalized_id
                ]
                non_birthing_parent_ids = [
                    value
                    for value in event.get(
                        "non_birthing_parent_person_ids", []
                    )
                    if value != normalized_id
                ]
                event["baby_person_ids"] = baby_ids
                event["birthing_parent_person_ids"] = birthing_parent_ids
                event["non_birthing_parent_person_ids"] = (
                    non_birthing_parent_ids
                )
                event["person_ids"] = list(
                    dict.fromkeys(
                        [
                            *baby_ids,
                            *birthing_parent_ids,
                            *non_birthing_parent_ids,
                        ]
                    )
                )
                event["eminence_person_ids"] = []
                event["eminence_skills"] = {}
            elif event_type == "murder":
                if not perpetrator_ids or not victim_ids:
                    removed_event_ids.add(event_id)
                    continue
                event["perpetrator_person_ids"] = perpetrator_ids
                event["victim_person_ids"] = victim_ids
                event["witness_person_ids"] = witness_ids
                event["affected_person_ids"] = affected_ids
                event["person_ids"] = list(
                    dict.fromkeys(
                        [
                            *perpetrator_ids,
                            *victim_ids,
                            *witness_ids,
                            *affected_ids,
                        ]
                    )
                )
            else:
                event["person_ids"] = [
                    value
                    for value in event.get("person_ids", [])
                    if value != normalized_id
                ]
                if event_type in {"died", GHOST_EVENT_TYPE} and not event[
                    "person_ids"
                ]:
                    removed_event_ids.add(event_id)
                    continue

            if "witness_person_ids" in event:
                event["witness_person_ids"] = witness_ids
            if "affected_person_ids" in event:
                event["affected_person_ids"] = affected_ids
            event["eminence_person_ids"] = [
                value
                for value in event.get("eminence_person_ids", [])
                if value != normalized_id
            ]
            event["eminence_skills"] = {
                person_id: skill
                for person_id, skill in (
                    event.get("eminence_skills", {})
                    if isinstance(event.get("eminence_skills", {}), dict)
                    else {}
                ).items()
                if person_id != normalized_id
            }
            item_new_owners = dict(event.get("item_new_owners", {}) or {})
            for item_id, owner in item_new_owners.items():
                if (
                    isinstance(owner, dict)
                    and owner.get("person_id") == normalized_id
                ):
                    item_new_owners[item_id] = {
                        "person_id": "",
                        "person_name": owner.get("person_name")
                        or deleted_person_name,
                    }
            event["item_new_owners"] = item_new_owners

        if removed_event_ids:
            self.data["events"] = [
                event
                for event in self.data.get("events", [])
                if str(
                    event.get("record_id")
                    or event.get("event_id")
                    or ""
                ).strip()
                not in removed_event_ids
            ]

        affected_death_people.discard(normalized_id)
        if affected_death_people:
            synchronize_people_death_records(
                self.data,
                tuple(affected_death_people),
            )

        # These collections are small compared with People and Events, but can
        # contain legacy embedded person references that are not represented
        # in the event reverse index.
        for organization in self.data.get("organizations", []):
            if not isinstance(organization, dict):
                continue
            organization["events"] = normalize_organization_events(
                [
                    {
                        **organization_event,
                        "person_ids": [
                            value
                            for value in organization_event.get(
                                "person_ids", []
                            )
                            if value != normalized_id
                        ],
                        "eminence_person_ids": [
                            value
                            for value in organization_event.get(
                                "eminence_person_ids", []
                            )
                            if value != normalized_id
                        ],
                        "eminence_skills": {
                            person_id: skill
                            for person_id, skill in (
                                organization_event.get(
                                    "eminence_skills", {}
                                )
                                if isinstance(
                                    organization_event.get(
                                        "eminence_skills", {}
                                    ),
                                    dict,
                                )
                                else {}
                            ).items()
                            if person_id != normalized_id
                        },
                    }
                    for organization_event in normalize_organization_events(
                        organization.get("events", [])
                    )
                ]
            )
            for organization_event in organization["events"]:
                owners = dict(
                    organization_event.get("item_new_owners", {}) or {}
                )
                for item_id, owner in owners.items():
                    if (
                        isinstance(owner, dict)
                        and owner.get("person_id") == normalized_id
                    ):
                        owners[item_id] = {
                            "person_id": "",
                            "person_name": owner.get("person_name")
                            or deleted_person_name,
                        }
                organization_event["item_new_owners"] = owners

        repaired_items = []
        for stored_item in self.data.get("items", []):
            item = normalize_item_record(stored_item)
            for passage in item["passage_history"]:
                if passage["person_id"] == normalized_id:
                    passage["person_id"] = ""
                    passage["person_name"] = (
                        passage["person_name"] or deleted_person_name
                    )
            repaired_items.append(normalize_item_record(item))
        self.data["items"] = repaired_items

        repaired_books = []
        for stored_book in self.data.get("books", []):
            book = normalize_book_record(stored_book)
            if book["author_person_id"] == normalized_id:
                book["author_person_id"] = ""
                book["author_name"] = book["author_name"] or deleted_person_name
            for holding in book["holdings"]:
                if (
                    holding["holder_type"] == "Private owner"
                    and holding["person_id"] == normalized_id
                ):
                    holding["person_id"] = ""
                    holding["holder_name"] = (
                        holding["holder_name"] or deleted_person_name
                    )
            repaired_books.append(normalize_book_record(book))
        self.data["books"] = repaired_books
        self.data["book_readings"] = [
            normalize_book_reading(
                {
                    **reading,
                    "source_person_id": (
                        ""
                        if reading.get("source_person_id") == normalized_id
                        else reading.get("source_person_id", "")
                    ),
                }
            )
            for reading in self.data.get("book_readings", [])
            if reading.get("person_id") != normalized_id
        ]

        self.dirty = True
        self.revision += 1
        self.rebuild_record_indexes()
        self.index_dirty = True
        self.notify_changed("people", (normalized_id,))
        return deepcopy(deleted_person)

    def _delete_person_legacy(self, record_id):
        for index, person in enumerate(self.data["people"]):
            if person.get("record_id") != record_id:
                continue

            deleted_person = self.data["people"].pop(index)
            deleted_person_name = str(
                deleted_person.get("displayed_name", "")
                or "Unnamed person"
            ).strip()

            for related_person in self.data["people"]:
                if related_person.get("biological_mother_id") == record_id:
                    related_person["biological_mother_id"] = ""
                    related_person[
                        "biological_mother_status"
                    ] = "unknown"

                if related_person.get("biological_father_id") == record_id:
                    related_person["biological_father_id"] = ""
                    related_person[
                        "biological_father_status"
                    ] = "unknown"

                related_person["mate_ids"] = [
                    mate_id
                    for mate_id in related_person.get("mate_ids", [])
                    if mate_id != record_id
                ]
                related_person["spouse_relationships"] = [
                    relationship
                    for relationship in normalize_spouse_relationships(
                        related_person.get("spouse_relationships", [])
                    )
                    if relationship["person_id"] != record_id
                ]

            retained_events = []

            for event in self.data.get("events", []):
                event_type = str(event.get("event_type", "") or "")
                perpetrator_ids = [
                    person_id
                    for person_id in event.get(
                        "perpetrator_person_ids",
                        [],
                    )
                    if person_id != record_id
                ]
                victim_ids = [
                    person_id
                    for person_id in event.get(
                        "victim_person_ids",
                        [],
                    )
                    if person_id != record_id
                ]
                witness_ids = [
                    person_id
                    for person_id in event.get(
                        "witness_person_ids",
                        [],
                    )
                    if person_id != record_id
                ]
                affected_ids = [
                    person_id
                    for person_id in event.get(
                        "affected_person_ids",
                        [],
                    )
                    if person_id != record_id
                ]

                if event_type == BIRTH_EVENT_TYPE:
                    baby_ids = [
                        person_id
                        for person_id in event.get(
                            "baby_person_ids",
                            [],
                        )
                        if person_id != record_id
                    ]

                    if not baby_ids:
                        continue

                    birthing_parent_ids = [
                        person_id
                        for person_id in event.get(
                            "birthing_parent_person_ids",
                            [],
                        )
                        if person_id != record_id
                    ]
                    non_birthing_parent_ids = [
                        person_id
                        for person_id in event.get(
                            "non_birthing_parent_person_ids",
                            [],
                        )
                        if person_id != record_id
                    ]
                    event["baby_person_ids"] = baby_ids
                    event[
                        "birthing_parent_person_ids"
                    ] = birthing_parent_ids
                    event[
                        "non_birthing_parent_person_ids"
                    ] = non_birthing_parent_ids
                    event["person_ids"] = list(
                        dict.fromkeys(
                            [
                                *baby_ids,
                                *birthing_parent_ids,
                                *non_birthing_parent_ids,
                            ]
                        )
                    )
                    event["eminence_person_ids"] = []
                    event["eminence_skills"] = {}
                elif event_type == "murder":
                    if not perpetrator_ids or not victim_ids:
                        continue

                    event["perpetrator_person_ids"] = perpetrator_ids
                    event["victim_person_ids"] = victim_ids
                    event["witness_person_ids"] = witness_ids
                    event["affected_person_ids"] = affected_ids
                    event["person_ids"] = list(
                        dict.fromkeys(
                            [
                                *perpetrator_ids,
                                *victim_ids,
                                *witness_ids,
                                *affected_ids,
                            ]
                        )
                    )
                else:
                    event["person_ids"] = [
                        person_id
                        for person_id in event.get("person_ids", [])
                        if person_id != record_id
                    ]

                    if event_type == "died" and not event["person_ids"]:
                        continue

                    if (
                        event_type == GHOST_EVENT_TYPE
                        and not event["person_ids"]
                    ):
                        continue

                if "witness_person_ids" in event:
                    event["witness_person_ids"] = witness_ids

                if "affected_person_ids" in event:
                    event["affected_person_ids"] = affected_ids

                event["eminence_person_ids"] = [
                    person_id
                    for person_id in event.get(
                        "eminence_person_ids",
                        [],
                    )
                    if person_id != record_id
                ]
                event["eminence_skills"] = {
                    person_id: skill
                    for person_id, skill in (
                        event.get("eminence_skills", {})
                        if isinstance(
                            event.get("eminence_skills", {}),
                            dict,
                        )
                        else {}
                    ).items()
                    if person_id != record_id
                }
                item_new_owners = dict(
                    event.get("item_new_owners", {}) or {}
                )

                for item_id, owner in item_new_owners.items():
                    if (
                        isinstance(owner, dict)
                        and owner.get("person_id") == record_id
                    ):
                        item_new_owners[item_id] = {
                            "person_id": "",
                            "person_name": (
                                owner.get("person_name")
                                or deleted_person_name
                            ),
                        }

                event["item_new_owners"] = item_new_owners

                retained_events.append(event)

            self.data["events"] = retained_events
            synchronize_birth_events_from_people(self.data)
            synchronize_people_death_records(self.data)

            for organization in self.data.get(
                "organizations",
                [],
            ):
                if not isinstance(organization, dict):
                    continue

                organization["events"] = (
                    normalize_organization_events(
                        [
                            {
                                **organization_event,
                                "person_ids": [
                                    person_id
                                    for person_id in organization_event.get(
                                        "person_ids",
                                        [],
                                    )
                                    if person_id != record_id
                                ],
                                "eminence_person_ids": [
                                    person_id
                                    for person_id in organization_event.get(
                                        "eminence_person_ids",
                                        [],
                                    )
                                    if person_id != record_id
                                ],
                                "eminence_skills": {
                                    person_id: skill
                                    for person_id, skill in (
                                        organization_event.get(
                                            "eminence_skills",
                                            {},
                                        )
                                        if isinstance(
                                            organization_event.get(
                                                "eminence_skills",
                                                {},
                                            ),
                                            dict,
                                        )
                                        else {}
                                    ).items()
                                    if person_id != record_id
                                },
                            }
                            for organization_event in (
                                normalize_organization_events(
                                    organization.get("events", [])
                                )
                            )
                        ]
                    )
                )

                for organization_event in organization["events"]:
                    item_new_owners = dict(
                        organization_event.get(
                            "item_new_owners",
                            {},
                        )
                        or {}
                    )

                    for item_id, owner in item_new_owners.items():
                        if (
                            isinstance(owner, dict)
                            and owner.get("person_id") == record_id
                        ):
                            item_new_owners[item_id] = {
                                "person_id": "",
                                "person_name": (
                                    owner.get("person_name")
                                    or deleted_person_name
                                ),
                            }

                    organization_event[
                        "item_new_owners"
                    ] = item_new_owners

                organization["events"] = normalize_organization_events(
                    organization["events"]
                )

            repaired_items = []

            for stored_item in self.data.get("items", []):
                item = normalize_item_record(stored_item)

                for passage in item["passage_history"]:
                    if passage["person_id"] != record_id:
                        continue

                    passage["person_id"] = ""
                    passage["person_name"] = (
                        passage["person_name"] or deleted_person_name
                    )

                repaired_items.append(normalize_item_record(item))

            self.data["items"] = repaired_items

            repaired_books = []

            for stored_book in self.data.get("books", []):
                book = normalize_book_record(stored_book)

                if book["author_person_id"] == record_id:
                    book["author_person_id"] = ""
                    book["author_name"] = (
                        book["author_name"] or deleted_person_name
                    )

                for holding in book["holdings"]:
                    if (
                        holding["holder_type"] == "Private owner"
                        and holding["person_id"] == record_id
                    ):
                        holding["person_id"] = ""
                        holding["holder_name"] = (
                            holding["holder_name"] or deleted_person_name
                        )
                repaired_books.append(normalize_book_record(book))

            self.data["books"] = repaired_books
            self.data["book_readings"] = [
                normalize_book_reading(
                    {
                        **reading,
                        "source_person_id": (
                            ""
                            if reading.get("source_person_id") == record_id
                            else reading.get("source_person_id", "")
                        ),
                    }
                )
                for reading in self.data.get("book_readings", [])
                if reading.get("person_id") != record_id
            ]

            legacy_import_id = str(
                deleted_person.get("legacy_import_id", "") or ""
            ).strip()
            if legacy_import_id:
                self.data["legacy_person_imports"] = [
                    item
                    for item in self.data.get("legacy_person_imports", [])
                    if item.get("record_id") != legacy_import_id
                ]
                self.record_indexes.get("legacy_person_imports", {}).pop(
                    legacy_import_id, None
                )

            self.dirty = True
            self.revision += 1
            self.rebuild_record_indexes()
            self.index_dirty = True
            self.notify_changed(
                "people",
                (record_id,),
            )

            return deepcopy(deleted_person)

        raise KeyError(f"Unknown person record_id: {record_id}")

    def list_records(self, collection_name):
        if collection_name not in (
            "people",
            "locations",
            "organizations",
            "events",
            "items",
            "books",
            "book_readings",
            "maps",
            "board_groups",
            "named_creatures",
            "person_tag_catalog",
            "legacy_person_imports",
        ):
            raise KeyError(f"Unknown application collection: {collection_name}")

        if not self.fully_loaded:
            raise RuntimeError(
                f"World data is still loading; use indexed {collection_name} summaries."
            )
        return deepcopy(self.data[collection_name])

    def read_record(self, collection_name, record_id):
        if collection_name not in (
            "people",
            "locations",
            "organizations",
            "events",
            "items",
            "books",
            "book_readings",
            "maps",
            "board_groups",
            "named_creatures",
            "person_tag_catalog",
            "legacy_person_imports",
        ):
            raise KeyError(
                f"Unknown application collection: {collection_name}"
            )

        return self.get_record(collection_name, record_id)

    def _set_person_event_reference(self, person_id, event_id, present):
        person = self.record_indexes.get("people", {}).get(
            str(person_id or "").strip()
        )
        if person is None:
            return False
        references = normalize_event_references(person.get("event_refs", []))
        normalized_event_id = str(event_id or "").strip()
        updated = [
            reference
            for reference in references
            if reference != normalized_event_id
        ]
        if present and normalized_event_id:
            updated.append(normalized_event_id)
        if updated == references:
            return False
        person["event_refs"] = updated
        return True

    def create_record(self, collection_name, values):
        if not isinstance(values, dict):
            raise TypeError("A database record must be a dictionary.")

        record = deepcopy(values)
        record.setdefault("record_id", str(uuid.uuid4()))

        if self.read_record(collection_name, record["record_id"]) is not None:
            raise ValueError(
                f"Duplicate {collection_name} record_id: {record['record_id']}"
            )

        current_time = datetime.now(timezone.utc).isoformat()
        record.setdefault("created_at", current_time)
        record["last_updated"] = current_time
        self.data[collection_name].append(record)
        self.dirty = True
        self.revision += 1
        self.record_indexes.setdefault(collection_name, {})[
            record["record_id"]
        ] = record
        if collection_name == "events":
            for person_id in event_linked_person_ids(record):
                self.event_person_reference_index.setdefault(
                    person_id,
                    set(),
                ).add(record["record_id"])
                self._set_person_event_reference(
                    person_id,
                    record["record_id"],
                    True,
                )
        self.index_dirty = True
        self.notify_changed(collection_name, (record["record_id"],))
        return deepcopy(record)

    def update_record(self, collection_name, record_id, values):
        if not isinstance(values, dict):
            raise TypeError("Database record changes must be a dictionary.")

        if "record_id" in values and values["record_id"] != record_id:
            raise ValueError("A database record_id cannot be changed.")

        for record in self.data[collection_name]:
            if record.get("record_id") != record_id:
                continue

            previous_person_ids = (
                set(event_linked_person_ids(record))
                if collection_name == "events"
                else set()
            )
            record.update(deepcopy(values))
            record["last_updated"] = datetime.now(timezone.utc).isoformat()
            if collection_name == "events":
                current_person_ids = set(event_linked_person_ids(record))
                for person_id in previous_person_ids - current_person_ids:
                    references = self.event_person_reference_index.get(
                        person_id
                    )
                    if references is not None:
                        references.discard(record_id)
                        if not references:
                            self.event_person_reference_index.pop(
                                person_id,
                                None,
                            )
                    self._set_person_event_reference(
                        person_id,
                        record_id,
                        False,
                    )
                for person_id in current_person_ids:
                    self.event_person_reference_index.setdefault(
                        person_id,
                        set(),
                    ).add(record_id)
                    self._set_person_event_reference(
                        person_id,
                        record_id,
                        True,
                    )
            self.dirty = True
            self.revision += 1
            self.index_dirty = True
            self.notify_changed(collection_name, (record_id,))
            return deepcopy(record)

        raise KeyError(f"Unknown {collection_name} record_id: {record_id}")

    def delete_record(self, collection_name, record_id):
        for index, record in enumerate(self.data[collection_name]):
            if record.get("record_id") != record_id:
                continue

            deleted_record = self.data[collection_name].pop(index)
            if collection_name == "events":
                for person_id in event_linked_person_ids(deleted_record):
                    references = self.event_person_reference_index.get(
                        person_id
                    )
                    if references is not None:
                        references.discard(record_id)
                        if not references:
                            self.event_person_reference_index.pop(
                                person_id,
                                None,
                            )
                    self._set_person_event_reference(
                        person_id,
                        record_id,
                        False,
                    )
            self.dirty = True
            self.revision += 1
            self.record_indexes.get(collection_name, {}).pop(
                record_id,
                None,
            )
            self.index_dirty = True
            self.notify_changed(collection_name, (record_id,))
            return deepcopy(deleted_record)

        raise KeyError(f"Unknown {collection_name} record_id: {record_id}")

    def prune_backups(self):
        if not self.backup_directory.exists():
            return

        backup_records = []

        for backup_path in self.backup_directory.glob("mage_maker-*.json"):
            name_parts = backup_path.stem.split("-")

            if (
                len(name_parts) < 4
                or name_parts[0] != "mage_maker"
                or len(name_parts[1]) != 8
                or len(name_parts[2]) != 6
                or len(name_parts[3]) != 6
                or not "".join(name_parts[1:4]).isdigit()
            ):
                continue

            try:
                backup_time = datetime.strptime(
                    "".join(name_parts[1:4]),
                    "%Y%m%d%H%M%S%f",
                )
            except ValueError:
                continue

            backup_records.append(
                (
                    backup_time,
                    backup_path,
                    "-".join(name_parts[:4]),
                )
            )

        if not backup_records:
            return

        backup_records.sort()
        daily_groups = {}
        weekly_groups = {}

        for backup_record in backup_records:
            backup_time = backup_record[0]
            daily_groups.setdefault(
                backup_time.date(),
                [],
            ).append(backup_record)
            iso_calendar = backup_time.isocalendar()
            weekly_groups.setdefault(
                (iso_calendar.year, iso_calendar.week),
                [],
            ).append(backup_record)

        daily_dates = sorted(daily_groups, reverse=True)[
            : self.DAILY_BACKUP_LIMIT
        ]
        weekly_dates = sorted(weekly_groups, reverse=True)[
            : self.WEEKLY_BACKUP_LIMIT
        ]
        daily_markers = {
            daily_groups[backup_date][0][1]
            for backup_date in daily_dates
        }
        weekly_markers = {
            weekly_groups[backup_week][0][1]
            for backup_week in weekly_dates
        }
        marker_backups = daily_markers | weekly_markers
        rolling_backups = []

        for backup_record in reversed(backup_records):
            backup_path = backup_record[1]

            if backup_path in marker_backups:
                continue

            rolling_backups.append(backup_path)

            if len(rolling_backups) == self.ROLLING_BACKUP_LIMIT:
                break

        retained_backups = marker_backups | set(rolling_backups)

        for backup_record in backup_records:
            backup_path = backup_record[1]

            if backup_path in retained_backups:
                continue

            try:
                backup_path.unlink()
            except OSError:
                continue

        for backup_record in backup_records:
            backup_path = backup_record[1]

            if backup_path not in retained_backups or not backup_path.exists():
                continue

            marker_names = []

            if backup_path in daily_markers:
                marker_names.append("daily")

            if backup_path in weekly_markers:
                marker_names.append("weekly")

            desired_stem = backup_record[2]

            if marker_names:
                desired_stem = f"{desired_stem}-{'-'.join(marker_names)}"

            desired_path = backup_path.with_name(f"{desired_stem}.json")

            if desired_path == backup_path or desired_path.exists():
                continue

            try:
                backup_path.rename(desired_path)
            except OSError:
                continue

    def save(self):
        if not self.fully_loaded:
            raise RuntimeError(
                "World data is still loading and cannot be saved yet."
            )
        if self.shared_store and self.shared_session:
            self.data["_database"]["last_saved"] = datetime.now(
                timezone.utc
            ).isoformat()
            self.shared_session.data = self.data
            outcome = self.shared_store.save(self.shared_session, "world-builder")
            if not outcome.saved:
                raise RuntimeError(
                    "World Builder found overlapping changes in the shared world data. "
                    "Reload World Builder before saving this record."
                )
            self.data = self.shared_session.data
            self.dirty = False
            self.rebuild_record_indexes()
            self.rebuild_world_index()
            return
        self.validate_database(self.data)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

        if self.database_path.exists():
            self.backup_directory.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            backup_path = self.backup_directory / f"mage_maker-{timestamp}.json"
            shutil.copy2(self.database_path, backup_path)

        self.data["_database"]["last_saved"] = datetime.now(
            timezone.utc
        ).isoformat()
        temporary_path = self.database_path.with_suffix(".json.tmp")

        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as database_file:
            json.dump(self.data, database_file, ensure_ascii=False, indent=2)
            database_file.write("\n")

        os.replace(temporary_path, self.database_path)
        self.prune_backups()
        self.dirty = False
        self.rebuild_record_indexes()
        self.rebuild_world_index()
