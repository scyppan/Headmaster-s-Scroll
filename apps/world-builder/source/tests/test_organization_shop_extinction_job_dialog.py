import inspect
import unittest
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock

from mage_maker.core.database import JsonDatabase
from mage_maker.core.wizarding_currency import (
    currency_component_input_is_valid,
)
from mage_maker.sections.development.organization_dialogs import (
    OrganizationSelectionDialog,
    QuickOrganizationDialog,
)
from mage_maker.sections.organizations.controller import (
    SHOP_STOCK_CATEGORIES,
    OrganizationController,
    normalize_organization_extinction_date,
    normalize_organization_record,
    normalize_shop_inventory,
)
from mage_maker.sections.organizations.job_dialog import (
    OrganizationJobDialog,
)
from mage_maker.sections.organizations.page import OrganizationPage


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
        if collection_name == "organizations":
            return deepcopy(self.organizations)

        return []

    def list_people(self):
        return []

    def save(self):
        return None


class OrganizationShopTests(unittest.TestCase):
    def test_shop_inventory_reserves_the_four_requested_categories(self):
        self.assertEqual(
            (
                ("always_in_stock", "Always in stock"),
                ("regularly_in_stock", "Regularly in stock"),
                ("sometimes_in_stock", "Sometimes in stock"),
                ("rarely_in_stock", "Rarely in stock"),
            ),
            SHOP_STOCK_CATEGORIES,
        )
        self.assertEqual(
            {
                "always_in_stock": [],
                "regularly_in_stock": [],
                "sometimes_in_stock": [],
                "rarely_in_stock": [],
            },
            normalize_shop_inventory({}),
        )
        self.assertEqual(
            ["wand-1", "wand-2"],
            normalize_shop_inventory(
                {
                    "always_in_stock": [
                        "wand-1",
                        "wand-1",
                        "wand-2",
                    ]
                }
            )["always_in_stock"],
        )

    def test_legacy_shop_type_opens_the_shop_placeholder(self):
        organization = normalize_organization_record(
            {
                "record_id": "flourish",
                "name": "Flourish and Blotts",
                "organization_type": "Shop",
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
                        "year": 1654,
                        "description": "",
                        "person_ids": [],
                    }
                ],
                "jobs": [],
            }
        )

        self.assertTrue(organization["has_shop"])
        self.assertEqual(
            normalize_shop_inventory({}),
            organization["shop_inventory"],
        )

    def test_shop_tab_is_conditional_and_the_form_saves_its_state(self):
        editor_source = inspect.getsource(OrganizationPage.build_editor)
        details_source = inspect.getsource(
            OrganizationPage.build_details_editor
        )
        visibility_source = inspect.getsource(
            OrganizationPage.update_shop_page_visibility
        )
        save_source = inspect.getsource(OrganizationPage.save_organization)

        self.assertIn('text="Has a shop"', details_source)
        self.assertIn('text="Shop"', editor_source)
        self.assertIn("pack_forget", visibility_source)
        self.assertIn("has_shop_value.get()", save_source)
        self.assertIn('"shop_inventory"', save_source)


class OrganizationExtinctionTests(unittest.TestCase):
    def test_extinct_organizations_require_and_normalize_a_date(self):
        with self.assertRaisesRegex(ValueError, "date"):
            normalize_organization_extinction_date("", True)

        self.assertEqual(
            "1750-07-31",
            normalize_organization_extinction_date(
                "1750-7-31",
                True,
            ),
        )
        self.assertEqual(
            "",
            normalize_organization_extinction_date(
                "1750-07-31",
                False,
            ),
        )

    def test_extinction_cannot_precede_founding(self):
        controller = OrganizationController(
            OrganizationDatabase(),
            lambda: [],
        )
        organization = controller.normalize_organization(
            {
                "name": "Old Council",
                "organization_type": "Governmental",
                "location_id": "",
                "parent_organization_id": "",
                "school_id": "",
                "has_shop": False,
                "shop_inventory": {},
                "extinct": True,
                "extinction_date": "1699-12-31",
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
                "jobs": [],
            }
        )

        with self.assertRaisesRegex(ValueError, "before it was founded"):
            controller.validate_organization(organization)

    def test_existing_year_search_respects_extinction(self):
        database = OrganizationDatabase(
            [
                {
                    "record_id": "old-council",
                    "name": "Old Council",
                    "organization_type": "Governmental",
                    "location_id": "",
                    "parent_organization_id": "",
                    "school_id": "",
                    "has_shop": False,
                    "shop_inventory": {},
                    "extinct": True,
                    "extinction_date": "1750-07-31",
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
                    "jobs": [],
                }
            ]
        )
        controller = OrganizationController(database, lambda: [])

        self.assertEqual(
            1,
            len(controller.search_organizations(existing_year=1750)),
        )
        self.assertEqual(
            [],
            controller.search_organizations(existing_year=1751),
        )

    def test_extinct_checkbox_reveals_a_dated_field(self):
        details_source = inspect.getsource(
            OrganizationPage.build_details_editor
        )
        visibility_source = inspect.getsource(
            OrganizationPage.update_extinction_date_visibility
        )
        save_source = inspect.getsource(OrganizationPage.save_organization)

        self.assertIn('text="Extinct"', details_source)
        self.assertIn('text="Extinction date"', details_source)
        self.assertIn("grid_remove", visibility_source)
        self.assertIn("extinction_date_value.get()", save_source)


class OrganizationParentDisplayTests(unittest.TestCase):
    def test_parent_picker_uses_only_the_concise_hierarchy_label(self):
        organizations = [
            {
                "record_id": "ministry",
                "name": "British Ministry for Magic",
                "parent_organization_id": "",
            },
            {
                "record_id": "department",
                "name": "Department of Magical Law Enforcement",
                "parent_organization_id": "ministry",
                "organization_type": "Governmental",
                "location_id": "london",
                "events": [
                    {
                        "event_type": "founding",
                        "year": 1707,
                    }
                ],
            },
        ]
        dialog = SimpleNamespace(organizations=organizations)

        self.assertEqual(
            "Department of Magical Law Enforcement "
            "(within British Ministry for Magic)",
            OrganizationSelectionDialog.organization_display_text(
                dialog,
                organizations[1],
            ),
        )


class OrganizationJobDialogTests(unittest.TestCase):
    def test_currency_fields_reject_out_of_range_input_immediately(self):
        self.assertTrue(currency_component_input_is_valid("", "28"))
        self.assertTrue(currency_component_input_is_valid("16", "16"))
        self.assertTrue(currency_component_input_is_valid("28", "28"))
        self.assertFalse(currency_component_input_is_valid("17", "16"))
        self.assertFalse(currency_component_input_is_valid("29", "28"))
        self.assertFalse(currency_component_input_is_valid("44", "28"))
        self.assertFalse(currency_component_input_is_valid("-1", "28"))
        self.assertFalse(currency_component_input_is_valid("1.5", "28"))

        job_source = inspect.getsource(OrganizationJobDialog.build_dialog)
        quick_source = inspect.getsource(QuickOrganizationDialog.build_dialog)

        self.assertIn('validate="key"', job_source)
        self.assertIn('"16"', job_source)
        self.assertIn('"28"', job_source)
        self.assertIn('validate="key"', quick_source)

    def test_job_dialog_positions_itself_in_the_upper_right(self):
        owner = SimpleNamespace(
            winfo_rootx=Mock(return_value=100),
            winfo_rooty=Mock(return_value=50),
            winfo_width=Mock(return_value=1200),
        )
        dialog = SimpleNamespace(
            master=SimpleNamespace(
                winfo_toplevel=Mock(return_value=owner)
            ),
            winfo_width=Mock(return_value=640),
            winfo_height=Mock(return_value=455),
            geometry=Mock(),
            lift=Mock(),
        )

        OrganizationJobDialog.position_upper_right(dialog)

        dialog.geometry.assert_called_once_with(
            "640x455+636+122"
        )
        dialog.lift.assert_called_once_with()


class OrganizationSchemaTests(unittest.TestCase):
    def test_schema_twenty_eight_adds_shop_and_extinction_fields(self):
        database_data = {
            "_database": {
                "schema_version": 27,
                "database_version": "0.27.0",
            },
            "_application_settings": {},
            "people": [],
            "locations": [],
            "events": [],
            "organizations": [
                {
                    "record_id": "flourish",
                    "name": "Flourish and Blotts",
                    "organization_type": "Shop",
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
                            "year": 1654,
                            "description": "",
                            "person_ids": [],
                        }
                    ],
                    "jobs": [],
                }
            ],
        }

        migrated = JsonDatabase("unused.json").migrate_database(
            database_data
        )
        organization = database_data["organizations"][0]

        self.assertTrue(migrated)
        self.assertEqual(
            29,
            database_data["_database"]["schema_version"],
        )
        self.assertEqual(
            "0.29.0",
            database_data["_database"]["database_version"],
        )
        self.assertTrue(organization["has_shop"])
        self.assertEqual(
            normalize_shop_inventory({}),
            organization["shop_inventory"],
        )
        self.assertFalse(organization["extinct"])
        self.assertEqual("", organization["extinction_date"])


if __name__ == "__main__":
    unittest.main()
