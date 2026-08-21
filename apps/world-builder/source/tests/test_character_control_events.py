import unittest

from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.models import normalize_world_event


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
