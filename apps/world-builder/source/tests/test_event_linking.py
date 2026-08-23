import unittest

from mage_maker.sections.events.link_dialog import (
    event_role_options,
    link_person_to_event,
    person_event_role,
)


class EventLinkingTests(unittest.TestCase):
    def test_ordinary_event_links_person_as_participant(self):
        linked = link_person_to_event(
            {
                "record_id": "event-1",
                "event_type": "travel",
                "title": "Travelled north",
                "date": "930",
                "person_ids": ["first-person"],
            },
            "second-person",
            "person_ids",
        )

        self.assertEqual(
            ["first-person", "second-person"],
            linked["person_ids"],
        )
        self.assertEqual(
            "Participant",
            person_event_role(linked, "second-person"),
        )

    def test_murder_roles_are_explicit_and_rebuild_people(self):
        event = {
            "record_id": "murder-1",
            "event_type": "murder",
            "title": "A murder",
            "date": "930",
            "perpetrator_person_ids": ["killer"],
            "victim_person_ids": ["victim"],
            "person_ids": ["killer", "victim"],
        }
        self.assertEqual(
            (
                ("perpetrator_person_ids", "Perpetrator"),
                ("victim_person_ids", "Victim"),
                ("witness_person_ids", "Witness"),
                ("affected_person_ids", "Affected by the murder"),
            ),
            event_role_options(event),
        )

        linked = link_person_to_event(
            event,
            "witness",
            "witness_person_ids",
        )
        self.assertEqual(["witness"], linked["witness_person_ids"])
        self.assertIn("witness", linked["person_ids"])

    def test_birth_links_only_into_selected_parent_role(self):
        linked = link_person_to_event(
            {
                "record_id": "birth:baby",
                "event_type": "born",
                "title": "Birth",
                "date": "930",
                "baby_person_ids": ["baby"],
                "person_ids": ["baby"],
            },
            "parent",
            "non_birthing_parent_person_ids",
        )

        self.assertEqual(["baby"], linked["baby_person_ids"])
        self.assertEqual(
            ["parent"],
            linked["non_birthing_parent_person_ids"],
        )
        self.assertEqual(["baby", "parent"], linked["person_ids"])

    def test_duplicate_person_link_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "already linked"):
            link_person_to_event(
                {
                    "record_id": "event-1",
                    "event_type": "travel",
                    "person_ids": ["person"],
                },
                "person",
                "person_ids",
            )


if __name__ == "__main__":
    unittest.main()
