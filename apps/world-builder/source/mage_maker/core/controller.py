from copy import deepcopy
from random import randrange

from mage_maker.core.dates import (
    format_date_parts,
    is_at_least_age,
    normalize_date_parts,
    normalize_historical_date_parts,
)
from mage_maker.sections.development.models import (
    DEVELOPMENT_ASSIGNMENT_SETTING_KEY,
    new_development_plan,
    non_magical_development_plan,
    normalize_development_assignment_policy,
    normalize_development_plan,
)
from mage_maker.sections.development.characteristics import (
    normalize_characteristics,
)
from mage_maker.sections.development.initial_bonuses import (
    normalize_initial_bonuses,
)
from mage_maker.sections.development.initial_values import (
    normalize_blood_status,
    normalize_developmental_environment,
    normalize_parental_values,
    require_blood_status_compatible,
    resolved_blood_status,
    resolved_developmental_environment,
    synchronized_family_parental_values,
)
from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
    person_can_give_birth,
)
from mage_maker.sections.family_tree.spouse_relationships import (
    empty_spouse_relationship,
    merge_mate_ids,
    normalize_spouse_relationships,
    reciprocal_relationship,
    relationship_ids,
)
from mage_maker.sections.names.history import empty_name_details, normalize_name_details
from mage_maker.sections.names.timeline import synchronize_name_change_events
from mage_maker.sections.events.models import (
    death_event_person_ids,
    normalize_world_event,
    synchronize_birth_events_from_people,
    synchronize_people_death_records,
)
from mage_maker.sections.events.types import canonical_event_type
from mage_maker.sections.settings.mage_groups import (
    MAGE_GROUPS_SETTING_KEY,
    default_mage_group_id,
    mage_group_definition,
    normalize_mage_groups,
    require_mage_group_id,
)
from mage_maker.sections.timeline.events import (
    normalize_timeline_events,
    synchronize_profile_timeline_events,
)
from mage_maker.sections.timeline.locations import (
    ParentLocationConflict,
    add_long_distance_note,
    born_long_distance_parent_ids,
    born_note_from_events,
    child_parent_location_context,
    ensure_life_start_events,
    remove_long_distance_note,
    starting_location_from_events,
)
from mage_maker.ui.colored_tags import normalize_colored_tags


RECENT_PERSON_STORAGE_KEY = "_recent_people"
RECENT_PERSON_STORAGE_LIMIT = 12
MARRIAGE_EVENT_SOURCE = "spouse_relationship"
ANIMAGUS_CHANCE_DENOMINATOR = 1000


class PeopleController:
    # These fields belong only to the selected person's presentation or
    # development state.  They do not alter family links, life events, blood
    # inheritance, or any other record.  Keeping this list explicit lets
    # ordinary autosaves avoid the intentionally expensive structural
    # reconciliation path below.
    local_profile_fields = frozenset(
        {
            "narrative",
            "notes",
            "canon",
            "player_character",
            "famous_person",
            "unfinished",
            "mage_group_id",
            "tags",
            "board",
            "development_plan",
            "initial_bonuses",
            "characteristics",
        }
    )
    text_fields = (
        "displayed_name",
        "narrative",
        "biological_mother_id",
        "biological_father_id",
        "biological_mother_status",
        "biological_father_status",
        "blood_status",
        "developmental_environment",
        "school",
        "mage_group_id",
        "notes",
    )
    boolean_fields = (
        "deceased",
        "canon",
        "player_character",
        "non_magical",
        "can_give_birth",
        "does_not_have_children",
        "famous_person",
        "animagus",
        "parseltongue",
        "unfinished",
    )
    number_fields = (
        "birth_year",
        "birth_month",
        "birth_day",
        "death_year",
        "death_month",
        "death_day",
    )
    summary_fields = (
        "record_id",
        "displayed_name",
        "birth_year",
        "birth_month",
        "birth_day",
        "deceased",
        "death_year",
        "death_month",
        "death_day",
        "canon",
        "player_character",
        "non_magical",
        "can_give_birth",
        "does_not_have_children",
        "famous_person",
        "animagus",
        "parseltongue",
        "unfinished",
        "mage_group_id",
        "school",
        "name_details",
        "biological_mother_id",
        "biological_father_id",
        "biological_mother_status",
        "biological_father_status",
        "mate_ids",
        "spouse_relationships",
        "blood_status",
        "developmental_environment",
        "parental_values",
        "initial_bonuses",
        "characteristics",
        "created_at",
    )

    def __init__(self, database):
        self.database = database
        self.last_changed_fields = frozenset()

    def list_people(self):
        people = self.database.list_people()
        people.sort(key=self.person_sort_key)
        return people

    def list_people_summaries(self):
        provider = getattr(self.database, "list_people_list_summaries", None)
        if callable(provider):
            summaries = provider()
            # Index format 2 installations created before the expanded family
            # summary omit relationship fields.  Once the canonical document
            # is available, supply those fields only for relationship-heavy
            # views until the disposable index is next rebuilt.
            if (
                getattr(self.database, "fully_loaded", True)
                and summaries
                and "spouse_relationships" not in summaries[0]
            ):
                summaries = [
                    {
                        field_name: deepcopy(person.get(field_name))
                        for field_name in self.summary_fields
                    }
                    for person in self.database.data.get("people", [])
                    if isinstance(person, dict)
                ]
        else:
            stored_people = self.database.data.get("people", [])
            summaries = [
                {
                    field_name: deepcopy(person.get(field_name))
                    for field_name in self.summary_fields
                }
                for person in stored_people
                if isinstance(person, dict)
            ]
        summaries.sort(key=self.person_sort_key)
        return summaries

    def get_people_summaries_by_ids(self, person_ids):
        provider = getattr(self.database, "get_summaries_by_ids", None)
        if callable(provider):
            return provider("people", person_ids)
        requested_ids = {
            str(person_id or "").strip()
            for person_id in person_ids or ()
            if str(person_id or "").strip()
        }
        if not requested_ids:
            return []
        return [
            person
            for person in self.list_people_summaries()
            if str(person.get("record_id", "") or "").strip()
            in requested_ids
        ]

    def list_people_list_summaries(self):
        provider = getattr(
            self.database,
            "list_people_list_summaries",
            None,
        )
        summaries = (
            provider()
            if callable(provider)
            else self.list_people_summaries()
        )
        summaries.sort(key=self.person_sort_key)
        return summaries

    def person_sort_key(self, person):
        birth_year = self.sortable_number(person.get("birth_year"), 10000)
        birth_month = self.sortable_number(person.get("birth_month"), 13)
        birth_day = self.sortable_number(person.get("birth_day"), 32)
        name = str(person.get("displayed_name", "")).casefold()
        return birth_year, birth_month, birth_day, name

    def sortable_number(self, value, fallback):
        if isinstance(value, bool):
            return fallback

        try:
            return int(value)
        except (TypeError, ValueError):
            return fallback

    def get_person(self, record_id):
        return self.database.read_person(record_id)

    def development_assignment_policy(self):
        settings = self.database.data.get(
            "_application_settings",
            {},
        )
        stored_policy = (
            settings.get(DEVELOPMENT_ASSIGNMENT_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )
        return normalize_development_assignment_policy(stored_policy)

    def list_mage_groups(self):
        settings = self.database.data.get(
            "_application_settings",
            {},
        )
        stored_groups = (
            settings.get(MAGE_GROUPS_SETTING_KEY)
            if isinstance(settings, dict)
            else None
        )
        return normalize_mage_groups(stored_groups)

    def default_mage_group_id(self):
        return default_mage_group_id(self.list_mage_groups())

    def mage_group(self, group_id):
        return mage_group_definition(
            group_id,
            self.list_mage_groups(),
        )

    def remember_person_interaction(self, record_id):
        normalized_record_id = str(record_id or "").strip()
        available_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in self.list_people_summaries()
            if str(person.get("record_id", "") or "").strip()
        }

        if normalized_record_id not in available_ids:
            return False

        stored_history = self.database.get_preference(
            RECENT_PERSON_STORAGE_KEY,
            [],
        )
        history = (
            [
                str(stored_record_id or "").strip()
                for stored_record_id in stored_history
                if str(stored_record_id or "").strip()
            ]
            if isinstance(stored_history, list)
            else []
        )
        updated_history = [
            normalized_record_id,
            *[
                stored_record_id
                for stored_record_id in history
                if stored_record_id != normalized_record_id
            ],
        ][:RECENT_PERSON_STORAGE_LIMIT]

        if updated_history == history:
            return False

        self.database.set_preference(
            RECENT_PERSON_STORAGE_KEY,
            updated_history,
        )
        return True

    def recent_person_ids(self, limit=5):
        available_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in self.list_people_summaries()
            if str(person.get("record_id", "") or "").strip()
        }
        stored_history = self.database.get_preference(
            RECENT_PERSON_STORAGE_KEY,
            [],
        )
        candidate_ids = (
            [
                str(stored_record_id or "").strip()
                for stored_record_id in stored_history
                if str(stored_record_id or "").strip()
            ]
            if isinstance(stored_history, list)
            else []
        )
        recent_ids = []

        for candidate_id in candidate_ids:
            if candidate_id not in available_ids:
                continue

            if candidate_id in recent_ids:
                continue

            recent_ids.append(candidate_id)

            if len(recent_ids) >= max(0, int(limit)):
                break

        return recent_ids

    def create_person(self, values):
        creation_values = deepcopy(values)
        starting_location = creation_values.pop("starting_location", None)
        starting_location_id = creation_values.pop(
            "starting_location_id",
            None,
        )
        long_distance_override = self.normalize_boolean(
            creation_values.pop("long_distance_parent_override", False),
            "long_distance_parent_override",
        )
        defaults = {
            "displayed_name": "",
            "name_details": empty_name_details(),
            "narrative": "",
            "birth_year": None,
            "birth_month": None,
            "birth_day": None,
            "deceased": False,
            "death_year": None,
            "death_month": None,
            "death_day": None,
            "canon": False,
            "player_character": False,
            "non_magical": False,
            "can_give_birth": False,
            "does_not_have_children": False,
            "famous_person": False,
            "animagus": False,
            "parseltongue": False,
            "unfinished": True,
            "biological_mother_id": "",
            "biological_father_id": "",
            "biological_mother_status": "unknown",
            "biological_father_status": "unknown",
            "blood_status": "",
            "developmental_environment": "",
            "parental_values": None,
            "initial_bonuses": None,
            "characteristics": None,
            "mate_ids": [],
            "spouse_relationships": [],
            "timeline_events": [],
            "school": "",
            "mage_group_id": self.default_mage_group_id(),
            "development_plan": None,
            "notes": "",
            "tags": [],
            "imported_fields": {},
        }
        defaults.update(creation_values)

        if bool(defaults.get("non_magical")):
            defaults["school"] = ""
            defaults["development_plan"] = (
                non_magical_development_plan(
                    defaults.get("development_plan")
                )
            )
        elif defaults.get("development_plan") in (None, ""):
            defaults["development_plan"] = new_development_plan(
                self.development_assignment_policy()
            )

        normalized = self.normalize_values(defaults)
        normalized = self.reconcile_spouse_fields(normalized)
        normalized = self.canonicalize_parent_states(normalized)
        normalized["blood_status"] = (
            normalize_blood_status(normalized["blood_status"])
            if normalized.get("blood_status")
            else resolved_blood_status(
                normalized,
                self.database.list_people(),
            )
        )
        normalized["developmental_environment"] = (
            normalize_developmental_environment(
                normalized.get("developmental_environment"),
                normalized["blood_status"],
            )
        )
        normalized["parental_values"] = normalize_parental_values(
            normalized.get("parental_values")
        )
        normalized["initial_bonuses"] = normalize_initial_bonuses(
            normalized.get("initial_bonuses")
        )
        normalized["characteristics"] = normalize_characteristics(
            normalized.get("characteristics")
        )

        if normalized["non_magical"]:
            normalized["animagus"] = False
            normalized["parseltongue"] = False
        else:
            normalized["parseltongue"] = bool(
                normalized.get("parseltongue")
                or self.has_parseltongue_parent(normalized)
            )
            if "animagus" not in creation_values:
                normalized["animagus"] = (
                    randrange(ANIMAGUS_CHANCE_DENOMINATOR) == 0
                )

        if normalized["non_magical"]:
            normalized["school"] = ""
            normalized["development_plan"] = (
                non_magical_development_plan(
                    normalized.get("development_plan")
                )
            )

        normalize_historical_date_parts(
            normalized.get("birth_year"),
            normalized.get("birth_month"),
            normalized.get("birth_day"),
            "Birth",
            required_year=False,
        )
        normalized = self.synchronize_life_start_timeline(
            normalized,
            starting_location,
            long_distance_override,
            starting_location_id,
        )
        normalized["timeline_events"] = synchronize_name_change_events(
            normalized["name_details"],
            normalized["timeline_events"],
        )
        normalized["timeline_events"] = synchronize_profile_timeline_events(
            normalized,
            normalized["timeline_events"],
            organizations=self.database.list_records("organizations"),
        )
        self.validate_values(normalized)
        created_person = self.database.create_person(normalized)
        self.synchronize_spouses(
            created_person["record_id"],
            [],
            created_person.get("spouse_relationships", []),
        )
        self.synchronize_coparents(created_person)
        self.synchronize_family_parental_values(
            created_person,
            prefer_anchor=True,
        )
        self.reconcile_child_parent_timelines(created_person, [])
        self.reconcile_child_timeline_events_for_parent(
            created_person["record_id"]
        )
        synchronize_birth_events_from_people(
            self.database.data,
            (created_person["record_id"],),
        )
        self.database.save()
        return self.database.read_person(created_person["record_id"])

    def update_person(
        self,
        record_id,
        values,
        synchronize_birth_event=True,
        save_database=True,
    ):
        current_person = self.get_person(record_id)

        if current_person is None:
            raise KeyError(f"Unknown person record_id: {record_id}")

        update_values = deepcopy(values)
        starting_location = update_values.pop("starting_location", None)
        starting_location_id = update_values.pop(
            "starting_location_id",
            None,
        )
        long_distance_override = self.normalize_boolean(
            update_values.pop("long_distance_parent_override", False),
            "long_distance_parent_override",
        )
        normalized = self.normalize_values(update_values)
        normalized = self.reconcile_spouse_fields(normalized, current_person)

        # Forms submit a complete snapshot, but most autosaves alter only one
        # field.  Compare normalized values so harmless UI representations
        # such as ``"910"`` versus ``910`` do not create false changes.
        current_comparable = self.normalize_values(
            {
                field_name: deepcopy(current_person.get(field_name))
                for field_name in normalized
            }
        )
        current_comparable = self.reconcile_spouse_fields(
            current_comparable,
            current_person,
        )
        changed_fields = {
            field_name
            for field_name, value in normalized.items()
            if current_comparable.get(field_name) != value
        }
        life_start_requested = any(
            value not in (None, "")
            for value in (
                starting_location,
                starting_location_id,
            )
        ) or long_distance_override

        # A focus change with no semantic edit should not create a revision,
        # backup, index rebuild, or cross-page refresh.
        if not changed_fields and not life_start_requested:
            self.last_changed_fields = frozenset()
            return current_person

        self.last_changed_fields = frozenset(changed_fields)

        # Notes, narrative, tags, board presentation, and basic classification
        # cannot affect another record.  Updating only the actual patch makes
        # these common saves O(one person) instead of repeatedly scanning and
        # normalizing the entire world.
        if (
            changed_fields
            and changed_fields <= self.local_profile_fields
            and not life_start_requested
        ):
            patch = {
                field_name: normalized[field_name]
                for field_name in changed_fields
            }
            updated_person = self.database.update_person(record_id, patch)
            if save_database:
                self.database.save(rebuild_indexes=False)
            return self.database.read_person(record_id)

        prospective_person = deepcopy(current_person)
        prospective_person.update(normalized)
        prospective_person = self.canonicalize_parent_states(prospective_person)
        parentage_changed = any(
            prospective_person.get(field_name)
            != current_person.get(field_name)
            for field_name in (
                "biological_mother_id",
                "biological_mother_status",
                "biological_father_id",
                "biological_father_status",
            )
        )

        if parentage_changed and "blood_status" not in normalized:
            people = self.database.list_people()
            prospective_person["blood_status"] = resolved_blood_status(
                prospective_person,
                people,
            )
            prospective_person["developmental_environment"] = (
                resolved_developmental_environment(
                    prospective_person,
                    people,
                )
            )
            normalized["blood_status"] = prospective_person[
                "blood_status"
            ]
            normalized["developmental_environment"] = (
                prospective_person["developmental_environment"]
            )
        else:
            prospective_person["blood_status"] = normalize_blood_status(
                prospective_person.get("blood_status")
            )
            prospective_person["developmental_environment"] = (
                normalize_developmental_environment(
                    prospective_person.get("developmental_environment"),
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

        if prospective_person.get("non_magical"):
            prospective_person["animagus"] = False
            prospective_person["parseltongue"] = False
            prospective_person["school"] = ""
            prospective_person["development_plan"] = (
                non_magical_development_plan(
                    prospective_person.get("development_plan")
                )
            )
        else:
            prospective_person["parseltongue"] = bool(
                prospective_person.get("parseltongue")
                or self.has_parseltongue_parent(prospective_person)
            )
        normalized["animagus"] = bool(prospective_person.get("animagus"))
        normalized["parseltongue"] = bool(
            prospective_person.get("parseltongue")
        )

        normalize_historical_date_parts(
            prospective_person.get("birth_year"),
            prospective_person.get("birth_month"),
            prospective_person.get("birth_day"),
            "Birth",
            required_year=False,
        )
        current_death_signature = (
            bool(current_person.get("deceased")),
            current_person.get("death_year"),
            current_person.get("death_month"),
            current_person.get("death_day"),
        )
        prospective_death_signature = (
            bool(prospective_person.get("deceased")),
            prospective_person.get("death_year"),
            prospective_person.get("death_month"),
            prospective_person.get("death_day"),
        )
        shared_death_exists = self.person_has_shared_death_event(
            record_id
        )

        if shared_death_exists:
            for field_name in (
                "deceased",
                "death_year",
                "death_month",
                "death_day",
            ):
                prospective_person[field_name] = current_person.get(
                    field_name
                )
                normalized[field_name] = current_person.get(field_name)

            prospective_death_signature = current_death_signature

        if (
            prospective_death_signature[0]
            and prospective_death_signature[1] not in (None, "")
            and prospective_death_signature != current_death_signature
        ):
            for shared_event in self.database.list_records("events"):
                if record_id in death_event_person_ids(shared_event):
                    raise ValueError(
                        "This person already has a Death event. Remove it "
                        "before entering a Profile death date."
                    )

        prospective_person = self.synchronize_life_start_timeline(
            prospective_person,
            starting_location,
            long_distance_override,
            starting_location_id,
        )
        prospective_person["timeline_events"] = synchronize_name_change_events(
            prospective_person.get("name_details", empty_name_details()),
            prospective_person["timeline_events"],
        )
        prospective_person["timeline_events"] = (
            synchronize_profile_timeline_events(
                prospective_person,
                prospective_person["timeline_events"],
                create_death_event=not shared_death_exists,
                organizations=self.database.list_records(
                    "organizations"
                ),
            )
        )
        normalized["biological_mother_status"] = prospective_person[
            "biological_mother_status"
        ]
        normalized["biological_father_status"] = prospective_person[
            "biological_father_status"
        ]
        normalized["developmental_environment"] = prospective_person[
            "developmental_environment"
        ]
        normalized["parental_values"] = deepcopy(
            prospective_person["parental_values"]
        )
        normalized["initial_bonuses"] = deepcopy(
            prospective_person["initial_bonuses"]
        )
        normalized["school"] = prospective_person.get("school", "")
        normalized["development_plan"] = deepcopy(
            prospective_person.get("development_plan")
        )
        normalized["timeline_events"] = prospective_person["timeline_events"]
        self.validate_values(prospective_person)
        old_spouse_relationships = normalize_spouse_relationships(
            current_person.get("spouse_relationships", [])
        )
        old_parent_ids = self.parent_ids_from_person(current_person)
        non_magical_changed = bool(
            current_person.get("non_magical")
        ) != bool(prospective_person.get("non_magical"))
        parseltongue_gained = (
            not bool(current_person.get("parseltongue"))
            and bool(prospective_person.get("parseltongue"))
        )
        updated_person = self.database.update_person(record_id, normalized)

        if non_magical_changed and updated_person.get("non_magical"):
            self.remove_person_eminence_associations(record_id)

        if non_magical_changed:
            self.reconcile_child_blood_statuses(record_id)
        if parseltongue_gained:
            self.reconcile_child_parseltongue_statuses(record_id)
        self.synchronize_spouses(
            record_id,
            old_spouse_relationships,
            updated_person.get("spouse_relationships", []),
        )
        self.synchronize_marriage_events(
            record_id,
            old_spouse_relationships,
            updated_person.get("spouse_relationships", []),
        )
        self.synchronize_coparents(updated_person)
        self.synchronize_family_parental_values(
            updated_person,
            prefer_anchor=(
                old_parent_ids
                != self.parent_ids_from_person(updated_person)
            ),
        )
        self.reconcile_child_parent_timelines(updated_person, old_parent_ids)
        self.reconcile_child_timeline_events_for_parent(record_id)

        if synchronize_birth_event:
            synchronize_birth_events_from_people(
                self.database.data,
                (record_id,),
            )

        if save_database:
            self.database.save()
        return self.database.read_person(record_id)

    def delete_person(self, record_id):
        current_person = self.database.read_person(record_id)
        old_parent_ids = self.parent_ids_from_person(current_person)
        deleted_person = self.database.delete_person(record_id)

        for parent_id in old_parent_ids:
            self.reconcile_child_timeline_events_for_parent(parent_id)

        self.database.save()
        return deleted_person

    def person_has_shared_death_event(self, person_id):
        normalized_person_id = str(person_id or "").strip()

        if not normalized_person_id:
            return False

        return any(
            normalized_person_id in death_event_person_ids(event)
            for event in self.database.list_records("events")
        )

    def has_parseltongue_parent(self, person):
        """Return whether either linked biological parent is a Parseltongue."""

        for field_name in (
            "biological_mother_id",
            "biological_father_id",
        ):
            parent_id = str(person.get(field_name, "") or "").strip()
            if not parent_id:
                continue
            parent = self.database.read_person(parent_id)
            if parent is not None and bool(parent.get("parseltongue")):
                return True
        return False

    def reconcile_child_parseltongue_statuses(self, parent_id):
        """Apply the hereditary trait to existing magical children."""

        normalized_parent_id = str(parent_id or "").strip()
        if not normalized_parent_id:
            return
        for child in self.list_people_summaries():
            if normalized_parent_id not in (
                str(child.get("biological_mother_id", "") or ""),
                str(child.get("biological_father_id", "") or ""),
            ):
                continue
            if child.get("non_magical") or child.get("parseltongue"):
                continue
            self.database.update_person(
                child["record_id"],
                {"parseltongue": True},
            )

    def normalize_values(self, values):
        normalized = deepcopy(values)

        for field_name in self.text_fields:
            if field_name in normalized:
                normalized[field_name] = str(normalized[field_name] or "").strip()

        for field_name in self.boolean_fields:
            if field_name in normalized:
                normalized[field_name] = self.normalize_boolean(
                    normalized[field_name],
                    field_name,
                )

        for field_name in self.number_fields:
            if field_name in normalized:
                normalized[field_name] = self.normalize_number(
                    normalized[field_name],
                    field_name,
                )

        if "mate_ids" in normalized:
            normalized["mate_ids"] = self.normalize_identifier_list(
                normalized["mate_ids"]
            )

        if "spouse_relationships" in normalized:
            normalized["spouse_relationships"] = normalize_spouse_relationships(
                normalized["spouse_relationships"]
            )

        if "name_details" in normalized:
            normalized["name_details"] = normalize_name_details(
                normalized["name_details"]
            )

        if "timeline_events" in normalized:
            normalized["timeline_events"] = normalize_timeline_events(
                normalized["timeline_events"]
            )

        if "tags" in normalized:
            normalized["tags"] = normalize_colored_tags(
                normalized["tags"]
            )

        if "development_plan" in normalized:
            normalized["development_plan"] = normalize_development_plan(
                normalized["development_plan"]
            )

        if (
            "blood_status" in normalized
            and normalized["blood_status"]
        ):
            normalized["blood_status"] = normalize_blood_status(
                normalized["blood_status"]
            )

        if "parental_values" in normalized:
            normalized["parental_values"] = (
                normalize_parental_values(
                    normalized["parental_values"]
                )
            )

        if "initial_bonuses" in normalized:
            normalized["initial_bonuses"] = (
                normalize_initial_bonuses(
                    normalized["initial_bonuses"]
                )
            )

        if "characteristics" in normalized:
            normalized["characteristics"] = (
                normalize_characteristics(
                    normalized["characteristics"]
                )
            )

        if "mage_group_id" in normalized:
            normalized["mage_group_id"] = require_mage_group_id(
                normalized["mage_group_id"],
                self.list_mage_groups(),
            )

        return normalized

    def reconcile_spouse_fields(self, values, current_person=None):
        normalized = deepcopy(values)
        current = current_person if isinstance(current_person, dict) else {}

        if "spouse_relationships" in normalized:
            relationships = normalize_spouse_relationships(
                normalized.get("spouse_relationships")
            )
            normalized["spouse_relationships"] = relationships
            normalized["mate_ids"] = relationship_ids(relationships)
            return normalized

        if "mate_ids" in normalized:
            relationships = merge_mate_ids(
                current.get("spouse_relationships", []),
                normalized.get("mate_ids", []),
            )
            normalized["spouse_relationships"] = relationships
            normalized["mate_ids"] = relationship_ids(relationships)

        return normalized

    def canonicalize_parent_states(self, values):
        normalized = deepcopy(values)

        for parent_role in ("mother", "father"):
            id_field = f"biological_{parent_role}_id"
            status_field = f"biological_{parent_role}_status"
            parent_id = str(normalized.get(id_field, "") or "").strip()
            status = str(normalized.get(status_field, "unknown") or "unknown")
            status = status.strip().casefold()

            if status not in ("unknown", "muggle", "person"):
                raise ValueError(
                    "A parent status must be Unknown, Muggle, or a named person."
                )

            normalized[id_field] = parent_id
            normalized[status_field] = "person" if parent_id else (
                "muggle" if status == "muggle" else "unknown"
            )

        return normalized

    def normalize_boolean(self, value, field_name):
        if isinstance(value, bool):
            return value

        normalized = str(value or "").strip().casefold()

        if normalized in ("yes", "true", "1"):
            return True

        if normalized in ("", "no", "false", "0"):
            return False

        raise ValueError(f"{field_name.replace('_', ' ').title()} must be Yes or No.")

    def normalize_number(self, value, field_name):
        if value in (None, ""):
            return None

        if isinstance(value, bool):
            raise ValueError(
                f"{field_name.replace('_', ' ').title()} must be a whole number."
            )

        try:
            return int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name.replace('_', ' ').title()} must be a whole number."
            ) from error

    def normalize_identifier_list(self, values):
        if values in (None, ""):
            return []

        if not isinstance(values, list):
            raise TypeError("Mate assignments must be a list of person identifiers.")

        normalized_ids = []

        for value in values:
            record_id = str(value or "").strip()

            if record_id and record_id not in normalized_ids:
                normalized_ids.append(record_id)

        return normalized_ids

    def validate_values(self, values):
        if not values.get("displayed_name", "").strip():
            raise ValueError("A magician must have a displayed name.")

        normalize_historical_date_parts(
            values.get("birth_year"),
            values.get("birth_month"),
            values.get("birth_day"),
            "Birth",
            required_year=False,
        )
        normalize_historical_date_parts(
            values.get("death_year"),
            values.get("death_month"),
            values.get("death_day"),
            "Death",
            required_year=False,
        )
        normalize_development_plan(values.get("development_plan"))
        normalize_parental_values(values.get("parental_values"))
        normalize_initial_bonuses(values.get("initial_bonuses"))
        normalize_characteristics(values.get("characteristics"))
        require_mage_group_id(
            values.get("mage_group_id"),
            self.list_mage_groups(),
        )
        require_blood_status_compatible(
            values,
            self.database.list_people(),
        )

        self.validate_relationships(values)

    def reconcile_child_blood_statuses(self, parent_id):
        normalized_parent_id = str(parent_id or "").strip()

        if not normalized_parent_id:
            return

        people = self.database.list_people()

        for child in people:
            if normalized_parent_id not in (
                str(child.get("biological_mother_id", "") or ""),
                str(child.get("biological_father_id", "") or ""),
            ):
                continue

            resolved_status = resolved_blood_status(child, people)
            resolved_environment = resolved_developmental_environment(
                {
                    **child,
                    "blood_status": resolved_status,
                },
                people,
            )

            if (
                child.get("blood_status") == resolved_status
                and child.get("developmental_environment", "")
                == resolved_environment
            ):
                continue

            self.database.update_person(
                child["record_id"],
                {
                    "blood_status": resolved_status,
                    "developmental_environment": (
                        resolved_environment
                    ),
                },
            )

    def synchronize_family_parental_values(
        self,
        anchor_person,
        prefer_anchor=False,
    ):
        people = self.database.list_people()
        synchronized_values = synchronized_family_parental_values(
            anchor_person,
            people,
            prefer_anchor=prefer_anchor,
        )

        for record_id, parental_values in synchronized_values.items():
            existing_person = self.database.read_person(record_id)

            if (
                existing_person is None
                or existing_person.get("parental_values")
                == parental_values
            ):
                continue

            self.database.update_person(
                record_id,
                {"parental_values": parental_values},
            )

    def synchronize_life_start_timeline(
        self,
        person,
        requested_starting_location=None,
        long_distance_override=False,
        requested_starting_location_id=None,
    ):
        synchronized = deepcopy(person)
        events = normalize_timeline_events(
            synchronized.get("timeline_events", [])
        )
        starting_location = (
            str(requested_starting_location or "").strip()
            if requested_starting_location is not None
            else starting_location_from_events(events)
        )
        born_note = born_note_from_events(events)
        previous_override_ids = born_long_distance_parent_ids(events)
        manually_selected_birth_location = any(
            event.get("event_type") in ("starting_location", "born")
            and str(
                event.get("birth_location_source", "") or ""
            ).strip()
            == "manual"
            for event in events
        )
        location_context = child_parent_location_context(
            synchronized,
            self.database.list_people(),
            self.database.list_records("events"),
            self.database.list_records("locations"),
        )
        override_parent_ids = []

        if location_context["conflict"]:
            override_is_current = (
                bool(previous_override_ids)
                and previous_override_ids == location_context["parent_ids"]
            )

            if not long_distance_override and not override_is_current:
                raise ParentLocationConflict(
                    synchronized.get("displayed_name", "This child"),
                    location_context["birthing_parent_name"],
                    location_context["birthing_location"],
                    location_context["non_birthing_parent_name"],
                    location_context["non_birthing_location"],
                    location_context["parent_ids"],
                )

            if not manually_selected_birth_location:
                starting_location = location_context[
                    "birthing_location"
                ]

            born_note = add_long_distance_note(born_note)
            override_parent_ids = location_context["parent_ids"]
        else:
            if (
                location_context["inherited_location"]
                and not manually_selected_birth_location
            ):
                starting_location = location_context["inherited_location"]

            born_note = remove_long_distance_note(born_note)

        synchronized["timeline_events"] = ensure_life_start_events(
            synchronized,
            starting_location=starting_location,
            starting_location_id=requested_starting_location_id,
            born_note=born_note,
            long_distance_parent_ids=override_parent_ids,
        )
        return synchronized

    def validate_relationships(self, values):
        record_id = str(values.get("record_id", "") or "")
        mother_id = str(values.get("biological_mother_id", "") or "")
        father_id = str(values.get("biological_father_id", "") or "")
        mate_ids = self.normalize_identifier_list(values.get("mate_ids", []))
        relationship_map = FamilyRelationshipMap(self.database.list_people())

        if record_id and record_id in (mother_id, father_id):
            raise ValueError("A person cannot be their own biological parent.")

        if mother_id and mother_id == father_id:
            raise ValueError(
                "Birthing and non-birthing parents must be different people."
            )

        for parent_id, role_label, required_capability in (
            (mother_id, "birthing parent", True),
            (father_id, "non-birthing parent", False),
        ):
            if not parent_id:
                continue

            parent = relationship_map.person(parent_id)

            if parent is None:
                raise ValueError(f"The selected {role_label} no longer exists.")

            if bool(parent.get("does_not_have_children")):
                raise ValueError(
                    f"The selected {role_label} is marked Does not have "
                    "children and cannot be added as a parent."
                )

            if person_can_give_birth(parent) != required_capability:
                requirement = "checked" if required_capability else "unchecked"
                raise ValueError(
                    f"A {role_label} must have Can give birth {requirement}."
                )

            age_check = is_at_least_age(parent, values, 18)

            if age_check is False:
                raise ValueError(
                    f"The selected {role_label} must be at least 18 when the "
                    "child is born."
                )

            if record_id and parent_id in relationship_map.descendants_of(record_id):
                raise ValueError("A descendant cannot also be a biological parent.")

        current_can_give_birth = person_can_give_birth(values)

        for mate_id in mate_ids:
            if mate_id == record_id:
                raise ValueError("A person cannot be their own mate.")

            mate = relationship_map.person(mate_id)

            if mate is None:
                raise ValueError("A selected mate no longer exists.")

            if person_can_give_birth(mate) == current_can_give_birth:
                raise ValueError(
                    "Mates must have opposite Can give birth assignments."
                )

            if record_id and (
                mate_id in relationship_map.ancestors_of(record_id)
                or mate_id in relationship_map.descendants_of(record_id)
            ):
                raise ValueError("A direct ancestor or descendant cannot be a mate.")

        if record_id:
            for child in self.database.list_people():
                is_parent = record_id in (
                    str(child.get("biological_mother_id", "") or ""),
                    str(child.get("biological_father_id", "") or ""),
                )

                if values.get("does_not_have_children") and is_parent:
                    raise ValueError(
                        "Does not have children cannot be checked while "
                        "this person is linked as a parent."
                    )

                if child.get("biological_mother_id") == record_id and not current_can_give_birth:
                    raise ValueError(
                        "Can give birth must remain checked while this person is listed "
                        "as a birthing parent."
                    )

                if child.get("biological_father_id") == record_id and current_can_give_birth:
                    raise ValueError(
                        "Can give birth must remain unchecked while this person is listed "
                        "as a non-birthing parent."
                    )

                if is_parent and is_at_least_age(values, child, 18) is False:
                    raise ValueError(
                        "This birth date would make the person younger than 18 "
                        f"when {child.get('displayed_name', 'their child')} was born."
                    )

    def remove_person_eminence_associations(self, record_id):
        normalized_record_id = str(record_id or "").strip()

        if not normalized_record_id:
            return False

        changed = False

        for event in self.database.data.get("events", []):
            if not isinstance(event, dict):
                continue

            earned_ids = event.get("eminence_person_ids", [])

            if isinstance(earned_ids, list) and normalized_record_id in earned_ids:
                event["eminence_person_ids"] = [
                    person_id
                    for person_id in earned_ids
                    if person_id != normalized_record_id
                ]
                changed = True

            skills = event.get("eminence_skills")

            if isinstance(skills, dict) and normalized_record_id in skills:
                skills.pop(normalized_record_id, None)
                changed = True

        for organization in self.database.data.get("organizations", []):
            if not isinstance(organization, dict):
                continue

            for event in organization.get("events", []):
                if not isinstance(event, dict):
                    continue

                earned_ids = event.get("eminence_person_ids", [])

                if isinstance(earned_ids, list) and normalized_record_id in earned_ids:
                    event["eminence_person_ids"] = [
                        person_id
                        for person_id in earned_ids
                        if person_id != normalized_record_id
                    ]
                    changed = True

                skills = event.get("eminence_skills")

                if isinstance(skills, dict) and normalized_record_id in skills:
                    skills.pop(normalized_record_id, None)
                    changed = True

        if changed:
            self.database.dirty = True

        return changed

    def synchronize_spouses(
        self,
        record_id,
        old_spouse_relationships,
        new_spouse_relationships,
    ):
        old_relationships = normalize_spouse_relationships(
            old_spouse_relationships
        )
        new_relationships = normalize_spouse_relationships(
            new_spouse_relationships
        )
        old_by_id = {
            relationship["person_id"]: relationship
            for relationship in old_relationships
        }
        new_by_id = {
            relationship["person_id"]: relationship
            for relationship in new_relationships
        }

        for mate_id in set(old_by_id) | set(new_by_id):
            mate = self.database.read_person(mate_id)

            if mate is None:
                continue

            reciprocal_relationships = normalize_spouse_relationships(
                mate.get("spouse_relationships", [])
            )
            reciprocal_relationships = [
                relationship
                for relationship in reciprocal_relationships
                if relationship["person_id"] != record_id
            ]

            if mate_id in new_by_id:
                reciprocal_relationships.append(
                    reciprocal_relationship(new_by_id[mate_id], record_id)
                )

            self.database.update_person(
                mate_id,
                {
                    "mate_ids": relationship_ids(reciprocal_relationships),
                    "spouse_relationships": reciprocal_relationships,
                },
            )

    def synchronize_marriage_events(
        self,
        record_id,
        old_spouse_relationships,
        new_spouse_relationships,
    ):
        selected_person_id = str(record_id or "").strip()

        if not selected_person_id:
            return False

        old_relationships_by_id = {
            relationship["person_id"]: relationship
            for relationship in normalize_spouse_relationships(
                old_spouse_relationships
            )
        }
        stored_events = self.database.list_records("events")
        marriage_events_by_pair = {}
        automatic_events_by_pair = {}

        for event in stored_events:
            if canonical_event_type(event.get("event_type")) != "got_married":
                continue

            person_ids = list(
                dict.fromkeys(
                    str(person_id or "").strip()
                    for person_id in event.get("person_ids", [])
                    if str(person_id or "").strip()
                )
            )

            if len(person_ids) != 2 or selected_person_id not in person_ids:
                continue

            pair = tuple(sorted(person_ids))
            marriage_events_by_pair.setdefault(pair, event)

            if (
                str(event.get("automatic_source", "") or "").strip()
                == MARRIAGE_EVENT_SOURCE
            ):
                automatic_events_by_pair[pair] = event

        changed = False

        for relationship in normalize_spouse_relationships(
            new_spouse_relationships
        ):
            if not relationship["married"]:
                continue

            mate_id = relationship["person_id"]
            pair = tuple(sorted((selected_person_id, mate_id)))
            marriage_date = format_date_parts(
                relationship.get("marriage_year"),
                relationship.get("marriage_month"),
                relationship.get("marriage_day"),
                unknown="",
            )
            automatic_event = automatic_events_by_pair.get(pair)
            relationship_changed = (
                old_relationships_by_id.get(mate_id) != relationship
            )

            if automatic_event is not None:
                if relationship_changed:
                    self.database.update_record(
                        "events",
                        automatic_event["record_id"],
                        {
                            "event_type": "got_married",
                            "title": "Marriage",
                            "date": marriage_date,
                            "person_ids": list(pair),
                            "automatic_source": MARRIAGE_EVENT_SOURCE,
                        },
                    )
                    changed = True

                continue

            if pair in marriage_events_by_pair:
                continue

            created_event = self.database.create_record(
                "events",
                normalize_world_event(
                    {
                        "event_type": "got_married",
                        "title": "Marriage",
                        "date": marriage_date,
                        "description": "",
                        "person_ids": list(pair),
                        "witness_person_ids": [],
                        "affected_person_ids": [],
                        "eminence_person_ids": [],
                        "eminence_skills": {},
                        "period_names": [],
                        "location_ids": [],
                        "locked_location_ids": [],
                        "organization_id": "",
                        "organization_name": "",
                        "automatic_source": MARRIAGE_EVENT_SOURCE,
                    }
                ),
            )
            marriage_events_by_pair[pair] = created_event
            automatic_events_by_pair[pair] = created_event
            changed = True

        return changed

    def synchronize_mates(self, record_id, old_mate_ids, new_mate_ids):
        old_relationships = merge_mate_ids([], old_mate_ids)
        new_relationships = merge_mate_ids([], new_mate_ids)
        self.synchronize_spouses(record_id, old_relationships, new_relationships)

    def synchronize_coparents(self, child):
        mother_id = str(child.get("biological_mother_id", "") or "").strip()
        father_id = str(child.get("biological_father_id", "") or "").strip()

        if not mother_id or not father_id or mother_id == father_id:
            return

        mother = self.database.read_person(mother_id)
        father = self.database.read_person(father_id)

        if mother is None or father is None:
            return

        mother_relationships = merge_mate_ids(
            mother.get("spouse_relationships", []),
            mother.get("mate_ids", []),
        )
        father_relationships = merge_mate_ids(
            father.get("spouse_relationships", []),
            father.get("mate_ids", []),
        )
        mother_mates = relationship_ids(mother_relationships)
        father_mates = relationship_ids(father_relationships)

        if father_id not in mother_mates:
            mother_mates.append(father_id)
            mother_relationships.append(empty_spouse_relationship(father_id))
            self.database.update_person(
                mother_id,
                {
                    "mate_ids": mother_mates,
                    "spouse_relationships": mother_relationships,
                },
            )

        if mother_id not in father_mates:
            father_mates.append(mother_id)
            father_relationships.append(empty_spouse_relationship(mother_id))
            self.database.update_person(
                father_id,
                {
                    "mate_ids": father_mates,
                    "spouse_relationships": father_relationships,
                },
            )

    def parent_ids_from_person(self, person):
        if not isinstance(person, dict):
            return []

        return self.normalize_identifier_list(
            [
                person.get("biological_mother_id"),
                person.get("biological_father_id"),
            ]
        )

    def reconcile_child_parent_timelines(self, child, previous_parent_ids):
        parent_ids = self.normalize_identifier_list(previous_parent_ids)

        for parent_id in self.parent_ids_from_person(child):
            if parent_id not in parent_ids:
                parent_ids.append(parent_id)

        for parent_id in parent_ids:
            self.reconcile_child_timeline_events_for_parent(parent_id)

    def reconcile_child_timeline_events_for_parent(self, parent_id):
        parent = self.database.read_person(parent_id)

        if parent is None:
            return

        existing_events = normalize_timeline_events(
            parent.get("timeline_events", [])
        )
        retained_events = [
            event
            for event in existing_events
            if event.get("automatic_source") != "child_assignment"
        ]
        normalized_events = normalize_timeline_events(retained_events)

        if normalized_events != existing_events:
            self.database.update_person(
                parent_id,
                {"timeline_events": normalized_events},
            )
