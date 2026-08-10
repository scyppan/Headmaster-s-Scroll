import json
import os
from pathlib import Path


EARLIEST_CALCULATION_YEAR = -99999
LATEST_CALCULATION_YEAR = 99999


class PeriodDefinitionError(ValueError):
    pass


def default_period_definitions_path():
    data_directory = os.environ.get("HEADMASTERS_SCROLL_DATA_DIRECTORY")
    if data_directory:
        return Path(data_directory) / "periods.json"
    return (
        Path(__file__).resolve().parents[3]
        / "data"
        / "periods"
        / "periods.json"
    )


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


def update_period_descriptor(period_name, descriptor, path=None):
    definitions_path = (
        Path(path)
        if path is not None
        else default_period_definitions_path()
    )
    normalized_period_name = str(period_name or "").strip()
    normalized_descriptor = str(descriptor or "").strip()

    if not normalized_period_name:
        raise PeriodDefinitionError("Select a period before saving its description.")

    load_period_definitions(definitions_path)

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

    matching_period = None

    for group in data.get("period_groups", []):
        for period in group.get("periods", []):
            if (
                str(period.get("name", "") or "").strip().casefold()
                == normalized_period_name.casefold()
            ):
                matching_period = period
                break

        if matching_period is not None:
            break

    if matching_period is None:
        raise PeriodDefinitionError(
            f'Could not find period "{normalized_period_name}".'
        )

    matching_period["descriptor"] = normalized_descriptor
    temporary_path = definitions_path.with_suffix(
        f"{definitions_path.suffix}.tmp"
    )

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as definitions_file:
            json.dump(data, definitions_file, ensure_ascii=False, indent=2)
            definitions_file.write("\n")

        temporary_path.replace(definitions_path)
    except OSError as error:
        try:
            temporary_path.unlink()
        except OSError:
            pass

        raise PeriodDefinitionError(
            f"Could not save period definitions: {definitions_path}"
        ) from error

    return normalized_descriptor


def update_period_definition(
    period_name,
    start_year,
    end_year,
    descriptor,
    path=None,
):
    definitions_path = (
        Path(path)
        if path is not None
        else default_period_definitions_path()
    )
    normalized_period_name = str(period_name or "").strip()
    normalized_descriptor = str(descriptor or "").strip()

    if not normalized_period_name:
        raise PeriodDefinitionError("Select a period before saving it.")

    definitions = load_period_definitions(definitions_path)

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

    period_records = []

    for group in data.get("period_groups", []):
        period_records.extend(group.get("periods", []))

    selected_index = None

    for index, period in enumerate(definitions):
        if period["name"].casefold() == normalized_period_name.casefold():
            selected_index = index
            break

    if selected_index is None:
        raise PeriodDefinitionError(
            f'Could not find period "{normalized_period_name}".'
        )

    normalized_start_year = normalize_period_boundary(
        start_year,
        "start",
        definitions[selected_index]["name"],
    )
    normalized_end_year = normalize_period_boundary(
        end_year,
        "end",
        definitions[selected_index]["name"],
    )

    if isinstance(normalized_start_year, str) and selected_index != 0:
        raise PeriodDefinitionError(
            "Only the first period can begin with Prehistory."
        )

    if (
        isinstance(normalized_end_year, str)
        and selected_index != len(definitions) - 1
    ):
        raise PeriodDefinitionError(
            "Only the final period can end with future."
        )

    start_years = [
        period["start_year"]
        for period in definitions
    ]
    end_years = [
        period["end_year"]
        for period in definitions
    ]

    for index, period in enumerate(definitions):
        if isinstance(period["start_year"], str) and index != 0:
            raise PeriodDefinitionError(
                "Only the first period can begin with Prehistory."
            )

        if (
            isinstance(period["end_year"], str)
            and index != len(definitions) - 1
        ):
            raise PeriodDefinitionError(
                "Only the final period can end with future."
            )

    start_years[selected_index] = normalized_start_year
    end_years[selected_index] = normalized_end_year
    selected_start_calculation_year = period_calculation_year(
        normalized_start_year
    )
    selected_end_calculation_year = period_calculation_year(
        normalized_end_year
    )

    if selected_end_calculation_year <= selected_start_calculation_year:
        raise PeriodDefinitionError(
            f'The ending year for "{definitions[selected_index]["name"]}" '
            "must be later than its starting year."
        )

    next_start_calculation_year = selected_start_calculation_year

    for index in range(selected_index - 1, -1, -1):
        adjusted_end_year = previous_period_year(
            next_start_calculation_year
        )
        current_start_calculation_year = period_calculation_year(
            start_years[index]
        )
        end_years[index] = adjusted_end_year

        if current_start_calculation_year >= adjusted_end_year:
            adjusted_start_year = previous_period_year(adjusted_end_year)
            start_years[index] = adjusted_start_year
            current_start_calculation_year = adjusted_start_year

        next_start_calculation_year = current_start_calculation_year

    previous_end_calculation_year = selected_end_calculation_year

    for index in range(selected_index + 1, len(definitions)):
        adjusted_start_year = next_period_year(
            previous_end_calculation_year
        )
        current_end_calculation_year = period_calculation_year(
            end_years[index]
        )
        start_years[index] = adjusted_start_year

        if current_end_calculation_year <= adjusted_start_year:
            adjusted_end_year = next_period_year(adjusted_start_year)
            end_years[index] = adjusted_end_year
            current_end_calculation_year = adjusted_end_year

        previous_end_calculation_year = current_end_calculation_year

    for index, period_record in enumerate(period_records):
        period_record["start_year"] = start_years[index]
        period_record["end_year"] = end_years[index]

    period_records[selected_index]["descriptor"] = normalized_descriptor
    temporary_path = definitions_path.with_suffix(
        f"{definitions_path.suffix}.tmp"
    )

    try:
        with temporary_path.open(
            "w",
            encoding="utf-8",
            newline="\n",
        ) as definitions_file:
            json.dump(data, definitions_file, ensure_ascii=False, indent=2)
            definitions_file.write("\n")

        temporary_path.replace(definitions_path)
    except OSError as error:
        try:
            temporary_path.unlink()
        except OSError:
            pass

        raise PeriodDefinitionError(
            f"Could not save period definitions: {definitions_path}"
        ) from error

    return load_period_definitions(definitions_path)


def period_calculation_year(value):
    if isinstance(value, str):
        if value.casefold() == "prehistory":
            return EARLIEST_CALCULATION_YEAR

        if value.casefold() == "future":
            return LATEST_CALCULATION_YEAR

    return int(value)


def next_period_year(year):
    next_year = int(year) + 1

    if next_year == 0:
        next_year = 1

    if next_year > LATEST_CALCULATION_YEAR:
        raise PeriodDefinitionError(
            "There is not enough room after this period to keep every "
            "period at least two years long."
        )

    return next_year


def previous_period_year(year):
    previous_year = int(year) - 1

    if previous_year == 0:
        previous_year = -1

    if previous_year < EARLIEST_CALCULATION_YEAR:
        raise PeriodDefinitionError(
            "There is not enough room before this period to keep every "
            "period at least two years long."
        )

    return previous_year


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
