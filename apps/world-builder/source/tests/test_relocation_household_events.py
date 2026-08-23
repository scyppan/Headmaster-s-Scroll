import unittest

from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.models import normalize_world_event


class _EventDatabase:
    def __init__(self, events=()):
        self.events = list(events)

    def list_records(self, collection):
        return list(self.events) if collection == "events" else []

    def get_linked_records(self, collection, record_id, relationship):
        if collection != "events" or relationship != "people":
            return []
        return [
            event
            for event in self.events
            if record_id in event.get("person_ids", [])
        ]


class RelocationHouseholdEventTests(unittest.TestCase):
    def setUp(self):
        self.people = [
            {
                "record_id": "parent",
                "displayed_name": "Parent",
                "birth_year": 1970,
            },
            {
                "record_id": "child",
                "displayed_name": "Dependent Child",
                "birth_year": 1984,
                "biological_mother_id": "parent",
            },
            {
                "record_id": "adult-child",
                "displayed_name": "Adult Child",
                "birth_year": 1980,
                "biological_mother_id": "parent",
            },
            {
                "record_id": "future-child",
                "displayed_name": "Future Child",
                "birth_year": 2002,
                "biological_mother_id": "parent",
            },
            {
                "record_id": "grandchild",
                "displayed_name": "Grandchild",
                "birth_year": 1998,
                "biological_mother_id": "child",
            },
            {
                "record_id": "foster-child",
                "displayed_name": "Foster Child",
                "birth_year": 1985,
            },
            {
                "record_id": "future-foster-child",
                "displayed_name": "Future Foster Child",
                "birth_year": 1991,
            },
        ]
        self.foster_events = [
            {
                "record_id": "foster-before",
                "event_type": "foster_child",
                "date": "1995",
                "person_ids": ["parent", "foster-child"],
                "foster_parent_person_ids": ["parent"],
                "foster_child_person_ids": ["foster-child"],
            },
            {
                "record_id": "foster-after",
                "event_type": "foster_child",
                "date": "2001",
                "person_ids": ["parent", "future-foster-child"],
                "foster_parent_person_ids": ["parent"],
                "foster_child_person_ids": ["future-foster-child"],
            },
        ]
        self.controller = EventController(
            _EventDatabase(self.foster_events),
            self.people.copy,
            [].copy,
            [].copy,
            people_summary_provider=self.people.copy,
        )

    def relocation(self):
        return {
            "record_id": "move-1",
            "event_type": "relocated",
            "title": "Relocated",
            "date": "2000",
            "person_ids": ["parent"],
            "location_ids": ["new-home"],
        }

    def test_relocation_adds_children_who_belong_to_household_on_date(self):
        prepared = self.controller.apply_event_rules(self.relocation())

        self.assertEqual(
            ["parent", "child", "foster-child"],
            prepared["person_ids"],
        )
        self.assertEqual(
            ["parent"],
            prepared["relocation_primary_person_ids"],
        )
        self.assertNotIn("future-child", prepared["person_ids"])
        self.assertNotIn("future-foster-child", prepared["person_ids"])
        self.assertNotIn("adult-child", prepared["person_ids"])

    def test_child_is_not_auto_added_on_seventeenth_birthday(self):
        self.people[1]["birth_year"] = 1983
        prepared = self.controller.apply_event_rules(self.relocation())

        self.assertNotIn("child", prepared["person_ids"])

    def test_resaving_does_not_expand_through_an_auto_added_child(self):
        first = normalize_world_event(
            self.controller.apply_event_rules(self.relocation())
        )
        second = self.controller.apply_event_rules(first, first)

        self.assertNotIn("grandchild", second["person_ids"])
        self.assertEqual(
            ["parent"],
            second["relocation_primary_person_ids"],
        )

    def test_non_relocation_event_drops_internal_primary_links(self):
        normalized = normalize_world_event(
            {
                "event_type": "travel",
                "title": "Travel",
                "date": "2000",
                "person_ids": ["parent"],
                "relocation_primary_person_ids": ["parent"],
            }
        )

        self.assertNotIn("relocation_primary_person_ids", normalized)


if __name__ == "__main__":
    unittest.main()
