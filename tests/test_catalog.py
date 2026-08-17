import unittest

from headmasters_scroll.catalog import (
    BOOK_CATEGORIES,
    CANONICAL_TAGS,
    enrich_catalog,
    validate_catalog,
)


class CatalogEnrichmentTests(unittest.TestCase):
    def document(self):
        return {
            "books": [
                {
                    "record_id": "book-stars", "name": "A Primer on Astronomical Observation",
                    "spells": [{"record_id": "spell-light"}], "proficiencies": [], "potions": [],
                },
                {"record_id": "book-empty", "name": "A Chronicle", "spells": [], "proficiencies": [], "potions": []},
            ],
            "spells": [{"record_id": "spell-light", "name": "Shielding Light", "skill": "Charms", "description": "Creates a protective shield."}],
            "proficiencies": [{"record_id": "prof-creature", "name": "Bat Awareness", "tags": ["Creature Awareness"]}],
            "potions": [{"record_id": "potion-heal", "name": "Healing Draught", "description": "Heals wounds."}],
            "preparations": [{"record_id": "prep", "name": "Powdered Root"}],
            "foods_and_drinks": [{"record_id": "food", "name": "Stew"}],
            "creatures": [{
                "record_id": "bat", "name": "Bat", "classification": "XX",
                "awareness_proficiency_id": "prof-creature", "can_be_lured": "Yes",
                "can_be_tamed": "No", "can_bond": "Yes",
            }],
            "wands": [{"record_id": "wand", "name": "Wand"}],
            "holdable_items": [], "accessories": [{"record_id": "ring", "name": "Ring"}],
            "general_items": [{"record_id": "rope", "name": "Rope"}], "plants": [],
        }

    def test_every_target_receives_reviewable_categories_tags_and_rules(self):
        enriched, audit = enrich_catalog(self.document())
        validate_catalog(enriched)
        self.assertEqual(audit["coverage"]["uncategorized_books"], 0)
        self.assertTrue(all(value == 0 for value in audit["coverage"]["untagged_records"].values()))
        self.assertIn("Astronomy", enriched["books"][0]["categories"])
        self.assertIn("History", enriched["books"][1]["categories"])
        self.assertIn("Shielding", enriched["spells"][0]["tags"])
        self.assertIn("Creature Awareness", enriched["proficiencies"][0]["tags"])
        self.assertEqual(enriched["creatures"][0]["interaction_rules"]["lure"]["threshold"], 12)
        self.assertEqual(enriched["creatures"][0]["interaction_rules"]["capture"]["required_proficiency_id"], "")
        self.assertEqual(enriched["wands"][0]["equipment_slot_type"], "focus")
        self.assertEqual(enriched["accessories"][0]["equipment_slot_type"], "accessory")
        self.assertEqual({item["name"] for item in enriched["tag_catalog"]}, set(CANONICAL_TAGS))
        self.assertTrue(set(enriched["books"][0]["categories"]).issubset(BOOK_CATEGORIES))

    def test_flyables_use_the_mounted_slot_and_require_a_threshold(self):
        document = self.document()
        document["general_items"].append({
            "record_id": "carpet", "name": "Flying Carpet", "type": "Flyable",
            "bonuses": [{"type": "Skill", "target": "Flying", "amount": 2}],
        })
        enriched, _audit = enrich_catalog(document)
        flyable = next(
            item for item in enriched["general_items"]
            if item["record_id"] == "carpet"
        )
        self.assertEqual(flyable["activation_mode"], "equipped")
        self.assertEqual(flyable["equipment_slot_type"], "flyable")
        self.assertEqual(flyable["flight_threshold"], 7)
        validate_catalog(enriched)

        flyable["flight_threshold"] = 0
        with self.assertRaisesRegex(ValueError, "Flying threshold"):
            validate_catalog(enriched)

    def test_catalog_tags_are_optional_but_supplied_ids_still_validate(self):
        enriched, _audit = enrich_catalog(self.document())
        enriched["spells"][0]["tags"] = []
        enriched["spells"][0]["tag_ids"] = []
        validate_catalog(enriched)
        enriched["spells"][0]["tag_ids"] = ["missing-tag"]
        with self.assertRaisesRegex(ValueError, "unknown tag"):
            validate_catalog(enriched)


if __name__ == "__main__":
    unittest.main()
