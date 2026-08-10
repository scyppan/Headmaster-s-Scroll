from copy import deepcopy

from mage_maker.sections.locations.models import (
    descendant_ids,
    founding_event_title,
    location_extinction_event_state,
    location_foundation_event_state,
    location_events_for_period,
    location_depth,
    location_path,
    location_paths_by_id,
    normalize_location_event,
    normalize_location_record,
    visible_location_timeline,
)
from mage_maker.sections.locations.periods import categorized_people_for_period
from mage_maker.sections.timeline.locations import normalize_location
from mage_maker.sections.events.models import (
    normalize_world_events,
    world_event_year,
)


RECENT_LOCATION_STORAGE_KEY = "_recent_locations"
RECENT_LOCATION_STORAGE_LIMIT = 12
RECENT_WORLD_LOCATION_ID = "__mage_maker_world__"


def mage_location_names(people):
    names = []
    used_names = set()

    for person in people if isinstance(people, list) else []:
        if not isinstance(person, dict):
            continue

        candidates = [
            person.get("starting_location"),
            person.get("birth_location"),
            person.get("current_location"),
            person.get("location"),
        ]

        for event in person.get("timeline_events", []):
            if not isinstance(event, dict):
                continue

            event_type = str(event.get("event_type", "") or "").strip()

            if event_type in ("starting_location", "relocated"):
                candidates.append(event.get("detail"))

            candidates.append(event.get("location"))

        for candidate in candidates:
            name = " ".join(str(candidate or "").strip().split())
            name_key = normalize_location(name)

            if not name_key or name_key in used_names:
                continue

            used_names.add(name_key)
            names.append(name)

    return names


class LocationController:
    def __init__(self, database, people_provider):
        self.database = database
        self.people_provider = people_provider
        self._locations_cache = None
        self._foundation_state_cache = {}
        self._extinction_state_cache = {}
        self._timeline_cache = {}
        self._distinctions_cache = {}
        self._mage_locations_synchronized = False

    def invalidate_caches(self, include_people_sync=False):
        self._locations_cache = None
        self._foundation_state_cache = {}
        self._extinction_state_cache = {}
        self._timeline_cache = {}
        self._distinctions_cache = {}

        if include_people_sync:
            self._mage_locations_synchronized = False

    def list_locations(self):
        if not self._mage_locations_synchronized:
            self.synchronize_mage_locations()
            self._mage_locations_synchronized = True

        if self._locations_cache is not None:
            return deepcopy(self._locations_cache)

        locations = self.database.list_records("locations")
        world_events = normalize_world_events(
            self.database.list_records("events")
        )
        world_events_by_location_id = {}

        for event in world_events:
            if not isinstance(event, dict):
                continue

            for location_id in event.get("location_ids", []) or []:
                world_events_by_location_id.setdefault(
                    str(location_id or "").strip(),
                    [],
                ).append(event)

        paths_by_id = location_paths_by_id(locations)
        decorated = []

        for location in locations:
            record_id = str(location.get("record_id", "") or "")
            foundation_state = location_foundation_event_state(
                location,
                world_events_by_location_id.get(record_id, []),
                world_events_are_normalized=True,
            )
            self._foundation_state_cache[record_id] = deepcopy(
                foundation_state
            )
            extinction_state = location_extinction_event_state(
                location,
                world_events_by_location_id.get(record_id, []),
                world_events_are_normalized=True,
            )
            self._extinction_state_cache[record_id] = deepcopy(
                extinction_state
            )
            decorated_location = deepcopy(location)
            decorated_location["_foundation_event_valid"] = (
                foundation_state["valid"]
            )
            decorated_location["_foundation_event_id"] = (
                foundation_state["foundation_event_id"]
            )
            decorated_location["extinct"] = bool(
                extinction_state["exists"]
            )
            decorated_location["extinction_year"] = (
                extinction_state["year"]
                if extinction_state["exists"]
                else ""
            )
            decorated_location["_extinction_event_id"] = (
                extinction_state["event_id"]
            )
            decorated_location["_extinction_event_date"] = (
                extinction_state["date"]
            )
            decorated.append(
                (
                    paths_by_id.get(record_id, "").casefold(),
                    decorated_location,
                )
            )

        decorated.sort(key=self.decorated_location_sort_key)
        self._locations_cache = [
            location for path, location in decorated
        ]
        return deepcopy(self._locations_cache)

    def foundation_state_for_location(self, location_id):
        selected_id = str(location_id or "").strip()

        if selected_id in self._foundation_state_cache:
            return deepcopy(
                self._foundation_state_cache[selected_id]
            )

        location = self.get_location(location_id)

        if location is None:
            return {
                "valid": False,
                "first_event_id": "",
                "foundation_event_id": "",
            }

        state = location_foundation_event_state(
            location,
            self.database.list_records("events"),
        )
        self._foundation_state_cache[selected_id] = deepcopy(state)
        return state

    def extinction_state_for_location(self, location_id):
        selected_id = str(location_id or "").strip()

        if selected_id in self._extinction_state_cache:
            return deepcopy(
                self._extinction_state_cache[selected_id]
            )

        location = self.database.read_record(
            "locations",
            selected_id,
        )

        if location is None:
            return {
                "exists": False,
                "event_id": "",
                "date": "",
                "year": None,
            }

        state = location_extinction_event_state(
            location,
            self.database.list_records("events"),
        )
        self._extinction_state_cache[selected_id] = deepcopy(state)
        return state

    def location_distinctions(self, location_id):
        selected_id = str(location_id or "").strip()

        if selected_id in self._distinctions_cache:
            return deepcopy(self._distinctions_cache[selected_id])

        location = self.get_location(selected_id)

        if location is None:
            return []

        distinctions = []
        foundation_state = self.foundation_state_for_location(selected_id)
        foundation_year = world_event_year(
            foundation_state.get("foundation_event_date", "")
        )
        foundation_type = str(
            foundation_state.get("foundation_event_type", "") or ""
        )

        if foundation_year is not None:
            if foundation_type == "wizarding_community_established":
                distinctions.append(
                    "First Wizarding community established in "
                    f"{foundation_year}"
                )
            else:
                distinctions.append(f"Founded in {foundation_year}")

        location_name_key = normalize_location(location.get("name", ""))
        famous_people = []

        for person in self.people_provider():
            if not isinstance(person, dict) or not bool(
                person.get("famous_person")
            ):
                continue

            starts_here = False

            for event in person.get("timeline_events", []) or []:
                if (
                    not isinstance(event, dict)
                    or str(event.get("event_type", "") or "")
                    != "starting_location"
                ):
                    continue

                linked_ids = {
                    str(linked_id or "").strip()
                    for linked_id in event.get("location_ids", []) or []
                    if str(linked_id or "").strip()
                }
                event_location_key = normalize_location(
                    event.get("detail", event.get("location", ""))
                )
                starts_here = (
                    selected_id in linked_ids
                    or bool(
                        location_name_key
                        and event_location_key == location_name_key
                    )
                )

                if starts_here:
                    break

            if starts_here:
                famous_people.append(
                    str(
                        person.get("displayed_name", "")
                        or "Unnamed magician"
                    ).strip()
                )

        for person_name in sorted(
            set(famous_people),
            key=str.casefold,
        ):
            distinctions.append(f"Birthplace of {person_name}")

        famous_organizations = sorted(
            {
                str(
                    organization.get("name", "")
                    or "Unnamed organization"
                ).strip()
                for organization in self.database.list_records(
                    "organizations"
                )
                if isinstance(organization, dict)
                and bool(organization.get("famous_organization"))
                and selected_id
                in (
                    str(
                        organization.get("location_id", "") or ""
                    ).strip(),
                    str(
                        organization.get("campus_location_id", "")
                        or ""
                    ).strip(),
                )
            },
            key=str.casefold,
        )

        for organization_name in famous_organizations:
            distinctions.append(f"Home of {organization_name}")

        self._distinctions_cache[selected_id] = deepcopy(distinctions)
        return distinctions

    def synchronize_mage_locations(self):
        locations = self.database.list_records("locations")
        known_names = {
            normalize_location(location.get("name", ""))
            for location in locations
            if normalize_location(location.get("name", ""))
        }
        created_locations = []

        for location_name in mage_location_names(self.people_provider()):
            location_key = normalize_location(location_name)

            if location_key in known_names:
                continue

            normalized = normalize_location_record(
                {
                    "name": location_name,
                    "parent_location_id": "",
                    "demographics": "",
                    "notes": "",
                    "timeline_events": [],
                }
            )
            created_locations.append(
                self.database.create_record("locations", normalized)
            )
            known_names.add(location_key)

        if created_locations:
            self.database.save()
            self._locations_cache = None
            self._foundation_state_cache = {}
            self._extinction_state_cache = {}
            self._timeline_cache = {}
            self._distinctions_cache = {}

        return created_locations

    def decorated_location_sort_key(self, decorated_location):
        return decorated_location[0]

    def get_location(self, record_id):
        location = self.database.read_record("locations", record_id)

        if location is None:
            return None

        state = self.extinction_state_for_location(record_id)
        location["extinct"] = bool(state["exists"])
        location["extinction_year"] = (
            state["year"] if state["exists"] else ""
        )
        location["_extinction_event_id"] = state["event_id"]
        location["_extinction_event_date"] = state["date"]
        return location

    def organizations_for_location(self, location_id):
        selected_id = str(location_id or "").strip()
        organizations = [
            organization
            for organization in self.database.list_records(
                "organizations"
            )
            if str(
                organization.get("location_id", "") or ""
            ).strip()
            == selected_id
            or str(
                organization.get("campus_location_id", "") or ""
            ).strip()
            == selected_id
        ]
        organizations.sort(key=self.organization_sort_key)
        return organizations

    def organization_sort_key(self, organization):
        return (
            str(organization.get("name", "") or "").casefold(),
            str(
                organization.get("organization_type", "") or ""
            ).casefold(),
        )

    def remember_location_interaction(self, location_id=""):
        normalized_location_id = str(location_id or "").strip()
        available_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in self.database.list_records("locations")
            if str(location.get("record_id", "") or "").strip()
        }

        if normalized_location_id and normalized_location_id not in available_ids:
            return False

        encoded_location_id = (
            normalized_location_id
            if normalized_location_id
            else RECENT_WORLD_LOCATION_ID
        )
        stored_history = self.database.data.get(
            RECENT_LOCATION_STORAGE_KEY,
            [],
        )
        history = (
            [
                str(stored_location_id or "").strip()
                for stored_location_id in stored_history
                if str(stored_location_id or "").strip()
            ]
            if isinstance(stored_history, list)
            else []
        )
        updated_history = [
            encoded_location_id,
            *[
                stored_location_id
                for stored_location_id in history
                if stored_location_id != encoded_location_id
            ],
        ][:RECENT_LOCATION_STORAGE_LIMIT]

        if updated_history == history:
            return False

        self.database.data[RECENT_LOCATION_STORAGE_KEY] = updated_history
        self.database.dirty = True
        return True

    def recent_location_ids(self, limit=5):
        available_ids = {
            str(location.get("record_id", "") or "").strip()
            for location in self.database.list_records("locations")
            if str(location.get("record_id", "") or "").strip()
        }
        stored_history = self.database.data.get(
            RECENT_LOCATION_STORAGE_KEY,
            [],
        )
        candidate_ids = (
            [
                str(stored_location_id or "").strip()
                for stored_location_id in stored_history
                if str(stored_location_id or "").strip()
            ]
            if isinstance(stored_history, list)
            else []
        )
        event_history = self.database.data.get(
            "_recent_event_associations",
            {},
        )

        if isinstance(event_history, dict):
            event_location_ids = event_history.get("location_ids", [])

            if isinstance(event_location_ids, list):
                candidate_ids.extend(
                    str(location_id or "").strip()
                    for location_id in event_location_ids
                    if str(location_id or "").strip()
                )

        recent_ids = []

        for candidate_id in candidate_ids:
            normalized_id = (
                ""
                if candidate_id == RECENT_WORLD_LOCATION_ID
                else candidate_id
            )

            if normalized_id and normalized_id not in available_ids:
                continue

            if normalized_id in recent_ids:
                continue

            recent_ids.append(normalized_id)

            if len(recent_ids) >= max(0, int(limit)):
                break

        return recent_ids

    def create_location(self, values, save_database=True):
        normalized = normalize_location_record(values)
        self.validate_location(normalized)
        created = self.database.create_record("locations", normalized)
        self.invalidate_caches()

        if save_database:
            self.database.save()

        return created

    def create_placeholder_location(self, place, parent_location_id=""):
        return self.create_location(
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

    def update_location(
        self,
        record_id,
        values,
        save_database=True,
    ):
        current = self.database.read_record("locations", record_id)

        if current is None:
            raise KeyError(f"Unknown location record_id: {record_id}")

        prospective = deepcopy(current)
        prospective.update(deepcopy(values))
        prospective = normalize_location_record(prospective)
        self.validate_location(prospective, record_id)
        updated = self.database.update_record(
            "locations",
            record_id,
            prospective,
        )
        self.invalidate_caches()

        if save_database:
            self.database.save()

        return updated

    def delete_location(self, record_id):
        locations = self.list_locations()
        location = self.get_location(record_id)
        children = [
            location
            for location in locations
            if str(location.get("parent_location_id", "") or "") == record_id
        ]

        if children:
            raise ValueError("Move or delete this location's nested locations first.")

        linked_organizations = [
            organization
            for organization in self.database.list_records("organizations")
            if record_id
            in (
                str(organization.get("location_id", "") or ""),
                str(
                    organization.get("campus_location_id", "") or ""
                ),
            )
        ]

        if linked_organizations:
            raise ValueError(
                "Move or delete the organizations tied to this location first."
            )

        linked_events = [
            event
            for event in self.database.list_records("events")
            if record_id in event.get("location_ids", [])
        ]
        linked_person_events = [
            event
            for person in self.people_provider()
            if isinstance(person, dict)
            for event in person.get("timeline_events", [])
            if isinstance(event, dict)
            and record_id in event.get("location_ids", [])
        ]

        if linked_events or linked_person_events:
            raise ValueError(
                "Move or remove the events tied to this location first."
            )

        linked_book_titles = [
            str(book.get("title", "Untitled book") or "Untitled book")
            for book in self.database.data.get("books", [])
            if (
                str(book.get("publication_location_id", "") or "")
                == str(record_id)
                or any(
                    str(holding.get("location_id", "") or "")
                    == str(record_id)
                    for holding in book.get("holdings", [])
                    if isinstance(holding, dict)
                )
            )
        ]

        if linked_book_titles:
            raise ValueError(
                "Move or remove the book publication and archive links "
                "before deleting this location: "
                f"{', '.join(linked_book_titles)}."
            )

        referenced_names = {
            normalize_location(name)
            for name in mage_location_names(self.people_provider())
        }
        location_name = normalize_location(
            (location or {}).get("name", "")
        )

        if location_name and location_name in referenced_names:
            raise ValueError(
                "Change the mages who reference this location before deleting it."
            )

        deleted = self.database.delete_record("locations", record_id)
        self.invalidate_caches()
        self.database.save()
        return deleted

    def add_event(self, location_id, event):
        location = self.get_location(location_id)

        if location is None:
            raise KeyError(f"Unknown location record_id: {location_id}")

        event_values = deepcopy(event)

        if (
            str(event_values.get("event_type", "") or "")
            in ("founding", "wizarding_community_established")
            and self.location_has_other_foundation(location)
        ):
            raise ValueError(
                "This location already has a founding event."
            )

        if str(event_values.get("event_type", "") or "") == "founding":
            event_values["title"] = (
                founding_event_title(location_id, self.list_locations())
                or event_values.get("title", "")
            )

        normalized_event = normalize_location_event(event_values)
        events = list(location.get("timeline_events", []))
        events.append(normalized_event)
        extinction_state = location_extinction_event_state(
            {**location, "timeline_events": events},
            self.database.list_records("events"),
        )
        updated = self.update_location(
            location_id,
            {
                "timeline_events": events,
                "extinct": bool(extinction_state["exists"]),
                "extinction_year": (
                    extinction_state["year"]
                    if extinction_state["exists"]
                    else ""
                ),
            },
        )
        return updated, normalized_event

    def update_event(self, location_id, event_id, values):
        location = self.get_location(location_id)

        if location is None:
            raise KeyError(f"Unknown location record_id: {location_id}")

        event_values = deepcopy(values)

        if (
            str(event_values.get("event_type", "") or "")
            in ("founding", "wizarding_community_established")
            and self.location_has_other_foundation(
                location,
                ignored_local_event_id=event_id,
            )
        ):
            raise ValueError(
                "This location already has a founding event."
            )

        if str(event_values.get("event_type", "") or "") == "founding":
            event_values["title"] = (
                founding_event_title(location_id, self.list_locations())
                or event_values.get("title", "")
            )

        normalized_event = normalize_location_event(
            {**event_values, "event_id": event_id}
        )
        events = []
        replaced = False

        for event in location.get("timeline_events", []):
            if event.get("event_id") == event_id:
                events.append(normalized_event)
                replaced = True
            else:
                events.append(event)

        if not replaced:
            raise KeyError(f"Unknown location event_id: {event_id}")

        extinction_state = location_extinction_event_state(
            {**location, "timeline_events": events},
            self.database.list_records("events"),
        )
        updated = self.update_location(
            location_id,
            {
                "timeline_events": events,
                "extinct": bool(extinction_state["exists"]),
                "extinction_year": (
                    extinction_state["year"]
                    if extinction_state["exists"]
                    else ""
                ),
            },
        )
        return updated, normalized_event

    def delete_event(self, location_id, event_id):
        location = self.get_location(location_id)

        if location is None:
            raise KeyError(f"Unknown location record_id: {location_id}")

        events = [
            event
            for event in location.get("timeline_events", [])
            if event.get("event_id") != event_id
        ]

        if len(events) == len(location.get("timeline_events", [])):
            raise KeyError(f"Unknown location event_id: {event_id}")

        extinction_state = location_extinction_event_state(
            {**location, "timeline_events": events},
            self.database.list_records("events"),
        )
        return self.update_location(
            location_id,
            {
                "timeline_events": events,
                "extinct": bool(extinction_state["exists"]),
                "extinction_year": (
                    extinction_state["year"]
                    if extinction_state["exists"]
                    else ""
                ),
            },
        )

    def timeline_for(self, location_id):
        selected_id = str(location_id or "").strip()

        if selected_id in self._timeline_cache:
            return deepcopy(self._timeline_cache[selected_id])

        timeline = visible_location_timeline(
            selected_id,
            self.list_locations(),
            self.people_provider(),
            self.database.list_records("events"),
        )
        self._timeline_cache[selected_id] = deepcopy(timeline)
        return timeline

    def location_has_other_foundation(
        self,
        location,
        ignored_local_event_id="",
    ):
        if not isinstance(location, dict):
            return False

        ignored_id = str(ignored_local_event_id or "").strip()
        candidate = deepcopy(location)
        candidate["timeline_events"] = [
            event
            for event in location.get("timeline_events", []) or []
            if str(event.get("event_id", "") or "").strip()
            != ignored_id
        ]
        state = location_foundation_event_state(
            candidate,
            self.database.list_records("events"),
        )
        return bool(state.get("foundation_event_id"))

    def people_for_period(
        self,
        start_year,
        end_year,
        location_id="",
        reproductive_without_children=False,
    ):
        return categorized_people_for_period(
            self.people_provider(),
            self.list_locations(),
            start_year,
            end_year,
            location_id,
            reproductive_without_children,
        )

    def events_for_period(
        self,
        start_year,
        end_year,
        location_id="",
        famous_people_only=False,
    ):
        return location_events_for_period(
            start_year,
            end_year,
            location_id,
            self.list_locations(),
            self.people_provider(),
            famous_people_only,
        )

    def parent_options(self, excluded_location_id=""):
        locations = self.list_locations()
        unavailable_ids = descendant_ids(excluded_location_id, locations)
        unavailable_ids.add(str(excluded_location_id or ""))
        options = []

        for location in locations:
            record_id = str(location.get("record_id", "") or "")

            if record_id in unavailable_ids:
                continue

            options.append(
                {
                    "record_id": record_id,
                    "label": location_path(record_id, locations),
                    "depth": location_depth(record_id, locations),
                }
            )

        return options

    def validate_location(self, values, record_id=""):
        locations = self.list_locations()
        name = str(values.get("name", "") or "").strip()
        parent_id = str(values.get("parent_location_id", "") or "").strip()

        for location in locations:
            existing_id = str(location.get("record_id", "") or "")

            if existing_id == record_id:
                continue

            if str(location.get("name", "") or "").strip().casefold() == name.casefold():
                raise ValueError(f'A location named "{name}" already exists.')

        if parent_id and self.get_location(parent_id) is None:
            raise ValueError("The selected parent location no longer exists.")

        if parent_id and parent_id == record_id:
            raise ValueError("A location cannot contain itself.")

        if record_id and parent_id in descendant_ids(record_id, locations):
            raise ValueError("A location cannot be nested inside its descendant.")
