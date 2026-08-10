import unittest

from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
    format_person_date,
    maiden_name_for,
)
from mage_maker.sections.family_tree.page import FamilyTreeView


class FamilyRelationshipMapTests(unittest.TestCase):
    def setUp(self):
        self.people = [
            {
                "record_id": "grandmother",
                "displayed_name": "Grandmother",
                "can_give_birth": True,
            },
            {
                "record_id": "mother",
                "displayed_name": "Mother",
                "biological_mother_id": "grandmother",
                "can_give_birth": True,
            },
            {
                "record_id": "aunt",
                "displayed_name": "Aunt",
                "biological_mother_id": "grandmother",
                "can_give_birth": True,
            },
            {
                "record_id": "father",
                "displayed_name": "Father",
                "can_give_birth": False,
            },
            {
                "record_id": "focus",
                "displayed_name": "Focus",
                "birth_year": 1980,
                "biological_mother_id": "mother",
                "biological_father_id": "father",
                "mate_ids": ["mate"],
            },
            {
                "record_id": "sibling",
                "displayed_name": "Sibling",
                "biological_mother_id": "mother",
                "biological_father_id": "father",
            },
            {
                "record_id": "other-father",
                "displayed_name": "Other Father",
                "can_give_birth": False,
            },
            {
                "record_id": "half-sibling",
                "displayed_name": "Half Sibling",
                "biological_mother_id": "mother",
                "biological_father_id": "other-father",
            },
            {
                "record_id": "cousin",
                "displayed_name": "Cousin",
                "biological_mother_id": "aunt",
            },
            {
                "record_id": "mate",
                "displayed_name": "Mate",
                "birth_year": 1985,
                "can_give_birth": True,
            },
            {
                "record_id": "child",
                "displayed_name": "Child",
                "birth_year": 2005,
                "biological_mother_id": "mate",
                "biological_father_id": "focus",
            },
            {
                "record_id": "unused-birthing-parent",
                "displayed_name": "Unused Birthing Parent",
                "birth_year": 1970,
                "can_give_birth": True,
            },
            {
                "record_id": "unused-non-birthing-parent",
                "displayed_name": "Unused Non-birthing Parent",
                "birth_year": 1975,
                "can_give_birth": False,
            },
        ]
        self.relationships = FamilyRelationshipMap(self.people)

    def test_five_generations_include_expected_relationships(self):
        generations = self.relationships.build_generations("focus")
        relations = [
            {node["person"]["record_id"]: node["relation"] for node in generation}
            for generation in generations
        ]
        self.assertEqual("Grandparent", relations[0]["grandmother"])
        self.assertEqual("Birthing parent", relations[1]["mother"])
        self.assertEqual("Birthing parent's sibling", relations[1]["aunt"])
        self.assertEqual("Sibling", relations[2]["sibling"])
        self.assertEqual("1/2 Sibling", relations[2]["half-sibling"])
        self.assertEqual("Birthing parent's cousin", relations[2]["cousin"])
        self.assertEqual("Child", relations[3]["child"])

    def test_mates_and_lineage_are_derived(self):
        self.assertEqual(["mate"], self.relationships.mates_of("focus"))
        self.assertIn("child", self.relationships.descendants_of("focus"))
        self.assertIn("grandmother", self.relationships.ancestors_of("focus"))

    def test_unknown_second_parent_does_not_prove_half_sibling_relationship(self):
        people = self.people + [
            {
                "record_id": "one-known-parent",
                "displayed_name": "One Known Parent",
                "biological_mother_id": "mother",
            }
        ]
        relationships = FamilyRelationshipMap(people)
        self.assertEqual(
            "Sibling",
            relationships.sibling_relation("focus", "one-known-parent"),
        )

    def test_open_spouse_fades_only_children_from_other_mates(self):
        people = self.people + [
            {
                "record_id": "second-mate",
                "displayed_name": "Second Mate",
                "can_give_birth": True,
            },
            {
                "record_id": "second-child",
                "displayed_name": "Second Child",
                "biological_mother_id": "second-mate",
                "biological_father_id": "focus",
            },
        ]
        family_view = FamilyTreeView.__new__(FamilyTreeView)
        family_view.current_person = self.relationships.person("focus")
        family_view.active_mate_id = "mate"
        family_view.relationship_map = FamilyRelationshipMap(people)

        self.assertFalse(family_view.child_is_faded("child"))
        self.assertTrue(family_view.child_is_faded("second-child"))
        self.assertFalse(family_view.child_is_faded("cousin"))

    def test_step_parents_are_derived_from_each_parents_other_mates(self):
        self.people[3]["mate_ids"] = ["mother", "step-parent"]
        people = self.people + [
            {
                "record_id": "step-parent",
                "displayed_name": "Step Parent",
                "can_give_birth": True,
            }
        ]
        relationships = FamilyRelationshipMap(people)
        self.assertEqual(
            {
                "mother": ["other-father"],
                "father": ["step-parent"],
            },
            relationships.step_parent_mates_of("focus"),
        )

    def test_open_step_parent_fades_their_mates_other_children(self):
        self.people[3]["mate_ids"] = ["mother", "step-parent"]
        people = self.people + [
            {
                "record_id": "step-parent",
                "displayed_name": "Step Parent",
                "can_give_birth": True,
            },
            {
                "record_id": "step-sibling",
                "displayed_name": "Step Sibling",
                "biological_mother_id": "step-parent",
                "biological_father_id": "father",
            },
        ]
        family_view = FamilyTreeView.__new__(FamilyTreeView)
        family_view.current_person = FamilyRelationshipMap(people).person("focus")
        family_view.active_spouse_owner_id = "father"
        family_view.active_mate_id = "step-parent"
        family_view.relationship_map = FamilyRelationshipMap(people)

        self.assertTrue(family_view.child_is_faded("focus"))
        self.assertFalse(family_view.child_is_faded("step-sibling"))

    def test_date_and_maiden_name_formatting(self):
        person = {
            "birth_year": 1982,
            "birth_month": 3,
            "name_details": {
                "entries": [
                    {"name_type": "Maiden name", "name_entry": "Earlier"}
                ]
            },
        }
        self.assertEqual("1982-03", format_person_date(person))
        self.assertEqual("Earlier", maiden_name_for(person))
        self.assertEqual("nd.", format_person_date({}))

    def test_alternate_father_options_are_unused_birthing_parents(self):
        candidate_ids = {
            person["record_id"]
            for person in self.relationships.parent_candidates(
                "cousin",
                "father",
                alternate_role=True,
            )
        }
        self.assertIn("unused-birthing-parent", candidate_ids)
        self.assertNotIn("mother", candidate_ids)
        self.assertNotIn("mate", candidate_ids)

    def test_alternate_mother_options_are_unused_non_birthing_parents(self):
        candidate_ids = {
            person["record_id"]
            for person in self.relationships.parent_candidates(
                "cousin",
                "mother",
                alternate_role=True,
            )
        }
        self.assertIn("unused-non-birthing-parent", candidate_ids)
        self.assertNotIn("father", candidate_ids)
        self.assertNotIn("focus", candidate_ids)

    def test_mate_options_support_safe_role_switches(self):
        primary_ids = {
            person["record_id"]
            for person in self.relationships.partner_candidates("focus")
        }
        alternate_ids = {
            person["record_id"]
            for person in self.relationships.partner_candidates(
                "focus",
                alternate_role=True,
            )
        }
        self.assertIn("unused-birthing-parent", primary_ids)
        self.assertIn("unused-non-birthing-parent", alternate_ids)
        self.assertNotIn("father", alternate_ids)

    def test_child_parent_choices_keep_existing_mates_in_the_preferred_group(self):
        existing_mate_ids = set(self.relationships.mates_of("focus"))
        new_parent_ids = {
            person["record_id"]
            for person in self.relationships.partner_candidates("focus")
        }
        self.assertEqual({"mate"}, existing_mate_ids)
        self.assertNotIn("mate", new_parent_ids)

    def test_parent_role_children_are_reported_for_checkbox_locking(self):
        birthing_child_ids = {
            child["record_id"]
            for child in self.relationships.children_for_parent_role(
                "mother",
                "mother",
            )
        }
        non_birthing_child_ids = {
            child["record_id"]
            for child in self.relationships.children_for_parent_role(
                "father",
                "father",
            )
        }
        self.assertEqual({"focus", "sibling", "half-sibling"}, birthing_child_ids)
        self.assertEqual({"focus", "sibling"}, non_birthing_child_ids)

    def test_child_candidates_adjust_to_the_youngest_selected_parent(self):
        people = self.people + [
            {
                "record_id": "born-1998",
                "displayed_name": "Born 1998",
                "birth_year": 1998,
            },
            {
                "record_id": "born-2003",
                "displayed_name": "Born 2003",
                "birth_year": 2003,
            },
            {
                "record_id": "born-unknown",
                "displayed_name": "Born Unknown",
                "birth_year": None,
            },
        ]
        relationships = FamilyRelationshipMap(people)
        focus_only_ids = {
            person["record_id"]
            for person in relationships.child_candidates("focus")
        }
        two_parent_ids = {
            person["record_id"]
            for person in relationships.child_candidates("focus", "mate")
        }
        self.assertIn("born-1998", focus_only_ids)
        self.assertNotIn("born-1998", two_parent_ids)
        self.assertIn("born-2003", two_parent_ids)
        self.assertNotIn("born-unknown", two_parent_ids)
        self.assertEqual(2003, relationships.minimum_child_birth_year("focus", "mate"))

    def test_child_candidates_are_empty_when_a_selected_parent_age_is_unknown(self):
        people = self.people + [
            {
                "record_id": "unknown-age-parent",
                "displayed_name": "Unknown Age Parent",
                "birth_year": None,
            }
        ]
        relationships = FamilyRelationshipMap(people)
        self.assertEqual(
            [],
            relationships.child_candidates("focus", "unknown-age-parent"),
        )


if __name__ == "__main__":
    unittest.main()
