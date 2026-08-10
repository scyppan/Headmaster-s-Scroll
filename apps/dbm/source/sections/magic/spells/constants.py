SPELL_SKILLS = (
    "Charms",
    "Transfiguration",
    "Defense",
    "Dark Arts",
)

SPELL_SKILLS_BY_NORMALIZED_NAME = {
    skill.casefold(): skill for skill in SPELL_SKILLS
}


SPELL_SUBTYPE_DESCRIPTIONS = {
    "Hex": "",
    "Curse": "",
    "Blood Magic": "",
    "Controlling": (
        "Controlling spells block one's movement or affect their ability "
        "to do things."
    ),
    "Banishing": "These spells cast spirits or beings away from an area.",
    "Mental": (
        "These are spells that affect your cognitions or emotion in a "
        "non-damaging or healing way. Use Enhancing category if the "
        "effect is clearly a buff."
    ),
    "Concealing": (
        "Conceals, erases, and blocks some important information, "
        "history, effect or other property"
    ),
    "Utility": (
        "Filling, removing, or cleaning something. Also applies to "
        "simple mending"
    ),
    "Enchanting": "",
    "Alteration": (
        "Changes some physical property of the object (or slightly "
        "changing its form), as in having it stick to something, become "
        "generally sticky or springy or slippery, or morph in its general "
        "rigidity or pliability. Distinct from transfiguration in that it "
        "does not involve changing the shape of the object substantially."
    ),
    "Healing": "",
    "Enhancing": "",
    "Environmental": (
        "Environmental spells are spells that affect some aspect of the "
        "environment, such as the weather, temperature, wind, rain, etc."
    ),
    "Jinx": "",
    "Shielding": (
        "Puts some sort of a shield in the way of incoming damage or "
        "attack. Can also be used for concealment"
    ),
    "Repelling": "",
    "Counterspell": "",
}

SPELL_SUBTYPES = tuple(SPELL_SUBTYPE_DESCRIPTIONS)
SPELL_SUBTYPES_BY_NORMALIZED_NAME = {
    subtype.casefold(): subtype for subtype in SPELL_SUBTYPES
}
