import unittest

from mage_maker.sections.events.controller import EventController
from mage_maker.sections.locations.models import (
    location_events_for_period,
    person_location_events,
    visible_location_timeline,
)


class EventLocationLinkTests(unittest.TestCase):
    def setUp(self):
        self.locations = [
            {
                "record_id": "ireland",
                "name": "Ireland",
                "parent_location_id": "",
                "timeline_events": [],
            },
            {
                "record_id": "limerick",
                "name": "Limerick",
                "parent_location_id": "ireland",
                "timeline_events": [],
            },
            {
                "record_id": "mungret",
                "name": "Mungret",
                "parent_location_id": "ireland",
                "timeline_events": [],
            },
        ]
        self.people = [
            {
                "record_id": "maeve",
                "displayed_name": "Maeve",
                "famous_person": True,
                "timeline_events": [
                    {
                        "event_id": "move",
                        "event_type": "custom",
                        "detail": "Worked between Limerick and Mungret",
                        "date": "965",
                        "note": "",
                        "location_ids": ["limerick", "mungret"],
                    }
                ],
            }
        ]

    def test_person_event_retains_every_explicit_location(self):
        events = person_location_events(self.people, self.locations)

        self.assertEqual(1, len(events))
        self.assertEqual(
            ["limerick", "mungret"],
            events[0]["location_ids"],
        )

    def test_person_event_appears_at_each_linked_location(self):
        limerick_events = visible_location_timeline(
            "limerick",
            self.locations,
            self.people,
            [],
        )
        mungret_events = visible_location_timeline(
            "mungret",
            self.locations,
            self.people,
            [],
        )

        self.assertEqual(
            ["mage:maeve:move"],
            [event["event_id"] for event in limerick_events],
        )
        self.assertEqual(
            ["mage:maeve:move"],
            [event["event_id"] for event in mungret_events],
        )

    def test_period_view_lists_multi_location_event_once(self):
        events = location_events_for_period(
            900,
            999,
            "",
            self.locations,
            self.people,
            famous_people_only=True,
        )

        self.assertEqual(
            ["mage:maeve:move"],
            [event["event_id"] for event in events],
        )

    def test_controller_requires_exactly_two_relocation_locations(self):
        controller = EventController(
            None,
            self.people.copy,
            self.locations.copy,
            [].copy,
        )
        event = {
            "event_type": "relocated",
            "person_ids": ["maeve"],
            "period_names": [],
            "location_ids": ["limerick"],
        }

        with self.assertRaisesRegex(
            ValueError,
            "Select exactly two locations for a relocation",
        ):
            controller.validate_associations(event)

        event["location_ids"] = ["limerick", "mungret"]
        controller.validate_associations(event)

        event["location_ids"] = ["ireland", "limerick", "mungret"]

        with self.assertRaisesRegex(
            ValueError,
            "Select exactly two locations for a relocation",
        ):
            controller.validate_associations(event)

    def test_founding_title_is_derived_from_its_location(self):
        controller = EventController(
            None,
            self.people.copy,
            self.locations.copy,
            [].copy,
        )
        titled_event = controller.apply_title_rules(
            {
                "event_type": "founding",
                "title": "Limerick founded by the Vikings",
                "location_ids": ["limerick"],
            }
        )

        self.assertEqual(
            "Founding of Limerick",
            titled_event["title"],
        )

    def test_controller_requires_one_founding_location(self):
        controller = EventController(
            None,
            self.people.copy,
            self.locations.copy,
            [].copy,
        )
        event = {
            "event_type": "founding",
            "person_ids": [],
            "period_names": [],
            "location_ids": [],
        }

        with self.assertRaisesRegex(
            ValueError,
            "Select exactly one location for a founding event",
        ):
            controller.validate_associations(event)

        event["location_ids"] = ["limerick"]
        controller.validate_associations(event)

        event["location_ids"] = ["limerick", "mungret"]

        with self.assertRaisesRegex(
            ValueError,
            "Select exactly one location for a founding event",
        ):
            controller.validate_associations(event)

    def test_existing_founding_event_uses_the_standard_title_in_locations(self):
        events = visible_location_timeline(
            "limerick",
            self.locations,
            self.people,
            [
                {
                    "record_id": "founding-limerick",
                    "event_type": "founding",
                    "title": "Limerick founded by the Vikings",
                    "date": "922",
                    "description": "",
                    "person_ids": [],
                    "period_names": [],
                    "location_ids": ["limerick"],
                }
            ],
        )
        founding_event = next(
            event
            for event in events
            if event.get("event_type") == "founding"
        )

        self.assertEqual(
            "Founding of Limerick",
            founding_event["title"],
        )


if __name__ == "__main__":
    unittest.main()
