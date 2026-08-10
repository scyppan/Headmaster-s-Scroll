import random
from copy import deepcopy
from operator import itemgetter


BLOOD_STATUS_PUREBLOOD = "Pureblood"
BLOOD_STATUS_HALFBLOOD = "Halfblood"
BLOOD_STATUS_MUGGLEBORN = "Muggleborn"
BLOOD_STATUS_OPTIONS = (
    BLOOD_STATUS_PUREBLOOD,
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_MUGGLEBORN,
)
DEVELOPMENTAL_ENVIRONMENT_MAGICAL = "Magical"
DEVELOPMENTAL_ENVIRONMENT_MUGGLE = "Muggle"
DEVELOPMENTAL_ENVIRONMENT_OPTIONS = (
    DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
    DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
)
PARENT_MAGIC_STATE_MAGICAL = "magical"
PARENT_MAGIC_STATE_NON_MAGICAL = "non-magical"
PARENT_MAGIC_STATE_UNKNOWN = "unknown"
PARENTAL_VALUE_NAMES = (
    "generosity",
    "permissiveness",
    "wealth",
)
PARENTAL_VALUE_MINIMUM = 1
PARENTAL_VALUE_MAXIMUM = 10
PARENTAL_MODE_SHARED = "Same as siblings"
PARENTAL_MODE_SLIGHTLY_RANDOMIZED = "Slightly randomize"
PARENTAL_MODE_FULLY_RANDOMIZED = "Fully randomize"
PARENTAL_MODE_OVERRIDE = "Override"
PARENTAL_MODE_OPTIONS = (
    PARENTAL_MODE_SHARED,
    PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
    PARENTAL_MODE_FULLY_RANDOMIZED,
    PARENTAL_MODE_OVERRIDE,
)
PARENTAL_SLIGHT_DELTA_OPTIONS = (-2, -1, 0, 1, 2)
PARENTAL_SLIGHT_DELTA_WEIGHTS = (1, 24, 50, 24, 1)
PARENTAL_SLIGHT_MAXIMUM_DEVIATION = 2


def normalize_blood_status(value, default=None):
    normalized_value = " ".join(
        str(value or "")
        .strip()
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )
    aliases = {
        "pureblood": BLOOD_STATUS_PUREBLOOD,
        "pure blood": BLOOD_STATUS_PUREBLOOD,
        "halfblood": BLOOD_STATUS_HALFBLOOD,
        "half blood": BLOOD_STATUS_HALFBLOOD,
        "magically raised halfblood": BLOOD_STATUS_HALFBLOOD,
        "magically raised half blood": BLOOD_STATUS_HALFBLOOD,
        "wizard raised halfblood": BLOOD_STATUS_HALFBLOOD,
        "wizarding raised halfblood": BLOOD_STATUS_HALFBLOOD,
        "muggle raised halfblood": BLOOD_STATUS_HALFBLOOD,
        "muggle raised half blood": BLOOD_STATUS_HALFBLOOD,
        "muggleborn": BLOOD_STATUS_MUGGLEBORN,
        "muggle born": BLOOD_STATUS_MUGGLEBORN,
    }

    if not normalized_value and default is not None:
        return normalize_blood_status(default)

    blood_status = aliases.get(normalized_value)

    if blood_status is None:
        valid_values = ", ".join(BLOOD_STATUS_OPTIONS)
        raise ValueError(
            f"Blood status must be one of: {valid_values}."
        )

    return blood_status


def legacy_developmental_environment(blood_status):
    normalized_value = " ".join(
        str(blood_status or "")
        .strip()
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )

    if normalized_value in (
        "magically raised halfblood",
        "magically raised half blood",
        "wizard raised halfblood",
        "wizarding raised halfblood",
    ):
        return DEVELOPMENTAL_ENVIRONMENT_MAGICAL

    if normalized_value in (
        "muggle raised halfblood",
        "muggle raised half blood",
    ):
        return DEVELOPMENTAL_ENVIRONMENT_MUGGLE

    return ""


def normalize_developmental_environment(
    value,
    blood_status,
    default=DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
):
    normalized_blood_status = normalize_blood_status(blood_status)

    if normalized_blood_status != BLOOD_STATUS_HALFBLOOD:
        return ""

    normalized_value = " ".join(
        str(value or "")
        .strip()
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )
    aliases = {
        "magical": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "magic": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "wizard": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "wizarding": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "magical world": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "wizarding world": DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
        "muggle": DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
        "non magical": DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
        "muggle world": DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
    }

    if not normalized_value:
        normalized_value = str(default or "").strip().casefold()

    developmental_environment = aliases.get(normalized_value)

    if developmental_environment is None:
        valid_values = ", ".join(DEVELOPMENTAL_ENVIRONMENT_OPTIONS)
        raise ValueError(
            "Developmental environment must be one of: "
            f"{valid_values}."
        )

    return developmental_environment


def person_magic_state(person):
    if not isinstance(person, dict):
        return PARENT_MAGIC_STATE_UNKNOWN

    if bool(person.get("non_magical")):
        return PARENT_MAGIC_STATE_NON_MAGICAL

    return PARENT_MAGIC_STATE_MAGICAL


def parent_magic_states(person, people):
    person_values = person if isinstance(person, dict) else {}
    people_by_id = (
        people
        if isinstance(people, dict)
        else {
            str(candidate.get("record_id", "") or "").strip(): candidate
            for candidate in people
            if isinstance(candidate, dict)
            and str(candidate.get("record_id", "") or "").strip()
        }
    )
    states = []

    for parent_role in ("mother", "father"):
        parent_id = str(
            person_values.get(
                f"biological_{parent_role}_id",
                "",
            )
            or ""
        ).strip()
        parent_status = str(
            person_values.get(
                f"biological_{parent_role}_status",
                "unknown",
            )
            or "unknown"
        ).strip().casefold()

        if parent_id:
            states.append(
                person_magic_state(people_by_id.get(parent_id))
            )
        elif parent_status == "muggle":
            states.append(PARENT_MAGIC_STATE_NON_MAGICAL)
        else:
            states.append(PARENT_MAGIC_STATE_UNKNOWN)

    return tuple(states)


def blood_status_options(person, people):
    known_states = [
        state
        for state in parent_magic_states(person, people)
        if state != PARENT_MAGIC_STATE_UNKNOWN
    ]

    if not known_states:
        return BLOOD_STATUS_OPTIONS

    if len(known_states) == 1:
        if known_states[0] == PARENT_MAGIC_STATE_MAGICAL:
            return (
                BLOOD_STATUS_PUREBLOOD,
                BLOOD_STATUS_HALFBLOOD,
            )

        return (
            BLOOD_STATUS_HALFBLOOD,
            BLOOD_STATUS_MUGGLEBORN,
        )

    if all(
        state == PARENT_MAGIC_STATE_MAGICAL
        for state in known_states
    ):
        return (BLOOD_STATUS_PUREBLOOD,)

    if all(
        state == PARENT_MAGIC_STATE_NON_MAGICAL
        for state in known_states
    ):
        return (BLOOD_STATUS_MUGGLEBORN,)

    return (BLOOD_STATUS_HALFBLOOD,)


def resolved_blood_status(person, people):
    person_values = (
        deepcopy(person)
        if isinstance(person, dict)
        else {}
    )
    available_options = blood_status_options(
        person_values,
        people,
    )
    stored_value = person_values.get("blood_status")

    try:
        stored_status = normalize_blood_status(stored_value)
    except ValueError:
        stored_status = None

    if stored_status in available_options:
        return stored_status

    return available_options[0]


def randomized_blood_status(person, people):
    return random.choice(
        blood_status_options(person, people)
    )


def resolved_developmental_environment(person, people):
    person_values = person if isinstance(person, dict) else {}
    blood_status = resolved_blood_status(person_values, people)

    if blood_status != BLOOD_STATUS_HALFBLOOD:
        return ""

    stored_environment = person_values.get(
        "developmental_environment",
        "",
    )

    if not stored_environment:
        stored_environment = legacy_developmental_environment(
            person_values.get("blood_status")
        )

    return normalize_developmental_environment(
        stored_environment,
        blood_status,
    )


def require_blood_status_compatible(person, people):
    person_values = person if isinstance(person, dict) else {}
    blood_status = normalize_blood_status(
        person_values.get("blood_status")
    )
    available_options = blood_status_options(
        person_values,
        people,
    )

    if blood_status not in available_options:
        if blood_status == BLOOD_STATUS_PUREBLOOD:
            raise ValueError(
                "Pureblood individuals can only have magical parents."
            )

        if blood_status == BLOOD_STATUS_MUGGLEBORN:
            raise ValueError(
                "Muggleborn individuals can only have non-magical parents."
            )

        raise ValueError(
            "A Halfblood must have one magical and one non-magical "
            "parent once both parents are assigned."
        )

    normalize_developmental_environment(
        person_values.get("developmental_environment"),
        blood_status,
    )
    return blood_status


def blood_status_is_compatible(person, people):
    person_values = (
        deepcopy(person)
        if isinstance(person, dict)
        else {}
    )

    if not person_values.get("blood_status"):
        person_values["blood_status"] = resolved_blood_status(
            person_values,
            people,
        )

    person_values["developmental_environment"] = (
        resolved_developmental_environment(
            person_values,
            people,
        )
    )

    try:
        require_blood_status_compatible(person_values, people)
    except (TypeError, ValueError):
        return False

    return True


def allowed_parent_magic_states(person, people, parent_role):
    if parent_role not in ("mother", "father"):
        raise ValueError(
            "Parent role must be birthing parent or "
            "non-birthing parent."
        )

    person_values = person if isinstance(person, dict) else {}
    blood_status = normalize_blood_status(
        person_values.get("blood_status"),
        default=resolved_blood_status(person_values, people),
    )

    if blood_status == BLOOD_STATUS_PUREBLOOD:
        return (PARENT_MAGIC_STATE_MAGICAL,)

    if blood_status == BLOOD_STATUS_MUGGLEBORN:
        return (PARENT_MAGIC_STATE_NON_MAGICAL,)

    states = parent_magic_states(person_values, people)
    other_index = 1 if parent_role == "mother" else 0
    other_parent_state = states[other_index]

    if other_parent_state == PARENT_MAGIC_STATE_MAGICAL:
        return (PARENT_MAGIC_STATE_NON_MAGICAL,)

    if other_parent_state == PARENT_MAGIC_STATE_NON_MAGICAL:
        return (PARENT_MAGIC_STATE_MAGICAL,)

    return (
        PARENT_MAGIC_STATE_MAGICAL,
        PARENT_MAGIC_STATE_NON_MAGICAL,
    )


def parent_candidate_explanation(person, people, parent_role):
    allowed_states = allowed_parent_magic_states(
        person,
        people,
        parent_role,
    )
    blood_status = resolved_blood_status(person, people)

    if allowed_states == (PARENT_MAGIC_STATE_MAGICAL,):
        if blood_status == BLOOD_STATUS_PUREBLOOD:
            return (
                "Showing only magical parent options because blood "
                "status is set to Pureblood."
            )

        return (
            "Showing only magical parent options because blood status "
            "is set to Halfblood and the other parent is non-magical."
        )

    if allowed_states == (PARENT_MAGIC_STATE_NON_MAGICAL,):
        if blood_status == BLOOD_STATUS_MUGGLEBORN:
            return (
                "Showing only non-magical parent options because blood "
                "status is set to Muggleborn."
            )

        return (
            "Showing only non-magical parent options because blood "
            "status is set to Halfblood and the other parent is magical."
        )

    return (
        "Showing magical and non-magical parent options because blood "
        "status is set to Halfblood and the other parent is not assigned."
    )


def normalize_parental_value(value, field_name):
    if isinstance(value, bool):
        raise ValueError(
            f"{field_name.title()} must be a whole number from "
            f"{PARENTAL_VALUE_MINIMUM} to {PARENTAL_VALUE_MAXIMUM}."
        )

    try:
        normalized_value = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(
            f"{field_name.title()} must be a whole number from "
            f"{PARENTAL_VALUE_MINIMUM} to {PARENTAL_VALUE_MAXIMUM}."
        ) from error

    if not PARENTAL_VALUE_MINIMUM <= normalized_value <= PARENTAL_VALUE_MAXIMUM:
        raise ValueError(
            f"{field_name.title()} must be from "
            f"{PARENTAL_VALUE_MINIMUM} to {PARENTAL_VALUE_MAXIMUM}."
        )

    return normalized_value


def normalize_parental_mode(value):
    normalized_value = " ".join(
        str(value or "")
        .strip()
        .casefold()
        .replace("_", " ")
        .replace("-", " ")
        .split()
    )
    aliases = {
        "": PARENTAL_MODE_SHARED,
        "same": PARENTAL_MODE_SHARED,
        "shared": PARENTAL_MODE_SHARED,
        "same as siblings": PARENTAL_MODE_SHARED,
        "match siblings": PARENTAL_MODE_SHARED,
        "slight": PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
        "slightly alter": PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
        "slightly randomize": PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
        "slightly randomized": PARENTAL_MODE_SLIGHTLY_RANDOMIZED,
        "full": PARENTAL_MODE_FULLY_RANDOMIZED,
        "fully random": PARENTAL_MODE_FULLY_RANDOMIZED,
        "fully randomize": PARENTAL_MODE_FULLY_RANDOMIZED,
        "fully randomized": PARENTAL_MODE_FULLY_RANDOMIZED,
        "override": PARENTAL_MODE_OVERRIDE,
        "manual": PARENTAL_MODE_OVERRIDE,
    }
    parental_mode = aliases.get(normalized_value)

    if parental_mode is None:
        valid_values = ", ".join(PARENTAL_MODE_OPTIONS)
        raise ValueError(
            f"Parental value handling must be one of: {valid_values}."
        )

    return parental_mode


def normalize_parental_values(value, allow_uninitialized=True):
    if value in (None, "", {}):
        if allow_uninitialized:
            return None

        raise ValueError("Parental values have not been initialized.")

    if not isinstance(value, dict):
        raise TypeError("Parental values must be a dictionary.")

    if value.get("initialized") is False:
        if allow_uninitialized:
            return None

        raise ValueError("Parental values have not been initialized.")

    mode = normalize_parental_mode(value.get("mode"))
    normalized_values = {
        field_name: normalize_parental_value(
            value.get(field_name),
            field_name,
        )
        for field_name in PARENTAL_VALUE_NAMES
    }
    stored_family_values = value.get("family_values")
    family_source = (
        stored_family_values
        if isinstance(stored_family_values, dict)
        else normalized_values
    )
    family_values = {
        field_name: normalize_parental_value(
            family_source.get(
                field_name,
                normalized_values[field_name],
            ),
            field_name,
        )
        for field_name in PARENTAL_VALUE_NAMES
    }

    if mode == PARENTAL_MODE_SHARED:
        normalized_values = deepcopy(family_values)

    if mode == PARENTAL_MODE_SLIGHTLY_RANDOMIZED:
        for field_name in PARENTAL_VALUE_NAMES:
            if abs(
                normalized_values[field_name]
                - family_values[field_name]
            ) > PARENTAL_SLIGHT_MAXIMUM_DEVIATION:
                raise ValueError(
                    "Slightly randomized parental values may differ "
                    "from the sibling baseline by at most two."
                )

    return {
        "initialized": True,
        "mode": mode,
        "source": str(value.get("source", "random") or "random"),
        "family_values": family_values,
        **normalized_values,
    }


def parental_family_key(person):
    if not isinstance(person, dict):
        return None

    parent_keys = []
    named_parent_count = 0

    for parent_role in ("mother", "father"):
        parent_id = str(
            person.get(f"biological_{parent_role}_id", "") or ""
        ).strip()
        parent_status = str(
            person.get(
                f"biological_{parent_role}_status",
                "unknown",
            )
            or "unknown"
        ).strip().casefold()

        if parent_id:
            parent_keys.append(f"person:{parent_id}")
            named_parent_count += 1
        elif parent_status == "muggle":
            parent_keys.append(f"muggle:{parent_role}")
        else:
            return None

    if named_parent_count == 0:
        return None

    return tuple(parent_keys)


def parental_parent_ids(person):
    if not isinstance(person, dict):
        return ()

    parent_ids = []

    for parent_role in ("mother", "father"):
        parent_id = str(
            person.get(f"biological_{parent_role}_id", "") or ""
        ).strip()

        if parent_id and parent_id not in parent_ids:
            parent_ids.append(parent_id)

    return tuple(parent_ids)


def parental_birth_position(person):
    if not isinstance(person, dict):
        return None

    try:
        birth_year = int(person.get("birth_year"))
    except (TypeError, ValueError):
        return None

    try:
        birth_month = int(person.get("birth_month"))
    except (TypeError, ValueError):
        birth_month = 7

    if not 1 <= birth_month <= 12:
        birth_month = 7

    try:
        birth_day = int(person.get("birth_day"))
    except (TypeError, ValueError):
        birth_day = 16

    if not 1 <= birth_day <= 31:
        birth_day = 16

    return (
        birth_year * 372
        + (birth_month - 1) * 31
        + birth_day
    )


def parental_sibling_reference(
    person,
    people,
    excluded_record_id="",
    include_context=False,
):
    if not isinstance(person, dict):
        return None

    current_id = str(person.get("record_id", "") or "").strip()
    excluded_id = str(excluded_record_id or "").strip()
    current_parent_ids = set(parental_parent_ids(person))

    if not current_parent_ids:
        return None

    people_by_id = {
        str(candidate.get("record_id", "") or "").strip(): candidate
        for candidate in people
        if isinstance(candidate, dict)
        and str(candidate.get("record_id", "") or "").strip()
    }
    candidates = []

    for candidate_id, candidate in people_by_id.items():
        if candidate_id in (current_id, excluded_id):
            continue

        shared_parent_ids = current_parent_ids.intersection(
            parental_parent_ids(candidate)
        )

        if not shared_parent_ids:
            continue

        parental_values = normalize_parental_values(
            candidate.get("parental_values")
        )

        if parental_values is None:
            continue

        candidates.append(
            {
                "person": {
                    **deepcopy(candidate),
                    "parental_values": parental_values,
                },
                "shared_parent_ids": tuple(
                    sorted(shared_parent_ids)
                ),
            }
        )

    if not candidates:
        return None

    parent_wealth_values = {}

    for parent_id in current_parent_ids:
        parent = people_by_id.get(parent_id)
        parent_values = normalize_parental_values(
            parent.get("parental_values")
            if isinstance(parent, dict)
            else None
        )

        if parent_values is not None:
            parent_wealth_values[parent_id] = parent_values["wealth"]

    if not parent_wealth_values:
        for parent_id in current_parent_ids:
            sibling_wealth_values = [
                candidate["person"]["parental_values"]["wealth"]
                for candidate in candidates
                if parent_id in candidate["shared_parent_ids"]
            ]

            if sibling_wealth_values:
                parent_wealth_values[parent_id] = max(
                    sibling_wealth_values
                )

    if parent_wealth_values:
        wealthiest_value = max(parent_wealth_values.values())
        wealthiest_parent_ids = {
            parent_id
            for parent_id, wealth_value in parent_wealth_values.items()
            if wealth_value == wealthiest_value
        }
        wealthiest_parent_candidates = [
            candidate
            for candidate in candidates
            if wealthiest_parent_ids.intersection(
                candidate["shared_parent_ids"]
            )
        ]

        if wealthiest_parent_candidates:
            candidates = wealthiest_parent_candidates

    current_birth_position = parental_birth_position(person)

    for candidate in candidates:
        candidate_birth_position = parental_birth_position(
            candidate["person"]
        )
        ages_are_comparable = (
            current_birth_position is not None
            and candidate_birth_position is not None
        )
        candidate["sort_key"] = (
            0 if ages_are_comparable else 1,
            (
                abs(
                    current_birth_position
                    - candidate_birth_position
                )
                if ages_are_comparable
                else 0
            ),
            -len(candidate["shared_parent_ids"]),
            str(
                candidate["person"].get("created_at", "") or ""
            ),
            str(
                candidate["person"].get("displayed_name", "") or ""
            ).casefold(),
            str(
                candidate["person"].get("record_id", "") or ""
            ),
        )

    candidates.sort(key=itemgetter("sort_key"))

    if include_context:
        return {
            "reference": deepcopy(candidates[0]["person"]),
            "siblings": [
                deepcopy(candidate["person"])
                for candidate in candidates
            ],
        }

    return deepcopy(candidates[0]["person"])


def family_parental_base(person, people, excluded_record_id=""):
    sibling = parental_sibling_reference(
        person,
        people,
        excluded_record_id=excluded_record_id,
    )

    if sibling is None:
        return None

    return {
        field_name: sibling["parental_values"][field_name]
        for field_name in PARENTAL_VALUE_NAMES
    }


def imported_parental_values(person):
    if not isinstance(person, dict):
        return None

    imported_fields = person.get("imported_fields")

    if not isinstance(imported_fields, dict):
        return None

    imported_values = {}

    for field_name in PARENTAL_VALUE_NAMES:
        imported_value = imported_fields.get(field_name.title())

        if imported_value in (None, ""):
            return None

        try:
            imported_values[field_name] = normalize_parental_value(
                imported_value,
                field_name,
            )
        except ValueError:
            return None

    return imported_values


def generational_wealth(person, people):
    if not isinstance(person, dict):
        return None

    people_by_id = {
        str(candidate.get("record_id", "") or ""): candidate
        for candidate in people
        if isinstance(candidate, dict)
        and str(candidate.get("record_id", "") or "")
    }
    inherited_wealth_values = []

    for parent_role in ("mother", "father"):
        parent_id = str(
            person.get(f"biological_{parent_role}_id", "") or ""
        )
        parent = people_by_id.get(parent_id)

        if parent is None:
            continue

        parental_values = normalize_parental_values(
            parent.get("parental_values")
        )

        if parental_values is not None:
            inherited_wealth_values.append(
                parental_values["wealth"]
            )

    if not inherited_wealth_values:
        return None

    inherited_wealth = max(inherited_wealth_values)
    wealth_delta = random.choice((-1, 0, 1, 1))
    inferred_wealth = max(
        PARENTAL_VALUE_MINIMUM,
        min(
            PARENTAL_VALUE_MAXIMUM,
            inherited_wealth + wealth_delta,
        ),
    )

    if inherited_wealth >= 7:
        inferred_wealth = max(7, inferred_wealth)

    return inferred_wealth


def build_parental_values(
    values,
    mode=PARENTAL_MODE_SHARED,
    source="random",
    family_values=None,
):
    normalized_values = {
        field_name: normalize_parental_value(
            values.get(field_name),
            field_name,
        )
        for field_name in PARENTAL_VALUE_NAMES
    }
    normalized_family_values = (
        {
            field_name: normalize_parental_value(
                family_values.get(field_name),
                field_name,
            )
            for field_name in PARENTAL_VALUE_NAMES
        }
        if isinstance(family_values, dict)
        else deepcopy(normalized_values)
    )
    return normalize_parental_values(
        {
            "initialized": True,
            "mode": mode,
            "source": source,
            "family_values": normalized_family_values,
            **normalized_values,
        },
        allow_uninitialized=False,
    )


def initialize_parental_values(person, people):
    person_values = person if isinstance(person, dict) else {}
    existing_values = normalize_parental_values(
        person_values.get("parental_values")
    )

    if existing_values is not None:
        return existing_values

    imported_values = imported_parental_values(person_values)

    if imported_values is not None:
        return build_parental_values(
            imported_values,
            mode=PARENTAL_MODE_OVERRIDE,
            source="imported",
        )

    sibling_values = family_parental_base(
        person_values,
        people,
        excluded_record_id=person_values.get("record_id"),
    )

    if sibling_values is not None:
        return build_parental_values(
            sibling_values,
            mode=PARENTAL_MODE_SHARED,
            source="sibling",
            family_values=sibling_values,
        )

    inherited_wealth = generational_wealth(person_values, people)
    randomized_values = {
        "generosity": random.randint(
            PARENTAL_VALUE_MINIMUM,
            PARENTAL_VALUE_MAXIMUM,
        ),
        "permissiveness": random.randint(
            PARENTAL_VALUE_MINIMUM,
            PARENTAL_VALUE_MAXIMUM,
        ),
        "wealth": (
            inherited_wealth
            if inherited_wealth is not None
            else random.randint(
                PARENTAL_VALUE_MINIMUM,
                PARENTAL_VALUE_MAXIMUM,
            )
        ),
    }
    return build_parental_values(
        randomized_values,
        mode=PARENTAL_MODE_SHARED,
        source=(
            "generational wealth"
            if inherited_wealth is not None
            else "random"
        ),
    )


def parental_values_for_mode(person, people, current_values, mode):
    normalized_current = normalize_parental_values(
        current_values,
        allow_uninitialized=False,
    )
    normalized_mode = normalize_parental_mode(mode)
    sibling_context = parental_sibling_reference(
        person,
        people,
        excluded_record_id=(
            person.get("record_id")
            if isinstance(person, dict)
            else ""
        ),
        include_context=True,
    )

    if sibling_context is None:
        family_values = deepcopy(
            normalized_current["family_values"]
        )
        sibling_people = []
    else:
        sibling_reference = sibling_context["reference"]
        family_values = {
            field_name: sibling_reference["parental_values"][field_name]
            for field_name in PARENTAL_VALUE_NAMES
        }
        sibling_people = sibling_context["siblings"]

    if normalized_mode == PARENTAL_MODE_OVERRIDE:
        return build_parental_values(
            normalized_current,
            mode=normalized_mode,
            source="override",
            family_values=family_values,
        )

    if normalized_mode == PARENTAL_MODE_FULLY_RANDOMIZED:
        randomized_values = {
            field_name: random.randint(
                PARENTAL_VALUE_MINIMUM,
                PARENTAL_VALUE_MAXIMUM,
            )
            for field_name in PARENTAL_VALUE_NAMES
        }
        return build_parental_values(
            randomized_values,
            mode=normalized_mode,
            source="fully randomized",
            family_values=family_values,
        )

    if normalized_mode == PARENTAL_MODE_SHARED:
        return build_parental_values(
            family_values,
            mode=normalized_mode,
            source="sibling" if parental_family_key(person) else "random",
            family_values=family_values,
        )

    wealth_minimum = max(
        PARENTAL_VALUE_MINIMUM,
        family_values["wealth"]
        - PARENTAL_SLIGHT_MAXIMUM_DEVIATION,
    )
    wealth_maximum = min(
        PARENTAL_VALUE_MAXIMUM,
        family_values["wealth"]
        + PARENTAL_SLIGHT_MAXIMUM_DEVIATION,
    )
    current_birth_position = parental_birth_position(person)

    if current_birth_position is not None and len(sibling_people) >= 2:
        ordered_sibling_wealth = []

        for sibling in sibling_people:
            sibling_birth_position = parental_birth_position(sibling)

            if sibling_birth_position is None:
                continue

            ordered_sibling_wealth.append(
                (
                    sibling_birth_position,
                    sibling["parental_values"]["wealth"],
                    str(sibling.get("record_id", "") or ""),
                )
            )

        ordered_sibling_wealth.sort()
        older_sibling_wealth = [
            sibling_values
            for sibling_values in ordered_sibling_wealth
            if sibling_values[0] < current_birth_position
        ]
        younger_sibling_wealth = [
            sibling_values
            for sibling_values in ordered_sibling_wealth
            if sibling_values[0] > current_birth_position
        ]

        if older_sibling_wealth and younger_sibling_wealth:
            older_wealth = older_sibling_wealth[-1][1]
            younger_wealth = younger_sibling_wealth[0][1]

            if older_wealth != younger_wealth:
                wealth_minimum = max(
                    wealth_minimum,
                    min(older_wealth, younger_wealth),
                )
                wealth_maximum = min(
                    wealth_maximum,
                    max(older_wealth, younger_wealth),
                )
        elif len(older_sibling_wealth) >= 2:
            nearest_older_wealth = older_sibling_wealth[-1][1]
            previous_distinct_wealth = None

            for sibling_values in reversed(
                older_sibling_wealth[:-1]
            ):
                if sibling_values[1] != nearest_older_wealth:
                    previous_distinct_wealth = sibling_values[1]
                    break

            if previous_distinct_wealth is not None:
                if nearest_older_wealth < previous_distinct_wealth:
                    wealth_maximum = min(
                        wealth_maximum,
                        nearest_older_wealth,
                    )
                else:
                    wealth_minimum = max(
                        wealth_minimum,
                        nearest_older_wealth,
                    )
        elif len(younger_sibling_wealth) >= 2:
            nearest_younger_wealth = younger_sibling_wealth[0][1]
            next_distinct_wealth = None

            for sibling_values in younger_sibling_wealth[1:]:
                if sibling_values[1] != nearest_younger_wealth:
                    next_distinct_wealth = sibling_values[1]
                    break

            if next_distinct_wealth is not None:
                if next_distinct_wealth < nearest_younger_wealth:
                    wealth_minimum = max(
                        wealth_minimum,
                        nearest_younger_wealth,
                    )
                else:
                    wealth_maximum = min(
                        wealth_maximum,
                        nearest_younger_wealth,
                    )

    randomized_values = {}

    for field_name in PARENTAL_VALUE_NAMES:
        randomized_delta = random.choices(
            PARENTAL_SLIGHT_DELTA_OPTIONS,
            weights=PARENTAL_SLIGHT_DELTA_WEIGHTS,
            k=1,
        )[0]
        randomized_values[field_name] = max(
            PARENTAL_VALUE_MINIMUM,
            min(
                PARENTAL_VALUE_MAXIMUM,
                family_values[field_name] + randomized_delta,
            ),
        )

        if field_name == "wealth":
            randomized_values[field_name] = max(
                wealth_minimum,
                min(
                    wealth_maximum,
                    randomized_values[field_name],
                ),
            )

    if all(
        randomized_values[field_name] == family_values[field_name]
        for field_name in PARENTAL_VALUE_NAMES
    ):
        changeable_fields = [
            field_name
            for field_name in PARENTAL_VALUE_NAMES
            if (
                field_name != "wealth"
                and (
                    family_values[field_name] > PARENTAL_VALUE_MINIMUM
                    or family_values[field_name] < PARENTAL_VALUE_MAXIMUM
                )
            )
            or (
                field_name == "wealth"
                and (
                    wealth_minimum < family_values[field_name]
                    or wealth_maximum > family_values[field_name]
                )
            )
        ]

        if changeable_fields:
            field_name = random.choice(changeable_fields)

            if (
                field_name == "wealth"
                and wealth_maximum == family_values[field_name]
            ):
                randomized_values[field_name] = (
                    family_values[field_name] - 1
                )
            else:
                randomized_values[field_name] = (
                    family_values[field_name] + 1
                    if (
                        field_name == "wealth"
                        and wealth_maximum > family_values[field_name]
                    )
                    or (
                        field_name != "wealth"
                        and family_values[field_name]
                        < PARENTAL_VALUE_MAXIMUM
                    )
                    else family_values[field_name] - 1
                )

    return build_parental_values(
        randomized_values,
        mode=normalized_mode,
        source="slightly randomized",
        family_values=family_values,
    )


def rebase_parental_values(person, people, current_values):
    normalized_current = normalize_parental_values(current_values)

    if normalized_current is None:
        return None

    family_values = family_parental_base(
        person,
        people,
        excluded_record_id=(
            person.get("record_id")
            if isinstance(person, dict)
            else ""
        ),
    )

    if family_values is None:
        return normalized_current

    mode = normalized_current["mode"]

    if mode in (
        PARENTAL_MODE_OVERRIDE,
        PARENTAL_MODE_FULLY_RANDOMIZED,
    ):
        return build_parental_values(
            normalized_current,
            mode=mode,
            source=normalized_current["source"],
            family_values=family_values,
        )

    if mode == PARENTAL_MODE_SHARED:
        return build_parental_values(
            family_values,
            mode=mode,
            source="sibling",
            family_values=family_values,
        )

    adjusted_values = {}

    for field_name in PARENTAL_VALUE_NAMES:
        previous_delta = (
            normalized_current[field_name]
            - normalized_current["family_values"][field_name]
        )
        adjusted_values[field_name] = max(
            PARENTAL_VALUE_MINIMUM,
            min(
                PARENTAL_VALUE_MAXIMUM,
                family_values[field_name] + previous_delta,
            ),
        )

    return build_parental_values(
        adjusted_values,
        mode=mode,
        source="slightly randomized",
        family_values=family_values,
    )


def synchronized_family_parental_values(
    anchor_person,
    people,
    prefer_anchor=False,
):
    if not isinstance(anchor_person, dict):
        return {}

    family_key = parental_family_key(anchor_person)
    anchor_values = normalize_parental_values(
        anchor_person.get("parental_values")
    )

    if family_key is None or anchor_values is None:
        return {}

    anchor_id = str(anchor_person.get("record_id", "") or "")
    family_values = None

    if not prefer_anchor:
        family_values = family_parental_base(
            anchor_person,
            people,
            excluded_record_id=anchor_id,
        )

    if family_values is None:
        family_values = (
            {
                field_name: anchor_values[field_name]
                for field_name in PARENTAL_VALUE_NAMES
            }
            if anchor_values["mode"] == PARENTAL_MODE_OVERRIDE
            else deepcopy(anchor_values["family_values"])
        )

    synchronized_values = {}

    for candidate in people:
        if not isinstance(candidate, dict):
            continue

        candidate_id = str(candidate.get("record_id", "") or "")

        if not candidate_id or parental_family_key(candidate) != family_key:
            continue

        candidate_values = normalize_parental_values(
            candidate.get("parental_values")
        )

        if candidate_values is None:
            continue

        mode = candidate_values["mode"]

        if mode in (
            PARENTAL_MODE_OVERRIDE,
            PARENTAL_MODE_FULLY_RANDOMIZED,
        ):
            synchronized = build_parental_values(
                candidate_values,
                mode=mode,
                source=candidate_values["source"],
                family_values=family_values,
            )
        elif mode == PARENTAL_MODE_SHARED:
            synchronized = build_parental_values(
                family_values,
                mode=mode,
                source="sibling",
                family_values=family_values,
            )
        else:
            adjusted_values = {}

            for field_name in PARENTAL_VALUE_NAMES:
                previous_delta = (
                    candidate_values[field_name]
                    - candidate_values["family_values"][field_name]
                )
                adjusted_values[field_name] = max(
                    PARENTAL_VALUE_MINIMUM,
                    min(
                        PARENTAL_VALUE_MAXIMUM,
                        family_values[field_name] + previous_delta,
                    ),
                )

            synchronized = build_parental_values(
                adjusted_values,
                mode=mode,
                source="slightly randomized",
                family_values=family_values,
            )

        synchronized_values[candidate_id] = synchronized

    return synchronized_values
