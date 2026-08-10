import random

from mage_maker.sections.development.initial_bonuses import (
    initial_bonus_requirements,
    normalize_initial_bonuses,
)
from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    normalize_blood_status,
    normalize_developmental_environment,
    normalize_parental_values,
)


CHARACTERISTIC_NAMES = (
    "creativity",
    "equanimity",
    "charisma",
    "attractiveness",
    "strength",
    "agility",
    "intellect",
    "willpower",
    "fortitude",
)
CHARACTERISTIC_BASE_VALUE = 1
CHARACTERISTIC_MAXIMUM_VALUE = 5
CHARACTERISTIC_POINTS_TO_SPEND = 8
CHARACTERISTIC_REQUIRED_TOTAL = (
    len(CHARACTERISTIC_NAMES) * CHARACTERISTIC_BASE_VALUE
    + CHARACTERISTIC_POINTS_TO_SPEND
)


def randomized_characteristics():
    randomized_values = {
        field_name: CHARACTERISTIC_BASE_VALUE
        for field_name in CHARACTERISTIC_NAMES
    }

    for _ in range(CHARACTERISTIC_POINTS_TO_SPEND):
        available_fields = [
            field_name
            for field_name in CHARACTERISTIC_NAMES
            if (
                randomized_values[field_name]
                < CHARACTERISTIC_MAXIMUM_VALUE
            )
        ]
        selected_field = random.choice(available_fields)
        randomized_values[selected_field] += 1

    return normalize_characteristics(
        randomized_values,
        allow_uninitialized=False,
    )


def normalize_characteristic_name(value, allow_blank=False):
    normalized_value = str(value or "").strip().casefold()
    names_by_key = {
        field_name.casefold(): field_name
        for field_name in CHARACTERISTIC_NAMES
    }
    characteristic = names_by_key.get(normalized_value)

    if characteristic is not None:
        return characteristic

    if allow_blank and not normalized_value:
        return ""

    valid_values = ", ".join(
        field_name.title()
        for field_name in CHARACTERISTIC_NAMES
    )
    raise ValueError(
        f"Characteristic buy must be one of: {valid_values}."
    )


def characteristic_school_year_sort_key(record):
    try:
        return int(record.get("year", 0) or 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def characteristic_values_through_school_year(
    initial_characteristics,
    school_year_records,
    through_year=None,
):
    values = normalize_characteristics(
        initial_characteristics,
        allow_uninitialized=False,
    )
    maximum_year = (
        int(through_year)
        if through_year not in (None, "")
        else None
    )
    ordered_records = sorted(
        (
            record
            for record in school_year_records or []
            if isinstance(record, dict)
        ),
        key=characteristic_school_year_sort_key,
    )

    for record in ordered_records:
        try:
            year_number = int(record.get("year", 0) or 0)
        except (TypeError, ValueError):
            continue

        if maximum_year is not None and year_number > maximum_year:
            continue

        characteristic = normalize_characteristic_name(
            record.get("characteristic"),
            allow_blank=True,
        )

        if not characteristic:
            continue

        if values[characteristic] >= CHARACTERISTIC_MAXIMUM_VALUE:
            raise ValueError(
                f"{characteristic.title()} cannot exceed "
                f"{CHARACTERISTIC_MAXIMUM_VALUE}."
            )

        values[characteristic] += 1

    return values


def available_characteristic_buys(
    initial_characteristics,
    school_year_records,
    before_year,
):
    values = characteristic_values_through_school_year(
        initial_characteristics,
        school_year_records,
        int(before_year) - 1,
    )
    return tuple(
        field_name
        for field_name in CHARACTERISTIC_NAMES
        if values[field_name] < CHARACTERISTIC_MAXIMUM_VALUE
    )


def editable_characteristic_buys(
    initial_characteristics,
    school_year_records,
    year_number,
):
    values = normalize_characteristics(
        initial_characteristics,
        allow_uninitialized=False,
    )

    for record in school_year_records or []:
        if not isinstance(record, dict):
            continue

        try:
            record_year = int(record.get("year", 0) or 0)
        except (TypeError, ValueError):
            continue

        if record_year == int(year_number):
            continue

        characteristic = normalize_characteristic_name(
            record.get("characteristic"),
            allow_blank=True,
        )

        if characteristic:
            values[characteristic] += 1

    return tuple(
        field_name
        for field_name in CHARACTERISTIC_NAMES
        if values[field_name] < CHARACTERISTIC_MAXIMUM_VALUE
    )


def characteristic_value_after_buy(
    initial_characteristics,
    school_year_records,
    year_number,
):
    record = next(
        (
            stored_record
            for stored_record in school_year_records or []
            if isinstance(stored_record, dict)
            and int(stored_record.get("year", 0) or 0)
            == int(year_number)
        ),
        None,
    )

    if record is None:
        return None

    characteristic = normalize_characteristic_name(
        record.get("characteristic"),
        allow_blank=True,
    )

    if not characteristic:
        return None

    values = characteristic_values_through_school_year(
        initial_characteristics,
        school_year_records,
        int(year_number),
    )
    return values[characteristic]


def normalize_characteristics(value, allow_uninitialized=True):
    if value in (None, "", {}):
        if allow_uninitialized:
            return None

        raise ValueError("Characteristics have not been assigned.")

    if not isinstance(value, dict):
        raise TypeError("Characteristics must be a dictionary.")

    normalized = {}

    for field_name in CHARACTERISTIC_NAMES:
        candidate = value.get(
            field_name,
            value.get(field_name.title()),
        )

        if candidate in (None, ""):
            candidate = CHARACTERISTIC_BASE_VALUE

        if isinstance(candidate, bool):
            raise ValueError(
                f"{field_name.title()} must be a whole number."
            )

        try:
            normalized_value = int(candidate)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"{field_name.title()} must be a whole number."
            ) from error

        if (
            isinstance(candidate, float)
            and not candidate.is_integer()
        ):
            raise ValueError(
                f"{field_name.title()} must be a whole number."
            )

        if not (
            CHARACTERISTIC_BASE_VALUE
            <= normalized_value
            <= CHARACTERISTIC_MAXIMUM_VALUE
        ):
            raise ValueError(
                f"{field_name.title()} must be between "
                f"{CHARACTERISTIC_BASE_VALUE} and "
                f"{CHARACTERISTIC_MAXIMUM_VALUE}."
            )

        normalized[field_name] = normalized_value

    assigned_total = sum(normalized.values())

    if assigned_total > CHARACTERISTIC_REQUIRED_TOTAL:
        raise ValueError(
            "Characteristics cannot use more than "
            f"{CHARACTERISTIC_POINTS_TO_SPEND} starting points."
        )

    if (
        not allow_uninitialized
        and assigned_total != CHARACTERISTIC_REQUIRED_TOTAL
    ):
        raise ValueError(
            "Spend all "
            f"{CHARACTERISTIC_POINTS_TO_SPEND} characteristic points."
        )

    return normalized


def characteristic_points_remaining(value):
    normalized = normalize_characteristics(value)

    if normalized is None:
        return CHARACTERISTIC_POINTS_TO_SPEND

    return CHARACTERISTIC_REQUIRED_TOTAL - sum(normalized.values())


def characteristics_are_complete(value):
    try:
        normalized = normalize_characteristics(
            value,
            allow_uninitialized=False,
        )
    except (TypeError, ValueError):
        return False

    return sum(normalized.values()) == CHARACTERISTIC_REQUIRED_TOTAL


def incomplete_initial_value_names(person):
    person_values = person if isinstance(person, dict) else {}
    incomplete_values = []

    try:
        blood_status = normalize_blood_status(
            person_values.get("blood_status")
        )
    except (TypeError, ValueError):
        blood_status = None
        incomplete_values.append("blood status")

    try:
        parental_values = normalize_parental_values(
            person_values.get("parental_values")
        )
    except (TypeError, ValueError):
        parental_values = None

    if parental_values is None:
        incomplete_values.append("parental values")

    requirements = None

    if blood_status is not None:
        try:
            developmental_environment = (
                normalize_developmental_environment(
                    person_values.get("developmental_environment"),
                    blood_status,
                )
            )
            requirements = initial_bonus_requirements(
                blood_status,
                developmental_environment,
                parental_values,
            )
        except (TypeError, ValueError):
            if blood_status == BLOOD_STATUS_HALFBLOOD:
                incomplete_values.append(
                    "developmental environment"
                )

    try:
        initial_bonuses = normalize_initial_bonuses(
            person_values.get("initial_bonuses")
        )
    except (TypeError, ValueError):
        initial_bonuses = None

    if requirements is not None:
        selected_skills = (
            initial_bonuses.get("skill_bonuses", [])
            if initial_bonuses is not None
            else []
        )
        selected_traits = (
            initial_bonuses.get("traits", [])
            if initial_bonuses is not None
            else []
        )

        if (
            len(selected_skills)
            != requirements["skill_bonus_count"]
        ):
            incomplete_values.append("initial skill bonuses")

        if len(selected_traits) != requirements["trait_count"]:
            incomplete_values.append("initial traits")

    if not characteristics_are_complete(
        person_values.get("characteristics")
    ):
        incomplete_values.append("characteristics")

    return tuple(incomplete_values)


def initial_values_are_complete(person):
    return not incomplete_initial_value_names(person)
