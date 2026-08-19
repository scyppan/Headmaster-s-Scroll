import hashlib
import random
import uuid
from copy import deepcopy

from mage_maker.core.dates import (
    historical_date_boundary,
    historical_year_after,
    historical_year_distance,
    historical_year_shift,
    next_historical_date,
    normalize_historical_date_parts,
    previous_historical_date,
)
from mage_maker.core.wizarding_currency import (
    monthly_salary_identity,
    normalize_monthly_salary,
)
from mage_maker.sections.development.mortality import (
    normalize_mortality_checked_through_age,
)
from mage_maker.sections.ledger.models import normalize_ledger_entries


DEVELOPMENT_SCHEMA_OPTIONS = (
    "One skill",
    "Two skill",
    "Three skills",
    "Ability-focus",
    "Material Crafting",
    "Ingredient Crafting",
    "Spell-crafting",
    "Social",
    "Scattershot",
)

DEVELOPMENT_SKILL_OPTIONS = (
    "Alchemy",
    "Runes",
    "Arithmancy",
    "Artificing",
    "Astronomy",
    "Charms",
    "Dark Arts",
    "Defense",
    "Divination",
    "Flying",
    "Herbology",
    "History",
    "Creatures",
    "Muggles",
    "Perception",
    "Potions",
    "Social",
    "Transfiguration",
)
DEVELOPMENT_CHARACTERISTIC_OPTIONS = (
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


def normalize_characteristic_name(value, allow_blank=False):
    normalized_value = str(value or "").strip().casefold()

    if normalized_value in DEVELOPMENT_CHARACTERISTIC_OPTIONS:
        return normalized_value

    if allow_blank and not normalized_value:
        return ""

    valid_values = ", ".join(
        field_name.title()
        for field_name in DEVELOPMENT_CHARACTERISTIC_OPTIONS
    )
    raise ValueError(
        f"Characteristic buy must be one of: {valid_values}."
    )

DEVELOPMENT_ABILITY_OPTIONS = (
    "Power",
    "Erudition",
    "Panache",
    "Naturalism",
)

DEVELOPMENT_SKILLS_BY_ABILITY = {
    "Power": (
        "Charms",
        "Transfiguration",
        "Defense",
        "Dark Arts",
    ),
    "Erudition": (
        "Arithmancy",
        "Runes",
        "History",
        "Muggles",
    ),
    "Panache": (
        "Potions",
        "Alchemy",
        "Artificing",
        "Flying",
        "Herbology",
    ),
    "Naturalism": (
        "Creatures",
        "Astronomy",
        "Divination",
        "Perception",
        "Social",
    ),
}

DEVELOPMENT_ABILITY_BY_SKILL = {
    skill: ability
    for ability, skills in DEVELOPMENT_SKILLS_BY_ABILITY.items()
    for skill in skills
}

DEVELOPMENT_ASSIGNMENT_RANDOM = "random"
DEVELOPMENT_ASSIGNMENT_PROMPT = "prompt"
DEVELOPMENT_ASSIGNMENT_SCATTERSHOT = "scattershot"
DEVELOPMENT_ASSIGNMENT_DEFAULT = DEVELOPMENT_ASSIGNMENT_RANDOM
DEVELOPMENT_ASSIGNMENT_SETTING_KEY = "development_strategy_assignment"
DEVELOPMENT_ASSIGNMENT_OPTIONS = (
    (
        DEVELOPMENT_ASSIGNMENT_RANDOM,
        "Always randomly assign development strategy",
    ),
    (
        DEVELOPMENT_ASSIGNMENT_PROMPT,
        "Always prompt to pick",
    ),
    (
        DEVELOPMENT_ASSIGNMENT_SCATTERSHOT,
        "Always pick Scattershot",
    ),
)
ACADEMIC_YEARS_TO_ADULTHOOD = 7
SCHOOL_YEAR_SKILL_IMPROVEMENT_COUNT = 2
SCHOOL_YEAR_BOOK_COUNT = 2
ADULT_YEAR_MAX_BOOK_COUNT = 3
EMINENCE_DEFAULT_TITLE = "Eminence earned"


def normalize_development_schema(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().replace("_", " ").split()
    )
    aliases = {
        "one skill": "One skill",
        "one-skill": "One skill",
        "two skill": "Two skill",
        "two skills": "Two skill",
        "two-skill": "Two skill",
        "three skill": "Three skills",
        "three skills": "Three skills",
        "three-skill": "Three skills",
        "ability focus": "Ability-focus",
        "ability-focus": "Ability-focus",
        "ability focused": "Ability-focus",
        "crafting": "Material Crafting",
        "material crafting": "Material Crafting",
        "material-crafting": "Material Crafting",
        "ingredient crafting": "Ingredient Crafting",
        "ingredient-crafting": "Ingredient Crafting",
        "spell crafting": "Spell-crafting",
        "spell-crafting": "Spell-crafting",
        "social": "Social",
        "scattershot": "Scattershot",
    }
    schema = aliases.get(normalized_value)

    if schema is None:
        valid_values = ", ".join(DEVELOPMENT_SCHEMA_OPTIONS)
        raise ValueError(
            f"Development strategy must be one of: {valid_values}."
        )

    return schema


def development_skill_count(schema):
    normalized_schema = normalize_development_schema(schema)
    counts = {
        "One skill": 1,
        "Two skill": 2,
        "Three skills": 3,
    }
    return counts.get(normalized_schema, 0)


def normalize_development_skill(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().replace("_", " ").split()
    )
    aliases = {
        skill.casefold(): skill
        for skill in DEVELOPMENT_SKILL_OPTIONS
    }
    aliases.update(
        {
            "care of magical creatures": "Creatures",
            "magical creatures": "Creatures",
            "creatures": "Creatures",
            "darkarts": "Dark Arts",
            "history of magic": "History",
            "muggle studies": "Muggles",
            "ancient runes": "Runes",
            "runes": "Runes",
            "social": "Social",
            "social skill": "Social",
            "social skills": "Social",
        }
    )
    skill = aliases.get(normalized_value)

    if skill is None:
        valid_values = ", ".join(DEVELOPMENT_SKILL_OPTIONS)
        raise ValueError(
            f"Development skill must be one of: {valid_values}."
        )

    return skill


def normalize_development_ability(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().replace("_", " ").split()
    )
    abilities = {
        ability.casefold(): ability
        for ability in DEVELOPMENT_ABILITY_OPTIONS
    }
    ability = abilities.get(normalized_value)

    if ability is None:
        valid_values = ", ".join(DEVELOPMENT_ABILITY_OPTIONS)
        raise ValueError(
            f"Development ability must be one of: {valid_values}."
        )

    return ability


def normalize_focused_skills(value, required_count):
    if value in (None, ""):
        candidate_values = []
    elif isinstance(value, str):
        candidate_values = [value]
    elif isinstance(value, (list, tuple)):
        candidate_values = list(value)
    else:
        raise TypeError("Focused skills must be a list.")

    focused_skills = []

    for candidate_value in candidate_values:
        skill = normalize_development_skill(candidate_value)

        if skill not in focused_skills:
            focused_skills.append(skill)

    for skill in DEVELOPMENT_SKILL_OPTIONS:
        if len(focused_skills) >= required_count:
            break

        if skill not in focused_skills:
            focused_skills.append(skill)

    return focused_skills[:required_count]


def normalize_academic_years_advanced(value):
    if value in (None, ""):
        return 0

    if isinstance(value, bool):
        raise ValueError(
            "Academic years advanced must be a whole number."
        )

    try:
        years_advanced = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "Academic years advanced must be a whole number."
        ) from error

    if years_advanced < 0:
        raise ValueError(
            "Academic years advanced cannot be negative."
        )

    return min(years_advanced, ACADEMIC_YEARS_TO_ADULTHOOD)


def normalize_school_started(value, years_advanced=0):
    normalized_years = normalize_academic_years_advanced(
        years_advanced
    )

    if normalized_years > 0:
        return True

    if value in (None, ""):
        return False

    if isinstance(value, bool):
        return value

    normalized_value = str(value).strip().casefold()

    if normalized_value in ("yes", "true", "1", "started"):
        return True

    if normalized_value in (
        "no",
        "false",
        "0",
        "not started",
    ):
        return False

    raise ValueError("School started must be Yes or No.")


def normalize_school_year_book(value):
    if isinstance(value, str):
        book = {
            "record_id": "",
            "name": value,
            "author": "",
        }
    elif isinstance(value, dict):
        record_id = str(
            value.get("record_id") or value.get("book_id") or ""
        ).strip()
        # A stable ID is the complete canonical reference.  Labels are kept
        # only for unresolved legacy entries and are resolved on display.
        book = (
            {"record_id": record_id}
            if record_id
            else {
                "record_id": "",
                "name": str(value.get("name", "") or "").strip(),
                "author": str(value.get("author", "") or "").strip(),
            }
        )
    else:
        raise TypeError("A school-year book must be a book reference.")

    if not book.get("record_id") and not book.get("name"):
        raise ValueError("A school-year book must have a name or record ID.")

    return book


def school_year_book_identity(value):
    book = normalize_school_year_book(value)

    if book["record_id"]:
        return f"id:{book['record_id']}"

    return (
        f"name:{book.get('name', '').casefold()}"
        f"|author:{book.get('author', '').casefold()}"
    )


def normalize_school_year_books(
    value,
    maximum_count=SCHOOL_YEAR_BOOK_COUNT,
):
    if value in (None, ""):
        candidate_books = []
    elif isinstance(value, (list, tuple)):
        candidate_books = list(value)
    else:
        raise TypeError("School-year books must be a list.")

    normalized_books = []
    seen_identities = set()

    for candidate_book in candidate_books:
        normalized_book = normalize_school_year_book(candidate_book)
        identity = school_year_book_identity(normalized_book)

        if identity in seen_identities:
            continue

        normalized_books.append(normalized_book)
        seen_identities.add(identity)

        if len(normalized_books) >= int(maximum_count):
            break

    return normalized_books


def normalize_assigned_school_year_books(value):
    if value in (None, ""):
        candidate_books = []
    elif isinstance(value, (list, tuple)):
        candidate_books = list(value)
    else:
        raise TypeError("Assigned school-year books must be a list.")

    normalized_books = []
    seen_identities = set()

    for candidate_book in candidate_books:
        normalized_book = normalize_school_year_book(candidate_book)
        identity = school_year_book_identity(normalized_book)

        if identity in seen_identities:
            continue

        normalized_books.append(normalized_book)
        seen_identities.add(identity)

    return normalized_books


def normalize_eminence_record(value):
    if not isinstance(value, dict):
        raise TypeError("An eminence record must be an object.")

    title = str(
        value.get("title", EMINENCE_DEFAULT_TITLE)
        or EMINENCE_DEFAULT_TITLE
    ).strip()
    description = str(
        value.get("description", "") or ""
    ).strip()
    skill = normalize_development_skill(value.get("skill"))
    record_id = str(
        value.get("record_id", "") or ""
    ).strip()

    if not record_id:
        identity_text = "|".join(
            (
                title.casefold(),
                description.casefold(),
                skill.casefold(),
            )
        )
        record_id = "eminence-" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()[:20]

    return {
        "record_id": record_id,
        "title": title,
        "description": description,
        "skill": skill,
        "points": 1,
    }


def normalize_eminence_records(value):
    if value in (None, ""):
        candidate_records = []
    elif isinstance(value, (list, tuple)):
        candidate_records = list(value)
    else:
        raise TypeError("Eminence records must be a list.")

    return [
        normalize_eminence_record(candidate_record)
        for candidate_record in candidate_records
    ]


def new_eminence_record(
    title,
    description,
    skill,
):
    return normalize_eminence_record(
        {
            "record_id": str(uuid.uuid4()),
            "title": title,
            "description": description,
            "skill": skill,
        }
    )


def eminence_skill_counts(value):
    counts = {}

    for record in normalize_eminence_records(value):
        skill = record["skill"]
        counts[skill] = counts.get(skill, 0) + 1

    return counts


def total_eminence_points(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    return (
        len(plan.get("initial_eminence", []))
        + sum(
            len(record.get("eminence", []))
            for record in plan.get("school_years", [])
        )
        + sum(
            len(record.get("eminence", []))
            for record in plan.get("adult_years", [])
        )
    )


def normalize_job_date(value, prefix, required):
    if not isinstance(value, dict):
        raise TypeError("A job record must be an object.")

    normalized_prefix = str(prefix or "").strip().casefold()

    if normalized_prefix not in ("start", "end"):
        raise ValueError("A job date prefix must be start or end.")

    year, month, day = normalize_historical_date_parts(
        value.get(f"{normalized_prefix}_year"),
        value.get(f"{normalized_prefix}_month"),
        value.get(f"{normalized_prefix}_day"),
        f"A job {normalized_prefix}",
        required_year=required,
    )

    return {
        f"{normalized_prefix}_year": year,
        f"{normalized_prefix}_month": month,
        f"{normalized_prefix}_day": day,
    }


def job_date_tuple(year, month=None, day=None, end_boundary=False):
    if year in (None, ""):
        return None

    return historical_date_boundary(
        year,
        month,
        day,
        end_boundary=end_boundary,
    )


def suggested_job_start_date(
    assignments,
    page_start_year,
    page_end_year=None,
):
    if page_start_year in (None, ""):
        return None

    normalized_page_start_year = int(page_start_year)
    normalized_page_end_year = int(
        normalized_page_start_year
        if page_end_year in (None, "")
        else page_end_year
    )
    latest_end_date = None

    for assignment in normalize_job_records(assignments or []):
        end_year = assignment["end_year"]

        if (
            end_year is None
            or end_year < normalized_page_start_year
            or end_year > normalized_page_end_year
        ):
            continue

        end_date = job_date_tuple(
            end_year,
            assignment["end_month"],
            assignment["end_day"],
            end_boundary=True,
        )

        if latest_end_date is None or end_date > latest_end_date:
            latest_end_date = end_date

    if latest_end_date is None:
        return None

    return next_historical_date(*latest_end_date)


def job_assignment_overlaps_year_range(
    value,
    start_year,
    end_year=None,
):
    job = normalize_job_record(value)
    normalized_start_year = int(start_year)
    normalized_end_year = int(
        normalized_start_year if end_year is None else end_year
    )
    page_start = (normalized_start_year, 1, 1)
    page_end = (normalized_end_year, 12, 31)
    job_start = job_date_tuple(
        job["start_year"],
        job["start_month"],
        job["start_day"],
    )
    job_end = job_date_tuple(
        job["end_year"],
        job["end_month"],
        job["end_day"],
        end_boundary=True,
    )
    return (
        job_start <= page_end
        and (job_end is None or job_end >= page_start)
    )


def normalize_job_record(value):
    if not isinstance(value, dict):
        raise TypeError("A job record must be an object.")

    organization_id = str(
        value.get("organization_id", "") or ""
    ).strip()
    organization_name = str(
        value.get("organization_name", "") or ""
    ).strip()
    organization_job_id = str(
        value.get("organization_job_id", "") or ""
    ).strip()
    title = str(value.get("title", "") or "").strip()
    salary = normalize_monthly_salary(value.get("salary"))
    concurrent = bool(value.get("concurrent", False))

    if not organization_id and not organization_name:
        raise ValueError("A job must have an organization.")

    if not title:
        raise ValueError("A job must have a title.")

    start_date = normalize_job_date(value, "start", True)
    end_date = normalize_job_date(value, "end", False)
    start_boundary = job_date_tuple(
        start_date["start_year"],
        start_date["start_month"],
        start_date["start_day"],
    )
    end_boundary = job_date_tuple(
        end_date["end_year"],
        end_date["end_month"],
        end_date["end_day"],
        end_boundary=True,
    )

    if (
        end_boundary is not None
        and end_boundary < start_boundary
    ):
        raise ValueError(
            "A job end date cannot be before its start date."
        )

    record_id = str(
        value.get("record_id", "") or ""
    ).strip()

    if not record_id:
        identity_text = "|".join(
            (
                organization_id.casefold(),
                organization_name.casefold(),
                organization_job_id.casefold(),
                title.casefold(),
                str(monthly_salary_identity(salary)),
                str(start_date["start_year"]),
                str(start_date["start_month"] or ""),
                str(start_date["start_day"] or ""),
                str(end_date["end_year"] or ""),
                str(end_date["end_month"] or ""),
                str(end_date["end_day"] or ""),
            )
        )
        record_id = "job-" + hashlib.sha256(
            identity_text.encode("utf-8")
        ).hexdigest()[:20]

    return {
        "record_id": record_id,
        "organization_id": organization_id,
        "organization_name": organization_name,
        "organization_job_id": organization_job_id,
        "title": title,
        "salary": salary,
        "concurrent": concurrent,
        **start_date,
        **end_date,
    }


def normalize_job_records(value):
    if value in (None, ""):
        candidate_records = []
    elif isinstance(value, (list, tuple)):
        candidate_records = list(value)
    else:
        raise TypeError("Job records must be a list.")

    return [
        normalize_job_record(candidate_record)
        for candidate_record in candidate_records
    ]


def new_job_record(
    organization_id,
    organization_name,
    title,
    salary,
    start_year,
    start_month=None,
    start_day=None,
    end_year=None,
    end_month=None,
    end_day=None,
    organization_job_id="",
    concurrent=False,
):
    return normalize_job_record(
        {
            "record_id": str(uuid.uuid4()),
            "organization_id": organization_id,
            "organization_name": organization_name,
            "organization_job_id": organization_job_id,
            "concurrent": bool(concurrent),
            "title": title,
            "salary": salary,
            "start_year": start_year,
            "start_month": start_month,
            "start_day": start_day,
            "end_year": end_year,
            "end_month": end_month,
            "end_day": end_day,
        }
    )


def job_assignment_active_on(
    value,
    year,
    month=1,
    day=1,
):
    assignment = normalize_job_record(value)
    selected_date = job_date_tuple(year, month, day)
    start_date = job_date_tuple(
        assignment["start_year"],
        assignment["start_month"],
        assignment["start_day"],
    )
    end_date = job_date_tuple(
        assignment["end_year"],
        assignment["end_month"],
        assignment["end_day"],
        end_boundary=True,
    )
    return (
        start_date <= selected_date
        and (
            end_date is None
            or selected_date <= end_date
        )
    )


def job_assignments_overlap(first_value, second_value):
    first = normalize_job_record(first_value)
    second = normalize_job_record(second_value)
    first_start = job_date_tuple(
        first["start_year"],
        first["start_month"],
        first["start_day"],
    )
    first_end = job_date_tuple(
        first["end_year"],
        first["end_month"],
        first["end_day"],
        end_boundary=True,
    )
    second_start = job_date_tuple(
        second["start_year"],
        second["start_month"],
        second["start_day"],
    )
    second_end = job_date_tuple(
        second["end_year"],
        second["end_month"],
        second["end_day"],
        end_boundary=True,
    )
    return (
        (second_end is None or first_start <= second_end)
        and (first_end is None or second_start <= first_end)
    )


def require_job_position_available(
    organization_job,
    assignment,
    existing_assignments,
    ignored_assignment_id="",
):
    if not isinstance(organization_job, dict):
        raise TypeError("An organization job must be an object.")

    normalized_assignment = normalize_job_record(assignment)
    position_id = str(
        organization_job.get("record_id", "") or ""
    ).strip()
    opened_year_value = organization_job.get("opened_year")

    if not position_id:
        raise ValueError("Choose an organization job.")

    try:
        opened_year = int(opened_year_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "The selected organization job has no valid opening year."
        ) from error

    if (
        normalized_assignment["organization_job_id"]
        != position_id
    ):
        raise ValueError(
            "The assignment does not match the selected organization job."
        )

    opened_date = job_date_tuple(
        opened_year,
        organization_job.get("opened_month"),
        organization_job.get("opened_day"),
    )
    assignment_start = job_date_tuple(
        normalized_assignment["start_year"],
        normalized_assignment["start_month"],
        normalized_assignment["start_day"],
    )
    assignment_end = job_date_tuple(
        normalized_assignment["end_year"],
        normalized_assignment["end_month"],
        normalized_assignment["end_day"],
        end_boundary=True,
    )

    if assignment_start < opened_date:
        raise ValueError(
            "This position does not open until "
            f"{organization_job.get('opened_date', opened_year)}."
        )

    closed_year = organization_job.get("closed_year")

    if closed_year not in (None, ""):
        closed_date = job_date_tuple(
            closed_year,
            organization_job.get("closed_month"),
            organization_job.get("closed_day"),
            end_boundary=True,
        )

        if assignment_end is None:
            raise ValueError(
                "This position closes on "
                f"{organization_job.get('closed_date', closed_year)}; "
                "enter an appointment end date."
            )

        if assignment_end > closed_date:
            raise ValueError(
                "This position closes on "
                f"{organization_job.get('closed_date', closed_year)}."
            )

    ignored_id = str(ignored_assignment_id or "").strip()

    for existing_assignment in normalize_job_records(
        existing_assignments
    ):
        if (
            existing_assignment["organization_job_id"]
            != position_id
            or existing_assignment["record_id"] == ignored_id
        ):
            continue

        if job_assignments_overlap(
            normalized_assignment,
            existing_assignment,
        ):
            raise ValueError(
                "This position is not open during the selected dates."
            )

    return normalized_assignment


def require_person_job_available(
    assignment,
    existing_assignments,
    ignored_assignment_id="",
):
    normalized_assignment = normalize_job_record(assignment)

    if normalized_assignment["concurrent"]:
        return normalized_assignment

    ignored_id = str(ignored_assignment_id or "").strip()

    for existing_assignment in normalize_job_records(
        existing_assignments
    ):
        if existing_assignment["record_id"] == ignored_id:
            continue

        if job_assignments_overlap(
            normalized_assignment,
            existing_assignment,
        ):
            raise ValueError(
                "This person is already holding another job during the "
                "selected dates. Select Hold concurrently to allow the "
                "appointments to overlap."
            )

    return normalized_assignment


def person_job_availability_window(
    existing_assignments,
    window_start,
    window_end,
    ignored_assignment_id="",
):
    start_boundary = tuple(window_start)
    end_boundary = tuple(window_end)

    if len(start_boundary) != 3 or len(end_boundary) != 3:
        raise ValueError("A job availability window needs full dates.")

    ignored_id = str(ignored_assignment_id or "").strip()
    assignments = [
        assignment
        for assignment in normalize_job_records(existing_assignments)
        if assignment["record_id"] != ignored_id
    ]
    cursor = start_boundary

    while True:
        blocking_assignment = None

        for assignment in assignments:
            assignment_start = job_date_tuple(
                assignment["start_year"],
                assignment["start_month"],
                assignment["start_day"],
            )
            assignment_end = job_date_tuple(
                assignment["end_year"],
                assignment["end_month"],
                assignment["end_day"],
                end_boundary=True,
            )

            if (
                assignment_start <= cursor
                and (assignment_end is None or cursor <= assignment_end)
            ):
                blocking_assignment = assignment
                break

        if blocking_assignment is None:
            break

        blocking_end = job_date_tuple(
            blocking_assignment["end_year"],
            blocking_assignment["end_month"],
            blocking_assignment["end_day"],
            end_boundary=True,
        )

        if blocking_end is None:
            return None

        cursor = next_historical_date(*blocking_end)

        if cursor > end_boundary:
            return None

    constrained_end = end_boundary

    for assignment in assignments:
        assignment_start = job_date_tuple(
            assignment["start_year"],
            assignment["start_month"],
            assignment["start_day"],
        )

        if assignment_start <= cursor:
            continue

        constrained_end = min(
            constrained_end,
            previous_historical_date(*assignment_start),
        )

    if constrained_end < cursor:
        return None

    return cursor, constrained_end


def normalize_adult_year_record(value):
    if not isinstance(value, dict):
        raise TypeError("An adult-year record must be an object.")

    adult_year_value = value.get(
        "adult_year",
        value.get("year"),
    )

    if isinstance(adult_year_value, bool):
        raise ValueError("An adult-year number must be a whole number.")

    try:
        adult_year = int(adult_year_value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "An adult-year number must be a whole number."
        ) from error

    if adult_year < 1:
        raise ValueError("An adult-year number must be at least one.")

    reading_characteristic = normalize_characteristic_name(
        value.get("reading_characteristic"),
        allow_blank=True,
    )

    if reading_characteristic not in (
        "",
        "intellect",
        "willpower",
    ):
        raise ValueError(
            "Adult reading must use Intellect or Willpower."
        )

    roll_values = value.get("reading_rolls", [])

    if roll_values in (None, ""):
        roll_values = []
    elif not isinstance(roll_values, (list, tuple)):
        raise TypeError("Adult reading rolls must be a list.")

    reading_rolls = []

    for roll_value in roll_values:
        if isinstance(roll_value, bool):
            raise ValueError(
                "Every adult reading die must be a whole number."
            )

        try:
            roll = int(roll_value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                "Every adult reading die must be a whole number."
            ) from error

        if not 1 <= roll <= 10:
            raise ValueError(
                "Every adult reading die must be between 1 and 10."
            )

        reading_rolls.append(roll)

    if reading_rolls and not reading_characteristic:
        raise ValueError(
            "Adult reading rolls require Intellect or Willpower."
        )

    reading_total = sum(reading_rolls)
    book_limit = min(
        ADULT_YEAR_MAX_BOOK_COUNT,
        max(0, reading_total - 20),
    )
    books = normalize_school_year_books(
        value.get("books", []),
        ADULT_YEAR_MAX_BOOK_COUNT,
    )[:book_limit]

    return {
        "adult_year": adult_year,
        "reading_characteristic": reading_characteristic,
        "reading_rolls": reading_rolls,
        "reading_total": reading_total,
        "book_limit": book_limit,
        "books": books,
        "eminence": normalize_eminence_records(
            value.get("eminence", [])
        ),
        "jobs": normalize_job_records(value.get("jobs", [])),
    }


def normalize_adult_year_records(value):
    if value in (None, ""):
        candidate_records = []
    elif isinstance(value, (list, tuple)):
        candidate_records = list(value)
    else:
        raise TypeError("Adult years must be a list.")

    records_by_year = {}

    for candidate_record in candidate_records:
        normalized_record = normalize_adult_year_record(
            candidate_record
        )
        records_by_year[normalized_record["adult_year"]] = (
            normalized_record
        )

    return [
        records_by_year[adult_year]
        for adult_year in sorted(records_by_year)
    ]


def ensure_adult_year_records(records, target_year_count):
    normalized_records = normalize_adult_year_records(records)
    records_by_year = {
        record["adult_year"]: record
        for record in normalized_records
        if record["adult_year"] <= int(target_year_count)
    }

    for adult_year in range(1, int(target_year_count) + 1):
        records_by_year.setdefault(
            adult_year,
            {
                "adult_year": adult_year,
                "reading_characteristic": "",
                "reading_rolls": [],
                "books": [],
                "eminence": [],
                "jobs": [],
            },
        )

    return [
        records_by_year[adult_year]
        for adult_year in sorted(records_by_year)
    ]


def normalize_school_year_electives(value):
    if value in (None, ""):
        candidate_values = []
    elif isinstance(value, str):
        candidate_values = value.split(",")
    elif isinstance(value, (list, tuple)):
        candidate_values = list(value)
    else:
        raise TypeError("School-year electives must be a list.")

    electives = []
    seen_electives = set()

    for candidate_value in candidate_values:
        elective = str(candidate_value or "").strip()
        elective_identity = elective.casefold()

        if not elective or elective_identity in seen_electives:
            continue

        electives.append(elective)
        seen_electives.add(elective_identity)

    return electives


def normalize_school_year_record(value):
    if not isinstance(value, dict):
        raise TypeError("A school-year record must be an object.")

    try:
        year_number = int(value.get("year"))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "A school-year record must have a whole-number year."
        ) from error

    if not 1 <= year_number <= ACADEMIC_YEARS_TO_ADULTHOOD:
        raise ValueError(
            "A school-year record must be between Year 1 and Year 7."
        )

    ability = normalize_development_ability(
        value.get("ability")
    )
    skill_values = value.get("skills", [])

    if isinstance(skill_values, str):
        skill_values = [skill_values]

    if not isinstance(skill_values, (list, tuple)):
        raise TypeError(
            "School-year skill improvements must be a list."
        )

    skills = [
        normalize_development_skill(skill)
        for skill in skill_values
    ]

    if len(skills) != SCHOOL_YEAR_SKILL_IMPROVEMENT_COUNT:
        raise ValueError(
            "Every school year must have exactly two skill improvements."
        )

    electives_were_stored = (
        "electives" in value
        or "selected_electives" in value
    )
    elective_values = value.get(
        "electives",
        value.get("selected_electives", []),
    )

    return {
        "year": year_number,
        "school": str(value.get("school", "") or "").strip(),
        "skipped": bool(value.get("skipped", False)),
        "ability": ability,
        "skills": skills,
        "characteristic": normalize_characteristic_name(
            value.get("characteristic"),
            allow_blank=True,
        ),
        "electives": normalize_school_year_electives(
            elective_values
        ),
        "electives_initialized": bool(
            value.get(
                "electives_initialized",
                electives_were_stored,
            )
        ),
        "assigned_books": normalize_assigned_school_year_books(
            value.get("assigned_books", [])
        ),
        "books": normalize_school_year_books(
            value.get("books", [])
        ),
        "eminence": normalize_eminence_records(
            value.get("eminence", [])
        ),
    }


def normalize_school_year_records(value):
    if value in (None, ""):
        candidate_records = []
    elif isinstance(value, (list, tuple)):
        candidate_records = list(value)
    else:
        raise TypeError("School years must be a list.")

    records_by_year = {}

    for candidate_record in candidate_records:
        normalized_record = normalize_school_year_record(
            candidate_record
        )
        records_by_year[normalized_record["year"]] = (
            normalized_record
        )

    return [
        records_by_year[year_number]
        for year_number in sorted(records_by_year)
    ]


def school_progress_text(school_started, years_advanced):
    normalized_years = normalize_academic_years_advanced(
        years_advanced
    )
    normalized_started = normalize_school_started(
        school_started,
        normalized_years,
    )

    if not normalized_started:
        return "Not yet started school"

    if normalized_years >= ACADEMIC_YEARS_TO_ADULTHOOD:
        return "Graduated"

    return f"Year {normalized_years + 1}"


def visible_school_year_count(school_started, years_advanced):
    normalized_years = normalize_academic_years_advanced(
        years_advanced
    )
    normalized_started = normalize_school_started(
        school_started,
        normalized_years,
    )

    if not normalized_started:
        return 0

    if normalized_years >= ACADEMIC_YEARS_TO_ADULTHOOD:
        return ACADEMIC_YEARS_TO_ADULTHOOD

    return normalized_years + 1


def normalize_development_plan(value, default_schema=None):
    if isinstance(value, str):
        plan = {"schema": value}
    elif isinstance(value, dict):
        plan = deepcopy(value)
    elif value in (None, ""):
        plan = {}
    else:
        raise TypeError("A development plan must be an object.")

    schema_value = plan.get("schema", default_schema)

    if schema_value in (None, ""):
        raise ValueError(
            "Every magician must have a development strategy."
        )

    schema = normalize_development_schema(schema_value)
    plan["schema"] = schema
    plan["blood_status_initialized"] = bool(
        plan.get("blood_status_initialized", False)
    )
    calendar_year_progression = bool(
        plan.get("calendar_year_progression", False)
    )

    if calendar_year_progression:
        plan["calendar_year_progression"] = True
    else:
        plan.pop("calendar_year_progression", None)
    plan["academic_years_advanced"] = normalize_academic_years_advanced(
        plan.get("academic_years_advanced", 0)
    )
    plan["school_started"] = normalize_school_started(
        plan.get("school_started"),
        plan["academic_years_advanced"],
    )

    if calendar_year_progression:
        plan["academic_years_advanced"] = 0
        plan["school_started"] = False

    plan["school_years"] = normalize_school_year_records(
        plan.get("school_years", [])
    )
    plan["ledger_entries"] = normalize_ledger_entries(
        plan.get("ledger_entries", [])
    )
    plan["initial_eminence"] = normalize_eminence_records(
        plan.get("initial_eminence", [])
    )
    plan["mortality_checked_through_age"] = (
        normalize_mortality_checked_through_age(
            plan.get("mortality_checked_through_age")
        )
    )
    plan["adult_years"] = normalize_adult_year_records(
        plan.get("adult_years", [])
    )

    plan.pop("age", None)

    required_skill_count = development_skill_count(schema)

    if required_skill_count:
        focused_skill_values = plan.get("focused_skills")

        if focused_skill_values in (None, ""):
            focused_skill_values = plan.get(
                "skills",
                plan.get(
                    "preferred_skills",
                    plan.get(
                        "preferred_skill",
                        plan.get("skill"),
                    ),
                ),
            )

        plan["focused_skills"] = normalize_focused_skills(
            focused_skill_values,
            required_skill_count,
        )
        plan.pop("focused_ability", None)
    elif schema == "Ability-focus":
        focused_ability = plan.get(
            "focused_ability",
            plan.get(
                "ability",
                plan.get("preferred_ability"),
            ),
        )

        if focused_ability in (None, ""):
            focused_ability = DEVELOPMENT_ABILITY_OPTIONS[0]

        plan["focused_ability"] = normalize_development_ability(
            focused_ability
        )
        plan.pop("focused_skills", None)
    else:
        plan.pop("focused_skills", None)
        plan.pop("focused_ability", None)

    for legacy_field in (
        "ability",
        "preferred_ability",
        "preferred_skill",
        "preferred_skills",
        "skill",
        "skills",
    ):
        plan.pop(legacy_field, None)

    return plan


def development_job_assignments(value):
    plan = normalize_development_plan(
        value,
        default_schema="Scattershot",
    )
    assignments = []
    seen_record_ids = set()

    for adult_year in plan.get("adult_years", []):
        for assignment in normalize_job_records(
            adult_year.get("jobs", [])
        ):
            record_id = assignment["record_id"]

            if record_id in seen_record_ids:
                continue

            seen_record_ids.add(record_id)
            assignments.append(assignment)

    return normalize_job_records(assignments)


def non_magical_development_plan(value, job_assignments=None):
    assignments = (
        development_job_assignments(value)
        if job_assignments is None
        else normalize_job_records(job_assignments)
    )
    adult_years = []

    if assignments:
        adult_years.append(
            {
                "adult_year": 1,
                "reading_characteristic": "",
                "reading_rolls": [],
                "books": [],
                "eminence": [],
                "jobs": assignments,
            }
        )

    return normalize_development_plan(
        {
            "schema": "Scattershot",
            "blood_status_initialized": False,
            "academic_years_advanced": 0,
            "school_started": False,
            "school_years": [],
            "ledger_entries": [],
            "initial_eminence": [],
            "adult_years": adult_years,
            "mortality_checked_through_age": None,
        }
    )


def normalize_development_assignment_policy(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().replace("_", " ").split()
    )
    aliases = {
        "": DEVELOPMENT_ASSIGNMENT_DEFAULT,
        "random": DEVELOPMENT_ASSIGNMENT_RANDOM,
        "always randomly assign development strategy": (
            DEVELOPMENT_ASSIGNMENT_RANDOM
        ),
        "prompt": DEVELOPMENT_ASSIGNMENT_PROMPT,
        "always prompt to pick": DEVELOPMENT_ASSIGNMENT_PROMPT,
        "scattershot": DEVELOPMENT_ASSIGNMENT_SCATTERSHOT,
        "always pick scattershot": DEVELOPMENT_ASSIGNMENT_SCATTERSHOT,
    }
    policy = aliases.get(normalized_value)

    if policy is None:
        return DEVELOPMENT_ASSIGNMENT_DEFAULT

    return policy


def random_development_schema(current_schema=None):
    normalized_current = None

    if current_schema not in (None, ""):
        normalized_current = normalize_development_schema(current_schema)

    choices = [
        schema
        for schema in DEVELOPMENT_SCHEMA_OPTIONS
        if schema != normalized_current
    ]

    if not choices:
        choices = list(DEVELOPMENT_SCHEMA_OPTIONS)

    return random.choice(choices)


def randomized_development_plan(
    current_schema=None,
    years_advanced=0,
    selected_schema=None,
    school_started=None,
    school_years=None,
    ledger_entries=None,
    adult_years=None,
    initial_eminence=None,
    mortality_checked_through_age=None,
    blood_status_initialized=False,
    calendar_year_progression=False,
):
    schema = (
        normalize_development_schema(selected_schema)
        if selected_schema not in (None, "")
        else random_development_schema(current_schema)
    )
    plan = {
        "schema": schema,
        "blood_status_initialized": bool(
            blood_status_initialized
        ),
        "academic_years_advanced": normalize_academic_years_advanced(
            years_advanced
        ),
        "school_started": normalize_school_started(
            school_started,
            years_advanced,
        ),
        "school_years": deepcopy(school_years or []),
        "ledger_entries": deepcopy(ledger_entries or []),
        "adult_years": deepcopy(adult_years or []),
        "initial_eminence": deepcopy(initial_eminence or []),
        "mortality_checked_through_age": (
            mortality_checked_through_age
        ),
    }

    if calendar_year_progression:
        plan["calendar_year_progression"] = True
    required_skill_count = development_skill_count(schema)

    if required_skill_count:
        plan["focused_skills"] = random.sample(
            list(DEVELOPMENT_SKILL_OPTIONS),
            required_skill_count,
        )
    elif schema == "Ability-focus":
        plan["focused_ability"] = random.choice(
            DEVELOPMENT_ABILITY_OPTIONS
        )

    return normalize_development_plan(plan)


def new_development_plan(assignment_policy, selected_schema=None):
    if selected_schema not in (None, ""):
        return randomized_development_plan(
            years_advanced=0,
            selected_schema=selected_schema,
        )

    policy = normalize_development_assignment_policy(
        assignment_policy
    )

    if policy == DEVELOPMENT_ASSIGNMENT_RANDOM:
        return randomized_development_plan()
    elif policy == DEVELOPMENT_ASSIGNMENT_SCATTERSHOT:
        schema = "Scattershot"
    else:
        raise ValueError(
            "Choose a development strategy before creating this magician."
        )

    return normalize_development_plan(
        {
            "schema": schema,
            "academic_years_advanced": 0,
            "school_started": False,
        }
    )


def migrated_development_plan(value, assignment_policy, record_id):
    stored_plan = (
        deepcopy(value)
        if isinstance(value, dict)
        else {"schema": value}
        if isinstance(value, str)
        else {}
    )
    supplied_skill_focus = any(
        stored_plan.get(field_name) not in (None, "", [])
        for field_name in (
            "focused_skills",
            "skills",
            "preferred_skills",
            "preferred_skill",
            "skill",
        )
    )
    supplied_ability_focus = any(
        stored_plan.get(field_name) not in (None, "")
        for field_name in (
            "focused_ability",
            "ability",
            "preferred_ability",
        )
    )
    identity = str(record_id or "unidentified-magician").encode(
        "utf-8"
    )
    digest = hashlib.sha256(identity).hexdigest()

    if value not in (None, ""):
        plan = normalize_development_plan(value)
    else:
        policy = normalize_development_assignment_policy(
            assignment_policy
        )

        if policy == DEVELOPMENT_ASSIGNMENT_RANDOM:
            schema_index = int(digest, 16) % len(
                DEVELOPMENT_SCHEMA_OPTIONS
            )
            schema = DEVELOPMENT_SCHEMA_OPTIONS[schema_index]
        else:
            schema = "Scattershot"

        plan = normalize_development_plan(
            {
                "schema": schema,
                "academic_years_advanced": 0,
                "school_started": False,
            }
        )

    schema = plan["schema"]
    required_skill_count = development_skill_count(schema)

    if required_skill_count and not supplied_skill_focus:
        starting_index = int(digest[:8], 16) % len(
            DEVELOPMENT_SKILL_OPTIONS
        )
        rotated_skills = (
            DEVELOPMENT_SKILL_OPTIONS[starting_index:]
            + DEVELOPMENT_SKILL_OPTIONS[:starting_index]
        )
        plan["focused_skills"] = list(
            rotated_skills[:required_skill_count]
        )
    elif schema == "Ability-focus" and not supplied_ability_focus:
        ability_index = int(digest[:8], 16) % len(
            DEVELOPMENT_ABILITY_OPTIONS
        )
        plan["focused_ability"] = DEVELOPMENT_ABILITY_OPTIONS[
            ability_index
        ]

    return plan


def calculate_school_start_year(birth_year, birth_month=None, birth_day=None):
    if birth_year in (None, ""):
        return None

    if isinstance(birth_year, bool):
        return None

    try:
        normalized_year = int(birth_year)
    except (TypeError, ValueError):
        return None

    normalized_month = None
    normalized_day = None

    if birth_month not in (None, ""):
        try:
            normalized_month = int(birth_month)
        except (TypeError, ValueError):
            return None

    if birth_day not in (None, ""):
        try:
            normalized_day = int(birth_day)
        except (TypeError, ValueError):
            return None

    after_cutoff = (
        normalized_month is not None
        and (
            normalized_month > 9
            or (
                normalized_month == 9
                and normalized_day is not None
                and normalized_day > 1
            )
        )
    )
    try:
        return historical_year_shift(
            normalized_year,
            12 if after_cutoff else 11,
        )
    except ValueError:
        return None


def calculate_development_start_year(
    birth_year,
    birth_month=None,
    birth_day=None,
    school_attended=True,
):
    return calculate_school_start_year(
        birth_year,
        birth_month,
        birth_day,
    )


def school_year_calendar_year(academic_start_year, school_year):
    if academic_start_year in (None, ""):
        return None

    try:
        return historical_year_shift(
            academic_start_year,
            int(school_year) - 1,
        )
    except (TypeError, ValueError):
        return None


def school_year_calendar_year_range(
    academic_start_year,
    school_year,
):
    start_year = school_year_calendar_year(
        academic_start_year,
        school_year,
    )

    if start_year is None:
        return None

    return start_year, historical_year_after(start_year)


def adult_year_calendar_year(academic_start_year, adult_year):
    if academic_start_year in (None, ""):
        return None

    try:
        normalized_adult_year = int(adult_year)
    except (TypeError, ValueError):
        return None

    try:
        graduation_year = historical_year_shift(
            academic_start_year,
            ACADEMIC_YEARS_TO_ADULTHOOD,
        )
    except (TypeError, ValueError):
        return None

    if normalized_adult_year == 1:
        return graduation_year

    try:
        return historical_year_shift(
            graduation_year,
            normalized_adult_year,
        )
    except ValueError:
        return None


def adult_year_calendar_year_range(
    academic_start_year,
    adult_year,
):
    calendar_year = adult_year_calendar_year(
        academic_start_year,
        adult_year,
    )

    if calendar_year is None:
        return None

    try:
        normalized_adult_year = int(adult_year)
    except (TypeError, ValueError):
        return None

    if normalized_adult_year == 1:
        return calendar_year, historical_year_after(calendar_year)

    return calendar_year, calendar_year


def calendar_year_age_range(
    calendar_year,
    birth_year,
    birth_month=None,
    birth_day=None,
):
    if calendar_year in (None, "") or birth_year in (None, ""):
        return None

    try:
        ending_age = historical_year_distance(
            birth_year,
            calendar_year,
        )
    except (TypeError, ValueError):
        return None

    return ending_age - 1, ending_age


def development_year_page_title(page):
    if not isinstance(page, dict):
        return "Development year"

    page_type = str(page.get("page_type", "") or "")
    calendar_year = page.get("calendar_year")
    calendar_end_year = page.get(
        "calendar_end_year",
        calendar_year,
    )

    if page_type == "school":
        school_year = page.get("school_year")

        if calendar_year is None or calendar_end_year is None:
            return f"Year {school_year}"

        return (
            f"Year {school_year} "
            f"({calendar_year}-{calendar_end_year})"
        )

    if (
        page_type == "adult"
        and page.get("adult_year") == 1
        and not bool(page.get("school_attended", True))
    ):
        if calendar_year is None or calendar_end_year is None:
            return "First development year"

        return f"{calendar_year} - {calendar_end_year}"

    if page_type == "adult" and page.get("adult_year") == 1:
        if calendar_year is None or calendar_end_year is None:
            return "Development year"

        return f"{calendar_year} - {calendar_end_year}"

    if page_type == "adult":
        return (
            str(calendar_year)
            if calendar_year is not None
            else f"Adult Year {page.get('adult_year')}"
        )

    return "Development year"


def development_year_pages(
    development_plan,
    academic_start_year=None,
    birth_year=None,
    birth_month=None,
    birth_day=None,
    school_attended=True,
):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    pages = []

    for school_year_record in plan.get("school_years", []):
        school_year = school_year_record["year"]
        calendar_year_range = school_year_calendar_year_range(
            academic_start_year,
            school_year,
        )
        calendar_year = (
            calendar_year_range[0]
            if calendar_year_range is not None
            else None
        )
        calendar_end_year = (
            calendar_year_range[1]
            if calendar_year_range is not None
            else None
        )
        page = {
            "page_key": f"school:{school_year}",
            "page_type": "school",
            "school_year": school_year,
            "adult_year": None,
            "calendar_year": calendar_year,
            "calendar_end_year": calendar_end_year,
            "age_range": (
                school_year + 10,
                school_year + 11,
            ),
            "school_attended": bool(school_attended),
        }
        page["title"] = development_year_page_title(page)
        pages.append(page)

    visible_adult_year_records = (
        plan.get("adult_years", [])
        if (
            bool(plan.get("calendar_year_progression"))
            or plan.get("academic_years_advanced", 0)
            >= ACADEMIC_YEARS_TO_ADULTHOOD
        )
        else []
    )

    for adult_year_record in visible_adult_year_records:
        adult_year = adult_year_record["adult_year"]
        calendar_year_range = adult_year_calendar_year_range(
            academic_start_year,
            adult_year,
        )
        calendar_year = (
            calendar_year_range[0]
            if calendar_year_range is not None
            else None
        )
        calendar_end_year = (
            calendar_year_range[1]
            if calendar_year_range is not None
            else None
        )
        page = {
            "page_key": f"adult:{adult_year}",
            "page_type": "adult",
            "school_year": None,
            "adult_year": adult_year,
            "calendar_year": calendar_year,
            "calendar_end_year": calendar_end_year,
            "age_range": (
                (0, 1)
                if adult_year == 1
                and not bool(school_attended)
                and birth_year not in (None, "")
                else calendar_year_age_range(
                    calendar_year,
                    birth_year,
                    birth_month,
                    birth_day,
                )
            ),
            "school_attended": bool(school_attended),
        }
        page["title"] = development_year_page_title(page)
        pages.append(page)

    return pages
