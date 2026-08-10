import inspect
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.initial_values import (
    PARENTAL_MODE_FULLY_RANDOMIZED,
    PARENTAL_MODE_OVERRIDE,
    PARENTAL_MODE_SHARED,
    PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
    PARENTAL_SLIGHT_DELTA_WEIGHTS,
    build_parental_values,
    initialize_parental_values,
    parental_sibling_reference,
    parental_values_for_mode,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.settings.mage_groups import (
    MAGE_GROUPS_SETTING_KEY,
    default_mage_groups,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeMenu:
    def __init__(self):
        self.items = []

    def delete(self, first_index, last_index=None):
        self.items = []

    def add_radiobutton(self, **values):
        self.items.append(values)


class ParentalValueModelTests(unittest.TestCase):
    def test_handling_options_use_a_menu_beside_the_parental_heading(self):
        panel_source = inspect.getsource(
            DevelopmentView.build_plan_panel
        )

        self.assertIn('text="Parental values"', panel_source)
        self.assertNotIn("Parental values (1–10)", panel_source)
        self.assertIn('text="Handling ▾"', panel_source)
        self.assertIn(
            "self.parental_handling_menu.add_radiobutton",
            inspect.getsource(
                DevelopmentView.update_parental_handling_menu
            ),
        )
        self.assertNotIn('text="Sibling handling"', panel_source)
        self.assertNotIn(
            "self.parental_mode_select = RoundedSelect",
            panel_source,
        )

    def test_first_development_activation_initializes_once(self):
        person = {
            "record_id": "bill",
            "displayed_name": "Bill",
            "parental_values": None,
        }
        view = object.__new__(DevelopmentView)
        view.current_person = dict(person)
        view.parental_values = None
        view.loading = False
        view.available_people = lambda: [dict(person)]
        view.apply_parental_values_to_controls = lambda: None
        view.update_parental_controls = lambda: None

        with patch(
            "mage_maker.sections.development.initial_values.random.randint",
            side_effect=[7, 8, 2],
        ):
            first_activation = DevelopmentView.activate(view)

        first_values = dict(view.parental_values)
        second_activation = DevelopmentView.activate(view)

        self.assertTrue(first_activation)
        self.assertFalse(second_activation)
        self.assertEqual(7, first_values["generosity"])
        self.assertEqual(8, first_values["permissiveness"])
        self.assertEqual(2, first_values["wealth"])
        self.assertEqual(first_values, view.parental_values)

    def test_birth_date_rebase_is_reported_as_an_automatic_change(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {"record_id": "bill"}
        view.parental_values = {
            "generosity": 5,
            "permissiveness": 5,
            "wealth": 5,
        }
        view.initial_bonuses = None
        view.pending_automatic_changes = False
        view.loading = False
        view.update_start_year = lambda: None
        view.available_people = lambda: []
        view.apply_parental_values_to_controls = lambda: None
        view.update_parental_controls = lambda: None
        view.reconcile_initial_bonus_assignments = lambda: False

        with patch(
            "mage_maker.sections.development.page.rebase_parental_values",
            return_value={
                "generosity": 6,
                "permissiveness": 5,
                "wealth": 5,
            },
        ):
            DevelopmentView.set_birth_date(view, 1980, 4, 3)

        self.assertTrue(view.pending_automatic_changes)

    def test_full_sibling_inherits_the_existing_family_values(self):
        bill = {
            "record_id": "bill",
            "biological_mother_id": "helga",
            "biological_father_id": "frank",
            "biological_mother_status": "person",
            "biological_father_status": "person",
            "parental_values": build_parental_values(
                {
                    "generosity": 7,
                    "permissiveness": 8,
                    "wealth": 2,
                },
                mode=PARENTAL_MODE_OVERRIDE,
                source="override",
            ),
        }
        sibling = {
            "record_id": "sibling",
            "biological_mother_id": "helga",
            "biological_father_id": "frank",
            "biological_mother_status": "person",
            "biological_father_status": "person",
            "parental_values": None,
        }
        initialized = initialize_parental_values(
            sibling,
            [bill, sibling],
        )

        self.assertEqual(PARENTAL_MODE_SHARED, initialized["mode"])
        self.assertEqual(7, initialized["generosity"])
        self.assertEqual(8, initialized["permissiveness"])
        self.assertEqual(2, initialized["wealth"])

    def test_slight_randomization_uses_the_sibling_baseline(self):
        current = build_parental_values(
            {
                "generosity": 3,
                "permissiveness": 3,
                "wealth": 3,
            }
        )
        person = {
            "record_id": "bill",
            "birth_year": 2000,
            "biological_mother_id": "helga",
            "parental_values": current,
        }
        sibling = {
            "record_id": "nearest",
            "displayed_name": "Nearest Sibling",
            "birth_year": 1998,
            "biological_mother_id": "helga",
            "parental_values": build_parental_values(
                {
                    "generosity": 7,
                    "permissiveness": 8,
                    "wealth": 2,
                },
                mode=PARENTAL_MODE_OVERRIDE,
                family_values={
                    "generosity": 1,
                    "permissiveness": 1,
                    "wealth": 1,
                },
            ),
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[1], [0], [-1]],
        ):
            adjusted = parental_values_for_mode(
                person,
                [person, sibling],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertEqual(
            PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            adjusted["mode"],
        )
        self.assertEqual(8, adjusted["generosity"])
        self.assertEqual(8, adjusted["permissiveness"])
        self.assertEqual(1, adjusted["wealth"])

    def test_slight_randomization_rarely_allows_two_points(self):
        self.assertLessEqual(
            (
                PARENTAL_SLIGHT_DELTA_WEIGHTS[0]
                + PARENTAL_SLIGHT_DELTA_WEIGHTS[-1]
            )
            / sum(PARENTAL_SLIGHT_DELTA_WEIGHTS),
            0.02,
        )
        current = build_parental_values(
            {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            }
        )
        person = {
            "record_id": "bill",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[2], [0], [0]],
        ):
            adjusted = parental_values_for_mode(
                person,
                [person],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertEqual(7, adjusted["generosity"])
        self.assertEqual(5, adjusted["permissiveness"])
        self.assertEqual(5, adjusted["wealth"])

    def test_declining_sibling_wealth_cannot_turn_upward(self):
        current = build_parental_values(
            {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            }
        )
        gary = {
            "record_id": "gary",
            "birth_year": 1990,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 7,
                }
            ),
        }
        nick = {
            "record_id": "nick",
            "birth_year": 1993,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 5,
                }
            ),
        }
        phil = {
            "record_id": "phil",
            "birth_year": 1996,
            "biological_mother_id": "parent",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[0], [0], [2]],
        ):
            adjusted = parental_values_for_mode(
                phil,
                [gary, nick, phil],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertGreaterEqual(adjusted["wealth"], 3)
        self.assertLessEqual(adjusted["wealth"], 5)

    def test_rising_sibling_wealth_cannot_turn_downward(self):
        current = build_parental_values(
            {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            }
        )
        older_sibling = {
            "record_id": "older",
            "birth_year": 1990,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 3,
                }
            ),
        }
        nearest_sibling = {
            "record_id": "nearest",
            "birth_year": 1993,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 5,
                }
            ),
        }
        person = {
            "record_id": "focus",
            "birth_year": 1996,
            "biological_mother_id": "parent",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[0], [0], [-2]],
        ):
            adjusted = parental_values_for_mode(
                person,
                [older_sibling, nearest_sibling, person],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertGreaterEqual(adjusted["wealth"], 5)
        self.assertLessEqual(adjusted["wealth"], 7)

    def test_equal_sibling_wealth_can_randomize_either_direction(self):
        current = build_parental_values(
            {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 5,
            }
        )
        older_sibling = {
            "record_id": "older",
            "birth_year": 1990,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 5,
                }
            ),
        }
        nearest_sibling = {
            "record_id": "nearest",
            "birth_year": 1993,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 5,
                }
            ),
        }
        person = {
            "record_id": "focus",
            "birth_year": 1996,
            "biological_mother_id": "parent",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[0], [0], [1]],
        ):
            adjusted = parental_values_for_mode(
                person,
                [older_sibling, nearest_sibling, person],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertEqual(6, adjusted["wealth"])

    def test_declining_wealth_continues_after_a_long_plateau(self):
        current = build_parental_values(
            {
                "generosity": 5,
                "permissiveness": 5,
                "wealth": 6,
            }
        )
        siblings = []

        for sibling_number, wealth in enumerate(
            (10, 9, 7, 7, 7, 6),
            start=1,
        ):
            siblings.append(
                {
                    "record_id": f"child-{sibling_number}",
                    "birth_year": 1990 + sibling_number,
                    "biological_mother_id": "parent",
                    "parental_values": build_parental_values(
                        {
                            "generosity": 5,
                            "permissiveness": 5,
                            "wealth": wealth,
                        }
                    ),
                }
            )

        youngest = {
            "record_id": "child-7",
            "birth_year": 1997,
            "biological_mother_id": "parent",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.choices",
            side_effect=[[0], [0], [-2]],
        ):
            adjusted = parental_values_for_mode(
                youngest,
                [*siblings, youngest],
                current,
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
            )

        self.assertEqual(4, adjusted["wealth"])

    def test_nearest_aged_initialized_sibling_is_the_reference(self):
        person = {
            "record_id": "focus",
            "birth_year": 2000,
            "birth_month": 6,
            "biological_mother_id": "parent",
        }
        older_sibling = {
            "record_id": "older",
            "displayed_name": "Older Sibling",
            "birth_year": 1990,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 2,
                    "permissiveness": 3,
                    "wealth": 4,
                }
            ),
        }
        nearest_sibling = {
            "record_id": "nearest",
            "displayed_name": "Nearest Sibling",
            "birth_year": 1998,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 7,
                    "permissiveness": 8,
                    "wealth": 9,
                }
            ),
        }
        uninitialized_sibling = {
            "record_id": "uninitialized",
            "displayed_name": "Uninitialized Sibling",
            "birth_year": 1999,
            "biological_mother_id": "parent",
            "parental_values": None,
        }
        reference = parental_sibling_reference(
            person,
            [
                person,
                older_sibling,
                nearest_sibling,
                uninitialized_sibling,
            ],
        )

        self.assertEqual("nearest", reference["record_id"])

    def test_half_sibling_uses_the_wealthiest_parent_line(self):
        wealthy_parent = {
            "record_id": "wealthy-parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 9,
                }
            ),
        }
        other_parent = {
            "record_id": "other-parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 5,
                    "permissiveness": 5,
                    "wealth": 2,
                }
            ),
        }
        person = {
            "record_id": "focus",
            "birth_year": 2000,
            "biological_mother_id": "wealthy-parent",
            "biological_father_id": "other-parent",
        }
        nearest_other_line = {
            "record_id": "other-half",
            "displayed_name": "Other Half-Sibling",
            "birth_year": 1999,
            "biological_father_id": "other-parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 2,
                    "permissiveness": 2,
                    "wealth": 2,
                }
            ),
        }
        wealthy_line = {
            "record_id": "wealthy-half",
            "displayed_name": "Wealthy Half-Sibling",
            "birth_year": 1995,
            "biological_mother_id": "wealthy-parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 8,
                    "permissiveness": 8,
                    "wealth": 9,
                }
            ),
        }
        reference = parental_sibling_reference(
            person,
            [
                wealthy_parent,
                other_parent,
                person,
                nearest_other_line,
                wealthy_line,
            ],
        )

        self.assertEqual("wealthy-half", reference["record_id"])

    def test_handling_menu_names_the_reference_and_hides_it_without_one(self):
        person = {
            "record_id": "focus",
            "birth_year": 2000,
            "biological_mother_id": "parent",
        }
        sibling = {
            "record_id": "sibling",
            "displayed_name": "Bill",
            "birth_year": 1998,
            "biological_mother_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 7,
                    "permissiveness": 8,
                    "wealth": 2,
                }
            ),
        }
        view = object.__new__(DevelopmentView)
        view.current_person = person
        view.parental_handling_menu = FakeMenu()
        view.parental_mode_value = FakeVariable(PARENTAL_MODE_SHARED)
        view.people_provider = Mock(return_value=[person, sibling])

        DevelopmentView.update_parental_handling_menu(view)

        self.assertEqual(
            [
                "Base on Bill",
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
                PARENTAL_MODE_FULLY_RANDOMIZED,
                PARENTAL_MODE_OVERRIDE,
            ],
            [
                item["label"]
                for item in view.parental_handling_menu.items
            ],
        )

        view.people_provider = Mock(return_value=[person])
        DevelopmentView.update_parental_handling_menu(view)

        self.assertEqual(
            [
                PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
                PARENTAL_MODE_FULLY_RANDOMIZED,
                PARENTAL_MODE_OVERRIDE,
            ],
            [
                item["label"]
                for item in view.parental_handling_menu.items
            ],
        )

    def test_override_keeps_manually_entered_values(self):
        current = build_parental_values(
            {
                "generosity": 3,
                "permissiveness": 3,
                "wealth": 3,
            },
            mode=PARENTAL_MODE_OVERRIDE,
        )
        current.update(
            {
                "generosity": 10,
                "permissiveness": 1,
                "wealth": 9,
            }
        )
        person = {
            "record_id": "bill",
            "parental_values": current,
        }
        overridden = parental_values_for_mode(
            person,
            [person],
            current,
            PARENTAL_MODE_OVERRIDE,
        )

        self.assertEqual(PARENTAL_MODE_OVERRIDE, overridden["mode"])
        self.assertEqual(10, overridden["generosity"])
        self.assertEqual(1, overridden["permissiveness"])
        self.assertEqual(9, overridden["wealth"])

    def test_fully_randomize_replaces_all_three_values(self):
        current = build_parental_values(
            {
                "generosity": 7,
                "permissiveness": 8,
                "wealth": 2,
            }
        )
        person = {
            "record_id": "bill",
            "parental_values": current,
        }

        with patch(
            "mage_maker.sections.development.initial_values.random.randint",
            side_effect=[10, 1, 6],
        ):
            randomized = parental_values_for_mode(
                person,
                [person],
                current,
                PARENTAL_MODE_FULLY_RANDOMIZED,
            )

        self.assertEqual(
            PARENTAL_MODE_FULLY_RANDOMIZED,
            randomized["mode"],
        )
        self.assertEqual("fully randomized", randomized["source"])
        self.assertEqual(10, randomized["generosity"])
        self.assertEqual(1, randomized["permissiveness"])
        self.assertEqual(6, randomized["wealth"])

    def test_wealth_uses_a_wealthy_grandparent_generation(self):
        parent = {
            "record_id": "parent",
            "parental_values": build_parental_values(
                {
                    "generosity": 4,
                    "permissiveness": 5,
                    "wealth": 9,
                }
            ),
        }
        child = {
            "record_id": "child",
            "biological_mother_id": "parent",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
            "parental_values": None,
        }

        with (
            patch(
                "mage_maker.sections.development.initial_values.random.choice",
                return_value=1,
            ),
            patch(
                "mage_maker.sections.development.initial_values.random.randint",
                side_effect=[4, 5],
            ),
        ):
            initialized = initialize_parental_values(
                child,
                [parent, child],
            )

        self.assertEqual(10, initialized["wealth"])
        self.assertEqual(
            "generational wealth",
            initialized["source"],
        )


class ParentalValuePersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "mage_maker.json"
        )
        self.database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 14,
                        "database_version": "0.14.0",
                        "last_saved": None,
                    },
                    "_application_settings": {
                        "development_strategy_assignment": (
                            "scattershot"
                        ),
                        MAGE_GROUPS_SETTING_KEY: default_mage_groups(),
                    },
                    "people": [],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        self.database = JsonDatabase(self.database_path)
        self.database.load()
        self.controller = PeopleController(self.database)
        self.helga = self.controller.create_person(
            {
                "displayed_name": "Helga",
                "can_give_birth": True,
            }
        )
        self.frank = self.controller.create_person(
            {
                "displayed_name": "Frank",
                "can_give_birth": False,
            }
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_creation_does_not_assign_parental_values(self):
        bill = self.controller.create_person(
            {"displayed_name": "Bill"}
        )

        self.assertIsNone(bill["parental_values"])

    def test_later_parentage_makes_bill_the_family_baseline(self):
        sibling = self.controller.create_person(
            {
                "displayed_name": "Bill's Sibling",
                "biological_mother_id": self.helga["record_id"],
                "biological_father_id": self.frank["record_id"],
                "parental_values": build_parental_values(
                    {
                        "generosity": 3,
                        "permissiveness": 3,
                        "wealth": 3,
                    }
                ),
            }
        )
        bill = self.controller.create_person(
            {
                "displayed_name": "Bill",
                "parental_values": build_parental_values(
                    {
                        "generosity": 7,
                        "permissiveness": 8,
                        "wealth": 2,
                    },
                    mode=PARENTAL_MODE_OVERRIDE,
                    source="override",
                ),
            }
        )
        self.controller.update_person(
            bill["record_id"],
            {
                "biological_mother_id": self.helga["record_id"],
                "biological_father_id": self.frank["record_id"],
            },
        )
        updated_sibling = self.controller.get_person(
            sibling["record_id"]
        )

        self.assertEqual(
            PARENTAL_MODE_SHARED,
            updated_sibling["parental_values"]["mode"],
        )
        self.assertEqual(
            7,
            updated_sibling["parental_values"]["generosity"],
        )
        self.assertEqual(
            8,
            updated_sibling["parental_values"]["permissiveness"],
        )
        self.assertEqual(
            2,
            updated_sibling["parental_values"]["wealth"],
        )

    def test_sibling_override_survives_family_synchronization(self):
        sibling = self.controller.create_person(
            {
                "displayed_name": "Independent Sibling",
                "biological_mother_id": self.helga["record_id"],
                "biological_father_id": self.frank["record_id"],
                "parental_values": build_parental_values(
                    {
                        "generosity": 1,
                        "permissiveness": 10,
                        "wealth": 6,
                    },
                    mode=PARENTAL_MODE_OVERRIDE,
                    source="override",
                ),
            }
        )
        bill = self.controller.create_person(
            {
                "displayed_name": "Bill",
                "parental_values": build_parental_values(
                    {
                        "generosity": 7,
                        "permissiveness": 8,
                        "wealth": 2,
                    },
                    mode=PARENTAL_MODE_OVERRIDE,
                    source="override",
                ),
            }
        )
        self.controller.update_person(
            bill["record_id"],
            {
                "biological_mother_id": self.helga["record_id"],
                "biological_father_id": self.frank["record_id"],
            },
        )
        updated_sibling = self.controller.get_person(
            sibling["record_id"]
        )

        self.assertEqual(
            1,
            updated_sibling["parental_values"]["generosity"],
        )
        self.assertEqual(
            10,
            updated_sibling["parental_values"]["permissiveness"],
        )
        self.assertEqual(
            6,
            updated_sibling["parental_values"]["wealth"],
        )


if __name__ == "__main__":
    unittest.main()
