import re


SICKLES_PER_GALLEON = 17
KNUTS_PER_SICKLE = 29


def currency_component_input_is_valid(proposed_value, maximum=""):
    proposed_text = str(proposed_value or "")

    if not proposed_text:
        return True

    if not proposed_text.isdigit():
        return False

    maximum_text = str(maximum or "").strip()

    if not maximum_text:
        return True

    return int(proposed_text) <= int(maximum_text)


def normalize_currency_component(value, unit_name):
    if value in (None, ""):
        return 0

    if isinstance(value, bool):
        raise ValueError(
            f"Monthly salary {unit_name} must be a whole number."
        )

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"Monthly salary {unit_name} must be a whole number."
        ) from error

    if normalized_value < 0:
        raise ValueError(
            f"Monthly salary {unit_name} cannot be negative."
        )

    return normalized_value


def normalize_monthly_salary(value):
    structured_input = isinstance(value, dict) or (
        isinstance(value, (list, tuple)) and len(value) == 3
    )

    if isinstance(value, dict):
        has_currency_value = any(
            key in value
            for key in (
                "galleons",
                "sickles",
                "knuts",
                "salary_galleons",
                "salary_sickles",
                "salary_knuts",
            )
        )

        if not has_currency_value:
            raise ValueError(
                "A monthly salary must list Galleons, Sickles, and Knuts."
            )

        galleons = normalize_currency_component(
            value.get(
                "galleons",
                value.get("salary_galleons", 0),
            ),
            "Galleons",
        )
        sickles = normalize_currency_component(
            value.get(
                "sickles",
                value.get("salary_sickles", 0),
            ),
            "Sickles",
        )
        knuts = normalize_currency_component(
            value.get(
                "knuts",
                value.get("salary_knuts", 0),
            ),
            "Knuts",
        )
    elif isinstance(value, (list, tuple)) and len(value) == 3:
        galleons = normalize_currency_component(
            value[0],
            "Galleons",
        )
        sickles = normalize_currency_component(
            value[1],
            "Sickles",
        )
        knuts = normalize_currency_component(
            value[2],
            "Knuts",
        )
    elif isinstance(value, bool) or value is None:
        raise ValueError(
            "A monthly salary must list Galleons, Sickles, and Knuts."
        )
    elif isinstance(value, (int, float)):
        galleons = normalize_currency_component(value, "Galleons")
        sickles = 0
        knuts = 0
    else:
        salary_text = str(value or "").strip()

        if not salary_text:
            raise ValueError(
                "A monthly salary must list Galleons, Sickles, and Knuts."
            )

        matches = re.findall(
            r"(-?\d+)\s*(Galleons?|Sickles?|Knuts?)",
            salary_text,
            flags=re.IGNORECASE,
        )

        if matches:
            galleons = 0
            sickles = 0
            knuts = 0

            for amount_text, unit_text in matches:
                amount = normalize_currency_component(
                    amount_text,
                    unit_text.title(),
                )
                normalized_unit = unit_text.casefold()

                if normalized_unit.startswith("galleon"):
                    galleons += amount
                elif normalized_unit.startswith("sickle"):
                    sickles += amount
                else:
                    knuts += amount
        else:
            galleons = normalize_currency_component(
                salary_text,
                "Galleons",
            )
            sickles = 0
            knuts = 0

    if structured_input and sickles >= SICKLES_PER_GALLEON:
        raise ValueError("Monthly salary Sickles must be between 0 and 16.")

    if structured_input and knuts >= KNUTS_PER_SICKLE:
        raise ValueError("Monthly salary Knuts must be between 0 and 28.")

    total_knuts = (
        (
            galleons * SICKLES_PER_GALLEON
            + sickles
        )
        * KNUTS_PER_SICKLE
        + knuts
    )
    normalized_galleons, remaining_knuts = divmod(
        total_knuts,
        SICKLES_PER_GALLEON * KNUTS_PER_SICKLE,
    )
    normalized_sickles, normalized_knuts = divmod(
        remaining_knuts,
        KNUTS_PER_SICKLE,
    )
    return {
        "galleons": normalized_galleons,
        "sickles": normalized_sickles,
        "knuts": normalized_knuts,
        "period": "month",
    }


def monthly_salary_identity(value):
    normalized = normalize_monthly_salary(value)
    return (
        normalized["galleons"],
        normalized["sickles"],
        normalized["knuts"],
    )


def format_monthly_salary(value):
    normalized = normalize_monthly_salary(value)
    return (
        f"{normalized['galleons']} Galleons, "
        f"{normalized['sickles']} Sickles, "
        f"{normalized['knuts']} Knuts per month"
    )
