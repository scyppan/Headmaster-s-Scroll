from copy import deepcopy


TRAIT_DEFINITIONS = (
    {
        "name": "Star gazer",
        "type": "Skill",
        "skill_bonus": "Astronomy",
        "subtype_bonus": "",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16681",
        "source_key": "12fc0",
    },
    {
        "name": "Bookworm",
        "type": "Skill",
        "skill_bonus": "History of Magic",
        "subtype_bonus": "",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16682",
        "source_key": "o7xq4",
    },
    {
        "name": "Animal lover",
        "type": "Skill",
        "skill_bonus": "Creatures",
        "subtype_bonus": "",
        "amount": 1,
        "ancillary_effect": "",
        "source_id": "16683",
        "source_key": "fc8kw",
    },
    {
        "name": "People person",
        "type": "Skill",
        "skill_bonus": "Social",
        "subtype_bonus": "",
        "amount": 1,
        "ancillary_effect": "",
        "source_id": "16684",
        "source_key": "k7uky",
    },
    {
        "name": "Clairvoyant",
        "type": "Skill",
        "skill_bonus": "Divination",
        "subtype_bonus": "",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16685",
        "source_key": "j3re0",
    },
    {
        "name": "Navigator",
        "type": "Skill",
        "skill_bonus": "Flying",
        "subtype_bonus": "",
        "amount": 2,
        "ancillary_effect": "",
        "source_id": "16686",
        "source_key": "l9987",
    },
    {
        "name": "Observant",
        "type": "Skill",
        "skill_bonus": "Perception",
        "subtype_bonus": "",
        "amount": 1,
        "ancillary_effect": "",
        "source_id": "16687",
        "source_key": "rqt0b",
    },
    {
        "name": "Green thumb",
        "type": "Skill",
        "skill_bonus": "Herbology",
        "subtype_bonus": "",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16688",
        "source_key": "ujlx3",
    },
    {
        "name": "Frugal",
        "type": "Ancillary",
        "skill_bonus": "",
        "subtype_bonus": "",
        "amount": None,
        "ancillary_effect": (
            "+9 sickles per month to your allowance under 17; "
            "+2 Galleons per month to your salary when employed and "
            "17 or older"
        ),
        "source_id": "16689",
        "source_key": "au1s6",
    },
    {
        "name": "Curious",
        "type": "Skill",
        "skill_bonus": "Arithmancy",
        "subtype_bonus": "",
        "amount": 1,
        "ancillary_effect": "",
        "source_id": "16690",
        "source_key": "ulnft",
    },
    {
        "name": "Inventive",
        "type": "Skill",
        "skill_bonus": "Artificing",
        "subtype_bonus": "",
        "amount": 1,
        "ancillary_effect": "",
        "source_id": "16691",
        "source_key": "f8ap5",
    },
    {
        "name": "Runologist",
        "type": "Skill",
        "skill_bonus": "Runes",
        "subtype_bonus": "",
        "amount": 2,
        "ancillary_effect": "",
        "source_id": "16692",
        "source_key": "xgbza",
    },
    {
        "name": "Protective",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Shielding",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16693",
        "source_key": "my8vg",
    },
    {
        "name": "Caring",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Healing",
        "amount": 2,
        "ancillary_effect": "",
        "source_id": "16694",
        "source_key": "gbcjh",
    },
    {
        "name": "Environmentalist",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Environmental",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16695",
        "source_key": "q46sw",
    },
    {
        "name": "Needler",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Mental",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16696",
        "source_key": "7qk9g",
    },
    {
        "name": "Contrarian",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Counterspell",
        "amount": 2,
        "ancillary_effect": "",
        "source_id": "16697",
        "source_key": "ny2ie",
    },
    {
        "name": "Resistant",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Repelling",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16698",
        "source_key": "x2a8k",
    },
    {
        "name": "Controlling",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Controlling",
        "amount": 2,
        "ancillary_effect": "",
        "source_id": "16699",
        "source_key": "rcfv4",
    },
    {
        "name": "Supportive",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Enhancing",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16700",
        "source_key": "74mwz",
    },
    {
        "name": "Ouster",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Banishing",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16701",
        "source_key": "nx9o7",
    },
    {
        "name": "Secretive",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Concealing",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16702",
        "source_key": "6pacd",
    },
    {
        "name": "Crafty",
        "type": "Subtype",
        "skill_bonus": "",
        "subtype_bonus": "Enchanting",
        "amount": 3,
        "ancillary_effect": "",
        "source_id": "16703",
        "source_key": "lp7af",
    },
)

TRAIT_NAMES = tuple(
    trait_definition["name"]
    for trait_definition in TRAIT_DEFINITIONS
)


def normalize_trait_name(value):
    normalized_value = " ".join(
        str(value or "").strip().casefold().split()
    )
    names = {
        trait_name.casefold(): trait_name
        for trait_name in TRAIT_NAMES
    }
    trait_name = names.get(normalized_value)

    if trait_name is None:
        valid_values = ", ".join(TRAIT_NAMES)
        raise ValueError(
            f"Trait must be one of: {valid_values}."
        )

    return trait_name


def trait_definition(value):
    trait_name = normalize_trait_name(value)

    for definition in TRAIT_DEFINITIONS:
        if definition["name"] == trait_name:
            return deepcopy(definition)

    raise ValueError(f"Unknown trait: {trait_name}.")


def trait_effect_text(value):
    definition = (
        trait_definition(value)
        if not isinstance(value, dict)
        else deepcopy(value)
    )
    ancillary_effect = str(
        definition.get("ancillary_effect", "") or ""
    ).strip()

    if ancillary_effect:
        return ancillary_effect

    amount = definition.get("amount")
    skill_bonus = str(
        definition.get("skill_bonus", "") or ""
    ).strip()
    subtype_bonus = str(
        definition.get("subtype_bonus", "") or ""
    ).strip()

    if skill_bonus:
        return f"+{amount} {skill_bonus} skill"

    if subtype_bonus:
        return f"+{amount} {subtype_bonus} subtype"

    return "No effect is recorded."
