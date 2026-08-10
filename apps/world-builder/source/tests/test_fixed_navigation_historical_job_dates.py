import inspect
import unittest
from unittest.mock import patch

from mage_maker.core.dates import (
    CALENDAR_ADOPTION_NOTE,
    historical_is_leap_year,
    historical_year_distance,
    historical_year_shift,
    next_historical_date,
    normalize_historical_date_parts,
)
from mage_maker.dialogs import creation
from mage_maker.sections.development import organization_dialogs
from mage_maker.sections.development.models import (
    adult_year_calendar_year_range,
    calculate_school_start_year,
    new_job_record,
    normalize_job_record,
    school_year_calendar_year_range,
    suggested_job_start_date,
)
from mage_maker.sections.development.page import DevelopmentView
from mage_maker.sections.development.position_assignment_dialog import (
    PositionAssignmentDialog,
)
from mage_maker.sections.events import dialog as event_dialog
from mage_maker.sections.events import editor as event_editor
from mage_maker.sections.family_tree import child_dialog
from mage_maker.sections.family_tree import spouse_dialog
from mage_maker.sections.ledger import dialog as ledger_dialog
from mage_maker.sections.locations import page as location_page
from mage_maker.sections.locations import periods_page
from mage_maker.sections.names import details as name_details
from mage_maker.sections.organizations import event_dialog as organization_event_dialog
from mage_maker.sections.organizations import job_dialog as organization_job_dialog
from mage_maker.sections.organizations import page as organization_page
from mage_maker.sections.profile import page as profile_page
from mage_maker.sections.settings import page as settings_page
from mage_maker.ui.widgets import CalendarAdoptionNotice


class HistoricalCalendarTests(unittest.TestCase):
    def test_early_julian_augustan_and_gregorian_leap_rules(self):
        self.assertFalse(historical_is_leap_year(-45))
        self.assertTrue(historical_is_leap_year(-42))
        self.assertFalse(historical_is_leap_year(-41))
        self.assertTrue(historical_is_leap_year(-9))
        self.assertFalse(historical_is_leap_year(-8))
        self.assertFalse(historical_is_leap_year(4))
        self.assertTrue(historical_is_leap_year(8))
        self.assertTrue(historical_is_leap_year(1500))
        self.assertTrue(historical_is_leap_year(1600))
        self.assertFalse(historical_is_leap_year(1700))
        self.assertTrue(historical_is_leap_year(2000))

    def test_next_day_handles_bc_leap_days_and_no_year_zero(self):
        self.assertEqual(
            (-42, 2, 29),
            next_historical_date(-42, 2, 28),
        )
        self.assertEqual(
            (-41, 3, 1),
            next_historical_date(-41, 2, 28),
        )
        self.assertEqual(
            (1, 1, 1),
            next_historical_date(-1, 12, 31),
        )

    def test_year_arithmetic_skips_year_zero(self):
        self.assertEqual(1, historical_year_shift(-1, 1))
        self.assertEqual(-1, historical_year_shift(1, -1))
        self.assertEqual(1, historical_year_distance(-1, 1))
        self.assertEqual(2, historical_year_distance(-1, 2))

    def test_development_year_ranges_skip_year_zero(self):
        self.assertEqual(-1, calculate_school_start_year(-12, 7, 31))
        self.assertEqual(
            (-1, 1),
            school_year_calendar_year_range(-1, 1),
        )
        self.assertEqual(
            (-1, 1),
            adult_year_calendar_year_range(-8, 1),
        )

    def test_next_day_uses_the_roman_1582_cutover_by_default(self):
        self.assertEqual(
            (1582, 10, 15),
            next_historical_date(1582, 10, 4),
        )
        self.assertEqual(
            (1582, 10, 11),
            next_historical_date(1582, 10, 10),
        )

    def test_manual_dates_in_later_adopting_countries_remain_enterable(self):
        self.assertEqual(
            (1582, 10, 10),
            normalize_historical_date_parts(
                1582,
                10,
                10,
                "Historical date",
            ),
        )

    def test_job_dates_reject_impossible_month_days(self):
        with self.assertRaisesRegex(
            ValueError,
            "not a valid calendar date",
        ):
            normalize_job_record(
                {
                    "organization_name": "Ministry",
                    "title": "Auror",
                    "salary": {
                        "galleons": 0,
                        "sickles": 0,
                        "knuts": 0,
                    },
                    "start_year": 1900,
                    "start_month": 2,
                    "start_day": 29,
                }
            )


class JobStartSuggestionTests(unittest.TestCase):
    def test_job_start_follows_the_latest_job_ending_on_the_page(self):
        earlier_job = new_job_record(
            "org-1",
            "Ministry",
            "Assistant",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1996,
            1,
            1,
            1998,
            3,
            10,
        )
        later_job = new_job_record(
            "org-2",
            "Hospital",
            "Clerk",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1997,
            1,
            1,
            1998,
            11,
            30,
        )
        self.assertEqual(
            (1998, 12, 1),
            suggested_job_start_date(
                [earlier_job, later_job],
                1998,
            ),
        )

    def test_partial_end_dates_use_the_true_end_of_the_period(self):
        month_only_job = new_job_record(
            "org-1",
            "Ministry",
            "Assistant",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1996,
            end_year=2000,
            end_month=2,
        )
        year_only_job = new_job_record(
            "org-2",
            "Hospital",
            "Clerk",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1997,
            end_year=2001,
        )
        self.assertEqual(
            (2000, 3, 1),
            suggested_job_start_date([month_only_job], 2000),
        )
        self.assertEqual(
            (2002, 1, 1),
            suggested_job_start_date([year_only_job], 2001),
        )

    def test_combined_first_adult_page_checks_both_displayed_years(self):
        job = new_job_record(
            "org-1",
            "Ministry",
            "Assistant",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1998,
            end_year=1999,
            end_month=7,
            end_day=31,
        )
        self.assertEqual(
            (1999, 8, 1),
            suggested_job_start_date([job], 1998, 1999),
        )

    def test_roman_cutover_and_early_julian_dates_feed_job_defaults(self):
        roman_job = new_job_record(
            "org-1",
            "Ministry",
            "Assistant",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1582,
            end_year=1582,
            end_month=10,
            end_day=4,
        )
        ancient_job = new_job_record(
            "org-2",
            "Guild",
            "Scribe",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            -45,
            end_year=-42,
            end_month=2,
            end_day=28,
        )
        self.assertEqual(
            (1582, 10, 15),
            suggested_job_start_date([roman_job], 1582),
        )
        self.assertEqual(
            (-42, 2, 29),
            suggested_job_start_date([ancient_job], -42),
        )

    def test_a_manually_entered_later_adoption_date_is_preserved(self):
        later_adoption_job = new_job_record(
            "org-1",
            "Guild",
            "Clerk",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1582,
            end_year=1582,
            end_month=10,
            end_day=10,
        )
        self.assertEqual(
            (1582, 10, 11),
            suggested_job_start_date([later_adoption_job], 1582),
        )


class DevelopmentNavigationAndDateNoticeTests(unittest.TestCase):
    def test_development_page_arrows_use_a_fixed_center_frame(self):
        source = inspect.getsource(DevelopmentView.build_plan_panel)
        self.assertIn("width=390", source)
        self.assertIn("height=32", source)
        self.assertIn("page_navigation_controls.grid_propagate(False)", source)
        self.assertIn("sticky=\"ew\"", source)

    def test_add_job_passes_the_calculated_month_and_day_defaults(self):
        source = inspect.getsource(DevelopmentView.open_job_dialog)
        signature = inspect.signature(PositionAssignmentDialog.__init__)
        self.assertIn("suggested_job_start_date", source)
        self.assertIn("default_start_month", signature.parameters)
        self.assertIn("default_start_day", signature.parameters)

    @patch("mage_maker.sections.development.page.JobDialog")
    def test_add_job_uses_the_day_after_a_job_ending_on_this_page(
        self,
        job_dialog,
    ):
        ending_job = new_job_record(
            "org-1",
            "Ministry",
            "Assistant",
            {"galleons": 0, "sickles": 0, "knuts": 0},
            1997,
            end_year=1998,
            end_month=2,
            end_day=28,
        )
        view = object.__new__(DevelopmentView)
        view.active_adult_year = 1
        view.birth_year = 1980
        view.birth_month = 7
        view.birth_day = 31
        view.adult_year_records = [
            {"adult_year": 1, "jobs": [ending_job]}
        ]
        view.organization_create_command = None
        view.organization_location_provider = None
        view.available_organizations = lambda: []
        view.all_job_assignments = lambda: [ending_job]
        view.save_job_record = lambda record: None

        DevelopmentView.open_job_dialog(view)

        call = job_dialog.call_args
        self.assertEqual(1998, call.args[2])
        self.assertEqual(3, call.kwargs["default_start_month"])
        self.assertEqual(1, call.kwargs["default_start_day"])

    def test_calendar_warning_matches_the_requested_wording(self):
        self.assertEqual(
            "Note: When the Romans switched from the Julian to the Gregorian "
            "Calendar, the days October 5 to October 14 were skipped. Other "
            "countries adopted the Gregorian Calendar at other times and those "
            "countries subsequently skipped some commensurate dates at their own "
            "discretion. If you are aiming for absolute historical accuracy, you "
            "should check the exact date you’re inputting against the historical "
            "record in the country your character was born. The adoption of the "
            "Gregorian Calendar ultimately took nearly 300 years to complete "
            "worldwide",
            CALENDAR_ADOPTION_NOTE,
        )

    def test_calendar_warning_is_available_by_mouse_and_keyboard(self):
        source = inspect.getsource(CalendarAdoptionNotice)
        self.assertIn("<Button-1>", source)
        self.assertIn("<Return>", source)
        self.assertIn("<space>", source)
        self.assertIn("messagebox.showinfo", source)

    def test_every_active_date_entry_surface_uses_the_calendar_notice(self):
        date_entry_modules = (
            creation,
            organization_dialogs,
            event_dialog,
            event_editor,
            child_dialog,
            spouse_dialog,
            ledger_dialog,
            location_page,
            periods_page,
            name_details,
            organization_event_dialog,
            organization_job_dialog,
            organization_page,
            profile_page,
            settings_page,
        )

        for module in date_entry_modules:
            with self.subTest(module=module.__name__):
                self.assertIn(
                    "CalendarAdoptionNotice",
                    inspect.getsource(module),
                )


if __name__ == "__main__":
    unittest.main()
