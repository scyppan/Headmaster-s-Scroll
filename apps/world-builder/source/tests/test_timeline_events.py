import unittest

from mage_maker.sections.timeline.events import (
    EVENT_TYPES,
    normalize_timeline_event,
    normalize_timeline_events,
    timeline_event_summary,
)
from mage_maker.sections.timeline.locations import ensure_life_start_events


class TimelineEventTests(unittest.TestCase):
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

    def test_lifecycle_events_always_occupy_the_first_three_lines(self):
        events = ensure_life_start_events(
            {
                "birth_year": 1980,
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
            ["starting_location", "born", "birth_name", "started_school"],
            [event["event_type"] for event in events],
        )
        self.assertEqual("Starting location: London", timeline_event_summary(events[0]))
        self.assertEqual("Born", timeline_event_summary(events[1]))
        self.assertEqual(
            "Birth name: Unnamed magician",
            timeline_event_summary(events[2]),
        )


if __name__ == "__main__":
    unittest.main()
