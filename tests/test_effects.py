import unittest

from headmasters_scroll.effects import (
    BONUS_TARGETS,
    normalize_bonus,
    normalize_target_scope,
    validate_bonus,
)


class EffectSchemaTests(unittest.TestCase):
    def test_legacy_item_bonus_gets_safe_defaults(self):
        bonus = normalize_bonus({
            "type": "Skill",
            "target": "Social Skills",
            "amount": 2,
        })
        self.assertEqual(bonus["target"], "Social")
        self.assertEqual(bonus["activation_mode"], "passive")
        self.assertEqual(bonus["target_scope"], "self")
        self.assertFalse(bonus["depletable"])
        validate_bonus(bonus)

    def test_clickable_bonus_can_be_depletable(self):
        bonus = normalize_bonus({
            "type": "Ability",
            "target": "Power",
            "amount": 1,
            "activation_mode": "click",
            "target_scope": "group",
            "depletable": True,
        })
        validate_bonus(bonus)
        self.assertTrue(bonus["depletable"])

    def test_passive_bonus_cannot_remain_depletable(self):
        bonus = normalize_bonus({
            "type": "Characteristic",
            "target": "Willpower",
            "amount": 1,
            "activation_mode": "passive",
            "depletable": True,
        })
        self.assertFalse(bonus["depletable"])

    def test_skill_targets_come_from_the_real_skill_catalog(self):
        self.assertIn("Charms", BONUS_TARGETS["Skill"])
        self.assertIn("Artificing", BONUS_TARGETS["Skill"])
        self.assertNotIn("Power", BONUS_TARGETS["Skill"])

    def test_no_target_label_normalizes(self):
        self.assertEqual(normalize_target_scope("No Target"), "none")


if __name__ == "__main__":
    unittest.main()
