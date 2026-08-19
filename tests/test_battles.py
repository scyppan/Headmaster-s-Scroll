import unittest
from unittest.mock import patch

from headmasters_scroll.battles import (
    calculated_order,
    normalize_battle,
    normalize_battles,
    public_battle,
)
from headmasters_scroll.game_board.service import GameBoardService


def battle_fixture():
    return normalize_battle({
        "record_id": "battle-1",
        "name": "Atrium",
        "map_id": "map-1",
        "status": "active",
        "round": 2,
        "current_participant_id": "turn-hidden",
        "participants": [
            {
                "record_id": "turn-player", "actor_type": "person",
                "actor_id": "person-player", "random_key": 0.1,
            },
            {
                "record_id": "turn-hidden", "actor_type": "creature",
                "actor_id": "creature-hidden", "random_key": 0.7,
            },
        ],
        "order": ["turn-player", "turn-hidden"],
        "calculated_order": ["turn-player", "turn-hidden"],
    })


class BattleStateTests(unittest.TestCase):
    def test_legacy_admin_snapshot_battle_list_is_migrated(self):
        battle = battle_fixture()
        migrated_snapshot = normalize_battles({"battles": [battle]})
        migrated_list = normalize_battles([battle])
        self.assertEqual(migrated_snapshot["battle-1"]["name"], "Atrium")
        self.assertEqual(migrated_list["battle-1"]["map_id"], "map-1")

    def test_actor_can_only_appear_in_one_active_battle(self):
        first = battle_fixture()
        second = battle_fixture()
        second["record_id"] = "battle-2"
        with self.assertRaisesRegex(ValueError, "only one active battle"):
            normalize_battles({"battle-1": first, "battle-2": second})

    def test_creature_random_position_is_fixed_by_persisted_key(self):
        people = [
            {"record_id": "p1", "calculated_rank": 0, "random_key": 0.4},
            {"record_id": "p2", "calculated_rank": 1, "random_key": 0.2},
        ]
        creatures = [{"record_id": "c1", "random_key": 0.51}]
        self.assertEqual(calculated_order(people, creatures), ["p1", "c1", "p2"])
        self.assertEqual(calculated_order(people, creatures), ["p1", "c1", "p2"])

    def test_player_snapshot_hides_hidden_identity_and_count(self):
        battle = battle_fixture()
        actors = {
            ("person", "person-player"): {
                "name": "Hermione Granger", "visibility": "headmaster",
            },
            ("creature", "creature-hidden"): {
                "name": "Graphorn", "visibility": "headmaster",
            },
        }
        public = public_battle(battle, actors, viewer_character_id="person-player")
        self.assertEqual(public["current_name"], "Headmaster turn")
        self.assertEqual([item["name"] for item in public["order"]], ["Hermione Granger"])
        self.assertNotIn("Graphorn", repr(public))

    def test_draft_battle_is_not_exposed_to_players(self):
        battle = battle_fixture()
        battle["status"] = "draft"
        actors = {
            ("person", "person-player"): {
                "name": "Hermione Granger", "visibility": "players",
            },
        }
        self.assertIsNone(
            public_battle(battle, actors, viewer_character_id="person-player")
        )

    def test_person_sort_uses_eminence_then_older_birth_then_fixed_random(self):
        service = object.__new__(GameBoardService)
        campaign = {"game_state": {"current_game_datetime": "2000-01-01T08:00", "people": {}}}
        def attributes(person, *_args):
            return {"skills": [{"breakdown": {"eminence": person["eminence"]}}]}
        older = {"record_id": "older", "birth_year": 1970, "birth_month": 1, "birth_day": 1, "eminence": 10}
        younger = {"record_id": "younger", "birth_year": 1980, "birth_month": 1, "birth_day": 1, "eminence": 10}
        higher = {"record_id": "higher", "birth_year": 1990, "birth_month": 1, "birth_day": 1, "eminence": 11}
        with patch("headmasters_scroll.game_board.service.calculate_character_attributes", side_effect=attributes):
            keys = {
                item["record_id"]: service._battle_person_sort_key(item, {}, {}, campaign, 0.5)
                for item in (older, younger, higher)
            }
        self.assertLess(keys["higher"], keys["older"])
        self.assertLess(keys["older"], keys["younger"])


if __name__ == "__main__":
    unittest.main()
