import unittest

from headmasters_scroll.character_attributes import calculate_character_attributes


class CharacterAttributesTests(unittest.TestCase):
    def setUp(self):
        self.person = {
            "record_id": "student-1",
            "displayed_name": "Student One",
            "birth_year": 1988,
            "birth_month": 8,
            "birth_day": 31,
            "school": "Hogwarts",
            "initial_attribute_buys": ["Power", "Power"],
            "initial_bonuses": {
                "skill_bonuses": ["Charms", "Runes"],
                "traits": ["Bookworm"],
            },
            "characteristics": {
                "fortitude": 0,
                "willpower": 6,
                "intellect": 3,
            },
            "parental_values": {
                "generosity": 8,
                "permissiveness": 4,
                "wealth": 2,
            },
            "development_plan": {
                "school_years": [
                    {
                        "year": 1,
                        "school": "Hogwarts",
                        "skipped": False,
                        "ability": "Erudition",
                        "characteristic": "willpower",
                        "electives": [],
                        "eminence": [{
                            "record_id": "manual-year-one",
                            "skill": "Defense",
                            "points": 1,
                        }],
                        "skills": ["Defense", "Defense"],
                    },
                    {
                        "year": 2,
                        "school": "Hogwarts",
                        "skipped": True,
                        "ability": "Naturalism",
                        "characteristic": "fortitude",
                        "electives": [],
                        "eminence": [],
                    },
                    {
                        "year": 3,
                        "school": "Hogwarts",
                        "skipped": False,
                        "ability": "Panache",
                        "characteristic": "intellect",
                        "electives": ["Divination"],
                        "eminence": [],
                    },
                ],
                "adult_years": [],
                "initial_eminence": [],
            },
        }
        self.world = {"people": [self.person], "events": []}
        self.database = {
            "schools": [{
                "name": "Hogwarts",
                "curriculum": [
                    {"year": 1, "core": ["Charms", "Defense"], "electives": []},
                    {"year": 2, "core": ["Charms", "History"], "electives": []},
                    {
                        "year": 3,
                        "core": ["Charms"],
                        "electives": ["Divination", "Creatures"],
                    },
                ],
            }],
        }

    @staticmethod
    def values(summary, collection):
        return {item["name"]: item.get("value", item.get("dice")) for item in summary[collection]}

    def test_school_credit_uses_september_boundary_electives_and_skips(self):
        before = calculate_character_attributes(
            self.person, self.world, self.database, "2001-08-31T23:59"
        )
        after = calculate_character_attributes(
            self.person, self.world, self.database, "2001-09-01T00:00"
        )
        before_skills = self.values(before, "skills")
        after_skills = self.values(after, "skills")
        self.assertEqual(before_skills["Charms"], 2)  # initial + first-year course
        self.assertEqual(before_skills["Divination"], 0)
        self.assertEqual(after_skills["Charms"], 3)
        self.assertEqual(after_skills["Divination"], 1)
        self.assertEqual(after_skills["Creatures"], 0)  # offered, but not elected
        self.assertEqual(after_skills["History"], 3)  # Bookworm trait; skipped course grants nothing

    def test_attributes_eminence_characteristics_and_parental_values(self):
        summary = calculate_character_attributes(
            self.person, self.world, self.database, "2001-09-01T08:00"
        )
        attributes = self.values(summary, "attributes")
        skills = self.values(summary, "skills")
        characteristics = self.values(summary, "characteristics")
        parental = self.values(summary, "parental_values")
        self.assertEqual(attributes, {
            "Power": 2,
            "Erudition": 1,
            "Panache": 1,
            "Naturalism": 1,
        })
        self.assertEqual(skills["Defense"], 4)  # course + two buys + one eminence
        self.assertEqual(characteristics["Fortitude"], 1)
        self.assertEqual(characteristics["Willpower"], 5)  # capped after earned year-one buy
        self.assertEqual(characteristics["Intellect"], 4)
        self.assertEqual(characteristics["Fortitude"], 1)  # base 0 + missed-year development
        self.assertEqual(parental["Generosity"], 8)
        self.assertEqual(summary["traits"], ["Bookworm"])
        defense = next(item for item in summary["skills"] if item["name"] == "Defense")
        self.assertEqual(defense["breakdown"], {
            "background": 0,
            "buys": 2,
            "core_courses": 1,
            "elective_courses": 0,
            "trait_bonus": 0,
            "wand_parts": 0,
            "wand": 0,
            "accessories": 0,
            "eminence": 1,
            "wand_quality": 0,
            "passive": 0,
            "temporary": 0,
            "base": 4,
            "total": 4,
        })
        self.assertEqual([item["label"] for item in defense["sources"]], [
            "Buys", "Corecourses", "Electives", "Traits", "Wand parts", "Wand",
            "Quality", "Accessories", "Passive", "Eminence", "Temp",
        ])
        self.assertEqual(next(item for item in defense["sources"] if item["label"] == "Electives")["points"], 0)

    def test_complete_hover_ledgers_and_parenthetical_modifiers(self):
        person = dict(self.person)
        person["roll_modifiers"] = {
            "abilities": {"Power": {"wand": 2, "accessories": -1, "passive": 1}},
            "skills": {"Charms": {"wand": 2, "temporary": 3}},
        }
        summary = calculate_character_attributes(
            person, {"people": [person], "events": []}, self.database,
            "2001-09-01T08:00",
        )
        power = next(item for item in summary["attributes"] if item["name"] == "Power")
        charms = next(item for item in summary["skills"] if item["name"] == "Charms")
        self.assertEqual(power["breakdown"], {
            "base": 2, "wand": 2, "accessories": -1, "passive": 1, "temporary": 0,
        })
        self.assertEqual((power["value"], power["bonus"], power["total"]), (2, 2, 4))
        self.assertEqual((charms["bonus"], charms["total"]), (5, charms["value"] + 5))
        self.assertTrue(all("points" in item for item in charms["sources"]))
        self.assertIn({"label": "Accessories", "points": 0}, charms["sources"])
        self.assertEqual([item["label"] for item in charms["sources"]], [
            "Buys", "Corecourses", "Electives", "Traits", "Wand parts", "Wand",
            "Quality", "Accessories", "Passive", "Eminence", "Temp",
        ])
        fortitude = next(
            item for item in summary["characteristics"] if item["name"] == "Fortitude"
        )
        self.assertEqual(fortitude["sources"], [
            {"label": "Base", "points": 1},
            {"label": "Passive", "points": 0},
        ])

    def test_characteristic_hover_includes_base_and_passive(self):
        person = dict(self.person)
        person["roll_modifiers"] = {
            "characteristics": {"Fortitude": {"passive": 2}},
        }
        summary = calculate_character_attributes(
            person, {"people": [person], "events": []}, self.database,
            "2001-09-01T08:00",
        )
        fortitude = next(
            item for item in summary["characteristics"] if item["name"] == "Fortitude"
        )
        self.assertEqual(fortitude["breakdown"], {"base": 1, "passive": 2})
        self.assertEqual(fortitude["dice"], 3)

    def test_legacy_initial_skill_buys_supply_corresponding_abilities(self):
        person = dict(self.person)
        person.pop("initial_attribute_buys")
        person["initial_bonuses"] = {
            "skill_bonuses": ["Charms", "Runes"],
            "traits": [],
        }
        summary = calculate_character_attributes(
            person, {"people": [person], "events": []}, self.database,
            "2001-09-01T08:00",
        )
        attributes = self.values(summary, "attributes")
        self.assertEqual(sum(attributes.values()), 5)
        self.assertEqual(attributes["Power"], 1)
        self.assertEqual(attributes["Erudition"], 2)


if __name__ == "__main__":
    unittest.main()
