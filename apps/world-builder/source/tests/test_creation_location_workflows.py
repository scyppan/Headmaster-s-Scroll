import unittest

from mage_maker.dialogs.creation import CreationWizardDialog
from mage_maker.sections.locations.page import LocationPage


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


class FakeTextControl:
    def __init__(self, value=""):
        self.text = FakeText(value)


class FakeSchoolField:
    def specialty_is_blank(self):
        return False

    def get_value(self):
        return "Hogwarts"


class FakeCreationEventController:
    def location_records(self):
        return [
            {
                "record_id": "ireland",
                "name": "Ireland",
                "parent_location_id": "",
            },
            {
                "record_id": "limerick",
                "name": "Limerick",
                "parent_location_id": "ireland",
            },
        ]


class FakeLocationController:
    def __init__(self):
        self.created_values = None

    def create_location(self, values):
        self.created_values = dict(values)
        return {
            "record_id": "new-location",
            "name": values["name"],
            "parent_location_id": values["parent_location_id"],
        }


class FakeLocationTree:
    def __init__(self):
        self.scope_changes = []

    def set_scope(self, location_id, notify=False):
        self.scope_changes.append((location_id, notify))


class CreationLocationWorkflowTests(unittest.TestCase):
    def test_creation_uses_the_selected_location_record(self):
        submitted_values = []
        dialog = object.__new__(CreationWizardDialog)
        dialog.event_controller = FakeCreationEventController()
        dialog.starting_location_id = ""
        dialog.starting_location_value = FakeVariable(
            "Select a starting location."
        )
        dialog.displayed_name_value = FakeVariable("Maeve")
        dialog.birth_year_value = FakeVariable("901")
        dialog.birth_month_value = FakeVariable("")
        dialog.birth_day_value = FakeVariable("")
        dialog.name_details = {
            "entries": [
                {
                    "entry_id": "birth-name",
                    "name_type": "birth name",
                    "name_entry": "Maeve of Limerick",
                    "date": "901",
                    "note": "",
                }
            ]
        }
        dialog.can_give_birth_value = FakeVariable(True)
        dialog.deceased_value = FakeVariable(True)
        dialog.death_year_value = FakeVariable("955")
        dialog.death_month_value = FakeVariable("03")
        dialog.death_day_value = FakeVariable("12")
        dialog.school_field = FakeSchoolField()
        dialog.create_command = submitted_values.append

        self.assertTrue(
            CreationWizardDialog.starting_location_chosen(
                dialog,
                "limerick",
            )
        )
        CreationWizardDialog.create_magician(dialog)

        self.assertEqual("limerick", dialog.starting_location_id)
        self.assertEqual(
            "Limerick",
            dialog.starting_location_value.get(),
        )
        self.assertEqual(1, len(submitted_values))
        self.assertEqual(
            "Limerick",
            submitted_values[0]["starting_location"],
        )
        self.assertEqual(
            "limerick",
            submitted_values[0]["starting_location_id"],
        )
        self.assertEqual(
            "Maeve of Limerick",
            submitted_values[0]["name_details"]["entries"][0]["name_entry"],
        )
        self.assertTrue(submitted_values[0]["deceased"])
        self.assertEqual("955", submitted_values[0]["death_year"])
        self.assertEqual("03", submitted_values[0]["death_month"])
        self.assertEqual("12", submitted_values[0]["death_day"])

    def test_saving_a_new_location_preserves_the_existing_region_lock(self):
        page = object.__new__(LocationPage)
        page.current_location_id = None
        page.region_lock_id = "ireland"
        page.loaded_parent_location_id = ""
        page.selected_parent_location_id = "limerick"
        page.name_value = FakeVariable("New village")
        page.extinct_value = FakeVariable(False)
        page.extinction_year_value = FakeVariable("")
        page.demographics_control = FakeTextControl()
        page.notes_control = FakeTextControl()
        page.controller = FakeLocationController()
        page.location_tree = FakeLocationTree()
        page.scope_change_command = lambda location_id: self.fail(
            "Creating a location must not change the region lock."
        )
        page.refreshed_location_id = ""
        page.refresh = lambda location_id: setattr(
            page,
            "refreshed_location_id",
            location_id,
        )
        page.status_command = lambda message: None

        self.assertTrue(LocationPage.save_location(page))
        self.assertEqual("ireland", page.region_lock_id)
        self.assertEqual([], page.location_tree.scope_changes)
        self.assertEqual(
            "new-location",
            page.refreshed_location_id,
        )
        self.assertEqual(
            "limerick",
            page.controller.created_values["parent_location_id"],
        )


if __name__ == "__main__":
    unittest.main()
