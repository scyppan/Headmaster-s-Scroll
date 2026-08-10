import inspect
import unittest

from mage_maker.shell.person_list import (
    FILTER_SHOW_ALL,
    SORT_AGE,
    SORT_BIRTH_YEAR,
    SORT_BIRTH_YEAR_NEWEST,
    SORT_GROUP,
    SORT_NAME,
    PeopleList,
)


class FakeVariable:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


class CallRecorder:
    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


class PeopleListFilterTests(unittest.TestCase):
    def setUp(self):
        self.people_list = object.__new__(PeopleList)
        self.people_list.people = [
            {
                "record_id": "ancient",
                "displayed_name": "Maeve",
                "birth_year": 900,
                "deceased": True,
                "death_year": 980,
            },
            {
                "record_id": "adult",
                "displayed_name": "Carina",
                "birth_year": 1970,
                "deceased": True,
                "death_year": 2010,
            },
            {
                "record_id": "school",
                "displayed_name": "Harry",
                "birth_year": 1990,
                "deceased": True,
                "death_year": 2005,
            },
            {
                "record_id": "unknown",
                "displayed_name": "Unknown Mage",
                "birth_year": None,
            },
        ]
        self.people_list.search_text_by_id = {
            "ancient": "maeve founders hogwarts 900",
            "adult": "carina wanderers durmstrang 1970",
            "school": "harry founders hogwarts 1990",
            "unknown": "unknown mage unassigned",
        }
        self.people_list.group_names_by_id = {
            "ancient": "Founders",
            "adult": "Wanderers",
            "school": "Founders",
            "unknown": "Unassigned",
        }
        self.people_list.search_value = FakeVariable()
        self.people_list.group_filter_value = FakeVariable(
            FILTER_SHOW_ALL
        )
        self.people_list.age_filter_value = FakeVariable(
            FILTER_SHOW_ALL
        )
        self.people_list.sort_value = FakeVariable(
            SORT_BIRTH_YEAR
        )
        self.people_list.filter_updates_paused = False

    def test_birth_year_is_the_default_oldest_first_sort(self):
        visible_people = PeopleList.filtered_people(
            self.people_list
        )

        self.assertEqual(
            ["unknown", "ancient", "adult", "school"],
            [
                person["record_id"]
                for person in visible_people
            ],
        )

    def test_group_and_age_filters_work_together(self):
        self.people_list.group_filter_value.set("Founders")
        self.people_list.age_filter_value.set("11–17")
        visible_people = PeopleList.filtered_people(
            self.people_list
        )

        self.assertEqual(
            ["school"],
            [
                person["record_id"]
                for person in visible_people
            ],
        )

    def test_search_text_combines_with_explicit_filters(self):
        self.people_list.search_value.set("maeve")
        self.people_list.group_filter_value.set("Founders")
        visible_people = PeopleList.filtered_people(
            self.people_list
        )

        self.assertEqual(
            ["ancient"],
            [
                person["record_id"]
                for person in visible_people
            ],
        )

    def test_sort_menu_supports_birth_name_group_and_age_ordering(self):
        expected_orders = {
            SORT_BIRTH_YEAR_NEWEST: [
                "unknown",
                "school",
                "adult",
                "ancient",
            ],
            SORT_NAME: [
                "adult",
                "school",
                "ancient",
                "unknown",
            ],
            SORT_GROUP: [
                "ancient",
                "school",
                "unknown",
                "adult",
            ],
            SORT_AGE: [
                "ancient",
                "adult",
                "school",
                "unknown",
            ],
        }

        for sort_name, expected_record_ids in expected_orders.items():
            with self.subTest(sort_name=sort_name):
                self.people_list.sort_value.set(sort_name)
                visible_people = PeopleList.filtered_people(
                    self.people_list
                )
                self.assertEqual(
                    expected_record_ids,
                    [
                        person["record_id"]
                        for person in visible_people
                    ],
                )

    def test_show_all_clears_search_and_filters_without_changing_sort(self):
        self.people_list.search_value.set("harry")
        self.people_list.group_filter_value.set("Founders")
        self.people_list.age_filter_value.set("11–17")
        self.people_list.sort_value.set(SORT_NAME)
        self.people_list.rebuild_rows = CallRecorder()

        PeopleList.show_all_people(self.people_list)

        self.assertEqual("", self.people_list.search_value.get())
        self.assertEqual(
            FILTER_SHOW_ALL,
            self.people_list.group_filter_value.get(),
        )
        self.assertEqual(
            FILTER_SHOW_ALL,
            self.people_list.age_filter_value.get(),
        )
        self.assertEqual(
            SORT_NAME,
            self.people_list.sort_value.get(),
        )
        self.assertEqual(
            1,
            self.people_list.rebuild_rows.calls,
        )

    def test_age_uses_age_at_death_and_respects_full_dates(self):
        age = PeopleList.person_age(
            self.people_list,
            {
                "birth_year": 2000,
                "birth_month": 12,
                "birth_day": 31,
                "deceased": True,
                "death_year": 2010,
                "death_month": 1,
                "death_day": 1,
            },
        )

        self.assertEqual(9, age)

    def test_filters_are_collapsed_into_one_compact_menu(self):
        source = inspect.getsource(PeopleList.__init__)

        self.assertIn('text="Filters ▾"', source)
        self.assertNotIn("group_filter_select", source)
        self.assertNotIn("age_filter_select", source)
        self.assertNotIn("sort_select", source)

    def test_name_is_the_first_line_of_each_list_entry(self):
        people_list = object.__new__(PeopleList)
        people_list.people = []
        people_list.labels_by_id = {}
        people_list.search_text_by_id = {}
        people_list.group_colors_by_id = {}
        people_list.group_names_by_id = {}
        people_list.initial_values_complete_by_id = {}
        people_list.group_filter_value = FakeVariable(
            FILTER_SHOW_ALL
        )
        people_list.filter_updates_paused = False
        people_list.rebuild_rows = CallRecorder()

        PeopleList.set_people(
            people_list,
            [
                {
                    "record_id": "maeve",
                    "displayed_name": "Maeve",
                    "birth_year": 901,
                }
            ],
            mage_groups=[],
        )

        self.assertEqual(
            "Maeve\nBorn 901",
            people_list.labels_by_id["maeve"],
        )


if __name__ == "__main__":
    unittest.main()
