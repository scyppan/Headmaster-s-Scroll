import json
import os
from pathlib import Path


EARLIEST_CALCULATION_YEAR = -9999
LATEST_CALCULATION_YEAR = 9999


class PeriodDefinitionError(ValueError):
    pass


def default_period_definitions_path():
    data_directory = os.environ.get("HEADMASTERS_SCROLL_DATA_DIRECTORY")
    if data_directory:
        return Path(data_directory) / "periods.json"
    return Path(__file__).resolve().parents[3] / "data" / "periods.json"


def load_period_definitions(path=None):
    definitions_path = (
        Path(path)
        if path is not None
        else default_period_definitions_path()
    )

    try:
        with definitions_path.open("r", encoding="utf-8") as definitions_file:
            data = json.load(definitions_file)
    except OSError as error:
        raise PeriodDefinitionError(
            f"Could not open period definitions: {definitions_path}"
        ) from error
    except json.JSONDecodeError as error:
        raise PeriodDefinitionError(
            f"Period definitions are not valid JSON: {definitions_path}"
        ) from error

    if not isinstance(data, dict):
        raise PeriodDefinitionError("Period definitions must be a JSON object.")

    groups = data.get("period_groups")

    if not isinstance(groups, list) or not groups:
        raise PeriodDefinitionError(
            "Period definitions must include at least one period group."
        )

    definitions = []
    used_names = set()

    for group in groups:
        if not isinstance(group, dict):
            raise PeriodDefinitionError("Every period group must be an object.")

        group_name = str(group.get("name", "") or "").strip()
        group_descriptor = str(group.get("descriptor", "") or "").strip()
        periods = group.get("periods")

        if not isinstance(periods, list) or not periods:
            group_label = group_name or "The first period group"
            raise PeriodDefinitionError(
                f"{group_label} must include at least one period."
            )

        for period in periods:
            normalized = normalize_period_definition(
                period,
                group_name,
                group_descriptor,
            )
            name_key = normalized["name"].casefold()

            if name_key in used_names:
                raise PeriodDefinitionError(
                    f'Duplicate period name: {normalized["name"]}'
                )

            used_names.add(name_key)
            definitions.append(normalized)

    return definitions


def normalize_period_definition(period, group_name="", group_descriptor=""):
    if not isinstance(period, dict):
        raise PeriodDefinitionError("Every period must be an object.")

    name = str(period.get("name", "") or "").strip()

    if not name:
        raise PeriodDefinitionError("Every period must have a name.")

    start_year = normalize_period_boundary(
        period.get("start_year"),
        "start",
        name,
    )
    end_year = normalize_period_boundary(
        period.get("end_year"),
        "end",
        name,
    )
    calculation_start_year = (
        EARLIEST_CALCULATION_YEAR
        if isinstance(start_year, str)
        else start_year
    )
    calculation_end_year = (
        LATEST_CALCULATION_YEAR
        if isinstance(end_year, str)
        else end_year
    )

    if calculation_end_year < calculation_start_year:
        raise PeriodDefinitionError(
            f'The ending year for "{name}" cannot be earlier than its starting year.'
        )

    return {
        "name": name,
        "start_year": start_year,
        "end_year": end_year,
        "calculation_start_year": calculation_start_year,
        "calculation_end_year": calculation_end_year,
        "descriptor": str(period.get("descriptor", "") or "").strip(),
        "group_name": str(group_name or "").strip(),
        "group_descriptor": str(group_descriptor or "").strip(),
    }


def normalize_period_boundary(value, boundary_name, period_name):
    if isinstance(value, bool) or value is None:
        raise PeriodDefinitionError(
            f'"{period_name}" must have a valid {boundary_name} year.'
        )

    if isinstance(value, str):
        text = value.strip()
        lowered = text.casefold()

        if boundary_name == "start" and lowered == "prehistory":
            return "Prehistory"

        if boundary_name == "end" and lowered == "future":
            return "future"

        try:
            value = int(text)
        except ValueError as error:
            raise PeriodDefinitionError(
                f'"{period_name}" has an invalid {boundary_name} year.'
            ) from error

    try:
        normalized = int(value)
    except (TypeError, ValueError) as error:
        raise PeriodDefinitionError(
            f'"{period_name}" has an invalid {boundary_name} year.'
        ) from error

    if (
        normalized == 0
        or normalized < EARLIEST_CALCULATION_YEAR
        or normalized > LATEST_CALCULATION_YEAR
    ):
        raise PeriodDefinitionError(
            f'"{period_name}" has an invalid {boundary_name} year.'
        )

    return normalized


def period_year_text(period):
    if not isinstance(period, dict):
        return ""

    start_year = str(period.get("start_year", "") or "")
    end_year = str(period.get("end_year", "") or "")

    if not start_year or not end_year:
        return ""

    return f"{start_year} to {end_year}"
