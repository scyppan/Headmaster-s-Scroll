import unittest
import shutil
import tempfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.book_dialog import (
    BookSelectionDialog,
)
from mage_maker.sections.development.models import (
    new_job_record,
    normalize_job_record,
    require_job_position_available,
)
from mage_maker.sections.development.school_years import (
    random_adult_year_record,
)
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    new_organization_job,
    normalize_organization_record,
    organization_path,
)


class FakeVariable:
    def __init__(self, value=None):
        self.value = value

    def get(self):
        return self.value


class FixedRandomizer:
    def __init__(self, rolls):
        self.rolls = list(rolls)

    def randint(self, minimum, maximum):
        return self.rolls.pop(0)

    def random(self):
        return 0.5

    def choice(self, values):
        return values[0]


class MemoryDatabase:
    def __init__(self, organizations=None, people=None):
        self.organizations = deepcopy(organizations or [])
        self.people = deepcopy(people or [])
        self.data = {
            "_application_settings": {
                "database_date": {
                    "year": 2000,
                    "month": 7,
                    "day": 31,
                }
            }
        }

    def list_records(self, collection_name):
        if collection_name != "organizations":
            return []

        return deepcopy(self.organizations)

    def list_people(self):
        return deepcopy(self.people)


def founding_event(year):
    return {
        "record_id": "organization-founding",
        "event_type": "founding",
        "title": "Founding",
        "year": year,
        "description": "",
    }


def organization(
    record_id,
    name,
    parent_organization_id="",
    jobs=None,
):
    return normalize_organization_record(
        {
            "record_id": record_id,
            "name": name,
            "organization_type": "Governmental",
            "location_id": "",
            "parent_organization_id": parent_organization_id,
            "overview": "",
            "notes": "",
            "events": [founding_event(1700)],
            "jobs": jobs or [],
        }
    )


def characteristic_values(intellect, willpower):
    values = {
        "creativity": 1,
        "equanimity": 1,
        "charisma": 1,
        "attractiveness": 1,
        "strength": 1,
        "agility": 1,
        "intellect": intellect,
        "willpower": willpower,
        "fortitude": 1,
    }
    remaining_points = (
        8
        - (intellect - 1)
        - (willpower - 1)
    )
    creativity_points = min(4, remaining_points)
    values["creativity"] += creativity_points
    values["equanimity"] += (
        remaining_points - creativity_points
    )
    return values


def book_records(count):
    return [
        {
            "record_id": f"book-{index}",
            "name": f"Book {index}",
            "author": f"Author {index}",
        }
        for index in range(1, count + 1)
    ]


class OrganizationHierarchyTests(unittest.TestCase):
    def test_nested_organization_path_lists_every_level(self):
        organizations = [
            organization("ministry", "Ministry for Magic"),
            organization(
                "aurors",
                "Auror's Office",
                "ministry",
            ),
        ]

        self.assertEqual(
            "Ministry for Magic / Auror's Office",
            organization_path("aurors", organizations),
        )

    def test_parent_options_exclude_self_and_descendants(self):
        organizations = [
            organization("ministry", "Ministry for Magic"),
            organization(
                "aurors",
                "Auror's Office",
                "ministry",
            ),
            organization("hospital", "St Mungo's"),
        ]
        controller = OrganizationController(
            MemoryDatabase(organizations),
            lambda: [],
        )

        options = controller.parent_options("ministry")
        option_ids = {
            option["record_id"]
            for option in options
        }

        self.assertNotIn("ministry", option_ids)
        self.assertNotIn("aurors", option_ids)
        self.assertIn("hospital", option_ids)

    def test_validation_rejects_nesting_cycle(self):
        organizations = [
            organization("ministry", "Ministry for Magic"),
            organization(
                "aurors",
                "Auror's Office",
                "ministry",
            ),
        ]
        controller = OrganizationController(
            MemoryDatabase(organizations),
            lambda: [],
        )
        updated_ministry = {
            **organizations[0],
            "parent_organization_id": "aurors",
        }

        with self.assertRaisesRegex(
            ValueError,
            "descendants",
        ):
            controller.validate_organization(
                updated_ministry,
                "ministry",
            )


class OrganizationJobAvailabilityTests(unittest.TestCase):
    def setUp(self):
        self.position = new_organization_job(
            "Auror",
            "120 Galleons",
            1980,
        )

    def assignment(
        self,
        start_year,
        end_year=None,
        start_month=None,
        start_day=None,
        end_month=None,
        end_day=None,
    ):
        return new_job_record(
            "aurors",
            "Auror's Office",
            self.position["title"],
            self.position["salary"],
            start_year,
            start_month,
            start_day,
            end_year,
            end_month,
            end_day,
            self.position["record_id"],
        )

    def test_assignment_can_have_no_end_date(self):
        assignment = normalize_job_record(
            self.assignment(1990)
        )

        self.assertIsNone(assignment["end_year"])
        self.assertIsNone(assignment["end_month"])
        self.assertIsNone(assignment["end_day"])

    def test_assignment_cannot_begin_before_position_opens(self):
        with self.assertRaisesRegex(
            ValueError,
            "does not open until 1980",
        ):
            require_job_position_available(
                self.position,
                self.assignment(1979),
                [],
            )

    def test_ongoing_assignment_keeps_position_closed(self):
        existing_assignment = self.assignment(1990)

        with self.assertRaisesRegex(
            ValueError,
            "not open",
        ):
            require_job_position_available(
                self.position,
                self.assignment(1995),
                [existing_assignment],
            )

    def test_position_reopens_after_assignment_ends(self):
        existing_assignment = self.assignment(
            1990,
            1995,
        )
        new_assignment = self.assignment(1996)

        self.assertEqual(
            new_assignment,
            require_job_position_available(
                self.position,
                new_assignment,
                [existing_assignment],
            ),
        )

    def test_overlapping_dated_assignments_are_rejected(self):
        existing_assignment = self.assignment(
            1990,
            1995,
        )

        with self.assertRaisesRegex(
            ValueError,
            "not open",
        ):
            require_job_position_available(
                self.position,
                self.assignment(1994, 1998),
                [existing_assignment],
            )

    def test_status_uses_database_date_and_assignment_end(self):
        ongoing_assignment = self.assignment(1990)
        person = {
            "record_id": "person-1",
            "development_plan": {
                "adult_years": [
                    {
                        "jobs": [ongoing_assignment],
                    }
                ]
            },
        }
        controller = OrganizationController(
            MemoryDatabase(
                [organization(
                    "aurors",
                    "Auror's Office",
                    jobs=[self.position],
                )],
                [person],
            ),
            lambda: [],
        )

        self.assertEqual(
            "Filled",
            controller.organization_job_status(self.position),
        )

        person["development_plan"]["adult_years"][0]["jobs"][0][
            "end_year"
        ] = 1999
        controller = OrganizationController(
            MemoryDatabase(
                [organization(
                    "aurors",
                    "Auror's Office",
                    jobs=[self.position],
                )],
                [person],
            ),
            lambda: [],
        )

        self.assertEqual(
            "Open",
            controller.organization_job_status(self.position),
        )


class AdultBookLimitTests(unittest.TestCase):
    def test_roll_of_twenty_three_selects_three_books(self):
        record = random_adult_year_record(
            1,
            {"schema": "Scattershot"},
            FixedRandomizer([10, 7, 6]),
            characteristic_values(3, 2),
            [],
            book_records(4),
            [],
            [],
        )

        self.assertEqual(23, record["reading_total"])
        self.assertEqual(3, record["book_limit"])
        self.assertEqual(3, len(record["books"]))

    def test_adult_book_dialog_preserves_three_selections(self):
        dialog = type(
            "BookDialogFixture",
            (),
            {},
        )()
        dialog.selected_books = book_records(3)
        dialog.required_book_count = 3
        dialog.save_command = Mock()
        dialog.destroy = Mock()

        BookSelectionDialog.save_books(dialog)

        saved_books = dialog.save_command.call_args.args[0]
        self.assertEqual(3, len(saved_books))
        dialog.destroy.assert_called_once_with()


class SchemaTwentyThreeTests(unittest.TestCase):
    def test_legacy_assignment_creates_and_links_organization_job(self):
        database_data = {
            "_database": {
                "schema_version": 22,
                "database_version": "0.22.0",
            },
            "organizations": [
                {
                    "record_id": "aurors",
                    "name": "Auror's Office",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "overview": "",
                    "notes": "",
                    "events": [founding_event(1700)],
                }
            ],
            "people": [
                {
                    "record_id": "person-1",
                    "development_plan": {
                        "schema": "Scattershot",
                        "school_started": True,
                        "academic_years_advanced": 7,
                        "school_years": [],
                        "adult_years": [
                            {
                                "adult_year": 1,
                                "reading_characteristic": "",
                                "reading_rolls": [],
                                "books": [],
                                "eminence": [],
                                "jobs": [
                                    {
                                        "record_id": "assignment-1",
                                        "organization_id": "aurors",
                                        "organization_name": (
                                            "Auror's Office"
                                        ),
                                        "title": "Auror",
                                        "salary": "120 Galleons",
                                        "start_year": 1990,
                                        "start_month": None,
                                        "start_day": None,
                                    }
                                ],
                            }
                        ],
                    },
                }
            ],
        }
        database = JsonDatabase("unused.json")

        self.assertTrue(database.migrate_database(database_data))
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        organization_job = database_data[
            "organizations"
        ][0]["jobs"][0]
        assignment = database_data["people"][0][
            "development_plan"
        ]["adult_years"][0]["jobs"][0]
        self.assertEqual(
            organization_job["record_id"],
            assignment["organization_job_id"],
        )
        self.assertIsNone(assignment["end_year"])

    def test_nested_job_assignment_survives_full_database_save(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            database_path = (
                Path(temporary_directory) / "mage_maker.json"
            )
            shutil.copy2(
                Path("data") / "mage_maker.json",
                database_path,
            )
            database = JsonDatabase(database_path)
            database.load()
            controller = OrganizationController(
                database,
                lambda: [],
            )
            ministry = controller.create_organization(
                {
                    "name": "Test Ministry for Magic",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "parent_organization_id": "",
                    "overview": "",
                    "notes": "",
                    "events": [founding_event(800)],
                    "jobs": [],
                }
            )
            auror_job = new_organization_job(
                "Auror",
                "120 Galleons",
                850,
            )
            auror_office = controller.create_organization(
                {
                    "name": "Test Auror's Office",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "parent_organization_id": ministry[
                        "record_id"
                    ],
                    "overview": "",
                    "notes": "",
                    "events": [founding_event(825)],
                    "jobs": [auror_job],
                }
            )
            person = database.list_people()[0]
            plan = deepcopy(person["development_plan"])
            plan["school_started"] = True
            plan["academic_years_advanced"] = 7
            plan["adult_years"] = [
                {
                    "adult_year": 1,
                    "reading_characteristic": "",
                    "reading_rolls": [],
                    "books": [],
                    "eminence": [],
                    "jobs": [
                        new_job_record(
                            auror_office["record_id"],
                            auror_office["name"],
                            auror_job["title"],
                            auror_job["salary"],
                            900,
                            organization_job_id=(
                                auror_job["record_id"]
                            ),
                        )
                    ],
                }
            ]
            database.update_person(
                person["record_id"],
                {"development_plan": plan},
            )
            database.save()
            reloaded = JsonDatabase(database_path)
            reloaded.load()
            saved_auror_office = next(
                organization_record
                for organization_record in reloaded.data[
                    "organizations"
                ]
                if organization_record["record_id"]
                == auror_office["record_id"]
            )
            saved_assignment = reloaded.data["people"][0][
                "development_plan"
            ]["adult_years"][0]["jobs"][0]

            self.assertEqual(
                ministry["record_id"],
                saved_auror_office["parent_organization_id"],
            )
            self.assertEqual(
                auror_job["record_id"],
                saved_assignment["organization_job_id"],
            )
            self.assertIsNone(saved_assignment["end_year"])


if __name__ == "__main__":
    unittest.main()
