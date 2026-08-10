WOUND_TYPES = (
    "Cuts/Scratches",
    "Abrasions/Scrapes",
    "Slashes/Gashes",
    "Punctures/Piercing",
    "Gouges",
    "Burns",
    "Disease/Toxic",
    "Blunt force/Crushing",
    "Despairing/Depressing",
    "Terror/Anxiety-inducing",
    "Sanity-shaking",
    "Eruption/Explosion",
    "Vital",
)

WOUND_SEVERITIES = (
    "Light",
    "Medium",
    "Heavy",
)

UNDEFINED = "{undefined}"

WOUND_TYPE_OPTIONS = (UNDEFINED, *WOUND_TYPES)
WOUND_SEVERITY_OPTIONS = (UNDEFINED, *WOUND_SEVERITIES)

WOUND_AMOUNT_LIMITS = {
    "Light": 2,
    "Medium": 1,
    "Heavy": 50,
}
