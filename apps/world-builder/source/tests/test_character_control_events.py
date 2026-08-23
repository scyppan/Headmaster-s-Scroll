import unittest

from mage_maker.core.reference_storage import world_event_to_timeline
from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.models import normalize_world_event
from mage_maker.sections.timeline.events import (
    murder_timeline_summary,
    timeline_event_summary,
)


class _WorldDatabase:
    def list_records(self, collection):
        if collection == "named_creatures":
            return [{
                "record_id": "named-1",
                "name": "Pip",
                "species_name": "Kneazle",
            }]
        return []


class _GameDatabase:
    def collection(self, collection):
        catalogs = {
            "spells": [{
                "record_id": "spell-1", "name": "Lumos",
                "skill": "Charms", "description": "Creates light",
            }],
            "proficiencies": [{
                "record_id": "prof-1", "name": "Research",
                "skill": "History",
            }],
            "potions": [{"record_id": "recipe-1", "name": "Calming Draught"}],
            "preparations": [],
            "foods_and_drinks": [],
            "recipes": [{
                "record_id": "recipe-2", "name": "Wiggenweld Recipe"
            }],
        }
        return catalogs.get(collection, [])


class CharacterControlEventTests(unittest.TestCase):
    def controller(self):
        return EventController(
            _WorldDatabase(), lambda: [], lambda: [], lambda: [],
            game_database=_GameDatabase(),
        )

    def test_teaching_event_retains_stable_typed_link(self):
        event = normalize_world_event({
            "record_id": "event-1", "event_type": "taught_spell",
            "title": "Taught Lumos", "date": "2000-01-01",
            "knowledge_record_id": "spell-1",
            "knowledge_collection": "spells", "knowledge_name": "Lumos",
        })
        self.assertEqual(event["knowledge_record_id"], "spell-1")
        self.assertEqual(event["knowledge_collection"], "spells")

    def test_creature_relationship_event_requires_named_creature(self):
        event = normalize_world_event({
            "record_id": "event-2", "event_type": "bonded_creature",
            "title": "Bonded Pip", "date": "2000-01-01",
            "named_creature_id": "named-1", "named_creature_name": "Pip",
        })
        self.assertEqual(event["named_creature_id"], "named-1")
        with self.assertRaisesRegex(ValueError, "named creature"):
            normalize_world_event({
                "record_id": "event-3", "event_type": "tamed_creature",
                "title": "Tamed creature", "date": "2000-01-01",
            })

    def test_search_options_use_ids_and_correct_large_catalogs(self):
        taught = self.controller().character_control_link_options("taught_spell")
        creatures = self.controller().character_control_link_options("irked_creature")
        self.assertEqual(taught[0]["value"], "spell-1")
        self.assertEqual(taught[0]["group"], "Spells")
        self.assertIn("Creates light", taught[0]["search_text"])
        self.assertEqual(creatures[0]["value"], "named-1")
        self.assertEqual(creatures[0]["collection"], "named_creatures")

    def test_invention_events_use_the_same_stable_catalog_links(self):
        event = normalize_world_event({
            "record_id": "event-invention",
            "event_type": "invented_spell",
            "title": "Invented Lumos",
            "date": "2000-01-01",
            "person_ids": ["person-1"],
            "knowledge_record_id": "spell-1",
            "knowledge_collection": "spells",
            "knowledge_name": "Lumos",
        })

        self.assertEqual("spell-1", event["knowledge_record_id"])
        options = self.controller().character_control_link_options(
            "invented_recipe"
        )
        recipe_option = next(
            option for option in options
            if option["value"] == "recipe-2"
        )
        self.assertEqual("recipes", recipe_option["collection"])

    def test_friend_group_events_store_one_group_reference(self):
        joined = normalize_world_event({
            "record_id": "event-friends-1",
            "event_type": "joined_friend_group",
            "title": "+ to friend group",
            "date": "2000-01-01",
            "person_ids": ["person-1"],
            "friend_group_name": "The Silver Circle",
        })
        left = normalize_world_event({
            "record_id": "event-friends-2",
            "event_type": "left_friend_group",
            "title": "− from friend group",
            "date": "2001-01-01",
            "person_ids": ["person-1"],
            "friend_group_name": "The Silver Circle",
        })

        self.assertEqual(joined["friend_group_id"], left["friend_group_id"])
        self.assertEqual("The Silver Circle", joined["friend_group_name"])

    def test_murder_supports_unnamed_muggle_and_mage_victims(self):
        event = normalize_world_event({
            "record_id": "event-murder-unnamed",
            "event_type": "murder",
            "title": "Murder",
            "date": "2000-01-01",
            "person_ids": ["killer-1"],
            "perpetrator_person_ids": ["killer-1"],
            "victim_person_ids": [],
            "unnamed_muggle_victim_count": 2,
            "unnamed_mage_victim_count": 1,
        })

        self.assertEqual(2, event["unnamed_muggle_victim_count"])
        self.assertEqual(1, event["unnamed_mage_victim_count"])
        people = [{"record_id": "killer-1", "displayed_name": "Killer"}]
        self.assertEqual(
            "Murdered 2 unnamed muggles and 1 unnamed mage",
            murder_timeline_summary(event, "killer-1", people),
        )
        self.assertEqual(
            "Murdered 2 unnamed muggles and 1 unnamed mage",
            timeline_event_summary(event),
        )

    def test_unnamed_murder_counts_survive_reference_hydration(self):
        event = normalize_world_event({
            "record_id": "event-murder-reference",
            "event_type": "murder",
            "title": "Murder",
            "date": "2000-01-01",
            "person_ids": ["killer-1"],
            "perpetrator_person_ids": ["killer-1"],
            "victim_person_ids": [],
            "unnamed_muggle_victim_count": 4,
            "unnamed_mage_victim_count": 3,
            "profile_owner_person_id": "killer-1",
            "profile_timeline_event_id": "timeline-1",
        })

        hydrated = world_event_to_timeline(event, "killer-1")
        self.assertEqual(4, hydrated["unnamed_muggle_victim_count"])
        self.assertEqual(3, hydrated["unnamed_mage_victim_count"])
        self.assertEqual(["killer-1"], hydrated["perpetrator_person_ids"])

    def test_foster_event_preserves_roles_and_canonical_person_links(self):
        event = normalize_world_event({
            "record_id": "event-foster",
            "event_type": "foster_child",
            "title": "Foster child",
            "date": "2000-09-01",
            "person_ids": [],
            "foster_parent_person_ids": ["parent-1"],
            "foster_child_person_ids": ["child-1"],
        })

        self.assertEqual(event["foster_parent_person_ids"], ["parent-1"])
        self.assertEqual(event["foster_child_person_ids"], ["child-1"])
        self.assertEqual(set(event["person_ids"]), {"parent-1", "child-1"})


if __name__ == "__main__":
    unittest.main()
