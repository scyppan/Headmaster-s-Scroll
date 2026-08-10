import inspect
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.sections.development.models import (
    ensure_adult_year_records,
    job_assignment_overlaps_year_range,
    new_job_record,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.organizations.controller import (
    OrganizationController,
    organization_context_label,
    organization_ids_in_scope,
)
from mage_maker.sections.organizations.page import OrganizationPage
from mage_maker.sections.profile.page import PersonForm
from mage_maker.shell.application import MageMakerApp
from mage_maker.shell.person_list import PeopleList
from mage_maker.ui.theme import LOCKED_BORDER


def organization(record_id, name, parent_id="", location_id=""):
    return {
        "record_id": record_id,
        "name": name,
        "organization_type": "Governmental",
        "location_id": location_id,
        "parent_organization_id": parent_id,
        "school_id": "",
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
            }
        ],
        "jobs": [],
    }


class OrganizationDatabase:
    def __init__(self, organizations=None):
        self.organizations = deepcopy(organizations or [])
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
        return (
            deepcopy(self.organizations)
            if collection_name == "organizations"
            else []
        )

    def read_record(self, collection_name, record_id):
        if collection_name != "organizations":
            return None

        return next(
            (
                deepcopy(record)
                for record in self.organizations
                if record["record_id"] == record_id
            ),
            None,
        )

    def create_record(self, collection_name, values):
        created = deepcopy(values)
        created["record_id"] = f"organization-{len(self.organizations) + 1}"
        self.organizations.append(created)
        return deepcopy(created)

    def list_people(self):
        return []

    def save(self):
        return None


class OrganizationNestingTests(unittest.TestCase):
    def setUp(self):
        self.organizations = [
            organization("org-0", "Org 0", location_id="london"),
            organization("org-1", "Org 1", "org-0", "london"),
            organization("org-2", "Org 2", "org-1", "london"),
            organization("org-3", "Org 3", "org-2", "london"),
            organization("other", "Other", location_id="paris"),
        ]

    def test_deep_organization_labels_use_only_the_root_context(self):
        self.assertEqual(
            "Org 3 (within Org 0)",
            organization_context_label("org-3", self.organizations),
        )

    def test_locked_scope_contains_only_the_selected_branch(self):
        self.assertEqual(
            {"org-1", "org-2", "org-3"},
            organization_ids_in_scope(self.organizations, "org-1"),
        )

    def test_new_child_inherits_its_parent_location(self):
        database = OrganizationDatabase(self.organizations[:1])
        controller = OrganizationController(
            database,
            lambda: [{"record_id": "london", "name": "London"}],
        )

        child = controller.create_default_organization("org-0")

        self.assertEqual("org-0", child["parent_organization_id"])
        self.assertEqual("london", child["location_id"])

    def test_tree_selection_cannot_discard_unsaved_changes(self):
        tree = Mock()
        tree.selection.return_value = ("org-2",)
        page = SimpleNamespace(
            suppress_tree_selection=False,
            organization_tree=tree,
            organization_lock_id="",
            current_organization_id="org-1",
            confirm_unsaved_organization_changes=Mock(return_value=False),
            select_organization_tree_item=Mock(),
            load_organization=Mock(),
            clear_form=Mock(),
            update_organization_lock_controls=Mock(),
        )

        OrganizationPage.organization_selected(page)

        page.select_organization_tree_item.assert_called_once_with("org-1")
        page.load_organization.assert_not_called()

    def test_leaving_the_organizations_section_also_checks_unsaved_changes(self):
        source = inspect.getsource(MageMakerApp.show_page)

        self.assertIn('active_page_name == "organizations"', source)
        self.assertIn("confirm_unsaved_organization_changes", source)

    def test_organization_hierarchy_exposes_branch_lock_controls(self):
        workspace_source = inspect.getsource(OrganizationPage.build_workspace)
        lock_source = inspect.getsource(
            OrganizationPage.update_organization_lock_controls
        )

        self.assertIn("ttk.Treeview", workspace_source)
        self.assertIn("organization_scope_button", workspace_source)
        self.assertIn("LOCKED_RED", lock_source)

    def test_organization_branch_lock_is_remembered(self):
        database = SimpleNamespace(
            data={"_application_settings": {}},
            dirty=False,
        )
        application = SimpleNamespace(database=database)

        self.assertTrue(
            MageMakerApp.remember_organization_lock(
                application,
                "org-1",
            )
        )
        self.assertEqual(
            "org-1",
            database.data["_application_settings"][
                "organization_lock_id"
            ],
        )
        self.assertTrue(database.dirty)


class UnfinishedMageTests(unittest.TestCase):
    def test_schema_twenty_seven_adds_the_unfinished_flag(self):
        database_data = {
            "_database": {
                "schema_version": 26,
                "database_version": "0.26.0",
            },
            "people": [{"record_id": "person-1"}],
            "organizations": [],
        }

        self.assertTrue(
            JsonDatabase("unused.json").migrate_database(database_data)
        )
        self.assertEqual(29, database_data["_database"]["schema_version"])
        self.assertFalse(database_data["people"][0]["unfinished"])

    def test_unfinished_mage_uses_the_red_list_border(self):
        label = Mock()
        people_list = SimpleNamespace(
            labels_by_id={"person-1": "Person"},
            initial_values_complete_by_id={"person-1": True},
            unfinished_by_id={"person-1": False},
            row_labels_by_id={"person-1": label},
        )

        PeopleList.set_initial_values_status(
            people_list,
            "person-1",
            True,
            True,
        )

        self.assertEqual(
            LOCKED_BORDER,
            label.configure.call_args.kwargs["highlightbackground"],
        )
        self.assertEqual(
            2,
            label.configure.call_args.kwargs["highlightthickness"],
        )

    def test_unfinished_control_is_in_classifications_and_is_saved(self):
        panel_source = inspect.getsource(DevelopmentView.build_plan_panel)
        values_source = inspect.getsource(PersonForm.current_profile_values)

        self.assertIn(
            ("unfinished", "Mark as unfinished"),
            PersonForm.status_fields,
        )
        self.assertNotIn('text="Mark as unfinished"', panel_source)
        self.assertIn(
            '"unfinished": self.variables["unfinished"].get()',
            values_source,
        )


class AdultJobDisplayTests(unittest.TestCase):
    def job(self, end_year=None):
        return new_job_record(
            "ministry",
            "Ministry for Magic",
            "Auror",
            {"galleons": 40, "sickles": 8, "knuts": 12},
            1998,
            8,
            1,
            end_year,
        )

    def test_job_overlap_handles_the_combined_first_adult_page(self):
        completed_job = self.job(1999)

        self.assertTrue(
            job_assignment_overlaps_year_range(
                completed_job,
                1998,
                1999,
            )
        )
        self.assertFalse(
            job_assignment_overlaps_year_range(
                completed_job,
                2000,
                2000,
            )
        )

    def test_ongoing_job_appears_on_later_adult_years(self):
        records = ensure_adult_year_records([], 2)
        records[0]["jobs"] = [self.job()]
        view = SimpleNamespace(
            birth_year=1980,
            birth_month=7,
            birth_day=31,
            adult_year_records=records,
        )

        visible_jobs = DevelopmentView.active_job_assignments_for_adult_year(
            view,
            2,
        )

        self.assertEqual(1, len(visible_jobs))
        self.assertEqual("Auror", visible_jobs[0]["title"])

    def test_editing_a_carried_job_updates_its_original_record(self):
        records = ensure_adult_year_records([], 2)
        original_job = self.job()
        records[0]["jobs"] = [original_job]
        edited_job = {**original_job, "end_year": 2001}
        view = SimpleNamespace(
            adult_year_records=records,
            development_plan={},
            adult_year_record=lambda: records[1],
            render_adult_year_record=Mock(),
            notify_change=Mock(),
        )

        DevelopmentView.save_job_record(view, edited_job)

        self.assertEqual(
            2001,
            view.adult_year_records[0]["jobs"][0]["end_year"],
        )
        self.assertEqual([], view.adult_year_records[1]["jobs"])

    def test_adult_job_lines_do_not_display_salary(self):
        source = inspect.getsource(DevelopmentView.render_adult_year_record)

        self.assertNotIn("format_monthly_salary", source)
        self.assertIn("organization_name", source)
        self.assertIn("start_date", source)


class DevelopmentNavigationTests(unittest.TestCase):
    def test_initial_and_latest_navigation_visit_existing_pages(self):
        view = SimpleNamespace(
            active_development_page_index=4,
            development_page_count=lambda: 8,
            update_school_progress_controls=Mock(),
        )

        DevelopmentView.show_initial_development_page(view)
        self.assertEqual(0, view.active_development_page_index)

        DevelopmentView.show_latest_development_page(view)
        self.assertEqual(7, view.active_development_page_index)
        self.assertEqual(2, view.update_school_progress_controls.call_count)

    def test_navigation_bar_has_initial_and_latest_actions(self):
        source = inspect.getsource(DevelopmentView.build_plan_panel)

        self.assertIn('text="Initial"', source)
        self.assertIn('text="Latest"', source)


if __name__ == "__main__":
    unittest.main()
