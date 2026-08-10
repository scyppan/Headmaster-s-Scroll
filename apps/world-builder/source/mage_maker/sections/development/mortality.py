import random

from mage_maker.sections.settings.simulation import (
    mortality_probability_for_age,
    normalize_database_date,
    normalize_mortality_table,
)


MORTALITY_START_AGE = 70


def normalize_mortality_checked_through_age(value):
    if value in (None, ""):
        return None

    if isinstance(value, bool):
        raise ValueError(
            "Mortality checked-through age must be a whole number."
        )

    try:
        age = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Mortality checked-through age must be a whole number."
        ) from error

    if age < MORTALITY_START_AGE:
        return None

    return age


def age_reached_by_database_date(
    birth_year,
    birth_month,
    birth_day,
    database_date,
):
    if birth_year in (None, "") or isinstance(birth_year, bool):
        return None

    try:
        normalized_birth_year = int(birth_year)
    except (TypeError, ValueError):
        return None

    target = normalize_database_date(database_date)
    age = target["year"] - normalized_birth_year

    if birth_month not in (None, ""):
        try:
            normalized_birth_month = int(birth_month)
        except (TypeError, ValueError):
            normalized_birth_month = None

        if normalized_birth_month is not None:
            normalized_birth_day = 1

            if birth_day not in (None, ""):
                try:
                    normalized_birth_day = int(birth_day)
                except (TypeError, ValueError):
                    normalized_birth_day = 1

            if (
                target["month"],
                target["day"],
            ) < (
                normalized_birth_month,
                normalized_birth_day,
            ):
                age -= 1

    return max(-1, age)


def simulate_mortality_to_database_date(
    person,
    checked_through_age,
    mortality_table,
    database_date,
    randomizer=None,
):
    person_values = person if isinstance(person, dict) else {}
    previous_checked_age = normalize_mortality_checked_through_age(
        checked_through_age
    )
    result = {
        "checked_through_age": previous_checked_age,
        "died": False,
        "death_age": None,
        "death_year": None,
    }

    if bool(person_values.get("deceased")):
        return result

    age_reached = age_reached_by_database_date(
        person_values.get("birth_year"),
        person_values.get("birth_month"),
        person_values.get("birth_day"),
        database_date,
    )

    if age_reached is None or age_reached < MORTALITY_START_AGE:
        return result

    selected_randomizer = randomizer or random
    table = normalize_mortality_table(mortality_table)
    first_age = max(
        MORTALITY_START_AGE,
        (
            previous_checked_age + 1
            if previous_checked_age is not None
            else MORTALITY_START_AGE
        ),
    )

    for age in range(first_age, age_reached + 1):
        probability = mortality_probability_for_age(age, table)
        result["checked_through_age"] = age

        if selected_randomizer.random() >= probability:
            continue

        result["died"] = True
        result["death_age"] = age
        result["death_year"] = (
            int(person_values["birth_year"]) + age
        )
        return result

    return result
