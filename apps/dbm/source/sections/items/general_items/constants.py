GENERAL_ITEM_TYPES = (
    "General Item",
    "Raw Material",
    "Charm Item",
    "Transfigurative Item",
    "Defensive Item",
    "Dark Arts Item",
    "Arithmancy Item",
    "Runic Item",
    "Historical Item",
    "Muggle Item",
    "Potioning Item",
    "Alchemical Item",
    "Artificing Item",
    "Flying Item",
    "Herbological Item",
    "Creature Item",
    "Astronomical Item",
    "Divinatory Item",
    "Perception Item",
    "Social Item",
    "Broom",
    "Flyable",
    "Instrument",
    "Magical Artifact",
    "Tool & Supply",
    "Other",
)

GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME = {
    item_type.casefold(): item_type for item_type in GENERAL_ITEM_TYPES
}
GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME.update({
    "raw material": "Raw Material",
    "alchemical": "Alchemical Item",
    "divination": "Divinatory Item",
    "ritual item": "General Item",
})
