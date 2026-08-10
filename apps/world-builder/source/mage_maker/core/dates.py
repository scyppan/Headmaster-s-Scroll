import re
from datetime import date


DATE_PART_FIELDS = ("year", "month", "day")
PARTIAL_DATE_PATTERN = re.compile(r"^(\d{1,4})(?:-(\d{1,2})(?:-(\d{1,2}))?)?$")
CALENDAR_ADOPTION_NOTE = (
    "Note: When the Romans switched from the Julian to the Gregorian "
    "Calendar, the days October 5 to October 14 were skipped. Other "
    "countries adopted the Gregorian Calendar at other times and those "
    "countries subsequently skipped some commensurate dates at their own "
    "discretion. If you are aiming for absolute historical accuracy, you "
    "should check the exact date you’re inputting against the historical "
    "record in the country your character was born. The adoption of the "
    "Gregorian Calendar ultimately took nearly 300 years to complete "
    "worldwide"
)
EARLIEST_HISTORICAL_YEAR = -99999
LATEST_HISTORICAL_YEAR = 99999
GREGORIAN_REFORM_YEAR = 1582
GREGORIAN_REFORM_MONTH = 10
GREGORIAN_LAST_JULIAN_DAY = 4
GREGORIAN_FIRST_DAY = 15
EARLY_JULIAN_LEAP_BC_YEARS = frozenset(
    range(42, 8, -3)
)


def normalize_historical_year(value, label="Date"):
    if value in (None, "") or isinstance(value, bool):
        raise ValueError(f"{label} year must be a whole number.")

    try:
        year = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{label} year must be a whole number."
        ) from error

    if (
        year == 0
        or year < EARLIEST_HISTORICAL_YEAR
        or year > LATEST_HISTORICAL_YEAR
    ):
        raise ValueError(
            f"{label} year must be between "
            f"{EARLIEST_HISTORICAL_YEAR} and "
            f"{LATEST_HISTORICAL_YEAR}, excluding 0."
        )

    return year


def historical_year_after(year):
    normalized_year = normalize_historical_year(year)
    return 1 if normalized_year == -1 else normalized_year + 1


def historical_year_shift(year, offset):
    normalized_year = normalize_historical_year(year)

    if isinstance(offset, bool):
        raise ValueError("A year offset must be a whole number.")

    try:
        normalized_offset = int(offset)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "A year offset must be a whole number."
        ) from error

    astronomical_year = (
        normalized_year
        if normalized_year > 0
        else normalized_year + 1
    )
    shifted_astronomical_year = astronomical_year + normalized_offset
    shifted_historical_year = (
        shifted_astronomical_year
        if shifted_astronomical_year > 0
        else shifted_astronomical_year - 1
    )
    return normalize_historical_year(shifted_historical_year)


def historical_year_distance(start_year, end_year):
    normalized_start_year = normalize_historical_year(start_year)
    normalized_end_year = normalize_historical_year(end_year)
    astronomical_start_year = (
        normalized_start_year
        if normalized_start_year > 0
        else normalized_start_year + 1
    )
    astronomical_end_year = (
        normalized_end_year
        if normalized_end_year > 0
        else normalized_end_year + 1
    )
    return astronomical_end_year - astronomical_start_year


def historical_is_leap_year(year):
    normalized_year = normalize_historical_year(year)

    if normalized_year >= GREGORIAN_REFORM_YEAR:
        return (
            normalized_year % 400 == 0
            or (
                normalized_year % 4 == 0
                and normalized_year % 100 != 0
            )
        )

    if normalized_year >= 8:
        return normalized_year % 4 == 0

    if normalized_year >= 1:
        return False

    bc_year = abs(normalized_year)

    if 9 <= bc_year <= 42:
        return bc_year in EARLY_JULIAN_LEAP_BC_YEARS

    if bc_year <= 45:
        return False

    astronomical_year = normalized_year + 1
    return astronomical_year % 4 == 0


def historical_days_in_month(year, month):
    normalized_year = normalize_historical_year(year)

    if isinstance(month, bool):
        raise ValueError("Date month must be a whole number.")

    try:
        normalized_month = int(month)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Date month must be a whole number."
        ) from error

    if not 1 <= normalized_month <= 12:
        raise ValueError("Date month must be between 1 and 12.")

    if normalized_month == 2:
        return 29 if historical_is_leap_year(normalized_year) else 28

    if normalized_month in (4, 6, 9, 11):
        return 30

    return 31


def historical_date_was_skipped(year, month, day):
    return (
        int(year) == GREGORIAN_REFORM_YEAR
        and int(month) == GREGORIAN_REFORM_MONTH
        and GREGORIAN_LAST_JULIAN_DAY < int(day) < GREGORIAN_FIRST_DAY
    )


def normalize_historical_date_parts(
    year,
    month=None,
    day=None,
    label="Date",
    required_year=True,
):
    if year in (None, ""):
        if required_year:
            raise ValueError(f"{label} year must be a whole number.")

        if month not in (None, "") or day not in (None, ""):
            raise ValueError(
                f"{label} month or day requires a year."
            )

        return None, None, None

    normalized_year = normalize_historical_year(year, label)
    normalized_month = None
    normalized_day = None

    if month not in (None, ""):
        if isinstance(month, bool):
            raise ValueError(
                f"{label} month must be a whole number."
            )

        try:
            normalized_month = int(month)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{label} month must be a whole number."
            ) from error

        if not 1 <= normalized_month <= 12:
            raise ValueError(
                f"{label} month must be between 1 and 12."
            )

    if day not in (None, ""):
        if isinstance(day, bool):
            raise ValueError(
                f"{label} day must be a whole number."
            )

        try:
            normalized_day = int(day)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{label} day must be a whole number."
            ) from error

        if normalized_month is None:
            raise ValueError(f"{label} day requires a month.")

        maximum_day = historical_days_in_month(
            normalized_year,
            normalized_month,
        )

        if not 1 <= normalized_day <= maximum_day:
            raise ValueError(
                f"{label} is not a valid calendar date."
            )

    return normalized_year, normalized_month, normalized_day


def historical_date_boundary(
    year,
    month=None,
    day=None,
    end_boundary=False,
):
    normalized_year, normalized_month, normalized_day = (
        normalize_historical_date_parts(
            year,
            month,
            day,
            required_year=True,
        )
    )
    boundary_month = normalized_month

    if boundary_month is None:
        boundary_month = 12 if end_boundary else 1

    boundary_day = normalized_day

    if boundary_day is None:
        boundary_day = (
            historical_days_in_month(
                normalized_year,
                boundary_month,
            )
            if end_boundary
            else 1
        )

    return normalized_year, boundary_month, boundary_day


def next_historical_date(year, month, day):
    normalized_year, normalized_month, normalized_day = (
        normalize_historical_date_parts(
            year,
            month,
            day,
            required_year=True,
        )
    )

    if (
        normalized_year == GREGORIAN_REFORM_YEAR
        and normalized_month == GREGORIAN_REFORM_MONTH
        and normalized_day == GREGORIAN_LAST_JULIAN_DAY
    ):
        return (
            GREGORIAN_REFORM_YEAR,
            GREGORIAN_REFORM_MONTH,
            GREGORIAN_FIRST_DAY,
        )

    maximum_day = historical_days_in_month(
        normalized_year,
        normalized_month,
    )

    if normalized_day < maximum_day:
        return normalized_year, normalized_month, normalized_day + 1

    if normalized_month < 12:
        return normalized_year, normalized_month + 1, 1

    return historical_year_after(normalized_year), 1, 1


def previous_historical_date(year, month, day):
    normalized_year, normalized_month, normalized_day = (
        normalize_historical_date_parts(
            year,
            month,
            day,
            required_year=True,
        )
    )

    if (
        normalized_year == GREGORIAN_REFORM_YEAR
        and normalized_month == GREGORIAN_REFORM_MONTH
        and normalized_day == GREGORIAN_FIRST_DAY
    ):
        return (
            GREGORIAN_REFORM_YEAR,
            GREGORIAN_REFORM_MONTH,
            GREGORIAN_LAST_JULIAN_DAY,
        )

    if normalized_day > 1:
        return normalized_year, normalized_month, normalized_day - 1

    if normalized_month > 1:
        previous_month = normalized_month - 1
        return (
            normalized_year,
            previous_month,
            historical_days_in_month(
                normalized_year,
                previous_month,
            ),
        )

    previous_year = historical_year_shift(normalized_year, -1)
    return previous_year, 12, 31


def normalize_date_parts(year, month, day, label="Date"):
    values = []

    for value, field_name in zip((year, month, day), DATE_PART_FIELDS):
        if value in (None, ""):
            values.append(None)
            continue

        if isinstance(value, bool):
            raise ValueError(f"{label} {field_name} must be a whole number.")

        try:
            values.append(int(value))
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{label} {field_name} must be a whole number."
            ) from error

    normalized_year, normalized_month, normalized_day = values

    if normalized_year is not None and not 1 <= normalized_year <= 9999:
        raise ValueError(f"{label} year must be between 1 and 9999.")

    if normalized_month is not None and not 1 <= normalized_month <= 12:
        raise ValueError(f"{label} month must be between 1 and 12.")

    if normalized_day is not None and not 1 <= normalized_day <= 31:
        raise ValueError(f"{label} day must be between 1 and 31.")

    if normalized_day is not None and normalized_month is None:
        raise ValueError(f"{label} day requires a month.")

    if (
        normalized_year is not None
        and normalized_month is not None
        and normalized_day is not None
    ):
        try:
            date(normalized_year, normalized_month, normalized_day)
        except ValueError as error:
            raise ValueError(f"{label} is not a valid calendar date.") from error

    return normalized_year, normalized_month, normalized_day


def person_date_parts(person, prefix="birth"):
    if not isinstance(person, dict):
        return None, None, None

    return (
        person.get(f"{prefix}_year"),
        person.get(f"{prefix}_month"),
        person.get(f"{prefix}_day"),
    )


def person_age_at_death(person):
    birth_year, birth_month, birth_day = person_date_parts(
        person,
        "birth",
    )
    death_year, death_month, death_day = person_date_parts(
        person,
        "death",
    )

    if birth_year in (None, "") or death_year in (None, ""):
        return None, False

    try:
        age = historical_year_distance(birth_year, death_year)
    except (TypeError, ValueError):
        return None, False

    exact = all(
        value not in (None, "")
        for value in (
            birth_month,
            birth_day,
            death_month,
            death_day,
        )
    )

    if exact:
        try:
            birth_month = int(birth_month)
            birth_day = int(birth_day)
            death_month = int(death_month)
            death_day = int(death_day)
        except (TypeError, ValueError):
            return None, False

        if (death_month, death_day) < (birth_month, birth_day):
            age -= 1

    if age < 0:
        return None, exact

    return age, exact


def person_death_age_text(person):
    age, exact = person_age_at_death(person)

    if age is None:
        return ""

    if exact:
        return f"age {age}"

    return f"approximately age {age}"


def is_at_least_age(older_person, younger_person, minimum_age=18):
    older_year, older_month, older_day = person_date_parts(older_person)
    younger_year, younger_month, younger_day = person_date_parts(younger_person)

    if older_year in (None, "") or younger_year in (None, ""):
        return None

    older_year = int(older_year)
    younger_year = int(younger_year)
    year_gap = younger_year - older_year

    if year_gap > minimum_age:
        return True

    if year_gap < minimum_age:
        return False

    if older_month in (None, "") or younger_month in (None, ""):
        return True

    older_month = int(older_month)
    younger_month = int(younger_month)

    if younger_month > older_month:
        return True

    if younger_month < older_month:
        return False

    if older_day in (None, "") or younger_day in (None, ""):
        return True

    return int(younger_day) >= int(older_day)


def format_date_parts(year, month, day, unknown="nd."):
    if year in (None, ""):
        return unknown

    formatted = str(year).zfill(4)

    if month not in (None, ""):
        formatted += f"-{int(month):02d}"

    if day not in (None, ""):
        formatted += f"-{int(day):02d}"

    return formatted


MONTH_ABBREVIATIONS = (
    "",
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


def format_historical_display_date(value, unknown="nd."):
    date_text = str(value or "").strip()

    if not date_text:
        return unknown

    negative = date_text.startswith("-")
    date_body = date_text[1:] if negative else date_text
    parts = date_body.split("-")

    try:
        year = int(parts[0])
    except (IndexError, TypeError, ValueError):
        return date_text

    if negative:
        year = -year

    if len(parts) == 1:
        return str(year)

    try:
        month = int(parts[1])
    except (IndexError, TypeError, ValueError):
        return date_text

    if not 1 <= month <= 12:
        return date_text

    if len(parts) == 2:
        return f"{MONTH_ABBREVIATIONS[month]} {year}"

    try:
        day = int(parts[2])
    except (IndexError, TypeError, ValueError):
        return date_text

    return f"{day} {MONTH_ABBREVIATIONS[month]} {year}"


def format_line_item_date(value, unknown="nd."):
    date_text = str(value or "").strip()

    if not date_text:
        return unknown

    negative = date_text.startswith("-")
    date_body = date_text[1:] if negative else date_text
    parts = date_body.split("-")

    try:
        year = int(parts[0])
    except (IndexError, TypeError, ValueError):
        return date_text

    if negative:
        year = -year

    if len(parts) == 1:
        return str(year)

    try:
        month = int(parts[1])
    except (IndexError, TypeError, ValueError):
        return date_text

    if not 1 <= month <= 12:
        return date_text

    if len(parts) == 2:
        return f"{year} ({MONTH_ABBREVIATIONS[month]})"

    try:
        day = int(parts[2])
    except (IndexError, TypeError, ValueError):
        return date_text

    return f"{year} ({day:02d} {MONTH_ABBREVIATIONS[month]})"


def normalize_partial_date(value, label="Date"):
    date_text = str(value or "").strip()

    if not date_text:
        return ""

    match = PARTIAL_DATE_PATTERN.fullmatch(date_text)

    if match is None:
        raise ValueError(f"{label} must use YYYY, YYYY-MM, or YYYY-MM-DD.")

    year, month, day = normalize_date_parts(
        match.group(1),
        match.group(2),
        match.group(3),
        label,
    )
    normalized = str(year).zfill(4)

    if month is not None:
        normalized += f"-{month:02d}"

    if day is not None:
        normalized += f"-{day:02d}"

    return normalized


def split_partial_date(value, label="Date"):
    normalized = normalize_partial_date(value, label)

    if not normalized:
        return "", "", ""

    parts = normalized.split("-")
    return (
        parts[0],
        parts[1] if len(parts) > 1 else "",
        parts[2] if len(parts) > 2 else "",
    )
