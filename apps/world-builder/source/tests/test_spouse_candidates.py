import unittest

from mage_maker.sections.family_tree.spouse_candidates import (
    shared_location_match,
    spouse_candidates,
)


class SpouseCandidateTests(unittest.TestCase):
    def setUp(self):
        self.focus = {
            "record_id": "focus",
            "displayed_name": "Focus",
            "can_give_birth": False,
            "birth_year": 1980,
            "timeline_events": [
                {
                    "event_type": "relocated",
                    "detail": "London",
                    "date": "1995",
                },
                {
                    "event_type": "relocated",
                    "detail": "Edinburgh",
                    "date": "2005",
                },
            ],
        }

    def test_candidates_require_opposite_birth_assignment_and_seven_year_age_range(self):
        people = [
            self.focus,
            {
                "record_id": "eligible",
                "displayed_name": "Eligible",
                "can_give_birth": True,
                "birth_year": 1987,
            },
            {
                "record_id": "too-old",
                "displayed_name": "Too Old",
                "can_give_birth": True,
                "birth_year": 1972,
            },
            {
                "record_id": "same-assignment",
                "displayed_name": "Same Assignment",
                "can_give_birth": False,
                "birth_year": 1981,
            },
            {
                "record_id": "unknown-age",
                "displayed_name": "Unknown Age",
                "can_give_birth": True,
                "birth_year": None,
            },
        ]
        ids = [
            person["record_id"]
            for person in spouse_candidates(self.focus, people)
        ]
        self.assertEqual(["eligible"], ids)

    def test_same_location_at_overlapping_time_is_ranked_first(self):
        people = [
            self.focus,
            {
                "record_id": "no-location",
                "displayed_name": "No Location",
                "can_give_birth": True,
                "birth_year": 1980,
                "timeline_events": [],
            },
            {
                "record_id": "london",
                "displayed_name": "London Match",
                "can_give_birth": True,
                "birth_year": 1984,
                "timeline_events": [
                    {
                        "event_type": "relocated",
                        "detail": "London",
                        "date": "1998",
                    },
                    {
                        "event_type": "relocated",
                        "detail": "Paris",
                        "date": "2002",
                    },
                ],
            },
        ]
        candidates = spouse_candidates(self.focus, people)
        self.assertEqual("london", candidates[0]["record_id"])
        self.assertEqual(
            "Same location: London (1998–2001)",
            candidates[0]["_spouse_match"],
        )

    def test_location_periods_must_overlap(self):
        earlier_london = {
            "timeline_events": [
                {"event_type": "relocated", "detail": "London", "date": "1980"},
                {"event_type": "relocated", "detail": "Paris", "date": "1990"},
            ]
        }
        later_london = {
            "timeline_events": [
                {"event_type": "relocated", "detail": "London", "date": "1995"}
            ]
        }
        self.assertEqual("", shared_location_match(earlier_london, later_london))


if __name__ == "__main__":
    unittest.main()
