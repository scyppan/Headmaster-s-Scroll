import unittest

from mage_maker.sections.events.models import birth_event_from_person
from mage_maker.sections.timeline.events import (
    EVENT_TYPES,
    normalize_timeline_event,
    normalize_timeline_events,
    timeline_event_summary,
)
from mage_maker.sections.timeline.locations import ensure_life_start_events
from mage_maker.sections.timeline.page import (
    profile_events_without_promoted_copies,
)


class TimelineEventTests(unittest.TestCase):
    def test_promoted_profile_event_is_not_rendered_twice(self):
        profile_events = [
            {
                "event_id": "name-change:entry-1",
                "event_type": "name_change",
                "detail": "Gunnhildr, fostrdottir Ozurar",
            }
        ]
        linked_events = [
            {
                "record_id": "profile-event:canonical-1",
                "profile_timeline_event_id": "name-change:entry-1",
                "event_type": "name_change",
            }
        ]

        self.assertEqual(
            [],
            profile_events_without_promoted_copies(
                profile_events,
                linked_events,
            ),
        )

    def test_events_are_normalized_and_sorted_by_partial_dates(self):
        events = normalize_timeline_events(
            [
                {
                    "event_id": "later",
                    "event_type": "relocated",
                    "detail": "London",
                    "date": "2001-4",
                    "note": "A move.",
                },
                {
                    "event_id": "earlier",
                    "event_type": "started_school",
                    "detail": "Hogwarts",
                    "date": "1998",
                    "note": "First year.",
                },
                {
                    "event_id": "unknown",
                    "event_type": "custom",
                    "detail": "Undated memory",
                    "date": "",
                    "note": "",
                },
            ]
        )
        self.assertEqual(["earlier", "later", "unknown"], [event["event_id"] for event in events])
        self.assertEqual("2001-04", events[1]["date"])

    def test_common_event_summaries_include_the_detail(self):
        self.assertEqual(
            "Started at Hogwarts school",
            timeline_event_summary(
                {"event_type": "started_school", "detail": "Hogwarts"}
            ),
        )
        self.assertEqual(
            "Relocated to Hogsmeade",
            timeline_event_summary(
                {"event_type": "relocated", "detail": "Hogsmeade"}
            ),
        )
        self.assertEqual(
            "Had a child",
            timeline_event_summary(
                {"event_type": "had_child", "detail": "Horace"}
            ),
        )

    def test_change_in_work_is_available_and_summarized(self):
        self.assertIn(
            ("work_change", "Change in work"),
            EVENT_TYPES,
        )
        self.assertEqual(
            "Change in work: Became a wandmaker",
            timeline_event_summary(
                {
                    "event_type": "work_change",
                    "detail": "Became a wandmaker",
                }
            ),
        )

    def test_custom_event_requires_a_description(self):
        with self.assertRaisesRegex(ValueError, "needs an event description"):
            normalize_timeline_event(
                {
                    "event_type": "custom",
                    "detail": "",
                    "date": "2000",
                }
            )

    def test_invalid_calendar_date_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "valid calendar date"):
            normalize_timeline_event(
                {
                    "event_type": "got_married",
                    "detail": "Partner",
                    "date": "2000-02-31",
                }
            )

    def test_birth_is_the_single_opening_event(self):
        events = ensure_life_start_events(
            {
                "birth_year": 1980,
                "displayed_name": "Display Name",
                "timeline_events": [
                    {
                        "event_id": "school",
                        "event_type": "started_school",
                        "detail": "Hogwarts",
                        "date": "1991",
                    }
                ],
            },
            starting_location="London",
        )
        self.assertEqual(
            ["born", "started_school"],
            [event["event_type"] for event in events],
        )
        self.assertEqual(
            "Born at London",
            timeline_event_summary(events[0]),
        )
        self.assertEqual("", events[0]["birth_name"])

    def test_birth_collapses_legacy_opening_rows_and_shows_explicit_name(self):
        events = ensure_life_start_events(
            {
                "record_id": "baby",
                "displayed_name": "Current Display Name",
                "birth_year": 1980,
                "name_details": {
                    "entries": [
                        {
                            "entry_id": "birth-name",
                            "name_type": "birth name",
                            "name_entry": "Original Name",
                            "date": "1980",
                            "note": "",
                        }
                    ]
                },
                "timeline_events": [
                    {
                        "event_id": "old-location",
                        "event_type": "starting_location",
                        "detail": "London",
                        "date": "1980",
                        "location_ids": ["london"],
                        "automatic_source": "life_start",
                    },
                    {
                        "event_id": "old-born",
                        "event_type": "born",
                        "detail": "",
                        "date": "1980",
                        "automatic_source": "life_start",
                    },
                    {
                        "event_id": "old-name",
                        "event_type": "birth_name",
                        "detail": "Original Name",
                        "date": "1980",
                        "automatic_source": "life_start",
                    },
                ],
            }
        )

        self.assertEqual(["born"], [event["event_type"] for event in events])
        self.assertEqual(["london"], events[0]["location_ids"])
        self.assertEqual(
            "Born at London · Birth name: Original Name",
            timeline_event_summary(events[0]),
        )

    def test_canonical_birth_event_keeps_one_location_and_optional_name(self):
        person = {
            "record_id": "baby",
            "displayed_name": "Current Display Name",
            "birth_year": 1980,
            "birth_month": 4,
            "birth_day": 12,
            "name_details": {"entries": []},
            "timeline_events": [
                {
                    "event_id": "life-start:born",
                    "event_type": "born",
                    "detail": "London",
                    "date": "1980-04-12",
                    "location_ids": ["london"],
                    "automatic_source": "life_start",
                }
            ],
        }

        event = birth_event_from_person(person)

        self.assertEqual(["baby"], event["baby_person_ids"])
        self.assertEqual(["london"], event["location_ids"])
        self.assertEqual("", event["birth_name"])

        person["name_details"]["entries"] = [
            {
                "entry_id": "birth-name",
                "name_type": "birth name",
                "name_entry": "Original Name",
                "date": "1980-04-12",
            }
        ]
        named_event = birth_event_from_person(person, event)
        self.assertEqual("Original Name", named_event["birth_name"])


if __name__ == "__main__":
    unittest.main()
