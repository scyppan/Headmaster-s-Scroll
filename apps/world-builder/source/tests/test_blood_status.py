import json
import tempfile
import unittest
from pathlib import Path

from mage_maker.core.controller import PeopleController
from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_MUGGLEBORN,
    BLOOD_STATUS_OPTIONS,
    BLOOD_STATUS_PUREBLOOD,
    DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
    DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
    DEVELOPMENTAL_ENVIRONMENT_OPTIONS,
    PARENT_MAGIC_STATE_MAGICAL,
    PARENT_MAGIC_STATE_NON_MAGICAL,
    allowed_parent_magic_states,
    blood_status_options,
    parent_candidate_explanation,
    resolved_blood_status,
    resolved_developmental_environment,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
)
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


class FakeGridWidget:
    def __init__(self):
        self.visible = True

    def grid(self):
        self.visible = True

    def grid_remove(self):
        self.visible = False


class FakeSelect(FakeGridWidget):
    def __init__(self, variable):
        super().__init__()
        self.variable = variable
        self.values = []

    def set_values(self, values):
        self.values = list(values)

        if (
            self.values
            and self.variable.get() not in self.values
        ):
            self.variable.set(self.values[0])


class BloodStatusModelTests(unittest.TestCase):
    def setUp(self):
        self.magical_birthing_parent = {
            "record_id": "magical-mother",
            "displayed_name": "Magical Mother",
            "can_give_birth": True,
            "non_magical": False,
        }
        self.magical_non_birthing_parent = {
            "record_id": "magical-father",
            "displayed_name": "Magical Father",
            "can_give_birth": False,
            "non_magical": False,
        }
        self.non_magical_birthing_parent = {
            "record_id": "non-magical-mother",
            "displayed_name": "Non-magical Mother",
            "can_give_birth": True,
            "non_magical": True,
        }
        self.non_magical_non_birthing_parent = {
            "record_id": "non-magical-father",
            "displayed_name": "Non-magical Father",
            "can_give_birth": False,
            "non_magical": True,
        }
        self.people = [
            self.magical_birthing_parent,
            self.magical_non_birthing_parent,
            self.non_magical_birthing_parent,
            self.non_magical_non_birthing_parent,
        ]

    def test_no_parents_offer_exactly_three_blood_statuses(self):
        person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "biological_mother_status": "unknown",
            "biological_father_status": "unknown",
        }

        self.assertEqual(
            (
                BLOOD_STATUS_PUREBLOOD,
                BLOOD_STATUS_HALFBLOOD,
                BLOOD_STATUS_MUGGLEBORN,
            ),
            BLOOD_STATUS_OPTIONS,
        )
        self.assertEqual(
            BLOOD_STATUS_OPTIONS,
            blood_status_options(person, self.people),
        )

    def test_one_magical_parent_excludes_muggleborn(self):
        person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "biological_mother_id": "magical-mother",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
        }
        options = blood_status_options(person, self.people)

        self.assertEqual(
            (
                BLOOD_STATUS_PUREBLOOD,
                BLOOD_STATUS_HALFBLOOD,
            ),
            options,
        )

    def test_one_non_magical_parent_excludes_pureblood(self):
        person = {
            "blood_status": BLOOD_STATUS_MUGGLEBORN,
            "biological_mother_id": "non-magical-mother",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
        }

        self.assertEqual(
            (
                BLOOD_STATUS_HALFBLOOD,
                BLOOD_STATUS_MUGGLEBORN,
            ),
            blood_status_options(person, self.people),
        )

    def test_muggle_placeholder_counts_as_non_magical_parent(self):
        person = {
            "blood_status": BLOOD_STATUS_MUGGLEBORN,
            "biological_mother_id": "",
            "biological_mother_status": "muggle",
            "biological_father_id": "",
            "biological_father_status": "unknown",
        }
        options = blood_status_options(person, self.people)

        self.assertIn(BLOOD_STATUS_MUGGLEBORN, options)
        self.assertNotIn(BLOOD_STATUS_PUREBLOOD, options)

    def test_two_magical_parents_fix_pureblood(self):
        person = {
            "biological_mother_id": "magical-mother",
            "biological_father_id": "magical-father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
        }

        self.assertEqual(
            (BLOOD_STATUS_PUREBLOOD,),
            blood_status_options(person, self.people),
        )
        self.assertEqual(
            BLOOD_STATUS_PUREBLOOD,
            resolved_blood_status(person, self.people),
        )

    def test_two_non_magical_parents_fix_muggleborn(self):
        person = {
            "biological_mother_id": "non-magical-mother",
            "biological_father_id": "non-magical-father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
        }

        self.assertEqual(
            (BLOOD_STATUS_MUGGLEBORN,),
            blood_status_options(person, self.people),
        )
        self.assertEqual(
            BLOOD_STATUS_MUGGLEBORN,
            resolved_blood_status(person, self.people),
        )

    def test_split_parentage_fixes_halfblood_and_defaults_environment(self):
        person = {
            "biological_mother_id": "magical-mother",
            "biological_father_id": "non-magical-father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
        }

        self.assertEqual(
            (BLOOD_STATUS_HALFBLOOD,),
            blood_status_options(person, self.people),
        )
        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            resolved_blood_status(person, self.people),
        )
        self.assertEqual(
            DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
            resolved_developmental_environment(person, self.people),
        )

    def test_halfblood_environment_has_exactly_two_options(self):
        self.assertEqual(
            (
                DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
                DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
            ),
            DEVELOPMENTAL_ENVIRONMENT_OPTIONS,
        )

    def test_halfblood_second_parent_must_be_opposite_first_parent(self):
        person = {
            "blood_status": BLOOD_STATUS_HALFBLOOD,
            "developmental_environment": (
                DEVELOPMENTAL_ENVIRONMENT_MAGICAL
            ),
            "biological_mother_id": "magical-mother",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
        }

        self.assertEqual(
            (PARENT_MAGIC_STATE_NON_MAGICAL,),
            allowed_parent_magic_states(
                person,
                self.people,
                "father",
            ),
        )

    def test_parent_explainer_matches_pureblood_filter(self):
        person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "biological_mother_status": "unknown",
            "biological_father_status": "unknown",
        }

        self.assertEqual(
            (
                "Showing only magical parent options because blood "
                "status is set to Pureblood."
            ),
            parent_candidate_explanation(
                person,
                self.people,
                "mother",
            ),
        )

    def test_parent_explainer_matches_halfblood_second_parent_filter(self):
        person = {
            "blood_status": BLOOD_STATUS_HALFBLOOD,
            "biological_mother_id": "magical-mother",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
        }

        self.assertEqual(
            (
                "Showing only non-magical parent options because blood "
                "status is set to Halfblood and the other parent is "
                "magical."
            ),
            parent_candidate_explanation(
                person,
                self.people,
                "father",
            ),
        )

    def test_pureblood_parent_picker_hides_non_magical_people(self):
        focus = {
            "record_id": "focus",
            "displayed_name": "Focus",
            "birth_year": 2000,
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "biological_mother_status": "unknown",
            "biological_father_status": "unknown",
        }
        relationships = FamilyRelationshipMap(
            [focus, *self.people]
        )
        mother_ids = {
            person["record_id"]
            for person in relationships.parent_candidates(
                "focus",
                "mother",
            )
        }

        self.assertIn("magical-mother", mother_ids)
        self.assertNotIn("non-magical-mother", mother_ids)

    def test_muggleborn_parent_picker_hides_magical_people(self):
        focus = {
            "record_id": "focus",
            "displayed_name": "Focus",
            "birth_year": 2000,
            "blood_status": BLOOD_STATUS_MUGGLEBORN,
            "biological_mother_status": "unknown",
            "biological_father_status": "unknown",
        }
        relationships = FamilyRelationshipMap(
            [focus, *self.people]
        )
        father_ids = {
            person["record_id"]
            for person in relationships.parent_candidates(
                "focus",
                "father",
            )
        }

        self.assertNotIn("magical-father", father_ids)
        self.assertIn("non-magical-father", father_ids)

    def test_halfblood_picker_switches_after_first_parent(self):
        focus = {
            "record_id": "focus",
            "displayed_name": "Focus",
            "birth_year": 2000,
            "blood_status": BLOOD_STATUS_HALFBLOOD,
            "developmental_environment": (
                DEVELOPMENTAL_ENVIRONMENT_MUGGLE
            ),
            "biological_mother_id": "magical-mother",
            "biological_mother_status": "person",
            "biological_father_status": "unknown",
        }
        relationships = FamilyRelationshipMap(
            [focus, *self.people]
        )
        father_ids = {
            person["record_id"]
            for person in relationships.parent_candidates(
                "focus",
                "father",
            )
        }

        self.assertNotIn("magical-father", father_ids)
        self.assertIn("non-magical-father", father_ids)

    def test_fixed_pureblood_uses_plain_text_and_hides_environment(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "biological_mother_id": "magical-mother",
            "biological_father_id": "magical-father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
        }
        view.people_provider = lambda: list(self.people)
        view.blood_status_value = FakeVariable(
            BLOOD_STATUS_MUGGLEBORN
        )
        view.developmental_environment_value = FakeVariable(
            DEVELOPMENTAL_ENVIRONMENT_MAGICAL
        )
        view.blood_status_select = FakeSelect(
            view.blood_status_value
        )
        view.blood_status_text = FakeGridWidget()
        view.environment_block = FakeGridWidget()
        view.loading = False

        DevelopmentView.update_blood_status_control(view)

        self.assertEqual(
            BLOOD_STATUS_PUREBLOOD,
            view.blood_status_value.get(),
        )
        self.assertFalse(view.blood_status_select.visible)
        self.assertTrue(view.blood_status_text.visible)
        self.assertFalse(view.environment_block.visible)

    def test_fixed_halfblood_uses_text_and_shows_environment_select(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "blood_status": BLOOD_STATUS_HALFBLOOD,
            "developmental_environment": (
                DEVELOPMENTAL_ENVIRONMENT_MUGGLE
            ),
            "biological_mother_id": "magical-mother",
            "biological_father_id": "non-magical-father",
            "biological_mother_status": "person",
            "biological_father_status": "person",
        }
        view.people_provider = lambda: list(self.people)
        view.blood_status_value = FakeVariable(
            BLOOD_STATUS_HALFBLOOD
        )
        view.developmental_environment_value = FakeVariable(
            DEVELOPMENTAL_ENVIRONMENT_MUGGLE
        )
        view.blood_status_select = FakeSelect(
            view.blood_status_value
        )
        view.blood_status_text = FakeGridWidget()
        view.environment_block = FakeGridWidget()
        view.loading = False

        DevelopmentView.update_blood_status_control(view)

        self.assertEqual(
            [BLOOD_STATUS_HALFBLOOD],
            view.blood_status_select.values,
        )
        self.assertFalse(view.blood_status_select.visible)
        self.assertTrue(view.blood_status_text.visible)
        self.assertTrue(view.environment_block.visible)
        self.assertEqual(
            DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
            view.developmental_environment_value.get(),
        )

    def test_add_child_candidates_respect_selected_parents(self):
        current_parent = {
            "record_id": "current-parent",
            "displayed_name": "Current Parent",
            "birth_year": 1970,
            "can_give_birth": False,
            "non_magical": False,
        }
        other_parent = {
            "record_id": "other-parent",
            "displayed_name": "Other Parent",
            "birth_year": 1972,
            "can_give_birth": True,
            "non_magical": True,
        }
        pureblood_child = {
            "record_id": "pureblood-child",
            "displayed_name": "Pureblood Child",
            "birth_year": 1995,
            "blood_status": BLOOD_STATUS_PUREBLOOD,
        }
        halfblood_child = {
            "record_id": "halfblood-child",
            "displayed_name": "Halfblood Child",
            "birth_year": 1996,
            "blood_status": BLOOD_STATUS_HALFBLOOD,
            "developmental_environment": (
                DEVELOPMENTAL_ENVIRONMENT_MAGICAL
            ),
        }
        relationships = FamilyRelationshipMap(
            [
                current_parent,
                other_parent,
                pureblood_child,
                halfblood_child,
            ]
        )
        child_ids = {
            person["record_id"]
            for person in relationships.child_candidates(
                "current-parent",
                "other-parent",
            )
        }

        self.assertNotIn("pureblood-child", child_ids)
        self.assertIn("halfblood-child", child_ids)


class BloodStatusPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_path = (
            Path(self.temporary_directory.name) / "mage_maker.json"
        )
        self.database_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 12,
                        "database_version": "0.12.0",
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
        self.magical_mother = self.controller.create_person(
            {
                "displayed_name": "Magical Mother",
                "can_give_birth": True,
            }
        )
        self.magical_father = self.controller.create_person(
            {
                "displayed_name": "Magical Father",
                "can_give_birth": False,
            }
        )
        self.non_magical_mother = self.controller.create_person(
            {
                "displayed_name": "Non-magical Mother",
                "can_give_birth": True,
                "non_magical": True,
            }
        )
        self.non_magical_father = self.controller.create_person(
            {
                "displayed_name": "Non-magical Father",
                "can_give_birth": False,
                "non_magical": True,
            }
        )

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_migration_registers_three_part_blood_model(self):
        self.assertEqual(
            29,
            self.database.data["_database"]["schema_version"],
        )

        for person in self.database.list_people():
            self.assertIn(
                person["blood_status"],
                BLOOD_STATUS_OPTIONS,
            )
            self.assertIn("developmental_environment", person)
            self.assertIn("parental_values", person)

    def test_legacy_halfblood_value_moves_upbringing_to_environment(self):
        legacy_path = (
            Path(self.temporary_directory.name) / "legacy.json"
        )
        legacy_path.write_text(
            json.dumps(
                {
                    "_database": {
                        "schema_version": 13,
                        "database_version": "0.13.0",
                    },
                    "_application_settings": {
                        "development_strategy_assignment": (
                            "scattershot"
                        ),
                        MAGE_GROUPS_SETTING_KEY: default_mage_groups(),
                    },
                    "people": [
                        {
                            "record_id": "legacy-halfblood",
                            "displayed_name": "Legacy Halfblood",
                            "blood_status": "Muggle-Raised Halfblood",
                            "biological_mother_id": "",
                            "biological_father_id": "",
                            "biological_mother_status": "unknown",
                            "biological_father_status": "unknown",
                            "mate_ids": [],
                            "spouse_relationships": [],
                            "development_plan": {
                                "schema": "Scattershot",
                                "academic_years_advanced": 0,
                            },
                            "mage_group_id": "unassigned",
                            "timeline_events": [],
                        }
                    ],
                    "locations": [],
                    "organizations": [],
                    "events": [],
                }
            ),
            encoding="utf-8",
        )
        legacy_database = JsonDatabase(legacy_path)
        legacy_database.load()
        migrated = legacy_database.read_person("legacy-halfblood")

        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            migrated["blood_status"],
        )
        self.assertEqual(
            DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
            migrated["developmental_environment"],
        )
        self.assertIsNone(migrated["parental_values"])

    def test_controller_derives_status_from_two_assigned_parents(self):
        pureblood = self.controller.create_person(
            {
                "displayed_name": "Pureblood Child",
                "biological_mother_id": self.magical_mother[
                    "record_id"
                ],
                "biological_father_id": self.magical_father[
                    "record_id"
                ],
            }
        )
        muggleborn = self.controller.create_person(
            {
                "displayed_name": "Muggleborn Child",
                "biological_mother_id": self.non_magical_mother[
                    "record_id"
                ],
                "biological_father_id": self.non_magical_father[
                    "record_id"
                ],
            }
        )
        halfblood = self.controller.create_person(
            {
                "displayed_name": "Halfblood Child",
                "biological_mother_id": self.magical_mother[
                    "record_id"
                ],
                "biological_father_id": self.non_magical_father[
                    "record_id"
                ],
            }
        )

        self.assertEqual(
            BLOOD_STATUS_PUREBLOOD,
            pureblood["blood_status"],
        )
        self.assertEqual(
            BLOOD_STATUS_MUGGLEBORN,
            muggleborn["blood_status"],
        )
        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            halfblood["blood_status"],
        )
        self.assertEqual(
            DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
            halfblood["developmental_environment"],
        )

    def test_controller_rejects_incompatible_parent_assignment(self):
        child = self.controller.create_person(
            {
                "displayed_name": "Halfblood Child",
                "blood_status": BLOOD_STATUS_HALFBLOOD,
                "developmental_environment": (
                    DEVELOPMENTAL_ENVIRONMENT_MAGICAL
                ),
                "biological_mother_id": self.magical_mother[
                    "record_id"
                ],
            }
        )

        with self.assertRaisesRegex(
            ValueError,
            "one magical and one non-magical",
        ):
            self.controller.update_person(
                child["record_id"],
                {
                    "biological_father_id": self.magical_father[
                        "record_id"
                    ],
                },
            )

    def test_parent_magic_change_reconciles_status_and_environment(self):
        child = self.controller.create_person(
            {
                "displayed_name": "Changing Child",
                "biological_mother_id": self.magical_mother[
                    "record_id"
                ],
                "biological_father_id": self.magical_father[
                    "record_id"
                ],
            }
        )
        self.controller.update_person(
            self.magical_father["record_id"],
            {"non_magical": True},
        )
        updated_child = self.controller.get_person(
            child["record_id"]
        )

        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            updated_child["blood_status"],
        )
        self.assertEqual(
            DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
            updated_child["developmental_environment"],
        )


if __name__ == "__main__":
    unittest.main()
