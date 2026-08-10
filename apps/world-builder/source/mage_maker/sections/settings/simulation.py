from copy import deepcopy
from datetime import date


DATABASE_DATE_SETTING_KEY = "database_date"
MORTALITY_TABLE_SETTING_KEY = "mortality_table"
DEFAULT_DATABASE_DATE = {
    "year": 2000,
    "month": 7,
    "day": 31,
}
MORTALITY_AGES = tuple(range(70, 150))
MORTALITY_MAXIMUM_EXACT_AGE = MORTALITY_AGES[-1]
MORTALITY_OLDEST_AGE_LABEL = "150+"
DEFAULT_MORTALITY_TABLE = {
    "70": 0.0040,
    "71": 0.0042,
    "72": 0.0044,
    "73": 0.0047,
    "74": 0.0049,
    "75": 0.0051,
    "76": 0.0053,
    "77": 0.0055,
    "78": 0.0058,
    "79": 0.0060,
    "80": 0.0062,
    "81": 0.0064,
    "82": 0.0066,
    "83": 0.0069,
    "84": 0.0071,
    "85": 0.0072,
    "86": 0.0118,
    "87": 0.0165,
    "88": 0.0211,
    "89": 0.0257,
    "90": 0.0304,
    "91": 0.0350,
    "92": 0.0396,
    "93": 0.0443,
    "94": 0.0489,
    "95": 0.0535,
    "96": 0.0582,
    "97": 0.0628,
    "98": 0.0674,
    "99": 0.0721,
    "100": 0.0722,
    "101": 0.0723,
    "102": 0.0724,
    "103": 0.0725,
    "104": 0.0726,
    "105": 0.0728,
    "106": 0.0729,
    "107": 0.0730,
    "108": 0.0731,
    "109": 0.0732,
    "110": 0.0733,
    "111": 0.0735,
    "112": 0.0736,
    "113": 0.0737,
    "114": 0.0738,
    "115": 0.0739,
    "116": 0.0741,
    "117": 0.0742,
    "118": 0.0743,
    "119": 0.0744,
    "120": 0.0745,
    "121": 0.0746,
    "122": 0.0748,
    "123": 0.0749,
    "124": 0.0750,
    "125": 0.0751,
    "126": 0.0752,
    "127": 0.0754,
    "128": 0.0755,
    "129": 0.0756,
    "130": 0.0757,
    "131": 0.0759,
    "132": 0.0760,
    "133": 0.0762,
    "134": 0.0764,
    "135": 0.0765,
    "136": 0.0767,
    "137": 0.0769,
    "138": 0.0771,
    "139": 0.0772,
    "140": 0.0774,
    "141": 0.0776,
    "142": 0.0777,
    "143": 0.0779,
    "144": 0.0781,
    "145": 0.0783,
    "146": 0.0784,
    "147": 0.0786,
    "148": 0.0788,
    "149": 0.0789,
    MORTALITY_OLDEST_AGE_LABEL: 0.0790,
}


def normalize_database_date(value):
    candidate = (
        dict(value)
        if isinstance(value, dict)
        else deepcopy(DEFAULT_DATABASE_DATE)
        if value in (None, "")
        else None
    )

    if candidate is None:
        raise TypeError("Database date must be an object.")

    normalized = {}

    for field_name in ("year", "month", "day"):
        field_value = candidate.get(
            field_name,
            DEFAULT_DATABASE_DATE[field_name],
        )

        if isinstance(field_value, bool):
            raise ValueError(
                f"Database date {field_name} must be a whole number."
            )

        try:
            normalized[field_name] = int(field_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"Database date {field_name} must be a whole number."
            ) from error

    try:
        date(
            normalized["year"],
            normalized["month"],
            normalized["day"],
        )
    except ValueError as error:
        raise ValueError(
            "Database date must be a valid date from year 1 through 9999."
        ) from error

    return normalized


def normalize_mortality_probability(value):
    if isinstance(value, bool):
        raise ValueError(
            "Annual death probability must be a number from 0 through 1."
        )

    try:
        probability = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Annual death probability must be a number from 0 through 1."
        ) from error

    if not 0 <= probability <= 1:
        raise ValueError(
            "Annual death probability must be a number from 0 through 1."
        )

    return round(probability, 4)


def normalize_mortality_table(value):
    candidate = dict(value) if isinstance(value, dict) else {}
    normalized = {}

    for age in MORTALITY_AGES:
        key = str(age)
        normalized[key] = normalize_mortality_probability(
            candidate.get(key, DEFAULT_MORTALITY_TABLE[key])
        )

    normalized[MORTALITY_OLDEST_AGE_LABEL] = (
        normalize_mortality_probability(
            candidate.get(
                MORTALITY_OLDEST_AGE_LABEL,
                DEFAULT_MORTALITY_TABLE[
                    MORTALITY_OLDEST_AGE_LABEL
                ],
            )
        )
    )
    return normalized


def mortality_table_rows(value):
    table = normalize_mortality_table(value)
    rows = [
        (str(age), table[str(age)])
        for age in MORTALITY_AGES
    ]
    rows.append(
        (
            MORTALITY_OLDEST_AGE_LABEL,
            table[MORTALITY_OLDEST_AGE_LABEL],
        )
    )
    return rows


def mortality_probability_for_age(age, value):
    try:
        normalized_age = int(age)
    except (TypeError, ValueError) as error:
        raise ValueError("Mortality age must be a whole number.") from error

    if normalized_age < MORTALITY_AGES[0]:
        return 0.0

    table = normalize_mortality_table(value)
    key = (
        str(normalized_age)
        if normalized_age <= MORTALITY_MAXIMUM_EXACT_AGE
        else MORTALITY_OLDEST_AGE_LABEL
    )
    return table[key]


def database_date_text(value):
    normalized = normalize_database_date(value)
    return (
        f"{normalized['year']:04d}-"
        f"{normalized['month']:02d}-"
        f"{normalized['day']:02d}"
    )


def development_cycle_year(value):
    normalized = normalize_database_date(value)
    if (normalized["month"], normalized["day"]) < (7, 1):
        return normalized["year"] - 1

    return normalized["year"]
