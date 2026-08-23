import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.timeline.locations import (
    LONG_DISTANCE_NOTE,
    ParentLocationConflict,
)


class PeopleControllerTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        database_path = Path(self.temporary_directory.name) / "mage_maker.json"
        database_path.write_text(
            json.dumps(
                {
                    "_database": {"schema_version": 3, "last_saved": None},
                    "people": [
                        {
                            "record_id": "young",
                            "displayed_name": "Young",
                            "birth_year": 1990,
                        },
                        {
                            "record_id": "old",
                            "displayed_name": "Old",
                            "birth_year": 1000,
                        },
                        {
                            "record_id": "unknown",
                            "displayed_name": "Unknown",
                            "birth_year": None,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )
        database = JsonDatabase(database_path)
        database.load()
        self.controller = PeopleController(database)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_people_are_sorted_oldest_first(self):
        record_ids = [person["record_id"] for person in self.controller.list_people()]
        self.assertEqual(["old", "young", "unknown"], record_ids)

    def test_notes_update_uses_record_scoped_fast_path(self):
        with patch.object(
            self.controller,
            "synchronize_spouses",
            side_effect=AssertionError("family reconciliation ran"),
        ), patch.object(
            self.controller,
            "synchronize_family_parental_values",
            side_effect=AssertionError("parent reconciliation ran"),
        ), patch(
            "mage_maker.core.controller.synchronize_birth_events_from_people",
            side_effect=AssertionError("birth reconciliation ran"),
        ), patch.object(self.controller.database, "save") as save_database:
            updated = self.controller.update_person(
                "young",
                {"notes": "A focused note edit."},
            )

        self.assertEqual("A focused note edit.", updated["notes"])
        self.assertEqual(frozenset({"notes"}), self.controller.last_changed_fields)
        save_database.assert_called_once_with(rebuild_indexes=False)

    def test_semantic_no_op_creates_no_database_change(self):
        current = self.controller.get_person("young")
        revision = self.controller.database.revision
        with patch.object(
            self.controller.database,
            "update_person",
        ) as update_person, patch.object(
            self.controller.database,
            "save",
        ) as save_database:
            returned = self.controller.update_person(
                "young",
                {"notes": current.get("notes", "")},
            )

        self.assertEqual("young", returned["record_id"])
        self.assertEqual(revision, self.controller.database.revision)
        self.assertEqual(frozenset(), self.controller.last_changed_fields)
        update_person.assert_not_called()
        save_database.assert_not_called()

    def test_recent_people_follow_view_order_without_duplicates(self):
        self.assertTrue(self.controller.remember_person_interaction("young"))
        self.assertTrue(self.controller.remember_person_interaction("old"))
        self.assertTrue(self.controller.remember_person_interaction("young"))
        self.assertEqual(
            ["young", "old"],
            self.controller.recent_person_ids(limit=5),
        )
        self.assertFalse(
            self.controller.remember_person_interaction("missing")
        )

    def test_creation_requires_a_name(self):
        with self.assertRaisesRegex(ValueError, "must have a displayed name"):
            self.controller.create_person({"displayed_name": ""})

    def test_birth_date_is_validated(self):
        with self.assertRaisesRegex(ValueError, "Birth month"):
            self.controller.create_person(
                {
                    "displayed_name": "Wrong Month",
                    "birth_year": "1980",
                    "birth_month": "13",
                }
            )

    def test_displayed_name_must_be_unique(self):
        with self.assertRaisesRegex(ValueError, "already exists"):
            self.controller.create_person({"displayed_name": "old"})

    def test_name_details_are_normalized(self):
        created = self.controller.create_person(
            {
                "displayed_name": "Name Keeper",
                "name_details": {
                    "entries": [
                        {
                            "entry_id": "keeper-alias",
                            "name_type": "  Alias  ",
                            "name_entry": "  The Keeper  ",
                            "date": "  1998  ",
                            "note": "  Used at school.  ",
                        }
                    ]
                },
            }
        )
        entry = created["name_details"]["entries"][0]
        self.assertEqual("Alias", entry["name_type"])
        self.assertEqual("The Keeper", entry["name_entry"])
        self.assertEqual("1998", entry["date"])
        self.assertEqual("Used at school.", entry["note"])

    @patch("mage_maker.core.controller.randrange", return_value=0)
    def test_new_magical_person_has_one_in_one_thousand_animagus_chance(
        self,
        mocked_randrange,
    ):
        created = self.controller.create_person(
            {"displayed_name": "Rare Animagus"}
        )
        self.assertTrue(created["animagus"])
        mocked_randrange.assert_called_once_with(1000)

    @patch("mage_maker.core.controller.randrange", return_value=1)
    def test_animagus_chance_is_rolled_only_during_creation(
        self,
        mocked_randrange,
    ):
        created = self.controller.create_person(
            {"displayed_name": "Ordinary Magician"}
        )
        self.assertFalse(created["animagus"])
        self.controller.update_person(
            created["record_id"],
            {"notes": "Updated later."},
        )
        mocked_randrange.assert_called_once_with(1000)

    @patch("mage_maker.core.controller.randrange", return_value=0)
    def test_non_magical_person_cannot_become_animagus(
        self,
        mocked_randrange,
    ):
        created = self.controller.create_person(
            {"displayed_name": "Non-magical Person", "non_magical": True}
        )
        self.assertFalse(created["animagus"])
        mocked_randrange.assert_not_called()

    def test_magical_child_inherits_parseltongue_from_either_parent(self):
        mother = self.controller.create_person(
            {
                "displayed_name": "Parseltongue Mother",
                "can_give_birth": True,
                "parseltongue": True,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Parseltongue Child",
                "biological_mother_id": mother["record_id"],
            }
        )
        self.assertTrue(child["parseltongue"])

    def test_non_magical_child_does_not_inherit_parseltongue(self):
        father = self.controller.create_person(
            {
                "displayed_name": "Parseltongue Father",
                "can_give_birth": False,
                "parseltongue": True,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Non-magical Child",
                "non_magical": True,
                "biological_father_id": father["record_id"],
            }
        )
        self.assertFalse(child["parseltongue"])

    def test_existing_magical_child_inherits_when_parent_is_marked_later(self):
        mother = self.controller.create_person(
            {
                "displayed_name": "Later Parseltongue Mother",
                "can_give_birth": True,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Existing Magical Child",
                "biological_mother_id": mother["record_id"],
            }
        )
        self.assertFalse(child["parseltongue"])

        self.controller.update_person(
            mother["record_id"],
            {"parseltongue": True},
        )

        updated_child = self.controller.get_person(child["record_id"])
        self.assertTrue(updated_child["parseltongue"])

    def test_family_assignments_and_mates_are_reciprocal(self):
        mother = self.controller.create_person(
            {"displayed_name": "Mother", "can_give_birth": True}
        )
        father = self.controller.create_person(
            {"displayed_name": "Father", "can_give_birth": False}
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Child",
                "biological_mother_id": mother["record_id"],
                "biological_father_id": father["record_id"],
            }
        )
        saved_mother = self.controller.get_person(mother["record_id"])
        saved_father = self.controller.get_person(father["record_id"])
        self.assertIn(father["record_id"], saved_mother["mate_ids"])
        self.assertIn(mother["record_id"], saved_father["mate_ids"])
        self.assertEqual(
            mother["record_id"],
            self.controller.get_person(child["record_id"])["biological_mother_id"],
        )

    def test_childs_new_other_parent_remains_a_reciprocal_mate(self):
        focus = self.controller.create_person(
            {"displayed_name": "Child Focus", "can_give_birth": False}
        )
        other_parent = self.controller.create_person(
            {"displayed_name": "Child Other Parent", "can_give_birth": True}
        )
        self.controller.create_person(
            {
                "displayed_name": "Their Child",
                "biological_mother_id": other_parent["record_id"],
                "biological_father_id": focus["record_id"],
            }
        )
        self.controller.update_person(
            focus["record_id"],
            {"mate_ids": [other_parent["record_id"]]},
        )
        saved_focus = self.controller.get_person(focus["record_id"])
        saved_other_parent = self.controller.get_person(other_parent["record_id"])
        self.assertIn(other_parent["record_id"], saved_focus["mate_ids"])
        self.assertIn(focus["record_id"], saved_other_parent["mate_ids"])

    def test_mates_need_opposite_birth_assignments(self):
        first = self.controller.create_person(
            {"displayed_name": "First Parent", "can_give_birth": True}
        )
        second = self.controller.create_person(
            {"displayed_name": "Second Parent", "can_give_birth": True}
        )

        with self.assertRaisesRegex(ValueError, "opposite"):
            self.controller.update_person(
                first["record_id"],
                {"mate_ids": [second["record_id"]]},
            )

    def test_parent_link_can_be_removed_without_deleting_parent(self):
        mother = self.controller.create_person(
            {"displayed_name": "Linked Mother", "can_give_birth": True}
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Linked Child",
                "biological_mother_id": mother["record_id"],
            }
        )
        updated_child = self.controller.update_person(
            child["record_id"],
            {"biological_mother_id": ""},
        )
        self.assertEqual("", updated_child["biological_mother_id"])
        self.assertIsNotNone(self.controller.get_person(mother["record_id"]))

    def test_unused_birthing_parent_can_change_to_father_role(self):
        candidate = self.controller.create_person(
            {"displayed_name": "Role Change Parent", "can_give_birth": True}
        )
        updated_candidate = self.controller.update_person(
            candidate["record_id"],
            {"can_give_birth": False},
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Role Change Child",
                "biological_father_id": candidate["record_id"],
            }
        )
        self.assertFalse(updated_candidate["can_give_birth"])
        self.assertEqual(candidate["record_id"], child["biological_father_id"])

    def test_adding_a_second_parent_automatically_links_both_parents_as_mates(self):
        harry = self.controller.create_person(
            {"displayed_name": "Harry", "can_give_birth": False}
        )
        ginny = self.controller.create_person(
            {"displayed_name": "Ginny", "can_give_birth": True}
        )
        carina = self.controller.create_person(
            {"displayed_name": "Carina", "can_give_birth": True}
        )
        self.controller.create_person(
            {
                "displayed_name": "Horace",
                "biological_mother_id": ginny["record_id"],
                "biological_father_id": harry["record_id"],
            }
        )
        second_child = self.controller.create_person(
            {
                "displayed_name": "Second Child",
                "biological_father_id": harry["record_id"],
            }
        )
        self.controller.update_person(
            second_child["record_id"],
            {"biological_mother_id": carina["record_id"]},
        )
        saved_harry = self.controller.get_person(harry["record_id"])
        saved_ginny = self.controller.get_person(ginny["record_id"])
        saved_carina = self.controller.get_person(carina["record_id"])
        self.assertEqual(
            {ginny["record_id"], carina["record_id"]},
            set(saved_harry["mate_ids"]),
        )
        self.assertIn(harry["record_id"], saved_ginny["mate_ids"])
        self.assertIn(harry["record_id"], saved_carina["mate_ids"])

    def test_assigning_a_child_adds_linked_timeline_events_to_both_parents(self):
        birthing_parent = self.controller.create_person(
            {"displayed_name": "Timeline Birthing", "can_give_birth": True}
        )
        non_birthing_parent = self.controller.create_person(
            {"displayed_name": "Timeline Non-birthing", "can_give_birth": False}
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Linked Timeline Child",
                "birth_year": 2004,
                "birth_month": 6,
                "birth_day": 8,
                "biological_mother_id": birthing_parent["record_id"],
                "biological_father_id": non_birthing_parent["record_id"],
            }
        )

        for parent in (birthing_parent, non_birthing_parent):
            saved_parent = self.controller.get_person(parent["record_id"])
            events = [
                event
                for event in saved_parent["timeline_events"]
                if event.get("automatic_source") == "child_assignment"
            ]
            self.assertEqual(1, len(events))
            self.assertEqual("had_child", events[0]["event_type"])
            self.assertEqual(child["record_id"], events[0]["related_person_id"])
            self.assertEqual("Linked Timeline Child", events[0]["detail"])
            self.assertEqual("2004-06-08", events[0]["date"])
            self.assertIn("Linked Timeline Child", events[0]["note"])

    def test_reassigning_a_parent_moves_the_automatic_child_event(self):
        first_parent = self.controller.create_person(
            {"displayed_name": "First Timeline Parent", "can_give_birth": True}
        )
        second_parent = self.controller.create_person(
            {"displayed_name": "Second Timeline Parent", "can_give_birth": True}
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Moved Timeline Child",
                "biological_mother_id": first_parent["record_id"],
            }
        )
        self.controller.update_person(
            child["record_id"],
            {"biological_mother_id": second_parent["record_id"]},
        )
        first_events = self.controller.get_person(first_parent["record_id"])[
            "timeline_events"
        ]
        second_events = self.controller.get_person(second_parent["record_id"])[
            "timeline_events"
        ]
        self.assertFalse(
            any(event.get("related_person_id") == child["record_id"] for event in first_events)
        )
        self.assertTrue(
            any(event.get("related_person_id") == child["record_id"] for event in second_events)
        )

    def test_child_details_update_without_duplicate_timeline_events(self):
        parent = self.controller.create_person(
            {"displayed_name": "Updating Timeline Parent", "can_give_birth": False}
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Original Child Name",
                "birth_year": 2001,
                "biological_father_id": parent["record_id"],
            }
        )
        self.controller.update_person(
            child["record_id"],
            {
                "displayed_name": "Updated Child Name",
                "birth_month": 9,
            },
        )
        events = [
            event
            for event in self.controller.get_person(parent["record_id"])[
                "timeline_events"
            ]
            if event.get("related_person_id") == child["record_id"]
        ]
        self.assertEqual(1, len(events))
        self.assertEqual("Updated Child Name", events[0]["detail"])
        self.assertEqual("2001-09", events[0]["date"])
        self.assertEqual("Child: Updated Child Name", events[0]["note"])

    def test_missing_and_muggle_parent_states_are_canonical(self):
        child = self.controller.create_person(
            {
                "displayed_name": "Parent State Child",
                "biological_mother_status": "muggle",
            }
        )
        self.assertEqual("muggle", child["biological_mother_status"])
        self.assertEqual("unknown", child["biological_father_status"])
        self.assertEqual("", child["biological_mother_id"])

    def test_parent_must_be_at_least_eighteen_when_child_is_born(self):
        parent = self.controller.create_person(
            {
                "displayed_name": "Too Young Parent",
                "birth_year": 1990,
                "can_give_birth": True,
            }
        )

        with self.assertRaisesRegex(ValueError, "at least 18"):
            self.controller.create_person(
                {
                    "displayed_name": "Too Close Child",
                    "birth_year": 2007,
                    "biological_mother_id": parent["record_id"],
                }
            )

    def test_exact_eighteenth_birthday_is_allowed(self):
        parent = self.controller.create_person(
            {
                "displayed_name": "Eighteen Parent",
                "birth_year": 1990,
                "birth_month": 12,
                "birth_day": 31,
                "can_give_birth": True,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Birthday Child",
                "birth_year": 2008,
                "birth_month": 12,
                "birth_day": 31,
                "biological_mother_id": parent["record_id"],
            }
        )
        self.assertEqual(parent["record_id"], child["biological_mother_id"])

    def test_parent_birth_date_cannot_be_changed_to_break_age_rule(self):
        parent = self.controller.create_person(
            {
                "displayed_name": "Editable Parent",
                "birth_year": 1980,
                "can_give_birth": False,
            }
        )
        self.controller.create_person(
            {
                "displayed_name": "Existing Child",
                "birth_year": 2000,
                "biological_father_id": parent["record_id"],
            }
        )

        with self.assertRaisesRegex(ValueError, "younger than 18"):
            self.controller.update_person(
                parent["record_id"],
                {"birth_year": 1985},
            )

    def test_spouse_history_is_reciprocal(self):
        first = self.controller.create_person(
            {
                "displayed_name": "Spouse One",
                "birth_year": 1980,
                "can_give_birth": False,
            }
        )
        second = self.controller.create_person(
            {
                "displayed_name": "Spouse Two",
                "birth_year": 1983,
                "can_give_birth": True,
            }
        )
        relationship = {
            "person_id": second["record_id"],
            "married": True,
            "marriage_year": 2004,
            "marriage_month": 6,
            "marriage_day": None,
            "divorced": True,
            "divorce_year": 2012,
            "divorce_month": None,
            "divorce_day": None,
        }
        self.controller.update_person(
            first["record_id"],
            {"spouse_relationships": [relationship]},
        )
        saved_second = self.controller.get_person(second["record_id"])
        reciprocal = saved_second["spouse_relationships"][0]
        self.assertEqual(first["record_id"], reciprocal["person_id"])
        self.assertTrue(reciprocal["married"])
        self.assertTrue(reciprocal["divorced"])
        self.assertEqual(2004, reciprocal["marriage_year"])
        self.assertEqual(2012, reciprocal["divorce_year"])

    def test_creation_builds_starting_location_then_born(self):
        created = self.controller.create_person(
            {
                "displayed_name": "Lifecycle Person",
                "birth_year": 1984,
                "birth_month": 3,
                "starting_location": "Godric's Hollow",
                "starting_location_id": "godrics-hollow",
            }
        )
        events = created["timeline_events"]
        self.assertEqual(
            ["starting_location", "born"],
            [event["event_type"] for event in events[:2]],
        )
        self.assertEqual("Godric's Hollow", events[0]["detail"])
        self.assertEqual("1984-03", events[0]["date"])
        self.assertEqual("1984-03", events[1]["date"])
        self.assertEqual(
            [["godrics-hollow"], ["godrics-hollow"]],
            [
                events[0]["location_ids"],
                events[1]["location_ids"],
            ],
        )

    def test_creation_keeps_bce_birth_dates_in_profile_and_events(self):
        created = self.controller.create_person(
            {
                "displayed_name": "Ancient Person",
                "birth_year": -5,
                "birth_month": 3,
                "birth_day": 14,
                "name_details": {
                    "entries": [
                        {
                            "name_type": "birth name",
                            "name_entry": "Ancient Person",
                            "date": "-5-3-14",
                        }
                    ]
                },
                "starting_location": "Rome",
                "starting_location_id": "rome",
            }
        )

        self.assertEqual(-5, created["birth_year"])
        self.assertEqual(
            "-0005-03-14",
            created["name_details"]["entries"][0]["date"],
        )
        life_start_dates = {
            event["event_type"]: event["date"]
            for event in created["timeline_events"]
            if event.get("automatic_source") == "life_start"
        }
        self.assertEqual(
            {
                "starting_location": "-0005-03-14",
                "born": "-0005-03-14",
                "birth_name": "-0005-03-14",
            },
            life_start_dates,
        )
        birth_event = next(
            event
            for event in self.controller.database.list_records("events")
            if event.get("event_type") == "born"
            and created["record_id"] in event.get("baby_person_ids", [])
        )
        self.assertEqual("-5-03-14", birth_event["date"])

    def test_assigning_same_location_parents_updates_child_starting_location(self):
        birthing_parent = self.controller.create_person(
            {
                "displayed_name": "London Birthing Parent",
                "birth_year": 1970,
                "starting_location": "London",
                "can_give_birth": True,
            }
        )
        non_birthing_parent = self.controller.create_person(
            {
                "displayed_name": "London Non-birthing Parent",
                "birth_year": 1968,
                "starting_location": " london ",
                "can_give_birth": False,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Location Child",
                "birth_year": 2000,
                "starting_location": "Elsewhere",
            }
        )
        updated_child = self.controller.update_person(
            child["record_id"],
            {
                "biological_mother_id": birthing_parent["record_id"],
                "biological_father_id": non_birthing_parent["record_id"],
            },
        )
        self.assertEqual("London", updated_child["timeline_events"][0]["detail"])
        self.assertEqual("born", updated_child["timeline_events"][1]["event_type"])

    def test_manually_selected_birth_location_survives_parent_synchronization(self):
        birthing_parent = self.controller.create_person(
            {
                "displayed_name": "Manual Location Birthing Parent",
                "birth_year": 1970,
                "starting_location": "London",
                "can_give_birth": True,
            }
        )
        non_birthing_parent = self.controller.create_person(
            {
                "displayed_name": "Manual Location Other Parent",
                "birth_year": 1968,
                "starting_location": "London",
                "can_give_birth": False,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Manual Location Child",
                "birth_year": 2000,
                "biological_mother_id": birthing_parent["record_id"],
                "biological_father_id": non_birthing_parent["record_id"],
            }
        )
        events = json.loads(json.dumps(child["timeline_events"]))
        events[0]["detail"] = "Paris"
        events[0]["location_ids"] = ["paris"]
        events[0]["birth_location_source"] = "manual"
        events[1]["location_ids"] = ["paris"]
        events[1]["birth_location_source"] = "manual"
        updated_child = self.controller.update_person(
            child["record_id"],
            {"timeline_events": events},
        )

        self.assertEqual(
            "Paris",
            updated_child["timeline_events"][0]["detail"],
        )
        self.assertEqual(
            ["paris"],
            updated_child["timeline_events"][1]["location_ids"],
        )

    def test_different_parent_locations_require_long_distance_override(self):
        birthing_parent = self.controller.create_person(
            {
                "displayed_name": "Paris Parent",
                "birth_year": 1970,
                "starting_location": "Paris",
                "can_give_birth": True,
            }
        )
        non_birthing_parent = self.controller.create_person(
            {
                "displayed_name": "London Parent",
                "birth_year": 1970,
                "starting_location": "London",
                "can_give_birth": False,
            }
        )
        values = {
            "displayed_name": "Long Distance Child",
            "birth_year": 2000,
            "biological_mother_id": birthing_parent["record_id"],
            "biological_father_id": non_birthing_parent["record_id"],
        }

        with self.assertRaises(ParentLocationConflict):
            self.controller.create_person(values)

        values["long_distance_parent_override"] = True
        child = self.controller.create_person(values)
        self.assertEqual("Paris", child["timeline_events"][0]["detail"])
        self.assertEqual(LONG_DISTANCE_NOTE, child["timeline_events"][1]["note"])
        updated_child = self.controller.update_person(
            child["record_id"],
            {"notes": "The override should remain valid."},
        )
        self.assertEqual(LONG_DISTANCE_NOTE, updated_child["timeline_events"][1]["note"])

    def test_parent_location_is_resolved_at_the_childs_birth_date(self):
        birthing_parent = self.controller.create_person(
            {
                "displayed_name": "Moving Parent",
                "birth_year": 1970,
                "starting_location": "London",
                "can_give_birth": True,
                "timeline_events": [
                    {
                        "event_id": "move-to-paris",
                        "event_type": "relocated",
                        "detail": "Paris",
                        "date": "2005",
                        "note": "",
                    }
                ],
            }
        )
        non_birthing_parent = self.controller.create_person(
            {
                "displayed_name": "Staying Parent",
                "birth_year": 1970,
                "starting_location": "London",
                "can_give_birth": False,
            }
        )
        child = self.controller.create_person(
            {
                "displayed_name": "Earlier Child",
                "birth_year": 2000,
                "biological_mother_id": birthing_parent["record_id"],
                "biological_father_id": non_birthing_parent["record_id"],
            }
        )
        self.assertEqual("London", child["timeline_events"][0]["detail"])

    def test_birth_date_changes_keep_lifecycle_event_dates_synchronized(self):
        person = self.controller.create_person(
            {
                "displayed_name": "Changing Birth Date",
                "birth_year": 1990,
                "starting_location": "York",
            }
        )
        updated = self.controller.update_person(
            person["record_id"],
            {"birth_month": 8, "birth_day": 14},
        )
        self.assertEqual(
            ["1990-08-14", "1990-08-14"],
            [event["date"] for event in updated["timeline_events"][:2]],
        )


if __name__ == "__main__":
    unittest.main()
