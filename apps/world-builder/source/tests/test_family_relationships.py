import unittest
from unittest.mock import Mock, patch

from mage_maker.sections.family_tree.relationships import (
    FamilyRelationshipMap,
    format_person_date,
    maiden_name_for,
)
from mage_maker.sections.family_tree.child_dialog import AddChildDialog
from mage_maker.sections.family_tree.page import FamilyTreeView
from mage_maker.sections.family_tree.relationship_picker import (
    BasicRelationshipDialog,
    RelationshipPickerDialog,
)
from mage_maker.sections.relationships.page import foster_relationship_text


class FamilyRelationshipMapTests(unittest.TestCase):
    def test_foster_relationship_text_names_both_roles(self):
        self.assertEqual(
            "Parent is foster parent of Child",
            foster_relationship_text("Parent", ["Child"], True),
        )
        self.assertEqual(
            "Parent is foster parent of Child",
            foster_relationship_text("Child", ["Parent"], False),
        )

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

    def test_siblings_are_presented_in_full_birth_order(self):
        people = [
            {
                "record_id": "parent",
                "displayed_name": "Parent",
                "birth_year": 850,
            },
            {
                "record_id": "younger",
                "displayed_name": "Younger",
                "birth_year": 915,
                "birth_month": 1,
                "biological_father_id": "parent",
            },
            {
                "record_id": "focus",
                "displayed_name": "Focus",
                "birth_year": 895,
                "birth_month": 12,
                "biological_father_id": "parent",
            },
            {
                "record_id": "same-year-older",
                "displayed_name": "Same-year older",
                "birth_year": 895,
                "birth_month": 2,
                "biological_father_id": "parent",
            },
        ]
        relationships = FamilyRelationshipMap(people)
        focus_generation_ids = [
            node["person"]["record_id"]
            for node in relationships.build_generations("focus")[2]
        ]

        self.assertEqual(
            ["same-year-older", "focus", "younger"],
            focus_generation_ids,
        )

    def test_default_child_candidates_exclude_parent_age_42_and_later(self):
        people = [
            {
                "record_id": "haraldr",
                "displayed_name": "Haraldr Hálfdanarson",
                "birth_year": 850,
            },
            {
                "record_id": "erik",
                "displayed_name": "Erik Bloodaxe",
                "birth_year": 895,
            },
        ]
        relationships = FamilyRelationshipMap(people)

        self.assertNotIn(
            "erik",
            {
                person["record_id"]
                for person in relationships.child_candidates("haraldr")
            },
        )

        self.assertIn(
            "erik",
            {
                person["record_id"]
                for person in relationships.child_candidates(
                    "haraldr",
                    ignore_age_limits=True,
                )
            },
        )

    def test_default_child_candidates_include_parent_age_41(self):
        people = [
            {
                "record_id": "parent",
                "displayed_name": "Parent",
                "birth_year": 850,
            },
            {
                "record_id": "child",
                "displayed_name": "Child",
                "birth_year": 891,
            },
        ]

        self.assertEqual(
            ["child"],
            [
                person["record_id"]
                for person in FamilyRelationshipMap(people).child_candidates(
                    "parent"
                )
            ],
        )

    def test_mates_and_lineage_are_derived(self):
        self.assertEqual(["mate"], self.relationships.mates_of("focus"))
        self.assertIn("child", self.relationships.descendants_of("focus"))
        self.assertIn("grandmother", self.relationships.ancestors_of("focus"))

    def test_parent_couple_search_keeps_mixed_magic_spouse_pair(self):
        people = [
            {
                "record_id": "child",
                "displayed_name": "Child",
                "birth_year": 950,
                "blood_status": "Pureblood",
            },
            {
                "record_id": "gunnhild",
                "displayed_name": "Gunnhild",
                "birth_year": 910,
                "can_give_birth": True,
                "mate_ids": ["erik"],
            },
            {
                "record_id": "erik",
                "displayed_name": "Erik Bloodaxe",
                "birth_year": 895,
                "can_give_birth": False,
                "non_magical": True,
                "mate_ids": ["gunnhild"],
            },
        ]
        relationships = FamilyRelationshipMap(people)

        self.assertEqual(
            [("gunnhild", "erik")],
            [
                (mother["record_id"], father["record_id"])
                for mother, father in relationships.parent_couple_candidates(
                    "child"
                )
            ],
        )

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

    def test_child_candidates_exclude_people_who_already_have_a_parent(self):
        people = self.people + [
            {
                "record_id": "available-child",
                "displayed_name": "Available Child",
                "birth_year": 2005,
            },
            {
                "record_id": "already-parented",
                "displayed_name": "Already Parented",
                "birth_year": 2005,
                "biological_father_id": "someone-else",
            },
        ]
        candidate_ids = {
            person["record_id"]
            for person in FamilyRelationshipMap(people).child_candidates(
                "focus"
            )
        }

        self.assertIn("available-child", candidate_ids)
        self.assertNotIn("already-parented", candidate_ids)

    def test_foster_relatives_use_the_right_generations_without_blood_edges(self):
        people = self.people + [
            {
                "record_id": "foster-parent",
                "displayed_name": "Foster Parent",
            },
            {
                "record_id": "foster-child",
                "displayed_name": "Foster Child",
            },
        ]
        events = [
            {
                "record_id": "foster-event-parent",
                "event_type": "foster_child",
                "person_ids": ["foster-parent", "focus"],
                "foster_parent_person_ids": ["foster-parent"],
                "foster_child_person_ids": ["focus"],
            },
            {
                "record_id": "foster-event-child",
                "event_type": "foster_child",
                "person_ids": ["focus", "foster-child"],
                "foster_parent_person_ids": ["focus"],
                "foster_child_person_ids": ["foster-child"],
            },
        ]
        relationships = FamilyRelationshipMap(people, foster_events=events)
        generations = relationships.build_generations("focus")
        parent_relations = {
            node["person"]["record_id"]: node["relation"]
            for node in generations[1]
        }
        child_relations = {
            node["person"]["record_id"]: node["relation"]
            for node in generations[3]
        }

        self.assertEqual("Foster parent", parent_relations["foster-parent"])
        self.assertEqual("Foster child", child_relations["foster-child"])
        visible_ids = {
            node["person"]["record_id"]
            for generation in generations
            for node in generation
        }
        edges = relationships.visible_parent_child_edges(visible_ids)
        self.assertNotIn(("foster-parent", "focus"), edges)
        self.assertNotIn(("focus", "foster-child"), edges)

    def test_foster_child_is_positioned_outside_biological_children(self):
        class RelationshipLayoutStub:
            def parents_of(self, record_id):
                return ["focus"] if record_id.startswith("child") else []

        view = object.__new__(FamilyTreeView)
        view.relationship_map = RelationshipLayoutStub()
        view.node_coordinates = {
            "focus": (300, 180, 132, 64),
        }
        nodes = [
            {
                "person": {"record_id": "child-a"},
                "relation": "Child",
            },
            {
                "person": {"record_id": "foster-child"},
                "relation": "Foster child",
            },
            {
                "person": {"record_id": "child-b"},
                "relation": "Child",
            },
        ]
        positions = FamilyTreeView.positions_for_row(
            view,
            nodes,
            3,
            0,
            700,
            300,
            "focus",
        )
        positions_by_id = {
            node["person"]["record_id"]: x_position
            for node, x_position, *_ in positions
        }

        self.assertGreater(
            positions_by_id["foster-child"],
            max(
                positions_by_id["child-a"],
                positions_by_id["child-b"],
            ),
        )


class BasicParentQuickAddTests(unittest.TestCase):
    class Variable:
        def __init__(self, value=""):
            self.value = value

        def get(self):
            return self.value

    def test_parent_quick_add_submits_required_birth_year(self):
        submitted = []
        dialog = object.__new__(BasicRelationshipDialog)
        dialog.displayed_name_value = self.Variable("Haraldr")
        dialog.birth_year_value = self.Variable("850")
        dialog.deceased_value = self.Variable(True)
        dialog.death_year_value = self.Variable("920")
        dialog.death_month_value = self.Variable("3")
        dialog.death_day_value = self.Variable("14")
        dialog.locations = [
            {"record_id": "norway", "name": "Norway"}
        ]
        dialog.create_location_command = Mock()
        dialog.starting_location_id = "norway"
        dialog.starting_location_value = self.Variable("Norway")
        dialog.save_command = lambda values: submitted.append(values) or values
        dialog.destroy = Mock()

        BasicRelationshipDialog.save_person(dialog)

        self.assertEqual(850, submitted[0]["birth_year"])
        self.assertTrue(submitted[0]["deceased"])
        self.assertEqual(920, submitted[0]["death_year"])
        self.assertEqual(3, submitted[0]["death_month"])
        self.assertEqual(14, submitted[0]["death_day"])
        self.assertEqual("norway", submitted[0]["starting_location_id"])
        dialog.destroy.assert_called_once_with()

    def test_quick_added_starting_location_is_available_to_parent(self):
        created = {
            "record_id": "new-village",
            "name": "New village",
        }
        dialog = object.__new__(BasicRelationshipDialog)
        dialog.locations = []
        dialog.create_location_command = Mock(return_value=created)

        result = BasicRelationshipDialog.create_starting_location(
            dialog,
            {"name": "New village"},
        )

        self.assertEqual(created, result)
        self.assertEqual([created], dialog.locations)


class AddChildPersonDialogTests(unittest.TestCase):
    def test_parent_birth_location_is_used_as_the_default(self):
        dialog = object.__new__(AddChildDialog)
        dialog.current_person = {
            "record_id": "parent",
            "displayed_name": "Parent",
        }
        dialog.other_parent_kind = "unknown"
        dialog.other_parent_id = ""
        dialog.people_provider = lambda: [dialog.current_person]
        dialog.event_provider = lambda person_id: [
            {
                "event_type": "born",
                "person_ids": [person_id],
                "location_ids": ["orkney"],
            }
        ]
        dialog.location_events_cache = {}

        location_id = AddChildDialog.preferred_parent_starting_location_id(
            dialog,
            [
                {"record_id": "northumbria", "name": "Northumbria"},
                {"record_id": "orkney", "name": "Orkney Islands"},
            ],
        )

        self.assertEqual("orkney", location_id)

    def test_new_child_profile_keeps_the_chosen_starting_location(self):
        class Variable:
            def __init__(self):
                self.value = ""

            def set(self, value):
                self.value = value

        class Listbox:
            def selection_clear(self, start, end):
                return None

        dialog = object.__new__(AddChildDialog)
        dialog.new_child_value = Variable()
        dialog.child_listbox = Listbox()

        result = AddChildDialog.set_new_child(
            dialog,
            {
                "displayed_name": "New child",
                "birth_year": 954,
                "starting_location_id": "orkney",
                "starting_location": "Orkney Islands",
                "non_magical": True,
            },
        )

        self.assertTrue(result)
        self.assertEqual(
            "orkney",
            dialog.new_child_profile["starting_location_id"],
        )
        self.assertEqual(
            "Orkney Islands",
            dialog.new_child_profile["starting_location"],
        )
        self.assertTrue(dialog.new_child_profile["non_magical"])


class ParentDisplayedNameSearchTests(unittest.TestCase):
    @patch(
        "mage_maker.sections.family_tree.page.parent_candidate_explanation",
        return_value="",
    )
    @patch("mage_maker.sections.family_tree.page.RelationshipPickerDialog")
    def test_parent_picker_refreshes_names_before_searching(
        self,
        picker_dialog,
        explanation,
    ):
        view = object.__new__(FamilyTreeView)
        view.current_person = {"record_id": "child"}
        view.reload_people = Mock()
        view.relationship_map = Mock()
        view.relationship_map.people_by_id = {}
        view.relationship_map.parent_candidates.side_effect = [[], []]
        view.set_parent = Mock()
        view.create_parent = Mock()
        view.set_parent_status = Mock()
        view.locations_provider = lambda: ()
        view.create_location_command = Mock()

        FamilyTreeView.open_parent_picker(view, "father")

        view.reload_people.assert_called_once_with(redraw=False)
        self.assertEqual(
            [
                (("child", "father"), {}),
                (("child", "father"), {"alternate_role": True}),
            ],
            view.relationship_map.parent_candidates.call_args_list,
        )
        picker_dialog.assert_called_once()

    def test_typed_display_name_searches_both_parent_roles(self):
        primary = [
            {"record_id": "haraldr", "displayed_name": "Haraldr"},
        ]
        alternate = [
            {"record_id": "erik", "displayed_name": "Erik Bloodaxe"},
        ]

        results = RelationshipPickerDialog.matching_people(
            primary,
            alternate,
            "erik bloodaxe",
            show_alternate=False,
        )

        self.assertEqual(["erik"], [person["record_id"] for person in results])

    def test_exact_display_name_is_ranked_before_partial_matches(self):
        primary = [
            {
                "record_id": "story",
                "displayed_name": "The Saga of Erik Bloodaxe",
            },
            {"record_id": "erik", "displayed_name": "Erik Bloodaxe"},
        ]

        results = RelationshipPickerDialog.matching_people(
            primary,
            (),
            "erik bloodaxe",
        )

        self.assertEqual(
            ["erik", "story"],
            [person["record_id"] for person in results],
        )


if __name__ == "__main__":
    unittest.main()
