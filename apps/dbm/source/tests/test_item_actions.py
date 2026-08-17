import unittest

from shared.item_actions import normalize_item_action, validate_item_actions


class CatalogDatabase:
    def get_collection(self, collection):
        return {
            "spells": [{"record_id": "spell-1", "name": "Lumos"}],
            "proficiencies": [
                {"record_id": "prof-1", "name": "Rune Carving"}
            ],
            "potions": [{"record_id": "potion-1", "name": "Tonic"}],
            "preparations": [],
        }.get(collection, [])


class ItemActionTests(unittest.TestCase):
    def test_linked_spell_is_a_clickable_authoritative_roll(self):
        action = normalize_item_action({
            "effect_type": "Spell",
            "target_id": "spell-1",
            "name": "Lumos",
            "depletable": True,
        })
        validate_item_actions([action], CatalogDatabase())
        self.assertEqual(action["action_type"], "roll")
        self.assertEqual(action["roll_type"], "spell")
        self.assertEqual(action["activation_mode"], "click")
        self.assertEqual(action["consume_quantity"], 1)

    def test_custom_effect_may_be_passive(self):
        action = normalize_item_action({
            "effect_type": "Custom",
            "name": "Warmth",
            "description": "Keeps the bearer warm.",
            "activation_mode": "passive",
            "depletable": True,
        })
        validate_item_actions([action], CatalogDatabase())
        self.assertEqual(action["action_type"], "message")
        self.assertEqual(action["activation_mode"], "passive")
        self.assertFalse(action["depletable"])


if __name__ == "__main__":
    unittest.main()
