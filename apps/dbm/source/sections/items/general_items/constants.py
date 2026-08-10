GENERAL_ITEM_TYPES = (
    "Alchemical",
    "Broom",
    "Divination",
    "Instrument",
    "Magical Artifact",
    "Muggle Item",
    "Ritual Item",
    "Tool & Supply",
    "Other",
)

GENERAL_ITEM_TYPES_BY_NORMALIZED_NAME = {
    item_type.casefold(): item_type for item_type in GENERAL_ITEM_TYPES
}
