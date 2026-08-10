from copy import deepcopy

from mage_maker.sections.locations.models import (
    descendant_ids,
    location_depth,
    location_path,
    normalize_location_event,
    normalize_location_record,
    visible_location_timeline,
)
from mage_maker.sections.locations.periods import categorized_people_for_period


class LocationController:
    def __init__(self, database, people_provider):
        self.database = database
        self.people_provider = people_provider

    def list_locations(self):
        locations = self.database.list_records("locations")
        decorated = []

        for location in locations:
            record_id = str(location.get("record_id", "") or "")
            decorated.append(
                (
                    location_path(record_id, locations).casefold(),
                    location,
                )
            )

        decorated.sort(key=self.decorated_location_sort_key)
        return [location for path, location in decorated]

    def decorated_location_sort_key(self, decorated_location):
        return decorated_location[0]

    def get_location(self, record_id):
        return self.database.read_record("locations", record_id)

    def create_location(self, values):
        normalized = normalize_location_record(values)
        self.validate_location(normalized)
        created = self.database.create_record("locations", normalized)
        self.database.save()
        return created

    def update_location(self, record_id, values):
        current = self.get_location(record_id)

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
        self.database.save()
        return updated

    def delete_location(self, record_id):
        locations = self.list_locations()
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
            if str(organization.get("location_id", "") or "") == record_id
        ]

        if linked_organizations:
            raise ValueError(
                "Move or delete the organizations tied to this location first."
            )

        deleted = self.database.delete_record("locations", record_id)
        self.database.save()
        return deleted

    def add_event(self, location_id, event):
        location = self.get_location(location_id)

        if location is None:
            raise KeyError(f"Unknown location record_id: {location_id}")

        normalized_event = normalize_location_event(event)
        events = list(location.get("timeline_events", []))
        events.append(normalized_event)
        updated = self.update_location(
            location_id,
            {"timeline_events": events},
        )
        return updated, normalized_event

    def update_event(self, location_id, event_id, values):
        location = self.get_location(location_id)

        if location is None:
            raise KeyError(f"Unknown location record_id: {location_id}")

        normalized_event = normalize_location_event(
            {**deepcopy(values), "event_id": event_id}
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

        updated = self.update_location(
            location_id,
            {"timeline_events": events},
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

        return self.update_location(location_id, {"timeline_events": events})

    def timeline_for(self, location_id):
        return visible_location_timeline(
            location_id,
            self.list_locations(),
            self.people_provider(),
        )

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
