import random
from copy import deepcopy

from mage_maker.sections.development.initial_values import (
    BLOOD_STATUS_HALFBLOOD,
    BLOOD_STATUS_MUGGLEBORN,
    BLOOD_STATUS_PUREBLOOD,
    DEVELOPMENTAL_ENVIRONMENT_MAGICAL,
    DEVELOPMENTAL_ENVIRONMENT_MUGGLE,
    normalize_blood_status,
    normalize_developmental_environment,
    normalize_parental_values,
)
from mage_maker.sections.development.models import (
    DEVELOPMENT_ABILITY_BY_SKILL,
    DEVELOPMENT_SKILL_OPTIONS,
    DEVELOPMENT_SKILLS_BY_ABILITY,
    normalize_development_plan,
    normalize_development_skill,
)
from mage_maker.sections.development.traits import (
    TRAIT_DEFINITIONS,
    TRAIT_NAMES,
    normalize_trait_name,
)


INITIAL_SELECTION_AUTOMATIC = "automatic"
INITIAL_SELECTION_MANUAL = "manual"
INITIAL_SELECTION_MODES = (
    INITIAL_SELECTION_AUTOMATIC,
    INITIAL_SELECTION_MANUAL,
)
MUGGLES_INITIAL_SKILL_BONUS = 11
FRUGAL_ALLOWANCE_BONUS = 9
SICKLES_PER_GALLEON = 17
STRATEGY_PREFERENCE_PROBABILITY = 0.90
SCHEMA_SKILLS = {
    "Material Crafting": (
        "Artificing",
        "Alchemy",
    ),
    "Ingredient Crafting": (
        "Herbology",
        "Potions",
        "Creatures",
    ),
    "Spell-crafting": (
        "Charms",
        "Transfiguration",
        "Defense",
        "Dark Arts",
    ),
}
SCHEMA_ABILITIES = {
    "Material Crafting": (
        "Panache",
    ),
    "Ingredient Crafting": (
        "Naturalism",
    ),
    "Spell-crafting": (
        "Power",
    ),
}
SOCIAL_SKILLS = (
    "Social",
    "Perception",
    "Muggles",
)
ABILITY_SKILLS = DEVELOPMENT_SKILLS_BY_ABILITY
SCHEMA_TRAITS = {
    "Material Crafting": (
        "Inventive",
        "Crafty",
    ),
    "Ingredient Crafting": (
        "Green thumb",
        "Animal lover",
        "Environmentalist",
    ),
    "Spell-crafting": (
        "Crafty",
    ),
    "Social": (
        "People person",
        "Observant",
        "Caring",
        "Needler",
        "Controlling",
        "Supportive",
        "Secretive",
    ),
}
ABILITY_TRAITS = {
    "Power": (
        "Protective",
        "Caring",
        "Environmentalist",
        "Needler",
        "Contrarian",
        "Resistant",
        "Controlling",
        "Supportive",
        "Ouster",
        "Secretive",
        "Crafty",
    ),
    "Erudition": (
        "Bookworm",
        "Curious",
        "Runologist",
    ),
    "Panache": (
        "Navigator",
        "Green thumb",
        "Inventive",
    ),
    "Naturalism": (
        "Star gazer",
        "Animal lover",
        "People person",
        "Clairvoyant",
        "Observant",
    ),
}


def normalize_initial_selection_mode(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().split()
    )
    aliases = {
        "": INITIAL_SELECTION_AUTOMATIC,
        "auto": INITIAL_SELECTION_AUTOMATIC,
        "automatic": INITIAL_SELECTION_AUTOMATIC,
        "random": INITIAL_SELECTION_AUTOMATIC,
        "manual": INITIAL_SELECTION_MANUAL,
        "selected": INITIAL_SELECTION_MANUAL,
    }
    mode = aliases.get(normalized_value)

    if mode is None:
        valid_values = ", ".join(INITIAL_SELECTION_MODES)
        raise ValueError(
            f"Initial selection mode must be one of: {valid_values}."
        )

    return mode


def normalize_initial_bonus_skills(value):
    if value in (None, ""):
        candidate_values = []
    elif isinstance(value, str):
        candidate_values = [value]
    elif isinstance(value, (list, tuple)):
        candidate_values = list(value)
    else:
        raise TypeError("Initial skill bonuses must be a list.")

    normalized_skills = []

    for candidate_value in candidate_values:
        skill = normalize_development_skill(candidate_value)
        normalized_skills.append(skill)

    return normalized_skills


def normalize_initial_traits(value):
    if value in (None, ""):
        candidate_values = []
    elif isinstance(value, str):
        candidate_values = [value]
    elif isinstance(value, (list, tuple)):
        candidate_values = list(value)
    else:
        raise TypeError("Initial traits must be a list.")

    normalized_traits = []

    for candidate_value in candidate_values:
        trait_name = normalize_trait_name(candidate_value)

        if trait_name not in normalized_traits:
            normalized_traits.append(trait_name)

    return normalized_traits


def summarize_initial_skill_bonuses(value):
    normalized_skills = normalize_initial_bonus_skills(value)
    bonus_counts = {}

    for skill in normalized_skills:
        bonus_counts[skill] = bonus_counts.get(skill, 0) + 1

    return ", ".join(
        f"{skill} +{amount}"
        for skill, amount in bonus_counts.items()
    )


def normalize_initial_bonuses(value, allow_uninitialized=True):
    if value in (None, "", {}):
        if allow_uninitialized:
            return None

        raise ValueError("Initial bonuses have not been assigned.")

    if not isinstance(value, dict):
        raise TypeError("Initial bonuses must be a dictionary.")

    if value.get("initialized") is False:
        if allow_uninitialized:
            return None

        raise ValueError("Initial bonuses have not been assigned.")

    return {
        "initialized": True,
        "skill_selection_mode": normalize_initial_selection_mode(
            value.get("skill_selection_mode")
        ),
        "trait_selection_mode": normalize_initial_selection_mode(
            value.get("trait_selection_mode")
        ),
        "skill_bonuses": normalize_initial_bonus_skills(
            value.get("skill_bonuses", [])
        ),
        "traits": normalize_initial_traits(
            value.get("traits", [])
        ),
    }


def initial_bonus_requirements(
    blood_status,
    developmental_environment="",
    parental_values=None,
):
    normalized_blood_status = normalize_blood_status(blood_status)
    normalized_environment = normalize_developmental_environment(
        developmental_environment,
        normalized_blood_status,
    )
    base_values = {
        BLOOD_STATUS_PUREBLOOD: {
            "skill_bonus_count": 3,
            "trait_count": 0,
            "muggles_skill_bonus": 0,
        },
        BLOOD_STATUS_HALFBLOOD: {
            "skill_bonus_count": (
                2
                if normalized_environment
                == DEVELOPMENTAL_ENVIRONMENT_MAGICAL
                else 1
            ),
            "trait_count": (
                1
                if normalized_environment
                == DEVELOPMENTAL_ENVIRONMENT_MAGICAL
                else 2
            ),
            "muggles_skill_bonus": (
                0
                if normalized_environment
                == DEVELOPMENTAL_ENVIRONMENT_MAGICAL
                else MUGGLES_INITIAL_SKILL_BONUS
            ),
        },
        BLOOD_STATUS_MUGGLEBORN: {
            "skill_bonus_count": 0,
            "trait_count": 3,
            "muggles_skill_bonus": MUGGLES_INITIAL_SKILL_BONUS,
        },
    }[normalized_blood_status]
    normalized_parental_values = normalize_parental_values(
        parental_values
    )
    trait_adjustment = 0

    if normalized_parental_values is not None:
        permissiveness = normalized_parental_values[
            "permissiveness"
        ]

        if permissiveness >= 7:
            trait_adjustment = 1
        elif permissiveness <= 3:
            trait_adjustment = -1

    requirements = deepcopy(base_values)
    requirements["trait_count"] = max(
        0,
        requirements["trait_count"] + trait_adjustment,
    )
    return requirements


def preferred_development_skills(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    schema = plan["schema"]

    if plan.get("focused_skills"):
        return list(plan["focused_skills"])

    if schema in SCHEMA_SKILLS:
        return list(SCHEMA_SKILLS[schema])

    if schema == "Social":
        return list(SOCIAL_SKILLS)

    if schema == "Ability-focus":
        return list(
            ABILITY_SKILLS.get(
                plan.get("focused_ability"),
                (),
            )
        )

    return []


def preferred_development_traits(development_plan):
    plan = normalize_development_plan(
        development_plan,
        default_schema="Scattershot",
    )
    preferred_skills = preferred_development_skills(plan)
    preferred_traits = []

    for definition in TRAIT_DEFINITIONS:
        skill_bonus = str(
            definition.get("skill_bonus", "") or ""
        ).strip()

        if not skill_bonus:
            continue

        try:
            normalized_skill = normalize_development_skill(
                skill_bonus
            )
        except ValueError:
            continue

        if (
            normalized_skill in preferred_skills
            and definition["name"] not in preferred_traits
        ):
            preferred_traits.append(definition["name"])

    preferred_abilities = []

    if plan["schema"] in (
        "One skill",
        "Two skill",
        "Three skills",
    ):
        for skill in preferred_skills:
            ability = DEVELOPMENT_ABILITY_BY_SKILL.get(skill)

            if ability and ability not in preferred_abilities:
                preferred_abilities.append(ability)
    elif plan["schema"] == "Ability-focus":
        focused_ability = plan.get("focused_ability")

        if focused_ability and focused_ability not in preferred_abilities:
            preferred_abilities.append(focused_ability)

    for ability in preferred_abilities:
        for trait_name in ABILITY_TRAITS.get(ability, ()):
            if trait_name not in preferred_traits:
                preferred_traits.append(trait_name)

    for trait_name in SCHEMA_TRAITS.get(plan["schema"], ()):
        if trait_name not in preferred_traits:
            preferred_traits.append(trait_name)

    return preferred_traits


def randomized_initial_skills(
    development_plan,
    required_count,
    existing_skills=None,
):
    selected_skills = normalize_initial_bonus_skills(
        existing_skills
    )
    selected_skills = selected_skills[:required_count]
    preferred_skills = preferred_development_skills(
        development_plan
    )

    while len(selected_skills) < required_count:
        random_skills = [
            skill
            for skill in DEVELOPMENT_SKILL_OPTIONS
            if skill not in preferred_skills
        ]
        use_preferred = (
            bool(preferred_skills)
            and random.random() < STRATEGY_PREFERENCE_PROBABILITY
        )
        selected_skills.append(
            random.choice(
                preferred_skills
                if use_preferred
                else random_skills or DEVELOPMENT_SKILL_OPTIONS
            )
        )

    return selected_skills


def randomized_initial_traits(
    development_plan,
    required_count,
    existing_traits=None,
):
    selected_traits = normalize_initial_traits(existing_traits)
    selected_traits = selected_traits[:required_count]
    preferred_traits = preferred_development_traits(
        development_plan
    )

    while len(selected_traits) < required_count:
        available_traits = [
            trait_name
            for trait_name in TRAIT_NAMES
            if trait_name not in selected_traits
        ]
        available_preferred_traits = [
            trait_name
            for trait_name in preferred_traits
            if trait_name in available_traits
        ]
        available_random_traits = [
            trait_name
            for trait_name in available_traits
            if trait_name not in preferred_traits
        ]
        use_preferred = (
            bool(available_preferred_traits)
            and random.random() < STRATEGY_PREFERENCE_PROBABILITY
        )
        selected_traits.append(
            random.choice(
                available_preferred_traits
                if use_preferred
                else available_random_traits or available_traits
            )
        )

    return selected_traits


def initialize_initial_bonuses(person, development_plan):
    person_values = person if isinstance(person, dict) else {}
    requirements = initial_bonus_requirements(
        person_values.get("blood_status"),
        person_values.get("developmental_environment"),
        person_values.get("parental_values"),
    )
    return normalize_initial_bonuses(
        {
            "initialized": True,
            "skill_selection_mode": INITIAL_SELECTION_AUTOMATIC,
            "trait_selection_mode": INITIAL_SELECTION_AUTOMATIC,
            "skill_bonuses": randomized_initial_skills(
                development_plan,
                requirements["skill_bonus_count"],
            ),
            "traits": randomized_initial_traits(
                development_plan,
                requirements["trait_count"],
            ),
        },
        allow_uninitialized=False,
    )


def reconcile_initial_bonuses(
    value,
    person,
    development_plan,
    refresh_automatic=False,
):
    normalized_bonuses = normalize_initial_bonuses(value)

    if normalized_bonuses is None:
        return initialize_initial_bonuses(
            person,
            development_plan,
        )

    person_values = person if isinstance(person, dict) else {}
    requirements = initial_bonus_requirements(
        person_values.get("blood_status"),
        person_values.get("developmental_environment"),
        person_values.get("parental_values"),
    )
    retained_skills = (
        []
        if (
            refresh_automatic
            and normalized_bonuses["skill_selection_mode"]
            == INITIAL_SELECTION_AUTOMATIC
        )
        else normalized_bonuses["skill_bonuses"]
    )
    retained_traits = (
        []
        if (
            refresh_automatic
            and normalized_bonuses["trait_selection_mode"]
            == INITIAL_SELECTION_AUTOMATIC
        )
        else normalized_bonuses["traits"]
    )
    normalized_bonuses["skill_bonuses"] = (
        randomized_initial_skills(
            development_plan,
            requirements["skill_bonus_count"],
            retained_skills,
        )
    )
    normalized_bonuses["traits"] = randomized_initial_traits(
        development_plan,
        requirements["trait_count"],
        retained_traits,
    )
    return normalize_initial_bonuses(
        normalized_bonuses,
        allow_uninitialized=False,
    )


def allowance_sickles(parental_values, traits=None):
    normalized_parental_values = normalize_parental_values(
        parental_values
    )

    if normalized_parental_values is None:
        return None

    selected_traits = normalize_initial_traits(traits)
    allowance = (
        normalized_parental_values["generosity"]
        * normalized_parental_values["wealth"]
    )

    if "Frugal" in selected_traits:
        allowance += FRUGAL_ALLOWANCE_BONUS

    return allowance


def starting_allowance_sickles(parental_values):
    normalized_parental_values = normalize_parental_values(
        parental_values
    )

    if normalized_parental_values is None:
        return None

    return (
        normalized_parental_values["generosity"]
        * normalized_parental_values["wealth"]
        * SICKLES_PER_GALLEON
    )


def format_wizard_currency(sickles):
    if sickles is None:
        return "Not assigned"

    normalized_sickles = max(0, int(sickles))

    if normalized_sickles <= SICKLES_PER_GALLEON:
        unit = "sickle" if normalized_sickles == 1 else "sickles"
        return f"{normalized_sickles} {unit}"

    galleons, remaining_sickles = divmod(
        normalized_sickles,
        SICKLES_PER_GALLEON,
    )
    galleon_unit = (
        "Galleon" if galleons == 1 else "Galleons"
    )

    if remaining_sickles == 0:
        return f"{galleons} {galleon_unit}"

    sickle_unit = (
        "sickle" if remaining_sickles == 1 else "sickles"
    )
    return (
        f"{galleons} {galleon_unit} and "
        f"{remaining_sickles} {sickle_unit}"
    )
