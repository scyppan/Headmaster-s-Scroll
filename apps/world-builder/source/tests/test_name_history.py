import unittest

from mage_maker.sections.names.details import NameEntryDialog
from mage_maker.sections.names.history import (
    migrate_legacy_name_details,
    normalize_name_details,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class FakeControl:
    def __init__(self):
        self.enabled = True

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)


class FakeField:
    def __init__(self):
        self.control = FakeControl()


class FakeLabel:
    def __init__(self):
        self.text = ""

    def configure(self, **values):
        self.text = str(values.get("text", self.text))


class FakeCombobox:
    def __init__(self):
        self.state = "readonly"

    def configure(self, **values):
        self.state = str(values.get("state", self.state))


class FakeText:
    def __init__(self, value=""):
        self.value = value

    def get(self, start, end):
        return self.value


class NameHistoryTests(unittest.TestCase):
    def test_legacy_fields_become_individual_entries(self):
        details = migrate_legacy_name_details(
            {
                "aliases": "First Alias\nSecond Alias",
                "sobriquets": "The Excellent",
                "name_changes": "Maiden name: Earlier Name",
            },
            "Displayed Name",
            "person-one",
        )
        self.assertEqual(
            [
                ("Alias", "First Alias"),
                ("Alias", "Second Alias"),
                ("Sobriquet", "The Excellent"),
                ("Maiden name", "Earlier Name"),
            ],
            [
                (entry["name_type"], entry["name_entry"])
                for entry in details["entries"]
            ],
        )

    def test_name_entry_requires_type_and_name(self):
        with self.assertRaisesRegex(ValueError, "Name type"):
            normalize_name_details(
                {
                    "entries": [
                        {
                            "name_type": "",
                            "name_entry": "Merlin",
                        }
                    ]
                }
            )

    def test_birth_name_date_matches_birthdate_and_is_locked(self):
        dialog = object.__new__(NameEntryDialog)
        dialog.entry_id = "birth-name"
        dialog.birth_name_locked = True
        dialog.birth_date = "0901-02-03"
        dialog.values = {
            "name_type": FakeVariable("birth name"),
            "name_entry": FakeVariable("Maeve ingen Ailella"),
            "date_year": FakeVariable("9999"),
            "date_month": FakeVariable("12"),
            "date_day": FakeVariable("31"),
        }
        dialog.name_type_field = FakeCombobox()
        dialog.date_heading = FakeLabel()
        dialog.date_year_field = FakeField()
        dialog.date_month_field = FakeField()
        dialog.date_day_field = FakeField()
        dialog.note_text = FakeText("Original name.")

        NameEntryDialog.apply_name_type_rules(dialog)
        entry = NameEntryDialog.get_entry(dialog)

        self.assertEqual("0901", dialog.values["date_year"].get())
        self.assertEqual("02", dialog.values["date_month"].get())
        self.assertEqual("03", dialog.values["date_day"].get())
        self.assertFalse(dialog.date_year_field.control.enabled)
        self.assertFalse(dialog.date_month_field.control.enabled)
        self.assertFalse(dialog.date_day_field.control.enabled)
        self.assertEqual("disabled", dialog.name_type_field.state)
        self.assertEqual("0901-02-03", entry["date"])

    def test_name_history_allows_zero_or_one_birth_name_but_not_two(self):
        without_birth_name = normalize_name_details(
            {
                "entries": [
                    {
                        "name_type": "alias",
                        "name_entry": "The Fearless",
                    }
                ]
            }
        )
        with_one_birth_name = normalize_name_details(
            {
                "entries": [
                    {
                        "name_type": "birth name",
                        "name_entry": "Fingal",
                    }
                ]
            }
        )

        self.assertEqual(1, len(without_birth_name["entries"]))
        self.assertEqual(1, len(with_one_birth_name["entries"]))

        with self.assertRaisesRegex(
            ValueError,
            "Only one Birth name",
        ):
            normalize_name_details(
                {
                    "entries": [
                        {
                            "name_type": "birth name",
                            "name_entry": "Fingal",
                        },
                        {
                            "name_type": "Birth Name",
                            "name_entry": "Fionnghall",
                        },
                    ]
                }
            )


if __name__ == "__main__":
    unittest.main()
