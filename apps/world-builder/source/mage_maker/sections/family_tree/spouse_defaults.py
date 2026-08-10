import calendar
import random
from copy import deepcopy
from datetime import date, timedelta

from mage_maker.core.dates import is_at_least_age, normalize_date_parts
from mage_maker.sections.family_tree.spouse_candidates import (
    integer_year,
    most_recent_location,
)


def random_spouse_birth_date(focus_person, children=None):
    focus = focus_person if isinstance(focus_person, dict) else {}
    focus_year = integer_year(focus.get("birth_year"))

    if focus_year is None:
        raise ValueError(
            "Enter the selected person's Birth year before creating a spouse."
        )

    earliest_year = max(1, focus_year - 7)
    latest_year = min(9999, focus_year + 7)
    earliest_date = date(earliest_year, 1, 1)
    latest_date = date(latest_year, 12, 31)

    for child in children or []:
        if not isinstance(child, dict):
            continue

        child_year = integer_year(child.get("birth_year"))

        if child_year is None or child_year <= 18:
            continue

        child_month = int(child.get("birth_month") or 1)
        child_day = int(child.get("birth_day") or 1)
        safe_year = child_year - 18
        child_day = min(child_day, calendar.monthrange(safe_year, child_month)[1])
        latest_date = min(
            latest_date,
            date(safe_year, child_month, child_day),
        )

    if latest_date < earliest_date:
        raise ValueError(
            "No birth date within seven years of this person would make the new "
            "spouse at least 18 when the existing children were born."
        )

    generated_date = earliest_date + timedelta(
        days=random.randint(0, (latest_date - earliest_date).days)
    )
    return generated_date.year, generated_date.month, generated_date.day


def prepare_new_spouse_values(focus_person, children, entered_values):
    values = deepcopy(entered_values if isinstance(entered_values, dict) else {})
    birth_fields_are_blank = all(
        values.get(field_name) in (None, "")
        for field_name in ("birth_year", "birth_month", "birth_day")
    )

    if birth_fields_are_blank:
        birth_year, birth_month, birth_day = random_spouse_birth_date(
            focus_person,
            children,
        )
        values["birth_year"] = birth_year
        values["birth_month"] = birth_month
        values["birth_day"] = birth_day

    normalized_year, normalized_month, normalized_day = normalize_date_parts(
        values.get("birth_year"),
        values.get("birth_month"),
        values.get("birth_day"),
        "Birth",
    )
    focus_year = integer_year(
        (focus_person if isinstance(focus_person, dict) else {}).get("birth_year")
    )

    if (
        focus_year is not None
        and normalized_year is not None
        and abs(normalized_year - focus_year) > 7
    ):
        raise ValueError(
            "A spouse must be within seven years of this person's age."
        )

    values["birth_year"] = normalized_year
    values["birth_month"] = normalized_month
    values["birth_day"] = normalized_day

    for child in children or []:
        if isinstance(child, dict) and is_at_least_age(values, child, 18) is False:
            raise ValueError(
                "This birth date would make the new spouse younger than 18 when "
                f"{child.get('displayed_name', 'an existing child')} was born."
            )

    values["starting_location"] = most_recent_location(focus_person)
    return values
