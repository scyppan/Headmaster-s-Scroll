import json
import os
import shutil
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

from mage_maker.sections.development.models import (
    DEVELOPMENT_ASSIGNMENT_SETTING_KEY,
    migrated_development_plan,
    normalize_development_assignment_policy,
    normalize_development_plan,
)
from mage_maker.sections.development.initial_bonuses import (
    normalize_initial_bonuses,
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
)
from mage_maker.sections.timeline.locations import ensure_life_start_events
from mage_maker.sections.events.models import normalize_world_events
from mage_maker.sections.settings.mage_groups import (
    MAGE_GROUPS_SETTING_KEY,
    normalize_mage_group_id,
    normalize_mage_groups,
    require_mage_group_id,
)


class JsonDatabase:
    def __init__(self, database_path):
        self.database_path = Path(database_path)
        self.backup_directory = self.database_path.parent / "backups"
        self.data = {}
        self.dirty = False

    def load(self):
        with self.database_path.open("r", encoding="utf-8") as database_file:
            loaded_data = json.load(database_file)

        migrated = self.migrate_database(loaded_data)
        collections_added = self.ensure_application_collections(loaded_data)
        self.validate_database(loaded_data)
        self.data = loaded_data
        self.dirty = migrated or collections_added

    def ensure_application_collections(self, database_data):
        changed = False

        for collection_name in ("locations", "organizations", "events"):
            if collection_name not in database_data:
                database_data[collection_name] = []
                changed = True

        return changed

    def migrate_database(self, database_data):
        if not isinstance(database_data, dict):
            return False

        metadata = database_data.get("_database", {})

        if not isinstance(metadata, dict):
            return False

        schema_version = metadata.get("schema_version")

        if not isinstance(schema_version, int) or schema_version >= 17:
            return False

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

        metadata["schema_version"] = 17
        metadata["database_version"] = "0.17.0"
        database_data["_database"] = metadata

        return migrated

    def validate_database(self, database_data):
        if not isinstance(database_data, dict):
            raise TypeError("The database root must be a JSON object.")

        if not isinstance(database_data.get("people"), list):
            raise TypeError("The database must contain a people collection.")

        for collection_name in ("locations", "organizations", "events"):
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

        mage_groups = normalize_mage_groups(
            settings[MAGE_GROUPS_SETTING_KEY]
        )
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
                database_data["people"],
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

            normalize_development_plan(person.get("development_plan"))
            normalize_timeline_events(person.get("timeline_events", []))

        for collection_name in ("locations", "organizations", "events"):
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

        normalize_world_events(database_data["events"])

    def list_people(self):
        return deepcopy(self.data["people"])

    def read_person(self, record_id):
        for person in self.data["people"]:
            if person.get("record_id") == record_id:
                return deepcopy(person)

        return None

    def create_person(self, values):
        if not isinstance(values, dict):
            raise TypeError("A person must be a dictionary.")

        person = deepcopy(values)
        person.setdefault("record_id", str(uuid.uuid4()))
        settings = self.data.get("_application_settings", {})
        assignment_policy = (
            settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )
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

        current_time = datetime.now(timezone.utc).isoformat()
        person.setdefault("created_at", current_time)
        person["last_updated"] = current_time
        self.data["people"].append(person)
        self.dirty = True

        return deepcopy(person)

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
            person.update(deepcopy(values))
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

            return deepcopy(person)

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
        for index, person in enumerate(self.data["people"]):
            if person.get("record_id") != record_id:
                continue

            deleted_person = self.data["people"].pop(index)

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
                event["person_ids"] = [
                    person_id
                    for person_id in event.get("person_ids", [])
                    if person_id != record_id
                ]

                retained_events.append(event)

            self.data["events"] = retained_events

            self.dirty = True

            return deepcopy(deleted_person)

        raise KeyError(f"Unknown person record_id: {record_id}")

    def list_records(self, collection_name):
        if collection_name not in ("locations", "organizations", "events"):
            raise KeyError(f"Unknown application collection: {collection_name}")

        return deepcopy(self.data[collection_name])

    def read_record(self, collection_name, record_id):
        for record in self.list_records(collection_name):
            if record.get("record_id") == record_id:
                return record

        return None

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
        return deepcopy(record)

    def update_record(self, collection_name, record_id, values):
        if not isinstance(values, dict):
            raise TypeError("Database record changes must be a dictionary.")

        if "record_id" in values and values["record_id"] != record_id:
            raise ValueError("A database record_id cannot be changed.")

        for record in self.data[collection_name]:
            if record.get("record_id") != record_id:
                continue

            record.update(deepcopy(values))
            record["last_updated"] = datetime.now(timezone.utc).isoformat()
            self.dirty = True
            return deepcopy(record)

        raise KeyError(f"Unknown {collection_name} record_id: {record_id}")

    def delete_record(self, collection_name, record_id):
        for index, record in enumerate(self.data[collection_name]):
            if record.get("record_id") != record_id:
                continue

            deleted_record = self.data[collection_name].pop(index)
            self.dirty = True
            return deepcopy(deleted_record)

        raise KeyError(f"Unknown {collection_name} record_id: {record_id}")

    def save(self):
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
        self.dirty = False
