import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.sections.development.organization_dialogs import (
    OrganizationLocationSelectionDialog,
)
from mage_maker.sections.events.dialog import EventPersonPickerDialog
from mage_maker.sections.organizations.controller import (
    OrganizationController,
)
from mage_maker.sections.organizations.page import (
    OrganizationPage,
    OrganizationSchoolSelectionDialog,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeText:
    def __init__(self, value=""):
        self.value = value

    def get(self, start, end):
        return self.value


class FakeButton:
    def __init__(self):
        self.enabled = None

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class FakeListbox:
    def __init__(self):
        self.items = []
        self.selected = []

    def delete(self, start, end):
        self.items = []
        self.selected = []

    def insert(self, index, value):
        self.items.append(value)

    def itemconfigure(self, index, **values):
        return None

    def selection_set(self, index):
        self.selected = [int(index)]

    def see(self, index):
        return None


class FakeEventController:
    def __init__(self, options):
        self.options = deepcopy(options)

    def people_options(self):
        return deepcopy(self.options)


class FakeOrganizationDatabase:
    def __init__(self):
        self.organizations = []
        self.save_count = 0
        self.data = {"_application_settings": {}}

    def list_records(self, collection_name):
        if collection_name == "organizations":
            return deepcopy(self.organizations)

        return []

    def read_record(self, collection_name, record_id):
        if collection_name != "organizations":
            return None

        return next(
            (
                deepcopy(record)
                for record in self.organizations
                if record.get("record_id") == record_id
            ),
            None,
        )

    def create_record(self, collection_name, values):
        created = deepcopy(values)
        created["record_id"] = f"organization-{len(self.organizations) + 1}"
        self.organizations.append(created)
        return deepcopy(created)

    def update_record(self, collection_name, record_id, values):
        for index, record in enumerate(self.organizations):
            if record.get("record_id") != record_id:
                continue

            updated = deepcopy(values)
            updated["record_id"] = record_id
            self.organizations[index] = updated
            return deepcopy(updated)

        raise KeyError(record_id)

    def list_people(self):
        return []

    def save(self):
        self.save_count += 1


def location_records():
    return [
        {
            "record_id": "british-isles",
            "name": "British Isles",
            "parent_location_id": "",
        },
        {
            "record_id": "england",
            "name": "England",
            "parent_location_id": "british-isles",
        },
        {
            "record_id": "london",
            "name": "London",
            "parent_location_id": "england",
        },
    ]


def founding_event(year=1707, person_ids=None):
    return {
        "record_id": "organization-founding",
        "event_type": "founding",
        "title": "Founding",
        "year": year,
        "description": "",
        "person_ids": list(person_ids or []),
    }


class OrganizationConsistencyRepairTests(unittest.TestCase):
    def test_organization_location_display_uses_compact_context(self):
        controller = OrganizationController(
            FakeOrganizationDatabase(),
            location_records,
        )

        self.assertEqual(
            "London, England",
            controller.location_label("london"),
        )

    def test_organization_search_keeps_full_location_path(self):
        database = FakeOrganizationDatabase()
        controller = OrganizationController(
            database,
            location_records,
        )
        controller.create_organization(
            {
                "name": "London Office",
                "organization_type": "Governmental",
                "location_id": "london",
                "events": [founding_event()],
            }
        )

        matches = controller.search_organizations(
            "british london",
            location_id="british-isles",
        )

        self.assertEqual(
            ["London Office"],
            [organization["name"] for organization in matches],
        )

    def test_location_dialog_selection_uses_compact_context(self):
        dialog = SimpleNamespace(
            locations=location_records(),
            selected_location_id="london",
            selection_value=FakeVariable(),
            use_button=FakeButton(),
        )

        OrganizationLocationSelectionDialog.location_selected(
            dialog,
            "london",
        )

        self.assertEqual(
            "London, England",
            dialog.selection_value.get(),
        )
        self.assertTrue(dialog.use_button.enabled)

    def test_school_picker_rows_have_visible_spacing(self):
        dialog = SimpleNamespace(
            schools=[
                {
                    "record_id": "hogwarts",
                    "name": "Hogwarts",
                    "location": "Scottish Highlands",
                    "curriculum": [],
                }
            ],
            visible_schools=[],
            selected_school_id="",
            search_value=FakeVariable(),
            results_value=FakeVariable(),
            school_list=FakeListbox(),
            use_button=FakeButton(),
        )
        dialog.school_search_text = (
            OrganizationSchoolSelectionDialog.school_search_text.__get__(
                dialog
            )
        )
        dialog.school_sort_key = (
            OrganizationSchoolSelectionDialog.school_sort_key.__get__(
                dialog
            )
        )

        OrganizationSchoolSelectionDialog.refresh_results(dialog)

        self.assertEqual(
            ["Hogwarts  ·  Scottish Highlands"],
            dialog.school_list.items,
        )
        self.assertNotIn("\n", dialog.school_list.items[0])

    def test_event_person_picker_rows_have_visible_spacing(self):
        picker = SimpleNamespace()
        picker.option_person = EventPersonPickerDialog.option_person.__get__(
            picker
        )
        picker.integer_value = EventPersonPickerDialog.integer_value.__get__(
            picker
        )
        text = EventPersonPickerDialog.person_display_text(
            picker,
            {
                "value": "harry",
                "label": "Harry Potter",
                "group_name": "Unassigned",
                "person": {"birth_year": 1980},
            },
        )

        self.assertEqual(
            "Harry Potter  ·  Born 1980 · Unassigned",
            text,
        )
        self.assertNotIn("\n", text)

    def test_one_event_person_displays_the_person_name(self):
        page = SimpleNamespace(
            event_list=FakeListbox(),
            event_controller=FakeEventController(
                [
                    {
                        "value": "harry",
                        "label": "Harry Potter",
                    },
                    {
                        "value": "ginny",
                        "label": "Ginny Weasley",
                    },
                ]
            ),
            organization_events=[
                founding_event(person_ids=["harry"]),
                {
                    **founding_event(1710, ["harry", "ginny"]),
                    "record_id": "second-event",
                    "event_type": "other",
                    "title": "Expansion",
                },
            ],
        )

        OrganizationPage.refresh_event_list(page)

        self.assertEqual(
            "1707 — Founding · Harry Potter",
            page.event_list.items[0],
        )
        self.assertEqual(
            "1710 — Expansion · 2 people",
            page.event_list.items[1],
        )

    def test_cancelled_school_selection_clears_link_checkbox(self):
        page = SimpleNamespace(
            selected_school_id="",
            link_school_value=FakeVariable(True),
            refresh_school_link=Mock(),
        )

        OrganizationPage.school_selection_cancelled(page)

        self.assertFalse(page.link_school_value.get())
        page.refresh_school_link.assert_called_once_with("")

    def test_save_button_creates_an_unsaved_organization(self):
        database = FakeOrganizationDatabase()
        controller = OrganizationController(
            database,
            location_records,
        )
        page = SimpleNamespace(
            current_organization_id=None,
            controller=controller,
            link_school_value=FakeVariable(False),
            selected_school_id="",
            name_value=FakeVariable("Ministry for Magic"),
            type_value=FakeVariable("Governmental"),
            selected_location_id="london",
            selected_parent_organization_id="",
            overview_control=SimpleNamespace(
                text=FakeText("The British magical government.")
            ),
            notes_control=SimpleNamespace(text=FakeText("")),
            organization_events=[founding_event()],
            organization_jobs=[],
            refresh=Mock(),
            status_command=Mock(),
            refresh_school_link=Mock(),
        )

        saved = OrganizationPage.save_organization(page)

        self.assertTrue(saved)
        self.assertEqual(1, database.save_count)
        self.assertEqual(
            "Ministry for Magic",
            database.organizations[0]["name"],
        )
        page.refresh.assert_called_once_with(
            "organization-1",
            force_load=True,
        )

    def test_save_clears_an_empty_school_link_instead_of_blocking(self):
        database = FakeOrganizationDatabase()
        controller = OrganizationController(
            database,
            location_records,
        )
        link_school_value = FakeVariable(True)
        page = SimpleNamespace(
            current_organization_id=None,
            controller=controller,
            link_school_value=link_school_value,
            selected_school_id="",
            name_value=FakeVariable("Independent School"),
            type_value=FakeVariable("School"),
            selected_location_id="london",
            selected_parent_organization_id="",
            overview_control=SimpleNamespace(text=FakeText("")),
            notes_control=SimpleNamespace(text=FakeText("")),
            organization_events=[founding_event()],
            organization_jobs=[],
            refresh=Mock(),
            status_command=Mock(),
        )
        page.refresh_school_link = (
            OrganizationPage.refresh_school_link.__get__(page)
        )
        page.school_value = FakeVariable()
        page.choose_school_button = FakeButton()
        page.name_field = SimpleNamespace(
            control=FakeButton(),
        )
        page.type_picker = SimpleNamespace(configure=Mock())
        controller.school_by_id = Mock(return_value=None)

        saved = OrganizationPage.save_organization(page)

        self.assertTrue(saved)
        self.assertFalse(link_school_value.get())
        self.assertEqual("", database.organizations[0]["school_id"])


if __name__ == "__main__":
    unittest.main()
