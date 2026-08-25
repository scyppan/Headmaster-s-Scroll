from copy import deepcopy

from mage_maker.core.dates import (
    format_date_parts,
    format_line_item_date,
    historical_year_distance,
    historical_days_in_month,
    historical_year_after,
    is_at_least_age,
)
from mage_maker.sections.development.models import (
    ensure_adult_year_records,
    job_assignment_active_on,
    job_date_tuple,
    new_job_record,
    normalize_development_plan,
    normalize_job_record,
    normalize_job_records,
    person_job_availability_window,
    require_job_position_available,
    require_person_job_available,
)
from mage_maker.sections.development.event_eminence import (
    apply_event_eminence_updates,
    prepare_event_eminence_updates,
    suggested_event_eminence_skill,
)
from mage_maker.sections.events.models import (
    BIRTH_EVENT_SOURCE,
    BIRTH_EVENT_TYPE,
    DEATH_EVENT_TYPES,
    GHOST_EVENT_TYPE,
    birth_event_baby_ids,
    birth_event_person_ids,
    death_event_person_ids,
    event_linked_person_ids,
    normalize_world_event,
    normalize_unnamed_victim_count,
    normalize_world_event_date,
    normalize_world_events,
    split_world_event_date,
    synchronize_birth_events_from_people,
    synchronize_people_death_records,
    world_event_date_is_on_or_after,
    world_event_sort_key,
    world_event_year,
)
from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
    person_can_give_birth,
)
from mage_maker.sections.family_tree.spouse_relationships import (
    empty_spouse_relationship,
    normalize_spouse_relationships,
    relationship_ids,
)
from mage_maker.sections.books.models import (
    book_publication_event_id,
    normalize_book_record,
)
from mage_maker.sections.events.types import (
    canonical_event_type,
    event_type_label,
    event_type_is_person_only,
)
from mage_maker.sections.items.models import (
    item_current_holder,
    item_passage_sort_key,
    item_possessor_ids_on_date,
    normalize_item_passage,
    normalize_item_record,
    normalize_item_records,
)
from mage_maker.sections.items.links import (
    ITEM_EVENT_NEW_OWNER_LINK_TYPES,
    item_event_new_owner,
    item_event_link_type,
    item_event_ownership_method,
    normalize_item_event_link_type,
    normalize_item_event_link_types,
    normalize_item_event_new_owner,
    normalize_item_event_new_owners,
)
from mage_maker.sections.locations.models import (
    ancestor_locations,
    founding_event_title,
    location_foundation_event_state,
    recent_location_label,
    synchronize_location_extinction_records,
)
from mage_maker.sections.organizations.controller import (
    ORGANIZATION_EVENT_FOUNDING,
    normalize_organization_jobs,
    normalize_organization_events,
    normalize_organization_record,
    organization_context_label,
    organization_event_as_world_event,
    organization_event_from_world_event,
    organization_event_world_id,
    organization_events_as_world_events,
    synchronize_school_campus_locations,
)
from mage_maker.sections.settings.mage_groups import (
    mage_group_definition,
    normalize_mage_groups,
)
from mage_maker.sections.timeline.events import normalize_timeline_events


RECENT_ASSOCIATION_STORAGE_KEY = "_recent_event_associations"
RECENT_ASSOCIATION_STORAGE_LIMIT = 12
RECENT_PERSON_STORAGE_KEY = "_recent_people"
RECENT_LOCATION_STORAGE_KEY = "_recent_locations"
RECENT_WORLD_LOCATION_ID = "__mage_maker_world__"
RETAINED_DEATH_STORAGE_KEY = "retained_item_death_events"


class DeathEventReplacementRequired(ValueError):
    def __init__(self, person_ids):
        self.person_ids = list(dict.fromkeys(person_ids or ()))
        person_word = "person" if len(self.person_ids) == 1 else "people"
        super().__init__(
            f"The selected {person_word} already has a Death event."
        )


class EventController:
    def __init__(
        self,
        database,
        people_provider,
        location_provider,
        period_provider,
        location_creator=None,
        people_creator=None,
        mage_groups_provider=None,
        people_summary_provider=None,
        game_database=None,
    ):
        self.database = database
        self.people_provider = people_provider
        self.location_provider = location_provider
        self.period_provider = period_provider
        self.location_creator = location_creator
        self.people_creator = people_creator
        self.mage_groups_provider = mage_groups_provider
        self.people_summary_provider = people_summary_provider
        self.game_database = game_database
        self._event_cache = None
        self._event_cache_revision = None
        self._events_by_record_id = {}
        self._events_by_person_id = {}
        self._events_by_location_id = {}
        self._events_by_item_id = {}
        self._events_by_named_creature_id = {}
        self._eminence_points_by_person_id = {}
        self._people_options_cache = None
        self._people_options_by_id_cache = {}
        self._people_options_cache_revision = None
        self._organization_records_cache = None
        self._organization_records_cache_revision = None
        self._eminence_eligible_ids_cache = None
        self._eminence_eligible_ids_cache_revision = None
        self._deferred_save_owner = None
        self._deferred_save_after_id = None
        self._deferred_save_error_command = None

    def cancel_deferred_save(self):
        """Cancel only the timer; already-applied edits remain database-dirty."""
        owner = self._deferred_save_owner
        after_id = self._deferred_save_after_id
        self._deferred_save_owner = None
        self._deferred_save_after_id = None
        self._deferred_save_error_command = None
        if owner is None or after_id is None:
            return
        try:
            owner.after_cancel(after_id)
        except Exception:
            pass

    def schedule_deferred_save(
        self,
        owner,
        error_command=None,
        delay_ms=3000,
    ):
        """Coalesce event edits into one full canonical world-file write."""
        self.cancel_deferred_save()
        self._deferred_save_owner = owner
        self._deferred_save_error_command = error_command
        try:
            self._deferred_save_after_id = owner.after(
                max(500, int(delay_ms)),
                self.flush_deferred_save,
            )
        except Exception:
            self._deferred_save_owner = None
            self._deferred_save_after_id = None
            self._deferred_save_error_command = None

    def flush_deferred_save(self):
        owner = self._deferred_save_owner
        error_command = self._deferred_save_error_command
        self._deferred_save_owner = None
        self._deferred_save_after_id = None
        self._deferred_save_error_command = None
        if not getattr(self.database, "dirty", False):
            return True
        try:
            self.database.save()
        except Exception as error:
            # Keep the database dirty so centralized shutdown still offers a
            # retry. Surface the failure without restoring a hot retry loop.
            if callable(error_command):
                try:
                    error_command(f"Could not save event changes: {error}")
                except Exception:
                    pass
            return False
        return True

    def character_control_link_options(self, event_type):
        """Searchable stable-ID choices for teaching and creature events."""
        event_type = str(event_type or "").strip()
        collection_map = {
            "taught_spell": ("spells",),
            "taught_proficiency": ("proficiencies",),
            "taught_recipe": (
                "recipes", "potions", "preparations", "foods_and_drinks"
            ),
            "invented_spell": ("spells",),
            "invented_proficiency": ("proficiencies",),
            "invented_recipe": (
                "recipes", "potions", "preparations", "foods_and_drinks"
            ),
        }
        options = []
        if event_type in collection_map and self.game_database is not None:
            for collection in collection_map[event_type]:
                for record in self.game_database.collection(collection):
                    record_id = str(record.get("record_id", "") or "").strip()
                    name = str(record.get("name") or record.get("title") or "").strip()
                    if record_id and name:
                        options.append({
                            "value": record_id,
                            "label": name,
                            "group": collection.replace("_", " ").title(),
                            "collection": collection,
                            "search_text": " ".join(str(record.get(key, "") or "") for key in ("name", "title", "skill", "subtype", "tradition", "description")),
                        })
        elif event_type in {"tamed_creature", "bonded_creature", "irked_creature"}:
            for record in self.database.list_records("named_creatures"):
                record_id = str(record.get("record_id", "") or "").strip()
                name = str(record.get("name", "") or "").strip()
                if record_id and name:
                    options.append({
                        "value": record_id,
                        "label": name,
                        "group": "Named creatures",
                        "collection": "named_creatures",
                        "search_text": " ".join((name, str(record.get("species_name", "") or ""))),
                    })
        elif event_type == "published_book":
            for record in self.database.list_records("books"):
                record_id = str(record.get("record_id", "") or "").strip()
                title = str(record.get("title", "") or "").strip()
                if record_id and title:
                    options.append({
                        "value": record_id,
                        "label": title,
                        "group": "Books",
                        "collection": "books",
                        "search_text": " ".join(
                            str(record.get(key, "") or "")
                            for key in (
                                "title",
                                "author_name",
                                "description",
                                "primary_category",
                            )
                        ),
                    })
        return sorted(options, key=lambda item: (item["label"].casefold(), item["value"]))

    def upsert_book_publication_event(self, event, save_database=True):
        """Make the selected book's single publication event authoritative."""
        book_ids = list(event.get("book_ids", []) or [])
        if len(book_ids) != 1:
            raise ValueError(
                "A Published a book event must link exactly one book."
            )

        book_id = str(book_ids[0] or "").strip()
        book = self.database.read_record("books", book_id)
        if book is None:
            raise ValueError("The selected book no longer exists.")

        prepared_book = deepcopy(book)
        prepared_book["publication_date"] = str(
            event.get("date", "") or ""
        ).strip()
        prepared_book["publication_event_id"] = (
            book_publication_event_id(book_id)
        )

        author_ids = list(event.get("person_ids", []) or [])
        if author_ids:
            author_id = str(author_ids[0] or "").strip()
            author = self.database.read_record("people", author_id)
            if author is None:
                raise ValueError("The selected author no longer exists.")
            prepared_book["author_person_id"] = author_id
            prepared_book["author_name"] = str(
                author.get("displayed_name", "") or ""
            ).strip()

        location_ids = list(event.get("location_ids", []) or [])
        prepared_book["publication_location_id"] = (
            str(location_ids[0] or "").strip() if location_ids else ""
        )
        prepared_book = normalize_book_record(prepared_book)
        self.database.update_record("books", book_id, prepared_book)

        event_id = prepared_book["publication_event_id"]
        prepared_event = deepcopy(event)
        prepared_event.update(
            {
                "record_id": event_id,
                "event_type": "published_book",
                "book_ids": [book_id],
                "book_title": prepared_book["title"],
                "book_author_name": prepared_book["author_name"],
            }
        )
        if str(prepared_event.get("title", "") or "").strip() in (
            "",
            "Published a book",
            "Published book",
        ):
            prepared_event["title"] = (
                f"Published {prepared_book['title']}"
            )
        prepared_event = normalize_world_event(prepared_event)
        current = self.get_event(event_id)
        self.validate_associations(prepared_event, current)
        if current is None:
            stored = self.database.create_record("events", prepared_event)
        else:
            stored = self.database.update_record(
                "events", event_id, prepared_event
            )
        self.invalidate_event_cache()
        self.remember_associations(stored)
        if save_database:
            self.database.save()
        return normalize_world_event(stored)

    def people_summaries(self):
        if callable(self.people_summary_provider):
            return self.people_summary_provider()

        return self.people_provider()

    def people_summaries_by_ids(self, person_ids=()):
        requested_ids = list(
            dict.fromkeys(
                str(person_id or "").strip()
                for person_id in person_ids or ()
                if str(person_id or "").strip()
            )
        )
        if not requested_ids:
            return []
        provider = getattr(self.database, "get_summaries_by_ids", None)
        if callable(provider):
            return provider("people", requested_ids)
        requested_id_set = set(requested_ids)
        return [
            person
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
            in requested_id_set
        ]

    def invalidate_event_cache(self):
        self._event_cache = None
        self._event_cache_revision = None
        self._events_by_record_id = {}
        self._events_by_person_id = {}
        self._events_by_location_id = {}
        self._events_by_item_id = {}
        self._events_by_named_creature_id = {}
        self._eminence_points_by_person_id = {}
        self._eminence_eligible_ids_cache = None
        self._eminence_eligible_ids_cache_revision = None

    def ensure_event_cache(self):
        database_revision = getattr(self.database, "revision", None)
        cacheable = isinstance(database_revision, int)

        if (
            self._event_cache is not None
            and cacheable
            and database_revision == self._event_cache_revision
        ):
            return

        stored_events = self.database.list_records("events")
        organization_events = organization_events_as_world_events(
            self.database.list_records("organizations")
        )
        eligible_person_ids = self.eminence_eligible_person_ids()
        normalized_events = normalize_world_events(
            [
                self.apply_title_rules(event)
                for event in [*stored_events, *organization_events]
            ]
        )
        events_by_record_id = {}
        events_by_person_id = {}
        events_by_location_id = {}
        events_by_item_id = {}
        events_by_named_creature_id = {}
        eminence_points_by_person_id = {}

        for event in normalized_events:
            awarded_person_ids = [
                person_id
                for person_id in event.get("eminence_person_ids", [])
                if person_id in eligible_person_ids
            ]
            event["eminence_person_ids"] = awarded_person_ids
            event["eminence_skills"] = {
                person_id: skill
                for person_id, skill in event.get(
                    "eminence_skills",
                    {},
                ).items()
                if person_id in awarded_person_ids
            }
            events_by_record_id[event["record_id"]] = event

            for person_id in event_linked_person_ids(event):
                events_by_person_id.setdefault(person_id, []).append(event)

            for person_id in awarded_person_ids:
                eminence_points_by_person_id[person_id] = (
                    eminence_points_by_person_id.get(person_id, 0) + 1
                )

            for location_id in event.get("location_ids", []):
                events_by_location_id.setdefault(location_id, []).append(event)

            for item_id in event.get("item_ids", []):
                events_by_item_id.setdefault(item_id, []).append(event)

            named_creature_id = str(
                event.get("named_creature_id", "") or ""
            ).strip()
            if named_creature_id:
                events_by_named_creature_id.setdefault(
                    named_creature_id, []
                ).append(event)

        self._event_cache = normalized_events
        self._events_by_record_id = events_by_record_id
        self._events_by_person_id = events_by_person_id
        self._events_by_location_id = events_by_location_id
        self._events_by_item_id = events_by_item_id
        self._events_by_named_creature_id = events_by_named_creature_id
        self._eminence_points_by_person_id = eminence_points_by_person_id
        self._event_cache_revision = database_revision

    def list_events(self):
        self.ensure_event_cache()
        return deepcopy(self._event_cache)

    def get_event(self, record_id):
        selected_id = str(record_id or "").strip()
        record_reader = getattr(self.database, "read_record", None)

        if callable(record_reader):
            selected_event = record_reader("events", selected_id)

            if selected_event is not None:
                return self.with_eligible_eminence(
                    normalize_world_event(
                        self.apply_title_rules(selected_event)
                    )
                )

        self.ensure_event_cache()
        selected_event = self._events_by_record_id.get(selected_id)
        return deepcopy(selected_event) if selected_event is not None else None

    def events_for_item(self, item_id):
        selected_item_id = str(item_id or "").strip()

        if not selected_item_id:
            return []

        self.ensure_event_cache()
        matching_events = list(
            self._events_by_item_id.get(selected_item_id, [])
        )
        matching_events.sort(key=world_event_sort_key)
        return deepcopy(matching_events)

    def events_for_named_creature(self, named_creature_id):
        selected_id = str(named_creature_id or "").strip()
        if not selected_id:
            return []
        linked_reader = getattr(self.database, "get_linked_records", None)
        if callable(linked_reader):
            matching_events = [
                normalize_world_event(self.apply_title_rules(event))
                for event in linked_reader(
                    "events", selected_id, "named_creatures"
                )
            ]
            matching_events.sort(key=world_event_sort_key)
            return deepcopy(matching_events)
        self.ensure_event_cache()
        matching_events = list(
            self._events_by_named_creature_id.get(selected_id, [])
        )
        matching_events.sort(key=world_event_sort_key)
        return deepcopy(matching_events)

    def item_options(
        self,
        possessor_person_ids=None,
        on_date="",
    ):
        items = self.item_records()
        items.sort(key=self.item_option_sort_key)
        options = []
        restricted_person_ids = (
            {
                str(person_id or "").strip()
                for person_id in possessor_person_ids or ()
                if str(person_id or "").strip()
            }
            if possessor_person_ids is not None
            else None
        )
        people_names_by_id = (
            {
                str(person.get("record_id", "") or "").strip(): str(
                    person.get("displayed_name", "")
                    or "Unknown person"
                ).strip()
                for person in self.people_summaries()
                if isinstance(person, dict)
                and str(person.get("record_id", "") or "").strip()
            }
            if restricted_person_ids is not None
            else {}
        )

        for item in items:
            if restricted_person_ids is not None:
                possessor_ids = item_possessor_ids_on_date(
                    item,
                    on_date,
                )

                if not restricted_person_ids.intersection(possessor_ids):
                    continue

                holder_names = [
                    people_names_by_id.get(
                        person_id,
                        "Unknown person",
                    )
                    for person_id in possessor_ids
                    if person_id in restricted_person_ids
                ]
                holder_detail = (
                    "Held by " + ", ".join(holder_names)
                )
            else:
                holder = item_current_holder(item)
                holder_detail = str(
                    holder.get("person_name", "Unpossessed")
                    or "Unpossessed"
                ).strip()

            options.append(
                {
                    "value": item["record_id"],
                    "label": item["name"],
                    "detail": (
                        f"{item['category']} · "
                        f"{holder_detail}"
                    ),
                }
            )

        return options

    def item_records(self):
        if self.database is None:
            return []

        try:
            stored_items = self.database.list_records("items")
        except (KeyError, TypeError):
            return []

        return normalize_item_records(stored_items)

    def synchronize_retained_item_events_for_deaths(self):
        if self.database is None:
            return False

        people = [
            person
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        ]
        items = self.item_records()

        if not people or not items:
            return False

        settings = self.database.data.get("_application_settings", {})
        normalized_settings = (
            deepcopy(settings) if isinstance(settings, dict) else {}
        )
        stored_processed = normalized_settings.get(
            RETAINED_DEATH_STORAGE_KEY,
            {},
        )
        processed = (
            dict(stored_processed)
            if isinstance(stored_processed, dict)
            else {}
        )
        self.ensure_event_cache()
        events = self._event_cache
        generated_events_by_pair = {}
        events_by_item_id = {}
        items_by_person_id = {}

        for item in items:
            item_person_ids = {
                str(passage.get("person_id", "") or "").strip()
                for passage in item.get("passage_history", [])
                if str(passage.get("person_id", "") or "").strip()
            }

            for item_person_id in item_person_ids:
                items_by_person_id.setdefault(
                    item_person_id,
                    [],
                ).append(item)

        for event in events:
            generated_person_id = str(
                event.get("retained_death_person_id", "") or ""
            ).strip()
            generated_item_id = str(
                event.get("retained_death_item_id", "") or ""
            ).strip()

            if generated_person_id and generated_item_id:
                generated_events_by_pair[
                    (generated_person_id, generated_item_id)
                ] = event

            for item_id in event.get("item_ids", []):
                events_by_item_id.setdefault(item_id, []).append(event)

        changed = False
        processed_changed = False

        for person in people:
            person_id = str(person.get("record_id", "") or "").strip()
            death_year = person.get("death_year")

            if death_year in (None, ""):
                continue

            try:
                death_date = normalize_world_event_date(
                    format_date_parts(
                        death_year,
                        person.get("death_month"),
                        person.get("death_day"),
                        unknown="",
                    )
                )
            except (TypeError, ValueError):
                continue

            death_year_text, death_month_text, death_day_text = (
                split_world_event_date(death_date)
            )
            person_name = str(
                person.get("displayed_name", "") or "Unnamed person"
            ).strip()

            for item in items_by_person_id.get(person_id, []):
                item_id = item["record_id"]
                pair_key = f"{person_id}:{item_id}"
                generated_event = generated_events_by_pair.get(
                    (person_id, item_id)
                )

                if person_id not in item_possessor_ids_on_date(
                    item,
                    death_date,
                ):
                    if generated_event is not None:
                        event_id = str(
                            generated_event.get("record_id", "") or ""
                        ).strip()

                        if event_id:
                            self.database.delete_record("events", event_id)
                            changed = True

                        if pair_key in processed:
                            processed.pop(pair_key, None)
                            processed_changed = True

                    continue

                explicit_event_found = False

                for event in events_by_item_id.get(item_id, []):
                    if event.get("retained_death_person_id"):
                        continue

                    event_date = str(event.get("date", "") or "").strip()

                    if not event_date:
                        continue

                    event_year, event_month, event_day = (
                        split_world_event_date(event_date)
                    )

                    if event_year != death_year_text:
                        continue

                    if (
                        death_month_text
                        and event_month != death_month_text
                    ):
                        continue

                    if death_day_text and event_day != death_day_text:
                        continue

                    explicit_event_found = True
                    break

                if generated_event is not None:
                    event_id = str(
                        generated_event.get("record_id", "") or ""
                    ).strip()
                    previous_generated_date = str(
                        generated_event.get(
                            "retained_death_generated_date",
                            "",
                        )
                        or ""
                    ).strip()
                    previous_generated_title = str(
                        generated_event.get(
                            "retained_death_generated_title",
                            "",
                        )
                        or ""
                    ).strip()
                    previous_generated_description = str(
                        generated_event.get(
                            "retained_death_generated_description",
                            "",
                        )
                        or ""
                    ).strip()
                    generated_title = (
                        f"{item['name']} retained at death of {person_name}"
                    )
                    generated_description = (
                        f"{item['name']} remained in {person_name}'s "
                        "possession at the time of death."
                    )
                    generated_event_is_untouched = (
                        generated_event.get("date", "")
                        == previous_generated_date
                        and generated_event.get("title", "")
                        == previous_generated_title
                        and generated_event.get("description", "")
                        == previous_generated_description
                        and generated_event.get("person_ids", [])
                        == [person_id]
                        and generated_event.get("item_ids", []) == [item_id]
                        and item_event_link_type(
                            generated_event,
                            item_id,
                        )
                        == "retained"
                    )

                    if explicit_event_found and generated_event_is_untouched:
                        self.database.delete_record("events", event_id)
                        processed[pair_key] = death_date
                        processed_changed = True
                        changed = True
                        continue

                    updates = {}

                    if (
                        previous_generated_date
                        and generated_event.get("date", "")
                        == previous_generated_date
                        and previous_generated_date != death_date
                    ):
                        updates["date"] = death_date
                        updates[
                            "retained_death_generated_date"
                        ] = death_date

                    if (
                        previous_generated_title
                        and generated_event.get("title", "")
                        == previous_generated_title
                        and previous_generated_title != generated_title
                    ):
                        updates["title"] = generated_title
                        updates[
                            "retained_death_generated_title"
                        ] = generated_title

                    if (
                        previous_generated_description
                        and generated_event.get("description", "")
                        == previous_generated_description
                        and previous_generated_description
                        != generated_description
                    ):
                        updates["description"] = generated_description
                        updates[
                            "retained_death_generated_description"
                        ] = generated_description

                    if event_id and updates:
                        self.database.update_record(
                            "events",
                            event_id,
                            updates,
                        )
                        changed = True

                    if processed.get(pair_key) != death_date:
                        processed[pair_key] = death_date
                        processed_changed = True

                    continue

                if processed.get(pair_key) == death_date:
                    continue

                if explicit_event_found:
                    processed[pair_key] = death_date
                    processed_changed = True
                    continue

                title = (
                    f"{item['name']} retained at death of {person_name}"
                )
                description = (
                    f"{item['name']} remained in {person_name}'s possession "
                    "at the time of death."
                )
                retained_event = normalize_world_event(
                    {
                        "event_type": "item_event",
                        "title": title,
                        "date": death_date,
                        "description": description,
                        "person_ids": [person_id],
                        "witness_person_ids": [],
                        "affected_person_ids": [],
                        "period_names": [],
                        "location_ids": [],
                        "item_ids": [item_id],
                        "item_link_types": {item_id: "retained"},
                        "item_new_owners": {},
                        "retained_death_person_id": person_id,
                        "retained_death_item_id": item_id,
                        "retained_death_generated_date": death_date,
                        "retained_death_generated_title": title,
                        "retained_death_generated_description": description,
                    }
                )
                self.database.create_record("events", retained_event)
                processed[pair_key] = death_date
                processed_changed = True
                changed = True

        if processed_changed:
            normalized_settings[
                RETAINED_DEATH_STORAGE_KEY
            ] = processed
            self.database.data[
                "_application_settings"
            ] = normalized_settings
            self.database.dirty = True

        if changed:
            self.invalidate_event_cache()

        return changed or processed_changed

    def synchronize_item_ownership_from_events(self):
        if self.database is None:
            return False

        items = self.item_records()

        if not items:
            return False

        people_by_id = {
            str(person.get("record_id", "") or "").strip(): str(
                person.get("displayed_name", "") or "Unnamed person"
            ).strip()
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        self.ensure_event_cache()
        events = self._event_cache
        ownership_events_by_item_id = {}

        for event in events:
            for item_id in event.get("item_ids", []):
                link_type = item_event_link_type(event, item_id)

                if not item_event_ownership_method(link_type):
                    continue

                ownership_events_by_item_id.setdefault(
                    item_id,
                    [],
                ).append(event)

        changed = False

        for stored_item in items:
            item = normalize_item_record(stored_item)
            existing_event_passages = {
                passage["source_event_id"]: passage
                for passage in item["passage_history"]
                if passage["source_event_id"]
            }
            passage_history = [
                passage
                for passage in item["passage_history"]
                if not passage["source_event_id"]
            ]

            for event in ownership_events_by_item_id.get(
                item["record_id"],
                [],
            ):
                event_id = str(
                    event.get("record_id", "") or ""
                ).strip()
                link_type = item_event_link_type(
                    event,
                    item["record_id"],
                )
                method = item_event_ownership_method(link_type)
                existing_passage = existing_event_passages.get(
                    event_id,
                    {},
                )
                person_id = ""
                person_name = ""

                if link_type in ITEM_EVENT_NEW_OWNER_LINK_TYPES:
                    owner = item_event_new_owner(
                        event,
                        item["record_id"],
                    )
                    person_id = owner["person_id"]
                    person_name = owner["person_name"]
                elif link_type in ("crafted", "found"):
                    direct_person_ids = [
                        str(candidate_id or "").strip()
                        for candidate_id in event.get("person_ids", [])
                        if str(candidate_id or "").strip()
                    ]

                    if direct_person_ids:
                        person_id = direct_person_ids[0]
                        person_name = people_by_id.get(person_id, "")

                    if not person_name:
                        person_id = ""
                        person_name = str(
                            existing_passage.get("person_name", "")
                            or ""
                        ).strip()

                passage_history.append(
                    normalize_item_passage(
                        {
                            "record_id": (
                                existing_passage.get("record_id")
                                or f"item-event:{item['record_id']}:{event_id}"
                            ),
                            "person_id": person_id,
                            "person_name": person_name,
                            "date": event.get("date", ""),
                            "time": event.get("time", ""),
                            "method": method,
                            "note": event.get("title", ""),
                            "source_event_id": event_id,
                        }
                    )
                )

            passage_history.sort(key=item_passage_sort_key)

            if passage_history == item["passage_history"]:
                continue

            self.database.update_record(
                "items",
                item["record_id"],
                {"passage_history": passage_history},
            )
            changed = True

        if changed:
            self.invalidate_event_cache()

        return changed

    def item_option_sort_key(self, item):
        return (
            item["category"].casefold(),
            item["name"].casefold(),
        )

    def linkable_event_options(self):
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): str(
                person.get("displayed_name", "") or ""
            ).strip()
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        locations_by_id = {
            str(location.get("record_id", "") or "").strip(): str(
                location.get("name", "") or ""
            ).strip()
            for location in self.location_provider()
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        }
        events = self.list_events()
        dated_events = [
            event
            for event in events
            if str(event.get("date", "") or "").strip()
        ]
        undated_events = [
            event
            for event in events
            if not str(event.get("date", "") or "").strip()
        ]
        dated_events.sort(key=world_event_sort_key, reverse=True)
        undated_events.sort(key=world_event_sort_key)
        options = []

        for event in [*dated_events, *undated_events]:
            event_date = format_line_item_date(
                event.get("date", ""),
                unknown="Date unknown",
            )
            event_time = str(event.get("time", "") or "").strip()

            if event_time:
                event_date = f"{event_date} {event_time}"

            event_type = event_type_label(event)
            organization_name = str(
                event.get("organization_name", "") or ""
            ).strip()
            person_names = [
                people_by_id.get(person_id, "")
                for person_id in event_linked_person_ids(event)
                if people_by_id.get(person_id, "")
            ]
            location_names = [
                locations_by_id.get(location_id, "")
                for location_id in event.get("location_ids", [])
                if locations_by_id.get(location_id, "")
            ]
            detail_parts = [event_type]

            if organization_name:
                detail_parts.append(organization_name)

            options.append(
                {
                    "value": event["record_id"],
                    "label": f"{event_date} · {event['title']}",
                    "detail": " · ".join(detail_parts),
                    "group": event_type,
                    "default_link_type": item_event_link_type(event, ""),
                    "search_text": " ".join(
                        [
                            *person_names,
                            *location_names,
                            *event.get("period_names", []),
                            event_time,
                        ]
                    ),
                }
            )

        return options

    def set_item_event_links(
        self,
        item_id,
        event_ids,
        event_link_types=None,
        event_new_owners=None,
    ):
        normalized_item_id = str(item_id or "").strip()
        known_item_ids = {
            item["record_id"]
            for item in self.item_records()
        }

        if normalized_item_id not in known_item_ids:
            raise KeyError(f"Unknown item record_id: {normalized_item_id}")

        selected_event_ids = []

        for event_id in event_ids or ():
            normalized_event_id = str(event_id or "").strip()

            if (
                normalized_event_id
                and normalized_event_id not in selected_event_ids
            ):
                selected_event_ids.append(normalized_event_id)

        known_event_ids = {
            event["record_id"]
            for event in self.list_events()
        }
        missing_event_ids = [
            event_id
            for event_id in selected_event_ids
            if event_id not in known_event_ids
        ]

        if missing_event_ids:
            raise ValueError(
                "One or more selected events no longer exist."
            )

        selected_event_id_set = set(selected_event_ids)
        requested_event_link_types = (
            event_link_types if isinstance(event_link_types, dict) else {}
        )
        requested_event_new_owners = (
            event_new_owners if isinstance(event_new_owners, dict) else {}
        )
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): str(
                person.get("displayed_name", "") or "Unnamed person"
            ).strip()
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        database_data = deepcopy(self.database.data)
        database_dirty = self.database.dirty
        database_revision = self.database.revision
        changed = False

        try:
            for event in self.database.list_records("events"):
                linked_item_ids = list(event.get("item_ids", []) or [])
                item_link_types = normalize_item_event_link_types(
                    event.get("item_link_types"),
                    linked_item_ids,
                    event.get("event_type", ""),
                )
                item_new_owners = normalize_item_event_new_owners(
                    event.get("item_new_owners"),
                    linked_item_ids,
                    item_link_types,
                )
                should_link = event["record_id"] in selected_event_id_set
                is_linked = normalized_item_id in linked_item_ids

                if should_link:
                    if not is_linked:
                        linked_item_ids.append(normalized_item_id)

                    item_link_types[normalized_item_id] = (
                        normalize_item_event_link_type(
                            requested_event_link_types.get(
                                event["record_id"],
                                item_link_types.get(normalized_item_id),
                            ),
                            event.get("event_type", ""),
                        )
                    )
                    requested_owner = normalize_item_event_new_owner(
                        requested_event_new_owners.get(
                            event["record_id"],
                            item_new_owners.get(normalized_item_id),
                        )
                    )

                    if (
                        item_link_types[normalized_item_id]
                        in ITEM_EVENT_NEW_OWNER_LINK_TYPES
                    ):
                        if requested_owner["person_id"] not in people_by_id:
                            raise ValueError(
                                "Choose the new owner for every Passed down, "
                                "Gifted, or Taken item link."
                            )

                        requested_owner["person_name"] = people_by_id[
                            requested_owner["person_id"]
                        ]
                        item_new_owners[
                            normalized_item_id
                        ] = requested_owner
                    else:
                        item_new_owners.pop(normalized_item_id, None)
                else:
                    linked_item_ids = [
                        linked_item_id
                        for linked_item_id in linked_item_ids
                        if linked_item_id != normalized_item_id
                    ]
                    item_link_types.pop(normalized_item_id, None)
                    item_new_owners.pop(normalized_item_id, None)

                item_new_owners = normalize_item_event_new_owners(
                    item_new_owners,
                    linked_item_ids,
                    item_link_types,
                )

                if (
                    linked_item_ids == event.get("item_ids", [])
                    and item_link_types
                    == event.get("item_link_types", {})
                    and item_new_owners
                    == event.get("item_new_owners", {})
                ):
                    continue

                self.database.update_record(
                    "events",
                    event["record_id"],
                    {
                        "item_ids": linked_item_ids,
                        "item_link_types": item_link_types,
                        "item_new_owners": item_new_owners,
                    },
                )
                changed = True

            for organization in self.database.list_records(
                "organizations"
            ):
                organization_id = str(
                    organization.get("record_id", "") or ""
                ).strip()
                organization_events = normalize_organization_events(
                    organization.get("events", [])
                )
                organization_changed = False

                for organization_event in organization_events:
                    world_event_id = organization_event_world_id(
                        organization_id,
                        organization_event["record_id"],
                    )
                    linked_item_ids = list(
                        organization_event.get("item_ids", []) or []
                    )
                    item_link_types = normalize_item_event_link_types(
                        organization_event.get("item_link_types"),
                        linked_item_ids,
                        organization_event.get("event_type", ""),
                    )
                    item_new_owners = normalize_item_event_new_owners(
                        organization_event.get("item_new_owners"),
                        linked_item_ids,
                        item_link_types,
                    )
                    should_link = (
                        world_event_id in selected_event_id_set
                    )
                    is_linked = normalized_item_id in linked_item_ids

                    if should_link:
                        if not is_linked:
                            linked_item_ids.append(normalized_item_id)

                        item_link_types[normalized_item_id] = (
                            normalize_item_event_link_type(
                                requested_event_link_types.get(
                                    world_event_id,
                                    item_link_types.get(normalized_item_id),
                                ),
                                organization_event.get("event_type", ""),
                            )
                        )
                        requested_owner = normalize_item_event_new_owner(
                            requested_event_new_owners.get(
                                world_event_id,
                                item_new_owners.get(normalized_item_id),
                            )
                        )

                        if (
                            item_link_types[normalized_item_id]
                            in ITEM_EVENT_NEW_OWNER_LINK_TYPES
                        ):
                            if (
                                requested_owner["person_id"]
                                not in people_by_id
                            ):
                                raise ValueError(
                                    "Choose the new owner for every Passed "
                                    "down, Gifted, or Taken item link."
                                )

                            requested_owner[
                                "person_name"
                            ] = people_by_id[
                                requested_owner["person_id"]
                            ]
                            item_new_owners[
                                normalized_item_id
                            ] = requested_owner
                        else:
                            item_new_owners.pop(
                                normalized_item_id,
                                None,
                            )
                    else:
                        linked_item_ids = [
                            linked_item_id
                            for linked_item_id in linked_item_ids
                            if linked_item_id != normalized_item_id
                        ]
                        item_link_types.pop(normalized_item_id, None)
                        item_new_owners.pop(normalized_item_id, None)

                    item_new_owners = normalize_item_event_new_owners(
                        item_new_owners,
                        linked_item_ids,
                        item_link_types,
                    )

                    if (
                        linked_item_ids
                        == organization_event.get("item_ids", [])
                        and item_link_types
                        == organization_event.get("item_link_types", {})
                        and item_new_owners
                        == organization_event.get(
                            "item_new_owners",
                            {},
                        )
                    ):
                        continue

                    organization_event["item_ids"] = linked_item_ids
                    organization_event[
                        "item_link_types"
                    ] = item_link_types
                    organization_event[
                        "item_new_owners"
                    ] = item_new_owners
                    organization_changed = True

                if not organization_changed:
                    continue

                organization["events"] = normalize_organization_events(
                    organization_events
                )
                self.database.update_record(
                    "organizations",
                    organization_id,
                    organization,
                )
                changed = True

            ownership_changed = (
                self.synchronize_item_ownership_from_events()
            )
            retained_events_changed = (
                self.synchronize_retained_item_events_for_deaths()
            )

            if changed or ownership_changed or retained_events_changed:
                self.database.save()
        except Exception:
            self.database.data = database_data
            self.database.dirty = database_dirty
            self.database.revision = database_revision
            self.invalidate_event_cache()
            raise

        self.invalidate_event_cache()
        return self.events_for_item(normalized_item_id)

    def synchronize_marriage_relationships(self, event):
        """Mirror a Marriage event into both people's family-tree records."""
        normalized = normalize_world_event(event)

        if canonical_event_type(normalized.get("event_type")) != "got_married":
            return False

        person_ids = [
            str(person_id or "").strip()
            for person_id in normalized.get("person_ids", [])
            if str(person_id or "").strip()
        ]

        if len(person_ids) != 2 or person_ids[0] == person_ids[1]:
            return False

        year_text, month_text, day_text = split_world_event_date(
            normalized.get("date", "")
        )

        def integer_or_none(value):
            try:
                return int(value) if str(value or "").strip() else None
            except (TypeError, ValueError):
                return None

        marriage_date = {
            "marriage_year": integer_or_none(year_text),
            "marriage_month": integer_or_none(month_text),
            "marriage_day": integer_or_none(day_text),
        }
        changed = False

        for person_id, spouse_id in (
            (person_ids[0], person_ids[1]),
            (person_ids[1], person_ids[0]),
        ):
            person = self.database.read_record("people", person_id)

            if not isinstance(person, dict):
                continue

            relationships = normalize_spouse_relationships(
                person.get("spouse_relationships", [])
            )
            relationship = next(
                (
                    candidate
                    for candidate in relationships
                    if candidate.get("person_id") == spouse_id
                ),
                empty_spouse_relationship(spouse_id),
            )
            updated_relationship = deepcopy(relationship)
            updated_relationship["married"] = True
            updated_relationship.update(marriage_date)
            updated_relationship = normalize_spouse_relationships(
                [updated_relationship]
            )[0]
            updated_relationships = [
                candidate
                for candidate in relationships
                if candidate.get("person_id") != spouse_id
            ]
            updated_relationships.append(updated_relationship)
            mate_ids = relationship_ids(updated_relationships)

            if (
                updated_relationships
                == normalize_spouse_relationships(
                    person.get("spouse_relationships", [])
                )
                and mate_ids == list(person.get("mate_ids", []) or [])
            ):
                continue

            self.database.update_person(
                person_id,
                {
                    "mate_ids": mate_ids,
                    "spouse_relationships": updated_relationships,
                },
            )
            changed = True

        return changed

    def create_event(
        self,
        values,
        replace_existing_death=False,
        save_database=True,
    ):
        self.require_single_death_location(values)
        prepared = normalize_world_event(
            self.apply_event_rules(values)
        )
        normalized = self.with_eligible_eminence(
            normalize_world_event(
                self.apply_event_rules(prepared)
            )
        )
        if (
            normalized["event_type"] == "published_book"
            and normalized.get("book_ids")
        ):
            return self.upsert_book_publication_event(
                normalized,
                save_database=save_database,
            )
        self.validate_associations(
            normalized,
            allow_death_replacement=replace_existing_death,
        )

        if normalized["event_type"] == "organization_founding":
            return self.create_organization_founding_event(
                normalized,
                save_database=save_database,
            )

        replaced_events, retained_replacement_events = (
            self.replace_death_event_conflicts(normalized)
            if replace_existing_death
            else ([], [])
        )
        eminence_updates = prepare_event_eminence_updates(
            self.database,
            replaced_events,
            (*retained_replacement_events, normalized),
        )
        created = self.database.create_record("events", normalized)
        self.synchronize_marriage_relationships(created)
        self.synchronize_started_job_assignments((), (created,))
        self.synchronize_birth_event_people((), (created,))
        self.synchronize_death_event_people(
            replaced_events,
            (*retained_replacement_events, created),
        )
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        if any(
            canonical_event_type(event.get("event_type")) == "extinction"
            for event in (*replaced_events, created)
        ):
            self.synchronize_location_extinction_state()
        self.remember_associations(created)

        item_ownership_may_have_changed = created.get("item_ids") or any(
            event.get("item_ids") for event in replaced_events
        )

        if item_ownership_may_have_changed:
            self.synchronize_item_ownership_from_events()

        if (
            created.get("event_type") in DEATH_EVENT_TYPES
            or item_ownership_may_have_changed
        ):
            self.synchronize_retained_item_events_for_deaths()

        if save_database:
            self.database.save()

        return normalize_world_event(created)

    def create_organization_founding_event(
        self,
        values,
        save_database=True,
    ):
        organization = self.database.read_record(
            "organizations",
            values["organization_id"],
        )

        if organization is None:
            raise KeyError("The selected organization no longer exists.")

        founding_event = normalize_organization_events(
            organization.get("events", [])
        )[0]
        current = organization_event_as_world_event(
            organization,
            founding_event,
        )
        prepared = deepcopy(values)
        prepared["record_id"] = current["record_id"]
        prepared["organization_event"] = True
        prepared["organization_event_id"] = founding_event["record_id"]
        return self.update_organization_event(
            current,
            prepared,
            save_database=save_database,
        )

    def update_event(
        self,
        record_id,
        values,
        replace_existing_death=False,
        save_database=True,
    ):
        current = self.get_event(record_id)

        if current is None:
            raise KeyError(f"Unknown event record_id: {record_id}")

        prospective = deepcopy(current)
        prospective.update(deepcopy(values))
        prospective["record_id"] = record_id
        self.require_single_death_location(prospective)
        normalized = self.with_eligible_eminence(
            normalize_world_event(
                self.apply_event_rules(prospective, current)
            )
        )
        if current.get("event_type") == "published_book":
            if normalized["event_type"] != "published_book":
                raise ValueError(
                    "A book's publication event cannot be changed into "
                    "another event type."
                )
            if normalized.get("book_ids"):
                return self.upsert_book_publication_event(
                    normalized,
                    save_database=save_database,
                )
        self.validate_associations(
            normalized,
            current,
            allow_death_replacement=replace_existing_death,
        )

        if current.get("organization_event"):
            return self.update_organization_event(
                current,
                normalized,
                save_database=save_database,
            )

        replaced_events, retained_replacement_events = (
            self.replace_death_event_conflicts(
                normalized,
                current,
            )
            if replace_existing_death
            else ([], [])
        )
        eminence_updates = prepare_event_eminence_updates(
            self.database,
            (current, *replaced_events),
            (normalized, *retained_replacement_events),
        )
        updated = self.database.update_record(
            "events",
            record_id,
            normalized,
        )
        self.synchronize_marriage_relationships(updated)
        self.synchronize_started_job_assignments(
            (current,),
            (updated,),
        )
        self.synchronize_birth_event_people(
            (current,),
            (updated,),
        )
        self.synchronize_death_event_people(
            (current, *replaced_events),
            (updated, *retained_replacement_events),
        )
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        if any(
            canonical_event_type(event.get("event_type")) == "extinction"
            for event in (
                current,
                updated,
                *replaced_events,
                *retained_replacement_events,
            )
        ):
            self.synchronize_location_extinction_state()
        self.remember_associations(updated)

        death_state_may_have_changed = (
            current.get("event_type") in DEATH_EVENT_TYPES
            or updated.get("event_type") in DEATH_EVENT_TYPES
        )
        item_ownership_may_have_changed = (
            current.get("item_ids")
            or updated.get("item_ids")
            or any(
            event.get("item_ids") for event in replaced_events
            )
        )

        if item_ownership_may_have_changed:
            self.synchronize_item_ownership_from_events()

        if death_state_may_have_changed or item_ownership_may_have_changed:
            self.synchronize_retained_item_events_for_deaths()

        if save_database:
            self.database.save()
        return normalize_world_event(updated)

    def delete_event(self, record_id):
        current = self.get_event(record_id)

        if current is None:
            raise KeyError(f"Unknown event record_id: {record_id}")

        if current.get("organization_event"):
            return self.delete_organization_event(current)

        if canonical_event_type(
            current.get("event_type")
        ) == BIRTH_EVENT_TYPE:
            raise ValueError(
                "A Birth event is a required part of the baby's Timeline "
                "and cannot be removed."
            )

        if canonical_event_type(
            current.get("event_type")
        ) == "published_book" and current.get("book_ids"):
            raise ValueError(
                "A Published a book event is required by its book and "
                "cannot be removed."
            )

        self.validate_ghost_event_dependencies(
            current_event=current,
            deleting=True,
        )

        eminence_updates = prepare_event_eminence_updates(
            self.database,
            (current,),
            (),
        )
        deleted = self.database.delete_record("events", record_id)
        self.synchronize_started_job_assignments((current,), ())
        self.synchronize_birth_event_people((current,), ())
        self.synchronize_death_event_people((current,), ())
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        if canonical_event_type(
            current.get("event_type")
        ) == "extinction":
            self.synchronize_location_extinction_state()

        if current.get("item_ids"):
            self.synchronize_item_ownership_from_events()
            self.synchronize_retained_item_events_for_deaths()
        self.database.save()
        return normalize_world_event(deleted)

    def duplicate_event(self, record_id):
        current = self.get_event(record_id)

        if current is None:
            raise KeyError(f"Unknown event record_id: {record_id}")

        if current.get("organization_event"):
            raise ValueError(
                "Organization-owned events cannot be duplicated here."
            )

        if current.get("automatic_source"):
            raise ValueError(
                "Automatic events cannot be duplicated."
            )

        if current.get("event_type") in DEATH_EVENT_TYPES:
            raise ValueError(
                "Death and Murder events cannot be duplicated."
            )

        duplicated = self.duplicate_event_values(current)
        return self.create_event(duplicated)

    def duplicate_events(self, record_id, count):
        if (
            isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or count > 100
        ):
            raise ValueError(
                "Choose between 1 and 100 event copies."
            )

        current = self.get_event(record_id)

        if current is None:
            raise KeyError(f"Unknown event record_id: {record_id}")

        if current.get("organization_event"):
            raise ValueError(
                "Organization-owned events cannot be duplicated here."
            )

        if current.get("automatic_source"):
            raise ValueError(
                "Automatic events cannot be duplicated."
            )

        if current.get("event_type") in DEATH_EVENT_TYPES:
            raise ValueError(
                "Death and Murder events cannot be duplicated."
            )

        database_data = deepcopy(self.database.data)
        database_dirty = self.database.dirty
        database_revision = self.database.revision
        duplicated_events = []

        try:
            for _ in range(count):
                duplicated_values = self.duplicate_event_values(current)
                current = self.create_event(
                    duplicated_values,
                    save_database=False,
                )
                duplicated_events.append(current)

            self.database.save()
        except Exception:
            self.database.data = database_data
            self.database.dirty = database_dirty
            self.database.revision = database_revision
            self.invalidate_event_cache()
            raise

        return deepcopy(duplicated_events)

    def duplicate_event_values(self, current):
        duplicated = deepcopy(current)

        for field_name in (
            "record_id",
            "event_id",
            "organization_event",
            "organization_event_id",
            "_stored_event",
            "_draft_event",
            "_person_id",
            "created_at",
            "last_updated",
        ):
            duplicated.pop(field_name, None)

        if duplicated.get("event_type") == "started_job":
            duplicated["job_assignment_id"] = ""

        duplicate_year, duplicate_month, duplicate_day = (
            split_world_event_date(duplicated.get("date", ""))
        )

        if duplicate_year:
            next_year = int(duplicate_year)

            if duplicate_month:
                next_month = int(duplicate_month) + 1

                if next_month > 12:
                    next_month = 1
                    next_year = historical_year_after(next_year)

                duplicated["date"] = f"{next_year}-{next_month:02d}"

                if duplicate_day:
                    next_day = min(
                        int(duplicate_day),
                        historical_days_in_month(next_year, next_month),
                    )
                    duplicated["date"] += f"-{next_day:02d}"
            else:
                duplicated["date"] = str(
                    historical_year_after(next_year)
                )

        return duplicated

    def synchronize_location_extinction_state(self):
        database_data = getattr(self.database, "data", None)

        if not isinstance(database_data, dict):
            return False

        changed = synchronize_location_extinction_records(
            database_data,
            create_legacy_events=False,
        )

        if changed and hasattr(self.database, "dirty"):
            self.database.dirty = True

        return changed

    def update_organization_event(
        self,
        current,
        values,
        save_database=True,
    ):
        organization_id = str(
            current.get("organization_id", "") or ""
        ).strip()
        organization_event_id = str(
            current.get("organization_event_id", "") or ""
        ).strip()
        organization = self.database.read_record(
            "organizations",
            organization_id,
        )

        if organization is None:
            raise KeyError(
                f"Unknown organization record_id: {organization_id}"
            )

        events = normalize_organization_events(
            organization.get("events", [])
        )
        existing_event = next(
            (
                event
                for event in events
                if event["record_id"] == organization_event_id
            ),
            None,
        )

        if existing_event is None:
            raise KeyError(
                "The organization event no longer exists."
            )

        updated_event = organization_event_from_world_event(
            values,
            existing_event,
        )
        updated_world_event = organization_event_as_world_event(
            organization,
            updated_event,
        )
        eminence_updates = prepare_event_eminence_updates(
            self.database,
            (current,),
            (updated_world_event,),
        )
        organization["events"] = normalize_organization_events(
            [
                (
                    updated_event
                    if event["record_id"] == organization_event_id
                    else event
                )
                for event in events
            ]
        )
        updated_organization = self.database.update_record(
            "organizations",
            organization_id,
            organization,
        )
        database_data = getattr(self.database, "data", None)

        if isinstance(database_data, dict):
            synchronize_school_campus_locations(database_data)

        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )
        self.remember_associations(values)

        if current.get("item_ids") or updated_world_event.get("item_ids"):
            self.synchronize_item_ownership_from_events()
            self.synchronize_retained_item_events_for_deaths()
        if save_database:
            self.database.save()
        return organization_event_as_world_event(
            updated_organization,
            updated_event,
        )

    def delete_organization_event(self, current):
        organization_id = str(
            current.get("organization_id", "") or ""
        ).strip()
        organization_event_id = str(
            current.get("organization_event_id", "") or ""
        ).strip()
        organization = self.database.read_record(
            "organizations",
            organization_id,
        )

        if organization is None:
            raise KeyError(
                f"Unknown organization record_id: {organization_id}"
            )

        events = normalize_organization_events(
            organization.get("events", [])
        )
        selected_event = next(
            (
                event
                for event in events
                if event["record_id"] == organization_event_id
            ),
            None,
        )

        if selected_event is None:
            raise KeyError(
                "The organization event no longer exists."
            )

        if (
            selected_event["event_type"]
            == ORGANIZATION_EVENT_FOUNDING
        ):
            raise ValueError(
                "An organization's founding event cannot be deleted."
            )

        eminence_updates = prepare_event_eminence_updates(
            self.database,
            (current,),
            (),
        )
        organization["events"] = normalize_organization_events(
            [
                event
                for event in events
                if event["record_id"] != organization_event_id
            ]
        )
        self.database.update_record(
            "organizations",
            organization_id,
            organization,
        )
        apply_event_eminence_updates(
            self.database,
            eminence_updates,
        )

        if current.get("item_ids"):
            self.synchronize_item_ownership_from_events()
            self.synchronize_retained_item_events_for_deaths()
        self.database.save()
        return normalize_world_event(current)

    def apply_title_rules(self, event):
        titled_event = deepcopy(event) if isinstance(event, dict) else {}
        event_type = canonical_event_type(
            titled_event.get("event_type")
        )

        if event_type in (
            "organization_founding",
            "joined_faction",
            "left_faction",
        ):
            organization_id = str(
                titled_event.get("organization_id", "") or ""
            ).strip()
            record_reader = getattr(self.database, "read_record", None)
            organization = (
                record_reader("organizations", organization_id)
                if callable(record_reader)
                else next(
                    (
                        candidate
                        for candidate in self.database.list_records(
                            "organizations"
                        )
                        if str(
                            candidate.get("record_id", "") or ""
                        ).strip()
                        == organization_id
                    ),
                    None,
                )
            )
            organization_name = str(
                (organization or {}).get("name", "")
                or titled_event.get("organization_name", "")
                or ""
            ).strip()

            if organization_name:
                organization_label = organization_context_label(
                    organization_id,
                    self.database.list_records("organizations"),
                    self.location_provider(),
                )
                titled_event["organization_name"] = organization_label
                if event_type == "organization_founding":
                    titled_event["title"] = (
                        f"Founding of {organization_label}"
                    )
                elif (
                    not str(titled_event.get("title", "") or "").strip()
                    or titled_event.get("title")
                    in {"Joined a faction", "Left a faction"}
                ):
                    verb = (
                        "Joined"
                        if event_type == "joined_faction"
                        else "Left"
                    )
                    titled_event["title"] = (
                        f"{verb} {organization_label}"
                    )

            titled_event["location_ids"] = []
            titled_event["locked_location_ids"] = []
            return titled_event

        if event_type != "founding":
            return titled_event

        location_ids = [
            str(location_id or "").strip()
            for location_id in titled_event.get("locked_location_ids", [])
            if str(location_id or "").strip()
        ]

        if not location_ids:
            location_ids = [
                str(location_id or "").strip()
                for location_id in titled_event.get("location_ids", [])
                if str(location_id or "").strip()
            ]

        title = (
            founding_event_title(
                location_ids[0],
                self.location_provider(),
            )
            if location_ids
            else ""
        )

        if title:
            titled_event["title"] = title

        return titled_event

    def apply_event_rules(self, event, current_event=None):
        prepared = self.apply_title_rules(event)
        event_type = canonical_event_type(
            prepared.get("event_type")
        )

        if event_type == "relocated":
            prepared = self.apply_relocation_household_rules(
                prepared,
                current_event,
            )

        if event_type == BIRTH_EVENT_TYPE:
            prepared["title"] = "Birth"
            prepared["automatic_source"] = BIRTH_EVENT_SOURCE
            prepared["eminence_person_ids"] = []
            prepared["eminence_skills"] = {}
        elif event_type == "died":
            prepared["eminence_person_ids"] = []
            prepared["eminence_skills"] = {}
        elif event_type == "murder":
            victim_ids = {
                str(person_id or "").strip()
                for person_id in prepared.get(
                    "victim_person_ids",
                    [],
                )
                if str(person_id or "").strip()
            }
            prepared["eminence_person_ids"] = [
                person_id
                for person_id in prepared.get(
                    "eminence_person_ids",
                    [],
                )
                if person_id not in victim_ids
            ]
            prepared["eminence_skills"] = {
                person_id: skill
                for person_id, skill in prepared.get(
                    "eminence_skills",
                    {},
                ).items()
                if person_id in prepared["eminence_person_ids"]
            }
        elif (
            event_type in ("romance", "breakup", "travel")
            and not str(prepared.get("title", "") or "").strip()
        ):
            prepared["title"] = {
                "romance": "Romance",
                "breakup": "Breakup",
                "travel": "Travel",
            }[event_type]
        elif (
            event_type == GHOST_EVENT_TYPE
            and not str(prepared.get("title", "") or "").strip()
        ):
            prepared["title"] = "Returns as ghost"

        if (
            event_type in DEATH_EVENT_TYPES
            and not str(prepared.get("title", "") or "").strip()
        ):
            prepared["title"] = (
                "Murder" if event_type == "murder" else "death"
            )

        if event_type not in ("started_job", "received_raise"):
            return prepared

        organization_job = self.job_event_organization_job(prepared)

        if organization_job is None:
            return prepared

        organization = organization_job["organization"]
        job = organization_job["job"]
        prepared["organization_id"] = str(
            organization.get("record_id", "") or ""
        )
        prepared["organization_name"] = organization_context_label(
            prepared["organization_id"],
            self.database.list_records("organizations"),
            self.location_provider(),
        )
        prepared["organization_job_id"] = job["record_id"]
        prepared["job_title"] = job["title"]

        if not str(prepared.get("title", "") or "").strip():
            prepared["title"] = (
                f"{job['title']} at {prepared['organization_name']}"
            )

        if event_type == "started_job":
            record_id = str(
                prepared.get("record_id", "")
                or (current_event or {}).get("record_id", "")
                or ""
            ).strip()
            existing_assignment = self.matching_started_job_assignment(
                prepared,
            )
            prepared["job_assignment_id"] = (
                existing_assignment["record_id"]
                if existing_assignment is not None
                else self.started_job_assignment_id(record_id)
            )
        else:
            active_assignment = self.active_assignment_for_job_event(
                prepared
            )
            prepared["job_assignment_id"] = (
                active_assignment["record_id"]
                if active_assignment is not None
                else ""
            )

        return prepared

    @staticmethod
    def unique_person_ids(values):
        return list(
            dict.fromkeys(
                str(person_id or "").strip()
                for person_id in values or ()
                if str(person_id or "").strip()
            )
        )

    def relocation_primary_person_ids(self, event, current_event=None):
        """Return deliberately selected movers, excluding generated links."""
        requested_ids = self.unique_person_ids(
            (event or {}).get("person_ids", [])
        )
        current = current_event if isinstance(current_event, dict) else {}
        current_full_ids = self.unique_person_ids(
            current.get("person_ids", [])
        )
        current_primary_ids = self.unique_person_ids(
            current.get("relocation_primary_person_ids")
            or current_full_ids
        )

        if current and requested_ids == current_full_ids:
            return current_primary_ids

        if current:
            retained_primary_ids = [
                person_id
                for person_id in current_primary_ids
                if person_id in requested_ids
            ]
            newly_selected_ids = [
                person_id
                for person_id in requested_ids
                if person_id not in current_full_ids
            ]
            primary_ids = self.unique_person_ids(
                [*retained_primary_ids, *newly_selected_ids]
            )
            if primary_ids:
                return primary_ids

        return requested_ids

    @staticmethod
    def person_birth_date(person):
        if not isinstance(person, dict) or person.get("birth_year") in (
            None,
            "",
        ):
            return ""
        try:
            return format_date_parts(
                person.get("birth_year"),
                person.get("birth_month"),
                person.get("birth_day"),
                unknown="",
            )
        except (TypeError, ValueError):
            return ""

    def person_exists_by_event_date(self, person, event_date):
        birth_date = self.person_birth_date(person)
        if not birth_date or not str(event_date or "").strip():
            return True
        try:
            return world_event_date_is_on_or_after(
                event_date,
                birth_date,
            )
        except (TypeError, ValueError):
            # Normal event validation will surface a malformed date.  The
            # household helper should not hide the rest of the edit first.
            return True

    def person_is_under_age_on_event_date(
        self,
        person,
        event_date,
        maximum_age,
    ):
        """Return True only when the person's age is known to be below the limit."""
        birth_date = self.person_birth_date(person)
        if not birth_date or not str(event_date or "").strip():
            return False
        try:
            birth_year, birth_month, birth_day = split_world_event_date(
                birth_date
            )
            event_year, event_month, event_day = split_world_event_date(
                event_date
            )
            age = historical_year_distance(birth_year, event_year)
        except (TypeError, ValueError):
            return False

        if (
            birth_month
            and birth_day
            and event_month
            and event_day
            and (int(event_month), int(event_day))
            < (int(birth_month), int(birth_day))
        ):
            age -= 1
        return 0 <= age < int(maximum_age)

    def person_birth_sort_key(self, person):
        birth_date = self.person_birth_date(person)
        if not birth_date:
            return (100000, 13, 32)
        try:
            year, month, day = split_world_event_date(birth_date)
            return (
                int(year),
                int(month) if month else 0,
                int(day) if day else 0,
            )
        except (TypeError, ValueError):
            return (100000, 13, 32)

    def foster_children_on_date(self, parent_id, event_date):
        database = self.database
        if database is None:
            return []
        linked_reader = getattr(database, "get_linked_records", None)
        if callable(linked_reader):
            events = linked_reader("events", parent_id, "people")
        else:
            events = database.list_records("events")

        child_ids = []
        for event in events:
            if (
                not isinstance(event, dict)
                or canonical_event_type(event.get("event_type"))
                != "foster_child"
                or parent_id
                not in self.unique_person_ids(
                    event.get("foster_parent_person_ids", [])
                )
            ):
                continue
            foster_date = str(event.get("date", "") or "").strip()
            if foster_date and str(event_date or "").strip():
                try:
                    if not world_event_date_is_on_or_after(
                        event_date,
                        foster_date,
                    ):
                        continue
                except (TypeError, ValueError):
                    continue
            child_ids.extend(
                self.unique_person_ids(
                    event.get("foster_child_person_ids", [])
                )
            )
        return self.unique_person_ids(child_ids)

    def apply_relocation_household_rules(self, event, current_event=None):
        """Add direct and foster children under 17 to a relocation."""
        prepared = deepcopy(event) if isinstance(event, dict) else {}
        primary_ids = self.relocation_primary_person_ids(
            prepared,
            current_event,
        )
        prepared["relocation_primary_person_ids"] = primary_ids
        if not primary_ids:
            prepared["person_ids"] = []
            return prepared

        people = [
            person
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        ]
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in people
        }
        relationships = FamilyRelationshipMap(people)
        event_date = str(prepared.get("date", "") or "").strip()
        child_ids = []
        for parent_id in primary_ids:
            child_ids.extend(relationships.children_of(parent_id))
            child_ids.extend(
                self.foster_children_on_date(parent_id, event_date)
            )

        eligible_child_ids = [
            child_id
            for child_id in self.unique_person_ids(child_ids)
            if child_id not in primary_ids
            and child_id in people_by_id
            and self.person_exists_by_event_date(
                people_by_id[child_id],
                event_date,
            )
            and self.person_is_under_age_on_event_date(
                people_by_id[child_id],
                event_date,
                17,
            )
        ]
        eligible_child_ids.sort(
            key=lambda child_id: (
                self.person_birth_sort_key(people_by_id[child_id]),
                str(
                    people_by_id[child_id].get("displayed_name", "") or ""
                ).casefold(),
                child_id,
            )
        )
        prepared["person_ids"] = self.unique_person_ids(
            [*primary_ids, *eligible_child_ids]
        )
        return prepared

    def organization_job_options(self):
        options = []
        organizations = self.database.list_records("organizations")
        locations = self.location_provider()

        for organization in organizations:
            if not isinstance(organization, dict):
                continue

            organization_id = str(
                organization.get("record_id", "") or ""
            ).strip()
            organization_name = organization_context_label(
                organization_id,
                organizations,
                locations,
            )

            for job in normalize_organization_jobs(
                organization.get("jobs", [])
            ):
                options.append(
                    {
                        "value": job["record_id"],
                        "label": f"{organization_name} — {job['title']}",
                        "event_title": (
                            f"{job['title']} at {organization_name}"
                        ),
                        "organization_id": organization_id,
                        "organization_name": organization_name,
                        "organization_job_id": job["record_id"],
                        "job_title": job["title"],
                        "level": job["level"],
                        "job": deepcopy(job),
                        "organization": deepcopy(organization),
                    }
                )

        options.sort(key=self.organization_job_option_sort_key)
        return options

    def organization_job_option_sort_key(self, option):
        return (
            str(option.get("organization_name", "") or "").casefold(),
            int(option.get("level", 0) or 0),
            str(option.get("job_title", "") or "").casefold(),
            str(option.get("organization_job_id", "") or ""),
        )

    def job_event_organization_job(self, event):
        organization_id = str(
            (event or {}).get("organization_id", "") or ""
        ).strip()
        organization_job_id = str(
            (event or {}).get("organization_job_id", "") or ""
        ).strip()

        for option in self.organization_job_options():
            if (
                option["organization_id"] == organization_id
                and option["organization_job_id"]
                == organization_job_id
            ):
                return option

        return None

    def all_job_assignments(self):
        assignments = []

        for person in self.people_provider():
            if not isinstance(person, dict):
                continue

            development_plan = person.get("development_plan")

            if not isinstance(development_plan, dict):
                continue

            for adult_year in development_plan.get("adult_years", []):
                if not isinstance(adult_year, dict):
                    continue

                assignments.extend(
                    normalize_job_records(
                        adult_year.get("jobs", [])
                    )
                )

        return normalize_job_records(assignments)

    def all_job_assignments_with_special_appointments(self):
        assignments = self.all_job_assignments()

        for stored_event in self.database.list_records("events"):
            if (
                canonical_event_type(stored_event.get("event_type"))
                != "started_job"
                or not str(
                    stored_event.get("special_appointment_name", "") or ""
                ).strip()
            ):
                continue

            normalized_event = normalize_world_event(stored_event)
            start_year, start_month, start_day = split_world_event_date(
                normalized_event.get("date", "")
            )
            end_year, end_month, end_day = split_world_event_date(
                normalized_event.get("job_end_date", "")
            )
            assignment = new_job_record(
                normalized_event["organization_id"],
                normalized_event["organization_name"],
                normalized_event["job_title"],
                normalized_event["salary"],
                start_year,
                start_month or None,
                start_day or None,
                end_year or None,
                end_month or None,
                end_day or None,
                normalized_event["organization_job_id"],
            )
            assignment["record_id"] = str(
                normalized_event.get("job_assignment_id", "")
                or self.started_job_assignment_id(
                    normalized_event.get("record_id", "")
                )
            )
            assignments.append(normalize_job_record(assignment))

        return normalize_job_records(assignments)

    def person_job_availability(
        self,
        person_id,
        window_start,
        window_end,
        ignored_assignment_id="",
    ):
        return person_job_availability_window(
            self.person_job_assignments(person_id),
            window_start,
            window_end,
            ignored_assignment_id,
        )

    def person_job_assignments(self, person_id):
        selected_person_id = str(person_id or "").strip()
        person = next(
            (
                candidate
                for candidate in self.people_provider()
                if isinstance(candidate, dict)
                and str(candidate.get("record_id", "") or "").strip()
                == selected_person_id
            ),
            None,
        )

        if person is None:
            return []

        assignments = []
        plan = person.get("development_plan")

        if not isinstance(plan, dict):
            return []

        for adult_year in plan.get("adult_years", []):
            if isinstance(adult_year, dict):
                assignments.extend(
                    normalize_job_records(
                        adult_year.get("jobs", [])
                    )
                )

        return normalize_job_records(assignments)

    def started_job_assignment_id(self, event_id):
        normalized_event_id = str(event_id or "").strip()

        if not normalized_event_id:
            return ""

        return f"event-job:{normalized_event_id}"

    def matching_started_job_assignment(self, event):
        person_ids = list((event or {}).get("person_ids", []) or [])

        if len(person_ids) != 1:
            return None

        year, month, day = split_world_event_date(
            (event or {}).get("date", "")
        )

        if not year:
            return None

        requested_start = job_date_tuple(year, month, day)

        for assignment in self.person_job_assignments(person_ids[0]):
            if (
                assignment["organization_id"]
                != str((event or {}).get("organization_id", "") or "")
                or assignment["organization_job_id"]
                != str(
                    (event or {}).get("organization_job_id", "") or ""
                )
            ):
                continue

            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )

            if assignment_start == requested_start:
                return assignment

        return None

    def active_assignment_for_job_event(self, event):
        person_ids = list((event or {}).get("person_ids", []) or [])

        if len(person_ids) != 1:
            return None

        year, month, day = split_world_event_date(
            (event or {}).get("date", "")
        )

        if not year:
            return None

        selected_job_id = str(
            (event or {}).get("organization_job_id", "") or ""
        ).strip()

        for assignment in self.person_job_assignments(person_ids[0]):
            if (
                assignment["organization_job_id"] == selected_job_id
                and job_assignment_active_on(
                    assignment,
                    year,
                    month or 1,
                    day or 1,
                )
            ):
                return assignment

        return None

    def started_job_assignment(self, event):
        normalized_event = normalize_world_event(event)
        year, month, day = split_world_event_date(
            normalized_event["date"]
        )
        end_year, end_month, end_day = split_world_event_date(
            normalized_event.get("job_end_date", "")
        )
        assignment = new_job_record(
            normalized_event["organization_id"],
            normalized_event["organization_name"],
            normalized_event["job_title"],
            normalized_event["salary"],
            year,
            month,
            day,
            end_year or None,
            end_month or None,
            end_day or None,
            normalized_event["organization_job_id"],
            concurrent=normalized_event.get("job_concurrent", False),
        )
        assignment["record_id"] = (
            normalized_event.get("job_assignment_id")
            or self.started_job_assignment_id(
                normalized_event["record_id"]
            )
        )
        return normalize_job_record(assignment)

    def synchronize_started_job_assignments(
        self,
        previous_events,
        updated_events,
    ):
        previous_started = [
            normalize_world_event(event)
            for event in previous_events or ()
            if canonical_event_type(
                (event or {}).get("event_type")
            )
            == "started_job"
        ]
        updated_started = [
            normalize_world_event(event)
            for event in updated_events or ()
            if canonical_event_type(
                (event or {}).get("event_type")
            )
            == "started_job"
        ]
        affected_person_ids = {
            person_id
            for event in (*previous_started, *updated_started)
            for person_id in event.get("person_ids", [])
        }

        for person_id in affected_person_ids:
            person = self.database.read_person(person_id)

            if person is None:
                continue

            plan = normalize_development_plan(
                person.get("development_plan"),
                default_schema="Scattershot",
            )
            adult_years = ensure_adult_year_records(
                plan.get("adult_years", []),
                1,
            )
            removed_assignment_ids = {
                str(event.get("job_assignment_id", "") or "")
                or self.started_job_assignment_id(
                    event.get("record_id", "")
                )
                for event in previous_started
                if person_id in event.get("person_ids", [])
            }

            for adult_year in adult_years:
                adult_year["jobs"] = [
                    assignment
                    for assignment in normalize_job_records(
                        adult_year.get("jobs", [])
                    )
                    if assignment["record_id"]
                    not in removed_assignment_ids
                ]

            for event in updated_started:
                if person_id not in event.get("person_ids", []):
                    continue

                assignment = self.started_job_assignment(event)

                for adult_year in adult_years:
                    adult_year["jobs"] = [
                        stored_assignment
                        for stored_assignment in normalize_job_records(
                            adult_year.get("jobs", [])
                        )
                        if stored_assignment["record_id"]
                        != assignment["record_id"]
                    ]

                adult_years[0]["jobs"] = normalize_job_records(
                    [*adult_years[0].get("jobs", []), assignment]
                )

            plan["adult_years"] = adult_years
            self.database.update_person(
                person_id,
                {"development_plan": plan},
            )

    def synchronize_birth_event_people(
        self,
        previous_events,
        updated_events,
    ):
        previous_birth_locations = {}

        for previous_event in previous_events or ():
            if canonical_event_type(
                (previous_event or {}).get("event_type")
            ) != BIRTH_EVENT_TYPE:
                continue

            previous_baby_ids = birth_event_baby_ids(previous_event)

            if len(previous_baby_ids) == 1:
                previous_birth_locations[previous_baby_ids[0]] = list(
                    previous_event.get("location_ids", []) or []
                )[-1:]

        updated_birth_events = [
            normalize_world_event(event)
            for event in updated_events or ()
            if canonical_event_type(
                (event or {}).get("event_type")
            )
            == BIRTH_EVENT_TYPE
        ]

        if not updated_birth_events:
            return False

        from mage_maker.core.controller import PeopleController

        people_controller = PeopleController(self.database)
        changed = False

        for birth_event in updated_birth_events:
            baby_ids = birth_event_baby_ids(birth_event)

            if len(baby_ids) != 1:
                continue

            baby_id = baby_ids[0]
            baby = self.database.read_person(baby_id)

            if baby is None:
                continue

            birth_date = str(
                birth_event.get("date", "") or ""
            ).strip()
            birth_year, birth_month, birth_day = (
                split_world_event_date(birth_date)
                if birth_date
                else ("", "", "")
            )
            birthing_parent_ids = birth_event.get(
                "birthing_parent_person_ids",
                [],
            )
            non_birthing_parent_ids = birth_event.get(
                "non_birthing_parent_person_ids",
                [],
            )
            birthing_parent_id = (
                birthing_parent_ids[0]
                if birthing_parent_ids
                else ""
            )
            non_birthing_parent_id = (
                non_birthing_parent_ids[0]
                if non_birthing_parent_ids
                else ""
            )
            update_values = {
                "birth_year": (
                    int(birth_year) if birth_year else None
                ),
                "birth_month": (
                    int(birth_month) if birth_month else None
                ),
                "birth_day": int(birth_day) if birth_day else None,
                "biological_mother_id": birthing_parent_id,
                "biological_mother_status": (
                    "person" if birthing_parent_id else "unknown"
                ),
                "biological_father_id": non_birthing_parent_id,
                "biological_father_status": (
                    "person" if non_birthing_parent_id else "unknown"
                ),
            }
            location_ids = list(
                birth_event.get("location_ids", []) or []
            )[-1:]

            if location_ids:
                location_id = location_ids[0]
                location = next(
                    (
                        candidate
                        for candidate in self.location_provider()
                        if str(
                            candidate.get("record_id", "") or ""
                        ).strip()
                        == location_id
                    ),
                    None,
                )

                if location is not None:
                    update_values["starting_location_id"] = location_id
                    update_values["starting_location"] = str(
                        location.get("name", "") or ""
                    ).strip()
            elif (
                baby_id in previous_birth_locations
                and previous_birth_locations[baby_id] != location_ids
            ):
                update_values["starting_location_id"] = ""
                update_values["starting_location"] = ""

            people_controller.update_person(
                baby_id,
                update_values,
                synchronize_birth_event=False,
            )
            synchronized_baby = self.database.read_person(baby_id)

            if synchronized_baby is not None:
                timeline_events = normalize_timeline_events(
                    synchronized_baby.get("timeline_events", [])
                )

                for timeline_event in timeline_events:
                    if (
                        timeline_event.get("event_type")
                        == BIRTH_EVENT_TYPE
                        and timeline_event.get("automatic_source")
                        == "life_start"
                    ):
                        timeline_event["note"] = str(
                            birth_event.get("description", "") or ""
                        ).strip()

                self.database.update_person(
                    baby_id,
                    {"timeline_events": timeline_events},
                )

            synchronize_birth_events_from_people(
                self.database.data,
                (baby_id,),
            )
            changed = True

        return changed

    def replace_death_event_conflicts(
        self,
        replacement_event,
        current_event=None,
    ):
        replacement_person_ids = set(
            death_event_person_ids(replacement_event)
        )

        if not replacement_person_ids:
            return [], []

        current_event_id = str(
            (current_event or {}).get("record_id", "") or ""
        ).strip()
        replaced_events = []
        retained_events = []

        for stored_event in self.database.list_records("events"):
            stored_event_id = str(
                stored_event.get("record_id", "") or ""
            ).strip()

            if stored_event_id == current_event_id:
                continue

            if not replacement_person_ids.intersection(
                death_event_person_ids(stored_event)
            ):
                continue

            normalized_stored_event = normalize_world_event(stored_event)
            replaced_events.append(normalized_stored_event)

            if normalized_stored_event.get("event_type") != "murder":
                self.database.delete_record("events", stored_event_id)
                continue

            retained_victim_ids = [
                person_id
                for person_id in normalized_stored_event.get(
                    "victim_person_ids",
                    [],
                )
                if person_id not in replacement_person_ids
            ]

            if not retained_victim_ids:
                self.database.delete_record("events", stored_event_id)
                continue

            retained_event = deepcopy(normalized_stored_event)
            retained_event["victim_person_ids"] = retained_victim_ids
            retained_event["person_ids"] = list(
                dict.fromkeys(
                    [
                        *retained_event.get(
                            "perpetrator_person_ids",
                            [],
                        ),
                        *retained_victim_ids,
                        *retained_event.get(
                            "witness_person_ids",
                            [],
                        ),
                        *retained_event.get(
                            "affected_person_ids",
                            [],
                        ),
                    ]
                )
            )
            retained_event = normalize_world_event(retained_event)
            self.database.update_record(
                "events",
                stored_event_id,
                retained_event,
            )
            retained_events.append(retained_event)

        for person_id in replacement_person_ids:
            person = self.database.read_person(person_id)

            if person is None:
                continue

            timeline_events = normalize_timeline_events(
                person.get("timeline_events", [])
            )
            retained_timeline_events = [
                timeline_event
                for timeline_event in timeline_events
                if canonical_event_type(
                    timeline_event.get("event_type")
                )
                != "died"
            ]

            if retained_timeline_events != timeline_events:
                self.database.update_person(
                    person_id,
                    {"timeline_events": retained_timeline_events},
                )

        return replaced_events, retained_events

    def synchronize_death_event_people(
        self,
        previous_events,
        updated_events,
    ):
        affected_person_ids = {
            person_id
            for event in (
                *tuple(previous_events or ()),
                *tuple(updated_events or ()),
            )
            for person_id in death_event_person_ids(event)
        }

        if not affected_person_ids:
            return False

        changed = synchronize_people_death_records(
            self.database.data,
            affected_person_ids,
        )

        if changed:
            self.database.dirty = True

        return changed

    def require_single_death_location(self, event):
        if canonical_event_type(
            (event or {}).get("event_type")
        ) not in DEATH_EVENT_TYPES:
            return

        location_ids = {
            str(location_id or "").strip()
            for location_id in (event or {}).get("location_ids", [])
            if str(location_id or "").strip()
        }

        if len(location_ids) > 1:
            raise ValueError(
                "A Death or Murder event can use no more than one location."
            )

    def events_for_period(self, period_name, start_year, end_year):
        normalized_start = int(start_year)
        normalized_end = int(end_year)
        matching_events = []
        self.ensure_event_cache()

        for event in self._event_cache:
            event_year = world_event_year(event.get("date"))

            if (
                event_year is not None
                and normalized_start <= event_year <= normalized_end
            ):
                matching_events.append(event)

        matching_events.sort(key=world_event_sort_key)
        return deepcopy(matching_events)

    def events_for_person(self, person_id):
        normalized_person_id = str(person_id or "").strip()
        if not normalized_person_id:
            return []
        linked_reader = getattr(
            self.database,
            "get_linked_records",
            None,
        )
        if callable(linked_reader):
            eligible_ids = (
                {normalized_person_id}
                if self.person_can_earn_eminence(normalized_person_id)
                else set()
            )
            matching_events = [
                self.with_eligible_eminence(
                    self.apply_title_rules(event),
                    eligible_ids,
                )
                for event in linked_reader(
                    "events",
                    normalized_person_id,
                    "people",
                )
            ]
            matching_events.sort(key=world_event_sort_key)
            return deepcopy(matching_events)
        self.ensure_event_cache()
        return deepcopy(
            self._events_by_person_id.get(normalized_person_id, [])
        )

    def eminence_points_for_person(self, person_id):
        normalized_person_id = str(person_id or "").strip()

        if not normalized_person_id:
            return 0

        if self._event_cache is None:
            return sum(
                1
                for event in self.events_for_person(normalized_person_id)
                if normalized_person_id
                in event.get("eminence_person_ids", [])
            )
        self.ensure_event_cache()
        return self._eminence_points_by_person_id.get(
            normalized_person_id,
            0,
        )

    def event_has_famous_person(self, event):
        linked_person_ids = {
            str(person_id or "").strip()
            for person_id in event_linked_person_ids(event)
            if str(person_id or "").strip()
        }

        if not linked_person_ids:
            return False

        return any(
            bool(person.get("famous_person"))
            and str(person.get("record_id", "") or "") in linked_person_ids
            for person in self.people_summaries()
            if isinstance(person, dict)
        )

    def event_is_individual(self, event):
        return event_type_is_person_only(
            (event or {}).get("event_type")
        )

    def events_for_location(self, location_id, include_ancestors=True):
        normalized_location_id = str(location_id or "").strip()

        if not normalized_location_id:
            return []

        visible_location_ids = {normalized_location_id}

        if include_ancestors:
            visible_location_ids.update(
                str(location.get("record_id", "") or "")
                for location in ancestor_locations(
                    normalized_location_id,
                    self.location_provider(),
                )
            )

        self.ensure_event_cache()
        matching_event_ids = {
            event["record_id"]
            for visible_location_id in visible_location_ids
            for event in self._events_by_location_id.get(
                visible_location_id,
                [],
            )
        }
        return deepcopy(
            [
                event
                for event in self._event_cache
                if event["record_id"] in matching_event_ids
            ]
        )

    def people_options(self):
        database_revision = getattr(self.database, "revision", None)
        cacheable = isinstance(database_revision, int)

        if (
            self._people_options_cache is not None
            and cacheable
            and self._people_options_cache_revision == database_revision
        ):
            return list(self._people_options_cache)

        groups = self.mage_groups()
        options = [
            {
                "value": str(person.get("record_id", "") or ""),
                "label": str(
                    person.get("displayed_name", "") or "Unnamed magician"
                ).strip(),
                "person": deepcopy(person),
                "group_name": mage_group_definition(
                    person.get("mage_group_id"),
                    groups,
                )["name"],
            }
            for person in self.people_summaries()
            if str(person.get("record_id", "") or "").strip()
        ]
        options.sort(key=self.association_option_sort_key)
        self._people_options_cache = options
        self._people_options_by_id_cache = {
            str(option.get("value", "") or "").strip(): option
            for option in options
            if str(option.get("value", "") or "").strip()
        }
        self._people_options_cache_revision = (
            database_revision if cacheable else None
        )
        return list(options)

    def people_options_for_ids(self, person_ids=()):
        """Build chooser rows only for the requested people.

        Compact event fields and timeline summaries call this method.  The
        complete searchable catalogue is still built by ``people_options``
        when the user explicitly opens the person chooser.
        """
        requested_ids = self.unique_person_ids(person_ids)
        summaries = self.people_summaries_by_ids(requested_ids)
        found_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in summaries
            if isinstance(person, dict)
        }
        # A disposable index can briefly lag a newly created/edited person.
        # Compact event pickers must still show every linked participant, so
        # use a few targeted canonical reads rather than silently dropping
        # those rows or scanning all people.
        record_reader = getattr(self.database, "read_record", None)
        if callable(record_reader):
            for person_id in requested_ids:
                if person_id in found_ids:
                    continue
                person = record_reader("people", person_id)
                if isinstance(person, dict):
                    summaries.append(person)
                    found_ids.add(person_id)

        groups = self.mage_groups()
        options = [
            {
                "value": str(person.get("record_id", "") or ""),
                "label": str(
                    person.get("displayed_name", "") or "Unnamed magician"
                ).strip(),
                "person": deepcopy(person),
                "group_name": mage_group_definition(
                    person.get("mage_group_id"),
                    groups,
                )["name"],
            }
            for person in summaries
            if str(person.get("record_id", "") or "").strip()
        ]
        options.sort(key=self.association_option_sort_key)
        return options

    def people_option_labels(self, person_ids=()):
        requested_ids = {
            str(person_id or "").strip()
            for person_id in person_ids or ()
            if str(person_id or "").strip()
        }
        options_by_id = {
            str(option.get("value", "") or "").strip(): option
            for option in self.people_options_for_ids(requested_ids)
        }
        return {
            person_id: str(
                options_by_id.get(person_id, {}).get(
                    "label", "Unknown person"
                )
                or "Unknown person"
            ).strip()
            for person_id in requested_ids
        }

    def person_can_earn_eminence(self, person_id):
        selected_person_id = str(person_id or "").strip()
        if not selected_person_id:
            return False
        people = self.people_summaries_by_ids((selected_person_id,))
        return bool(people and not people[0].get("non_magical"))

    def eminence_eligible_person_ids(self):
        database_revision = getattr(self.database, "revision", None)

        if (
            self._eminence_eligible_ids_cache is not None
            and isinstance(database_revision, int)
            and database_revision
            == self._eminence_eligible_ids_cache_revision
        ):
            return set(self._eminence_eligible_ids_cache)

        eligible_ids = {
            str(person.get("record_id", "") or "").strip()
            for person in self.people_summaries()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
            and not bool(person.get("non_magical"))
        }

        if isinstance(database_revision, int):
            self._eminence_eligible_ids_cache = set(eligible_ids)
            self._eminence_eligible_ids_cache_revision = database_revision

        return eligible_ids

    def with_eligible_eminence(
        self,
        event,
        eligible_person_ids=None,
    ):
        normalized = normalize_world_event(event)
        eligible_ids = (
            self.eminence_eligible_person_ids()
            if eligible_person_ids is None
            else set(eligible_person_ids)
        )
        awarded_person_ids = [
            person_id
            for person_id in normalized.get(
                "eminence_person_ids",
                [],
            )
            if person_id in eligible_ids
        ]
        normalized["eminence_person_ids"] = awarded_person_ids
        normalized["eminence_skills"] = {
            person_id: skill
            for person_id, skill in normalized.get(
                "eminence_skills",
                {},
            ).items()
            if person_id in awarded_person_ids
        }
        return normalized

    def suggest_event_eminence_skill(
        self,
        person_id,
        event_identity="",
    ):
        selected_person_id = str(person_id or "").strip()
        record_provider = getattr(self.database, "get_record", None)
        person = (
            record_provider("people", selected_person_id)
            if callable(record_provider) and selected_person_id
            else None
        )
        if not isinstance(person, dict):
            person = next(
                (
                    candidate
                    for candidate in self.people_provider()
                    if isinstance(candidate, dict)
                    and str(candidate.get("record_id", "") or "").strip()
                    == selected_person_id
                ),
                {},
            )
        return suggested_event_eminence_skill(
            person.get("development_plan"),
            selected_person_id,
            event_identity,
        )

    def mage_groups(self):
        if self.mage_groups_provider is not None:
            return normalize_mage_groups(
                self.mage_groups_provider()
            )

        settings = self.database.data.get(
            "_application_settings",
            {},
        )
        stored_groups = (
            settings.get("mage_groups")
            if isinstance(settings, dict)
            else None
        )
        return normalize_mage_groups(stored_groups)

    def school_records(self):
        game_database = getattr(self, "game_database", None)

        if game_database is not None and bool(
            getattr(game_database, "loaded", False)
        ):
            return game_database.schools()

        return []

    def create_event_person(self, values):
        if self.people_creator is None:
            raise ValueError("The people collection is unavailable.")

        return deepcopy(self.people_creator(values))

    def current_location_id_for_person(self, person_id):
        selected_person_id = str(person_id or "").strip()

        if not selected_person_id:
            return ""

        person = next(
            (
                candidate
                for candidate in self.people_provider()
                if isinstance(candidate, dict)
                and str(candidate.get("record_id", "") or "").strip()
                == selected_person_id
            ),
            None,
        )

        if person is None:
            return ""

        locations = self.location_records()
        locations_by_id = {
            str(location.get("record_id", "") or "").strip(): location
            for location in locations
            if str(location.get("record_id", "") or "").strip()
        }
        location_ids_by_name = {}

        for location_id, location in locations_by_id.items():
            location_name = str(
                location.get("name", "") or ""
            ).strip().casefold()
            location_label = recent_location_label(
                location_id,
                locations,
            ).strip().casefold()

            if location_name and location_name not in location_ids_by_name:
                location_ids_by_name[location_name] = location_id

            if location_label:
                location_ids_by_name[location_label] = location_id

        candidates = []

        for event in normalize_timeline_events(
            person.get("timeline_events", [])
        ):
            event_type = str(event.get("event_type", "") or "").strip()

            if event_type not in (
                "born",
                "starting_location",
                "relocated",
            ):
                continue

            location_id = next(
                (
                    str(location_id or "").strip()
                    for location_id in reversed(
                        event.get("location_ids", []) or []
                    )
                    if str(location_id or "").strip() in locations_by_id
                ),
                "",
            )

            if not location_id:
                location_id = location_ids_by_name.get(
                    str(event.get("detail", "") or "")
                    .strip()
                    .casefold(),
                    "",
                )

            if not location_id:
                continue

            event_key = world_event_sort_key(
                {
                    "date": event.get("date", ""),
                    "time": event.get("time", ""),
                    "title": event.get("detail", ""),
                    "record_id": event.get("event_id", ""),
                }
            )
            candidates.append(
                (
                    event_key[0],
                    1 if event_type == "relocated" else 0,
                    event_key[1],
                    event_key[2],
                    event_key[3],
                    location_id,
                )
            )

        for event in self.events_for_person(selected_person_id):
            if (
                event.get("event_type") != "relocated"
                or selected_person_id not in event.get("person_ids", [])
            ):
                continue

            location_id = next(
                (
                    str(location_id or "").strip()
                    for location_id in reversed(
                        event.get("location_ids", []) or []
                    )
                    if str(location_id or "").strip() in locations_by_id
                ),
                "",
            )

            if not location_id:
                continue

            event_key = world_event_sort_key(event)
            candidates.append(
                (
                    event_key[0],
                    1,
                    event_key[1],
                    event_key[2],
                    event_key[3],
                    location_id,
                )
            )

        if candidates:
            candidates.sort()
            return candidates[-1][-1]

        for field_name in (
            "current_location",
            "location",
            "starting_location",
            "birth_location",
        ):
            stored_location = str(
                person.get(field_name, "") or ""
            ).strip()
            location_id = (
                stored_location
                if stored_location in locations_by_id
                else location_ids_by_name.get(
                    stored_location.casefold(),
                    "",
                )
            )

            if location_id:
                return location_id

        return ""

    def location_options(
        self,
        available_for_founding=False,
        include_ids=(),
    ):
        locations = self.location_records(
            available_for_founding=available_for_founding,
            include_ids=include_ids,
        )
        options = [
            {
                "value": str(location.get("record_id", "") or ""),
                "label": recent_location_label(
                    location.get("record_id", ""),
                    locations,
                ),
            }
            for location in locations
            if str(location.get("record_id", "") or "").strip()
        ]
        options.sort(key=self.association_option_sort_key)
        return options

    def location_records(
        self,
        available_for_founding=False,
        include_ids=(),
    ):
        locations = [
            deepcopy(location)
            for location in self.location_provider()
            if isinstance(location, dict)
        ]

        if not available_for_founding:
            return locations

        included_ids = {
            str(location_id or "").strip()
            for location_id in include_ids or ()
            if str(location_id or "").strip()
        }
        world_events_by_location_id = {}

        for event in normalize_world_events(
            self.database.list_records("events")
        ):
            if bool(event.get("organization_event")):
                continue

            for location_id in event.get("location_ids", []):
                normalized_location_id = str(
                    location_id or ""
                ).strip()

                if not normalized_location_id:
                    continue

                world_events_by_location_id.setdefault(
                    normalized_location_id,
                    [],
                ).append(event)

        return [
            location
            for location in locations
            if (
                str(location.get("record_id", "") or "")
                in included_ids
                or not location_foundation_event_state(
                    location,
                    world_events_by_location_id.get(
                        str(location.get("record_id", "") or "").strip(),
                        [],
                    ),
                    world_events_are_normalized=True,
                ).get(
                    "foundation_event_id"
                )
            )
        ]

    def location_has_foundation_event(
        self,
        location_id,
        ignored_event_id="",
    ):
        selected_id = str(location_id or "").strip()
        ignored_id = str(ignored_event_id or "").strip()
        location = next(
            (
                candidate
                for candidate in self.location_provider()
                if str(candidate.get("record_id", "") or "").strip()
                == selected_id
            ),
            None,
        )

        if location is None:
            return False

        world_events = [
            event
            for event in (
                self.database.list_records("events")
                if self.database is not None
                else []
            )
            if str(event.get("record_id", "") or "").strip()
            != ignored_id
        ]
        state = location_foundation_event_state(
            location,
            world_events,
        )
        return bool(state.get("foundation_event_id"))

    def organization_records(self):
        database_revision = getattr(self.database, "revision", None)
        if (
            self._organization_records_cache is not None
            and database_revision
            == self._organization_records_cache_revision
        ):
            return deepcopy(self._organization_records_cache)

        organizations = [
            normalize_organization_record(organization)
            for organization in self.database.list_records(
                "organizations"
            )
            if isinstance(organization, dict)
        ]
        self._organization_records_cache = organizations
        self._organization_records_cache_revision = database_revision
        return deepcopy(organizations)

    def organization_options(self):
        organizations = self.organization_records()
        locations = self.location_provider()
        options = [
            {
                "value": str(
                    organization.get("record_id", "") or ""
                ).strip(),
                "label": organization_context_label(
                    organization.get("record_id", ""),
                    organizations,
                    locations,
                ),
            }
            for organization in organizations
            if str(
                organization.get("record_id", "") or ""
            ).strip()
        ]
        options.sort(key=self.association_option_sort_key)
        return options

    def create_placeholder_location(self, place, parent_location_id=""):
        if self.location_creator is None:
            raise ValueError("The location collection is unavailable.")

        created = self.location_creator(
            {
                "name": str(place or "").strip(),
                "parent_location_id": str(
                    parent_location_id or ""
                ).strip(),
                "demographics": "",
                "notes": "",
                "extinct": False,
                "extinction_year": "",
                "timeline_events": [],
            }
        )
        return deepcopy(created)

    def defined_year_bounds(self):
        start_years = []
        end_years = []

        for period in self.period_provider():
            try:
                start_years.append(
                    int(period.get("calculation_start_year"))
                )
                end_years.append(
                    int(period.get("calculation_end_year"))
                )
            except (AttributeError, TypeError, ValueError):
                continue

        if not start_years or not end_years:
            return None, None

        return min(start_years), max(end_years)

    def clamp_year_to_defined_periods(self, year):
        normalized_year = int(year)
        periods = []

        for period in self.period_provider():
            try:
                start_year = int(
                    period.get("calculation_start_year")
                )
                end_year = int(
                    period.get("calculation_end_year")
                )
            except (AttributeError, TypeError, ValueError):
                continue

            periods.append((start_year, end_year))

        if not periods:
            return normalized_year

        periods.sort()

        if normalized_year == 0:
            normalized_year = 1

        for start_year, end_year in periods:
            if start_year <= normalized_year <= end_year:
                return normalized_year

        if normalized_year < periods[0][0]:
            return periods[0][0]

        if normalized_year > periods[-1][1]:
            return periods[-1][1]

        for index in range(len(periods) - 1):
            previous_end = periods[index][1]
            next_start = periods[index + 1][0]

            if previous_end < normalized_year < next_start:
                if (
                    normalized_year - previous_end
                    <= next_start - normalized_year
                ):
                    return previous_end

                return next_start

        return normalized_year

    def recent_people_options(self, limit=5):
        preferred_ids = self.recent_interaction_ids(
            RECENT_PERSON_STORAGE_KEY,
        )
        # "Recently viewed" means profiles the user actually opened.  Event
        # participants are not a substitute; using them as a fallback made
        # this list look like an arbitrary collection of famous people.
        options = self.people_options_for_ids(preferred_ids)
        options_by_id = {
            str(option.get("value", "") or "").strip(): option
            for option in options
            if str(option.get("value", "") or "").strip()
        }
        return self.recent_association_options(
            "person_ids",
            options,
            limit,
            preferred_ids,
            options_by_id=options_by_id,
        )

    def recent_location_options(self, limit=5):
        return self.recent_association_options(
            "location_ids",
            self.location_options(),
            limit,
            self.recent_interaction_ids(
                RECENT_LOCATION_STORAGE_KEY,
                excluded_ids=(RECENT_WORLD_LOCATION_ID,),
            ),
        )

    def remember_location_selection(self, location_id):
        selected_location_id = str(location_id or "").strip()
        available_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in self.location_provider()
            if isinstance(location, dict)
            and str(location.get("record_id", "") or "").strip()
        }

        if not selected_location_id or selected_location_id not in available_ids:
            return False

        stored_history = self.database.data.get(
            RECENT_LOCATION_STORAGE_KEY,
            [],
        )
        history = (
            [
                str(stored_id or "").strip()
                for stored_id in stored_history
                if str(stored_id or "").strip()
            ]
            if isinstance(stored_history, list)
            else []
        )
        updated_history = [
            selected_location_id,
            *[
                stored_id
                for stored_id in history
                if stored_id != selected_location_id
            ],
        ][:RECENT_ASSOCIATION_STORAGE_LIMIT]

        if updated_history == history:
            return False

        self.database.data[RECENT_LOCATION_STORAGE_KEY] = updated_history
        self.database.dirty = True
        return True

    def recent_association_options(
        self,
        field_name,
        options,
        limit,
        preferred_ids=(),
        options_by_id=None,
    ):
        resolved_options_by_id = (
            options_by_id
            if isinstance(options_by_id, dict)
            else {
                str(option.get("value", "") or ""): option
                for option in options
                if str(option.get("value", "") or "").strip()
            }
        )
        recent_options = []
        candidate_ids = [
            *[
                str(association_id or "").strip()
                for association_id in preferred_ids
                if str(association_id or "").strip()
            ],
            *self.recent_association_ids(field_name),
        ]
        used_ids = set()

        for association_id in candidate_ids:
            if association_id in used_ids:
                continue

            used_ids.add(association_id)
            option = resolved_options_by_id.get(association_id)

            if option is None:
                continue

            recent_options.append(deepcopy(option))

            if len(recent_options) >= max(0, int(limit)):
                break

        return recent_options

    def recent_interaction_ids(self, storage_key, excluded_ids=()):
        preference_reader = getattr(self.database, "get_preference", None)
        if (
            storage_key == RECENT_PERSON_STORAGE_KEY
            and callable(preference_reader)
        ):
            stored_history = preference_reader(storage_key, [])
        else:
            stored_history = self.database.data.get(storage_key, [])

        if not isinstance(stored_history, list):
            return []

        excluded = {
            str(record_id or "").strip()
            for record_id in excluded_ids
            if str(record_id or "").strip()
        }
        recent_ids = []

        for record_id in stored_history:
            normalized_id = str(record_id or "").strip()

            if (
                not normalized_id
                or normalized_id in excluded
                or normalized_id in recent_ids
            ):
                continue

            recent_ids.append(normalized_id)

        return recent_ids

    def recent_association_ids(self, field_name):
        if field_name not in ("person_ids", "location_ids"):
            raise KeyError(f"Unknown event association field: {field_name}")

        history = self.database.data.get(
            RECENT_ASSOCIATION_STORAGE_KEY,
            {},
        )
        stored_ids = (
            history.get(field_name, [])
            if isinstance(history, dict)
            else []
        )

        if isinstance(stored_ids, list) and stored_ids:
            return [
                str(association_id or "").strip()
                for association_id in stored_ids
                if str(association_id or "").strip()
            ]

        inferred_ids = []

        for event in reversed(self.database.list_records("events")):
            association_ids = event.get(field_name, [])

            if not isinstance(association_ids, list):
                continue

            for association_id in reversed(association_ids):
                normalized_id = str(association_id or "").strip()

                if normalized_id and normalized_id not in inferred_ids:
                    inferred_ids.append(normalized_id)

                if len(inferred_ids) >= RECENT_ASSOCIATION_STORAGE_LIMIT:
                    return inferred_ids

        return inferred_ids

    def remember_associations(self, event):
        current_history = self.database.data.get(
            RECENT_ASSOCIATION_STORAGE_KEY,
            {},
        )
        history = (
            deepcopy(current_history)
            if isinstance(current_history, dict)
            else {}
        )

        for field_name in ("person_ids", "location_ids"):
            previous_ids = self.recent_association_ids(field_name)
            event_ids = [
                str(association_id or "").strip()
                for association_id in (
                    event_linked_person_ids(event)
                    if field_name == "person_ids"
                    else event.get(field_name, [])
                )
                if str(association_id or "").strip()
            ]
            history[field_name] = (
                event_ids
                + [
                    association_id
                    for association_id in previous_ids
                    if association_id not in event_ids
                ]
            )[:RECENT_ASSOCIATION_STORAGE_LIMIT]

        self.database.data[RECENT_ASSOCIATION_STORAGE_KEY] = history
        self.database.dirty = True

    def association_option_sort_key(self, option):
        return (
            str(option.get("label", "") or "").casefold(),
            str(option.get("value", "") or ""),
        )

    def association_label_context(self):
        """Build shared lookup tables for rendering a collection of events."""

        people_by_id = {
            str(person.get("record_id", "") or ""): str(
                person.get("displayed_name", "") or "Unnamed magician"
            ).strip()
            for person in self.people_summaries()
        }
        locations = self.location_provider()
        organizations = self.organization_records()
        location_labels = {
            str(location.get("record_id", "") or ""): recent_location_label(
                location.get("record_id", ""),
                locations,
            )
            for location in locations
        }
        return {
            "people_by_id": people_by_id,
            "locations": locations,
            "organizations": organizations,
            "location_labels": location_labels,
            "periods": self.period_provider(),
        }

    def association_labels(self, event, context=None):
        normalized = normalize_world_event(event)
        resolved_context = (
            context
            if isinstance(context, dict)
            else self.association_label_context()
        )
        people_by_id = resolved_context.get("people_by_id", {})
        locations = resolved_context.get("locations", [])
        organizations = resolved_context.get("organizations", [])
        location_labels = resolved_context.get("location_labels", {})
        return {
            "people": [
                people_by_id.get(person_id, "Missing person")
                for person_id in normalized["person_ids"]
            ],
            "periods": self.period_names_for_date(
                normalized.get("date"),
                resolved_context.get("periods"),
            ),
            "locations": [
                location_labels.get(location_id, "Missing location")
                for location_id in normalized["location_ids"]
            ],
            "organizations": (
                [
                    organization_context_label(
                        normalized.get("organization_id", ""),
                        organizations,
                        locations,
                    )
                ]
                if normalized.get("organization_id")
                else []
            ),
        }

    def infer_period_name(self, event):
        normalized = normalize_world_event(event)
        period_names = self.period_names_for_event(normalized)
        return period_names[0] if period_names else ""

    def period_names_for_event(self, event):
        normalized = normalize_world_event(event)
        return self.period_names_for_date(normalized.get("date"))

    def period_names_for_date(self, date_value, period_definitions=None):
        event_year = world_event_year(date_value)

        if event_year is None:
            return []

        matching_names = []

        definitions = (
            period_definitions
            if isinstance(period_definitions, list)
            else self.period_provider()
        )
        for period in definitions:
            try:
                start_year = int(period.get("calculation_start_year"))
                end_year = int(period.get("calculation_end_year"))
            except (TypeError, ValueError):
                continue

            period_name = str(period.get("name", "") or "").strip()

            if (
                period_name
                and start_year <= event_year <= end_year
                and period_name not in matching_names
            ):
                matching_names.append(period_name)

        return matching_names

    def validate_associations(
        self,
        event,
        current_event=None,
        allow_death_replacement=False,
    ):
        self.validate_job_event(event, current_event)
        self.validate_birth_event(event, current_event)
        self.validate_death_event(
            event,
            current_event,
            allow_death_replacement,
        )
        self.validate_murder_event(
            event,
            current_event,
            allow_death_replacement,
        )
        self.validate_ghost_event_dependencies(
            event,
            current_event,
            allow_death_replacement,
        )

        if (
            event.get("event_type") == "got_married"
            and len(event.get("person_ids", [])) != 2
        ):
            raise ValueError(
                "A Marriage event needs exactly two people."
            )

        if (
            event.get("event_type") == "relocated"
            and len(event.get("location_ids", [])) != 1
        ):
            raise ValueError(
                "Select exactly one destination location for a relocation."
            )

        if (
            event.get("event_type") == "founding"
            and len(event.get("location_ids", [])) != 1
        ):
            raise ValueError(
                "Select exactly one location for a founding event."
            )

        if (
            event.get("event_type") == "extinction"
            and len(event.get("location_ids", [])) != 1
        ):
            raise ValueError(
                "Select exactly one location for an extinction event."
            )

        if (
            event.get("event_type") in (
                BIRTH_EVENT_TYPE,
                *DEATH_EVENT_TYPES,
            )
            and len(event.get("location_ids", [])) > 1
        ):
            raise ValueError(
                "A Birth, Death, or Murder event can use no more than one "
                "location."
            )

        if event.get("event_type") == "founding":
            founding_location_id = event["location_ids"][0]
            ignored_event_id = (
                str(current_event.get("record_id", "") or "")
                if isinstance(current_event, dict)
                else ""
            )

            if self.location_has_foundation_event(
                founding_location_id,
                ignored_event_id,
            ):
                raise ValueError(
                    "The selected location already has a founding event."
                )

        if (
            event.get("event_type")
            in ("organization_founding", "joined_faction", "left_faction")
            and not str(event.get("organization_id", "") or "").strip()
        ):
            raise ValueError(
                "Select exactly one faction organization."
            )

        if (
            event.get("event_type")
            in ("organization_founding", "joined_faction", "left_faction")
            and event.get("location_ids", [])
        ):
            raise ValueError(
                "Organization founding events do not use locations."
            )

        if (
            event.get("event_type")
            in ("began_friendship", "romance", "breakup")
            and len(event.get("person_ids", [])) < 2
        ):
            event_label = {
                "began_friendship": "friendship",
                "romance": "romance",
                "breakup": "breakup",
            }[event.get("event_type")]
            raise ValueError(
                f"A {event_label} event needs at least two people."
            )

        if event.get("event_type") == "foster_child":
            foster_parent_ids = list(
                event.get("foster_parent_person_ids", []) or []
            )
            foster_child_ids = list(
                event.get("foster_child_person_ids", []) or []
            )

            if len(foster_parent_ids) != 1 or len(foster_child_ids) != 1:
                raise ValueError(
                    "A foster-child event needs one foster parent and one "
                    "foster child."
                )

            if foster_parent_ids[0] == foster_child_ids[0]:
                raise ValueError(
                    "A person cannot be their own foster parent."
                )

        linked_person_ids = event_linked_person_ids(event)
        raw_item_new_owners = event.get("item_new_owners", {})
        referenced_person_ids = {
            *linked_person_ids,
            *(
                str(owner.get("person_id", "") or "").strip()
                for owner in (
                    raw_item_new_owners.values()
                    if isinstance(raw_item_new_owners, dict)
                    else ()
                )
                if isinstance(owner, dict)
                and str(owner.get("person_id", "") or "").strip()
            ),
        }
        people = self.people_summaries() if referenced_person_ids else []
        known_person_ids = {
            str(person.get("record_id", "") or "")
            for person in people
        }
        person_names_by_id = {
            str(person.get("record_id", "") or ""): str(
                person.get("displayed_name", "") or "Unnamed person"
            ).strip()
            for person in people
            if str(person.get("record_id", "") or "")
        }
        known_period_names = (
            {
                str(period.get("name", "") or "")
                for period in self.period_provider()
            }
            if event.get("period_names")
            else set()
        )
        known_location_ids = (
            {
                str(location.get("record_id", "") or "")
                for location in self.location_provider()
            }
            if event.get("location_ids")
            else set()
        )
        organizations = (
            self.organization_records()
            if event.get("organization_id")
            else []
        )
        known_organization_ids = {
            str(organization.get("record_id", "") or "")
            for organization in organizations
        }
        known_item_ids = (
            {
                str(item.get("record_id", "") or "")
                for item in self.item_records()
            }
            if event.get("item_ids")
            else set()
        )
        if event.get("event_type") != "murder":
            event_role_ids = [
                *event.get("person_ids", []),
                *event.get("witness_person_ids", []),
                *event.get("affected_person_ids", []),
            ]

            if len(event_role_ids) != len(set(event_role_ids)):
                raise ValueError(
                    "Each person can belong to only one event category."
                )

        missing_people = [
            person_id
            for person_id in linked_person_ids
            if person_id not in known_person_ids
        ]
        missing_periods = [
            period_name
            for period_name in event["period_names"]
            if period_name not in known_period_names
        ]
        missing_locations = [
            location_id
            for location_id in event["location_ids"]
            if location_id not in known_location_ids
        ]
        missing_items = [
            item_id
            for item_id in event.get("item_ids", [])
            if item_id not in known_item_ids
        ]
        item_link_types = normalize_item_event_link_types(
            event.get("item_link_types"),
            event.get("item_ids", []),
            event.get("event_type", ""),
        )
        item_new_owners = normalize_item_event_new_owners(
            event.get("item_new_owners"),
            event.get("item_ids", []),
            item_link_types,
        )
        missing_item_owner_ids = [
            item_id
            for item_id in event.get("item_ids", [])
            if item_link_types.get(item_id)
            in ITEM_EVENT_NEW_OWNER_LINK_TYPES
            and not item_new_owners.get(item_id, {}).get("person_id")
        ]
        unknown_item_owner_ids = [
            owner["person_id"]
            for owner in item_new_owners.values()
            if owner["person_id"]
            and owner["person_id"] not in known_person_ids
        ]

        if missing_people:
            raise ValueError(
                "One or more selected people no longer exist."
            )

        if missing_periods:
            raise ValueError(
                "One or more selected periods no longer exist."
            )

        if missing_locations:
            raise ValueError(
                "One or more selected locations no longer exist."
            )

        if missing_items:
            raise ValueError(
                "One or more selected items no longer exist."
            )

        if missing_item_owner_ids:
            raise ValueError(
                "Choose the new owner for every Passed down, Gifted, or "
                "Taken item link."
            )

        if unknown_item_owner_ids:
            raise ValueError(
                "One or more selected new item owners no longer exist."
            )

        for owner in item_new_owners.values():
            if owner["person_id"] in person_names_by_id:
                owner["person_name"] = person_names_by_id[
                    owner["person_id"]
                ]

        event["item_new_owners"] = item_new_owners

        if (
            event.get("event_type")
            in ("organization_founding", "joined_faction", "left_faction")
            and event.get("organization_id")
            not in known_organization_ids
        ):
            raise ValueError(
                "The selected organization no longer exists."
            )

        if event.get("event_type") in (
            "joined_faction",
            "left_faction",
        ):
            organization = next(
                (
                    item
                    for item in organizations
                    if str(item.get("record_id", "") or "")
                    == str(event.get("organization_id", "") or "")
                ),
                None,
            )
            if not organization or not organization.get("is_faction"):
                raise ValueError(
                    "Faction membership events require an organization "
                    "marked as an in-world faction."
                )

    def validate_birth_event(self, event, current_event=None):
        if canonical_event_type(
            (event or {}).get("event_type")
        ) != BIRTH_EVENT_TYPE:
            return

        baby_ids = birth_event_baby_ids(event)
        birthing_parent_ids = list(
            (event or {}).get("birthing_parent_person_ids", []) or []
        )
        non_birthing_parent_ids = list(
            (event or {}).get(
                "non_birthing_parent_person_ids",
                [],
            )
            or []
        )

        if len(baby_ids) != 1:
            raise ValueError(
                "A Birth event needs exactly one baby."
            )

        if len((event or {}).get("location_ids", []) or []) != 1:
            raise ValueError(
                "A Birth event needs exactly one starting location."
            )

        if len(birthing_parent_ids) > 1:
            raise ValueError(
                "A Birth event can have no more than one birthing parent."
            )

        if len(non_birthing_parent_ids) > 1:
            raise ValueError(
                "A Birth event can have no more than one non-birthing "
                "parent."
            )

        all_role_ids = [
            *baby_ids,
            *birthing_parent_ids,
            *non_birthing_parent_ids,
        ]

        if len(all_role_ids) != len(set(all_role_ids)):
            raise ValueError(
                "The baby and parents must be different people."
            )

        if (event or {}).get("eminence_person_ids", []):
            raise ValueError(
                "A Birth event cannot award Eminence."
            )

        current_baby_ids = birth_event_baby_ids(current_event)

        if current_baby_ids and baby_ids != current_baby_ids:
            raise ValueError(
                "The baby on an existing Birth event cannot be changed."
            )

        current_event_id = str(
            (current_event or {}).get("record_id", "") or ""
        ).strip()

        for stored_event in (
            self.database.list_records("events")
            if self.database is not None
            else []
        ):
            if (
                str(stored_event.get("record_id", "") or "").strip()
                == current_event_id
            ):
                continue

            if baby_ids[0] in birth_event_baby_ids(stored_event):
                raise ValueError(
                    "This baby already has a Birth event."
                )

        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in self.people_provider()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }
        baby = people_by_id.get(baby_ids[0])

        if baby is None:
            return

        dated_baby = deepcopy(baby)
        birth_date = str((event or {}).get("date", "") or "").strip()

        if birth_date:
            birth_year, birth_month, birth_day = split_world_event_date(
                birth_date
            )
            dated_baby.update(
                {
                    "birth_year": int(birth_year),
                    "birth_month": (
                        int(birth_month) if birth_month else None
                    ),
                    "birth_day": int(birth_day) if birth_day else None,
                }
            )
        relationship_map = FamilyRelationshipMap(
            self.people_provider()
        )

        for parent_ids, role_label, required_capability in (
            (birthing_parent_ids, "birthing parent", True),
            (
                non_birthing_parent_ids,
                "non-birthing parent",
                False,
            ),
        ):
            if not parent_ids:
                continue

            parent_id = parent_ids[0]
            parent = people_by_id.get(parent_id)

            if parent is None:
                continue

            if bool(parent.get("does_not_have_children")):
                raise ValueError(
                    f"The selected {role_label} is marked Does not have "
                    "children."
                )

            if person_can_give_birth(parent) != required_capability:
                requirement = "checked" if required_capability else "unchecked"
                raise ValueError(
                    f"A {role_label} must have Can give birth {requirement}."
                )

            if is_at_least_age(parent, dated_baby, 18) is False:
                raise ValueError(
                    f"The selected {role_label} must be at least 18 when "
                    "the baby is born."
                )

            if parent_id in relationship_map.descendants_of(baby_ids[0]):
                raise ValueError(
                    "A descendant cannot also be a biological parent."
                )

    def validate_death_event(
        self,
        event,
        current_event=None,
        allow_death_replacement=False,
    ):
        if canonical_event_type(
            (event or {}).get("event_type")
        ) != "died":
            return

        person_ids = list((event or {}).get("person_ids", []) or [])

        if len(person_ids) != 1:
            raise ValueError(
                "A Death event must belong to exactly one person."
            )

        self.require_person_without_other_death_event(
            person_ids[0],
            current_event,
            allow_death_replacement,
        )

    def validate_murder_event(
        self,
        event,
        current_event=None,
        allow_death_replacement=False,
    ):
        if canonical_event_type(
            (event or {}).get("event_type")
        ) != "murder":
            return

        perpetrator_ids = list(
            (event or {}).get("perpetrator_person_ids", []) or []
        )
        victim_ids = list(
            (event or {}).get("victim_person_ids", []) or []
        )
        witness_ids = list(
            (event or {}).get("witness_person_ids", []) or []
        )
        affected_ids = list(
            (event or {}).get("affected_person_ids", []) or []
        )

        if not perpetrator_ids:
            raise ValueError(
                "A Murder event needs at least one perpetrator."
            )

        unnamed_victim_count = sum(
            normalize_unnamed_victim_count(
                (event or {}).get(field_name, 0)
            )
            for field_name in (
                "unnamed_muggle_victim_count",
                "unnamed_mage_victim_count",
            )
        )

        if not victim_ids and not unnamed_victim_count:
            raise ValueError("A Murder event needs at least one victim.")

        if set(perpetrator_ids).intersection(victim_ids):
            raise ValueError(
                "The same person cannot be both perpetrator and victim."
            )

        all_role_ids = [
            *perpetrator_ids,
            *victim_ids,
            *witness_ids,
            *affected_ids,
        ]

        if len(all_role_ids) != len(set(all_role_ids)):
            raise ValueError(
                "Each Murder participant can belong to only one category."
            )

        victim_eminence_ids = set(victim_ids).intersection(
            (event or {}).get("eminence_person_ids", []) or []
        )

        if victim_eminence_ids:
            raise ValueError(
                "Victims cannot earn Eminence from a Murder event."
            )

        for victim_id in victim_ids:
            self.require_person_without_other_death_event(
                victim_id,
                current_event,
                allow_death_replacement,
            )

    def validate_ghost_event_dependencies(
        self,
        event=None,
        current_event=None,
        allow_death_replacement=False,
        deleting=False,
    ):
        prospective_event_type = canonical_event_type(
            (event or {}).get("event_type")
        )
        current_event_type = canonical_event_type(
            (current_event or {}).get("event_type")
        )
        relevant_event_types = {
            GHOST_EVENT_TYPE,
            "died",
            "murder",
        }

        if (
            prospective_event_type not in relevant_event_types
            and current_event_type not in relevant_event_types
        ):
            return

        stored_events = (
            self.database.list_records("events")
            if self.database is not None
            else []
        )
        has_stored_ghost_event = any(
            canonical_event_type(stored_event.get("event_type"))
            == GHOST_EVENT_TYPE
            for stored_event in stored_events
            if isinstance(stored_event, dict)
        )

        if (
            prospective_event_type != GHOST_EVENT_TYPE
            and not has_stored_ghost_event
        ):
            return

        current_event_id = str(
            (current_event or {}).get("record_id", "") or ""
        ).strip()
        prospective_event = (
            normalize_world_event(event)
            if isinstance(event, dict) and not deleting
            else None
        )
        prospective_events = []
        replaced_current = False

        for stored_event in stored_events:
            stored_event_id = str(
                stored_event.get("record_id", "") or ""
            ).strip()

            if current_event_id and stored_event_id == current_event_id:
                replaced_current = True

                if prospective_event is not None:
                    prospective_events.append(prospective_event)

                continue

            prospective_events.append(normalize_world_event(stored_event))

        if prospective_event is not None and not replaced_current:
            prospective_events.append(prospective_event)

        replacement_person_ids = (
            set(death_event_person_ids(prospective_event))
            if allow_death_replacement
            and prospective_event is not None
            else set()
        )
        people_by_id = {
            str(person.get("record_id", "") or "").strip(): person
            for person in self.people_provider()
            if isinstance(person, dict)
            and str(person.get("record_id", "") or "").strip()
        }

        for ghost_event in prospective_events:
            if canonical_event_type(
                ghost_event.get("event_type")
            ) != GHOST_EVENT_TYPE:
                continue

            ghost_person_ids = list(
                ghost_event.get("person_ids", []) or []
            )

            if len(ghost_person_ids) != 1:
                raise ValueError(
                    "A Returns as ghost event must belong to exactly one "
                    "person."
                )

            ghost_person_id = ghost_person_ids[0]
            shared_death_events = [
                candidate_event
                for candidate_event in prospective_events
                if ghost_person_id
                in death_event_person_ids(candidate_event)
            ]

            if ghost_person_id in replacement_person_ids:
                shared_death_events = [
                    prospective_event
                ]

            profile_death_events = []
            person = people_by_id.get(ghost_person_id)

            if (
                person is not None
                and ghost_person_id not in replacement_person_ids
            ):
                profile_death_events = [
                    timeline_event
                    for timeline_event in person.get(
                        "timeline_events",
                        [],
                    )
                    or []
                    if canonical_event_type(
                        (timeline_event or {}).get("event_type")
                    )
                    == "died"
                    and str(
                        (timeline_event or {}).get("date", "") or ""
                    ).strip()
                ]

            death_events = [
                *shared_death_events,
                *profile_death_events,
            ]

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

    def require_person_without_other_death_event(
        self,
        person_id,
        current_event=None,
        allow_death_replacement=False,
    ):
        selected_person_id = str(person_id or "").strip()
        current_event_id = str(
            (current_event or {}).get("record_id", "") or ""
        ).strip()
        stored_events = (
            self.database.list_records("events")
            if self.database is not None
            else []
        )

        for stored_event in stored_events:
            if (
                str(stored_event.get("record_id", "") or "").strip()
                == current_event_id
            ):
                continue

            if selected_person_id in death_event_person_ids(stored_event):
                if not allow_death_replacement:
                    raise DeathEventReplacementRequired(
                        [selected_person_id]
                    )

                return

        person = next(
            (
                candidate
                for candidate in self.people_provider()
                if str(candidate.get("record_id", "") or "").strip()
                == selected_person_id
            ),
            None,
        )

        if person is None:
            return

        for timeline_event in person.get("timeline_events", []) or []:
            if canonical_event_type(
                (timeline_event or {}).get("event_type")
            ) == "died":
                if not allow_death_replacement:
                    raise DeathEventReplacementRequired(
                        [selected_person_id]
                    )

                return

    def validate_job_event(self, event, current_event=None):
        event_type = canonical_event_type(
            (event or {}).get("event_type")
        )

        if event_type not in ("started_job", "received_raise"):
            return

        person_ids = list((event or {}).get("person_ids", []) or [])
        special_appointment_name = str(
            (event or {}).get("special_appointment_name", "") or ""
        ).strip()

        if len(person_ids) > 1:
            raise ValueError(
                "A job event can belong to only one person."
            )

        if bool(person_ids) == bool(special_appointment_name):
            raise ValueError(
                "Choose one person or enter one special appointment name."
            )

        if self.job_event_organization_job(event) is None:
            raise ValueError("Choose an existing organization job.")

        if (event or {}).get("salary") is None:
            raise ValueError("Enter the monthly salary for this job event.")

        if event_type == "received_raise":
            if special_appointment_name:
                raise ValueError(
                    "A salary raise must belong to an individual."
                )

            if self.active_assignment_for_job_event(event) is None:
                raise ValueError(
                    "The selected person is not holding this job on the "
                    "event date."
                )

            return

        if special_appointment_name:
            special_assignment = self.started_job_assignment_id(
                (event or {}).get("record_id", "")
            )
            special_assignment_values = new_job_record(
                str((event or {}).get("organization_id", "") or ""),
                str((event or {}).get("organization_name", "") or ""),
                str((event or {}).get("job_title", "") or ""),
                (event or {}).get("salary"),
                *split_world_event_date((event or {}).get("date", "")),
                *(
                    value or None
                    for value in split_world_event_date(
                        (event or {}).get("job_end_date", "")
                    )
                ),
                str(
                    (event or {}).get("organization_job_id", "") or ""
                ),
            )
            special_assignment_values["record_id"] = special_assignment
            selected_job = self.job_event_organization_job(event)["job"]
            require_job_position_available(
                selected_job,
                special_assignment_values,
                self.all_job_assignments_with_special_appointments(),
                str(
                    (event or {}).get("job_assignment_id", "")
                    or (current_event or {}).get("job_assignment_id", "")
                    or special_assignment
                ).strip(),
            )
            return

        assignment = self.started_job_assignment(event)
        selected_job = self.job_event_organization_job(event)["job"]
        ignored_assignment_id = str(
            (event or {}).get("job_assignment_id", "") or ""
        ).strip()

        if not ignored_assignment_id and current_event is not None:
            ignored_assignment_id = str(
                current_event.get("job_assignment_id", "") or ""
            ).strip()

        require_job_position_available(
            selected_job,
            assignment,
            self.all_job_assignments_with_special_appointments(),
            ignored_assignment_id,
        )
        require_person_job_available(
            assignment,
            self.person_job_assignments(person_ids[0]),
            ignored_assignment_id,
        )


WorldEventController = EventController
