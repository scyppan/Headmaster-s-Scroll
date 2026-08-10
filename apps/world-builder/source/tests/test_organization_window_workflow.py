import inspect
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.core.wizarding_currency import (
    format_monthly_salary,
    normalize_monthly_salary,
)
from mage_maker.sections.development.models import new_job_record
from mage_maker.sections.development.organization_dialogs import (
    QuickOrganizationDialog,
)
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    new_organization_job,
)
from mage_maker.sections.organizations.page import OrganizationPage


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeButton:
    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class OrganizationDatabase:
    def __init__(self):
        self.organizations = []
        self.people = []
        self.save_count = 0
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
        if collection_name == "organizations":
            return deepcopy(self.organizations)

        return []

    def read_record(self, collection_name, record_id):
        if collection_name != "organizations":
            return None

        return next(
            (
                deepcopy(organization)
                for organization in self.organizations
                if organization.get("record_id") == record_id
            ),
            None,
        )

    def create_record(self, collection_name, values):
        created = deepcopy(values)
        created["record_id"] = f"organization-{len(self.organizations) + 1}"
        self.organizations.append(created)
        return deepcopy(created)

    def list_people(self):
        return deepcopy(self.people)

    def save(self):
        self.save_count += 1


class MonthlySalaryTests(unittest.TestCase):
    def test_legacy_salary_becomes_three_part_monthly_currency(self):
        salary = normalize_monthly_salary("120 Galleons")

        self.assertEqual(
            {
                "galleons": 120,
                "sickles": 0,
                "knuts": 0,
                "period": "month",
            },
            salary,
        )
        self.assertEqual(
            "120 Galleons, 0 Sickles, 0 Knuts per month",
            format_monthly_salary(salary),
        )

    def test_currency_components_reject_values_above_their_maximums(self):
        with self.assertRaisesRegex(ValueError, "Sickles"):
            normalize_monthly_salary(
                {
                    "galleons": 0,
                    "sickles": 17,
                    "knuts": 0,
                }
            )

        self.assertEqual(
            {
                "galleons": 4,
                "sickles": 16,
                "knuts": 28,
                "period": "month",
            },
            normalize_monthly_salary(
                {
                    "galleons": 4,
                    "sickles": 16,
                    "knuts": 28,
                }
            ),
        )

        with self.assertRaisesRegex(ValueError, "Knuts"):
            normalize_monthly_salary(
                {
                    "galleons": 0,
                    "sickles": 16,
                    "knuts": 29,
                }
            )

    def test_organization_and_person_jobs_share_monthly_salary(self):
        organization_job = new_organization_job(
            "Auror",
            {
                "galleons": 40,
                "sickles": 8,
                "knuts": 12,
            },
            1980,
        )
        assignment = new_job_record(
            "aurors",
            "Auror's Office",
            organization_job["title"],
            organization_job["salary"],
            1990,
            organization_job_id=organization_job["record_id"],
        )

        self.assertEqual(
            organization_job["salary"],
            assignment["salary"],
        )


class OrganizationCreationTests(unittest.TestCase):
    def setUp(self):
        self.database = OrganizationDatabase()
        self.controller = OrganizationController(
            self.database,
            lambda: [],
        )

    def test_new_organization_is_saved_without_a_job(self):
        first = self.controller.create_default_organization()
        second = self.controller.create_default_organization()

        self.assertEqual("New Organization", first["name"])
        self.assertEqual("New Organization 2", second["name"])
        self.assertEqual([], first["jobs"])
        self.assertEqual(2000, first["events"][0]["year"])
        self.assertEqual(2, self.database.save_count)

    def test_main_new_action_does_not_open_quick_create_dialog(self):
        source = inspect.getsource(
            OrganizationPage.create_organization
        )

        self.assertIn("create_default_organization", source)
        self.assertNotIn("QuickOrganizationDialog", source)

    def test_quick_create_can_make_an_organization_without_jobs(self):
        create_command = Mock(
            return_value={
                "record_id": "organization-1",
                "name": "The Daily Prophet",
            }
        )
        save_command = Mock()
        dialog = SimpleNamespace(
            selected_location_id="london",
            founding_year_value=FakeVariable("1881"),
            job_title_value=FakeVariable(""),
            job_salary_galleons_value=FakeVariable(""),
            job_salary_sickles_value=FakeVariable(""),
            job_salary_knuts_value=FakeVariable(""),
            job_opened_year_value=FakeVariable(""),
            name_value=FakeVariable("The Daily Prophet"),
            type_value=FakeVariable("Media"),
            create_command=create_command,
            save_command=save_command,
            destroy=Mock(),
        )

        QuickOrganizationDialog.create_organization(dialog)

        self.assertEqual([], create_command.call_args.args[0]["jobs"])
        save_command.assert_called_once_with(
            create_command.return_value
        )


class OrganizationInterfaceTests(unittest.TestCase):
    def test_sidebar_uses_real_two_line_name_and_location_rows(self):
        workspace_source = inspect.getsource(
            OrganizationPage.build_workspace
        )
        insert_source = inspect.getsource(
            OrganizationPage.insert_organization_record
        )

        self.assertIn("self.organization_tree = ttk.Treeview", workspace_source)
        self.assertIn(
            "self.controller.location_label",
            insert_source,
        )
        self.assertIn(
            'text=f"{name}\\n{location_label}"',
            insert_source,
        )

    def test_toolbar_order_matches_other_editors(self):
        source = inspect.getsource(OrganizationPage.build_toolbar)
        button_positions = [
            source.index(f'text="{label}"')
            for label in ("New", "Delete", "Revert", "Save")
        ]

        self.assertEqual(sorted(button_positions), button_positions)
        self.assertNotIn("Save organization", source)

    def test_jobs_have_their_own_organization_page(self):
        editor_source = inspect.getsource(OrganizationPage.build_editor)
        details_source = inspect.getsource(
            OrganizationPage.build_details_editor
        )
        job_source = inspect.getsource(OrganizationPage.build_jobs)

        self.assertIn("self.jobs_page", editor_source)
        self.assertIn("self.build_jobs(self.jobs_page)", editor_source)
        self.assertNotIn("self.build_jobs", details_source)
        self.assertIn('text="Jobs"', job_source)
        self.assertNotIn("optional", job_source.casefold())

    def test_revert_and_save_enable_only_after_a_change(self):
        page = SimpleNamespace(
            delete_button=FakeButton(),
            revert_button=FakeButton(),
            save_button=FakeButton(),
            form_updates_paused=False,
            form_dirty=False,
            current_organization_id="organization-1",
            status_command=Mock(),
        )

        OrganizationPage.set_editor_state(page, True, False)

        self.assertTrue(page.delete_button.enabled)
        self.assertFalse(page.revert_button.enabled)
        self.assertFalse(page.save_button.enabled)

        OrganizationPage.mark_form_dirty(page)

        self.assertTrue(page.form_dirty)
        self.assertTrue(page.revert_button.enabled)
        self.assertTrue(page.save_button.enabled)


class SalaryMigrationTests(unittest.TestCase):
    def test_schema_twenty_five_salary_strings_migrate_to_schema_twenty_six(self):
        database_data = {
            "_database": {
                "schema_version": 25,
                "database_version": "0.25.0",
            },
            "organizations": [
                {
                    "record_id": "aurors",
                    "name": "Auror's Office",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "parent_organization_id": "",
                    "school_id": "",
                    "overview": "",
                    "notes": "",
                    "events": [
                        {
                            "record_id": "organization-founding",
                            "event_type": "founding",
                            "title": "Founding",
                            "year": 1700,
                            "description": "",
                            "person_ids": [],
                        }
                    ],
                    "jobs": [
                        {
                            "record_id": "auror-position",
                            "title": "Auror",
                            "salary": "40 Galleons monthly",
                            "opened_year": 1800,
                        }
                    ],
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
                                "books": [],
                                "eminence": [],
                                "jobs": [
                                    {
                                        "record_id": "assignment-1",
                                        "organization_id": "aurors",
                                        "organization_name": "Auror's Office",
                                        "organization_job_id": "auror-position",
                                        "title": "Auror",
                                        "salary": "40 Galleons monthly",
                                        "start_year": 1990,
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
        self.assertEqual(
            {
                "galleons": 40,
                "sickles": 0,
                "knuts": 0,
                "period": "month",
            },
            database_data["organizations"][0]["jobs"][0][
                "salary"
            ],
        )
        self.assertEqual(
            database_data["organizations"][0]["jobs"][0][
                "salary"
            ],
            database_data["people"][0]["development_plan"][
                "adult_years"
            ][0]["jobs"][0]["salary"],
        )


if __name__ == "__main__":
    unittest.main()
