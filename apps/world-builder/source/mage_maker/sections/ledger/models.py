import hashlib
import uuid
from copy import deepcopy

from mage_maker.core.dates import (
    historical_year_after,
    historical_year_shift,
)


LEDGER_KIND_EARNED = "earned"
LEDGER_KIND_BOUGHT = "bought"
LEDGER_KIND_NEUTRAL = "neutral"
LEDGER_KINDS = (
    LEDGER_KIND_EARNED,
    LEDGER_KIND_BOUGHT,
    LEDGER_KIND_NEUTRAL,
)
LEDGER_SOURCE_ALLOWANCE = "monthly_allowance"
LEDGER_SOURCE_SCHOOL_BOOK = "school_book"
LEDGER_SOURCE_STARTING_ALLOWANCE = "starting_allowance"
MONTH_NAMES = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
LEDGER_YEAR_START_MONTH = 7
FIRST_MONTHLY_ALLOWANCE_MONTH = 8
LEDGER_YEAR_MONTHS = (
    7,
    8,
    9,
    10,
    11,
    12,
    1,
    2,
    3,
    4,
    5,
    6,
)
FIRST_LEDGER_YEAR_ALLOWANCE_MONTHS = (
    8,
    9,
    10,
    11,
    12,
    1,
    2,
    3,
    4,
    5,
    6,
)
SICKLES_PER_GALLEON = 17
LEDGER_LATE_JULY_FIRST_DAY = 20
LEDGER_LATE_JULY_LAST_DAY = 31


def normalize_ledger_month(value):
    if isinstance(value, bool):
        raise ValueError("Ledger month must be January through December.")

    if isinstance(value, str):
        normalized_value = value.strip().casefold()

        if normalized_value in ("start", "opening", "opening balance"):
            return 0

        month_lookup = {
            month_name.casefold(): month_number
            for month_number, month_name in enumerate(
                MONTH_NAMES,
                start=1,
            )
        }

        if normalized_value in month_lookup:
            return month_lookup[normalized_value]

    try:
        month_number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Ledger month must be January through December."
        ) from error

    if not 0 <= month_number <= 12:
        raise ValueError(
            "Ledger month must be Start or January through December."
        )

    return month_number


def ledger_days_in_month(calendar_year, month):
    normalized_month = normalize_ledger_month(month)

    if normalized_month in (0, 1, 3, 5, 7, 8, 10, 12):
        return 31

    if normalized_month in (4, 6, 9, 11):
        return 30

    try:
        normalized_year = int(calendar_year)
    except (TypeError, ValueError):
        return 29

    is_leap_year = (
        normalized_year % 4 == 0
        and (
            normalized_year % 100 != 0
            or normalized_year % 400 == 0
        )
    )
    return 29 if is_leap_year else 28


def normalize_ledger_day(value, calendar_year=None, month=None):
    if value in (None, ""):
        day = 1
    elif isinstance(value, bool):
        raise ValueError("Ledger day must be a whole number.")
    else:
        try:
            day = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Ledger day must be a whole number."
            ) from error

    maximum_day = ledger_days_in_month(
        calendar_year,
        1 if month in (None, "") else month,
    )

    if not 1 <= day <= maximum_day:
        raise ValueError(
            f"Ledger day must be between 1 and {maximum_day}."
        )

    return day


def normalize_ledger_kind(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().replace("_", " ").split()
    )
    aliases = {
        "earned": LEDGER_KIND_EARNED,
        "income": LEDGER_KIND_EARNED,
        "sold": LEDGER_KIND_EARNED,
        "sold or earned": LEDGER_KIND_EARNED,
        "bought": LEDGER_KIND_BOUGHT,
        "purchase": LEDGER_KIND_BOUGHT,
        "purchased": LEDGER_KIND_BOUGHT,
        "expense": LEDGER_KIND_BOUGHT,
        "neutral": LEDGER_KIND_NEUTRAL,
        "": LEDGER_KIND_NEUTRAL,
    }
    kind = aliases.get(normalized_value)

    if kind is None:
        raise ValueError(
            "Ledger type must be bought, sold or earned, or neutral."
        )

    return kind


def normalize_ledger_entry(value):
    if not isinstance(value, dict):
        raise TypeError("A ledger entry must be an object.")

    school_year_value = value.get("school_year")
    school_year = None

    if school_year_value not in (None, ""):
        try:
            school_year = int(school_year_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "A ledger school year must be a whole number."
            ) from error

        if not 1 <= school_year <= 7:
            raise ValueError(
                "A ledger school year must be Year 1 through Year 7."
            )

    adult_year_value = value.get("adult_year")
    adult_year = None

    if adult_year_value not in (None, ""):
        try:
            adult_year = int(adult_year_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "A ledger adult year must be a whole number."
            ) from error

        if adult_year < 1:
            raise ValueError(
                "A ledger adult year must be at least one."
            )

    if school_year is not None and adult_year is not None:
        raise ValueError(
            "A ledger entry cannot belong to both a school and adult year."
        )

    calendar_year_value = value.get("calendar_year")

    if calendar_year_value in (None, ""):
        calendar_year = None
    else:
        try:
            calendar_year = int(calendar_year_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Ledger calendar year must be a whole number."
            ) from error

    if (
        school_year is None
        and adult_year is None
        and calendar_year is None
    ):
        raise ValueError(
            "A ledger entry must belong to a development calendar year."
        )

    month = normalize_ledger_month(value.get("month"))
    day = normalize_ledger_day(
        value.get("day", 1),
        calendar_year,
        month,
    )
    item = str(value.get("item", "") or "").strip()

    if not item:
        raise ValueError("A ledger entry must have an item.")

    amount_value = value.get("amount_sickles", 0)

    if isinstance(amount_value, bool):
        raise ValueError(
            "Ledger amount must be a non-negative whole number of sickles."
        )

    try:
        amount_sickles = int(amount_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Ledger amount must be a non-negative whole number of sickles."
        ) from error

    if amount_sickles < 0:
        raise ValueError(
            "Ledger amount must be a non-negative whole number of sickles."
        )

    automatic_source = str(
        value.get("automatic_source", "") or ""
    ).strip()
    book_record_id = str(
        value.get("book_record_id", "") or ""
    ).strip()
    suppressed_value = value.get("suppressed", False)
    suppressed = (
        suppressed_value
        if isinstance(suppressed_value, bool)
        else str(suppressed_value or "").strip().casefold()
        in ("1", "true", "yes", "suppressed")
    )
    entry_id = str(value.get("entry_id", "") or "").strip()

    if not entry_id:
        identity_text = "|".join(
            (
                str(school_year or ""),
                str(adult_year or ""),
                str(calendar_year or ""),
                str(month),
                str(day),
                item.casefold(),
                str(amount_sickles),
                normalize_ledger_kind(value.get("kind")).casefold(),
                automatic_source.casefold(),
                book_record_id.casefold(),
            )
        )
        entry_id = "ledger-" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()[:20]

    return {
        "entry_id": entry_id,
        "school_year": school_year,
        "adult_year": adult_year,
        "calendar_year": calendar_year,
        "month": month,
        "day": day,
        "item": item,
        "amount_sickles": amount_sickles,
        "kind": normalize_ledger_kind(value.get("kind")),
        "note": str(value.get("note", "") or "").strip(),
        "automatic_source": automatic_source,
        "book_record_id": book_record_id,
        "suppressed": suppressed,
    }


def ledger_entry_sort_key(entry):
    automatic_order = {
        LEDGER_SOURCE_STARTING_ALLOWANCE: 0,
        LEDGER_SOURCE_ALLOWANCE: 1,
        LEDGER_SOURCE_SCHOOL_BOOK: 2,
        "": 3,
    }
    fallback_year = (
        entry["school_year"]
        if entry["school_year"] is not None
        else (
            7 + entry["adult_year"]
            if entry["adult_year"] is not None
            else 0
        )
    )
    return (
        entry["calendar_year"] is None,
        (
            entry["calendar_year"]
            if entry["calendar_year"] is not None
            else fallback_year
        ),
        entry["month"],
        entry["day"],
        automatic_order.get(entry["automatic_source"], 3),
        entry["item"].casefold(),
        entry["entry_id"],
    )


def normalize_ledger_entries(value):
    if value in (None, ""):
        candidate_entries = []
    elif isinstance(value, (list, tuple)):
        candidate_entries = list(value)
    else:
        raise TypeError("Ledger entries must be a list.")

    entries_by_id = {}

    for candidate_entry in candidate_entries:
        normalized_entry = normalize_ledger_entry(candidate_entry)
        entries_by_id[normalized_entry["entry_id"]] = normalized_entry

    return sorted(
        entries_by_id.values(),
        key=ledger_entry_sort_key,
    )


def visible_ledger_entries(value):
    return [
        entry
        for entry in normalize_ledger_entries(value)
        if not entry["suppressed"]
    ]


def replace_ledger_entry(entries, replacement):
    normalized_replacement = normalize_ledger_entry(replacement)
    replacement_id = normalized_replacement["entry_id"]
    normalized_entries = normalize_ledger_entries(entries)

    if not any(
        entry["entry_id"] == replacement_id
        for entry in normalized_entries
    ):
        raise KeyError(f"Unknown ledger entry_id: {replacement_id}")

    return normalize_ledger_entries(
        [
            (
                normalized_replacement
                if entry["entry_id"] == replacement_id
                else entry
            )
            for entry in normalized_entries
        ]
    )


def delete_ledger_entry(entries, entry_id):
    selected_id = str(entry_id or "").strip()
    normalized_entries = normalize_ledger_entries(entries)
    selected_entry = next(
        (
            entry
            for entry in normalized_entries
            if entry["entry_id"] == selected_id
        ),
        None,
    )

    if selected_entry is None:
        raise KeyError(f"Unknown ledger entry_id: {selected_id}")

    if selected_entry["automatic_source"]:
        suppressed_entry = deepcopy(selected_entry)
        suppressed_entry["suppressed"] = True
        return replace_ledger_entry(
            normalized_entries,
            suppressed_entry,
        )

    return normalize_ledger_entries(
        [
            entry
            for entry in normalized_entries
            if entry["entry_id"] != selected_id
        ]
    )


def updated_ledger_entry(
    existing_entry,
    calendar_year,
    month,
    day,
    item,
    amount_sickles,
    kind,
    note="",
):
    normalized_existing = normalize_ledger_entry(existing_entry)
    return normalize_ledger_entry(
        {
            **normalized_existing,
            "calendar_year": calendar_year,
            "month": month,
            "day": day,
            "item": item,
            "amount_sickles": amount_sickles,
            "kind": kind,
            "note": note,
            "suppressed": False,
        }
    )


def ledger_book_identity(book):
    if not isinstance(book, dict):
        return ""

    record_id = str(book.get("record_id", "") or "").strip()

    if record_id:
        return f"id:{record_id}"

    name = str(book.get("name", "") or "").strip().casefold()
    author = str(book.get("author", "") or "").strip().casefold()

    if not name:
        return ""

    return f"name:{name}|author:{author}"


def ledger_calendar_year(academic_start_year, school_year):
    if academic_start_year in (None, ""):
        return None

    try:
        return historical_year_shift(
            academic_start_year,
            int(school_year) - 1,
        )
    except (TypeError, ValueError):
        return None


def ledger_adult_calendar_year(
    academic_start_year,
    adult_year,
):
    if academic_start_year in (None, ""):
        return None

    try:
        normalized_adult_year = int(adult_year)
    except (TypeError, ValueError):
        return None

    try:
        graduation_year = historical_year_shift(
            academic_start_year,
            7,
        )
    except ValueError:
        return None

    if normalized_adult_year == 1:
        return graduation_year

    return historical_year_shift(
        graduation_year,
        normalized_adult_year,
    )


def ledger_page_calendar_years(
    academic_start_year,
    school_year=None,
    adult_year=None,
):
    if school_year not in (None, ""):
        start_year = ledger_calendar_year(
            academic_start_year,
            school_year,
        )

        if start_year is None:
            return set()

        return {start_year, historical_year_after(start_year)}

    if adult_year not in (None, ""):
        calendar_year = ledger_adult_calendar_year(
            academic_start_year,
            adult_year,
        )

        if calendar_year is None:
            return set()

        if int(adult_year) == 1:
            return {
                calendar_year,
                historical_year_after(calendar_year),
            }

        return {calendar_year}

    return set()


def ledger_month_calendar_year(
    development_year_start,
    month,
):
    if development_year_start in (None, ""):
        return None

    normalized_month = normalize_ledger_month(month)

    try:
        start_year = int(development_year_start)
    except (TypeError, ValueError):
        return None

    if normalized_month in (0, 7, 8, 9, 10, 11, 12):
        return start_year

    return historical_year_after(start_year)


def random_late_july_day(school_year, book_identity):
    identity_text = (
        f"{int(school_year)}|{str(book_identity or '').strip()}"
    )
    digest = hashlib.sha256(
        identity_text.encode("utf-8")
    ).hexdigest()
    day_span = (
        LEDGER_LATE_JULY_LAST_DAY
        - LEDGER_LATE_JULY_FIRST_DAY
        + 1
    )
    return (
        LEDGER_LATE_JULY_FIRST_DAY
        + int(digest[:8], 16) % day_span
    )


def automatic_allowance_entry(
    school_year,
    month,
    amount_sickles,
    academic_start_year=None,
):
    normalized_school_year = int(school_year)
    normalized_month = normalize_ledger_month(month)
    return normalize_ledger_entry(
        {
            "entry_id": (
                f"allowance:{normalized_school_year}:"
                f"{normalized_month}"
            ),
            "school_year": normalized_school_year,
            "calendar_year": ledger_month_calendar_year(
                ledger_calendar_year(
                    academic_start_year,
                    normalized_school_year,
                ),
                normalized_month,
            ),
            "month": normalized_month,
            "day": 1,
            "item": "Monthly allowance",
            "amount_sickles": int(amount_sickles),
            "kind": LEDGER_KIND_EARNED,
            "note": "Received at the beginning of the month",
            "automatic_source": LEDGER_SOURCE_ALLOWANCE,
        }
    )


def automatic_starting_allowance_entry(
    school_year,
    amount_sickles,
    academic_start_year=None,
):
    normalized_school_year = int(school_year)
    return normalize_ledger_entry(
        {
            "entry_id": "starting-allowance",
            "school_year": normalized_school_year,
            "calendar_year": ledger_calendar_year(
                academic_start_year,
                normalized_school_year,
            ),
            "month": LEDGER_YEAR_START_MONTH,
            "day": 1,
            "item": "starting allowance",
            "amount_sickles": int(amount_sickles),
            "kind": LEDGER_KIND_EARNED,
            "note": "Wealth × generosity Galleons",
            "automatic_source": LEDGER_SOURCE_STARTING_ALLOWANCE,
        }
    )


def automatic_school_book_entry(
    school_year,
    book,
    academic_start_year=None,
):
    if not isinstance(book, dict):
        raise TypeError("A school-book ledger entry needs a book.")

    name = str(book.get("name", "") or "").strip()
    identity = ledger_book_identity(book)

    if not name or not identity:
        raise ValueError("A school-book ledger entry needs a named book.")

    normalized_school_year = int(school_year)
    identity_digest = hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()[:20]
    return normalize_ledger_entry(
        {
            "entry_id": (
                f"school-book:{normalized_school_year}:"
                f"{identity_digest}"
            ),
            "school_year": normalized_school_year,
            "calendar_year": ledger_month_calendar_year(
                ledger_calendar_year(
                    academic_start_year,
                    normalized_school_year,
                ),
                7,
            ),
            "month": 7,
            "day": random_late_july_day(
                normalized_school_year,
                identity,
            ),
            "item": name,
            "amount_sickles": 0,
            "kind": LEDGER_KIND_NEUTRAL,
            "note": "purchased by caregivers",
            "automatic_source": LEDGER_SOURCE_SCHOOL_BOOK,
            "book_record_id": str(
                book.get("record_id", "") or ""
            ).strip(),
        }
    )


def merge_automatic_ledger_entry(
    expected_entry,
    existing_entry,
):
    normalized_expected = normalize_ledger_entry(expected_entry)

    if existing_entry is None:
        return normalized_expected

    normalized_existing = normalize_ledger_entry(existing_entry)
    merged = deepcopy(normalized_expected)

    for field_name in (
        "calendar_year",
        "month",
        "day",
        "item",
        "amount_sickles",
        "kind",
        "note",
        "suppressed",
    ):
        merged[field_name] = normalized_existing[field_name]

    return normalize_ledger_entry(merged)


def reconcile_school_ledger_entries(
    entries,
    school_year_records,
    monthly_allowance_sickles,
    academic_start_year=None,
):
    normalized_entries = normalize_ledger_entries(entries)
    visible_year_records = []

    for record in school_year_records or []:
        if not isinstance(record, dict):
            continue

        try:
            school_year = int(record.get("year", 0) or 0)
        except (TypeError, ValueError):
            continue

        if 1 <= school_year <= 7:
            visible_year_records.append(record)

    visible_years = {
        int(record["year"])
        for record in visible_year_records
    }
    existing_by_id = {
        entry["entry_id"]: entry
        for entry in normalized_entries
    }
    retained_manual_entries = [
        entry
        for entry in normalized_entries
        if not entry["automatic_source"]
        and entry["school_year"] in visible_years
    ]
    expected_automatic_entries = []

    for record in visible_year_records:
        school_year = int(record["year"])

        if monthly_allowance_sickles is not None:
            allowance_months = (
                FIRST_LEDGER_YEAR_ALLOWANCE_MONTHS
                if school_year == 1
                else LEDGER_YEAR_MONTHS
            )

            for month in allowance_months:
                expected_entry = automatic_allowance_entry(
                    school_year,
                    month,
                    monthly_allowance_sickles,
                    academic_start_year,
                )
                existing_entry = existing_by_id.get(
                    expected_entry["entry_id"]
                )
                expected_automatic_entries.append(
                    merge_automatic_ledger_entry(
                        expected_entry,
                        existing_entry,
                    )
                )

        seen_assigned_books = set()

        for book in record.get("assigned_books", []) or []:
            identity = ledger_book_identity(book)

            if not identity or identity in seen_assigned_books:
                continue

            seen_assigned_books.add(identity)
            expected_entry = automatic_school_book_entry(
                school_year,
                book,
                academic_start_year,
            )
            expected_automatic_entries.append(
                merge_automatic_ledger_entry(
                    expected_entry,
                    existing_by_id.get(
                        expected_entry["entry_id"]
                    ),
                )
            )

    return normalize_ledger_entries(
        retained_manual_entries + expected_automatic_entries
    )


def reconcile_development_ledger_entries(
    entries,
    school_year_records,
    adult_year_records,
    monthly_allowance_sickles,
    starting_allowance_sickles,
    academic_start_year=None,
):
    normalized_entries = normalize_ledger_entries(entries)
    visible_school_records = []
    visible_adult_records = []

    for record in school_year_records or []:
        if not isinstance(record, dict):
            continue

        try:
            school_year = int(record.get("year", 0) or 0)
        except (TypeError, ValueError):
            continue

        if 1 <= school_year <= 7:
            visible_school_records.append(record)

    for record in adult_year_records or []:
        if not isinstance(record, dict):
            continue

        try:
            adult_year = int(record.get("adult_year", 0) or 0)
        except (TypeError, ValueError):
            continue

        if adult_year >= 1:
            visible_adult_records.append(record)

    visible_school_years = {
        int(record["year"])
        for record in visible_school_records
    }
    visible_adult_years = {
        int(record["adult_year"])
        for record in visible_adult_records
    }
    visible_calendar_years = set()

    for record in visible_school_records:
        visible_calendar_years.update(
            ledger_page_calendar_years(
                academic_start_year,
                school_year=int(record["year"]),
            )
        )

    for record in visible_adult_records:
        visible_calendar_years.update(
            ledger_page_calendar_years(
                academic_start_year,
                adult_year=int(record["adult_year"]),
            )
        )
    existing_by_id = {
        entry["entry_id"]: entry
        for entry in normalized_entries
    }
    retained_manual_entries = []

    for entry in normalized_entries:
        if entry["automatic_source"]:
            continue

        retained_entry = deepcopy(entry)

        if retained_entry["school_year"] in visible_school_years:
            retained_entry["calendar_year"] = (
                ledger_month_calendar_year(
                    ledger_calendar_year(
                        academic_start_year,
                        retained_entry["school_year"],
                    ),
                    retained_entry["month"],
                )
            )
            retained_manual_entries.append(retained_entry)
            continue

        if retained_entry["adult_year"] in visible_adult_years:
            adult_year = retained_entry["adult_year"]
            adult_calendar_year = ledger_adult_calendar_year(
                academic_start_year,
                adult_year,
            )

            if adult_year == 1:
                allowed_years = ledger_page_calendar_years(
                    academic_start_year,
                    adult_year=adult_year,
                )

                if retained_entry["calendar_year"] not in allowed_years:
                    retained_entry["calendar_year"] = (
                        ledger_month_calendar_year(
                            adult_calendar_year,
                            retained_entry["month"],
                        )
                    )
            else:
                retained_entry["calendar_year"] = (
                    adult_calendar_year
                )

            retained_manual_entries.append(retained_entry)
            continue

        if (
            retained_entry["school_year"] is None
            and retained_entry["adult_year"] is None
            and retained_entry["calendar_year"] in visible_calendar_years
        ):
            retained_manual_entries.append(retained_entry)
    expected_automatic_entries = []

    for record in visible_school_records:
        school_year = int(record["year"])

        if (
            school_year == 1
            and starting_allowance_sickles is not None
        ):
            expected_entry = automatic_starting_allowance_entry(
                school_year,
                starting_allowance_sickles,
                academic_start_year,
            )
            existing_entry = existing_by_id.get(
                expected_entry["entry_id"]
            )
            expected_automatic_entries.append(
                merge_automatic_ledger_entry(
                    expected_entry,
                    existing_entry,
                )
            )

        if monthly_allowance_sickles is not None:
            allowance_months = (
                FIRST_LEDGER_YEAR_ALLOWANCE_MONTHS
                if school_year == 1
                else LEDGER_YEAR_MONTHS
            )

            for month in allowance_months:
                expected_entry = automatic_allowance_entry(
                    school_year,
                    month,
                    monthly_allowance_sickles,
                    academic_start_year,
                )
                existing_entry = existing_by_id.get(
                    expected_entry["entry_id"]
                )
                expected_automatic_entries.append(
                    merge_automatic_ledger_entry(
                        expected_entry,
                        existing_entry,
                    )
                )

        seen_assigned_books = set()

        for book in record.get("assigned_books", []) or []:
            identity = ledger_book_identity(book)

            if not identity or identity in seen_assigned_books:
                continue

            seen_assigned_books.add(identity)
            expected_entry = automatic_school_book_entry(
                school_year,
                book,
                academic_start_year,
            )
            expected_automatic_entries.append(
                merge_automatic_ledger_entry(
                    expected_entry,
                    existing_by_id.get(
                        expected_entry["entry_id"]
                    ),
                )
            )

    return normalize_ledger_entries(
        retained_manual_entries + expected_automatic_entries
    )


def new_manual_ledger_entry(
    school_year,
    month,
    item,
    amount_sickles,
    kind,
    note="",
    calendar_year=None,
    day=1,
):
    return normalize_ledger_entry(
        {
            "entry_id": str(uuid.uuid4()),
            "school_year": school_year,
            "adult_year": None,
            "calendar_year": calendar_year,
            "month": month,
            "day": day,
            "item": item,
            "amount_sickles": amount_sickles,
            "kind": kind,
            "note": note,
        }
    )


def new_manual_calendar_ledger_entry(
    calendar_year,
    month,
    item,
    amount_sickles,
    kind,
    note="",
    school_year=None,
    adult_year=None,
    day=1,
):
    return normalize_ledger_entry(
        {
            "entry_id": str(uuid.uuid4()),
            "school_year": school_year,
            "adult_year": adult_year,
            "calendar_year": calendar_year,
            "month": month,
            "day": day,
            "item": item,
            "amount_sickles": amount_sickles,
            "kind": kind,
            "note": note,
        }
    )


def ledger_entries_for_school_year(entries, school_year):
    normalized_school_year = int(school_year)
    return [
        deepcopy(entry)
        for entry in visible_ledger_entries(entries)
        if entry["school_year"] == normalized_school_year
    ]


def ledger_entries_for_calendar_year(
    entries,
    calendar_year,
    school_year=None,
    adult_year=None,
):
    normalized_calendar_year = (
        int(calendar_year)
        if calendar_year not in (None, "")
        else None
    )
    normalized_school_year = (
        int(school_year)
        if school_year not in (None, "")
        else None
    )
    normalized_adult_year = (
        int(adult_year)
        if adult_year not in (None, "")
        else None
    )
    normalized_entries = visible_ledger_entries(entries)

    if normalized_school_year is not None:
        return [
            deepcopy(entry)
            for entry in normalized_entries
            if entry["school_year"] == normalized_school_year
        ]

    if normalized_adult_year is not None:
        return [
            deepcopy(entry)
            for entry in normalized_entries
            if entry["adult_year"] == normalized_adult_year
        ]

    return [
        deepcopy(entry)
        for entry in normalized_entries
        if (
            normalized_calendar_year is not None
            and entry["calendar_year"] == normalized_calendar_year
        )
    ]


def ledger_balance_sickles(entries):
    balance = 0

    for entry in visible_ledger_entries(entries):
        if entry["kind"] == LEDGER_KIND_EARNED:
            balance += entry["amount_sickles"]
        elif entry["kind"] == LEDGER_KIND_BOUGHT:
            balance -= entry["amount_sickles"]

    return balance


def ledger_running_balances(entries):
    running_balance = 0
    balances_by_entry_id = {}

    for entry in visible_ledger_entries(entries):
        if entry["kind"] == LEDGER_KIND_EARNED:
            running_balance += entry["amount_sickles"]
        elif entry["kind"] == LEDGER_KIND_BOUGHT:
            running_balance -= entry["amount_sickles"]

        balances_by_entry_id[entry["entry_id"]] = running_balance

    return balances_by_entry_id


def ledger_entry_date_text(entry):
    normalized_entry = normalize_ledger_entry(entry)
    calendar_year = normalized_entry["calendar_year"]
    month = normalized_entry["month"]
    day = normalized_entry["day"]

    if month == 0:
        return (
            f"{calendar_year} opening"
            if calendar_year is not None
            else "Opening"
        )

    if calendar_year is None:
        return f"{MONTH_NAMES[month - 1]} {day}"

    return f"{calendar_year:04d}-{month:02d}-{day:02d}"


def format_ledger_currency(sickles):
    normalized_sickles = abs(int(sickles))

    if normalized_sickles == 0:
        return "$0"

    if normalized_sickles <= SICKLES_PER_GALLEON:
        unit = "sickle" if normalized_sickles == 1 else "sickles"
        return f"{normalized_sickles} {unit}"

    galleons, remaining_sickles = divmod(
        normalized_sickles,
        SICKLES_PER_GALLEON,
    )
    galleon_unit = "Galleon" if galleons == 1 else "Galleons"

    if remaining_sickles == 0:
        return f"{galleons} {galleon_unit}"

    sickle_unit = (
        "sickle" if remaining_sickles == 1 else "sickles"
    )
    return (
        f"{galleons} {galleon_unit} and "
        f"{remaining_sickles} {sickle_unit}"
    )


def format_signed_ledger_currency(sickles):
    normalized_sickles = int(sickles)
    amount_text = format_ledger_currency(normalized_sickles)

    if normalized_sickles > 0:
        return f"+{amount_text}"

    if normalized_sickles < 0:
        return f"−{amount_text}"

    return amount_text


def ledger_amount_text(entry):
    normalized_entry = normalize_ledger_entry(entry)
    amount_text = format_ledger_currency(
        normalized_entry["amount_sickles"]
    )

    if normalized_entry["amount_sickles"] == 0:
        return amount_text

    if normalized_entry["kind"] == LEDGER_KIND_EARNED:
        return f"+{amount_text}"

    if normalized_entry["kind"] == LEDGER_KIND_BOUGHT:
        return f"−{amount_text}"

    return amount_text
