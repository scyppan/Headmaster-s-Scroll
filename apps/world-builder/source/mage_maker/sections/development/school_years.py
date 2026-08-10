import random
from copy import deepcopy

from mage_maker.sections.development.characteristics import (
    CHARACTERISTIC_MAXIMUM_VALUE,
    CHARACTERISTIC_NAMES,
    available_characteristic_buys,
    characteristic_values_through_school_year,
    normalize_characteristic_name,
    normalize_characteristics,
)
from mage_maker.sections.development.initial_bonuses import (
    SCHEMA_ABILITIES,
    STRATEGY_PREFERENCE_PROBABILITY,
    preferred_development_skills,
)
from mage_maker.sections.development.models import (
    ADULT_YEAR_MAX_BOOK_COUNT,
    DEVELOPMENT_ABILITY_BY_SKILL,
    DEVELOPMENT_ABILITY_OPTIONS,
    DEVELOPMENT_SKILL_OPTIONS,
    SCHOOL_YEAR_BOOK_COUNT,
    eminence_skill_counts,
    normalize_adult_year_record,
    normalize_adult_year_records,
    normalize_development_ability,
    normalize_development_plan,
    normalize_development_skill,
    normalize_school_year_book,
    normalize_school_year_electives,
    normalize_school_year_record,
    normalize_school_year_records,
    school_year_book_identity,
)


ELECTIVE_CONTINUATION_PROBABILITY = 0.97
EMINENCE_ELECTIVE_WEIGHT_PER_POINT = 0.35
EMINENCE_ELECTIVE_WEIGHT_POINT_LIMIT = 3


def reconcile_school_year_characteristic_buys(
    initial_characteristics,
    school_year_records,
):
    normalized_records = normalize_school_year_records(
        school_year_records
    )
    normalized_initial = normalize_characteristics(
        initial_characteristics
    )

    if normalized_initial is None:
        return normalized_records

    characteristic_values = deepcopy(normalized_initial)

    for record in normalized_records:
        selected_characteristic = normalize_characteristic_name(
            record.get("characteristic"),
            allow_blank=True,
        )

        if (
            selected_characteristic
            and characteristic_values[selected_characteristic]
            < CHARACTERISTIC_MAXIMUM_VALUE
        ):
            characteristic_values[selected_characteristic] += 1
            continue

        replacement_characteristic = ""

        for characteristic_name in CHARACTERISTIC_NAMES:
            if (
                characteristic_values[characteristic_name]
                >= CHARACTERISTIC_MAXIMUM_VALUE
            ):
                continue

            if (
                not replacement_characteristic
                or characteristic_values[characteristic_name]
                < characteristic_values[replacement_characteristic]
            ):
                replacement_characteristic = characteristic_name

        record["characteristic"] = replacement_characteristic

        if replacement_characteristic:
            characteristic_values[replacement_characteristic] += 1

    return normalize_school_year_records(normalized_records)


def reconcile_development_plan_characteristics(
    development_plan,
    initial_characteristics,
):
    normalized_plan = normalize_development_plan(development_plan)
    normalized_plan["school_years"] = (
        reconcile_school_year_characteristic_buys(
            initial_characteristics,
            normalized_plan.get("school_years", []),
        )
    )
    return normalize_development_plan(normalized_plan)


def strategy_weighted_choice(options, preferred_options, randomizer=None):
    available_options = list(options)

    if not available_options:
        raise ValueError("At least one development option is required.")

    preferred = [
        option
        for option in preferred_options
        if option in available_options
    ]
    random_options = [
        option
        for option in available_options
        if option not in preferred
    ]
    selected_randomizer = randomizer or random
    use_preferred = (
        bool(preferred)
        and selected_randomizer.random()
        < STRATEGY_PREFERENCE_PROBABILITY
    )
    return selected_randomizer.choice(
        preferred
        if use_preferred
        else random_options or available_options
    )


def school_curriculum_year(schools, school_name, year_number):
    selected_school_name = str(school_name or "").strip()

    if not selected_school_name:
        return None

    try:
        selected_year_number = int(year_number)
    except (TypeError, ValueError):
        return None

    school_records = (
        list(schools)
        if isinstance(schools, (list, tuple))
        else []
    )

    for school in school_records:
        if not isinstance(school, dict):
            continue

        candidate_school_name = str(
            school.get("name", "") or ""
        ).strip()

        if (
            candidate_school_name.casefold()
            != selected_school_name.casefold()
        ):
            continue

        curriculum = school.get("curriculum", []) or []

        if not isinstance(curriculum, (list, tuple)):
            return None

        for curriculum_year in curriculum:
            if not isinstance(curriculum_year, dict):
                continue

            try:
                candidate_year_number = int(
                    curriculum_year.get("year")
                )
            except (TypeError, ValueError):
                continue

            if candidate_year_number != selected_year_number:
                continue

            core_courses = normalize_school_year_electives(
                curriculum_year.get("core", [])
            )
            elective_courses = normalize_school_year_electives(
                curriculum_year.get("electives", [])
            )

            try:
                elective_limit = int(
                    curriculum_year.get("elective_limit", 0)
                    or 0
                )
            except (TypeError, ValueError):
                elective_limit = 0

            return {
                "year": selected_year_number,
                "core": core_courses,
                "electives": elective_courses,
                "elective_limit": min(
                    max(0, elective_limit),
                    len(elective_courses),
                ),
            }

        return None

    return None


def reconcile_school_year_electives(
    selected_electives,
    approved_electives,
    elective_limit,
):
    normalized_approved_electives = (
        normalize_school_year_electives(approved_electives)
    )
    approved_by_identity = {
        elective.casefold(): elective
        for elective in normalized_approved_electives
    }
    normalized_selected_electives = (
        normalize_school_year_electives(selected_electives)
    )

    try:
        normalized_limit = int(elective_limit or 0)
    except (TypeError, ValueError):
        normalized_limit = 0

    normalized_limit = min(
        max(0, normalized_limit),
        len(normalized_approved_electives),
    )

    if normalized_limit == 0:
        return []

    reconciled_electives = []

    for selected_elective in normalized_selected_electives:
        approved_elective = approved_by_identity.get(
            selected_elective.casefold()
        )

        if (
            approved_elective is None
            or approved_elective in reconciled_electives
        ):
            continue

        reconciled_electives.append(approved_elective)

        if len(reconciled_electives) >= normalized_limit:
            break

    return reconciled_electives


def development_eminence_skill_counts(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    eminence_records = list(plan.get("initial_eminence", []))

    for school_year in plan.get("school_years", []):
        eminence_records.extend(
            school_year.get("eminence", [])
        )

    for adult_year in plan.get("adult_years", []):
        eminence_records.extend(
            adult_year.get("eminence", [])
        )

    return eminence_skill_counts(eminence_records)


def eminence_weighted_elective_choice(
    electives,
    eminence_counts,
    randomizer=None,
):
    available_electives = list(electives)

    if not available_electives:
        raise ValueError("At least one elective is required.")

    selected_randomizer = randomizer or random
    weights = []

    for elective in available_electives:
        try:
            elective_skill = normalize_development_skill(elective)
        except ValueError:
            elective_skill = ""

        eminence_count = min(
            max(0, int(eminence_counts.get(elective_skill, 0))),
            EMINENCE_ELECTIVE_WEIGHT_POINT_LIMIT,
        )
        weights.append(
            1.0
            + eminence_count
            * EMINENCE_ELECTIVE_WEIGHT_PER_POINT
        )

    if all(weight == 1.0 for weight in weights):
        return selected_randomizer.choice(available_electives)

    selection_point = selected_randomizer.random() * sum(weights)
    cumulative_weight = 0.0

    for elective, weight in zip(available_electives, weights):
        cumulative_weight += weight

        if selection_point < cumulative_weight:
            return elective

    return available_electives[-1]


def select_school_year_electives(
    approved_electives,
    elective_limit,
    development_plan,
    randomizer=None,
    previous_electives=None,
):
    available_electives = normalize_school_year_electives(
        approved_electives
    )

    try:
        normalized_limit = int(elective_limit or 0)
    except (TypeError, ValueError):
        normalized_limit = 0

    normalized_limit = min(
        max(0, normalized_limit),
        len(available_electives),
    )
    preferred_skills = set(
        preferred_development_skills(development_plan)
    )
    eminence_counts = development_eminence_skill_counts(
        development_plan
    )
    selected_randomizer = randomizer or random
    selected_electives = reconcile_school_year_electives(
        previous_electives or [],
        available_electives,
        normalized_limit,
    )
    switched_electives = []
    switch_alternatives = [
        elective
        for elective in available_electives
        if elective not in selected_electives
    ]

    if (
        selected_electives
        and len(selected_electives) == normalized_limit
        and switch_alternatives
        and selected_randomizer.random()
        >= ELECTIVE_CONTINUATION_PROBABILITY
    ):
        guidance_scores = {}

        for elective in selected_electives:
            try:
                elective_skill = normalize_development_skill(
                    elective
                )
            except ValueError:
                elective_skill = ""

            guidance_scores[elective] = (
                (2 if elective_skill in preferred_skills else 0)
                + int(eminence_counts.get(elective_skill, 0))
            )

        lowest_guidance_score = min(guidance_scores.values())
        switch_candidates = [
            elective
            for elective in selected_electives
            if guidance_scores[elective] == lowest_guidance_score
        ]
        switched_elective = selected_randomizer.choice(
            switch_candidates
        )
        selected_electives.remove(switched_elective)
        switched_electives.append(switched_elective)

    remaining_electives = [
        elective
        for elective in available_electives
        if elective not in selected_electives
        and elective not in switched_electives
    ]

    while (
        remaining_electives
        and len(selected_electives) < normalized_limit
    ):
        preferred_electives = []

        for elective in remaining_electives:
            try:
                elective_skill = normalize_development_skill(
                    elective
                )
            except ValueError:
                continue

            if elective_skill in preferred_skills:
                preferred_electives.append(elective)

        random_electives = [
            elective
            for elective in remaining_electives
            if elective not in preferred_electives
        ]
        use_preferred = (
            bool(preferred_electives)
            and selected_randomizer.random()
            < STRATEGY_PREFERENCE_PROBABILITY
        )
        selection_pool = (
            preferred_electives
            if use_preferred
            else random_electives or remaining_electives
        )
        selected_elective = eminence_weighted_elective_choice(
            selection_pool,
            eminence_counts,
            selected_randomizer,
        )
        selected_electives.append(selected_elective)
        remaining_electives.remove(selected_elective)

    if (
        len(selected_electives) < normalized_limit
        and switched_electives
    ):
        selected_electives.extend(
            switched_electives[
                : normalized_limit - len(selected_electives)
            ]
        )

    return selected_electives


def preferred_development_abilities(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    preferred_abilities = []

    if plan["schema"] == "Ability-focus":
        focused_ability = plan.get("focused_ability")

        if focused_ability:
            preferred_abilities.append(
                normalize_development_ability(focused_ability)
            )

    schema_abilities = SCHEMA_ABILITIES.get(plan["schema"], ())

    if schema_abilities:
        return [
            normalize_development_ability(ability)
            for ability in schema_abilities
        ]

    for skill in preferred_development_skills(plan):
        ability = DEVELOPMENT_ABILITY_BY_SKILL.get(skill)

        if ability and ability not in preferred_abilities:
            preferred_abilities.append(ability)

    return preferred_abilities


def random_school_year_ability(development_plan, randomizer=None):
    return strategy_weighted_choice(
        DEVELOPMENT_ABILITY_OPTIONS,
        preferred_development_abilities(development_plan),
        randomizer,
    )


def random_school_year_skill(development_plan, randomizer=None):
    return strategy_weighted_choice(
        DEVELOPMENT_SKILL_OPTIONS,
        preferred_development_skills(development_plan),
        randomizer,
    )


def random_annual_improvements(development_plan, randomizer=None):
    return {
        "ability": random_school_year_ability(
            development_plan,
            randomizer,
        ),
        "skills": [
            random_school_year_skill(
                development_plan,
                randomizer,
            ),
            random_school_year_skill(
                development_plan,
                randomizer,
            ),
        ],
    }


def random_characteristic_buy(
    characteristic_options,
    randomizer=None,
):
    available_options = [
        normalize_characteristic_name(option)
        for option in characteristic_options
    ]

    if not available_options:
        raise ValueError(
            "At least one characteristic must remain below five."
        )

    selected_randomizer = randomizer or random
    return selected_randomizer.choice(available_options)


def random_adult_year_record(
    adult_year,
    development_plan,
    randomizer=None,
    initial_characteristics=None,
    school_year_records=None,
    books=None,
    spells=None,
    proficiencies=None,
    excluded_book_identities=None,
):
    if initial_characteristics in (None, "", {}):
        reading_characteristic = ""
        reading_rolls = []
    else:
        characteristic_values = (
            characteristic_values_through_school_year(
                initial_characteristics,
                school_year_records or [],
            )
        )
        reading_characteristic = (
            "intellect"
            if characteristic_values["intellect"]
            >= characteristic_values["willpower"]
            else "willpower"
        )
        selected_randomizer = randomizer or random
        reading_rolls = [
            selected_randomizer.randint(1, 10)
            for _ in range(
                characteristic_values[reading_characteristic]
            )
        ]

    book_limit = min(
        ADULT_YEAR_MAX_BOOK_COUNT,
        max(0, sum(reading_rolls) - 20),
    )
    return normalize_adult_year_record(
        {
            "adult_year": int(adult_year),
            "reading_characteristic": reading_characteristic,
            "reading_rolls": reading_rolls,
            "books": select_school_year_books(
                development_plan,
                books or [],
                spells or [],
                proficiencies or [],
                randomizer,
                excluded_book_identities,
                target_count=book_limit,
            ),
            "eminence": [],
            "jobs": [],
        }
    )


def ensure_adult_year_records_with_improvements(
    records,
    target_year_count,
    development_plan,
    randomizer=None,
    initial_characteristics=None,
    school_year_records=None,
    books=None,
    spells=None,
    proficiencies=None,
    manage_reading=True,
):
    normalized_records = normalize_adult_year_records(records)
    records_by_year = {
        record["adult_year"]: record
        for record in normalized_records
        if record["adult_year"] <= int(target_year_count)
    }

    used_book_identities = set()

    for school_record in school_year_records or []:
        if not isinstance(school_record, dict):
            continue

        for field_name in ("assigned_books", "books"):
            for book in school_record.get(field_name, []) or []:
                used_book_identities.add(
                    school_year_book_identity(book)
                )

    for adult_year in range(1, int(target_year_count) + 1):
        existing_record = records_by_year.get(adult_year)

        if not manage_reading:
            records_by_year[adult_year] = normalize_adult_year_record(
                existing_record
                if existing_record is not None
                else {
                    "adult_year": adult_year,
                    "reading_characteristic": "",
                    "reading_rolls": [],
                    "books": [],
                    "eminence": [],
                    "jobs": [],
                }
            )
            continue

        if (
            existing_record is None
            or not existing_record.get("reading_rolls")
        ):
            generated_record = random_adult_year_record(
                adult_year,
                development_plan,
                randomizer,
                initial_characteristics,
                school_year_records,
                books,
                spells,
                proficiencies,
                used_book_identities,
            )

            if existing_record is not None:
                generated_record["eminence"] = deepcopy(
                    existing_record.get("eminence", [])
                )
                generated_record["jobs"] = deepcopy(
                    existing_record.get("jobs", [])
                )

            records_by_year[adult_year] = (
                normalize_adult_year_record(generated_record)
            )
        else:
            book_limit = int(
                existing_record.get("book_limit", 0) or 0
            )
            existing_record["books"] = select_school_year_books(
                development_plan,
                books or [],
                spells or [],
                proficiencies or [],
                randomizer,
                used_book_identities,
                existing_record.get("books", []),
                target_count=book_limit,
            )
            records_by_year[adult_year] = (
                normalize_adult_year_record(existing_record)
            )

        used_book_identities.update(
            school_year_book_identity(book)
            for book in records_by_year[adult_year].get(
                "books",
                [],
            )
        )

    return [
        records_by_year[adult_year]
        for adult_year in sorted(records_by_year)
    ]


def migrate_annual_progression_choices(
    development_plan,
    initial_characteristics,
    identity,
):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    selected_randomizer = random.Random(str(identity or "mage"))
    migrated_school_records = []

    for record in plan.get("school_years", []):
        year_number = int(record["year"])
        characteristic_options = (
            available_characteristic_buys(
                initial_characteristics,
                migrated_school_records,
                year_number,
            )
            if initial_characteristics not in (None, "", {})
            else CHARACTERISTIC_NAMES
        )
        characteristic = normalize_characteristic_name(
            record.get("characteristic"),
            allow_blank=True,
        )

        if characteristic not in characteristic_options:
            record["characteristic"] = random_characteristic_buy(
                characteristic_options,
                selected_randomizer,
            )

        migrated_school_records.append(
            normalize_school_year_record(record)
        )

    plan["school_years"] = migrated_school_records
    plan["adult_years"] = normalize_adult_year_records(
        plan.get("adult_years", [])
    )
    return normalize_development_plan(plan)


def indexed_skill_records(records):
    records_by_id = {}
    records_by_name = {}

    for record in records or []:
        if not isinstance(record, dict):
            continue

        record_id = str(
            record.get("record_id", "") or ""
        ).strip()
        record_name = str(
            record.get("name", "") or ""
        ).strip()

        if record_id:
            records_by_id[record_id] = record

        if record_name:
            records_by_name[record_name.casefold()] = record

    return records_by_id, records_by_name


def linked_record(reference, records_by_id, records_by_name):
    if isinstance(reference, dict):
        record_id = str(
            reference.get("record_id", "") or ""
        ).strip()
        record_name = str(
            reference.get("name", "") or ""
        ).strip()
        return (
            records_by_id.get(record_id)
            or records_by_name.get(record_name.casefold())
            or reference
        )

    reference_text = str(reference or "").strip()
    return (
        records_by_id.get(reference_text)
        or records_by_name.get(reference_text.casefold())
    )


def normalized_skill_from_record(record):
    if not isinstance(record, dict):
        return None

    try:
        return normalize_development_skill(record.get("skill"))
    except ValueError:
        return None


def book_linked_skill_sets(book, spells=None, proficiencies=None):
    spell_records_by_id, spell_records_by_name = (
        indexed_skill_records(spells)
    )
    proficiency_records_by_id, proficiency_records_by_name = (
        indexed_skill_records(proficiencies)
    )
    return book_linked_skill_sets_from_indexes(
        book,
        spell_records_by_id,
        spell_records_by_name,
        proficiency_records_by_id,
        proficiency_records_by_name,
    )


def book_linked_skill_sets_from_indexes(
    book,
    spell_records_by_id,
    spell_records_by_name,
    proficiency_records_by_id,
    proficiency_records_by_name,
):
    if not isinstance(book, dict):
        return set(), set()

    explicitly_linked_skills = set()

    for spell_reference in book.get("spells", []) or []:
        spell = linked_record(
            spell_reference,
            spell_records_by_id,
            spell_records_by_name,
        )
        skill = normalized_skill_from_record(spell)

        if skill:
            explicitly_linked_skills.add(skill)

    for proficiency_reference in (
        book.get("proficiencies", []) or []
    ):
        proficiency = linked_record(
            proficiency_reference,
            proficiency_records_by_id,
            proficiency_records_by_name,
        )
        skill = normalized_skill_from_record(proficiency)

        if skill:
            explicitly_linked_skills.add(skill)

    category_skills = set()

    for category in book.get("categories", []) or []:
        try:
            category_skills.add(
                normalize_development_skill(category)
            )
        except ValueError:
            continue

    return explicitly_linked_skills, category_skills


def normalized_book_candidates(books):
    candidates = []
    seen_identities = set()

    for book in books or []:
        if not isinstance(book, dict):
            continue

        try:
            book_reference = normalize_school_year_book(book)
        except (TypeError, ValueError):
            continue

        identity = school_year_book_identity(book_reference)

        if identity in seen_identities:
            continue

        candidates.append(
            {
                "source": deepcopy(book),
                "reference": book_reference,
                "identity": identity,
            }
        )
        seen_identities.add(identity)

    return candidates


def assigned_school_books_by_year(
    school_name,
    schools,
    books=None,
):
    normalized_school_name = str(school_name or "").strip().casefold()

    if not normalized_school_name:
        return {}

    selected_school = next(
        (
            school
            for school in schools or []
            if isinstance(school, dict)
            and str(school.get("name", "") or "")
            .strip()
            .casefold()
            == normalized_school_name
        ),
        None,
    )

    if selected_school is None:
        return {}

    books_by_id, books_by_name = indexed_skill_records(books)
    assigned_by_year = {}
    seen_by_year = {}

    for course_book in selected_school.get("course_books", []) or []:
        if not isinstance(course_book, dict):
            continue

        try:
            year_number = int(course_book.get("year"))
        except (TypeError, ValueError):
            continue

        if not 1 <= year_number <= 7:
            continue

        resolved_book = linked_record(
            course_book,
            books_by_id,
            books_by_name,
        )

        try:
            book_reference = normalize_school_year_book(
                resolved_book or course_book
            )
        except (TypeError, ValueError):
            continue

        identity = school_year_book_identity(book_reference)
        year_identities = seen_by_year.setdefault(
            year_number,
            set(),
        )

        if identity in year_identities:
            continue

        assigned_by_year.setdefault(year_number, []).append(
            book_reference
        )
        year_identities.add(identity)

    return assigned_by_year


def select_school_year_books(
    development_plan,
    books,
    spells=None,
    proficiencies=None,
    randomizer=None,
    excluded_book_identities=None,
    initial_books=None,
    target_count=SCHOOL_YEAR_BOOK_COUNT,
):
    try:
        selected_target_count = max(0, int(target_count))
    except (TypeError, ValueError) as error:
        raise ValueError(
            "The number of books to select must be a whole number."
        ) from error

    if selected_target_count == 0:
        return []

    excluded_identities = set(excluded_book_identities or ())
    normalized_initial_books = []
    normalized_initial_identities = set()

    for initial_book in initial_books or []:
        try:
            normalized_initial_book = normalize_school_year_book(
                initial_book
            )
        except (TypeError, ValueError):
            continue

        identity = school_year_book_identity(
            normalized_initial_book
        )

        if (
            identity in excluded_identities
            or identity in normalized_initial_identities
        ):
            continue

        normalized_initial_books.append(normalized_initial_book)
        normalized_initial_identities.add(identity)

        if len(normalized_initial_books) >= selected_target_count:
            break

    candidates = [
        candidate
        for candidate in normalized_book_candidates(books)
        if candidate["identity"] not in excluded_identities
    ]

    if not candidates:
        return normalized_initial_books

    selected_randomizer = randomizer or random
    preferred_skills = set(
        preferred_development_skills(development_plan)
    )
    spell_records_by_id, spell_records_by_name = (
        indexed_skill_records(spells)
    )
    proficiency_records_by_id, proficiency_records_by_name = (
        indexed_skill_records(proficiencies)
    )
    skill_sets_by_identity = {}

    for candidate in candidates:
        skill_sets_by_identity[candidate["identity"]] = (
            book_linked_skill_sets_from_indexes(
                candidate["source"],
                spell_records_by_id,
                spell_records_by_name,
                proficiency_records_by_id,
                proficiency_records_by_name,
            )
        )

    candidates_by_identity = {
        candidate["identity"]: candidate
        for candidate in candidates
    }
    selected_books = []
    selected_identities = set()

    for normalized_initial_book in normalized_initial_books:
        identity = school_year_book_identity(
            normalized_initial_book
        )

        if (
            identity in selected_identities
            or identity not in candidates_by_identity
        ):
            continue

        selected_books.append(
            deepcopy(
                candidates_by_identity[identity]["reference"]
            )
        )
        selected_identities.add(identity)

        if len(selected_books) >= selected_target_count:
            break

    while (
        len(selected_books) < selected_target_count
        and len(selected_identities) < len(candidates)
    ):
        remaining_candidates = [
            candidate
            for candidate in candidates
            if candidate["identity"] not in selected_identities
        ]
        explicit_matches = [
            candidate
            for candidate in remaining_candidates
            if (
                skill_sets_by_identity[candidate["identity"]][0]
                & preferred_skills
            )
        ]
        category_matches = [
            candidate
            for candidate in remaining_candidates
            if (
                candidate not in explicit_matches
                and (
                    skill_sets_by_identity[
                        candidate["identity"]
                    ][1]
                    & preferred_skills
                )
            )
        ]
        preferred_matches = explicit_matches or category_matches
        all_matching_identities = {
            candidate["identity"]
            for candidate in explicit_matches + category_matches
        }
        deviation_matches = [
            candidate
            for candidate in remaining_candidates
            if candidate["identity"] not in all_matching_identities
        ]
        use_preferred = (
            bool(preferred_matches)
            and selected_randomizer.random()
            < STRATEGY_PREFERENCE_PROBABILITY
        )
        selection_pool = (
            preferred_matches
            if use_preferred
            else deviation_matches or remaining_candidates
        )
        selected_candidate = selected_randomizer.choice(
            selection_pool
        )
        selected_books.append(
            deepcopy(selected_candidate["reference"])
        )
        selected_identities.add(selected_candidate["identity"])

    return selected_books


def random_school_year_record(
    year_number,
    development_plan,
    books=None,
    spells=None,
    proficiencies=None,
    randomizer=None,
    school_name="",
    assigned_books=None,
    excluded_book_identities=None,
    characteristic_options=None,
    curriculum_year=None,
    previous_electives=None,
):
    improvements = random_annual_improvements(
        development_plan,
        randomizer,
    )
    curriculum = (
        curriculum_year
        if isinstance(curriculum_year, dict)
        else None
    )
    selected_electives = (
        select_school_year_electives(
            curriculum.get("electives", []),
            curriculum.get("elective_limit", 0),
            development_plan,
            randomizer,
            previous_electives,
        )
        if curriculum is not None
        else []
    )
    record = {
        "year": int(year_number),
        "school": str(school_name or "").strip(),
        "skipped": False,
        "ability": improvements["ability"],
        "skills": improvements["skills"],
        "characteristic": random_characteristic_buy(
            characteristic_options or CHARACTERISTIC_NAMES,
            randomizer,
        ),
        "electives": selected_electives,
        "electives_initialized": curriculum is not None,
        "assigned_books": deepcopy(assigned_books or []),
        "books": select_school_year_books(
            development_plan,
            books or [],
            spells or [],
            proficiencies or [],
            randomizer,
            excluded_book_identities,
        ),
        "eminence": [],
    }
    return normalize_school_year_record(record)


def rebuild_school_year_records(
    records,
    development_plan,
    randomizer=None,
    initial_characteristics=None,
    schools=None,
):
    normalized_records = normalize_school_year_records(records)
    rebuilt_records = []

    for existing_record in normalized_records:
        year_number = existing_record["year"]
        previous_electives = []

        for previous_record in reversed(rebuilt_records):
            if previous_record.get("electives"):
                previous_electives = list(
                    previous_record["electives"]
                )
                break

        characteristic_options = (
            available_characteristic_buys(
                initial_characteristics,
                rebuilt_records,
                year_number,
            )
            if initial_characteristics not in (None, "", {})
            else CHARACTERISTIC_NAMES
        )
        curriculum_year = None

        if schools is not None:
            curriculum_year = school_curriculum_year(
                schools,
                existing_record.get("school", ""),
                year_number,
            ) or {
                "year": year_number,
                "core": [],
                "electives": [],
                "elective_limit": 0,
            }

        rebuilt_record = random_school_year_record(
            year_number,
            development_plan,
            randomizer=randomizer,
            school_name=existing_record.get("school", ""),
            assigned_books=existing_record.get(
                "assigned_books",
                [],
            ),
            characteristic_options=characteristic_options,
            curriculum_year=curriculum_year,
            previous_electives=previous_electives,
        )
        rebuilt_record["skipped"] = bool(
            existing_record.get("skipped", False)
        )

        if schools is None:
            rebuilt_record["electives"] = deepcopy(
                existing_record.get("electives", [])
            )
            rebuilt_record["electives_initialized"] = bool(
                existing_record.get(
                    "electives_initialized",
                    False,
                )
            )

        if rebuilt_record["skipped"]:
            rebuilt_record["electives"] = []
            rebuilt_record["electives_initialized"] = False

        rebuilt_record["books"] = deepcopy(
            existing_record.get("books", [])
        )
        rebuilt_record["eminence"] = deepcopy(
            existing_record.get("eminence", [])
        )
        rebuilt_records.append(
            normalize_school_year_record(rebuilt_record)
        )

    return rebuilt_records


def ensure_school_year_records(
    records,
    target_year_count,
    development_plan,
    books=None,
    spells=None,
    proficiencies=None,
    randomizer=None,
    school_name="",
    assigned_books_by_year=None,
    initial_characteristics=None,
    manage_books=True,
    schools=None,
):
    normalized_records = reconcile_school_year_characteristic_buys(
        initial_characteristics,
        records,
    )
    records_by_year = {
        record["year"]: record
        for record in normalized_records
        if record["year"] <= int(target_year_count)
    }

    selected_school_name = str(school_name or "").strip()
    assignments = (
        assigned_books_by_year
        if manage_books and isinstance(assigned_books_by_year, dict)
        else {}
    )
    assigned_identities = set()
    intentional_identities = set()

    for year_number in range(1, int(target_year_count) + 1):
        existing_record = records_by_year.get(year_number)
        earlier_records = [
            records_by_year[earlier_year]
            for earlier_year in sorted(records_by_year)
            if earlier_year < year_number
        ]
        previous_electives = []

        for earlier_record in reversed(earlier_records):
            if earlier_record.get("electives"):
                previous_electives = list(
                    earlier_record["electives"]
                )
                break

        characteristic_options = (
            available_characteristic_buys(
                initial_characteristics,
                earlier_records,
                year_number,
            )
            if initial_characteristics not in (None, "", {})
            else CHARACTERISTIC_NAMES
        )

        if existing_record is None:
            assigned_books = deepcopy(
                assignments.get(year_number, [])
            )

            for assigned_book in assigned_books:
                assigned_identities.add(
                    school_year_book_identity(assigned_book)
                )

            curriculum_year = None

            if schools is not None:
                curriculum_year = school_curriculum_year(
                    schools,
                    selected_school_name,
                    year_number,
                ) or {
                    "year": year_number,
                    "core": [],
                    "electives": [],
                    "elective_limit": 0,
                }

            records_by_year[year_number] = random_school_year_record(
                year_number,
                development_plan,
                books if manage_books else [],
                spells,
                proficiencies,
                randomizer,
                selected_school_name,
                assigned_books,
                assigned_identities | intentional_identities,
                characteristic_options,
                curriculum_year,
                previous_electives,
            )
            intentional_identities.update(
                school_year_book_identity(book)
                for book in records_by_year[year_number].get(
                    "books",
                    [],
                )
            )
            continue

        record_school = str(
            existing_record.get("school", "") or ""
        ).strip()
        school_changed = False
        existing_characteristic = normalize_characteristic_name(
            existing_record.get("characteristic"),
            allow_blank=True,
        )

        if existing_characteristic not in characteristic_options:
            existing_record["characteristic"] = (
                random_characteristic_buy(
                    characteristic_options,
                    randomizer,
                )
            )

        if bool(existing_record.get("skipped", False)):
            school_changed = (
                record_school.casefold()
                != selected_school_name.casefold()
            )
            existing_record["school"] = selected_school_name
            existing_record["electives"] = []
            existing_record["electives_initialized"] = False

            if manage_books:
                for assigned_book in assignments.get(
                    year_number,
                    [],
                ):
                    assigned_identities.add(
                        school_year_book_identity(assigned_book)
                    )

                existing_record["assigned_books"] = []
                existing_record["books"] = select_school_year_books(
                    development_plan,
                    books or [],
                    spells or [],
                    proficiencies or [],
                    randomizer,
                    assigned_identities | intentional_identities,
                    existing_record.get("books", []),
                )

            records_by_year[year_number] = (
                normalize_school_year_record(existing_record)
            )
            intentional_identities.update(
                school_year_book_identity(book)
                for book in records_by_year[year_number].get(
                    "books",
                    [],
                )
            )
            continue

        if (
            not record_school
            or record_school.casefold()
            == selected_school_name.casefold()
        ):
            school_changed = (
                record_school.casefold()
                != selected_school_name.casefold()
            )
            existing_record["school"] = selected_school_name

            if manage_books:
                existing_record["assigned_books"] = deepcopy(
                    assignments.get(year_number, [])
                )

        if manage_books:
            for assigned_book in existing_record.get(
                "assigned_books",
                [],
            ):
                assigned_identities.add(
                    school_year_book_identity(assigned_book)
                )

            existing_record["books"] = select_school_year_books(
                development_plan,
                books or [],
                spells or [],
                proficiencies or [],
                randomizer,
                assigned_identities | intentional_identities,
                existing_record.get("books", []),
            )

        if schools is not None:
            curriculum_year = school_curriculum_year(
                schools,
                existing_record.get("school", ""),
                year_number,
            ) or {
                "year": year_number,
                "core": [],
                "electives": [],
                "elective_limit": 0,
            }

            if (
                school_changed
                or not bool(
                    existing_record.get(
                        "electives_initialized",
                        False,
                    )
                )
            ):
                existing_record["electives"] = (
                    select_school_year_electives(
                        curriculum_year["electives"],
                        curriculum_year["elective_limit"],
                        development_plan,
                        randomizer,
                        previous_electives,
                    )
                )
            else:
                existing_record["electives"] = (
                    reconcile_school_year_electives(
                        existing_record.get("electives", []),
                        curriculum_year["electives"],
                        curriculum_year["elective_limit"],
                    )
                )

            existing_record["electives_initialized"] = True

        records_by_year[year_number] = normalize_school_year_record(
            existing_record
        )
        intentional_identities.update(
            school_year_book_identity(book)
            for book in records_by_year[year_number].get(
                "books",
                [],
            )
        )

    return [
        records_by_year[year_number]
        for year_number in sorted(records_by_year)
    ]
