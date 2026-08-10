import unittest
from copy import deepcopy
from unittest.mock import patch

from mage_maker.core.database import JsonDatabase
from mage_maker.core.dates import (
    person_age_at_death,
    person_death_age_text,
)
from mage_maker.sections.development.event_eminence import (
    event_eminence_record_id,
    reconcile_person_event_eminence,
)
from mage_maker.sections.development.characteristics import (
    CHARACTERISTIC_NAMES,
)
from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_MUGGLEBORN,
    BLOOD_STATUS_OPTIONS,
    BLOOD_STATUS_PUREBLOOD,
    randomized_blood_status,
)
from mage_maker.sections.development.models import (
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    normalize_development_plan,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.events.controller import EventController
from mage_maker.sections.events.period_view import (
    period_event_display_text,
)
from mage_maker.sections.locations.periods import lifespan_text
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    new_organization_event,
)


class EventEminenceDatabase:
    def __init__(self, people):
        self.people = deepcopy(people)
        self.records = {
            "events": [],
            "organizations": [],
            "locations": [],
        }
        self.data = {"_application_settings": {}}
        self.dirty = False
        self.save_count = 0

    def list_people(self):
        return deepcopy(self.people)

    def update_person(self, record_id, values):
        for person in self.people:
            if person.get("record_id") != record_id:
                continue

            person.update(deepcopy(values))
            self.dirty = True
            return deepcopy(person)

        raise KeyError(record_id)

    def list_records(self, collection_name):
        return deepcopy(self.records[collection_name])

    def read_record(self, collection_name, record_id):
        return next(
            (
                deepcopy(record)
                for record in self.records[collection_name]
                if record.get("record_id") == record_id
            ),
            None,
        )

    def create_record(self, collection_name, values):
        record = deepcopy(values)
        self.records[collection_name].append(record)
        self.dirty = True
        return deepcopy(record)

    def update_record(self, collection_name, record_id, values):
        for record in self.records[collection_name]:
            if record.get("record_id") != record_id:
                continue

            record.update(deepcopy(values))
            self.dirty = True
            return deepcopy(record)

        raise KeyError(record_id)

    def delete_record(self, collection_name, record_id):
        for index, record in enumerate(self.records[collection_name]):
            if record.get("record_id") != record_id:
                continue

            deleted = self.records[collection_name].pop(index)
            self.dirty = True
            return deepcopy(deleted)

        raise KeyError(record_id)

    def save(self):
        self.save_count += 1
        self.dirty = False


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def development_school_year(year):
    return {
        "year": year,
        "school": "Hogwarts",
        "skipped": False,
        "ability": DEVELOPMENT_ABILITY_OPTIONS[0],
        "skills": list(DEVELOPMENT_SKILL_OPTIONS[:2]),
        "characteristic": "",
        "assigned_books": [],
        "books": [],
        "eminence": [],
    }


def developed_person(record_id="person-1"):
    return {
        "record_id": record_id,
        "displayed_name": "Test Magician",
        "birth_year": 1980,
        "birth_month": 7,
        "birth_day": 31,
        "development_plan": normalize_development_plan(
            {
                "schema": "Scattershot",
                "blood_status_initialized": True,
                "academic_years_advanced": 7,
                "school_started": True,
                "school_years": [
                    development_school_year(year)
                    for year in range(1, 8)
                ],
                "adult_years": [
                    {
                        "adult_year": 1,
                        "reading_characteristic": "",
                        "reading_rolls": [],
                        "books": [],
                        "eminence": [],
                        "jobs": [],
                    }
                ],
            }
        ),
    }


def world_event(
    record_id="event-1",
    date="1998",
    person_id="person-1",
    awards_eminence=True,
):
    return {
        "record_id": record_id,
        "event_type": "other",
        "title": "Defended London",
        "date": date,
        "description": "Protected the city.",
        "person_ids": [person_id],
        "eminence_person_ids": (
            [person_id]
            if awards_eminence
            else []
        ),
        "period_names": [],
        "location_ids": [],
        "locked_location_ids": [],
    }


class DeathAgeTests(unittest.TestCase):
    def test_complete_dates_show_exact_age(self):
        person = {
            "birth_year": 1980,
            "birth_month": 7,
            "birth_day": 31,
            "death_year": 1998,
            "death_month": 7,
            "death_day": 30,
        }

        self.assertEqual((17, True), person_age_at_death(person))
        self.assertEqual("age 17", person_death_age_text(person))

        person["death_day"] = 31
        self.assertEqual((18, True), person_age_at_death(person))

    def test_year_only_dates_show_approximate_age(self):
        person = {
            "birth_year": 923,
            "death_year": 998,
            "deceased": True,
        }

        self.assertEqual((75, False), person_age_at_death(person))
        self.assertEqual(
            "approximately age 75",
            person_death_age_text(person),
        )
        self.assertEqual(
            "0923 to 0998 (approximately age 75)",
            lifespan_text(person),
        )

    def test_age_calculation_crosses_bc_to_ad_without_year_zero(self):
        person = {
            "birth_year": -1,
            "birth_month": 3,
            "birth_day": 1,
            "death_year": 1,
            "death_month": 3,
            "death_day": 1,
        }

        self.assertEqual((1, True), person_age_at_death(person))


class BloodStatusInitializationTests(unittest.TestCase):
    def test_first_development_activation_randomizes_only_once(self):
        view = object.__new__(DevelopmentView)
        view.current_person = {
            "record_id": "person-1",
            "blood_status": BLOOD_STATUS_PUREBLOOD,
            "developmental_environment": "",
        }
        view.development_plan = {
            "schema": "Scattershot",
            "blood_status_initialized": False,
            "academic_years_advanced": 0,
            "school_started": False,
        }
        view.blood_status_value = FakeVariable(
            BLOOD_STATUS_PUREBLOOD
        )
        view.available_people = lambda: [view.current_person]
        view.update_blood_status_control = lambda: None
        view.parental_values = {
            "generosity": 5,
            "permissiveness": 5,
            "wealth": 5,
        }
        view.characteristics = {
            field_name: 1
            for field_name in CHARACTERISTIC_NAMES
        }
        view.characteristics["creativity"] = 5
        view.characteristics["equanimity"] = 5
        view.loading = False
        view.update_parental_controls = lambda: None
        view.update_initial_bonus_controls = lambda: None
        view.update_initial_values_completion = lambda: None

        with patch(
            "mage_maker.sections.development.page.randomized_blood_status",
            return_value=BLOOD_STATUS_HALFBLOOD,
        ) as random_status:
            first_activation = DevelopmentView.activate(view)
            second_activation = DevelopmentView.activate(view)

        self.assertTrue(first_activation)
        self.assertFalse(second_activation)
        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            view.current_person["blood_status"],
        )
        self.assertTrue(
            view.development_plan["blood_status_initialized"]
        )
        random_status.assert_called_once()

    def test_random_status_is_limited_by_genealogy(self):
        magical_parent = {
            "record_id": "magical-parent",
            "non_magical": False,
        }
        muggle_parent = {
            "record_id": "muggle-parent",
            "non_magical": True,
        }
        mixed_child = {
            "biological_mother_id": "magical-parent",
            "biological_father_id": "muggle-parent",
        }

        self.assertEqual(
            BLOOD_STATUS_HALFBLOOD,
            randomized_blood_status(
                mixed_child,
                [magical_parent, muggle_parent],
            ),
        )
        self.assertEqual(
            BLOOD_STATUS_PUREBLOOD,
            randomized_blood_status(
                {
                    "biological_mother_id": "magical-parent",
                    "biological_father_id": "magical-parent-2",
                },
                [
                    magical_parent,
                    {
                        "record_id": "magical-parent-2",
                        "non_magical": False,
                    },
                ],
            ),
        )
        self.assertEqual(
            BLOOD_STATUS_MUGGLEBORN,
            randomized_blood_status(
                {
                    "biological_mother_id": "muggle-parent",
                    "biological_father_id": "muggle-parent-2",
                },
                [
                    muggle_parent,
                    {
                        "record_id": "muggle-parent-2",
                        "non_magical": True,
                    },
                ],
            ),
        )

    def test_unknown_genealogy_randomizes_across_all_statuses(self):
        with patch(
            "mage_maker.sections.development.initial_values.random.choice",
            return_value=BLOOD_STATUS_HALFBLOOD,
        ) as random_choice:
            selected = randomized_blood_status({}, [])

        self.assertEqual(BLOOD_STATUS_HALFBLOOD, selected)
        random_choice.assert_called_once_with(BLOOD_STATUS_OPTIONS)

    def test_schema_twenty_nine_tracks_first_development_visit(self):
        database_data = {
            "_database": {
                "schema_version": 28,
                "database_version": "0.28.0",
            },
            "events": [],
            "organizations": [],
            "people": [
                {
                    "record_id": "not-started",
                    "development_plan": {
                        "schema": "Scattershot",
                    },
                },
                {
                    "record_id": "already-started",
                    "parental_values": {
                        "generosity": 5,
                        "permissiveness": 5,
                        "wealth": 5,
                    },
                    "development_plan": {
                        "schema": "Scattershot",
                    },
                },
            ],
        }

        self.assertTrue(
            JsonDatabase("unused.json").migrate_database(database_data)
        )
        self.assertEqual(29, database_data["_database"]["schema_version"])
        self.assertFalse(
            database_data["people"][0]["development_plan"][
                "blood_status_initialized"
            ]
        )
        self.assertTrue(
            database_data["people"][1]["development_plan"][
                "blood_status_initialized"
            ]
        )


class PeriodEventDisplayTests(unittest.TestCase):
    def test_founding_event_is_not_prefixed_by_a_duplicate_type(self):
        self.assertEqual(
            "43  ·  Founding of London",
            period_event_display_text(
                {
                    "date": "43",
                    "event_type": "founding",
                    "title": "Founding of London",
                }
            ),
        )


class EventEminenceTests(unittest.TestCase):
    def event_controller(self, database):
        return EventController(
            database,
            database.list_people,
            lambda: [],
            lambda: [],
        )

    def test_shared_event_adds_moves_and_removes_eminence(self):
        database = EventEminenceDatabase([developed_person()])
        controller = self.event_controller(database)
        created = controller.create_event(world_event())
        person = database.list_people()[0]
        adult_records = person["development_plan"]["adult_years"]

        self.assertEqual(1, len(adult_records[0]["eminence"]))
        self.assertEqual(
            event_eminence_record_id("event-1", "person-1"),
            adult_records[0]["eminence"][0]["record_id"],
        )
        self.assertEqual(
            DEVELOPMENT_SKILL_OPTIONS[0],
            adult_records[0]["eminence"][0]["skill"],
        )

        moved_event = deepcopy(created)
        moved_event["date"] = "1997"
        controller.update_event("event-1", moved_event)
        moved_person = database.list_people()[0]
        school_records = moved_person["development_plan"]["school_years"]
        adult_records = moved_person["development_plan"]["adult_years"]

        self.assertEqual(1, len(school_records[6]["eminence"]))
        self.assertEqual([], adult_records[0]["eminence"])

        moved_event["eminence_person_ids"] = []
        controller.update_event("event-1", moved_event)
        unawarded_person = database.list_people()[0]

        self.assertTrue(
            all(
                not record["eminence"]
                for record in unawarded_person["development_plan"][
                    "school_years"
                ]
            )
        )
        self.assertEqual(
            [],
            unawarded_person["development_plan"]["adult_years"][0][
                "eminence"
            ],
        )

    def test_future_event_award_appears_when_year_is_created(self):
        person = developed_person()
        person["development_plan"]["adult_years"] = []
        event = world_event()
        without_target = reconcile_person_event_eminence(
            person,
            [event],
        )

        self.assertEqual([], without_target["adult_years"])

        person["development_plan"]["adult_years"] = [
            {
                "adult_year": 1,
                "reading_characteristic": "",
                "reading_rolls": [],
                "books": [],
                "eminence": [],
                "jobs": [],
            }
        ]
        with_target = reconcile_person_event_eminence(person, [event])

        self.assertEqual(
            1,
            len(with_target["adult_years"][0]["eminence"]),
        )

    def test_organization_event_awards_and_removes_eminence(self):
        database = EventEminenceDatabase([developed_person()])
        controller = OrganizationController(database, lambda: [])
        organization_event = new_organization_event(
            "Defended London",
            1998,
            "Protected the city.",
            ["person-1"],
            ["person-1"],
        )
        organization = controller.create_organization(
            {
                "record_id": "organization-1",
                "name": "Order of Merlin",
                "organization_type": "Non-profit",
                "location_id": "",
                "parent_organization_id": "",
                "school_id": "",
                "has_shop": False,
                "shop_inventory": {},
                "extinct": False,
                "extinction_date": "",
                "overview": "",
                "notes": "",
                "events": [
                    {
                        "record_id": "organization-founding",
                        "event_type": "founding",
                        "title": "Founding",
                        "year": 1900,
                        "description": "",
                        "person_ids": [],
                    },
                    organization_event,
                ],
                "jobs": [],
            }
        )

        self.assertEqual(
            1,
            len(
                database.list_people()[0]["development_plan"][
                    "adult_years"
                ][0]["eminence"]
            ),
        )

        organization["events"][1]["eminence_person_ids"] = []
        controller.update_organization(
            "organization-1",
            organization,
        )

        self.assertEqual(
            [],
            database.list_people()[0]["development_plan"][
                "adult_years"
            ][0]["eminence"],
        )


if __name__ == "__main__":
    unittest.main()
